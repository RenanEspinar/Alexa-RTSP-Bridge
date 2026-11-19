#!/usr/bin/env python3
"""Carga sostenida RTSP -> HLS para Alexa RTSP Bridge Pro Max v0.2.0b1.

Se ejecuta en Ubuntu (host Docker). No modifica cámaras, Docker ni AWS.
No registra URLs RTSP, claves, tokens CSRF ni URLs HLS firmadas.

Uso: python3 benchmark_sostenido.py --concurrency all --duration 60
     python3 benchmark_sostenido.py --concurrency 8 --duration 60
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
from datetime import datetime, timezone
import json
import os
import platform
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

DEFAULT_ORDER = (
    'solario', 'jardin', 'pasillo', 'estacionamiento',
    'calle_kantutas_a', 'calle_kantutas_b',
    'calle_gladiolos_a', 'calle_gladiolos_b',
)
MB = 1024 * 1024


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def get_json(url, csrf=None):
    headers = {'Content-Type': 'application/json'} if csrf else {}
    if csrf:
        headers['X-Bridge-CSRF'] = csrf
    req = Request(url, data=b'{}' if csrf else None, headers=headers)
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def get_available_kib():
    try:
        line = next(line for line in Path('/proc/meminfo').read_text().splitlines()
                    if line.startswith('MemAvailable:'))
        return int(line.split()[1])
    except (OSError, StopIteration, ValueError):
        return -1


def parse_memory(text):
    match = re.match(r'\s*([\d.,]+)\s*(B|KiB|MiB|GiB|TiB)', text)
    if not match:
        raise ValueError('Formato Docker RAM inesperado')
    value = float(match[1].replace(',', '.'))
    return round(value * {'B': 1/MB, 'KiB': 1/1024, 'MiB': 1,
                          'GiB': 1024, 'TiB': 1024*1024}[match[2]], 3)


def docker_sample(container):
    cmd = ['docker', 'stats', '--no-stream', '--format',
           '{{.CPUPerc}}|{{.MemUsage}}', container]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12, check=True)
    line = proc.stdout.strip().splitlines()[0]
    cpu, memory = line.split('|', 1)
    return float(cpu.strip().strip('%').replace(',', '.')), parse_memory(memory)


def sampler(container, begin, stop, phase, samples, flags, max_cpu, min_mem_mib):
    consecutive_high = 0
    while not stop.is_set():
        try:
            cpu, mem = docker_sample(container)
            free_kib = get_available_kib()
            samples.append({'utc': now_iso(), 'elapsed_s': round(time.monotonic() - begin, 3),
                            'phase': phase[0], 'cpu_docker_pct': cpu, 'mem_mib': mem,
                            'mem_host_available_mib': round(free_kib / 1024, 1) if free_kib >= 0 else ''})
            consecutive_high = consecutive_high + 1 if cpu > max_cpu else 0
            if consecutive_high >= 3:
                flags.append('CPU Docker > umbral durante tres muestras')
                stop.set()
            if free_kib >= 0 and free_kib < min_mem_mib * 1024:
                flags.append('Memoria disponible del host < umbral')
                stop.set()
        except (IndexError, ValueError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired, OSError):
            samples.append({'utc': now_iso(), 'elapsed_s': round(time.monotonic() - begin, 3),
                            'phase': phase[0], 'cpu_docker_pct': '', 'mem_mib': '',
                            'mem_host_available_mib': ''})
        stop.wait(1.0)


def check_ts(data):
    if len(data) < 188 * 3 or len(data) % 188:
        raise ValueError('Tamaño MPEG-TS inválido')
    if any(data[i] != 0x47 for i in range(0, min(len(data), 188*12), 188)):
        raise ValueError('Sincronización MPEG-TS inválida')


def media_worker(slug, signed_path, base_url, barrier, stop, ready, started_at, poll):
    # Las URLs firmadas se usan solo en RAM y jamás se guardan en los informes.
    url = base_url + signed_path
    urlp = urlsplit(url)
    result = {'slug': slug, 'first_playlist_s': '', 'first_ts_s': '',
              'unique_segments': 0, 'ts_bytes': 0, 'playlist_requests': 0,
              'segment_requests': 0, 'http_errors': 0, 'other_errors': 0,
              'max_gap_new_ts_s': '', 'first_error_type': '', 'ready': False}
    seen = set()
    last_new_ts = None
    max_gap = 0.0
    barrier.wait(timeout=15)
    while not stop.is_set():
        try:
            req = Request(url, headers={'Cache-Control': 'no-cache'})
            with urlopen(req, timeout=25) as response:
                playlist = response.read(1024 * 1024).decode('utf-8')
            result['playlist_requests'] += 1
            if not playlist.startswith('#EXTM3U'):
                raise ValueError('Playlist inválida')
            if result['first_playlist_s'] == '':
                result['first_playlist_s'] = round(time.monotonic() - started_at, 3)
            segments = [ln.strip() for ln in playlist.splitlines()
                        if re.fullmatch(r'segment_\d+\.ts', ln.strip())]
            # Un único segmento nuevo por ciclo permite medir continuidad, no descargas masivas.
            new = [x for x in segments if x not in seen]
            if new:
                segment = new[-1]
                target = urljoin(url, segment)
                dest = urlsplit(target)
                if dest.netloc != urlp.netloc or not dest.path.startswith('/s/'):
                    raise ValueError('Segmento externo inesperado')
                result['segment_requests'] += 1
                with urlopen(target, timeout=15) as response:
                    content = response.read(4 * MB + 1)
                if len(content) > 4*MB:
                    raise ValueError('Segmento mayor que el límite del test')
                check_ts(content)
                seen.add(segment)
                result['unique_segments'] += 1
                result['ts_bytes'] += len(content)
                t = time.monotonic()
                if result['first_ts_s'] == '':
                    result['first_ts_s'] = round(t - started_at, 3)
                    result['ready'] = True
                    ready.set()
                if last_new_ts is not None:
                    max_gap = max(max_gap, t - last_new_ts)
                last_new_ts = t
        except (HTTPError, URLError) as exc:
            result['http_errors'] += 1
            if not result['first_error_type']:
                result['first_error_type'] = type(exc).__name__
        except (OSError, TimeoutError, ValueError, UnicodeError) as exc:
            result['other_errors'] += 1
            if not result['first_error_type']:
                result['first_error_type'] = type(exc).__name__
        stop.wait(poll)
    if last_new_ts is not None:
        max_gap = max(max_gap, time.monotonic() - last_new_ts)
    result['max_gap_new_ts_s'] = round(max_gap, 3) if last_new_ts is not None else ''
    return result


def write_csv(path, records, fields):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(records)


def wait_idle(admin_url, selected, grace=46):
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        try:
            states = get_json(admin_url + '/api/state')['status']
            active = [s for s in selected if states.get(s, {}).get('running')]
            if not active:
                return True, []
        except (KeyError, ValueError, URLError):
            pass
        time.sleep(2)
    try:
        states = get_json(admin_url + '/api/state')['status']
        return False, [s for s in selected if states.get(s, {}).get('running')]
    except (KeyError, ValueError, URLError):
        return False, ['ESTADO_NO_DISPONIBLE']


def run_stage(stage, selected, state, args, folder):
    label = f'{stage:02d}'
    print(f'\n=== {stage} cámara(s) | preparación + {args.duration}s sostenidos ===', flush=True)
    paths = {s: get_json(args.admin + '/api/sign/' + s, state['csrf'])['path']
             for s in selected}
    # Los slugs de cámaras se anonimizan en los archivos publicados.
    aliases = {s: f'camera_{DEFAULT_ORDER.index(s)+1:02d}' for s in selected}
    stop = threading.Event()
    phase = ['inicio']
    samples, flags = [], []
    start = time.monotonic()
    sensor = threading.Thread(target=sampler, args=(args.container, start, stop, phase,
                            samples, flags, args.max_cpu, args.min_host_mem), daemon=True)
    sensor.start()
    ready = {s: threading.Event() for s in selected}
    barrier = threading.Barrier(stage)
    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=stage) as pool:
            futures = {s: pool.submit(media_worker, s, paths[s], args.hls, barrier,
                                     stop, ready[s], start, args.poll) for s in selected}
            try:
                deadline = start + args.startup_timeout
                while not stop.is_set() and time.monotonic() < deadline:
                    if all(e.is_set() for e in ready.values()):
                        break
                    time.sleep(0.2)
                initial_ok = sum(e.is_set() for e in ready.values())
                phase[0] = 'sostenido'
                print(f'Segmento inicial válido: {initial_ok}/{stage}; iniciando ventana sostenida.', flush=True)
                end = time.monotonic() + args.duration
                while not stop.is_set() and time.monotonic() < end:
                    time.sleep(0.2)
            finally:
                # Al pulsar Ctrl+C, soltamos los workers antes de salir del executor.
                stop.set()
            for slug, future in futures.items():
                try:
                    row = future.result(timeout=35)
                except Exception as exc:
                    row = {'slug': slug, 'ready': False, 'first_playlist_s': '', 'first_ts_s': '',
                           'unique_segments': 0, 'ts_bytes': 0, 'playlist_requests': 0,
                           'segment_requests': 0, 'http_errors': 0, 'other_errors': 1,
                           'max_gap_new_ts_s': '', 'first_error_type': type(exc).__name__}
                row['camera_id'] = aliases[slug]
                row['concurrency'] = stage
                row['duration_target_s'] = args.duration
                results.append(row)
    finally:
        stop.set()
    sensor.join(timeout=15)
    # Guardar modo efectivo ANTES de que el watchdog elimine la sesión.
    statuses = get_json(args.admin + '/api/state')['status']
    for row in results:
        row['effective_mode'] = statuses.get(row['slug'], {}).get('mode', '')
        print(f"  {row['camera_id']} | 1er TS: {row['first_ts_s']} s | "
              f"TS válidos distintos: {row['unique_segments']} | "
              f"HTTP errors: {row['http_errors']} | {row['effective_mode']}", flush=True)
        row.pop('slug')
    idle_ok, active = wait_idle(args.admin, selected, args.cooldown)
    print('Apagado por inactividad:', 'OK' if idle_ok else f'NO confirmado ({len(active)} activos)')
    steady = [s for s in samples if s['phase'] == 'sostenido' and isinstance(s['cpu_docker_pct'], float)]
    cpu_values = [s['cpu_docker_pct'] for s in steady]
    mem_values = [s['mem_mib'] for s in steady]
    summary = {'concurrency': stage, 'target_sustained_s': args.duration,
               'streams_ready': initial_ok, 'streams_expected': stage,
               'streams_with_new_segments': sum(r['unique_segments'] > 1 for r in results),
               'total_unique_segments': sum(r['unique_segments'] for r in results),
               'http_errors': sum(r['http_errors'] for r in results),
               'other_errors': sum(r['other_errors'] for r in results),
               'cpu_avg_pct': round(statistics.mean(cpu_values), 2) if cpu_values else '',
               'cpu_peak_pct': round(max(cpu_values), 2) if cpu_values else '',
               'memory_peak_mib': round(max(mem_values), 2) if mem_values else '',
               'samples_steady': len(steady), 'all_idle_after': idle_ok,
               'aborted_by_guardrail': bool(flags), 'abort_reason': '; '.join(flags)}
    print(f"CPU sostenida prom.: {summary['cpu_avg_pct']} % | pico: {summary['cpu_peak_pct']} % | "
          f"RAM pico: {summary['memory_peak_mib']} MiB | muestras: {len(steady)}")
    write_csv(folder / f'samples_{label}.csv', samples,
              ['utc','elapsed_s','phase','cpu_docker_pct','mem_mib','mem_host_available_mib'])
    write_csv(folder / f'cameras_{label}.csv', results,
              ['concurrency','camera_id','duration_target_s','first_playlist_s','first_ts_s',
               'ready','effective_mode','unique_segments','ts_bytes','playlist_requests',
               'segment_requests','http_errors','other_errors','max_gap_new_ts_s','first_error_type'])
    return summary


def inspect_environment(container):
    result = {'os_kernel': platform.release(), 'machine_arch': platform.machine()}
    try:
        cpu_model = next((ln.split(':', 1)[1].strip() for ln in Path('/proc/cpuinfo').read_text().splitlines()
                          if ln.startswith('model name')), '')
        result['cpu_model'] = cpu_model
    except OSError:
        result['cpu_model'] = ''
    for key, command in (
        ('docker_version', ['docker', 'version', '--format', '{{.Server.Version}}']),
        ('container_image_id', ['docker', 'inspect', '-f', '{{.Image}}', container]),
        ('ffmpeg_version', ['docker', 'exec', container, 'ffmpeg', '-version']),
    ):
        try:
            out = subprocess.run(command, check=True, capture_output=True, text=True,
                                 timeout=10).stdout.strip()
            result[key] = out.splitlines()[0] if out else ''
        except (OSError, subprocess.SubprocessError):
            result[key] = 'not captured'
    return result


def main():
    p = argparse.ArgumentParser(description='Prueba sostenida Pro Max con URLs HLS firmadas locales')
    p.add_argument('--concurrency', choices=['1','4','8','all'], default='all')
    p.add_argument('--duration', type=int, default=60, help='Segundos sostenidos tras arranque (por etapa)')
    p.add_argument('--poll', type=float, default=0.8, help='Intervalo entre solicitudes por cámara')
    p.add_argument('--startup-timeout', type=int, default=45)
    p.add_argument('--cooldown', type=int, default=46)
    p.add_argument('--max-cpu', type=float, default=330, help='Aborta tras 3 muestras > este porcentaje')
    p.add_argument('--min-host-mem', type=int, default=750, help='MiB libres en host, guardarraíl')
    p.add_argument('--admin', default='http://127.0.0.1:18099')
    p.add_argument('--hls', default='http://127.0.0.1:18090')
    p.add_argument('--container', default='alexa_rtsp_bridge_pro_beta')
    p.add_argument('--out', default=str(Path.home() / 'alexa-promax-resultados'))
    args = p.parse_args()
    if args.duration < 15 or args.duration > 300:
        p.error('El intervalo permitido es 15–300 segundos')
    if args.poll < 0.25 or args.poll > 5:
        p.error('Intervalo poll permitido: 0.25–5 segundos')
    state = get_json(args.admin + '/api/state')
    existing = {c['slug'] for c in state['cameras']}
    order = [s for s in DEFAULT_ORDER if s in existing]
    stages = [1,4,8] if args.concurrency == 'all' else [int(args.concurrency)]
    if len(order) < max(stages):
        raise SystemExit(f'Cámaras disponibles: {len(order)}; se requieren {max(stages)}')
    # No interferir si una cámara ya está usándose.
    running = [s for s in order if state['status'].get(s, {}).get('running')]
    if running:
        raise SystemExit(f'Hay {len(running)} cámaras Pro Max activas; reintenta cuando estén en IDLE.')
    out = Path(args.out).expanduser() / ('run_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(parents=True, mode=0o700)
    os.chmod(out, 0o700)
    metadata = {'timestamp_utc': now_iso(), 'app_version': state.get('version'),
                'host_logical_cpu': os.cpu_count(),
                'host_mem_total_mib': round(int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines()
                                      if line.startswith('MemTotal:'))) / 1024, 1),
                'source_note': 'Canales RTSP del mismo grabador; no son 8 modelos de cámara independientes',
                'protocol': 'HTTP HLS signed URL, local 127.0.0.1; MPEG-TS validation structural',
                'duration_s': args.duration, 'poll_s': args.poll,
                'cooldown_s': args.cooldown, 'stages': stages,
                'stats_source': 'docker stats --no-stream',
                'note': 'CPU% Docker: 100% ≈ un núcleo; no mide latencia glass-to-glass ni decodificación Alexa.'}
    metadata.update(inspect_environment(args.container))
    (out / 'metadata.json').write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print('Destino:', out)
    print('Versión:', state.get('version'), '| CPU lógicas:', os.cpu_count())
    print('No se registrarán URLs ni credenciales. Uso de CPU limitado con guardarraíles.')
    summaries = []
    try:
        for stage in stages:
            summary = run_stage(stage, order[:stage], state, args, out)
            summaries.append(summary)
            if summary['aborted_by_guardrail'] or not summary['all_idle_after']:
                print('Se interrumpe el protocolo por seguridad/revisión.', flush=True)
                break
    except KeyboardInterrupt:
        print('\nInterrupción solicitada; el controlador parará cámaras por inactividad.', flush=True)
    finally:
        write_csv(out / 'summary.csv', summaries,
                  ['concurrency','target_sustained_s','streams_ready','streams_expected',
                   'streams_with_new_segments','total_unique_segments','http_errors','other_errors',
                   'cpu_avg_pct','cpu_peak_pct','memory_peak_mib','samples_steady',
                   'all_idle_after','aborted_by_guardrail','abort_reason'])
    print('\nINFORMES:', out)
    print('Puedes publicar CSV/JSON tras revisar contenido; NO publiques archivos de configuración o URLs RTSP.')
    if not summaries or any(r['aborted_by_guardrail'] or not r['all_idle_after'] or
                            r['streams_ready'] != r['streams_expected'] for r in summaries):
        return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (HTTPError, URLError, KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print('Fallo al iniciar prueba:', type(exc).__name__, file=sys.stderr)
        sys.exit(1)

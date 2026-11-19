"""Read-only system telemetry and on-demand media checks; no camera URLs in output."""
from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import threading
import time

from .media import inspect_source, inspect_audio_source, select_mode

_CPU_LOCK = threading.Lock()
_CPU_LAST = None


def _cgroup_number(name):
    try:
        value = (Path('/sys/fs/cgroup') / name).read_text().strip()
        return int(value) if value != 'max' else None
    except (OSError, ValueError):
        return None


def system_metrics():
    global _CPU_LAST
    now = time.monotonic()
    cpu_usage = None
    try:
        for line in Path('/sys/fs/cgroup/cpu.stat').read_text().splitlines():
            if line.startswith('usage_usec '):
                cpu_usage = int(line.split()[1])
                break
    except (OSError, ValueError, IndexError):
        pass
    pct = None
    if cpu_usage is not None:
        with _CPU_LOCK:
            if _CPU_LAST is not None:
                dt = now - _CPU_LAST[0]
                if dt > 0.1 and cpu_usage >= _CPU_LAST[1]:
                    pct = round(100 * (cpu_usage-_CPU_LAST[1]) / 1_000_000 / dt, 2)
            _CPU_LAST = (now, cpu_usage)
    memory = _cgroup_number('memory.current')
    limit = _cgroup_number('memory.max')
    try:
        load = [round(n, 2) for n in os.getloadavg()]
    except OSError:
        load = None
    return {
        'cpu_percent_one_core': pct,
        'cpu_logical_host': os.cpu_count(),
        'memory_mib': round(memory / 1024**2, 1) if memory is not None else None,
        'memory_limit_mib': round(limit / 1024**2, 1) if limit is not None else None,
        'host_load_average': load,
    }


def probe_camera(cam):
    video = inspect_source(cam['rtsp_url'])
    try:
        audio = inspect_audio_source(cam['rtsp_url'])
    except RuntimeError:
        audio = None
    return {'slug': cam['slug'], 'video': video, 'audio': audio,
            'audio_mode': cam.get('audio_mode', 'off'),
            'recommended_video_mode': select_mode({**cam, 'mode': 'auto'}, video),
            'audio_warning': ('AAC enabled but no RTSP audio was detected' if
                              cam.get('audio_mode') == 'aac' and audio is None else None)}


def check_local_hls(manager, slug, timeout=25):
    """Start the selected camera, inspect its first TS file, and return safe metrics.

    This tests local HLS output, not external HTTPS/Alexa playback. It will
    leave FFmpeg running only until the normal idle timeout.
    """
    start = time.monotonic()
    playlist = manager.request(slug)
    target = playlist.parent
    deadline = start + timeout
    segment = None
    while time.monotonic() < deadline:
        if playlist.exists() and playlist.stat().st_size > 10:
            # A nonempty segment referenced by the playlist must exist.
            lines = playlist.read_text(errors='replace').splitlines()
            for line in lines:
                if line.startswith('segment_') and line.endswith('.ts'):
                    candidate = target / line
                    if candidate.is_file() and candidate.stat().st_size > 188:
                        segment = candidate
                        break
        if segment:
            break
        time.sleep(.2)
    if segment is None:
        raise RuntimeError('No HLS MPEG-TS segment produced within the deadline')
    elapsed = round(time.monotonic() - start, 3)
    # Probe and decode the *local* segment. No source RTSP URL is passed here.
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'stream=codec_name,codec_type',
             '-of', 'json', str(segment)],
            capture_output=True, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('FFprobe timed out or unavailable') from exc
    if result.returncode:
        raise RuntimeError('FFprobe could not parse the generated segment')
    try:
        streams = json.loads(result.stdout.decode('utf-8'))['streams']
    except (ValueError, UnicodeDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError('FFprobe returned an invalid segment report') from exc
    video_codec = next((s.get('codec_name') for s in streams if s.get('codec_type') == 'video'), None)
    audio_codec = next((s.get('codec_name') for s in streams if s.get('codec_type') == 'audio'), None)
    expected_audio = manager.store.get(slug).get('audio_mode', 'off')
    if video_codec != 'h264':
        raise RuntimeError('HLS segment does not contain H.264 video')
    if expected_audio == 'aac' and audio_codec != 'aac':
        raise RuntimeError('AAC was requested but is missing from the HLS segment')
    if expected_audio == 'off' and audio_codec is not None:
        raise RuntimeError('Audio OFF expected a video-only segment')
    try:
        decode = subprocess.run(
            ['ffmpeg', '-hide_banner', '-nostdin', '-v', 'error', '-i', str(segment),
             '-map', '0:v:0', '-f', 'null', '-'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('Video decode timed out or unavailable') from exc
    if decode.returncode:
        raise RuntimeError('Generated segment did not decode as video')
    return {'slug': slug, 'first_ts_seconds': elapsed,
            'segment_bytes': segment.stat().st_size,
            'video_codec': video_codec, 'audio_codec': audio_codec or 'NONE',
            'video_decode': 'ok',
            'scope': 'local RTSP-to-HLS segment; not Alexa/Cloudflare validation'}

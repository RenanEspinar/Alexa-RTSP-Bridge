"""FFmpeg per camera, with opt-in AAC and a bounded recovery watchdog."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import threading
import time


@dataclass
class CameraState:
    proc: object = None
    requested_at: float = 0
    started_at: float = 0
    failures: int = 0
    retry_after: float = 0
    codec: str = ''
    effective_mode: str = ''
    audio_mode: str = 'off'
    starts: int = 0
    recoveries: int = 0
    stalls: int = 0
    pending_recovery: bool = False
    last_exit: int | None = None
    last_error: str = ''
    snapshot_time: float = 0
    snapshot_lock: object = field(default_factory=threading.Lock)


def _probe_stream(url, select, fields, timeout):
    args = ['ffprobe', '-v', 'error', '-rtsp_transport', 'tcp',
            '-select_streams', select, '-show_entries', f'stream={fields}',
            '-of', 'json', url]
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError('ffprobe timed out or unavailable') from exc
    if result.returncode:
        raise RuntimeError('ffprobe could not read the RTSP source')
    try:
        streams = json.loads(result.stdout.decode()).get('streams', [])
        return streams[0] if streams else None
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise RuntimeError('ffprobe returned invalid data') from exc


def inspect_source(url, timeout=8):
    info = _probe_stream(url, 'v:0', 'codec_name,profile,width,height,pix_fmt', timeout)
    if info is None:
        raise RuntimeError('No video track was found')
    return info


def inspect_audio_source(url, timeout=8):
    """Return None for a source without audio; never return RTSP credentials."""
    return _probe_stream(url, 'a:0', 'codec_name,channels,sample_rate', timeout)


def select_mode(config, stream_info):
    mode = config['mode']
    compatible = (stream_info.get('codec_name') == 'h264'
                  and stream_info.get('profile') in ('Constrained Baseline', 'Baseline', 'Main')
                  and stream_info.get('pix_fmt', 'yuv420p') == 'yuv420p')
    if mode == 'copy' and not compatible:
        raise RuntimeError('Copy requires H.264 Baseline/Main 4:2:0; choose auto')
    if mode == 'auto':
        return 'copy' if compatible else 'transcode'
    return mode


def stream_command(camera, target: Path, mode):
    args = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
            '-rtsp_transport', 'tcp', '-fflags', '+genpts',
            '-i', camera['rtsp_url'], '-map', '0:v:0']
    audio = camera.get('audio_mode', 'off')
    if audio == 'off':
        args += ['-an']
    elif audio == 'aac':
        # The audio track must exist. Failing is better than claiming AAC to Alexa
        # while silently delivering a stream without any audio.
        args += ['-map', '0:a:0', '-c:a', 'aac', '-ar', '48000', '-ac', '1', '-b:a', '64k']
    else:
        raise ValueError('Unknown audio mode')
    if mode == 'copy':
        args += ['-c:v', 'copy', '-bsf:v', 'h264_mp4toannexb']
    else:
        fps, kbps = camera['fps'], camera['bitrate_kbps']
        w, h = camera['width'], camera['height']
        vf = (f'scale={w}:{h}:force_original_aspect_ratio=decrease,'
              f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,fps={fps}')
        args += ['-vf', vf, '-c:v', 'libx264', '-profile:v', 'baseline',
                 '-level:v', ('3.1' if w * h <= 1280 * 720 else '4.0'),
                 '-preset', 'veryfast', '-tune', 'zerolatency', '-bf', '0',
                 '-g', str(fps), '-keyint_min', str(fps), '-sc_threshold', '0',
                 '-x264-params', 'repeat-headers=1:open-gop=0',
                 '-b:v', f'{kbps}k', '-maxrate', f'{kbps}k', '-bufsize', f'{kbps * 2}k']
    args += ['-f', 'hls', '-hls_segment_type', 'mpegts', '-hls_time', '1',
             '-hls_list_size', '6',
             '-hls_flags', 'delete_segments+omit_endlist+independent_segments',
             '-hls_segment_filename', str(target / 'segment_%010d.ts'),
             str(target / 'index.m3u8')]
    return args


def snapshot_command(camera, target: Path):
    return ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
            '-rtsp_transport', 'tcp', '-i', camera['rtsp_url'], '-map', '0:v:0',
            '-vf', 'scale=640:-2', '-frames:v', '1', '-q:v', '4',
            '-f', 'image2', '-update', '1', '-y', str(target)]


class Manager:
    def __init__(self, store, idle_timeout=30, snapshot_ttl=120, runtime_dir=None, *, watchdog=True):
        self.store = store
        self.idle_timeout = max(10, int(idle_timeout))
        self.snapshot_ttl = max(15, int(snapshot_ttl))
        self.root = Path(runtime_dir or store.root / 'hls')
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == 'posix':
            self.root.chmod(0o700)
        self.lock = threading.RLock()
        self.states: dict[str, CameraState] = {}
        self.events = deque(maxlen=100)
        self.closed = threading.Event()
        self.watchdog_enabled = bool(watchdog)
        if watchdog:
            threading.Thread(target=self.watch, daemon=True, name='ffmpeg-watchdog').start()

    def _event(self, slug, code, detail=''):
        # Structured, sanitized events only. Never log command lines or RTSP URLs.
        self.events.append({'utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                            'camera': slug, 'event': code, 'detail': detail})

    def recent_events(self, count=30):
        with self.lock:
            return list(self.events)[-min(max(int(count), 1), 100):][::-1]

    def _state(self, slug):
        return self.states.setdefault(slug, CameraState())

    def _backoff(self, st, now):
        st.failures += 1
        st.retry_after = now + min(60, 3 * 2 ** min(st.failures - 1, 4))
        st.pending_recovery = True

    def _start_locked(self, slug, camera, st):
        now = time.monotonic()
        if st.proc:
            code = st.proc.poll()
            if code is None:
                return
            st.last_exit = code
            st.last_error = f'FFmpeg exited ({code})'
            st.proc = None
            self._backoff(st, now)
            self._event(slug, 'worker_exit', 'Retry scheduled')
        if now < st.retry_after:
            raise RuntimeError('Camera cooling down after a failed start')
        target = self.root / slug
        target.mkdir(exist_ok=True)
        for f in target.glob('*'):
            if f.is_file() and f.suffix in ('.ts', '.m3u8'):
                f.unlink(missing_ok=True)
        try:
            mode = camera['mode']
            if mode in ('auto', 'copy'):
                video = inspect_source(camera['rtsp_url'])
                mode = select_mode(camera, video)
                st.codec = video.get('codec_name', '')
            else:
                st.codec = 'transcoded'
            audio = camera.get('audio_mode', 'off')
            if audio == 'aac' and inspect_audio_source(camera['rtsp_url']) is None:
                raise RuntimeError('Audio enabled but camera has no audio track')
            cmd = stream_command(camera, target, mode)
            st.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
            st.started_at = now
            st.last_error = ''
            st.effective_mode = mode
            st.audio_mode = audio
            st.starts += 1
            if st.pending_recovery:
                st.recoveries += 1
                st.pending_recovery = False
                self._event(slug, 'recovered', f'mode={mode} audio={audio}')
            else:
                self._event(slug, 'started', f'mode={mode} audio={audio}')
            print(f'[START] camera={slug} mode={mode} audio={audio}', flush=True)
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            self._backoff(st, now)
            st.last_error = (str(exc) if isinstance(exc, RuntimeError) and 'Audio enabled' in str(exc)
                             else type(exc).__name__)
            self._event(slug, 'start_failed', 'Check camera settings or RTSP connectivity')
            raise RuntimeError('Unable to start this camera') from exc

    def request(self, slug):
        camera = self.store.get(slug)
        if camera is None:
            raise KeyError('Unknown camera')
        with self.lock:
            st = self._state(slug)
            st.requested_at = time.monotonic()
            self._start_locked(slug, camera, st)
        return self.root / slug / 'index.m3u8'

    def stop(self, slug):
        with self.lock:
            st = self.states.get(slug)
            if st is None or not st.proc:
                return
            proc = st.proc
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
                print(f'[STOP] camera={slug}', flush=True)
            st.last_exit = proc.returncode
            st.proc = None
            self._event(slug, 'stopped')

    def restart(self, slug):
        """Manual restart only for an already streaming camera."""
        with self.lock:
            cam = self.store.get(slug)
            if not cam:
                raise KeyError('Unknown camera')
            st = self._state(slug)
            active = st.proc is not None and st.proc.poll() is None
            if not active:
                return False
            self.stop(slug)
            st.failures = 0
            st.retry_after = 0
            self._event(slug, 'manual_restart')
            self._start_locked(slug, cam, st)
            return True

    def _latest_segment_age(self, slug):
        target = self.root / slug
        latest = max((f.stat().st_mtime for f in target.glob('segment_*.ts') if f.is_file()),
                     default=None)
        return None if latest is None else max(0.0, time.time() - latest)

    def watch_once(self):
        now = time.monotonic()
        with self.lock:
            for slug, st in list(self.states.items()):
                camera = self.store.get(slug)
                if camera is None:
                    self.stop(slug)
                    del self.states[slug]
                    continue
                if st.proc is None:
                    if (st.requested_at and now - st.requested_at < self.idle_timeout
                            and now >= st.retry_after):
                        try:
                            self._start_locked(slug, camera, st)
                        except (RuntimeError, OSError):
                            pass
                    continue
                if st.proc.poll() is None and now - st.started_at > 40 and st.failures:
                    st.failures = 0
                if st.requested_at and now - st.requested_at >= self.idle_timeout:
                    self.stop(slug)
                    st.failures = 0
                    st.retry_after = 0
                    self._event(slug, 'idle_timeout')
                    continue
                exit_code = st.proc.poll()
                playlist = self.root / slug / 'index.m3u8'
                playlist_age = (time.time() - playlist.stat().st_mtime if playlist.exists() else None)
                segment_age = self._latest_segment_age(slug)
                stale = (exit_code is None and now - st.started_at > 20
                         and (playlist_age is None or playlist_age > 15
                              or segment_age is None or segment_age > 15))
                if exit_code is not None or stale:
                    st.last_error = 'No new HLS segments' if stale else f'FFmpeg exited ({exit_code})'
                    if stale:
                        st.stalls += 1
                        self._event(slug, 'stalled', 'No fresh HLS segments for 15s')
                    else:
                        self._event(slug, 'worker_exit', f'code={exit_code}')
                    self.stop(slug)
                    self._backoff(st, now)
                    self._event(slug, 'retry_scheduled', f'in {round(st.retry_after - now)}s')
                    print(f'[RECOVERY] camera={slug} retry in {round(st.retry_after - now)}s', flush=True)

    def watch(self):
        while not self.closed.wait(5):
            try:
                self.watch_once()
            except (OSError, RuntimeError):
                print('[WATCHDOG] check failed; will retry', flush=True)

    def snapshot(self, slug):
        cam = self.store.get(slug)
        if cam is None:
            raise KeyError('Unknown camera')
        with self.lock:
            st = self._state(slug)
        output = self.root / slug / 'snapshot.jpg'
        output.parent.mkdir(parents=True, exist_ok=True)
        with st.snapshot_lock:
            if output.exists() and time.time() - output.stat().st_mtime <= self.snapshot_ttl:
                return output
            temp = output.parent / 'snapshot.new.jpg'
            try:
                proc = subprocess.run(snapshot_command(cam, temp), stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                                      check=False)
                if proc.returncode or not temp.is_file() or temp.stat().st_size < 100:
                    raise RuntimeError('Camera did not return a snapshot')
                os.replace(temp, output)
                if os.name == 'posix':
                    output.chmod(0o600)
                st.snapshot_time = time.time()
            finally:
                temp.unlink(missing_ok=True)
        return output

    def status(self):
        with self.lock:
            output = {}
            for slug, st in self.states.items():
                p = st.proc
                active = p is not None and p.poll() is None
                age = self._latest_segment_age(slug) if active else None
                output[slug] = {'running': active, 'mode': st.effective_mode,
                                'audio_mode': st.audio_mode, 'codec': st.codec,
                                'starts': st.starts, 'failures': st.failures,
                                'recoveries': st.recoveries, 'stalls': st.stalls,
                                'last_error': st.last_error, 'last_exit_code': st.last_exit,
                                'cooldown_seconds': max(0, round(st.retry_after-time.monotonic())),
                                'segment_age_seconds': round(age, 1) if age is not None else None,
                                'idle_seconds': max(0, round(time.monotonic() - st.requested_at)) if st.requested_at else None,
                                'snapshot_age_seconds': (round(time.time() - (self.root / slug / 'snapshot.jpg').stat().st_mtime)
                                                         if (self.root / slug / 'snapshot.jpg').exists() else None)}
            return output

    def close(self):
        self.closed.set()
        for slug in list(self.states):
            self.stop(slug)

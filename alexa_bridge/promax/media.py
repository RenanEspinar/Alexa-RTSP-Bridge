"""On-demand FFmpeg processes, with per-camera recovery and snapshots."""
from __future__ import annotations
from dataclasses import dataclass, field
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
    starts: int = 0
    last_exit: int | None = None
    last_error: str = ''
    snapshot_time: float = 0
    snapshot_lock: object = field(default_factory=threading.Lock)


def inspect_source(url, timeout=8):
    args = ['ffprobe', '-v', 'error', '-rtsp_transport', 'tcp', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,profile,width,height,pix_fmt', '-of', 'json', url]
    result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise RuntimeError('ffprobe could not read the video stream')
    try:
        return json.loads(result.stdout.decode())['streams'][0]
    except (ValueError, IndexError, KeyError) as exc:
        raise RuntimeError('ffprobe returned no video stream') from exc


def select_mode(config, stream_info):
    mode = config['mode']
    compatible = (stream_info.get('codec_name') == 'h264'
                  and stream_info.get('profile') in ('Constrained Baseline', 'Baseline', 'Main')
                  and stream_info.get('pix_fmt', 'yuv420p') == 'yuv420p')
    if mode == 'copy' and not compatible:
        raise RuntimeError('Copy mode requires compatible H.264 Baseline/Main 4:2:0; choose auto')
    if mode == 'auto':
        return 'copy' if compatible else 'transcode'
    return mode


def stream_command(camera, target: Path, mode):
    url = camera['rtsp_url']
    args = ['ffmpeg', '-hide_banner', '-nostdin', '-loglevel', 'error',
            '-rtsp_transport', 'tcp', '-fflags', '+genpts', '-i', url, '-map', '0:v:0', '-an']
    if mode == 'copy':
        args += ['-c:v', 'copy', '-bsf:v', 'h264_mp4toannexb']
    else:
        fps, kbps = camera['fps'], camera['bitrate_kbps']
        w, h = camera['width'], camera['height']
        vf = f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format=yuv420p,fps={fps}'
        args += ['-vf', vf, '-c:v', 'libx264', '-profile:v', 'baseline', '-level:v', ('3.1' if camera['width'] * camera['height'] <= 1280 * 720 else '4.0'),
                 '-preset', 'veryfast', '-tune', 'zerolatency', '-bf', '0',
                 '-g', str(fps), '-keyint_min', str(fps), '-sc_threshold', '0',
                 '-x264-params', 'repeat-headers=1:open-gop=0',
                 '-b:v', f'{kbps}k', '-maxrate', f'{kbps}k', '-bufsize', f'{kbps * 2}k']
    args += ['-f', 'hls', '-hls_segment_type', 'mpegts', '-hls_time', '1',
             '-hls_list_size', '6', '-hls_flags', 'delete_segments+omit_endlist+independent_segments',
             '-hls_segment_filename', str(target / 'segment_%010d.ts'),
             str(target / 'index.m3u8')]
    return args


def snapshot_command(camera, target: Path):
    # A single frame on demand; this does not leave a transcoder running.
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
        self.closed = threading.Event()
        if watchdog:
            threading.Thread(target=self.watch, daemon=True, name='ffmpeg-watchdog').start()

    def _state(self, slug):
        return self.states.setdefault(slug, CameraState())

    def _start_locked(self, slug, camera, st):
        now = time.monotonic()
        if st.proc:
            code = st.proc.poll()
            if code is None:
                return
            st.last_exit = code
            st.last_error = f'ffmpeg exited ({code})'
            st.proc = None
            st.failures += 1
            st.retry_after = now + min(60, 3 * (2 ** min(st.failures - 1, 4)))
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
                codec = inspect_source(camera['rtsp_url'])
                mode = select_mode(camera, codec)
                st.codec = codec.get('codec_name', '')
            else:
                st.codec = 'transcoded'
            cmd = stream_command(camera, target, mode)
            st.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
            st.started_at = now
            st.last_error = ''
            st.effective_mode = mode
            st.starts += 1
            print(f'[START] camera={slug} mode={mode}', flush=True)
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            st.failures += 1
            st.retry_after = now + min(60, 3 * (2 ** min(st.failures - 1, 4)))
            st.last_error = type(exc).__name__
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

    def watch_once(self):
        now = time.monotonic()
        with self.lock:
            for slug, st in list(self.states.items()):
                if self.store.get(slug) is None:
                    self.stop(slug)
                    del self.states[slug]
                    continue
                if st.proc is None:
                    # A viewer may still be requesting playlists after a crashed
                    # worker. Restart only while requests are recent and after
                    # the cooldown; leave unrelated cameras alone.
                    if (st.requested_at and now - st.requested_at < self.idle_timeout
                            and now >= st.retry_after):
                        camera = self.store.get(slug)
                        if camera:
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
                    continue
                exit_code = st.proc.poll()
                playlist = self.root / slug / 'index.m3u8'
                stale = (exit_code is None and now - st.started_at > 20
                         and (not playlist.exists() or time.time() - playlist.stat().st_mtime > 15))
                if exit_code is not None or stale:
                    if stale:
                        st.last_error = 'Playlist stalled'
                    else:
                        st.last_error = f'ffmpeg exited ({exit_code})'
                    self.stop(slug)
                    st.failures += 1
                    st.retry_after = now + min(60, 3 * (2 ** min(st.failures - 1, 4)))
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
                output[slug] = {'running': active, 'mode': st.effective_mode,
                                'codec': st.codec, 'starts': st.starts,
                                'failures': st.failures, 'last_error': st.last_error,
                                'idle_seconds': max(0, round(time.monotonic() - st.requested_at)) if st.requested_at else None,
                                'snapshot_age_seconds': (round(time.time() - (self.root / slug / 'snapshot.jpg').stat().st_mtime)
                                                         if (self.root / slug / 'snapshot.jpg').exists() else None)}
            return output

    def close(self):
        self.closed.set()
        for slug in list(self.states):
            self.stop(slug)

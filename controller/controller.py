"""Reference on-demand HLS controller.

Live-source adaptation of the author's running architecture, with signed stream
URLs and a Docker API proxy. NOT independently verified on an Echo device.
"""
from __future__ import annotations
import hashlib
import hmac
import http.server
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

CAMERA_MAP = json.loads(Path(os.environ.get('CAMERA_MAP_FILE', '/app/camera-map.json')).read_text())
HLS_ROOT = Path(os.environ.get('HLS_ROOT', '/hls'))
DOCKER_API = os.environ.get('DOCKER_API', 'http://dockerproxy:2375').rstrip('/')
KEY = Path(os.environ.get('SIGNING_KEY_FILE', '/run/secrets/hls_signing_key')).read_bytes().strip()
IDLE_TIMEOUT = max(5, int(os.environ.get('IDLE_TIMEOUT', '30')))
STARTUP_TIMEOUT = max(2, float(os.environ.get('STARTUP_TIMEOUT', '12')))
MAX_TOKEN_LIFETIME = 3600
PATH_RX = re.compile(r'^/s/(?P<expiry>\d{10})/(?P<signature>[0-9a-f]{64})/(?P<slug>[a-z][a-z0-9_]{0,39})/(?P<name>index\.m3u8|segment_\d+\.ts)$')
locks = {name: threading.RLock() for name in CAMERA_MAP}
last_access = {}

if len(KEY) < 32 or not CAMERA_MAP or not all(re.fullmatch(r'[a-z][a-z0-9_]{0,39}', k) for k in CAMERA_MAP):
    raise ValueError('Invalid camera map or signing secret')


def validate_signed_path(path, now=None):
    match = PATH_RX.fullmatch(urlsplit(path).path)
    if match is None:
        return None
    d = match.groupdict()
    now = time.time() if now is None else now
    exp = int(d['expiry'])
    if d['slug'] not in CAMERA_MAP or exp <= now or exp > now + MAX_TOKEN_LIFETIME:
        return None
    expected = hmac.new(KEY, f"{exp}:{d['slug']}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, d['signature']):
        return None
    return d['slug'], d['name']


def docker_request(method, path):
    req = Request(f'{DOCKER_API}{path}', method=method)
    try:
        with urlopen(req, timeout=8) as response:
            return response.status, response.read()
    except HTTPError as err:
        return err.code, err.read()


def running(slug):
    status, payload = docker_request('GET', f'/containers/{CAMERA_MAP[slug]}/json')
    if status != 200:
        raise RuntimeError(f'Container inspection failed: HTTP {status}')
    return bool(json.loads(payload)['State']['Running'])


def start(slug):
    if running(slug):
        return
    folder = HLS_ROOT / slug
    folder.mkdir(parents=True, exist_ok=True)
    for file in folder.iterdir():
        if file.is_file() and (file.suffix in ('.ts', '.m3u8')):
            file.unlink(missing_ok=True)
    code, _ = docker_request('POST', f'/containers/{CAMERA_MAP[slug]}/start')
    if code not in (204, 304):
        raise RuntimeError(f'Docker start returned HTTP {code}')
    print(f'[START] camera={slug}', flush=True)


def stop(slug):
    if not running(slug):
        return
    code, _ = docker_request('POST', f'/containers/{CAMERA_MAP[slug]}/stop?t=10')
    if code not in (204, 304):
        raise RuntimeError(f'Docker stop returned HTTP {code}')
    print(f'[STOP] camera={slug}', flush=True)


def watchdog():
    while True:
        time.sleep(5)
        for slug in CAMERA_MAP:
            with locks[slug]:
                stamp = last_access.get(slug)
                if stamp is None or time.monotonic() - stamp <= IDLE_TIMEOUT:
                    continue
                try:
                    stop(slug)
                    last_access.pop(slug, None)
                except (OSError, URLError, RuntimeError, ValueError) as e:
                    print(f'[WATCHDOG] camera={slug}, error={type(e).__name__}', flush=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.serve(send_body=False)

    def do_GET(self):
        self.serve(send_body=True)

    def serve(self, send_body):
        parsed = validate_signed_path(self.path)
        if parsed is None:
            self.send_error(403, 'Invalid or expired stream URL')
            return
        slug, name = parsed
        path = HLS_ROOT / slug / name
        try:
            if name == 'index.m3u8':
                with locks[slug]:
                    last_access[slug] = time.monotonic()
                    start(slug)
                deadline = time.monotonic() + STARTUP_TIMEOUT
                while time.monotonic() < deadline:
                    if path.is_file() and path.stat().st_size > 0:
                        break
                    time.sleep(0.15)
                else:
                    self.send_error(503, 'Playlist not ready')
                    return
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, 'Segment missing or expired')
            return
        except (OSError, URLError, RuntimeError, ValueError):
            print(f'[ERROR] camera={slug}, file={name}', flush=True)
            self.send_error(503, 'Streaming service unavailable')
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.apple.mpegurl' if name.endswith('.m3u8') else 'video/mp2t')
        self.send_header('Cache-Control', 'private, no-store, max-age=0')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if send_body:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, fmt, *args):
        # Do not log the request path: it embeds a temporary bearer credential.
        pass


if __name__ == '__main__':
    threading.Thread(target=watchdog, daemon=True).start()
    print('Signed HLS on-demand controller started', flush=True)
    http.server.ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()

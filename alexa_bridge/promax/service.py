"""Two separate HTTP surfaces: HA-authenticated admin UI and signed HLS."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .media import Manager, inspect_source, select_mode
from .security import SLUG, make_path, verify_path
from .store import Store

STATIC = Path(__file__).parent / 'static'
MAX_REQUEST = 8_192


class Application:
    def __init__(self, root, *, idle_timeout=30, snapshot_ttl=120, watchdog=True):
        self.store = Store(root)
        self.manager = Manager(self.store, idle_timeout, snapshot_ttl, watchdog=watchdog)
        self.csrf = secrets.token_urlsafe(32)
        self.started = time.time()


def respond(handler, status, body=b'', mime='application/json', *, head=False):
    handler.send_response(status)
    handler.send_header('Content-Type', mime)
    handler.send_header('Content-Length', str(len(body)))
    handler.send_header('Cache-Control', 'no-store')
    handler.send_header('X-Content-Type-Options', 'nosniff')
    handler.send_header('Referrer-Policy', 'no-referrer')
    handler.end_headers()
    if not head:
        try:
            handler.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def json_reply(handler, status, data, *, head=False):
    respond(handler, status, json.dumps(data, ensure_ascii=False).encode('utf-8'), head=head)


def make_handler(app: Application, admin=False):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Don't log paths: signed URLs are bearer credentials.
            pass

        def do_HEAD(self):
            self.get(head=True)

        def do_GET(self):
            self.get(head=False)

        def get(self, *, head):
            path = urlsplit(self.path).path
            if admin:
                if path in ('/', '/index.html'):
                    respond(self, 200, (STATIC / 'index.html').read_bytes(), 'text/html; charset=utf-8', head=head)
                elif path == '/static/app.css':
                    respond(self, 200, (STATIC / 'app.css').read_bytes(), 'text/css; charset=utf-8', head=head)
                elif path == '/static/app.js':
                    respond(self, 200, (STATIC / 'app.js').read_bytes(), 'application/javascript; charset=utf-8', head=head)
                elif path == '/api/state':
                    json_reply(self, 200, {'version': '0.4.0b1', 'csrf': app.csrf,
                                           'cameras': app.store.public(), 'status': app.manager.status(),
                                           'uptime_seconds': round(time.time() - app.started)}, head=head)
                elif path == '/api/endpoint-map':
                    if self.headers.get('X-Bridge-CSRF') != app.csrf:
                        respond(self, 403, head=head)
                        return
                    json_reply(self, 200, app.store.endpoint_map(), head=head)
                elif path.startswith('/api/snapshot/'):
                    if self.headers.get('X-Bridge-CSRF') != app.csrf:
                        respond(self, 403, head=head)
                        return
                    slug = path.removeprefix('/api/snapshot/')
                    if not SLUG.fullmatch(slug):
                        respond(self, 404, head=head)
                        return
                    try:
                        image = app.manager.snapshot(slug).read_bytes()
                        respond(self, 200, image, 'image/jpeg', head=head)
                    except (OSError, RuntimeError, KeyError):
                        json_reply(self, 503, {'error': 'Camera snapshot unavailable'}, head=head)
                else:
                    respond(self, 404, head=head)
                return
            result = verify_path(self.path, app.store.key, app.store.slugs())
            if not result:
                respond(self, 403, head=head)
                return
            slug, filename = result
            try:
                if filename == 'index.m3u8':
                    file = app.manager.request(slug)
                    end = time.monotonic() + 20
                    while time.monotonic() < end and (not file.exists() or file.stat().st_size == 0):
                        time.sleep(0.15)
                    if not file.exists() or file.stat().st_size == 0:
                        raise RuntimeError('Playlist not ready')
                elif filename == 'snapshot.jpg':
                    file = app.manager.snapshot(slug)
                else:
                    file = app.manager.root / slug / filename
                mime = ('application/vnd.apple.mpegurl' if filename.endswith('.m3u8')
                        else 'image/jpeg' if filename.endswith('.jpg') else 'video/mp2t')
                respond(self, 200, file.read_bytes(), mime, head=head)
            except FileNotFoundError:
                respond(self, 404, head=head)
            except (RuntimeError, OSError, KeyError):
                respond(self, 503, head=head)

        def do_POST(self):
            self.mutate('POST')

        def do_DELETE(self):
            self.mutate('DELETE')

        def mutate(self, method):
            if not admin:
                respond(self, 405)
                return
            # Only the UI behind Home Assistant Ingress (or local SSH tunnel)
            # can call these operations. The public stream server never can.
            if self.headers.get('X-Bridge-CSRF') != app.csrf:
                json_reply(self, 403, {'error': 'Invalid admin request'})
                return
            path = urlsplit(self.path).path
            try:
                if method == 'POST':
                    if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                        json_reply(self, 415, {'error': 'Use application/json'})
                        return
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= MAX_REQUEST:
                        json_reply(self, 413, {'error': 'Invalid request size'})
                        return
                    data = json.loads(self.rfile.read(length))
                    if path == '/api/cameras':
                        camera = app.store.upsert(data)
                        app.manager.stop(camera['slug'])
                        json_reply(self, 200, {'ok': True, 'slug': camera['slug']})
                    elif path == '/api/secret':
                        if data != {'confirm': 'I_UNDERSTAND'}:
                            json_reply(self, 400, {'error': 'Confirmation required'})
                            return
                        json_reply(self, 200, {'key': app.store.key.decode('ascii')})
                    elif path.startswith('/api/probe/'):
                        slug = path.removeprefix('/api/probe/')
                        camera = app.store.get(slug)
                        if not camera:
                            json_reply(self, 404, {'error': 'Camera not found'})
                            return
                        info = inspect_source(camera['rtsp_url'])
                        json_reply(self, 200, {'codec': info.get('codec_name'),
                                               'profile': info.get('profile'), 'width': info.get('width'),
                                               'height': info.get('height'), 'recommended_mode': select_mode({**camera, 'mode': 'auto'}, info)})
                    elif path.startswith('/api/check-hls/'):
                        # Local self-test: media never leaves the private admin response.
                        slug = path.removeprefix('/api/check-hls/')
                        if not SLUG.fullmatch(slug) or not app.store.get(slug):
                            json_reply(self, 404, {'error': 'Camera not found'})
                            return
                        started = time.monotonic()
                        playlist = app.manager.request(slug)
                        deadline = started + 22
                        while time.monotonic() < deadline:
                            if playlist.is_file() and playlist.stat().st_size > 0:
                                contents = playlist.read_text(errors='replace')
                                names = [line.strip() for line in contents.splitlines()
                                         if re.fullmatch(r'segment_[0-9]+\.ts', line.strip())]
                                for name in reversed(names):
                                    segment = playlist.parent / name
                                    if segment.is_file() and segment.stat().st_size >= 188:
                                        with segment.open('rb') as stream:
                                            valid_ts = stream.read(1) == b'\x47'
                                        if valid_ts:
                                            json_reply(self, 200, {
                                                'ok': True, 'segment_bytes': segment.stat().st_size,
                                                'elapsed_s': round(time.monotonic() - started, 3)})
                                            return
                            time.sleep(0.2)
                        json_reply(self, 503, {'error': 'No valid MPEG-TS segment within 22 seconds'})
                    elif path.startswith('/api/sign/'):
                        slug = path.removeprefix('/api/sign/')
                        if not app.store.get(slug):
                            json_reply(self, 404, {'error': 'Camera not found'})
                            return
                        json_reply(self, 200, {'path': make_path(app.store.key, slug, lifetime=600)})
                    else:
                        respond(self, 404)
                elif path.startswith('/api/cameras/'):
                    slug = path.removeprefix('/api/cameras/')
                    if not SLUG.fullmatch(slug):
                        respond(self, 404)
                        return
                    app.manager.stop(slug)
                    if app.store.delete(slug):
                        json_reply(self, 200, {'ok': True})
                    else:
                        respond(self, 404)
                else:
                    respond(self, 404)
            except (ValueError, KeyError) as exc:
                json_reply(self, 400, {'error': str(exc)})
            except (RuntimeError, OSError):
                json_reply(self, 503, {'error': 'Camera service unavailable'})

    return Handler


def serve():
    root = os.environ.get('DATA_DIR', '/data')
    options = {}
    options_file = Path(root) / 'options.json'
    if options_file.exists():
        options = json.loads(options_file.read_text())
    idle = int(os.environ.get('IDLE_TIMEOUT', options.get('idle_timeout', 30)))
    snapshot_ttl = int(os.environ.get('SNAPSHOT_TTL', options.get('snapshot_ttl', 120)))
    app = Application(root, idle_timeout=idle, snapshot_ttl=snapshot_ttl)
    ui_port = int(os.environ.get('UI_PORT', 8099))
    media_port = int(os.environ.get('HLS_PORT', 8090))
    ui = ThreadingHTTPServer(('0.0.0.0', ui_port), make_handler(app, admin=True))
    media = ThreadingHTTPServer(('0.0.0.0', media_port), make_handler(app))
    threading.Thread(target=ui.serve_forever, daemon=True, name='admin-ui').start()
    print(f'Alexa RTSP Bridge Pro v0.4.0b1 started (UI {ui_port}, signed HLS {media_port})', flush=True)
    try:
        media.serve_forever()
    finally:
        ui.shutdown()
        media.server_close()
        ui.server_close()
        app.manager.close()


if __name__ == '__main__':
    serve()

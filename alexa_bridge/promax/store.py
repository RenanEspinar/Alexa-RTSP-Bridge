"""Atomic, local camera settings. Credentials never leave the data directory."""
from __future__ import annotations
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
from .security import check_camera


def atomic_private(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.bridge-', dir=str(path.parent))
    try:
        if hasattr(os, 'fchmod'):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if os.name == 'posix':
            self.root.chmod(0o700)
        self.lock = threading.RLock()
        self.path = self.root / 'cameras.json'
        keypath = self.root / 'hls_signing_key'
        if not keypath.exists():
            atomic_private(keypath, secrets.token_hex(32).encode())
        self.key = keypath.read_bytes().strip()
        if len(self.key) < 32:
            raise ValueError('Signing secret too short')
        self.cameras = {}
        if self.path.exists():
            entries = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(entries, list):
                raise ValueError('cameras.json must be an array')
            for row in entries:
                cam = check_camera(row)
                if cam['slug'] in self.cameras:
                    raise ValueError('Duplicate camera slug')
                self.cameras[cam['slug']] = cam

    def _save(self):
        content = json.dumps(list(self.cameras.values()), indent=2, ensure_ascii=False).encode()
        atomic_private(self.path, content)

    def get(self, slug):
        with self.lock:
            camera = self.cameras.get(slug)
            return dict(camera) if camera else None

    def slugs(self):
        with self.lock:
            return set(self.cameras)

    def public(self):
        with self.lock:
            # No URL, password or signing key in any listing.
            return [{**{k: v for k, v in c.items() if k != 'rtsp_url'},
                     'configured': bool(c.get('rtsp_url'))} for c in self.cameras.values()]

    def upsert(self, payload):
        if not isinstance(payload, dict):
            raise ValueError('Expected a camera object')
        slug = payload.get('slug')
        with self.lock:
            existing = self.cameras.get(slug, {})
            merged = {**existing, **payload}
            if not payload.get('rtsp_url') and existing:
                merged['rtsp_url'] = existing['rtsp_url']
            camera = check_camera(merged)
            endpoint = camera['alexa_endpoint_id']
            if endpoint and any(c['alexa_endpoint_id'] == endpoint and s != slug
                                for s, c in self.cameras.items()):
                raise ValueError('Alexa endpoint ID already used')
            if camera.get('overlay_mode') == 'boxes' and any(
                c.get('overlay_mode') == 'boxes' for s,c in self.cameras.items() if s != slug
            ):
                raise ValueError('Only one Alexa AI overlay camera is allowed in CPU-safe beta')
            self.cameras[slug] = camera
            self._save()
            return camera

    def delete(self, slug):
        with self.lock:
            if slug not in self.cameras:
                return False
            self.cameras.pop(slug)
            self._save()
            return True

    def endpoint_map(self):
        with self.lock:
            return {c['alexa_endpoint_id']: (
                {'slug': slug, 'audioCodec': 'AAC'} if c.get('audio_mode') == 'aac' else slug
            ) for slug, c in self.cameras.items() if c['alexa_endpoint_id']}

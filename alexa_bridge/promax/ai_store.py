"""Private, optional AI event database shared by the gateway and its AI sidecar.

Only the gateway's authenticated administrative surface exposes these records.
Never store RTSP URLs, passwords, HLS secrets or face identities in events.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from .security import SLUG, validate_rtsp
from .store import atomic_private

EVENT_ID = re.compile(r'^[0-9a-f]{32}$')
CATEGORIES = frozenset({'person', 'car', 'motorcycle', 'bicycle', 'bus', 'truck', 'cat', 'dog'})
DEFAULTS = {
    'enabled': False,
    'interval_seconds': 3,
    'confidence': 0.45,
    'cooldown_seconds': 90,
    'retention_days': 7,
    'motion_fraction': 0.006,
    'cameras': {},
}


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class AIStore:
    def __init__(self, data_root):
        self.path = Path(data_root) / 'ai'
        self.path.mkdir(parents=True, exist_ok=True)
        self.path.chmod(0o700)
        self.images = self.path / 'snapshots'
        self.images.mkdir(exist_ok=True)
        self.images.chmod(0o700)
        # Short-lived viewer-only annotated preview. Never exposed by the HLS service.
        self.overlay_dir = self.path / 'overlay'
        self.overlay_dir.mkdir(exist_ok=True)
        self.overlay_dir.chmod(0o700)
        self.preview_dir = self.path / 'previews'
        self.preview_dir.mkdir(exist_ok=True)
        self.preview_dir.chmod(0o700)
        self.config_path = self.path / 'config.json'
        self.status_path = self.path / 'status.json'
        self.db_path = self.path / 'events.sqlite3'
        self.lock = threading.RLock()
        self._create_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=5)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute('PRAGMA busy_timeout=5000')
            with conn:
                yield conn
        finally:
            conn.close()

    def _create_db(self):
        with self._connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, camera TEXT NOT NULL,
                category TEXT NOT NULL, confidence REAL NOT NULL,
                image TEXT NOT NULL, feedback TEXT NOT NULL DEFAULT 'pending',
                bbox TEXT NOT NULL DEFAULT '[]'
            )''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC)')
        if self.db_path.exists():
            self.db_path.chmod(0o600)

    def config(self):
        with self.lock:
            if not self.config_path.exists():
                return json.loads(json.dumps(DEFAULTS))
            loaded = json.loads(self.config_path.read_text(encoding='utf-8'))
            if not isinstance(loaded, dict):
                raise ValueError('Invalid AI config file')
            return {**DEFAULTS, **loaded}

    def public_config(self):
        data = self.config()
        clean = {}
        for slug, settings in data['cameras'].items():
            clean[slug] = {'enabled': bool(settings.get('enabled', False)),
                           'substream_configured': bool(settings.get('substream')),
                           'road_mode': bool(settings.get('road_mode',False))}
        data['cameras'] = clean
        return data

    def save_config(self, changes, known_slugs):
        if not isinstance(changes, dict):
            raise ValueError('Invalid AI configuration')
        with self.lock:
            current = self.config()
            if 'enabled' in changes:
                if type(changes['enabled']) is not bool:
                    raise ValueError('enabled must be boolean')
                current['enabled'] = changes['enabled']
            rules = {'interval_seconds': (1, 30, int), 'confidence': (0.20, 0.95, (int, float)),
                     'cooldown_seconds': (20, 3600, int), 'retention_days': (1, 30, int),
                     'motion_fraction': (0.0, 0.2, (int, float))}
            for key, (lo, hi, kind) in rules.items():
                if key in changes:
                    v = changes[key]
                    if type(v) is bool or not isinstance(v, kind) or not lo <= v <= hi:
                        raise ValueError(f'Invalid {key}')
                    current[key] = v
            if 'camera' in changes:
                c = changes['camera']
                if not isinstance(c, dict) or c.get('slug') not in known_slugs:
                    raise ValueError('Camera not found')
                slug = c['slug']
                if not SLUG.fullmatch(slug):
                    raise ValueError('Invalid camera')
                settings = current['cameras'].get(slug, {'enabled': False, 'substream': '', 'road_mode': False})
                if 'enabled' in c:
                    if type(c['enabled']) is not bool:
                        raise ValueError('Camera enabled must be boolean')
                    settings['enabled'] = c['enabled']
                if 'road_mode' in c:
                    if type(c['road_mode']) is not bool:
                        raise ValueError('Road mode must be boolean')
                    settings['road_mode'] = c['road_mode']
                if 'substream' in c:
                    url = c['substream']
                    if not isinstance(url, str):
                        raise ValueError('Invalid substream')
                    settings['substream'] = validate_rtsp(url) if url.strip() else ''
                current['cameras'][slug] = settings
            if current['enabled']:
                count = sum(bool(v.get('enabled')) for s, v in current['cameras'].items()
                            if s in known_slugs)
                if count > 2:
                    raise ValueError('Maximum two AI cameras in CPU-safe beta')
            atomic_private(self.config_path, json.dumps(current, indent=2).encode('utf-8'))
            return self.public_config()

    def status(self):
        if not self.status_path.exists():
            return {'state': 'not_started', 'last_seen': None, 'healthy': False}
        try:
            data = json.loads(self.status_path.read_text(encoding='utf-8'))
            ts = float(data.get('epoch', 0))
            # Do not leak configured RTSP sources or exceptions into the UI.
            return {'state': data.get('state', 'unknown'),
                    'last_seen': data.get('last_seen'),
                    'healthy': (time.time() - ts) < 45,
                    'model_loaded': bool(data.get('model_loaded')),
                    'camera': data.get('camera'),
                    'detections': int(data.get('detections', 0)),
                    'message': data.get('message', '')[:140]}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {'state': 'status_unavailable', 'last_seen': None, 'healthy': False}

    def heartbeat(self, state, **details):
        payload = {'state': state, 'epoch': time.time(), 'last_seen': now_utc(), **details}
        atomic_private(self.status_path, json.dumps(payload).encode('utf-8'))

    def add_event(self, camera, category, confidence, jpg, bbox):
        if not SLUG.fullmatch(camera) or category not in CATEGORIES:
            raise ValueError('Unsupported detection')
        if not isinstance(jpg, bytes) or not (8 <= len(jpg) <= 300_000) or not jpg.startswith(b'\xff\xd8'):
            raise ValueError('Invalid JPEG')
        if not 0 <= float(confidence) <= 1:
            raise ValueError('Invalid confidence')
        eid = uuid.uuid4().hex
        filename = eid + '.jpg'
        atomic_private(self.images / filename, jpg)
        with self._connect() as conn:
            conn.execute('INSERT INTO events (id, created_at, camera, category, confidence, image, bbox) VALUES (?,?,?,?,?,?,?)',
                         (eid, now_utc(), camera, category, float(confidence), filename, json.dumps(bbox)))
        return eid

    def events(self, limit=50):
        with self._connect() as conn:
            rows = conn.execute('SELECT id, created_at, camera, category, confidence, feedback, bbox FROM events ORDER BY created_at DESC, rowid DESC LIMIT ?',
                                (max(1, min(200, int(limit))),)).fetchall()
        return [dict(row) for row in rows]

    def summary(self, hours=24):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec='seconds')
        with self._connect() as conn:
            rows = conn.execute('SELECT category, feedback, COUNT(*) AS n FROM events WHERE created_at >= ? GROUP BY category, feedback',
                                (cutoff,)).fetchall()
        by_class = {}
        feedback = {'pending': 0, 'confirmed': 0, 'false_positive': 0}
        for row in rows:
            category, label, n = row['category'], row['feedback'], int(row['n'])
            by_class[category] = by_class.get(category, 0) + n
            if label in feedback:
                feedback[label] += n
        return {'hours': hours, 'total': sum(by_class.values()), 'categories': by_class,
                'feedback': feedback}

    def feedback(self, eid, decision):
        if not EVENT_ID.fullmatch(eid) or decision not in ('confirmed', 'false_positive', 'pending'):
            raise ValueError('Invalid feedback')
        with self._connect() as conn:
            cur = conn.execute('UPDATE events SET feedback=? WHERE id=?', (decision, eid))
            return cur.rowcount > 0

    def image(self, eid):
        if not EVENT_ID.fullmatch(eid):
            return None
        with self._connect() as conn:
            row = conn.execute('SELECT image FROM events WHERE id=?', (eid,)).fetchone()
        if row is None or row['image'] != eid + '.jpg':
            return None
        path = self.images / (eid + '.jpg')
        return path.read_bytes() if path.is_file() else None

    def set_preview_watch(self, slug, enabled):
        """Authorize a short viewer session; worker writes frames only while watched."""
        if not SLUG.fullmatch(slug):
            raise ValueError('Invalid camera')
        key = self.preview_dir / (slug + '.watch')
        if enabled:
            atomic_private(key, str(time.time() + 45).encode('ascii'))
        else:
            key.unlink(missing_ok=True)
            (self.preview_dir / (slug + '.jpg')).unlink(missing_ok=True)
            (self.preview_dir / (slug + '.json')).unlink(missing_ok=True)

    def preview_watched(self, slug):
        if not SLUG.fullmatch(slug):
            return False
        try:
            return float((self.preview_dir / (slug + '.watch')).read_text()) >= time.time()
        except (OSError, ValueError):
            return False

    def save_preview(self, slug, jpg, *, boxes, analyzed, motion, inference_ms):
        if not SLUG.fullmatch(slug) or not self.preview_watched(slug):
            return False
        if not isinstance(jpg, bytes) or not jpg.startswith(b'\xff\xd8') or len(jpg) > 450000:
            raise ValueError('Invalid preview image')
        meta = {'camera': slug, 'utc': now_utc(), 'epoch': time.time(),
                'analyzed': bool(analyzed), 'motion': bool(motion),
                'inference_ms': round(float(inference_ms), 1),
                'objects': [{'category': n, 'confidence': round(float(score), 3),
                             'bbox': [int(x) for x in box]} for n,score,box in boxes[:30]]}
        atomic_private(self.preview_dir / (slug + '.jpg'), jpg)
        atomic_private(self.preview_dir / (slug + '.json'), json.dumps(meta).encode())
        return True

    def preview_info(self, slug):
        if not SLUG.fullmatch(slug) or not self.preview_watched(slug):
            return None
        try:
            meta = json.loads((self.preview_dir / (slug + '.json')).read_text())
            if meta.get('camera') != slug or time.time()-meta.get('epoch', 0) > 35:
                return None
            meta['age_seconds'] = round(max(0, time.time()-meta['epoch']), 1)
            return meta
        except (OSError, ValueError, TypeError):
            return None

    def preview_jpeg(self, slug):
        meta = self.preview_info(slug)
        if meta is None:
            return None
        try:
            data = (self.preview_dir / (slug + '.jpg')).read_bytes()
            return data if data.startswith(b'\xff\xd8') else None
        except OSError:
            return None

    def save_live_boxes(self, slug, *, width, height, objects, ttl_seconds=4):
        """Private detector output consumed only by the local HLS overlay controller."""
        if not SLUG.fullmatch(slug) or not 1 <= width <= 8192 or not 1 <= height <= 8192:
            raise ValueError('Invalid detector frame')
        clean = []
        for category, confidence, bbox in objects[:8]:
            if category not in CATEGORIES or not 0 <= confidence <= 1 or len(bbox) != 4:
                continue
            coords = [int(x) for x in bbox]
            if (0 <= coords[0] < coords[2] <= width and
                    0 <= coords[1] < coords[3] <= height):
                clean.append({'category': category, 'confidence': round(float(confidence), 3),
                              'bbox': coords})
        if not 1 <= float(ttl_seconds) <= 8:
            raise ValueError('Invalid overlay TTL')
        atomic_private(self.overlay_dir / (slug + '.json'), json.dumps({
            'ttl': float(ttl_seconds), 'epoch': time.time(), 'camera': slug, 'width': int(width),
            'height': int(height), 'objects': clean
        }, separators=(',', ':')).encode())

    def purge_old(self):
        days = int(self.config().get('retention_days', 7))
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec='seconds')
        with self._connect() as conn:
            old = conn.execute('SELECT image FROM events WHERE created_at < ?', (cutoff,)).fetchall()
            conn.execute('DELETE FROM events WHERE created_at < ?', (cutoff,))
        for row in old:
            name = row['image']
            if EVENT_ID.fullmatch(name.removesuffix('.jpg')) and name.endswith('.jpg'):
                (self.images / name).unlink(missing_ok=True)
        return len(old)

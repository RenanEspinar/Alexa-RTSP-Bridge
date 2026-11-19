"""URL signatures and input validation shared by the gateway and the tests."""
from __future__ import annotations
import hashlib
import hmac
import re
import time
from urllib.parse import urlsplit

SLUG = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
MEDIA = re.compile(
    r'^/s/(?P<expiry>\d{10})/(?P<sig>[a-f0-9]{64})/'
    r'(?P<slug>[a-z][a-z0-9_]{0,39})/'
    r'(?P<file>index\.m3u8|segment_\d+\.ts|snapshot\.jpg)$'
)
MAX_LIFETIME = 3600


def make_path(secret: bytes, slug: str, filename='index.m3u8', *, now=None, lifetime=1800):
    if not SLUG.fullmatch(slug) or not re.fullmatch(r'index\.m3u8|segment_\d+\.ts|snapshot\.jpg', filename):
        raise ValueError('Invalid camera or file name')
    if not 1 <= lifetime <= MAX_LIFETIME:
        raise ValueError('Invalid URL lifetime')
    expiry = int(time.time() if now is None else now) + lifetime
    digest = hmac.new(secret, f'{expiry}:{slug}'.encode(), hashlib.sha256).hexdigest()
    return f'/s/{expiry}/{digest}/{slug}/{filename}'


def verify_path(path: str, secret: bytes, known_slugs, *, now=None):
    match = MEDIA.fullmatch(urlsplit(path).path)
    if match is None:
        return None
    d = match.groupdict()
    current = time.time() if now is None else now
    expiry = int(d['expiry'])
    if d['slug'] not in known_slugs or not current < expiry <= current + MAX_LIFETIME:
        return None
    signature = hmac.new(secret, f"{expiry}:{d['slug']}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, d['sig']):
        return None
    return d['slug'], d['file']


def validate_rtsp(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048 or any(c in url for c in '\r\n\0'):
        raise ValueError('Invalid RTSP URL')
    try:
        u = urlsplit(url.strip())
        if u.scheme not in ('rtsp', 'rtsps') or not u.hostname or (u.port is not None and not 1 <= u.port <= 65535):
            raise ValueError('RTSP URL must include a valid hostname')
    except (ValueError, AttributeError) as exc:
        raise ValueError('Invalid RTSP URL') from exc
    return url.strip()


def check_camera(data, *, allow_no_url=False):
    if not isinstance(data, dict):
        raise ValueError('Camera must be a JSON object')
    slug = data.get('slug')
    if not isinstance(slug, str) or not SLUG.fullmatch(slug):
        raise ValueError('Slug must be lowercase letters, numbers or underscores')
    mode = data.get('mode', 'auto')
    if mode not in ('auto', 'copy', 'transcode'):
        raise ValueError('Mode must be auto, copy or transcode')
    overlay_mode = data.get('overlay_mode', 'off')
    if overlay_mode not in ('off', 'boxes'):
        raise ValueError('Overlay mode must be off or boxes')
    audio_mode = data.get('audio_mode', 'off')
    if audio_mode not in ('off', 'aac'):
        raise ValueError('Audio mode must be off or aac')
    name = data.get('name', slug)
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50 or any(c in name for c in '<>\r\n'):
        raise ValueError('Invalid camera name')
    url = data.get('rtsp_url')
    if url:
        validate_rtsp(url)
    elif not allow_no_url:
        raise ValueError('RTSP URL required')
    width, height, fps, bitrate = (data.get('width', 960), data.get('height', 540),
                                   data.get('fps', 15), data.get('bitrate_kbps', 1000))
    for label, value, lo, hi in [('width', width, 320, 1920), ('height', height, 240, 1080),
                                 ('fps', fps, 5, 30), ('bitrate', bitrate, 250, 6000)]:
        if type(value) is not int or not lo <= value <= hi:
            raise ValueError(f'Invalid {label}')
    if width % 2 or height % 2:
        raise ValueError('Width and height must be even')
    endpoint = data.get('alexa_endpoint_id', '')
    if not isinstance(endpoint, str) or len(endpoint) > 200:
        raise ValueError('Invalid Alexa endpoint ID')
    return {
        'slug': slug, 'name': name.strip(), 'rtsp_url': url,
        'mode': mode, 'width': width, 'height': height,
        'fps': fps, 'bitrate_kbps': bitrate, 'alexa_endpoint_id': endpoint,
        'audio_mode': audio_mode, 'overlay_mode': overlay_mode,
    }

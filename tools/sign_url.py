#!/usr/bin/env python3
"""URL HLS temporal para probar una cámara sin pasar por Alexa."""
import hashlib
import hmac
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parent.parent

def sign(slug, key, base='http://127.0.0.1:8090', lifetime=900, now=None):
    # No compartas este enlace: cualquiera que lo tenga puede usarlo hasta que caduque.
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', slug):
        raise ValueError('Invalid camera slug')
    if lifetime <= 0 or lifetime > 3600:
        raise ValueError('Lifetime must be 1..3600 seconds')
    expiry = int(time.time() if now is None else now) + lifetime
    sig = hmac.new(key, f'{expiry}:{slug}'.encode(), hashlib.sha256).hexdigest()
    return f'{base.rstrip("/")}/s/{expiry}/{sig}/{slug}/index.m3u8'

if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: python3 tools/sign_url.py <camera_slug>')
    slug = sys.argv[1]
    config = json.loads((ROOT / 'local' / 'camera-map.json').read_text())
    if slug not in config:
        sys.exit('Camera slug does not exist in local/camera-map.json')
    key = (ROOT / 'local' / 'secrets' / 'hls_signing_key').read_bytes().strip()
    if len(key) < 32:
        sys.exit('Signing secret too short')
    print('Temporary local access URL (keep private):')
    print(sign(slug, key))

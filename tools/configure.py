#!/usr/bin/env python3
"""Arma el Compose local a partir de config/cameras.json.

Revisa que los archivos RTSP existan y tengan formato correcto, pero nunca
copia su contenido al Compose. Tampoco arranca contenedores.
"""
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
CAMERA_CONFIG = ROOT / 'config' / 'cameras.json'
COMPOSE_FILE = ROOT / 'compose.generated.yml'
RUNTIME_CONFIG = ROOT / 'local' / 'camera-map.json'
SLUG = re.compile(r'^[a-z][a-z0-9_]{0,39}$')


def load_cameras(path=CAMERA_CONFIG):
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or not isinstance(obj.get('cameras'), list) or not obj['cameras']:
        raise ValueError('config/cameras.json requires a nonempty cameras array')
    cameras = obj['cameras']
    seen = set()
    seen_endpoints = set()
    for row in cameras:
        if not isinstance(row, dict):
            raise ValueError('Each camera must be an object')
        slug = row.get('slug')
        endpoint = row.get('alexa_endpoint_id')
        if not isinstance(slug, str) or not SLUG.fullmatch(slug):
            raise ValueError(f'Invalid camera slug: {slug!r}')
        if not isinstance(endpoint, str) or not endpoint.strip():
            raise ValueError(f'Missing alexa_endpoint_id for {slug}')
        if slug in seen or endpoint in seen_endpoints:
            raise ValueError('Duplicate slug or Alexa endpoint ID')
        seen.add(slug)
        seen_endpoints.add(endpoint)
        secret = ROOT / 'local' / 'secrets' / f'{slug}.url'
        if not secret.is_file() or not secret.read_text(encoding='utf-8').strip().startswith(('rtsp://', 'rtsps://')):
            raise ValueError(f'Missing or invalid local/secrets/{slug}.url (do not add it to git)')
        if secret.stat().st_mode & 0o077:
            raise ValueError(f'Permissions too broad: chmod 600 local/secrets/{slug}.url')
    return cameras


def build_compose(cameras):
    # Docker Compose también acepta JSON. Así evitamos depender de PyYAML.
    services = {
        'dockerproxy': {
            'image': 'tecnativa/docker-socket-proxy:v0.4.1',
            'restart': 'unless-stopped',
            'environment': {'CONTAINERS': '1', 'POST': '1'},
            'volumes': ['/var/run/docker.sock:/var/run/docker.sock:ro'],
            'networks': ['control'],
            'security_opt': ['no-new-privileges:true'],
        },
        'controller': {
            'image': 'python:3.13-alpine',
            'restart': 'unless-stopped',
            'command': ['python', '-u', '/app/controller.py'],
            'volumes': [
                './controller/controller.py:/app/controller.py:ro',
                './local/camera-map.json:/app/camera-map.json:ro',
                './local/secrets/hls_signing_key:/run/secrets/hls_signing_key:ro',
                './local/hls:/hls:rw',
            ],
            'environment': {
                'CAMERA_MAP_FILE': '/app/camera-map.json',
                'SIGNING_KEY_FILE': '/run/secrets/hls_signing_key',
                'DOCKER_API': 'http://dockerproxy:2375',
                'IDLE_TIMEOUT': '${IDLE_TIMEOUT:-30}',
                'STARTUP_TIMEOUT': '${STARTUP_TIMEOUT:-12}',
            },
            'networks': ['control', 'media'],
            'depends_on': ['dockerproxy'],
            'security_opt': ['no-new-privileges:true'],
        },
        'nginx': {
            'image': 'nginx:1.28-alpine',
            'restart': 'unless-stopped',
            'ports': ['127.0.0.1:${HLS_PORT:-8090}:80'],
            'volumes': ['./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro'],
            'networks': ['media'],
            'depends_on': ['controller'],
            'tmpfs': ['/var/cache/nginx', '/var/run', '/tmp'],
            'security_opt': ['no-new-privileges:true'],
        },
    }
    # Los contenedores se crean detenidos: el controlador los prende al pedir video.
    for c in cameras:
        slug = c['slug']
        container = f'alexa_cam_{slug}'
        services[container] = {
            'image': 'lscr.io/linuxserver/ffmpeg:latest',
            'container_name': container,
            'profiles': ['camera'],
            'restart': 'no',
            'entrypoint': ['/bin/bash', '/bridge/start-camera.sh'],
            'environment': {'CAMERA_SLUG': slug},
            'volumes': [
                './ffmpeg/start-camera.sh:/bridge/start-camera.sh:ro',
                f'./local/secrets/{slug}.url:/run/secrets/rtsp_url:ro',
                './local/hls:/hls:rw',
            ],
            'networks': ['camera'],
            'security_opt': ['no-new-privileges:true'],
        }
    return {
        'name': 'alexa-rtsp-bridge',
        'services': services,
        'networks': {
            'control': {'internal': True},
            'media': {},
            'camera': {},
        },
    }


def main():
    cameras = load_cameras()
    signing = ROOT / 'local' / 'secrets' / 'hls_signing_key'
    if not signing.is_file() or len(signing.read_bytes().strip()) < 32:
        raise ValueError('Generate local/secrets/hls_signing_key with at least 32 random bytes (see docs/INSTALL.md)')
    if signing.stat().st_mode & 0o077:
        raise ValueError('Run chmod 600 local/secrets/hls_signing_key')
    (ROOT / 'local').mkdir(exist_ok=True)
    RUNTIME_CONFIG.write_text(json.dumps({c['slug']: f"alexa_cam_{c['slug']}" for c in cameras}, indent=2)+'\n')
    COMPOSE_FILE.write_text(json.dumps(build_compose(cameras), indent=2)+'\n')
    print(f'Prepared {len(cameras)} camera(s) in compose.generated.yml')
    print('The generator does not modify Docker services or read camera frames.')
    print('Do not publish local/ or compose.generated.yml with private modifications.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as e:
        print(f'Configuration error: {e}', file=sys.stderr)
        sys.exit(2)

"""Reference Alexa Smart Home v3 proxy backed by Home Assistant.

This is a safer, configurable adaptation of the repository's original lambda.py;
NOT a byte-for-byte copy of the AWS function deployed by the author.
"""
import hashlib
import hmac
import json
import logging
import os
import time
from urllib import request, error

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)


def signed_uri(base, slug, secret, now=None, lifetime=1800):
    if not slug or not all(c.islower() or c.isdigit() or c == '_' for c in slug):
        raise ValueError('Bad camera slug')
    if not base.startswith('https://'):
        raise ValueError('ALEXA_HLS_BASE must use HTTPS')
    expiry = int(time.time() if now is None else now) + lifetime
    digest = hmac.new(secret.encode(), f'{expiry}:{slug}'.encode(), hashlib.sha256).hexdigest()
    return f'{base.rstrip("/")}/s/{expiry}/{digest}/{slug}/index.m3u8'


def error_response(message_id, code, description):
    return {'event': {'header': {
        'namespace': 'Alexa', 'name': 'ErrorResponse',
        'messageId': message_id or 'error-message', 'payloadVersion': '3'},
        'payload': {'type': code, 'message': description}}}


def lambda_handler(event, context):
    directive = event.get('directive') if isinstance(event, dict) else None
    if not isinstance(directive, dict):
        return error_response(None, 'INVALID_DIRECTIVE', 'Missing directive')
    header = directive.get('header') or {}
    message_id = header.get('messageId')
    if header.get('payloadVersion') != '3':
        return error_response(message_id, 'INVALID_DIRECTIVE', 'Expected Alexa v3')

    scope = ((directive.get('endpoint') or {}).get('scope') or
             (directive.get('payload') or {}).get('grantee') or
             (directive.get('payload') or {}).get('scope') or {})
    token = scope.get('token') if scope.get('type') == 'BearerToken' else None
    if not token:
        return error_response(message_id, 'INVALID_AUTHORIZATION_CREDENTIAL', 'Missing OAuth bearer token')

    base_url = os.environ.get('HOME_ASSISTANT_URL', '').rstrip('/')
    hls_base = os.environ.get('ALEXA_HLS_BASE', '')
    secret = os.environ.get('HLS_SIGNING_KEY', '')
    try:
        mappings = json.loads(os.environ.get('CAMERA_ENDPOINT_MAP_JSON', '{}'))
        if not base_url.startswith('https://') or not hls_base.startswith('https://') or len(secret) < 32:
            raise ValueError('Missing HTTPS URLs or signing secret')
        if not isinstance(mappings, dict):
            raise ValueError('Invalid endpoint map')
    except ValueError:
        return error_response(message_id, 'INTERNAL_ERROR', 'Lambda configuration incomplete')

    req = request.Request(
        base_url + '/api/alexa/smart_home',
        data=json.dumps(event).encode('utf-8'),
        headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with request.urlopen(req, timeout=12) as response:
            ha_result = json.load(response)
    except error.HTTPError as exc:
        LOG.warning('Home Assistant HTTP %s', exc.code)
        code = 'INVALID_AUTHORIZATION_CREDENTIAL' if exc.code in (401, 403) else 'INTERNAL_ERROR'
        return error_response(message_id, code, 'Home Assistant request rejected')
    except (error.URLError, TimeoutError, ValueError) as exc:
        LOG.warning('Home Assistant communication failed: %s', type(exc).__name__)
        return error_response(message_id, 'INTERNAL_ERROR', 'Home Assistant request failed')

    if not isinstance(ha_result, dict):
        return error_response(message_id, 'INTERNAL_ERROR', 'Invalid Home Assistant response')
    response_event = ha_result.get('event') or {}
    response_header = response_event.get('header') or {}
    if response_header.get('namespace') == 'Alexa.CameraStreamController' and response_header.get('name') == 'Response':
        slug = mappings.get((response_event.get('endpoint') or {}).get('endpointId'))
        if slug:
            try:
                uri = signed_uri(hls_base, slug, secret)
            except ValueError:
                return error_response(message_id, 'INTERNAL_ERROR', 'Invalid HLS URL configuration')
            streams = (response_event.get('payload') or {}).get('cameraStreams') or []
            for stream in streams:
                if isinstance(stream, dict):
                    stream.update({
                        'uri': uri,
                        'protocol': 'HLS',
                        'authorizationType': 'NONE',
                        'videoCodec': 'H264',
                        'audioCodec': 'NONE',
                        'resolution': {'width': 960, 'height': 540},
                    })
    return ha_result

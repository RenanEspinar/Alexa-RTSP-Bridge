import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
KEY = '0123456789abcdef' * 4


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


configure = load_module('reference_configure', ROOT / 'tools/configure.py')
signer = load_module('reference_signer', ROOT / 'tools/sign_url.py')
lambda_fn = load_module('reference_lambda', ROOT / 'lambda/lambda_function.py')
with tempfile.TemporaryDirectory() as td:
    d = Path(td)
    (d / 'cameras.json').write_text(json.dumps({'front_door': 'alexa_cam_front_door'}))
    (d / 'signing_key').write_text(KEY)
    with mock.patch.dict(os.environ, {'CAMERA_MAP_FILE': str(d / 'cameras.json'), 'SIGNING_KEY_FILE': str(d / 'signing_key')}):
        controller = load_module('reference_controller', ROOT / 'controller/controller.py')


class ConfigurationTests(unittest.TestCase):
    def test_requires_existing_secret_file(self):
        with tempfile.TemporaryDirectory() as td:
            old_root = configure.ROOT
            try:
                configure.ROOT = Path(td)
                p = Path(td) / 'config'
                p.mkdir()
                cfg = p / 'cameras.json'
                cfg.write_text(json.dumps({'cameras': [{'slug': 'front_door', 'alexa_endpoint_id': 'camera#front_door'}]}))
                with self.assertRaises(ValueError):
                    configure.load_cameras(cfg)
            finally:
                configure.ROOT = old_root

    def test_blocks_slugs_and_duplicates(self):
        with tempfile.TemporaryDirectory() as td:
            old_root = configure.ROOT
            try:
                configure.ROOT = Path(td)
                p = Path(td) / 'config'
                p.mkdir()
                cfg = p / 'cameras.json'
                cfg.write_text(json.dumps({'cameras': [{'slug': '../bad', 'alexa_endpoint_id': 'id'}]}))
                with self.assertRaises(ValueError):
                    configure.load_cameras(cfg)
            finally:
                configure.ROOT = old_root

    def test_generates_named_stopped_camera_services(self):
        cfg = configure.build_compose([{'slug': 'front_door', 'alexa_endpoint_id': 'camera#front_door'}])
        camera = cfg['services']['alexa_cam_front_door']
        self.assertEqual(camera['profiles'], ['camera'])
        self.assertEqual(camera['restart'], 'no')
        self.assertNotIn('ports', cfg['services']['controller'])
        self.assertNotIn('ports', cfg['services']['dockerproxy'])
        self.assertTrue(cfg['services']['nginx']['ports'][0].startswith('127.0.0.1:'))
        self.assertFalse(any('PASSWORD=' in str(s) for s in camera['volumes']))


class SignatureTests(unittest.TestCase):
    def test_lambda_local_signatures_match(self):
        link = lambda_fn.signed_uri('https://hls.example.net', 'front_door', KEY, now=2000000000, lifetime=900)
        self.assertEqual(controller.validate_signed_path(urlsplit(link).path, now=2000000100), ('front_door', 'index.m3u8'))
        segment = urlsplit(link).path.replace('index.m3u8', 'segment_19999999.ts')
        self.assertEqual(controller.validate_signed_path(segment, now=2000000100), ('front_door', 'segment_19999999.ts'))

    def test_expired_and_modified_signature_rejected(self):
        link = signer.sign('front_door', KEY.encode(), now=2000000000, lifetime=900)
        path = urlsplit(link).path
        self.assertIsNone(controller.validate_signed_path(path, now=2000000900))
        self.assertIsNone(controller.validate_signed_path(path.replace('/front_door/', '/garage/'), now=2000000010))
        self.assertIsNone(controller.validate_signed_path(path.replace('index.m3u8', 'secret.ini'), now=2000000010))
        self.assertIsNone(controller.validate_signed_path('/front_door/index.m3u8', now=2000000010))

    def test_far_future_rejected(self):
        link = lambda_fn.signed_uri('https://hls.example.net', 'front_door', KEY, now=2000000000, lifetime=1800)
        self.assertIsNone(controller.validate_signed_path(urlsplit(link).path, now=1999996000))


class LambdaTests(unittest.TestCase):
    def _event(self):
        return {'directive': {'header': {'payloadVersion': '3', 'messageId': 'one'},
                'endpoint': {'scope': {'type': 'BearerToken', 'token': 'FAKE_TEST_TOKEN'}}}}

    def test_rewrites_matching_camera(self):
        source = {'event': {'header': {'namespace': 'Alexa.CameraStreamController', 'name': 'Response'},
                  'endpoint': {'endpointId': 'camera#front_door'},
                  'payload': {'cameraStreams': [{'uri': 'https://origin.example/video', 'protocol': 'HLS'}]}}}
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return json.dumps(source).encode()
        env = {'HOME_ASSISTANT_URL': 'https://ha.example.net', 'ALEXA_HLS_BASE': 'https://hls.example.net',
               'HLS_SIGNING_KEY': KEY, 'CAMERA_ENDPOINT_MAP_JSON': '{"camera#front_door":"front_door"}'}
        with mock.patch.dict(os.environ, env), mock.patch.object(lambda_fn.request, 'urlopen', return_value=Response()):
            out = lambda_fn.lambda_handler(self._event(), None)
        url = out['event']['payload']['cameraStreams'][0]['uri']
        self.assertEqual(urlsplit(url).hostname, 'hls.example.net')
        self.assertIn('/front_door/index.m3u8', url)
        self.assertNotIn('FAKE_TEST_TOKEN', json.dumps(out))

    def test_rejects_missing_token(self):
        event = self._event()
        event['directive']['endpoint']['scope'].pop('token')
        self.assertEqual(lambda_fn.lambda_handler(event, None)['event']['payload']['type'], 'INVALID_AUTHORIZATION_CREDENTIAL')


class FileServingTests(unittest.TestCase):
    def test_protected_playlist_and_segment_over_http(self):
        import http.server
        from urllib.request import urlopen
        from urllib.error import HTTPError
        import threading
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / 'front_door'
            directory.mkdir()
            (directory / 'index.m3u8').write_text('#EXTM3U\nsegment_12345.ts\n')
            (directory / 'segment_12345.ts').write_bytes(b'TEST-MPEG-TS')
            with mock.patch.object(controller, 'HLS_ROOT', Path(td)), mock.patch.object(controller, 'start', lambda slug: None):
                server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), controller.Handler)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    base = f'http://127.0.0.1:{server.server_port}'
                    link = signer.sign('front_door', KEY.encode(), base=base, lifetime=300)
                    with urlopen(link, timeout=2) as response:
                        self.assertIn(b'#EXTM3U', response.read())
                    with urlopen(link.replace('index.m3u8', 'segment_12345.ts'), timeout=2) as response:
                        self.assertEqual(response.read(), b'TEST-MPEG-TS')
                    with self.assertRaises(HTTPError) as err:
                        urlopen(base + '/front_door/index.m3u8', timeout=2)
                    self.assertEqual(err.exception.code, 403)
                finally:
                    server.shutdown()
                    server.server_close()

if __name__ == '__main__':
    unittest.main()

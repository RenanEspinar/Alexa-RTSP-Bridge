"""Check that the AWS adapter issues URLs accepted by the Pro HLS gateway."""
import importlib.util
from pathlib import Path
import unittest
from urllib.parse import urlsplit

from alexa_bridge.promax.security import verify_path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pro_lambda', ROOT / 'aws/lambda_function.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LambdaCompatibilityTests(unittest.TestCase):
    def test_signed_uri_matches_gateway(self):
        key = '0123456789abcdef' * 4
        uri = module.signed_uri('https://hls.example.net', 'solario', key,
                                now=2_000_000_000, lifetime=600)
        self.assertEqual(
            verify_path(urlsplit(uri).path, key.encode('ascii'), {'solario'},
                        now=2_000_000_020), ('solario', 'index.m3u8'))

    def test_expired_and_modified_paths_rejected(self):
        key = '0123456789abcdef' * 4
        uri = module.signed_uri('https://hls.example.net', 'solario', key,
                                now=2_000_000_000, lifetime=600)
        path = urlsplit(uri).path
        self.assertIsNone(verify_path(path, key.encode(), {'solario'},
                                      now=2_000_000_600))
        self.assertIsNone(verify_path(path.replace('/solario/', '/jardin/'),
                                      key.encode(), {'solario', 'jardin'},
                                      now=2_000_000_010))

    def test_requires_https(self):
        with self.assertRaises(ValueError):
            module.signed_uri('http://hls.example.net', 'solario', 'abcd' * 16)

if __name__ == '__main__':
    unittest.main()

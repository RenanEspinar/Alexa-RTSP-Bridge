"""Regression tests for the first-time setup UI and protected HLS diagnostics."""
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'alexa_bridge'))
from promax.service import Application, make_handler

CAM = {'slug': 'demo', 'name': 'Demo', 'rtsp_url': 'rtsp://private:secret@localhost:554/ch0',
       'mode': 'auto', 'width': 960, 'height': 540, 'fps': 15, 'bitrate_kbps': 1000,
       'alexa_endpoint_id': ''}

class SetupWizardTests(unittest.TestCase):
    def test_wizard_links_and_no_embedded_credentials(self):
        js = (ROOT/'alexa_bridge/promax/static/app.js').read_text()
        self.assertIn('WIZARD_COUNT = 11', js)
        for item in ('console.aws.amazon.com/lambda/', 'developer.amazon.com/alexa/console/ask',
                     'developers.cloudflare.com/tunnel/get-started/',
                     'www.home-assistant.io/integrations/alexa.smart_home/',
                     "localStorage.setItem(WIZARD_DATA_KEY", 'HLS_SIGNING_KEY',
                     'api/check-hls/'):
            self.assertIn(item, js)
        self.assertNotIn('localStorage.setItem(\'HLS_SIGNING_KEY', js)
        self.assertIn('instalación desde cero', (ROOT/'docs/WIZARD_DESDE_CERO_ES.md').read_text().lower())

    def test_hls_check_requires_csrf_and_returns_only_nonsecret_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            app = Application(td, watchdog=False)
            app.store.upsert(CAM)
            folder = app.manager.root/'demo'; folder.mkdir(exist_ok=True)
            playlist = folder/'index.m3u8'
            playlist.write_text('#EXTM3U\n#EXTINF:1.000\nsegment_000001.ts\n')
            (folder/'segment_000001.ts').write_bytes(b'\x47'+b'\0'*187)
            server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(app, admin=True))
            thread=Thread(target=server.serve_forever, daemon=True);thread.start()
            try:
                url=f'http://127.0.0.1:{server.server_port}/api/check-hls/demo'
                req=Request(url, data=b'{}', method='POST', headers={'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as ex: urlopen(req,timeout=3)
                self.assertEqual(ex.exception.code,403)
                req.add_header('X-Bridge-CSRF', app.csrf)
                with patch.object(app.manager, 'request', return_value=playlist):
                    with urlopen(req, timeout=3) as response: result=json.load(response)
                self.assertTrue(result['ok'])
                self.assertEqual(result['segment_bytes'],188)
                self.assertNotIn('secret', json.dumps(result))
            finally:
                server.shutdown();server.server_close();app.manager.close()

if __name__ == '__main__': unittest.main()

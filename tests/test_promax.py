"""Offline tests; no camera, Docker daemon or Alexa account required."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from urllib.request import urlopen, Request
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'alexa_bridge'))
from promax.security import make_path, verify_path, check_camera, validate_rtsp
from promax.store import Store
from promax.media import stream_command, snapshot_command, select_mode, Manager
from promax.service import Application, make_handler
from http.server import ThreadingHTTPServer

EXAMPLE = {'slug': 'front_door', 'name': 'Front Door', 'rtsp_url': 'rtsp://name:veryprivate@localhost/live',
           'mode': 'auto', 'width': 960, 'height': 540, 'fps': 15, 'bitrate_kbps': 1000,
           'alexa_endpoint_id': 'camera#front_door'}


class SecurityTests(unittest.TestCase):
    key = b'a' * 64

    def test_signed_stream_and_jpeg(self):
        for filename in ('index.m3u8', 'segment_123.ts', 'snapshot.jpg'):
            path = make_path(self.key, 'front_door', filename, now=2000000000, lifetime=600)
            self.assertEqual(verify_path(path, self.key, {'front_door'}, now=2000000001), ('front_door', filename))
            self.assertIsNone(verify_path(path, self.key, {'front_door'}, now=2000000600))

    def test_rejects_tampering_traversal_and_clock_skew(self):
        path = make_path(self.key, 'front_door', now=2000000000)
        for tampered in (path.replace('front_door', 'garage'), path + '/../cameras.json',
                         path.replace('index.m3u8', 'secret.env'),
                         '/front_door/index.m3u8'):
            self.assertIsNone(verify_path(tampered, self.key, {'front_door'}, now=2000000001))
        self.assertIsNone(verify_path(path, self.key, {'front_door'}, now=1999990000))

    def test_validates_rtsp_and_camera(self):
        self.assertEqual(check_camera(EXAMPLE)['mode'], 'auto')
        for url in ('http://camera', 'rtsp://', 'rtsp://cam\r\nHEADER:BAD', 'rtsp://cam:99999/live'):
            with self.assertRaises(ValueError):
                validate_rtsp(url)
        for bad_slug in ('../etc', 'front/door', 'MyCamera', '_private'):
            with self.assertRaises(ValueError):
                check_camera({**EXAMPLE, 'slug': bad_slug})
        with self.assertRaises(ValueError):
            check_camera({**EXAMPLE, 'fps': True})


class StorageTests(unittest.TestCase):
    def test_persists_without_exposing_urls(self):
        with tempfile.TemporaryDirectory() as td:
            s = Store(td)
            s.upsert(EXAMPLE)
            self.assertEqual(s.endpoint_map(), {'camera#front_door':'front_door'})
            self.assertNotIn('veryprivate', json.dumps(s.public()))
            self.assertEqual(s.get('front_door')['rtsp_url'], EXAMPLE['rtsp_url'])
            s.upsert({**EXAMPLE, 'rtsp_url': '', 'name': 'New name'})
            self.assertEqual(s.get('front_door')['rtsp_url'], EXAMPLE['rtsp_url'])
            self.assertEqual(Store(td).get('front_door')['name'], 'New name')
            if os.name != 'nt':
                self.assertEqual((Path(td)/'cameras.json').stat().st_mode & 0o077, 0)
                self.assertEqual((Path(td)/'hls_signing_key').stat().st_mode & 0o077, 0)
            self.assertTrue(s.delete('front_door'))
            self.assertFalse(s.delete('front_door'))

    def test_endpoint_collision_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            s = Store(td)
            s.upsert(EXAMPLE)
            with self.assertRaises(ValueError):
                s.upsert({**EXAMPLE, 'slug':'garage'})


class MediaTests(unittest.TestCase):
    def test_auto_mode_chooses_copy_only_for_compatible_h264(self):
        self.assertEqual(select_mode(EXAMPLE, {'codec_name':'h264', 'profile':'Main', 'pix_fmt':'yuv420p'}), 'copy')
        self.assertEqual(select_mode(EXAMPLE, {'codec_name':'hevc', 'profile':'Main'}), 'transcode')
        with self.assertRaises(RuntimeError):
            select_mode({**EXAMPLE, 'mode':'copy'}, {'codec_name':'hevc'})

    def test_ffmpeg_args_keep_credentials_in_argv_not_shell(self):
        folder=Path('/tmp/camera')
        for mode in ('copy','transcode'):
            cmd=stream_command(EXAMPLE, folder, mode)
            self.assertIsInstance(cmd, list)
            self.assertEqual(cmd[cmd.index('-i')+1], EXAMPLE['rtsp_url'])
            self.assertIn('mpegts', cmd)
            self.assertIn('index.m3u8', ' '.join(cmd))
            self.assertEqual('-an', cmd[cmd.index('-an')])
        self.assertIn('snapshot.new.jpg', str(snapshot_command(EXAMPLE, Path('/tmp/snapshot.new.jpg'))))

    def test_watchdog_recovers_only_recently_requested_camera(self):
        with tempfile.TemporaryDirectory() as td:
            s = Store(td)
            s.upsert(EXAMPLE)
            mgr = Manager(s, idle_timeout=30, watchdog=False)
            fake = mock.Mock()
            fake.poll.return_value = None
            with mgr.lock:
                st = mgr._state('front_door')
                st.requested_at = time.monotonic() - 1
                st.retry_after = time.monotonic() - 1
            with mock.patch('promax.media.inspect_source', return_value={
                'codec_name':'h264','profile':'Main','pix_fmt':'yuv420p'}), \
                 mock.patch('promax.media.subprocess.Popen', return_value=fake):
                mgr.watch_once()
            self.assertIs(mgr.states['front_door'].proc, fake)
            self.assertEqual(mgr.states['front_door'].effective_mode, 'copy')
            fake.poll.return_value = 0
            mgr.close()

    def test_watchdog_stops_idle_worker(self):
        with tempfile.TemporaryDirectory() as td:
            s=Store(td);s.upsert(EXAMPLE)
            mgr=Manager(s, idle_timeout=10, watchdog=False)
            proc=mock.Mock();proc.poll.return_value=None;proc.wait.return_value=0;proc.returncode=0
            with mgr.lock:
                st=mgr._state('front_door');st.proc=proc;st.requested_at=time.monotonic()-20
            mgr.watch_once()
            proc.terminate.assert_called_once()
            self.assertIsNone(mgr.states['front_door'].proc)


class HTTPTests(unittest.TestCase):
    def test_snapshot_private_endpoint_rejects_unauthorized_request(self):
        with tempfile.TemporaryDirectory() as td:
            app=Application(td,watchdog=False)
            app.store.upsert(EXAMPLE)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app,admin=True))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with self.assertRaises(HTTPError) as exc:
                    urlopen(f'http://127.0.0.1:{server.server_port}/api/snapshot/front_door')
                self.assertEqual(exc.exception.code,403)
            finally:
                server.shutdown();server.server_close();app.manager.close()

    def test_admin_requires_csrf_and_media_requires_signature(self):
        with tempfile.TemporaryDirectory() as td:
            app=Application(td, watchdog=False)
            app.store.upsert(EXAMPLE)
            admin=ThreadingHTTPServer(('127.0.0.1',0), make_handler(app,admin=True))
            media=ThreadingHTTPServer(('127.0.0.1',0), make_handler(app,admin=False))
            threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in (admin,media)]
            for th in threads:th.start()
            try:
                root=f'http://127.0.0.1:{admin.server_port}'
                with urlopen(root+'/api/state') as response:
                    state=json.load(response)
                self.assertNotIn('veryprivate',json.dumps(state))
                req=Request(root+'/api/cameras',method='POST',data=json.dumps(EXAMPLE).encode(),
                            headers={'Content-Type':'application/json'})
                with self.assertRaises(HTTPError) as e:urlopen(req)
                self.assertEqual(e.exception.code,403)
                with self.assertRaises(HTTPError) as e:urlopen(f'http://127.0.0.1:{media.server_port}/front_door/index.m3u8')
                self.assertEqual(e.exception.code,403)
                hls=app.manager.root/'front_door';hls.mkdir(exist_ok=True)
                (hls/'segment_123.ts').write_bytes(b'TS-TEST')
                url=f'http://127.0.0.1:{media.server_port}'+make_path(app.store.key,'front_door','segment_123.ts')
                with urlopen(url) as response:self.assertEqual(response.read(),b'TS-TEST')
            finally:
                admin.shutdown();media.shutdown();admin.server_close();media.server_close();app.manager.close()


if __name__=='__main__':unittest.main()

"""v0.5 checks: AAC per camera, safe diagnostics, HLS and watchdog recovery."""
from pathlib import Path
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'alexa_bridge'))
from promax.security import check_camera
from promax.store import Store
from promax.media import Manager, stream_command, inspect_audio_source
from promax.service import Application, make_handler

spec = importlib.util.spec_from_file_location('audio_lambda', ROOT / 'aws/lambda_function.py')
lambda_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lambda_module)

CAM = {'slug': 'solario', 'name': 'Solario',
       'rtsp_url': 'rtsp://user:NOT_PUBLIC@127.0.0.1:554/Streaming/Channels/801',
       'mode': 'transcode', 'fps': 15, 'width': 960, 'height': 540,
       'bitrate_kbps': 1000, 'alexa_endpoint_id': 'camera#solario'}


class AudioSettings(unittest.TestCase):
    def test_default_off_and_rejects_other_modes(self):
        self.assertEqual(check_camera(CAM)['audio_mode'], 'off')
        for bad in (True, 'copy', 'unknown', 1, None):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                check_camera({**CAM, 'audio_mode': bad})

    def test_ffmpeg_uses_video_only_or_aac(self):
        off = stream_command(CAM, Path('/tmp/solario'), 'transcode')
        self.assertIn('-an', off)
        self.assertNotIn('0:a:0', off)
        on = stream_command({**CAM, 'audio_mode': 'aac'}, Path('/tmp/solario'), 'transcode')
        self.assertIn('0:a:0', on)
        self.assertIn('-c:a', on)
        self.assertEqual(on[on.index('-c:a')+1], 'aac')
        self.assertNotIn('-an', on)
        # No shell expansion and no credential-bearing command string.
        self.assertIsInstance(on, list)
        self.assertEqual(on[on.index('-i')+1], CAM['rtsp_url'])

    def test_storage_and_lambda_mapping_remain_backward_compatible(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(td)
            store.upsert(CAM)
            self.assertEqual(store.endpoint_map(), {'camera#solario': 'solario'})
            store.upsert({'slug': 'solario', 'audio_mode': 'aac'})
            self.assertEqual(store.endpoint_map(), {'camera#solario': {'slug':'solario', 'audioCodec':'AAC'}})
            self.assertEqual(Store(td).get('solario')['audio_mode'], 'aac')
            self.assertNotIn('NOT_PUBLIC', json.dumps(store.public()))

    def test_lambda_rewrites_audio_only_when_requested(self):
        def perform(mapping):
            payload = {'event': {
                'header': {'namespace': 'Alexa.CameraStreamController', 'name':'Response'},
                'endpoint': {'endpointId': 'camera#solario'},
                'payload': {'cameraStreams': [{'uri':'https://example.org/original','audioCodec':'NONE'}]}}}
            class Response:
                def __enter__(self): return self
                def __exit__(self, *_): return False
                def read(self): return json.dumps(payload).encode()
            environ = {
                'HOME_ASSISTANT_URL':'https://ha.example.org',
                'ALEXA_HLS_BASE':'https://media.example.org',
                'HLS_SIGNING_KEY': 'a' * 64,
                'CAMERA_ENDPOINT_MAP_JSON': json.dumps({'camera#solario':mapping}),
            }
            event = {'directive': {'header': {'payloadVersion':'3', 'messageId':'test'},
                                  'endpoint': {'scope': {'type': 'BearerToken', 'token': 'FAKE'}}}}
            with mock.patch.dict(os.environ,environ), mock.patch.object(lambda_module.request,'urlopen',return_value=Response()):
                return lambda_module.lambda_handler(event,None)['event']['payload']['cameraStreams'][0]
        self.assertEqual(perform('solario')['audioCodec'], 'NONE')
        self.assertEqual(perform({'slug':'solario', 'audioCodec':'AAC'})['audioCodec'], 'AAC')

    def test_probe_audio_absent_returns_none(self):
        with mock.patch('promax.media._probe_stream', return_value=None) as fn:
            self.assertIsNone(inspect_audio_source('rtsp://camera.local/a'))
        self.assertEqual(fn.call_args.args[1], 'a:0')


class RecoveryTests(unittest.TestCase):
    def test_stalled_segments_schedule_backoff_without_credentials_in_events(self):
        with tempfile.TemporaryDirectory() as td:
            store = Store(td)
            store.upsert(CAM)
            mgr = Manager(store, watchdog=False)
            fake = mock.Mock()
            fake.poll.return_value = None
            fake.returncode = 0
            with mgr.lock:
                st = mgr._state('solario')
                st.proc = fake
                st.started_at = time.monotonic()-30
                st.requested_at = time.monotonic()-1
            mgr.watch_once()
            status=mgr.status()['solario']
            self.assertFalse(status['running'])
            self.assertEqual(status['stalls'], 1)
            self.assertGreater(status['cooldown_seconds'], 0)
            self.assertEqual(status['recoveries'],0)
            self.assertNotIn('NOT_PUBLIC', json.dumps(mgr.recent_events()))
            fake.terminate.assert_called_once()
            mgr.close()

    def test_auto_recovery_starts_only_a_recently_requested_camera(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(td)
            store.upsert(CAM)
            mgr=Manager(store,watchdog=False)
            fake=mock.Mock()
            fake.poll.return_value=None
            with mgr.lock:
                st=mgr._state('solario')
                st.requested_at=time.monotonic()-1
                st.retry_after=time.monotonic()-1
                st.pending_recovery=True
            with mock.patch('promax.media.subprocess.Popen',return_value=fake):
                mgr.watch_once()
            self.assertEqual(mgr.status()['solario']['recoveries'],1)
            self.assertTrue(mgr.status()['solario']['running'])
            mgr.close()

    def test_manual_restart_does_not_start_idle_cameras(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(td)
            store.upsert(CAM)
            mgr=Manager(store,watchdog=False)
            self.assertFalse(mgr.restart('solario'))
            self.assertEqual(mgr.status()['solario']['starts'],0)
            mgr.close()


class ProtectedEndpoints(unittest.TestCase):
    def test_diagnostics_requires_admin_csrf_and_returns_safe_values(self):
        with tempfile.TemporaryDirectory() as td:
            app=Application(td,watchdog=False)
            app.store.upsert(CAM)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app,admin=True))
            thread=Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                addr=f'http://127.0.0.1:{server.server_port}'
                with self.assertRaises(HTTPError) as e:
                    urlopen(addr+'/api/diagnostics')
                self.assertEqual(e.exception.code,403)
                req=Request(addr+'/api/diagnostics',headers={'X-Bridge-CSRF':app.csrf})
                with urlopen(req) as r:
                    data=json.load(r)
                self.assertFalse(data['watchdog_enabled'])  # Test disables background watchdog
                self.assertIn('system',data)
                self.assertNotIn('NOT_PUBLIC',json.dumps(data))
                with self.assertRaises(HTTPError) as e:
                    urlopen(Request(addr+'/api/restart/solario',data=b'{}',headers={'Content-Type':'application/json'}))
                self.assertEqual(e.exception.code,403)
                req=Request(addr+'/api/restart/solario',data=b'{}',headers={'Content-Type':'application/json','X-Bridge-CSRF':app.csrf})
                with urlopen(req) as r:
                    result=json.load(r)
                self.assertFalse(result['restarted'])
            finally:
                server.shutdown();server.server_close();app.manager.close()


class RealFFmpegAudio(unittest.TestCase):
    def test_off_and_aac_contain_expected_streams(self):
        if not all(__import__('shutil').which(x) for x in ('ffmpeg','ffprobe')):
            self.skipTest('FFmpeg not available')
        with tempfile.TemporaryDirectory() as td:
            inp=Path(td)/'input.ts'
            make = ['ffmpeg','-hide_banner','-nostdin','-loglevel','error',
                    '-f','lavfi','-i','testsrc2=size=160x120:rate=5',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000',
                    '-t','2','-c:v','libx264','-preset','ultrafast','-c:a','aac',
                    '-f','mpegts','-y',str(inp)]
            result=subprocess.run(make,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=20)
            if result.returncode:
                self.fail('Could not create test MPEG-TS media')
            for audio in ('off','aac'):
                with self.subTest(audio=audio):
                    target=Path(td)/audio
                    target.mkdir()
                    cam={**CAM,'rtsp_url':str(inp),'width':320,'height':240,'fps':5,'audio_mode':audio}
                    command=stream_command(cam,target,'transcode')
                    ix=command.index('-rtsp_transport');del command[ix:ix+2]
                    # Keep the output bounded; this uses local generated media.
                    command[command.index('-i')+1] = str(inp)
                    command[1:1] = ['-y']
                    result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=30)
                    if result.returncode:
                        self.fail('FFmpeg HLS mux failed in mode '+audio)
                    segments=list(target.glob('segment_*.ts'))
                    self.assertTrue(segments)
                    probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name',
                        '-of','json',str(segments[0])],capture_output=True,timeout=10)
                    streams=json.loads(probe.stdout)['streams']
                    types={s.get('codec_type') for s in streams}
                    self.assertIn('video', types)
                    self.assertEqual('audio' in types, audio=='aac')
                    if audio=='aac':
                        self.assertIn('aac', [s.get('codec_name') for s in streams])


if __name__=='__main__': unittest.main()

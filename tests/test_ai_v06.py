"""v0.6 AI: secure API, configuration, evidence, feedback, and deterministic image processing."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import mock
import json
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'alexa_bridge'))
from promax.ai_store import AIStore
from promax.service import Application, make_handler

CAM = dict(slug='solario', name='Solario',rtsp_url='rtsp://test:PRIVATE@127.0.0.1:554/101',
           mode='auto', width=960, height=540, fps=15,bitrate_kbps=1000,
           alexa_endpoint_id='camera#solario')
JPEG = b'\xff\xd8' + b'fakejpegdata' * 10


class StoreTests(unittest.TestCase):
    def test_off_by_default_and_private_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            ai=AIStore(td)
            self.assertFalse(ai.public_config()['enabled'])
            ai.save_config({'camera':{'slug':'solario','enabled':True,
                                     'substream':'rtsp://test:VERY_PRIVATE@192.168.0.1/stream'}}, {'solario'})
            self.assertTrue(ai.public_config()['cameras']['solario']['substream_configured'])
            self.assertNotIn('VERY_PRIVATE',json.dumps(ai.public_config()))
            self.assertIn('VERY_PRIVATE',ai.config()['cameras']['solario']['substream'])
            self.assertEqual((Path(td)/'ai/config.json').stat().st_mode & 0o777,0o600)

    def test_validation_maximum_cameras_and_bad_values(self):
        with tempfile.TemporaryDirectory() as td:
            ai=AIStore(td)
            for slug in ('solario','jardin','pasillo'):
                ai.save_config({'camera':{'slug':slug,'enabled':True}},set(('solario','jardin','pasillo')))
            with self.assertRaisesRegex(ValueError,'Maximum two'):
                ai.save_config({'enabled':True},{'solario','jardin','pasillo'})
            for bad in ({'interval_seconds': 0}, {'confidence':True}, {'camera':{'slug':'unknown'}},
                        {'camera':{'slug':'solario','substream':'http://example.com/foo'}},
                        {'enabled':'true'}):
                with self.subTest(bad=bad),self.assertRaises(ValueError):
                    ai.save_config(bad,{'solario','jardin','pasillo'})

    def test_event_feedback_image_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            ai=AIStore(td)
            eid=ai.add_event('solario','person',0.89,JPEG,[1,2,3,4])
            self.assertEqual(ai.image(eid),JPEG)
            self.assertIsNone(ai.image('../../secret'))
            self.assertEqual(ai.events()[0]['feedback'],'pending')
            self.assertTrue(ai.feedback(eid,'false_positive'))
            self.assertEqual(ai.events()[0]['feedback'],'false_positive')
            self.assertEqual(ai.summary()['total'],1)
            self.assertEqual(ai.summary()['feedback']['false_positive'],1)
            self.assertFalse(ai.feedback('0'*32,'confirmed'))
            self.assertNotIn('PRIVATE',json.dumps(ai.events()))
            self.assertEqual((Path(td)/'ai/snapshots'/f'{eid}.jpg').stat().st_mode & 0o777,0o600)
            for category in ('password','face_id'):
                with self.assertRaises(ValueError):
                    ai.add_event('solario',category,.9,JPEG,[])


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app=Application(self.tmp.name,watchdog=False)
        self.app.store.upsert(CAM)
        self.admin=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app,admin=True))
        self.media=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app,admin=False))
        self.th=Thread(target=self.admin.serve_forever,daemon=True)
        self.th2=Thread(target=self.media.serve_forever,daemon=True)
        self.th.start();self.th2.start()
        self.url=f'http://127.0.0.1:{self.admin.server_port}'
        self.media_url=f'http://127.0.0.1:{self.media.server_port}'
    def tearDown(self):
        self.admin.shutdown();self.admin.server_close()
        self.media.shutdown();self.media.server_close()
        self.app.manager.close();self.tmp.cleanup()
    def _req(self,path,method='GET',payload=None,csrf=True):
        headers={'X-Bridge-CSRF':self.app.csrf} if csrf else {}
        if payload is not None:
            headers['Content-Type']='application/json'
            payload=json.dumps(payload).encode()
        req=Request(self.url+path,data=payload,headers=headers,method=method)
        return urlopen(req,timeout=3)
    def test_ai_admin_auth_and_hls_isolation(self):
        for path in ('/api/ai/config','/api/ai/events'):
            with self.assertRaises(HTTPError) as e:
                self._req(path,csrf=False)
            self.assertEqual(e.exception.code,403)
            with self.assertRaises(HTTPError) as e:
                urlopen(self.media_url+path,timeout=3)
            self.assertEqual(e.exception.code,403)
        with self._req('/api/ai/config') as response:
            config=json.load(response)
        self.assertFalse(config['config']['enabled'])
        self.assertEqual(config['status']['state'],'not_started')
        self.assertNotIn('PRIVATE',json.dumps(config))

    def test_feedback_via_admin_api(self):
        eid=self.app.ai.add_event('solario','car',.81,JPEG,[])
        with self._req('/api/ai/feedback/'+eid,'POST',{'feedback':'confirmed'}) as r:
            self.assertTrue(json.load(r)['ok'])
        with self._req('/api/ai/events') as r:
            self.assertEqual(json.load(r)['events'][0]['feedback'],'confirmed')
        with self._req('/api/ai/snapshot/'+eid) as r:
            self.assertEqual(r.read(),JPEG)
        with self.assertRaises(HTTPError) as e:
            self._req('/api/ai/snapshot/'+eid,csrf=False)
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(HTTPError) as e:
            self._req('/api/ai/feedback/'+eid,'POST',{'feedback':'unexpected'})
        self.assertEqual(e.exception.code,400)

    def test_update_ai_and_preserve_existing_cameras(self):
        with self._req('/api/ai/config','POST',{'camera':{'slug':'solario','enabled':True}}) as r:
            self.assertTrue(json.load(r)['config']['cameras']['solario']['enabled'])
        with self._req('/api/ai/config','POST',{'enabled':True,'interval_seconds':5}) as r:
            self.assertTrue(json.load(r)['config']['enabled'])
        with self._req('/api/state') as r:
            state=json.load(r)
        self.assertEqual(state['version'],'0.6.1b1')
        self.assertEqual(len(state['cameras']),1)
        self.assertNotIn('PRIVATE',json.dumps(state))


class ImageAlgorithms(unittest.TestCase):
    def test_motion_gate_detects_changed_image(self):
        try:
            import cv2,numpy as np
        except ImportError:
            self.skipTest('opencv/numpy not installed')
        from promax.ai_engine import MotionGate
        a=np.zeros((90,160,3),dtype=np.uint8)
        b=a.copy();b[15:60,20:70,:]=255
        gate=MotionGate()
        self.assertTrue(gate.active(a))
        self.assertFalse(gate.active(a))
        self.assertTrue(gate.active(b))

    def test_yolox_grid_decode_known_object(self):
        try:
            import cv2,numpy as np
        except ImportError:
            self.skipTest('opencv/numpy not installed')
        from promax.ai_engine import decode_yolox
        pred=np.zeros((1,3549,85),dtype=np.float32)
        # Cell at stride 8, x=3,y=2: center (28,20), 32x32 box.
        idx=2*52+3
        pred[0,idx,:4]=(0.5,0.5,float(np.log(4)),float(np.log(4)))
        pred[0,idx,4]=0.9
        pred[0,idx,5+2]=0.9
        found=decode_yolox(pred,confidence=.5)
        self.assertEqual(len(found),1)
        category,score,box=found[0]
        self.assertEqual(category,'car')
        self.assertGreater(score,.8)
        self.assertGreater(box[2]-box[0],20)

    def test_tracker_does_not_emit_on_stale_detection(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy not installed')
        import types
        class Detection:
            def __init__(self,points,data):
                self.points=points
                self.data=data
        class FakeTrack:
            def __init__(self):
                self.last_detection=None
                self.id=7
        class Tracker:
            def __init__(self,**_):self.track=FakeTrack()
            def update(self,detections):
                if detections:
                    self.track.last_detection=detections[0]
                return [self.track] if self.track.last_detection else []
        from promax.ai_engine import TrackBuffer
        with mock.patch.dict(sys.modules,{'norfair':types.SimpleNamespace(Tracker=Tracker,Detection=Detection)}):
            tracker=TrackBuffer()
            obj=[('person',0.9,[10,10,35,50])]
            self.assertEqual(tracker.ready(obj,60),[])
            self.assertEqual(len(tracker.ready(obj,60)),1)
            self.assertEqual(tracker.ready([],60),[])

    def test_ha_notification_only_when_explicitly_configured(self):
        from promax.ai_engine import notify_home_assistant
        with mock.patch.dict('os.environ',{},clear=True):
            self.assertFalse(notify_home_assistant('solario','person',.9,'a'*32))
        with mock.patch.dict('os.environ',{'AI_HA_URL':'https://ha.example', 'AI_HA_TOKEN':'abc'},clear=True), \
                mock.patch('promax.ai_engine.request.urlopen') as fn:
            fn.return_value.__enter__.return_value.status=200
            self.assertTrue(notify_home_assistant('solario','person',.9,'a'*32))
            self.assertIn('/api/events/alexa_rtsp_ai_detection',fn.call_args.args[0].full_url)
            self.assertNotIn('abc',fn.call_args.args[0].data.decode())

if __name__=='__main__':unittest.main()

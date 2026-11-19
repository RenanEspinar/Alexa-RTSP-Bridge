"""v0.6.1: opt-in annotated diagnostic preview, privacy and fast traffic mode."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest import TestCase, mock
import json, sys, tempfile, time, types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'alexa_bridge'))
from promax.ai_store import AIStore
from promax.service import Application,make_handler

CAM={'slug':'gladiolos','name':'Gladiolos','rtsp_url':'rtsp://user:secret@127.0.0.1:554/701',
     'mode':'auto','width':960,'height':540,'fps':15,'bitrate_kbps':1000}
JPEG=b'\xff\xd8'+b'valid-test-preview'*15+b'\xff\xd9'

class StorePreviewTests(TestCase):
    def test_preview_only_while_watched_and_nonpersistent_api(self):
        with tempfile.TemporaryDirectory() as d:
            a=AIStore(d)
            self.assertFalse(a.preview_watched('gladiolos'))
            self.assertFalse(a.save_preview('gladiolos', JPEG, boxes=[], analyzed=True,
                                             motion=False,inference_ms=32.0))
            a.set_preview_watch('gladiolos', True)
            self.assertTrue(a.preview_watched('gladiolos'))
            ok=a.save_preview('gladiolos', JPEG, boxes=[('truck',.9,[1,2,3,4])],
                              analyzed=True,motion=True,inference_ms=42.3)
            self.assertTrue(ok)
            self.assertEqual(a.preview_jpeg('gladiolos'),JPEG)
            info=a.preview_info('gladiolos')
            self.assertEqual(info['objects'][0]['category'],'truck')
            self.assertEqual(info['objects'][0]['bbox'],[1,2,3,4])
            self.assertNotIn('secret',json.dumps(info))
            a.set_preview_watch('gladiolos',False)
            self.assertIsNone(a.preview_info('gladiolos'))
            self.assertFalse((Path(d)/'ai/previews/gladiolos.jpg').exists())
            with self.assertRaises(ValueError):a.set_preview_watch('../etc',True)

    def test_road_mode_is_private_and_validated(self):
        with tempfile.TemporaryDirectory() as d:
            a=AIStore(d)
            a.save_config({'camera':{'slug':'gladiolos','enabled':True,'road_mode':True}}, {'gladiolos'})
            c=a.public_config()['cameras']['gladiolos']
            self.assertTrue(c['road_mode'])
            self.assertTrue(c['enabled'])
            a.save_config({'interval_seconds':1},{'gladiolos'})
            self.assertEqual(a.config()['interval_seconds'],1)
            with self.assertRaisesRegex(ValueError,'Road mode must be boolean'):
                a.save_config({'camera':{'slug':'gladiolos','road_mode':'yes'}},{'gladiolos'})

class PreviewHttpTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=Application(self.temp.name,watchdog=False)
        self.app.store.upsert(CAM)
        self.servers=[ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app,admin=a)) for a in (True,False)]
        for server in self.servers:Thread(target=server.serve_forever,daemon=True).start()
        self.base=[f'http://127.0.0.1:{s.server_port}' for s in self.servers]
    def tearDown(self):
        for s in self.servers:s.shutdown();s.server_close()
        self.app.manager.close()
        self.temp.cleanup()
    def req(self,path,*,method='GET',data=None,admin=True,csrf=True):
        hdr={'X-Bridge-CSRF':self.app.csrf} if csrf else {}
        payload=json.dumps(data).encode() if data is not None else None
        if payload is not None:hdr['Content-Type']='application/json'
        return urlopen(Request(self.base[0 if admin else 1]+path,headers=hdr,data=payload,method=method),timeout=4)
    def test_viewer_requires_enabled_camera_and_csrf(self):
        with self.assertRaises(HTTPError) as exc:
            self.req('/api/ai/watch/gladiolos',method='POST',data={'watch':True})
        self.assertEqual(exc.exception.code,400)
        self.app.ai.save_config({'camera':{'slug':'gladiolos','enabled':True}}, {'gladiolos'})
        self.app.ai.save_config({'enabled':True}, {'gladiolos'})
        with self.assertRaises(HTTPError) as exc:
            self.req('/api/ai/watch/gladiolos',method='POST',data={'watch':True},csrf=False)
        self.assertEqual(exc.exception.code,403)
        with self.req('/api/ai/watch/gladiolos',method='POST',data={'watch':True}) as r:
            self.assertTrue(json.load(r)['watch'])
        self.app.ai.save_preview('gladiolos',JPEG,boxes=[('car',.93,[2,3,4,5])],
                                 analyzed=True,motion=True,inference_ms=70)
        with self.req('/api/ai/preview/gladiolos') as r:
            self.assertEqual(r.read(),JPEG)
        with self.req('/api/ai/preview-status/gladiolos') as r:
            data=json.load(r)['preview']
            self.assertEqual(data['objects'][0]['category'],'car')
        for p in ['/api/ai/preview/gladiolos','/api/ai/preview-status/gladiolos']:
            with self.assertRaises(HTTPError) as exc:self.req(p,csrf=False)
            self.assertEqual(exc.exception.code,403)
            with self.assertRaises(HTTPError) as exc:self.req(p,admin=False)
            self.assertEqual(exc.exception.code,403)
        with self.req('/api/ai/watch/gladiolos',method='POST',data={'watch':False}) as r:
            self.assertFalse(json.load(r)['watch'])
        with self.assertRaises(HTTPError) as exc:self.req('/api/ai/preview/gladiolos')
        self.assertEqual(exc.exception.code,404)

class RoadModeTrackingTests(TestCase):
    def test_fast_traffic_emits_single_high_confidence_observation(self):
        try:import numpy
        except ImportError:self.skipTest('numpy unavailable')
        class DummyTrack:
            last_detection=None
        class Tracker:
            def __init__(self,**k):pass
            def update(self,**k):return []
        class Detection:
            def __init__(self,*args,**kwargs):pass
        from promax.ai_engine import TrackBuffer
        with mock.patch.dict(sys.modules,{'norfair':types.SimpleNamespace(Tracker=Tracker,Detection=Detection)}):
            t=TrackBuffer()
            detection=[('truck',0.89,[10,20,90,110])]
            self.assertEqual(t.ready(detection,60,fast_traffic=False),[])
            self.assertEqual(t.ready(detection,60,fast_traffic=True),detection)
            self.assertEqual(t.ready(detection,60,fast_traffic=True),[])

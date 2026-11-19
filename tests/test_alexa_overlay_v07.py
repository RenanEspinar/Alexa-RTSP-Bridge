"""Opt-in HLS drawing should preserve original media defaults and never expose AI data."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'alexa_bridge'))
from promax.ai_store import AIStore
from promax.media import stream_command
from promax.overlay import overlay_filters, project_boxes
from promax.security import check_camera
from promax.store import Store

CAM=dict(slug='road',name='Road',rtsp_url='rtsp://127.0.0.1:554/test',
         mode='auto',width=960,height=540,fps=15,bitrate_kbps=1000,
         alexa_endpoint_id='camera#road')

class OverlayTests(unittest.TestCase):
    def test_default_unchanged_and_option_is_validated(self):
        self.assertEqual(check_camera(CAM)['overlay_mode'],'off')
        with tempfile.TemporaryDirectory() as td:
            store=Store(td)
            store.upsert(CAM)
            self.assertEqual(store.get('road')['overlay_mode'],'off')
            self.assertEqual(Store(td).get('road')['overlay_mode'],'off')
        with self.assertRaisesRegex(ValueError,'Overlay mode'):
            check_camera({**CAM,'overlay_mode':'private_url'})

    def test_only_one_overlay_camera_can_be_enabled(self):
        with tempfile.TemporaryDirectory() as td:
            store=Store(td)
            store.upsert({**CAM,'overlay_mode':'boxes'})
            with self.assertRaisesRegex(ValueError,'Only one Alexa AI overlay'):
                store.upsert({**CAM,'slug':'road2','name':'Road Two',
                              'alexa_endpoint_id':'camera#road2','overlay_mode':'boxes'})
            store.upsert({**CAM,'overlay_mode':'off'})
            store.upsert({**CAM,'slug':'road2','name':'Road Two',
                          'alexa_endpoint_id':'camera#road2','overlay_mode':'boxes'})

    def test_hls_uses_same_encoder_and_no_new_network_surface(self):
        with tempfile.TemporaryDirectory() as td:
            original=stream_command(check_camera(CAM),Path(td),'transcode')
            self.assertNotIn('zmq=',original[original.index('-vf')+1])
            overlay_cam=check_camera({**CAM,'overlay_mode':'boxes'})
            with self.assertRaises(ValueError):
                stream_command(overlay_cam,Path(td),'copy',overlay_port=5500)
            cmd=stream_command(overlay_cam,Path(td),'transcode',overlay_port=5500)
            self.assertIn('drawbox@b0',cmd[cmd.index('-vf')+1])
            self.assertIn('zmq=',cmd[cmd.index('-vf')+1])
            self.assertIn('libx264',cmd)
            self.assertIn('mpegts',cmd)
            self.assertIn('ultrafast',cmd)

    def test_projection_keeps_aspect_ratio(self):
        boxes=project_boxes({'epoch':100,'width':1920,'height':1080,'objects':[
            {'category':'person','confidence':.8,'bbox':[960,540,1152,756]}]},
            960,540,now=101)
        self.assertEqual(boxes,[(480,270,96,108,'lime@0.95')])
        boxes=project_boxes({'epoch':100,'width':1280,'height':720,'objects':[
            {'category':'truck','confidence':.9,'bbox':[100,100,300,300]}]},
            640,480,now=101)
        self.assertEqual(boxes,[(50,110,100,100,'cyan@0.95')])
        self.assertEqual(project_boxes({'epoch':100,'width':1920,'height':1080,'objects':[]},960,540,now=105),[])

    def test_private_metadata_contains_no_camera_password(self):
        with tempfile.TemporaryDirectory() as td:
            ai=AIStore(td)
            ai.save_live_boxes('road',width=640,height=360,
                               objects=[('car',.76,[30,40,100,120])])
            data=(Path(td)/'ai/overlay/road.json').read_text()
            self.assertEqual(json.loads(data)['objects'][0]['category'],'car')
            self.assertNotIn('rtsp://',data)
            self.assertEqual((Path(td)/'ai/overlay/road.json').stat().st_mode & 0o777,0o600)

    def test_ffmpeg_dynamic_box_visible_on_synthetic_video(self):
        """Integration test on runners with FFmpeg ZMQ and OpenCV installed."""
        try:
            import cv2
            import zmq
        except ImportError:
            self.skipTest('FFmpeg overlay dependencies are not installed')
        import shutil
        import subprocess
        from promax.overlay import OverlayController
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('FFmpeg not installed')
        support=subprocess.run(['ffmpeg','-hide_banner','-filters'],capture_output=True,text=True)
        if ' zmq ' not in support.stdout:
            self.skipTest('FFmpeg was built without zmq filter')
        with tempfile.TemporaryDirectory() as td:
            camera={**CAM,'width':320,'height':180}
            controller=OverlayController(td,'road',camera)
            output=Path(td)/'video.ts'
            vf=overlay_filters(controller.port)
            cmd=['ffmpeg','-hide_banner','-loglevel','error','-re','-f','lavfi','-i',
                 'color=c=black:size=320x180:rate=10','-vf',vf,
                 '-t','7.0','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
                 '-f','mpegts','-y',str(output)]
            p=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            controller.start(p)
            try:
                time.sleep(.7)
                AIStore(td).save_live_boxes('road',width=320,height=180,
                     objects=[('car',.83,[50,40,150,120])])
                time.sleep(3.5)
                AIStore(td).save_live_boxes('road',width=320,height=180,objects=[])
                self.assertEqual(p.wait(timeout=8),0,p.stderr.read().decode()[:500])
                # Sample when box should have been painted (t=1.7 s).
                img=Path(td)/'frame.png'
                subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(output),'-ss','3.5',
                     '-frames:v','1','-update','1','-y',str(img)],check=True,timeout=8)
                frame=cv2.imread(str(img))
                self.assertIsNotNone(frame)
                self.assertGreater(int(frame[40,80].max()),60,
                    'Dynamic bounding rectangle was not burned into the HLS-compatible video')
                img2=Path(td)/'frame_clear.png'
                subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-i',str(output),'-ss','6.0',
                     '-frames:v','1','-update','1','-y',str(img2)],check=True,timeout=8)
                clear=cv2.imread(str(img2))
                self.assertLess(int(clear[40,80].max()),30,
                    'Overlay did not clear a stale bounding rectangle')
            finally:
                controller.stop()
                if p.poll() is None:p.terminate();p.wait(timeout=5)
                p.stderr.close()

if __name__=='__main__':unittest.main()

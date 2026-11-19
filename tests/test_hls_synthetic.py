"""Smoke-test the signed HTTP gateway using real H.264/HLS bytes from a test pattern."""
import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'alexa_bridge'))
from promax.service import Application, make_handler
from promax.security import make_path

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg not available on the test runner')
class SyntheticHLSTests(unittest.TestCase):
    def test_signed_playlist_and_real_ts_playback(self):
        with tempfile.TemporaryDirectory() as td:
            app=Application(td,watchdog=False)
            app.store.upsert({'slug':'test_cam','name':'Test card','rtsp_url':'rtsp://localhost/test',
                              'mode':'transcode'})
            target=app.manager.root/'test_cam'; target.mkdir()
            cmd=['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi',
                 '-i','testsrc2=size=320x240:rate=15','-t','3','-c:v','libx264',
                 '-profile:v','baseline','-pix_fmt','yuv420p','-g','15','-an',
                 '-f','hls','-hls_time','1','-hls_list_size','6',
                 '-hls_segment_type','mpegts',
                 '-hls_segment_filename',str(target/'segment_%06d.ts'),str(target/'index.m3u8')]
            subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
            server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(app))
            th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
            app.manager.request=lambda slug:target/'index.m3u8'
            try:
                root=f'http://127.0.0.1:{server.server_port}'
                playlist_url=root+make_path(app.store.key,'test_cam')
                with urlopen(playlist_url) as response:
                    playlist=response.read().decode()
                self.assertIn('#EXTM3U',playlist)
                segment_name=next(s for s in playlist.splitlines() if s.endswith('.ts'))
                with urlopen(root+make_path(app.store.key,'test_cam',segment_name)) as response:
                    data=response.read()
                self.assertGreater(len(data),1000)
                self.assertEqual(data[0],0x47) # MPEG transport stream sync byte
                probe=subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_name',
                                      '-of','json',str(target/segment_name)],capture_output=True,check=True)
                self.assertIn('h264',probe.stdout.decode())
            finally:
                server.shutdown();server.server_close();app.manager.close()

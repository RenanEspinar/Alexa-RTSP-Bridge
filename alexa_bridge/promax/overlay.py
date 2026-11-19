"""Experimental private metadata -> FFmpeg drawbox, without an extra video decoder.

Only the local gateway connects to the runtime ZMQ socket bound on loopback.
No RTSP URL or secret is sent over the command channel.  Boxes are best-effort:
YOLOX observations can lag rapidly moving objects, and are never predictions.
"""
from __future__ import annotations
import json
from pathlib import Path
import socket
import threading
import time

MAX_BOXES = 4


def overlay_filters(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Invalid private overlay port')
    # Two escape layers: FFmpeg filtergraph and the zmq filter's option parser.
    commands = [f'zmq=b=tcp\\\\://127.0.0.1\\\\:{port}']
    commands += [f'drawbox@b{i}=x=0:y=0:w=2:h=2:color=lime@0:t=3'
                 for i in range(MAX_BOXES)]
    return ','.join(commands)


def project_boxes(payload, output_width, output_height, *, now=None):
    """Map source boxes through the gateway's aspect-preserving scale + pad."""
    now = time.time() if now is None else now
    if not isinstance(payload, dict):
        return []
    try:
        ttl=float(payload.get('ttl',4))
        if not 1 <= ttl <= 8 or not 0 <= now-float(payload.get('epoch', -1e9)) <= ttl:
            return []
    except (ValueError,TypeError):
        return []
    w = payload.get('width');h = payload.get('height')
    if (type(w) is not int or type(h) is not int or
            not 1 <= w <= 8192 or not 1 <= h <= 8192):
        return []
    ratio=min(output_width/w, output_height/h)
    pad_x=(output_width-w*ratio)/2
    pad_y=(output_height-h*ratio)/2
    boxes=[]
    for obj in payload.get('objects', [])[:8]:
        try:
            box=obj['bbox']; category=obj['category']; conf=float(obj['confidence'])
            if category not in {'person','bicycle','car','motorcycle','bus','truck','cat','dog'}:
                continue
            if len(box)!=4 or not 0 <= conf <= 1:continue
            x1,y1,x2,y2=map(float,box)
            if not (0<=x1<x2<=w and 0<=y1<y2<=h):continue
            x=max(0,round(x1*ratio+pad_x))
            y=max(0,round(y1*ratio+pad_y))
            bw=max(2,min(output_width-x,round((x2-x1)*ratio)))
            bh=max(2,min(output_height-y,round((y2-y1)*ratio)))
            if x+bw>output_width or y+bh>output_height:continue
            color='lime@0.95' if category=='person' else 'cyan@0.95'
            boxes.append((conf, (x,y,bw,bh,color)))
        except (ValueError,TypeError,KeyError):
            continue
    boxes.sort(key=lambda item:item[0],reverse=True)
    return [box for _,box in boxes[:MAX_BOXES]]


def choose_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


class OverlayController:
    def __init__(self, data_root, slug, camera):
        self.slug=slug
        self.path=Path(data_root)/'ai'/'overlay'/(slug+'.json')
        self.width=int(camera['width'])
        self.height=int(camera['height'])
        self.port=choose_loopback_port()
        self._stop=threading.Event()
        self._thread=None

    def start(self, process):
        self._thread=threading.Thread(target=self._run,args=(process,),daemon=True,
                                      name='overlay-'+self.slug)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _read(self):
        try:
            payload=json.loads(self.path.read_text(encoding='utf-8'))
            return project_boxes(payload,self.width,self.height)
        except (OSError,ValueError,TypeError,json.JSONDecodeError):
            return []

    def _run(self, process):
        try:
            import zmq
        except ImportError:
            return  # A missing dependency cannot interrupt ordinary HLS playback.
        ctx=zmq.Context.instance()
        sock=None
        prev=[(0,0,2,2,'lime@0')]*MAX_BOXES
        while not self._stop.is_set() and process.poll() is None:
            values=self._read()
            padded=values+[(0,0,2,2,'lime@0')]*(MAX_BOXES-len(values))
            if prev != padded:
                try:
                    if sock is None:
                        sock=ctx.socket(zmq.REQ)
                        sock.setsockopt(zmq.RCVTIMEO,250)
                        sock.setsockopt(zmq.SNDTIMEO,250)
                        sock.setsockopt(zmq.LINGER,0)
                        sock.connect(f'tcp://127.0.0.1:{self.port}')
                    # Each update targets an already-running drawbox filter.
                    for i,(x,y,w,h,color) in enumerate(padded):
                        if prev is not None and padded[i]==prev[i]:continue
                        for name,option in (('x',x),('y',y),('w',w),('h',h),('color',color)):
                            sock.send_string(f'drawbox@b{i} {name} {option}')
                            reply=sock.recv_string()
                            if not reply.startswith('0 Success'):
                                raise RuntimeError('FFmpeg rejected private overlay command')
                    prev=padded
                except (zmq.ZMQError,RuntimeError):
                    if sock is not None:sock.close(linger=0)
                    sock=None
                    prev=[(0,0,2,2,'lime@0')]*MAX_BOXES
            self._stop.wait(0.35)
        if sock is not None:
            sock.close(linger=0)

"""Opt-in YOLOX-Nano/ONNX CPU sidecar. Not imported by the media gateway.

COCO model: https://github.com/Megvii-BaseDetection/YOLOX (Apache-2.0).
ONNX input: [1,3,416,416] BGR float32; output: [1,3549,85], raw YOLOX grids.
"""
from __future__ import annotations

from collections import defaultdict
import logging
import os
from pathlib import Path
import signal
import time
from urllib import request

from .ai_store import AIStore, CATEGORIES
from .store import Store

MODEL_SHA256 = 'c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d'
COCO_CLASSES = {0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle',
                5: 'bus', 7: 'truck', 15: 'cat', 16: 'dog'}
LOG = logging.getLogger('pro-ai')


def decode_yolox(output, *, confidence=0.45, input_size=416, frame_width=416, frame_height=416):
    """Decode 3549 anchor-free YOLOX raw predictions; return [(class, score, bbox)]."""
    import cv2
    import numpy as np
    pred = np.asarray(output, dtype=np.float32).reshape(-1, 85).copy()
    grids, expanded = [], []
    for stride in (8, 16, 32):
        n = input_size // stride
        yy, xx = np.meshgrid(np.arange(n), np.arange(n), indexing='ij')
        grids.append(np.stack((xx, yy), axis=-1).reshape(-1, 2))
        expanded.append(np.full((n*n, 1), stride))
    grid = np.concatenate(grids).astype(np.float32)
    scale = np.concatenate(expanded).astype(np.float32)
    if len(pred) != len(grid):
        raise ValueError('Unexpected YOLOX output dimensions')
    centers = (pred[:, :2] + grid) * scale
    wh = np.exp(np.clip(pred[:, 2:4], -10, 10)) * scale
    ratio = min(input_size/frame_width, input_size/frame_height)
    x1 = np.clip((centers[:,0] - wh[:,0]/2) / ratio, 0, frame_width)
    y1 = np.clip((centers[:,1] - wh[:,1]/2) / ratio, 0, frame_height)
    w = np.clip(wh[:,0] / ratio, 0, frame_width)
    h = np.clip(wh[:,1] / ratio, 0, frame_height)
    results = []
    for cls, name in COCO_CLASSES.items():
        scores = pred[:,4] * pred[:,5+cls]
        candidate = np.flatnonzero(scores >= confidence)
        if not len(candidate):
            continue
        boxes = [[int(x1[i]), int(y1[i]), int(w[i]), int(h[i])] for i in candidate]
        hits = cv2.dnn.NMSBoxes(boxes, scores[candidate].tolist(), confidence, 0.45)
        for local in np.asarray(hits).reshape(-1):
            i = candidate[int(local)]
            bx = [max(0, int(x1[i])), max(0, int(y1[i])),
                  min(frame_width, int(x1[i]+w[i])), min(frame_height, int(y1[i]+h[i]))]
            if bx[2] > bx[0] and bx[3] > bx[1]:
                results.append((name, float(scores[i]), bx))
    return results


class YOLOXNano:
    def __init__(self, path):
        import hashlib
        import onnxruntime as ort
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError('Missing verified YOLOX Nano model; see docs/PRO_AI_V06_ES.md')
        sha = hashlib.sha256(self.path.read_bytes()).hexdigest()
        if sha != MODEL_SHA256:
            raise RuntimeError('Model checksum mismatch; refusing to execute unverified ONNX')
        self.session = ort.InferenceSession(str(path), sess_options=self._opts(ort),
                                            providers=['CPUExecutionProvider'])
        if list(self.session.get_inputs()[0].shape) != [1, 3, 416, 416]:
            raise RuntimeError('Unexpected YOLOX model input shape')
        self.input_name = self.session.get_inputs()[0].name

    @staticmethod
    def _opts(ort):
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        return opts

    def infer(self, frame, threshold):
        import cv2
        import numpy as np
        height, width = frame.shape[:2]
        ratio = min(416/width, 416/height)
        resized = cv2.resize(frame, (int(width*ratio), int(height*ratio)))
        padded = np.full((416,416,3), 114, dtype=np.uint8)
        padded[:resized.shape[0], :resized.shape[1]] = resized
        tensor = padded.transpose(2,0,1)[None].astype(np.float32)
        result = self.session.run(None,{self.input_name: tensor})[0]
        return decode_yolox(result, confidence=threshold, frame_width=width, frame_height=height)


class MotionGate:
    def __init__(self):
        self.reference = None

    def active(self, frame, min_fraction=0.006):
        import cv2
        # 160x90 low-cost gating; skip meaningless differences using blur.
        img = cv2.resize(frame, (160, 90))
        gray = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (7,7), 0)
        if self.reference is None:
            self.reference = gray.astype('float32')
            return True
        ref = cv2.convertScaleAbs(self.reference)
        diff = cv2.absdiff(ref, gray)
        _, changed = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
        ratio = cv2.countNonZero(changed) / changed.size
        cv2.accumulateWeighted(gray, self.reference, 0.12)
        return ratio >= min_fraction


class TrackBuffer:
    """Norfair per-class IDs, with debounce and event cooldown."""
    def __init__(self):
        from norfair import Tracker
        self.trackers = {category: Tracker(distance_function='euclidean', distance_threshold=65,
                                           hit_counter_max=4, initialization_delay=1)
                         for category in CATEGORIES}
        self.last_alert = {}
        self.observations = defaultdict(int)
        self.alerted_ids = set()

    def ready(self, detections, cooldown, *, fast_traffic=False):
        import numpy as np
        from norfair import Detection
        grouped = defaultdict(list)
        for name, score, box in detections:
            grouped[name].append((name,score,box))
        output = []
        now = time.monotonic()
        for category, tracker in self.trackers.items():
            objects = grouped.get(category, [])
            det = [Detection(np.array([[(b[0]+b[2])/2, (b[1]+b[3])/2]],dtype=np.float32),
                             data={'box':b,'score':score})
                   for _,score,b in objects]
            tracks = tracker.update(detections=det)
            # Opt-in road mode: passing vehicles may be visible in a single 1s sample.
            # Require a stronger score and use the same per-class cooldown.
            if (fast_traffic and category in {'car','truck','bus','motorcycle','bicycle'}
                    and now - self.last_alert.get(category,-1e6) >= cooldown):
                candidates = [obj for obj in objects if obj[1] >= 0.72]
                if candidates:
                    chosen = max(candidates, key=lambda obj: obj[1])
                    self.last_alert[category] = now
                    output.append(chosen)
            for track in tracks:
                # Do not treat a stale Norfair track as a fresh model observation.
                if track.last_detection is None or not any(track.last_detection is d for d in det):
                    continue
                key = (category, track.id)
                self.observations[key] += 1
                # At least two model observations and category-wide cooldown.
                if key in self.alerted_ids or self.observations[key] < 2 or now - self.last_alert.get(category, -1e6) < cooldown:
                    continue
                self.last_alert[category] = now
                self.alerted_ids.add(key)
                data = track.last_detection.data
                output.append((category, data['score'], data['box']))
        return output


def annotated_jpeg(frame, detections):
    import cv2
    # Evidence resized to 640px. No facial recognition or biometric identifiers.
    h,w=frame.shape[:2]
    ratio=min(640/w,640/h,1)
    image=cv2.resize(frame,(int(w*ratio),int(h*ratio)))
    for name, score, box in detections:
        x1,y1,x2,y2=[int(a*ratio) for a in box]
        cv2.rectangle(image,(x1,y1),(x2,y2),(0,220,80),2)
        cv2.putText(image,f'{name} {score:.2f}',(x1,max(15,y1-6)),cv2.FONT_HERSHEY_SIMPLEX,0.48,(0,220,80),1)
    ok, result=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,70])
    if not ok: raise RuntimeError('JPEG encoder failed')
    return result.tobytes()


def notify_home_assistant(camera, category, confidence, event_id):
    """Optional local HA event and push. Never send snapshots, passwords or tokens in event data."""
    import json
    base = os.environ.get('AI_HA_URL', '').rstrip('/')
    token = os.environ.get('AI_HA_TOKEN', '')
    if not (base.startswith(('http://', 'https://')) and token):
        return False
    payload = {'event_id': event_id, 'camera': camera, 'category': category,
               'confidence': round(float(confidence), 3)}
    def post(path, data):
        req = request.Request(base + path, data=json.dumps(data).encode(), method='POST',
                              headers={'Authorization': 'Bearer ' + token,
                                       'Content-Type': 'application/json'})
        with request.urlopen(req, timeout=4) as response:
            return 200 <= response.status < 300
    try:
        ok=post('/api/events/alexa_rtsp_ai_detection', payload)
        service=os.environ.get('AI_HA_NOTIFY_SERVICE','')
        if service and service.startswith('mobile_app_') and service.replace('_','').isalnum():
            title=f'Pro Max AI · {camera}'
            text=f'{category} detectado ({confidence:.0%}). Revisa la evidencia y confirma en Pro Max.'
            post('/api/services/notify/'+service,
                 {'title': title, 'message': text,
                  'data': {'tag': 'pro_ai_'+camera+'_'+category}})
        return ok
    except Exception as exc:
        LOG.warning('Home Assistant delivery unavailable: %s',type(exc).__name__)
        return False


class Worker:
    def __init__(self, root):
        self.ai = AIStore(root)
        self.root = Path(root)
        self.detector = None
        self.opened = {}
        self.active_sources = {}
        self.gates = {}
        self.trackers = {}
        self.next_scan = {}
        self.count = 0
        self.sample_counter = {}
        self.last_purge = 0

    def close(self):
        for capture in self.opened.values():
            capture.release()
        self.opened.clear()
        self.active_sources.clear()

    def iteration(self):
        import cv2
        settings=self.ai.config()
        if time.monotonic()-self.last_purge>3600:
            self.ai.purge_old();self.last_purge=time.monotonic()
        if not settings['enabled']:
            self.close()
            self.ai.heartbeat('disabled',model_loaded=self.detector is not None,detections=self.count)
            time.sleep(4)
            return
        enabled={s:v for s,v in settings.get('cameras',{}).items() if v.get('enabled')}
        if not enabled:
            self.ai.heartbeat('waiting_for_camera',model_loaded=self.detector is not None,detections=self.count)
            time.sleep(4)
            return
        if self.detector is None:
            self.detector=YOLOXNano(self.root/'ai/models/yolox_nano.onnx')
        cameras=Store(self.root)
        for slug in list(self.opened):
            if slug not in enabled or slug not in cameras.slugs():
                self.opened.pop(slug).release()
                self.active_sources.pop(slug,None)
                self.gates.pop(slug,None)
                self.trackers.pop(slug,None)
        # CPU-safe beta: maximum 2 cameras, one model instance and sequential inference.
        for slug,conf in list(enabled.items())[:2]:
            cam=cameras.get(slug)
            if cam is None:continue
            url=conf.get('substream') or cam['rtsp_url']
            cap=self.opened.get(slug)
            if cap is not None and self.active_sources.get(slug)!=url:
                cap.release()
                self.opened.pop(slug,None)
                cap=None
            if cap is None or not cap.isOpened():
                cap=cv2.VideoCapture(url,cv2.CAP_FFMPEG,
                                     [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,5000,
                                      cv2.CAP_PROP_READ_TIMEOUT_MSEC,5000])
                if not cap.isOpened():
                    cap.release()
                    self.ai.heartbeat('camera_offline',camera=slug,model_loaded=True,
                                      message='RTSP connection failed',detections=self.count)
                    time.sleep(3)
                    continue
                self.opened[slug]=cap
                self.active_sources[slug]=url
                self.gates[slug]=MotionGate()
                self.trackers[slug]=TrackBuffer()
            ok,frame=cap.read()
            if not ok:
                cap.release();self.opened.pop(slug,None)
                self.active_sources.pop(slug,None)
                self.ai.heartbeat('camera_offline',camera=slug,model_loaded=True,
                                  message='No new frame',detections=self.count)
                continue
            due=self.next_scan.get(slug,0)
            if time.monotonic()<due:continue
            road_mode=bool(conf.get('road_mode',False))
            interval=1 if road_mode else int(settings['interval_seconds'])
            self.next_scan[slug]=time.monotonic()+interval
            self.sample_counter[slug]=self.sample_counter.get(slug,0)+1
            motion=self.gates[slug].active(frame,float(settings['motion_fraction']))
            watched=self.ai.preview_watched(slug)
            # While someone watches diagnostic preview, always run the model.
            # Otherwise retain motion gating and periodic stationary-object scans.
            analyzed=motion or watched or road_mode or self.sample_counter[slug]%4==0
            detections=[]
            elapsed_ms=0.0
            if analyzed:
                tic=time.monotonic()
                detections=self.detector.infer(frame,float(settings['confidence']))
                elapsed_ms=(time.monotonic()-tic)*1000
            if watched:
                try:
                    jpg=annotated_jpeg(frame,detections)
                    self.ai.save_preview(slug,jpg,boxes=detections,
                                         analyzed=analyzed,motion=motion,inference_ms=elapsed_ms)
                except (OSError,ValueError) as exc:
                    LOG.warning('Preview not saved: %s',type(exc).__name__)
            if not analyzed:
                self.ai.heartbeat('running',camera=slug,model_loaded=True,detections=self.count,
                                  message='No motion; skipped this sample')
                continue
            for category,score,box in self.trackers[slug].ready(detections,int(settings['cooldown_seconds']),fast_traffic=road_mode):
                jpg=annotated_jpeg(frame,[(category,score,box)])
                eid=self.ai.add_event(slug,category,score,jpg,box)
                notify_home_assistant(slug,category,score,eid)
                self.count+=1
            self.ai.heartbeat('running',camera=slug,model_loaded=True,detections=self.count)
        time.sleep(0.08)


def serve():
    logging.basicConfig(level=logging.INFO, format='[AI] %(levelname)s %(message)s')
    os.environ.setdefault('OPENCV_FFMPEG_CAPTURE_OPTIONS','rtsp_transport;tcp')
    root=os.environ.get('DATA_DIR','/data')
    worker=Worker(root)
    stop=False
    def halt(_sig,_frame):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,halt)
    signal.signal(signal.SIGINT,halt)
    try:
        while not stop:
            try:
                worker.iteration()
            except (Exception) as exc:
                # Redacted error class only: OpenCV errors can echo RTSP credentials.
                worker.close()
                worker.ai.heartbeat('error',message=type(exc).__name__,
                                    model_loaded=worker.detector is not None,
                                    detections=worker.count)
                LOG.error('AI worker error: %s (details intentionally redacted)',type(exc).__name__)
                time.sleep(5)
    finally:
        worker.close()
        worker.ai.heartbeat('stopped',detections=worker.count)


if __name__=='__main__':
    serve()

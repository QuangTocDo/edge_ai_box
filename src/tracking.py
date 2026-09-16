"""Tracker dung chung: 1x YOLO + OC-SORT, diem moc Bottom-Center."""
from collections import deque
from typing import Any
import numpy as np

from ultralytics import YOLO

from .constants import (TRACK_MAX_AGE_FRAMES, TRACK_PTS_MAXLEN,
                         TRACK_VEL_EMA_ALPHA)
from .geometry import bottom_center


class TrackState:
    """State giu per track_id (rule engine doc, khong phu thuoc tracker ben trong)."""

    def __init__(self, tid, cls, conf, bc):
        self.tid = tid
        self.cls = cls
        self.conf = conf
        self.pts = deque([bc], maxlen=TRACK_PTS_MAXLEN)  # lich su bottom-center
        self.hits = 1
        self.vel = (0.0, 0.0)  # van toc lam muot (px/frame)
        self.bbox = None
        self.last_frame = -1
        # line_id -> (frame_idx, time_s) cat dung chieu
        self.line_flags = {}
        # line_id -> [so frame nguoc lien tuc, quang duong px tich luy]
        self.reverse = {}
        # violation_type -> thoi diem het cooldown (giay)
        self.cooldowns = {}
        # zone_id -> {inside, enter_t, fired} cho no_entry_road
        self.zones = {}
        # scratch rieng cho rule den do / toc do (None = chua khoi tao)
        self.red: dict[str, Any] | None = None
        self.speed: dict[str, Any] | None = None

    def update(self, cls, conf, bc, bbox, frame_idx):
        prev = self.pts[-1]
        dx, dy = bc[0] - prev[0], bc[1] - prev[1]
        a = TRACK_VEL_EMA_ALPHA  # EMA giu cu + moi
        self.vel = (a * self.vel[0] + (1 - a) * dx,
                    a * self.vel[1] + (1 - a) * dy)
        self.pts.append(bc)
        self.cls, self.conf, self.bbox = cls, conf, bbox
        self.hits += 1
        self.last_frame = frame_idx


class Tracker:
    def __init__(self, weights="weights/best.pt", conf=0.4, imgsz=640,
                 classes=None, tracker_cfg="ocsort.yaml", device=None,
                 max_age_frames=TRACK_MAX_AGE_FRAMES):
        self.model = YOLO(weights)
        self.names = self.model.names
        self.conf = conf
        self.imgsz = imgsz
        self.classes = classes
        self.tracker_cfg = tracker_cfg
        self.device = device
        self.max_age = max_age_frames
        self.tracks = {}  # tid -> TrackState

    def warmup(self, imgsz=None):
        """Warm-up model ONNX tren GPU truoc khi xu ly video, tranh freeze 2-3s o frame dau."""
        sz = imgsz or self.imgsz or 640
        dummy = np.zeros((sz, sz, 3), dtype=np.uint8)
        try:
            self.model.predict(dummy, imgsz=sz, device=self.device, verbose=False)
        except Exception:
            pass

    def update(self, frame, frame_idx):
        """Chay track 1 frame, tra ve dict tid -> TrackState dang alive."""
        res = self.model.track(frame, persist=True, tracker=self.tracker_cfg,
                               conf=self.conf, imgsz=self.imgsz,
                               classes=self.classes, device=self.device,
                               verbose=False)[0]
        seen = set()
        if res.boxes is not None and res.boxes.id is not None:
            ids = res.boxes.id.int().tolist()  # pyright: ignore[reportAttributeAccessIssue]
            xyxy = res.boxes.xyxy.tolist()
            clss = res.boxes.cls.int().tolist()  # pyright: ignore[reportAttributeAccessIssue]
            confs = res.boxes.conf.tolist()
            for tid, bb, c, cf in zip(ids, xyxy, clss, confs):
                bc = bottom_center(*bb)
                if tid in self.tracks:
                    self.tracks[tid].update(c, cf, bc, bb, frame_idx)
                else:
                    st = TrackState(tid, c, cf, bc)
                    st.bbox = bb
                    st.last_frame = frame_idx
                    self.tracks[tid] = st
                seen.add(tid)
        # prune track mat dau qua lau (ID-switch/ roi frame)
        dead = [t for t, s in self.tracks.items()
                if frame_idx - s.last_frame > self.max_age]
        for t in dead:
            del self.tracks[t]
        return {t: self.tracks[t] for t in seen}

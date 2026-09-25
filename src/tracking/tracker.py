"""Tracker dung chung: 1x YOLO + OC-SORT, diem moc Bottom-Center."""
import logging
import math
from collections import deque
from typing import Any
import numpy as np

from ultralytics import YOLO

from ..utils.constants import (TRACK_JUMP_MIN_PX, TRACK_JUMP_PX_RATIO,
                                 TRACK_JUMP_STREAK, TRACK_MAX_AGE_FRAMES,
                                 TRACK_PTS_MAXLEN, TRACK_VEL_EMA_ALPHA)
from ..utils.geometry import bottom_center, heading_deg
from ..utils.vehicle import vehicle_name

# Nguong toc do toi thieu (px/frame, theo vel EMA) de cap nhat heading.
# Duoi nguong (dung yen/tre cham) giu heading cu, tranh nhay loan.
HEADING_MIN_SPEED_PX = 1.0


class TrackState:
    """State giu per track_id (rule engine doc, khong phu thuoc tracker ben trong)."""

    def __init__(self, tid, cls, conf, bc):
        self.tid = tid
        self.cls = cls
        self.conf = conf
        self.pts = deque([bc], maxlen=TRACK_PTS_MAXLEN)  # lich su bottom-center
        self.hits = 1
        self.vel = (0.0, 0.0)  # van toc lam muot (px/frame)
        self.heading = None  # goc huong di chuyen (do, quy uoc geometry.heading_deg)
        self.jump_streak = 0  # so frame nhay lien tuc (nghi ID-switch)
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

    def update(self, cls, conf, bc, bbox, frame_idx, jump_px=None):
        """Cap nhat track. Tra ve True neu buoc nay bi loai la nhay ID-switch."""
        prev = self.pts[-1]
        dx, dy = bc[0] - prev[0], bc[1] - prev[1]
        step = math.hypot(dx, dy)
        # Chong ID-switch: buoc nhay bat thuong thi khong tin (khong cap
        # nhat vel/heading), nhung van giu pts/hits de track song tiep.
        # Nhay lien tuc >= STREAK thi chap nhan la chuyen dong that.
        if jump_px is not None and step > jump_px:
            self.jump_streak += 1
            self.pts.append(bc)
            self.cls, self.conf, self.bbox = cls, conf, bbox
            self.hits += 1
            self.last_frame = frame_idx
            if self.jump_streak < TRACK_JUMP_STREAK:
                return True
        self.jump_streak = 0
        a = TRACK_VEL_EMA_ALPHA  # EMA giu cu + moi
        self.vel = (a * self.vel[0] + (1 - a) * dx,
                    a * self.vel[1] + (1 - a) * dy)
        hd = heading_deg(*self.vel)
        if hd is not None and math.hypot(*self.vel) >= HEADING_MIN_SPEED_PX:
            self.heading = hd
        self.pts.append(bc)
        self.cls, self.conf, self.bbox = cls, conf, bbox
        self.hits += 1
        self.last_frame = frame_idx
        return False


class Tracker:
    def __init__(self, weights="weights/best.pt", conf=0.4, imgsz=640,
                 classes=None, tracker_cfg="ocsort.yaml", device=None,
                 max_age_frames=TRACK_MAX_AGE_FRAMES, names=None):
        self.model = YOLO(weights)
        if names:
            self.names = {int(k): str(v) for k, v in names.items()} if isinstance(names, dict) else names
        else:
            raw_names = getattr(self.model, "names", {})
            if isinstance(raw_names, dict):
                self.names = {cid: vehicle_name(cid, raw_names) for cid in raw_names}
            elif isinstance(raw_names, (list, tuple)):
                self.names = [vehicle_name(i, raw_names) for i in range(len(raw_names))]
            else:
                self.names = raw_names
        self.conf = conf
        self.imgsz = imgsz
        self.classes = classes
        self.tracker_cfg = tracker_cfg
        self.device = device
        self.max_age = max_age_frames
        self.tracks = {}  # tid -> TrackState
        self.jump_px = max(TRACK_JUMP_MIN_PX,
                           TRACK_JUMP_PX_RATIO * float(imgsz or 640))
        self.n_jump_reject = 0  # dem buoc nhay bi loai (xem bang --debug-rules)

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
                    if self.tracks[tid].update(c, cf, bc, bb, frame_idx,
                                               jump_px=self.jump_px):
                        self.n_jump_reject += 1
                        logging.debug("jump reject tid=%s frame=%d (tong %d)",
                                      tid, frame_idx, self.n_jump_reject)
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

"""Tracker dung chung: 1x YOLO + OC-SORT, diem moc Bottom-Center."""
from collections import deque

from ultralytics import YOLO

from .geometry import bottom_center


class TrackState:
    """State giu per track_id (rule engine doc, khong phu thuoc tracker ben trong)."""

    def __init__(self, tid, cls, conf, bc):
        self.tid = tid
        self.cls = cls
        self.conf = conf
        self.pts = deque([bc], maxlen=30)  # lich su bottom-center
        self.hits = 1
        self.vel = (0.0, 0.0)  # van toc lam muot (px/frame)
        self.bbox = None
        self.last_frame = -1
        # line_id -> (frame_idx, time_s, v_entry)
        self.line_flags = {}
        # line_id -> thoi diem cat medial/divider gan nhat (giay)
        self.medial_cross_t = None
        # line_id -> [so frame nguoc lien tuc, quang duong px tich luy]
        self.reverse = {}
        # violation_type -> thoi diem het cooldown (giay)
        self.cooldowns = {}

    def update(self, cls, conf, bc, bbox, frame_idx):
        prev = self.pts[-1]
        dx, dy = bc[0] - prev[0], bc[1] - prev[1]
        a = 0.6  # EMA giu 60% cu + 40% moi
        self.vel = (a * self.vel[0] + (1 - a) * dx,
                    a * self.vel[1] + (1 - a) * dy)
        self.pts.append(bc)
        self.cls, self.conf, self.bbox = cls, conf, bbox
        self.hits += 1
        self.last_frame = frame_idx


class Tracker:
    def __init__(self, weights="weights/yolo26n.pt", conf=0.4, imgsz=640,
                 classes=None, tracker_cfg="ocsort.yaml", device=None,
                 max_age_frames=30):
        self.model = YOLO(weights)
        self.names = self.model.names
        self.conf = conf
        self.imgsz = imgsz
        self.classes = classes
        self.tracker_cfg = tracker_cfg
        self.device = device
        self.max_age = max_age_frames
        self.tracks = {}  # tid -> TrackState

    def update(self, frame, frame_idx):
        """Chay track 1 frame, tra ve dict tid -> TrackState dang alive."""
        res = self.model.track(frame, persist=True, tracker=self.tracker_cfg,
                               conf=self.conf, imgsz=self.imgsz,
                               classes=self.classes, device=self.device,
                               verbose=False)[0]
        seen = set()
        if res.boxes is not None and res.boxes.id is not None:
            ids = res.boxes.id.int().tolist()
            xyxy = res.boxes.xyxy.tolist()
            clss = res.boxes.cls.int().tolist()
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

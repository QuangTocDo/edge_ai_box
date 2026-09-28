from typing import Any, Dict, List, Optional, Tuple
"""Dung Tracker va Secondary Detectors tu model config (seam de test/mock, tranh khoi tao cung trong main)."""
import logging
from pathlib import Path
from ultralytics import YOLO
from ..tracking.tracker import Tracker
from ..utils.geometry import point_in_polygon


def _iou(bb1, bb2):
    """Tinh Intersection-over-Union giua 2 bounding boxes."""
    ix1 = max(bb1[0], bb2[0])
    iy1 = max(bb1[1], bb2[1])
    ix2 = min(bb1[2], bb2[2])
    iy2 = min(bb1[3], bb2[3])
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area1 = (bb1[2] - bb1[0]) * (bb1[3] - bb1[1])
    area2 = (bb2[2] - bb2[0]) * (bb2[3] - bb2[1])
    return inter / float(area1 + area2 - inter + 1e-6)


class SimplePedTracker:
    """Tracker IoU nhe de dinh danh ID on dinh cho tung nguoi di bo trong vung."""

    def __init__(self, max_lost=15, iou_thresh=0.2):
        self.next_id = 1
        self.tracks = {}  # {id: {"bbox": ..., "bc": ..., "lost": 0, "conf": ...}}
        self.max_lost = max_lost
        self.iou_thresh = iou_thresh

    def update(self, detections):
        """detections: list [{'bbox': [x1, y1, x2, y2], 'conf': ..., 'bc': ..., 'cls': ...}]
        Tra ve list copy voi truong 'id': int on dinh.
        """
        if not detections:
            for tid in list(self.tracks.keys()):
                self.tracks[tid]["lost"] += 1
                if self.tracks[tid]["lost"] > self.max_lost:
                    del self.tracks[tid]
            return []

        track_ids = list(self.tracks.keys())
        matched_tracks = set()
        matched_dets = set()
        assigned = {}

        if track_ids:
            ious = []
            for d_idx, d in enumerate(detections):
                for tid in track_ids:
                    iou_val = _iou(d["bbox"], self.tracks[tid]["bbox"])
                    # Neu nguoi di cham / dung yen, tinh them khoang cach tam chan (bc)
                    bc_d = d["bc"]
                    bc_t = self.tracks[tid]["bc"]
                    dist = ((bc_d[0] - bc_t[0]) ** 2 + (bc_d[1] - bc_t[1]) ** 2) ** 0.5
                    if dist < 45:
                        iou_val = max(iou_val, 0.4)
                    if iou_val >= self.iou_thresh:
                        ious.append((iou_val, d_idx, tid))

            ious.sort(key=lambda x: x[0], reverse=True)
            for iou_val, d_idx, tid in ious:
                if d_idx not in matched_dets and tid not in matched_tracks:
                    matched_dets.add(d_idx)
                    matched_tracks.add(tid)
                    assigned[d_idx] = tid

        result = []
        for d_idx, d in enumerate(detections):
            d_copy = dict(d)
            if d_idx in assigned:
                tid = assigned[d_idx]
            else:
                tid = self.next_id
                self.next_id += 1
            d_copy["id"] = tid
            self.tracks[tid] = {
                "bbox": d["bbox"],
                "bc": d["bc"],
                "lost": 0,
                "conf": d.get("conf", 0.0)
            }
            result.append(d_copy)

        for tid in track_ids:
            if tid not in matched_tracks:
                self.tracks[tid]["lost"] += 1
                if self.tracks[tid]["lost"] > self.max_lost:
                    del self.tracks[tid]

        return result


def create_tracker(mc, imgsz_override=0):
    """mc: dict model trong camera config. imgsz_override>0 thi thang CLI."""
    return Tracker(weights=mc["weights"], conf=mc.get("conf", 0.4),
                   imgsz=imgsz_override or mc.get("imgsz", 640),
                   classes=mc.get("classes"),
                   tracker_cfg=mc.get("tracker", "ocsort.yaml"),
                   device=mc.get("device"),
                   names=mc.get("names"),
                   vote_interval=int(mc.get("window_size") or mc.get("vote_interval") or 10))


class PedestrianDetector:
    """Secondary detector chuyen biet cho nguoi di bo / tu tap dong nguoi su dung file ONNX rieng."""

    def __init__(self, weights, conf=0.35, imgsz=640, device=None, classes=None):
        self.weights = str(weights)
        self.model = YOLO(self.weights, task="detect")
        self.conf = float(conf)
        self.imgsz = int(imgsz)
        self.device = device
        self.names = getattr(self.model, "names", {0: "pedestrian"})
        self.tracker = SimplePedTracker()

        # Xac dinh target class IDs: uu tien config classes, neu khong thi tu dong tim person/pedestrian
        if classes is not None:
            self.target_classes = set(int(c) for c in classes)
        else:
            matched = set()
            for cid, cname in self.names.items():
                cn = str(cname).lower()
                if "person" in cn or "pedestrian" in cn or "nguoi" in cn:
                    matched.add(int(cid))
            if matched:
                self.target_classes = matched
            elif len(self.names) == 1:
                self.target_classes = {0}
            else:
                self.target_classes = {0}
        logging.info("PedestrianDetector target classes: %s (%s)",
                     self.target_classes,
                     {c: self.names.get(c) for c in self.target_classes})

    def detect(self, img):
        """Nhan dien nguoi di bo tren anh (full frame hoac crop ROI).
        Tra ve list dict: [{'bbox': [x1, y1, x2, y2], 'conf': float, 'bc': (x, y), 'cls': int}]
        """
        if img is None or img.size == 0 or img.shape[0] < 10 or img.shape[1] < 10:
            return []
        res = self.model.predict(img, conf=self.conf, imgsz=self.imgsz,
                                 device=self.device, verbose=False)[0]
        dets = []
        if res.boxes is not None and len(res.boxes) > 0:
            xyxy = res.boxes.xyxy.tolist()
            confs = res.boxes.conf.tolist()
            cls_ids = res.boxes.cls.tolist() if res.boxes.cls is not None else [0] * len(xyxy)
            for bb, cf, cl in zip(xyxy, confs, cls_ids):
                cid = int(cl)
                if cid in self.target_classes:
                    bc = ((bb[0] + bb[2]) / 2.0, bb[3])
                    dets.append({"bbox": [int(v) for v in bb], "conf": float(cf), "bc": bc, "cls": cid})
        return dets

    def detect_in_polygon(self, frame, polygon_pts, pad=20):
        """Chi nhan dien nguoi ben trong vung polygon (crop ROI) thay vi ca frame.
        - Crop vung bounding box cua polygon kem padding de bao quat ca dau/chan nguoi.
        - Chay model predict tren crop ROI.
        - Anh xa nguoc lai toa do frame goc.
        - Loc bo bat ky ai co diem tiep dat (bottom-center) nam ngoai polygon.
        - Dinh danh track ID on dinh cho tung nguoi bang SimplePedTracker.
        """
        if not polygon_pts or len(polygon_pts) < 3 or frame is None:
            return []

        xs = [pt[0] for pt in polygon_pts]
        ys = [pt[1] for pt in polygon_pts]
        h, w = frame.shape[:2]

        x1 = max(0, int(min(xs)) - pad)
        y1 = max(0, int(min(ys)) - pad)
        x2 = min(w, int(max(xs)) + pad)
        y2 = min(h, int(max(ys)) + pad)

        if x2 - x1 < 10 or y2 - y1 < 10:
            return []

        crop = frame[y1:y2, x1:x2]
        crop_dets = self.detect(crop)

        in_poly_dets = []
        for d in crop_dets:
            bx1, by1, bx2, by2 = d["bbox"]
            real_bbox = [bx1 + x1, by1 + y1, bx2 + x1, by2 + y1]
            real_bc = ((real_bbox[0] + real_bbox[2]) / 2.0, float(real_bbox[3]))
            if point_in_polygon(real_bc, polygon_pts):
                in_poly_dets.append({
                    "bbox": real_bbox,
                    "conf": d["conf"],
                    "bc": real_bc,
                    "cls": d["cls"],
                    "in_zone": True,
                })

        # Cap nhat dinh danh ID on dinh cho nguoi di bo
        tracked_dets = self.tracker.update(in_poly_dets)
        return tracked_dets


def create_pedestrian_detector(cfg, async_mode: bool = True):
    """cfg: dict model config cho no_gathering (hoac secondary_models.pedestrian).
    async_mode: Neu True, boc boi AsyncPedestrianDetector de chay worker thread rieng tranh drop FPS.
    """
    if not cfg:
        return None
    m = cfg.get("model", cfg)
    if not m or not m.get("weights"):
        return None
    # Neu co flag enable ro rang va enable la False thi bo qua
    if m.get("enable") is False or cfg.get("enable") is False:
        return None
    wpath = Path(m["weights"])
    if not wpath.is_file():
        logging.warning("File model ONNX cho pedestrian khong ton tai: %s (bo qua khoi tao)", wpath)
        return None
    try:
        base_det = PedestrianDetector(
            weights=m["weights"],
            conf=m.get("conf", 0.35),
            imgsz=m.get("imgsz", 640),
            device=m.get("device"),
            classes=m.get("classes")
        )
        return AsyncPedestrianDetector(base_det) if async_mode else base_det
    except Exception as ex:
        logging.exception("Khong the khoi tao PedestrianDetector: %s", ex)
        return None


import queue
import threading


class AsyncPedestrianDetector:
    """Async worker wrapper cho PedestrianDetector su dung worker thread rieng.

    Triet tieu hoan toan hien tuong spike/drop FPS tren main thread khi goi model phu (ONNX)
    dinh ky de phat hien tu tap dong nguoi.
    """

    def __init__(self, detector: PedestrianDetector):
        self.detector = detector
        self._task_queue: queue.Queue = queue.Queue(maxsize=1)
        self._lock = threading.Lock()
        self._latest_result: Optional[Dict[str, Any]] = None
        self._stopped = False
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True, name="AsyncPedDetectorWorker"
        )
        self._worker_thread.start()

    def _worker_loop(self):
        while not self._stopped:
            try:
                task = self._task_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if task is None or self._stopped:
                break

            frame_idx, t, wall_min, frame, gathering_entries = task
            try:
                poly_results = []
                all_peds = []
                for ge in gathering_entries:
                    poly_obj = ge.get("polygon") or {}
                    pts = poly_obj.get("polygon") or []
                    if not pts:
                        continue
                    peds_in_poly = self.detector.detect_in_polygon(frame, pts)
                    all_peds.extend(peds_in_poly)
                    poly_results.append({
                        "ge": ge,
                        "poly_obj": poly_obj,
                        "peds": peds_in_poly,
                    })

                with self._lock:
                    self._latest_result = {
                        "frame_idx": frame_idx,
                        "t": t,
                        "wall_min": wall_min,
                        "frame": frame,
                        "all_peds": all_peds,
                        "poly_results": poly_results,
                    }
            except Exception:
                logging.exception("AsyncPedestrianDetector worker error frame %d", frame_idx)
            finally:
                self._task_queue.task_done()

    def submit(self, frame, gathering_entries, frame_idx: int, t: float, wall_min: Optional[int] = None) -> bool:
        """Submit frame cho worker phan tich khong chan (non-blocking).
        Neu worker dang ban xu ly frame truoc thi bo qua (drop) de khong tich luy tre.
        Tra ve True neu submit thanh cong, False neu bi drop.
        """
        if self._stopped or not gathering_entries:
            return False
        try:
            frame_copy = frame.copy()
            self._task_queue.put_nowait((frame_idx, t, wall_min, frame_copy, gathering_entries))
            return True
        except queue.Full:
            return False

    def poll_result(self) -> Optional[Dict[str, Any]]:
        """Lay ket qua moi nhat tu worker (non-blocking). Tra ve None neu chua co ket qua moi."""
        with self._lock:
            res = self._latest_result
            self._latest_result = None
            return res

    def stop(self):
        self._stopped = True
        try:
            self._task_queue.put_nowait(None)
        except Exception:
            pass
        if self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)

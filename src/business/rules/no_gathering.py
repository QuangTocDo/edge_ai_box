"""Loi cam tu tap dong nguoi (no_gathering).

- Ap dung tren Polygon cam tu tap (khu vuc quan trong, quang truong, cong co quan...).
- Su dung model phu (hoac detector chung) de dem so nguoi dong thoi (Concurrent Count)
  co mat trong polygon tai tung thoi diem.
- Neu so nguoi dong thoi >= min_persons: bat dau tich luy dwell_s va quay video clip.
- Khi du dwell_s: ghi nhan vi pham, tiep tuc quay video trong post_dwell_s de bat tron
  nhung nguoi vao sau / thoi diem dam dong dong nhat (Peak).
- Crop bboxes cua tung nguoi (pedestrian crop avatars) khi vung dat nguong vi pham.
  Nguoi da crop thi khong crop lai, chi crop cho nhung ID moi buoc vao.
- Xuat bo bang chung toan dien:
  + Video Clip (.mp4): Toan bo qua trinh tu luc bat dau tu tap -> them nguoi vao sau -> thoi diem dong nhat (chi hien thi polygon cam, khong hien thi bboxes nguoi).
  + Individual Crops (.jpg): Cac file crop bboxes rieng le cua tung nguoi tham gia {stem}_ped_{id}.jpg.
  + Diptych Photo (.jpg): 2 anh (Anh 1 luc bat dau, Anh 2 luc dong nhat - Peak).
  + Metadata (.json): Thong tin chi tiet, duong dan video_path, danh sach pedestrian_crops, so nguoi, thoi gian.
- Cooldown: Tranh bao spam lien tuc tren cung mot dam dong.
"""
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np

from ...utils.geometry import in_active_hours, parse_window, point_in_polygon
from .base import BaseRule, cooldown_ok


def _make_annotated_frame(frame, polygon_pts, persons_in_zone, pid, count, min_p, dwell_s, target_dwell, is_violated):
    """Ve overlay tren frame de ghi vao video clip evidence: chi ve polygon cam, KHONG ve bboxes nguoi."""
    if frame is None:
        return None
    annotated = frame.copy()

    # 1. Ve polygon cam (vang cam khi dang dem, do khi da vi pham)
    if polygon_pts and len(polygon_pts) >= 3:
        pts = np.array(polygon_pts, dtype=np.int32).reshape((-1, 1, 2))
        color = (0, 0, 255) if is_violated else (0, 215, 255)
        cv2.polylines(annotated, [pts], True, color, 3)
        # Nhan ten polygon o goc da giac
        first_pt = tuple(int(v) for v in polygon_pts[0])
        cv2.putText(annotated, pid, (first_pt[0], max(20, first_pt[1] - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    # 2. KHONG ve bboxes nguoi trong video clip theo yeu cau

    # 3. Top banner thong tin
    h, w = annotated.shape[:2]
    cv2.rectangle(annotated, (0, 0), (w, 40), (20, 20, 20), -1)
    status_str = "VIOLATION: NO GATHERING" if is_violated else "MONITORING GATHERING"
    status_col = (0, 0, 255) if is_violated else (0, 255, 255)
    text1 = f"[{status_str}] Zone: {pid} | Count: {count}/{min_p} | Dwell: {dwell_s:.1f}s / {target_dwell:.1f}s"
    cv2.putText(annotated, text1, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.65, status_col, 2)
    return annotated


class NoGatheringRule(BaseRule):
    """Loi cam tu tap dong nguoi qua Concurrent Count trong polygon."""

    TYPE = "no_gathering"
    PARAMS = {
        "min_persons": 5,
        "dwell_s": 60.0,
        "cooldown_s": 300.0,
        "min_hits": 1,
        "model": None,
        "post_dwell_s": 0.0,
        "max_clip_s": 30.0,
        "save_video": True,
        "video_fps": 6.0,
    }

    def __init__(
        self,
        min_persons: int = 5,
        dwell_s: float = 60.0,
        cooldown_s: float = 300.0,
        min_hits: int = 1,
        model: Optional[Dict[str, Any]] = None,
        post_dwell_s: float = 0.0,
        max_clip_s: float = 30.0,
        save_video: bool = True,
        video_fps: float = 6.0,
    ):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)
        self.min_persons = int(min_persons)
        self.dwell_s = float(dwell_s)
        self.cooldown_s = float(cooldown_s)
        self.model_cfg = model or {}
        self.post_dwell_s = float(post_dwell_s)
        self.max_clip_s = float(max_clip_s)
        self.save_video = bool(save_video)
        self.video_fps = float(video_fps)

        # Trang thai theo tung polygon: {pid: {...}}
        self.zone_states: Dict[str, Dict[str, Any]] = {}
        # Cooldown theo tung zone de khong spam
        self.zone_cooldowns: Dict[str, float] = {}

    @staticmethod
    def _windows(polygon: Dict[str, Any]) -> List[Tuple[int, int]]:
        if polygon.get("_windows") is not None:
            return polygon["_windows"]
        return [parse_window(w) for w in polygon.get("active_hours", [])]

    def get_zone_status(self, pid: str, t: float = 0.0) -> Dict[str, Any]:
        """Tra ve trang thai hien tai cua vung de hien thi visualizer overlay."""
        st = self.zone_states.get(pid, {})
        curr = st.get("current_count", 0)
        min_p = st.get("min_p", self.min_persons)
        target_dwell = st.get("target_dwell", self.dwell_s)
        start_t = st.get("start_t")
        elapsed = max(0.0, t - start_t) if start_t is not None else 0.0
        violated = st.get("violated_t") is not None
        return {
            "count": curr,
            "min_persons": min_p,
            "dwell_s": round(elapsed, 1),
            "target_dwell_s": target_dwell,
            "gathering": curr >= min_p,
            "violated": violated,
            "fired": bool(st.get("fired", False)),
            "peak_count": st.get("peak_count", curr),
            "persons_in_zone": st.get("persons_in_zone", []),
            "cropped_count": len(st.get("cropped_peds", {})),
        }

    def _finalize_gathering_event(
        self,
        pid: str,
        st: Dict[str, Any],
        frame_idx: int,
        t: float,
    ) -> Dict[str, Any]:
        """Dong goi event no_gathering kem bo anh Diptych, Video clip va cac crop bboxes ca nhan."""
        shot1 = st.get("start_frame")
        shot1_t = st.get("start_t", t)
        shot1_boxes = st.get("start_bboxes") or []
        start_count = st.get("start_count", 0)

        # Shot 2 dung thoi diem dong nhat (Peak) de khong bo sot nhung nguoi vao sau
        shot2 = st.get("peak_frame")
        shot2_t = st.get("peak_t", t)
        shot2_boxes = st.get("peak_bboxes") or []
        peak_count = st.get("peak_count", start_count)

        all_boxes = shot2_boxes or shot1_boxes
        if all_boxes:
            min_x = min(b[0] for b in all_boxes)
            min_y = min(b[1] for b in all_boxes)
            max_x = max(b[2] for b in all_boxes)
            max_y = max(b[3] for b in all_boxes)
            group_bbox = [int(min_x), int(min_y), int(max_x), int(max_y)]
            center_bc = ((min_x + max_x) / 2.0, float(max_y))
        else:
            group_bbox = [0, 0, 100, 100]
            center_bc = (50.0, 100.0)

        total_dwell = round(t - shot1_t, 1)
        ev = {
            "type": self.TYPE,
            "track_id": f"crowd_{pid}_{frame_idx}",
            "cls": "gathering",
            "conf": 1.0,
            "bbox": group_bbox,
            "bc": center_bc,
            "line_id": pid,
            "frame_idx": frame_idx,
            "t": t,
            "extra": {
                "zone_id": pid,
                "concurrent_count": peak_count,
                "start_count": start_count,
                "peak_count": peak_count,
                "min_persons_threshold": st.get("min_p", self.min_persons),
                "dwell_s": total_dwell,
                "target_dwell_s": st.get("target_dwell", self.dwell_s),
                "person_bboxes": shot2_boxes,
            },
        }

        # Crop bboxes cua tung nguoi vao vung trong suot dot vi pham
        ped_crops_list = list(st.get("cropped_peds", {}).values())
        if ped_crops_list:
            ev["extra"]["pedestrian_crops"] = ped_crops_list

        # Video clip frames (chi chua polygon cam, khong chua bboxes)
        if self.save_video and st.get("clip_frames"):
            ev["extra"]["video_frames"] = list(st["clip_frames"])
            ev["extra"]["video_fps"] = self.video_fps

        if shot1 is not None and shot2 is not None:
            ev["extra"]["triptych"] = [shot1, shot2]
            ev["extra"]["triptych_timestamps"] = [round(shot1_t, 3), round(shot2_t, 3)]
            ev["extra"]["triptych_bboxes"] = [group_bbox, group_bbox]
            ev["extra"]["triptych_bcs"] = [center_bc, center_bc]
            ev["extra"]["triptych_captions"] = [
                f"1 BAT DAU ({start_count} NGUOI)",
                f"2 DINH DIEM ({peak_count} NGUOI, TU TAP {int(total_dwell)}S)",
            ]
        elif shot2 is not None:
            ev["extra"]["evidence_frame"] = shot2

        # Set cooldown va reset state
        self.zone_cooldowns[pid] = t + self.cooldown_s
        self.zone_states.pop(pid, None)
        return ev

    def update_zone(
        self,
        polygon: Optional[Dict[str, Any]] = None,
        persons: Optional[List[Dict[str, Any]]] = None,
        wall_min: Optional[int] = None,
        frame_idx: int = 0,
        t: float = 0.0,
        frame: Optional[Any] = None,
        **kwargs: Any,
    ) -> Optional[Dict[str, Any]]:
        """Cap nhat trang thai tu tap theo polygon va danh sach nguoi duoc detect."""
        poly_obj = polygon if polygon is not None else kwargs.get("poly", {})
        raw_persons = persons if persons is not None else kwargs.get("persons_in_zone", [])
        pid = poly_obj.get("id", "POLY_GATHERING")

        # 1. Kiem tra khung gio hoat dong (neu co cau hinh active_hours)
        windows = self._windows(poly_obj)
        if windows and wall_min is not None and not in_active_hours(wall_min, windows):
            self.zone_states.pop(pid, None)
            return None

        # 2. Neu dang trong thoi gian cooldown sau khi vua bao vi pham -> bo qua
        if t < self.zone_cooldowns.get(pid, 0.0):
            self.zone_states.pop(pid, None)
            return None

        # 3. Loc nguoi nam ben trong polygon (dua vao bottom-center bc)
        poly_pts = poly_obj.get("polygon") or []
        if poly_pts:
            persons_in_zone = [
                p for p in raw_persons
                if point_in_polygon(p.get("bc", (0, 0)), poly_pts)
            ]
        else:
            persons_in_zone = list(raw_persons)

        # 4. Lay nguong min_persons, dwell_s, post_dwell_s, max_clip_s tu config
        rule_cfg = (poly_obj.get("rules") or {}).get(self.TYPE) or {}
        min_p = int(poly_obj.get("min_persons") or rule_cfg.get("min_persons") or self.min_persons)
        target_dwell = float(poly_obj.get("dwell_s") or rule_cfg.get("dwell_s") or self.dwell_s)
        post_dwell = float(poly_obj.get("post_dwell_s") if poly_obj.get("post_dwell_s") is not None
                           else (rule_cfg.get("post_dwell_s") if rule_cfg.get("post_dwell_s") is not None
                                 else self.post_dwell_s))
        max_clip = float(poly_obj.get("max_clip_s") or rule_cfg.get("max_clip_s") or self.max_clip_s)

        current_count = len(persons_in_zone)
        st = self.zone_states.setdefault(pid, {
            "start_t": None,
            "start_frame_idx": None,
            "start_frame": None,
            "start_count": 0,
            "start_bboxes": [],
            "peak_count": 0,
            "peak_frame": None,
            "peak_bboxes": [],
            "peak_t": 0.0,
            "violated_t": None,
            "clip_frames": [],
            "cropped_peds": {},
            "fired": False,
            "current_count": 0,
            "target_dwell": target_dwell,
            "min_p": min_p,
            "persons_in_zone": [],
        })
        st["current_count"] = current_count
        st["target_dwell"] = target_dwell
        st["min_p"] = min_p
        st["persons_in_zone"] = persons_in_zone

        # Neu so nguoi khong du nguong dam dong (< min_p)
        if current_count < min_p:
            if st.get("violated_t") is not None:
                # Da tung dat nguong vi pham, nay bat dau tan ra -> chot clip ngay de khong bo sot!
                return self._finalize_gathering_event(pid, st, frame_idx, t)
            # Reset bo dem khi nguoi < min_p
            st["start_t"] = None
            st["start_frame"] = None
            st["start_count"] = 0
            st["start_bboxes"] = []
            st["peak_count"] = 0
            st["peak_frame"] = None
            st["peak_bboxes"] = []
            st["clip_frames"] = []
            st["cropped_peds"] = {}
            st["violated_t"] = None
            return None

        # Du nguong >= min_persons:
        # Neu chua bat dau theo doi dam dong -> khoi tao
        if st["start_t"] is None:
            st["start_t"] = t
            st["start_frame_idx"] = frame_idx
            st["start_frame"] = frame.copy() if frame is not None else None
            st["start_count"] = current_count
            st["start_bboxes"] = [p.get("bbox") for p in persons_in_zone if p.get("bbox")]
            st["peak_count"] = current_count
            st["peak_frame"] = frame.copy() if frame is not None else None
            st["peak_bboxes"] = list(st["start_bboxes"])
            st["peak_t"] = t
            st["violated_t"] = None
            st["clip_frames"] = []
            st["cropped_peds"] = {}
            st["fired"] = False

        # Cap nhat thoi diem dong nhat (Peak) de bat tron nhung nguoi vao sau
        if current_count >= st.get("peak_count", 0):
            st["peak_count"] = current_count
            st["peak_frame"] = frame.copy() if frame is not None else None
            st["peak_bboxes"] = [p.get("bbox") for p in persons_in_zone if p.get("bbox")]
            st["peak_t"] = t

        elapsed = t - st["start_t"]
        is_violated = (st.get("violated_t") is not None) or (elapsed >= target_dwell)
        if elapsed >= target_dwell and st.get("violated_t") is None:
            st["violated_t"] = t

        # KHI VUNG DANG CO LOI (is_violated = True):
        # Crop bboxes cua tat ca cac ped trong vung.
        # Luu y: bboxes da cat roi thi khong cat lai, chi cat cho nhung ID moi buoc vao!
        if is_violated and frame is not None and getattr(frame, "size", 0) > 0:
            h_fr, w_fr = frame.shape[:2]
            for p in persons_in_zone:
                p_id = p.get("id")
                if p_id is None:
                    bb = p.get("bbox", [])
                    p_id = f"pos_{int(bb[0])}_{int(bb[1])}" if bb else "unknown"

                if p_id not in st["cropped_peds"]:
                    bb = p.get("bbox")
                    if bb:
                        bx1, by1, bx2, by2 = [int(v) for v in bb]
                        pad_x = max(5, int((bx2 - bx1) * 0.08))
                        pad_y = max(5, int((by2 - by1) * 0.08))
                        cx1 = max(0, bx1 - pad_x)
                        cy1 = max(0, by1 - pad_y)
                        cx2 = min(w_fr, bx2 + pad_x)
                        cy2 = min(h_fr, by2 + pad_y)
                        if cx2 > cx1 and cy2 > cy1:
                            crop_img = frame[cy1:cy2, cx1:cx2].copy()
                            st["cropped_peds"][p_id] = {
                                "id": p_id,
                                "crop": crop_img,
                                "bbox": [bx1, by1, bx2, by2],
                                "conf": float(p.get("conf", 0.0)),
                                "t": round(t, 2),
                                "frame_idx": frame_idx,
                            }

        # Thu thap frame cho video clip (chi ve polygon cam va banner, khong ve bboxes)
        if self.save_video and frame is not None:
            ann_fr = _make_annotated_frame(
                frame, poly_pts, persons_in_zone, pid, current_count,
                min_p, elapsed, target_dwell, is_violated
            )
            st["clip_frames"].append(ann_fr)

        # Kiem tra dieu kien chot video clip va xuat event:
        # Da vuot qua dwell_s va da quay them du post_dwell_s (de ghi nhan nguoi vao sau)
        # hoac tong thoi luong clip cham nguong max_clip_s
        if st.get("violated_t") is not None:
            time_since_violated = t - st["violated_t"]
            total_duration = t - st["start_t"]
            if time_since_violated >= post_dwell or total_duration >= max_clip:
                return self._finalize_gathering_event(pid, st, frame_idx, t)

        return None

    def update(self, track: Any, *args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Loi no_gathering hoat dong theo zone, khong theo single track ca nhan."""
        return None

    def run(self, entry: Dict[str, Any], track: Any, frame_idx: int, t: float,
            wall_min: Optional[int] = None, frame: Optional[Any] = None,
            signals: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Phuong thuc run chuan theo BaseRule (duoc pipeline goi)."""
        return None

    def explain(self, pid: str, t: Optional[float] = None) -> str:
        """Giai thich trang thai hien tai cua khu vuc cam tu tap."""
        st = self.zone_states.get(pid)
        if not st or st.get("start_t") is None:
            return f"no_gathering zone={pid}: chua co dam dong dat nguong"
        el = round(t - st["start_t"], 1) if t is not None else 0.0
        if st.get("violated_t") is not None:
            crop_cnt = len(st.get("cropped_peds", {}))
            return f"no_gathering zone={pid}: da vi pham ({st.get('peak_count')} nguoi, {crop_cnt} crops), dang quay clip evidence"
        return f"no_gathering zone={pid}: dang theo doi {el}/{self.dwell_s:.0f}s"

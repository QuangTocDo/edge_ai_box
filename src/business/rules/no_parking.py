"""Loi dung / do xe trai phep (no_parking).

- Ap dung tren Polygon cam dung do.
- Kiem tra xe dung yen / di chuyen cuc cham (van toc < max_speed_px) trong zone.
- Neu duy tri dung yen >= dwell_s -> bao vi pham NO_PARKING 1 lan duy nhat.
- Spatial deduplication: Ghi nho vi tri da phat (fined_spots). Trong suot thoi
  gian xe van tiep tuc dau tai vi tri do (ke ca khi tracker bi nhay ID-switch),
  he thong khong bao loi lai va khong chup anh trung lap.
- Khi xe roi di va cho do trong xe qua spot_clear_s -> giai phong vi tri de
  theo doi xe khac neu den do sau do.
- Xuat bo 2 anh Diptych (1 luc bat dau dung, 2 luc dung qua han).
"""
from ...utils.geometry import in_active_hours, parse_window, point_in_polygon
from .base import BaseRule, cooldown_ok


class NoParkingRule(BaseRule):
    """Loi dung / do xe trai phep trong polygon."""

    TYPE = "no_parking"
    PARAMS = {
        "dwell_s": 3.0,
        "max_speed_px": 5.0,
        "min_hits": 3,
        "cooldown_s": 15.0,
        "spot_clear_s": 10.0,
        "spot_dist_px": 50.0,
    }

    def __init__(
        self,
        dwell_s=3.0,
        max_speed_px=5.0,
        min_hits=3,
        cooldown_s=15.0,
        spot_clear_s=10.0,
        spot_dist_px=50.0,
    ):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)
        self.dwell_s = float(dwell_s)
        self.max_speed_px = float(max_speed_px)
        self.spot_clear_s = float(spot_clear_s)
        self.spot_dist_px = float(spot_dist_px)
        # {pid: [{"center": (x, y), "bbox": bbox, "last_seen_t": t, "fired_t": t, "tid": tid}]}
        self.fined_spots = {}

    @staticmethod
    def _windows(polygon):
        if polygon.get("_windows") is not None:
            return polygon["_windows"]
        return [parse_window(w) for w in polygon.get("active_hours", [])]

    @staticmethod
    def _st(track):
        st = getattr(track, "parking", None)
        if st is None:
            st = track.parking = {}
        return st

    @staticmethod
    def _is_inside_poly(track, polygon_pts):
        """Kiem tra mui/tam day (bottom-center) hoac tam bounding box co trong polygon khong."""
        if not polygon_pts:
            return False
        curr = track.pts[-1]
        if point_in_polygon(curr, polygon_pts):
            return True
        if getattr(track, "bbox", None) is not None:
            bb = track.bbox
            center = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
            if point_in_polygon(center, polygon_pts):
                return True
        return False

    def _find_matching_fined_spot(self, pid, center, bbox, t):
        """Kiem tra vi tri hien tai co trung voi xe da bi phat dang dau khong."""
        spots = self.fined_spots.setdefault(pid, [])
        # Don dep cac diem do da trong xe qua spot_clear_s
        self.fined_spots[pid] = [
            s for s in spots if (t - s.get("last_seen_t", 0.0)) <= self.spot_clear_s
        ]
        spots = self.fined_spots[pid]

        for s in spots:
            sc = s.get("center")
            if sc is not None:
                dist = ((center[0] - sc[0]) ** 2 + (center[1] - sc[1]) ** 2) ** 0.5
                if dist <= self.spot_dist_px:
                    return s

            sb = s.get("bbox")
            if sb is not None and bbox is not None:
                # Kiem tra IoU overlap
                ix1 = max(sb[0], bbox[0])
                iy1 = max(sb[1], bbox[1])
                ix2 = min(sb[2], bbox[2])
                iy2 = min(sb[3], bbox[3])
                if ix2 > ix1 and iy2 > iy1:
                    iarea = (ix2 - ix1) * (iy2 - iy1)
                    sarea = (sb[2] - sb[0]) * (sb[3] - sb[1])
                    barea = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                    iou = iarea / float(sarea + barea - iarea + 1e-6)
                    if iou >= 0.25:
                        return s
        return None

    def update(self, track, polygon, wall_min, frame_idx, t, frame=None):  # pyright: ignore[reportIncompatibleMethodOverride]
        pid = polygon.get("id", "POLY")
        # Kiem tra khung gio cam do (neu co)
        if self._windows(polygon) and not in_active_hours(
                wall_min, self._windows(polygon)):
            self._st(track).pop(pid, None)
            return None

        # Kiem tra loai xe bi cam do (neu polygon co cau hinh banned_classes khong rong)
        banned = polygon.get("banned_classes")
        if banned and track.cls not in banned:
            self._st(track).pop(pid, None)
            return None

        if len(track.pts) < 2 or track.hits < self.min_hits:
            return None

        curr = track.pts[-1]
        prev = track.pts[-2]
        poly_pts = polygon.get("polygon", [])

        # Kiem tra vi tri xe co trong polygon cam do khong
        in_zone = self._is_inside_poly(track, poly_pts)
        pst = self._st(track)
        z = pst.get(pid)

        if not in_zone:
            if z and not z.get("fired"):
                pst.pop(pid, None)
            return None

        # Tinh toa do tam xe
        bb = track.bbox
        center = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0) if bb is not None else curr

        # Kiem tra xem vi tri nay da co xe bi phat chua (chong trung lap khi xe dau lau hoac nhay track ID)
        fined_spot = self._find_matching_fined_spot(pid, center, bb, t)
        if fined_spot is not None:
            # Xe van dang dau o vi tri cu da bi phat -> cap nhat thoi gian nhin thay, khong bao loi lai
            fined_spot["last_seen_t"] = t
            if z is not None:
                z["fired"] = True
            return None

        # Neu chinh track nay da ban roi va van chua roi di -> khong ban them
        if z is not None and z.get("fired"):
            return None

        # Tinh van toc tuc thoi va EMA
        step = ((curr[0] - prev[0]) ** 2 + (curr[1] - prev[1]) ** 2) ** 0.5
        vx, vy = getattr(track, "vel", (curr[0] - prev[0], curr[1] - prev[1]))
        spd = (vx * vx + vy * vy) ** 0.5

        if z is None:
            # Bat dau dung: xe phai di chuyen cham
            if step > self.max_speed_px and spd > self.max_speed_px:
                return None
            pst[pid] = {
                "start_t": t,
                "start_frame_idx": frame_idx,
                "start_bc": list(curr),
                "start_bbox": list(track.bbox) if track.bbox is not None else None,
                "start_frame": frame.copy() if frame is not None else None,
                "fired": False,
            }
            return None

        # Da ghi nhan xe bat dau dung:
        # Kiem tra khoang cach hien tai so voi vi tri ban dau luc dung (chong rung jitter tracker)
        start_bc = z.get("start_bc", curr)
        dist_from_start = ((curr[0] - start_bc[0]) ** 2 + (curr[1] - start_bc[1]) ** 2) ** 0.5

        # Xe chi bi coi la roi di neu da cach xa vi tri do (> 35px) VA van toc cao
        if dist_from_start > 35.0 and (step > self.max_speed_px and spd > self.max_speed_px):
            if not z.get("fired"):
                pst.pop(pid, None)
            return None

        dwell_time = t - z["start_t"]
        target_dwell = float(polygon.get("dwell_s", self.dwell_s))

        if not z["fired"] and dwell_time >= target_dwell and cooldown_ok(track, self.TYPE, t):
            z["fired"] = True
            track.cooldowns[self.TYPE] = t + self.cooldown_s

            # Luu vi tri da phat de cac frame tiep theo hoac track ID moi khong bi phat trung lap
            self.fined_spots.setdefault(pid, []).append({
                "center": center,
                "bbox": list(bb) if bb is not None else None,
                "last_seen_t": t,
                "fired_t": t,
                "tid": track.tid,
            })

            shot1 = z.get("start_frame")
            shot1_t = z.get("start_t", t)
            shot1_bb = z.get("start_bbox") or track.bbox
            shot1_bc = z.get("start_bc") or curr

            shot2 = frame.copy() if frame is not None else None
            shot2_t = t
            shot2_bb = list(track.bbox) if track.bbox is not None else None
            shot2_bc = list(curr)

            ev = {
                "type": self.TYPE,
                "track_id": track.tid,
                "cls": track.cls,
                "conf": track.conf,
                "bbox": track.bbox,
                "bc": curr,
                "line_id": pid,
                "frame_idx": frame_idx,
                "t": t,
                "extra": {
                    "zone_id": pid,
                    "dwell_s": round(dwell_time, 1),
                    "target_dwell_s": target_dwell,
                    "speed_px": round(spd, 2),
                },
            }

            if shot1 is not None and shot2 is not None:
                ev["extra"]["triptych"] = [shot1, shot2]
                ev["extra"]["triptych_timestamps"] = [round(shot1_t, 3), round(shot2_t, 3)]
                ev["extra"]["triptych_bboxes"] = [shot1_bb, shot2_bb]
                ev["extra"]["triptych_bcs"] = [shot1_bc, shot2_bc]
                ev["extra"]["triptych_captions"] = ["1 BAT DAU DUNG", f"2 DO QUA {int(target_dwell)}S"]
            elif shot2 is not None:
                ev["extra"]["evidence_frame"] = shot2

            return ev

        return None

    def run(self, entry, track, frame_idx, t, wall_min=None, frame=None, signals=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay)."""
        poly = entry.get("polygon")
        if not poly or not poly.get("polygon"):
            return None
        return self.update(track, poly, wall_min, frame_idx, t, frame=frame)

    def explain(self, track, t=None, polygon=None, wall_min=None, **ctx):
        """Ly do trang thai hien tai (khong doi state)."""
        pid = (polygon or {}).get("id", "?")
        if polygon is not None and self._windows(polygon) \
                and wall_min is not None and not in_active_hours(
                    wall_min, self._windows(polygon)):
            return f"no_parking tid={track.tid}: ngoai gio cam do ({pid})"
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return f"no_parking tid={track.tid}: track moi (hits={track.hits}<{self.min_hits})"
        poly_pts = (polygon or {}).get("polygon", [])
        if not self._is_inside_poly(track, poly_pts):
            return f"no_parking tid={track.tid}: ngoai zone ({pid})"
        
        # Kiem tra da phat vi tri
        if t is not None:
            bb = track.bbox
            center = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0) if bb is not None else track.pts[-1]
            if self._find_matching_fined_spot(pid, center, bb, t) is not None:
                return f"no_parking tid={track.tid}: xe tai vi tri nay da bi phat ({pid})"

        pst = self._st(track)
        z = pst.get(pid)
        if z and z.get("start_t") is not None:
            dw = round(t - z["start_t"], 1) if t is not None else 0.0
            target = float((polygon or {}).get("dwell_s", self.dwell_s))
            if z.get("fired"):
                return f"no_parking tid={track.tid}: da bao do xe ({pid})"
            return f"no_parking tid={track.tid}: dang dung trong zone {dw}/{target:.0f}s ({pid})"
        return f"no_parking tid={track.tid}: dang di chuyen trong zone ({pid})"

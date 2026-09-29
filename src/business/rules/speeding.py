"""Loi chay qua toc do (§4.5 + homography doc).

- Bottom-Center -> pixel_to_road(H) -> (X, Y) met.
- Sliding window N frames + chieu longitudinal len road_dir + MA 0.8s.
- Reject: thieu history, bbox nho, jump/ID-switch, frame rung.
- Vuot limit + duy tri sustain_s -> bao 1 lan (dedup bang cooldown).
- Luu y phap ly (plan): chi canh bao/thong ke, khong phat truc tiep.
"""
import math
from collections import deque

import cv2
import numpy as np

from ...utils.constants import EPS
from ...utils.homography import longitudinal_dist, pixel_to_road
from .base import BaseRule, cooldown_ok


class SpeedingRule(BaseRule):
    """Pure-vision speeding tren road plane."""

    TYPE = "speeding"
    PARAMS = {"limit_kmh": 80.0, "window_size": 10, "smooth_window_s": 0.8, #speed 80
              "min_track_frames": 20, "min_bbox_height": 15.0,
              "max_speed_kmh": 250.0, "sustain_s": 1.0, #max_speed 250
              "max_background_shift_px": 2.0, "measure": "longitudinal",
              "min_hits": 3, "cooldown_s": 10.0, "mode": "spline"}

    def __init__(self, limit_kmh=80.0, window_size=10, smooth_window_s=0.8,
                 min_track_frames=20, min_bbox_height=15.0,
                 max_speed_kmh=250.0, sustain_s=1.0,
                 max_background_shift_px=2.0, measure="longitudinal",
                 min_hits=3, cooldown_s=10.0, mode="spline"):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)
        self.limit = float(limit_kmh)
        self.window = int(window_size)
        self.smooth_s = float(smooth_window_s)
        self.min_frames = int(min_track_frames)
        self.min_h = float(min_bbox_height)
        self.max_speed = float(max_speed_kmh)
        self.sustain_s = float(sustain_s)
        self.max_shift = float(max_background_shift_px)
        self.measure = measure
        self.mode = mode
        # Cache LK theo frame (tinh 1 lan/frame, khong phai moi track)
        self._bg = {"idx": -1, "shift": 0.0, "gray": None, "pts": None}

    # -- state tren track (tracker tu prune -> khong leak) --
    @staticmethod
    def _st(track):
        st = getattr(track, "speed", None)
        if st is None:
            st = track.speed = {"hist": deque(maxlen=64),
                                "raw": deque(maxlen=64),
                                "smooth": 0.0, "conf": 0.0,
                                "over_since": None, "last": 0.0,
                                "skipped_shake": False}
        return st

    def _bg_shift(self, frame, frame_idx):
        """Do dich chuyen nen (px) 1 lan/frame. None neu khong do duoc."""
        if frame is None:
            return 0.0
        if self._bg["idx"] == frame_idx:
            return self._bg["shift"]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        prev, p0 = self._bg["gray"], self._bg["pts"]
        shift = 0.0
        if prev is not None and p0 is not None and len(p0) >= 10:
            p1, st_mask, _ = cv2.calcOpticalFlowPyrLK(prev, gray, p0, None)  # pyright: ignore[reportCallIssue, reportArgumentType]
            if p1 is not None:
                ok = st_mask.ravel().astype(bool)
                if int(ok.sum()) >= 10:
                    d = (p1[ok] - p0[ok]).reshape(-1, 2)
                    shift = float(np.median(np.hypot(d[:, 0], d[:, 1])))
        p0 = cv2.goodFeaturesToTrack(gray, maxCorners=150, qualityLevel=0.01,
                                     minDistance=15)
        self._bg = {"idx": frame_idx, "shift": shift, "gray": gray, "pts": p0}
        return shift

    def update(self, track, H, road_dir, H_error, frame, frame_idx, t, spline=None):  # pyright: ignore[reportIncompatibleMethodOverride]
        st = self._st(track)
        st["limit"] = self.limit  # overlay dung de to mau
        st["skipped_shake"] = False
        if len(track.pts) < 1 or track.hits < self.min_hits:
            return None
        try:
            bbox_h = float(track.bbox[3] - track.bbox[1])
        except (TypeError, IndexError):
            bbox_h = 0.0
        if bbox_h < self.min_h:
            return None  # bbox nho: vi tri khong dang tin (§40)
        if self._bg_shift(frame, frame_idx) > self.max_shift:
            st["skipped_shake"] = True  # rung: bo frame, khong tich luy
            return None
        bc = track.pts[-1]

        # 1. Tinh toa do mat duong bang Spline tim duong (cong + thang) hoac ma tran H
        if spline is not None:
            try:
                s, d, _ = spline.project(bc[0], bc[1])
            except Exception:
                return None
            st["hist"].append((t, s, d))
            if len(st["hist"]) < 2 or track.hits < self.min_frames:
                return None
            i0 = max(0, len(st["hist"]) - 1 - self.window)
            t0, s0, d0 = st["hist"][i0]
            dt = t - t0
            if dt <= EPS:
                return None
            dist_m = s - s0
        else:
            try:
                X, Y = pixel_to_road(H, bc[0], bc[1])
            except ValueError:
                return None
            st["hist"].append((t, X, Y))
            if len(st["hist"]) < 2 or track.hits < self.min_frames:
                return None
            i0 = max(0, len(st["hist"]) - 1 - self.window)
            t0, X0, Y0 = st["hist"][i0]
            dt = t - t0
            if dt <= EPS:
                return None
            if self.measure == "longitudinal" and road_dir:
                dist_m = longitudinal_dist((X0, Y0), (X, Y), road_dir)
            else:
                dist_m = math.hypot(X - X0, Y - Y0)

        raw = abs(dist_m) / dt * 3.6
        if raw > self.max_speed:
            # Jump/ID-switch/H sai: xa lich su, khong dau doc
            st["hist"].clear()
            if spline is not None:
                st["hist"].append((t, s, d))
            else:
                st["hist"].append((t, X, Y))
            st["raw"].clear()
            st["over_since"] = None
            st["skipped_jump"] = True
            return None
        st["skipped_jump"] = False
        st["raw"].append((t, raw))
        win = [v for tt, v in st["raw"] if t - tt <= self.smooth_s]
        st["smooth"] = sum(win) / len(win)
        st["last"] = raw
        st["conf"] = self._confidence(track, H_error)
        if st["smooth"] > self.limit:
            if st["over_since"] is None:
                st["over_since"] = t
            if t - st["over_since"] >= self.sustain_s \
                    and cooldown_ok(track, self.TYPE, t):
                track.cooldowns[self.TYPE] = t + self.cooldown_s
                return {"type": self.TYPE, "track_id": track.tid,
                        "cls": track.cls, "conf": track.conf,
                        "bbox": track.bbox, "bc": bc,
                        "line_id": "speed",
                        "frame_idx": frame_idx, "t": t,
                        "extra": {"speed_kmh": round(st["smooth"], 1),
                                  "speed_limit_kmh": self.limit,
                                  "confidence": st["conf"],
                                  "calib_mode": "spline" if spline is not None else "homography",
                                  "homography_error_m": H_error if spline is None else 0.0}}
        else:
            st["over_since"] = None
        return None

    def _confidence(self, track, H_error):
        st = self._st(track)
        c_len = min(1.0, len(st["hist"]) / (2.0 * self.window))
        try:
            h = float(track.bbox[3] - track.bbox[1])
        except (TypeError, IndexError):
            h = 0.0
        c_size = min(1.0, h / (3.0 * self.min_h))
        recent = [v for _, v in list(st["raw"])[-5:]]
        if len(recent) >= 2:
            mu = sum(recent) / len(recent)
            var = sum((v - mu) ** 2 for v in recent) / len(recent)
            c_jit = 1.0 / (1.0 + math.sqrt(var) / 10.0)
        else:
            c_jit = 0.5
        c_cal = 1.0 / (1.0 + (H_error or 0.0) * 5.0)
        return round((c_len + c_size + c_jit + c_cal) / 4.0, 2)

    def run(self, entry, track, frame_idx, t, wall_min=None,
            frame=None, signals=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay)."""
        poly = entry["polygon"]
        if poly is None:
            return None
        spline = poly.get("_spline")
        H = poly.get("_H")
        if spline is None and H is None:
            return None
        return self.update(track, H, poly.get("_road_dir", [1.0, 0.0]),
                           float(poly.get("_H_error", 0.0)),
                           frame, frame_idx, t, spline=spline)

    def explain(self, track, t=None, **ctx):
        """Ly do trang thai hien tai (khong doi state)."""
        if len(track.pts) < 1 or track.hits < self.min_hits:
            return (f"speeding tid={track.tid}: track moi "
                    f"(hits={track.hits}<{self.min_hits})")
        st = self._st(track)
        if st.get("skipped_shake"):
            return f"speeding tid={track.tid}: bo frame (camera rung)"
        if st.get("skipped_jump"):
            return f"speeding tid={track.tid}: nghi ID-switch (jump toc do)"
        if len(st["hist"]) < 2 or track.hits < self.min_frames:
            return (f"speeding tid={track.tid}: chua du history "
                    f"({len(st['hist'])}/{self.window + 1})")
        if t is not None:
            left = track.cooldowns.get(self.TYPE, 0.0) - t
            if left > 0:
                return f"speeding tid={track.tid}: cooldown {left:.1f}s"
        if st.get("over_since") is not None and t is not None:
            el = t - st["over_since"]
            return (f"speeding tid={track.tid}: {st['smooth']:.1f}/"
                    f"{self.limit:.0f} kmh, duy tri {el:.1f}/{self.sustain_s:.0f}s")
        return (f"speeding tid={track.tid}: {st['smooth']:.1f}/"
                f"{self.limit:.0f} kmh (conf {st['conf']:.2f})")

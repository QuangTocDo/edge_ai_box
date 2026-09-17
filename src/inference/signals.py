"""Nguon trang thai den giao thong bang HSV (Phase 1, PROJECT_PLAN.md §4.4).

- Moi den co ROI rieng (`signals: [{id, roi, ttl_s}]`).
- Moi frame: crop ROI -> mask HSV do/vang/xanh -> mau troi + debounce
  2 frames lien tiep -> chot state. Khong can model ML.
- Nguong HSV co ban ngay (`hsv`) + ban dem (`hsv_night`, chon theo gio).
- Ho tro tu phat hien che do vang chop tat (flashing yellow mode) ban dem.
"""
import cv2
import numpy as np

GREEN, YELLOW, RED, UNKNOWN = "GREEN", "YELLOW", "RED", "UNKNOWN"
FLASHING_YELLOW = "FLASHING_YELLOW"

DEFAULT_HSV = {
    "red": [[[0, 100, 100], [10, 255, 255]],
            [[160, 100, 100], [180, 255, 255]]],
    "yellow": [[[20, 100, 100], [35, 255, 255]]],
    "green": [[[35, 100, 100], [90, 255, 255]]],
    "min_ratio": 0.05,
    "debounce": 2,
}


def _norm_cfg(hsv_cfg):
    """Gop config user voi default (thieu key lay default)."""
    cfg = {k: v for k, v in DEFAULT_HSV.items()}
    for k, v in (hsv_cfg or {}).items():
        cfg[k] = v
    return cfg


def classify_roi_hsv(crop, hsv_cfg=None):
    """Tra ve 1 trong GREEN/YELLOW/RED/UNKNOWN cho anh crop BGR."""
    cfg = _norm_cfg(hsv_cfg)
    if crop is None or crop.size == 0:
        return UNKNOWN
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    total = hsv.shape[0] * hsv.shape[1]
    best, best_ratio = UNKNOWN, 0.0
    for state, ranges in (("RED", cfg["red"]), ("YELLOW", cfg["yellow"]),
                          ("GREEN", cfg["green"])):
        mask = None
        for lo, hi in ranges:
            m = cv2.inRange(hsv, np.array(lo, dtype=np.uint8),
                            np.array(hi, dtype=np.uint8))
            mask = m if mask is None else cv2.bitwise_or(mask, m)
        if mask is None:  # khong co range nao -> bo qua mau nay
            continue
        ratio = float(np.count_nonzero(mask)) / total
        if ratio > best_ratio:
            best, best_ratio = state, ratio
    if best_ratio < float(cfg["min_ratio"]):
        return UNKNOWN
    return best


def pick_hsv_cfg(red_cfg, wall_min=None):
    """Chon ban ngay/dem theo gio (mac dinh dem 18h-06h)."""
    red_cfg = red_cfg or {}
    night = red_cfg.get("hsv_night")
    if not night:
        return red_cfg.get("hsv")
    try:
        start, end = red_cfg.get("night_hours", [18, 6])
        hour = (wall_min // 60) % 24 if wall_min is not None else -1
        is_night = (hour >= start or hour < end) if start > end \
            else (start <= hour < end)
    except Exception:
        is_night = False
    return night if is_night else red_cfg.get("hsv")


class SignalStore:
    """Store trung tam trang thai cac den (pipeline update moi frame)."""

    def __init__(self, signals_cfg, red_cfg=None, wall_min=None):
        self.signals = {}
        for s in signals_cfg or []:
            self.signals[s["id"]] = {
                "id": s["id"],
                "roi": [int(v) for v in s["roi"]],
                "ttl_s": float(s.get("ttl_s", 1.0)),
                "state": UNKNOWN,
                "updated_at": -1.0,
                "state_changed_at": -1.0,
                "previous_state": UNKNOWN,
                "pending_state": UNKNOWN,
                "pending_count": 0,
                "yellow_to_red_latency_ms": None,
                "is_flashing_yellow": False,
                "_toggle_history": [],  # list (t, raw_state)
            }
        self.red_cfg = red_cfg or {}
        self.wall_min = wall_min

    def _crop(self, frame, roi):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = roi
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def update(self, frame, t, wall_min=None):
        """Classify moi ROI + debounce + phat hien vang chop tat. Tra ve {signal_id: state}."""
        if wall_min is not None:
            self.wall_min = wall_min
        hsv_cfg = pick_hsv_cfg(self.red_cfg, self.wall_min)
        debounce = int((hsv_cfg or {}).get("debounce",
                                           DEFAULT_HSV["debounce"]))
        out = {}
        for sid, s in self.signals.items():
            raw = classify_roi_hsv(self._crop(frame, s["roi"]), hsv_cfg)
            if raw == s["pending_state"]:
                s["pending_count"] += 1
            else:
                s["pending_state"], s["pending_count"] = raw, 1

            # Quan sat chuyen trang thai de phat hien vang chop tat
            hist = s["_toggle_history"]
            if not hist or hist[-1][1] != raw:
                hist.append((t, raw))
            # Giu lich su trong vong 4 giay
            while hist and (t - hist[0][0]) > 4.0:
                hist.pop(0)

            # Kiem tra vang chop tat: neu chi co YELLOW va UNKNOWN lien tuc toggle >= 3 lan
            if len(hist) >= 4:
                states_in_window = {st for _, st in hist}
                if states_in_window.issubset({YELLOW, UNKNOWN}):
                    s["is_flashing_yellow"] = True

            if s["pending_count"] >= debounce and raw != s["state"]:
                prev = s["state"]
                # Neu bat duoc solid GREEN hoac RED du lau, reset che do vang chop
                if raw in (GREEN, RED):
                    s["is_flashing_yellow"] = False
                s["previous_state"] = prev
                s["state"] = FLASHING_YELLOW if s["is_flashing_yellow"] and raw in (YELLOW, UNKNOWN) else raw
                s["state_changed_at"] = t
                if prev == YELLOW and raw == RED \
                        and s.get("_yellow_t") is not None:
                    s["yellow_to_red_latency_ms"] = round(
                        (t - s["_yellow_t"]) * 1000.0, 1)

            if raw == YELLOW and s["state"] in (YELLOW, FLASHING_YELLOW):
                s["_yellow_t"] = t
            s["updated_at"] = t

            # Neu dang o che do vang chop tat ma debounce roi vao UNKNOWN/YELLOW, luon tra ve FLASHING_YELLOW
            eff_state = FLASHING_YELLOW if s["is_flashing_yellow"] else s["state"]
            s["state"] = eff_state
            out[sid] = eff_state
        return out

    def get(self, sid):
        """State dict cua 1 den (None neu khong co)."""
        return self.signals.get(sid)

    def snapshot(self):
        """{sid: {state, roi}} cho overlay debug."""
        return {sid: {"state": s["state"], "roi": s["roi"]}
                for sid, s in self.signals.items()}

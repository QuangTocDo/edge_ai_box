"""Loi dung de vach (§4.4 trong PROJECT_PLAN.md).

Cung diem cat nhu red_light_running nhung xe DUNG LAI sau vach
(toc do < nguong stop_speed_px, dung yen qua stop_dwell_s) -> STOP_LINE_VIOLATION.
Xe tiep tuc di vao giao lo thuoc ve red_light_running (multi-event).
"""
from ..geometry import point_in_polygon
from ._shared import crossed_stop_lines, light_at, red_state
from .base import BaseRule, cooldown_ok


class StopLineRule(BaseRule):
    """RED + dung sau vach -> STOP_LINE_VIOLATION (anh diptych / snapshot)."""

    TYPE = "stop_line_violation"
    PARAMS = {
        "min_hits": 3,
        "cooldown_s": 10.0,
        "stop_speed_px": 1.5,
        "stop_dwell_s": 1.5,
        "dilemma_grace_s": 0.5,
        "dilemma_grace_ms": 500,
        "stop_line_speed_threshold_kmh": 3.0,
        "cand_ttl_s": 30.0,
        "intersection_clearance_zone": None,
    }

    def __init__(self, min_hits=3, cooldown_s=10.0, stop_speed_px=1.5,
                 stop_dwell_s=1.5, dilemma_grace_s=0.5, dilemma_grace_ms=None,
                 stop_line_speed_threshold_kmh=None, cand_ttl_s=30.0,
                 intersection_clearance_zone=None):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)
        self.stop_speed_px = stop_speed_px
        self.stop_dwell_s = stop_dwell_s
        if dilemma_grace_ms is not None:
            self.dilemma_grace_s = dilemma_grace_ms / 1000.0
        else:
            self.dilemma_grace_s = dilemma_grace_s
        self.stop_line_speed_threshold_kmh = stop_line_speed_threshold_kmh
        self.cand_ttl_s = cand_ttl_s
        self.intersection_clearance_zone = intersection_clearance_zone

    def update(self, track, lines, signals, frame_idx, t, frame=None, clearance=None):  # pyright: ignore[reportIncompatibleMethodOverride]
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return None
        sig_lines = [ln for ln in lines if ln.get("signal_id")]
        if not sig_lines:
            return None

        rs = red_state(track)
        curr = track.pts[-1]

        # Don dep candidates cu qua han
        stops = rs.setdefault("stops", {})
        for lid in [k for k, c in stops.items() if t - c["cross_t"] > self.cand_ttl_s]:
            del stops[lid]

        # Kiem tra cat stop-line
        for ln in crossed_stop_lines(track, sig_lines):
            lid = ln["id"]
            if ln.get("allow_right_on_red"):
                continue
            sid = ln.get("signal_id")
            state, sig = light_at(signals, sid, t)

            # Mui xe cham vach luc GREEN/YELLOW/UNKNOWN -> Whitelist cho qua toan bo
            if state in ("GREEN", "YELLOW", "UNKNOWN"):
                rs["wl"] = True
                rs["wl_lines"].add(lid)
                continue

            if rs["wl"] or lid in rs["wl_lines"]:
                continue

            red_start = sig.get("state_changed_at", sig.get("updated_at", t)) if sig else t
            if t - red_start < self.dilemma_grace_s:
                # Trong khoang dilemma, khong phanh kip -> cho qua
                rs["wl_lines"].add(lid)
                continue

            stops[lid] = {
                "cross_t": t,
                "cross_bc": list(curr),
                "cross_bbox": list(track.bbox) if track.bbox is not None else None,
                "cross_frame": frame.copy() if frame is not None else None,
                "signal_id": sid,
                "slow_since": None,
                "fired": False,
            }

        # Theo doi dung sau vach
        clearance = clearance or []
        for lid, c in stops.items():
            if c["fired"]:
                continue
            if rs.get("red_fired"):
                # Xe da vuot nga tu -> khong bat loi dung de vach
                c["fired"] = True
                continue

            # Neu xe da tien vao clearance zone -> thuoc ve red_light_running
            if any(point_in_polygon(curr, poly.get("polygon", [])) for poly in clearance):
                continue

            # Kiem tra trang thai den: den phai dang RED
            sid = c.get("signal_id")
            state, sig = light_at(signals, sid, t)
            if state != "RED":
                # Den khong con RED (da sang GREEN/YELLOW) -> reset slow_since
                c["slow_since"] = None
                continue

            vx, vy = track.vel
            slow = (vx * vx + vy * vy) ** 0.5 < self.stop_speed_px
            if slow:
                if c["slow_since"] is None:
                    c["slow_since"] = t
                if (t - c["slow_since"] >= self.stop_dwell_s
                        and cooldown_ok(track, self.TYPE, t)):
                    c["fired"] = True
                    track.cooldowns[self.TYPE] = t + self.cooldown_s
                    dwell_time = round(t - c["slow_since"], 2)

                    cross_fr = c.get("cross_frame")
                    now_fr = frame.copy() if frame is not None else None
                    cross_bb = c.get("cross_bbox")
                    curr_bb = list(track.bbox) if track.bbox is not None else None
                    cross_bc = c.get("cross_bc")

                    extra = {
                        "light_state": "RED",
                        "light_source": sig.get("source", "vision-hsv") if sig else "vision-hsv",
                        "stop_dwell_s": dwell_time,
                    }
                    if frame is not None:
                        # 2 anh Diptych: 1. De vach + 2. Dung qua vach
                        extra["triptych"] = [cross_fr, now_fr]
                        extra["triptych_timestamps"] = [round(c["cross_t"], 3), round(t, 3)]
                        extra["triptych_bboxes"] = [cross_bb, curr_bb]
                        extra["triptych_bcs"] = [cross_bc, list(curr)]
                        extra["triptych_captions"] = ["1 DE VACH", "2 DUNG QUA VACH"]

                    return {
                        "type": self.TYPE,
                        "track_id": track.tid,
                        "cls": track.cls,
                        "conf": track.conf,
                        "bbox": track.bbox,
                        "bc": curr,
                        "line_id": lid,
                        "frame_idx": frame_idx,
                        "t": t,
                        "extra": extra,
                    }
            else:
                c["slow_since"] = None  # dang chay -> tam dung dem

        return None

    def run(self, entry, track, frame_idx, t, wall_min=None, frame=None,
            signals=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay)."""
        return self.update(track, entry["lines"], signals or {},
                           frame_idx, t, frame=frame,
                           clearance=entry.get("clearance", []))

    def explain(self, track, t=None, **ctx):
        """Ly do trang thai hien tai (khong doi state)."""
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return (f"stop_line tid={track.tid}: track moi "
                    f"(hits={track.hits}<{self.min_hits})")
        rs = getattr(track, "red", None) or {}
        if rs.get("wl"):
            return f"stop_line tid={track.tid}: whitelist (GREEN/YELLOW/UNKNOWN luc vao)"
        if rs.get("wl_lines"):
            return f"stop_line tid={track.tid}: whitelist line(s) {sorted(list(rs['wl_lines']))}"
        stops = rs.get("stops", {})
        active_stops = {k: v for k, v in stops.items() if not v["fired"]}
        if active_stops:
            lid, c = next(iter(active_stops.items()))
            if c.get("slow_since") is not None and t is not None:
                dw = round(t - c["slow_since"], 1)
                return (f"stop_line tid={track.tid}: dang dung sau "
                        f"vach {lid} ({dw}/{self.stop_dwell_s:.1f}s)")
            return (f"stop_line tid={track.tid}: theo doi dung sau "
                    f"vach {lid}")
        if t is not None:
            left = track.cooldowns.get(self.TYPE, 0.0) - t
            if left > 0:
                return f"stop_line tid={track.tid}: cooldown {left:.1f}s"
        return f"stop_line tid={track.tid}: chua cat vach luc do"

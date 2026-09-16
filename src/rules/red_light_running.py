"""Loi vuot den do (Stop-line x RED).

- Gan signal_id vao line tuong ung.
- Stop-line cat dung chieu + trang thai den luc mui xe cham vach:
  GREEN / YELLOW / UNKNOWN (ke ca tin cu het han) -> whitelist track (khong phat).
- RED:
  + Neu KHONG co clearance polygon:
    Giai phap Movement / Velocity Confirmation:
    Khi xe cat vach luc den DO, tao candidate theo doi chuyen dong:
    - Neu xe tiep tuc di chuyen ve phia truoc (forward_px >= confirm_dist_px)
      va duy tri van toc (speed >= confirm_speed_px) qua >= confirm_frames
      -> Xac nhan VUOT DEN DO (red_light_running).
      Xuat bo 3 anh triptych (1 truoc vach, 2 de vach, 3 xac nhan vuot)
      ngay trong pha den DO, voi bounding box rieng cho tung shot!
    - Neu xe giam toc va dung lai gan vach -> Nhuong cho StopLineRule xu ly
      loi DUNG DE VACH (stop_line_violation).
  + Neu CO clearance polygon: Theo doi den khi xe tien vao clearance zone roi moi phat (mode 3 anh triptych).
- Line co allow_right_on_red=true -> bo qua (re phai hop le khi den do).
"""
from ..geometry import allowed_vec, dot, point_in_polygon
from ._shared import (crossed_stop_lines, is_before_stop_line, light_at,
                      near_stop_line, red_state, stash_pre_frame)
from .base import BaseRule, cooldown_ok

# Re-export de tuong thich (code cu import tu day van chay).
__all__ = ["RedLightRunningRule", "red_state", "crossed_stop_lines",
           "is_before_stop_line", "near_stop_line", "light_at",
           "stash_pre_frame"]


class RedLightRunningRule(BaseRule):
    """Stop-line x RED -> RED_LIGHT_RUNNING."""

    TYPE = "red_light_running"
    PARAMS = {
        "min_hits": 3,
        "cooldown_s": 10.0,
        "dilemma_grace_s": 0.0,
        "dilemma_grace_ms": 0,
        "yellow_grace_ms": 1000,
        "pre_zone_px": 150.0,
        "cand_ttl_s": 30.0,
        "intersection_clearance_zone": None,
        "evidence_format": "single",
        "confirm_dist_px": 30.0,
        "confirm_speed_px": 1.5,
        "confirm_frames": 2,
    }

    def __init__(self, min_hits=3, cooldown_s=10.0, dilemma_grace_s=0.0,
                 dilemma_grace_ms=None, yellow_grace_ms=None,
                 pre_zone_px=150.0, cand_ttl_s=30.0,
                 intersection_clearance_zone=None, evidence_format="single",
                 confirm_dist_px=30.0, confirm_speed_px=1.5, confirm_frames=2):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)
        if dilemma_grace_ms is not None:
            self.dilemma_grace_s = dilemma_grace_ms / 1000.0
        else:
            self.dilemma_grace_s = dilemma_grace_s
        self.yellow_grace_ms = yellow_grace_ms
        self.pre_zone_px = pre_zone_px
        self.cand_ttl_s = cand_ttl_s
        self.intersection_clearance_zone = intersection_clearance_zone
        self.evidence_format = evidence_format
        self.confirm_dist_px = float(confirm_dist_px)
        self.confirm_speed_px = float(confirm_speed_px)
        self.confirm_frames = int(confirm_frames)

    def update(self, track, lines, signals, clearance, frame, frame_idx, t):  # pyright: ignore[reportIncompatibleMethodOverride]
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return None
        sig_lines = [ln for ln in lines if ln.get("signal_id")]
        if not sig_lines:
            return None

        rs = red_state(track)
        curr = track.pts[-1]
        prev = track.pts[-2]

        # Don dep candidate cu qua han
        for lid in [k for k, c in rs["cands"].items()
                    if t - c["cross_t"] > self.cand_ttl_s]:
            del rs["cands"][lid]

        # Luon luu truoc frame truoc vach luc den RED lam shot 1 cho triptych
        stash_pre_frame(track, sig_lines, signals, t, frame, self.pre_zone_px)

        # Kiem tra cat stop-line
        for ln in crossed_stop_lines(track, sig_lines):
            lid = ln["id"]
            if ln.get("allow_right_on_red"):
                continue
            sid = ln.get("signal_id")
            state, sig = light_at(signals, sid, t)

            # Mui xe cham vach luc GREEN/YELLOW/UNKNOWN -> whitelist cho qua toan bo
            if state in ("GREEN", "YELLOW", "UNKNOWN"):
                rs["wl"] = True
                rs["wl_lines"].add(lid)
                continue

            if rs["wl"] or lid in rs["wl_lines"]:
                continue

            # RED: kiem tra dilemma grace neu duoc cau hinh (> 0)
            if self.dilemma_grace_s > 0:
                red_start = sig.get("state_changed_at", sig.get("updated_at", t)) if sig else t
                if t - red_start < self.dilemma_grace_s:
                    rs["wl_lines"].add(lid)
                    continue

            # Neu khong co clearance va dat confirm_dist_px <= 0 -> phat ngay lap tuc
            if not clearance and self.confirm_dist_px <= 0 and self.confirm_frames <= 1:
                if not cooldown_ok(track, self.TYPE, t):
                    continue
                rs["red_fired"] = True
                track.cooldowns[self.TYPE] = t + self.cooldown_s
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
                    "extra": {
                        "light_state": "RED",
                        "light_source": sig.get("source", "vision-hsv") if sig else "vision-hsv",
                        "signal_id": sid,
                        "yellow_to_red_latency_ms": sig.get("yellow_to_red_latency_ms") if sig else None,
                    },
                }

            # Tao candidate theo doi chuyen dong
            shot1 = rs.get("pre")
            shot1_t = rs.get("pre_t")
            shot1_bb = rs.get("pre_bbox")
            shot1_bc = rs.get("pre_bc")
            cross_frame = frame.copy() if frame is not None else None
            cross_bbox = list(track.bbox) if track.bbox is not None else None
            rs["cands"][lid] = {
                "line": ln,
                "shot1": shot1,
                "shot1_t": shot1_t,
                "shot1_bbox": shot1_bb,
                "shot1_bc": shot1_bc,
                "cross_frame": cross_frame,
                "cross_t": t,
                "cross_frame_idx": frame_idx,
                "cross_bc": list(curr),
                "cross_bbox": cross_bbox,
                "signal_id": sid,
                "latency": sig.get("yellow_to_red_latency_ms") if sig else None,
                "forward_px": 0.0,
                "moving_frames": 0,
                "fired": False,
            }

        # Theo doi candidate vuot den do
        for lid, c in rs["cands"].items():
            if c["fired"]:
                continue

            sid = c.get("signal_id")
            state, sig = light_at(signals, sid, t)
            # Den da sang GREEN hoac dang bat dau chuyen sang GREEN -> huy candidate
            pending_green = sig and sig.get("pending_state") == "GREEN"
            if state in ("GREEN", "YELLOW") or pending_green:
                c["fired"] = True
                continue

            # Case 1: Co clearance polygon
            if clearance:
                if not any(point_in_polygon(curr, poly.get("polygon", []))
                           for poly in clearance):
                    continue

                if not cooldown_ok(track, self.TYPE, t):
                    continue

                c["fired"] = True
                rs["red_fired"] = True
                track.cooldowns[self.TYPE] = t + self.cooldown_s

                if lid in rs.get("stops", {}):
                    rs["stops"][lid]["fired"] = True

                shot3 = frame.copy() if frame is not None else None
                shot1 = c["shot1"] if c.get("shot1") is not None else c["cross_frame"]
                t1 = c["shot1_t"] if c.get("shot1_t") is not None else round(c["cross_t"] - 0.5, 3)
                shot1_bb = c.get("shot1_bbox") or c["cross_bbox"]
                shot1_bc = c.get("shot1_bc") or c["cross_bc"]

                triptych = [shot1, c["cross_frame"], shot3] if frame is not None else None
                triptych_bboxes = [shot1_bb, c["cross_bbox"], list(track.bbox) if track.bbox is not None else None]
                triptych_bcs = [shot1_bc, c["cross_bc"], curr]

                ev = {
                    "type": self.TYPE,
                    "track_id": track.tid,
                    "cls": track.cls,
                    "conf": track.conf,
                    "bbox": track.bbox,
                    "bc": curr,
                    "line_id": lid,
                    "frame_idx": frame_idx,
                    "t": t,
                    "extra": {
                        "light_state": "RED",
                        "light_source": sig.get("source", "vision-hsv") if sig else "vision-hsv",
                        "yellow_to_red_latency_ms": c["latency"],
                        "clearance_zone_entered": True,
                        "triptych_timestamps": [
                            round(t1, 3),
                            round(c["cross_t"], 3),
                            round(t, 3),
                        ],
                        "triptych_bboxes": triptych_bboxes,
                        "triptych_bcs": triptych_bcs,
                    },
                }
                if triptych:
                    ev["extra"]["triptych"] = triptych
                return ev

            # Case 2: Khong co clearance -> Movement / Velocity Confirmation
            else:
                ln = c.get("line")
                if not ln:
                    continue
                ax, ay = allowed_vec(ln["p1"], ln["p2"], ln.get("allowed_sign", 1))
                step = dot(curr[0] - prev[0], curr[1] - prev[1], ax, ay)
                if step > 0:
                    c["forward_px"] += step

                vx, vy = track.vel
                spd = (vx * vx + vy * vy) ** 0.5
                if spd >= self.confirm_speed_px:
                    c["moving_frames"] += 1
                else:
                    c["moving_frames"] = max(0, c["moving_frames"] - 1)

                # Kiem tra dieu kien vuot: di tiep qua nguong confirm_dist_px va duy tri toc do
                if (c["forward_px"] >= self.confirm_dist_px
                        and c["moving_frames"] >= self.confirm_frames
                        and spd >= self.confirm_speed_px
                        and cooldown_ok(track, self.TYPE, t)):
                    c["fired"] = True
                    rs["red_fired"] = True
                    track.cooldowns[self.TYPE] = t + self.cooldown_s

                    # Xe tiep tuc chay qua giao lo -> huy candidate dung de vach
                    if lid in rs.get("stops", {}):
                        rs["stops"][lid]["fired"] = True

                    shot1 = c["shot1"] if c.get("shot1") is not None else c["cross_frame"]
                    t1 = c["shot1_t"] if c.get("shot1_t") is not None else round(c["cross_t"] - 0.5, 3)
                    shot1_bb = c.get("shot1_bbox") or c["cross_bbox"]
                    shot1_bc = c.get("shot1_bc") or c["cross_bc"]
                    curr_bb = list(track.bbox) if track.bbox is not None else c["cross_bbox"]

                    ev = {
                        "type": self.TYPE,
                        "track_id": track.tid,
                        "cls": track.cls,
                        "conf": track.conf,
                        "bbox": c["cross_bbox"] or track.bbox,
                        "bc": c["cross_bc"] or curr,
                        "line_id": lid,
                        "frame_idx": c.get("cross_frame_idx", frame_idx),
                        "t": c.get("cross_t", t),
                        "extra": {
                            "light_state": "RED",
                            "light_source": sig.get("source", "vision-hsv") if sig else "vision-hsv",
                            "signal_id": sid,
                            "yellow_to_red_latency_ms": c.get("latency"),
                            "forward_px": round(c["forward_px"], 1),
                            "speed_px": round(spd, 2),
                        },
                    }

                    # Neu co frame -> xuat 3 anh triptych voi bbox rieng tung shot
                    if frame is not None and c.get("cross_frame") is not None:
                        shot3 = frame.copy()
                        ev["extra"]["triptych"] = [shot1, c["cross_frame"], shot3]
                        ev["extra"]["triptych_timestamps"] = [
                            round(t1, 3),
                            round(c["cross_t"], 3),
                            round(t, 3),
                        ]
                        ev["extra"]["triptych_bboxes"] = [shot1_bb, c["cross_bbox"], curr_bb]
                        ev["extra"]["triptych_bcs"] = [shot1_bc, c["cross_bc"], curr]
                    else:
                        ev["extra"]["evidence_frame"] = c.get("cross_frame")

                    return ev

        return None

    def run(self, entry, track, frame_idx, t, wall_min=None, frame=None,
            signals=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay)."""
        return self.update(track, entry["lines"], signals or {},
                           entry.get("clearance", []), frame,
                           frame_idx, t)

    def explain(self, track, t=None, lines=None, signals=None, **ctx):
        """Ly do trang thai hien tai (khong doi state)."""
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return (f"red_light tid={track.tid}: track moi "
                    f"(hits={track.hits}<{self.min_hits})")
        rs = getattr(track, "red", None) or {}
        if rs.get("red_fired"):
            return f"red_light tid={track.tid}: da bao vuot den do"
        if rs.get("wl"):
            return f"red_light tid={track.tid}: whitelist (GREEN/YELLOW/UNKNOWN luc vao)"
        if rs.get("wl_lines"):
            return f"red_light tid={track.tid}: whitelist line(s) {sorted(list(rs['wl_lines']))}"
        if rs.get("cands"):
            active_cands = [k for k, v in rs["cands"].items() if not v["fired"]]
            if active_cands:
                lid = active_cands[0]
                c = rs["cands"][lid]
                dt = round(t - c["cross_t"], 1) if t is not None else 0.0
                return (f"red_light tid={track.tid}: theo doi chuyen dong sau {lid} "
                        f"(fwd={c.get('forward_px', 0):.0f}/{self.confirm_dist_px:.0f}px, "
                        f"dt={dt}s)")
        if t is not None:
            left = track.cooldowns.get(self.TYPE, 0.0) - t
            if left > 0:
                return f"red_light tid={track.tid}: cooldown {left:.1f}s"
        return f"red_light tid={track.tid}: chua cat vach luc do"

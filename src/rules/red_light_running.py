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
      Anh evidence duoc luu tai dung frame cat vach.
    - Neu xe giam toc va dung lai gan vach -> Nhuong cho StopLineRule xu ly
      loi DUNG DE VACH (stop_line_violation).
  + Neu CO clearance polygon: Theo doi den khi xe tien vao clearance zone roi moi phat (mode 3 anh triptych).
- Line co allow_right_on_red=true -> bo qua (re phai hop le khi den do).
"""
from ..geometry import allowed_vec, crossing_sign, dot, point_in_polygon
from .base import BaseRule, cooldown_ok


def red_state(track):
    """Scratch rieng den do tren track (tu clean khi track chet)."""
    rs = getattr(track, "red", None)
    if rs is None:
        rs = track.red = {
            "wl": False,
            "wl_lines": set(),
            "cands": {},
            "stops": {},
            "pre": None,
            "pre_t": None,
            "red_fired": False,
        }
    return rs


def _dist_pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    if n < 1e-9:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / n))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def is_before_stop_line(pt, ln):
    """Kiem tra diem pt co dang o phia truoc vach dung (chua vuot) hay khong."""
    p1, p2 = ln["p1"], ln["p2"]
    allowed_sign = ln.get("allowed_sign", 1)
    ax, ay = allowed_vec(p1, p2, allowed_sign)
    mx, my = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    vx, vy = pt[0] - mx, pt[1] - my
    return dot(vx, vy, ax, ay) < 0


def crossed_stop_lines(track, lines):
    """Cac stop-line vua cat dung chieu frame nay [(line, ...)]."""
    if len(track.pts) < 2:
        return []
    prev, curr = track.pts[-2], track.pts[-1]
    out = []
    for ln in lines:
        if ln.get("role") == "divider":
            continue
        sign = crossing_sign(prev, curr, ln["p1"], ln["p2"])
        if sign != 0 and sign == ln.get("allowed_sign", 1):
            out.append(ln)
    return out


def near_stop_line(track, lines, px):
    """Kiem tra xe co o gan bat ky stop-line nao trong khoang cach px."""
    if not track.pts:
        return False
    curr = track.pts[-1]
    for ln in lines:
        if ln.get("role") == "divider":
            continue
        ax, ay = ln["p1"]
        bx, by = ln["p2"]
        if _dist_pt_seg(curr[0], curr[1], ax, ay, bx, by) <= px:
            return True
    return False


def stash_pre_frame(track, lines, signals, t, frame, px=150.0):
    """Luu frame truoc vach luc den RED lam anh 1 cho triptych (neu can)."""
    if frame is None or len(track.pts) < 1:
        return
    curr = track.pts[-1]
    rs = red_state(track)
    for ln in lines:
        if ln.get("role") == "divider":
            continue
        sid = ln.get("signal_id")
        if not sid:
            continue
        ax, ay = ln["p1"]
        bx, by = ln["p2"]
        if _dist_pt_seg(curr[0], curr[1], ax, ay, bx, by) <= px:
            if is_before_stop_line(curr, ln):
                state, _ = light_at(signals, sid, t)
                if state == "RED":
                    rs["pre"] = frame.copy()
                    rs["pre_t"] = t
                    return


def light_at(signals, sid, t, default_ttl=1.0):
    """(state, sig_dict) tai thoi diem t. Cu het han -> UNKNOWN."""
    if not sid or not signals:
        return "UNKNOWN", None
    sig = signals.get(sid) if hasattr(signals, "get") else None
    if not sig:
        return "UNKNOWN", None
    if isinstance(sig, str):
        sig = {"state": sig, "updated_at": t, "state_changed_at": t, "ttl_s": default_ttl, "source": "test"}
    ttl = float(sig.get("ttl_s", default_ttl))
    up = sig.get("updated_at", -1.0)
    if up >= 0 and (t - up) >= ttl:
        return "UNKNOWN", sig
    return sig.get("state", "UNKNOWN"), sig


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

    def update(self, track, lines, signals, clearance, frame, frame_idx, t):
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

        # Stash frame truoc vach luc den RED (neu dung mode triptych voi clearance)
        if clearance:
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
            cross_frame = frame.copy() if frame is not None else None
            rs["cands"][lid] = {
                "line": ln,
                "shot1": shot1,
                "shot1_t": shot1_t,
                "cross_frame": cross_frame,
                "cross_t": t,
                "cross_frame_idx": frame_idx,
                "cross_bc": curr,
                "cross_bbox": list(track.bbox) if track.bbox is not None else None,
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
            # Den da sang GREEN -> huy candidate
            if state == "GREEN":
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
                triptych = [shot1, c["cross_frame"], shot3]

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
                        "yellow_to_red_latency_ms": c["latency"],
                        "clearance_zone_entered": True,
                        "triptych_timestamps": [
                            round(t1, 3),
                            round(c["cross_t"], 3),
                            round(t, 3),
                        ],
                        "triptych": triptych,
                    },
                }

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

                    return {
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
                            "evidence_frame": c.get("cross_frame"),
                        },
                    }

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

"""Helpers dung chung cho 2 rule den do (red_light_running + stop_line_violation).

Tach rieng de pha bo phu thuoc stop_line -> red_light_running:
sua 1 rule khong con nguy co vo tinh vo rule kia.
"""
from ..constants import EPS
from ..geometry import allowed_vec, crossing_sign, dot, point_in_polygon


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
            "pre_bbox": None,
            "pre_bc": None,
            "red_fired": False,
        }
    return rs


def _dist_pt_seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    n = dx * dx + dy * dy
    if n < EPS:
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
                    rs["pre_bbox"] = list(track.bbox) if track.bbox is not None else None
                    rs["pre_bc"] = list(curr)
                    return

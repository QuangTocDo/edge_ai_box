"""Loi cam quay dau (§4.3).

Sequence thuan, KHONG check thoi gian: cat line 1 dung chieu ->
cat line 2 dung chieu (RL->LR hoac LR->RL tuy cau hinh pair)
la bao vi pham. Xe chay nhanh cham 2 vach cach nhau <2s van ban.
Xac nhan dao huong bang heading: EMA (on dinh) hoac huong tuc thoi
buoc cuoi (nhay bat quay dau nhanh ma EMA chua kip lat).
"""
import math

from ...utils.geometry import crossing_sign, heading_deg
from .base import BaseRule, cooldown_ok


class NoUTurnRule(BaseRule):
    """Sequence thuan + xac nhan dao huong bang heading.

    Cat line 1 dung chieu -> flag (kem heading luc cat). Cat line 2 dung
    chieu -> chi fire neu heading dao ~180 do (delta trong [120, 240]).
    Thieu heading (xe cham/dung) thi fire nhu cu. Khong fire thi xoa flag
    line 1 (het treo oan). Khong check thoi gian nhu cu.
    """

    TYPE = "no_uturn"
    PARAMS = {"min_hits": 3, "cooldown_s": 10.0}

    # Nguong dao chieu (do): chap nhan cua khong gat
    TURN_MIN_DEG = 120.0
    TURN_MAX_DEG = 240.0
    # Nguong buoc tuc thoi toi thieu (px) de tin huong frame cuoi.
    # Du lon de loai rung bbox, du nho de bat quay dau nhanh.
    INST_MIN_STEP_PX = 3.0

    def __init__(self, min_hits=3, cooldown_s=10.0):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)

    def update(self, track, lines, pairs, frame_idx, t):  # pyright: ignore[reportIncompatibleMethodOverride]
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return None
        prev, curr = track.pts[-2], track.pts[-1]
        heading_now = getattr(track, "heading", None)
        second_now = set()  # line dung chieu vua cat frame nay
        for ln in lines:
            if ln.get("role") == "divider":
                continue
            sign = crossing_sign(prev, curr, ln["p1"], ln["p2"])
            if sign != 0 and sign == ln.get("allowed_sign", 1):
                track.line_flags[ln["id"]] = (frame_idx, t, heading_now)
                second_now.add(ln["id"])
        for pr in pairs:
            f1, f2 = pr["first"], pr["second"]
            if f2 not in second_now or f1 not in track.line_flags:
                continue
            flag = track.line_flags[f1]
            _, t_entry = flag[0], flag[1]
            h_entry = flag[2] if len(flag) > 2 else None
            dt = t - t_entry
            if not cooldown_ok(track, self.TYPE, t):
                continue
            h_now = heading_now
            turn = None
            if h_entry is not None and h_now is not None:
                d = abs(float(h_now) - float(h_entry)) % 360.0
                if self.TURN_MIN_DEG <= d <= self.TURN_MAX_DEG:
                    turn = (float(h_entry), float(h_now), d)
            if turn is None and h_entry is not None:
                # EMA chua kip lat (quay dau nhanh): thu huong tuc thoi
                # buoc cuoi (bo qua rung nho). Van khong dat -> xoa flag.
                step = math.hypot(curr[0] - prev[0], curr[1] - prev[1])
                h_inst = heading_deg(curr[0] - prev[0], curr[1] - prev[1]) \
                    if step >= self.INST_MIN_STEP_PX else None
                if h_inst is not None:
                    d2 = abs(float(h_inst) - float(h_entry)) % 360.0
                    if self.TURN_MIN_DEG <= d2 <= self.TURN_MAX_DEG:
                        turn = (float(h_entry), float(h_inst), d2)
            if turn is None:
                # Di thang qua 2 vach, khong phai quay dau: xoa flag
                track.line_flags.pop(f1, None)
                continue
            track.cooldowns[self.TYPE] = t + self.cooldown_s
            track.line_flags.pop(f1, None)
            extra: dict = {"dt_s": round(dt, 2)}
            if turn is not None:
                extra["heading_from"] = round(turn[0], 1)
                extra["heading_to"] = round(turn[1], 1)
                extra["turn_deg"] = round(turn[2], 1)
            return {"type": self.TYPE, "track_id": track.tid,
                    "cls": track.cls, "conf": track.conf,
                    "bbox": track.bbox, "bc": curr,
                    "line_id": f"{f1}->{f2}", "frame_idx": frame_idx, "t": t,
                    "extra": extra}
        return None

    def run(self, entry, track, frame_idx, t, wall_min=None,
            frame=None, signals=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay)."""
        for pr in entry["pairs"]:
            e = self.update(track, entry["lines"], [pr], frame_idx, t)
            if e:
                return e
        return None

    def explain(self, track, t=None, pairs=None, **ctx):
        """Ly do trang thai hien tai (khong doi state)."""
        if len(track.pts) < 2:
            return f"no_uturn tid={track.tid}: chua du 2 diem"
        if track.hits < self.min_hits:
            return (f"no_uturn tid={track.tid}: track moi "
                    f"(hits={track.hits}<{self.min_hits})")
        if track.line_flags:
            have = sorted(track.line_flags)
            return (f"no_uturn tid={track.tid}: co flag {have}, "
                    f"doi cat vach 2")
        if t is not None:
            left = track.cooldowns.get(self.TYPE, 0.0) - t
            if left > 0:
                return f"no_uturn tid={track.tid}: cooldown {left:.1f}s"
        return f"no_uturn tid={track.tid}: chua co flag cat vach"

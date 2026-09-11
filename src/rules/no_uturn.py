"""Loi cam quay dau (§4.3).

Sequence thuan, KHONG check thoi gian: cat line 1 dung chieu ->
cat line 2 dung chieu (RL->LR hoac LR->RL tuy cau hinh pair)
la bao vi pham. Xe chay nhanh cham 2 vach cach nhau <2s van ban.
"""
from ..geometry import crossing_sign
from .base import BaseRule, cooldown_ok


class NoUTurnRule(BaseRule):
    """Sequence thuan, KHONG check thoi gian: cat line 1 dung chieu ->
    cat line 2 dung chieu (RL->LR hoac LR->RL tuy cau hinh pair)
    la bao vi pham."""

    TYPE = "no_uturn"
    PARAMS = {"min_hits": 3, "cooldown_s": 10.0}

    def __init__(self, min_hits=3, cooldown_s=10.0):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)

    def update(self, track, lines, pairs, frame_idx, t):
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return None
        prev, curr = track.pts[-2], track.pts[-1]
        second_now = set()  # line dung chieu vua cat frame nay
        for ln in lines:
            if ln.get("role") == "divider":
                continue
            sign = crossing_sign(prev, curr, ln["p1"], ln["p2"])
            if sign != 0 and sign == ln.get("allowed_sign", 1):
                track.line_flags[ln["id"]] = (frame_idx, t)
                second_now.add(ln["id"])
        for pr in pairs:
            f1, f2 = pr["first"], pr["second"]
            if f2 not in second_now or f1 not in track.line_flags:
                continue
            _, t_entry = track.line_flags[f1]
            dt = t - t_entry
            if not cooldown_ok(track, self.TYPE, t):
                continue
            track.cooldowns[self.TYPE] = t + self.cooldown_s
            track.line_flags.pop(f1, None)
            return {"type": self.TYPE, "track_id": track.tid,
                    "cls": track.cls, "conf": track.conf,
                    "bbox": track.bbox, "bc": curr,
                    "line_id": f"{f1}->{f2}", "frame_idx": frame_idx, "t": t,
                    "extra": {"dt_s": round(dt, 2)}}
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

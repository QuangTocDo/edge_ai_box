"""Loi di nguoc chieu (§4.1).

Cat line nguoc allowed_dir + duy tri nguoc >= N frames (hoac X px).
"""
from ..geometry import allowed_vec, crossing_sign, dot
from .base import BaseRule, cooldown_ok


class WrongWayRule(BaseRule):
    """Cat line nguoc allowed_dir + duy tri nguoc >= N frames (hoac X px)."""

    TYPE = "wrong_way"
    PARAMS = {"min_hits": 3, "min_reverse_frames": 5, "min_reverse_px": 60.0,
              "cooldown_s": 10.0, "min_speed_px": 1.0}

    def __init__(self, min_hits=3, min_reverse_frames=5, min_reverse_px=60.0,
                 cooldown_s=10.0, min_speed_px=1.0):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)
        self.min_reverse_frames = min_reverse_frames
        self.min_reverse_px = min_reverse_px
        self.min_speed_px = min_speed_px

    def update(self, track, lines, frame_idx, t):
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return None
        prev, curr = track.pts[-2], track.pts[-1]
        motion = (curr[0] - prev[0], curr[1] - prev[1])
        for ln in lines:
            if ln.get("role") == "divider":
                continue
            lid = ln["id"]
            avec = allowed_vec(ln["p1"], ln["p2"], ln.get("allowed_sign", 1))
            sign = crossing_sign(prev, curr, ln["p1"], ln["p2"])
            if sign != 0 and sign != ln.get("allowed_sign", 1):
                # vua cat nguoc -> bat dau dem (frame nay tinh la 1)
                track.reverse[lid] = [1, 0.0]
                continue
            st = track.reverse.get(lid)
            if st is None:
                continue
            if dot(motion[0], motion[1], avec[0], avec[1]) < 0:
                step = (motion[0] ** 2 + motion[1] ** 2) ** 0.5
                if step >= self.min_speed_px:
                    st[0] += 1
                    st[1] += step
            else:
                st[0], st[1] = 0, 0.0  # quay lai dung huong / dung yen -> reset
            if (st[0] >= self.min_reverse_frames or st[1] >= self.min_reverse_px) \
                    and cooldown_ok(track, self.TYPE, t):
                track.cooldowns[self.TYPE] = t + self.cooldown_s
                track.reverse.pop(lid, None)
                return {"type": self.TYPE, "track_id": track.tid,
                        "cls": track.cls, "conf": track.conf,
                        "bbox": track.bbox, "bc": curr, "line_id": lid,
                        "frame_idx": frame_idx, "t": t,
                        "extra": {"reverse_frames": st[0],
                                  "reverse_px": round(st[1], 1)}}
        return None

    def run(self, entry, track, frame_idx, t, wall_min=None,
            frame=None, signals=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay)."""
        return self.update(track, entry["lines"], frame_idx, t)

    def explain(self, track, t=None, lines=None, **ctx):
        """Ly do trang thai hien tai (khong doi state)."""
        if len(track.pts) < 2:
            return f"wrong_way tid={track.tid}: chua du 2 diem"
        if track.hits < self.min_hits:
            return (f"wrong_way tid={track.tid}: track moi "
                    f"(hits={track.hits}<{self.min_hits})")
        if track.reverse:
            lid, (c, px) = next(iter(track.reverse.items()))
            return (f"wrong_way tid={track.tid}: dang nguoc {c}/"
                    f"{self.min_reverse_frames}f "
                    f"({px:.0f}/{self.min_reverse_px:.0f}px) tren {lid}")
        if t is not None:
            left = track.cooldowns.get(self.TYPE, 0.0) - t
            if left > 0:
                return f"wrong_way tid={track.tid}: cooldown {left:.1f}s"
        return f"wrong_way tid={track.tid}: chua cat line nguoc"

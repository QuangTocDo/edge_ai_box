"""Rule Engine: wrong_way (§4.1) + no_uturn (§4.3) theo PROJECT_PLAN.md."""
from .geometry import allowed_vec, crossing_sign, dot


def _cooldown_ok(track, vtype, t):
    return track.cooldowns.get(vtype, 0.0) <= t


class WrongWayRule:
    """Cat line nguoc allowed_dir + duy tri nguoc >= N frames (hoac X px)."""

    TYPE = "wrong_way"

    def __init__(self, min_hits=3, min_reverse_frames=5, min_reverse_px=60.0,
                 cooldown_s=10.0, min_speed_px=1.0):
        self.min_hits = min_hits
        self.min_reverse_frames = min_reverse_frames
        self.min_reverse_px = min_reverse_px
        self.cooldown_s = cooldown_s
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
                    and _cooldown_ok(track, self.TYPE, t):
                track.cooldowns[self.TYPE] = t + self.cooldown_s
                track.reverse.pop(lid, None)
                return {"type": self.TYPE, "track_id": track.tid,
                        "cls": track.cls, "conf": track.conf,
                        "bbox": track.bbox, "bc": curr, "line_id": lid,
                        "frame_idx": frame_idx, "t": t,
                        "extra": {"reverse_frames": st[0],
                                  "reverse_px": round(st[1], 1)}}
        return None


class NoUTurnRule:
    """Sequence 2 line dung chieu + dao chieu van toc + cat medial divider."""

    TYPE = "no_uturn"

    def __init__(self, time_window_s=(2.0, 12.0), require_velocity_inversion=True,
                 require_medial=True, min_hits=3, cooldown_s=10.0):
        self.w0, self.w1 = time_window_s
        self.require_inversion = require_velocity_inversion
        self.require_medial = require_medial
        self.min_hits = min_hits
        self.cooldown_s = cooldown_s

    def update(self, track, lines, pairs, frame_idx, t):
        if len(track.pts) < 2 or track.hits < self.min_hits:
            return None
        prev, curr = track.pts[-2], track.pts[-1]
        second_now = set()  # line dung chieu vua cat frame nay
        for ln in lines:
            sign = crossing_sign(prev, curr, ln["p1"], ln["p2"])
            if sign == 0:
                continue
            if ln.get("role") == "divider":
                track.medial_cross_t = t
                continue
            if sign == ln.get("allowed_sign", 1):
                track.line_flags[ln["id"]] = (frame_idx, t, tuple(track.vel))
                second_now.add(ln["id"])
        # prune flag qua han
        for lid in [k for k, (_, ft, _) in track.line_flags.items()
                    if t - ft > self.w1]:
            del track.line_flags[lid]
        for pr in pairs:
            f1, f2 = pr["first"], pr["second"]
            if f2 not in second_now or f1 not in track.line_flags:
                continue
            _, t_entry, v_entry = track.line_flags[f1]
            _, _, v_exit = track.line_flags[f2]
            dt = t - t_entry
            if not (self.w0 <= dt <= self.w1):
                continue
            if self.require_inversion and \
                    dot(v_exit[0], v_exit[1], v_entry[0], v_entry[1]) >= 0:
                track.line_flags.pop(f1, None)  # nghi ID-switch -> huy
                continue
            if self.require_medial and not (
                    track.medial_cross_t is not None
                    and t_entry < track.medial_cross_t <= t):
                continue
            if not _cooldown_ok(track, self.TYPE, t):
                continue
            track.cooldowns[self.TYPE] = t + self.cooldown_s
            track.line_flags.pop(f1, None)
            return {"type": self.TYPE, "track_id": track.tid,
                    "cls": track.cls, "conf": track.conf,
                    "bbox": track.bbox, "bc": curr,
                    "line_id": f"{f1}->{f2}", "frame_idx": frame_idx, "t": t,
                    "extra": {"dt_s": round(dt, 2),
                              "velocity_inverted": dot(
                                  v_exit[0], v_exit[1],
                                  v_entry[0], v_entry[1]) < 0}}
        return None

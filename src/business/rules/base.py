"""Base class chung cho moi rule vi pham.

Moi rule con phai dinh nghia:
- TYPE: str — ten loai vi pham, khop key trong config (vd "wrong_way").
- PARAMS: dict — key param hop le + gia tri mac dinh.
- update(...): chay detect tren 1 track, tra ve event dict hoac None.
  (Chu y: moi rule tu chuyen tham so update rieng, khong khop chu ky base —
  pipeline luon goi qua run() nen day la co y, khong phai bug.)
- explain(...): 1 dong ly do trang thai hien tai (phuc vu debug live).
"""


def cooldown_ok(track, vtype, t):
    return track.cooldowns.get(vtype, 0.0) <= t


class BaseRule:
    TYPE = "base"
    PARAMS = {"min_hits": 3, "cooldown_s": 10.0}

    def __init__(self, min_hits=3, cooldown_s=10.0):
        self.min_hits = min_hits
        self.cooldown_s = cooldown_s

    def update(self, track, *args):
        raise NotImplementedError

    def run(self, entry, track, frame_idx, t, wall_min=None,
            frame=None, signals=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay thay vi
        re nhanh if/elif theo ten rule)."""
        raise NotImplementedError

    def explain(self, track, t=None, **ctx):
        """1 dong ly do: tai sao bao / tai sao chua bao. Khong doi state."""
        return f"{self.TYPE}: chua ro trang thai track={track.tid}"

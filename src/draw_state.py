"""May trang thai chuot cho tool ve (khong GUI, test headless duoc).

Van de goc: double-click de chon line luon ban ra 2 single-click truoc,
lam tool tu tao line rac + cuop selection. Giai phap:
- 2 clicks chi tao line sau khi yen CREATE_DELAY_S giay (poll moi frame).
- double-click huy ngay cac clicks trong DBL_WINDOW_S gan nhat roi moi chon.
"""
import math

from .line_config import add_directed, add_divider, add_pair, iter_all_lines

CREATE_DELAY_S = 0.35  # doi double-click di qua roi moi tao line
DBL_WINDOW_S = 0.5     # click don trong window nay truoc dblclk thi huy
NEAR_PX = 12


def nearest_line(lines, x, y):
    best, bd = None, NEAR_PX
    for ln in lines:
        ax, ay, bx, by = *ln["p1"], *ln["p2"]
        dx, dy = bx - ax, by - ay
        n = dx * dx + dy * dy
        t = 0.0 if n < 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / n))
        d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
        if d <= bd:
            best, bd = ln, d
    return best


class DrawState:
    """Nhan su kien chuot + thoi gian now (giay, tuy y fake khi test)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.mode = "directed"  # directed | divider | pair
        self.clicks = []        # [(x, y, t)]
        self.picks = []         # id lines cho pair
        self.selected = None    # line dict dang chon

    # -- API cho GUI --
    def set_mode(self, mode):
        self.mode = mode
        self.clicks.clear()
        self.picks.clear()

    def on_down(self, x, y, now):
        """Tra ve action (kind, payload) de GUI hien thi/log."""
        if self.mode == "pair":
            ln = nearest_line(list(iter_all_lines(self.cfg)), x, y)
            if ln is None:
                return ("pair_miss", None)
            self.picks.append(ln["id"])
            if len(self.picks) == 3:
                try:
                    pr = add_pair(self.cfg, *self.picks)
                    self.picks.clear()
                    return ("pair_created", pr)
                except ValueError as e:
                    self.picks.clear()
                    return ("pair_error", str(e))
            return ("pair_pick", (len(self.picks), ln["id"]))
        self.clicks.append((x, y, now))
        return ("click", (x, y))

    def on_dblclk(self, x, y, now):
        """Huy clicks vua nhan (cua thao tac double) roi chon line."""
        self.clicks = [c for c in self.clicks if now - c[2] > DBL_WINDOW_S]
        self.picks.clear()
        self.selected = nearest_line(list(iter_all_lines(self.cfg)), x, y)
        return ("selected", self.selected["id"] if self.selected else None)

    def poll(self, now):
        """Goi moi frame: du 2 clicks + qua delay -> tao line."""
        if self.mode == "pair" or len(self.clicks) < 2:
            return (None, None)
        (x1, y1, _), (x2, y2, t2) = self.clicks[0], self.clicks[1]
        if now - t2 < CREATE_DELAY_S:
            return (None, None)
        try:
            ln = add_directed(self.cfg, (x1, y1), (x2, y2)) \
                if self.mode == "directed" \
                else add_divider(self.cfg, (x1, y1), (x2, y2))
            self.selected = ln
            self.clicks.clear()
            return ("line_created", ln)
        except ValueError as e:
            self.clicks.clear()
            return ("line_error", str(e))

    def cancel(self):
        self.clicks.clear()
        self.picks.clear()

"""May trang thai cho cong cu ve (khong GUI, test headless duoc).

Cac cai tien kien truc:
- Chuan hoa su kien bang DrawResult (tuple 2 phan tu tuong thich nguoc, kem metadata).
- Quan ly tap trung bo nho dem cac diem dở dang (clicks, poly_pts, calib_pts, roi_drag).
- Ho tro target_polygon_id de gan line truc tiep vao polygon, tranh tao roi xoa o top-level.
- Bo sung undo_last_point() va is_busy() giup kiem soat thao tac de dang.
- Ho tro select_at() hop nhat cho line, signal box va polygon.
"""
from __future__ import annotations

import math
from typing import Any

from ..config.zones import (
    add_directed,
    add_divider,
    add_nested_line,
    add_pair,
    find_polygon,
    get_polygons,
    iter_all_lines,
    next_id,
)
from ..utils.constants import EPS
from ..utils.geometry import point_in_polygon

CREATE_DELAY_S = 0.35  # doi double-click di qua roi moi tao line
DBL_WINDOW_S = 0.5     # click don trong window nay truoc dblclk thi huy
NEAR_PX = 20
MIN_LINE_PX = 10.0     # 2 diem gan nhau hon -> double-click cham, bo qua


class DrawResult(tuple):
    """Ket qua tra ve tu thao tac ve.

    Ke thua tuple 2 phan tu (kind, payload) de tuong thich 100% voi cu phap
    unpacking cu: `kind, payload = st.on_down(...)` hoac `st.poll(...)`.
    Dong thoi cung cap cac thuoc tinh: .kind, .payload, .message, .is_dirty.
    """

    kind: str | None
    payload: Any
    message: str
    is_dirty: bool

    def __new__(
        cls,
        kind: str | None,
        payload: Any = None,
        message: str = "",
        is_dirty: bool = False,
    ):
        obj = super().__new__(cls, (kind, payload))
        obj.kind = kind
        obj.payload = payload
        obj.message = message
        obj.is_dirty = is_dirty
        return obj

    def __repr__(self) -> str:
        return f"DrawResult(kind={self.kind!r}, payload={self.payload!r}, dirty={self.is_dirty})"


def nearest_line(lines: list[dict] | tuple[dict, ...], x: float, y: float) -> dict | None:
    """Tim line gan toa do (x, y) nhat trong pham vi NEAR_PX."""
    best, bd = None, float(NEAR_PX)
    for ln in lines:
        ax, ay = ln["p1"]
        bx, by = ln["p2"]
        dx, dy = bx - ax, by - ay
        n = dx * dx + dy * dy
        t = 0.0 if n < EPS else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / n))
        d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
        if d <= bd:
            best, bd = ln, d
    return best


def resolve_enter_action(wizard: dict | None, tool_mode: str) -> str:
    """Enter re nhanh nao, khong can GUI. Tra ve:
    'wizard_close' (flow gop phim 1) | 'standalone_close' (polygon le phim 4)
    | 'none' (khong lam gi)."""
    if wizard is not None and wizard.get("poly_id") is None:
        return "wizard_close"
    if tool_mode == "polygon":
        return "standalone_close"
    return "none"


def mode_label(wizard: dict | None, tool_mode: str, draw_mode: str | None) -> str:
    """Nhan hien thi tren status, phan biet 2 flow polygon."""
    if wizard is not None:
        stage = "ve dinh" if wizard.get("poly_id") is None else "ve 2 lines"
        return f"ZONE-FLOW ({stage})"
    if tool_mode == "polygon":
        return "POLYGON-LE"
    if tool_mode == "roi":
        return "ROI-DEN"
    if tool_mode == "calib":
        return "HIEU-CHUAN-H"
    return (draw_mode or "line").upper()


class DrawState:
    """May trang thai chuot va bo dem ve (khong GUI, headless)."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.mode: str = "directed"  # directed | divider | pair
        self.target_polygon_id: str | None = None

        # Bo dem cac thao tac dang thuc hien
        self.clicks: list[tuple[float, float, float]] = []  # [(x, y, t)] cho line
        self.picks: list[str] = []                          # [line_id] cho pair
        self.poly_pts: list[tuple[int, int]] = []           # [(x, y)] dinh polygon
        self.calib_pts: list[tuple[int, int]] = []          # [(x, y)] diem hieu chuan
        self.roi_drag: dict[str, tuple[int, int] | None] = {"p0": None, "p1": None}

        # Doi tuong dang duoc chon
        self.selected: dict | None = None          # line dict
        self.selected_poly: dict | None = None     # polygon dict
        self.selected_signal: dict | None = None   # signal dict

    # -- Quan ly che do va muc tieu --
    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.clicks.clear()
        self.picks.clear()

    def set_target_polygon(self, poly_id: str | None) -> None:
        """Thiet lap polygon dich de khi ve line se gan truc tiep vao day."""
        self.target_polygon_id = poly_id

    # -- Quan ly bo dem dinh polygon / calib --
    def add_poly_point(self, x: int | float, y: int | float) -> None:
        self.poly_pts.append((int(x), int(y)))

    def clear_poly_points(self) -> None:
        self.poly_pts.clear()

    def add_calib_point(self, x: int | float, y: int | float) -> None:
        self.calib_pts.append((int(x), int(y)))

    def clear_calib_points(self) -> None:
        self.calib_pts.clear()

    def undo_last_point(self) -> tuple[bool, str]:
        """Xoa diem gan nhat dang ve do (ho tro Backspace / Ctrl+Z)."""
        if self.poly_pts:
            pt = self.poly_pts.pop()
            return True, f"Da go dinh polygon {pt}"
        if self.calib_pts:
            pt = self.calib_pts.pop()
            return True, f"Da go diem hieu chuan {pt}"
        if self.clicks:
            pt = self.clicks.pop()
            return True, f"Da go diem click ({int(pt[0])}, {int(pt[1])})"
        return False, "Khong co diem nao dang ve de go"

    def is_busy(self) -> bool:
        """Kiem tra xem he thong co dang trong tien trinh ve do hay khong."""
        return bool(
            self.clicks
            or self.picks
            or self.poly_pts
            or self.calib_pts
            or self.roi_drag.get("p0") is not None
        )

    # -- Su kien chuot --
    def on_down(self, x: int | float, y: int | float, now: float) -> DrawResult:
        """Xu ly click chuot xuong: them diem hoac chon pair."""
        if self.mode == "pair":
            ln = nearest_line(list(iter_all_lines(self.cfg)), float(x), float(y))
            if ln is None:
                return DrawResult("pair_miss", None, "Click gan 1 line da ve (first->second)")
            self.picks.append(ln["id"])
            if len(self.picks) == 2:
                try:
                    pr = add_pair(self.cfg, *self.picks)
                    self.picks.clear()
                    return DrawResult("pair_created", pr, f"Da tao pair {pr}", is_dirty=True)
                except ValueError as e:
                    self.picks.clear()
                    return DrawResult("pair_error", str(e), f"Pair loi: {e}")
            return DrawResult("pair_pick", (len(self.picks), ln["id"]))

        self.clicks.append((float(x), float(y), float(now)))
        return DrawResult("click", (int(x), int(y)))

    def on_dblclk(self, x: int | float, y: int | float, now: float) -> DrawResult:
        """Huy cac click don vua nhan roi tim line gan nhat."""
        self.clicks = [c for c in self.clicks if now - c[2] > DBL_WINDOW_S]
        self.picks.clear()
        self.selected = nearest_line(list(iter_all_lines(self.cfg)), float(x), float(y))
        lid = self.selected["id"] if self.selected else None
        return DrawResult("selected", lid, message=f"Da chon {lid}" if lid else "Khong co line gan do")

    def select_at(self, x: int | float, y: int | float, now: float) -> DrawResult:
        """Hop nhat double-click chon: line -> signal box -> polygon."""
        self.clicks = [c for c in self.clicks if now - c[2] > DBL_WINDOW_S]
        self.picks.clear()

        # 1. Chon line
        ln = nearest_line(list(iter_all_lines(self.cfg)), float(x), float(y))
        if ln is not None:
            self.selected = ln
            self.selected_poly = None
            self.selected_signal = None
            return DrawResult("selected_line", ln, message=f"Da chon line {ln['id']}")

        # 2. Chon signal
        for s in self.cfg.get("signals", []):
            roi = s.get("roi")
            if roi and len(roi) == 4:
                x1, y1, x2, y2 = [int(v) for v in roi]
                xa, xb = sorted([x1, x2])
                ya, yb = sorted([y1, y2])
                if (xa - 5) <= x <= (xb + 5) and (ya - 5) <= y <= (yb + 5):
                    self.selected = None
                    self.selected_poly = None
                    self.selected_signal = s
                    return DrawResult("selected_signal", s, message=f"Da chon signal {s.get('id')}")

        # 3. Chon polygon
        for p in get_polygons(self.cfg):
            if point_in_polygon((float(x), float(y)), p.get("polygon", [])):
                self.selected = None
                self.selected_poly = p
                self.selected_signal = None
                return DrawResult("selected_poly", p, message=f"Da chon polygon {p.get('id')}")

        self.selected = None
        self.selected_poly = None
        self.selected_signal = None
        return DrawResult("selected_none", None, message="Khong co line/signal/polygon gan do")

    def poll(self, now: float) -> DrawResult:
        """Kiem tra dinh ky moi frame: du 2 clicks + qua delay -> tao line."""
        if self.mode == "pair" or len(self.clicks) < 2:
            return DrawResult(None, None)

        (x1, y1, _), (x2, y2, t2) = self.clicks[0], self.clicks[1]
        if now - t2 < CREATE_DELAY_S:
            return DrawResult(None, None)

        if math.hypot(x2 - x1, y2 - y1) < MIN_LINE_PX:
            self.clicks.clear()
            return DrawResult("ignored_short", None)

        try:
            # Neu co polygon dich da chon -> them truc tiep vao polygon, tranh tao roi xoa
            if self.target_polygon_id is not None and find_polygon(self.cfg, self.target_polygon_id):
                lid = next_id(self.cfg)
                ln = {
                    "id": lid,
                    "p1": [int(x1), int(y1)],
                    "p2": [int(x2), int(y2)],
                }
                if self.mode == "directed":
                    ln["allowed_sign"] = 1
                else:
                    ln["role"] = "divider"
                add_nested_line(self.cfg, self.target_polygon_id, ln)
            else:
                ln = (
                    add_directed(self.cfg, (x1, y1), (x2, y2))
                    if self.mode == "directed"
                    else add_divider(self.cfg, (x1, y1), (x2, y2))
                )

            self.selected = ln
            self.clicks.clear()
            return DrawResult("line_created", ln, f"Da ve {ln['id']} ({self.mode})", is_dirty=True)
        except ValueError as e:
            self.clicks.clear()
            return DrawResult("line_error", str(e), f"Loi tao line: {e}")

    def cancel(self) -> None:
        """Huy toan bo thao tac ve dở dang cua tat ca cac che do."""
        self.clicks.clear()
        self.picks.clear()
        self.poly_pts.clear()
        self.calib_pts.clear()
        self.roi_drag = {"p0": None, "p1": None}

"""Hinh hoc dung chung cho Rule Engine (PROJECT_PLAN.md muc 4).

- Diem moc chuan: Bottom-Center (x_mid, y_max), KHONG dung centroid.
- Cat line: Segment Intersection doan dich chuyen x_prev->x_curr vs line
  (chong xuyen ham khi xe chay nhanh), kem huong cat de biet thuan/nguoc.
"""
import math


def bottom_center(x1, y1, x2, y2):
    """Diem tiep xuc banh xe/chan voi mat duong."""
    return ((x1 + x2) / 2.0, float(y2))


def _cross(ax, ay, bx, by):
    return ax * by - ay * bx


def crossing_sign(prev, curr, p1, p2):
    """Huong cat cua doan prev->curr qua line p1->p2.

    Tra ve +1 / -1 neu 2 doan giao nhau, 0 neu khong.
    Dau duong/ am xac dinh boi cross(line_vec, motion).
    """
    rx, ry = curr[0] - prev[0], curr[1] - prev[1]
    sx, sy = p2[0] - p1[0], p2[1] - p1[1]
    denom = _cross(rx, ry, sx, sy)
    if abs(denom) < 1e-9:
        return 0  # song song
    qpx, qpy = p1[0] - prev[0], p1[1] - prev[1]
    t = _cross(qpx, qpy, sx, sy) / denom
    u = _cross(qpx, qpy, rx, ry) / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        # denom = cross(motion, line) = -cross(line, motion)
        return -1 if denom > 0 else 1
    return 0


def allowed_vec(p1, p2, allowed_sign):
    """Vector don vi huong di cho phep cua directed line.

    allowed_sign=+1 <-> normal n=(-ly,lx)/|l|; -1 thi dao lai.
    Cung khong gian toan cuc voi crossing_sign nen nhat quan.
    """
    lx, ly = p2[0] - p1[0], p2[1] - p1[1]
    n = math.hypot(lx, ly)
    if n < 1e-9:
        return (0.0, 0.0)
    nx, ny = -ly / n, lx / n
    if allowed_sign < 0:
        nx, ny = -nx, -ny
    return (nx, ny)


def dot(ax, ay, bx, by):
    return ax * bx + ay * by


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _on_segment(px, py, ax, ay, bx, by):
    return (min(ax, bx) - 1e-9 <= px <= max(ax, bx) + 1e-9
            and min(ay, by) - 1e-9 <= py <= max(ay, by) + 1e-9
            and abs(_cross(bx - ax, by - ay, px - ax, py - ay)) < 1e-9)


def point_in_polygon(pt, poly):
    """True neu diem trong polygon (tinh ca bien). Ray-casting truc X+."""
    x, y = pt
    if not poly:
        return False
    n = len(poly)
    if n < 3:
        return False
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if _on_segment(x, y, ax, ay, bx, by):
            return True
    inside = False
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        if (ay > y) != (by > y):
            xin = ax + (bx - ax) * (y - ay) / (by - ay)
            if x < xin:
                inside = not inside
    return inside


def containing_polygons(pt, polygons):
    """Cac polygon chua diem (theo Bottom-Center)."""
    return [p for p in polygons
            if point_in_polygon(pt, p.get("polygon", []))]


def polygon_valid(poly):
    """>=3 dinh + dien tich > 0 (loai tu cat don gian)."""
    if len(poly) < 3:
        return False
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
               - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly)))
    return abs(area) > 1e-9


def parse_window(s):
    """'18:00-05:00' -> (1080, 300) phut. Cho phep qua dem (start > end)."""
    try:
        a, b = s.split("-")
        def to_min(x):
            h, m = x.strip().split(":")
            return int(h) * 60 + int(m)
        s0, e0 = to_min(a), to_min(b)
        if not (0 <= s0 < 1440 and 0 <= e0 < 1440):
            raise ValueError
        return (s0, e0)
    except Exception:
        raise ValueError(f"Khung gio sai format HH:MM-HH:MM: {s!r}")


def in_active_hours(now_min, windows):
    """now_min: so phut tu 0h. windows: list (start, end)."""
    for s, e in windows:
        if s <= e:
            if s <= now_min <= e:
                return True
        elif now_min >= s or now_min <= e:  # qua dem
            return True
    return False


def now_minutes(tzname="Asia/Ho_Chi_Minh"):
    """Phut hien tai theo gio edge. Fallback UTC+7 neu thieu tzdata."""
    from datetime import datetime, timedelta, timezone
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tzname)
    except Exception:
        tz = timezone(timedelta(hours=7))
    now = datetime.now(tz)
    return now.hour * 60 + now.minute

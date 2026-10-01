"""Hinh hoc dung chung cho Rule Engine (PROJECT_PLAN.md muc 4).

- Diem moc chuan: Bottom-Center (x_mid, y_max), KHONG dung centroid.
- Cat line: Segment Intersection doan dich chuyen x_prev->x_curr vs line
  (chong xuyen ham khi xe chay nhanh), kem huong cat de biet thuan/nguoc.
"""
import math

from .constants import EPS


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
    if abs(denom) < EPS:
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
    if n < EPS:
        return (0.0, 0.0)
    nx, ny = -ly / n, lx / n
    if allowed_sign < 0:
        nx, ny = -nx, -ny
    return (nx, ny)


def dot(ax, ay, bx, by):
    return ax * bx + ay * by


COMPASS8 = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def heading_deg(dx, dy):
    """Goc huong di chuyen (do) tu vector (dx, dy) pixel.

    Quy uoc NOI BO (khong phai la ban): 0 = len tren anh, tang theo
    chieu kim dong ho (90 = sang phai, 180 = xuong duoi, 270 = sang trai).
    Tra ve None neu vector ~0 (dung yen -> khong co huong).
    """
    if math.hypot(dx, dy) < EPS:
        return None
    return (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0


def compass8(deg):
    """0-360 do -> 1 trong 8 nhan N/NE/E/SE/S/SW/W/NW. None -> None."""
    if deg is None:
        return None
    return COMPASS8[int((deg + 22.5) // 45) % 8]


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _on_segment(px, py, ax, ay, bx, by):
    return (min(ax, bx) - EPS <= px <= max(ax, bx) + EPS
            and min(ay, by) - EPS <= py <= max(ay, by) + EPS
            and abs(_cross(bx - ax, by - ay, px - ax, py - ay)) < EPS)


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


def distance_point_to_segment(p, a, b):
    """Khoang cach tu diem p den doan thang a-b."""
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < EPS:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    proj_x = ax + t * dx
    proj_y = ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def line_near_or_in_polygon(p1, p2, poly, max_dist=25.0):
    """Kiem tra xem line (p1, p2) co nam trong, cat, hoac nam sat polygon (<= max_dist)."""
    if not poly or len(poly) < 3:
        return False
    pm = ((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
    if point_in_polygon(pm, poly) or point_in_polygon(p1, poly) or point_in_polygon(p2, poly):
        return True
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        if crossing_sign(p1, p2, a, b) != 0:
            return True
    for pt in (pm, p1, p2):
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            if distance_point_to_segment(pt, a, b) <= max_dist:
                return True
    return False


def polygon_valid(poly):
    """>=3 dinh + dien tich > 0 (loai tu cat don gian)."""
    if len(poly) < 3:
        return False
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1]
               - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly)))
    return abs(area) > EPS


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


def seg_intersect(p1, p2, p3, p4):
    """Kiem tra 2 doan thang p1->p2 va p3->p4 co cat nhau hay khong."""
    return crossing_sign(p1, p2, p3, p4) != 0


dist_pt_seg = distance_point_to_segment

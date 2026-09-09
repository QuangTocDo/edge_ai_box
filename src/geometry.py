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

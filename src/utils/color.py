"""Mau xe dominant tu crop bbox (HSV, khong model).

Kien truc loc chong lop (re, edge-friendly):
  Lop 0: crop qua nho/rong -> 'unknown' ngay.
  Lop 1: chi dem pixel trong ELLIPSE noi tiep (tam bbox, truc 60%) de loai
         4 goc nen duong khi xe chay xeo (nhe den nang).
  Lop 2: mask nhieu - bo pixel V thap (lop/gam/bong) va S thap (xam) khoi
         histogram hue; trang/bac/den quyet bang TI LE pixel, khong mean.
  Lop 3: cong trung thuc - peak yeu (conf < 0.5) -> 'unknown', khong ep mau.
  Lop 4 (rieng): grabcut_foreground() cho xe xeo nang + nghi ngo.
"""
import cv2
import numpy as np

BASIC_COLORS_VN = ["do", "cam", "vang", "xanh la", "xanh duong",
                   "tim", "trang", "bac", "den"]

MIN_SIDE_PX = 32  # crop nho hon thi histogram khong dang tin (vd 23px -> unknown)
MIN_CONF = 0.5
# Nguong V/S de loai nhieu (lop, gam, bong do, kinh phan chieu mo)
DARK_V_THRESH = 40
GRAY_S_THRESH = 45  # can bang: 30 nhan nham xe xam phan chieu xanh, 60 an mat xanh that
# Ti le pixel de ket luan trang/bac/den
WHITE_V_THRESH = 180
WHITE_RATIO = 0.6
BLACK_V_THRESH = 65
BLACK_RATIO = 0.6


def _ellipse_mask(h, w, axis_ratio=0.6):
    """Mask ellipse noi tiep: tam bbox, truc = axis_ratio * w/h."""
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    rx, ry = (w / 2.0) * axis_ratio, (h / 2.0) * axis_ratio
    rx = max(rx, 1.0)
    ry = max(ry, 1.0)
    return ((xx - cx) ** 2 / rx ** 2 + (yy - cy) ** 2 / ry ** 2) <= 1.0


def _to_hsv(bgr_img):
    try:
        return cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
    except cv2.error:
        return None


# Bien do am sac cho phep truoc khi can thiep (tranh tay mau xe that)
CAST_THRESH = 25.0
# Kep gain de chi nhuộm nhe, khong bao gio lat hue (0.75~1.33)
GAIN_LO, GAIN_HI = 0.75, 1.33


def frame_gains(frame, p=6):
    """Uoc luong gain can bang trang tu FULL FRAME (chu yeu nen duong xam).
    Tra ve gains (3,) hoac None neu khong can thiet / khong tinh duoc.
    KHONG bao gio goi tren crop xe (xe ap dao mau lam lech uoc luong)."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    try:
        h, w = frame.shape[:2]
        small = frame
        if max(h, w) > 320:
            scale = 320.0 / max(h, w)
            small = cv2.resize(frame, (int(w * scale), int(h * scale)))
        img = small.reshape(-1, 3).astype(np.float64)
        means = np.array([np.power(np.mean(np.power(img[:, c], p)), 1.0 / p)
                          for c in range(3)])
        means = np.maximum(means, 1e-6)
        if abs(float(means[0]) - float(means[2])) <= CAST_THRESH:
            return None
        gray = float(means.mean())
        gains = np.clip(gray / means, GAIN_LO, GAIN_HI)
        if np.allclose(gains, 1.0, atol=0.05):
            return None
        return gains
    except (ValueError, cv2.error):
        return None


def white_balance(bgr_img, gains=None, p=6):
    """Can bang trang bang gains cho san (tu frame_gains) hoac tu uoc luong
    noi bo khi thieu. Gain luon bi kep de khong lat hue."""
    if bgr_img is None or bgr_img.size == 0:
        return bgr_img
    try:
        if gains is None:
            return bgr_img
        gains = np.clip(np.asarray(gains, dtype=np.float64), GAIN_LO, GAIN_HI)
        out = np.clip(bgr_img.astype(np.float64) * gains.reshape(1, 1, 3),
                      0, 255).astype(np.uint8)
        return out
    except (ValueError, OverflowError):
        return bgr_img


def needs_white_balance(bgr_img):
    """Giu de tuong thich nguoc (khong dung trong pipeline moi)."""
    return False


def dominant_color(bgr_img, min_conf=MIN_CONF, gains=None):
    """Tra ve (color, confidence). color trong BASIC_COLORS_VN + 'unknown'.
    gains: tu frame_gains(full_frame) - can bang truoc khi dem hue."""
    if bgr_img is None or bgr_img.size == 0:
        return "unknown", 0.0
    h, w = bgr_img.shape[:2]
    if h < MIN_SIDE_PX or w < MIN_SIDE_PX:
        return "unknown", 0.0
    bgr_img = white_balance(bgr_img, gains)
    hsv = _to_hsv(bgr_img)
    if hsv is None:
        return "unknown", 0.0

    # Lop 1: ellipse trung tam 60% (chong nen duong khi xe xeo)
    keep = _ellipse_mask(h, w)
    if int(keep.sum()) < 50:
        return "unknown", 0.0
    s = hsv[:, :, 1].astype(float)[keep]
    v = hsv[:, :, 2].astype(float)[keep]
    hue = hsv[:, :, 0].astype(float)[keep]
    n = float(s.size)
    if n <= 0:
        return "unknown", 0.0

    # Lop 2a: trang/bac/den bang ti le pixel (S thap)
    gray = s < GRAY_S_THRESH
    n_gray = float(gray.sum())
    if n_gray / n > 0.5:
        v_gray = v[gray]
        white_ratio = float((v_gray > WHITE_V_THRESH).sum()) / max(n_gray, 1.0)
        black_ratio = float((v_gray < BLACK_V_THRESH).sum()) / max(n_gray, 1.0)
        if white_ratio >= WHITE_RATIO:
            return "trang", round(min(1.0, 0.5 + white_ratio * 0.5), 2)
        if black_ratio >= BLACK_RATIO:
            return "den", round(min(1.0, 0.5 + black_ratio * 0.5), 2)
        return "bac", round(0.5 + (n_gray / n - 0.5), 2)

    # Lop 2b: mask pixel toi (lop/gam/bong) truoc khi dem hue.
    # Trong so theo S: kinh phan chieu/kinh xe (S thap) bi giam quyen,
    # son xe dam dac (S cao) ap dao. Do quan 2 dau hue 0/180 duoc gop.
    lit = v >= DARK_V_THRESH
    hue_lit = hue[lit]
    s_lit = (s[lit] / 255.0) if hue_lit.size else np.array([])
    if hue_lit.size < 50:
        return "unknown", 0.0
    hist, _ = np.histogram(hue_lit, bins=180, range=(0, 180),
                           weights=s_lit)
    total = float(hist.sum())
    if total <= 0:
        return "unknown", 0.0
    red_score = float(hist[0:10].sum() + hist[170:180].sum())
    peak = int(hist.argmax())
    peak_score = float(hist[peak])
    if red_score >= peak_score:
        peak, peak_score = 5, red_score
    # Do tap trung co trong so S (uniform ~0.006)
    conf = round(min(1.0, peak_score / total * 6.0), 2)

    # Lop 3: cong trung thuc - peak yeu thi unknown, khong ep
    if conf < min_conf:
        return "unknown", conf
    if peak < 10 or peak >= 170:
        return "do", conf
    if peak < 25:
        return "cam", conf
    if peak < 35:
        return "vang", conf
    if peak < 85:
        return "xanh la", conf
    if peak < 130:
        return "xanh duong", conf
    return "tim", conf


def needs_grabcut(bbox, color, conf):
    """Co nen chay GrabCut xac nhan? Khi: mau unknown/yeu VA bbox det/xeo
    (ti le w/h lech xa 1 - dau hieu xe ngang)."""
    try:
        w = float(bbox[2]) - float(bbox[0])
        h = float(bbox[3]) - float(bbox[1])
    except (TypeError, IndexError, ValueError):
        return False
    if w <= 0 or h <= 0:
        return False
    ratio = max(w, h) / min(w, h)
    weak = (color == "unknown") or (conf < MIN_CONF)
    return bool(weak and ratio >= 1.8)


def grabcut_foreground(bgr_img, iters=2):
    """ tach foreground (xe) khoi background (duong) bang GrabCut.
    Tra ve anh chi giu foreground (nen = den), hoac None khi loi.
    Nang (~20-50ms) -> chi goi khi needs_grabcut() True."""
    if bgr_img is None or bgr_img.size == 0:
        return None
    h, w = bgr_img.shape[:2]
    if h < MIN_SIDE_PX or w < MIN_SIDE_PX:
        return None
    try:
        mask = np.zeros((h, w), np.uint8)
        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        m = min(w, h)
        rect = (m // 10, m // 10, w - m // 5, h - m // 5)
        cv2.grabCut(bgr_img, mask, rect, bgd, fgd, iters,
                    cv2.GC_INIT_WITH_RECT)
        fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
                      255, 0).astype(np.uint8)
        if int(fg.sum() / 255) < 50:
            return None
        out = bgr_img.copy()
        out[fg == 0] = (0, 0, 0)
        return out
    except cv2.error:
        return None


def dominant_color_robust(bgr_img, bbox=None, gains=None):
    """Pipeline day du: mau thuong (co gains tu full frame) -> neu yeu +
    bbox xeo thi GrabCut xac nhan. Tra ve (color, confidence, method)."""
    color, conf = dominant_color(bgr_img, gains=gains)
    if bbox is not None and needs_grabcut(bbox, color, conf):
        fg = grabcut_foreground(bgr_img)
        if fg is not None:
            color2, conf2 = dominant_color(fg, gains=gains)
            if color2 != "unknown" and conf2 >= conf:
                return color2, conf2, "grabcut"
    return color, conf, "hsv"

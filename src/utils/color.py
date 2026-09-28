"""Mau xe dominant tu crop bbox su dung K-Means Clustering trong khong gian CIE Lab.

Giai phap 3 (Top-2 Dominant Colors):
  - Khong phu thuoc vao ellipse tam hep (tranh bi lech khi dính vung nho nhu tem dan, noc, kinh lay troi).
  - Lay mau tren toan bo dien tich xe (loai bo le 5-7% tranh background mat duong).
  - Phan cum K-Means (K=3) trong khong gian mau dong nhat CIE Lab (khoang cach Euclidean tuong thich cam nhan Delta E).
  - Xac dinh Top-2 Dominant Colors: Mau chu dao (than xe) + Mau thu hai (noc xe, tem dan, tem phan quang, ...).
  - Tuong thich hoan toan voi ObjectStore, SQLite va Cyber Dashboard UI.
"""
import cv2
import numpy as np

BASIC_COLORS_VN = ["do", "cam", "vang", "xanh la", "xanh duong",
                   "tim", "trang", "bac", "den", "nau"]

MIN_SIDE_PX = 16   # Cho phep nhan dien ca crop xe may goc xa (19-28px)
MIN_AREA_PX = 120  # Dien tich toi thieu h * w de dam bao du pixel phan cum
MIN_CONF = 0.5

# Nguong kiem tra am sac (Color cast) de can bang trang tu full frame
CAST_THRESH = 25.0
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
    if bgr_img is None or getattr(bgr_img, "size", 0) == 0 or gains is None:
        return bgr_img
    try:
        gains = np.clip(np.asarray(gains, dtype=np.float64), GAIN_LO, GAIN_HI)
        out = np.clip(bgr_img.astype(np.float64) * gains.reshape(1, 1, 3),
                      0, 255).astype(np.uint8)
        return out
    except (ValueError, OverflowError):
        return bgr_img


def needs_white_balance(bgr_img):
    """Giu de tuong thich nguoc (khong dung trong pipeline moi)."""
    return False


def classify_bgr_color(bgr):
    """Phan loai 1 pixel BGR (hoac centroid BGR tu K-Means) thanh nhan mau tieng Viet
    thuoc BASIC_COLORS_VN hoac 'unknown'.
    Ket hop ca CIE Lab (do sang L) va HSV (sac do H, do bao hoa S, do sang V)."""
    try:
        bgr_arr = np.uint8([[bgr]])
        hsv = cv2.cvtColor(bgr_arr, cv2.COLOR_BGR2HSV)[0, 0]
        lab = cv2.cvtColor(bgr_arr, cv2.COLOR_BGR2Lab)[0, 0]
    except Exception:
        return "unknown"

    b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])
    l_val = int(lab[0])

    # 1. Den (Black): V thap hoac L thap
    if v <= 48 or l_val <= 42:
        return "den"

    # 2. Mau Do (Red):
    # Xe mau do ngoai troi thuong bi giam do bao hoa S (S chi khoang 18-45)
    # do phan xa anh sang troi va bui duong, va Hue bi lech ve phia Burgundy/Crimson (h >= 150 hoac h < 11).
    # Mat khac, xe bac/xam phan xa troi lam B >= R, nen chi co xe DO moi co (r > g + 6 hoac r > b + 4).
    # Khong xet sang dai Cam (h >= 11).
    is_red = (h < 11 or h >= 150) and s >= 18 and (r > g + 6 or r > b + 4)
    if is_red:
        return "do"

    # 3. Mau vo sac: Trang / Bac (Gray/Silver) khi do bao hoa S thap
    # Xe bac phan xa troi xanh co the co S den 42-45 va Hue xanh duong.
    # Nguong S <= 45 cho cac mau khong phai do giup chong nhan nham xe bac thanh xanh duong!
    if s <= 45:
        if v >= 185 or l_val >= 190:
            return "trang"
        return "bac"

    # 4. Mau nau (Brown): S dam nhung V thap trong khoang cam/vang dam
    if (10 <= h < 24) and (48 < v < 115) and (s > 45):
        return "nau"

    # 5. Cac nhan mau sac thai dua tren Hue (0-179 trong OpenCV)
    if h < 25:
        return "cam"
    if h < 36:
        return "vang"
    if h < 85:
        return "xanh la"
    if h < 132:
        return "xanh duong"
    if h < 150:
        return "tim" if s > 50 else "bac"

    return "unknown"


def cluster_colors_kmeans(bgr_img, k=3, max_samples=1500, margin_ratio=0.06):
    """Phan cum cac pixel trong vung than xe bang K-Means trong khong gian CIE Lab.
    Loai bo bien 5-7% de tranh mat duong, giu tron ven than xe.
    Tra ve danh sach cac cluster da sap xep theo ty le dien tich giam dan:
      [{'color': str, 'weight': float, 'bgr': [B, G, R], 'count': int}, ...]
    """
    if bgr_img is None or getattr(bgr_img, "size", 0) == 0:
        return []
    h, w = bgr_img.shape[:2]
    if h < MIN_SIDE_PX or w < MIN_SIDE_PX or (h * w < MIN_AREA_PX):
        return []

    # Loai bo vien mat duong ngoai bien (khoang 5-6%)
    m_y = max(1, int(h * margin_ratio))
    m_x = max(1, int(w * margin_ratio))
    crop_roi = bgr_img[m_y:h - m_y, m_x:w - m_x]
    if crop_roi.size == 0:
        crop_roi = bgr_img

    pixels_bgr = crop_roi.reshape(-1, 3)
    if len(pixels_bgr) < 15:
        return []

    # Subsample neu so luong pixel lon de thoi gian thuc thi < 1ms
    n_pix = len(pixels_bgr)
    if n_pix > max_samples:
        step = max(1, n_pix // max_samples)
        pixels_bgr = pixels_bgr[::step][:max_samples]

    # Chuyen doi sang CIE Lab (khoang cach Euclidean tuong dong Delta E cua mat nguoi)
    try:
        pixels_lab = cv2.cvtColor(pixels_bgr.reshape(-1, 1, 3), cv2.COLOR_BGR2Lab).reshape(-1, 3)
    except cv2.error:
        return []

    data = np.float32(pixels_lab)
    actual_k = min(k, len(data))
    if actual_k <= 1:
        mean_bgr = np.mean(pixels_bgr, axis=0).astype(int)
        cname = classify_bgr_color(mean_bgr)
        return [{"color": cname, "weight": 1.0, "bgr": mean_bgr.tolist(), "count": len(data)}]

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 1.0)
    flags = cv2.KMEANS_PP_CENTERS
    try:
        _, labels, centers = cv2.kmeans(data, actual_k, None, criteria, attempts=3, flags=flags)
    except cv2.error:
        return []

    labels = labels.flatten()
    total = len(labels)
    clusters = []

    for i in range(actual_k):
        cnt = int(np.sum(labels == i))
        if cnt == 0:
            continue
        w_i = float(cnt) / total
        center_lab = np.uint8([[centers[i]]])
        center_bgr = cv2.cvtColor(center_lab, cv2.COLOR_Lab2BGR)[0, 0]
        color_name = classify_bgr_color(center_bgr)
        clusters.append({
            "color": color_name,
            "weight": round(w_i, 3),
            "bgr": [int(v) for v in center_bgr],
            "count": cnt,
        })

    clusters.sort(key=lambda c: c["weight"], reverse=True)
    return clusters


def dominant_colors_top2(bgr_img, k=3, gains=None):
    """Trich xuat Top-2 mau chu dao (Dominant & Secondary) bang K-Means Clustering.
    Tra ve dict:
      {
        "dominant": (color, conf),
        "secondary": (color, conf),
        "clusters": [...]
      }
    """
    if bgr_img is None or getattr(bgr_img, "size", 0) == 0:
        return {
            "dominant": ("unknown", 0.0),
            "secondary": ("unknown", 0.0),
            "clusters": [],
        }

    bgr_img = white_balance(bgr_img, gains)
    clusters = cluster_colors_kmeans(bgr_img, k=k)
    if not clusters:
        return {
            "dominant": ("unknown", 0.0),
            "secondary": ("unknown", 0.0),
            "clusters": [],
        }

    # Gop trong so cac cluster co cung ten mau (vd: do sang + do dam gop lai)
    color_weights = {}
    for c in clusters:
        name = c["color"]
        color_weights[name] = color_weights.get(name, 0.0) + c["weight"]

    sorted_colors = sorted(color_weights.items(), key=lambda x: x[1], reverse=True)
    dom_color, dom_weight = sorted_colors[0]

    # Xu ly truong hop gam xe / lop / bong mat duong / kinh xe (den/bac/trang) vs mau son than xe:
    # Neu cluster so 1 la trung tinh nhung co mau son than xe ro rang (do, xanh, cam, vang...):
    # - Voi xanh duong: de bi phan xa troi xanh tren kinh/noc xe bac nen can ti le >= 28%.
    # - Voi do, cam, vang: chi can >= 18% da la mau dac trung cua xe.
    neutral_total = sum(w for c, w in color_weights.items() if c in ("den", "bac", "trang"))
    chromatics = [(c, w) for c, w in sorted_colors if c not in ("den", "bac", "trang")]
    if dom_color in ("den", "bac", "trang") and chromatics:
        c_name, c_weight = chromatics[0]
        min_thresh = 0.28 if c_name == "xanh duong" else 0.18
        if c_weight >= min_thresh and neutral_total < 0.82:
            dom_color, dom_weight = c_name, c_weight
            rem_colors = [(c, w) for c, w in sorted_colors if c != dom_color]
            sec_color, sec_weight = rem_colors[0] if rem_colors else ("unknown", 0.0)
        else:
            sec_color, sec_weight = sorted_colors[1] if len(sorted_colors) > 1 else ("unknown", 0.0)
    else:
        sec_color, sec_weight = sorted_colors[1] if len(sorted_colors) > 1 else ("unknown", 0.0)

    dom_conf = round(min(1.0, dom_weight * 1.4), 2)
    sec_conf = round(min(1.0, sec_weight * 1.4), 2) if sec_weight >= 0.18 else 0.0
    if sec_conf == 0.0 or sec_color == dom_color:
        sec_color = "unknown"
        sec_conf = 0.0

    return {
        "dominant": (dom_color, dom_conf),
        "secondary": (sec_color, sec_conf),
        "clusters": clusters,
    }


def dominant_color(bgr_img, min_conf=MIN_CONF, gains=None):
    """Tra ve (color, confidence). color trong BASIC_COLORS_VN + 'unknown'.
    gains: tu frame_gains(full_frame) - can bang truoc khi phan cum."""
    res = dominant_colors_top2(bgr_img, k=3, gains=gains)
    col, conf = res["dominant"]
    if conf < min_conf:
        return "unknown", conf
    return col, conf


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
    """Tach foreground (xe) khoi background (duong) bang GrabCut.
    Tra ve anh chi giu foreground (nen = den), hoac None khi loi.
    Nang (~20-50ms) -> chi goi khi needs_grabcut() True."""
    if bgr_img is None or getattr(bgr_img, "size", 0) == 0:
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
    """Pipeline day du: mau thuong (co gains tu full frame) bang K-Means -> neu yeu +
    bbox xeo thi GrabCut xac nhan. Tra ve (color, confidence, method)."""
    color, conf = dominant_color(bgr_img, gains=gains)
    if bbox is not None and needs_grabcut(bbox, color, conf):
        fg = grabcut_foreground(bgr_img)
        if fg is not None:
            color2, conf2 = dominant_color(fg, gains=gains)
            if color2 != "unknown" and conf2 >= conf:
                return color2, conf2, "grabcut"
    return color, conf, "kmeans"

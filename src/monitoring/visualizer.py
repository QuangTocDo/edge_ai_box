"""Module Visualizer: render bounding box, lines, polygons, tin hieu den va thong tin vi pham.

Tach biet hoan toan khoi pipeline core giup headless chay nhe va de unit test.
"""
from typing import Any, Dict, List, Optional
import math
import cv2
import numpy as np
from ..utils.geometry import allowed_vec
from ..utils.vehicle import vehicle_name

ARROW_LEN = 60
# Modern high-tech palette (BGR format for OpenCV, matched with Dashboard)
# Emerald (#10b981), Vivid Cyan (#06b6d4), Indigo (#6366f1), Amber (#f59e0b),
# Violet (#8b5cf6), Teal (#14b8a6), Coral Rose (#f43f5e)
COLORS = [
    (212, 182, 6),    # Cyan (#06b6d4)
    (241, 102, 99),   # Indigo (#6366f1)
    (129, 185, 16),   # Emerald (#10b981)
    (11, 158, 245),   # Amber (#f59e0b)
    (246, 92, 139),   # Violet (#8b5cf6)
    (166, 184, 20),   # Teal (#14b8a6)
    (94, 63, 244),    # Coral (#f43f5e)
    (230, 200, 100),  # Sky blue
]


def cls_name(names, cls: int) -> str:
    """Tra ve ten class tu danh sach names hoac dict (tu dong gop day/night)."""
    if names is None:
        return f"class {cls}"
    if isinstance(names, dict):
        raw = names.get(cls)
    elif isinstance(names, (list, tuple)) and isinstance(cls, int) and 0 <= cls < len(names):
        raw = names[cls]
    else:
        raw = None

    if raw is None:
        return f"class {cls}"
    return vehicle_name(cls, {cls: raw})


def draw_overlay(img, tracks, lines, polygons, fps, counts, frame_idx,
                 names=None, t_video=0.0, signals=None,
                 pedestrians=None, gathering_zones=None):
    """Ve overlay toan dien len frame: den tin hieu, polygons, lines, tracks, pedestrians va HUD."""
    # 1. Ve tin hieu den giao thong (neu co)
    for sid, s in (signals.snapshot() if signals else {}).items():
        x1, y1, x2, y2 = s["roi"]
        col = {
            "RED": (0, 0, 255),
            "YELLOW": (0, 255, 255),
            "FLASHING_YELLOW": (0, 215, 255),
            "GREEN": (0, 255, 0),
        }.get(s["state"], (128, 128, 128))
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
        cv2.putText(img, f"{sid}:{s['state']}", (x1, max(0, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)

    # 2. Ve cac vung da giac (polygons) voi translucent alpha overlay
    poly_overlay = img.copy()
    valid_polys = []
    for p in polygons:
        pts = [(int(x), int(y)) for x, y in (p.get("polygon") or [])]
        if len(pts) >= 3:
            pid = p.get("id", "")
            rules = p.get("rules") or {}
            g_status = (gathering_zones or {}).get(pid)
            
            # Mau sac dong bo voi Dashboard
            if g_status and g_status.get("gathering"):
                is_violated = g_status.get("violated", False) or g_status.get("fired", False)
                col = (94, 63, 244) if is_violated else (11, 158, 245)
            elif "speeding" in rules or "homography" in p:
                col = (129, 185, 16)  # Emerald green
            elif "no_uturn" in rules:
                col = (246, 92, 139)  # Violet
            elif "no_entry_road" in rules or p.get("kind") == "banned":
                col = (94, 63, 244)   # Coral rose
            elif "no_parking" in rules:
                col = (241, 102, 99)   # Indigo
            elif "no_gathering" in rules:
                col = (166, 184, 20)   # Teal
            else:
                col = (212, 182, 6)    # Cyan

            pts_arr = np.array([pts], dtype=np.int32)
            cv2.fillPoly(poly_overlay, pts_arr, col)
            valid_polys.append((p, pts, pid, rules, g_status, col))

    if valid_polys:
        # Alpha blend tao hieu ung kinh mo hien dai
        cv2.addWeighted(poly_overlay, 0.15, img, 0.85, 0, img)

    # Ve duong vien sac net va nhan dan
    for p, pts, pid, rules, g_status, col in valid_polys:
        thick = 3 if (g_status and g_status.get("gathering")) else 2
        for a, b in zip(pts, pts[1:] + pts[:1]):
            cv2.line(img, a, b, col, thick, cv2.LINE_AA)



        # Nhan dan vung da giac
        poly_label = pid
        if g_status:
            cnt = g_status.get("count", 0)
            min_p = g_status.get("min_persons", 2)
            dw = g_status.get("dwell_s", 0.0)
            tdw = g_status.get("target_dwell_s", 3.0)
            if g_status.get("violated"):
                poly_label += f" [{cnt}/{min_p}p REC CLIP!]"
            elif cnt >= min_p:
                poly_label += f" [{cnt}/{min_p}p {dw:.1f}/{tdw:.0f}s!]"
            else:
                poly_label += f" [{cnt}/{min_p}p]"
        
        lx, ly = pts[0]
        (tw, th), _ = cv2.getTextSize(poly_label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        cv2.rectangle(img, (lx, max(0, ly - th - 8)), (lx + tw + 8, ly + 2), (15, 23, 42), -1)
        cv2.rectangle(img, (lx, max(0, ly - th - 8)), (lx + tw + 8, ly + 2), col, 1, cv2.LINE_AA)
        cv2.putText(img, poly_label, (lx + 4, max(0, ly - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    # 3. Ve cac vach ao (lines)
    for ln in lines:
        p1 = tuple(int(v) for v in ln["p1"])
        p2 = tuple(int(v) for v in ln["p2"])
        col = (255, 0, 0) if ln.get("role") == "divider" else (0, 255, 0)
        cv2.line(img, p1, p2, col, 2)
        if ln.get("role") != "divider":
            mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
            ax, ay = allowed_vec(ln["p1"], ln["p2"], ln.get("allowed_sign", 1))
            cv2.arrowedLine(img, (mx, my),
                            (int(mx + ax * ARROW_LEN), int(my + ay * ARROW_LEN)),
                            (0, 255, 255), 2)
        cv2.putText(img, ln["id"], (p1[0], p1[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)

    # 4. Ve cac xe dang track
    for tid, st in tracks.items():
        if st.bbox is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in st.bbox]
        cls = int(st.cls)
        color = COLORS[cls % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

        pts = [(int(x), int(y)) for x, y in st.pts]
        for a, b in zip(pts[:-1], pts[1:]):
            cv2.line(img, a, b, (255, 0, 255), 2)
        bc = pts[-1]
        cv2.circle(img, bc, 4, (0, 255, 255), -1)

        # Mui ten huong di chuyen (chi khi track co heading = dang di chuyen)
        heading = getattr(st, "heading", None)
        if heading is not None:
            rad = math.radians(heading)
            tip = (int(bc[0] + math.sin(rad) * ARROW_LEN),
                   int(bc[1] - math.cos(rad) * ARROW_LEN))
            cv2.arrowedLine(img, bc, tip, color, 2, tipLength=0.3)

        label = f"id{tid} {cls_name(names, cls)} {st.conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

        # Thoi gian luu tru trong vung (dwell no_entry_road)
        for zid, zs in st.zones.items():
            if not zs.get("inside"):
                continue
            dw = next((float(p.get("dwell_s", 0)) for p in polygons
                       if p.get("id") == zid), 0.0)
            ztxt = f"{zid} {t_video - zs['enter_t']:.1f}/{dw:.0f}s"
            cv2.putText(img, ztxt, (bc[0] - 40, bc[1] + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Thoi gian dung do (no_parking)
        parking_st = getattr(st, "parking", {})
        for pid, pz in parking_st.items():
            if not pz or pz.get("fired"):
                continue
            pdw = t_video - pz["start_t"]
            ptxt = f"PARK {pid} {pdw:.1f}s"
            cv2.putText(img, ptxt, (bc[0] - 40, bc[1] + 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)

        # Hien thi van toc neu co
        spd = getattr(st, "speed", None)
        if spd is not None and spd.get("hist"):
            lim = float(spd.get("limit", 50.0))
            stxt = f"{spd.get('smooth', 0.0):.0f} km/h"
            scol = (0, 0, 255) if spd.get('smooth', 0.0) > lim else (255, 255, 255)
            cv2.putText(img, stxt, (x1, y2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, scol, 2)

    # 4b. Ve nguoi di bo (giu nguyen label ped, kem id neu co, khong doi label khi vao vung)
    for p in (pedestrians or []):
        bb = p.get("bbox")
        if not bb:
            continue
        px1, py1, px2, py2 = [int(v) for v in bb]
        p_conf = float(p.get("conf", 0.0))
        p_col = (255, 255, 0)  # Cyan
        cv2.rectangle(img, (px1, py1), (px2, py2), p_col, 2)
        bc = (int(p.get("bc", ((px1 + px2) / 2, py2))[0]), int(p.get("bc", ((px1 + px2) / 2, py2))[1]))
        cv2.circle(img, bc, 4, p_col, -1)
        pid_str = f"id{p['id']} " if p.get("id") is not None else ""
        p_lbl = f"{pid_str}ped {p_conf:.2f}"
        (pw, ph), _ = cv2.getTextSize(p_lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img, (px1, py1 - ph - 6), (px1 + pw + 4, py1), p_col, -1)
        cv2.putText(img, p_lbl, (px1 + 2, py1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

    # 5. HUD thong tin tren goc trai (FPS, Frame, Thong ke vi pham)
    y = 30
    ev_txt = "  ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    has_violations = sum(v for k, v in counts.items() if k != "skipped") > 0
    for txt, col in [\
        (f"FPS: {fps:.1f}", (0, 255, 0)),
        (f"frame {frame_idx} tracks {len(tracks)} peds {len(pedestrians or [])}", (0, 255, 0)),
        (ev_txt, (0, 0, 255) if has_violations else (0, 255, 0)),
    ]:
        cv2.putText(img, txt, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        y += 28

    return img


class Visualizer:
    """Lop Visualizer dong goi tien loi cho pipeline va de dang mock khi test."""

    def __init__(self, lines: Optional[List[Dict[str, Any]]] = None,
                 polygons: Optional[List[Dict[str, Any]]] = None,
                 names: Optional[Any] = None):
        self.lines = list(lines or [])
        self.polygons = list(polygons or [])
        self.names = names

    def render(self, img, tracks, fps: float = 0.0, counts: Optional[Dict[str, int]] = None,
               frame_idx: int = 0, t_video: float = 0.0, signals: Optional[Any] = None,
               pedestrians: Optional[List[Dict[str, Any]]] = None,
               gathering_zones: Optional[Dict[str, Dict[str, Any]]] = None):
        return draw_overlay(
            img, tracks, self.lines, self.polygons, fps, counts or {},
            frame_idx, names=self.names, t_video=t_video, signals=signals,
            pedestrians=pedestrians, gathering_zones=gathering_zones
        )

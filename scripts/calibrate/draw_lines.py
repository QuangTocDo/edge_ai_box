"""Tool ve/quan ly virtual lines + polygons, ghi vao configs/active.yaml.
Chay: python scripts/calibrate/draw_lines.py assets/video.mp4 [--config configs/active.yaml]

Chon loi truoc (bat buoc de ve moi):
  1=wrong_way (chi ve line) | 2=no_uturn (polygon+line+pair)
  3=no_entry (polygon banned) | 4=red_light (polygon lane+line+ROI+nga tu)
  5=speeding (polygon+calib) | 6=no_parking (polygon cam do)
  7=no_gathering (polygon cam tu tap)
  0=ve menu tu do (legacy)
Sau khi chon loi, chi hien/nhan cong cu duoc phep:
  l=ve line | p=ve dinh polygon | a=gan pair tay | r=keo ROI den
  i=ve vung nga tu | c=hieu chuan H | k=gan signal vao line
Chung:
  double-click = chon line (gan), signal (trong hop den), hoac polygon (trong)
  f = dao chieu line dang chon
  x = xoa line / polygon / signal dang chon (lien quan tu dong go / rot)
  u = go lien ket signal khoi line dang chon
  k = gan signal san co vao line dang chon (loi 4)
  s = luu bat cu luc nao (tu doc lai file de xac nhan)
  Esc = huy thao tac do | q = thoat (chua luu phai nhan q 2 lan)
"""
import math
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.calibration.draw_state import DrawState, mode_label, resolve_enter_action  # noqa: E402
from src.calibration.draw_menu import (allowed_tools, default_rules, get_mode, menu_text,
                           rules_off, subkey_tool, tools_help,
                           validate_tool)  # noqa: E402
from src.utils.geometry import (allowed_vec, line_near_or_in_polygon,
                          point_in_polygon)  # noqa: E402
from src.utils.homography import build_H, pixel_to_road  # noqa: E402
from src.config.zones import (add_polygon, delete_line, delete_polygon,
                             delete_signal, finalize_zone, find_polygon,
                             flip_line, get_polygons, iter_all_lines,
                             load_config, role_of, save_config, validate,
                             validate_polygons)  # noqa: E402


def all_pairs(cfg):
    out = list(cfg.get("uturn_pairs", []))
    for p in get_polygons(cfg):
        out += list(p.get("uturn_pairs", []))
    return out

ARROW_LEN = 60

# Bang mau chuan BGR dong bo voi Dashboard Tailwind/CSS
PALETTE = {
    "speeding": (239, 70, 217),        # #d946ef Fuchsia
    "wrong_way": (94, 197, 34),        # #22c55e Green
    "no_uturn": (8, 179, 234),         # #eab308 Amber
    "no_entry_road": (22, 115, 249),    # #f97316 Orange
    "red_light": (68, 68, 239),        # #ef4444 Red
    "stop_line": (11, 158, 245),       # #f59e0b Amber-500
    "no_parking": (212, 182, 6),       # #06b6d4 Cyan
    "no_gathering": (247, 85, 168),    # #a855f7 Purple
    "intersection": (246, 130, 59),    # #3b82f6 Sky/Blue
    "divider": (246, 130, 59),         # #3b82f6 Sky/Blue
    "homography": (129, 185, 16),      # #10b981 Emerald
    "arrow": (21, 204, 250),           # #facc15 Yellow neon
    "selected": (50, 50, 255),         # Bright Coral / Red
    "dark_bg": (15, 23, 42),           # #0f172a Slate-900
    "white": (255, 255, 255),
    "gray": (148, 163, 184),           # Slate-400
}


def draw_pill_badge(vis, text, pos, border_col, bg_col=(15, 23, 42), text_col=(255, 255, 255),
                    font_scale=0.45, thickness=1, pad_x=6, pad_y=4):
    """Ve nhan dark pill voi vien mau sac net giong Dashboard."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    x, y = int(pos[0]), int(pos[1])
    x1 = x - pad_x
    y1 = y - th - pad_y
    x2 = x + tw + pad_x
    y2 = y + pad_y

    h, w = vis.shape[:2]
    if x1 < 2:
        diff = 2 - x1; x1 += diff; x2 += diff; x += diff
    if x2 > w - 2:
        diff = x2 - (w - 2); x1 -= diff; x2 -= diff; x -= diff
    if y1 < 2:
        diff = 2 - y1; y1 += diff; y2 += diff; y += diff
    if y2 > h - 2:
        diff = y2 - (h - 2); y1 -= diff; y2 -= diff; y += diff

    sub = vis[y1:y2, x1:x2]
    if sub.shape[0] > 0 and sub.shape[1] > 0:
        dark = np.full_like(sub, bg_col)
        cv2.addWeighted(dark, 0.88, sub, 0.12, 0, sub)
    cv2.rectangle(vis, (x1, y1), (x2, y2), border_col, 1, lineType=cv2.LINE_AA)
    cv2.putText(vis, text, (x, y), font, font_scale, text_col, thickness, lineType=cv2.LINE_AA)
    return (x1, y1, x2, y2)


def draw_filled_poly(vis, pts, col, fill_alpha=0.18, border_thick=2, is_selected=False):
    """Ve da giac voi lop mau phu ban trong suot giong Dashboard SVG fill."""
    if len(pts) < 3:
        return
    pts_arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
    overlay = vis.copy()
    cv2.fillPoly(overlay, [pts_arr], col)
    cv2.addWeighted(overlay, fill_alpha, vis, 1.0 - fill_alpha, 0, vis)
    cv2.polylines(vis, [pts_arr], isClosed=True, color=col, thickness=border_thick, lineType=cv2.LINE_AA)
    if is_selected:
        cv2.polylines(vis, [pts_arr], isClosed=True, color=(255, 255, 255), thickness=1, lineType=cv2.LINE_AA)


def draw_dashed_polyline(vis, pts, col, thickness=2, dash_len=8, gap_len=6, closed=True):
    """Ve duong net dut (dashed line) dung cho khung 4 diem Homography."""
    n = len(pts)
    if n < 2:
        return
    segments = [(pts[i], pts[i + 1]) for i in range(n - 1)]
    if closed and n > 2:
        segments.append((pts[-1], pts[0]))
    for p1, p2 in segments:
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if dist < 1e-3:
            continue
        dx = (p2[0] - p1[0]) / dist
        dy = (p2[1] - p1[1]) / dist
        curr = 0.0
        while curr < dist:
            end = min(curr + dash_len, dist)
            pa = (int(p1[0] + dx * curr), int(p1[1] + dy * curr))
            pb = (int(p1[0] + dx * end), int(p1[1] + dy * end))
            cv2.line(vis, pa, pb, col, thickness, lineType=cv2.LINE_AA)
            curr += dash_len + gap_len


def draw_point_marker(vis, pt, col, r=5, label=None, label_col=None):
    """Ve diem dinh voi vong tron vien trang noi bat."""
    x, y = int(pt[0]), int(pt[1])
    cv2.circle(vis, (x, y), r + 2, (255, 255, 255), 1, lineType=cv2.LINE_AA)
    cv2.circle(vis, (x, y), r, col, -1, lineType=cv2.LINE_AA)
    if label:
        draw_pill_badge(vis, label, (x + 8, y - 4), border_col=label_col or col, font_scale=0.40, pad_x=4, pad_y=2)


def get_polygon_color_and_label(poly):
    """Xac dinh mau sac va nhan hien thi chuan theo tung loai rule giong Dashboard."""
    pid = poly.get("id", "ZONE")
    rules = poly.get("rules", {})
    if "speeding" in rules or poly.get("homography"):
        limit = 50
        sp_cfg = rules.get("speeding")
        if isinstance(sp_cfg, dict):
            limit = sp_cfg.get("limit_kmh", 50)
        return PALETTE["speeding"], f"{pid}: {limit}km/h"
    if "no_uturn" in rules:
        return PALETTE["no_uturn"], f"{pid} [No U-Turn]"
    if "no_entry_road" in rules:
        return PALETTE["no_entry_road"], f"{pid} [No Entry]"
    if "no_parking" in rules:
        return PALETTE["no_parking"], f"{pid} [No Parking]"
    if "no_gathering" in rules:
        return PALETTE["no_gathering"], f"{pid} [No Gathering]"
    if "red_light_running" in rules:
        return PALETTE["red_light"], f"{pid} [Red Light]"

    kind = poly.get("kind", "")
    if kind == "banned":
        return PALETTE["no_entry_road"], f"{pid} [Banned]"
    if kind == "intersection":
        return PALETTE["intersection"], f"{pid} [Intersection]"
    return PALETTE["wrong_way"], f"{pid} [{kind or 'Poly'}]"


def draw_all(vis, cfg, pairs, selected, clicks, poly_pts, sel_poly, roi_drag=None, sel_signal=None,
             calib_pts=None, calib_dir=None, violation=None):
    # 1. Signals (Hop den giao thong)
    for s in cfg.get("signals", []):
        roi = s.get("roi")
        if roi and len(roi) == 4:
            x1, y1, x2, y2 = [int(v) for v in roi]
            sel = sel_signal is not None and s.get("id") == sel_signal.get("id")
            col = PALETTE["selected"] if sel else PALETTE["red_light"]

            sub = vis[min(y1, y2):max(y1, y2), min(x1, x2):max(x1, x2)]
            if sub.shape[0] > 0 and sub.shape[1] > 0:
                fill_color = np.full_like(sub, col)
                cv2.addWeighted(fill_color, 0.18, sub, 0.82, 0, sub)

            cv2.rectangle(vis, (x1, y1), (x2, y2), col, 2, lineType=cv2.LINE_AA)
            draw_pill_badge(vis, f"SIGNAL {s.get('id', '')}", (min(x1, x2) + 4, min(y1, y2) - 6), border_col=col, font_scale=0.45)

    # 2. Khung ROI dang keo chuot
    if roi_drag and roi_drag.get("p0") is not None:
        p0 = roi_drag["p0"]
        p1 = roi_drag.get("p1") or p0
        xa, xb = sorted([p0[0], p1[0]])
        ya, yb = sorted([p0[1], p1[1]])
        sub = vis[ya:yb, xa:xb]
        if sub.shape[0] > 0 and sub.shape[1] > 0:
            fill_c = np.full_like(sub, PALETTE["red_light"])
            cv2.addWeighted(fill_c, 0.22, sub, 0.78, 0, sub)
        cv2.rectangle(vis, (xa, ya), (xb, yb), PALETTE["red_light"], 2, lineType=cv2.LINE_AA)
        draw_pill_badge(vis, "SIGNAL ROI (keo chuot)", (xa + 4, ya - 6), border_col=PALETTE["red_light"])

    # 3. Polygons da luu (Zones, Speeding, Banned, etc.)
    for p in get_polygons(cfg):
        pts = [(int(x), int(y)) for x, y in (p.get("polygon") or [])]
        if len(pts) >= 3:
            sel = sel_poly is not None and p["id"] == sel_poly.get("id")
            col, label = get_polygon_color_and_label(p)
            if sel:
                col = PALETTE["selected"]

            # Fill transparent & outline
            draw_filled_poly(vis, pts, col, fill_alpha=0.18, border_thick=3 if sel else 2, is_selected=sel)

            # Midpoint for label
            mx = sum(x for x, y in pts) // len(pts)
            my = sum(y for x, y in pts) // len(pts)
            draw_pill_badge(vis, label, (mx - 24, my), border_col=col, font_scale=0.48)

            # Neu co homography (Speeding), ve 4 diem goc H bang net dut xanh emerald
            hom = p.get("homography")
            if hom and hom.get("src") and len(hom["src"]) == 4:
                h_pts = [(int(x), int(y)) for x, y in hom["src"]]
                draw_dashed_polyline(vis, h_pts, PALETTE["homography"], thickness=1, dash_len=6, gap_len=4, closed=True)
                for i, hpt in enumerate(h_pts):
                    draw_point_marker(vis, hpt, PALETTE["homography"], r=4, label=f"P{i+1}")

            # Neu co huong road_dir, ve mui ten vang
            r_pts = p.get("road_dir_points")
            if r_pts and len(r_pts) == 2:
                cv2.arrowedLine(vis, (int(r_pts[0][0]), int(r_pts[0][1])),
                                (int(r_pts[1][0]), int(r_pts[1][1])),
                                PALETTE["arrow"], 3, tipLength=0.25)
            elif p.get("road_dir") and len(p["road_dir"]) == 2:
                rdir = p["road_dir"]
                p_end = (int(mx + rdir[0] * 50), int(my + rdir[1] * 50))
                cv2.arrowedLine(vis, (mx, my), p_end, PALETTE["arrow"], 3, tipLength=0.25)

    # 4. Lines (Vach dung, Vach nguoc chieu, Dai phan cach)
    for ln in iter_all_lines(cfg):
        p1 = tuple(int(v) for v in ln["p1"])
        p2 = tuple(int(v) for v in ln["p2"])
        sel = selected is not None and ln["id"] == selected.get("id")

        is_stop = role_of(ln) == "stop_line" or "STOP" in ln["id"].upper()
        is_divider = role_of(ln) == "divider"

        if sel:
            col = PALETTE["selected"]
        elif is_stop:
            col = PALETTE["stop_line"]
        elif is_divider:
            col = PALETTE["divider"]
        else:
            col = PALETTE["wrong_way"]

        thick = 4 if is_stop else (3 if sel else 2)
        cv2.line(vis, p1, p2, col, thick, lineType=cv2.LINE_AA)

        # Endpoint markers
        draw_point_marker(vis, p1, col, r=4)
        draw_point_marker(vis, p2, col, r=4)

        mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2

        if is_divider:
            tag = f"{ln['id']} [divider]"
        elif is_stop:
            tag = f"{ln['id']} [stop]"
            if ln.get("signal_id"):
                tag += f" -> {ln.get('signal_id', '')}"
        else:
            ax, ay = allowed_vec(ln["p1"], ln["p2"], ln.get("allowed_sign", 1))
            arrow_end = (int(mx + ax * ARROW_LEN), int(my + ay * ARROW_LEN))
            cv2.arrowedLine(vis, (mx, my), arrow_end, PALETTE["arrow"], 2, tipLength=0.25)
            tag = f"{ln['id']} {ln.get('allowed_sign', 1):+d}"
            if ln.get("signal_id"):
                tag += f" -> {ln.get('signal_id', '')}"

        draw_pill_badge(vis, tag, (mx - 15, my - 8), border_col=col, font_scale=0.45)

    # 5. Clicks dang ve dở dang
    for i, c in enumerate(clicks):
        x, y = int(c[0]), int(c[1])
        draw_point_marker(vis, (x, y), PALETTE["selected"], r=5, label=f"pt{i+1}")

    # 6. Poly pts dang ve dở dang
    if poly_pts:
        pts = [(int(x), int(y)) for x, y in poly_pts]
        if violation == "5":
            sp_labels = ["P1 (Vao-Trai)", "P2 (Vao-Phai)", "P3 (Ra-Phai)", "P4 (Ra-Trai)"]
            for i in range(1, len(pts)):
                cv2.line(vis, pts[i - 1], pts[i], PALETTE["speeding"], 2, lineType=cv2.LINE_AA)
            if len(pts) == 4:
                cv2.line(vis, pts[3], pts[0], PALETTE["speeding"], 2, lineType=cv2.LINE_AA)
                pts_arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
                overlay = vis.copy()
                cv2.fillPoly(overlay, [pts_arr], PALETTE["speeding"])
                cv2.addWeighted(overlay, 0.18, vis, 0.82, 0, vis)

                # Huong xe tu dong: Trung diem (P1, P2) -> Trung diem (P3, P4)
                m12 = ((pts[0][0] + pts[1][0]) // 2, (pts[0][1] + pts[1][1]) // 2)
                m34 = ((pts[2][0] + pts[3][0]) // 2, (pts[2][1] + pts[3][1]) // 2)
                cv2.arrowedLine(vis, m12, m34, PALETTE["arrow"], 3, tipLength=0.25)
                draw_pill_badge(vis, "Huong xe tu dong", ((m12[0] + m34[0]) // 2 - 38, (m12[1] + m34[1]) // 2 - 8),
                                border_col=PALETTE["arrow"], font_scale=0.42)

            for i, pt in enumerate(pts):
                lbl = sp_labels[i] if i < len(sp_labels) else f"P{i+1}"
                draw_point_marker(vis, pt, PALETTE["speeding"], r=6, label=lbl, label_col=PALETTE["speeding"])
        else:
            for i in range(1, len(pts)):
                cv2.line(vis, pts[i - 1], pts[i], PALETTE["speeding"], 2, lineType=cv2.LINE_AA)
            if len(pts) >= 3:
                pts_arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
                overlay = vis.copy()
                cv2.fillPoly(overlay, [pts_arr], PALETTE["speeding"])
                cv2.addWeighted(overlay, 0.14, vis, 0.86, 0, vis)
                cv2.line(vis, pts[-1], pts[0], PALETTE["speeding"], 1, cv2.LINE_AA)
            for i, pt in enumerate(pts):
                draw_point_marker(vis, pt, PALETTE["speeding"], r=5, label=f"{i+1}")

    # 7. Calib pts dang cham (4 diem Homography)
    if calib_pts:
        c_pts = [(int(x), int(y)) for x, y in calib_pts]
        if len(c_pts) >= 2:
            draw_dashed_polyline(vis, c_pts, PALETTE["homography"], thickness=2, dash_len=8, gap_len=6, closed=(len(c_pts) == 4))
        if len(c_pts) == 4:
            pts_arr = np.array(c_pts, dtype=np.int32).reshape((-1, 1, 2))
            overlay = vis.copy()
            cv2.fillPoly(overlay, [pts_arr], PALETTE["homography"])
            cv2.addWeighted(overlay, 0.18, vis, 0.82, 0, vis)
        for i, pt in enumerate(c_pts):
            draw_point_marker(vis, pt, PALETTE["homography"], r=6, label=f"P{i+1}", label_col=PALETTE["homography"])

    # 8. Calib dir dang cham (Huong road_dir)
    if calib_dir and len(calib_dir) == 2:
        (ax, ay), (bx, by) = calib_dir
        cv2.arrowedLine(vis, (int(ax), int(ay)), (int(bx), int(by)),
                        PALETTE["arrow"], 3, tipLength=0.25)
        draw_point_marker(vis, (ax, ay), PALETTE["arrow"], r=5, label="A (Dau)")
        draw_point_marker(vis, (bx, by), PALETTE["arrow"], r=5, label="B (Huong)")

    # 9. Pairs (Cap line U-Turn)
    y = 85
    for i, p in enumerate(pairs):
        text = f"pair{i}: {p['first']} -> {p['second']}" + (f" [med={p.get('medial', '')}]" if p.get("medial") else "")
        draw_pill_badge(vis, text, (vis.shape[1] - 250, y), border_col=PALETTE["no_uturn"], font_scale=0.42)
        y += 24

    return vis


def handle_action(kind, payload, st):
    """In action tu DrawState, tra ve True neu cfg doi."""
    if kind == "line_created":
        print(f"Da ve {payload['id']} ({st.mode})")
        return True
    if kind == "line_error":
        print(f"Loi tao line: {payload}")
    elif kind == "pair_pick":
        print(f"pair pick {payload[0]}/2: {payload[1]}")
    elif kind == "pair_created":
        print(f"Da tao pair {payload}")
        return True
    elif kind == "pair_error":
        print(f"Pair loi: {payload} (lam lai tu dau)")
    elif kind == "pair_miss":
        print("Click gan 1 line da ve (first->second)")
    elif kind == "selected":
        print(f"Da chon {payload}" if payload else "Khong co line gan do")
    return False


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "assets/video1.mp4"
    cfg_path = Path(sys.argv[sys.argv.index("--config") + 1]) \
        if "--config" in sys.argv else Path("configs/active.yaml")
    cfg_path = cfg_path.resolve()
    is_new = not cfg_path.exists()
    cfg = load_config(cfg_path)
    st = DrawState(cfg)
    n_top = len(cfg.get("lines", []))
    n_nest = sum(len(p.get("lines", [])) for p in get_polygons(cfg))
    print(f"Da nap {n_top + n_nest} lines ({len(get_polygons(cfg))} polygons), "
          f"{len(cfg['uturn_pairs'])} pairs tu {cfg_path}")
    if is_new:
        print(f"CANH BAO: file {cfg_path} chua ton tai -> dang mo config TRANG. "
              f"Neu muon sua hinh cu, chay lai voi --config <file cu> "
              f"(vd --config configs/active.yaml). Nhan s se tao file moi.")

    cap = cv2.VideoCapture(src if not str(src).isdigit() else int(src))
    ok, frame = cap.read()
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
    if n > 1:
        cap.set(cv2.CAP_PROP_POS_FRAMES, n // 3)
        ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"Khong doc duoc frame tu: {src}")

    msg, dirty, quit_armed = "", False, False
    tool_mode = "line"  # line | polygon (ve dinh polygon)
    poly_pts: list = []
    sel_poly: dict | None = None
    sel_signal: dict | None = None
    wizard: dict | None = None  # {"poly_id": str|None} flow gop, None = tat
    standalone = False  # True = ve wrong_way don, giu top-level
    roi_drag: dict = {"p0": None, "p1": None}  # keo chuot mode roi
    calib: dict | None = None  # {"poly_id": str, "stage": "pts"|"dir", "pts": [(x,y)]} mode c
    violation: str | None = None  # None = menu chinh; "1".."7" = loi dang chon
    pending_kind: str | None = None  # kind ep cho polygon sap ve (menu tu dat)
    active_red_poly: str | None = None  # id polygon do dang ve (loi 4, de gan clearance)

    def next_signal_id():
        used = {s.get("id") for s in cfg.get("signals", [])}
        i = 1
        while f"SIG_{i:02d}" in used:
            i += 1
        return f"SIG_{i:02d}"

    def on_mouse(ev, x, y, *_):
        nonlocal dirty, sel_poly, sel_signal, wizard
        now = time.monotonic()
        if violation is not None and ev in (
                cv2.EVENT_LBUTTONDOWN, cv2.EVENT_LBUTTONUP):
            need = None
            if tool_mode == "polygon":
                need = ("intersection"
                        if pending_kind == "intersection" else "polygon")
            elif tool_mode == "roi":
                need = "roi"
            elif tool_mode == "calib":
                need = "calib"
            elif tool_mode == "line":
                if st.mode == "directed":
                    need = "line"
                elif st.mode == "pair":
                    need = "pair"
                else:
                    need = "divider"
            if need is not None:
                ok, why = validate_tool(violation, need)
                if not ok:
                    print(f"Bi chan: {why}")
                    return
        if tool_mode == "calib":
            if ev == cv2.EVENT_LBUTTONDOWN and calib is not None:
                if calib["stage"] == "dir" and len(calib["pts"]) >= 2:
                    return
                calib["pts"].append((x, y))
            return
        if tool_mode == "roi":
            if ev == cv2.EVENT_LBUTTONDOWN:
                roi_drag["p0"], roi_drag["p1"] = (x, y), None
            elif ev == cv2.EVENT_MOUSEMOVE and roi_drag["p0"] is not None:
                roi_drag["p1"] = (x, y)
            elif ev == cv2.EVENT_LBUTTONUP and roi_drag["p0"] is not None:
                x0, y0 = roi_drag["p0"]
                x1, y1 = (x, y) if roi_drag["p1"] is None else roi_drag["p1"]
                roi_drag["p0"], roi_drag["p1"] = None, None
                xa, xb = sorted([x0, x1])
                ya, yb = sorted([y0, y1])
                if xb - xa < 8 or yb - ya < 8:
                    print("ROI qua nho, bo qua")
                    return
                sid = next_signal_id()
                cfg.setdefault("signals", []).append(
                    {"id": sid, "roi": [xa, ya, xb, yb], "ttl_s": 1.0})
                if st.selected is not None and \
                        st.selected.get("role") != "divider":
                    st.selected["signal_id"] = sid
                    print(f"Da tao {sid} roi={xa, ya, xb, yb} "
                          f"-> gan vao line {st.selected['id']}")
                else:
                    print(f"Da tao {sid} roi={xa, ya, xb, yb} "
                          "(chua gan line: double-click line roi keo lai)")
                dirty = True
            return
        if tool_mode == "polygon":
            if ev == cv2.EVENT_LBUTTONDOWN:
                if violation == "5" and len(poly_pts) >= 4:
                    print("Da du 4 diem P1..P4 cho vung toc do. Nhan ENTER de xac nhan hoac Esc de huy.")
                    return
                poly_pts.append((x, y))
                if violation == "5":
                    sp_labels = ["P1 (Rong vao-Trai)", "P2 (Rong vao-Phai)", "P3 (Rong ra-Phai)", "P4 (Rong ra-Trai)"]
                    print(f"  -> Da cham {sp_labels[len(poly_pts) - 1]}: ({x}, {y})")
                    if len(poly_pts) == 4:
                        print(">> Da du 4 diem P1..P4! Nhan ENTER de nhap W, L va hoan tat vung toc do.")
            return
        if ev == cv2.EVENT_LBUTTONDBLCLK:
            kind, payload = st.on_dblclk(x, y, now)
            if payload is not None:
                sel_poly = None
                sel_signal = None
            else:
                clicked_sig = None
                for s in cfg.get("signals", []):
                    roi = s.get("roi")
                    if roi and len(roi) == 4:
                        x1, y1, x2, y2 = [int(v) for v in roi]
                        xa, xb = sorted([x1, x2])
                        ya, yb = sorted([y1, y2])
                        if (xa - 5) <= x <= (xb + 5) and (ya - 5) <= y <= (yb + 5):
                            clicked_sig = s
                            break
                if clicked_sig is not None:
                    sel_signal = clicked_sig
                    sel_poly = None
                    print(f"Da chon signal {clicked_sig['id']}")
                else:
                    sel_signal = None
                    for p in get_polygons(cfg):
                        if point_in_polygon((x, y), p.get("polygon", [])):
                            sel_poly = p
                            print(f"Da chon polygon {p['id']}")
                            break
                    else:
                        sel_poly = None
                        print("Khong co line/polygon/signal gan do")
            dirty |= handle_action(kind, payload, st)
        elif ev == cv2.EVENT_LBUTTONDOWN:
            dirty |= handle_action(*st.on_down(x, y, now), st)

    def close_wizard_polygon():
        nonlocal dirty, wizard, tool_mode
        if len(poly_pts) < 3:
            print(f"Can >=3 dinh (dang co {len(poly_pts)})")
            return False
        try:
            p = add_polygon(cfg, poly_pts, kind="directional")
        except ValueError as e:
            print(f"Polygon loi: {e} (giua lai dinh de sua)")
            return False
        print(f"Da tao {p['id']}: ve 2 lines ben trong (moi line click 2 diem)")
        poly_pts.clear()
        st.set_mode("directed")
        tool_mode = "line"
        wizard = {"poly_id": p["id"]}
        dirty = True
        return True

    def close_polygon():
        nonlocal dirty, pending_kind, active_red_poly, sel_poly
        nonlocal tool_mode, wizard
        in_menu = violation is not None
        kind: str | None = None
        if pending_kind is not None:
            kind, pending_kind = pending_kind, None
            print(f"--- Polygon kind={kind} (menu tu dat) ---")
        else:
            print("--- Polygon le (khong thuoc zone flow phim 1) ---")
        if len(poly_pts) < 3:
            print(f"Can >=3 dinh (dang co {len(poly_pts)})")
            return False
        if not in_menu:
            kind = (input("kind [banned/directional/intersection] (mac dinh directional): ")
                    or "directional").strip()
        elif kind is None:
            kind = "banned" if violation in ("3", "6", "7") else "directional"
        try:
            if violation == "5":
                if len(poly_pts) != 4:
                    print(f"Loi 5 (speeding) yeu cau dung 4 diem (P1..P4). Dang co {len(poly_pts)} diem. (Esc de huy)")
                    return False
                P1, P2, P3, P4 = poly_pts[0], poly_pts[1], poly_pts[2], poly_pts[3]
                print("\n=== CAU HINH VUNG DO TOC DO 4 DIEM ===")
                print(f"  P1({P1[0]},{P1[1]}) - P2({P2[0]},{P2[1]}): Chieu rong dau vao")
                print(f"  P3({P3[0]},{P3[1]}) - P4({P4[0]},{P4[1]}): Chieu rong dau ra")
                print("  Huong xe: Tu trung diem (P1,P2) -> trung diem (P3,P4)")
                w_in = input("Nhap chieu rong duong W (met, mac dinh 3.5): ").strip() or "3.5"
                l_in = input("Nhap chieu dai doan L (met, mac dinh 20.0): ").strip() or "20.0"
                sp_in = input("Nhap toc do gioi han (km/h, mac dinh 50): ").strip() or "50"
                width_m = float(w_in)
                length_m = float(l_in)
                limit_kmh = float(sp_in)

                world_dst = [
                    [0.0, 0.0],
                    [width_m, 0.0],
                    [width_m, length_m],
                    [0.0, length_m],
                ]
                H_mat, inliers, reproj_err = build_H(poly_pts, world_dst)
                print(f"Homography OK: {inliers}/4 inliers, reproj error {reproj_err:.2f}m")

                m12 = [(P1[0] + P2[0]) / 2.0, (P1[1] + P2[1]) / 2.0]
                m34 = [(P3[0] + P4[0]) / 2.0, (P3[1] + P4[1]) / 2.0]

                p = add_polygon(cfg, poly_pts, kind="directional")
                p["homography"] = {
                    "src": [[int(x), int(y)] for x, y in poly_pts],
                    "dst": world_dst,
                    "measured_at": datetime.now().isoformat(timespec="seconds"),
                }
                p["road_dir"] = [0.0, 1.0]
                p["road_dir_points"] = [
                    [round(m12[0], 1), round(m12[1], 1)],
                    [round(m34[0], 1), round(m34[1], 1)],
                ]
                p.setdefault("rules", {})["speeding"] = {
                    "enable": True,
                    "limit_kmh": limit_kmh,
                }
                print(f"Da tao vung toc do {p['id']}: {width_m}m x {length_m}m, limit={limit_kmh}km/h, huong xe tu dong.")
                poly_pts.clear()
                dirty = True
                sel_poly = p
                tool_mode = "line"
                return p["id"]
            elif violation == "6":
                dw = input("dwell_s thoi gian do xe de bao loi (mac dinh 10s): ").strip() or "10"
                p = add_polygon(cfg, poly_pts, kind="banned",
                                banned_classes=[],
                                active_hours=[],
                                dwell_s=float(dw))
            elif violation == "7":
                mp = input("min_persons so nguoi toi thieu de bao tu tap (mac dinh 5): ").strip() or "5"
                dw = input("dwell_s thoi gian duy tri dam dong (mac dinh 60s): ").strip() or "60"
                ah = input("active_hours vd '22:00-05:00' (mac dinh rong): ").strip()
                p = add_polygon(cfg, poly_pts, kind="banned",
                                banned_classes=[],
                                active_hours=[x for x in ah.split(",") if x.strip()],
                                dwell_s=float(dw))
                p.setdefault("rules", {})["no_gathering"] = {
                    "enable": True,
                    "min_persons": int(mp),
                    "dwell_s": float(dw),
                    "cooldown_s": 300.0,
                }
            elif kind == "banned":
                bc = input("banned_classes vd '0,4' (mac dinh rong): ").strip()
                ah = input("active_hours vd '18:00-05:00' (mac dinh rong): "
                           ).strip()
                dw = input("dwell_s (mac dinh 2): ").strip() or "2"
                p = add_polygon(cfg, poly_pts, kind="banned",
                                banned_classes=[int(x) for x in bc.split(",")
                                                if x.strip()],
                                active_hours=[x for x in ah.split(",")
                                              if x.strip()],
                                dwell_s=float(dw))
            elif kind == "intersection":
                p = add_polygon(cfg, poly_pts, kind="directional")
                p["kind"] = "intersection"
                p["rules"] = {}
            else:
                p = add_polygon(cfg, poly_pts, kind="directional")
                if not in_menu:
                    ans_red = input("Bat vuot den do / dung de vach tren lane nay? [y/N]: ").strip().lower()
                    if ans_red == "y":
                        clr = input("Id polygon clearance nga tu (vd POLY_junction_center, Enter bo qua): ").strip()
                        rules = p.setdefault("rules", {})
                        rules["red_light_running"] = {
                            "enable": True,
                            "intersection_clearance_zone": clr if clr else "POLY_junction_center"
                        }
                        rules["stop_line"] = {"enable": True}
            print(f"Da tao polygon {p['id']} [{p['kind']}]")
            poly_pts.clear()
            dirty = True
            if in_menu:
                _apply_menu_rules(p, kind)
                if violation == "2" and kind == "directional":
                    sel_poly = p
                    st.set_mode("directed")
                    tool_mode = "line"
                    wizard = {"poly_id": p["id"]}
                    print(f"Ve 2 lines trong {p['id']} (moi line click 2 diem), "
                          f"du 2 lines tu hoi pair")
            return p["id"]
        except (ValueError, TypeError) as e:
            print(f"Polygon loi: {e} (giua lai dinh de sua)")
            return None

    def _apply_menu_rules(p, kind):
        nonlocal active_red_poly, sel_poly
        if kind == "intersection" and violation == "4":
            p["rules"] = rules_off()
            rp = find_polygon(cfg, active_red_poly) if active_red_poly else None
            if rp is not None:
                rr = rp.setdefault("rules", {}).setdefault(
                    "red_light_running", {})
                rr["enable"] = True
                rr["intersection_clearance_zone"] = p["id"]
                print(f"Da gan clearance {p['id']} vao {rp['id']}")
            else:
                print("Khong thay polygon do de gan clearance "
                      "(ve polygon do truoc)")
            return
        existing_custom = (p.get("rules") or {}).get("no_gathering", {})
        p["rules"] = default_rules(violation)
        if violation == "7" and existing_custom:
            p["rules"]["no_gathering"].update(existing_custom)
        if violation == "4":
            active_red_poly = p["id"]
        if violation == "5":
            sel_poly = p
        print(f"Da bat rules cho {p['id']}: "
              f"{[r for r, b in p['rules'].items() if b.get('enable')]}")

    def close_calib():
        nonlocal dirty, calib, tool_mode
        if calib is None:
            return False
        poly = find_polygon(cfg, calib["poly_id"])
        if poly is None:
            print("Polygon da bi xoa, huy hieu chuan")
            calib = None
            tool_mode = "line"
            return False
        if calib["stage"] == "pts":
            pts = calib["pts"]
            if len(pts) < 4:
                print(f"Can >=4 diem (dang co {len(pts)})")
                return False
            print("Nhap toa do met (X Y) cho tung diem anh:")
            dst = []
            for i, (x, y) in enumerate(pts):
                while True:
                    raw = input(f"  P{i + 1} ({x},{y}) -> X Y met: ").strip()
                    try:
                        X, Y = [float(v) for v in raw.split()]
                        dst.append([X, Y])
                        break
                    except (ValueError, IndexError):
                        print("    Sai format, vd: 0 0")
            try:
                H, inl, err = build_H(
                    [[x, y] for x, y in pts], dst)
            except ValueError as e:
                print(f"H loi: {e} (chon lai diem, Esc huy)")
                return False
            print(f"H OK: {inl}/{len(pts)} inliers, reproj error {err:.2f}m")
            ok = input("Luu H vao polygon? [Y/n]: ").strip().lower()
            if ok not in ("", "y", "yes"):
                print("Bo qua, giu diem de sua")
                return False
            poly["homography"] = {
                "src": [[int(x), int(y)] for x, y in pts],
                "dst": dst,
                "measured_at": datetime.now().isoformat(timespec="seconds"),
            }
            dirty = True
            calib["stage"] = "dir"
            calib["pts"] = []
            print("Da luu H. Click 2 diem A->B doc huong duong "
                  "roi Enter de chot road_dir")
            return True
        pts = calib["pts"]
        if len(pts) != 2:
            print(f"Can dung 2 diem huong (dang co {len(pts)}), Esc huy")
            return False
        (ax, ay), (bx, by) = pts
        src_pts = poly.get("homography", {}).get("src")
        dst_pts = poly.get("homography", {}).get("dst")
        if src_pts and dst_pts and len(src_pts) >= 4 and len(dst_pts) >= 4:
            try:
                H_mat, _, _ = build_H(src_pts, dst_pts)
                xa, ya = pixel_to_road(H_mat, ax, ay)
                xb, yb = pixel_to_road(H_mat, bx, by)
                dx, dy = xb - xa, yb - ya
                n = math.hypot(dx, dy)
                if n < 1e-9:
                    print("2 diem tren mat duong trung nhau, chon lai (Esc huy)")
                    calib["pts"] = []
                    return False
                poly["road_dir"] = [dx / n, dy / n]
                print(f"Da chieu len mat duong met: A({xa:.2f},{ya:.2f}) -> B({xb:.2f},{yb:.2f})")
                print(f"Da luu road_dir={[round(v, 4) for v in poly['road_dir']]} vao {poly['id']}")
                calib = None
                tool_mode = "line"
                dirty = True
                return True
            except Exception as e:
                print(f"Loi chieu road_dir qua H: {e}, fallback dung toa do pixel")
        n = math.hypot(bx - ax, by - ay)
        if n < 1e-9:
            print("2 diem trung nhau, chon lai (Esc huy)")
            calib["pts"] = []
            return False
        poly["road_dir"] = [(bx - ax) / n, (by - ay) / n]
        print(f"Da luu road_dir={[round(v, 3) for v in poly['road_dir']]} "
              f"vao {poly['id']}")
        calib = None
        tool_mode = "line"
        dirty = True
        return True

    def _busy():
        return bool(st.clicks or st.picks or poly_pts
                    or wizard is not None or calib is not None
                    or roi_drag.get("p0") is not None)

    def _gate(tool):
        ok, why = validate_tool(violation, tool)
        if not ok:
            print(f"Bi chan: {why}")
            return True
        return False

    def _start_polygon_draw(kind):
        nonlocal tool_mode, wizard, standalone, pending_kind
        st.cancel()
        poly_pts.clear()
        tool_mode = "polygon"
        wizard = None
        standalone = False
        pending_kind = kind
        label = {"directional": "lane/zone", "banned": "vung cam/cam do/cam tu tap",
                 "intersection": "vung nga tu"}.get(kind, kind)
        print(f"Ve {label}: click tung dinh -> Enter chot, Esc huy")

    def _start_line_draw():
        nonlocal tool_mode, wizard, standalone
        st.cancel()
        st.set_mode("directed")
        tool_mode = "line"
        wizard = None
        standalone = (violation == "1")
        if standalone:
            print("Ve line nguoc chieu: click 2 diem/line (top-level)")
        else:
            print("Ve line: click 2 diem/line (tu gan vao polygon gan nhat)")

    def _start_pair_mode():
        nonlocal tool_mode, wizard, standalone
        st.set_mode("pair")
        tool_mode = "line"
        wizard = None
        standalone = False
        print("Pair mode: click 2 lines (first->second)")

    def _start_roi_mode():
        nonlocal tool_mode, wizard, standalone
        st.cancel()
        tool_mode = "roi"
        wizard = None
        standalone = False
        poly_pts.clear()
        _msg = "Che do ROI den: nhan-giu-keo chuot de chon hop den"
        if st.selected and st.selected.get("role") != "divider":
            _msg += f" (se gan vao line {st.selected['id']})"
        else:
            _msg += " (chua chon line: double-click line truoc neu muon gan ngay)"
        print(_msg)
        return _msg

    def _start_calib_mode():
        nonlocal tool_mode, wizard, standalone, calib
        st.cancel()
        wizard = None
        standalone = False
        poly_pts.clear()
        if sel_poly is None:
            print("Hieu chuan can 1 polygon: double-click vao polygon "
                  "truoc roi nhan c")
            tool_mode = "line"
            return "Hieu chuan can 1 polygon (double-click polygon truoc)"
        calib = {"poly_id": sel_poly["id"], "stage": "pts", "pts": []}
        tool_mode = "calib"
        print(f"Hieu chuan {sel_poly['id']}: click >=4 diem tren mat "
              "duong -> Enter (Esc huy)")
        return f"Hieu chuan {sel_poly['id']}: click >=4 diem -> Enter"

    def _link_signal():
        nonlocal dirty
        if st.selected is None or st.selected.get("role") == "divider":
            return "Chua chon line (double-click line truoc)"
        sigs = cfg.get("signals", [])
        if not sigs:
            return "Chua co signal nao (dung r de tao ROI den truoc)"
        if len(sigs) == 1:
            sid = sigs[0]["id"]
            st.selected["signal_id"] = sid
            dirty = True
            return f"Da gan {sid} vao line {st.selected['id']}"
        print("Cac signal hien co:", [s.get('id') for s in sigs])
        chosen = input(f"Nhap signal_id muon gan vao line {st.selected['id']}: ").strip()
        if any(s.get('id') == chosen for s in sigs):
            st.selected["signal_id"] = chosen
            dirty = True
            return f"Da gan {chosen} vao line {st.selected['id']}"
        return f"Khong tim thay signal: {chosen}"

    cv2.namedWindow("draw_lines")
    cv2.setMouseCallback("draw_lines", on_mouse)
    while True:
        kind, payload = st.poll(time.monotonic())
        if kind == "line_created" and standalone:
            assert isinstance(payload, dict), payload
            print(f"Da ve {payload['id']} (wrong_way don, top-level)")
            dirty = True
        elif kind == "line_created":
            assert isinstance(payload, dict), payload
            attached = None
            if sel_poly is not None and line_near_or_in_polygon(
                    payload["p1"], payload["p2"], sel_poly.get("polygon", []), max_dist=50.0):
                attached = sel_poly
            if attached is None:
                for p in get_polygons(cfg):
                    if line_near_or_in_polygon(
                            payload["p1"], payload["p2"], p.get("polygon", []), max_dist=30.0):
                        attached = p
                        break
            if attached is not None:
                if payload in cfg.get("lines", []):
                    cfg["lines"].remove(payload)
                attached.setdefault("lines", []).append(payload)
                print(f"Da ve {payload['id']} -> gan vao {attached['id']}")
            else:
                print(f"Da ve {payload['id']} ({st.mode}, top-level)")
            dirty = True
            if wizard is not None and wizard.get("poly_id") is not None \
                    and attached is not None \
                    and attached["id"] == wizard["poly_id"]:
                n = sum(1 for ln in attached.get("lines", [])
                        if role_of(ln) != "divider")
                if n >= 2:
                    ans = input(
                        f"Zone {attached['id']} du 2 lines. "
                        "Bat cam quay dau? [y/N]: ").strip().lower()
                    try:
                        res = finalize_zone(cfg, attached["id"],
                                            no_uturn=(ans == "y"))
                        print(f"Zone xong: {res['polygon']} "
                              f"lines={res['lines']} pairs={res['pairs']}")
                    except ValueError as e:
                        print(f"Loi: {e}")
                    wizard = None
                else:
                    print(f"Zone {attached['id']}: {n}/2 lines, ve tiep")
        elif kind is not None:
            dirty |= handle_action(kind, payload, st)
        vis = draw_all(frame.copy(), cfg, all_pairs(cfg),
                       st.selected, st.clicks, poly_pts, sel_poly,
                       roi_drag=roi_drag, sel_signal=sel_signal,
                       calib_pts=calib["pts"] if calib else None,
                       calib_dir=(calib["pts"][:2]
                                  if calib and calib["stage"] == "dir" else None),
                       violation=violation)
        # Thanh dieu khien HUD phong cach Dashboard hien dai
        hud_h = 68
        w = vis.shape[1]
        sub = vis[0:hud_h, 0:w]
        dark = np.full_like(sub, PALETTE["dark_bg"])
        cv2.addWeighted(dark, 0.90, sub, 0.10, 0, sub)
        cv2.line(vis, (0, hud_h), (w, hud_h), (51, 65, 85), 1, lineType=cv2.LINE_AA)

        font = cv2.FONT_HERSHEY_SIMPLEX
        if violation is None:
            banner1 = f"{menu_text()} | S=luu Q=thoat"
            cv2.putText(vis, banner1, (14, 26), font, 0.48, (226, 232, 240), 1, lineType=cv2.LINE_AA)
        else:
            m = get_mode(violation)
            assert m is not None, violation
            mode_color = PALETTE.get(m.get("violation", ""), (16, 185, 129))
            draw_pill_badge(vis, f"LOI: {m[label]}", (14, 24), border_col=mode_color, bg_col=(30, 41, 59), font_scale=0.48)
            tools_txt = f"Cong cu: {'  '.join(tools_help(violation))} | 0=doi loi | S=luu | Q=thoat"
            cv2.putText(vis, tools_txt, (260, 24), font, 0.46, (226, 232, 240), 1, lineType=cv2.LINE_AA)

        sel = st.selected["id"] if st.selected else (
            sel_signal["id"] if sel_signal else (
                sel_poly["id"] if sel_poly else "-"))
        n_lines = len(cfg.get("lines", [])) + sum(
            len(p.get("lines", [])) for p in get_polygons(cfg))
        n_sigs = len(cfg.get("signals", []))
        hud_row2 = (f"MODE={'STANDALONE-WW' if standalone else mode_label(wizard, tool_mode, st.mode)} | "
                    f"lines={n_lines} | poly={len(get_polygons(cfg))} | sigs={n_sigs} | "
                    f"pairs={len(all_pairs(cfg))} | sel={sel} | "
                    "dblclick=chon F=dao X=xoa U=go-den K=gan-den Esc=huy")
        cv2.putText(vis, hud_row2, (14, 52), font, 0.44, (148, 163, 184), 1, lineType=cv2.LINE_AA)

        # Polygon rules active list
        y0 = hud_h + 24
        for p in get_polygons(cfg):
            rules_dict = p.get("rules") or {}
            active_rules = []
            for r in ("wrong_way", "no_uturn", "no_entry_road", "no_parking", "no_gathering", "red_light_running", "stop_line", "speeding"):
                rc = rules_dict.get(r, {})
                if rc.get("enable", True):
                    if r == "speeding":
                        active_rules.append(f"speed({rc.get('limit_kmh', 50)}km/h)")
                    else:
                        active_rules.append(r)
            p_col, _ = get_polygon_color_and_label(p)
            poly_info = f"{p['id']}: {'+'.join(active_rules) if active_rules else 'tat het'}"
            draw_pill_badge(vis, poly_info, (14, y0), border_col=p_col, font_scale=0.42, pad_x=4, pad_y=2)
            y0 += 22
            if y0 > frame.shape[0] - 20:
                break

        if msg:
            draw_pill_badge(vis, f"ALERT: {msg}", (14, hud_h + 30), border_col=(50, 50, 255),
                            bg_col=(50, 10, 10), font_scale=0.52, pad_x=8, pad_y=4)
        cv2.imshow("draw_lines", vis)
        key = cv2.waitKey(20) & 0xFF
        msg = ""
        if key != ord("q"):
            quit_armed = False

        kchr = chr(key) if key < 256 else ""
        if kchr in ("1", "2", "3", "4", "5", "6", "7"):
            if _busy():
                msg = "Dang ve do, Esc truoc khi doi loi"
                print(msg)
            else:
                violation = kchr
                m = get_mode(kchr)
                assert m is not None, kchr
                tool_mode, wizard = "line", None
                st.cancel()
                st.set_mode("directed")
                poly_pts.clear()
                pending_kind, active_red_poly = None, None
                standalone = (kchr == "1")
                print(f"Chon loi: {m['violation']} "
                      f"(chi duoc: {', '.join(m['tools'])})")
                print("Cong cu: " + "  ".join(tools_help(kchr)))
                if kchr == "5":
                    print("\n>>> CHE DO SPEEDING 4 DIEM TRUC TIEP <<<")
                    print("  Nhan 'p' de bat dau cham 4 diem P1->P2->P3->P4 tren mat duong:")
                    print("    * P1 (Trai) & P2 (Phai): Chieu rong dau vao (W)")
                    print("    * P3 (Phai) & P4 (Trai): Chieu rong dau ra (W)")
                    print("    * Huong xe va Homography se tu dong duoc tinh tu trung diem (P1,P2) -> (P3,P4)!")
            continue
        if kchr == "0":
            if _busy():
                msg = "Dang ve do, Esc truoc khi ve menu"
                print(msg)
            else:
                violation = None
                tool_mode, wizard = "line", None
                st.cancel()
                st.set_mode("directed")
                pending_kind = None
                print(menu_text())
            continue
        if violation is not None:
            if kchr in ("l", "p", "a", "r", "i", "c", "k"):
                if _busy() and kchr in ("p", "i"):
                    msg = "Dang ve do, Esc truoc khi doi cong cu"
                    print(msg)
                    continue
                tool = subkey_tool(kchr)
                if _gate(tool):
                    msg = f"Bi chan phim '{kchr}'"
                    continue
                if kchr == "l":
                    _start_line_draw()
                elif kchr == "p":
                    _start_polygon_draw(
                        "banned" if violation in ("3", "6", "7") else "directional")
                elif kchr == "a":
                    _start_pair_mode()
                elif kchr == "r":
                    msg = _start_roi_mode()
                elif kchr == "i":
                    _start_polygon_draw("intersection")
                elif kchr == "c":
                    if violation == "5" and sel_poly is None:
                        msg = "Speeding tich hop tu dong: nhan 'p' ve 4 diem P1->P2->P3->P4 roi Enter!"
                        print(msg)
                    else:
                        msg = _start_calib_mode()
                elif kchr == "k":
                    msg = _link_signal()
                    print(msg)
                continue
        else:
            if key == ord("1"):
                st.cancel()
                poly_pts.clear()
                tool_mode = "polygon"
                wizard = {"poly_id": None}
                standalone = False
                print("Zone flow: click tung dinh polygon -> Enter chot, Esc huy")
                continue
            elif key == ord("2"):
                st.set_mode("divider")
                tool_mode = "line"
                wizard = None
                standalone = False
                continue
            elif key == ord("3"):
                st.set_mode("pair")
                tool_mode = "line"
                wizard = None
                standalone = False
                print("Pair mode: click 2 lines (first->second)")
                continue
            elif key == ord("w"):
                st.cancel()
                st.set_mode("directed")
                tool_mode = "line"
                wizard = None
                standalone = True
                print("Wrong-way don: click 2 diem/line (giu top-level, nhu ban dau)")
                continue
            elif key == ord("4"):
                st.cancel()
                tool_mode = "polygon"
                wizard = None
                standalone = False
                print("Polygon le: click tung dinh -> Enter chot, Esc huy")
                continue
            elif key == ord("5"):
                msg = _start_roi_mode()
                continue
            elif key == ord("c"):
                msg = _start_calib_mode()
                print(msg)
                continue
        if key == ord("f") and st.selected:
            try:
                msg = f"{st.selected['id']} sign=" \
                      f"{flip_line(cfg, st.selected['id']):+d}"
                dirty = True
            except ValueError as e:
                msg = str(e)
        elif key in (ord("x"), 127) and (st.selected or sel_poly or sel_signal):
            if sel_signal:
                sid = sel_signal.get("id")
                sig, unlinked = delete_signal(cfg, sid)
                msg = f"Da xoa signal {sid}" + (
                    f" (go khoi {len(unlinked)} line: {unlinked})" if unlinked else "")
                sel_signal = None
            elif st.selected:
                ln, dropped = delete_line(cfg, st.selected["id"])
                msg = (f"Da xoa {ln['id']}" +
                       (f" (+rot {len(dropped)} pair)" if dropped else ""))
                st.selected = None
            else:
                assert sel_poly is not None
                poly, dropped = delete_polygon(cfg, sel_poly["id"])
                msg = (f"Da xoa polygon {poly['id']} "
                       f"(+{len(poly.get('lines', []))} lines con, "
                       f"{len(dropped)} pair)")
                sel_poly = None
            print(msg)
            dirty = True
        elif key == ord("u") and st.selected and st.selected.get("signal_id"):
            old_sid = st.selected.pop("signal_id")
            msg = f"Da go signal {old_sid} khoi line {st.selected['id']}"
            print(msg)
            dirty = True
        elif key in (ord("k"), ord("l")) and st.selected and st.selected.get("role") != "divider":
            if violation is not None:
                if kchr == "l":
                    msg = "Dung phim 'k' de gan signal (phim 'l' la ve line)"
                    print(msg)
                    continue
                if _gate("roi_link"):
                    msg = "Bi chan gan signal"
                    continue
            msg = _link_signal()
            print(msg)
        elif key == ord("s"):
            cfg["source"] = str(src)
            if str(src).lower().endswith(
                    (".jpg", ".jpeg", ".png", ".bmp", ".webp")):
                print("CANH BAO: source la anh tinh — pipeline doc anh "
                      "se dung sau 1 frame. Muon chay video/RTSP thi sua "
                      "field 'source:' trong YAML.")
            warns = validate(cfg) + validate_polygons(cfg)
            save_config(cfg, cfg_path)
            back = load_config(cfg_path)
            now_ids = ({l["id"] for l in iter_all_lines(cfg)},
                       len(cfg["uturn_pairs"]), len(get_polygons(cfg)))
            back_ids = ({l["id"] for l in iter_all_lines(back)},
                         len(back["uturn_pairs"]), len(get_polygons(back)))
            ok_save = now_ids == back_ids
            dirty = False
            msg = (f"Da luu {len(now_ids[0])} lines + "
                   f"{now_ids[1]} pairs + {now_ids[2]} polygons + {len(cfg.get('signals', []))} signals -> {cfg_path}"
                   + ("" if ok_save else " [LOI XAC NHAN, thu lai!]"))
            print(msg)
            for w in warns:
                print(" -", w)
        elif key == 27:
            st.cancel()
            st.set_mode("directed")
            tool_mode = "line"
            poly_pts.clear()
            sel_signal = None
            if calib is not None:
                print("Da huy hieu chuan")
            calib = None
            if wizard is not None:
                print("Da huy zone flow")
            wizard = None
            standalone = False
        elif key == 13:
            if tool_mode == "calib":
                if violation is not None and _gate("calib"):
                    continue
                close_calib()
                continue
            action = resolve_enter_action(wizard, tool_mode)
            if action == "wizard_close":
                close_wizard_polygon()
            elif action == "standalone_close":
                if violation is not None:
                    need = ("intersection"
                            if pending_kind == "intersection" else "polygon")
                    if _gate(need):
                        continue
                close_polygon()
        elif key == ord("q"):
            if dirty and not quit_armed:
                msg = "Chua luu! Nhan q lan nua de thoat (s de luu)"
                print(msg)
                quit_armed = True
            else:
                break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

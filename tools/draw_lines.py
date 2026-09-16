"""Tool ve/quan ly virtual lines + polygons, ghi vao camera_config.yaml.
Chay: python tools/draw_lines.py assets/video.mp4 [--config camera_config.yaml]

Chon loi truoc (bat buoc de ve moi):
  1=wrong_way (chi ve line) | 2=no_uturn (polygon+line+pair)
  3=no_entry (polygon banned) | 4=red_light (polygon lane+line+ROI+nga tu)
  5=speeding (polygon+calib) | 0=ve menu tu do (legacy)
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
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.draw_state import DrawState, mode_label, resolve_enter_action  # noqa: E402
from src.draw_menu import (allowed_tools, default_rules, get_mode, menu_text,
                           rules_off, subkey_tool, tools_help,
                           validate_tool)  # noqa: E402
from src.geometry import (allowed_vec, line_near_or_in_polygon,
                          point_in_polygon)  # noqa: E402
from src.homography import build_H  # noqa: E402
from src.line_config import (add_polygon, delete_line, delete_polygon,
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


def draw_all(vis, cfg, pairs, selected, clicks, poly_pts, sel_poly, roi_drag=None, sel_signal=None,
             calib_pts=None, calib_dir=None):
    # Ve hop den giao thong (signals)
    for s in cfg.get("signals", []):
        roi = s.get("roi")
        if roi and len(roi) == 4:
            x1, y1, x2, y2 = [int(v) for v in roi]
            sel = sel_signal is not None and s.get("id") == sel_signal.get("id")
            col = (0, 0, 255) if sel else (0, 255, 255)
            cv2.rectangle(vis, (x1, y1), (x2, y2), col, 3 if sel else 2)
            cv2.putText(vis, f"SIGNAL {s.get('id', '')}", (x1, max(15, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, col, 2)
    # Ve khung ROI dang keo chuot
    if roi_drag and roi_drag.get("p0") is not None:
        p0 = roi_drag["p0"]
        p1 = roi_drag.get("p1") or p0
        xa, xb = sorted([p0[0], p1[0]])
        ya, yb = sorted([p0[1], p1[1]])
        cv2.rectangle(vis, (xa, ya), (xb, yb), (0, 255, 255), 2)

    for p in get_polygons(cfg):
        pts = [(int(x), int(y)) for x, y in (p.get("polygon") or [])]
        if len(pts) >= 3:
            sel = sel_poly is not None and p["id"] == sel_poly["id"]
            if sel:
                col = (0, 0, 255)
            elif p.get("kind") == "banned":
                col = (0, 0, 255)
            elif p.get("kind") == "intersection":
                col = (255, 255, 0)
            else:
                col = (0, 255, 0)
            for a, b in zip(pts, pts[1:] + pts[:1]):
                cv2.line(vis, a, b, col, 3 if sel else 2)
            cv2.putText(vis, f"{p['id']} [{p.get('kind')}]", pts[0],
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    for ln in iter_all_lines(cfg):
        p1 = tuple(int(v) for v in ln["p1"])
        p2 = tuple(int(v) for v in ln["p2"])
        sel = selected is not None and ln["id"] == selected["id"]
        if role_of(ln) == "divider":
            col = (0, 0, 255) if sel else (255, 0, 0)
            cv2.line(vis, p1, p2, col, 3 if sel else 2)
            tag = f"{ln['id']} [med]"
        else:
            col = (0, 0, 255) if sel else (0, 255, 0)
            cv2.line(vis, p1, p2, col, 3 if sel else 2)
            mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
            ax, ay = allowed_vec(ln["p1"], ln["p2"], ln.get("allowed_sign", 1))
            cv2.arrowedLine(vis, (mx, my),
                            (int(mx + ax * ARROW_LEN), int(my + ay * ARROW_LEN)),
                            (0, 255, 255), 2)
            tag = f"{ln['id']} {ln.get('allowed_sign', 1):+d}"
            if ln.get("signal_id"):
                tag += f" [{ln['signal_id']}]"
        cv2.putText(vis, tag, (p1[0], p1[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    for x, y, _ in clicks:
        cv2.circle(vis, (int(x), int(y)), 5, (0, 0, 255), -1)
    for i, (x, y) in enumerate(poly_pts):
        cv2.circle(vis, (int(x), int(y)), 5, (255, 255, 0), -1)
        if i:
            cv2.line(vis, (int(poly_pts[i - 1][0]), int(poly_pts[i - 1][1])),
                     (int(x), int(y)), (255, 255, 0), 2)
    for i, (x, y) in enumerate(calib_pts or []):
        cv2.circle(vis, (int(x), int(y)), 6, (255, 0, 255), -1)
        cv2.putText(vis, f"P{i + 1}", (int(x) + 8, int(y) - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
    if calib_dir and len(calib_dir) == 2:
        (ax, ay), (bx, by) = calib_dir
        cv2.arrowedLine(vis, (int(ax), int(ay)), (int(bx), int(by)),
                        (255, 0, 255), 3)
    y = 30
    for i, p in enumerate(pairs):
        cv2.putText(vis, f"pair{i}: {p['first']}->{p['second']}" + (f" med={p['medial']}" if p.get("medial") else ""),
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 0, 255), 2)
        y += 22
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
        if "--config" in sys.argv else Path("camera_config.yaml")
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
              f"(vd --config camera_config.yaml). Nhan s se tao file moi.")

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
    violation: str | None = None  # None = menu chinh; "1".."5" = loi dang chon
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
        # Gate theo loi dang chon: chan click ve cong cu khong duoc phep
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
                    need = "divider"  # legacy, menu khong cho
            if need is not None:
                ok, why = validate_tool(violation, need)
                if not ok:
                    print(f"Bi chan: {why}")
                    return
        if tool_mode == "calib":
            if ev == cv2.EVENT_LBUTTONDOWN and calib is not None:
                if calib["stage"] == "dir" and len(calib["pts"]) >= 2:
                    return  # du 2 diem huong, Enter de chot
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
                poly_pts.append((x, y))
            return
        if ev == cv2.EVENT_LBUTTONDBLCLK:
            kind, payload = st.on_dblclk(x, y, now)
            if payload is not None:
                sel_poly = None
                sel_signal = None
            else:
                # Thu chon signal truoc (hop den nho thuong nam trong polygon)
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
        """Enter trong wizard phim 1: tao directional polygon ngay,
        chuyen sang ve 2 lines. Tra ve True neu tao."""
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
        """Chot polygon. Menu mode: kind lay tu pending_kind, rules tu dong
        theo loi dang chon. Tra ve pid hoac None."""
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
        # Legacy (khong chon loi): hoi tay nhu cu
        if not in_menu:
            kind = (input("kind [banned/directional/intersection] (mac dinh directional): ")
                    or "directional").strip()
        elif kind is None:
            # Menu nhung khong co pending_kind (vd Enter lac): suy tu loi
            kind = "banned" if violation == "3" else "directional"
        try:
            if kind == "banned":
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
                # Loi 2: tu chuyen sang ve 2 lines trong polygon moi
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
        """Gan rules + lien ket phu sau khi tao polygon trong menu."""
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
        p["rules"] = default_rules(violation)
        if violation == "4":
            active_red_poly = p["id"]
        if violation == "5":
            sel_poly = p  # tu chon de nhan c hieu chuan ngay
        print(f"Da bat rules cho {p['id']}: "
              f"{[r for r, b in p['rules'].items() if b.get('enable')]}")

    def close_calib():
        nonlocal dirty, calib, tool_mode
        """Enter trong mode hieu chuan: pts -> hoi toa do met -> tinh H;
        dir -> chot road_dir. Tra ve True neu xong 1 buoc."""
        from datetime import datetime
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
                from src.homography import build_H
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
        # stage dir
        pts = calib["pts"]
        if len(pts) != 2:
            print(f"Can dung 2 diem huong (dang co {len(pts)}), Esc huy")
            return False
        (ax, ay), (bx, by) = pts
        import math
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
        """True neu dang ve do (clicks/picks/dinh/wizard/calib/roi keo do)."""
        return bool(st.clicks or st.picks or poly_pts
                    or wizard is not None or calib is not None
                    or roi_drag.get("p0") is not None)

    def _need_violation():
        if violation is None:
            msg = "Chua chon loi (nhan 1-5 truoc)"
            print(msg)
            return True
        return False

    def _gate(tool):
        """Chan cong cu khong thuoc loi dang chon. Tra ve True neu chan."""
        ok, why = validate_tool(violation, tool)
        if not ok:
            print(f"Bi chan: {why}")
            return True
        return False

    def _start_polygon_draw(kind):
        """Bat dau ve dinh polygon voi kind ep san (menu)."""
        nonlocal tool_mode, wizard, standalone, pending_kind
        st.cancel()
        poly_pts.clear()
        tool_mode = "polygon"
        wizard = None
        standalone = False
        pending_kind = kind
        label = {"directional": "lane/zone", "banned": "vung cam",
                 "intersection": "vung nga tu"}.get(kind, kind)
        print(f"Ve {label}: click tung dinh -> Enter chot, Esc huy")

    def _start_line_draw():
        nonlocal tool_mode, wizard, standalone
        st.cancel()
        st.set_mode("directed")
        tool_mode = "line"
        wizard = None
        # Loi 1 wrong_way: line doc lap top-level; loi khac gan vao polygon
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
        """Gan signal co san vao line dang chon (phim k, loi 4)."""
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
            # phim w: line wrong_way don, giu top-level (loader tu boc vao
            # __GLOBAL__, rule chay voi moi track)
            assert isinstance(payload, dict), payload
            print(f"Da ve {payload['id']} (wrong_way don, top-level)")
            dirty = True
        elif kind == "line_created":  # tu gan vao polygon chua hoac sat line
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
                                  if calib and calib["stage"] == "dir" else None))
        # Banner dong 1: menu tuy theo loi dang chon (chi hien tool duoc phep)
        if violation is None:
            banner1 = f"{menu_text()} | S=luu Q=thoat"
        else:
            m = get_mode(violation)
            assert m is not None, violation
            banner1 = (f"LOI {m['label']} | tool: "
                       f"{'  '.join(tools_help(violation))} | 0=doi loi S=luu Q=thoat")
        cv2.putText(vis, banner1,
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        sel = st.selected["id"] if st.selected else (
            sel_signal["id"] if sel_signal else (
                sel_poly["id"] if sel_poly else "-"))
        n_lines = len(cfg.get("lines", [])) + sum(
            len(p.get("lines", [])) for p in get_polygons(cfg))
        n_sigs = len(cfg.get("signals", []))
        cv2.putText(vis, f"MODE={'STANDALONE-WW' if standalone else mode_label(wizard, tool_mode, st.mode)} lines={n_lines} "
                         f"poly={len(get_polygons(cfg))} sigs={n_sigs} "
                         f"pairs={len(all_pairs(cfg))} sel={sel} "
                         "| dblclick=chon F=dao chieu X=xoa U=go-den K=gan-den Esc=huy",
                    (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        y0 = 108
        for p in get_polygons(cfg):
            on = [r for r in ("wrong_way", "no_uturn", "no_entry_road", "red_light_running", "stop_line")
                  if (p.get("rules") or {}).get(r, {}).get("enable", True)]
            cv2.putText(vis, f"{p['id']}: {'+'.join(on) if on else 'tat het'}",
                        (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                        (0, 255, 255), 2)
            y0 += 20
            if y0 > frame.shape[0] - 10:
                break
        if msg:
            cv2.putText(vis, msg, (10, 82),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imshow("draw_lines", vis)
        key = cv2.waitKey(20) & 0xFF
        msg = ""
        if key != ord("q"):
            quit_armed = False  # phim khac thi huy trang thai cho-thoat

        kchr = chr(key) if key < 256 else ""
        if kchr in ("1", "2", "3", "4", "5"):
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
                print("Che do tu do (legacy): 1=zone gop w=wrong-way 2=divider "
                      "3=pair 4=polygon 5=ROI c=calib")
            continue
        # --- Che do co chon loi: chi nhan phim con duoc phep ---
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
                    # polygon lane/vung cam tuy loi
                    _start_polygon_draw(
                        "banned" if violation == "3" else "directional")
                elif kchr == "a":
                    _start_pair_mode()
                elif kchr == "r":
                    msg = _start_roi_mode()
                elif kchr == "i":
                    _start_polygon_draw("intersection")
                elif kchr == "c":
                    msg = _start_calib_mode()
                elif kchr == "k":
                    msg = _link_signal()
                    print(msg)
                continue
            elif kchr == "w":
                _m = get_mode(violation)
                assert _m is not None, violation
                msg = (f"Dang o loi {_m['violation']}: "
                       f"dung phim con ({' '.join(tools_help(violation))}), "
                       f"khong dung phim cu 'w' (nhan 0 de ve tu do)")
                print(msg)
                continue
        else:
            # --- Che do tu do legacy (violation is None): giu phim cu ---
            if key == ord("1"):
                st.cancel()
                poly_pts.clear()
                tool_mode = "polygon"
                wizard = {"poly_id": None}  # ve dinh truoc, Enter chot
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
        if False:
            pass
        elif key == ord("f") and st.selected:
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
            # Menu mode: chi 'k' + phai thuoc loi 4; free mode: 'k'/'l' deu duoc
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
            warns = validate(cfg) + validate_polygons(cfg)
            save_config(cfg, cfg_path)
            back = load_config(cfg_path)  # doc lai de xac nhan
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
        elif key == 27:  # Esc: huy sach se ve che do ve line
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
        elif key == 13:  # Enter: re nhanh theo flow hien tai
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

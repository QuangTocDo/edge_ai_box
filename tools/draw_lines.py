"""Tool ve/quan ly virtual lines + polygons, ghi vao camera_config.yaml.
Chay: python tools/draw_lines.py assets/video.mp4 [--config camera_config.yaml]

Che do (nhan phim de doi):
  1 = ve line co chieu: click 2 diem (doi ~0.35s de loai double-click)
      -> tu gan vao polygon chua diem giua (khong thi nam top-level)
  2 = ve divider/medial: click 2 diem
  3 = gan pair U-turn: click lan luot gan 3 lines (first->second->medial)
  4 = ve polygon: click tung dinh -> Enter chot (>=3 dinh),
      roi nhap kind/fields o terminal
Chung:
  double-click = chon line (gan) hoac polygon (trong)
  f = dao chieu line dang chon
  x = xoa line/polygon dang chon (lien quan tu rot)
  s = luu bat cu luc nao (tu doc lai file de xac nhan)
  Esc = huy thao tac do | q = thoat (chua luu phai nhan q 2 lan)
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.draw_state import DrawState  # noqa: E402
from src.geometry import allowed_vec, point_in_polygon  # noqa: E402
from src.line_config import (add_polygon, delete_line, delete_polygon,
                             find_polygon, flip_line, get_polygons,
                             iter_all_lines, load_config, role_of, save_config,
                             validate, validate_polygons)  # noqa: E402

ARROW_LEN = 60


def draw_all(vis, cfg, pairs, selected, clicks, poly_pts, sel_poly):
    for p in get_polygons(cfg):
        pts = [(int(x), int(y)) for x, y in p.get("polygon", [])]
        if len(pts) >= 3:
            sel = sel_poly is not None and p["id"] == sel_poly["id"]
            col = (0, 0, 255) if sel else (
                (0, 0, 255) if p.get("kind") == "banned" else (0, 255, 0))
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
        cv2.putText(vis, tag, (p1[0], p1[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    for x, y, _ in clicks:
        cv2.circle(vis, (int(x), int(y)), 5, (0, 0, 255), -1)
    for i, (x, y) in enumerate(poly_pts):
        cv2.circle(vis, (int(x), int(y)), 5, (255, 255, 0), -1)
        if i:
            cv2.line(vis, (int(poly_pts[i - 1][0]), int(poly_pts[i - 1][1])),
                     (int(x), int(y)), (255, 255, 0), 2)
    y = 30
    for i, p in enumerate(pairs):
        cv2.putText(vis, f"pair{i}: {p['first']}->{p['second']} med={p['medial']}",
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
        print(f"pair pick {payload[0]}/3: {payload[1]}")
    elif kind == "pair_created":
        print(f"Da tao pair {payload}")
        return True
    elif kind == "pair_error":
        print(f"Pair loi: {payload} (lam lai tu dau)")
    elif kind == "pair_miss":
        print("Click gan 1 line da ve (first->second->medial)")
    elif kind == "selected":
        print(f"Da chon {payload}" if payload else "Khong co line gan do")
    return False


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "assets/video.mp4"
    cfg_path = Path(sys.argv[sys.argv.index("--config") + 1]) \
        if "--config" in sys.argv else Path("camera_config.yaml")
    cfg_path = cfg_path.resolve()
    cfg = load_config(cfg_path)
    st = DrawState(cfg)
    n_top = len(cfg.get("lines", []))
    n_nest = sum(len(p.get("lines", [])) for p in get_polygons(cfg))
    print(f"Da nap {n_top + n_nest} lines ({len(get_polygons(cfg))} polygons), "
          f"{len(cfg['uturn_pairs'])} pairs tu {cfg_path}")

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
    poly_pts, sel_poly = [], None

    def on_mouse(ev, x, y, *_):
        nonlocal dirty, sel_poly
        now = time.monotonic()
        if tool_mode == "polygon":
            if ev == cv2.EVENT_LBUTTONDOWN:
                poly_pts.append((x, y))
            return
        if ev == cv2.EVENT_LBUTTONDBLCLK:
            kind, payload = st.on_dblclk(x, y, now)
            if payload is None:  # khong trung line -> thu chon polygon
                for p in get_polygons(cfg):
                    if point_in_polygon((x, y), p.get("polygon", [])):
                        sel_poly = p
                        print(f"Da chon polygon {p['id']}")
                        break
                else:
                    sel_poly = None
                    print("Khong co line/polygon gan do")
            else:
                sel_poly = None
            dirty |= handle_action(kind, payload, st)
        elif ev == cv2.EVENT_LBUTTONDOWN:
            dirty |= handle_action(*st.on_down(x, y, now), st)

    def close_polygon():
        """Chot polygon tu poly_pts, hoi fields o terminal. Tra ve True neu tao."""
        nonlocal dirty
        if len(poly_pts) < 3:
            print(f"Can >=3 dinh (dang co {len(poly_pts)})")
            return False
        kind = (input("kind [banned/directional] (mac dinh banned): ")
                or "banned").strip()
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
            else:
                p = add_polygon(cfg, poly_pts, kind="directional")
            print(f"Da tao polygon {p['id']} [{p['kind']}]")
            poly_pts.clear()
            dirty = True
            return True
        except (ValueError, TypeError) as e:
            print(f"Polygon loi: {e} (giua lai dinh de sua)")
            return False

    cv2.namedWindow("draw_lines")
    cv2.setMouseCallback("draw_lines", on_mouse)
    while True:
        kind, payload = st.poll(time.monotonic())
        if kind == "line_created":  # tu gan vao polygon chua diem giua
            mx = (payload["p1"][0] + payload["p2"][0]) / 2
            my = (payload["p1"][1] + payload["p2"][1]) / 2
            for p in get_polygons(cfg):
                if point_in_polygon((mx, my), p.get("polygon", [])):
                    cfg["lines"].remove(payload)
                    p.setdefault("lines", []).append(payload)
                    print(f"Da ve {payload['id']} -> gan vao {p['id']}")
                    break
            else:
                print(f"Da ve {payload['id']} ({st.mode}, top-level)")
            dirty = True
        elif kind is not None:
            dirty |= handle_action(kind, payload, st)
        vis = draw_all(frame.copy(), cfg, cfg["uturn_pairs"],
                       st.selected, st.clicks, poly_pts, sel_poly)
        cv2.putText(vis, "mode: 1=line chieu  2=divider  3=pair  4=polygon | S=luu  Q=thoat",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        sel = st.selected["id"] if st.selected else (
            sel_poly["id"] if sel_poly else "-")
        n_lines = len(cfg.get("lines", [])) + sum(
            len(p.get("lines", [])) for p in get_polygons(cfg))
        cv2.putText(vis, f"MODE={tool_mode}/{st.mode} lines={n_lines} "
                         f"poly={len(get_polygons(cfg))} "
                         f"pairs={len(cfg['uturn_pairs'])} sel={sel} "
                         "| dblclick=chon F=dao chieu X=xoa Esc=huy",
                    (10, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        if msg:
            cv2.putText(vis, msg, (10, 82),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imshow("draw_lines", vis)
        key = cv2.waitKey(20) & 0xFF
        msg = ""
        if key != ord("q"):
            quit_armed = False  # phim khac thi huy trang thai cho-thoat

        if key == ord("1"):
            st.set_mode("directed")
            tool_mode = "line"
        elif key == ord("2"):
            st.set_mode("divider")
            tool_mode = "line"
        elif key == ord("3"):
            st.set_mode("pair")
            tool_mode = "line"
            print("Pair mode: click 3 lines (first->second->medial)")
        elif key == ord("4"):
            st.cancel()
            tool_mode = "polygon"
            print("Polygon mode: click tung dinh -> Enter chot, Esc huy")
        elif key == ord("f") and st.selected:
            try:
                msg = f"{st.selected['id']} sign=" \
                      f"{flip_line(cfg, st.selected['id']):+d}"
                dirty = True
            except ValueError as e:
                msg = str(e)
        elif key in (ord("x"), 127) and (st.selected or sel_poly):
            if st.selected:
                ln, dropped = delete_line(cfg, st.selected["id"])
                msg = (f"Da xoa {ln['id']}" +
                       (f" (+rot {len(dropped)} pair)" if dropped else ""))
                st.selected = None
            else:
                poly, dropped = delete_polygon(cfg, sel_poly["id"])
                msg = (f"Da xoa polygon {poly['id']} "
                       f"(+{len(poly.get('lines', []))} lines con, "
                       f"{len(dropped)} pair)")
                sel_poly = None
            print(msg)
            dirty = True
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
                   f"{now_ids[1]} pairs + {now_ids[2]} polygons -> {cfg_path}"
                   + ("" if ok_save else " [LOI XAC NHAN, thu lai!]"))
            print(msg)
            for w in warns:
                print(" -", w)
        elif key == 27:  # Esc
            st.cancel()
            poly_pts.clear()
        elif key == 13:  # Enter: chot polygon
            if tool_mode == "polygon":
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

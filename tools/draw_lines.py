"""Tool ve/quan ly virtual lines tu do, ghi vao camera_config.yaml.
Chay: python tools/draw_lines.py assets/video.mp4 [--config camera_config.yaml]

Che do (nhan phim de doi):
  1 = ve line co chieu: click 2 diem (doi ~0.35s de loai double-click)
  2 = ve divider/medial: click 2 diem
  3 = gan pair U-turn: click lan luot gan 3 lines (first->second->medial)
Chung:
  double-click gan line = chon | f = dao chieu line dang chon
  x = xoa line dang chon (pair lien quan tu rot)
  s = luu bat cu luc nao (tu doc lai file de xac nhan)
  Esc = huy thao tac do | q = thoat (chua luu phai nhan q 2 lan)
"""
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.draw_state import DrawState  # noqa: E402
from src.geometry import allowed_vec  # noqa: E402
from src.line_config import (delete_line, flip_line, load_config, role_of,
                             save_config, validate)  # noqa: E402

ARROW_LEN = 60


def draw_all(vis, lines, pairs, selected, clicks):
    for ln in lines:
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
    print(f"Da nap {len(cfg['lines'])} lines, {len(cfg['uturn_pairs'])} pairs "
          f"tu {cfg_path}")

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

    def on_mouse(ev, x, y, *_):
        nonlocal dirty
        now = time.monotonic()
        if ev == cv2.EVENT_LBUTTONDBLCLK:
            dirty |= handle_action(*st.on_dblclk(x, y, now), st)
        elif ev == cv2.EVENT_LBUTTONDOWN:
            dirty |= handle_action(*st.on_down(x, y, now), st)

    cv2.namedWindow("draw_lines")
    cv2.setMouseCallback("draw_lines", on_mouse)
    while True:
        dirty |= handle_action(*st.poll(time.monotonic()), st)
        vis = draw_all(frame.copy(), cfg["lines"], cfg["uturn_pairs"],
                       st.selected, st.clicks)
        cv2.putText(vis, "mode: 1=line chieu  2=divider  3=pair U-turn | S=luu  Q=thoat",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        sel = st.selected["id"] if st.selected else "-"
        cv2.putText(vis, f"MODE={st.mode} lines={len(cfg['lines'])} "
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
        elif key == ord("2"):
            st.set_mode("divider")
        elif key == ord("3"):
            st.set_mode("pair")
            print("Pair mode: click 3 lines (first->second->medial)")
        elif key == ord("f") and st.selected:
            try:
                msg = f"{st.selected['id']} sign=" \
                      f"{flip_line(cfg, st.selected['id']):+d}"
                dirty = True
            except ValueError as e:
                msg = str(e)
        elif key in (ord("x"), 127) and st.selected:
            ln, dropped = delete_line(cfg, st.selected["id"])
            msg = (f"Da xoa {ln['id']}" +
                   (f" (+rot {len(dropped)} pair)" if dropped else ""))
            print(msg)
            st.selected = None
            dirty = True
        elif key == ord("s"):
            warns = validate(cfg)
            save_config(cfg, cfg_path)
            back = load_config(cfg_path)  # doc lai de xac nhan
            ok_save = ({l["id"] for l in back["lines"]},
                       len(back["uturn_pairs"])) == \
                      ({l["id"] for l in cfg["lines"]}, len(cfg["uturn_pairs"]))
            dirty = False
            msg = (f"Da luu {len(back['lines'])} lines + "
                   f"{len(back['uturn_pairs'])} pairs -> {cfg_path}"
                   + ("" if ok_save else " [LOI XAC NHAN, thu lai!]"))
            print(msg)
            for w in warns:
                print(" -", w)
        elif key == 27:  # Esc
            st.cancel()
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

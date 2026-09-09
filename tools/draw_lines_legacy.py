"""Tool ve virtual line bang click chuot, ghi vao camera_config.yaml.
Chay: python tools/draw_lines.py video.mp4
Click theo thu tu: 2 diem L_NB -> 2 diem L_SB -> 2 diem L_medial (divider).
Phim: f = dao chieu line vua ve | z = undo | s = luu | q = thoat
Mui ten vang = huong cho phep (allowed_sign). Sai thi nhan f.
"""
import sys
from pathlib import Path

import cv2
import yaml

ORDER = [("L_NB", None), ("L_SB", None), ("L_medial", "divider")]


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "assets/video.mp4"
    cfg_path = Path("camera_config.yaml")
    cfg = yaml.safe_load(open(cfg_path)) if cfg_path.exists() else {"lines": []}

    cap = cv2.VideoCapture(src if not src.isdigit() else int(src))
    ok, frame = cap.read()
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 1)
    if n > 1:  # lay frame giua video de ve
        cap.set(cv2.CAP_PROP_POS_FRAMES, n // 3)
        ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"Khong doc duoc frame tu: {src}")

    drawn = []  # (id, p1, p2, role, allowed_sign)
    clicks = []

    def on_mouse(ev, x, y, *_):
        if ev == cv2.EVENT_LBUTTONDOWN and len(drawn) < len(ORDER):
            clicks.append((x, y))

    cv2.namedWindow("draw_lines")
    cv2.setMouseCallback("draw_lines", on_mouse)
    print("Click 2 diem cho", ORDER[0][0])
    while True:
        vis = frame.copy()
        for i, (lid, p1, p2, role, s) in enumerate(drawn):
            col = (255, 0, 0) if role else (0, 255, 0)
            cv2.line(vis, p1, p2, col, 2)
            cv2.putText(vis, f"{lid} sign={s:+d}", (p1[0], p1[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        for x, y in clicks:
            cv2.circle(vis, (x, y), 5, (0, 0, 255), -1)
        if len(drawn) < len(ORDER):
            cv2.putText(vis, f"Click 2 diem: {ORDER[len(drawn)][0]} "
                             "(f=dao chieu, z=undo, s=luu, q=thoat)",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(vis, "Du 3 lines (s=luu, z=undo, q=thoat)", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imshow("draw_lines", vis)
        key = cv2.waitKey(20) & 0xFF

        if len(clicks) == 2 and len(drawn) < len(ORDER):
            lid, role = ORDER[len(drawn)]
            drawn.append((lid, clicks[0], clicks[1], role, 1))
            clicks = []
            print(f"Da ve {lid}, sign=+1 (sai huong thi nhan f)")
        if key == ord("f") and drawn:
            lid, p1, p2, role, s = drawn[-1]
            drawn[-1] = (lid, p1, p2, role, -s)
            print(f"{lid} sign={-s:+d}")
        elif key == ord("z"):
            if clicks:
                clicks.pop()
            elif drawn:
                print("Bo", drawn.pop()[0])
        elif key == ord("s"):
            if len(drawn) < len(ORDER):
                print("Chua du 3 lines!")
                continue
            cfg["lines"] = [
                {"id": lid, "p1": list(p1), "p2": list(p2),
                 **({"role": role} if role else {}),
                 **({} if role else {"allowed_sign": s})}
                for lid, p1, p2, role, s in drawn
            ]
            cfg.setdefault("uturn_pairs", [
                {"first": "L_NB", "second": "L_SB", "medial": "L_medial"}])
            with open(cfg_path, "w") as f:
                yaml.safe_dump(cfg, f, sort_keys=False)
            print(f"Da luu vao {cfg_path}")
        elif key in (ord("q"), 27):
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

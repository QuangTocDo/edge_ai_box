"""Xem anh kem labels YOLO (bbox + id + ten class).

Chay 1 anh:
  python tools/show_yolo_labels.py data_v2/train/images/<anh>.jpg
Chay ca thu muc (n/p chuyen anh, q thoat):
  python tools/show_yolo_labels.py --dir data_v2/train --limit 50
Luu ra file thay vi hien (headless):
  python tools/show_yolo_labels.py --dir data_v2/val --save /tmp/yolo_view --limit 20
Chi dinh data.yaml de lay ten class:
  python tools/show_yolo_labels.py --dir data_v2/train --data data_v2/data.yaml
"""
import argparse
import sys
from pathlib import Path

import cv2
import yaml

COLORS = [(0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255),
          (255, 0, 255), (255, 255, 0), (0, 128, 255), (128, 0, 255),
          (0, 200, 100), (200, 100, 0)]


def load_names(data_yaml):
    if not data_yaml:
        return []
    try:
        d = yaml.safe_load(Path(data_yaml).read_text(encoding="utf-8")) or {}
        names = d.get("names", [])
        if isinstance(names, dict):
            return [names[k] for k in sorted(names)]
        return list(names)
    except OSError:
        return []


def read_labels(txt_path, img_w, img_h):
    boxes = []
    try:
        lines = txt_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return boxes
    for line in lines:
        p = line.split()
        if len(p) < 5:
            continue
        try:
            cls = int(float(p[0]))
            cx, cy, bw, bh = (float(v) for v in p[1:5])
        except ValueError:
            continue
        x1, y1 = int((cx - bw / 2) * img_w), int((cy - bh / 2) * img_h)
        x2, y2 = int((cx + bw / 2) * img_w), int((cy + bh / 2) * img_h)
        boxes.append((cls, x1, y1, x2, y2))
    return boxes


def draw(img_path, names):
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"Khong doc duoc anh: {img_path}")
        return None
    h, w = img.shape[:2]
    txt = img_path.with_suffix(".txt")
    alt = Path(str(img_path).replace("/images/", "/labels/")).with_suffix(".txt")
    for cand in (txt, alt):
        if cand.is_file():
            txt = cand
            break
    boxes = read_labels(txt, w, h) if txt.is_file() else []
    for cls, x1, y1, x2, y2 in boxes:
        color = COLORS[cls % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = f"{cls}:{names[cls]}" if 0 <= cls < len(names) else str(cls)
        cv2.putText(img, label, (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.putText(img, f"{img_path.name} [{len(boxes)} box]",
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return img


def main(argv=None):
    ap = argparse.ArgumentParser(description="Xem anh kem labels YOLO")
    ap.add_argument("image", nargs="?", default="",
                    help="file anh don (mac dinh doc --dir)")
    ap.add_argument("--dir", default="",
                    help="thu muc images (tu tim labels canh ben)")
    ap.add_argument("--data", default="",
                    help="data.yaml de lay ten class")
    ap.add_argument("--save", default="",
                    help="luu anh ve ra thu muc nay thay vi hien")
    ap.add_argument("--limit", type=int, default=0,
                    help="gioi han so anh (0 = het)")
    args = ap.parse_args(argv)

    names = load_names(args.data)
    if args.image:
        paths = [Path(args.image)]
    else:
        if not args.dir:
            print("Truyen file anh hoac --dir", file=sys.stderr)
            return 2
        root = Path(args.dir)
        sub = root / "images"
        if sub.is_dir():
            root = sub  # kieu data_v2/{train,val}/images
        paths = sorted(root.glob("*.*"))
        paths = [p for p in paths
                 if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp")]
        if args.limit > 0:
            paths = paths[:args.limit]
    if not paths:
        print("Khong thay anh nao", file=sys.stderr)
        return 2

    if args.save:
        out = Path(args.save)
        out.mkdir(parents=True, exist_ok=True)
        for p in paths:
            img = draw(p, names)
            if img is not None:
                cv2.imwrite(str(out / p.name), img)
        print(f"Da luu {len(paths)} anh vao {out}")
        return 0

    idx = 0
    total = len(paths)
    print("Duyet thu muc: a/d = truoc/ke tiep, x = xoa anh+label, q = thoat")
    win = "yolo view (a/d=chuyen, x=xoa, q=thoat)"
    while paths:
        total = len(paths)
        idx %= total
        img = draw(paths[idx], names)
        if img is None:
            idx = (idx + 1) % total
            continue
        cv2.putText(img, f"[{idx + 1}/{total}]", (10, 58),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow(win, img)
        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("d"):
            idx = (idx + 1) % total
        elif key == ord("a"):
            idx = (idx - 1) % total
        elif key == ord("x"):
            gone = paths.pop(idx)
            removed = []
            for cand in (gone, gone.with_suffix(".txt"),
                         Path(str(gone).replace("/images/", "/labels/")).with_suffix(".txt")):
                try:
                    if cand.is_file():
                        cand.unlink()
                        removed.append(cand.name)
                except OSError as e:
                    print(f"Xoa loi {cand}: {e}")
            print(f"Da xoa: {gone.name}" + (f" + {', '.join(removed[1:])}" if len(removed) > 1 else ""))
            if not paths:
                print("Het anh.")
                break
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

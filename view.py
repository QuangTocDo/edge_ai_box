"""Show anh + bounding box YOLO. Chay:
  python view.py data_v1/images/train
  python view.py data_v1/images/val --save out/
Phim: -> / Space = tiep, <- = lui, s = luu anh, q = thoat
"""
import sys
from pathlib import Path

import cv2

COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255),
    (255, 0, 255), (255, 255, 0), (0, 128, 255), (128, 0, 255),
]


def load_boxes(txt_path, img_w, img_h):
    """Doc file txt YOLO: class cx cy w h [conf] -> (cls, x1, y1, x2, y2, conf)."""
    boxes = []
    if not txt_path.exists():
        return boxes
    for line in txt_path.read_text().splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        cls, cx, cy, w, h = int(float(p[0])), *[float(x) for x in p[1:5]]
        conf = float(p[5]) if len(p) > 5 else None
        x1 = int((cx - w / 2) * img_w)
        y1 = int((cy - h / 2) * img_h)
        x2 = int((cx + w / 2) * img_w)
        y2 = int((cy + h / 2) * img_h)
        boxes.append((cls, x1, y1, x2, y2, conf))
    return boxes


def draw(img, boxes, names):
    for cls, x1, y1, x2, y2, conf in boxes:
        color = COLORS[cls % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        label = names[cls] if cls < len(names) else f"class {cls}"
        if conf is not None:
            label += f" {conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return img


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data_v1/images/train")
    save_dir = Path(sys.argv[sys.argv.index("--save") + 1]) if "--save" in sys.argv else None
    names_file = Path(sys.argv[sys.argv.index("--names") + 1]) if "--names" in sys.argv else None
    names = names_file.read_text().splitlines() if names_file and names_file.exists() else []

    imgs = sorted([p for p in folder.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    if not imgs:
        raise SystemExit(f"Khong thay anh trong: {folder}")
    print(f"Tim thay {len(imgs)} anh trong {folder}")

    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    i = 0
    while 0 <= i < len(imgs):
        img = cv2.imread(str(imgs[i]))
        if img is None:
            print(f"Khong doc duoc: {imgs[i].name}")
            i += 1
            continue
        h, w = img.shape[:2]
        boxes = load_boxes(imgs[i].with_suffix(".txt"), w, h)
        img = draw(img, boxes, names)
        cv2.putText(img, f"{i+1}/{len(imgs)} {imgs[i].name} ({len(boxes)} boxes)",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        if save_dir:
            cv2.imwrite(str(save_dir / imgs[i].name), img)
            print(f"[{i+1}/{len(imgs)}] {imgs[i].name}: {len(boxes)} boxes")
            i += 1
            continue

        cv2.imshow("YOLO viewer", img)
        key = cv2.waitKey(0) & 0xFF
        if key in (ord("q"), 27):
            break
        elif key == ord("s"):
            cv2.imwrite(f"vis_{imgs[i].name}", img)
            print(f"Da luu vis_{imgs[i].name}")
        elif key == 81:  # mui trai
            i = max(0, i - 1)
        else:  # mui phai / space / enter
            i += 1

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

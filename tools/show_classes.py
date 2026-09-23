"""Xuat 8 anh mau, moi anh chua 1 class 0-7. Chay:
  python tools/show_classes.py              -> luu vao assets/class_samples/
  python tools/show_classes.py --show       -> vua luu vua hien thi
"""
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data_v2"
OUT = ROOT / "assets/class_samples"
COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255),
    (255, 0, 255), (255, 255, 0), (0, 128, 255), (128, 0, 255),
]


def find_one_per_class():
    """Tim txt dau tien chua moi class 0-7 -> {cls: txt_path}."""
    found = {}
    for split in ("train", "val", "test"):
        for txt in sorted((DATA / "labels" / split).glob("*.txt")):
            for line in txt.read_text().splitlines():
                p = line.split()
                if p and p[0] not in found:
                    found[p[0]] = (split, txt)
                    if len(found) == 8:
                        return found
    return found


def draw(img, txt_path, target):
    h, w = img.shape[:2]
    n_target = 0
    for line in txt_path.read_text().splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        cls = int(float(p[0]))
        cx, cy, bw, bh = (float(x) for x in p[1:5])
        x1, y1 = int((cx - bw / 2) * w), int((cy - bh / 2) * h)
        x2, y2 = int((cx + bw / 2) * w), int((cy + bh / 2) * h)
        is_target = cls == target
        n_target += is_target
        color = COLORS[cls % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 3 if is_target else 1)
        label = f"class {cls}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return img, n_target


def main():
    show = "--show" in sys.argv
    OUT.mkdir(exist_ok=True)
    found = find_one_per_class()
    missing = [str(c) for c in range(8) if str(c) not in found]
    if missing:
        print(f"Canh bao: khong thay anh cho class {missing}")

    for cls in range(8):
        key = str(cls)
        if key not in found:
            continue
        split, txt = found[key]
        img_path = DATA / "images" / split / (txt.stem + ".jpg")
        img = cv2.imread(str(img_path))
        if img is None:  # thu png neu jpg khong co
            img_path = img_path.with_suffix(".png")
            img = cv2.imread(str(img_path))
        if img is None:
            print(f"class {cls}: khong doc duoc {txt.stem}")
            continue
        img, n = draw(img, txt, cls)
        out = OUT / f"class_{cls}.jpg"
        cv2.imwrite(str(out), img)
        print(f"class {cls}: {img_path.name} ({split}, {n} box class {cls}) -> {out}")
        if show:
            cv2.imshow(f"class {cls}", img)
            if cv2.waitKey(0) & 0xFF in (ord("q"), 27):
                break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

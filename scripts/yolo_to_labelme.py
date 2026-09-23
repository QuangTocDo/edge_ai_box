"""YOLO txt -> JSON X-AnyLabeling (labelme) dat canh anh.

De mo trong X-AnyLabeling xem/sua/them label. Dung format giong file mau
cua user: imageData null, 10 keys/shape, rectangle 4 diem.

Chay:
  python scripts/yolo_to_labelme.py --split train
  python scripts/yolo_to_labelme.py --all
  python scripts/yolo_to_labelme.py --all --dry-run   # chi dem
  python scripts/yolo_to_labelme.py --all --overwrite # ghi de ca JSON tay (can than)

Mac dinh BO QUA file da co JSON thu cong. Map: 8->pedestrian + 0-7 ten xe v1.
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "pedestrian.v3i.yolov8"
SPLITS = ["train", "valid", "test"]

NAMES = {
    0: "motorbike_day", 1: "car_day", 2: "bus_day", 3: "truck_day",
    4: "motorbike_night", 5: "car_night", 6: "bus_night", 7: "truck_night",
    8: "pedestrian",
}


def convert_split(split, dry_run=False, overwrite=False):
    import cv2
    img_dir = DATA / split / "images"
    imgs = sorted([p for p in img_dir.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    n_new = n_skip = n_box = n_noimg = 0
    for img in imgs:
        js = img.with_suffix(".json")
        if js.is_file() and not overwrite:
            n_skip += 1
            continue
        txt = img.with_suffix(".txt")
        if not txt.is_file():
            txt = DATA / split / "labels" / (img.stem + ".txt")
            if not txt.is_file():
                n_noimg += 1
                continue
        im = cv2.imread(str(img))
        if im is None:
            n_noimg += 1
            continue
        ih, iw = im.shape[:2]
        shapes = []
        for line in txt.read_text().splitlines():
            p = line.split()
            if len(p) < 5:
                continue
            try:
                cls = int(float(p[0]))
                cx, cy, bw, bh = (float(v) for v in p[1:5])
            except ValueError:
                continue
            if cls not in NAMES:
                print(f"Bo id la {cls} trong {txt.name}")
                continue
            x1, y1 = (cx - bw / 2) * iw, (cy - bh / 2) * ih
            x2, y2 = (cx + bw / 2) * iw, (cy + bh / 2) * ih
            shapes.append({
                "label": NAMES[cls],
                "score": 1.0,
                "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                "group_id": None,
                "description": "",
                "difficult": False,
                "shape_type": "rectangle",
                "flags": {},
                "attributes": {},
                "kie_linking": [],
            })
        if not dry_run:
            js.write_text(json.dumps({
                "version": "4.0.6",
                "flags": {},
                "checked": False,
                "shapes": shapes,
                "imagePath": img.name,
                "imageData": None,
                "imageHeight": ih,
                "imageWidth": iw,
            }, ensure_ascii=False), encoding="utf-8")
        n_new += 1
        n_box += len(shapes)
    return n_new, n_box, n_skip, n_noimg, len(imgs)


def main(argv=None):
    ap = argparse.ArgumentParser(description="YOLO txt -> JSON X-AnyLabeling")
    ap.add_argument("--split", default="train", choices=SPLITS + ["all"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true",
                    help="ghi de ca JSON thu cong (can than)")
    args = ap.parse_args(argv)

    splits = SPLITS if (args.all or args.split == "all") else [args.split]
    for s in splits:
        n_new, n_box, n_skip, n_noimg, total = convert_split(
            s, dry_run=args.dry_run, overwrite=args.overwrite)
        print(f"[{s}] {total} anh -> JSON moi {n_new} (+{n_box} shapes), "
              f"bo qua tay {n_skip}, thieu txt {n_noimg}"
              + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

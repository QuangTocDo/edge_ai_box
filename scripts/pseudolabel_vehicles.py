"""Pseudo-label XE bang best_15thg9.pt cho pedestrian.v3i.yolov8.

THEM box xe (id nguyen ban model 0-7, khong tach day/night) vao txt hien co
(giu box person id 8). Khong ghi de, khong xoa.

Chay:
  python scripts/pseudolabel_vehicles.py --all
  python scripts/pseudolabel_vehicles.py --split valid --conf 0.5 --dry-run

Mac dinh: model=weights/best_15thg9.pt, classes=[0..7], conf=0.5,
iou=0.5, imgsz=1280. Backup labels truoc: labels_prevehicle_backup/.
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "pedestrian.v3i.yolov8"
SPLITS = ["train", "valid", "test"]
VEHICLE_CLASSES = list(range(8))


def run_split(model, split, conf, iou, imgsz, dry_run):
    img_dir = DATA / split / "images"
    lbl_dir = DATA / split / "labels"
    imgs = sorted([p for p in img_dir.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    n_img = n_box = 0
    for img in imgs:
        res = model.predict(str(img), classes=VEHICLE_CLASSES, conf=conf,
                            iou=iou, imgsz=imgsz, verbose=False)[0]
        lines = []
        if res.boxes is not None:
            for b in res.boxes:
                cls = int(b.cls[0].item())
                cx, cy, bw, bh = (float(v) for v in b.xywhn[0].tolist())
                if bw <= 0 or bh <= 0:
                    continue
                lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        if not lines:
            continue
        if not dry_run:
            old = []
            txt = lbl_dir / (img.stem + ".txt")
            if txt.is_file():
                old = [l for l in txt.read_text().splitlines() if l.strip()]
            txt.write_text("\n".join(old + lines) + "\n")
        n_img += 1
        n_box += len(lines)
    return n_img, n_box, len(imgs)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Them pseudo-label xe id 0-7 vao v3i")
    ap.add_argument("--model", default=str(REPO / "weights" / "best_15thg9.pt"))
    ap.add_argument("--split", default="train", choices=SPLITS + ["all"])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--conf", type=float, default=0.5)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    splits = SPLITS if (args.all or args.split == "all") else [args.split]
    bak = DATA / "labels_prevehicle_backup"
    if not args.dry_run and not bak.is_dir():
        print("CANH BAO: chua backup labels! Chay backup truoc.", file=sys.stderr)
        return 2

    from ultralytics import YOLO
    model = YOLO(args.model)
    for s in splits:
        n_img, n_box, total = run_split(
            model, s, args.conf, args.iou, args.imgsz, args.dry_run)
        print(f"[{s}] {total} anh -> them box xe cho {n_img} anh, "
              f"+{n_box} box 0-7" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

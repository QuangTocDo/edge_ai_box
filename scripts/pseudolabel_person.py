"""Pseudo-label person bang yolo26n.pt cho pedestrian.v3i.yolov8.

Ghi de labels/*.txt bang 1 class duy nhat (id 8 = pedestrian, dong bo data_v2).
Labels goc PHAl backup truoc (labels_orig_backup/) vi ghi de la mat vinh vien.

Chay:
  python scripts/pseudolabel_person.py --split train            # 1 split
  python scripts/pseudolabel_person.py --all                    # train+valid+test
  python scripts/pseudolabel_person.py --all --conf 0.5 --dry-run  # thu khong ghi

Mac dinh: model=weights/yolo26n.pt, classes=[0] (person COCO), conf=0.7,
iou=0.5, imgsz=1280, out_id=8.
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "pedestrian.v3i.yolov8"
SPLITS = ["train", "valid", "test"]


def run_split(model, split, out_id, conf, iou, imgsz, dry_run):
    from ultralytics import YOLO  # noqa
    img_dir = DATA / split / "images"
    lbl_dir = DATA / split / "labels"
    imgs = sorted([p for p in img_dir.iterdir()
                   if p.suffix.lower() in (".jpg", ".jpeg", ".png")])
    n_img = n_box = n_empty = 0
    for img in imgs:
        res = model.predict(str(img), classes=[0], conf=conf, iou=iou,
                            imgsz=imgsz, verbose=False)[0]
        lines = []
        if res.boxes is not None:
            h, w = res.boxes.orig_shape
            for b in res.boxes:
                cx, cy, bw, bh = (float(v) for v in b.xywhn[0].tolist())
                if bw <= 0 or bh <= 0:
                    continue
                lines.append(f"{out_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        if not lines:
            n_empty += 1
            continue
        if not dry_run:
            (lbl_dir / (img.stem + ".txt")).write_text("\n".join(lines) + "\n")
        n_img += 1
        n_box += len(lines)
    return n_img, n_box, n_empty, len(imgs)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pseudo-label person id 8 bang yolo26n.pt")
    ap.add_argument("--model", default=str(REPO / "weights" / "yolo26n.pt"))
    ap.add_argument("--split", default="train", choices=SPLITS + ["all"])
    ap.add_argument("--all", action="store_true", help="chay train+valid+test")
    ap.add_argument("--out-id", type=int, default=8)
    ap.add_argument("--conf", type=float, default=0.7)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--dry-run", action="store_true", help="chi dem, khong ghi")
    args = ap.parse_args(argv)

    splits = SPLITS if (args.all or args.split == "all") else [args.split]
    bak = DATA / "labels_orig_backup"
    if not args.dry_run and not bak.is_dir():
        print("CANH BAO: chua backup labels goc! Chay backup truoc.", file=sys.stderr)
        return 2

    from ultralytics import YOLO
    model = YOLO(args.model)
    for s in splits:
        n_img, n_box, n_empty, total = run_split(
            model, s, args.out_id, args.conf, args.iou, args.imgsz, args.dry_run)
        print(f"[{s}] {total} anh -> {n_img} anh co box, {n_box} box id{args.out_id}, "
              f"{n_empty} anh trang" + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

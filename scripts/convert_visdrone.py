"""Convert VisDrone DET annotations -> YOLO txt cho data_v2 (person only).

Quy tac chot:
- Chi class 0 (pedestrian) + 1 (people) -> id 8 (khong dung id v1 0-7).
- Bo dong score=0 (vung ignore).
- Loc rider: bo box person nam gon >=80% trong box motor/bicycle cung anh.
- Ghi sang data_v2/{split}/{images,labels}/, khong dung archive/data_v1.
- Split dung san: train/val/test-dev (test-challenge khong label -> bo).

Chay: python scripts/convert_visdrone.py [--check-only]
"""
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARCH = REPO / "archive"
OUT = REPO / "data_v2"
PERSON_ID = 8
# VisDrone class can lay / bo (chi giu 0,1)
KEEP = {0, 1}
# class xe 2 banh de loc rider chong lap (motor=9, bicycle=2)
RIDER_HOSTS = {2, 9}
OVERLAP_THRESH = 0.8

SPLITS = {
    "train": "VisDrone2019-DET-train/VisDrone2019-DET-train",
    "val": "VisDrone2019-DET-val/VisDrone2019-DET-val",
    "test": "VisDrone2019-DET-test-dev/VisDrone2019-DET-test-dev",
}


def parse_line(line):
    p = line.strip().replace(",", " ").split()
    if len(p) < 6:
        return None
    try:
        x, y, w, h = float(p[0]), float(p[1]), float(p[2]), float(p[3])
        score, cls = float(p[4]), int(float(p[5]))
    except ValueError:
        return None
    return x, y, w, h, score, cls


def inside_ratio(inner, outer):
    ix1 = max(inner[0], outer[0])
    iy1 = max(inner[1], outer[1])
    ix2 = min(inner[0] + inner[2], outer[0] + outer[2])
    iy2 = min(inner[1] + inner[3], outer[1] + outer[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = max(1.0, inner[2] * inner[3])
    return inter / area


def convert_split(split, src_dir, check_only=False):
    import cv2
    img_dir = src_dir / "images"
    ann_dir = src_dir / "annotations"
    out_img = OUT / split / "images"
    out_lbl = OUT / split / "labels"
    if not check_only:
        out_img.mkdir(parents=True, exist_ok=True)
        out_lbl.mkdir(parents=True, exist_ok=True)
    n_img = n_person = n_rider_drop = n_empty = 0
    ann_files = sorted(ann_dir.glob("*.txt"))
    for ann in ann_files:
        stem = ann.stem
        img = None
        for ext in (".jpg", ".png", ".jpeg"):
            cand = img_dir / (stem + ext)
            if cand.is_file():
                img = cand
                break
        if img is None:
            continue
        boxes, hosts = [], []
        for line in ann.read_text(errors="ignore").splitlines():
            r = parse_line(line)
            if r is None:
                continue
            x, y, w, h, score, cls = r
            if score <= 0:
                continue
            if cls in KEEP:
                boxes.append((x, y, w, h))
            elif cls in RIDER_HOSTS:
                hosts.append((x, y, w, h))
        # loc rider: person nam gon trong motor/bicycle
        kept = [b for b in boxes
                if not any(inside_ratio(b, hb) >= OVERLAP_THRESH for hb in hosts)]
        n_rider_drop += len(boxes) - len(kept)
        im = cv2.imread(str(img))
        if im is None:
            continue
        ih, iw = im.shape[:2]
        lines = []
        for (x, y, w, h) in kept:
            cx, cy = (x + w / 2) / iw, (y + h / 2) / ih
            bw, bh = w / iw, h / ih
            if bw <= 0 or bh <= 0:
                continue
            lines.append(f"{PERSON_ID} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        if not lines:
            n_empty += 1
            continue
        if not check_only:
            shutil.copy2(img, out_img / img.name)
            (out_lbl / (stem + ".txt")).write_text("\n".join(lines) + "\n")
        n_img += 1
        n_person += len(lines)
    return {"images": n_img, "boxes": n_person,
            "rider_dropped": n_rider_drop, "empty": n_empty,
            "total_ann": len(ann_files)}


def main():
    check_only = "--check-only" in sys.argv
    print(f"archive: {ARCH}")
    total = {}
    for split, rel in SPLITS.items():
        src = ARCH / rel
        if not src.is_dir():
            print(f"[{split}] thieu {src} -> bo qua")
            continue
        st = convert_split(split, src, check_only=check_only)
        total[split] = st
        print(f"[{split}] ann={st['total_ann']} img_co_person={st['images']} "
              f"box_id8={st['boxes']} rider_drop={st['rider_dropped']} "
              f"empty={st['empty']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

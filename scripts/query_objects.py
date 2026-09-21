"""Truy van nhanh object theo date + loai xe + mau (khong do camera).

VD: python scripts/query_objects.py --type car --color do --date 2026-09-18
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.storage.object_store import ObjectStore


def main(argv=None):
    ap = argparse.ArgumentParser(description="Truy van object store")
    ap.add_argument("--db", default="objects.db")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (mac dinh: hom nay)")
    ap.add_argument("--type", dest="vtype", default="",
                    choices=["", "car", "bus", "truck", "motorbike", "unknown"])
    ap.add_argument("--color", default="",
                    help="do/cam/vang/xanh la/xanh duong/tim/trang/bac/den/nau/unknown")
    ap.add_argument("--camera", default="")
    ap.add_argument("--include-low-quality", action="store_true")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args(argv)

    if not args.date:
        from datetime import datetime
        args.date = datetime.now().strftime("%Y-%m-%d")
    store = ObjectStore(db_path=args.db)
    rows = store.query(date=args.date, vehicle_type=args.vtype,
                       color=args.color, camera_id=args.camera,
                       include_low_quality=args.include_low_quality,
                       limit=args.limit)
    store.close()
    print(f"{len(rows)} xe | date={args.date} type={args.vtype or '*'} "
          f"color={args.color or '*'} camera={args.camera or '*'}")
    print(f"{'track':>6} {'camera':<12} {'loai':<10} {'mau':<10} "
          f"{'conf':>5} {'vao':<8} {'ra':<8} crop")
    for r in rows:
        print(f"{r['track_id']:>6} {r['camera_id']:<12} {r['vehicle_type']:<10} "
              f"{r['color']:<10} {r['best_conf']:>5.2f} "
              f"{r['first_seen']:>8.1f} {r['last_seen']:>8.1f} {r['crop_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

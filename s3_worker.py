"""Batch upload anh vi pham len S3 (chay theo lich, vd cron 20:00 hang ngay).

Chi upload file .jpg. Key S3 suy tu file goc (on dinh) nen idempotent:
crash giua chung roi chay lai chi ghi de cung key, khong sinh trung.
Xoa ca cap .jpg + .json cung stem sau khi PUT OK.

Vi du cron (host):
  0 20 * * * cd /opt/digital-city-expand && .venv/bin/python s3_worker.py --camera CAM_TEST_01 >> logs/s3.log 2>&1

Chay bu tay ngay cu / kiem tra:
  .venv/bin/python s3_worker.py --camera CAM_TEST_01 --date 2026-09-15
  .venv/bin/python s3_worker.py --camera CAM_TEST_01 --dry-run --limit 5

Sinh URL xem co han cho web (khong can public bucket):
  .venv/bin/python s3_worker.py --presigned camera-01/2026/09/15/anh.jpg --expires 3600

Don S3 cu theo tuoi (lich RIENG, vd cron chu nhat; lan dau bat buoc --dry-run):
  .venv/bin/python s3_worker.py --cleanup --prefix camera-01 --older-than 90 --dry-run

Exit code: 0 = xong (khong con failed), 2 = con file that bai.
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import boto3

EVIDENCE_ROOT = Path(__file__).resolve().parent / "evidence"

DEFAULT_BUCKET = "edge-devices-dc"
DEFAULT_REGION = "us-east-1"
DEFAULT_PREFIX = "camera-01"

RETRIES = 3


def make_client(region):
    """Lazy boto3 client (creds tu env AWS_ACCESS_KEY_ID/SECRET_ACCESS_KEY
    hoac IAM role, khong hardcode trong code)."""
    return boto3.client("s3", region_name=region)


def s3_key(prefix, image_path, cam_dir):
    """Key on dinh suy tu file goc: {prefix}/YYYY/MM/DD/{filename}.
    Ngay lay tu thu muc cha date=YYYY-MM-DD (khong dung gio upload)."""
    date_part = image_path.parent.parent.name  # date=2026-09-15
    ymd = date_part[5:] if date_part.startswith("date=") else "unknown-date"
    try:
        yyyy, mm, dd = ymd.split("-")
    except ValueError:
        yyyy, mm, dd = "unknown", "unknown", "unknown"
    _ = cam_dir  # giu tham so cho ro nguon quet (khong dung vao key)
    pre = (prefix or "").strip().strip("/")
    base = f"{pre}/" if pre else ""
    return f"{base}{yyyy}/{mm}/{dd}/{image_path.name}"


def scan_jpgs(cam_dir, date_str=""):
    """Liet ke .jpg theo thu tu on dinh. Loc theo ngay neu co."""
    base = Path(cam_dir)
    if not base.is_dir():
        return []
    pat = f"date={date_str}" if date_str else "date=*"
    return sorted(base.glob(f"{pat}/*/*.jpg"))


def upload_one(s3, bucket, key, image_path):
    """PUT 1 anh, retry loi mang. Tra ve True neu OK."""
    last_err = None
    for attempt in range(1, RETRIES + 1):
        try:
            s3.upload_file(
                str(image_path),
                bucket,
                key,
                ExtraArgs={
                    "ContentType": "image/jpeg"
                }
            )
            return True
        except Exception as e:
            last_err = e
            print(f"Upload failed (lan {attempt}/{RETRIES}): "
                  f"{image_path} -> {e}")
            time.sleep(min(2 ** attempt, 30))
    print(f"Bo cuoc {image_path} sau {RETRIES} lan: {last_err}")
    return False


def delete_pair(image_path):
    """Xoa .jpg vua upload + .json cung stem (neu co). Tra ve so byte giai phong."""
    freed = 0
    try:
        freed += image_path.stat().st_size
        image_path.unlink()
    except OSError as e:
        print(f"Upload OK nhung xoa local loi {image_path}: {e}")
        return freed
    js = image_path.with_suffix(".json")
    try:
        if js.is_file():
            freed += js.stat().st_size
            js.unlink()
    except OSError as e:
        print(f"Xoa json loi {js}: {e}")
    return freed


def presign_url(s3, bucket, key, expires=3600):
    """Sinh URL xem anh co han (cho web, khong can public bucket)."""
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=max(1, int(expires)),
    )


def ensure_camera_prefix(s3, bucket, prefix):
    """Dam bao prefix camera ton tai tren S3 (PUT object giu cho .keep).
    Idempotent: da co object nao thi skip (ton 1 request LIST)."""
    pre = (prefix or "").strip().strip("/")
    if not pre:
        return False
    try:
        resp = s3.list_objects_v2(Bucket=bucket, Prefix=pre + "/", MaxKeys=1)
        if resp.get("KeyCount", 0) > 0:
            return False
        s3.put_object(Bucket=bucket, Key=pre + "/.keep", Body=b"")
        print(f"Da tao prefix giu cho: s3://{bucket}/{pre}/.keep")
        return True
    except Exception as e:
        print(f"Kiem tra/tao prefix loi (bo qua, van upload): {e}")
        return False


def cleanup_old(s3, bucket, prefix, older_than_days, dry_run=False):
    """Xoa object qua han tuoi trong prefix. Tra ve (deleted, kept, bytes)."""
    from datetime import timezone
    pre = (prefix or "").strip().strip("/")
    scope = (pre + "/") if pre else ""
    now = datetime.now(timezone.utc)
    deleted = kept = freed = 0
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=scope):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/.keep"):
                kept += 1
                continue
            age_days = (now - obj["LastModified"]).days
            if age_days <= older_than_days:
                kept += 1
                continue
            size = int(obj.get("Size", 0))
            if dry_run:
                print(f"DRY-RUN xoa ({age_days} ngay): s3://{bucket}/{key}")
                deleted += 1
                continue
            try:
                s3.delete_object(Bucket=bucket, Key=key)
                deleted += 1
                freed += size
            except Exception as e:
                print(f"Xoa loi {key}: {e}")
    return deleted, kept, freed


def main():
    ap = argparse.ArgumentParser(
        description="Batch upload anh vi pham len S3 (chay theo lich 20:00)")
    ap.add_argument("--camera", default="",
                    help="vd CAM_TEST_01 (bat buoc cho che do upload)")
    ap.add_argument("--evidence-dir", default=str(EVIDENCE_ROOT))
    ap.add_argument("--bucket", default=DEFAULT_BUCKET)
    ap.add_argument("--region", default=DEFAULT_REGION)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX,
                    help="tien to truoc YYYY/MM/DD (vd camera-01)")
    ap.add_argument("--date", default="",
                    help="chi upload ngay YYYY-MM-DD (mac dinh: moi ngay)")
    ap.add_argument("--dry-run", action="store_true",
                    help="chi liet ke, khong upload/xoa")
    ap.add_argument("--limit", type=int, default=0,
                    help="gioi han so anh (0 = het)")
    ap.add_argument("--presigned", default="",
                    help="sinh URL xem co han cho S3 key (khong upload)")
    ap.add_argument("--expires", type=int, default=3600,
                    help="han presigned URL giay (mac dinh 3600)")
    ap.add_argument("--cleanup", action="store_true",
                    help="xoa object tren S3 qua han tuoi (lich rieng, "
                         "khong chung cron upload)")
    ap.add_argument("--older-than", type=int, default=90,
                    help="tuoi object toi da ngay truoc khi xoa (mac dinh 90)")
    args = ap.parse_args()

    s3 = make_client(args.region)

    # Che do 1: sinh presigned URL (khong can camera/evidence)
    if args.presigned:
        try:
            url = presign_url(s3, args.bucket, args.presigned,
                              args.expires)
        except Exception as e:
            print(f"Sinh presigned URL loi: {e}", file=sys.stderr)
            return 2
        print(url)
        return 0

    # Che do 2: don S3 cu theo tuoi (lich rieng, dry-run truoc lan dau)
    if args.cleanup:
        deleted, kept, freed = cleanup_old(
            s3, args.bucket, args.prefix, args.older_than,
            dry_run=args.dry_run)
        print(f"cleanup prefix={args.prefix or '(goc bucket)'} "
              f"older-than={args.older_than}d dry-run={args.dry_run}: "
              f"deleted={deleted} kept={kept} freed={freed / 1048576:.1f}MB")
        return 0

    # Che do 3 (mac dinh): batch upload
    if not args.camera:
        print("Thieu --camera (bat buoc cho che do upload)",
              file=sys.stderr)
        return 2
    cam_dir = Path(args.evidence_dir) / args.camera
    if not cam_dir.is_dir():
        print(f"Khong thay thu muc evidence: {cam_dir}", file=sys.stderr)
        return 2

    ensure_camera_prefix(s3, args.bucket, args.prefix)

    ok = fail = freed = 0
    images = scan_jpgs(str(cam_dir), args.date)
    if args.limit > 0:
        images = images[:args.limit]
    print(f"[{datetime.now()}] Found {len(images)} images "
          f"(camera={args.camera} date={args.date or 'moi ngay'})")
    if args.dry_run:
        for image_path in images:
            print(f"DRY-RUN {image_path} -> "
                  f"s3://{args.bucket}/"
                  f"{s3_key(args.prefix, image_path, str(cam_dir))}")
        return 0
    for image_path in images:
        key = s3_key(args.prefix, image_path, str(cam_dir))
        print(f"Uploading: {image_path} -> {key}")
        if not upload_one(s3, args.bucket, key, image_path):
            fail += 1
            continue
        freed += delete_pair(image_path)
        ok += 1
        print(f"Uploaded and deleted: {image_path}")

    print(f"xong: uploaded={ok}, failed={fail}, "
          f"freed={freed / 1048576:.1f}MB")
    return 2 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())

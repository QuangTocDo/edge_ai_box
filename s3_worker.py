"""LEGACY shim (P3 restructure): new home là src/storage/uploader.py.

Chạy mới: python -m src.storage.uploader --camera CAM_TEST_01
Chạy cũ (vẫn chạy): python s3_worker.py --camera CAM_TEST_01
"""
from src.storage.uploader import (  # noqa: F401
    DEFAULT_BUCKET, DEFAULT_PREFIX, DEFAULT_REGION, EVIDENCE_ROOT, RETRIES,
    cleanup_old, delete_pair, ensure_camera_prefix, main, make_client,
    presign_url, s3_key, scan_jpgs, upload_one,
)

if __name__ == "__main__":
    raise SystemExit(main())

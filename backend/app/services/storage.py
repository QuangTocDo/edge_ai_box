from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from ..config import ALLOWED_VIDEO_SUFFIXES, JOBS_DIR, MAX_UPLOAD_BYTES


def safe_filename(filename: Optional[str]) -> str:
    base = Path(filename or "video.mp4").name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return cleaned or "video.mp4"


def create_job_storage() -> Tuple[str, Path, Path]:
    job_id = str(uuid4())
    job_dir = JOBS_DIR / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    return job_id, input_dir, output_dir


async def store_upload(upload: UploadFile, input_dir: Path) -> Path:
    filename = safe_filename(upload.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload an MP4, MOV, M4V, AVI, or MKV video.")

    path = input_dir / filename
    size = 0
    try:
        with path.open("wb") as target:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds the 1 GB upload limit.")
                target.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    return path


def delete_job_storage(job_id: str) -> None:
    job_dir = (JOBS_DIR / job_id).resolve()
    if job_dir.parent != JOBS_DIR.resolve():
        raise ValueError("Invalid job path")
    shutil.rmtree(job_dir, ignore_errors=True)


def resolve_job_file(output_dir: str, relative_path: str) -> Path:
    root = Path(output_dir).resolve()
    path = (root / relative_path).resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")
    return path

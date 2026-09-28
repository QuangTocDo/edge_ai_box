from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProcessingJob, ViolationEvent
from ..services.storage import resolve_job_file


router = APIRouter(prefix="/api", tags=["media"])


def require_job(job_id: str, db: Session) -> ProcessingJob:
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@router.get("/jobs/{job_id}/video")
def job_video(job_id: str, db: Session = Depends(get_db)):
    job = require_job(job_id, db)
    path = resolve_job_file(job.output_path, "annotated.mp4")
    return FileResponse(path, media_type="video/mp4", filename=f"{job_id}-annotated.mp4")


@router.get("/jobs/{job_id}/events.json")
def events_json(job_id: str, db: Session = Depends(get_db)):
    job = require_job(job_id, db)
    path = resolve_job_file(job.output_path, "events.json")
    return FileResponse(path, media_type="application/json", filename=f"{job_id}-events.json")


@router.get("/jobs/{job_id}/events.csv")
def events_csv(job_id: str, db: Session = Depends(get_db)):
    job = require_job(job_id, db)
    path = resolve_job_file(job.output_path, "events.csv")
    return FileResponse(path, media_type="text/csv", filename=f"{job_id}-events.csv")


def require_event(event_id: int, db: Session) -> tuple[ViolationEvent, ProcessingJob]:
    event = db.get(ViolationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    job = require_job(event.job_id, db)
    return event, job


@router.get("/events/{event_id}/screenshot")
def event_screenshot(event_id: int, db: Session = Depends(get_db)):
    event, job = require_event(event_id, db)
    if not event.screenshot_path:
        raise HTTPException(status_code=404, detail="No screenshot for this event.")
    path = resolve_job_file(job.output_path, event.screenshot_path)
    return FileResponse(path, media_type="image/jpeg", filename=Path(path).name)


@router.get("/events/{event_id}/clip")
def event_clip(event_id: int, db: Session = Depends(get_db)):
    event, job = require_event(event_id, db)
    if not event.clip_path:
        raise HTTPException(status_code=404, detail="No clip for this event.")
    path = resolve_job_file(job.output_path, event.clip_path)
    return FileResponse(path, media_type="video/mp4", filename=Path(path).name)


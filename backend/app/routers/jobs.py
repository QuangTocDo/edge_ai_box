from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProcessingJob, ViolationEvent
from ..schemas import EventResponse, JobResponse, OverviewResponse
from ..services.processing import enqueue_job
from ..services.storage import create_job_storage, delete_job_storage, store_upload


router = APIRouter(prefix="/api", tags=["jobs"])


def event_response(event: ViolationEvent) -> EventResponse:
    return EventResponse(
        id=event.id,
        job_id=event.job_id,
        type=event.type,
        track_id=event.track_id,
        frame=event.frame,
        time_s=event.time_s,
        severity=event.severity,
        speed_kmh=event.speed_kmh,
        world_x=event.world_x,
        world_y=event.world_y,
        lane_id=event.lane_id,
        light_phase=event.light_phase,
        screenshot_url=f"/api/events/{event.id}/screenshot" if event.screenshot_path else None,
        clip_url=f"/api/events/{event.id}/clip" if event.clip_path else None,
        measured=json.loads(event.measured_json or "{}"),
        evidence=json.loads(event.evidence_json or "{}"),
    )


def job_response(job: ProcessingJob) -> JobResponse:
    return JobResponse(
        id=job.id,
        original_filename=job.original_filename,
        source_type=job.source_type,
        status=job.status,
        progress_percent=job.progress_percent,
        current_frame=job.current_frame,
        total_frames=job.total_frames,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        event_count=len(job.events),
    )


@router.post("/jobs/upload", response_model=JobResponse, status_code=201)
async def upload_job(video: UploadFile = File(...), db: Session = Depends(get_db)):
    job_id, input_dir, output_dir = create_job_storage()
    try:
        input_path = await store_upload(video, input_dir)
    except Exception:
        delete_job_storage(job_id)
        raise
    job = ProcessingJob(
        id=job_id,
        original_filename=Path(video.filename or input_path.name).name,
        input_path=str(input_path),
        output_path=str(output_dir),
        status="queued",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job_response(job)


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    jobs = db.scalars(select(ProcessingJob).order_by(ProcessingJob.created_at.desc())).unique().all()
    return [job_response(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job_response(job)


@router.post("/jobs/{job_id}/process", response_model=JobResponse, status_code=202)
def start_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status == "processing":
        raise HTTPException(status_code=409, detail="Job is already processing.")
    if job.status == "completed":
        raise HTTPException(status_code=409, detail="Job is already complete.")
    job.status = "queued"
    job.progress_percent = 0
    job.current_frame = 0
    job.error_message = None
    db.commit()
    enqueue_job(job_id)
    return job_response(job)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(ProcessingJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status == "processing":
        raise HTTPException(status_code=409, detail="A processing job cannot be deleted.")
    db.delete(job)
    db.commit()
    delete_job_storage(job_id)


@router.get("/overview", response_model=OverviewResponse)
def overview(db: Session = Depends(get_db)):
    jobs = db.scalars(select(ProcessingJob).order_by(ProcessingJob.created_at.desc())).unique().all()
    total_events = db.scalar(select(func.count(ViolationEvent.id))) or 0
    by_type = dict(db.execute(select(ViolationEvent.type, func.count()).group_by(ViolationEvent.type)).all())
    by_severity = dict(db.execute(select(ViolationEvent.severity, func.count()).group_by(ViolationEvent.severity)).all())
    recent = db.scalars(select(ViolationEvent).order_by(ViolationEvent.id.desc()).limit(6)).all()
    return OverviewResponse(
        total_jobs=len(jobs),
        completed_jobs=sum(job.status == "completed" for job in jobs),
        processing_jobs=sum(job.status in {"queued", "processing"} for job in jobs),
        failed_jobs=sum(job.status == "failed" for job in jobs),
        total_events=total_events,
        violations_by_type=by_type,
        severity_counts=by_severity,
        recent_events=[event_response(event) for event in recent],
    )


from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ProcessingJob, ViolationEvent
from ..schemas import EventResponse
from .jobs import event_response


router = APIRouter(prefix="/api", tags=["events"])


@router.get("/jobs/{job_id}/events", response_model=list[EventResponse])
def job_events(job_id: str, db: Session = Depends(get_db)):
    if db.get(ProcessingJob, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    events = db.scalars(
        select(ViolationEvent).where(ViolationEvent.job_id == job_id).order_by(ViolationEvent.frame)
    ).all()
    return [event_response(event) for event in events]


@router.get("/events/{event_id}", response_model=EventResponse)
def get_event(event_id: int, db: Session = Depends(get_db)):
    event = db.get(ViolationEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event_response(event)


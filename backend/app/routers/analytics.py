from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Camera, CameraEvent, ProcessingJob, ViolationEvent


router = APIRouter(prefix="/api", tags=["analytics"])


class AnalyticsResponse(BaseModel):
    total_violations: int
    live_total: int
    job_total: int
    avg_speed_kmh: Optional[float]
    max_speed_kmh: Optional[float]
    by_type: Dict[str, int]
    by_severity: Dict[str, int]
    speed_histogram: List[Dict[str, Any]]
    by_hour: List[Dict[str, Any]]
    daily: List[Dict[str, Any]]
    top_sources: List[Dict[str, Any]]


# Unified record we build from both event tables so the charts treat live and
# uploaded violations the same way.
def _collect(db: Session):
    rows = []  # (type, severity, speed, timestamp, source_name)

    job_names = {j.id: j.original_filename for j in db.scalars(select(ProcessingJob)).all()}
    job_created = {j.id: j.created_at for j in db.scalars(select(ProcessingJob)).all()}
    for e in db.scalars(select(ViolationEvent)).all():
        rows.append((e.type, e.severity, e.speed_kmh, job_created.get(e.job_id), job_names.get(e.job_id, "Uploaded video")))

    cam_names = {c.id: c.name for c in db.scalars(select(Camera)).all()}
    for e in db.scalars(select(CameraEvent)).all():
        rows.append((e.type, e.severity, e.speed_kmh, e.created_at, cam_names.get(e.camera_id, "Live camera")))
    return rows


@router.get("/analytics", response_model=AnalyticsResponse)
def analytics(db: Session = Depends(get_db)):
    rows = _collect(db)
    job_count = len(db.scalars(select(ViolationEvent.id)).all())
    live_count = len(db.scalars(select(CameraEvent.id)).all())

    by_type: Counter = Counter()
    by_severity: Counter = Counter()
    speeds: List[float] = []
    by_hour = [0] * 24
    daily_counter: Counter = Counter()
    source_counter: Counter = Counter()

    today = datetime.now(timezone.utc).date()
    window_start = today - timedelta(days=13)

    for (vtype, severity, speed, ts, source_name) in rows:
        by_type[vtype] += 1
        by_severity[severity] += 1
        if speed is not None:
            speeds.append(float(speed))
        source_counter[source_name] += 1
        if ts is not None:
            t = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
            by_hour[t.hour] += 1
            d = t.date()
            if d >= window_start:
                daily_counter[d.isoformat()] += 1

    # Speed histogram in 20 km/h bands.
    bands = [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]
    hist = []
    for lo, hi in bands:
        hist.append({"bucket": f"{lo}–{hi}", "count": sum(1 for s in speeds if lo <= s < hi)})
    hist.append({"bucket": "100+", "count": sum(1 for s in speeds if s >= 100)})

    daily = []
    for i in range(14):
        d = (window_start + timedelta(days=i)).isoformat()
        daily.append({"date": d[5:], "count": daily_counter.get(d, 0)})

    top_sources = [
        {"name": name, "count": count}
        for name, count in source_counter.most_common(6)
    ]

    return AnalyticsResponse(
        total_violations=len(rows),
        live_total=live_count,
        job_total=job_count,
        avg_speed_kmh=round(sum(speeds) / len(speeds), 1) if speeds else None,
        max_speed_kmh=round(max(speeds), 1) if speeds else None,
        by_type=dict(by_type),
        by_severity=dict(by_severity),
        speed_histogram=hist,
        by_hour=[{"hour": f"{h:02d}", "count": by_hour[h]} for h in range(24)],
        daily=daily,
        top_sources=top_sources,
    )

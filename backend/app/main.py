from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import auth
from .config import ensure_data_dirs
from .database import Base, SessionLocal, engine
from .models import ProcessingJob
from .routers import analytics, cameras, events, jobs, objects, videos
from .services.live import registry, ws_key
from .services.processing import enqueue_job
from .websocket import manager


def _recover_orphaned_jobs() -> None:
    """Re-queue uploaded-video jobs left mid-flight by a server restart.

    Upload processing runs inside this process, so a restart kills the worker
    thread and the job is stranded as 'processing' forever. On startup we find
    those (and anything still 'queued') and resubmit them so they finish.
    """
    from sqlalchemy import select

    with SessionLocal() as db:
        stale = db.scalars(
            select(ProcessingJob).where(ProcessingJob.status.in_(("processing", "queued")))
        ).all()
        ids = []
        for job in stale:
            job.status = "queued"
            job.progress_percent = 0
            job.current_frame = 0
            ids.append(job.id)
        db.commit()
    for job_id in ids:
        enqueue_job(job_id)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_data_dirs()
    Base.metadata.create_all(bind=engine)
    manager.set_loop(asyncio.get_running_loop())
    _recover_orphaned_jobs()
    yield
    # Stop all live camera workers on shutdown so capture/inference threads and
    # VideoCapture handles are released cleanly.
    registry.stop_all()


app = FastAPI(title="Traffic Vision Operations API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(events.router)
app.include_router(videos.router)
app.include_router(cameras.router)
app.include_router(analytics.router)
app.include_router(objects.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.websocket("/ws/jobs/{job_id}")
async def job_socket(websocket: WebSocket, job_id: str):
    await manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(job_id, websocket)


@app.websocket("/ws/cameras/{camera_id}")
async def camera_socket(websocket: WebSocket, camera_id: str):
    key = ws_key(camera_id)
    await manager.connect(key, websocket)
    # Push the current status immediately so the UI doesn't wait for the next tick.
    worker = registry.get(camera_id)
    if worker is not None:
        await websocket.send_json(worker.status_payload())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(key, websocket)

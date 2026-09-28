from __future__ import annotations

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import yaml
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import CAMERAS_DIR, CONFIGS_DIR, PROJECT_ROOT, VISION_CONFIG_PATH
from ..database import get_db
from ..models import Camera, CameraEvent
from ..schemas import (
    CalibrationRectangle,
    CalibrationRequest,
    CameraCreate,
    CameraEventResponse,
    CameraResponse,
    HomographyPreview,
)
from ..services.live import registry
from ..services.sources import build_source, mask_rtsp_credentials


router = APIRouter(prefix="/api/cameras", tags=["cameras"])


# --- helpers ---------------------------------------------------------------

def _camera_dir(camera_id: str) -> Path:
    return CAMERAS_DIR / camera_id


def _compute_homography(src_pts, dst_pts):
    src = np.array(src_pts, dtype=np.float32)
    dst = np.array(dst_pts, dtype=np.float32)
    H, _ = cv2.findHomography(src, dst)
    if H is None:
        raise ValueError("Cannot compute homography from these points.")
    return H.tolist()


def _write_camera_config(camera_id: str, calibrated: bool) -> Path:
    cam_dir = _camera_dir(camera_id)
    cam_dir.mkdir(parents=True, exist_ok=True)
    config_path = cam_dir / "config.yaml"

    if VISION_CONFIG_PATH.exists():
        with open(VISION_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}

    cfg["camera_id"] = camera_id
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)
    return config_path


def _safe_uri(camera: Camera) -> str:
    if camera.source_type == "rtsp":
        return mask_rtsp_credentials(camera.source_uri)
    return camera.source_uri


def camera_response(camera: Camera, db: Session) -> CameraResponse:
    worker = registry.get(camera.id)
    status = worker.status if worker is not None else camera.last_status
    event_count = (
        db.scalar(
            select(func.count(CameraEvent.id)).where(CameraEvent.camera_id == camera.id)
        )
        or 0
    )
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        source_type=camera.source_type,
        source_uri=_safe_uri(camera),
        calibrated=camera.calibrated,
        enabled=camera.enabled,
        status=status,
        last_error=worker.last_error if worker is not None else camera.last_error,
        created_at=camera.created_at,
        fps=round(worker.measured_fps, 1) if worker is not None else None,
        processed_frames=worker.processed_frames if worker is not None else None,
        active_vehicles=worker.active_vehicles if worker is not None else None,
        event_count=event_count,
    )


def event_response(event: CameraEvent) -> CameraEventResponse:
    return CameraEventResponse(
        id=event.id,
        camera_id=event.camera_id,
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
        screenshot_url=(
            f"/api/cameras/{event.camera_id}/events/{event.id}/screenshot"
            if event.screenshot_path
            else None
        ),
        clip_url=(
            f"/api/cameras/{event.camera_id}/events/{event.id}/clip"
            if event.clip_path
            else None
        ),
        measured=json.loads(event.measured_json or "{}"),
        evidence=json.loads(event.evidence_json or "{}"),
        created_at=event.created_at,
    )


def require_camera(camera_id: str, db: Session) -> Camera:
    camera = db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found.")
    return camera


def _resolve_evidence(evidence_dir: str, relative_path: str) -> Path:
    root = Path(evidence_dir).resolve()
    path = (root / relative_path).resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid media path.")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")
    return path


def _auto_seed_camera(db: Session):
    existing = db.scalars(select(Camera)).first()
    if existing is not None:
        return
    cam_id = "CAM_TEST_01"
    config_path = CONFIGS_DIR / "active.yaml"
    evidence_path = _camera_dir(cam_id) / "evidence_root"
    evidence_path.mkdir(parents=True, exist_ok=True)
    cam = Camera(
        id=cam_id,
        name="Camera Giám Sát 01 (Test)",
        source_type="file",
        source_uri="assets/speed1.mp4",
        config_path=str(config_path),
        evidence_path=str(evidence_path),
        calibrated=True,
        enabled=True,
        last_status="Offline",
    )
    db.add(cam)
    db.commit()


# --- CRUD ------------------------------------------------------------------

@router.get("", response_model=list[CameraResponse])
def list_cameras(db: Session = Depends(get_db)):
    _auto_seed_camera(db)
    cameras = db.scalars(select(Camera).order_by(Camera.created_at.desc())).all()
    return [camera_response(c, db) for c in cameras]


@router.post("", response_model=CameraResponse, status_code=201)
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    try:
        build_source(payload.source_type, payload.source_uri)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    camera_id = str(uuid4())
    config_path = _write_camera_config(camera_id, calibrated=False)
    evidence_dir = _camera_dir(camera_id) / "evidence_root"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    camera = Camera(
        id=camera_id,
        name=payload.name,
        source_type=payload.source_type.lower(),
        source_uri=payload.source_uri,
        config_path=str(config_path),
        evidence_path=str(evidence_dir),
        calibrated=False,
        enabled=True,
        last_status="Offline",
    )
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return camera_response(camera, db)


@router.get("/{camera_id}", response_model=CameraResponse)
def get_camera(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    return camera_response(camera, db)


@router.delete("/{camera_id}", status_code=204)
def delete_camera(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    registry.stop(camera_id)
    shutil.rmtree(_camera_dir(camera_id), ignore_errors=True)
    db.delete(camera)
    db.commit()


# --- Lifecycle actions -----------------------------------------------------

@router.post("/{camera_id}/start", response_model=CameraResponse)
def start_camera(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    camera.enabled = True
    db.commit()
    registry.start(camera)
    return camera_response(camera, db)


@router.post("/{camera_id}/stop", response_model=CameraResponse)
def stop_camera(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    registry.stop(camera_id)
    camera.enabled = False
    camera.last_status = "Offline"
    camera.last_error = None
    db.commit()
    return camera_response(camera, db)


@router.post("/{camera_id}/reconnect", response_model=CameraResponse)
def reconnect_camera(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    registry.stop(camera_id)
    if camera.enabled:
        registry.start(camera)
    return camera_response(camera, db)


# --- Snapshot & Calibration ------------------------------------------------

@router.get("/{camera_id}/snapshot")
def camera_snapshot(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    worker = registry.get(camera_id)
    if worker is not None:
        jpeg = worker.get_latest_jpeg()
        if jpeg is not None:
            return StreamingResponse(iter([jpeg]), media_type="image/jpeg")

    # Fallback to single frame capture
    source = build_source(camera.source_type, camera.source_uri)
    uri = source.processing_uri()
    cap = cv2.VideoCapture(uri)
    if not cap.isOpened():
        raise HTTPException(status_code=502, detail=f"Cannot connect to {source.display_uri()}")
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise HTTPException(status_code=502, detail="Connected to camera but received no frame.")
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode snapshot JPEG.")
    return StreamingResponse(iter([buf.tobytes()]), media_type="image/jpeg")


def _world_points_from_rect(rect: CalibrationRectangle) -> list[list[float]]:
    w, l = float(rect.world_width_m), float(rect.world_length_m)
    return [[0.0, 0.0], [w, 0.0], [w, l], [0.0, l]]


def _to_world(H, pt):
    arr = np.array([[[float(pt[0]), float(pt[1])]]], dtype=np.float64)
    out = cv2.perspectiveTransform(arr, np.array(H, dtype=np.float64)).reshape(2)
    return (float(out[0]), float(out[1]))


@router.post("/{camera_id}/homography_preview", response_model=HomographyPreview)
def homography_preview(camera_id: str, rect: CalibrationRectangle, db: Session = Depends(get_db)):
    require_camera(camera_id, db)
    if len(rect.image_points) != 4:
        raise HTTPException(status_code=422, detail="Exactly four ground points are required.")
    world = _world_points_from_rect(rect)
    try:
        H = _compute_homography(rect.image_points, world)
    except ValueError as exc:
        return HomographyPreview(condition_number=0, mean_error_m=0, ok=False, message=str(exc))
    cond = float(np.linalg.cond(np.array(H, dtype=np.float64)))
    projected = [_to_world(H, p) for p in rect.image_points]
    errors = [float(np.hypot(projected[i][0] - world[i][0], projected[i][1] - world[i][1])) for i in range(4)]
    mean_err = sum(errors) / len(errors)
    ok = cond < 1e7 and mean_err < 0.5
    msg = (
        "Geometry looks good."
        if ok
        else "Points look degenerate - spread the rectangle wider and avoid a near-straight line."
    )
    return HomographyPreview(condition_number=cond, mean_error_m=mean_err, ok=ok, message=msg)


@router.post("/{camera_id}/calibrate", response_model=CameraResponse)
def calibrate_camera(camera_id: str, payload: CalibrationRequest, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    if len(payload.rectangle.image_points) != 4:
        raise HTTPException(status_code=422, detail="Exactly four ground points are required.")
    if len(payload.stop_line) != 2:
        raise HTTPException(status_code=422, detail="The stop line needs exactly two points.")

    world = _world_points_from_rect(payload.rectangle)
    try:
        H = _compute_homography(payload.rectangle.image_points, world)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    config_path = Path(camera.config_path)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    polys = config.get("polygons", [])
    if not polys:
        polys = [
            {
                "id": f"POLY_1",
                "polygon": payload.rectangle.image_points,
                "rules": {"speeding": {"enable": True}, "wrong_way": {"enable": True}},
            }
        ]
    polys[0]["homography"] = {
        "src": payload.rectangle.image_points,
        "dst": world,
        "measured_at": datetime.now().isoformat(),
    }
    config["polygons"] = polys
    config["lines"] = [
        {
            "id": f"STOP_1",
            "pt1": payload.stop_line[0],
            "pt2": payload.stop_line[1],
        }
    ]

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, default_flow_style=False)

    camera.calibrated = True
    db.commit()
    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        registry.start(camera)
    db.refresh(camera)
    return camera_response(camera, db)


# --- MJPEG stream ----------------------------------------------------------

@router.get("/{camera_id}/stream")
def camera_stream(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    worker = registry.get(camera_id)
    if worker is None or not worker.is_running():
        raise HTTPException(status_code=409, detail="Camera is not running. Start it first.")

    boundary = "frame"

    def generate():
        while True:
            jpeg = worker.get_latest_jpeg()
            if jpeg is not None:
                yield (
                    b"--" + boundary.encode() + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
            time.sleep(0.066)

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


# --- Camera Events & Evidence ----------------------------------------------

@router.get("/{camera_id}/events", response_model=list[CameraEventResponse])
def camera_events(
    camera_id: str, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)
):
    require_camera(camera_id, db)
    events = db.scalars(
        select(CameraEvent)
        .where(CameraEvent.camera_id == camera_id)
        .order_by(CameraEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [event_response(e) for e in events]


@router.get("/{camera_id}/events/{event_id}/screenshot")
def event_screenshot(camera_id: str, event_id: int, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    event = db.get(CameraEvent, event_id)
    if event is None or event.camera_id != camera_id:
        raise HTTPException(status_code=404, detail="Event not found.")
    if not event.screenshot_path:
        raise HTTPException(status_code=404, detail="No screenshot for this event.")
    path = _resolve_evidence(camera.evidence_path, event.screenshot_path)
    return FileResponse(path, media_type="image/jpeg")


@router.get("/{camera_id}/events/{event_id}/clip")
def event_clip(camera_id: str, event_id: int, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    event = db.get(CameraEvent, event_id)
    if event is None or event.camera_id != camera_id:
        raise HTTPException(status_code=404, detail="Event not found.")
    if not event.clip_path:
        raise HTTPException(status_code=404, detail="No clip for this event.")
    path = _resolve_evidence(camera.evidence_path, event.clip_path)
    return FileResponse(path, media_type="video/mp4")

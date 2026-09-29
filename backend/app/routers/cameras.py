from __future__ import annotations

import asyncio

import json
import math
import shutil
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import yaml
from fastapi import APIRouter, Body, Depends, HTTPException
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
    RawConfigRequest,
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
    config_path = VISION_CONFIG_PATH
    if not config_path.exists():
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump({"camera_id": camera_id}, f, default_flow_style=False)
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


@router.get("/{camera_id}/config")
def get_camera_config(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if not config_path.exists():
        return {
            "camera_id": camera_id,
            "config_path": str(config_path),
            "raw_yaml": "",
            "polygons": [],
            "lines": [],
            "signals": [],
        }
    with open(config_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    cfg = yaml.safe_load(raw_text) or {}

    return {
        "camera_id": camera_id,
        "config_path": str(config_path),
        "raw_yaml": raw_text,
        "polygons": cfg.get("polygons", []),
        "lines": cfg.get("lines", []),
        "signals": cfg.get("signals", []),
        "no_entry_road": cfg.get("no_entry_road", {}),
        "no_gathering": cfg.get("no_gathering", {}),
        "no_parking": cfg.get("no_parking", {}),
        "no_uturn": cfg.get("no_uturn", {}),
        "wrong_way": cfg.get("wrong_way", {}),
    }


@router.put("/{camera_id}/config/raw")
def update_raw_config(camera_id: str, payload: RawConfigRequest, db: Session = Depends(get_db)):
    """Cho phep sua va luu truc tiep file active.yaml tu Dashboard."""
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)

    # 1. Kiem tra cu phap YAML
    try:
        cfg = yaml.safe_load(payload.yaml_content)
        if not isinstance(cfg, dict):
            raise ValueError("Noi dung YAML phai la mot mapping/dictionary o root.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Loi cu phap YAML: {exc}")

    # 2. Validate schema
    try:
        from src.config.validator import validate_config_schema
        validate_config_schema(cfg)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cau hinh khong hop le: {exc}")

    # 3. Ghi file
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(payload.yaml_content)

    # 4. Khoi dong lai worker neu dang chay
    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        if camera.enabled:
            registry.start(camera)

    return {"status": "ok", "message": f"Da cap nhat thanh cong tap tin {config_path.name}!"}


@router.delete("/{camera_id}/config/polygons/{polygon_id}")
def delete_camera_polygon(camera_id: str, polygon_id: str, db: Session = Depends(get_db)):
    """Xoa truc tiep 1 polygon khoi active.yaml."""
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay tap tin cau hinh")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    polygons = cfg.get("polygons", [])
    before_len = len(polygons)
    polygons = [p for p in polygons if p.get("id") != polygon_id]
    if len(polygons) == before_len:
        raise HTTPException(status_code=404, detail=f"Khong tim thay polygon {polygon_id}")

    cfg["polygons"] = polygons
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)

    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        if camera.enabled:
            registry.start(camera)

    return {"status": "ok", "deleted": polygon_id, "remaining_polygons": len(polygons)}


@router.post("/{camera_id}/config/polygons")
def save_camera_polygon(camera_id: str, poly: dict = Body(...), db: Session = Depends(get_db)):
    """Ghi truc tiep 1 polygon vao active.yaml tuong tu nhu draw_lines.py."""
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay tap tin cau hinh")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    polygons = cfg.setdefault("polygons", [])
    pid = poly.get("id")
    if "homography" in poly and poly["homography"].get("src") and poly["homography"].get("dst"):
        from src.utils.homography import build_H, pixel_to_road
        src = poly["homography"]["src"]
        dst = poly["homography"]["dst"]
        try:
            H_mat, inliers, reproj_err = build_H(src, dst)
            r_pts = poly.pop("road_dir_points", None)
            if r_pts and len(r_pts) == 2:
                xa, ya = pixel_to_road(H_mat, r_pts[0][0], r_pts[0][1])
                xb, yb = pixel_to_road(H_mat, r_pts[1][0], r_pts[1][1])
                dx = xb - xa
                dy = yb - ya
                mag = math.hypot(dx, dy)
                poly["road_dir"] = [float(dx / mag), float(dy / mag)] if mag > 1e-9 else [0.0, 1.0]
            elif not poly.get("road_dir"):
                poly["road_dir"] = [0.0, 1.0]
        except Exception:
            if not poly.get("road_dir"):
                poly["road_dir"] = [0.0, 1.0]
    elif (poly.get("homography") or poly.get("rules", {}).get("speeding", {}).get("enable")) and not poly.get("road_dir"):
        poly["road_dir"] = [0.0, 1.0]
    if not pid:
        used = {p.get("id") for p in polygons if isinstance(p, dict)}
        idx = 1
        while f"POLY_{idx}" in used:
            idx += 1
        pid = f"POLY_{idx}"
        poly["id"] = pid

    existing = next((p for p in polygons if isinstance(p, dict) and p.get("id") == pid), None)
    if existing:
        idx = polygons.index(existing)
        # merge to preserve homography if not supplied
        if "homography" in existing and "homography" not in poly:
            poly["homography"] = existing["homography"]
        polygons[idx] = poly
    else:
        polygons.append(poly)

    cfg["polygons"] = polygons
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)

    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        if camera.enabled:
            registry.start(camera)

    return {"status": "ok", "message": f"Da ghi truc tiep polygon {pid} vao {config_path.name}", "polygon": poly}


@router.post("/{camera_id}/config/lines")
def save_camera_line(camera_id: str, line: dict = Body(...), db: Session = Depends(get_db)):
    """Ghi truc tiep 1 vach ke vao active.yaml tuong tu nhu draw_lines.py."""
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay tap tin cau hinh")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    lines = cfg.setdefault("lines", [])
    lid = line.get("id")
    if not lid:
        used = {l.get("id") for l in lines if isinstance(l, dict)}
        idx = 1
        while f"L{idx}" in used:
            idx += 1
        lid = f"L{idx}"
        line["id"] = lid

    existing = next((l for l in lines if isinstance(l, dict) and l.get("id") == lid), None)
    if existing:
        idx = lines.index(existing)
        lines[idx] = line
    else:
        lines.append(line)

    cfg["lines"] = lines
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)

    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        if camera.enabled:
            registry.start(camera)

    return {"status": "ok", "message": f"Da ghi truc tiep vach {lid} vao {config_path.name}", "line": line}


@router.post("/{camera_id}/config/signals")
def save_camera_signal(camera_id: str, sig: dict = Body(...), db: Session = Depends(get_db)):
    """Ghi truc tiep hop den tin hieu vao active.yaml tuong tu nhu draw_lines.py."""
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay tap tin cau hinh")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    signals = cfg.setdefault("signals", [])
    sid = sig.get("id", "SIGNAL_1")
    sig["id"] = sid
    if "box" in sig and "roi" not in sig:
        sig["roi"] = sig["box"]
    elif "roi" in sig and "box" not in sig:
        sig["box"] = sig["roi"]

    existing = next((s for s in signals if isinstance(s, dict) and s.get("id") == sid), None)
    if existing:
        idx = signals.index(existing)
        signals[idx] = sig
    else:
        signals.append(sig)

    cfg["signals"] = signals
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)

    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        if camera.enabled:
            registry.start(camera)

    return {"status": "ok", "message": f"Da ghi truc tiep den tin hieu {sid} vao {config_path.name}", "signal": sig}


@router.delete("/{camera_id}/config/signals/{signal_id}")
def delete_camera_signal(camera_id: str, signal_id: str, db: Session = Depends(get_db)):
    """Xoa truc tiep 1 hop den tin hieu khoi active.yaml."""
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay tap tin cau hinh")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    signals = cfg.get("signals", [])
    before_len = len(signals)
    signals = [s for s in signals if s.get("id") != signal_id]
    if len(signals) == before_len:
        raise HTTPException(status_code=404, detail=f"Khong tim thay den {signal_id}")

    cfg["signals"] = signals
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)

    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        if camera.enabled:
            registry.start(camera)

    return {"status": "ok", "deleted": signal_id, "remaining_signals": len(signals)}


@router.delete("/{camera_id}/config/lines/{line_id}")
def delete_camera_line(camera_id: str, line_id: str, db: Session = Depends(get_db)):
    """Xoa truc tiep 1 vach ke khoi active.yaml."""
    camera = require_camera(camera_id, db)
    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay tap tin cau hinh")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    lines = cfg.get("lines", [])
    before_len = len(lines)
    lines = [ln for ln in lines if ln.get("id") != line_id]
    if len(lines) == before_len:
        raise HTTPException(status_code=404, detail=f"Khong tim thay vach ke {line_id}")

    cfg["lines"] = lines
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, default_flow_style=False)

    if registry.get(camera_id) is not None:
        registry.stop(camera_id)
        if camera.enabled:
            registry.start(camera)

    return {"status": "ok", "deleted": line_id, "remaining_lines": len(lines)}


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
    w = float(getattr(rect, "width_m", None) or getattr(rect, "world_width_m", None) or 3.5)
    l = float(getattr(rect, "length_m", None) or getattr(rect, "world_length_m", None) or 15.0)
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

    config_path = VISION_CONFIG_PATH if VISION_CONFIG_PATH.exists() else Path(camera.config_path)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = {}

    polygons = config.get("polygons", [])
    lines = config.get("lines", [])
    signals = config.get("signals", [])

    # Filter out requested deletions
    if payload.deleted_polygon_ids:
        polygons = [p for p in polygons if p.get("id") not in payload.deleted_polygon_ids]
    if payload.deleted_line_ids:
        lines = [ln for ln in lines if ln.get("id") not in payload.deleted_line_ids]
    if payload.deleted_signal_ids:
        signals = [s for s in signals if s.get("id") not in payload.deleted_signal_ids]

    # 1. Ground Rectangle (Homography)
    if payload.rectangle and len(payload.rectangle.image_points) == 4:
        world = _world_points_from_rect(payload.rectangle)
        try:
            _ = _compute_homography(payload.rectangle.image_points, world)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        from src.utils.homography import build_H, pixel_to_road
        H_mat, inliers, reproj_err = build_H(payload.rectangle.image_points, world)

        speed_rdir = payload.rectangle.road_dir
        if not speed_rdir and payload.rectangle.road_dir_points and len(payload.rectangle.road_dir_points) == 2:
            pA, pB = payload.rectangle.road_dir_points
            xa, ya = pixel_to_road(H_mat, pA[0], pA[1])
            xb, yb = pixel_to_road(H_mat, pB[0], pB[1])
            dx = xb - xa
            dy = yb - ya
            mag = math.hypot(dx, dy)
            speed_rdir = [float(dx / mag), float(dy / mag)] if mag > 1e-9 else [0.0, 1.0]

        if not speed_rdir:
            # Metric road plane travel direction along road length (+Y axis)
            speed_rdir = [0.0, 1.0]

        poly_found = False
        for p in polygons:
            if "homography" in p or p.get("id") in ("POLY_1", "POLY_SPEED"):
                p["homography"] = {
                    "src": payload.rectangle.image_points,
                    "dst": world,
                    "measured_at": datetime.now().isoformat(),
                }
                p["road_dir"] = speed_rdir
                if not p.get("polygon"):
                    p["polygon"] = payload.rectangle.image_points
                p.setdefault("rules", {})["speeding"] = {"enable": True}
                poly_found = True
                break
        if not poly_found:
            polygons.append({
                "id": "POLY_1",
                "kind": "directional",
                "polygon": payload.rectangle.image_points,
                "road_dir": speed_rdir,
                "rules": {"speeding": {"enable": True}},
                "homography": {
                    "src": payload.rectangle.image_points,
                    "dst": world,
                    "measured_at": datetime.now().isoformat(),
                },
            })

    # 2. Stop Line
    if payload.stop_line and len(payload.stop_line) == 2:
        stop_line_item = {
            "id": "STOP_1",
            "p1": payload.stop_line[0],
            "p2": payload.stop_line[1],
            "pt1": payload.stop_line[0],
            "pt2": payload.stop_line[1],
        }
        lines = [ln for ln in lines if ln.get("id") != "STOP_1"]
        lines.append(stop_line_item)
    elif payload.deleted_line_ids and "STOP_1" in payload.deleted_line_ids:
        lines = [ln for ln in lines if ln.get("id") != "STOP_1"]

    # 3. Traffic Light Box
    if payload.light_box and len(payload.light_box) == 4:
        coords = [float(x) for x in payload.light_box]
        sig_item = {
            "id": "SIGNAL_1",
            "roi": coords,
            "box": coords,
            "default": "red",
        }
        signals = [s for s in signals if s.get("id") != "SIGNAL_1"]
        signals.append(sig_item)
    elif payload.deleted_signal_ids and "SIGNAL_1" in payload.deleted_signal_ids:
        signals = [s for s in signals if s.get("id") != "SIGNAL_1"]

    # 4. Lanes
    if payload.lanes:
        for idx, lane in enumerate(payload.lanes):
            lane_id = lane.id or f"LANE_{idx + 1}"
            road_dir = None
            if lane.arrow and len(lane.arrow) == 2:
                dx = lane.arrow[1][0] - lane.arrow[0][0]
                dy = lane.arrow[1][1] - lane.arrow[0][1]
                mag = math.hypot(dx, dy)
                if mag > 0:
                    road_dir = [float(dx / mag), float(dy / mag)]

            existing = next((p for p in polygons if p.get("id") == lane_id), None)
            if existing:
                existing["polygon"] = lane.polygon
                if road_dir:
                    existing["road_dir"] = road_dir
                existing.setdefault("rules", {})["wrong_way"] = {"enable": True}
            else:
                p_item = {
                    "id": lane_id,
                    "kind": "directional",
                    "polygon": lane.polygon,
                    "rules": {"wrong_way": {"enable": True}},
                }
                if road_dir:
                    p_item["road_dir"] = road_dir
                polygons.append(p_item)

    # 5. Rule Zones (speeding, wrong_way, no_uturn, no_entry_road, no_parking, no_gathering, red_light_running, stop_line_violation)
    if payload.rule_zones:
        for rz in payload.rule_zones:
            if not rz.enabled or not rz.polygon:
                continue
            zone_id = rz.id or f"ZONE_{rz.rule_type.upper()}"
            existing = next((p for p in polygons if p.get("id") == zone_id), None)
            
            if rz.rule_type == "speeding" and len(rz.polygon) == 4:
                world = [[0.0, 0.0], [7.5, 0.0], [7.5, 50.0], [0.0, 50.0]]
                item = {
                    "id": zone_id,
                    "kind": "directional",
                    "polygon": rz.polygon,
                    "rules": {"speeding": {"enable": True, "limit_kmh": rz.speed_limit_kmh or 50.0}},
                    "homography": {"src": rz.polygon, "dst": world, "measured_at": datetime.now().isoformat()},
                }
            elif rz.rule_type == "wrong_way":
                road_dir = None
                lines_for_poly = []
                if rz.arrow and len(rz.arrow) == 2:
                    dx = rz.arrow[1][0] - rz.arrow[0][0]
                    dy = rz.arrow[1][1] - rz.arrow[0][1]
                    mag = math.hypot(dx, dy)
                    if mag > 0:
                        road_dir = [float(dx / mag), float(dy / mag)]
                        mx = (rz.arrow[0][0] + rz.arrow[1][0]) / 2.0
                        my = (rz.arrow[0][1] + rz.arrow[1][1]) / 2.0
                        px, py = -dy / mag, dx / mag
                        span = 80.0
                        lines_for_poly.append({
                            "id": f"LINE_{zone_id}",
                            "p1": [round(mx - px * span, 1), round(my - py * span, 1)],
                            "p2": [round(mx + px * span, 1), round(my + py * span, 1)],
                            "allowed_sign": 1,
                        })
                item = {
                    "id": zone_id,
                    "kind": "directional",
                    "polygon": rz.polygon,
                    "road_dir": road_dir,
                    "rules": {"wrong_way": {"enable": True}},
                }
                if lines_for_poly:
                    item["lines"] = lines_for_poly
            elif rz.rule_type in ("no_uturn", "no_entry_road", "no_parking", "no_gathering"):
                r_cfg = {"enable": True}
                if rz.dwell_s is not None:
                    r_cfg["dwell_s"] = float(rz.dwell_s)
                if rz.min_persons is not None:
                    r_cfg["min_persons"] = int(rz.min_persons)
                item = {
                    "id": zone_id,
                    "kind": "banned" if rz.rule_type in ("no_entry_road", "no_parking") else "zone",
                    "polygon": rz.polygon,
                    "rules": {rz.rule_type: r_cfg},
                }
            else:
                continue

            if existing:
                idx = polygons.index(existing)
                # merge rules to preserve any other active rule flags
                old_rules = dict(existing.get("rules", {}))
                old_rules.update(item.get("rules", {}))
                item["rules"] = old_rules
                polygons[idx] = item
            else:
                polygons.append(item)

    config["polygons"] = polygons
    config["lines"] = lines
    if signals:
        config["signals"] = signals

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
async def camera_stream(camera_id: str, db: Session = Depends(get_db)):
    camera = require_camera(camera_id, db)
    worker = registry.get(camera_id)
    if worker is None or not worker.is_running():
        raise HTTPException(status_code=409, detail="Camera is not running. Start it first.")

    boundary = "frame"

    async def generate():
        last_frame = None
        try:
            while worker.is_running():
                jpeg = worker.get_latest_jpeg()
                if jpeg is not None and (last_frame is None or jpeg != last_frame):
                    last_frame = jpeg
                    yield (
                        b"--" + boundary.encode() + b"\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + jpeg
                        + b"\r\n"
                    )
                await asyncio.sleep(0.033)
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        generate(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "close",
        },
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

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from sqlalchemy import delete

from ..config import PROJECT_ROOT, VISION_CONFIG_PATH
from ..database import SessionLocal
from ..models import ProcessingJob, ViolationEvent
from ..websocket import manager
from .sources import UploadedFileSource


if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.engine import TrafficPipelineEngine


executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vision-worker")


def enqueue_job(job_id: str) -> None:
    executor.submit(process_job, job_id)


def _event_slug(event_type: str, track_id: Any, frame: int) -> str:
    clean_type = re.sub(r"[^A-Za-z0-9_-]+", "_", str(event_type))
    clean_track = re.sub(r"[^A-Za-z0-9_-]+", "_", str(track_id))
    return f"{clean_type}_track{clean_track}_frame{frame}"


def clean_metadata_for_json(obj: Any) -> Any:
    """Recursively sanitize metadata for JSON persistence and API payloads.

    Strips heavy binary image arrays and frame buffers (triptych, video_frames, crop,
    etc.), and converts NumPy types to native Python types.
    """
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            # Drop heavy image/video frame buffers
            if k in {"triptych", "video_frames", "evidence_frame", "start_frame", "peak_frame", "crop"}:
                continue
            if k == "pedestrian_crops" and isinstance(v, list):
                cleaned[k] = [
                    {sub_k: clean_metadata_for_json(sub_v) for sub_k, sub_v in item.items() if sub_k != "crop"}
                    if isinstance(item, dict)
                    else clean_metadata_for_json(item)
                    for item in v
                ]
                continue
            cleaned[k] = clean_metadata_for_json(v)
        return cleaned

    if isinstance(obj, (list, tuple)):
        res = []
        for item in obj:
            # If item is a multi-dimensional numpy array or serialized image matrix, drop it
            if isinstance(item, np.ndarray) and (item.ndim >= 2 or item.size > 200):
                continue
            if isinstance(item, list) and len(item) > 0:
                first = item[0]
                if isinstance(first, list) and len(first) > 50:
                    continue
            res.append(clean_metadata_for_json(item))
        return res

    if isinstance(obj, np.ndarray):
        if obj.ndim <= 2 and obj.size <= 200:
            return obj.tolist()
        return None

    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, set):
        return [clean_metadata_for_json(x) for x in obj]
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "to_dict"):
        return clean_metadata_for_json(obj.to_dict())
    if hasattr(obj, "tolist"):
        try:
            arr = obj.tolist()
            if isinstance(arr, list) and len(arr) > 0 and isinstance(arr[0], list):
                return None
            return arr
        except Exception:
            pass

    return obj


def safe_json_dumps(obj: Any) -> str:
    cleaned = clean_metadata_for_json(obj)
    return json.dumps(cleaned)


def _draw_label_badge(
    img: np.ndarray,
    text: str,
    x: int,
    y: int,
    bg_color: tuple = (0, 0, 220),
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.65
    thickness = 2
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
    badge_y1 = max(0, y - th - 12)
    badge_y2 = y
    badge_x1 = max(0, x)
    badge_x2 = min(img.shape[1], x + tw + 16)

    cv2.rectangle(img, (badge_x1, badge_y1), (badge_x2, badge_y2), bg_color, -1)
    cv2.putText(
        img,
        text,
        (badge_x1 + 8, badge_y2 - 6),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def render_evidence_frame(
    raw_frame: np.ndarray,
    event: Dict[str, Any],
    lines: Optional[List[Dict[str, Any]]] = None,
    polygons: Optional[List[Dict[str, Any]]] = None,
) -> np.ndarray:
    """Render an evidence screenshot on a copy of the clean frame,
    drawing ONLY the violating object's bounding box and violation markers,
    leaving all other vehicles/pedestrians clean without bounding boxes.
    """
    img = raw_frame.copy()
    h_img, w_img = img.shape[:2]
    ev_type = str(event.get("type", "violation")).replace("_", " ").upper()
    track_id = event.get("track_id", "")
    extra = event.get("extra") or {}

    # 1. If line_id is specified, draw the violated line
    line_id = event.get("line_id")
    if lines and line_id:
        for ln in lines:
            if ln.get("id") == line_id:
                p1 = tuple(int(v) for v in ln["p1"])
                p2 = tuple(int(v) for v in ln["p2"])
                cv2.line(img, p1, p2, (0, 0, 255), 3)
                break

    # 2. If zone_id or pid is specified, draw that zone polygon
    zone_id = extra.get("zone_id") or extra.get("pid")
    if polygons and zone_id:
        for p in polygons:
            if p.get("id") == zone_id:
                pts = [(int(x), int(y)) for x, y in (p.get("polygon") or [])]
                if len(pts) >= 3:
                    for a, b in zip(pts, pts[1:] + pts[:1]):
                        cv2.line(img, a, b, (0, 0, 255), 3)
                break

    # 3. Handle Gathering violations
    if event.get("type") == "no_gathering":
        # Draw bboxes of gathering persons only
        person_bboxes = extra.get("person_bboxes") or []
        for pbb in person_bboxes:
            if pbb and len(pbb) == 4:
                px1, py1, px2, py2 = [int(v) for v in pbb]
                px1, py1 = max(0, px1), max(0, py1)
                px2, py2 = min(w_img - 1, px2), min(h_img - 1, py2)
                cv2.rectangle(img, (px1, py1), (px2, py2), (0, 165, 255), 2)
        gbb = event.get("bbox")
        if gbb and len(gbb) == 4:
            gx1, gy1, gx2, gy2 = [int(v) for v in gbb]
            gx1, gy1 = max(0, gx1), max(0, gy1)
            gx2, gy2 = min(w_img - 1, gx2), min(h_img - 1, gy2)
            cv2.rectangle(img, (gx1, gy1), (gx2, gy2), (0, 0, 255), 3)
            label = f"NO GATHERING | {len(person_bboxes)} PERSONS"
            _draw_label_badge(img, label, gx1, gy1, bg_color=(0, 0, 220))
        return img

    # 4. Standard vehicle violation: Draw ONLY the violating vehicle bbox
    bbox = event.get("bbox")
    if bbox is not None and len(bbox) == 4:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_img - 1, x2), min(h_img - 1, y2)

        # Draw red violation bounding box
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)

        # Bottom center point
        bc = event.get("bc")
        if bc is not None and len(bc) >= 2:
            cv2.circle(img, (int(bc[0]), int(bc[1])), 5, (0, 255, 255), -1)

        # Label badge
        label = f"VIOLATION: {ev_type} | ID {track_id}"
        speed_kmh = extra.get("speed_kmh")
        if speed_kmh:
            label += f" | {speed_kmh:.1f} km/h"
        _draw_label_badge(img, label, x1, y1, bg_color=(0, 0, 220))

    return img


def process_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        if job is None:
            return
        job.status = "processing"
        job.progress_percent = 0
        job.current_frame = 0
        job.error_message = None
        job.started_at = datetime.now(timezone.utc)
        input_path = Path(job.input_path)
        output_dir = Path(job.output_path)
        db.commit()

    manager.broadcast_from_thread(
        job_id,
        {"type": "progress", "progress_percent": 0, "current_frame": 0, "total_frames": 0},
    )

    try:
        (output_dir / "evidence" / "screenshots").mkdir(parents=True, exist_ok=True)
        (output_dir / "evidence" / "clips").mkdir(parents=True, exist_ok=True)

        source = UploadedFileSource(str(input_path))
        cap = cv2.VideoCapture(source.processing_uri())
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open video input: {input_path}")

        raw_fps = cap.get(cv2.CAP_PROP_FPS)
        fps_src = float(raw_fps) if (raw_fps and raw_fps > 0 and raw_fps == raw_fps) else 25.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

        engine = TrafficPipelineEngine(
            config_path=str(VISION_CONFIG_PATH),
            overrides={"camera": {"source": source.processing_uri()}},
        )
        engine.setup()

        raw_video_path = output_dir / "annotated_raw.mp4"
        final_video_path = output_dir / "annotated.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(raw_video_path), fourcc, fps_src, (width, height))

        events_collected = []
        frame_idx = 0

        def on_progress(cur: int, tot: int, pct: int) -> None:
            with SessionLocal() as db:
                j = db.get(ProcessingJob, job_id)
                if j:
                    j.current_frame = cur
                    j.total_frames = tot
                    j.progress_percent = pct
                    db.commit()
            manager.broadcast_from_thread(
                job_id,
                {"type": "progress", "progress_percent": pct, "current_frame": cur, "total_frames": tot},
            )

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            frame_idx += 1
            t_video = (frame_idx - 1) / fps_src

            tracks, new_events = engine.process_frame(frame, frame_idx, t_video)

            vis = engine.vis_renderer.render(
                frame,
                tracks,
                fps=fps_src,
                counts=engine.counts,
                frame_idx=frame_idx,
                t_video=t_video,
                signals=engine.signals,
                pedestrians=engine.last_peds,
                gathering_zones=engine.gathering_status,
            )
            writer.write(vis)

            # Handle events
            if new_events:
                all_lines = getattr(engine, "all_lines", None)
                plan_polys = getattr(getattr(engine, "plan", None), "polygons", None)

                for ev in new_events:
                    ev_type = str(ev.get("type", "violation"))
                    raw_tid = ev.get("track_id", 0)
                    try:
                        track_id: Any = int(raw_tid)
                    except (ValueError, TypeError):
                        track_id = str(raw_tid)
                    slug = _event_slug(ev_type, track_id, frame_idx)

                    # Save screenshot with ONLY violating bounding box
                    sc_rel = f"evidence/screenshots/{slug}.jpg"
                    sc_abs = output_dir / sc_rel
                    ev_vis = render_evidence_frame(
                        frame,
                        ev,
                        lines=all_lines,
                        polygons=plan_polys,
                    )
                    cv2.imwrite(str(sc_abs), ev_vis)

                    ev_info = {
                        "type": ev_type,
                        "track_id": track_id,
                        "slug": slug,
                        "frame": frame_idx,
                        "time_s": t_video,
                        "screenshot": sc_rel,
                        "clip": None,
                        "extra": clean_metadata_for_json(ev.get("extra", {})),
                        "bbox": clean_metadata_for_json(ev.get("bbox")),
                        "line_id": ev.get("line_id"),
                    }
                    events_collected.append(ev_info)

            # Periodic progress update
            if frame_idx % 10 == 0 or frame_idx == total_frames:
                pct = int(min(99, (frame_idx / total_frames) * 100))
                on_progress(frame_idx, total_frames, pct)

        cap.release()
        writer.release()
        engine.teardown()

        # Re-encode video with ffmpeg to h264 for web playback
        if raw_video_path.exists():
            try:
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-i",
                        str(raw_video_path),
                        "-c:v",
                        "libx264",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        str(final_video_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                raw_video_path.unlink(missing_ok=True)
            except Exception as e:
                logging.warning("ffmpeg h264 encode failed, using raw mp4v: %s", e)
                raw_video_path.replace(final_video_path)

        # Slice short clips for events
        for ev in events_collected:
            slug = ev.get("slug") or _event_slug(ev["type"], ev["track_id"], ev["frame"])
            clip_rel = f"evidence/clips/{slug}.mp4"
            clip_abs = output_dir / clip_rel
            start_sec = max(0.0, ev["time_s"] - 2.5)
            duration_sec = 5.0
            if final_video_path.exists():
                try:
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-ss",
                            str(start_sec),
                            "-i",
                            str(final_video_path),
                            "-t",
                            str(duration_sec),
                            "-c:v",
                            "libx264",
                            "-pix_fmt",
                            "yuv420p",
                            "-movflags",
                            "+faststart",
                            str(clip_abs),
                        ],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if clip_abs.exists():
                        ev["clip"] = clip_rel
                except Exception:
                    pass

        # Save to database
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if job is None:
                return
            db.execute(delete(ViolationEvent).where(ViolationEvent.job_id == job_id))
            for event in events_collected:
                extra = event.get("extra") or {}
                speed_val = extra.get("speed_kmh")
                ev_type = event["type"]
                severity = (
                    "high"
                    if ev_type in ("red_light_running", "wrong_way", "no_entry_road")
                    else ("medium" if (speed_val or 0) > 80 else "low")
                )

                db.add(
                    ViolationEvent(
                        job_id=job_id,
                        type=ev_type,
                        track_id=event["track_id"],
                        frame=event["frame"],
                        time_s=event["time_s"],
                        severity=severity,
                        speed_kmh=speed_val,
                        world_x=None,
                        world_y=None,
                        lane_id=str(event.get("line_id") or ""),
                        light_phase=str(extra.get("signal_state") or ""),
                        screenshot_path=event.get("screenshot"),
                        clip_path=event.get("clip"),
                        measured_json=safe_json_dumps(extra),
                        evidence_json=safe_json_dumps(event),
                    )
                )
            job.status = "completed"
            job.progress_percent = 100
            job.current_frame = total_frames
            job.total_frames = total_frames
            job.completed_at = datetime.now(timezone.utc)
            db.commit()

        manager.broadcast_from_thread(
            job_id,
            {"type": "complete", "status": "completed", "progress_percent": 100},
        )
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = f"{type(exc).__name__}: {exc}"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
        traceback.print_exc()
        manager.broadcast_from_thread(
            job_id,
            {"type": "failed", "status": "failed", "error_message": str(exc)},
        )

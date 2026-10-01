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
            if k in {
                "triptych",
                "video_frames",
                "evidence_frame",
                "cross_frame",
                "shot1",
                "shot3",
                "start_frame",
                "peak_frame",
                "crop",
            }:
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
    return obj


def safe_json_dumps(obj: Any) -> str:
    cleaned = clean_metadata_for_json(obj)
    try:
        return json.dumps(cleaned, ensure_ascii=False)
    except Exception:
        return "{}"


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


def _annotate_single_evidence_shot(
    base_frame: np.ndarray,
    event: Dict[str, Any],
    bbox: Optional[Any] = None,
    bc: Optional[Any] = None,
    lines: Optional[List[Dict[str, Any]]] = None,
    polygons: Optional[List[Dict[str, Any]]] = None,
    badge_title: Optional[str] = None,
    badge_subtitle: Optional[str] = None,
) -> np.ndarray:
    """Helper to draw ONLY the designated vehicle bbox, bottom center, and line/polygon on a frame."""
    img = base_frame.copy()
    h_img, w_img = img.shape[:2]
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

    # 3. Draw ONLY the target vehicle bounding box and bottom-center
    target_bb = bbox if bbox is not None else event.get("bbox")
    if target_bb is not None and len(target_bb) == 4:
        x1, y1, x2, y2 = [int(v) for v in target_bb]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_img - 1, x2), min(h_img - 1, y2)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)

        target_bc = bc if bc is not None else event.get("bc")
        if target_bc is not None and len(target_bc) >= 2:
            cv2.circle(img, (int(target_bc[0]), int(target_bc[1])), 5, (0, 255, 255), -1)

        if badge_title:
            _draw_label_badge(img, badge_title, x1, y1, bg_color=(0, 0, 220))
        if badge_subtitle:
            cv2.putText(
                img,
                badge_subtitle,
                (max(10, x1), min(h_img - 10, y2 + 22)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

    return img


def render_evidence_frame(
    raw_frame: np.ndarray,
    event: Dict[str, Any],
    lines: Optional[List[Dict[str, Any]]] = None,
    polygons: Optional[List[Dict[str, Any]]] = None,
) -> np.ndarray:
    """Render an evidence screenshot on a copy of the clean frame,
    drawing ONLY the violating object's bounding box and violation markers,
    leaving all other vehicles/pedestrians clean without bounding boxes.

    - For red light running: stacks 3 moments (1: before stop line, 2: touching stop line, 3: entering intersection).
    - For stop line violation: captures ONLY the single frame when touching stop line.
    - For other violations: captures the single clean frame with the violating object's bbox.
    """
    ev_type = str(event.get("type", "violation"))
    track_id = event.get("track_id", "")
    extra = event.get("extra") or {}
    triptych = extra.get("triptych")

    # 1. Red Light Running: Luu 3 khoanh khac (truoc vach, de vach, di vao giao lo)
    if ev_type in ("red_light_running", "red_light"):
        if triptych and isinstance(triptych, (list, tuple)) and len(triptych) >= 2:
            caps = extra.get(
                "triptych_captions",
                ["1 TRUOC VACH", "2 DE VACH", "3 DI VAO GIAO LO"]
                if len(triptych) >= 3
                else ["1 DE VACH", "2 DI VAO GIAO LO"],
            )
            bboxes = extra.get("triptych_bboxes") or []
            bcs = extra.get("triptych_bcs") or []
            timestamps = extra.get("triptych_timestamps") or []

            shots = []
            for i, fr in enumerate(triptych[:3]):
                shot_fr = fr if fr is not None else raw_frame
                cap = caps[i] if i < len(caps) else f"SHOT {i+1}"
                bb_i = bboxes[i] if i < len(bboxes) and bboxes[i] is not None else event.get("bbox")
                bc_i = bcs[i] if i < len(bcs) and bcs[i] is not None else event.get("bc")
                ts_i = timestamps[i] if i < len(timestamps) else event.get("t", 0.0)

                badge = f"{cap} | ID {track_id}"
                sub = (
                    f"VUOT DEN DO | t={ts_i:.2f}s"
                    if isinstance(ts_i, (int, float))
                    else f"VUOT DEN DO | {ts_i}"
                )
                shot_img = _annotate_single_evidence_shot(
                    shot_fr,
                    event,
                    bbox=bb_i,
                    bc=bc_i,
                    lines=lines,
                    polygons=polygons,
                    badge_title=badge,
                    badge_subtitle=sub,
                )
                shots.append(shot_img)

            w = max(s.shape[1] for s in shots)
            norm = [
                s if s.shape[1] == w else cv2.resize(s, (w, int(s.shape[0] * w / s.shape[1])))
                for s in shots
            ]
            return cv2.vconcat(norm)

    # 2. Stop Line Violation: CHI luu frame de vach (single frame)
    if ev_type in ("stop_line_violation", "stop_line"):
        cross_fr = None
        cross_bb = None
        cross_bc = None
        cross_t = None

        if triptych and isinstance(triptych, (list, tuple)) and len(triptych) > 0:
            cross_fr = triptych[0]
            bboxes = extra.get("triptych_bboxes") or []
            if bboxes and bboxes[0] is not None:
                cross_bb = bboxes[0]
            bcs = extra.get("triptych_bcs") or []
            if bcs and bcs[0] is not None:
                cross_bc = bcs[0]
            ts = extra.get("triptych_timestamps") or []
            if ts and ts[0] is not None:
                cross_t = ts[0]

        if cross_fr is None:
            cross_fr = extra.get("cross_frame") or extra.get("evidence_frame") or raw_frame
        if cross_bb is None:
            cross_bb = extra.get("cross_bbox") or event.get("bbox")
        if cross_bc is None:
            cross_bc = extra.get("cross_bc") or event.get("bc")
        if cross_t is None:
            cross_t = event.get("t", 0.0)

        badge = f"DE VACH DUNG | ID {track_id}"
        sub = (
            f"STOP LINE | t={cross_t:.2f}s"
            if isinstance(cross_t, (int, float))
            else f"STOP LINE | {cross_t}"
        )
        return _annotate_single_evidence_shot(
            cross_fr,
            event,
            bbox=cross_bb,
            bc=cross_bc,
            lines=lines,
            polygons=polygons,
            badge_title=badge,
            badge_subtitle=sub,
        )

    # 3. Handle Gathering violations
    if ev_type == "no_gathering":
        img = raw_frame.copy()
        h_img, w_img = img.shape[:2]
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
    ev_title = ev_type.replace("_", " ").upper()
    badge = f"VIOLATION: {ev_title} | ID {track_id}"
    speed_kmh = extra.get("speed_kmh")
    sub = f"SPEED: {speed_kmh:.1f} km/h" if speed_kmh else None

    return _annotate_single_evidence_shot(
        raw_frame,
        event,
        bbox=event.get("bbox"),
        bc=event.get("bc"),
        lines=lines,
        polygons=polygons,
        badge_title=badge,
        badge_subtitle=sub,
    )


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

            res = engine.process_frame(frame, frame_idx, t_video)
            if isinstance(res, dict):
                tracks = res.get("tracks", {})
                new_events = res.get("events", [])
            else:
                tracks, new_events = res

            # Handle events FIRST using pristine, unannotated frame
            if new_events:
                all_lines = getattr(engine, "all_lines", None)
                plan_polys = (
                    getattr(getattr(engine, "vis_renderer", None), "polygons", None)
                    or (engine.cfg.get("polygons", []) if hasattr(engine, "cfg") else None)
                )

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
                    sc_abs.parent.mkdir(parents=True, exist_ok=True)
                    ev_vis = render_evidence_frame(
                        frame,
                        ev,
                        lines=all_lines,
                        polygons=plan_polys,
                    )
                    cv2.imwrite(str(sc_abs), ev_vis, [int(cv2.IMWRITE_JPEG_QUALITY), 90])

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

            # Render overlay on a copy of the frame for the annotated video
            vis = engine.vis_renderer.render(
                frame.copy(),
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

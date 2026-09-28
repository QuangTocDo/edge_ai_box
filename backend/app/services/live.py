from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from ..config import PROJECT_ROOT
from ..database import SessionLocal
from ..models import Camera, CameraEvent
from ..websocket import manager
from .processing import render_evidence_frame, safe_json_dumps
from .sources import VideoSource, build_source


if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.pipeline.engine import TrafficPipelineEngine


# Health states surfaced to the dashboard.
OFFLINE = "Offline"
CONNECTING = "Connecting"
LIVE = "Live"
RECONNECTING = "Reconnecting"
ERROR = "Error"

# Bounded exponential backoff for RTSP reconnects.
_BACKOFF_START_S = 1.0
_BACKOFF_MAX_S = 30.0

# How often to push a routine status frame over the WebSocket (seconds).
_STATUS_INTERVAL_S = 0.5


def ws_key(camera_id: str) -> str:
    """WebSocket channel key. Prefixed so it never collides with job ids."""
    return f"cam:{camera_id}"


class LiveCameraWorker:
    """Owns the background capture thread, pipeline, and state for one camera."""

    def __init__(
        self,
        camera_id: str,
        source: VideoSource,
        config_path: str,
        evidence_dir: str,
        fps_hint: float = 15.0,
    ) -> None:
        self.camera_id = camera_id
        self.source = source
        self.config_path = config_path
        self.evidence_dir = Path(evidence_dir)
        self.fps_hint = fps_hint

        self.status = OFFLINE
        self.last_error: Optional[str] = None
        self.measured_fps: float = 0.0
        self.processed_frames: int = 0
        self.active_vehicles: int = 0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._jpeg_lock = threading.Lock()
        self._latest_jpeg: Optional[bytes] = None

        self.screenshot_dir = self.evidence_dir / "evidence" / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_main,
            name=f"live-cam-{self.camera_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._set_status(OFFLINE)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # -- worker thread -------------------------------------------------------

    def _worker_main(self) -> None:
        backoff = _BACKOFF_START_S
        while not self._stop_event.is_set():
            try:
                self._set_status(CONNECTING)
                cap = self.source.open()
                backoff = _BACKOFF_START_S
                self._set_status(LIVE)
                self._run_loop(cap)
            except Exception as exc:
                self._set_status(ERROR, error=f"{type(exc).__name__}: {exc}")
                traceback.print_exc()
            finally:
                try:
                    self.source.close()
                except Exception:
                    pass

            if self._stop_event.is_set():
                break

            self._set_status(RECONNECTING)
            # Sleep with periodic checks for cancel
            deadline = time.time() + backoff
            while time.time() < deadline and not self._stop_event.is_set():
                time.sleep(0.2)
            backoff = min(backoff * 2, _BACKOFF_MAX_S)

        self._set_status(OFFLINE)

    def _run_loop(self, cap: cv2.VideoCapture) -> None:
        engine = TrafficPipelineEngine(
            config_path=self.config_path,
            overrides={"camera": {"source": self.source.processing_uri()}},
        )
        engine.setup()

        frame_idx = 0
        fps_tracker: deque[float] = deque(maxlen=30)
        last_t = time.time()
        last_status_push = 0.0

        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    # Video files loop; RTSP drops indicate stream ended
                    if getattr(self.source, "is_finite", False):
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    raise RuntimeError("Stream read returned empty frame")

                now = time.time()
                dt = now - last_t
                last_t = now
                if dt > 0:
                    fps_tracker.append(1.0 / dt)
                    self.measured_fps = sum(fps_tracker) / len(fps_tracker)

                frame_idx += 1
                self.processed_frames = frame_idx
                time_s = frame_idx / (self.measured_fps or self.fps_hint)

                tracks, new_events = engine.process_frame(
                    frame,
                    frame_idx=frame_idx,
                    t_video=time_s,
                )

                self.active_vehicles = len(tracks)

                # Render overlays
                annotated = engine.vis_renderer.render(
                    frame,
                    tracks,
                    fps=self.measured_fps or self.fps_hint,
                    counts=engine.counts,
                    frame_idx=frame_idx,
                    t_video=time_s,
                    signals=engine.signals,
                    pedestrians=engine.last_peds,
                    gathering_zones=engine.gathering_status,
                )

                self._encode_jpeg(annotated)

                for event in new_events:
                    self._persist_event(event, frame, engine)

                if new_events:
                    self._push_status(force=True)
                elif now - last_status_push >= _STATUS_INTERVAL_S:
                    self._push_status()
                    last_status_push = now
        except Exception as exc:
            self._set_status(ERROR, error=f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
        finally:
            engine.teardown()

    def _encode_jpeg(self, annotated: np.ndarray) -> None:
        ok, buf = cv2.imencode(".jpg", annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            with self._jpeg_lock:
                self._latest_jpeg = buf.tobytes()

    def get_latest_jpeg(self) -> Optional[bytes]:
        with self._jpeg_lock:
            return self._latest_jpeg

    @staticmethod
    def _event_slug(event_type: str, track_id: Any, frame: int) -> str:
        clean_type = re.sub(r"[^A-Za-z0-9_-]+", "_", str(event_type))
        clean_track = re.sub(r"[^A-Za-z0-9_-]+", "_", str(track_id))
        return f"{clean_type}_track{clean_track}_frame{frame}"

    # -- persistence + status ------------------------------------------------

    def _persist_event(
        self,
        event: Dict[str, Any],
        raw_frame: np.ndarray,
        engine: Optional[TrafficPipelineEngine] = None,
    ) -> None:
        ev_type = str(event.get("type", "violation"))
        raw_tid = event.get("track_id", 0)
        try:
            track_id: Any = int(raw_tid)
        except (ValueError, TypeError):
            track_id = str(raw_tid)
        frame_idx = int(event.get("frame_idx", self.processed_frames))
        slug = self._event_slug(ev_type, track_id, frame_idx)

        # Save screenshot with ONLY violating bounding box
        sc_rel = f"evidence/screenshots/{slug}.jpg"
        sc_abs = self.evidence_dir / sc_rel
        all_lines = getattr(engine, "all_lines", None) if engine else None
        plan_polys = getattr(getattr(engine, "plan", None), "polygons", None) if engine else None
        ev_vis = render_evidence_frame(
            raw_frame,
            event,
            lines=all_lines,
            polygons=plan_polys,
        )
        cv2.imwrite(str(sc_abs), ev_vis)

        extra = dict(event.get("extra", {}) or {})
        speed_kmh = extra.get("speed_kmh")
        severity = (
            "high"
            if ev_type in ("red_light_running", "wrong_way", "no_entry_road")
            else ("medium" if (speed_kmh or 0) > 80 else "low")
        )

        try:
            with SessionLocal() as db:
                row = CameraEvent(
                    camera_id=self.camera_id,
                    type=ev_type,
                    track_id=track_id,
                    frame=frame_idx,
                    time_s=float(event.get("t", 0.0)),
                    severity=severity,
                    speed_kmh=speed_kmh,
                    world_x=None,
                    world_y=None,
                    lane_id=str(event.get("line_id") or ""),
                    light_phase=str(extra.get("signal_state") or ""),
                    screenshot_path=sc_rel,
                    clip_path=None,
                    measured_json=safe_json_dumps(extra),
                    evidence_json=safe_json_dumps(event),
                )
                db.add(row)
                db.commit()
        except Exception:
            traceback.print_exc()

    def _set_status(self, status: str, error: Optional[str] = None) -> None:
        self.status = status
        if error is not None or status in (LIVE, OFFLINE):
            self.last_error = error
        self._persist_status()
        self._push_status(force=True)

    def _persist_status(self) -> None:
        try:
            with SessionLocal() as db:
                cam = db.get(Camera, self.camera_id)
                if cam is not None:
                    cam.last_status = self.status
                    cam.last_error = self.last_error
                    db.commit()
        except Exception:
            pass

    def status_payload(self) -> Dict[str, Any]:
        return {
            "type": "status",
            "camera_id": self.camera_id,
            "status": self.status,
            "last_error": self.last_error,
            "fps": round(self.measured_fps, 1),
            "processed_frames": self.processed_frames,
            "active_vehicles": self.active_vehicles,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    def _push_status(self, force: bool = False) -> None:
        manager.broadcast_from_thread(ws_key(self.camera_id), self.status_payload())


class LiveCameraRegistry:
    """Tracks one worker per camera_id; prevents duplicate workers."""

    def __init__(self) -> None:
        self._workers: Dict[str, LiveCameraWorker] = {}
        self._lock = threading.Lock()

    def get(self, camera_id: str) -> Optional[LiveCameraWorker]:
        with self._lock:
            return self._workers.get(camera_id)

    def start(self, camera: Camera, fps_hint: float = 15.0) -> LiveCameraWorker:
        with self._lock:
            existing = self._workers.get(camera.id)
            if existing is not None and existing.is_running():
                return existing
            source = build_source(camera.source_type, camera.source_uri)
            worker = LiveCameraWorker(
                camera_id=camera.id,
                source=source,
                config_path=camera.config_path,
                evidence_dir=camera.evidence_path,
                fps_hint=fps_hint,
            )
            self._workers[camera.id] = worker
        worker.start()
        return worker

    def stop(self, camera_id: str) -> bool:
        with self._lock:
            worker = self._workers.pop(camera_id, None)
        if worker is None:
            return False
        worker.stop()
        return True

    def stop_all(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for worker in workers:
            worker.stop()


registry = LiveCameraRegistry()

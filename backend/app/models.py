from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    input_path: Mapped[str] = mapped_column(Text, nullable=False)
    output_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_frame: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_frames: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    events: Mapped[List["ViolationEvent"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="ViolationEvent.frame"
    )


class ViolationEvent(Base):
    __tablename__ = "violation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    track_id: Mapped[Any] = mapped_column(String(80), nullable=False)
    frame: Mapped[int] = mapped_column(Integer, nullable=False)
    time_s: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    speed_kmh: Mapped[Optional[float]] = mapped_column(Float)
    world_x: Mapped[Optional[float]] = mapped_column(Float)
    world_y: Mapped[Optional[float]] = mapped_column(Float)
    lane_id: Mapped[Optional[str]] = mapped_column(String(80))
    light_phase: Mapped[Optional[str]] = mapped_column(String(24))
    screenshot_path: Mapped[Optional[str]] = mapped_column(Text)
    clip_path: Mapped[Optional[str]] = mapped_column(Text)
    measured_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)

    job: Mapped[ProcessingJob] = relationship(back_populates="events")


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # "rtsp" | "webcam" | "file" — drives source construction.
    source_type: Mapped[str] = mapped_column(String(16), default="rtsp", nullable=False)
    # RTSP URL, webcam device index, or file path. For RTSP this may contain
    # credentials, so it is never returned raw by the API (see masking).
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    config_path: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_path: Mapped[str] = mapped_column(Text, nullable=False)
    # Until a camera has a validated homography, metric rules stay disabled and
    # the worker emits no violations (boxes only) instead of confident garbage.
    calibrated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Last known runtime state, persisted so the dashboard can render it even
    # before a WebSocket connects: Offline/Connecting/Live/Reconnecting/Error.
    last_status: Mapped[str] = mapped_column(String(16), default="Offline", nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    events: Mapped[List["CameraEvent"]] = relationship(
        back_populates="camera", cascade="all, delete-orphan", order_by="CameraEvent.id.desc()"
    )


class CameraEvent(Base):
    __tablename__ = "camera_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(80), nullable=False)
    track_id: Mapped[Any] = mapped_column(String(80), nullable=False)
    frame: Mapped[int] = mapped_column(Integer, nullable=False)
    time_s: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(24), nullable=False)
    speed_kmh: Mapped[Optional[float]] = mapped_column(Float)
    world_x: Mapped[Optional[float]] = mapped_column(Float)
    world_y: Mapped[Optional[float]] = mapped_column(Float)
    lane_id: Mapped[Optional[str]] = mapped_column(String(80))
    light_phase: Mapped[Optional[str]] = mapped_column(String(24))
    screenshot_path: Mapped[Optional[str]] = mapped_column(Text)
    clip_path: Mapped[Optional[str]] = mapped_column(Text)
    measured_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    camera: Mapped[Camera] = relationship(back_populates="events")

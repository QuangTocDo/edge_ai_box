from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    source_type: str
    status: str
    progress_percent: int
    current_frame: int
    total_frames: int
    error_message: Optional[str]
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    event_count: int = 0


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: str
    type: str
    track_id: Union[int, str]
    frame: int
    time_s: float
    severity: str
    speed_kmh: Optional[float]
    world_x: Optional[float]
    world_y: Optional[float]
    lane_id: Optional[str]
    light_phase: Optional[str]
    screenshot_url: Optional[str] = None
    clip_url: Optional[str] = None
    measured: Dict[str, Any]
    evidence: Dict[str, Any]


class CameraCreate(BaseModel):
    name: str
    source_type: str = "rtsp"  # rtsp | webcam | file
    source_uri: str
    enabled: bool = True


class CameraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_type: str
    source_uri: str  # masked for RTSP — never the raw credentialed URL
    calibrated: bool
    enabled: bool
    status: str
    last_error: Optional[str] = None
    created_at: datetime
    # Live runtime metrics, populated when a worker is active.
    fps: Optional[float] = None
    processed_frames: Optional[int] = None
    active_vehicles: Optional[int] = None
    event_count: int = 0


class CameraEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    camera_id: str
    type: str
    track_id: Union[int, str]
    frame: int
    time_s: float
    severity: str
    speed_kmh: Optional[float]
    world_x: Optional[float]
    world_y: Optional[float]
    lane_id: Optional[str]
    light_phase: Optional[str]
    screenshot_url: Optional[str] = None
    clip_url: Optional[str] = None
    measured: Dict[str, Any]
    evidence: Dict[str, Any]
    created_at: datetime


class CalibrationRectangle(BaseModel):
    # Four ground points clicked in order TL, TR, BR, BL, plus the real-world
    # size of that rectangle in metres (e.g. a lane segment: width 3.5, length 14).
    image_points: List[List[float]]
    width_m: float
    length_m: float


class CalibrationLane(BaseModel):
    id: str
    polygon: List[List[float]]
    arrow: List[List[float]]  # [tail, head] in image pixels = travel direction
    speed_limit_kmh: float = 50


class CalibrationRequest(BaseModel):
    rectangle: CalibrationRectangle
    stop_line: List[List[float]]  # two image points
    lanes: List[CalibrationLane] = []
    light_box: Optional[List[float]] = None  # [x1, y1, x2, y2] image pixels


class HomographyPreview(BaseModel):
    condition_number: float
    mean_error_m: float
    ok: bool
    message: str


class OverviewResponse(BaseModel):
    total_jobs: int
    completed_jobs: int
    processing_jobs: int
    failed_jobs: int
    total_events: int
    violations_by_type: Dict[str, int]
    severity_counts: Dict[str, int]
    recent_events: List[EventResponse]

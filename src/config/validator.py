"""Xac thuc cau hinh camera tu active.yaml bang Pydantic.

Kiem tra:
- Kieu du lieu va rang buoc cua cac tham so duoc truyen tu active.yaml
- Toa do polygon: it nhat 3 dinh, dinh dang [x, y], toa do so hop le
- Toa do line: p1 [x, y], p2 [x, y]
- ROI tin hieu den: [x1, y1, x2, y2]
- File trong so ONNX model: canh bao som neu file chua ton tai tren disk
- Hoan toan khong set cung gia tri mac dinh gia lap
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class ConfigValidationError(Exception):
    """Loi cau truc cau hinh nghiem trong khong the khoi dong pipeline."""
    pass


class LineSchema(BaseModel):
    id: str
    p1: List[float] = Field(..., min_length=2, max_length=2)
    p2: List[float] = Field(..., min_length=2, max_length=2)
    allowed_sign: Optional[int] = None
    role: Optional[str] = None
    signal_id: Optional[str] = None

    @field_validator("allowed_sign")
    @classmethod
    def check_sign(cls, v):
        if v is not None and v not in (-1, 0, 1):
            raise ValueError(f"allowed_sign phai la -1, 0 hoac 1, nhan duoc: {v}")
        return v


class PolygonSchema(BaseModel):
    id: str
    polygon: Optional[List[List[float]]] = None
    kind: Optional[str] = None
    rules: Optional[Dict[str, Any]] = None
    lines: Optional[List[LineSchema]] = None
    banned_classes: Optional[List[Union[str, int]]] = None
    active_hours: Optional[List[str]] = None
    dwell_s: Optional[float] = Field(default=None, ge=0.0)
    direction_vector: Optional[List[float]] = None

    @field_validator("polygon")
    @classmethod
    def check_polygon_pts(cls, pts):
        if pts is not None:
            if len(pts) < 3:
                raise ValueError(f"Polygon phai co it nhat 3 dinh, nhan duoc {len(pts)} dinh")
            for idx, pt in enumerate(pts):
                if len(pt) < 2:
                    raise ValueError(f"Dinh {idx} cua polygon phai co toa do [x, y], nhan duoc {pt}")
        return pts


class SignalSchema(BaseModel):
    id: str
    roi: Optional[List[float]] = None
    box: Optional[List[float]] = None

    @model_validator(mode="before")
    @classmethod
    def check_roi(cls, data: Any):
        if isinstance(data, dict):
            coords = data.get("roi") or data.get("box")
            if coords is None:
                raise ValueError("Signal phai co 'roi' hoac 'box'")
            data["roi"] = coords
            data["box"] = coords
        return data

    @field_validator("roi")
    @classmethod
    def check_roi_length(cls, v):
        if v is None or len(v) != 4:
            raise ValueError("roi phai co dung 4 toa do [x1, y1, x2, y2]")
        return v


class ModelSchema(BaseModel):
    weights: Optional[str] = None
    conf: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    iou: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    imgsz: Optional[int] = Field(default=None, ge=32)
    device: Optional[Union[str, int]] = None
    tracker: Optional[str] = None
    vote_interval: Optional[int] = Field(default=None, ge=1)
    window_size: Optional[int] = Field(default=None, ge=1)


class EvidenceSchema(BaseModel):
    dir: Optional[str] = None
    retention_days: Optional[int] = Field(default=None, ge=1)
    jpeg_quality: Optional[int] = Field(default=None, ge=10, le=100)


class CameraConfigSchema(BaseModel):
    # Toan bo thong so doc truc tiep tu active.yaml, khong set cung bat ky gia tri mac dinh nao
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    name: Optional[str] = None
    config_version: Optional[str] = None
    timezone: Optional[str] = None
    source: Optional[Union[str, int]] = None
    model: Optional[ModelSchema] = None
    evidence: Optional[EvidenceSchema] = None
    polygons: Optional[List[PolygonSchema]] = Field(default_factory=list)
    lines: Optional[List[LineSchema]] = Field(default_factory=list)
    signals: Optional[List[SignalSchema]] = Field(default_factory=list)

    model_config = {"extra": "allow"}


def validate_config_schema(raw_cfg: Dict[str, Any]) -> List[str]:
    """Validate toan bo schema cau hinh tu yaml.
    Tra ve list warning neu thieu thong tin quan trong nhung khong gay crash.
    Nem ConfigValidationError neu co loi kieu du lieu/schema vi pham rang buoc.
    """
    warnings: List[str] = []
    try:
        validated = CameraConfigSchema.model_validate(raw_cfg)
    except Exception as e:
        raise ConfigValidationError(f"[CONFIG SCHEMA ERROR] Cau truc active.yaml khong hop le: {e}")

    # Canh bao neu thieu dinh danh camera trong file active.yaml
    if not (validated.camera_id or validated.camera_name or validated.name):
        warnings.append("[CONFIG WARN] File active.yaml chua khai bao 'camera_id'.")

    # Kiem tra file weights model chinh
    if validated.model and validated.model.weights:
        w_path = Path(validated.model.weights)
        if not w_path.exists():
            warnings.append(
                f"[CONFIG WARN] Model weights khong ton tai tai '{w_path}'. "
                f"Hay dam bao da download file model onnx/pt truoc khi chay pipeline."
            )
    elif not validated.model:
        warnings.append("[CONFIG WARN] active.yaml chua khai bao muc 'model'.")

    # Kiem tra secondary model (pedestrian) neu co rule no_gathering
    sec_models = raw_cfg.get("secondary_models", {})
    ped_m = (raw_cfg.get("no_gathering") or {}).get("model") or sec_models.get("pedestrian") or {}
    if ped_m and "weights" in ped_m:
        pw = Path(ped_m["weights"])
        if not pw.exists():
            warnings.append(
                f"[CONFIG WARN] Secondary pedestrian model weights '{pw}' chua ton tai tren disk."
            )

    return warnings

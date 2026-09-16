"""Dung Tracker tu model config (seam de test/mock, tranh khoi tao cung trong main)."""
from .tracking import Tracker


def create_tracker(mc, imgsz_override=0):
    """mc: dict model trong camera config. imgsz_override>0 thi thang CLI."""
    return Tracker(weights=mc["weights"], conf=mc.get("conf", 0.4),
                   imgsz=imgsz_override or mc.get("imgsz", 640),
                   classes=mc.get("classes"),
                   tracker_cfg=mc.get("tracker", "ocsort.yaml"),
                   device=mc.get("device"))

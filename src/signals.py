"""LEGACY shim (P2 restructure): use src.inference instead."""
from src.inference.signals import (  # noqa: F401
    FLASHING_YELLOW, DEFAULT_HSV, SignalStore, classify_roi_hsv, pick_hsv_cfg,
)

__all__ = ["FLASHING_YELLOW", "DEFAULT_HSV", "SignalStore", "classify_roi_hsv", "pick_hsv_cfg"]

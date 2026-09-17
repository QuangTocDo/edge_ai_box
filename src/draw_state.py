"""LEGACY shim (P2 restructure): use src.calibration instead."""
from src.calibration.draw_state import DrawState, mode_label, nearest_line, resolve_enter_action  # noqa: F401

__all__ = ["DrawState", "mode_label", "nearest_line", "resolve_enter_action"]

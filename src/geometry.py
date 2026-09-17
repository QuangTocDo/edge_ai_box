"""LEGACY shim (P2 restructure): use src.utils instead."""
from src.utils.geometry import (  # noqa: F401
    allowed_vec, bottom_center, containing_polygons, crossing_sign,
    dist, distance_point_to_segment, dot, in_active_hours, line_near_or_in_polygon,
    now_minutes, parse_window, point_in_polygon, polygon_valid,
)

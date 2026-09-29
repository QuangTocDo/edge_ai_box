"""Centerline Spline & Arc-Length Integration for Curved & Straight Roads.

Supports:
- Straight roads: 2 points (P0 -> P1) with total length L meters.
- Curved roads: N >= 3 points sampled along curve, interpolated via Catmull-Rom spline.
- Arc-length projection: Maps any (u, v) pixel -> (s, d) where:
    s: distance along road curve in meters [0, L]
    d: lateral offset distance in pixels from the road curve.
- Speed estimation: v = Delta s / Delta t (immune to lateral swerving / bbox jitter).
"""
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np


class CenterlineSpline:
    """Parametric curve representation for road centerline with arc-length stations in meters."""

    def __init__(
        self,
        points: List[List[float]],
        length_m: float,
        stations: Optional[List[float]] = None,
        num_samples: int = 100,
    ):
        if len(points) < 2:
            raise ValueError("Centerline requires at least 2 points (start and end).")
        self.control_points = np.array(points, dtype=np.float64)
        self.length_m = float(length_m)
        if self.length_m <= 0:
            raise ValueError(f"length_m must be positive, got {length_m}")

        # If explicit stations (landmark distances) not provided, distribute proportionally to pixel distance
        if stations is not None and len(stations) == len(points):
            self.control_stations = np.array(stations, dtype=np.float64)
        else:
            chords = [0.0]
            for i in range(len(points) - 1):
                p1, p2 = self.control_points[i], self.control_points[i + 1]
                chords.append(chords[-1] + math.hypot(p2[0] - p1[0], p2[1] - p1[1]))
            total_chord = chords[-1] if chords[-1] > 1e-6 else 1.0
            self.control_stations = np.array(
                [c / total_chord * self.length_m for c in chords], dtype=np.float64
            )

        # Dense sampling along Catmull-Rom spline (or linear if 2 points)
        self.dense_points, self.dense_stations, self.dense_tangents = self._build_dense_curve(num_samples)

    def _build_dense_curve(self, num_samples: int):
        n = len(self.control_points)
        if n == 2:
            # Straight line: sample linearly
            ts = np.linspace(0.0, 1.0, num_samples)
            dense_pts = (1.0 - ts[:, None]) * self.control_points[0] + ts[:, None] * self.control_points[1]
            dense_stations = (1.0 - ts) * self.control_stations[0] + ts * self.control_stations[1]
            tan = self.control_points[1] - self.control_points[0]
            tan_norm = tan / (np.linalg.norm(tan) or 1.0)
            dense_tangents = np.tile(tan_norm, (num_samples, 1))
            return dense_pts, dense_stations, dense_tangents

        # Catmull-Rom Spline for curved roads (N >= 3 points)
        pts = self.control_points
        stations = self.control_stations
        dense_pts = []
        dense_stations = []
        dense_tangents = []

        sub_samples = max(10, num_samples // (n - 1))
        for i in range(n - 1):
            p0 = pts[max(0, i - 1)]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[min(n - 1, i + 2)]

            s1 = stations[i]
            s2 = stations[i + 1]

            t_vals = np.linspace(0.0, 1.0, sub_samples, endpoint=(i == n - 2))
            for t in t_vals:
                # Catmull-Rom formula: 0.5 * ((2*P1) + (-P0 + P2)*t + (2*P0 - 5*P1 + 4*P2 - P3)*t^2 + (-P0 + 3*P1 - 3*P2 + P3)*t^3)
                pt = 0.5 * (
                    2.0 * p1
                    + (-p0 + p2) * t
                    + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * (t**2)
                    + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * (t**3)
                )
                # Tangent derivative
                tan = 0.5 * (
                    (-p0 + p2)
                    + 2.0 * (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t
                    + 3.0 * (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * (t**2)
                )
                tn = float(np.linalg.norm(tan))
                tan_norm = tan / (tn if tn > 1e-6 else 1.0)
                st = s1 + t * (s2 - s1)

                dense_pts.append(pt)
                dense_stations.append(st)
                dense_tangents.append(tan_norm)

        return np.array(dense_pts), np.array(dense_stations), np.array(dense_tangents)

    def project(self, u: float, v: float) -> Tuple[float, float, Tuple[float, float]]:
        """Project pixel coordinate (u, v) onto centerline.

        Returns:
            s: Arc-length station in meters [0, length_m]
            d: Lateral distance in pixels from centerline
            tangent: Unit tangent vector (tx, ty) along road direction
        """
        P = np.array([float(u), float(v)], dtype=np.float64)
        pts = self.dense_points
        stations = self.dense_stations
        tangents = self.dense_tangents

        p1 = pts[:-1]
        p2 = pts[1:]
        v_seg = p2 - p1
        seg_len_sq = np.sum(v_seg**2, axis=1)
        seg_len_sq = np.where(seg_len_sq < 1e-9, 1e-9, seg_len_sq)

        w = P - p1
        tau = np.sum(w * v_seg, axis=1) / seg_len_sq
        tau_clamped = np.clip(tau, 0.0, 1.0)

        proj_pts = p1 + tau_clamped[:, None] * v_seg
        dist_sq = np.sum((P - proj_pts) ** 2, axis=1)

        best_idx = int(np.argmin(dist_sq))
        best_tau = float(tau_clamped[best_idx])
        min_dist = math.sqrt(float(dist_sq[best_idx]))

        s_val = float(stations[best_idx] + best_tau * (stations[best_idx + 1] - stations[best_idx]))
        tangent = (float(tangents[best_idx][0]), float(tangents[best_idx][1]))

        return s_val, min_dist, tangent

    def build_corridor_polygon(self, corridor_width_px: float = 60.0) -> List[List[float]]:
        """Tạo đa giác bao quanh làn đường (corridor) dọc theo đường cong tim đường."""
        half_w = float(corridor_width_px) / 2.0
        # Sample ~20-30 points along the dense curve for a clean polygon
        step = max(1, len(self.dense_points) // 25)
        indices = list(range(0, len(self.dense_points), step))
        if indices[-1] != len(self.dense_points) - 1:
            indices.append(len(self.dense_points) - 1)

        left_side: List[List[float]] = []
        right_side: List[List[float]] = []

        for idx in indices:
            pt = self.dense_points[idx]
            tx, ty = self.dense_tangents[idx]
            # Normal vector perpendicular to tangent (-ty, tx)
            nx, ny = -ty, tx
            left_pt = [round(float(pt[0] + nx * half_w), 1), round(float(pt[1] + ny * half_w), 1)]
            right_pt = [round(float(pt[0] - nx * half_w), 1), round(float(pt[1] - ny * half_w), 1)]
            left_side.append(left_pt)
            right_side.append(right_pt)

        # Polygon walks left side from start to end, then right side from end to start
        polygon = left_side + list(reversed(right_side))
        return polygon

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": self.control_points.tolist(),
            "length_m": self.length_m,
            "stations": self.control_stations.tolist(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CenterlineSpline":
        return cls(
            points=data["points"],
            length_m=data.get("length_m", 50.0),
            stations=data.get("stations"),
        )

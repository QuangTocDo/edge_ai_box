"""Homography pixel -> met tren mat phang duong (PROJECT_PLAN.md §4.5).

- Moi speed polygon co 1 ma tran H rieng (khuyen nghi homography doc §5).
- Build bang cv2.findHomography RANSAC, validate inlier + reproj error
  ngay luc load config (fail-fast).
"""
import math

import cv2
import numpy as np

from .constants import EPS, RANSAC_THRESH


def build_H(src_pts, dst_pts):
    """Dung ma tran H tu >=4 cap diem. Tra ve (H_list, inliers, err_m).

    Raises ValueError neu khong du diem hoac RANSAC that bai.
    """
    src = np.asarray(src_pts, dtype=np.float32)
    dst = np.asarray(dst_pts, dtype=np.float32)
    if src.shape[0] < 4 or dst.shape[0] < 4 or src.shape[0] != dst.shape[0]:
        raise ValueError(
            f"Can >=4 cap diem tuong ung, nhan {src.shape[0]}/{dst.shape[0]}")
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_THRESH)
    if H is None or mask is None:
        raise ValueError("RANSAC that bai: cac diem thang hang hoac suy bien")
    mask = mask.ravel().astype(bool)
    if int(mask.sum()) < 4:
        raise ValueError(
            f"RANSAC chi giu {int(mask.sum())} inliers (<4), kiem tra lai diem")
    proj = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
    err = float(np.linalg.norm(proj[mask] - dst[mask], axis=1).mean())
    return H.tolist(), int(mask.sum()), err


def pixel_to_road(H, u, v):
    """Map 1 diem pixel -> (X, Y) met. H la list 3x3."""
    m = np.asarray(H, dtype=np.float64).reshape(3, 3)
    p = m @ np.array([float(u), float(v), 1.0], dtype=np.float64)
    if abs(p[2]) < EPS:
        raise ValueError("Homography suy bien tai diem "
                         f"({u}, {v}): w~=0")
    return float(p[0] / p[2]), float(p[1] / p[2])


def longitudinal_dist(p1, p2, road_dir):
    """Quang duong chieu len huong duong (m). road_dir chua chuan hoa cung duoc."""
    dx, dy = road_dir
    n = math.hypot(dx, dy)
    if n < EPS:
        raise ValueError("road_dir suy bien (do dai ~0)")
    ux, uy = dx / n, dy / n
    return (p2[0] - p1[0]) * ux + (p2[1] - p1[1]) * uy

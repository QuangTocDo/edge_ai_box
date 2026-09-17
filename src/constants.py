"""LEGACY shim (P2 restructure): use src.utils instead."""
from src.utils.constants import (  # noqa: F401
    EPS, HOMOGRAPHY_MAX_ERR_M, RANSAC_THRESH, TRACK_MAX_AGE_FRAMES,
    TRACK_PTS_MAXLEN, TRACK_VEL_EMA_ALPHA,
)

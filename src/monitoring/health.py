"""Health helpers per-camera (tách từ pipeline._touch_heartbeat + Dockerfile HEALTHCHECK).

Giữ hành vi cũ: touch file mỗi giây video, HEALTHCHECK pass khi mtime <90s,
deploy.sh status LIVE khi <=30s.
"""
import os
import time
from pathlib import Path

LIVE_S = 30
HEALTHY_S = 90


def heartbeat_path(camera_id, explicit=""):
    if explicit:
        return explicit
    return os.environ.get("HEARTBEAT_FILE") or f"/app/data/heartbeat_{camera_id}"


def touch_heartbeat(path):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).touch()
    except Exception:
        pass


def heartbeat_age_s(path):
    try:
        return time.time() - os.path.getmtime(path)
    except OSError:
        return float("inf")


def is_live(path, threshold=LIVE_S):
    return heartbeat_age_s(path) <= threshold


def is_healthy(path, threshold=HEALTHY_S):
    return heartbeat_age_s(path) <= threshold

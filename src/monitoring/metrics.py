"""Metrics nhẹ per-camera (counts events trong pipeline loop).

Chưa gắn Prometheus; chỉ chuẩn hóa dict counts + render 1 dòng log.
Muốn exporter sau này: đọc dict này qua file /app/data/metrics_<CAM>.json.
"""
import json
import time
from pathlib import Path


def new_counts():
    return {"skipped": 0}


def bump(counts, event_type):
    counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def summary_line(frame_idx, total_s, fps, counts):
    avg = frame_idx / total_s if total_s > 0 else 0.0
    return f"Frames: {frame_idx} | Time: {total_s:.1f}s | Avg FPS: {avg:.1f} (live {fps:.1f}) | Events: {counts}"


def dump_json(path, camera_id, counts, fps=0.0):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({
            "camera_id": camera_id, "ts": time.time(),
            "fps": round(float(fps), 2), "counts": counts,
        }), encoding="utf-8")
    except Exception:
        pass

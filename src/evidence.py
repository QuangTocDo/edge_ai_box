"""Luu minh chung vi pham: evidence.jpg + metadata.json (PROJECT_PLAN.md muc 6.0)."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2


def save_event(frame, event, lines, class_names, out_dir="evidence",
               camera_id="CAM_TEST_01", config_version="cfg_v1",
               model_version="yolo26n_coco", jpeg_quality=90):
    """Ve overlay len ban sao frame, luu jpg + json. Tra ve (jpg_path, json_path)."""
    out = Path(out_dir) / event["type"]
    out.mkdir(parents=True, exist_ok=True)
    eid = uuid.uuid4().hex[:12]
    ts = datetime.now(timezone.utc).isoformat()

    img = frame.copy()
    x1, y1, x2, y2 = [int(v) for v in event["bbox"]]
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    bc = event["bc"]
    cv2.circle(img, (int(bc[0]), int(bc[1])), 6, (0, 255, 255), -1)
    for ln in lines:
        p1 = tuple(int(v) for v in ln["p1"])
        p2 = tuple(int(v) for v in ln["p2"])
        col = (255, 0, 0) if ln.get("role") == "divider" else (0, 255, 0)
        cv2.line(img, p1, p2, col, 2)
    cv2.putText(img, f"{event['type']} {ts}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    jpg = out / f"{eid}.jpg"
    cv2.imwrite(str(jpg), img,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    digest = hashlib.sha256(jpg.read_bytes()).hexdigest()

    cls = int(event["cls"])
    meta = {
        "event_id": eid,
        "camera_id": camera_id,
        "violation": event["type"],
        "timestamp": ts,
        "frame_idx": event["frame_idx"],
        "reference_point": "bottom_center",
        "bottom_center_coord": [round(float(bc[0]), 1), round(float(bc[1]), 1)],
        "bbox": [x1, y1, x2, y2],
        "track_id": int(event["track_id"]),
        "class_id": cls,
        "class": class_names.get(cls, str(cls)) if isinstance(class_names, dict)
        else (class_names[cls] if cls < len(class_names) else str(cls)),
        "confidence": round(float(event["conf"]), 3),
        "config_version": config_version,
        "model_version": model_version,
        "line_id": event["line_id"],
        "extra": event.get("extra", {}),
        "image_hash_sha256": digest,
    }
    js = out / f"{eid}.json"
    js.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return str(jpg), str(js)

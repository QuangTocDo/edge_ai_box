"""Luu minh chung vi pham theo ngay: out/camera/date=YYYY-MM-DD/violation/ (PROJECT_PLAN.md muc 6.0)."""
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2


def _now_local(tzname="Asia/Ho_Chi_Minh"):
    """Datetime hien tai theo timezone camera. Fallback UTC+7 neu thieu tzdata."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tzname)
    except Exception:
        tz = timezone(timedelta(hours=7))
    return datetime.now(tz)


def _resolve_time(event_time, tzname):
    if isinstance(event_time, datetime):
        if event_time.tzinfo is None:
            try:
                from zoneinfo import ZoneInfo
                event_time = event_time.replace(tzinfo=ZoneInfo(tzname))
            except Exception:
                event_time = event_time.replace(
                    tzinfo=timezone(timedelta(hours=7)))
        return event_time
    return _now_local(tzname)


def _event_paths(out_dir, camera_id, violation, ts_local):
    date_str = ts_local.strftime("%Y-%m-%d")
    out = Path(out_dir) / camera_id / f"date={date_str}" / violation
    out.mkdir(parents=True, exist_ok=True)
    return out, date_str


def _new_names(ts_local, suffix=""):
    eid = uuid.uuid4().hex[:8]
    file_ts = ts_local.strftime("%H%M%S") + f"_{ts_local.microsecond // 1000:03d}"
    stem = f"{file_ts}_{eid}{suffix}"
    return eid, stem


def prune_old_dates(cam_dir, retention_days=7):
    """Xoa thu muc date=YYYY-MM-DD qua han. Tra ve [dirs da xoa]."""
    try:
        days = int(retention_days)
    except (TypeError, ValueError):
        return []
    if days <= 0:
        return []
    base = Path(cam_dir)
    if not base.is_dir():
        return []
    today = _now_local().date()
    removed = []
    for d in base.glob("date=*"):
        if not d.is_dir():
            continue
        try:
            ddate = datetime.strptime(d.name[len("date="):], "%Y-%m-%d").date()
        except ValueError:
            continue  # ten la -> bo qua, khong xoa
        if ddate == today:
            continue
        if (today - ddate).days > days:
            shutil.rmtree(d, ignore_errors=True)
            removed.append(str(d))
    return removed


def save_event(frame, event, lines, class_names, out_dir="evidence",
               camera_id="CAM_TEST_01", config_version="cfg_v1",
               model_version="best_v1", jpeg_quality=90,
               timezone_name="Asia/Ho_Chi_Minh", event_time=None,
               retention_days=7):
    """Ve overlay len ban sao frame, luu jpg + json theo ngay. Tra ve (jpg, json)."""
    ts_local = _resolve_time(event_time, timezone_name)
    out, date_str = _event_paths(out_dir, camera_id, event["type"], ts_local)
    eid, stem = _new_names(ts_local)
    ts = ts_local.isoformat()

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

    jpg = out / f"{stem}.jpg"
    cv2.imwrite(str(jpg), img,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    digest = hashlib.sha256(jpg.read_bytes()).hexdigest()

    cls = int(event["cls"])
    meta = {
        "event_id": eid,
        "camera_id": camera_id,
        "violation": event["type"],
        "timestamp": ts,
        "date": date_str,
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
    js = out / f"{stem}.json"
    js.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return str(jpg), str(js)


def _annotate(img, event, lines, caption, ts_text, class_names):
    x1, y1, x2, y2 = [int(v) for v in event["bbox"]]
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 3)
    bc = event["bc"]
    cv2.circle(img, (int(bc[0]), int(bc[1])), 6, (0, 255, 255), -1)
    for ln in lines:
        p1 = tuple(int(v) for v in ln["p1"])
        p2 = tuple(int(v) for v in ln["p2"])
        col = (255, 0, 0) if ln.get("role") == "divider" else (0, 255, 0)
        cv2.line(img, p1, p2, col, 2)
    cls = int(event["cls"])
    name = class_names.get(cls, str(cls)) if isinstance(class_names, dict) \
        else (class_names[cls] if cls < len(class_names) else str(cls))
    cv2.putText(img, f"{caption} | {name} {event['type']}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(img, ts_text, (10, 60),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    return img


def save_triptych(frames, frame_now, event, lines, class_names,
                  out_dir="evidence", camera_id="CAM_TEST_01",
                  config_version="cfg_v1", model_version="best_v1",
                  jpeg_quality=90, timezone_name="Asia/Ho_Chi_Minh",
                  event_time=None, retention_days=7):
    """Ghep doc 3 anh (truoc vach / de vach / trong nga tu) + 1 json chung.

    frames: [shot1|None, shot2|None, shot3|None] (BGR ndarrays).
    Tra ve (jpg_path, json_path).
    """
    ts_local = _resolve_time(event_time, timezone_name)
    out, date_str = _event_paths(out_dir, camera_id, event["type"], ts_local)
    eid, stem = _new_names(ts_local, suffix="_triptych")
    ts = ts_local.isoformat()
    stamps = event.get("extra", {}).get("triptych_timestamps", [])
    captions = ["1 TRUOC VACH", "2 DE VACH", "3 TRONG NGA TU"]
    shots = []
    for i, (fr, cap) in enumerate(zip(frames, captions)):
        if fr is None:
            fr = frame_now
        tst = stamps[i] if i < len(stamps) else ts
        shots.append(_annotate(fr.copy(), event, lines, cap, str(tst),
                               class_names))
    w = max(s.shape[1] for s in shots)
    norm = [s if s.shape[1] == w else cv2.resize(
        s, (w, int(s.shape[0] * w / s.shape[1]))) for s in shots]
    triptych = cv2.vconcat(norm)
    jpg = out / f"{stem}.jpg"
    cv2.imwrite(str(jpg), triptych, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])

    cls = int(event["cls"])
    meta = {
        "event_id": eid,
        "camera_id": camera_id,
        "violation": event["type"],
        "timestamp": ts,
        "date": date_str,
        "frame_idx": event["frame_idx"],
        "reference_point": "bottom_center",
        "bottom_center_coord": [round(float(event["bc"][0]), 1),
                                round(float(event["bc"][1]), 1)],
        "bbox": [int(v) for v in event["bbox"]],
        "track_id": int(event["track_id"]),
        "class_id": cls,
        "class": class_names.get(cls, str(cls))
        if isinstance(class_names, dict)
        else (class_names[cls] if cls < len(class_names) else str(cls)),
        "confidence": round(float(event["conf"]), 3),
        "config_version": config_version,
        "model_version": model_version,
        "line_id": event["line_id"],
        "extra": {k: v for k, v in event.get("extra", {}).items()
                  if k != "triptych"},
        "image_hash_sha256": hashlib.sha256(jpg.read_bytes()).hexdigest(),
    }
    js = out / f"{stem}.json"
    js.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    return str(jpg), str(js)

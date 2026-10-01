"""Ghi evidence local (khong day di dau).

- handle_event(): luu file local (save_event/save_triptych). Loi ghi file
  -> raise de caller bo event.
- AsyncEvidenceSaver: worker background luu evidence khong block inference loop.
- prune_evidence(): xoay vong thu muc date=* qua han (goi dinh ky, throttle).
"""
import logging
import queue
import threading
from pathlib import Path

from .evidence import prune_old_dates, save_event, save_triptych


def handle_event(e, *, frame, all_lines, names, out_dir, camera_id,
                 config_version, model_version, jpeg_quality,
                 timezone_name):
    """Luu file local. Tra ve (jpg_path, json_path).
    Loi ghi file -> raise de caller bo event."""
    tri = e["extra"].pop("triptych", None)
    ev_type = e.get("type")

    # Voi stop_line_violation: Chi can luu 1 frame de vach (cross_frame / shot 1 trong triptych)
    if ev_type in ("stop_line_violation", "stop_line"):
        target_fr = None
        if tri is not None and len(tri) > 0 and tri[0] is not None:
            target_fr = tri[0]
            bboxes = e.get("extra", {}).get("triptych_bboxes") or []
            if bboxes and bboxes[0] is not None:
                e["bbox"] = bboxes[0]
            bcs = e.get("extra", {}).get("triptych_bcs") or []
            if bcs and bcs[0] is not None:
                e["bc"] = bcs[0]
        if target_fr is None:
            target_fr = e["extra"].pop("evidence_frame", None)
        target = target_fr if target_fr is not None else frame
        jp, js = save_event(
            target, e, all_lines, names,
            out_dir=out_dir, camera_id=camera_id,
            config_version=config_version, model_version=model_version,
            jpeg_quality=jpeg_quality, timezone_name=timezone_name)
    elif tri is not None:
        jp, js = save_triptych(
            tri, frame, e, all_lines, names,
            out_dir=out_dir, camera_id=camera_id,
            config_version=config_version, model_version=model_version,
            jpeg_quality=jpeg_quality, timezone_name=timezone_name)
    else:
        ev_frame = e["extra"].pop("evidence_frame", None)
        target = ev_frame if ev_frame is not None else frame
        jp, js = save_event(
            target, e, all_lines, names,
            out_dir=out_dir, camera_id=camera_id,
            config_version=config_version, model_version=model_version,
            jpeg_quality=jpeg_quality, timezone_name=timezone_name)
    return jp, js


class AsyncEvidenceSaver:
    """Worker background de luu file evidence khong block vong lap tracking chinh."""

    def __init__(self, maxsize=100):
        self._q = queue.Queue(maxsize=maxsize)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="async-evidence-saver")
        self._thread.start()

    def submit(self, e, *, frame, all_lines, names, out_dir, camera_id,
               config_version, model_version, jpeg_quality, timezone_name):
        try:
            f_copy = frame.copy() if frame is not None else None
            e_copy = dict(e)
            if "extra" in e and isinstance(e["extra"], dict):
                e_copy["extra"] = dict(e["extra"])
                if "triptych" in e["extra"]:
                    e_copy["extra"]["triptych"] = [img.copy() for img in e["extra"]["triptych"]]
                if "evidence_frame" in e["extra"] and e["extra"]["evidence_frame"] is not None:
                    e_copy["extra"]["evidence_frame"] = e["extra"]["evidence_frame"].copy()
                if "video_frames" in e["extra"] and e["extra"]["video_frames"]:
                    e_copy["extra"]["video_frames"] = list(e["extra"]["video_frames"])
                if "pedestrian_crops" in e["extra"] and e["extra"]["pedestrian_crops"]:
                    e_copy["extra"]["pedestrian_crops"] = [dict(c) for c in e["extra"]["pedestrian_crops"]]
            self._q.put_nowait((e_copy, f_copy, all_lines, names, out_dir, camera_id,
                                config_version, model_version, jpeg_quality, timezone_name))
            return True
        except queue.Full:
            logging.warning("AsyncEvidenceSaver queue day (%d), bo qua event %s",
                            self._q.maxsize, e.get("type"))
            return False

    def _worker(self):
        # Tiep tuc xu ly cho den khi stop VA queue da duoc tieu thu het
        while not self._stop.is_set() or not self._q.empty():
            try:
                item = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            (e, frame, all_lines, names, out_dir, camera_id,
             config_version, model_version, jpeg_quality, timezone_name) = item
            try:
                jp, js = handle_event(
                    e, frame=frame, all_lines=all_lines, names=names,
                    out_dir=out_dir, camera_id=camera_id,
                    config_version=config_version, model_version=model_version,
                    jpeg_quality=jpeg_quality, timezone_name=timezone_name)
                logging.info("[%s] (async) track=%s line=%s -> %s",
                             e.get("type"), e.get("track_id"), e.get("line_id"), jp)
            except Exception:
                logging.exception("Async evidence saving loi (bo qua event)")
            finally:
                self._q.task_done()

    def stop(self, timeout=10.0):
        """Dung worker va doi ghi sach se cac event con ton dong trong queue."""
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)


def maybe_prune(ev_dir, camera_id, retention_days, last, now,
                interval_s=300.0):
    """Goi dinh ky tu pipeline: xoa thu muc date=* qua han. Tra ve last moi."""
    if now - last <= interval_s:
        return last
    try:
        removed = prune_old_dates(Path(ev_dir) / camera_id, retention_days)
        for d in removed:
            logging.info("Prune evidence cu: %s", d)
    except Exception:
        logging.exception("Prune evidence loi (bo qua)")

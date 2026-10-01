"""TrafficPipelineEngine: Dong goi toan bo vong doi thuc thi cua pipeline camera giao thong tai bien.

Kien truc sach:
- Setup: Nap & validate schema cau hinh, khoi tao model, tracker, object store, rules runner.
- Frame processing: Tracker -> Signals -> Rule evaluation -> Async secondary detector -> Object store.
- Async workers:
    + AsyncStreamReader: Chong tre RTSP buffer.
    + AsyncEvidenceSaver: Luu bang chung I/O khong chan loop.
    + AsyncPedestrianDetector: Worker thread rieng cho secondary model chong sụt FPS.
- Teardown: Don dep tai nguyen, xan evidence, dong database sach se.
"""
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import cv2

from ..camera.capture import (AsyncStreamReader, _is_stream, _mask_source,
                              _open_capture)
from ..config.loader import ConfigError, load_camera_config
from ..config.zones import iter_all_lines
from ..inference.detector import create_pedestrian_detector, create_tracker
from ..inference.signals import SignalStore
from ..monitoring.health import touch_heartbeat
from ..monitoring.visualizer import Visualizer
from ..pipeline.runner import (FrameContext, build_runners, run_first_event,
                              wanted_entries)
from ..storage.object_store import ObjectStore
from ..storage.sinks import AsyncEvidenceSaver, maybe_prune
from ..utils.geometry import now_minutes


def read_secret(name: str, default: str = "") -> str:
    """Doc secret: uu tien file {NAME}_FILE (vd /run/secrets/*), fallback env {NAME}."""
    fpath = os.environ.get(f"{name}_FILE", "")
    if fpath:
        try:
            val = Path(fpath).read_text(encoding="utf-8").strip()
            if val:
                return val
        except OSError as ex:
            logging.warning("Khong doc duoc secrets file %s (%s), fallback env %s",
                            fpath, ex, name)
    return os.environ.get(name, default)


def resolve_camera_source(args_source: Optional[str], cfg_source: Optional[Any]) -> Tuple[Any, str]:
    """Uu tien nguon dau vao theo thu tu:
    1. CLI args_source
    2. Secret / Env CAM_SOURCE
    3. Auto-compose RTSP tu IP_CAMERA, TK_CAMERA, PASSWORD_CAMERA...
    4. Config source
    5. Default: assets/video.mp4
    """
    if args_source:
        return args_source, "CLI --source"
    env_src = read_secret("CAM_SOURCE")
    if env_src:
        return env_src, "secrets/env CAM_SOURCE"
    ip_cam = os.environ.get("IP_CAMERA")
    if ip_cam:
        tk = read_secret("TK_CAMERA", "")
        pw = read_secret("PASSWORD_CAMERA", "")
        ext = os.environ.get("EXTEND_RSTP_LINK", "/MediaInput/h264/stream_1")
        if tk and pw:
            return f"rtsp://{tk}:{pw}@{ip_cam}{ext}", "env IP_CAMERA (RTSP auto-composed)"
        elif tk:
            return f"rtsp://{tk}@{ip_cam}{ext}", "env IP_CAMERA (RTSP auto-composed)"
        return f"rtsp://{ip_cam}{ext}", "env IP_CAMERA (RTSP auto-composed)"
    if cfg_source:
        return cfg_source, "file camera source:"
    return "assets/video.mp4", "mac dinh assets/video.mp4"


def today_str(tzname: str = "Asia/Ho_Chi_Minh") -> str:
    """Ngay YYYY-MM-DD theo timezone camera."""
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        return datetime.now(ZoneInfo(tzname)).strftime("%Y-%m-%d")
    except Exception:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d")


class TrafficPipelineEngine:
    """Class dieu phoi toan bo pipeline phan tich camera giao thong edge."""

    def __init__(
        self,
        config_path: str = "configs/active.yaml",
        source_override: Optional[str] = None,
        no_show: bool = False,
        save_path: str = "",
        max_frames: int = 0,
        imgsz_override: int = 0,
        debug_rules: bool = False,
        fps: Optional[float] = None,
        frame_size: Optional[Tuple[int, int]] = None,
        **kwargs: Any,
    ):
        self.config_path = config_path
        self.source_override = source_override
        self.no_show = no_show
        self.save_path = save_path
        self.max_frames = max_frames
        self.imgsz_override = imgsz_override
        self.debug_rules = debug_rules

        self.stopped = False
        self.is_setup = False

        # Core components
        self.cfg: Dict[str, Any] = {}
        self.camera_id: str = "CAM_01"
        self.tz: str = "Asia/Ho_Chi_Minh"
        self.heartbeat_file: str = ""
        self.cap = None
        self._fps_given = fps is not None
        self.fps_src: float = float(fps) if fps is not None else 30.0
        self.frame_size = frame_size
        self.writer = None

        self.tracker = None
        self.runners = []
        self.plan_entries = []
        self.rule_of = {}
        self.signals = None
        self.vis_renderer = None
        self.evidence_saver = None
        self.obj_store = None
        self.all_lines = []

        # Secondary pedestrian detector & async worker
        self.gathering_entries = []
        self.ped_detector = None
        self.ped_interval: int = 30
        self.last_peds: List[Dict[str, Any]] = []
        self.gathering_status: Dict[str, Any] = {}

        # Tracking state
        self.counts: Dict[str, int] = {"skipped": 0}
        self.prev_tids: Set[int] = set()
        self.frame_idx: int = 0
        self.start_t: float = 0.0
        self.date_str: str = ""
        self.wall_min: int = 0
        self.last_prune: float = 0.0
        self.ev_dir: str = "evidence"
        self.retention_days: int = 7

    def setup(self):
        """Nap va kiem tra toan bo cau hinh, khoi tao model va tai nguyen."""
        if self.is_setup:
            return

        cfg, warns = load_camera_config(self.config_path)
        self.cfg = cfg
        for w in warns:
            logging.warning("[config] Canh bao: %s", w)

        self.camera_id = str(cfg.get("camera_id") or cfg.get("camera_name") or cfg.get("name") or "CAM_01")
        self.tz = cfg.get("timezone", "Asia/Ho_Chi_Minh")
        edge = cfg.get("edge", {})
        self.heartbeat_file = (
            os.environ.get("HEARTBEAT_FILE")
            or edge.get("heartbeat_file")
            or f"/app/data/heartbeat_{self.camera_id}"
        )

        ev = cfg.get("evidence", {})
        self.ev_dir = str(ev.get("dir", "evidence"))
        self.retention_days = ev.get("retention_days", 7)

        mc = cfg.get("model", {})
        polys = cfg.get("polygons", [])
        plan = cfg.get("_plan", [])
        self.runners = build_runners(plan)
        self.plan_entries = [e for e, _ in self.runners]
        self.rule_of = {id(e): r for e, r in self.runners}

        logging.info("Khoi tao %d runner cho %d polygon x rule", len(self.runners), len(polys))

        # Camera input capture
        src, src_from = resolve_camera_source(self.source_override, cfg.get("source"))
        if isinstance(src, str) and src.startswith("/dev/video"):
            try:
                src = int(src[len("/dev/video"):])
            except (ValueError, TypeError):
                pass
        try:
            src = int(src)
        except (ValueError, TypeError):
            pass

        if _is_stream(src):
            logging.info("Khoi tao AsyncStreamReader (chong tre buffer RTSP) cho %s", _mask_source(src))
            self.cap = AsyncStreamReader(src, reconnect_fn=_open_capture, should_stop=lambda: self.stopped)
            if not self.cap.isOpened():
                raise RuntimeError(f"[INPUT SRC] Khong mo duoc stream ({src_from}): {_mask_source(src)}")
        else:
            self.cap = _open_capture(src)
            if self.cap is None:
                raise RuntimeError(
                    f"[INPUT SRC] Khong mo duoc ({src_from}): {_mask_source(src)} "
                    "(video can mount ./assets, RTSP can mang + dung pass)"
                )

        if not self._fps_given and self.cap is not None:
            self.fps_src = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        logging.info("Mo INPUT SRC OK (%s): %s (fps~%.1f)", src_from, _mask_source(src), self.fps_src)

        # Main Tracker & Detector
        effective_imgsz = self.imgsz_override or int(mc.get("imgsz", 640))
        self.tracker = create_tracker(mc, imgsz_override=effective_imgsz)
        logging.info(
            "[CONFIG] Camera ID: %s | Model: %s | Imgsz: %dpx",
            self.camera_id, mc.get("weights", ""), effective_imgsz
        )

        # Secondary Pedestrian Detector (Async Worker)
        self.gathering_entries = [e for e in plan if e.get("rule") == "no_gathering"]
        if self.gathering_entries:
            sec_cfg = cfg.get("secondary_models", {})
            ped_cfg = (cfg.get("no_gathering") or {}).get("model") or sec_cfg.get("pedestrian") or {}
            if not ped_cfg:
                for ge in self.gathering_entries:
                    m = (ge.get("polygon", {}).get("rules", {}).get("no_gathering") or {}).get("model")
                    if m:
                        ped_cfg = m
                        break
            self.ped_detector = create_pedestrian_detector(ped_cfg, async_mode=True)
            self.ped_interval = max(1, int(ped_cfg.get("infer_interval_frames", int(self.fps_src or 30))))
            if self.ped_detector is not None:
                logging.info(
                    "[SECONDARY] Async Pedestrian Detector da kich hoat (worker thread) cho %d polygon: %s",
                    len(self.gathering_entries), ped_cfg.get("weights")
                )

        # Traffic signals & visualizer
        red_cfg = cfg.get("red_light") or cfg.get("red_light_running") or {}
        self.signals = SignalStore(cfg.get("signals", []), red_cfg, wall_min=now_minutes(self.tz))
        self.all_lines = list(iter_all_lines(cfg))
        self.vis_renderer = Visualizer(lines=self.all_lines, polygons=polys, names=self.tracker.names)
        self.evidence_saver = AsyncEvidenceSaver()

        # Object Store (SQLite)
        run_id = uuid.uuid4().hex[:8]
        try:
            if os.environ.get("OBJECT_STORE", "1") == "1":
                self.obj_store = ObjectStore(run_id=run_id)
                self.obj_store.prune()
            else:
                self.obj_store = None
        except Exception:
            logging.exception("object store khoi tao loi (chay tiep khong store)")
            self.obj_store = None
        logging.info("Object store run_id=%s", run_id)

        self.start_t = time.perf_counter()
        self.date_str = today_str(self.tz)
        self.wall_min = now_minutes(self.tz)
        self.last_prune = self.start_t
        touch_heartbeat(self.heartbeat_file)
        self.is_setup = True

    def process_frame(self, frame, frame_idx: int, t_video: Optional[float] = None) -> Dict[str, Any]:
        """Xu ly 1 khung hinh qua toan bo pipeline: tracker -> rules -> evidence -> async ped."""
        t = t_video if t_video is not None else (frame_idx / self.fps_src)
        if frame_idx % int(self.fps_src) == 1:
            self.wall_min = now_minutes(self.tz)
            self.date_str = today_str(self.tz)
            touch_heartbeat(self.heartbeat_file)

        # 1. Tracking update
        try:
            tracks = self.tracker.update(frame, frame_idx)
        except Exception:
            logging.exception("tracker.update loi frame %d (bo qua)", frame_idx)
            return {"tracks": {}, "events": []}

        # 2. Traffic signals update
        self.signals.update(frame, t, self.wall_min)
        ctx = FrameContext(
            frame_idx=frame_idx, t=t, wall_min=self.wall_min,
            frame=frame, signals=self.signals
        )

        # 3. Traffic violation rules evaluation
        events = []
        for st in tracks.values():
            wanted = wanted_entries(st, self.plan_entries)
            if not wanted:
                self.counts["skipped"] += 1
                continue

            e = run_first_event(st, wanted, self.rule_of, ctx=ctx)
            if e:
                events.append(e)
                self.counts[e["type"]] = self.counts.get(e["type"], 0) + 1
                self.evidence_saver.submit(
                    e, frame=frame, all_lines=self.all_lines,
                    names=self.tracker.names,
                    out_dir=self.ev_dir, camera_id=self.camera_id,
                    config_version=str(self.cfg.get("config_version", "cfg_v1")),
                    model_version=Path(str(self.cfg.get("model", {}).get("weights", "model"))).stem,
                    jpeg_quality=int(self.cfg.get("evidence", {}).get("jpeg_quality", 90)),
                    timezone_name=self.tz
                )
                self.last_prune = maybe_prune(
                    self.ev_dir, self.camera_id, self.retention_days,
                    self.last_prune, time.perf_counter()
                )

        # 4. Async Secondary Pedestrian Detector (Gathering Rule)
        if self.ped_detector is not None and self.gathering_entries:
            # Poll ket qua hoan tat tu worker thread truoc (non-blocking)
            ped_res = self.ped_detector.poll_result()
            if ped_res is not None:
                self.last_peds = ped_res["all_peds"]
                for pitem in ped_res["poly_results"]:
                    ge = pitem["ge"]
                    poly_obj = pitem["poly_obj"]
                    peds_in_poly = pitem["peds"]
                    g_rule = self.rule_of.get(id(ge))
                    if g_rule is not None:
                        ev_g = g_rule.update_zone(
                            polygon=poly_obj,
                            persons=peds_in_poly,
                            wall_min=ped_res["wall_min"],
                            frame_idx=ped_res["frame_idx"],
                            t=ped_res["t"],
                            frame=ped_res["frame"]
                        )
                        if ev_g:
                            events.append(ev_g)
                            self.counts[ev_g["type"]] = self.counts.get(ev_g["type"], 0) + 1
                            self.evidence_saver.submit(
                                ev_g, frame=ped_res["frame"], all_lines=self.all_lines,
                                names={0: "pedestrian", -1: "gathering"},
                                out_dir=self.ev_dir, camera_id=self.camera_id,
                                config_version=str(self.cfg.get("config_version", "cfg_v1")),
                                model_version="pedestrian",
                                jpeg_quality=int(self.cfg.get("evidence", {}).get("jpeg_quality", 90)),
                                timezone_name=self.tz
                            )
                            self.last_prune = maybe_prune(
                                self.ev_dir, self.camera_id, self.retention_days,
                                self.last_prune, time.perf_counter()
                            )

            # Submit frame moi cho worker xu ly dinh ky (non-blocking, drop frame neu worker ban)
            if frame_idx % self.ped_interval == 0:
                self.ped_detector.submit(
                    frame=frame,
                    gathering_entries=self.gathering_entries,
                    frame_idx=frame_idx,
                    t=t,
                    wall_min=self.wall_min
                )

            # Cap nhat trang thai zone cho visualizer
            for ge in self.gathering_entries:
                poly_obj = ge.get("polygon") or {}
                pid = poly_obj.get("id")
                g_rule = self.rule_of.get(id(ge))
                if g_rule and hasattr(g_rule, "get_zone_status"):
                    self.gathering_status[pid] = g_rule.get_zone_status(pid, t=t)

        # 5. Object Store tracking lifecycle (Top-2 Dominant Colors)
        if self.obj_store is not None:
            try:
                cur_tids = set()
                for tid, st in tracks.items():
                    cur_tids.add(tid)
                    self.obj_store.observe(
                        tid, st.cls, st.conf, st.bbox, frame,
                        self.camera_id, self.date_str, t
                    )
                for gone in self.prev_tids - cur_tids:
                    self.obj_store.finalize(gone, self.camera_id, self.date_str, t)
                self.prev_tids = cur_tids
                self.obj_store.flush()
            except Exception:
                logging.exception("object store loi frame %d (bo qua)", frame_idx)

        # 6. Debug rules
        if self.debug_rules and frame_idx % 30 == 1:
            for st in tracks.values():
                has_red = bool(getattr(st, "red", None))
                if not (st.reverse or st.line_flags or st.zones or has_red):
                    continue
                for entry in wanted_entries(st, self.plan_entries):
                    rule = self.rule_of[id(entry)]
                    logging.debug(
                        "[dbg f%d] %s", frame_idx,
                        rule.explain(
                            st, t=t, lines=entry["lines"], pairs=entry.get("pairs", []),
                            polygon=entry["polygon"], wall_min=self.wall_min, signals=self.signals
                        )
                    )

        return {
            "tracks": tracks,
            "events": events,
            "t": t,
        }

    def run(self):
        """Vong lap chinh chay capture -> process -> render/save."""
        self.setup()
        prev_t = time.perf_counter()
        fps = 0.0

        try:
            while not self.stopped:
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    if _is_stream(self.source_override or self.cfg.get("source")):
                        time.sleep(0.01)
                        continue
                    break  # Het video

                self.frame_idx += 1
                res = self.process_frame(frame, self.frame_idx)
                tracks = res["tracks"]

                now = time.perf_counter()
                fps = 1.0 / (now - prev_t) if now > prev_t else 0.0
                prev_t = now

                # Visualizer & Output
                need_vis = not self.no_show or bool(self.save_path)
                vis = self.vis_renderer.render(
                    frame, tracks, fps=fps, counts=self.counts,
                    frame_idx=self.frame_idx, t_video=res.get("t", 0.0),
                    signals=self.signals,
                    pedestrians=self.last_peds,
                    gathering_zones=self.gathering_status
                ) if need_vis else frame

                if self.save_path:
                    if self.writer is None:
                        h, w = vis.shape[:2]
                        self.writer = cv2.VideoWriter(
                            self.save_path, cv2.VideoWriter_fourcc(*"mp4v"), self.fps_src, (w, h)
                        )
                    self.writer.write(vis)

                if not self.no_show:
                    try:
                        cv2.imshow("pipeline: edge traffic violation (q=thoat)", vis)
                    except cv2.error:
                        logging.warning("imshow that bai (headless?) -> tat show")
                        self.no_show = True
                    else:
                        if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                            break

                if self.max_frames and self.frame_idx >= self.max_frames:
                    break
        finally:
            self.teardown()

    def stop(self):
        """Danh dau dung pipeline tu tin hieu ngoai."""
        self.stopped = True

    def teardown(self):
        """Don dep sach se toan bo tai nguyen."""
        logging.info("Dang thuc hien graceful teardown pipeline...")
        if self.ped_detector is not None and hasattr(self.ped_detector, "stop"):
            try:
                self.ped_detector.stop()
            except Exception:
                pass

        if self.evidence_saver is not None:
            self.evidence_saver.stop(timeout=5.0)

        if self.obj_store is not None:
            try:
                t = self.frame_idx / self.fps_src if self.fps_src else 0.0
                for gone in self.prev_tids:
                    self.obj_store.finalize(gone, self.camera_id, self.date_str, t)
                self.obj_store.flush(force=True)
                self.obj_store.close()
            except Exception:
                pass

        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass

        if self.writer is not None:
            try:
                self.writer.release()
            except Exception:
                pass

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        total = time.perf_counter() - self.start_t if self.start_t > 0 else 0.0
        avg_fps = self.frame_idx / total if total > 0 else 0.0
        logging.info(
            "Frames: %d | Time: %.1fs | Avg FPS: %.1f | Events: %s%s",
            self.frame_idx, total, avg_fps, self.counts,
            " (STOP)" if self.stopped else ""
        )

"""Pipeline: capture -> YOLO+OC-SORT -> rules -> evidence (edge headless).
Chay host: python pipeline.py --source assets/video.mp4
Chay docker: CAM_SOURCE="rtsp://user:pass@ip/stream" python pipeline.py --config /app/config.yaml --no-show
  (thu tu source: CLI --source > env CAM_SOURCE > env IP_CAMERA (RTSP) > file camera source: > assets/video.mp4)
Ve truoc tren host: python tools/draw_lines.py snap_cam01.jpg --config configs/cam_01.yaml
"""
import argparse
import logging
import os
import signal
import sys
import time
from pathlib import Path

import cv2
import yaml

from src.camera.capture import (AsyncStreamReader, _is_stream, _mask_source,
                                 _open_capture)
from src.config.loader import ConfigError, load_camera_config
from src.utils.geometry import now_minutes
from src.inference.detector import create_tracker
from src.config.zones import iter_all_lines
from src.pipeline.runner import (FrameContext, build_runners, run_first_event,
                                wanted_entries)
from src.inference.signals import SignalStore
from src.storage.sinks import AsyncEvidenceSaver, maybe_prune
from src.monitoring.visualizer import Visualizer

STOP = {"flag": False}  # SIGINT/SIGTERM -> dung loop, cleanup sach se


def _read_secret(name, default=""):
    """Doc secret: uu tien file {NAME}_FILE (vd /run/secrets/*), fallback env {NAME}.
    Tra ve default neu ca hai deu trong. Dung cho thong tin nhay cam (RTSP pass)."""
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


def _resolve_camera_source(args_source, cfg_source):
    """Uu tien nguon dau vao theo thu tu:
    1. CLI --source (khi test thu cong voi video hoac RTSP truc tiep)
    2. Secret / Env CAM_SOURCE
    3. Auto-compose RTSP tu cac bien IP_CAMERA, TK_CAMERA, PASSWORD_CAMERA, EXTEND_RSTP_LINK
    4. File config YAML (key source:)
    5. Fallback mac dinh: assets/video.mp4
    """
    if args_source:
        return args_source, "CLI --source"
    env_src = _read_secret("CAM_SOURCE")
    if env_src:
        return env_src, "secrets/env CAM_SOURCE"
    ip_cam = os.environ.get("IP_CAMERA")
    if ip_cam:
        tk = _read_secret("TK_CAMERA", "")
        pw = _read_secret("PASSWORD_CAMERA", "")
        ext = os.environ.get("EXTEND_RSTP_LINK", "/MediaInput/h264/stream_1")
        if tk and pw:
            return f"rtsp://{tk}:{pw}@{ip_cam}{ext}", "env IP_CAMERA (RTSP auto-composed)"
        elif tk:
            return f"rtsp://{tk}@{ip_cam}{ext}", "env IP_CAMERA (RTSP auto-composed)"
        return f"rtsp://{ip_cam}{ext}", "env IP_CAMERA (RTSP auto-composed)"
    if cfg_source:
        return cfg_source, "file camera source:"
    return "assets/video.mp4", "mac dinh assets/video.mp4"


def _on_stop(signum, frame):
    STOP["flag"] = True


def _touch_heartbeat(path):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).touch()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=None,
                    help="uu tien nhat; mac dinh lay tu file camera (source:), "
                         "cuoi cung la assets/video.mp4")
    ap.add_argument("--config", default="camera_config.yaml")
    ap.add_argument("--no-show", action="store_true")
    ap.add_argument("--save", default="")
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--imgsz", type=int, default=0,
                    help="0 = lay tu config; 480 = nhanh ~2x, 640 = chuan ngay")
    ap.add_argument("--run-config", default="",
                    help="file yaml test (vd configs/test_config.yaml); "
                         "CLI truyen tay van uu tien hon file")
    ap.add_argument("--debug-rules", action="store_true",
                    help="in explain() cua tracks dang active moi 30 frames "
                         "(debug xe vao khong bao)")
    # nap run-config lam default truoc, CLI de sau se ghi de
    if "--run-config" in sys.argv:
        with open(sys.argv[sys.argv.index("--run-config") + 1],
                  encoding="utf-8") as f:
            run = yaml.safe_load(f) or {}
        ap.set_defaults(**{k: v for k, v in run.items() if k in (
            "source", "config", "save", "max_frames", "no_show", "imgsz")})
    args = ap.parse_args()

    # Log format chuan RFC3339-ish UTC/local, de parse qua log collector
    logging.basicConfig(
        level=logging.DEBUG if args.debug_rules else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S")

    signal.signal(signal.SIGINT, _on_stop)
    signal.signal(signal.SIGTERM, _on_stop)

    try:
        cfg, warns = load_camera_config(args.config)
    except ConfigError as ex:
        raise SystemExit(f"Loi config {args.config}: {ex}")
    except FileNotFoundError:
        raise SystemExit(f"Khong thay file config {args.config}")
    for w in warns:
        logging.warning("[config] Canh bao: %s", w)

    camera_id = str(cfg.get("camera_id") or cfg.get("camera_name") or cfg.get("name") or "CAM_01")
    edge = cfg.get("edge", {})
    heartbeat = os.environ.get("HEARTBEAT_FILE") or edge.get("heartbeat_file") or f"/app/data/heartbeat_{camera_id}"

    mc = cfg.get("model", {})
    ev = cfg.get("evidence", {})
    polys = cfg.get("polygons", [])
    tz = str(cfg.get("timezone", "Asia/Ho_Chi_Minh"))

    # Uu tien imgsz: CLI --imgsz > root imgsz trong config > model.imgsz trong config > mac dinh 640
    effective_imgsz = int(args.imgsz or cfg.get("imgsz") or mc.get("imgsz") or 640)
    mc["imgsz"] = effective_imgsz

    plan = cfg["_plan"]
    runners = build_runners(plan)
    logging.info("Khoi tao %d runner cho %d polygon x rule",
                 len(runners), len(polys))

    src, src_from = _resolve_camera_source(args.source, cfg.get("source"))

    tracker = create_tracker(mc, imgsz_override=effective_imgsz)
    logging.info("[CONFIG] Camera ID: %s | Model: %s | Imgsz: %dpx | Source: %s (%s)",
                 camera_id, mc.get("weights", ""), effective_imgsz, _mask_source(src), src_from)

    red_cfg = cfg.get("red_light", {})
    signals = SignalStore(cfg.get("signals", []), red_cfg,
                          wall_min=now_minutes(tz))
    all_lines = list(iter_all_lines(cfg))
    vis_renderer = Visualizer(lines=all_lines, polygons=polys, names=tracker.names)
    evidence_saver = AsyncEvidenceSaver()

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
        logging.info("Khoi tao AsyncStreamReader (chong tre buffer RTSP) cho %s",
                     _mask_source(src))
        cap = AsyncStreamReader(src, reconnect_fn=_open_capture,
                                should_stop=lambda: STOP["flag"])
        if not cap.isOpened():
            raise SystemExit(
                f"[INPUT SRC] Khong mo duoc stream ({src_from}): {_mask_source(src)}")
    else:
        cap = _open_capture(src)
        if cap is None:
            raise SystemExit(
                f"[INPUT SRC] Khong mo duoc ({src_from}): {_mask_source(src)} "
                f"(video can mount ./assets, RTSP can mang + dung pass)")

    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    logging.info("Mo INPUT SRC OK (%s): %s (fps~%.1f)",
                 src_from, _mask_source(src), fps_src)
    writer = None

    counts = {"skipped": 0}
    frame_idx, prev_t, start_t = 0, time.perf_counter(), time.perf_counter()
    fps = 0.0
    wall_min = now_minutes(tz)
    plan_entries = [e for e, _ in runners]
    rule_of = {id(e): r for e, r in runners}
    _touch_heartbeat(heartbeat)
    last_prune = start_t
    ev_dir = str(ev.get("dir", "evidence"))
    retention_days = ev.get("retention_days", 7)

    try:
        while not STOP["flag"]:
            ok, frame = cap.read()
            if not ok or frame is None:
                if _is_stream(src):
                    time.sleep(0.01)
                    continue
                break  # file video het -> ket thuc binh thuong

            frame_idx += 1
            t = frame_idx / fps_src
            if frame_idx % int(fps_src) == 1:
                wall_min = now_minutes(tz)
                _touch_heartbeat(heartbeat)

            try:
                tracks = tracker.update(frame, frame_idx)
            except Exception:
                logging.exception("tracker.update loi frame %d (bo qua, khong sap)",
                                  frame_idx)
                continue

            signals.update(frame, t, wall_min)
            ctx = FrameContext(frame_idx=frame_idx, t=t, wall_min=wall_min,
                               frame=frame, signals=signals)

            for st in tracks.values():
                wanted = wanted_entries(st, plan_entries)
                if not wanted:
                    counts["skipped"] += 1
                    continue

                e = run_first_event(st, wanted, rule_of, ctx=ctx)
                if e:
                    counts[e["type"]] = counts.get(e["type"], 0) + 1
                    evidence_saver.submit(
                        e, frame=frame, all_lines=all_lines,
                        names=tracker.names,
                        out_dir=ev_dir, camera_id=camera_id,
                        config_version=str(cfg.get("config_version", "cfg_v1")),
                        model_version=Path(str(mc["weights"])).stem,
                        jpeg_quality=int(ev.get("jpeg_quality", 90)),
                        timezone_name=tz)

                    last_prune = maybe_prune(ev_dir, camera_id,
                                             retention_days, last_prune,
                                             time.perf_counter())

            if args.debug_rules and frame_idx % 30 == 1:
                for st in tracks.values():
                    has_red = bool(getattr(st, "red", None))
                    if not (st.reverse or st.line_flags or st.zones or has_red):
                        continue
                    for entry in wanted_entries(st, plan_entries):
                        rule = rule_of[id(entry)]
                        logging.debug("[dbg f%d] %s", frame_idx, rule.explain(
                            st, t=t, lines=entry["lines"], pairs=entry.get("pairs", []),
                            polygon=entry["polygon"], wall_min=wall_min, signals=signals))

            now = time.perf_counter()
            fps = 1.0 / (now - prev_t) if now > prev_t else 0.0
            prev_t = now

            # Chi ve overlay neu hien thi len man hinh hoac luu video
            need_vis = not args.no_show or bool(args.save)
            vis = vis_renderer.render(frame, tracks, fps=fps, counts=counts,
                                      frame_idx=frame_idx, t_video=t,
                                      signals=signals) if need_vis else frame

            if args.save:
                if writer is None:
                    h, w = vis.shape[:2]
                    writer = cv2.VideoWriter(
                        args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps_src, (w, h))
                writer.write(vis)

            if not args.no_show:
                try:
                    cv2.imshow("pipeline: edge traffic violation (q=thoat)", vis)
                except cv2.error:
                    logging.warning("imshow that bai (headless?) -> tat show")
                    args.no_show = True
                else:
                    if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                        break

            if args.max_frames and frame_idx >= args.max_frames:
                break

    finally:
        # Graceful shutdown: luu not toan bo evidence con ton dong truoc khi thoat
        evidence_saver.stop(timeout=5.0)
        try:
            cap.release()
        except Exception:
            pass
        try:
            if writer:
                writer.release()
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

    total = time.perf_counter() - start_t
    logging.info("Frames: %d | Time: %.1fs | Avg FPS: %.1f | Events: %s%s",
                 frame_idx, total, frame_idx / total if total > 0 else 0,
                 counts, " (STOP)" if STOP["flag"] else "")


if __name__ == "__main__":
    main()

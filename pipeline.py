"""Pipeline: capture -> YOLO+OC-SORT -> rules -> evidence (edge headless).
Chay host: python pipeline.py --source assets/video.mp4
Chay docker: CAM_SOURCE="rtsp://user:pass@ip/stream" python pipeline.py --config /app/config.yaml --no-show
  (thu tu source: CLI --source > env CAM_SOURCE > file camera source: > assets/video.mp4)
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

from src.config_loader import (ConfigError, entries_for,
                                 load_camera_config)
from src.evidence import prune_old_dates, save_event, save_triptych
from src.geometry import allowed_vec, now_minutes, point_in_polygon
from src.line_config import iter_all_lines
from src.rules import create as create_rule
from src.signals import SignalStore
from src.tracking import Tracker

ARROW_LEN = 60
COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255),
    (255, 0, 255), (255, 255, 0), (0, 128, 255), (128, 0, 255),
]

STOP = {"flag": False}  # SIGINT/SIGTERM -> dung loop, cleanup sach se


def _on_stop(signum, frame):
    STOP["flag"] = True


def _mask_source(src):
    """An user:pass trong RTSP khi log (khong lo credential)."""
    if isinstance(src, str) and "://" in src and "@" in src:
        try:
            pre, rest = src.split("://", 1)
            creds, tail = rest.split("@", 1)
            user = creds.split(":", 1)[0]
            return f"{pre}://{user}:***@{tail}"
        except ValueError:
            return "<rtsp>"
    return src


def _is_stream(src):
    return isinstance(src, str) and src.startswith(("rtsp://", "rtsps://",
                                                    "http://", "https://"))


def _open_capture(src, attempts=5, delay_s=3.0):
    """Mo VideoCapture co retry (cho RTSP rot mang). Tra ve cap hoac None."""
    for i in range(max(1, attempts)):
        cap = cv2.VideoCapture(src)
        if cap.isOpened():
            return cap
        cap.release()
        if i + 1 < attempts:
            logging.warning("Khong mo duoc source %s (lan %d/%d), thu lai sau %.0fs",
                            _mask_source(src), i + 1, attempts, delay_s)
            time.sleep(delay_s)
    return None


def _touch_heartbeat(path):
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).touch()
    except Exception:
        pass


def _cls_name(names, cls):
    if names is None:
        return f"class {cls}"
    if isinstance(names, dict):
        return names.get(cls, f"class {cls}")
    return names[cls] if cls < len(names) else f"class {cls}"


def draw_overlay(img, tracks, lines, polygons, fps, counts, frame_idx,
                 names=None, t_video=0.0, signals=None):
    for sid, s in (signals.snapshot() if signals else {}).items():
        x1, y1, x2, y2 = s["roi"]
        col = {"RED": (0, 0, 255), "YELLOW": (0, 255, 255),
               "GREEN": (0, 255, 0)}.get(s["state"], (128, 128, 128))
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 2)
        cv2.putText(img, f"{sid}:{s['state']}", (x1, max(0, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    for p in polygons:
        pts = [(int(x), int(y)) for x, y in (p.get("polygon") or [])]
        if len(pts) >= 3:
            col = (0, 0, 255) if p.get("kind") == "banned" else (0, 255, 0)
            for a, b in zip(pts, pts[1:] + pts[:1]):
                cv2.line(img, a, b, col, 2)
            cv2.putText(img, p["id"], pts[0],
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    for ln in lines:
        p1 = tuple(int(v) for v in ln["p1"])
        p2 = tuple(int(v) for v in ln["p2"])
        col = (255, 0, 0) if ln.get("role") == "divider" else (0, 255, 0)
        cv2.line(img, p1, p2, col, 2)
        if ln.get("role") != "divider":
            mx, my = (p1[0] + p2[0]) // 2, (p1[1] + p2[1]) // 2
            ax, ay = allowed_vec(ln["p1"], ln["p2"], ln.get("allowed_sign", 1))
            cv2.arrowedLine(img, (mx, my),
                            (int(mx + ax * ARROW_LEN), int(my + ay * ARROW_LEN)),
                            (0, 255, 255), 2)
        cv2.putText(img, ln["id"], (p1[0], p1[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
    for tid, st in tracks.items():
        if st.bbox is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in st.bbox]
        cls = int(st.cls)
        color = COLORS[cls % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        pts = [(int(x), int(y)) for x, y in st.pts]
        for a, b in zip(pts[:-1], pts[1:]):
            cv2.line(img, a, b, (255, 0, 255), 2)
        bc = pts[-1]
        cv2.circle(img, bc, 4, (0, 255, 255), -1)
        label = f"id{tid} {_cls_name(names, cls)} {st.conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(img, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(img, label, (x1 + 2, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        for zid, zs in st.zones.items():
            if not zs.get("inside"):
                continue
            dw = next((float(p.get("dwell_s", 0)) for p in polygons
                       if p.get("id") == zid), 0.0)
            ztxt = f"{zid} {t_video - zs['enter_t']:.1f}/{dw:.0f}s"
            cv2.putText(img, ztxt, (bc[0] - 40, bc[1] + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        spd = getattr(st, "speed", None)
        if spd is not None and spd.get("hist"):
            lim = float(spd.get("limit", 50.0))
            stxt = f"{spd.get('smooth', 0.0):.0f} km/h"
            scol = (0, 0, 255) if spd.get("smooth", 0.0) > lim \
                else (255, 255, 255)
            cv2.putText(img, stxt, (x1, y2 + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, scol, 2)
    y = 30
    ev_txt = "  ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    for txt, col in [(f"FPS: {fps:.1f}", (0, 255, 0)),
                     (f"frame {frame_idx} tracks {len(tracks)}", (0, 255, 0)),
                     (ev_txt,
                      (0, 0, 255) if sum(v for k, v in counts.items()
                                         if k != "skipped") else (0, 255, 0))]:
        cv2.putText(img, txt, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        y += 28
    return img


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
                    help="file yaml test (vd test_config.yaml); "
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

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(message)s")
    # headless (docker/khong DISPLAY): ep --no-show de tranh cv2.imshow crash
    if not args.no_show and not os.environ.get("DISPLAY") \
            and sys.platform.startswith("linux"):
        logging.warning("Khong thay DISPLAY -> tu dong bat --no-show (headless)")
        args.no_show = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_stop)
        except (OSError, ValueError):
            pass
    heartbeat = os.environ.get("HEARTBEAT_FILE", "/tmp/heartbeat")

    try:
        cfg, warns = load_camera_config(args.config)
    except ConfigError as e:
        raise SystemExit(f"[INPUT CONFIG] LOI file {args.config}: {e}")
    except FileNotFoundError:
        raise SystemExit(f"[INPUT CONFIG] Khong thay file {args.config} "
                         f"(mount ./configs vao container chua?)")
    for w in warns:
        logging.warning("[config] canh bao: %s", w)
    if not cfg.get("polygons") and not list(iter_all_lines(cfg)):
        raise SystemExit(f"[INPUT CONFIG] File {args.config} chua co polygon/line "
                         f"nao (ve xong tu draw tool chua? python tools/draw_lines.py "
                         f"snap.jpg --config {args.config})")
    mc = cfg["model"]
    tracker = Tracker(weights=mc["weights"], conf=mc.get("conf", 0.4),
                      imgsz=args.imgsz or mc.get("imgsz", 640),
                      classes=mc.get("classes"),
                      tracker_cfg=mc.get("tracker", "ocsort.yaml"),
                      device=mc.get("device"))
    # 1 instance rule cho moi (polygon x rule duoc bat). Ten rule anh xa
    # sang class qua registry (them loi moi khong can sua pipeline).
    runners = []
    for e in cfg["_plan"]:
        runners.append((e, create_rule(e["rule"], e["params"])))
    logging.info("[config] %s: %d rule dang bat",
                 cfg.get('camera_id'), len(runners))
    for e, _ in runners:
        p = e["polygon"]
        logging.info("  - %s @ %s (params: %s)", e['rule'],
                     p['id'] if p else 'GLOBAL', e['params'])
    polys = cfg.get("polygons", [])
    tz = cfg.get("timezone", "Asia/Ho_Chi_Minh")
    all_lines = list(iter_all_lines(cfg))
    ev = cfg.get("evidence", {})
    red_cfg = cfg.get("red_light", {})
    signals = SignalStore(cfg.get("signals", []), red_cfg,
                          wall_min=now_minutes(tz))
    if cfg.get("signals"):
        logging.info("[signals] %d den: %s",
                     len(cfg['signals']), [s['id'] for s in cfg['signals']])

    src = (args.source or os.environ.get("CAM_SOURCE")
           or cfg.get("source") or "assets/video.mp4")
    src_from = ("CLI --source" if args.source
                else ("env CAM_SOURCE" if os.environ.get("CAM_SOURCE")
                      else ("file camera source:" if cfg.get("source")
                            else "mac dinh assets/video.mp4")))
    try:
        src = int(src)
    except (ValueError, TypeError):
        pass
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
    while not STOP["flag"]:
        ok, frame = cap.read()
        if not ok or frame is None:
            if _is_stream(src):  # RTSP/HTTP rot -> reconnect thay vi thoat
                logging.warning("Mat frame tu %s, reconnect...",
                                _mask_source(src))
                cap.release()
                cap = _open_capture(src)
                if cap is None:
                    logging.error("Reconnect that bai, dung pipeline")
                    break
                fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
                continue
            break  # file video het -> ket thuc binh thuong
        frame_idx += 1
        t = frame_idx / fps_src
        if frame_idx % int(fps_src) == 1:  # cap nhat gio wall moi giay
            wall_min = now_minutes(tz)
            _touch_heartbeat(heartbeat)
        try:
            tracks = tracker.update(frame, frame_idx)
        except Exception:
            logging.exception("tracker.update loi frame %d (bo qua, khong sap)",
                              frame_idx)
            continue
        signals.update(frame, t, wall_min)
        for st in tracks.values():
            bc = st.pts[-1]
            wanted = entries_for(bc, plan_entries, point_in_polygon, track=st)
            if not wanted:
                counts["skipped"] += 1
                continue  # ngoai moi polygon: hien overlay, khong chay rule
            e = None
            for entry in wanted:
                rule = rule_of[id(entry)]
                e = rule.run(entry, st, frame_idx, t, wall_min,
                             frame=frame, signals=signals)
                if e:
                    break
            if e:
                counts[e["type"]] = counts.get(e["type"], 0) + 1
                common = dict(
                    out_dir=ev.get("dir", "evidence"),
                    camera_id=cfg.get("camera_id", "CAM"),
                    config_version=cfg.get("config_version", "cfg_v1"),
                    model_version=Path(mc["weights"]).stem,
                    jpeg_quality=ev.get("jpeg_quality", 90),
                    timezone_name=cfg.get("timezone", "Asia/Ho_Chi_Minh"))
                try:
                    tri = e["extra"].pop("triptych", None)
                    if tri is not None:
                        jp, js = save_triptych(
                            tri, frame, e, all_lines, tracker.names, **common)
                    else:
                        ev_frame = e["extra"].pop("evidence_frame", None)
                        target_frame = ev_frame if ev_frame is not None else frame
                        jp, js = save_event(target_frame, e, all_lines,
                                            tracker.names, **common)
                except Exception:
                    logging.exception("Ghi evidence loi (bo qua event, khong sap)")
                    continue
                # xoay vong theo ngay (throttle 5 phut, khong block inference)
                try:
                    if time.perf_counter() - last_prune > 300:
                        prune_old_dates(
                            Path(ev.get("dir", "evidence"))
                            / cfg.get("camera_id", "CAM"),
                            ev.get("retention_days", 7))
                        last_prune = time.perf_counter()
                except Exception:
                    pass
                logging.info("[%s] track=%s line=%s frame=%d -> %s",
                             e["type"], e["track_id"], e["line_id"], frame_idx, jp)
        if args.debug_rules and frame_idx % 30 == 1:
            for st in tracks.values():
                has_red = bool(getattr(st, "red", None))
                if not (st.reverse or st.line_flags or st.zones or has_red):
                    continue  # chi log track dang co trang thai
                bc = st.pts[-1]
                for entry in entries_for(bc, plan_entries, point_in_polygon, track=st):
                    rule = rule_of[id(entry)]
                    logging.debug("[dbg f%d] %s", frame_idx, rule.explain(
                        st, t=t, lines=entry["lines"], pairs=entry.get("pairs", []),
                        polygon=entry["polygon"], wall_min=wall_min, signals=signals))
        now = time.perf_counter()
        fps = 1.0 / (now - prev_t) if now > prev_t else 0.0
        prev_t = now

        # no-show + khong save thi khoi ve overlay (tiet kiem ~1ms/frame)
        need_vis = not args.no_show or bool(args.save)
        vis = draw_overlay(frame, tracks, all_lines, polys,
                           fps, counts, frame_idx, tracker.names, t,
                           signals=signals) \
            if need_vis else frame
        if args.save:
            if writer is None:
                h, w = vis.shape[:2]
                writer = cv2.VideoWriter(
                    args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps_src, (w, h))
            writer.write(vis)
        if not args.no_show:
            try:
                cv2.imshow("pipeline: wrong_way + no_uturn (q=thoat)", vis)
            except cv2.error:
                logging.warning("imshow that bai (headless?) -> tat show")
                args.no_show = True
            else:
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
        if args.max_frames and frame_idx >= args.max_frames:
            break

    total = time.perf_counter() - start_t
    logging.info("Frames: %d | Time: %.1fs | Avg FPS: %.1f | Events: %s%s",
                 frame_idx, total, frame_idx / total if total > 0 else 0,
                 counts, " (STOP)" if STOP["flag"] else "")
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


if __name__ == "__main__":
    main()

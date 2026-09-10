"""Pipeline: capture -> YOLO+OC-SORT -> wrong_way/no_uturn -> evidence.
Chay: python pipeline.py --source assets/video.mp4
      python pipeline.py --source 0
      python pipeline.py --source assets/video.mp4 --no-show --max-frames 600
      python pipeline.py --source assets/video.mp4 --no-show --imgsz 480  # nhanh ~2x
      python pipeline.py --run-config test_config.yaml  # doc cau hinh test tu file
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import yaml

from src.config_loader import (ConfigError, entries_for,
                                 load_camera_config)
from src.evidence import save_event
from src.geometry import allowed_vec, now_minutes, point_in_polygon
from src.line_config import iter_all_lines
from src.rules import create as create_rule
from src.tracking import Tracker

ARROW_LEN = 60
COLORS = [
    (0, 255, 0), (255, 0, 0), (0, 0, 255), (0, 255, 255),
    (255, 0, 255), (255, 255, 0), (0, 128, 255), (128, 0, 255),
]


def _cls_name(names, cls):
    if names is None:
        return f"class {cls}"
    if isinstance(names, dict):
        return names.get(cls, f"class {cls}")
    return names[cls] if cls < len(names) else f"class {cls}"


def draw_overlay(img, tracks, lines, polygons, fps, counts, frame_idx,
                 names=None, t_video=0.0):
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
        run = yaml.safe_load(
            open(sys.argv[sys.argv.index("--run-config") + 1])) or {}
        ap.set_defaults(**{k: v for k, v in run.items() if k in (
            "source", "config", "save", "max_frames", "no_show", "imgsz")})
    args = ap.parse_args()

    try:
        cfg, warns = load_camera_config(args.config)
    except ConfigError as e:
        raise SystemExit(f"[config] LOI: {e}")
    for w in warns:
        print(f"[config] canh bao: {w}")
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
    print(f"[config] {cfg.get('camera_id')}: {len(runners)} rule dang bat")
    for e, _ in runners:
        p = e["polygon"]
        print(f"  - {e['rule']} @ {p['id'] if p else 'GLOBAL'} "
              f"(params: {e['params']})")
    polys = cfg.get("polygons", [])
    tz = cfg.get("timezone", "Asia/Ho_Chi_Minh")
    all_lines = list(iter_all_lines(cfg))
    ev = cfg.get("evidence", {})
    ev_dir = str(Path(ev.get("dir", "evidence")) / cfg.get("camera_id", "CAM"))

    src = args.source or cfg.get("source") or "assets/video.mp4"
    try:
        src = int(src)
    except ValueError:
        pass
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"Khong mo duoc source (CLI/run-config/file camera): {src}")
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    writer = None

    counts = {"skipped": 0}
    frame_idx, prev_t, start_t = 0, time.perf_counter(), time.perf_counter()
    fps = 0.0
    wall_min = now_minutes(tz)
    plan_entries = [e for e, _ in runners]
    rule_of = {id(e): r for e, r in runners}
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        frame_idx += 1
        t = frame_idx / fps_src
        if frame_idx % int(fps_src) == 1:  # cap nhat gio wall moi giay
            wall_min = now_minutes(tz)
        tracks = tracker.update(frame, frame_idx)
        for st in tracks.values():
            bc = st.pts[-1]
            wanted = entries_for(bc, plan_entries, point_in_polygon)
            if not wanted:
                counts["skipped"] += 1
                continue  # ngoai moi polygon: hien overlay, khong chay rule
            e = None
            for entry in wanted:
                rule = rule_of[id(entry)]
                e = rule.run(entry, st, frame_idx, t, wall_min)
                if e:
                    break
            if e:
                counts[e["type"]] = counts.get(e["type"], 0) + 1
                jp, js = save_event(
                    frame, e, all_lines, tracker.names,
                    out_dir=str(Path(ev.get("dir", "evidence"))
                                / cfg.get("camera_id", "CAM")),
                    camera_id=cfg.get("camera_id", "CAM"),
                    config_version=cfg.get("config_version", "cfg_v1"),
                    model_version=Path(mc["weights"]).stem,
                    jpeg_quality=ev.get("jpeg_quality", 90))
                print(f"[{e['type']}] track={e['track_id']} "
                      f"line={e['line_id']} frame={frame_idx} -> {jp}")
        if args.debug_rules and frame_idx % 30 == 1:
            for st in tracks.values():
                if not (st.reverse or st.line_flags or st.zones):
                    continue  # chi log track dang co trang thai
                bc = st.pts[-1]
                for entry in entries_for(bc, plan_entries, point_in_polygon):
                    rule = rule_of[id(entry)]
                    print(f"[dbg f{frame_idx}] " + rule.explain(
                        st, t=t, lines=entry["lines"], pairs=entry["pairs"],
                        polygon=entry["polygon"], wall_min=wall_min))
        now = time.perf_counter()
        fps = 1.0 / (now - prev_t) if now > prev_t else 0.0
        prev_t = now

        # no-show + khong save thi khoi ve overlay (tiet kiem ~1ms/frame)
        need_vis = not args.no_show or bool(args.save)
        vis = draw_overlay(frame, tracks, all_lines, polys,
                           fps, counts, frame_idx, tracker.names, t) \
            if need_vis else frame
        if args.save:
            if writer is None:
                h, w = vis.shape[:2]
                writer = cv2.VideoWriter(
                    args.save, cv2.VideoWriter_fourcc(*"mp4v"), fps_src, (w, h))
            writer.write(vis)
        if not args.no_show:
            cv2.imshow("pipeline: wrong_way + no_uturn (q=thoat)", vis)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
        if args.max_frames and frame_idx >= args.max_frames:
            break

    total = time.perf_counter() - start_t
    print(f"Frames: {frame_idx} | Time: {total:.1f}s | "
          f"Avg FPS: {frame_idx/total:.1f} | Events: {counts}")
    cap.release()
    if writer:
        writer.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

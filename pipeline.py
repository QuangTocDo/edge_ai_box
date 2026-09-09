"""Pipeline: capture -> YOLO+OC-SORT -> wrong_way/no_uturn -> evidence.
Chay: python pipeline.py --source video.mp4
      python pipeline.py --source 0
      python pipeline.py --source video.mp4 --no-show --max-frames 600
"""
import argparse
import time
from pathlib import Path

import cv2
import yaml

from src.evidence import save_event
from src.geometry import allowed_vec
from src.rules import NoUTurnRule, WrongWayRule
from src.tracking import Tracker

ARROW_LEN = 60


def draw_overlay(img, tracks, lines, fps, counts, frame_idx):
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
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 0), 2)
        pts = [(int(x), int(y)) for x, y in st.pts]
        for a, b in zip(pts[:-1], pts[1:]):
            cv2.line(img, a, b, (255, 0, 255), 2)
        bc = pts[-1]
        cv2.circle(img, bc, 4, (0, 255, 255), -1)
        cv2.putText(img, f"id{tid}", (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    y = 30
    for txt, col in [(f"FPS: {fps:.1f}", (0, 255, 0)),
                     (f"frame {frame_idx} tracks {len(tracks)}", (0, 255, 0)),
                     (f"wrong_way {counts['wrong_way']}  no_uturn {counts['no_uturn']}",
                      (0, 0, 255) if sum(counts.values()) else (0, 255, 0))]:
        cv2.putText(img, txt, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        y += 28
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="assets/video.mp4")
    ap.add_argument("--config", default="camera_config.yaml")
    ap.add_argument("--no-show", action="store_true")
    ap.add_argument("--save", default="")
    ap.add_argument("--max-frames", type=int, default=0)
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    mc = cfg["model"]
    tracker = Tracker(weights=mc["weights"], conf=mc.get("conf", 0.4),
                      imgsz=mc.get("imgsz", 640), classes=mc.get("classes"),
                      tracker_cfg=mc.get("tracker", "ocsort.yaml"),
                      device=mc.get("device"))
    wc, uc = cfg["wrong_way"], cfg["no_uturn"]
    ww = WrongWayRule(min_hits=wc.get("min_hits", 3),
                      min_reverse_frames=wc.get("min_reverse_frames", 5),
                      min_reverse_px=wc.get("min_reverse_px", 60.0),
                      cooldown_s=wc.get("cooldown_s", 10.0))
    ut = NoUTurnRule(time_window_s=tuple(uc.get("time_window_s", [2, 12])),
                     require_velocity_inversion=uc.get(
                         "require_velocity_inversion", True),
                     require_medial=uc.get("require_medial", True),
                     min_hits=uc.get("min_hits", 3),
                     cooldown_s=uc.get("cooldown_s", 10.0))
    lines, pairs = cfg["lines"], cfg.get("uturn_pairs", [])
    ev = cfg.get("evidence", {})

    src = args.source
    try:
        src = int(src)
    except ValueError:
        pass
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        raise SystemExit(f"Khong mo duoc source: {args.source}")
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    writer = None

    counts = {"wrong_way": 0, "no_uturn": 0}
    frame_idx, prev_t, start_t = 0, time.perf_counter(), time.perf_counter()
    fps = 0.0
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        frame_idx += 1
        t = frame_idx / fps_src
        tracks = tracker.update(frame, frame_idx)
        for st in tracks.values():
            for rule in (ww, ut):
                e = rule.update(st, lines, pairs, frame_idx, t) \
                    if isinstance(rule, NoUTurnRule) \
                    else rule.update(st, lines, frame_idx, t)
                if e:
                    counts[e["type"]] += 1
                    jp, js = save_event(
                        frame, e, lines, tracker.names,
                        out_dir=ev.get("dir", "evidence"),
                        camera_id=cfg.get("camera_id", "CAM"),
                        config_version=cfg.get("config_version", "cfg_v1"),
                        model_version=Path(mc["weights"]).stem,
                        jpeg_quality=ev.get("jpeg_quality", 90))
                    print(f"[{e['type']}] track={e['track_id']} "
                          f"line={e['line_id']} frame={frame_idx} -> {jp}")
        now = time.perf_counter()
        fps = 1.0 / (now - prev_t) if now > prev_t else 0.0
        prev_t = now

        vis = draw_overlay(frame, tracks, lines, fps, counts, frame_idx)
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

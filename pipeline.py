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

from src.evidence import save_event
from src.geometry import (allowed_vec, containing_polygons, in_active_hours,
                          now_minutes, parse_window)
from src.line_config import iter_all_lines
from src.rules import NoEntryRule, NoUTurnRule, WrongWayRule
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
        pts = [(int(x), int(y)) for x, y in p.get("polygon", [])]
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
    for txt, col in [(f"FPS: {fps:.1f}", (0, 255, 0)),
                     (f"frame {frame_idx} tracks {len(tracks)}", (0, 255, 0)),
                     (f"wrong_way {counts.get('wrong_way', 0)}  "
                      f"no_uturn {counts.get('no_uturn', 0)}  "
                      f"no_entry {counts.get('no_entry_road', 0)}  "
                      f"skip {counts.get('skipped', 0)}",
                      (0, 0, 255) if sum(v for k, v in counts.items()
                                         if k != "skipped") else (0, 255, 0))]:
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
    ap.add_argument("--imgsz", type=int, default=0,
                    help="0 = lay tu config; 480 = nhanh ~2x, 640 = chuan ngay")
    ap.add_argument("--run-config", default="",
                    help="file yaml test (vd test_config.yaml); "
                         "CLI truyen tay van uu tien hon file")
    # nap run-config lam default truoc, CLI de sau se ghi de
    if "--run-config" in sys.argv:
        run = yaml.safe_load(
            open(sys.argv[sys.argv.index("--run-config") + 1])) or {}
        ap.set_defaults(**{k: v for k, v in run.items() if k in (
            "source", "config", "save", "max_frames", "no_show", "imgsz")})
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    mc = cfg["model"]
    tracker = Tracker(weights=mc["weights"], conf=mc.get("conf", 0.4),
                      imgsz=args.imgsz or mc.get("imgsz", 640),
                      classes=mc.get("classes"),
                      tracker_cfg=mc.get("tracker", "ocsort.yaml"),
                      device=mc.get("device"))
    wc, uc = cfg.get("wrong_way", {}), cfg.get("no_uturn", {})
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
    nc = cfg.get("no_entry_road", {})
    ner = NoEntryRule(dwell_s=nc.get("dwell_s", 2.0),
                      min_hits=nc.get("min_hits", 3),
                      cooldown_s=nc.get("cooldown_s", 10.0))
    # polygons: dinh tuyen track theo Bottom-Center. Khong co polygon nao
    # (= config cu lines phang) thi chay kieu cu cho tat ca tracks.
    polys = cfg.get("polygons", [])
    legacy_lines = cfg.get("lines", [])
    pairs = cfg.get("uturn_pairs", [])
    tz = cfg.get("timezone", "Asia/Ho_Chi_Minh")
    for p in polys:
        wins = []
        for w in p.get("active_hours", []):
            try:
                wins.append(parse_window(w))
            except ValueError as e:
                print(f"[cfg] {p.get('id')}: {e} -> khung gio nay bi bo qua")
        p["_windows"] = wins
    nested_ids = {ln["id"] for p in polys for ln in p.get("lines", [])}
    line_poly = {}
    for p in polys:
        for ln in p.get("lines", []):
            line_poly[ln["id"]] = p
    all_lines = list(legacy_lines) + [ln for p in polys
                                      for ln in p.get("lines", [])]
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

    counts = {"wrong_way": 0, "no_uturn": 0, "no_entry_road": 0,
              "skipped": 0}
    frame_idx, prev_t, start_t = 0, time.perf_counter(), time.perf_counter()
    fps = 0.0
    wall_min = now_minutes(tz)
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
            assigned = containing_polygons(bc, polys) if polys else []
            if polys and not assigned:
                counts["skipped"] += 1
                continue  # ngoai moi polygon: hien overlay, khong chay rule
            ww_lines = list(legacy_lines)
            ut_pairs, ner_polys = [], []
            for p in assigned:
                h = p.get("handler", [])
                if "wrong_way" in h:
                    ww_lines += [ln for ln in p.get("lines", [])
                                 if ln not in ww_lines]
                if "no_uturn" in h:
                    for pr in pairs:
                        f1, f2 = pr["first"], pr["second"]
                        in_here = (line_poly.get(f1, p) is p
                                   and line_poly.get(f2, p) is p)
                        legacy = f1 not in nested_ids and f2 not in nested_ids
                        if (in_here or legacy) and pr not in ut_pairs:
                            ut_pairs.append(pr)
                if p.get("kind") == "banned" and "no_entry_road" in h:
                    ner_polys.append(p)
            e = ww.update(st, ww_lines, frame_idx, t)
            if e is None:
                for pr in ut_pairs:
                    e = ut.update(st, all_lines, [pr], frame_idx, t)
                    if e:
                        break
            if e is None:
                for poly in ner_polys:
                    e = ner.update(st, poly, wall_min, frame_idx, t)
                    if e:
                        break
            if e:
                counts[e["type"]] += 1
                jp, js = save_event(
                    frame, e, all_lines, tracker.names,
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

"""Pipeline: capture -> YOLO+OC-SORT -> rules -> evidence (edge headless).
Chay host: python pipeline.py --source assets/video.mp4
Chay docker: CAM_SOURCE="rtsp://user:pass@ip/stream" python pipeline.py --config /app/config.yaml --no-show
  (thu tu source: CLI --source > env CAM_SOURCE > env IP_CAMERA (RTSP) > file camera source: > assets/video.mp4)
Ve truoc tren host: python tools/draw_lines.py snap_cam01.jpg --config configs/cam_01.yaml
"""
import argparse
import logging
import signal
import sys
import yaml

from src.pipeline.engine import TrafficPipelineEngine

GLOBAL_ENGINE = None


def _on_stop(signum, frame):
    global GLOBAL_ENGINE
    if GLOBAL_ENGINE is not None:
        GLOBAL_ENGINE.stop()


def parse_args():
    ap = argparse.ArgumentParser(description="Edge Traffic Violation Pipeline")
    ap.add_argument("--source", default=None,
                    help="uu tien nhat; mac dinh lay tu file camera (source:), "
                         "cuoi cung la assets/video.mp4")
    ap.add_argument("--config", default="configs/active.yaml")
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

    if "--run-config" in sys.argv:
        cfg_idx = sys.argv.index("--run-config") + 1
        if cfg_idx < len(sys.argv):
            with open(sys.argv[cfg_idx], encoding="utf-8") as f:
                run = yaml.safe_load(f) or {}
            ap.set_defaults(**{k: v for k, v in run.items() if k in (
                "source", "config", "save", "max_frames", "no_show", "imgsz")})

    return ap.parse_args()

def main():
    global GLOBAL_ENGINE
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug_rules else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )

    signal.signal(signal.SIGINT, _on_stop)
    signal.signal(signal.SIGTERM, _on_stop)

    engine = TrafficPipelineEngine(
        config_path=args.config,
        source_override=args.source,
        no_show=args.no_show,
        save_path=args.save,
        max_frames=args.max_frames,
        imgsz_override=args.imgsz,
        debug_rules=args.debug_rules,
    )
    GLOBAL_ENGINE = engine
    engine.run()


if __name__ == "__main__":
    main()

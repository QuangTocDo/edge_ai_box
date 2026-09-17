# src/ — layered core (P2 restructure, per-camera edge)

```
src/
├── camera/      capture.py       # video/RTSP + AsyncStreamReader
├── inference/   detector.py      # create_tracker (YOLO) + signals.py (đèn HSV)
├── tracking/    tracker.py       # TrackState + Tracker (bottom-center)
├── business/    rules/           # 7 rule + registry + base (thêm lỗi = 1 file + 1 dòng)
├── pipeline/    runner.py        # FrameContext + build_runners + run_first_event
├── storage/     evidence.py + sinks.py + uploader.py (S3)
├── monitoring/  visualizer.py + health.py + metrics.py
├── utils/       geometry.py + homography.py + constants.py
├── config/      loader.py + zones.py
└── calibration/ draw_state.py + draw_menu.py
```

Shim tương thích (xóa ở P4 sau khi tools/tests chuyển hẳn sang path mới):
`src/capture.py`, `infer.py`, `signals.py`, `tracking/` (package re-export),
`rules/` (package re-export), `runner.py`, `evidence.py`, `sinks.py`,
`visualizer.py`, `geometry.py`, `homography.py`, `constants.py`,
`config_loader.py`, `line_config.py`, `draw_state.py`, `draw_menu.py`.

Quy ước mới: code mới import từ `src.<layer>` (vd `from src.pipeline import build_runners`),
không import qua shim. Internal import dùng relative 2 chấm từ package con
(vd trong `business/rules/`: `from ...utils.geometry import ...`).

# digital-city-expand — Traffic Violation Edge (per-camera)

Edge device chạy độc lập **1 camera = 1 container/process**.
Luồng: `source (RTSP/video)` → `capture` → `YOLO + OC-SORT` → `rules/` → `evidence/` → `S3`.

## Quickstart (5 phút)

```bash
cp .env.example .env
# Ve truoc (luu vao active.yaml kem source), roi chay pipeline doc tu do
python scripts/calibrate/draw_lines.py snap_cam01.jpg --config configs/active.yaml
python pipeline.py --config configs/active.yaml --no-show
# Chạy thử video local (override source tam)
python pipeline.py --source assets/uturn.mp4 --config configs/active.yaml --no-show
# Docker 1 camera
docker compose up --build -d
docker compose logs -f
# Multi-camera (mỗi camera 1 container)
./deploy.sh build
./deploy.sh start configs/cameras/cam_01.yaml
./deploy.sh start-all
./deploy.sh status
```

## Cấu trúc (sau P0–P1)

```
pipeline.py main.py            # entry (shim tương thích sau khi chẻ src/)
s3_worker.py                   # LEGACY shim -> src/storage/uploader.py
src/                           # core: capture, inference, tracking, rules, runner, evidence, sinks, signals, visualizer
src/business/rules/            # plugin rule: thêm lỗi mới = 1 file + 1 dòng registry
configs/                       # base.yaml + cameras/cam_*.yaml + active.yaml + examples/
models/                        # versioning model (README) + mirror weights/
scripts/                       # calibrate, benchmark, download_models, health_check (chuẩn duy nhất)
tests/ docs/                   # được track từ P0 (trước đây bị gitignore)
weights/                       # runtime .pt/.onnx (file thật, không symlink)
runtime/ (không commit)        # assets/, evidence/, data/heartbeat
```

Per-camera: config riêng `configs/cameras/<cam>.yaml`, heartbeat `data/heartbeat_<CAM>`,
evidence `evidence/<CAM>/date=YYYY-MM-DD/<violation>/`.

## Config

- `configs/base.yaml`: defaults chung (model conf/imgsz, rule enable, evidence 7 ngày).
- `configs/cameras/cam_*.yaml`: override theo camera (polygon, lines, homography).
- `configs/active.yaml`: CANONICAL — draw luu vao day (kem `source:`), pipeline/entrypoint/compose doc tu day.
- `camera_config.yaml` (root): legacy fallback, giu tuong thich.
- Override runtime: `CLI --source > CAM_SOURCE > IP_CAMERA_* > yaml source: > assets/video.mp4`;
  `CLI --imgsz > yaml imgsz > 640`.

## Thêm luật mới

1. Tạo `src/business/rules/my_rule.py` (copy `wrong_way.py`), đặt `TYPE`, `PARAMS`, `run()`, `explain()`.
2. Đăng ký 1 dòng trong `src/business/rules/registry.py`.
3. Thêm YAML `polygons[].rules.my_rule: {enable: true, ...}` + test `tests/test_rule_my_rule.py`.

## Vận hành edge

- Health: `entrypoint.sh` tạo `HEARTBEAT_FILE`, `pipeline.py` touch mỗi giây, `Dockerfile HEALTHCHECK <90s`, `./deploy.sh status` check LIVE/STALE.
- Log: compose `20m x3`; `deploy.sh` đã thêm `--log-opt` đồng nhất (P2).
- Disk: `retention_days: 7` + `maybe_prune 300s`; cron `s3_worker.py --camera <CAM>` xóa local sau PUT OK.
- OTA: sửa YAML + `restart` container cam đó; đổi model: thay `models/detector/` + restart. Không rebuild trừ khi đổi code.

Chi tiết: `docs/HUONG_DAN_CHAY.md`, `docs/PROJECT_PLAN.md`, `models/README.md`.

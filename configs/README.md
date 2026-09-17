# configs/ — cấu hình per-camera

```
configs/
├── base.yaml            # defaults chung (model, rule enable, evidence 7 ngày)
├── active.yaml          # config đang chạy (copy từ camera_config.yaml root legacy)
├── cameras/
│   ├── cam_01.yaml      # bản chuẩn (copy từ configs/cam_01.yaml legacy)
│   └── cam_speed_test.yaml
├── cam_01.yaml          # LEGACY shim (giữ để deploy.sh/entrypoint cũ vẫn chạy)
├── cam_speed_test.yaml  # LEGACY shim
├── test_config.yaml     # LEGACY shim (bản chuẩn ở examples/)
└── examples/
    └── test_config.yaml # mẫu --run-config
```

Quy ước:
- Sửa camera mới: copy `cameras/cam_01.yaml` → `cameras/cam_02.yaml`, đổi `camera_id/polygons/lines`.
- File root `camera_config.yaml` và `configs/cam_*.yaml` là shim legacy, giữ đồng bộ 1 phase rồi bỏ ở P4.
- Thứ tự resolve: `entrypoint.sh` ưu tiên `camera_config.yaml` (legacy) → `configs/active.yaml` → `CAMERA_ID` trong `cameras/` → `configs/`.
- `deploy.sh start cam_01` tìm cả `cameras/` và `configs/`; `start-all` quét cả hai.

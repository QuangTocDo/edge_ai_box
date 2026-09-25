# configs/ — cấu hình per-camera

```
configs/
├── base.yaml            # defaults chung (model, rule enable, evidence 7 ngày)
├── active.yaml          # CANONICAL: draw luu vao day, pipeline doc tu day (local-only, gitignore)
├── cameras/
│   ├── cam_01.yaml      # bản chuẩn per-camera
│   └── cam_speed_test.yaml
└── examples/
    └── test_config.yaml # mẫu --run-config
```

Quy ước:
- Sửa camera mới: copy `cameras/cam_01.yaml` → `cameras/cam_02.yaml`, đổi `camera_id/polygons/lines`.
- File root `camera_config.yaml` là legacy fallback (giữ để tương thích, không dùng mới).
- Thứ tự resolve: `entrypoint.sh` ưu tiên `CONFIG_POS > CONFIG_FILE > configs/active.yaml > configs/cameras/${CAMERA_ID}.yaml`.
- `deploy.sh start cam_01` tìm trong `configs/cameras/`; `start-all` chỉ quét `configs/cameras/cam_*.yaml`.

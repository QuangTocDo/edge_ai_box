# scripts/ (P3 restructure; tools/ là legacy shim)

```
scripts/
├── calibrate/draw_lines.py   # GUI vẽ polygon/line (copy từ tools/, bản chuẩn mới)
├── benchmark_onnx.py         # bench .pt vs .onnx
├── show_classes.py           # xuất mẫu dataset
├── strip_medial.py           # dọn medial/divider
├── health_check.sh           # check heartbeat (dùng cho `make health`)
├── download_models.sh        # hướng dẫn lấy model về weights/
└── _archive/
    ├── draw_lines_legacy.py  # cũ, ghi no_way.yaml — đừng dùng
    └── split_dataset.py      # one-shot tạo data_v1, đã stale
```

Quy ước: code mới viết ở `scripts/`, `tools/` giữ nguyên để docs/lệnh cũ vẫn chạy.
`draw_lines.py` mới import được cả `src.calibration` (mới) lẫn `src.draw_state` (shim cũ).

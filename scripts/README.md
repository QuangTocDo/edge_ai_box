# scripts/ (chuẩn duy nhất, đã thay thế tools/ legacy)

```
scripts/
├── calibrate/draw_lines.py   # GUI vẽ polygon/line (bản chuẩn)
├── benchmark_onnx.py         # bench .pt vs .onnx
├── show_classes.py           # xuất mẫu dataset
├── show_yolo_labels.py       # xem ảnh kèm labels YOLO
├── strip_medial.py           # dọn medial/divider
├── health_check.sh           # check heartbeat (dùng cho `make health`)
├── download_models.sh        # hướng dẫn lấy model về weights/
└── _archive/
    ├── draw_lines_legacy.py  # cũ, ghi no_way.yaml — đừng dùng
    └── split_dataset.py      # one-shot tạo data_v1, đã stale
```

Quy ước: mọi tool mới viết ở `scripts/`, thư mục `tools/` legacy đã xóa.

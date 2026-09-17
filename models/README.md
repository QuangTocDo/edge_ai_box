# Model versioning — detector
# File thật trong weights/ (runtime) + mô tả ở đây. Không dùng symlink sang assets/.

| File | Size | Nguồn | Dùng ở đâu | Ghi chú |
|---|---|---|---|---|
| weights/best_15thg9.pt | 5.2M | train 15/09 | camera_config.yaml model.weights | YOLO chính hiện tại, conf 0.7, imgsz 640–1280 |
| weights/best_15thg9.onnx | 9.6M | export từ .pt (`tools/benchmark_onnx.py`) | thử ONNXRuntime CPU (P1) | đã cho vào Docker image từ P0 |
| weights/best.pt | 15M | copy thật từ assets/best.pt (P0 fix symlink gãy) | fallback / base.yaml | trước đây là symlink -> ../assets/best.pt |

Quy ước thêm model mới:
1. Đặt file vào `weights/` (hoặc `models/detector/` ở P2, mirror nhau 1 phase).
2. Thêm 1 dòng vào bảng này: ngày train, data (data_v1 v1?), mAP, conf/imgsz khuyến nghị.
3. Đừng commit `*.engine/*.tflite` trừ khi edge target cần; video/dataset giữ ngoài repo.

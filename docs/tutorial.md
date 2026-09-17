# HƯỚNG DẪN NHANH 5 PHÚT (QUICKSTART TUTORIAL)

Tài liệu này giúp bạn làm quen và vận hành nhanh hệ thống AI giám sát giao thông thông minh (**Traffic Edge**) trong vòng 5 phút.

> [!TIP]
> Để xem tài liệu kỹ thuật chuyên sâu và đầy đủ tất cả các tham số chi tiết, vui lòng xem [HUONG_DAN_CHAY.md](HUONG_DAN_CHAY.md).

---

## Bước 1: Chạy Thử Nghiệm Pipeline Ngay Lập Tức

Chạy lệnh sau từ thư mục gốc dự án để xem hệ thống nhận diện xe, bám vết (OC-SORT) và tính toán vi phạm thời gian thực:

```bash
.venv/bin/python pipeline.py --source assets/video.mp4 --max-frames 200
```
- Màn hình sẽ hiển thị bounding box phương tiện, vệt di chuyển (trajectory), điểm tiếp đất (bottom-center màu vàng), và các vạch ảo.
- Nhấn `q` để thoát.

Nếu muốn chạy nhanh không cần mở cửa sổ GUI (chế độ Headless):
```bash
.venv/bin/python pipeline.py --source assets/video.mp4 --no-show --imgsz 480
```

---

## Bước 2: Thiết Lập Vạch Phạt Bằng Công Cụ Trực Quan (`draw_lines.py`)

Hệ thống cung cấp giao diện vẽ vạch ảo theo quy trình **Chọn Loại Lỗi Trước (Phím 1-5)**:

```bash
.venv/bin/python tools/draw_lines.py snap_cam01.jpg --config no_way.yaml
```
*(Nếu chưa có ảnh snapshot, có thể truyền trực tiếp file video: `python tools/draw_lines.py assets/video.mp4`)*.

### 📌 Các bước vẽ cho từng loại lỗi:

1. **Đi ngược chiều (`wrong_way`):**
   - Nhấn phím `1` $\to$ Nhấn phím `l` $\to$ Click 2 điểm để vẽ vạch ngang đường.
   - Nhấn `f` nếu muốn đảo ngược chiều mũi tên cho phép.
2. **Cấm quay đầu (`no_uturn`):**
   - Nhấn phím `2` $\to$ Nhấn phím `p` vẽ vùng đa giác (click các đỉnh $\to$ Enter).
   - Tool tự động cho phép vẽ 2 vạch bên trong và tự động liên kết 2 chiều quay đầu.
3. **Đường cấm theo giờ / theo loại xe (`no_entry_road`):**
   - Nhấn phím `3` $\to$ Nhấn phím `p` vẽ đa giác bao quanh đoạn đường cấm $\to$ Enter.
   - Nhập loại xe cấm và khung giờ cấm (vd: `18:00-05:00`) trên màn hình terminal.
4. **Vượt đèn đỏ & dừng đè vạch (`red_light`):**
   - Nhấn phím `4` $\to$ Nhấn phím `p` vẽ làn dừng $\to$ Nhấn `l` vẽ vạch dừng (Stop-line).
   - Nhấn `r` $\to$ Kéo chuột vẽ khung chữ nhật bao quanh hộp đèn tín hiệu.
   - Double-click chọn vạch dừng $\to$ Nhấn `k` để liên kết hộp đèn với vạch dừng.
   - Nhấn `i` vẽ vùng ngã tư giao lộ (clearance zone) nếu muốn tự động chụp ảnh 3 khung hình (Triptych).
5. **Đo tốc độ (`speeding`):**
   - Nhấn phím `5` $\to$ Nhấn phím `p` vẽ làn đường $\to$ Double-click chọn vùng $\to$ Nhấn `c` hiệu chuẩn Homography theo toạ độ mét thực tế.

👉 **Lưu lại:** Nhấn phím **`s`** để lưu vào file YAML. Nhấn **`q`** để thoát.

---

## Bước 3: Xem Bằng Chứng Vi Phạm Đã Thu Thập

Khi phát hiện phương tiện vi phạm, hệ thống tự động ghi nhận tại thư mục `evidence/`:

```text
evidence/
└── CAM_01/
    └── date=2026-09-11/
        ├── wrong_way/
        │   ├── 163908_469_3ceabe51.jpg   <-- Ảnh chụp kèm bbox, vạch vi phạm
        │   └── 163908_469_3ceabe51.json  <-- Metadata (ID, class, SHA-256 hash)
        └── red_light_running/
            └── 164500_120_a1b2c3d4_triptych.jpg <-- Ảnh ghép 3 góc (Trước - Đè - Trong ngã tư)
```

Kiểm tra nhanh các vi phạm vừa ghi nhận:
```bash
ls -lh evidence/*/*/*/*.jpg
```

---

## Bước 4: Triển Khai Thực Tế Với Docker Edge (RTSP Camera)

Chạy camera giao thông trên thiết bị biên chạy nền (Headless):

```bash
# 1. Chạy thử với video giả lập
CAM_SOURCE=assets/video.mp4 docker compose up -d --build

# 2. Chạy với luồng camera RTSP thật
CAM_SOURCE="rtsp://admin:matkhau123@192.168.1.100:554/stream" docker compose up -d --build

# 3. Xem log thời gian thực của camera
docker logs -f traffic-cam01

# 4. Kiểm tra nhịp tim camera còn hoạt động
docker exec traffic-cam01 cat /tmp/heartbeat
```

---

## ⚡ Bảng Phím Tắt Cần Nhớ Trong Công Cụ Vẽ

| Phím | Chức năng |
|---|---|
| `1` $\to$ `5` | Chọn loại vi phạm cần cấu hình |
| `l` | Vẽ vạch (click 2 điểm) |
| `p` | Vẽ vùng đa giác (click các đỉnh $\to$ Enter chốt) |
| `r` | Kéo chuột vẽ hộp đèn tín hiệu giao thông |
| `k` | Gán đèn vào vạch Stop-line |
| `f` | Đảo chiều mũi tên cho phép của vạch |
| `x` | Xoá đối tượng đang chọn |
| `s` | Lưu cấu hình vào file YAML |
| `q` | Thoát |

---

## 📚 Tài Liệu Tham Khảo Thêm
- [HUONG_DAN_CHAY.md](HUONG_DAN_CHAY.md): Hướng dẫn chi tiết kiến trúc, unit test, thuật toán và cấu hình đầy đủ.
- [PROJECT_PLAN.md](PROJECT_PLAN.md): Kế hoạch và thiết kế hệ thống giao thông thông minh.

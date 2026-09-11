# HƯỚNG DẪN CHẠY DỰ ÁN

Mọi lệnh chạy từ thư mục gốc dự án (`digital-city-expand`), dùng virtualenv `.venv`:
```bash
.venv/bin/python <script> ...
```
*(Nếu đã chạy `source .venv/bin/activate` thì có thể gọi trực tiếp `python <script> ...`)*.

---

## 1. Pipeline phát hiện vi phạm (`pipeline.py`)

Hệ thống xử lý video/RTSP thời gian thực theo mô hình Edge: **Capture $\to$ YOLOv11 + OC-SORT Tracking $\to$ Rule Engine $\to$ Evidence Storage**.

### 1.1. Các lệnh chạy thông dụng

| Trường hợp | Lệnh |
|---|---|
| Test nhanh qua file cấu hình | `python pipeline.py --run-config test_config.yaml` |
| Xem trực tiếp kèm overlay GUI | `python pipeline.py --source assets/video1.mp4 --max-frames 300` |
| Chạy ngầm (headless, không GUI) | `python pipeline.py --source assets/video1.mp4 --no-show` |
| Chạy tăng tốc (~2x FPS, imgsz 480) | `python pipeline.py --source assets/video1.mp4 --no-show --imgsz 480` |
| Xuất và lưu video kèm overlay | `python pipeline.py --source assets/video1.mp4 --save out.mp4 --no-show` |
| Chạy từ Webcam máy tính | `python pipeline.py --source 0` |
| Chạy với cấu hình camera riêng | `python pipeline.py --config configs/cam_01.yaml` *(lấy nguồn từ `source:` trong file)* |
| Ghi đè nguồn RTSP stream | `python pipeline.py --config configs/cam_01.yaml --source "rtsp://user:pass@ip:554/stream"` |
| Bật debug phân tích rules | `python pipeline.py --config camera_config.yaml --debug-rules` |

- **Thứ tự ưu tiên nguồn video (`source`):**
  `Tham số CLI --source` > `Biến môi trường CAM_SOURCE` > `Trường source: trong YAML` > `Mặc định assets/video.mp4`.
- **Thứ tự ưu tiên tham số chạy:**
  `CLI trỏ trực tiếp` > `File test_config.yaml` > `File camera config YAML` > `Default hardcoded`.
- Nhấn `q` hoặc `Esc` để thoát khi đang xem cửa sổ trực tiếp.

### 1.2. Danh sách 6 loại lỗi vi phạm được hỗ trợ

1. **`wrong_way` (Đi ngược chiều):**
   - Xe cắt vạch theo hướng ngược chiều quy định (`allowed_sign`).
   - Yêu cầu duy trì di chuyển ngược $\ge$ `min_reverse_frames` (mặc định 5 frames) hoặc tích luỹ quãng đường ngược $\ge$ `min_reverse_px` (mặc định 60px). Tự động reset nếu xe quay đầu đúng hướng hoặc dừng đỗ.
2. **`no_uturn` (Cấm quay đầu):**
   - Sequence thuận 2 vạch trong cùng zone: Xe chạm vạch $L_1$ đúng chiều $\to$ chạm vạch $L_2$ đúng chiều (hoặc ngược lại tuỳ cấu hình pair).
   - Không ràng buộc thời gian (xe chạy nhanh hay chậm đều phát hiện chuẩn xác).
3. **`no_entry_road` (Đi vào đường cấm):**
   - Áp dụng cho vùng cấm đa giác (`kind: banned`).
   - Lọc theo loại phương tiện cấm (`banned_classes`, ví dụ: xe tải, xe máy) và khung giờ cấm (`active_hours`, ví dụ `18:00-05:00` hoặc 24/7).
   - Xe thuộc diện cấm đi vào và duy trì điểm tiếp đất trong vùng $\ge$ `dwell_s` (mặc định 2.0s) $\to$ Kích hoạt vi phạm.
4. **`red_light_running` (Vượt đèn đỏ):**
   - Xe vượt qua vạch dừng Stop-line khi tín hiệu đèn của vạch đó đang **RED**.
   - **Whitelist thông minh:** Mũi xe chạm vạch lúc đèn đang **GREEN**, **YELLOW** hoặc **UNKNOWN** (mất tín hiệu / hết hạn TTL) sẽ được miễn phạt hoàn toàn.
   - Hỗ trợ dung sai phản xạ (`dilemma_grace_s`) và bỏ qua nếu làn cho phép rẽ phải khi đèn đỏ (`allow_right_on_red: true`).
   - **2 chế độ lưu bằng chứng:**
     - *Có vùng ngã tư (`intersection_clearance_zone`):* Theo dõi xe tiến vào trung tâm giao lộ $\to$ Xuất ảnh ghép 3 khung hình **Triptych** (*Trước vạch - Đè vạch - Trong ngã tư*).
     - *Không có clearance (đường thẳng/vạch độc lập):* Cơ chế **Movement/Velocity Confirmation** — xe tiếp tục tiến về phía trước $\ge 30$ px và duy trì tốc độ $\ge 1.5$ px/frame $\to$ Báo vi phạm với ảnh chụp đúng thời điểm cắt vạch.
5. **`stop_line_violation` (Dừng đè vạch người đi bộ khi đèn đỏ):**
   - Xe đè qua Stop-line lúc đèn **RED**, sau đó giảm tốc độ ($< 1.5$ px/frame) và dừng yên $\ge$ `stop_dwell_s` (mặc định 3.0s).
   - Nếu sau đó xe tiếp tục vượt vào giao lộ $\to$ Sự kiện vượt đèn đỏ sẽ ghi đè và huỷ bỏ lỗi đè vạch để tránh phạt 2 lần.
6. **`speeding` (Chạy quá tốc độ - Pure Vision):**
   - Ánh xạ điểm tiếp đất của bánh xe sang toạ độ thực (mét) bằng ma trận phối cảnh Homography $H$.
   - Chiếu quãng đường theo trục hướng đường (`road_dir`) và làm mượt bằng Moving Average trong 0.8s.
   - Tích hợp chống rung camera bằng Lucas-Kanade Optical Flow; tự phát hiện nhảy ID/ID-switch để tránh đo sai.
   - Vượt ngưỡng `limit_kmh` liên tục trong `sustain_s` $\ge 1.0$s $\to$ Báo vi phạm kèm độ tin cậy `confidence`. *(Khuyến nghị: Dùng cảnh báo/thống kê)*.

### 1.3. Nhận diện Đèn Tín hiệu Giao thông (`src/signals.py`)

- Tự động phân tích màu đèn bằng xử lý ảnh HSV thuần trên vùng ROI hộp đèn (`signals: [{id, roi, ttl_s}]`).
- Tách biệt ngưỡng màu ban ngày (`hsv`) và ban đêm (`hsv_night`) theo giờ máy chủ edge.
- Cơ chế **Debounce 2 frames** liên tiếp chống hiện tượng chớp nháy đèn.
- Tự động đo độ trễ từ lúc đèn vàng kết thúc sang đèn đỏ (`yellow_to_red_latency_ms`).

### 1.4. Quản lý Bằng chứng Vi phạm (`evidence/`)

- Lưu trữ theo định dạng chuẩn: `evidence/<camera_id>/date=YYYY-MM-DD/<violation_type>/`.
- Mỗi vụ vi phạm tạo 2 file:
  - File ảnh `.jpg`: Ảnh đơn hoặc ảnh ghép 3 khung hình Triptych, vẽ bbox, điểm tiếp đất, vạch dừng, timestamp.
  - File `.json`: Metadata chi tiết (ID xe, class, độ tin cậy, toạ độ, trạng thái đèn, mã băm SHA-256 của file ảnh đảm bảo tính pháp lý).
- **Tự động dọn dẹp (Retention):** Định kỳ kiểm tra và xoá các thư mục ngày cũ hơn `retention_days` (mặc định 7 ngày).

---

## 2. Công cụ Vẽ & Quản lý Zone / Lines trực quan (`tools/draw_lines.py`)

Giao diện đồ hoạ tương tác dùng để thiết lập vạch ảo, vùng đa giác, hộp đèn giao thông và hiệu chuẩn tốc độ trực tiếp trên ảnh chụp/video camera.

```bash
python tools/draw_lines.py assets/video1.mp4 [--config camera_config.yaml]
```

### 2.1. Menu Chọn Lỗi theo Phím Số (1 đến 5)

Để tránh vẽ nhầm hoặc cấu hình sai công cụ, hệ thống yêu cầu **chọn loại lỗi cần thiết lập trước**:

| Phím | Loại lỗi | Công cụ được phép dùng | Mô tả luồng thao tác |
|---|---|---|---|
| `1` | **wrong_way** *(Ngược chiều)* | `l` | Nhấn `l` $\to$ click 2 điểm vẽ line độc lập ngang làn. Mũi tên vàng chỉ hướng đi hợp lệ. |
| `2` | **no_uturn** *(Cấm quay đầu)* | `p`, `l`, `a` | Nhấn `p` vẽ đa giác vùng quay đầu (Enter chốt) $\to$ tự chuyển sang vẽ 2 line $L_1, L_2$ bên trong $\to$ tool tự sinh cả 2 chiều pair quay đầu ($L_1 \to L_2$ và $L_2 \to L_1$). Hoặc dùng `a` gán pair thủ công. |
| `3` | **no_entry** *(Đường cấm)* | `p` | Nhấn `p` $\to$ click các đỉnh polygon bao quanh đoạn đường cấm $\to$ **Enter** $\to$ nhập `banned_classes` (vd `0,4`), `active_hours` (vd `18:00-05:00`, Enter để trống = cấm 24/7), `dwell_s`. |
| `4` | **red_light** *(Đèn đỏ & Đè vạch)* | `p`, `l`, `r`, `i`, `k` | Nhấn `p` vẽ polygon làn dừng $\to$ `l` vẽ vạch dừng (Stop-line) $\to$ `r` kéo chuột chọn hộp đèn $\to$ `k` gán đèn vào vạch $\to$ `i` vẽ vùng ngã tư giao lộ (clearance zone). |
| `5` | **speeding** *(Đo tốc độ)* | `p`, `c` | Nhấn `p` vẽ polygon làn đo $\to$ double-click chọn polygon $\to$ nhấn `c` hiệu chuẩn Homography mặt đường. |
| `0` | **Menu Tự do** *(Legacy)* | Tất cả | Cho phép vẽ tự do không ràng buộc theo lỗi (dành cho người dùng nâng cao). |

### 2.2. Bảng Phím Tắt Thao Tác Chi Tiết

| Phím / Thao tác | Tác dụng |
|---|---|
| **Double-click chuột** | **Chọn đối tượng:** Chọn line (click gần vạch), chọn hộp đèn signal (click trong hộp), hoặc chọn polygon (click trong vùng). Đối tượng được chọn chuyển màu đỏ kèm nhãn `sel=<id>`. |
| `l` | **Vẽ Line:** Click 2 điểm để tạo vạch ảo (tự gán vào polygon gần nhất hoặc top-level). |
| `p` | **Vẽ Polygon:** Click từng đỉnh ($\ge 3$ đỉnh) $\to$ nhấn **Enter** để chốt vùng đa giác. |
| `r` | **Kéo ROI Hộp đèn:** Nhấn, giữ và kéo chuột tạo khung chữ nhật bao quanh đèn giao thông. |
| `k` | **Gán Đèn vào Vạch:** Double-click chọn Stop-line $\to$ nhấn `k` để liên kết `signal_id` với vạch đó. |
| `i` | **Vẽ Vùng Giao Lộ:** Vẽ polygon ngã tư (`kind: intersection`), tự động liên kết làm clearance zone cho lỗi vượt đèn đỏ. |
| `c` | **Hiệu chuẩn Tốc độ (Homography):** Double-click chọn polygon $\to$ nhấn `c` $\to$ click $\ge 4$ điểm trên mặt đường $\to$ **Enter** $\to$ nhập toạ độ mét thực tế $\to$ `y` xác nhận $\to$ click 2 điểm A $\to$ B dọc đường $\to$ **Enter** chốt `road_dir`. |
| `f` | **Đảo chiều:** Đảo ngược hướng mũi tên cho phép (`allowed_sign`) của line đang chọn. |
| `x` *(hoặc Delete)* | **Xoá đối tượng:** Xoá line, polygon hoặc hộp đèn đang được chọn (các pair/liên kết liên quan tự động gỡ theo). |
| `u` | **Gỡ Đèn:** Gỡ bỏ liên kết signal khỏi line đang chọn. |
| `a` | **Gán Pair U-turn tay:** Click lần lượt 2 vạch đã vẽ ($L_1 \to L_2$). |
| `s` | **Lưu cấu hình:** Ghi toàn bộ thay đổi vào file cấu hình YAML (tự validate dữ liệu và đọc lại file để đối soát). |
| `Esc` | **Huỷ thao tác:** Huỷ bỏ thao tác vẽ dở hoặc thoát khỏi chế độ công cụ hiện tại. |
| `q` | **Thoát:** Đóng công cụ (nếu có thay đổi chưa lưu, phải nhấn `q` 2 lần để xác nhận). |

---

## 3. Cấu hình YAML Chuẩn (`camera_config.yaml` / `configs/cam_01.yaml`)

Dự án hỗ trợ kiến trúc gộp cấu hình: file camera con có thể khai báo `base: base.yaml` để kế thừa toàn bộ tham số model/evidence và chỉ ghi đè phần toạ độ hình học riêng.

```yaml
camera_id: CAM_HOANG_HOA_THAM_01
config_version: cfg_v2
timezone: Asia/Ho_Chi_Minh
source: "rtsp://admin:pass123@192.168.1.100:554/Streaming/Channels/101"

model:
  weights: weights/best.pt
  conf: 0.4
  imgsz: 640
  classes: [0, 1, 2, 3, 4, 5, 6, 7]
  tracker: ocsort.yaml
  device: null   # null = auto CPU/CUDA, 0 = GPU 0

# 1. Hộp đèn giao thông (phân tích HSV)
signals:
  - id: SIG_01
    roi: [1200, 150, 1240, 260]   # [x1, y1, x2, y2]
    ttl_s: 1.5

# 2. Danh sách các vùng đa giác (Polygons)
polygons:
  # Làn dừng đèn đỏ và đè vạch
  - id: POLY_RED_LANE_01
    kind: directional
    polygon: [[200, 400], [500, 400], [550, 800], [150, 800]]
    lines:
      - id: L_STOP_01
        p1: [210, 450]
        p2: [490, 450]
        allowed_sign: 1
        signal_id: SIG_01
        allow_right_on_red: false
    rules:
      red_light_running:
        enable: true
        intersection_clearance_zone: POLY_JUNCTION_CENTER
      stop_line_violation:
        enable: true
        stop_dwell_s: 3.0
      wrong_way: {enable: false}
      no_uturn: {enable: false}

  # Vùng trung tâm ngã tư (clearance zone cho vượt đèn đỏ)
  - id: POLY_JUNCTION_CENTER
    kind: intersection
    polygon: [[200, 200], [800, 200], [850, 400], [150, 400]]
    rules:
      red_light_running: {enable: false}

  # Vùng cấm quay đầu
  - id: POLY_UTURN_ZONE
    kind: directional
    polygon: [[100, 500], [600, 500], [600, 900], [100, 900]]
    lines:
      - id: L_UTURN_IN
        p1: [120, 600]
        p2: [300, 600]
        allowed_sign: 1
      - id: L_UTURN_OUT
        p1: [350, 600]
        p2: [580, 600]
        allowed_sign: -1
    uturn_pairs:
      - {first: L_UTURN_IN, second: L_UTURN_OUT}
      - {first: L_UTURN_OUT, second: L_UTURN_IN}
    rules:
      no_uturn: {enable: true}
      wrong_way: {enable: false}

  # Đoạn đường cấm theo giờ
  - id: POLY_BANNED_STREET
    kind: banned
    polygon: [[50, 300], [250, 300], [250, 700], [50, 700]]
    banned_classes: [0, 4]             # Class xe máy ngày + đêm
    active_hours: ["06:00-09:00", "16:30-19:30"]
    dwell_s: 2.0
    rules:
      no_entry_road: {enable: true}

# 3. Vạch đơn độc lập (Top-level wrong_way)
lines:
  - id: L_ONEWAY_01
    p1: [700, 500]
    p2: [950, 500]
    allowed_sign: 1

# 4. Tham số mặc định toàn cục
wrong_way:
  min_hits: 3
  min_reverse_frames: 5
  min_reverse_px: 60.0
  cooldown_s: 10.0

red_light:
  dilemma_grace_ms: 0
  confirm_dist_px: 30.0
  confirm_speed_px: 1.5
  confirm_frames: 2

evidence:
  dir: evidence
  jpeg_quality: 90
  retention_days: 7
```

---

## 4. Kiểm thử Đơn vị (Unit Tests)

Dự án sở hữu bộ test toàn diện bao phủ toàn bộ các module hình học, bộ quy tắc vi phạm và parser cấu hình:

```bash
# Chạy toàn bộ các test quy tắc vi phạm (Rules)
python -m tests.test_rule_wrong_way     # Ngược chiều (trigger, reset khi quay đúng hướng, explain)
python -m tests.test_rule_no_uturn       # Cấm quay đầu (2 chiều, sequence đúng/sai, xe chạy nhanh)
python -m tests.test_rule_no_entry       # Đường cấm (dwell time, banned classes, active hours)
python -m tests.test_rule_red_light      # Vượt đèn đỏ (movement confirmation, whitelist xanh/vàng, triptych)
python -m tests.test_rule_stop_line      # Đè vạch (dừng đủ dwell, nhường lỗi khi xe tiếp tục vượt)
python -m tests.test_rule_speeding       # Quá tốc độ (homography, lọc rung camera, lọc ID-switch)

# Chạy kiểm thử lõi hệ thống & cấu hình
python -m tests.test_geometry            # Thuật toán cắt vạch crossing_sign, allowed_vec, ray-casting
python -m tests.test_homography          # RANSAC homography matrix, reprojection error
python -m tests.test_registry            # Đăng ký và nạp dynamic rule runner
python -m tests.test_polygon             # Quản lý đa giác, kiểm tra khung giờ qua đêm
python -m tests.test_line_config         # CRUD lines, polygons, pairs, signals
python -m tests.test_config_loader       # Deep merge base.yaml, fail-fast validation, routing
python -m tests.test_evidence            # Lưu bằng chứng JPG/JSON, triptych, xoay vòng dọn dẹp
python -m tests.test_draw_state          # Máy trạng thái chuột, lọc nhiễu double-click
python -m tests.test_draw_menu           # Logic menu phím chọn lỗi 1-5
```

---

## 5. Thêm Quy tắc Vi phạm Mới (Quy chuẩn Mở rộng)

Hệ thống được thiết kế theo kiến trúc **Open-Closed Principle** — thêm lỗi mới trong đúng 1 file mà không cần can thiệp vào `pipeline.py`:

1. Tạo file quy tắc mới: `src/rules/ten_loi_moi.py`:
   - Kế thừa lớp `BaseRule`.
   - Định nghĩa hằng số `TYPE = "ten_loi_moi"` và dictionary `PARAMS = {...}`.
   - Cài đặt phương thức `update(self, track, ...)` và `explain(self, track, ...)`.
2. Đăng ký quy tắc vào [`src/rules/registry.py`](file:///home/toan/Documents/project/digital-city-expand/src/rules/registry.py):
   - Import class vừa tạo và thêm vào `RULE_REGISTRY` cùng `CANONICAL_TYPES`.
3. Viết unit test tương ứng trong `tests/test_rule_ten_loi_moi.py`.
4. Khai báo rule trong cấu hình YAML: Pipeline sẽ tự động nạp và kích hoạt.

---

## 6. Huấn luyện Mô hình YOLOv11 (`yolo26n`)

Các lệnh chạy trên máy chủ huấn luyện có GPU:

```bash
# Huấn luyện trên 1 GPU
yolo detect train data=data_v1/data.yaml model=weights/yolo26n.pt epochs=100 imgsz=640 device=0 batch=16 patience=20 project=runs name=yolo26n_v1_8cls pretrained=True val=True plots=True save=True

# Huấn luyện song song trên 2 GPU
yolo detect train data=data_v1/data.yaml model=weights/yolo26n.pt epochs=100 imgsz=640 device=0,1 batch=64 patience=20 workers=16 cache=disk seed=42 project=runs name=yolo26n_v1_8cls pretrained=True val=True plots=True save=True

# Đánh giá độ chính xác trên tập test
yolo detect val data=data_v1/data.yaml model=runs/yolo26n_v1_8cls/weights/best.pt split=test
```

- **Lưu ý:** File `data_v1/data.yaml` không đặt đường dẫn tuyệt đối `path:` — Ultralytics sẽ tự động nhận diện thư mục chứa file làm gốc, giúp clone repo về bất kỳ máy nào cũng chạy được ngay.
- Huấn luyện xong, copy file trọng số tốt nhất về `weights/best.pt` và kiểm tra 8 class xe tương thích.

---

## 7. Triển khai Docker Container tại Thiết bị Biên (Edge)

Mỗi camera tương ứng với 1 container chạy độc lập, tự động khởi động lại khi gặp sự cố:

### 7.1. Quy trình thiết lập

1. **Chụp ảnh Snapshot chuẩn độ phân giải stream:**
   ```bash
   ffmpeg -i "rtsp://user:pass@ip:554/stream" -vframes 1 snap_cam01.jpg
   ```
   *(Lưu ý bắt buộc: Ảnh snapshot vẽ zone phải có cùng độ phân giải với stream thực tế tại runtime, ví dụ cùng là 1920x1080)*.
2. **Vẽ cấu hình trên máy host (có màn hình GUI):**
   ```bash
   python tools/draw_lines.py snap_cam01.jpg --config configs/cam_01.yaml
   ```
3. **Chạy thử nghiệm bằng docker-compose:**
   ```bash
   CAM_SOURCE="assets/video1.mp4" docker compose up --build
   ```
4. **Chạy chính thức với luồng RTSP thật:**
   ```bash
   CAM_SOURCE="rtsp://user:pass@ip:554/stream" docker compose up -d --build
   docker logs -f traffic-cam01
   ```

### 7.2. Đặc điểm kỹ thuật trong Docker
- Container tự động bật cờ `--no-show` khi phát hiện môi trường headless (không có biến `$DISPLAY`).
- URL chứa tài khoản/mật khẩu RTSP được tự động che thành dạng `rtsp://user:***@ip/...` khi ghi log, đảm bảo an toàn bảo mật.
- Hỗ trợ cơ chế phục hồi tự động khi đứt kết nối mạng RTSP: pipeline tự động reconnect sau mỗi 3 giây thay vì crash tiến trình.
- Cập nhật file nhịp tim `/tmp/heartbeat` định kỳ 1 giây. Giám sát container còn sống bằng:
  ```bash
  docker exec traffic-cam01 cat /tmp/heartbeat
  ```

---

## 8. Xử lý Sự cố Thường Gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân phổ biến | Cách khắc phục |
|---|---|---|
| `CUDA device invalid` / `is_available(): False` | Phiên bản PyTorch CUDA không tương thích driver máy host | Hạ phiên bản PyTorch khớp với CUDA của driver (ví dụ cu121/cu124), hoặc chạy thuần CPU mode (`device: null`). |
| Cảnh báo thiếu thư viện `lap` khi tracking | Thuật toán OC-SORT cần thư viện giải bài toán phân công Linear Assignment | Chạy `.venv/bin/pip install "lap>=0.5.12"` hoặc để Ultralytics tự biên dịch tải về. |
| Xe đi qua vùng nhưng không báo vi phạm | 1) Điểm đáy bánh xe (Bottom-Center) lệch ra ngoài đa giác (xem số `skip` trên overlay).<br>2) Chưa đủ thời gian `dwell_s` hoặc số frame tích luỹ `min_hits`.<br>3) Xe không nằm trong danh sách `banned_classes` hoặc ngoài khung giờ cấm. | Bật cờ `--debug-rules` khi chạy pipeline để xem log chi tiết dòng giải thích `explain()` cho từng chiếc xe. |
| Nhấn phím trong `draw_lines.py` không phản hồi | Chuột đang focus ở cửa sổ Terminal thay vì cửa sổ hình ảnh | Click chuột vào cửa sổ đồ hoạ `draw_lines` trước khi bấm phím tắt. |
| Đèn đỏ nhưng không kích hoạt lỗi vượt | Đèn đang ở trạng thái `YELLOW`, `UNKNOWN` (hết hạn TTL) hoặc xe chạm vạch trước khi đèn chuyển sang đỏ $\to$ lọt vào Whitelist. | Kiểm tra lại ROI hộp đèn qua overlay; đảm bảo vùng ROI cắt đúng 3 khoang đèn đỏ/vàng/xanh và không bị bóng cây che khuất. |
| Container tự thoát ngay sau khi chạy | File cấu hình `camera_config.yaml` chưa có polygon/line nào | Dùng `tools/draw_lines.py` vẽ và nhấn `s` để lưu ít nhất một vạch/vùng trước khi chạy. |

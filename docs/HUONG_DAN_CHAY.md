# HƯỚNG DẪN CHẠY DỰ ÁN (VIDEO CÓ SẴN & RTSP STREAM)

Tất cả các lệnh thực hiện từ thư mục gốc dự án (`digital-city-expand`), sử dụng môi trường virtualenv `.venv`:
```bash
# Kích hoạt môi trường ảo (khuyên dùng)
source .venv/bin/activate
python <script> ...

# Hoặc gọi trực tiếp từ binary:
.venv/bin/python <script> ...
```

---

## 1. Tổng quan Nguồn Dữ liệu Đầu vào (Source Resolution)

Hệ thống xử lý đầu vào đa dạng: **File Video có sẵn (.mp4, .mkv, .avi, ...)**, **Luồng RTSP/HTTP từ Camera IP**, và **Webcam trực tiếp**.

### Thứ tự ưu tiên xác định nguồn video (`source`):
1. **Tham số dòng lệnh (`CLI --source`)**: Ưu tiên cao nhất khi chạy test thử nghiệm hoặc ghi đè nhanh.
2. **Biến môi trường / Secret (`CAM_SOURCE` hoặc `CAM_SOURCE_FILE`)**: Thích hợp khi chạy Docker hoặc triển khai edge device.
3. **Tự động ghép nối RTSP link qua các biến môi trường**: `IP_CAMERA`, `TK_CAMERA`, `PASSWORD_CAMERA`, `EXTEND_RSTP_LINK`.
4. **Trường `source:` khai báo trong file cấu hình YAML** (ví dụ `configs/cam_01.yaml`).
5. **Nguồn mặc định dự phòng**: `assets/video.mp4`.

---

## 2. Hướng dẫn Chạy với Video có sẵn (Local Video Files)

Khi phát triển, kiểm thử thuật toán hoặc đánh giá độ chính xác của các quy tắc vi phạm, chạy với video có sẵn là giải pháp nhanh chóng và đáng tin cậy nhất.

### 2.1. Quy trình chuẩn bị và vẽ vạch cho Video có sẵn
Trước khi chạy pipeline phát hiện vi phạm, bạn cần vẽ vạch và vùng kiểm tra tương ứng với góc máy của video:
```bash
# Mở trực tiếp file video trong công cụ vẽ (tự động lấy frame đại diện ở 1/3 video):
python tools/draw_lines.py assets/video1.mp4 --config configs/cam_01.yaml
```
*(Xem chi tiết hướng dẫn thao tác vẽ vạch tại [Mục 4](#4-công-cụ-vẽ--quản-lý-zone--lines-trực-quan-toolsdraw_linespy))*.

### 2.2. Các kịch bản chạy thường gặp với Video có sẵn

| Kịch bản | Lệnh thực hiện | Mục đích |
|---|---|---|
| **Xem trực tiếp có GUI Overlay** | `python pipeline.py --config configs/cam_01.yaml --source assets/video1.mp4` | Quan sát trực tiếp xe chạy, bounding box, ID tracking, trạng thái đèn và sự kiện vi phạm trên màn hình. Nhấn `q` hoặc `Esc` để thoát. |
| **Chạy ngầm tốc độ cao (Headless)** | `python pipeline.py --config configs/cam_01.yaml --source assets/video1.mp4 --no-show` | Bỏ qua hiển thị GUI của OpenCV để đạt tốc độ xử lý (FPS) tối đa, tiết kiệm CPU/GPU. |
| **Tăng tốc xử lý (~2x FPS)** | `python pipeline.py --config configs/cam_01.yaml --source assets/video1.mp4 --no-show --imgsz 480` | Giảm kích thước ảnh đầu vào YOLO xuống 480px, xử lý cực nhanh trên các máy cấu hình khiêm tốn. |
| **Test nhanh số lượng khung hình** | `python pipeline.py --config configs/cam_01.yaml --source assets/video1.mp4 --max-frames 300` | Chỉ chạy đúng 300 khung hình đầu tiên rồi tự động xuất kết quả và kết thúc. |
| **Xuất và lưu video kết quả có vẽ Overlay** | `python pipeline.py --config configs/cam_01.yaml --source assets/video1.mp4 --save output_annotated.mp4 --no-show` | Ghi toàn bộ kết quả phân tích kèm vạch kẻ, khung nhận diện xe, thông tin vi phạm ra file `.mp4`. |
| **Bật Debug logic phân tích Rules** | `python pipeline.py --config configs/cam_01.yaml --source assets/video1.mp4 --debug-rules` | In ra terminal giải thích chi tiết (`explain()`) lý do tại sao một phương tiện bị hoặc chưa bị bắt lỗi sau mỗi 30 frames. |
| **Chạy qua file cấu hình test tổng hợp** | `python pipeline.py --run-config configs/test_config.yaml` | Tải sẵn toàn bộ tham số test từ file YAML (đường dẫn video, config, imgsz, max_frames). |

### 2.3. Đặc điểm khi chạy với Video có sẵn
- Pipeline đọc tuần tự từng frame theo FPS gốc của video.
- Khi video kết thúc, pipeline sẽ tự động xả hết bằng chứng còn trong hàng đợi (flush evidence saver), đóng file và hiển thị bảng thống kê tổng số frame, thời gian chạy, FPS trung bình và số lượng vi phạm đã ghi nhận.

---

## 3. Hướng dẫn Chạy với Luồng RTSP Camera (Live Streams)

Khi triển khai thực tế trên thiết bị biên (Edge) hoặc kết nối trực tiếp đến Camera IP giao thông, hệ thống hỗ trợ giao thức RTSP với các cơ chế chống trễ và bảo mật cao cấp.

### 3.1. Các cách cấu hình nguồn RTSP

#### Cách 1: Truyền trực tiếp qua CLI (Nhanh nhất khi test link RTSP)
```bash
python pipeline.py --config configs/cam_01.yaml --source "rtsp://admin:Password123@192.168.1.100:554/Streaming/Channels/101"
```

#### Cách 2: Khai báo trong file cấu hình YAML của Camera
Trong file cấu hình (ví dụ `configs/cam_01.yaml`), thêm trường `source:` ở cấp gốc:
```yaml
camera_id: CAM_HOANG_HOA_THAM_01
source: "rtsp://admin:Password123@192.168.1.100:554/Streaming/Channels/101"
# ... các cấu hình model, rules, polygons khác ...
```
Sau đó chỉ cần chạy:
```bash
python pipeline.py --config configs/cam_01.yaml
```

#### Cách 3: Dùng biến môi trường `CAM_SOURCE` (Khuyên dùng khi chạy Docker/CI)
Tránh để lộ mật khẩu trong code hoặc file config:
```bash
export CAM_SOURCE="rtsp://admin:Password123@192.168.1.100:554/Streaming/Channels/101"
python pipeline.py --config configs/cam_01.yaml --no-show
```

#### Cách 4: Tự động ghép nối URL từ thông tin Camera (Auto-composed RTSP)
Hệ thống hỗ trợ tự động lắp ghép URL RTSP từ các biến môi trường riêng biệt:
```bash
export IP_CAMERA="192.168.1.100:554"
export TK_CAMERA="admin"
export PASSWORD_CAMERA="Password123"
export EXTEND_RSTP_LINK="/Streaming/Channels/101" # Nếu không đặt, mặc định là /MediaInput/h264/stream_1

python pipeline.py --config configs/cam_01.yaml --no-show
```
*Pipeline sẽ tự động tạo URL dạng: `rtsp://admin:Password123@192.168.1.100:554/Streaming/Channels/101`.*

#### Cách 5: Đọc mật khẩu từ Docker Secrets File
Để đạt tiêu chuẩn an toàn thông tin cao nhất trên Edge device (không lưu password dạng plaintext trong env hay process table):
```bash
export IP_CAMERA="192.168.1.100:554"
export TK_CAMERA="admin"
export PASSWORD_CAMERA_FILE="/run/secrets/cam_password"
export EXTEND_RSTP_LINK="/Streaming/Channels/101"

python pipeline.py --config configs/cam_01.yaml --no-show
```

### 3.2. Cơ chế kỹ thuật chuyên dụng cho luồng RTSP
- **`AsyncStreamReader` - Chống trễ tích lũy (Anti Buffer Drift):**
  Khác với video file, luồng RTSP truyền liên tục 25-30 FPS. Nếu phần cứng chạy inference mô hình chỉ đạt 15 FPS, việc dùng `cv2.VideoCapture` thông thường sẽ khiến buffer tràn và hình ảnh bị trễ dần (sau vài giờ có thể trễ tới hàng chục phút). Hệ thống sử dụng background thread liên tục đọc frame từ stream và chỉ giữ **frame mới nhất** cho pipeline xử lý.
- **Che giấu thông tin nhạy cảm (`_mask_source`):**
  Toàn bộ URL RTSP chứa tài khoản/mật khẩu đều tự động được che thành dạng `rtsp://admin:***@192.168.1.100:554/...` trên console log và hệ thống ghi log, đảm bảo tuyệt đối an toàn.
- **Tự động phục hồi kết nối (Auto-reconnect):**
  Khi camera bị mất mạng, sụt nguồn hoặc rớt gói tin RTSP, pipeline không bị crash mà tự động thử kết nối lại theo chu kỳ định kỳ 1s – 3s cho đến khi luồng hoạt động trở lại.
- **Vòng lặp stream không tắt:**
  Khi đọc stream RTSP, nếu tạm thời mất frame, pipeline sẽ ngủ nhẹ 10ms (`time.sleep(0.01)`) để nhường CPU và tiếp tục chờ frame mới, không tự động ngắt như đối với video file.

### 3.3. Quy trình thiết lập vạch (Zone/Lines) cho Camera RTSP
Do Camera RTSP là luồng động trực tiếp, quy trình vẽ cấu hình chuẩn như sau:

1. **Bước 1: Chụp 1 khung hình (Snapshot) từ RTSP đúng độ phân giải gốc:**
   ```bash
   ffmpeg -y -i "rtsp://admin:Password123@192.168.1.100:554/Streaming/Channels/101" -vframes 1 snap_cam01.jpg
   ```
   > [!IMPORTANT]
   > Ảnh snapshot dùng để vẽ vạch **bắt buộc** phải có cùng độ phân giải (ví dụ 1920x1080) với luồng stream mà camera sẽ truyền vào khi chạy thật.

2. **Bước 2: Mở ảnh snapshot trong `tools/draw_lines.py` để thiết lập vạch/vùng:**
   ```bash
   python tools/draw_lines.py snap_cam01.jpg --config configs/cam_01.yaml
   ```
   Vẽ các vạch, vùng cấm, hộp đèn giao thông theo hướng dẫn bên dưới và nhấn `s` để lưu cấu hình.

3. **Bước 3: Khởi chạy pipeline giám sát chính thức:**
   ```bash
   python pipeline.py --config configs/cam_01.yaml --source "rtsp://admin:Password123@192.168.1.100:554/Streaming/Channels/101" --no-show
   ```

---

## 4. Công cụ Vẽ & Quản lý Zone / Lines trực quan (`tools/draw_lines.py`)

Giao diện đồ hoạ tương tác dùng để thiết lập vạch ảo, vùng đa giác, hộp đèn giao thông và hiệu chuẩn tốc độ trực tiếp trên ảnh chụp hoặc video camera:

```bash
# Mở từ file video:
python tools/draw_lines.py assets/video1.mp4 --config configs/cam_01.yaml

# Hoặc mở từ ảnh snapshot camera:
python tools/draw_lines.py snap_cam01.jpg --config configs/cam_01.yaml
```

### 4.1. Menu Chọn Lỗi theo Phím Số (1 đến 5)
Để tránh vẽ nhầm hoặc cấu hình sai công cụ, hệ thống yêu cầu **chọn loại lỗi cần thiết lập trước**:

| Phím | Loại lỗi | Công cụ được phép dùng | Mô tả luồng thao tác |
|---|---|---|---|
| `1` | **wrong_way** *(Ngược chiều)* | `l` | Nhấn `l` $\to$ click 2 điểm vẽ line độc lập ngang làn. Mũi tên vàng chỉ hướng đi hợp lệ. |
| `2` | **no_uturn** *(Cấm quay đầu)* | `p`, `l`, `a` | Nhấn `p` vẽ đa giác vùng quay đầu (Enter chốt) $\to$ tự chuyển sang vẽ 2 line $L_1, L_2$ bên trong $\to$ tool tự sinh cả 2 chiều pair quay đầu ($L_1 \to L_2$ và $L_2 \to L_1$). Hoặc dùng `a` gán pair thủ công. |
| `3` | **no_entry** *(Đường cấm)* | `p` | Nhấn `p` $\to$ click các đỉnh polygon bao quanh đoạn đường cấm $\to$ **Enter** $\to$ nhập `banned_classes` (vd `0,4`), `active_hours` (vd `18:00-05:00`, Enter để trống = cấm 24/7), `dwell_s`. |
| `4` | **red_light** *(Đèn đỏ & Đè vạch)* | `p`, `l`, `r`, `i`, `k` | Nhấn `p` vẽ polygon làn dừng $\to$ `l` vẽ vạch dừng (Stop-line) $\to$ `r` kéo chuột chọn hộp đèn $\to$ `k` gán đèn vào vạch $\to$ `i` vẽ vùng ngã tư giao lộ (clearance zone). |
| `5` | **speeding** *(Đo tốc độ)* | `p`, `c` | Nhấn `p` vẽ polygon làn đo $\to$ double-click chọn polygon $\to$ nhấn `c` hiệu chuẩn Homography mặt đường. |
| `0` | **Menu Tự do** *(Legacy)* | Tất cả | Cho phép vẽ tự do không ràng buộc theo lỗi (dành cho người dùng nâng cao). |

### 4.2. Bảng Phím Tắt Thao Tác Chi Tiết

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

## 5. Danh mục 6 Loại Vi phạm được Hỗ trợ

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

---

## 6. Cấu hình YAML Chuẩn (`configs/cam_01.yaml`)

Dự án hỗ trợ kiến trúc gộp cấu hình: file camera con có thể khai báo `base: base.yaml` để kế thừa toàn bộ tham số model/evidence và chỉ ghi đè phần toạ độ hình học riêng.

```yaml
camera_id: CAM_HOANG_HOA_THAM_01
config_version: cfg_v2
timezone: Asia/Ho_Chi_Minh

# Nguon video: File video cuc bo hoac RTSP stream
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

## 7. Triển khai Docker trên Từng Thiết bị Biên (Standalone Edge Deployment)

Trong mô hình thực tế, **mỗi thiết bị biên (Edge Box / IPC / mini-PC tại cột đèn) chỉ phụ trách xử lý duy nhất 1 Camera cục bộ**, không chạy tập trung nhiều camera trên một máy chủ. Do đó, quy trình được tối ưu để chỉ cần **1 lệnh khởi chạy duy nhất** trên từng con biên.

---

### 7.1. Quy trình Chuẩn bị tại Con Biên (Chỉ làm 1 lần)

1. **Chuẩn bị file cấu hình camera (`camera_config.yaml`) cho con biên:**
   Mỗi con biên chỉ cần 1 file `camera_config.yaml` chứa vạch kẻ, vùng cấm, đèn tín hiệu tương ứng với góc nhìn camera của nó.
   *(Có thể vẽ trước trên máy cá nhân bằng `tools/draw_lines.py` rồi copy file `camera_config.yaml` sang con biên)*.

2. **Cấu hình nguồn luồng RTSP qua file `.env`:**
   ```bash
   cp .env.example .env
   # Sửa địa chỉ IP và tài khoản camera trong .env:
   # CAM_SOURCE=rtsp://admin:Password123@192.168.1.100:554/Streaming/Channels/101
   ```

---

### 7.2. Khởi chạy 1 Lệnh Duy Nhất qua `docker compose` (Khuyên dùng)

Trên con biên, chỉ cần chạy đúng 1 lệnh:
```bash
docker compose up -d
```
Container `traffic-edge` sẽ tự động:
- Đọc file `./camera_config.yaml` được mount vào container.
- Kết nối tới luồng RTSP của camera cục bộ.
- Kích hoạt chế độ `restart: always` (tự động bật lại ngay lập tức khi tủ điện/con biên mất điện rồi có điện lại).
- Kích hoạt chế độ mạng `network_mode: host` giúp đọc luồng RTSP mượt mà, loại bỏ hoàn toàn độ trễ và hiện tượng rớt gói tin qua Docker NAT.
- Giới hạn kích thước file log (`max-size: 20m`) bảo vệ bộ nhớ SSD/eMMC của thiết bị biên không bị đầy.

**Các lệnh vận hành nhanh trên con biên:**
```bash
# Xem log phân tích trực tiếp:
docker compose logs -f

# Khởi động lại dịch vụ:
docker compose restart

# Dừng dịch vụ:
docker compose down
```

---

### 7.3. Khởi chạy bằng `docker run` độc lập (Không cần compose)

Nếu bạn không muốn dùng `docker-compose`, chỉ cần chạy 1 lệnh `docker run`:

```bash
docker run -d --name traffic-edge \
  --restart always \
  --network host \
  -v ./camera_config.yaml:/app/camera_config.yaml:ro \
  -v ./evidence:/app/evidence \
  -v ./data:/app/data \
  traffic-edge
```
*(Nếu muốn ghi đè nguồn camera trực tiếp từ dòng lệnh, thêm cờ `-e CAM_SOURCE="rtsp://..."`)*.

---

### 7.4. Triển khai Ngoại tuyến (Offline Deploy) ra Hiện trường không có Internet

Tại các cột đèn giao thông ngoài đường, thiết bị biên thường **không có internet tốc độ cao** để build docker hay tải thư viện nặng:

1. **Tại máy phát triển (có mạng Internet):**
   ```bash
   # Build image sẵn:
   docker build -t traffic-edge .

   # Đóng gói image thành file nén:
   docker save traffic-edge:latest | gzip > traffic-edge.tar.gz
   ```

2. **Chuyển ra thiết bị biên (qua USB hoặc mạng LAN nội bộ):**
   ```bash
   # Nạp image vào Docker của con biên trong vài giây:
   docker load -i traffic-edge.tar.gz

   # Khởi chạy camera ngay lập tức:
   docker compose up -d
   ```

---

### 7.5. Giám sát Trạng thái (Healthcheck & Heartbeat) trên Con Biên

Mỗi 1 giây, container định kỳ gửi nhịp tim vào file `./data/heartbeat`. Hệ thống watchdog giám sát của thiết bị biên có thể kiểm tra:
```bash
# Xem thời gian ghi nhận nhịp tim gần nhất:
cat data/heartbeat

# Kiểm tra trạng thái sức khoẻ do Docker Healthcheck giám sát:
docker inspect --format='{{json .State.Health.Status}}' traffic-edge
```

---

## 8. Quản lý Bằng chứng Vi phạm & Tải lên S3 (`s3_worker.py`)

- Lưu trữ cục bộ tại edge: `evidence/<camera_id>/date=YYYY-MM-DD/<violation_type>/`
  - Gồm file ảnh `.jpg` (ảnh đơn hoặc ảnh ghép 3 khung hình Triptych) và metadata `.json` (kèm mã SHA-256 xác thực).
- **Tải lên AWS S3 định kỳ (Batch Upload lúc 20:00):**
  ```bash
  # Vận hành thủ công kiểm tra:
  .venv/bin/python s3_worker.py --camera CAM_HOANG_HOA_THAM_01 --dry-run
  .venv/bin/python s3_worker.py --camera CAM_HOANG_HOA_THAM_01 --limit 5

  # Xem ảnh qua presigned URL (hiệu lực 3600 giây):
  .venv/bin/python s3_worker.py --presigned camera-01/2026/09/16/anh.jpg --expires 3600
  ```

---

## 9. Kiểm thử Đơn vị (Unit Tests)

Hệ thống sở hữu bộ test toàn diện bao phủ toàn bộ các module hình học, bộ quy tắc vi phạm và parser cấu hình:

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
python -m tests.test_signals             # Nhận diện màu HSV, debounce, phát hiện đèn vàng nhấp nháy
python -m tests.test_homography          # RANSAC homography matrix, reprojection error
python -m tests.test_registry            # Đăng ký và nạp dynamic rule runner
python -m tests.test_polygon             # Quản lý đa giác, kiểm tra khung giờ qua đêm
python -m tests.test_line_config         # CRUD lines, polygons, pairs, signals
python -m tests.test_config_loader       # Deep merge base.yaml, fail-fast validation, routing
python -m tests.test_evidence            # Lưu bằng chứng JPG/JSON, triptych, xoay vòng dọn dẹp, webhook
python -m tests.test_draw_state          # Máy trạng thái chuột, lọc nhiễu double-click
python -m tests.test_draw_menu           # Logic menu phím chọn lỗi 1-5
```

---

## 10. Xử lý Sự cố Thường Gặp (Troubleshooting)

| Hiện tượng | Nguyên nhân phổ biến | Cách khắc phục |
|---|---|---|
| `[INPUT SRC] Khong mo duoc stream` | Sai URL RTSP, sai user/password, hoặc camera không cùng dải mạng | 1) Thử mở link bằng `ffplay "rtsp://..."` hoặc VLC trên cùng máy.<br>2) Đảm bảo ping thông IP camera.<br>3) Kiểm tra tài khoản/mật khẩu có ký tự đặc biệt (nếu có cần URL encode). |
| `[INPUT SRC] Khong mo duoc video` | Sai đường dẫn file video hoặc chưa mount vào Docker | Kiểm tra file có tồn tại bằng `ls -l <path>`. Trong Docker, mount thư mục chứa video vào container (`./assets:/app/assets`). |
| Video chạy bị giật lag / FPS thấp | Chế độ hiển thị GUI chiếm nhiều tài nguyên hoặc chạy CPU | 1) Thêm cờ `--no-show` để tắt GUI.<br>2) Thêm cờ `--imgsz 480` để giảm tải cho bộ nhận diện YOLO.<br>3) Kiểm tra card đồ hoạ đã kích hoạt CUDA (`device: 0`). |
| Stream RTSP bị trễ hình (delay) sau một thời gian chạy | Pipeline thông thường bị dồn buffer khi inference chậm | Pipeline đã tích hợp sẵn `AsyncStreamReader` chạy thread nền để loại bỏ trễ. Đảm bảo bạn chạy trực tiếp qua `pipeline.py` mà không can thiệp tắt module này. |
| Xe đi qua vùng nhưng không báo vi phạm | 1) Điểm tiếp đất (Bottom-Center) lệch ra ngoài đa giác.<br>2) Chưa đủ thời gian `dwell_s` hoặc số frame `min_hits`.<br>3) Xe không thuộc `banned_classes` hoặc ngoài giờ cấm. | Bật cờ `--debug-rules` khi chạy pipeline để xem log chi tiết dòng giải thích `explain()` cho từng chiếc xe. |
| Nhấn phím trong `draw_lines.py` không phản hồi | Chuột đang focus ở cửa sổ Terminal thay vì cửa sổ hình ảnh | Click chuột vào cửa sổ đồ hoạ `draw_lines` trước khi bấm phím tắt. |
| Vạch vẽ trong `draw_lines` bị lệch so với luồng camera thật | Ảnh snapshot chụp để vẽ vạch khác độ phân giải với luồng RTSP | Chụp lại snapshot từ đúng luồng RTSP bằng ffmpeg với cùng resolution trước khi vẽ. |
| Đèn đỏ nhưng không kích hoạt lỗi vượt | Đèn đang ở trạng thái `YELLOW`, `UNKNOWN` hoặc xe chạm vạch lúc đèn còn xanh | Kiểm tra lại ROI hộp đèn qua overlay; đảm bảo vùng ROI cắt đúng 3 khoang đèn đỏ/vàng/xanh và không bị bóng cây che khuất. |

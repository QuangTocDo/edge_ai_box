# 🚦 Edge Traffic Vision & Digital City AI Platform
> **Hệ thống AI Biên Giám Sát, Nhận Diện Vi Phạm Giao Thông & Trật Tự Đô Thị Thời Gian Thực**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://react.dev/)
[![ONNX Runtime](https://img.shields.io/badge/ONNX_Runtime-GPU%20%2F%20CPU-005CED.svg)](https://onnxruntime.ai/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6.svg)](https://www.typescriptlang.org/)

---

## 📌 1. Giới thiệu tổng quan

**Edge Traffic Vision (`digital-city-expand`)** là giải pháp phần mềm thị giác máy tính biên (Edge AI) toàn diện, được thiết kế chuyên biệt cho các thiết bị Edge AI Box (NVIDIA Jetson, Industrial PC x86 tích hợp GPU RTX) và máy chủ phân tán. Hệ thống phân tích trực tiếp các luồng camera giám sát giao thông đô thị (RTSP IP Camera, Video file) với hiệu năng cao, độ trễ cực thấp và khả năng vận hành độc lập (headless edge) hoặc đồng bộ cùng hệ thống Dashboard quản trị tập trung.

### ✨ Các điểm nổi bật:
* **Xử lý đa luồng & suy luận AI tối ưu**: Tích hợp YOLO (ONNX Runtime với CUDA / TensorRT / CPU fallback) kết hợp bộ theo dõi chuyển động đa đối tượng **OC-SORT / ByteTrack** đảm bảo độ chính xác theo dấu đối tượng ngay cả khi bị che khuất tạm thời.
* **Bộ quy tắc xử lý vi phạm giao thông chuẩn mực**: Xây dựng dưới dạng máy trạng thái (State Machine) nghiêm ngặt, hỗ trợ 9 nhóm hành vi vi phạm phổ biến theo quy chuẩn giao thông Việt Nam và quốc tế.
* **Cơ chế lưu trữ bằng chứng phạt nguội chuyên nghiệp (Evidence Vault)**: Tự động trích xuất chuỗi khoảnh khắc vàng (3 frames cho lỗi vượt đèn đỏ: *trước vạch - đè vạch - vào giao lộ*; 1 frame cho lỗi *đè vạch*), lọc và chỉ giữ lại bounding box của phương tiện vi phạm phục vụ lập hồ sơ xử phạt minh bạch.
* **Bảng điều khiển trực quan (Operations Dashboard)**: Web application hiện đại (React 18 + Vite + TypeScript) cho phép giám sát live feed, xem lịch sử vi phạm và cung cấp công cụ hiệu chuẩn hình học (SVG Canvas) trực tiếp ghi cấu hình xuống tệp `active.yaml`.

---

## 🏗️ 2. Kiến trúc hệ thống (System Architecture)

```mermaid
flowchart TD
    subgraph INGESTION ["1. Ingestion Layer"]
        CAM["RTSP IP Cameras / Local Videos"] --> CAPTURE["Threaded Video Capture (OpenCV / PyAV)"]
    end

    subgraph EDGE_CORE ["2. Edge AI Pipeline Core"]
        CAPTURE --> INFER["YOLO Object Detection (ONNX Runtime / TensorRT)"]
        INFER --> TRACKER["Multi-Object Tracker (OC-SORT / ByteTrack)"]
        TRACKER --> RULES["Traffic Business Rules Engine"]
        
        subgraph RULES_SET ["Quy tắc vi phạm"]
            R1["Đèn đỏ / Đè vạch dừng"]
            R2["Cấm quay đầu (Heading Reversal)"]
            R3["Đi ngược chiều (Directional Vector)"]
            R4["Quá tốc độ (Homography BEV)"]
            R5["Đường cấm / Dừng đỗ / Tụ tập"]
        end
        RULES --> RULES_SET
    end

    subgraph EVIDENCE ["3. Evidence & Event Sinks"]
        RULES_SET --> EV_MGR["Evidence Manager (Object Store)"]
        EV_MGR --> SNAP["Lưu ảnh 3 khoảng khắc (Chỉ giữ bbox xe vi phạm)"]
        EV_MGR --> SQLITE[("SQLite Event Database")]
    end

    subgraph GATEWAY ["4. Backend & Web Dashboard"]
        SQLITE --> FASTAPI["FastAPI REST & WebSocket Gateway"]
        FASTAPI --> WS["Live Stream & WebSocket Events"]
        FASTAPI --> CALIB["Live Geometry Calibrator (active.yaml)"]
        
        WS --> UI["React 18 Dashboard UI"]
        CALIB --> UI
    end
```

---

## ⚖️ 3. Danh mục quy tắc vi phạm (Business Rules Engine)

| Mã Rule | Tên quy tắc | Nguyên lý kỹ thuật & Cơ chế phát hiện | Chuẩn bằng chứng |
| :--- | :--- | :--- | :--- |
| `red_light_running` | **Vượt đèn đỏ** | Máy trạng thái 3 pha liên hoàn: Đèn tín hiệu ĐỎ $\to$ Xe cắt vạch dừng `STOP_LINE` $\to$ Xe tiến sâu vào vùng giao lộ `INTERSECTION_POLYGON`. | Lưu **3 ảnh**: Trước vạch, đè vạch và đi vào giao lộ. Bounding box làm nổi bật xe vi phạm. |
| `stop_line` | **Đè vạch dừng** | Xe chạm/đè qua vạch dừng khi đèn tín hiệu giao thông đang đỏ nhưng không tiến sâu vào giao lộ. | Lưu **1 ảnh** khoảnh khắc đè vạch (chỉ giữ bbox xe vi phạm). |
| `no_uturn` | **Cấm quay đầu** | Giám sát sequence 2 vạch có hướng (`L1 ➔ L2`), xác thực độ lệch góc di chuyển ban đầu và kết thúc $\Delta \in [120^\circ, 240^\circ]$. Loại trừ xe đi thẳng để tránh bắt oan. | Ảnh chụp xe tại thời điểm cắt vạch kết thúc, metadata kèm góc quay $\Delta^\circ$ và thời gian $dt$. |
| `wrong_way` | **Đi ngược chiều** | So sánh vector chuyển động của phương tiện với vector pháp tuyến cho phép (`allowed_sign`) của vạch kiểm soát hoặc hướng quy định của đa giác làn đường. | Ảnh chụp xe vi phạm kèm vector hướng di chuyển ngược chiều. |
| `speeding` | **Chạy quá tốc độ** | Sử dụng ma trận biến đổi phối cảnh 4 điểm **Homography** chuyển tọa độ camera sang mặt phẳng chuẩn (Bird's-Eye View - mét), đo vận tốc $v = \frac{\Delta s}{\Delta t}$ (km/h). | Ảnh chụp xe tại vị trí vượt quá tốc độ giới hạn quy định, kèm vận tốc đo được. |
| `no_entry_road` | **Đi vào đường cấm** | Xe di chuyển vào vùng đa giác quy định là đường cấm hoặc khu vực cấm lưu thông. | Ảnh chụp xe bên trong vùng cấm. |
| `no_parking` | **Dừng đỗ trái phép** | Theo dõi vị trí phương tiện dừng đỗ bất động bên trong đa giác cấm đỗ vượt quá ngưỡng thời gian quy định (`dwell_s`). | Ảnh chụp tại thời điểm phát hiện đỗ và thời điểm hết hạn ngưỡng đỗ. |
| `no_gathering` | **Tụ tập đông người** | Đếm tổng số người (`person`) trong khu vực kiểm soát vượt ngưỡng `min_persons` trong khoảng thời gian `dwell_s`. | Ảnh chụp bao quát kèm nhãn số lượng đối tượng tụ tập. |
| `heavy_traffic` | **Ùn tắc giao thông** | Đánh giá đồng thời mật độ phương tiện trên làn và vận tốc trung bình của dòng xe. | Cảnh báo trạng thái ùn tắc trên tuyến đường. |

---

## 📸 4. Cơ chế lưu trữ & Trích xuất bằng chứng (Evidence Pipeline)

Nhằm đảm bảo tính chính xác và bằng chứng minh bạch phục vụ phạt nguội:
1. **Lọc Bounding Box thông minh**:
   - Hệ thống không lưu lại hàng loạt bounding box của các phương tiện xung quanh làm rối hình ảnh.
   - Chỉ giữ lại **duy nhất bounding box và nhãn của phương tiện thực sự vi phạm**.
2. **Chuỗi 3 khoảnh khắc vàng cho lỗi vượt đèn đỏ**:
   - **Ảnh 1 (Trước vạch)**: Chụp lại khi xe đang tiếp cận vạch dừng lúc đèn tín hiệu đã chuyển đỏ.
   - **Ảnh 2 (Đè vạch)**: Chụp lại thời điểm tâm đáy của xe chạm đè lên vạch dừng.
   - **Ảnh 3 (Vào giao lộ)**: Chụp lại thời điểm xe đã đi sâu vào tim giao lộ (chứng minh hành vi vượt đèn đỏ hoàn tất).
3. **Quản lý vòng đời tệp**: Tự động dọn dẹp các ảnh bằng chứng cũ theo cấu hình `retention_days` (mặc định 7 ngày).

---

## 🖥️ 5. Giao diện điều hành & Hiệu chuẩn Web (Dashboard)

Giao diện Web tương tác hoàn chỉnh xây dựng trên nền tảng React 18 + Vite + TypeScript:
* **Live Camera Feed**: Giám sát hình ảnh trực tiếp qua WebSocket/JPEG Stream thời gian thực.
* **Canvas Hiệu chuẩn Hình học (SVG Calibrator)**:
  * Vẽ vùng giao lộ / làn đường đa giác (`polygons`).
  * Vẽ vạch dừng (`STOP_LINE`), hộp nhận diện đèn tín hiệu (`SIGNAL`), vạch kiểm soát quay đầu (`UTURN_L`).
  * Nút **Đổi chiều ⇄** (`flip`) đảo nhanh hướng vector cho phép mà không cần nhập tọa độ thủ công.
  * Tự động sinh cặp quay đầu **Auto A ⇄ B** hoặc gán cặp thủ công kèm đường cong trực quan (`Arc Curve`).
  * Đo khoảng cách và hiệu chuẩn ma trận phối cảnh Homography cho bài toán đo tốc độ.
* **Evidence Viewer**: Bảng tra cứu sự kiện vi phạm, lọc theo loại vi phạm, khoảng thời gian và xem ảnh bằng chứng độ phân giải gốc.

---

## 📂 6. Cấu trúc thư mục dự án

```text
digital-city-expand/
├── backend/                        # Backend API Gateway (FastAPI)
│   └── app/
│       ├── database.py             # Kết nối SQLite & Session
│       ├── models.py               # SQLAlchemy ORM Models (Cameras, Events)
│       ├── schemas.py              # Pydantic Schemas
│       ├── routers/                # API Routers (cameras, events, live, websocket)
│       └── services/               # Background workers, streaming & video processing
├── frontend/                       # Web Dashboard (React 18 + TypeScript + Vite)
│   ├── src/
│   │   ├── components/             # Reusable UI components & layouts
│   │   ├── pages/                  # Dashboard, CalibratePage, Events, LiveCameras
│   │   └── services/api.ts         # API Client giao tiếp backend
├── src/                            # Lõi xử lý AI (Edge Processing Engine)
│   ├── business/
│   │   └── rules/                  # Máy trạng thái các quy tắc vi phạm giao thông
│   ├── config/                     # Trình tải, chuẩn hóa & kiểm tra schema active.yaml
│   ├── pipeline/                   # Engine suy luận, tracker & điều phối luồng
│   ├── storage/                    # Quản lý SQLite sink & Object store lưu ảnh
│   └── utils/                      # Xử lý hình học phẳng, vector, homography
├── configs/                        # Thư mục lưu trữ cấu hình YAML camera
│   ├── base.yaml                   # Cấu hình gốc mặc định
│   └── active.yaml                 # Cấu hình đang chạy của camera
├── scripts/
│   └── calibrate/                  # Bộ công cụ hiệu chuẩn local (draw_lines.py, ...)
├── weights/                        # Thư mục chứa trọng số mô hình YOLO (ONNX)
├── assets/                         # Video & hình ảnh mẫu kiểm thử
├── pipeline.py                     # Entrypoint CLI chạy độc lập trên Edge
├── start_dashboard.sh              # Script khởi chạy toàn bộ dịch vụ (Backend + UI)
└── README.md                       # Tài liệu hướng dẫn dự án
```

---

## 🚀 7. Hướng dẫn cài đặt & Khởi chạy

### 7.1. Yêu cầu môi trường
* **Hệ điều hành**: Linux (Ubuntu 20.04 / 22.04 LTS khuyến nghị)
* **Python**: Phiên bản 3.10 trở lên
* **Node.js**: Phiên bản 18+ và `npm`
* **GPU (Tùy chọn nhưng khuyến nghị)**: NVIDIA GPU hỗ trợ CUDA 11.8+ / 12.x để đạt FPS tối ưu qua ONNX Runtime CUDAExecutionProvider.

### 7.2. Cài đặt môi trường
```bash
# 1. Clone mã nguồn dự án
git clone https://github.com/QuangTocDo/edge_ai_box.git
cd digital-city-expand

# 2. Tạo và kích hoạt môi trường ảo Python
python3 -m venv .venv
source .venv/bin/activate

# 3. Cài đặt các gói phụ thuộc Python
pip install --upgrade pip
pip install -r requirements.txt

# 4. Cài đặt phụ thuộc cho Frontend Dashboard
cd frontend
npm install
cd ..
```

### 7.3. Khởi chạy toàn bộ hệ thống (Backend API + Web Dashboard)
Dự án đi kèm script khởi động tự động:
```bash
chmod +x start_dashboard.sh
./start_dashboard.sh
```
Sau khi khởi chạy thành công:
* **Dashboard Web UI**: `http://127.0.0.1:5173`
* **Swagger API Documentation**: `http://127.0.0.1:8000/docs`

### 7.4. Khởi chạy Engine AI độc lập (Headless Edge Mode)
Bạn có thể chạy riêng tiến trình AI pipeline từ dòng lệnh trên các thiết bị biên:
```bash
# Chạy với video mẫu và cấu hình active.yaml
.venv/bin/python pipeline.py --source assets/uturn.mp4 --config configs/active.yaml

# Chạy với luồng RTSP camera IP và ẩn cửa sổ GUI:
.venv/bin/python pipeline.py --source "rtsp://admin:pass@192.168.1.100:554/live" --config configs/active.yaml --no-show
```

---

## ⚙️ 8. Quy chuẩn tệp cấu hình (`configs/active.yaml`)

Cấu hình cho mỗi camera được lưu trữ dưới định dạng YAML chuẩn:
```yaml
camera_id: CAM_TEST_01
config_version: cfg_v2

# Cấu hình lưu trữ bằng chứng
evidence:
  dir: evidence
  jpeg_quality: 90
  retention_days: 7

# Cấu hình mô hình nhận diện
model:
  weights: weights/best_15thg9.onnx
  imgsz: 1280
  conf: 0.7
  tracker: ocsort.yaml

# Cấu hình vạch dừng & vạch kiểm soát
lines:
  - id: STOP_LINE_1
    p1: [320, 750]
    p2: [960, 750]
    role: stop
  - id: UTURN_L1
    p1: [400, 600]
    p2: [550, 600]
    allowed_sign: 1
    role: uturn

# Cặp vạch kiểm soát quay đầu
uturn_pairs:
  - first: UTURN_L1
    second: UTURN_L2

# Vùng đa giác giao lộ & kiểm soát
polygons:
  - id: ZONE_INTERSECTION
    kind: directional
    polygon: [[300, 500], [1000, 500], [1100, 900], [200, 900]]
    rules:
      red_light_running:
        enable: true
      no_uturn:
        enable: true
```

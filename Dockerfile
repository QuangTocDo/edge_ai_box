# Standalone Edge Device: moi thiet bi bien chay 1 camera doc lap.
#
# Trien khai nhanh nhat tai tung con bien:
#   1. Dat file cau hinh camera tai ./configs/active.yaml
#      (ve bang tools/draw_lines.py -> luu vao active.yaml; pipeline doc tu day)
#      hoac khai bao qua .env (CONFIG_FILE)
#   2. Khoi chay don gian chi voi file config:
#        docker compose up -d
#      Hoac build lai neu co code moi:
#        docker compose up --build
#      Hoac dung docker run:
#        docker run -d --name traffic-edge --restart always --network host \
#          -v ./configs/active.yaml:/app/camera_config.yaml:ro \
#          -v ./evidence:/app/evidence \
#          -v ./data:/app/data \
#          -v ./assets:/app/assets:ro \
#          traffic-edge
#
# Build image tren con bien (hoac build 1 lan roi export tar mang ra cac con bien):
#   docker build -t traffic-edge .
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# ffmpeg (doc stream RTSP OpenCV) + libGL / glib ho tro xu ly anh
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app app

WORKDIR /app

# torch + torchvision CPU pin cung version (toi uu kich thuoc va on dinh cho edge CPU)
RUN pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 \
    --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ma nguon, cong cu & cau hinh dung chung
# (configs/active.yaml la canonical: COPY configs/ da gom; khong COPY
# camera_config.yaml root legacy de tranh nham trong image)
COPY pipeline.py entrypoint.sh s3_worker.py ./
COPY src/ ./src/
COPY configs/ ./configs/

# Model weights: best_15thg9.pt/.onnx có sẵn trong image
# (weights/best.pt là local-only, không COPY — mọi config đã trỏ best_15thg9.pt)
COPY weights/ ./weights/

RUN chmod +x /app/entrypoint.sh \
    && mkdir -p /app/data /app/evidence \
    && chmod -R 777 /app/data /app/evidence

# Thu muc runtime persistent (mount ra host khi trien khai thuc te)
VOLUME ["/app/evidence", "/app/data"]

# Bien moi truong mac dinh cho tung camera container (tat ca deu co fallback doc tu configs/active.yaml)
ENV CAMERA_ID="" \
    CONFIG_FILE="" \
    CAM_SOURCE="" \
    HEARTBEAT_FILE="" \
    IMGSZ="" \
    DEBUG_RULES="" \
    LOG_LEVEL=INFO \
    YOLO_CONFIG_DIR=/tmp

# Healthcheck tu dong kiem tra heartbeat theo tung camera (doc bat ky file heartbeat nao trong /app/data)
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,time,sys,glob;hb=os.environ.get('HEARTBEAT_FILE');files=[hb] if hb and os.path.exists(hb) else glob.glob('/app/data/heartbeat*');sys.exit(0 if files and any(os.path.exists(f) and time.time()-os.path.getmtime(f)<90 for f in files) else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
CMD []

# Edge x86_64 CPU: pipeline headless (draw tool chay tren host, khong trong image).
# Build: docker build -t traffic-edge .
# Chay thu video: CAM_SOURCE=assets/video.mp4 docker compose up
# Chay that RTSP: CAM_SOURCE="rtsp://user:pass@ip/stream" docker compose up -d
# Secrets (khuyen nghi file thay vi env plain): CAM_SOURCE_FILE, WEBHOOK_URL_FILE,
# WEBHOOK_SECRET_FILE (mount tu /run/secrets/*).
FROM python:3.12-slim@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# ffmpeg (RTSP qua OpenCV) + libGL cho opencv-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r app && useradd -r -g app app

WORKDIR /app

# torch + torchvision CPU pin cung version (tranh mismatch torchvision::nms,
# nhe hon nhieu so voi CUDA wheel mac dinh tu pypi)
RUN pip install --no-cache-dir torch==2.7.1 torchvision==0.22.1 \
    --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# code + configs (weights bake vao image de chay on dinh, khoi mount)
COPY pipeline.py ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY camera_config.yaml ./
COPY weights/best.pt ./weights/best.pt
RUN mkdir -p /app/data /app/evidence && chown -R app:app /app

USER app

# thu muc runtime (mount ra host khi chay)
VOLUME ["/app/evidence", "/app/data"]

ENV CAM_SOURCE="" \
    HEARTBEAT_FILE=/app/data/heartbeat \
    LOG_LEVEL=INFO \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,time,sys;f=os.environ.get('HEARTBEAT_FILE','/app/data/heartbeat');sys.exit(0 if os.path.exists(f) and time.time()-os.path.getmtime(f)<90 else 1)"

ENTRYPOINT ["python", "pipeline.py"]
CMD ["--config", "/app/configs/cam_01.yaml", "--no-show"]

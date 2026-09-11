# Edge x86_64 CPU: pipeline headless (draw tool chay tren host, khong trong image).
# Build: docker build -t traffic-edge .
# Chay thu video: CAM_SOURCE=assets/video.mp4 docker compose up
# Chay that RTSP: CAM_SOURCE="rtsp://user:pass@ip/stream" docker compose up -d
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# ffmpeg (RTSP qua OpenCV) + libGL cho opencv-python
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch + torchvision CPU cung version (nhe hon nhieu so voi CUDA wheel mac dinh)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# code + configs (weights bake vao image de chay on dinh, khoi mount)
COPY pipeline.py ./
COPY src/ ./src/
COPY configs/ ./configs/
COPY camera_config.yaml ./
COPY weights/best.pt ./weights/best.pt

# thu muc runtime (mount ra host khi chay)
VOLUME ["/app/evidence"]

ENV CAM_SOURCE="" \
    HEARTBEAT_FILE=/tmp/heartbeat \
    LOG_LEVEL=INFO \
    YOLO_CONFIG_DIR=/tmp/Ultralytics

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os,time,sys;f=os.environ.get('HEARTBEAT_FILE','/tmp/heartbeat');sys.exit(0 if os.path.exists(f) and time.time()-os.path.getmtime(f)<90 else 1)"

ENTRYPOINT ["python", "pipeline.py"]
CMD ["--config", "/app/configs/cam_01.yaml", "--no-show"]

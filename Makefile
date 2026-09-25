IMAGE ?= traffic-edge
CONFIG ?= configs/active.yaml
CAM ?= cam_01

.PHONY: build up down test bench health logs status s3-cleanup

build:
	docker build -t $(IMAGE) .

up:
	docker compose up --build -d

down:
	docker compose down

# Chạy thử 1 camera cụ thể (per-camera)
run-cam:
	./deploy.sh start $(CAM)

start-all:
	./deploy.sh start-all

status:
	./deploy.sh status

logs:
	./deploy.sh logs $(CAM)

test:
	python -m pytest tests/ -q

bench:
	python scripts/benchmark_onnx.py --weights weights/best_15thg9.onnx 2>/dev/null || python scripts/benchmark_onnx.py

health:
	./scripts/health_check.sh 2>/dev/null || ls -l data/heartbeat_* 2>/dev/null || echo "no heartbeat yet (run pipeline first)"

#!/usr/bin/env bash
# Tải model về weights/ (chạy 1 lần trên máy build, không commit model lên git).
set -euo pipefail
mkdir -p weights
echo "weights/ hiện có:"
ls -lh weights/ || true
echo ""
echo "Đặt file .pt/.onnx mới vào weights/, rồi cập nhật models/README.md"
echo "VD: scp edge-models/best_*.pt ./weights/ && make bench"

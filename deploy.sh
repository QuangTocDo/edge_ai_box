#!/usr/bin/env bash
# ==============================================================================
# Script Triển Khai & Quản Lý Nhanh Nhiều Camera Biên (Edge Multi-Camera Deploy)
#
# Cách dùng:
#   ./deploy.sh build                      # Build Docker image chung (1 lần duy nhất)
#   ./deploy.sh start configs/cam_01.yaml  # Khởi chạy 1 camera từ config
#   ./deploy.sh start cam_01               # Khởi chạy nhanh theo mã camera
#   ./deploy.sh start cam_02 "rtsp://..."  # Khởi chạy camera kèm link RTSP
#   ./deploy.sh start-all                  # Khởi chạy TẤT CẢ camera có trong configs/
#   ./deploy.sh status                     # Xem trạng thái và heartbeat của các camera
#   ./deploy.sh logs cam_01                # Xem logs realtime của camera
#   ./deploy.sh stop cam_01                # Dừng 1 camera
#   ./deploy.sh stop-all                   # Dừng tất cả camera
# ==============================================================================

set -e

IMAGE_NAME="traffic-edge"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p configs evidence data assets

_extract_cam_name() {
    local raw="$1"
    raw="$(basename "$raw")"
    raw="${raw%.yaml}"
    raw="${raw%.yml}"
    echo "$raw"
}

cmd_build() {
    echo "==> [BUILD] Đang build Docker image: $IMAGE_NAME ..."
    docker build -t "$IMAGE_NAME" .
    echo "==> [BUILD] Hoàn thành! Image: $IMAGE_NAME"
}

cmd_start() {
    local target="$1"
    local source_override="$2"

    if [ -z "$target" ]; then
        echo "Lỗi: Cần truyền file config hoặc mã camera."
        echo "Ví dụ: $0 start configs/cam_01.yaml [rtsp_link]"
        echo "       $0 start cam_01 [rtsp_link]"
        exit 1
    fi

    local cam_name
    cam_name="$(_extract_cam_name "$target")"
    local container_name="traffic-${cam_name}"

    # Resolve duong dan config (uu tien cameras/ moi, fallback root configs/ legacy)
    local config_file="$target"
    if [ ! -f "$config_file" ]; then
        if [ -f "configs/cameras/${target}.yaml" ]; then
            config_file="configs/cameras/${target}.yaml"
        elif [ -f "configs/${target}.yaml" ]; then
            config_file="configs/${target}.yaml"
        elif [ -f "configs/cameras/cam_${target}.yaml" ]; then
            config_file="configs/cameras/cam_${target}.yaml"
        elif [ -f "configs/cam_${target}.yaml" ]; then
            config_file="configs/cam_${target}.yaml"
        fi
    fi

    if [ ! -f "$config_file" ]; then
        echo "Lỗi: Không tìm thấy file config tương ứng với '$target'."
        exit 1
    fi

    # Neu container da ton tai thi xoa truoc khi khoi dong lai
    if docker ps -a --format '{{.Names}}' | grep -q "^${container_name}$"; then
        echo "--> Container '$container_name' đã tồn tại. Đang dọn dẹp để khởi động lại..."
        docker rm -f "$container_name" >/dev/null 2>&1 || true
    fi

    echo "==> [START] Khởi chạy Camera: $cam_name"
    echo "    - Container : $container_name"
    echo "    - Config    : $config_file"
    if [ -n "$source_override" ]; then
        echo "    - Source    : $source_override"
    fi

    local run_args=(
        -d
        --name "$container_name"
        --restart unless-stopped
        --log-opt max-size=20m
        --log-opt max-file=3
        -v "$SCRIPT_DIR/configs:/app/configs:ro"
        -v "$SCRIPT_DIR/assets:/app/assets:ro"
        -v "$SCRIPT_DIR/evidence:/app/evidence"
        -v "$SCRIPT_DIR/data:/app/data"
    )

    if [ -n "$source_override" ]; then
        run_args+=(-e "CAM_SOURCE=$source_override")
    fi

    docker run "${run_args[@]}" "$IMAGE_NAME" "$config_file"

    echo "==> [OK] Camera '$cam_name' đã khởi chạy thành công!"
    echo "    Theo dõi log bằng: ./deploy.sh logs $cam_name"
}

cmd_start_all() {
    echo "==> [START-ALL] Quét tất cả file config trong thư mục configs/cameras/ + configs/ ..."
    local found=0
    for cfg in configs/cameras/cam_*.yaml configs/cameras/cam*.yaml configs/cam_*.yaml configs/cam*.yaml; do
        [ -e "$cfg" ] || continue
        # Bo qua file test tam thoi neu can
        if [[ "$cfg" == *"test"* ]]; then
            continue
        fi
        cmd_start "$cfg"
        echo "------------------------------------------------------------------"
        found=$((found + 1))
    done

    if [ "$found" -eq 0 ]; then
        echo "Cảnh báo: Không tìm thấy file config nào dạng configs/cam_*.yaml!"
    else
        echo "==> [START-ALL] Đã khởi chạy xong toàn bộ $found camera."
    fi
}

cmd_stop() {
    local target="$1"
    if [ -z "$target" ]; then
        echo "Lỗi: Cần truyền mã camera cần dừng."
        echo "Ví dụ: $0 stop cam_01"
        exit 1
    fi
    local cam_name="$(_extract_cam_name "$target")"
    local container_name="traffic-${cam_name}"

    echo "==> [STOP] Đang dừng $container_name ..."
    docker rm -f "$container_name" >/dev/null 2>&1 || true
    echo "==> [OK] Đã dừng $container_name"
}

cmd_stop_all() {
    echo "==> [STOP-ALL] Đang dừng tất cả camera traffic-* ..."
    local containers
    containers="$(docker ps -a --filter "name=traffic-" --format '{{.Names}}')"
    if [ -n "$containers" ]; then
        echo "$containers" | xargs docker rm -f
        echo "==> [OK] Đã dừng toàn bộ camera."
    else
        echo "Không có camera nào đang chạy."
    fi
}

cmd_logs() {
    local target="$1"
    if [ -z "$target" ]; then
        echo "Lỗi: Cần truyền mã camera cần xem log."
        echo "Ví dụ: $0 logs cam_01"
        exit 1
    fi
    local cam_name="$(_extract_cam_name "$target")"
    local container_name="traffic-${cam_name}"
    docker logs -f --tail 100 "$container_name"
}

cmd_status() {
    echo "=================================================================="
    echo " DANH SÁCH CONTAINER CAMERA ĐANG CHẠY"
    echo "=================================================================="
    docker ps -a --filter "name=traffic-" --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}"

    echo ""
    echo "=================================================================="
    echo " KIỂM TRA NHỊP TIM (HEARTBEAT MỚI NHẤT CỦA TỪNG CAMERA)"
    echo "=================================================================="
    local found=0
    for hb in data/heartbeat_*; do
        [ -e "$hb" ] || continue
        found=1
        local fname
        fname="$(basename "$hb")"
        local cam_tag="${fname#heartbeat_}"
        local age_sec
        local now
        now="$(date +%s)"
        local mtime
        mtime="$(stat -c %Y "$hb" 2>/dev/null || stat -f %m "$hb" 2>/dev/null || echo "$now")"
        age_sec=$((now - mtime))
        if [ "$age_sec" -le 30 ]; then
            echo "  [LIVE]  $cam_tag: Heartbeat $age_sec giây trước (Bình thường)"
        else
            echo "  [STALE] $cam_tag: Heartbeat $age_sec giây trước (Cảnh báo mất tín hiệu!)"
        fi
    done
    if [ "$found" -eq 0 ]; then
        echo "  (Chưa có file heartbeat nào trong thư mục data/)"
    fi
    echo "=================================================================="
}

case "$1" in
    build)
        cmd_build
        ;;
    start)
        cmd_start "$2" "$3"
        ;;
    start-all)
        cmd_start_all
        ;;
    stop)
        cmd_stop "$2"
        ;;
    stop-all)
        cmd_stop_all
        ;;
    restart)
        cmd_stop "$2"
        cmd_start "$2" "$3"
        ;;
    logs)
        cmd_logs "$2"
        ;;
    status)
        cmd_status
        ;;
    *)
        echo "HỆ THỐNG QUẢN LÝ & TRIỂN KHAI CAMERA BIÊN (MULTI-CAMERA EDGE DEPLOY)"
        echo ""
        echo "Cách dùng: $0 <lệnh> [tham số]"
        echo ""
        echo "Các lệnh hỗ trợ:"
        echo "  build                      Build Docker image '$IMAGE_NAME' dùng chung"
        echo "  start <config/cam_id> [src] Khởi chạy 1 container camera riêng biệt"
        echo "  start-all                  Khởi chạy tất cả camera có file config trong configs/"
        echo "  stop <config/cam_id>       Dừng 1 camera"
        echo "  stop-all                   Dừng tất cả camera"
        echo "  restart <config/cam_id>    Khởi động lại 1 camera"
        echo "  status                     Xem danh sách container và nhịp tim từng camera"
        echo "  logs <config/cam_id>       Xem log thời gian thực của camera"
        echo ""
        echo "Ví dụ:"
        echo "  $0 start configs/cam_01.yaml"
        echo "  $0 start cam_02 \"rtsp://admin:pass@192.168.1.102:554/stream\""
        echo "  $0 start-all"
        echo "  $0 status"
        exit 1
        ;;
esac

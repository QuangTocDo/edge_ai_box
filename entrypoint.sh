#!/usr/bin/env bash
set -e

# Dam bao moi file va thu muc sinh ra tu container co quyen doc/ghi day du cho host
umask 000
mkdir -p /app/data /app/evidence

# Neu command truyen vao la mot chuong trinh khac (bash, sh, pytest, s3_worker, etc.)
if [ "$#" -gt 0 ] && [ "$1" != "pipeline.py" ] && [[ "$1" != --* ]] && [[ "$1" != *.yaml ]] && [[ "$1" != *.yml ]] && [ ! -f "configs/$1.yaml" ] && [ ! -f "configs/cam_$1.yaml" ] && [ ! -f "configs/cameras/$1.yaml" ] && [ ! -f "configs/cameras/cam_$1.yaml" ] && [ ! -f "/app/configs/$1.yaml" ] && [ ! -f "/app/configs/cam_$1.yaml" ] && [ ! -f "/app/configs/cameras/$1.yaml" ] && [ ! -f "/app/configs/cameras/cam_$1.yaml" ]; then
    if command -v "$1" >/dev/null 2>&1; then
        exec "$@"
    fi
fi

# Neu command bat dau bang "pipeline.py", bo qua tu khoa nay
if [ "$1" = "pipeline.py" ]; then
    shift
fi

# Neu nguoi dung truyen truc tiep cac flags CLI (bat dau bang --)
if [ "$#" -gt 0 ] && [[ "$1" == --* ]]; then
    exec python pipeline.py "$@"
fi

# Xu ly tham so vi tri nhanh:
# Cu phap: entrypoint.sh [config_path_hoac_cam_id] [source_url] [flags_khac...]
CONFIG_POS=""
SOURCE_POS=""

if [ "$#" -gt 0 ]; then
    ARG1="$1"
    if [[ "$ARG1" == *.yaml ]] || [[ "$ARG1" == *.yml ]]; then
        CONFIG_POS="$ARG1"
        shift
    elif [ -f "configs/${ARG1}.yaml" ] || [ -f "/app/configs/${ARG1}.yaml" ] || [ -f "configs/cameras/${ARG1}.yaml" ] || [ -f "/app/configs/cameras/${ARG1}.yaml" ]; then
        if [ -f "configs/cameras/${ARG1}.yaml" ] || [ -f "/app/configs/cameras/${ARG1}.yaml" ]; then
            CONFIG_POS="configs/cameras/${ARG1}.yaml"
        else
            CONFIG_POS="configs/${ARG1}.yaml"
        fi
        shift
    elif [ -f "configs/cam_${ARG1}.yaml" ] || [ -f "/app/configs/cam_${ARG1}.yaml" ] || [ -f "configs/cameras/cam_${ARG1}.yaml" ] || [ -f "/app/configs/cameras/cam_${ARG1}.yaml" ]; then
        if [ -f "configs/cameras/cam_${ARG1}.yaml" ] || [ -f "/app/configs/cameras/cam_${ARG1}.yaml" ]; then
            CONFIG_POS="configs/cameras/cam_${ARG1}.yaml"
        else
            CONFIG_POS="configs/cam_${ARG1}.yaml"
        fi
        shift
    elif [[ "$ARG1" != --* ]]; then
        if [[ "$ARG1" == cam* ]] || [[ "$ARG1" == CAM* ]]; then
            CONFIG_POS="configs/${ARG1}.yaml"
        else
            CONFIG_POS="configs/cam_${ARG1}.yaml"
        fi
        shift
    fi

    # Neu tham so tiep theo la RTSP stream hoac video file (khong bat dau bang --)
    if [ "$#" -gt 0 ] && [[ "$1" != --* ]]; then
        SOURCE_POS="$1"
        shift
    fi
fi

# Uu tien bien CONFIG tren thiet bi bien (Edge Box):
# 1. Tham so vi tri ($1)
# 2. Bien moi truong CONFIG_FILE / CONFIG_PATH
# 3. configs/active.yaml (canonical: draw luu vao day, pipeline doc tu day)
# 4. camera_config.yaml (legacy fallback tai root)
# 5. config.yaml
# 6. Theo CAMERA_ID (configs/cameras/${CAMERA_ID}.yaml -> configs/${CAMERA_ID}.yaml)
# 7. Fallback configs/cameras/cam_01.yaml -> configs/cam_01.yaml
CONFIG="${CONFIG_POS:-${CONFIG_FILE:-${CONFIG_PATH:-}}}"
if [ -z "$CONFIG" ]; then
    if [ -f "configs/active.yaml" ] || [ -f "/app/configs/active.yaml" ]; then
        CONFIG="configs/active.yaml"
    elif [ -f "camera_config.yaml" ] || [ -f "/app/camera_config.yaml" ]; then
        CONFIG="camera_config.yaml"
    elif [ -f "config.yaml" ] || [ -f "/app/config.yaml" ]; then
        CONFIG="config.yaml"
    else
        CID="${CAMERA_ID:-${CAMERA:-}}"
        if [ -n "$CID" ]; then
            if [ -f "configs/cameras/${CID}.yaml" ] || [ -f "/app/configs/cameras/${CID}.yaml" ]; then
                CONFIG="configs/cameras/${CID}.yaml"
            elif [ -f "configs/${CID}.yaml" ] || [ -f "/app/configs/${CID}.yaml" ]; then
                CONFIG="configs/${CID}.yaml"
            elif [ -f "configs/cameras/cam_${CID}.yaml" ] || [ -f "/app/configs/cameras/cam_${CID}.yaml" ]; then
                CONFIG="configs/cameras/cam_${CID}.yaml"
            elif [ -f "configs/cam_${CID}.yaml" ] || [ -f "/app/configs/cam_${CID}.yaml" ]; then
                CONFIG="configs/cam_${CID}.yaml"
            else
                CONFIG="configs/cameras/${CID}.yaml"
            fi
        else
            if [ -f "configs/cameras/cam_01.yaml" ] || [ -f "/app/configs/cameras/cam_01.yaml" ]; then
                CONFIG="configs/cameras/cam_01.yaml"
            else
                CONFIG="configs/cam_01.yaml"
            fi
        fi
    fi
fi

# Trich xuat thong tin tu file config YAML (camera_id, imgsz, source) neu chua co trong env
CFG_FILE="$CONFIG"
[ ! -f "$CFG_FILE" ] && [ -f "/app/$CFG_FILE" ] && CFG_FILE="/app/$CFG_FILE"

if [ -f "$CFG_FILE" ]; then
    CFG_INFO=$(python -c "
import yaml
try:
    with open('$CFG_FILE', 'r', encoding='utf-8') as f:
        d = yaml.safe_load(f) or {}
    cid = d.get('camera_id') or d.get('camera_name') or d.get('name') or ''
    imgsz = d.get('imgsz') or (d.get('model') or {}).get('imgsz') or ''
    src = d.get('source') or ''
    print(f'{cid}|{imgsz}|{src}')
except Exception:
    print('||')
" 2>/dev/null || echo "||")

    IFS="|" read -r PARSED_CAM_ID PARSED_IMGSZ PARSED_SRC <<< "$CFG_INFO"
fi

CAM_NAME="${CAMERA_ID:-${PARSED_CAM_ID:-CAM_01}}"
EFFECTIVE_IMGSZ="${IMGSZ:-${PARSED_IMGSZ:-640}}"

# Uu tien SOURCE: Tham so vi tri > CAM_SOURCE > source trong YAML
SRC="${SOURCE_POS:-${CAM_SOURCE:-${PARSED_SRC:-}}}"

# Tu dong chuan hoa duong dan video neu truyen duong dan tu host
if [ -n "$SRC" ] && [ ! -e "$SRC" ]; then
    if [[ "$SRC" == */assets/* ]] && [ -e "/app/assets/${SRC#*/assets/}" ]; then
        SRC="assets/${SRC#*/assets/}"
    fi
fi

# Tu dong tao HEARTBEAT_FILE theo camera_id tren con bien
if [ -z "$HEARTBEAT_FILE" ]; then
    export HEARTBEAT_FILE="/app/data/heartbeat_${CAM_NAME}"
fi

ARGS=("--config" "$CONFIG" "--no-show")

if [ -n "$SRC" ]; then
    ARGS+=("--source" "$SRC")
fi

if [ -n "$EFFECTIVE_IMGSZ" ] && [ "$EFFECTIVE_IMGSZ" != "0" ]; then
    ARGS+=("--imgsz" "$EFFECTIVE_IMGSZ")
fi

if [ "$DEBUG_RULES" = "true" ] || [ "$DEBUG_RULES" = "1" ]; then
    ARGS+=("--debug-rules")
fi

if [ -n "$MAX_FRAMES" ]; then
    ARGS+=("--max-frames" "$MAX_FRAMES")
fi

if [ -n "$SAVE_VIDEO" ]; then
    ARGS+=("--save" "$SAVE_VIDEO")
fi

# Neu con cac tham so tuy chon CLI khac, truyen them vao
if [ "$#" -gt 0 ]; then
    ARGS+=("$@")
fi

echo "=================================================================="
echo " [TRAFFIC-EDGE] KHOI DONG CON BIEN (STANDALONE EDGE DEVICE)"
echo "  - Config File   : $CONFIG"
echo "  - Camera ID     : $CAM_NAME (tu config / env)"
echo "  - Image Size    : ${EFFECTIVE_IMGSZ}px (tu config / env)"
if [ -n "$SRC" ]; then
    echo "  - Source        : $SRC"
else
    echo "  - Source        : Lay tu config ($CONFIG) hoac env CAM_SOURCE"
fi
echo "  - Heartbeat File: $HEARTBEAT_FILE"
echo "=================================================================="

exec python pipeline.py "${ARGS[@]}"

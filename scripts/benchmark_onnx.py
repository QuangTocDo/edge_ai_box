"""Chay thu nghiem model ONNX tren video mp4 va do FPS.
Chay: python scripts/benchmark_onnx.py [video.mp4] [imgsz]
      python scripts/benchmark_onnx.py assets/red_light1.mp4 640
"""
import sys
import time
from pathlib import Path

import cv2
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent.parent


def run_onnx_demo():
    # File model ONNX va video mac dinh
    onnx_path = str(ROOT / "weights/best_15thg9.onnx")
    pt_path = str(ROOT / "weights/best_15thg9.pt")
    video_path = str(ROOT / "assets/red_light1.mp4")
    imgsz = 640
    device = 0  # 0: GPU (Quadro P2200 qua CUDAExecutionProvider), "cpu": CPU

    # 1. Neu chua co file ONNX, tu dong export tu file .pt
    if not Path(onnx_path).is_file():
        print(f"[*] Dang export {pt_path} sang {onnx_path}...")
        pt_model = YOLO(pt_path)
        pt_model.export(format="onnx", imgsz=imgsz, dynamic=False, simplify=True)
        print("[*] Export ONNX thanh cong!")

    # Xu ly tham so dong lenh
    argv = sys.argv[1:]
    if len(argv) >= 1 and not argv[0].isdigit():
        video_path = argv[0]
    if len(argv) >= 2 and argv[1].isdigit():
        imgsz = int(argv[1])
    elif len(argv) == 1 and argv[0].isdigit():
        imgsz = int(argv[0])

    # 2. Khoi tao model ONNX Runtime
    print(f"[*] Nap model: {onnx_path} (device={device}, imgsz={imgsz})")
    model = YOLO(onnx_path, task="detect")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise SystemExit(f"Khong mo duoc video: {video_path}")

    prev_t = time.perf_counter()
    start_t = prev_t
    count = 0

    print(f"[*] Bat dau chay video: {video_path} (Nhan 'q' de thoat)...")
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        # Inference truc tiep qua ONNX Runtime (CUDAExecutionProvider tren GPU)
        results = model.predict(frame, imgsz=imgsz, device=device, verbose=False)
        annotated = results[0].plot()

        # Do FPS
        now = time.perf_counter()
        fps = 1.0 / (now - prev_t) if now != prev_t else 0.0
        prev_t = now
        count += 1

        cv2.putText(annotated, f"ONNX FPS: {fps:.1f} | GPU: Quadro P2200", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("ONNX Inference", annotated)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    total = time.perf_counter() - start_t
    if total > 0:
        print(f"\n[*] Hoan tat! Frames: {count} | Thoi gian: {total:.1f}s | FPS trung binh: {count/total:.1f}")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_onnx_demo()

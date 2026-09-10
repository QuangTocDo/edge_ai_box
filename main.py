"""YOLO26n + FPS tu file mp4. Chay: python main.py assets/video.mp4"""
import sys
import time

import cv2
from ultralytics import YOLO

VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "assets/video.mp4"

model = YOLO("weights/yolo12n.pt")  # lan dau tu tai ve
cap = cv2.VideoCapture(VIDEO_PATH)
if not cap.isOpened():
    raise SystemExit(f"Khong mo duoc file: {VIDEO_PATH}")

prev_t = time.perf_counter()
start_t = prev_t
count = 0

while True:
    ok, frame = cap.read()
    if not ok or frame is None:
        break  # het video

    results = model.predict(frame, verbose=False)
    frame = results[0].plot()

    # --- do FPS ---
    now = time.perf_counter()
    fps = 1.0 / (now - prev_t) if now != prev_t else 0
    prev_t = now
    count += 1

    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("YOLO26n - mp4", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

total = time.perf_counter() - start_t
print(f"Frames: {count} | Time: {total:.1f}s | Avg FPS: {count/total:.1f}")

cap.release()
cv2.destroyAllWindows()

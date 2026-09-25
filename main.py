"""Main Entrypoint: Khoi dong Edge Traffic Violation Detection Pipeline.

Cach chay:
  python main.py
  python main.py --source assets/video1.mp4
  python main.py --config configs/cameras/cam_01.yaml
  python main.py --help
"""
import sys
from pipeline import main as pipeline_main

if __name__ == "__main__":
    sys.exit(pipeline_main() or 0)
# from ultralytics import YOLO
#
# # Load a model
# model = YOLO("weights/helmet.pt")  # load a custom-trained model
#
# # Export the model
# model.export(format="onnx",dynamic=True, simplify=True)
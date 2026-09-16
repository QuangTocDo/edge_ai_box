"""Main Entrypoint: Khoi dong Edge Traffic Violation Detection Pipeline.

Cach chay:
  python main.py
  python main.py --source assets/video1.mp4
  python main.py --config configs/cam_01.yaml
  python main.py --help
"""
import sys
from pipeline import main as pipeline_main

if __name__ == "__main__":
    sys.exit(pipeline_main() or 0)

from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
JOBS_DIR = DATA_DIR / "jobs"
CAMERAS_DIR = DATA_DIR / "cameras"
CONFIGS_DIR = PROJECT_ROOT / "configs"
EVIDENCE_DIR = PROJECT_ROOT / "evidence"
DATABASE_PATH = DATA_DIR / "dashboard.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
VISION_CONFIG_PATH = CONFIGS_DIR / "active.yaml"
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    CAMERAS_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

"""Hang so tap trung (thay magic numbers rai rac). Rule PARAMS giu nguyen
vi la thong so nguoi dung chinh trong config; day la default ha tang."""

# --- Hinh hoc ---
EPS = 1e-9  # nguong coi nhu 0 cho phep chia / song song

# --- Tracking (src/tracking.py) ---
TRACK_PTS_MAXLEN = 30  # lich su bottom-center giu lai moi track
TRACK_VEL_EMA_ALPHA = 0.6  # giu 60% cu + 40% moi
TRACK_MAX_AGE_FRAMES = 30  # prune track mat dau qua lau
# Chong ID-switch lam lech heading: buoc nhay/frame vuot nguong thi bo qua
TRACK_JUMP_PX_RATIO = 0.08  # nguong = max(MIN, RATIO * imgsz)
TRACK_JUMP_MIN_PX = 50.0  # san duoi tuyet doi, tranh nhay o imgsz nho
TRACK_JUMP_STREAK = 3  # nhay lien tuc >= N frame thi chap nhan la that

# --- Homography (src/homography.py) ---
RANSAC_THRESH = 3.0  # nguong RANSAC cua cv2.findHomography
HOMOGRAPHY_MAX_ERR_M = 0.3  # sai so reproj toi da chap nhan khi load config

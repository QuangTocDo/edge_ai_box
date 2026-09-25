"""ONE-SHOT lich su: da dung de tao data_v1 (KHONG chay lai khi archive da het).
Muon tao version moi thi copy script nay thanh build_data_vX.py va sua SUBSETS/DATA.
"""
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent  # project root (script nam trong scripts/_archive/)
DATA = ROOT / "data"
SEED = 42
SUBSETS = [
    ROOT / "archive/daytime-dataset/daytime",
    ROOT / "archive/nighttime-dataset/nighttime",
]
IMG_EXTS = (".jpg", ".jpeg", ".png")

random.seed(SEED)
for split in ("train", "val", "test"):
    (DATA / "images" / split).mkdir(parents=True, exist_ok=True)
    (DATA / "labels" / split).mkdir(parents=True, exist_ok=True)

total = {"train": 0, "val": 0, "test": 0}

for src in SUBSETS:
    imgs = sorted([p for p in src.iterdir() if p.suffix.lower() in IMG_EXTS])
    if not imgs:
        print(f"Bo qua (rong): {src}")
        continue
    random.shuffle(imgs)
    n = len(imgs)
    n_train, n_val = int(n * 0.8), int(n * 0.1)
    parts = {
        "train": imgs[:n_train],
        "val": imgs[n_train:n_train + n_val],
        "test": imgs[n_train + n_val:],
    }
    for split, files in parts.items():
        moved_txt = 0
        for img in files:
            shutil.move(str(img), str(DATA / "images" / split / img.name))
            txt = img.with_suffix(".txt")
            if txt.exists():  # anh le khong txt -> lam background
                shutil.move(str(txt), str(DATA / "labels" / split / txt.name))
                moved_txt += 1
        total[split] += len(files)
        print(f"[{src.name}] {split}: {len(files)} anh (+{moved_txt} txt)")

(DATA / "data.yaml").write_text(
    f"path: {DATA.resolve()}\n"
    "train: images/train\nval: images/val\ntest: images/test\n"
    "nc: 8\nnames: ['class 0', 'class 1', 'class 2', 'class 3', "
    "'class 4', 'class 5', 'class 6', 'class 7']\n"
)
print("Tong:", total, "-> data/data.yaml OK")

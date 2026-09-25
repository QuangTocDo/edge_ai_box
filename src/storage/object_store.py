"""Object store: 1 record/track cho truy van nhanh (date + type + color).

G1: ghi ngay khi ID moi (crop + mau co the unknown).
G2: thay the toi da 3 lan khi ro rang tot hon (area>=1.5x hoac conf+0.15).
G3: finalize khi track prune (last_seen, duration, low_quality).
DB: SQLite 1 file, index (date, vehicle_type, color). Prune theo retention.
"""
import sqlite3
import time
from pathlib import Path

import cv2

from ..utils.color import dominant_color_robust, frame_gains

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    track_id INTEGER,
    camera_id TEXT,
    date TEXT,
    run_id TEXT DEFAULT '',
    vehicle_type TEXT,
    color TEXT,
    color_conf REAL,
    best_conf REAL,
    best_bbox TEXT,
    crop_path TEXT,
    first_seen REAL,
    last_seen REAL,
    frames INTEGER DEFAULT 1,
    rewrites INTEGER DEFAULT 0,
    low_quality INTEGER DEFAULT 0,
    PRIMARY KEY (track_id, camera_id, date, run_id)
);
CREATE INDEX IF NOT EXISTS idx_objects_query
    ON objects (date, vehicle_type, color);
CREATE INDEX IF NOT EXISTS idx_objects_track
    ON objects (track_id, camera_id);
"""

# class id YOLO (day/night + pedestrian id 8).
VEHICLE_TYPE = {0: "motorbike", 1: "car", 2: "bus", 3: "truck",
                4: "motorbike", 5: "car", 6: "bus", 7: "truck",
                8: "pedestrian"}

AREA_REPLACE_FACTOR = 1.5
CONF_REPLACE_DELTA = 0.15
MAX_REWRITES = 3
MIN_CONF = 0.75  # best_conf duoi nguong nay -> xoa han luc finalize
MIN_AREA_PX = 64 * 64
MIN_DURATION_S = 1.0
CROP_PAD = 0.0  # khong margin: crop khit bbox de mau HSV dung vung than xe
CROP_QUALITY = 90


def vehicle_type_of(cls):
    try:
        return VEHICLE_TYPE.get(int(cls), "unknown")
    except (TypeError, ValueError):
        return "unknown"


class ObjectStore:
    """DB + crop nam gon trong var/ ( tranh bi don nham voi code).
    db: var/objects.db | crop: var/objects/<ngay>/<run>/."""

    def __init__(self, db_path="var/objects.db", crop_root="var/objects",
                 retention_days=7, run_id=""):
        self.db_path = str(db_path)
        self.crop_root = Path(crop_root)
        self.retention_days = retention_days
        self.run_id = run_id or ""
        self._db = sqlite3.connect(self.db_path)
        self._migrate()
        self._db.executescript(SCHEMA)
        self._db.execute("PRAGMA journal_mode=WAL")
        self.crop_root.mkdir(parents=True, exist_ok=True)

    def _migrate(self):
        """DB cu (PK thieu run_id -> cac lan chay de record lan nhau):
        dung lai bang moi co PK (track_id, camera_id, date, run_id),
        du lieu cu gan run_id='pre-runs'."""
        try:
            cols = [r[1] for r in self._db.execute("PRAGMA table_info(objects)")]
        except Exception:
            return
        if not cols:
            return
        if "run_id" in cols:
            return
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS objects_new (
                track_id INTEGER, camera_id TEXT, date TEXT,
                run_id TEXT DEFAULT '', vehicle_type TEXT, color TEXT,
                color_conf REAL, best_conf REAL, best_bbox TEXT,
                crop_path TEXT, first_seen REAL, last_seen REAL,
                frames INTEGER DEFAULT 1, rewrites INTEGER DEFAULT 0,
                low_quality INTEGER DEFAULT 0,
                PRIMARY KEY (track_id, camera_id, date, run_id));
            INSERT INTO objects_new
                (track_id, camera_id, date, run_id, vehicle_type, color,
                 color_conf, best_conf, best_bbox, crop_path, first_seen,
                 last_seen, frames, rewrites, low_quality)
                SELECT track_id, camera_id, date, 'pre-runs', vehicle_type,
                 color, color_conf, best_conf, best_bbox, crop_path,
                 first_seen, last_seen, frames, rewrites, low_quality
                FROM objects;
            DROP TABLE objects;
            ALTER TABLE objects_new RENAME TO objects;
        """)
        self._db.commit()

    def _crop_and_save(self, frame, bbox, date, tid, rev):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [float(v) for v in bbox]
        bw, bh = x2 - x1, y2 - y1
        x1 = max(0, int(x1 - bw * CROP_PAD))
        y1 = max(0, int(y1 - bh * CROP_PAD))
        x2 = min(w, int(x2 + bw * CROP_PAD))
        y2 = min(h, int(y2 + bh * CROP_PAD))
        if x2 <= x1 or y2 <= y1:
            return None, 0, None
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None, 0, None
        runshort = (self.run_id or "local")[:8]
        out = self.crop_root / str(date) / runshort / f"{tid}_{rev}.jpg"
        out.parent.mkdir(parents=True, exist_ok=True)
        ok = cv2.imwrite(str(out), crop,
                         [cv2.IMWRITE_JPEG_QUALITY, CROP_QUALITY])
        if not ok:
            return None, 0, None
        area = (x2 - x1) * (y2 - y1)
        return str(out), area, crop

    def _where_run(self):
        return "track_id=? AND camera_id=? AND date=? AND run_id=?"

    def _row(self, tid, camera_id, date):
        cur = self._db.execute(
            "SELECT best_conf, best_bbox, rewrites FROM objects "
            f"WHERE {self._where_run()}",
            (tid, camera_id, date, self.run_id))
        return cur.fetchone()

    def _frame_gains(self, frame, t, ttl_s=1.0):
        """Gain can bang uoc tu full frame, cache ~1s (tinh 1 lan/giay)."""
        try:
            last = getattr(self, "_gains_t", -1e9)
            if t - last > ttl_s:
                self._gains = frame_gains(frame)
                self._gains_t = float(t)
            return getattr(self, "_gains", None)
        except Exception:
            return None

    def observe(self, tid, cls, conf, bbox, frame, camera_id, date, t):
        """G1/G2: ghi moi hoac thay the khi tot hon. Tra ve True neu co ghi."""
        try:
            conf = float(conf)
            area_now = max(0.0, (float(bbox[2]) - float(bbox[0])) *
                           (float(bbox[3]) - float(bbox[1])))
        except (TypeError, IndexError, ValueError):
            return False
        row = self._row(tid, camera_id, date)
        if row is None:
            # G1: ID moi -> chi ghi khi du chuan conf ngay tu dau.
            # Track yeu khong ton imwrite/HSV/INSERT; doi frame sau dat
            # chuan thi G1 bat dau tu do (G2 bu lai shot tot hon).
            if conf < MIN_CONF:
                return False
            crop_path, _, crop_img = self._crop_and_save(frame, bbox, date, tid, 0)
            color, cconf, _ = dominant_color_robust(
                crop_img, bbox,
                self._frame_gains(frame, t))
            self._db.execute(
                "INSERT INTO objects (track_id, camera_id, date, run_id, vehicle_type,"
                " color, color_conf, best_conf, best_bbox, crop_path,"
                " first_seen, last_seen, frames, rewrites) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (tid, camera_id, date, self.run_id, vehicle_type_of(cls), color, cconf,
                 conf, ",".join(str(v) for v in bbox), crop_path or "",
                 t, t, 1, 0))
            return True
        best_conf, best_bbox, rewrites = row
        if rewrites >= MAX_REWRITES:
            self._db.execute(
                "UPDATE objects SET last_seen=?, frames=frames+1 "
                f"WHERE {self._where_run()}",
                (t, tid, camera_id, date, self.run_id))
            return False
        try:
            old = [float(v) for v in str(best_bbox).split(",")]
            area_old = max(0.0, (old[2] - old[0]) * (old[3] - old[1]))
        except (ValueError, IndexError):
            area_old = 0.0
        # G2: chi thay khi ro rang tot hon VA dat chuan conf
        # (tranh ha best_conf xuong duoi nguong bang shot to nhung mo).
        if conf < MIN_CONF or not (
                area_now >= area_old * AREA_REPLACE_FACTOR
                or conf >= float(best_conf) + CONF_REPLACE_DELTA):
            self._db.execute(
                "UPDATE objects SET last_seen=?, frames=frames+1 "
                f"WHERE {self._where_run()}",
                (t, tid, camera_id, date, self.run_id))
            return False
        rev = int(rewrites) + 1
        crop_path, _, crop_img = self._crop_and_save(frame, bbox, date, tid, rev)
        if crop_path is None or crop_img is None:
            return False
        color, cconf, _ = dominant_color_robust(
            crop_img, bbox, self._frame_gains(frame, t))
        self._db.execute(
            "UPDATE objects SET best_conf=?, best_bbox=?, crop_path=?,"
            " color=?, color_conf=?, last_seen=?, frames=frames+1,"
            f" rewrites=? WHERE {self._where_run()}",
            (conf, ",".join(str(v) for v in bbox), crop_path, color,
             cconf, t, rev, tid, camera_id, date, self.run_id))
        return True

    def finalize(self, tid, camera_id, date, t):
        """G3: chot last_seen/duration; XOA HAN record co best_conf < MIN_CONF
        (ke ca file crop); danh low_quality neu qua ngan/nho."""
        cur = self._db.execute(
            "SELECT first_seen, best_bbox, best_conf, crop_path FROM objects "
            f"WHERE {self._where_run()}",
            (tid, camera_id, date, self.run_id))
        row = cur.fetchone()
        if row is None:
            return
        first_seen, best_bbox, best_conf, crop_path = row
        try:
            if float(best_conf or 0.0) < MIN_CONF:
                self._db.execute(
                    f"DELETE FROM objects WHERE {self._where_run()}",
                    (tid, camera_id, date, self.run_id))
                try:
                    if crop_path:
                        Path(crop_path).unlink(missing_ok=True)
                except OSError:
                    pass
                return
        except (TypeError, ValueError):
            pass
        try:
            old = [float(v) for v in str(best_bbox).split(",")]
            area = max(0.0, (old[2] - old[0]) * (old[3] - old[1]))
        except (ValueError, IndexError):
            area = 0.0
        duration = max(0.0, float(t) - float(first_seen or t))
        low = 1 if (duration < MIN_DURATION_S and area < MIN_AREA_PX) else 0
        self._db.execute(
            "UPDATE objects SET last_seen=?, low_quality=? "
            f"WHERE {self._where_run()}",
            (t, low, tid, camera_id, date, self.run_id))

    def query(self, date="", vehicle_type="", color="", camera_id="",
              run_id="", include_low_quality=False, limit=200):
        """Truy van nhanh theo index (date, vehicle_type, color).
        Luon loc cung best_conf >= MIN_CONF (quy tac, ke ca include_low).
        run_id='' = moi lan chay (mac dinh, dung cho UI theo ngay)."""
        conds: list = ["best_conf>=?"]
        params: list = [MIN_CONF]
        if date:
            conds.append("date=?")
            params.append(date)
        if run_id:
            conds.append("run_id=?")
            params.append(run_id)
        if vehicle_type:
            conds.append("vehicle_type=?")
            params.append(vehicle_type)
        if color:
            conds.append("color=?")
            params.append(color)
        if camera_id:
            conds.append("camera_id=?")
            params.append(camera_id)
        if not include_low_quality:
            conds.append("low_quality=0")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        cur = self._db.execute(
            "SELECT track_id, camera_id, date, run_id, vehicle_type, color,"
            " color_conf, best_conf, best_bbox, crop_path, first_seen,"
            " last_seen, frames FROM objects "
            f"{where} ORDER BY first_seen LIMIT ?", (*params, int(limit)))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def prune(self, retention_days=None):
        """Xoa record + crop qua han (gi resolutions theo ngay)."""
        days = retention_days if retention_days is not None else self.retention_days
        cutoff = time.time() - days * 86400
        cur = self._db.execute(
            "SELECT crop_path FROM objects WHERE last_seen < ?", (cutoff,))
        for (p,) in cur.fetchall():
            try:
                if p:
                    Path(p).unlink(missing_ok=True)
            except OSError:
                pass
        cur = self._db.execute("DELETE FROM objects WHERE last_seen < ?",
                               (cutoff,))
        self._db.commit()
        return cur.rowcount

    def flush(self, force=False, interval_s=5.0):
        """Commit don. Mac dinh chi commit khi qua interval_s ke tu lan
        truoc (tranh fsync moi frame ~30ms). force=True khi shutdown."""
        try:
            now = time.time()
            if not force and now - getattr(self, "_last_commit", 0.0) < interval_s:
                return
            self._db.commit()
            self._last_commit = now
        except Exception:
            pass

    def close(self):
        try:
            self._db.commit()
            self._db.close()
        except Exception:
            pass

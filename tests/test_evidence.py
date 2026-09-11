"""Test evidence theo ngay: date dirs, filename time, prune.
Chay: python -m tests.test_evidence
"""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from src.evidence import prune_old_dates, save_event, save_triptych


def _frame(h=120, w=160):
    return np.zeros((h, w, 3), dtype=np.uint8)


def _event(vtype="speeding"):
    return {"type": vtype, "track_id": 1, "cls": 1, "conf": 0.9,
            "bbox": [10, 10, 50, 60], "bc": (30, 60),
            "frame_idx": 10, "line_id": "speed", "extra": {}}


def _dt(day, h=10, m=5, s=7, ms=123):
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Ho_Chi_Minh")
    except Exception:
        tz = timezone(timedelta(hours=7))
    return datetime(2026, 9, day, h, m, s, ms * 1000, tzinfo=tz)


def test_save_event_daily_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        jp1, js1 = save_event(_frame(), _event(), [], ["c"] * 8,
                              out_dir=tmp, camera_id="CAM1",
                              event_time=_dt(10, 10, 5, 7))
        jp2, _ = save_event(_frame(), _event(), [], ["c"] * 8,
                             out_dir=tmp, camera_id="CAM1",
                             event_time=_dt(11, 23, 0, 0))
        p1, p2 = Path(jp1), Path(jp2)
        assert "date=2026-09-10" in str(p1), p1
        assert "date=2026-09-11" in str(p2), p2
        assert p1.parent == Path(tmp) / "CAM1" / "date=2026-09-10" / "speeding"
        assert p1.stem.startswith("100507_123_"), p1.stem
        meta = json.loads(Path(js1).read_text())
        assert meta["date"] == "2026-09-10"
        assert "+07:00" in meta["timestamp"], meta["timestamp"]
        assert len(meta["event_id"]) == 8
        print("daily dirs OK")


def test_filename_sorts_by_time():
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for s in (5, 15, 25):
            jp, _ = save_event(_frame(), _event(), [], ["c"] * 8,
                                out_dir=tmp, camera_id="C",
                                event_time=_dt(10, 9, 0, s))
            names.append(Path(jp).name)
        assert names == sorted(names), names
        print("filename sort OK")


def test_triptych_daily():
    with tempfile.TemporaryDirectory() as tmp:
        fr = [_frame(), _frame(), _frame()]
        jp, js = save_triptych(fr, _frame(), _event("red_light_running"), [],
                                ["c"] * 8, out_dir=tmp, camera_id="CAM1",
                                event_time=_dt(10))
        assert "date=2026-09-10" in jp and jp.endswith("_triptych.jpg"), jp
        meta = json.loads(Path(js).read_text())
        assert meta["date"] == "2026-09-10"
        print("triptych daily OK")


def test_prune_old_dates():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "CAM1"
        today = datetime.now().date()
        old = (today - timedelta(days=10)).strftime("date=%Y-%m-%d")
        keep = (today - timedelta(days=2)).strftime("date=%Y-%m-%d")
        (base / old / "speeding").mkdir(parents=True)
        (base / keep / "speeding").mkdir(parents=True)
        (base / "date=bad-name" / "speeding").mkdir(parents=True)
        (base / old / "speeding" / "x.jpg").write_text("x")
        removed = prune_old_dates(base, 7)
        assert not (base / old).exists(), removed
        assert (base / keep).exists()
        assert (base / "date=bad-name").exists()  # ten la -> giu
        assert any(old in r for r in removed), removed
        print("prune OK")


def test_prune_invalid():
    assert prune_old_dates("/nope", 7) == []
    assert prune_old_dates("/nope", 0) == []
    print("prune invalid OK")


if __name__ == "__main__":
    test_save_event_daily_dirs()
    test_filename_sorts_by_time()
    test_triptych_daily()
    test_prune_old_dates()
    test_prune_invalid()
    print("ALL EVIDENCE TESTS PASSED")

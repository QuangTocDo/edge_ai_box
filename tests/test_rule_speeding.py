"""Test rule do toc do (headless, H tong hop scale deu 10px = 1m).
Chay tu project root: python -m tests.test_rule_speeding
"""
import numpy as np

from src.homography import build_H
from src.rules import SpeedingRule
from src.tracking import TrackState

FPS = 30.0
H, _, _ = build_H([[0, 0], [100, 0], [100, 100], [0, 100]],
                  [[0, 0], [10, 0], [10, 10], [0, 10]])
ROAD = [1.0, 0.0]
BBOX = [0, 0, 40, 60]  # cao 60px > min default


def drive(pts, rule, frame=None, bbox=BBOX, start_hits=25):
    """Gia lap track di qua cac diem pts (pixel). Tra ve (evs, st)."""
    st = TrackState(1, 2, 0.9, pts[0])
    st.hits = start_hits
    st.bbox = bbox
    evs = []
    for i in range(1, len(pts)):
        st.update(2, 0.9, pts[i], bbox, i)
        e = rule.update(st, H, ROAD, 0.0, frame, i, i / FPS)
        if e:
            evs.append(e)
    return evs, st


def test_speeding_trigger():
    # 5px/frame @30fps, 10px=1m -> 15 m/s = 54 km/h > limit 50
    rule = SpeedingRule(limit_kmh=50.0, min_track_frames=5, sustain_s=0.5)
    pts = [(10 + 5 * i, 100) for i in range(80)]
    evs, st = drive(pts, rule)
    assert len(evs) == 1 and evs[0]["type"] == "speeding", evs
    ex = evs[0]["extra"]
    assert abs(ex["speed_kmh"] - 54.0) < 3.0, ex
    assert ex["speed_limit_kmh"] == 50.0
    assert 0.0 <= ex["confidence"] <= 1.0
    print("speeding trigger OK:", ex["speed_kmh"])


def test_under_limit_silent():
    # 2px/frame -> 6 m/s = 21.6 km/h < 50
    rule = SpeedingRule(limit_kmh=50.0, min_track_frames=5, sustain_s=0.5)
    pts = [(10 + 2 * i, 100) for i in range(80)]
    evs, _ = drive(pts, rule)
    assert evs == [], evs
    print("under-limit silent OK")


def test_lateral_move_ignored():
    # Chi di ngang (doc road_dir Y): toc do doc ~0
    rule = SpeedingRule(limit_kmh=50.0, min_track_frames=5, sustain_s=0.5)
    pts = [(100, 10 + 5 * i) for i in range(80)]
    evs, _ = drive(pts, rule)
    assert evs == [], evs
    print("lateral ignored OK")


def test_jump_rejected():
    # Truoc/sau jump deu duoi limit (2px/frame ~ 21.6 km/h).
    # Chi spike jump moi co the bao -> phai im lang + reset lich su.
    rule = SpeedingRule(limit_kmh=50.0, min_track_frames=5, sustain_s=0.5)
    pts = [(10 + 2 * i, 100) for i in range(10)]
    pts += [(900, 100)]  # jump ~880px/frame ~ 10560 km/h
    pts += [(900 + 2 * i, 100) for i in range(1, 41)]
    evs, st = drive(pts, rule)
    assert evs == [], evs
    assert len(st.speed["hist"]) <= 41  # lich su bi reset o frame jump
    print("jump rejected OK")


def test_small_bbox_skipped():
    rule = SpeedingRule(limit_kmh=50.0, min_track_frames=5, sustain_s=0.5,
                        min_bbox_height=100.0)
    pts = [(10 + 5 * i, 100) for i in range(80)]
    evs, _ = drive(pts, rule, bbox=[0, 0, 40, 60])
    assert evs == [], evs
    print("small-bbox skipped OK")


def test_shake_skipped():
    # Frame dich 5px (gia rung) -> bo qua update
    rule = SpeedingRule(limit_kmh=50.0, min_track_frames=5, sustain_s=5,
                        max_background_shift_px=2.0)
    base = np.zeros((120, 160), dtype=np.uint8)
    for y in range(10, 120, 20):
        for x in range(10, 160, 20):
            base[y - 3:y + 3, x - 3:x + 3] = 255
    M = np.float32([[1, 0, 5], [0, 1, 0]])
    moved = cv2_warp(base, M)
    pts = [(10 + 5 * i, 100) for i in range(60)]
    st = TrackState(1, 2, 0.9, pts[0])
    st.hits = 25
    st.bbox = BBOX
    shaken = 0
    for i in range(1, len(pts)):
        st.update(2, 0.9, pts[i], BBOX, i)
        fr = moved if i % 2 == 0 else base
        import cv2
        fr = cv2.cvtColor(fr, cv2.COLOR_GRAY2BGR)
        e = rule.update(st, H, ROAD, 0.0, fr, i, i / FPS)
        assert e is None
        shaken += 1 if st.speed.get("skipped_shake") else 0
    assert shaken > 0, "LK phai phat hien rung 5px"
    print(f"shake skipped OK ({shaken} frames)")


def cv2_warp(img, M):
    import cv2
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]))


def test_explain_branches():
    rule = SpeedingRule(limit_kmh=50.0, min_track_frames=20)
    st = TrackState(1, 2, 0.9, (10, 100))
    assert "track moi" in rule.explain(st, t=1.0)
    st.hits = 25
    st.bbox = BBOX
    for i in range(1, 10):
        st.update(2, 0.9, (10 + 5 * i, 100), BBOX, i)
        rule.update(st, H, ROAD, 0.0, None, i, i / FPS)
    msg = rule.explain(st, t=1.0)
    assert "kmh" in msg, msg
    print("explain OK:", msg)


if __name__ == "__main__":
    test_speeding_trigger()
    test_under_limit_silent()
    test_lateral_move_ignored()
    test_jump_rejected()
    test_small_bbox_skipped()
    test_shake_skipped()
    test_explain_branches()
    print("ALL SPEEDING TESTS PASSED")

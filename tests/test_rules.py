"""Unit test Rule Engine bang track gia lap (khong can model/video).
Chay tu project root: python -m tests.test_rules
"""
from src.geometry import allowed_vec, crossing_sign
from src.rules import NoUTurnRule, WrongWayRule
from src.tracking import TrackState

FPS = 30.0


def drive(rule_lines, pts, rule, pairs=None, min_hits=3):
    """Gia lap track di qua cac diem pts, tra ve list events."""
    st = TrackState(1, 2, 0.9, pts[0])
    st.hits = min_hits
    evs = []
    for i in range(1, len(pts)):
        st.update(2, 0.9, pts[i], [0, 0, 10, 10], i)
        t = i / FPS
        if pairs is None:
            e = rule.update(st, rule_lines, i, t)
        else:
            e = rule.update(st, rule_lines, pairs, i, t)
        if e:
            evs.append(e)
    return evs


def test_crossing_sign():
    line = ((0, 100), (200, 100))
    assert crossing_sign((100, 80), (100, 120), *line) == 1   # xuong
    assert crossing_sign((100, 120), (100, 80), *line) == -1  # len
    assert crossing_sign((10, 50), (50, 50), *line) == 0       # song song
    # allowed_vec phai nhat quan voi dau cat
    av = allowed_vec((0, 100), (200, 100), 1)
    assert av[1] > 0, av  # sign +1 <-> huong xuong
    print("crossing_sign OK")


def test_wrong_way_trigger():
    lines = [{"id": "L", "p1": [0, 100], "p2": [200, 100], "allowed_sign": -1}]
    rule = WrongWayRule(min_hits=3, min_reverse_frames=5, min_reverse_px=1e9)
    pts = [(100, 80 + 10 * i) for i in range(8)]  # di xuong = nguoc
    evs = drive(lines, pts, rule)
    assert len(evs) == 1 and evs[0]["type"] == "wrong_way", evs
    assert evs[0]["extra"]["reverse_frames"] >= 5
    print("wrong_way trigger OK:", evs[0]["extra"])


def test_wrong_way_compliant():
    lines = [{"id": "L", "p1": [0, 100], "p2": [200, 100], "allowed_sign": 1}]
    rule = WrongWayRule(min_hits=3, min_reverse_frames=5, min_reverse_px=1e9)
    pts = [(100, 80 + 10 * i) for i in range(8)]  # di xuong = dung chieu
    assert drive(lines, pts, rule) == []
    print("wrong_way compliant OK")


def test_wrong_way_swerve_reset():
    lines = [{"id": "L", "p1": [0, 100], "p2": [200, 100], "allowed_sign": -1}]
    rule = WrongWayRule(min_hits=3, min_reverse_frames=5, min_reverse_px=1e9)
    pts = [(100, 80), (100, 90), (100, 100), (100, 110),
           (100, 100), (100, 90)]  # cham vach roi quay lai
    assert drive(lines, pts, rule) == []
    print("wrong_way swerve-reset OK")


def uturn_lines():
    return [
        {"id": "L_NB", "p1": [0, 200], "p2": [200, 200], "allowed_sign": 1},
        {"id": "L_SB", "p1": [0, 400], "p2": [200, 400], "allowed_sign": -1},
        {"id": "L_med", "p1": [300, 150], "p2": [300, 450], "role": "divider"},
    ]


def uturn_path(with_medial=True, invert=True):
    """Xuong qua NB -> (quanh qua x=350 neu with_medial) -> len qua SB."""
    pts = [(100, 150 + 10 * i) for i in range(8)]      # 150..220, cat NB
    pts += [(100, 230 + 20 * i) for i in range(1, 12)]  # ..450
    mid = [(130 + 20 * i, 450) for i in range(1, 12)] if with_medial \
        else [(100, 450)] * 11                          # quanh (cat medial x=300)
    pts += mid
    start_x = 350 if with_medial else 100  # khong medial -> o yen x=100
    pts += [(start_x - 25 * i, 450) for i in range(1, 11) if start_x - 25 * i >= 100]
    pts += [(100, 450)] * 3
    up = (430 - 20 * i for i in range(1, 8))            # len dan
    pts += [(100, y) for y in up]
    if not invert:  # gia ID-switch: van di xuong sau khi "cat" SB
        pts = [(x, 450 + 5 * i) for i, (x, _) in enumerate(pts[-7:])]
        base = uturn_path(True, True)[:len(uturn_path(True, True)) - 7]
        return base + pts
    return pts


def test_uturn_trigger():
    rule = NoUTurnRule(time_window_s=(0.1, 12.0))
    pairs = [{"first": "L_NB", "second": "L_SB", "medial": "L_med"}]
    evs = drive(uturn_lines(), uturn_path(True, True), rule, pairs)
    assert len(evs) == 1 and evs[0]["type"] == "no_uturn", evs
    print("no_uturn trigger OK:", evs[0]["extra"])


def test_uturn_no_medial():
    rule = NoUTurnRule(time_window_s=(0.1, 12.0))
    pairs = [{"first": "L_NB", "second": "L_SB", "medial": "L_med"}]
    assert drive(uturn_lines(), uturn_path(False, True), rule, pairs) == []
    print("no_uturn no-medial-reject OK")


def test_uturn_idswitch():
    rule = NoUTurnRule(time_window_s=(0.1, 12.0))
    pairs = [{"first": "L_NB", "second": "L_SB", "medial": "L_med"}]
    assert drive(uturn_lines(), uturn_path(True, False), rule, pairs) == []
    print("no_uturn id-switch-reject OK")


if __name__ == "__main__":
    test_crossing_sign()
    test_wrong_way_trigger()
    test_wrong_way_compliant()
    test_wrong_way_swerve_reset()
    test_uturn_trigger()
    test_uturn_no_medial()
    test_uturn_idswitch()
    print("ALL RULE TESTS PASSED")

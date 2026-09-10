"""Test rule di nguoc chieu.
Chay tu project root: python -m tests.test_rule_wrong_way
"""
from tests._helpers import drive
from src.rules import WrongWayRule
from src.tracking import TrackState
from src.tracking import TrackState


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


def test_wrong_way_explain():
    rule = WrongWayRule(min_hits=3, min_reverse_frames=5, min_reverse_px=60.0)
    st = TrackState(1, 2, 0.9, (100, 80))
    st.update(2, 0.9, (100, 90), [0, 0, 10, 10], 1)
    assert "track moi" in rule.explain(st, t=1.0)  # hits=2<3
    st.hits = 5
    st.reverse["L"] = [3, 42.0]
    msg = rule.explain(st, t=1.0)
    assert "dang nguoc 3/5f" in msg and "L" in msg, msg
    st.reverse.clear()
    st.cooldowns["wrong_way"] = 6.0
    assert "cooldown" in rule.explain(st, t=1.0)
    print("wrong_way explain OK")


if __name__ == "__main__":
    test_wrong_way_trigger()
    test_wrong_way_compliant()
    test_wrong_way_swerve_reset()
    test_wrong_way_explain()
    print("ALL WRONG-WAY TESTS PASSED")

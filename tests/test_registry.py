"""Test registry: anh xa ten -> class, loc key la, dispatch run().
Chay tu project root: python -m tests.test_registry
"""
from src.rules import (NoEntryRule, NoUTurnRule, RedLightRunningRule,
                       SpeedingRule, StopLineRule, WrongWayRule, create,
                       known_types)
from src.tracking import TrackState
from tests._helpers import FPS, drive


def test_known_types():
    assert set(known_types()) == {
        "wrong_way", "no_uturn", "no_entry_road",
        "red_light_running", "stop_line_violation", "speeding",
    }
    print("known_types OK")


def test_create_filters_unknown_keys():
    # key cu da bo (vd time_window_s) khong duoc gay crash
    r = create("no_uturn", {"time_window_s": [1, 2], "min_hits": 5})
    assert isinstance(r, NoUTurnRule) and r.min_hits == 5
    r = create("wrong_way", {})
    assert isinstance(r, WrongWayRule) and r.min_hits == 3
    r = create("no_entry_road", {"dwell_s": 1.5})
    assert isinstance(r, NoEntryRule) and r.dwell_s == 1.5
    r = create("red_light_running", {"dilemma_grace_ms": 600, "unknown_key": 123})
    assert isinstance(r, RedLightRunningRule) and r.dilemma_grace_s == 0.6
    r = create("stop_line_violation", {"stop_dwell_s": 2.5, "unknown_param": "foo"})
    assert isinstance(r, StopLineRule) and r.stop_dwell_s == 2.5
    r = create("speeding", {"limit_kmh": 60, "bogus_key": 1})
    assert isinstance(r, SpeedingRule) and r.limit == 60.0
    print("create OK (loc key la + default)")


def test_create_unknown_name():
    try:
        create("wrong_way_xxx", {})
        raise AssertionError("ten la phai loi")
    except KeyError as e:
        assert "wrong_way" in str(e)
    print("unknown name KeyError OK")


def test_run_dispatch():
    # wrong_way qua run()
    entry = {"rule": "wrong_way", "polygon": None,
             "lines": [{"id": "L", "p1": [0, 100], "p2": [200, 100],
                        "allowed_sign": -1}],
             "pairs": []}
    rule = create("wrong_way",
                  {"min_hits": 3, "min_reverse_frames": 5,
                   "min_reverse_px": 1e9})
    st = TrackState(1, 2, 0.9, (100, 80))
    st.hits = 3
    e = None
    for i in range(1, 8):
        st.update(2, 0.9, (100, 80 + 10 * i), [0, 0, 10, 10], i)
        e = rule.run(entry, st, i, i / FPS)
        if e:
            break
    assert e is not None and e["type"] == "wrong_way", e
    # no_uturn qua run()
    entry2 = {"rule": "no_uturn", "polygon": None,
              "lines": [
                  {"id": "A", "p1": [0, 100], "p2": [200, 100],
                   "allowed_sign": 1},
                  {"id": "B", "p1": [0, 150], "p2": [200, 150],
                   "allowed_sign": -1}],
              "pairs": [{"first": "A", "second": "B"}]}
    rule2 = create("no_uturn", {})
    st2 = TrackState(2, 2, 0.9, (100, 80))
    st2.hits = 3
    e2 = None
    pts = [(100, 80 + 5 * i) for i in range(8)]       # xuong qua A
    pts += [(100, 120 + 5 * i) for i in range(1, 10)]  # tiep (qua B xuong=nguoc?)
    for i in range(1, len(pts)):
        st2.update(2, 0.9, pts[i], [0, 0, 10, 10], i)
        e2 = rule2.run(entry2, st2, i, i / FPS)
        if e2:
            break
    # di xuong qua A dung chieu; de trigger can quay len qua B:
    if e2 is None:
        pts3 = [(100, 165 - 5 * i) for i in range(1, 8)]  # quay len qua B
        base = len(pts)
        for j in range(1, len(pts3)):
            i = base + j
            st2.update(2, 0.9, pts3[j], [0, 0, 10, 10], i)
            e2 = rule2.run(entry2, st2, i, i / FPS)
            if e2:
                break
    assert e2 is not None and e2["type"] == "no_uturn", e2
    # no_entry qua run()
    entry3 = {"rule": "no_entry_road",
              "polygon": {"id": "Z", "polygon": [[0, 0], [200, 0],
                                                 [200, 200], [0, 200]],
                          "banned_classes": [2], "dwell_s": 0.1,
                          "active_hours": []},
              "lines": [], "pairs": []}
    rule3 = create("no_entry_road", {})
    st3 = TrackState(3, 2, 0.9, (100, 150))
    st3.hits = 5
    e3 = None
    for i in range(1, 10):  # dung yen trong zone 0.3s >= dwell 0.1s
        st3.update(2, 0.9, (100, 150), [0, 0, 10, 10], i)
        e3 = rule3.run(entry3, st3, i, i / FPS, wall_min=1200)
        if e3:
            break
    assert e3 is not None and e3["type"] == "no_entry_road", e3

    # red_light_running qua run()
    entry4 = {"rule": "red_light_running", "polygon": None,
              "lines": [{"id": "L_STOP", "p1": [0, 100], "p2": [200, 100],
                         "allowed_sign": 1, "signal_id": "SIG_1"}],
              "pairs": [],
              "clearance": [{"id": "CLR", "polygon": [[0, 150], [200, 150],
                                                      [200, 300], [0, 300]]}]}
    rule4 = create("red_light_running", {"dilemma_grace_s": 0.0})
    st4 = TrackState(4, 2, 0.9, (100, 80))
    st4.hits = 3
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}
    e4 = None
    # Di tu y=80 qua vach y=100 toi clearance y=160
    for idx, y in enumerate([80, 90, 110, 130, 160], start=1):
        st4.update(2, 0.9, (100, y), [90, y - 20, 110, y], idx)
        e4 = rule4.run(entry4, st4, idx, idx / FPS, signals=sigs)
        if e4:
            break
    assert e4 is not None and e4["type"] == "red_light_running", e4

    # stop_line_violation qua run()
    entry5 = {"rule": "stop_line_violation", "polygon": None,
              "lines": [{"id": "L_STOP", "p1": [0, 100], "p2": [200, 100],
                         "allowed_sign": 1, "signal_id": "SIG_1"}],
              "pairs": []}
    rule5 = create("stop_line_violation", {"dilemma_grace_s": 0.0, "stop_dwell_s": 0.1})
    st5 = TrackState(5, 2, 0.9, (100, 80))
    st5.hits = 3
    e5 = None
    # Cat vach tai y=110 roi dung yen tai do
    for idx in range(1, 20):
        y = 110 if idx > 1 else 90
        st5.update(2, 0.9, (100, y), [90, y - 20, 110, y], idx)
        e5 = rule5.run(entry5, st5, idx, idx / FPS, signals=sigs)
        if e5:
            break
    assert e5 is not None and e5["type"] == "stop_line_violation", e5

    print("run dispatch OK (wrong_way/no_uturn/no_entry/red_light/stop_line)")


if __name__ == "__main__":
    test_known_types()
    test_create_filters_unknown_keys()
    test_create_unknown_name()
    test_run_dispatch()
    print("ALL REGISTRY TESTS PASSED")


"""Test registry: anh xa ten -> class, loc key la, dispatch run().
Chay tu project root: python -m tests.test_registry
"""
from src.rules import (NoEntryRule, NoUTurnRule, WrongWayRule, create,
                       known_types)
from src.tracking import TrackState
from tests._helpers import FPS, drive


def test_known_types():
    assert set(known_types()) == {"wrong_way", "no_uturn", "no_entry_road"}
    print("known_types OK")


def test_create_filters_unknown_keys():
    # key cu da bo (vd time_window_s) khong duoc gay crash
    r = create("no_uturn", {"time_window_s": [1, 2], "min_hits": 5})
    assert isinstance(r, NoUTurnRule) and r.min_hits == 5
    r = create("wrong_way", {})
    assert isinstance(r, WrongWayRule) and r.min_hits == 3
    r = create("no_entry_road", {"dwell_s": 1.5})
    assert isinstance(r, NoEntryRule) and r.dwell_s == 1.5
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
    print("run dispatch OK (wrong_way/no_uturn/no_entry)")


if __name__ == "__main__":
    test_known_types()
    test_create_filters_unknown_keys()
    test_create_unknown_name()
    test_run_dispatch()
    print("ALL REGISTRY TESTS PASSED")

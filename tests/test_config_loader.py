"""Test config loader: merge base, auto-wrap, params, validate, routing.
Chay tu project root: python -m tests.test_config_loader
"""
import tempfile
from pathlib import Path

import yaml

from src.config_loader import (ConfigError, deep_merge, effective_params,
                               entries_for, is_enabled, load_camera_config)
from src.geometry import point_in_polygon
from src.rules import WrongWayRule
from src.tracking import TrackState

FPS = 30.0


def flat_cfg():
    return {"camera_id": "T", "model": {}, "lines": [
        {"id": "L", "p1": [0, 100], "p2": [200, 100], "allowed_sign": -1}],
        "uturn_pairs": [],
        "wrong_way": {"min_reverse_frames": 5, "min_reverse_px": 1e9},
        "no_uturn": {}, "no_entry_road": {}}


def write_tmp(cfg):
    d = tempfile.mkdtemp()
    p = Path(d) / "cam.yaml"
    yaml.safe_dump(cfg, open(p, "w"))
    return str(p)


def test_merge():
    base = {"model": {"conf": 0.4, "imgsz": 640}, "wrong_way": {"cooldown_s": 10},
            "polygons": [{"id": "OLD"}]}
    over = {"model": {"conf": 0.5}, "polygons": [{"id": "NEW"}]}
    m = deep_merge(base, over)
    assert m["model"] == {"conf": 0.5, "imgsz": 640}
    assert m["wrong_way"] == {"cooldown_s": 10}
    assert m["polygons"] == [{"id": "NEW"}]  # list thay toan bo
    print("merge OK")


def test_base_override_file():
    d = tempfile.mkdtemp()
    yaml.safe_dump({"model": {"conf": 0.4}, "timezone": "X"},
                   open(Path(d) / "base.yaml", "w"))
    yaml.safe_dump({"base": "base.yaml", "camera_id": "C1",
                    "model": {"conf": 0.7}},
                   open(Path(d) / "cam.yaml", "w"))
    cfg, warns = load_camera_config(str(Path(d) / "cam.yaml"))
    assert cfg["model"]["conf"] == 0.7 and cfg["timezone"] == "X"
    assert cfg["camera_id"] == "C1" and warns == []
    print("base+override OK")


def test_autowrap_equivalence():
    """Config phang cu -> implicit poly, rule chay y nhu cu."""
    cfg, _ = load_camera_config(write_tmp(flat_cfg()))
    assert cfg["polygons"][0]["id"] == "__GLOBAL__"
    assert cfg["lines"] == [] and cfg["uturn_pairs"] == []
    plan = cfg["_plan"]
    assert [e["rule"] for e in plan] == ["wrong_way", "no_uturn"]
    entry = [e for e in plan if e["rule"] == "wrong_way"][0]
    rule = WrongWayRule(min_hits=3, min_reverse_frames=5, min_reverse_px=1e9)
    st = TrackState(1, 2, 0.9, (100, 80))
    st.hits = 3
    evs = []
    for i in range(1, 8):
        st.update(2, 0.9, (100, 80 + 10 * i), [0, 0, 10, 10], i)
        if rule.update(st, entry["lines"], i, i / FPS):
            evs.append(1)
    assert len(evs) == 1
    # ngoai polygon explicit = skip, nhung implicit khop moi track
    assert entries_for((9999, 9999), plan, point_in_polygon) != []
    print("autowrap equivalence OK")


def test_effective_params():
    cfg = {"wrong_way": {"cooldown_s": 10, "min_hits": 3},
           "no_uturn": {}, "no_entry_road": {},
           "polygons": [{"id": "P", "kind": "directional",
                         "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
                         "lines": [], "rules": {
                             "wrong_way": {"enable": True, "cooldown_s": 99},
                             "no_uturn": {"enable": False}}}]}
    p = cfg["polygons"][0]
    pr = effective_params(cfg, p, "wrong_way")
    assert pr == {"cooldown_s": 99, "min_hits": 3}  # override + ke thua + bo enable
    assert is_enabled(cfg, p, "wrong_way") is True
    assert is_enabled(cfg, p, "no_uturn") is False
    assert is_enabled(cfg, p, "no_entry_road") is True  # mac dinh global
    print("effective params OK")


def test_validate_errors():
    def bad(**kw):
        c = {"camera_id": "T", "model": {}, "lines": [], "uturn_pairs": [],
             "wrong_way": {}, "no_uturn": {}, "no_entry_road": {}}
        c.update(kw)
        return c

    # pair xuyen polygon: dat pair o A nhung L2 o B
    c = bad(polygons=[
        {"id": "A", "kind": "directional",
         "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
         "lines": [{"id": "L1", "p1": [0, 0], "p2": [1, 1], "allowed_sign": 1}],
         "rules": {}, "uturn_pairs": [
             {"first": "L1", "second": "L2", "medial": "L1"}]},
        {"id": "B", "kind": "directional",
         "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
         "lines": [{"id": "L2", "p1": [0, 0], "p2": [1, 1], "allowed_sign": 1}],
         "rules": {}}])
    try:
        load_camera_config(write_tmp(c))
        raise AssertionError("pair xuyen polygon phai loi")
    except ConfigError:
        pass
    c = bad(polygons=[{"id": "T", "kind": "trajectory",
                       "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
                       "lines": [], "rules": {"no_uturn": {"enable": True}}}])
    try:
        load_camera_config(write_tmp(c))
        raise AssertionError("trajectory thieu pair phai loi")
    except ConfigError:
        pass
    c = bad(polygons=[{"id": "B", "kind": "banned",
                       "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
                       "lines": [], "rules": {"no_entry_road": {"enable": True}}}])
    try:
        load_camera_config(write_tmp(c))
        raise AssertionError("banned thieu classes phai loi")
    except ConfigError:
        pass
    c = bad(polygons=[{"id": "B", "kind": "banned",
                       "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
                       "lines": [], "banned_classes": [1],
                       "active_hours": ["99:99-00:00"],
                       "rules": {"no_entry_road": {"enable": True}}}])
    try:
        load_camera_config(write_tmp(c))
        raise AssertionError("gio sai phai loi")
    except ConfigError:
        pass
    c = bad(polygons=[{"id": "P", "kind": "directional",
                       "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
                       "lines": [], "rules": {"wrong_wya": {"enable": True}}}])
    try:
        load_camera_config(write_tmp(c))
        raise AssertionError("ten rule la phai loi")
    except ConfigError:
        pass
    print("validate errors OK (5 case)")


def test_unimplemented_warns_not_raise():
    c = {"camera_id": "T", "model": {}, "lines": [], "uturn_pairs": [],
         "wrong_way": {}, "no_uturn": {}, "no_entry_road": {},
         "polygons": [{"id": "P", "kind": "banned",
                       "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
                       "lines": [], "banned_classes": [1],
                       "rules": {"no_parking": {"enable": True}}}]}
    cfg, warns = load_camera_config(write_tmp(c))
    assert any("no_parking" in w for w in warns), warns
    assert all(e["rule"] != "no_parking" for e in cfg["_plan"])
    print("unimplemented warn OK")


def test_disabled_never_in_plan():
    c = {"camera_id": "T", "model": {}, "lines": [
        {"id": "L", "p1": [0, 0], "p2": [1, 1], "allowed_sign": 1}],
        "uturn_pairs": [], "wrong_way": {"enable": False},
        "no_uturn": {"enable": False}, "no_entry_road": {"enable": False}}
    cfg, _ = load_camera_config(write_tmp(c))
    assert cfg["_plan"] == []
    print("disabled never in plan OK")


def test_routing_skip():
    c = {"camera_id": "T", "model": {}, "lines": [], "uturn_pairs": [],
         "wrong_way": {}, "no_uturn": {}, "no_entry_road": {},
         "polygons": [{"id": "Z", "kind": "directional",
                       "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
                       "lines": [{"id": "L", "p1": [0, 0], "p2": [9, 9],
                                  "allowed_sign": 1}],
                       "rules": {"wrong_way": {"enable": True}}}]}
    cfg, _ = load_camera_config(write_tmp(c))
    assert entries_for((4, 4), cfg["_plan"], point_in_polygon) != []
    assert entries_for((99, 99), cfg["_plan"], point_in_polygon) == []
    print("routing skip OK")


def test_standalone_ww_flow():
    """Mo phong phim w: line wrong_way don nam top-level, loader boc
    __GLOBAL__ (khop moi track), rule ban khi cat nguoc."""
    cfg = {"camera_id": "T", "model": {}, "lines": [
        {"id": "W1", "p1": [0, 100], "p2": [200, 100], "allowed_sign": -1}],
        "uturn_pairs": [],
        "wrong_way": {"min_reverse_frames": 5, "min_reverse_px": 1e9},
        "no_uturn": {"enable": False}, "no_entry_road": {"enable": False}}
    cfg, warns = load_camera_config(write_tmp(cfg))
    assert warns == []
    assert [e["rule"] for e in cfg["_plan"]] == ["wrong_way"]
    entry = cfg["_plan"][0]
    assert entry["polygon"]["id"] == "__GLOBAL__"
    rule = WrongWayRule(min_hits=3, min_reverse_frames=5, min_reverse_px=1e9)
    st = TrackState(1, 2, 0.9, (100, 80))
    st.hits = 3
    evs = []
    for i in range(1, 8):
        st.update(2, 0.9, (100, 80 + 10 * i), [0, 0, 10, 10], i)
        if rule.update(st, entry["lines"], i, i / FPS):
            evs.append(1)
    assert len(evs) == 1
    # track o bat cu dau cung khop (khong skip nhu polygon explicit)
    assert entries_for((9999, 9999), cfg["_plan"], point_in_polygon) != []
    print("standalone ww flow OK")


def test_nouturn_enabled_no_pairs_warns():
    """no_uturn bat nhung polygon khong co pair -> warn to (khong im lang
    nhu bug POLY_1: rule khong bao gio ban)."""
    c = {"camera_id": "T", "model": {}, "lines": [], "uturn_pairs": [],
         "wrong_way": {"enable": False}, "no_uturn": {},
         "no_entry_road": {"enable": False},
         "polygons": [{"id": "P", "kind": "directional",
                       "polygon": [[0, 0], [9, 0], [9, 9], [0, 9]],
                       "lines": [{"id": "L1", "p1": [0, 0], "p2": [9, 0],
                                  "allowed_sign": 1}],
                       "rules": {"no_uturn": {"enable": True}}}]}
    _, warns = load_camera_config(write_tmp(c))
    assert any("uturn_pairs rong" in w for w in warns), warns
    print("no-uturn-no-pairs warn OK")


if __name__ == "__main__":
    test_merge()
    test_base_override_file()
    test_autowrap_equivalence()
    test_effective_params()
    test_validate_errors()
    test_unimplemented_warns_not_raise()
    test_disabled_never_in_plan()
    test_routing_skip()
    test_standalone_ww_flow()
    test_nouturn_enabled_no_pairs_warns()
    print("ALL CONFIG-LOADER TESTS PASSED")

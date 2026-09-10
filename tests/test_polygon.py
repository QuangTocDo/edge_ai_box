"""Test polygon zone + gio cam (geometry + config).
Rule no_entry_road nam o tests/test_rule_no_entry.py.
Chay tu project root: python -m tests.test_polygon
"""
from src.geometry import (containing_polygons, in_active_hours, parse_window,
                          point_in_polygon, polygon_valid)
from src.line_config import (add_divider, add_directed, add_entry_line,
                             add_pair, add_polygon, delete_polygon,
                             validate_polygons)

SQ = [[0, 0], [200, 0], [200, 200], [0, 200]]


def test_pip():
    assert point_in_polygon((100, 100), SQ)
    assert not point_in_polygon((300, 100), SQ)
    assert point_in_polygon((0, 100), SQ)      # tren canh
    assert point_in_polygon((0, 0), SQ)        # dinh
    assert not point_in_polygon((100, 100), [[0, 0], [1, 1]])
    assert polygon_valid(SQ) and not polygon_valid([[0, 0], [1, 1]])
    assert not polygon_valid([[0, 0], [1, 1], [2, 2]])  # thang hang
    polys = [{"id": "A", "polygon": SQ}, {"id": "B", "polygon": [[500] * 2] * 4}]
    assert [p["id"] for p in containing_polygons((10, 10), polys)] == ["A"]
    # polygon None (implicit __GLOBAL__) khong duoc crash, coi nhu khong chua
    assert point_in_polygon((10, 10), None) is False
    assert point_in_polygon((10, 10), []) is False
    polys_none = [{"id": "__GLOBAL__", "polygon": None}]
    assert containing_polygons((10, 10), polys_none) == []
    print("pip OK")


def test_hours():
    assert parse_window("18:00-05:00") == (1080, 300)
    assert in_active_hours(1200, [(1080, 300)])       # 20:00 trong
    assert in_active_hours(120, [(1080, 300)])        # 02:00 qua dem
    assert not in_active_hours(600, [(1080, 300)])    # 10:00 ngoai
    assert in_active_hours(1080, [(1080, 300)])       # bien
    assert in_active_hours(300, [(1080, 300)])        # bien
    assert in_active_hours(600, [(540, 660)])
    assert not in_active_hours(539, [(540, 660)])
    try:
        parse_window("25:00-05:00")
        raise AssertionError("phai loi gio")
    except ValueError:
        pass
    print("hours OK")


def test_polygon_crud():
    cfg = {"lines": [], "uturn_pairs": []}
    p = add_polygon(cfg, SQ, kind="banned", banned_classes=[0, 4],
                    active_hours=["18:00-05:00"], dwell_s=2)
    assert p["id"] == "POLY_1" and p["handler"] == ["no_entry_road"]
    assert p["entry_lines"] == []
    e = add_entry_line(cfg, "POLY_1", (50, 200), (150, 200))
    assert e["id"] == "ENTRY_1"
    d = add_polygon(cfg, SQ, kind="directional")
    assert d["handler"] == ["wrong_way", "no_uturn"]
    for bad in ({"kind": "x"},):
        try:
            add_polygon(cfg, SQ, **bad)
            raise AssertionError("phai loi kind")
        except ValueError:
            pass
    try:
        add_polygon(cfg, [[0, 0], [1, 1]], kind="banned")
        raise AssertionError("phai loi polygon")
    except ValueError:
        pass
    add_directed(cfg, (0, 0), (10, 0))  # L1 top-level (khong lien quan)
    poly, dropped = delete_polygon(cfg, "POLY_1")
    assert poly["id"] == "POLY_1" and dropped == []
    assert [x["id"] for x in cfg["lines"]] == ["L1"]  # top-level giu lai
    assert validate_polygons({"lines": [], "uturn_pairs": [],
                              "polygons": [{"id": "X", "kind": "banned",
                                            "polygon": SQ}]}) != []
    print("polygon CRUD OK")


if __name__ == "__main__":
    test_pip()
    test_hours()
    test_polygon_crud()
    print("ALL POLYGON TESTS PASSED")

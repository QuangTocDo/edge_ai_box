"""Test polygon zone + gio cam + NoEntryRule (headless).
Chay tu project root: python -m tests.test_polygon
"""
from src.geometry import (containing_polygons, in_active_hours, parse_window,
                          point_in_polygon, polygon_valid)
from src.line_config import (add_divider, add_directed, add_entry_line,
                             add_pair, add_polygon, delete_polygon,
                             validate_polygons)
from src.rules import NoEntryRule
from src.tracking import TrackState

FPS = 30.0
SQ = [[0, 0], [200, 0], [200, 200], [0, 200]]


def ban_poly(**kw):
    p = {"id": "BAN_A", "kind": "banned", "polygon": SQ,
         "banned_classes": [1], "active_hours": ["18:00-05:00"],
         "entry_lines": [{"id": "E1", "p1": [50, 200], "p2": [150, 200]}],
         "dwell_s": 2.0, "handler": ["no_entry_road"]}
    p.update(kw)
    return p


def drive(poly, pts, wall_min=1200, dwell=2.0):
    rule = NoEntryRule(dwell_s=dwell)
    st = TrackState(1, 1, 0.9, pts[0])
    st.hits = 5
    evs = []
    for i in range(1, len(pts)):
        st.update(1, 0.9, pts[i], [0, 0, 10, 10], i)
        e = rule.update(st, poly, wall_min, i, i / FPS)
        if e:
            evs.append(e)
    return evs


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


def test_no_entry_trigger():
    pts = [(100, 250 - 2 * i) for i in range(100)]  # vao cua E1, o trong
    evs = drive(ban_poly(), pts)
    assert len(evs) == 1 and evs[0]["type"] == "no_entry_road", evs
    assert evs[0]["extra"]["zone_id"] == "BAN_A"
    assert evs[0]["extra"]["dwell_s"] >= 2.0
    print("no_entry trigger OK")


def test_no_entry_filters():
    pts = [(100, 250 - 2 * i) for i in range(100)]
    assert drive(ban_poly(), pts, wall_min=600) == []       # ngoai gio
    poly = ban_poly(banned_classes=[2])                     # class 1 khong cam
    assert drive(poly, pts) == []
    short = [(100, 250 - 5 * i) for i in range(20)]          # vao roi ra ngay
    short += [(100, 150 + 10 * i) for i in range(1, 20)]
    assert drive(ban_poly(), short) == []
    print("no_entry filters OK (gio/class/dwell-reset)")


def test_no_entry_lateral():
    across = [(-50 + i, 100) for i in range(300)]  # xuyên ngang, huong nao cung bao
    evs = drive(ban_poly(), across)
    assert len(evs) == 1 and evs[0]["type"] == "no_entry_road", evs
    print("no_entry lateral OK")


def test_no_entry_spawn():
    inside = [(100, 150 - i) for i in range(80)]   # moc san di len
    assert len(drive(ban_poly(), inside)) == 1
    parked = [(100, 150)] * 80                     # moc san dung yen
    assert len(drive(ban_poly(), parked)) == 1
    print("no_entry spawn OK (di + dung yen deu bao)")


def test_no_entry_reentry():
    pts = [(100, 250 - 2 * i) for i in range(100)]  # vao, bao lan 1
    pts += [(100, 50 + 5 * i) for i in range(1, 60)]  # ra (thoat ~i=130)
    for _ in range(200):  # doi het cooldown 10s ngoai zone (->i=359)
        pts.append((100, 400))
    pts += [(100, 400 - 2 * i) for i in range(1, 171)]  # vao lai (198, bao 519)
    evs = drive(ban_poly(), pts)
    assert len(evs) == 2, evs
    print("no_entry reentry OK")


def test_no_entry_cooldown():
    pts = [(100, 250 - i) for i in range(200)]  # vao cham, o trong lau
    evs = drive(ban_poly(), pts)
    assert len(evs) == 1, evs  # cooldown chan bao lap
    print("no_entry cooldown OK")


if __name__ == "__main__":
    test_pip()
    test_hours()
    test_polygon_crud()
    test_no_entry_trigger()
    test_no_entry_filters()
    test_no_entry_lateral()
    test_no_entry_spawn()
    test_no_entry_reentry()
    test_no_entry_cooldown()
    print("ALL POLYGON TESTS PASSED")

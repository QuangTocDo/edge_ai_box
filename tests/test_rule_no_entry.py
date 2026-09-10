"""Test rule duong cam.
Chay tu project root: python -m tests.test_rule_no_entry
"""
from src.rules import NoEntryRule
from src.tracking import TrackState
from tests._helpers import FPS

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


def test_no_entry_explain():
    rule = NoEntryRule(dwell_s=2.0)
    poly = ban_poly()
    st = TrackState(1, 1, 0.9, (100, 100))
    st.hits = 5
    assert "ngoai gio" in rule.explain(st, t=1.0, polygon=poly, wall_min=600)
    assert "khong cam" in rule.explain(
        st, t=1.0, polygon=ban_poly(banned_classes=[9]), wall_min=1200)
    outsider = TrackState(1, 1, 0.9, (300, 300))
    outsider.hits = 5
    assert "ngoai zone" in rule.explain(
        outsider, t=1.0, polygon=poly, wall_min=1200)
    st.zones["BAN_A"] = {"inside": True, "enter_t": 0.5, "fired": False}
    msg = rule.explain(st, t=1.2, polygon=poly, wall_min=1200)
    assert "trong zone 0.7/2s" in msg, msg
    st.zones["BAN_A"]["fired"] = True
    assert "da bao" in rule.explain(st, t=5.0, polygon=poly, wall_min=1200)
    print("no_entry explain OK")


if __name__ == "__main__":
    test_no_entry_trigger()
    test_no_entry_filters()
    test_no_entry_lateral()
    test_no_entry_spawn()
    test_no_entry_reentry()
    test_no_entry_cooldown()
    test_no_entry_explain()
    print("ALL NO-ENTRY TESTS PASSED")

"""Test rule cam quay dau.
Chay tu project root: python -m tests.test_rule_no_uturn
"""
from tests._helpers import drive
from src.rules import NoUTurnRule, WrongWayRule
from src.tracking import TrackState
from src.tracking import TrackState


def uturn_lines():
    # Vach RL: xe R->L (xuong) di dung chieu; vach LR: xe L->R (len).
    return [
        {"id": "L_RL", "p1": [0, 200], "p2": [200, 200], "allowed_sign": 1},
        {"id": "L_LR", "p1": [0, 400], "p2": [200, 400], "allowed_sign": -1},
    ]


def uturn_path_rl_lr():
    """Xuong qua RL -> quay dau -> len qua LR."""
    pts = [(100, 150 + 10 * i) for i in range(8)]      # 150..220, cat RL
    pts += [(100, 230 + 20 * i) for i in range(1, 12)]  # ..450
    pts += [(100, 450)] * 3
    pts += [(100, 430 - 20 * i) for i in range(1, 8)]   # 410..290, cat LR
    return pts


def uturn_path_lr_rl():
    """Nguoc lai: len qua LR -> quay dau -> xuong qua RL."""
    pts = [(100, 450 - 10 * i) for i in range(8)]      # 450..380, cat LR
    pts += [(100, 370 - 20 * i) for i in range(1, 12)]  # ..150
    pts += [(100, 150)] * 3
    pts += [(100, 170 + 20 * i) for i in range(1, 8)]   # 190..310, cat RL
    return pts


def test_uturn_rl_lr():
    rule = NoUTurnRule()
    pairs = [{"first": "L_RL", "second": "L_LR"}]
    evs = drive(uturn_lines(), uturn_path_rl_lr(), rule, pairs)
    assert len(evs) == 1 and evs[0]["type"] == "no_uturn", evs
    assert evs[0]["line_id"] == "L_RL->L_LR"
    print("no_uturn RL->LR OK:", evs[0]["extra"])


def test_uturn_lr_rl():
    rule = NoUTurnRule()
    pairs = [{"first": "L_LR", "second": "L_RL"}]
    evs = drive(uturn_lines(), uturn_path_lr_rl(), rule, pairs)
    assert len(evs) == 1 and evs[0]["type"] == "no_uturn", evs
    assert evs[0]["line_id"] == "L_LR->L_RL"
    print("no_uturn LR->RL OK")


def test_uturn_wrong_dir():
    """Cat first nguoc chieu -> khong co flag -> khong bao."""
    rule = NoUTurnRule()
    pairs = [{"first": "L_RL", "second": "L_LR"}]
    pts = [(100, 250 - 10 * i) for i in range(8)]  # len qua RL = nguoc
    pts += [(100, 170 - 20 * i) for i in range(1, 12)]
    assert drive(uturn_lines(), pts, rule, pairs) == []
    print("no_uturn wrong-dir OK")


def test_uturn_fast_crossing():
    """Hoi quy bug xe nhanh: 2 lan cham cach nhau <2s (dt~0.4s) van phai
    ban. Logic cu (window 2-12s) loai truong hop nay."""
    rule = NoUTurnRule()
    pairs = [{"first": "L_RL", "second": "L_LR"}]
    pts = [(100, 180 + 20 * i) for i in range(13)]   # xuong qua RL
    pts += [(100, 420 - 20 * i) for i in range(1, 4)]  # quay len qua LR
    evs = drive(uturn_lines(), pts, rule, pairs)
    assert len(evs) == 1 and evs[0]["type"] == "no_uturn", evs
    assert evs[0]["extra"]["dt_s"] < 2.0
    print("no_uturn fast-crossing OK:", evs[0]["extra"])


def test_uturn_real_geometry_poly1():
    """Hoi quy bug POLY_1 that: L1(-1) o y~362, L2(+1) o y~155.
    Xe di len qua L1 dung chieu, quay dau, di xuong qua L2 dung chieu
    trong window 2-12s -> phai ban 1 event moi chieu."""
    lines = [
        {"id": "L1", "p1": [850, 356], "p2": [1187, 368], "allowed_sign": -1},
        {"id": "L2", "p1": [847, 149], "p2": [1197, 162], "allowed_sign": 1},
    ]
    rule = NoUTurnRule()
    # L1 -> L2: tu duoi (y=500) di len qua L1, quay dau, di xuong qua L2
    pts = [(1000, 500 - 5 * i) for i in range(41)]    # len toi y=300
    pts += [(1000, 300 - 5 * i) for i in range(1, 41)]  # len toi y=100
    pts += [(1000, 100 + 5 * i) for i in range(1, 30)]  # xuong lai
    evs = drive(lines, pts, rule, [{"first": "L1", "second": "L2"}])
    assert len(evs) == 1 and evs[0]["type"] == "no_uturn", evs
    assert evs[0]["line_id"] == "L1->L2"
    # L2 -> L1 (chieu nguoc lai)
    pts2 = [(1000, 50 + 5 * i) for i in range(41)]     # xuong toi y=250
    pts2 += [(1000, 250 + 5 * i) for i in range(1, 41)]  # xuong toi y=450
    pts2 += [(1000, 450 - 5 * i) for i in range(1, 40)]  # quay len
    evs2 = drive(lines, pts2, rule, [{"first": "L2", "second": "L1"}])
    assert len(evs2) == 1 and evs2[0]["type"] == "no_uturn", evs2
    assert evs2[0]["line_id"] == "L2->L1"
    print("no_uturn real-geometry POLY_1 OK (ca 2 chieu)")


def test_zone_bundle_flow():
    """Flow gop phim 1: polygon + 2 lines + finalize(no_uturn=True).
    Cham ca 2 vach dung chieu -> no_uturn; di nguoc 1 vach -> wrong_way."""
    from src.line_config import add_polygon, finalize_zone, find_polygon
    cfg = {"lines": [], "uturn_pairs": []}
    p = add_polygon(cfg, [(0, 0), (200, 0), (200, 200), (0, 200)],
                    kind="directional")
    p["lines"].append({"id": "L_RL", "p1": [0, 100], "p2": [200, 100],
                       "allowed_sign": 1})
    p["lines"].append({"id": "L_LR", "p1": [0, 150], "p2": [200, 150],
                       "allowed_sign": -1})
    res = finalize_zone(cfg, p["id"], no_uturn=True)
    assert sorted(res["pairs"]) == [("L_LR", "L_RL"), ("L_RL", "L_LR")]
    got = find_polygon(cfg, p["id"])
    ut = NoUTurnRule()
    pts = [(100, 80 + 5 * i) for i in range(8)]    # xuong qua RL (40..115)
    pts += [(100, 120 + 5 * i) for i in range(1, 10)]  # tiep den 165 qua LR
    pts += [(100, 165 - 5 * i) for i in range(1, 8)]   # quay len (165..135)
    evs = drive(got["lines"], pts, ut, got["uturn_pairs"])
    assert len(evs) == 1 and evs[0]["type"] == "no_uturn", evs
    ww = WrongWayRule(min_hits=3, min_reverse_frames=5, min_reverse_px=1e9)
    pts2 = [(100, 120 - 10 * i) for i in range(8)]  # len qua RL = nguoc
    evs2 = drive(got["lines"], pts2, ww)
    assert len(evs2) == 1 and evs2[0]["type"] == "wrong_way", evs2
    print("zone bundle flow OK")


def test_uturn_explain():
    rule = NoUTurnRule()
    st = TrackState(1, 2, 0.9, (100, 80))
    st.update(2, 0.9, (100, 90), [0, 0, 10, 10], 1)
    assert "track moi" in rule.explain(st, t=1.0)  # hits=2<3
    st.hits = 5
    st.line_flags["L_RL"] = (10, 3.1)
    msg = rule.explain(st, t=4.0)
    assert "doi" in msg and "L_RL" in msg, msg
    st.line_flags.clear()
    st.cooldowns["no_uturn"] = 9.0
    assert "cooldown" in rule.explain(st, t=4.0)
    print("no_uturn explain OK")


if __name__ == "__main__":
    test_uturn_rl_lr()
    test_uturn_lr_rl()
    test_uturn_wrong_dir()
    test_uturn_fast_crossing()
    test_uturn_real_geometry_poly1()
    test_zone_bundle_flow()
    test_uturn_explain()
    print("ALL NO-UTURN TESTS PASSED")

"""Test rule dung de vach (StopLineRule).
Chay tu project root: python -m tests.test_rule_stop_line
"""
from src.rules import RedLightRunningRule, StopLineRule
from src.tracking import TrackState

FPS = 30.0


def test_stop_line_trigger():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.2, stop_speed_px=1.5)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(1, 2, 0.9, (100, 80))
    st.hits = 3
    ev = None

    # Frame 1-2: cat vach tai y=110
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, 1, 1 / FPS)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    rule.update(st, lines, sigs, 2, 2 / FPS)

    # Frame 3+: dung yen tai y=110
    for f in range(3, 30):
        t = f / FPS
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        ev = rule.update(st, lines, sigs, f, t)
        if ev:
            break

    assert ev is not None, "Phai kich hoat stop_line_violation"
    assert ev["type"] == "stop_line_violation"
    assert ev["line_id"] == "L1"
    assert ev["extra"]["light_state"] == "RED"
    assert ev["extra"]["stop_dwell_s"] >= 0.2
    print("stop_line trigger OK:", ev["extra"])


def test_green_whitelist():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.2)
    sigs = {"SIG_1": {"state": "GREEN", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(2, 2, 0.9, (100, 80))
    st.hits = 3

    # Cat vach luc GREEN
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, 1, 1 / FPS)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    rule.update(st, lines, sigs, 2, 2 / FPS)

    # Den chuyen RED va xe dung yen
    sigs["SIG_1"] = {"state": "RED", "updated_at": 2 / FPS, "ttl_s": 10.0}
    ev = None
    for f in range(3, 25):
        t = f / FPS
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        ev = rule.update(st, lines, sigs, f, t)
        if ev:
            break

    assert ev is None, "Vao vach luc GREEN khong duoc phat stop_line"
    print("stop_line green whitelist OK")


def test_yellow_whitelist():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.2)
    sigs = {"SIG_1": {"state": "YELLOW", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(3, 2, 0.9, (100, 80))
    st.hits = 3
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, 1, 1 / FPS)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    rule.update(st, lines, sigs, 2, 2 / FPS)

    sigs["SIG_1"] = {"state": "RED", "updated_at": 2 / FPS, "ttl_s": 10.0}
    ev = None
    for f in range(3, 25):
        t = f / FPS
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        ev = rule.update(st, lines, sigs, f, t)
        if ev:
            break

    assert ev is None, "Vao vach luc YELLOW khong duoc phat stop_line"
    print("stop_line yellow whitelist OK")


def test_dilemma_grace():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.5, stop_dwell_s=0.2)
    # Den vua do luc t=1.0s
    sigs = {"SIG_1": {"state": "RED", "updated_at": 1.0, "ttl_s": 10.0}}

    st = TrackState(4, 2, 0.9, (100, 80))
    st.hits = 3
    # Cat vach tai t=1.2s (< 1.0 + 0.5s dilemma)
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, 1, 1.1)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    rule.update(st, lines, sigs, 2, 1.2)

    # Sau do dung yen
    ev = None
    for f in range(3, 25):
        t = 1.2 + f / FPS
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        ev = rule.update(st, lines, sigs, f, t)
        if ev:
            break

    assert ev is None, "Vao vach trong dilemma khong duoc phat stop_line"
    print("stop_line dilemma grace OK")


def test_not_stopped():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.2, stop_speed_px=1.5)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(5, 2, 0.9, (100, 80))
    st.hits = 3
    ev = None
    # Xe chay voi van toc 10px/frame khong bao gio dung
    for f in range(1, 20):
        t = f / FPS
        y = 80 + f * 10
        st.update(2, 0.9, (100, y), [90, y - 20, 110, y], f)
        ev = rule.update(st, lines, sigs, f, t)
        if ev:
            break

    assert ev is None, "Xe khong dung sau vach khong duoc bao stop_line"
    print("stop_line not stopped OK")


def test_interrupted_dwell():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.3, stop_speed_px=1.5)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(6, 2, 0.9, (100, 80))
    st.hits = 3

    # Cat vach
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, 1, 1 / FPS)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    rule.update(st, lines, sigs, 2, 2 / FPS)

    # Dung yen vai frame (chua du 0.3s)
    for f in range(3, 7):
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        ev = rule.update(st, lines, sigs, f, f / FPS)
        assert ev is None

    # Di chuyen manh 2 frame (van toc > 1.5px/frame -> reset dwell)
    st.update(2, 0.9, (100, 125), [90, 105, 110, 125], 7)
    rule.update(st, lines, sigs, 7, 7 / FPS)
    assert getattr(st, "red", {}).get("stops", {}).get("L1", {}).get("slow_since") is None

    # Dung lai 2 frame (van chua du 0.3s)
    st.update(2, 0.9, (100, 125), [90, 105, 110, 125], 8)
    ev = rule.update(st, lines, sigs, 8, 8 / FPS)
    assert ev is None
    print("stop_line interrupted dwell reset OK")


def test_light_turned_green_before_dwell():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.3)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(7, 2, 0.9, (100, 80))
    st.hits = 3
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, 1, 1 / FPS)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    rule.update(st, lines, sigs, 2, 2 / FPS)

    # Dung yen den frame 7 (chua du 0.3s)
    for f in range(3, 7):
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        rule.update(st, lines, sigs, f, f / FPS)

    # Den chuyen GREEN o frame 7
    sigs["SIG_1"] = {"state": "GREEN", "updated_at": 7 / FPS, "ttl_s": 10.0}

    # Xe tiep tuc dung yen qua frame 15
    ev = None
    for f in range(7, 20):
        t = f / FPS
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        ev = rule.update(st, lines, sigs, f, t)
        if ev:
            break

    assert ev is None, "Khi den da sang GREEN truoc khi du dwell thi khong bao dung de vach den do"
    print("stop_line light turned green before dwell OK")


def test_clearance_suppress():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    clearance = [{"id": "CLR", "polygon": [[0, 150], [200, 150], [200, 300], [0, 300]]}]
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.2)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(8, 2, 0.9, (100, 80))
    st.hits = 3
    # Cat vach tai frame 2
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, 1, 1 / FPS, clearance=clearance)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    rule.update(st, lines, sigs, 2, 2 / FPS, clearance=clearance)

    # Xe di vao clearance zone y=160 va dung o do
    ev = None
    for f in range(3, 20):
        t = f / FPS
        st.update(2, 0.9, (100, 160), [90, 140, 110, 160], f)
        ev = rule.update(st, lines, sigs, f, t, clearance=clearance)
        if ev:
            break

    assert ev is None, "Xe o trong clearance zone khong duoc bao stop_line_violation"
    print("stop_line clearance suppress OK")


def test_multi_event_stop_then_red_light():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    clearance = [{"id": "CLR", "polygon": [[0, 150], [200, 150], [200, 300], [0, 300]]}]
    r_stop = StopLineRule(min_hits=3, dilemma_grace_s=0.0, stop_dwell_s=0.2)
    r_red = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(9, 2, 0.9, (100, 80))
    st.hits = 3

    # 1. Cat vach o y=110
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    r_stop.update(st, lines, sigs, 1, 1 / FPS, clearance=clearance)
    r_red.update(st, lines, sigs, clearance, None, 1, 1 / FPS)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    r_stop.update(st, lines, sigs, 2, 2 / FPS, clearance=clearance)
    r_red.update(st, lines, sigs, clearance, None, 2, 2 / FPS)

    # 2. Dung yen 15 frames -> phat stop_line_violation
    ev_stop = None
    for f in range(3, 20):
        t = f / FPS
        st.update(2, 0.9, (100, 110), [90, 90, 110, 110], f)
        ev_stop = r_stop.update(st, lines, sigs, f, t, clearance=clearance)
        if ev_stop:
            break

    assert ev_stop is not None and ev_stop["type"] == "stop_line_violation", ev_stop

    # 3. Sau khi bi phat dung de vach, xe tiep tuc phong vao clearance y=160
    ev_red = None
    for f in range(20, 25):
        t = f / FPS
        st.update(2, 0.9, (100, 160), [90, 140, 110, 160], f)
        ev_red = r_red.update(st, lines, sigs, clearance, None, f, t)
        if ev_red:
            break

    assert ev_red is not None and ev_red["type"] == "red_light_running", ev_red
    print("multi-event stop -> red_light OK")


def test_explain():
    rule = StopLineRule(min_hits=3, dilemma_grace_s=0.5, stop_dwell_s=3.0)
    st = TrackState(10, 2, 0.9, (100, 80))
    assert "track moi" in rule.explain(st)
    st.update(2, 0.9, (100, 85), [90, 65, 110, 85], 2)
    st.hits = 5
    assert "chua cat vach" in rule.explain(st)
    st.red = {"wl": True}
    assert "whitelist" in rule.explain(st)
    print("stop_line explain OK")


if __name__ == "__main__":
    test_stop_line_trigger()
    test_green_whitelist()
    test_yellow_whitelist()
    test_dilemma_grace()
    test_not_stopped()
    test_interrupted_dwell()
    test_light_turned_green_before_dwell()
    test_clearance_suppress()
    test_multi_event_stop_then_red_light()
    test_explain()
    print("ALL STOP LINE TESTS PASSED")

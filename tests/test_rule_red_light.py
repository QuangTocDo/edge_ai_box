"""Test rule vuot den do (RedLightRunningRule).
Chay tu project root: python -m tests.test_rule_red_light
"""
import numpy as np
from src.rules import RedLightRunningRule
from src.tracking import TrackState

FPS = 30.0


def test_red_light_movement_confirmation():
    """Xe di tiep sau khi cat vach luc den DO -> Xac nhan vuot den do."""
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0,
                               confirm_dist_px=30.0, confirm_speed_px=1.5,
                               confirm_frames=2)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    frame = np.zeros((300, 300, 3), dtype=np.uint8)

    st = TrackState(1, 2, 0.9, (100, 70))
    st.hits = 3
    ev = None
    # Cat vach o f=20 (y=110), tiep tuc di chuyen o f=21 (y=130), f=22 (y=150)
    for f in range(1, 30):
        t = f / FPS
        if f < 20:
            y = 70 + f
        elif f == 20:
            y = 110  # Cat vach y=100
        elif f == 21:
            y = 130
        else:
            y = 150
        st.update(2, 0.9, (100, y), [90, y - 20, 110, y], f)
        ev = rule.update(st, lines, sigs, [], frame, f, t)
        if ev:
            break

    assert ev is not None, "Phai kich hoat vuot den do khi xe di tiep qua vach"
    assert ev["type"] == "red_light_running"
    assert ev["line_id"] == "L1"
    assert ev["extra"]["light_state"] == "RED"
    assert ev["frame_idx"] == 20, "Evidence frame_idx phai la frame cat vach (f=20)"
    assert f in (21, 22), f"Phai xac nhan sau khi di du khoang cach (f=21 hoac 22), nhan duoc: f={f}"
    print("red_light movement confirmation OK:", f)


def test_red_light_stop_not_running():
    """Xe dung lai sau khi cat vach -> KHONG duoc bao vuot den do (nhuong cho stop_line)."""
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0,
                               confirm_dist_px=30.0, confirm_speed_px=1.5,
                               confirm_frames=2)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(10, 2, 0.9, (100, 70))
    st.hits = 3
    ev = None
    # Cat vach y=100 o f=20 (y=105) nhung dung yen luon o do (y=105)
    for f in range(1, 35):
        t = f / FPS
        if f < 20:
            y = 70 + f
        else:
            y = 105  # Dung yen ngay sau vach (chi de qua vach 5px)
        st.update(2, 0.9, (100, y), [90, y - 20, 110, y], f)
        ev = rule.update(st, lines, sigs, [], None, f, t)
        assert ev is None, f"Xe dung lai o f={f} khong duoc bao vuot den do"

    print("red_light stop not running OK")


def test_immediate_mode():
    """Khi confirm_dist_px=0 va confirm_frames=1 -> Phat ngay lap tuc tai vach."""
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0,
                               confirm_dist_px=0.0, confirm_frames=1)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(11, 2, 0.9, (100, 70))
    st.hits = 3
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, [], None, 1, 1.0)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    ev = rule.update(st, lines, sigs, [], None, 2, 1.033)
    assert ev is not None, "Mode immediate phai phat ngay khi cat vach"
    print("red_light immediate mode OK")


def test_green_whitelist():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0)
    sigs = {"SIG_1": {"state": "GREEN", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(2, 2, 0.9, (100, 80))
    st.hits = 3
    ev = None

    for f in range(1, 6):
        t = f / FPS
        y = 80 + f * 5
        st.update(2, 0.9, (100, y), [90, y - 20, 110, y], f)
        ev = rule.update(st, lines, sigs, [], None, f, t)
        assert ev is None

    sigs["SIG_1"] = {"state": "RED", "updated_at": 6 / FPS, "ttl_s": 10.0}

    for f in range(6, 20):
        t = f / FPS
        y = 105 + (f - 5) * 5
        st.update(2, 0.9, (100, y), [90, y - 20, 110, y], f)
        ev = rule.update(st, lines, sigs, [], None, f, t)
        assert ev is None, "Xe da vao luc GREEN thi phai duoc whitelist, khong duoc phat"

    assert getattr(st, "red", {}).get("wl") is True
    print("green whitelist OK")


def test_yellow_whitelist():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0)
    sigs = {"SIG_1": {"state": "YELLOW", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(3, 2, 0.9, (100, 80))
    st.hits = 3

    for f in range(1, 6):
        t = f / FPS
        y = 80 + f * 5
        st.update(2, 0.9, (100, y), [90, y - 20, 110, y], f)
        ev = rule.update(st, lines, sigs, [], None, f, t)
        assert ev is None

    sigs["SIG_1"] = {"state": "RED", "updated_at": 6 / FPS, "ttl_s": 10.0}
    for f in range(6, 20):
        t = f / FPS
        y = 105 + (f - 5) * 5
        st.update(2, 0.9, (100, y), [90, y - 20, 110, y], f)
        ev = rule.update(st, lines, sigs, [], None, f, t)
        assert ev is None, "Xe cat vach luc YELLOW phai duoc whitelist"

    assert getattr(st, "red", {}).get("wl") is True
    print("yellow whitelist OK")


def test_unknown_whitelist():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 1.0}}

    st = TrackState(4, 2, 0.9, (100, 80))
    st.hits = 3
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, [], None, 1, 5.0)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    ev = rule.update(st, lines, sigs, [], None, 2, 5.033)
    assert ev is None
    assert getattr(st, "red", {}).get("wl") is True, "Tin hieu cu het han phai whitelist"
    print("unknown / expired TTL whitelist OK")


def test_dilemma_grace():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.5)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 2.0, "ttl_s": 10.0}}

    st = TrackState(5, 2, 0.9, (100, 80))
    st.hits = 3
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, [], None, 1, 2.1)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    ev = rule.update(st, lines, sigs, [], None, 2, 2.2)
    assert ev is None, "Trong khoang dilemma khong duoc tao candidate hoac trigger"
    assert "L1" in getattr(st, "red", {}).get("wl_lines", set())

    st.update(2, 0.9, (100, 160), [90, 140, 110, 160], 3)
    ev = rule.update(st, lines, sigs, [], None, 3, 3.0)
    assert ev is None, "Xe vao vach luc dilemma khong duoc bao vi pham sau do"
    print("dilemma grace OK")


def test_allow_right_on_red():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1",
              "allow_right_on_red": True}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(6, 2, 0.9, (100, 80))
    st.hits = 3
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, [], None, 1, 1.0)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    ev = rule.update(st, lines, sigs, [], None, 2, 1.033)
    assert ev is None, "Cho phep re phai khi den do khong duoc bao"
    print("allow_right_on_red OK")


def test_clearance_mode_backward_compat():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    clearance = [{"id": "POLY_CLR", "polygon": [[0, 150], [200, 150],
                                                [200, 300], [0, 300]]}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0,
                               intersection_clearance_zone="POLY_CLR")
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(7, 2, 0.9, (100, 80))
    st.hits = 3
    st.update(2, 0.9, (100, 95), [90, 75, 110, 95], 1)
    rule.update(st, lines, sigs, clearance, None, 1, 1.0)
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 2)
    ev1 = rule.update(st, lines, sigs, clearance, None, 2, 1.033)
    assert ev1 is None, "O mode clearance, chua vao clearance thi chua bao vi pham"

    # Khi den doi xanh truoc khi vao clearance
    sigs["SIG_1"] = {"state": "GREEN", "updated_at": 2.0, "ttl_s": 10.0}
    st.update(2, 0.9, (100, 160), [90, 140, 110, 160], 3)
    ev2 = rule.update(st, lines, sigs, clearance, None, 3, 2.1)
    assert ev2 is None, "Khi vao clearance ma den da chuyen sang GREEN thi khong bao vuot den do"
    print("clearance mode backward compat OK")


def test_cooldown():
    lines = [{"id": "L1", "p1": [0, 100], "p2": [200, 100],
              "allowed_sign": 1, "signal_id": "SIG_1"}]
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.0, cooldown_s=10.0,
                               confirm_dist_px=0.0, confirm_frames=1)
    sigs = {"SIG_1": {"state": "RED", "updated_at": 0.0, "ttl_s": 10.0}}

    st = TrackState(8, 2, 0.9, (100, 90))
    st.hits = 3
    st.update(2, 0.9, (100, 110), [90, 90, 110, 110], 1)
    ev1 = rule.update(st, lines, sigs, [], None, 1, 1.0)
    assert ev1 is not None

    st.update(2, 0.9, (100, 120), [90, 100, 110, 120], 2)
    ev2 = rule.update(st, lines, sigs, [], None, 2, 1.1)
    assert ev2 is None, "Trong cooldown khong duoc bao tiep"
    print("cooldown OK")


def test_explain():
    rule = RedLightRunningRule(min_hits=3, dilemma_grace_s=0.5)
    st = TrackState(9, 2, 0.9, (100, 80))
    assert "track moi" in rule.explain(st)
    st.update(2, 0.9, (100, 85), [90, 65, 110, 85], 2)
    st.hits = 5
    assert "chua cat vach" in rule.explain(st)
    st.red = {"wl": True}
    assert "whitelist" in rule.explain(st)
    print("red_light explain OK")


if __name__ == "__main__":
    test_red_light_movement_confirmation()
    test_red_light_stop_not_running()
    test_immediate_mode()
    test_green_whitelist()
    test_yellow_whitelist()
    test_unknown_whitelist()
    test_dilemma_grace()
    test_allow_right_on_red()
    test_clearance_mode_backward_compat()
    test_cooldown()
    test_explain()
    print("ALL RED LIGHT TESTS PASSED")

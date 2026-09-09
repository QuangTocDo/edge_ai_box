"""Test hoi quy bug double-click sinh line rac.
Chay tu project root: python -m tests.test_draw_state
"""
from src.draw_state import DrawState
from src.line_config import add_directed, add_divider


def make_cfg():
    return {"lines": [{"id": "L_NB", "p1": [100, 100], "p2": [300, 100],
                       "allowed_sign": 1}],
            "uturn_pairs": []}


def test_double_click_selects_no_stray():
    """Mo phong dung bug cu: down-down-dblclk len line co san."""
    st = DrawState(make_cfg())
    st.on_down(200, 102, 0.00)   # click 1 cua double (lech 2px)
    st.on_down(201, 101, 0.10)   # click 2 cua double
    kind, sel = st.on_dblclk(200, 102, 0.15)
    assert kind == "selected" and sel == "L_NB", (kind, sel)
    kind, payload = st.poll(1.0)  # qua delay -> phai KHONG tao line
    assert kind is None and payload is None, (kind, payload)
    assert [l["id"] for l in st.cfg["lines"]] == ["L_NB"]
    assert st.selected["id"] == "L_NB"
    print("double-click select OK (khong line rac, chon dung)")


def test_normal_draw_still_works():
    st = DrawState(make_cfg())
    st.on_down(10, 10, 0.0)
    st.on_down(50, 10, 0.1)
    assert st.poll(0.2) == (None, None)  # chua qua delay
    kind, ln = st.poll(0.6)              # qua delay -> tao
    assert kind == "line_created" and ln["id"] == "L1", (kind, ln)
    assert st.selected["id"] == "L1"
    print("normal draw OK")


def test_divider_and_pair_flow():
    st = DrawState(make_cfg())
    st.set_mode("divider")
    st.on_down(0, 0, 0.0)
    st.on_down(0, 50, 0.1)
    kind, ln = st.poll(1.0)
    assert kind == "line_created" and ln["role"] == "divider"
    add_directed(st.cfg, (0, 200), (300, 200))  # L2
    st.set_mode("pair")
    st.on_down(150, 100, 2.0)  # gan L_NB
    st.on_down(150, 200, 2.1)  # gan L2
    kind, pr = st.on_down(0, 25, 2.2)  # gan divider
    assert kind == "pair_created", (kind, pr)
    assert pr == {"first": "L_NB", "second": "L2", "medial": "L1"}
    print("divider + pair OK")


def test_dblclk_clears_pending():
    st = DrawState(make_cfg())
    st.on_down(400, 400, 0.0)  # click le that (khong gan line)
    kind, sel = st.on_dblclk(900, 900, 0.1)  # dblclk cho trong
    assert (kind, sel) == ("selected", None)
    kind, _ = st.poll(1.0)
    assert kind is None and len(st.cfg["lines"]) == 1
    print("dblclk clears pending OK")


if __name__ == "__main__":
    test_double_click_selects_no_stray()
    test_normal_draw_still_works()
    test_divider_and_pair_flow()
    test_dblclk_clears_pending()
    print("ALL DRAW-STATE TESTS PASSED")

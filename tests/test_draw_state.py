"""Test hoi quy bug double-click sinh line rac.
Chay tu project root: python -m tests.test_draw_state
"""
from src.draw_state import DrawState, mode_label, resolve_enter_action
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
    st.on_down(150, 100, 2.0)  # gan L_NB (pick 1/2)
    kind, pr = st.on_down(150, 200, 2.1)  # gan L2 -> tao pair
    assert kind == "pair_created", (kind, pr)
    assert pr == {"first": "L_NB", "second": "L2"}
    print("divider + pair OK")


def test_dblclk_clears_pending():
    st = DrawState(make_cfg())
    st.on_down(400, 400, 0.0)  # click le that (khong gan line)
    kind, sel = st.on_dblclk(900, 900, 0.1)  # dblclk cho trong
    assert (kind, sel) == ("selected", None)
    kind, _ = st.poll(1.0)
    assert kind is None and len(st.cfg["lines"]) == 1
    print("dblclk clears pending OK")


def test_resolve_enter_action():
    # wizard dang ve dinh -> khoa wizard
    assert resolve_enter_action({"poly_id": None}, "polygon") == "wizard_close"
    # wizard da co polygon (dang ve lines) -> Enter khong lam gi
    assert resolve_enter_action({"poly_id": "P1"}, "line") == "none"
    # khong wizard + dang o che do polygon -> flow le
    assert resolve_enter_action(None, "polygon") == "standalone_close"
    # che do ve line thuong -> Enter vo nghia
    assert resolve_enter_action(None, "line") == "none"
    print("resolve_enter_action OK")


def test_mode_label():
    assert mode_label({"poly_id": None}, "polygon", "directed") == \
        "ZONE-FLOW (ve dinh)"
    assert mode_label({"poly_id": "P1"}, "line", "directed") == \
        "ZONE-FLOW (ve 2 lines)"
    assert mode_label(None, "polygon", "directed") == "POLYGON-LE"
    assert mode_label(None, "line", "pair") == "PAIR"
    print("mode_label OK")


def test_esc_then_enter_is_noop():
    """Mo phong dung bug user gap: phim 1 -> Esc -> Enter.
    Sau Esc: tool_mode='line', wizard=None -> Enter khong lam gi,
    khong hien prompt kind le."""
    tool_mode, wizard = "polygon", {"poly_id": None}
    # xu ly Esc (giong handler trong tool)
    tool_mode, wizard = "line", None
    assert resolve_enter_action(wizard, tool_mode) == "none"
    assert mode_label(wizard, tool_mode, "directed") == "DIRECTED"
    print("esc-then-enter noop OK")


def test_slow_doubleclick_no_stray():
    """Double-click cham (>0.35s moi toi DBLCLK): poll dung tao line rac,
    dblclk phai chon dung line that."""
    st = DrawState({"lines": [], "uturn_pairs": []})
    st.on_down(100, 100, 0.0)
    st.on_down(300, 100, 0.1)
    assert st.poll(1.0)[0] == "line_created"
    st.on_down(100, 200, 2.0)
    st.on_down(300, 200, 2.1)
    assert st.poll(3.0)[0] == "line_created"
    assert [l["id"] for l in st.cfg["lines"]] == ["L1", "L2"]
    # double-click cham len L2: poll chay truoc DBLCLK
    st.on_down(200, 200, 10.0)
    st.on_down(202, 201, 10.2)
    kind, _ = st.poll(10.6)
    assert kind == "ignored_short", kind
    kind, sel = st.on_dblclk(200, 200, 10.65)
    assert (kind, sel) == ("selected", "L2"), (kind, sel)
    assert [l["id"] for l in st.cfg["lines"]] == ["L1", "L2"]
    print("slow double-click OK (khong rac, chon dung)")


def test_short_line_legit_threshold():
    """Line that (>=10px) van tao binh thuong; duoi 10px thi bo."""
    st = DrawState({"lines": [], "uturn_pairs": []})
    st.on_down(0, 0, 0.0)
    st.on_down(50, 0, 0.1)
    kind, ln = st.poll(1.0)
    assert kind == "line_created" and ln["id"] == "L1", (kind, ln)
    print("legit short line OK")


def test_wizard_two_lines_unique_ids_and_select():
    """Mo phong flow wizard: polygon + 2 lines (auto-attach) -> ids duy
    nhat, double-click tung line chon dung, flip dung line."""
    from src import line_config as LC
    cfg = {"lines": [], "uturn_pairs": []}
    p = LC.add_polygon(cfg, [(0, 0), (400, 0), (400, 400), (0, 400)],
                       kind="directional")

    def attach(ln):
        mx = (ln["p1"][0] + ln["p2"][0]) / 2
        my = (ln["p1"][1] + ln["p2"][1]) / 2
        for q in LC.get_polygons(cfg):
            from src.geometry import point_in_polygon
            if point_in_polygon((mx, my), q.get("polygon", [])):
                cfg["lines"].remove(ln)
                q.setdefault("lines", []).append(ln)
                return q["id"]
        return None

    st = DrawState(cfg)
    st.on_down(100, 100, 0.0)
    st.on_down(300, 100, 0.1)
    kind, l1 = st.poll(1.0)
    assert kind == "line_created"
    assert attach(l1) == p["id"]
    st.on_down(100, 200, 2.0)
    st.on_down(300, 200, 2.1)
    kind, l2 = st.poll(3.0)
    assert kind == "line_created"
    assert attach(l2) == p["id"]
    assert [l["id"] for l in p["lines"]] == ["L1", "L2"]
    # chon tung line + flip dung line
    assert st.on_dblclk(200, 100, 4.0) == ("selected", "L1")
    assert LC.flip_line(cfg, "L1") == -1
    assert st.on_dblclk(200, 200, 5.0) == ("selected", "L2")
    assert LC.flip_line(cfg, "L2") == -1
    by_id = {l["id"]: l for l in p["lines"]}
    assert by_id["L1"]["allowed_sign"] == -1
    assert by_id["L2"]["allowed_sign"] == -1
    print("wizard two-lines unique/select/flip OK")


if __name__ == "__main__":
    test_double_click_selects_no_stray()
    test_normal_draw_still_works()
    test_divider_and_pair_flow()
    test_dblclk_clears_pending()
    test_resolve_enter_action()
    test_mode_label()
    test_esc_then_enter_is_noop()
    test_slow_doubleclick_no_stray()
    test_short_line_legit_threshold()
    test_wizard_two_lines_unique_ids_and_select()
    print("ALL DRAW-STATE TESTS PASSED")

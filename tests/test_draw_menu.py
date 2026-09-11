"""Test menu chon loi 1-5 cho tool ve (gate theo tung loi).
Chay: python -m pytest tests/test_draw_menu.py -v
"""
from src.draw_menu import (allowed_tools, default_rules, get_mode, menu_text,
                           subkey_tool, tools_help, validate_tool)


def test_modes_have_expected_tools():
    assert allowed_tools("1") == ["line"]
    assert allowed_tools("2") == ["polygon", "line", "pair"]
    assert allowed_tools("3") == ["polygon", "fields"]
    assert "polygon" in allowed_tools("4") and "roi" in allowed_tools("4")
    assert "intersection" in allowed_tools("4")
    assert allowed_tools("5") == ["polygon", "calib"]
    print("modes tools OK")


def test_wrong_way_blocks_polygon():
    ok, _ = validate_tool("1", "line")
    assert ok
    for bad in ("polygon", "pair", "roi", "intersection", "calib"):
        ok, why = validate_tool("1", bad)
        assert not ok, (bad, why)
    print("wrong_way gate OK")


def test_each_violation_allows_only_its_tools():
    cases = {
        "2": (["polygon", "line", "pair"], ["roi", "calib", "intersection"]),
        "3": (["polygon"], ["line", "pair", "roi", "calib", "intersection"]),
        "4": (["polygon", "line", "roi", "intersection"],
              ["pair", "calib"]),
        "5": (["polygon", "calib"], ["line", "pair", "roi", "intersection"]),
    }
    for key, (good, bad) in cases.items():
        for t in good:
            assert validate_tool(key, t)[0], (key, t)
        for t in bad:
            assert not validate_tool(key, t)[0], (key, t)
    print("per-violation gate OK")


def test_no_violation_blocks_all():
    ok, why = validate_tool(None, "line")
    assert not ok and "1-5" in why
    print("no-violation gate OK")


def test_subkeys_map():
    assert subkey_tool("l") == "line"
    assert subkey_tool("p") == "polygon"
    assert subkey_tool("a") == "pair"
    assert subkey_tool("r") == "roi"
    assert subkey_tool("i") == "intersection"
    assert subkey_tool("c") == "calib"
    assert subkey_tool("k") == "roi_link"
    assert subkey_tool("z") is None
    print("subkeys OK")


def test_roi_link_only_for_red_light():
    assert validate_tool("4", "roi_link")[0]
    for k in ("1", "2", "3", "5"):
        assert not validate_tool(k, "roi_link")[0], k
    print("roi_link gate OK")


def test_tools_help_only_shows_allowed():
    h1 = " ".join(tools_help("1"))
    assert "l=" in h1 and "p=" not in h1 and "r=" not in h1
    h4 = " ".join(tools_help("4"))
    assert "l=" in h4 and "r=" in h4 and "k=" in h4 and "i=" in h4
    assert "a=" not in h4  # pair khong thuoc loi 4
    print("tools_help OK")


def test_default_rules_enable_only_selected():
    r1 = default_rules("1")
    assert r1["wrong_way"]["enable"] is True
    assert r1["no_uturn"]["enable"] is False
    r4 = default_rules("4")
    assert r4["red_light_running"]["enable"] is True
    print("default_rules OK")


def test_menu_text_lists_all():
    t = menu_text()
    for s in ("wrong_way", "no_uturn", "no_entry", "red_light", "speeding"):
        assert s in t, s
    assert get_mode("9") is None
    print("menu_text OK")


if __name__ == "__main__":
    test_modes_have_expected_tools()
    test_wrong_way_blocks_polygon()
    test_each_violation_allows_only_its_tools()
    test_no_violation_blocks_all()
    test_subkeys_map()
    test_roi_link_only_for_red_light()
    test_tools_help_only_shows_allowed()
    test_default_rules_enable_only_selected()
    test_menu_text_lists_all()
    print("ALL DRAW-MENU TESTS PASSED")

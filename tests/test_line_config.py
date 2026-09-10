"""Unit test logic config lines (headless).
Chay tu project root: python -m tests.test_line_config
"""
import tempfile
from pathlib import Path

from src.line_config import (add_directed, add_divider, add_pair, add_polygon,
                             delete_line, delete_pair, finalize_zone,
                             flip_line, load_config, next_id,
                             remove_tiny_lines, save_config, validate)


def blank():
    return {"lines": [], "uturn_pairs": []}


def test_add_and_ids():
    cfg = blank()
    a = add_directed(cfg, (0, 0), (10, 0))
    b = add_divider(cfg, (5, 0), (5, 10))
    assert (a["id"], b["id"]) == ("L1", "L2"), (a["id"], b["id"])
    assert a["allowed_sign"] == 1 and b["role"] == "divider"
    assert next_id(cfg) == "L3"
    print("add/ids OK")


def test_flip_and_errors():
    cfg = blank()
    add_directed(cfg, (0, 0), (10, 0))
    add_divider(cfg, (5, 0), (5, 10))
    assert flip_line(cfg, "L1") == -1
    for fn, arg in ((flip_line, "L2"), (flip_line, "L9")):
        try:
            fn(cfg, arg)
            raise AssertionError(f"{arg} phai loi")
        except ValueError:
            pass
    print("flip/errors OK")


def test_pair_and_delete_cascade():
    cfg = blank()
    add_directed(cfg, (0, 0), (10, 0))   # L1
    add_directed(cfg, (0, 5), (10, 5))   # L2
    add_divider(cfg, (5, 0), (5, 10))    # L3
    add_pair(cfg, "L1", "L2", "L3")
    try:  # medial sai loai
        add_pair(cfg, "L1", "L2", "L1")
        raise AssertionError("phai loi medial")
    except ValueError:
        pass
    try:  # first la divider
        add_pair(cfg, "L3", "L2", "L3")
        raise AssertionError("phai loi first")
    except ValueError:
        pass
    ln, dropped = delete_line(cfg, "L1")
    assert len(dropped) == 1 and cfg["uturn_pairs"] == []
    assert delete_pair({"uturn_pairs": [{"a": 1}]}, 0) == {"a": 1}
    print("pair/delete-cascade OK")


def test_pair_same_scope():
    from src.line_config import add_polygon
    sq = [[0, 0], [9, 0], [9, 9], [0, 9]]
    cfg = blank()
    t1 = add_directed(cfg, (0, 0), (10, 0))["id"]
    t2 = add_directed(cfg, (0, 5), (10, 5))["id"]
    t3 = add_divider(cfg, (5, 0), (5, 10))["id"]
    add_pair(cfg, t1, t2, t3)          # cung top-level -> OK
    p = add_polygon(cfg, sq, kind="directional")  # POLY_1
    p["lines"].append({"id": "N1", "p1": [0, 0], "p2": [9, 0],
                       "allowed_sign": 1})
    try:  # first top-level + second nested -> loi
        add_pair(cfg, t1, "N1", t3)
        raise AssertionError("xuyen scope phai loi")
    except ValueError:
        pass
    print("pair same-scope OK")


def test_validate_and_roundtrip():
    cfg = blank()
    assert any("Chua co line" in w for w in validate(cfg))
    add_directed(cfg, (0, 0), (10, 0))
    cfg["uturn_pairs"].append({"first": "L1", "second": "L9", "medial": "L8"})
    assert any("L9" in w for w in validate(cfg))
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "c.yaml"
        save_config(cfg, p)
        back = load_config(p)
        assert back["lines"][0]["id"] == "L1"
    print("validate/roundtrip OK")


def test_legacy_config():
    from src.config_loader import load_camera_config
    cfg, warns = load_camera_config("camera_config.yaml")
    assert warns == [], warns
    assert cfg["_plan"], "config that phai sinh plan rong"
    print("legacy config OK:",
          [(e["polygon"]["id"], e["rule"]) for e in cfg["_plan"]])


def test_finalize_zone():
    from src.line_config import find_polygon
    cfg = blank()
    p = add_polygon(cfg, [(0, 0), (200, 0), (200, 200), (0, 200)],
                    kind="directional")
    # chua du 2 lines -> loi
    try:
        finalize_zone(cfg, p["id"], no_uturn=True)
        raise AssertionError("phai loi thieu lines")
    except ValueError as e:
        assert ">=2 lines" in str(e)
    p["lines"].append({"id": "A", "p1": [0, 100], "p2": [200, 100],
                       "allowed_sign": 1})
    p["lines"].append({"id": "B", "p1": [0, 150], "p2": [200, 150],
                       "allowed_sign": -1})
    res = finalize_zone(cfg, p["id"], no_uturn=True)
    assert res["lines"] == ["A", "B"], res
    assert sorted(res["pairs"]) == [("A", "B"), ("B", "A")], res
    got = find_polygon(cfg, p["id"])
    assert got["rules"]["wrong_way"] == {"enable": True}
    assert got["rules"]["no_uturn"] == {"enable": True}
    assert len(got["uturn_pairs"]) == 2
    # goi lai: idempotent, khong trung pair
    res2 = finalize_zone(cfg, p["id"], no_uturn=True)
    assert len(find_polygon(cfg, p["id"])["uturn_pairs"]) == 2, res2
    # tat no_uturn: khong sinh pair moi
    cfg2 = blank()
    q = add_polygon(cfg2, [(0, 0), (200, 0), (200, 200), (0, 200)],
                    kind="directional")
    q["lines"].append({"id": "A", "p1": [0, 100], "p2": [200, 100],
                       "allowed_sign": 1})
    q["lines"].append({"id": "B", "p1": [0, 150], "p2": [200, 150],
                       "allowed_sign": -1})
    res3 = finalize_zone(cfg2, q["id"], no_uturn=False)
    assert res3["pairs"] == [] and q.get("uturn_pairs", []) == []
    assert find_polygon(cfg2, q["id"])["rules"]["no_uturn"] == {"enable": False}
    print("finalize_zone OK")


def test_pair_no_medial_warn():
    from src.line_config import validate_polygons
    cfg = blank()
    p = add_polygon(cfg, [(0, 0), (200, 0), (200, 200), (0, 200)],
                    kind="directional")
    p["lines"].append({"id": "A", "p1": [0, 100], "p2": [200, 100],
                       "allowed_sign": 1})
    p["lines"].append({"id": "B", "p1": [0, 150], "p2": [200, 150],
                       "allowed_sign": -1})
    p.setdefault("uturn_pairs", []).append({"first": "A", "second": "B"})
    p["rules"] = {"wrong_way": {"enable": True},
                  "no_uturn": {"enable": False}}
    warns = validate_polygons(cfg)
    assert any("no_uturn=false" in w for w in warns), warns
    print("pair-no-medial-warn OK")


def test_next_id_across_scopes():
    """next_id dem ca nested: top-level rong van khong tai dung id."""
    cfg = blank()
    p = add_polygon(cfg, [(0, 0), (200, 0), (200, 200), (0, 200)],
                    kind="directional")
    a = add_directed(cfg, (0, 0), (100, 0))   # L1 top-level
    cfg["lines"].remove(a)
    p.setdefault("lines", []).append(a)       # auto-attach vao polygon
    b = add_directed(cfg, (0, 50), (100, 50))  # phai la L2, khong phai L1
    assert b["id"] == "L2", b
    try:
        add_directed(cfg, (0, 60), (100, 60), lid="L1")
        raise AssertionError("trung id nested phai loi")
    except ValueError as e:
        assert "Trung id" in str(e)
    print("next_id across scopes OK")


def test_remove_tiny_lines():
    cfg = blank()
    add_directed(cfg, (0, 0), (200, 0))          # L1 dai -> giu
    add_directed(cfg, (10, 10), (13, 12))        # L2 ~3.6px -> xoa
    p = add_polygon(cfg, [(0, 0), (200, 0), (200, 200), (0, 200)],
                    kind="directional")
    p["lines"].append({"id": "N1", "p1": [0, 0], "p2": [100, 0],
                       "allowed_sign": 1})       # dai -> giu
    p["lines"].append({"id": "N2", "p1": [5, 5], "p2": [7, 6],
                       "allowed_sign": 1})       # ~2.2px -> xoa
    removed = remove_tiny_lines(cfg)
    assert sorted(removed) == ["L2", "N2"], removed
    assert [l["id"] for l in cfg["lines"]] == ["L1"]
    assert [l["id"] for l in p["lines"]] == ["N1"]
    assert remove_tiny_lines(cfg) == []  # idempotent
    print("remove_tiny_lines OK")


if __name__ == "__main__":
    test_add_and_ids()
    test_flip_and_errors()
    test_pair_and_delete_cascade()
    test_pair_same_scope()
    test_finalize_zone()
    test_pair_no_medial_warn()
    test_next_id_across_scopes()
    test_remove_tiny_lines()
    test_validate_and_roundtrip()
    test_legacy_config()
    print("ALL LINE-CONFIG TESTS PASSED")

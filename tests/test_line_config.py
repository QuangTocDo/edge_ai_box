"""Unit test logic config lines (headless).
Chay tu project root: python -m tests.test_line_config
"""
import tempfile
from pathlib import Path

from src.line_config import (add_directed, add_divider, add_pair, delete_line,
                             delete_pair, flip_line, load_config, next_id,
                             save_config, validate)


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
    cfg = load_config("camera_config.yaml")
    ids = {ln["id"] for ln in cfg["lines"]}
    assert {"L_NB", "L_SB", "L_medial"} <= ids, ids
    assert cfg["uturn_pairs"], "mat pairs cu"
    assert validate(cfg) == [], validate(cfg)
    print("legacy config OK:", sorted(ids))


if __name__ == "__main__":
    test_add_and_ids()
    test_flip_and_errors()
    test_pair_and_delete_cascade()
    test_validate_and_roundtrip()
    test_legacy_config()
    print("ALL LINE-CONFIG TESTS PASSED")

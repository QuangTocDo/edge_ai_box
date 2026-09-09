"""Logic quan ly lines + uturn_pairs trong camera_config.yaml (khong GUI).

Schema (giong cu, pipeline/rules doc truc tiep):
- directed: {id, p1:[x,y], p2:[x,y], allowed_sign: +1|-1}
- divider:  {id, p1, p2, role: divider}
- uturn_pairs: [{first, second, medial}]
"""
from pathlib import Path

import yaml

DIVIDER = "divider"


def role_of(ln):
    return ln.get("role", "directed")


def load_config(path):
    path = Path(path)
    if not path.exists():
        return {"lines": [], "uturn_pairs": []}
    cfg = yaml.safe_load(open(path)) or {}
    cfg.setdefault("lines", [])
    cfg.setdefault("uturn_pairs", [])
    return cfg


def save_config(cfg, path):
    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)


def get_lines(cfg):
    return cfg.setdefault("lines", [])


def get_pairs(cfg):
    return cfg.setdefault("uturn_pairs", [])


def find_line(cfg, lid):
    for ln in get_lines(cfg):
        if ln["id"] == lid:
            return ln
    return None


def next_id(cfg, prefix="L"):
    used = {ln["id"] for ln in get_lines(cfg)}
    i = 1
    while f"{prefix}{i}" in used:
        i += 1
    return f"{prefix}{i}"


def add_directed(cfg, p1, p2, allowed_sign=1, lid=None):
    lid = lid or next_id(cfg)
    if find_line(cfg, lid):
        raise ValueError(f"Trung id: {lid}")
    ln = {"id": lid, "p1": [int(p1[0]), int(p1[1])],
          "p2": [int(p2[0]), int(p2[1])], "allowed_sign": int(allowed_sign)}
    get_lines(cfg).append(ln)
    return ln


def add_divider(cfg, p1, p2, lid=None):
    lid = lid or next_id(cfg)
    if find_line(cfg, lid):
        raise ValueError(f"Trung id: {lid}")
    ln = {"id": lid, "p1": [int(p1[0]), int(p1[1])],
          "p2": [int(p2[0]), int(p2[1])], "role": DIVIDER}
    get_lines(cfg).append(ln)
    return ln


def flip_line(cfg, lid):
    ln = find_line(cfg, lid)
    if ln is None:
        raise ValueError(f"Khong thay line: {lid}")
    if role_of(ln) == DIVIDER:
        raise ValueError(f"{lid} la divider, khong co chieu")
    ln["allowed_sign"] = -ln.get("allowed_sign", 1)
    return ln["allowed_sign"]


def delete_line(cfg, lid):
    lines = get_lines(cfg)
    ln = find_line(cfg, lid)
    if ln is None:
        raise ValueError(f"Khong thay line: {lid}")
    lines.remove(ln)
    dropped = [p for p in get_pairs(cfg)
               if lid in (p.get("first"), p.get("second"), p.get("medial"))]
    for p in dropped:
        get_pairs(cfg).remove(p)
    return ln, dropped


def add_pair(cfg, first, second, medial):
    f1, f2, fm = (find_line(cfg, x) for x in (first, second, medial))
    if f1 is None or f2 is None or fm is None:
        missing = [x for x, f in ((first, f1), (second, f2), (medial, fm))
                   if f is None]
        raise ValueError(f"Chua ve: {missing}")
    if role_of(f1) == DIVIDER or role_of(f2) == DIVIDER:
        raise ValueError("first/second phai la line co chieu")
    if role_of(fm) != DIVIDER:
        raise ValueError("medial phai la divider")
    pr = {"first": first, "second": second, "medial": medial}
    if pr in get_pairs(cfg):
        raise ValueError("Pair da ton tai")
    get_pairs(cfg).append(pr)
    return pr


def delete_pair(cfg, idx):
    pairs = get_pairs(cfg)
    if not (0 <= idx < len(pairs)):
        raise ValueError(f"Pair #{idx} khong ton tai")
    return pairs.pop(idx)


def validate(cfg):
    """Tra ve list canh bao (rong = sach). Pipeline van chay duoc."""
    warns = []
    ids = [ln["id"] for ln in get_lines(cfg)]
    if len(ids) != len(set(ids)):
        warns.append("Trung id line")
    for ln in get_lines(cfg):
        if role_of(ln) != DIVIDER and ln.get("allowed_sign", 1) not in (1, -1):
            warns.append(f"{ln['id']}: allowed_sign la")
    for p in get_pairs(cfg):
        for k in ("first", "second", "medial"):
            if find_line(cfg, p.get(k)) is None:
                warns.append(f"Pair thieu line: {k}={p.get(k)}")
    if not get_lines(cfg):
        warns.append("Chua co line nao (pipeline chay nhung khong rule nao kich hoat)")
    return warns

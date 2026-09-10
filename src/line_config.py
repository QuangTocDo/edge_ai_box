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
    ln, _ = find_line_any(cfg, lid)
    if ln is None:
        raise ValueError(f"Khong thay line: {lid}")
    if role_of(ln) == DIVIDER:
        raise ValueError(f"{lid} la divider, khong co chieu")
    ln["allowed_sign"] = -ln.get("allowed_sign", 1)
    return ln["allowed_sign"]


def delete_line(cfg, lid):
    ln, owner = find_line_any(cfg, lid)
    if ln is None:
        raise ValueError(f"Khong thay line: {lid}")
    (owner.get("lines", []) if owner else get_lines(cfg)).remove(ln)
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
    if not get_lines(cfg) and not get_polygons(cfg):
        warns.append("Chua co line/polygon nao (pipeline chay nhung khong rule nao kich hoat)")
    return warns


# ---------------- Polygons (zone duong cam / ROI) ----------------

KNOWN_HANDLERS = {"wrong_way", "no_uturn", "no_entry_road",
                  "red_light", "stop_line", "presence"}


def get_polygons(cfg):
    return cfg.setdefault("polygons", [])


def find_polygon(cfg, pid):
    for p in get_polygons(cfg):
        if p["id"] == pid:
            return p
    return None


def next_poly_id(cfg, prefix="POLY"):
    used = {p["id"] for p in get_polygons(cfg)}
    i = 1
    while f"{prefix}_{i}" in used:
        i += 1
    return f"{prefix}_{i}"


def add_polygon(cfg, vertices, kind="banned", pid=None, handler=None, **fields):
    """Tao polygon. banned: handler=[no_entry_road] + fields
    (banned_classes, active_hours, dwell_s). directional: handler tuy chon."""
    from .geometry import polygon_valid
    if not polygon_valid(vertices):
        raise ValueError("Polygon can >=3 dinh va dien tich > 0")
    pid = pid or next_poly_id(cfg)
    if find_polygon(cfg, pid):
        raise ValueError(f"Trung id polygon: {pid}")
    if kind not in ("directional", "banned"):
        raise ValueError(f"kind la: {kind}")
    poly = {"id": pid, "kind": kind,
            "polygon": [[int(x), int(y)] for x, y in vertices],
            "lines": [],
            "handler": handler or (["no_entry_road"] if kind == "banned"
                                   else ["wrong_way", "no_uturn"])}
    for h in poly["handler"]:
        if h not in KNOWN_HANDLERS:
            raise ValueError(f"handler la: {h}")
    if kind == "banned":
        poly["banned_classes"] = list(fields.get("banned_classes", []))
        poly["active_hours"] = list(fields.get("active_hours", []))
        poly["dwell_s"] = float(fields.get("dwell_s", 2.0))
        poly["entry_lines"] = list(fields.get("entry_lines", []))
    get_polygons(cfg).append(poly)
    return poly


def delete_polygon(cfg, pid):
    poly = find_polygon(cfg, pid)
    if poly is None:
        raise ValueError(f"Khong thay polygon: {pid}")
    get_polygons(cfg).remove(poly)
    nested = {ln["id"] for ln in poly.get("lines", [])}
    nested |= {e["id"] for e in poly.get("entry_lines", [])}
    dropped = [p for p in get_pairs(cfg)
               if pid in () or p.get("first") in nested
               or p.get("second") in nested or p.get("medial") in nested]
    for p in dropped:
        get_pairs(cfg).remove(p)
    return poly, dropped


def add_nested_line(cfg, pid, line):
    """Gan line co san (dict) vao polygon. Id phai duy nhat toan cuc."""
    poly = find_polygon(cfg, pid)
    if poly is None:
        raise ValueError(f"Khong thay polygon: {pid}")
    if find_line_any(cfg, line["id"])[0] is not None:
        raise ValueError(f"Trung id line: {line['id']}")
    poly.setdefault("lines", []).append(line)
    return line


def add_entry_line(cfg, pid, p1, p2, lid=None):
    """Line cua vao (khong can allowed_sign: huong vao suy tu centroid)."""
    poly = find_polygon(cfg, pid)
    if poly is None:
        raise ValueError(f"Khong thay polygon: {pid}")
    used = {e["id"] for e in poly.get("entry_lines", [])}
    used |= {ln["id"] for ln in iter_all_lines(cfg)}
    lid = lid or _next_entry_id(used)
    if lid in used:
        raise ValueError(f"Trung id entry line: {lid}")
    e = {"id": lid, "p1": [int(p1[0]), int(p1[1])],
         "p2": [int(p2[0]), int(p2[1])]}
    poly.setdefault("entry_lines", []).append(e)
    return e


def _next_entry_id(used):
    i = 1
    while f"ENTRY_{i}" in used:
        i += 1
    return f"ENTRY_{i}"


def iter_all_lines(cfg):
    """Tat ca lines: top-level + nested trong polygons."""
    for ln in get_lines(cfg):
        yield ln
    for p in get_polygons(cfg):
        for ln in p.get("lines", []):
            yield ln


def find_line_any(cfg, lid):
    """(line, polygon_chua|None). Tim ca top-level + nested."""
    for ln in get_lines(cfg):
        if ln["id"] == lid:
            return ln, None
    for p in get_polygons(cfg):
        for ln in p.get("lines", []):
            if ln["id"] == lid:
                return ln, p
    return None, None


def validate_polygons(cfg):
    from .geometry import polygon_valid, parse_window
    warns = []
    ids = [ln["id"] for ln in iter_all_lines(cfg)]
    if len(ids) != len(set(ids)):
        warns.append("Trung id line (tinh ca nested)")
    for p in get_polygons(cfg):
        if not polygon_valid(p.get("polygon", [])):
            warns.append(f"{p.get('id')}: polygon khong hop le")
        for h in p.get("handler", []):
            if h not in KNOWN_HANDLERS:
                warns.append(f"{p.get('id')}: handler la {h}")
        if p.get("kind") == "banned":
            if not p.get("banned_classes"):
                warns.append(f"{p.get('id')}: chua co banned_classes")
            for w in p.get("active_hours", []):
                try:
                    parse_window(w)
                except ValueError as e:
                    warns.append(f"{p.get('id')}: {e}")
    for pr in get_pairs(cfg):
        for k in ("first", "second", "medial"):
            if find_line_any(cfg, pr.get(k))[0] is None:
                warns.append(f"Pair thieu line: {k}={pr.get(k)}")
    return warns

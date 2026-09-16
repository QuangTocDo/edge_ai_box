"""Logic quan ly lines + uturn_pairs trong no_way.yaml (khong GUI).

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
    used = {ln["id"] for ln in iter_all_lines(cfg)}
    i = 1
    while f"{prefix}{i}" in used:
        i += 1
    return f"{prefix}{i}"


def add_directed(cfg, p1, p2, allowed_sign=1, lid=None):
    lid = lid or next_id(cfg)
    if find_line_any(cfg, lid)[0] is not None:
        raise ValueError(f"Trung id: {lid}")
    ln = {"id": lid, "p1": [int(p1[0]), int(p1[1])],
          "p2": [int(p2[0]), int(p2[1])], "allowed_sign": int(allowed_sign)}
    get_lines(cfg).append(ln)
    return ln


def add_divider(cfg, p1, p2, lid=None):
    lid = lid or next_id(cfg)
    if find_line_any(cfg, lid)[0] is not None:
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


def _all_pair_lists(cfg):
    yield get_pairs(cfg)
    for p in get_polygons(cfg):
        yield p.setdefault("uturn_pairs", [])


def delete_line(cfg, lid):
    ln, owner = find_line_any(cfg, lid)
    if ln is None:
        raise ValueError(f"Khong thay line: {lid}")
    (owner.get("lines", []) if owner else get_lines(cfg)).remove(ln)
    dropped = []
    for lst in _all_pair_lists(cfg):
        for p in [x for x in lst if lid in (x.get("first"), x.get("second"),
                                            x.get("medial"))]:
            lst.remove(p)
            dropped.append(p)
    return ln, dropped


def line_length(ln):
    """Do dai doan thang cua line (px)."""
    (x1, y1), (x2, y2) = ln["p1"], ln["p2"]
    return ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5


def remove_tiny_lines(cfg, min_px=10.0):
    """Xoa lines ngan hon min_px (rac tu double-click cham).
    Tra ve [ids da xoa]. Pair lien quan rot theo nhu delete_line."""
    tiny = [ln["id"] for ln in iter_all_lines(cfg)
            if line_length(ln) < min_px]
    for lid in tiny:
        delete_line(cfg, lid)
    return tiny


def add_pair(cfg, first, second, medial=None):
    """Tao pair U-turn: cat first dung chieu -> second dung chieu.
    first/second phai chung scope (tat ca top-level hoac cung 1 polygon).
    medial (ten line divider) la DI SAN cu: chap nhan de tuong thich,
    rule hien tai bo qua."""
    f1, o1 = find_line_any(cfg, first)
    f2, o2 = find_line_any(cfg, second)
    if None in (f1, f2):
        missing = [x for x, f in ((first, f1), (second, f2)) if f is None]
        raise ValueError(f"Chua ve: {missing}")
    if role_of(f1) == DIVIDER or role_of(f2) == DIVIDER:
        raise ValueError("first/second phai la line co chieu")
    if o1 is not o2:
        raise ValueError("first/second phai chung 1 polygon "
                         "(hoac ca hai top-level)")
    fm = None
    if medial is not None:
        fm, _ = find_line_any(cfg, medial)
        if fm is None:
            raise ValueError(f"Chua ve: [{medial}]")
        if role_of(fm) != DIVIDER:
            raise ValueError("medial phai la divider")
    pr = {"first": first, "second": second}
    if medial is not None:
        pr["medial"] = medial  # di san: rule bo qua, strip_medial.py se don
    target = o1.setdefault("uturn_pairs", []) if o1 is not None \
        else get_pairs(cfg)
    if pr in target:
        raise ValueError("Pair da ton tai")
    target.append(pr)
    return pr


def delete_pair(cfg, idx):
    pairs = get_pairs(cfg)
    if not (0 <= idx < len(pairs)):
        raise ValueError(f"Pair #{idx} khong ton tai")
    return pairs.pop(idx)


def finalize_zone(cfg, poly_id, no_uturn):
    """Chot zone sau flow ve gop: wrong_way luon bat; no_uturn tuy flag.

    - Dat rules.wrong_way.enable=True, rules.no_uturn.enable=bool(no_uturn).
    - Neu no_uturn: lay 2 directed lines dau tien trong polygon, tu sinh
      ca 2 pairs nguoc chieu (A->B va B->A). Goi lai khong tao trung.
    Tra ve {"polygon": pid, "lines": [...], "pairs": [...]}.
    """
    poly = find_polygon(cfg, poly_id)
    if poly is None:
        raise ValueError(f"Khong thay polygon: {poly_id}")
    directed = [ln for ln in poly.get("lines", [])
                if role_of(ln) != "divider"]
    if len(directed) < 2:
        raise ValueError(f"Polygon {poly_id} can >=2 lines co chieu "
                         f"(dang co {len(directed)})")
    rules = poly.setdefault("rules", {})
    rules["wrong_way"] = {"enable": True}
    rules["no_uturn"] = {"enable": bool(no_uturn)}
    made = []
    if no_uturn:
        a, b = directed[0]["id"], directed[1]["id"]
        for first, second in ((a, b), (b, a)):
            try:
                made.append(add_pair(cfg, first, second))
            except ValueError as e:
                if "da ton tai" not in str(e):
                    raise
    return {"polygon": poly_id,
            "lines": [ln["id"] for ln in directed[:2]],
            "pairs": [(p["first"], p["second"]) for p in made]}


def validate(cfg):
    """Tra ve list canh bao (rong = sach). Pipeline van chay duoc."""
    warns = []
    ids = [ln["id"] for ln in iter_all_lines(cfg)]
    if len(ids) != len(set(ids)):
        warns.append("Trung id line (tinh ca nested)")
    for ln in get_lines(cfg):
        if role_of(ln) != DIVIDER and ln.get("allowed_sign", 1) not in (1, -1):
            warns.append(f"{ln['id']}: allowed_sign la")
    for p in get_pairs(cfg):
        for k in ("first", "second"):
            if find_line_any(cfg, p.get(k))[0] is None:
                warns.append(f"Pair thieu line: {k}={p.get(k)}")
        if p.get("medial") is not None and \
                find_line_any(cfg, p.get("medial"))[0] is None:
            warns.append(f"Pair thieu medial cu: {p.get('medial')}")
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
    if kind not in ("directional", "banned", "intersection"):
        raise ValueError(f"kind la: {kind}")
    if handler is None:
        handler = ["no_entry_road"] if kind == "banned" else \
            ([] if kind == "intersection" else ["wrong_way", "no_uturn"])
    poly = {"id": pid, "kind": kind,
            "polygon": [[int(x), int(y)] for x, y in vertices],
            "lines": [],
            "handler": handler}
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
    dropped = []
    for lst in _all_pair_lists(cfg):
        for p in [x for x in lst if x.get("first") in nested
                  or x.get("second") in nested or x.get("medial") in nested]:
            lst.remove(p)
            dropped.append(p)
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
        for k in ("first", "second"):
            if find_line_any(cfg, pr.get(k))[0] is None:
                warns.append(f"Pair thieu line: {k}={pr.get(k)}")
        if pr.get("medial") is not None and \
                find_line_any(cfg, pr.get("medial"))[0] is None:
            warns.append(f"Pair thieu medial cu: {pr.get('medial')}")
    for p in get_polygons(cfg):
        if p.get("uturn_pairs") and not (p.get("rules") or {}).get(
                "no_uturn", {}).get("enable", True):
            warns.append(f"{p.get('id')}: co pair nhung no_uturn=false "
                         "(pair thua, rule khong chay)")
    return warns


def find_signal(cfg, sid):
    """Tim signal theo id trong cfg['signals']."""
    for s in cfg.get("signals", []):
        if s.get("id") == sid:
            return s
    return None


def delete_signal(cfg, sid):
    """Xoa signal khoi cfg['signals'], go signal_id khoi tat ca cac line dang tro toi."""
    sigs = cfg.get("signals", [])
    target = None
    for s in sigs:
        if s.get("id") == sid:
            target = s
            break
    if target is None:
        raise ValueError(f"Khong tim thay signal: {sid}")
    sigs.remove(target)
    unlinked = []
    for ln in iter_all_lines(cfg):
        if ln.get("signal_id") == sid:
            ln.pop("signal_id", None)
            unlinked.append(ln["id"])
    return target, unlinked

import math
"""Nap + chuan hoa + validate config camera (base + override, rules theo polygon).

Schema:
- File camera tuy chon `base: <path tuong doi>` -> deep-merge (dict gop,
  list thay toan bo, camera thang).
- Global `wrong_way: / no_uturn: / no_entry_road:` vua la params mac dinh
  vua co `enable:` (mac dinh true).
- Moi polygon co the `rules: {ten_rule: {enable:, ...override}}`._
- `lines:` phang + `uturn_pairs:` global tu boc vao polygon implicit
  `__GLOBAL__` (khop moi track) de config cu chay y nhu cu.\
- Ngoai moi polygon explicit = hop le (skip), khong chay rule.
"""
from pathlib import Path

import yaml

from ..business.rules import PLANNED_TYPES, known_types
from ..utils.constants import HOMOGRAPHY_MAX_ERR_M
from ..utils.geometry import parse_window

RULES = known_types()
# Biet ten nhung chua co class Rule -> enable:true chi warn, khong crash.
UNIMPLEMENTED = PLANNED_TYPES
IMPLICIT_ID = "__GLOBAL__"


class ConfigError(Exception):
    pass


def deep_merge(base, over):
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v  # list/scalar: thay toan bo
    return out


def load_camera_config(path):
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    base = cfg.pop("base", None)
    if base:
        bpath = (path.parent / base).resolve()
        if not bpath.exists():
            raise ConfigError(f"Khong thay base config: {bpath}")
        with open(bpath, "r", encoding="utf-8") as f:
            cfg = deep_merge(yaml.safe_load(f) or {}, cfg)
    cfg["_cfg_path"] = str(path.resolve())
    from .validator import validate_config_schema, ConfigValidationError
    try:
        schema_warnings = validate_config_schema(cfg)
    except ConfigValidationError as e:
        raise ConfigError(str(e))
    normalize(cfg)
    warnings = schema_warnings + validate(cfg)
    resolve_plan(cfg)
    return cfg, warnings


def normalize(cfg):
    """Boc lines/pairs phang vao polygon implicit. Dich `handler:` cu."""
    cfg.setdefault("polygons", [])
    cfg.setdefault("lines", [])
    cfg.setdefault("uturn_pairs", [])
    for name in RULES:
        cfg.setdefault(name, {})
    # Chuan hoa alias rule global: red_light -> red_light_running, stop_line -> stop_line_violation
    if "stop_line" in cfg:
        cfg.setdefault("stop_line_violation", {})
        cfg["stop_line_violation"] = {**cfg.pop("stop_line"), **cfg["stop_line_violation"]}
    if "red_light" in cfg:
        cfg.setdefault("red_light_running", {})
        cfg["red_light_running"] = {**cfg.pop("red_light"), **cfg["red_light_running"]}

    for p in cfg["polygons"]:
        # dich legacy `handler: [wrong_way, ...]` -> rules enable map
        if "handler" in p and "rules" not in p:
            p["rules"] = {r: {"enable": True} for r in p.pop("handler")}
        p.setdefault("rules", {})
        # Chuan hoa alias rule trong polygon
        rules = p["rules"]
        if "stop_line" in rules and "stop_line_violation" not in rules:
            rules["stop_line_violation"] = rules.pop("stop_line")
        if "red_light" in rules and "red_light_running" not in rules:
            rules["red_light_running"] = rules.pop("red_light")
        p.setdefault("lines", [])

    # Tu dong gan lines top-level co signal_id vao polygon co rule red/stop neu line o gan hoac chi co 1 polygon
    from ..utils.geometry import line_near_or_in_polygon
    flat_lines = cfg.get("lines") or []
    remaining_flat = []
    for ln in flat_lines:
        attached_poly = None
        if ln.get("signal_id"):
            red_polys = [p for p in cfg["polygons"] if p.get("id") != IMPLICIT_ID and (
                (p.get("rules") or {}).get("red_light_running") or
                (p.get("rules") or {}).get("stop_line_violation"))]
            for p in red_polys:
                if line_near_or_in_polygon(ln["p1"], ln["p2"], p.get("polygon") or [], max_dist=80.0):
                    attached_poly = p
                    break
            if attached_poly is None and len(red_polys) == 1:
                attached_poly = red_polys[0]
        if attached_poly is not None:
            attached_poly.setdefault("lines", []).append(ln)
        else:
            remaining_flat.append(ln)
    cfg["lines"] = remaining_flat

    flat_lines = cfg.get("lines") or []
    flat_pairs = cfg.get("uturn_pairs") or []
    if flat_lines or flat_pairs:
        glob = {"id": IMPLICIT_ID, "kind": "directional", "polygon": None,
                "lines": flat_lines, "handler": [], "rules": {}}
        cfg["polygons"].insert(0, glob)
        cfg["lines"] = []
        # pairs global giu nguyen key de pipeline/draw tool cu doc duoc,
        # nhung thuoc ve implicit poly (khop moi track).
        glob["_pairs"] = flat_pairs
        cfg["uturn_pairs"] = []

    for p in cfg["polygons"]:
        rules = p.get("rules") or {}
        r = {k: (v or {}).get("enable", True) for k, v in rules.items()}
        # Tu dong alias speed_limit_kmh -> limit_kmh
        sp = (p.get("rules") or {}).get("speeding")
        if isinstance(sp, dict) and "speed_limit_kmh" in sp:
            sp["limit_kmh"] = sp.pop("speed_limit_kmh")

        # Tu dong tao directed line cho wrong_way neu da co road_dir va polygon ma chua co line
        if r.get("wrong_way") and not p.get("lines") and p.get("road_dir") and p.get("polygon"):
            poly_pts = p["polygon"]
            if len(poly_pts) >= 3:
                cx = sum(pt[0] for pt in poly_pts) / len(poly_pts)
                cy = sum(pt[1] for pt in poly_pts) / len(poly_pts)
                dx, dy = float(p["road_dir"][0]), float(p["road_dir"][1])
                px, py = dy, -dx
                span = 80.0
                p1 = [round(cx - px * span, 1), round(cy - py * span, 1)]
                p2 = [round(cx + px * span, 1), round(cy + py * span, 1)]
                p["lines"] = [{
                    "id": f"LINE_{p['id']}",
                    "p1": p1,
                    "p2": p2,
                    "allowed_sign": 1,
                }]
        # Tu dong gan signal_id neu chi co 1 signal va line chua co signal_id
        if r.get("red_light_running") or r.get("stop_line_violation"):
            sigs = cfg.get("signals", [])
            if len(sigs) == 1:
                default_sid = sigs[0]["id"]
                for ln in p["lines"]:
                    if ln.get("role") != "divider" and not ln.get("signal_id"):
                        ln["signal_id"] = default_sid
        if p.get("kind") == "banned":
            p.setdefault("entry_lines", [])
            p.setdefault("banned_classes", [])
            p.setdefault("active_hours", [])
            p.setdefault("dwell_s", 2.0)
        if p.get("homography") is not None and p["id"] != IMPLICIT_ID:
            p["_H"], p["_H_error"], p["_road_dir"] = _build_polygon_H(cfg, p)
        wins = []
        for w in p.get("active_hours", []):
            try:
                wins.append(parse_window(w))
            except ValueError as e:
                raise ConfigError(f"Polygon {p.get('id')}: {e}")
        p["_windows"] = wins


def _poly_lines(pid, cfg):
    for p in cfg["polygons"]:
        if p["id"] == pid:
            return p.get("lines", [])
    return None


def _build_polygon_H(cfg, poly):
    """Build + validate H cho speed polygon. Loi -> ConfigError ro rang."""
    from ..utils.homography import build_H
    pid = poly.get("id")
    h = poly.get("homography") or {}
    src, dst = h.get("src"), h.get("dst")
    if not src or not dst:
        raise ConfigError(
            f"{pid}: speeding can 'homography: {{src: [...], dst: [...]}}' "
            "toi thieu 4 cap diem (xem tool hieu chuan phim c)")
    try:
        H, inl, err = build_H(src, dst)
    except ValueError as e:
        raise ConfigError(f"{pid}: homography loi: {e}")
    max_err = float(poly.get("homography_max_err_m",
                             cfg.get("speeding", {}).get(
                                 "homography_max_err_m",
                                 HOMOGRAPHY_MAX_ERR_M)))\
        if poly.get("homography_max_err_m") is not None else HOMOGRAPHY_MAX_ERR_M
    if err > max_err:
        raise ConfigError(
            f"{pid}: homography reproj error {err:.2f}m > {max_err:.2f}m, "
            "chup lai diem calibration")
    rdir = poly.get("road_dir") or [0.0, 1.0]
    return H, err, list(rdir)


def validate(cfg):
    """Fail-fast loi cau truc. Tra ve warnings (rule chua implement)."""
    from ..business.rules import RULE_REGISTRY
    warns = []
    for name in RULES:
        for k in (cfg.get(name) or {}):
            if k != "enable" and k not in RULE_REGISTRY[name].PARAMS:
                raise ConfigError(
                    f"global '{name}': param la '{k}' "
                    f"(hop le: {sorted(RULE_REGISTRY[name].PARAMS)})\")")
    pids = [p.get("id") for p in cfg["polygons"]]
    if len(pids) != len(set(pids)):
        raise ConfigError("Trung id polygon")
    sids = [s.get("id") for s in cfg.get("signals", [])]
    if len(sids) != len(set(sids)):
        raise ConfigError("Trung id signal")
    for s in cfg.get("signals", []):
        roi = s.get("roi", [])
        if len(roi) != 4 or not all(isinstance(v, (int, float)) for v in roi):
            raise ConfigError(f"Signal {s.get('id')}: roi phai co 4 so")
    lids = []
    for p in cfg["polygons"]:
        lids += [ln.get("id") for ln in p.get("lines", [])]
    lids += [ln.get("id") for ln in cfg.get("lines", [])]
    if len(lids) != len(set(lids)):
        raise ConfigError("Trung id line (tinh ca nested)")
    all_ids = set(lids)
    for p in cfg["polygons"]:
        pid = p.get("id")
        for rname, rblock in (p.get("rules") or {}).items():
            if rname in UNIMPLEMENTED:
                if (rblock or {}).get("enable", False):
                    warns.append(f"{pid}: rule '{rname}' chua implement, bo qua")
                continue
            if rname not in RULES:
                raise ConfigError(f"{pid}: ten rule la '{rname}'")
            for k in (rblock or {}):
                if k != "enable" and k not in RULE_REGISTRY[rname].PARAMS:
                    raise ConfigError(
                        f"{pid}: param la '{rname}.{k}' "
                        f"(hop le: {sorted(RULE_REGISTRY[rname].PARAMS)})\")")
        r = {k: (v or {}).get("enable", True)
             for k, v in (p.get("rules") or {}).items() if k in RULES}
        ndir = [ln for ln in p.get("lines", [])
                if ln.get("role") != "divider"]
        if p.get("kind") == "trajectory" and r.get("no_uturn"):
            if not p.get("uturn_pairs"):
                raise ConfigError(f"{pid}: no_uturn bat nhung thieu uturn_pairs")
        if p.get("kind") != "trajectory" and r.get("no_uturn") \
                and not p.get("uturn_pairs"):
            warns.append(f"{pid}: no_uturn bat nhung uturn_pairs rong "
                         "-> rule khong bao gio ban (them pair trong tool phim 3)")
        if p.get("kind") == "banned" and r.get("no_entry_road"):
            if not p.get("banned_classes"):
                raise ConfigError(f"{pid}: no_entry bat nhung thieu banned_classes")
            from ..utils.geometry import polygon_valid
            if not polygon_valid(p.get("polygon") or []):
                raise ConfigError(f"{pid}: polygon khong hop le")
        if r.get("wrong_way") and not ndir and p["id"] != IMPLICIT_ID:
            raise ConfigError(f"{pid}: wrong_way bat nhung thieu directed line")
        if r.get("speeding") and p.get("_H") is None \
                and p["id"] != IMPLICIT_ID:
            raise ConfigError(
                f"{pid}: speeding bat nhung chua hieu chuan homography "
                "(them 'homography: {{src, dst}}' + 'road_dir', "
                "xem tool hieu chuan phim c)")
        if r.get("red_light_running") or r.get("stop_line_violation") or r.get("stop_line"):
            sig_lines = [ln for ln in ndir if ln.get("signal_id")]
            if not sig_lines:
                raise ConfigError(
                    f"{pid}: red/stop bat nhung khong co stop-line nao "
                    "co signal_id")
            cfg_sigs = {s.get("id") for s in cfg.get("signals", [])}
            if not cfg_sigs:
                raise ConfigError(
                    f"{pid}: red/stop bat nhung thieu muc 'signals' "
                    "trong config")
            for ln in sig_lines:
                if ln.get("signal_id") not in cfg_sigs:
                    raise ConfigError(
                        f"{pid}: line {ln['id']} tro toi signal la "
                        f"'{ln.get('signal_id')}'")
    for pr in cfg.get("uturn_pairs", []):
        _check_pair(pr, None, all_ids)
    for p in cfg["polygons"]:
        mine = {ln.get("id") for ln in p.get("lines", [])}
        for pr in list(p.get("uturn_pairs", [])) + list(p.get("_pairs", [])):
            _check_pair(pr, p["id"], all_ids, mine)
    return warns


def _check_pair(pr, pid, all_ids, mine=None):
    where = pid or "global"
    for k in ("first", "second"):
        lid = pr.get(k)
        if lid not in all_ids:
            raise ConfigError(f"Pair {where}: thieu line {k}={lid}")
        if mine is not None and lid not in mine:
            raise ConfigError(f"Pair {where}: line {k}={lid} khac polygon")
    med = pr.get("medial")
    if med is not None and med not in all_ids:
        raise ConfigError(f"Pair {where}: thieu medial={med}")


def effective_params(cfg, poly, rule):
    """Params hieu dung = global override boi polygon (bo key enable)."""
    base = {k: v for k, v in cfg.get(rule, {}).items() if k != "enable"}
    over = (poly.get("rules") or {}).get(rule) or {}
    over = {k: v for k, v in over.items() if k != "enable"}
    return {**base, **over}


def is_enabled(cfg, poly, rule):
    poly_rules = poly.get("rules") or {}
    if rule in poly_rules:
        return bool(poly_rules[rule].get("enable", True))

    # Cac rule dac thu ve vung/thiet bi chi ap dung khi duoc khai bao truc tiep trong polygon
    if rule in ("no_parking", "no_gathering", "speeding", "red_light_running", "stop_line_violation"):
        return False

    g = cfg.get(rule, {}).get("enable", True)
    return bool(g)

def resolve_plan(cfg):
    """Dung san _plan: [{polygon|None, rule, params, lines, pairs}]."""
    plan = []
    for p in cfg["polygons"]:
        lines = p.get("lines", [])
        for rule in RULES:
            if not is_enabled(cfg, p, rule):
                continue
            if rule == "wrong_way":
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": [ln for ln in lines
                                       if ln.get("role") != "divider"],
                             "pairs": []})
            elif rule == "no_uturn":
                pairs = list(p.get("uturn_pairs", []))\
                    + list(p.get("_pairs", []))
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": lines, "pairs": pairs})
            elif rule == "no_entry_road":
                if p.get("kind") != "banned" or p["id"] == IMPLICIT_ID:
                    continue
                plan.append({"polygon": p, "rule": rule,
                              "params": effective_params(cfg, p, rule),
                              "lines": [], "pairs": []})
            elif rule == "no_parking":
                if p["id"] == IMPLICIT_ID or not p.get("polygon"):
                    continue
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": [], "pairs": []})
            elif rule == "no_gathering":
                if p["id"] == IMPLICIT_ID or not p.get("polygon"):
                    continue
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": [], "pairs": []})
            elif rule == "speeding":
                if p["id"] == IMPLICIT_ID or p.get("_H") is None:
                    continue
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": [], "pairs": []})
            elif rule in ("red_light_running", "stop_line_violation", "stop_line"):
                sig_lines = [ln for ln in lines
                             if ln.get("signal_id") and ln.get("role") != "divider"]
                if p["id"] == IMPLICIT_ID:
                    if sig_lines:
                        plan.append({"polygon": p, "rule": rule,
                                     "params": effective_params(cfg, p, rule),
                                     "lines": sig_lines,
                                     "pairs": [],
                                     "clearance": []})
                    continue
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": [ln for ln in lines
                                       if ln.get("role") != "divider"],
                             "pairs": [],
                             "clearance": _resolve_clearance(
                                 cfg, p, effective_params(cfg, p, rule))})
    cfg["_plan"] = plan


def _resolve_clearance(cfg, poly, params):
    """Giai quyet intersection_clearance_zone (str hoac list id)
    thanh list polygon objects. Khong co -> []."""
    ref = params.get("intersection_clearance_zone")
    if not ref:
        return []
    ids = [ref] if isinstance(ref, str) else list(ref)
    by_id = {str(p.get("id")): p for p in cfg.get("polygons", [])}
    out = []
    for i in ids:
        s = str(i).strip()
        if s in by_id:
            out.append(by_id[s])
        elif f"POLY_{s}" in by_id:
            out.append(by_id[f"POLY_{s}"])
        else:
            raise ConfigError(
                f"{poly.get('id')}: clearance zone la '{i}'. Hop le: {sorted(by_id.keys())}")
    return out


def entries_for(bc, plan, containing_fn, track=None):
    """Cac plan entry ap dung cho track: polygon None/implicit = moi track,
    polygon explicit phai chua Bottom-Center hoac clearance. Tra ve [] = skip (hop le)."""
    out = []
    for e in plan:
        p = e["polygon"]
        if p is None or p.get("id") == IMPLICIT_ID or p.get("polygon") is None:
            out.append(e)
            continue
        if containing_fn(bc, p.get("polygon", [])):
            out.append(e)
            continue
        # Ho tro clearance zone cho red_light_running (neu co)
        if any(containing_fn(bc, clr.get("polygon", []))
               for clr in e.get("clearance", [])):
            out.append(e)
            continue
        # Neu track dang co candidate active tren line cua entry nay, van tiep tuc theo doi
        if track is not None:
            # Ho tro kiem tra ca tam xe (center) ngoai bottom_center cho bounding box
            if getattr(track, "bbox", None) is not None:
                bb = track.bbox
                center = ((bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0)
                if containing_fn(center, p.get("polygon", [])):
                    out.append(e)
                    continue
            # Neu track dang co phien dung/do trong polygon nay, van tiep tuc theo doi
            pk = getattr(track, "parking", None)
            if pk and p.get("id") in pk:
                out.append(e)
                continue
            rs = getattr(track, "red", None)
            if rs:
                elids = {ln.get("id") for ln in e.get("lines", [])}
                if any(lid in elids for lid, c in rs.get("cands", {}).items() if not c.get("fired")) or \
                   any(lid in elids for lid, c in rs.get("stops", {}).items() if not c.get("fired")):
                    out.append(e)
                    continue
            rev = getattr(track, "reverse", None)
            if rev:
                elids = {ln.get("id") for ln in e.get("lines", [])}
                if any(lid in elids for lid in rev):
                    out.append(e)
                    continue
    return out

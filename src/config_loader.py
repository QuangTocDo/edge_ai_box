"""Nap + chuan hoa + validate config camera (base + override, rules theo polygon).

Schema:
- File camera tuy chon `base: <path tuong doi>` -> deep-merge (dict gop,
  list thay toan bo, camera thang).
- Global `wrong_way: / no_uturn: / no_entry_road:` vua la params mac dinh
  vua co `enable:` (mac dinh true).
- Moi polygon co the `rules: {ten_rule: {enable:, ...override}}`.
- `lines:` phang + `uturn_pairs:` global tu boc vao polygon implicit
  `__GLOBAL__` (khop moi track) de config cu chay y nhu cu.
- Ngoai moi polygon explicit = hop le (skip), khong chay rule.
"""
from pathlib import Path

import yaml

from .geometry import parse_window
from .rules import PLANNED_TYPES, known_types

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
    cfg = yaml.safe_load(open(path)) or {}
    base = cfg.pop("base", None)
    if base:
        bpath = (path.parent / base).resolve()
        if not bpath.exists():
            raise ConfigError(f"Khong thay base config: {bpath}")
        cfg = deep_merge(yaml.safe_load(open(bpath)) or {}, cfg)
    cfg["_cfg_path"] = str(path.resolve())
    normalize(cfg)
    warnings = validate(cfg)
    resolve_plan(cfg)
    return cfg, warnings


def normalize(cfg):
    """Boc lines/pairs phang vao polygon implicit. Dich `handler:` cu."""
    cfg.setdefault("polygons", [])
    cfg.setdefault("lines", [])
    cfg.setdefault("uturn_pairs", [])
    for name in RULES:
        cfg.setdefault(name, {})
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
        # dich legacy `handler: [wrong_way, ...]` -> rules enable map
        if "handler" in p and "rules" not in p:
            p["rules"] = {r: {"enable": True} for r in p.pop("handler")}
        p.setdefault("rules", {})
        p.setdefault("lines", [])
        if p.get("kind") == "banned":
            p.setdefault("entry_lines", [])
            p.setdefault("banned_classes", [])
            p.setdefault("active_hours", [])
            p.setdefault("dwell_s", 2.0)
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


def validate(cfg):
    """Fail-fast loi cau truc. Tra ve warnings (rule chua implement)."""
    from .rules import RULE_REGISTRY
    warns = []
    for name in RULES:
        for k in (cfg.get(name) or {}):
            if k != "enable" and k not in RULE_REGISTRY[name].PARAMS:
                warns.append(f"global '{name}': param la '{k}' "
                             f"(hop le: {sorted(RULE_REGISTRY[name].PARAMS)})")
    pids = [p.get("id") for p in cfg["polygons"]]
    if len(pids) != len(set(pids)):
        raise ConfigError("Trung id polygon")
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
                    warns.append(f"{pid}: param la '{rname}.{k}' "
                                 f"(hop le: {sorted(RULE_REGISTRY[rname].PARAMS)})")
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
            from .geometry import polygon_valid
            if not polygon_valid(p.get("polygon") or []):
                raise ConfigError(f"{pid}: polygon khong hop le")
        if r.get("wrong_way") and not ndir and p["id"] != IMPLICIT_ID:
            raise ConfigError(f"{pid}: wrong_way bat nhung thieu directed line")
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
    g = cfg.get(rule, {}).get("enable", True)
    return (poly.get("rules") or {}).get(rule, {}).get("enable", g)


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
                pairs = list(p.get("uturn_pairs", []))
                if p["id"] == IMPLICIT_ID:  # pairs phang cu nam o _pairs
                    pairs += list(p.get("_pairs", []))
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": lines, "pairs": pairs})
            elif rule == "no_entry_road":
                if p.get("kind") != "banned" or p["id"] == IMPLICIT_ID:
                    continue
                plan.append({"polygon": p, "rule": rule,
                             "params": effective_params(cfg, p, rule),
                             "lines": [], "pairs": []})
    cfg["_plan"] = plan


def entries_for(bc, plan, containing_fn):
    """Cac plan entry ap dung cho track: polygon None/implicit = moi track,
    polygon explicit phai chua Bottom-Center. Tra ve [] = skip (hop le)."""
    out = []
    for e in plan:
        p = e["polygon"]
        if p is None or p.get("id") == IMPLICIT_ID or p.get("polygon") is None:
            out.append(e)
            continue
        if containing_fn(bc, p.get("polygon", [])):
            out.append(e)
    return out

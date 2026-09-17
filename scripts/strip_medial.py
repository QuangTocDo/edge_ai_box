"""Don vach tim/divider thua sau khi U-turn chuyen sang sequence thuan.

Chay kho (chi liet ke): python tools/strip_medial.py --config no_way.yaml
Ghi that:               python tools/strip_medial.py --config no_way.yaml --apply

- Drop key `medial` khoi moi pair (rule hien tai bo qua).
- Xoa divider line nao khong con pair nao dung lam first/second.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config.zones import (find_line_any, get_polygons, iter_all_lines,
                             load_config, role_of, save_config)  # noqa: E402


def scan(cfg):
    dividers = [ln["id"] for ln in iter_all_lines(cfg)
                if role_of(ln) == "divider"]
    pairs = []

    def collect(lst):
        for pr in lst:
            if pr.get("medial") is not None:
                pairs.append(pr)
    collect(cfg.get("uturn_pairs", []))
    for p in get_polygons(cfg):
        collect(p.get("uturn_pairs", []))
    used = set()
    for lst in [cfg.get("uturn_pairs", [])] + \
               [p.get("uturn_pairs", []) for p in get_polygons(cfg)]:
        for pr in lst:
            used.update([pr.get("first"), pr.get("second")])
    return dividers, pairs, used


def strip(cfg):
    dividers, pairs, used = scan(cfg)
    report = {"pairs_cleaned": 0, "dividers_deleted": [], "dividers_kept": []}

    def clean(lst):
        for pr in lst:
            if pr.pop("medial", None) is not None:
                report["pairs_cleaned"] += 1
    clean(cfg.get("uturn_pairs", []))
    for p in get_polygons(cfg):
        clean(p.get("uturn_pairs", []))
    for lid in dividers:
        if lid in used:
            report["dividers_kept"].append(lid)  # dang lam first/second
            continue
        ln, owner = find_line_any(cfg, lid)
        if ln is not None:
            (owner.get("lines", []) if owner else cfg["lines"]).remove(ln)
            report["dividers_deleted"].append(lid)
    return report


def main():
    cfg_path = Path(sys.argv[sys.argv.index("--config") + 1]) \
        if "--config" in sys.argv else Path("no_way.yaml")
    apply = "--apply" in sys.argv
    cfg = load_config(cfg_path)
    dividers, pairs, _ = scan(cfg)
    print(f"divider lines: {dividers or 'khong co'}")
    print(f"pairs con medial: {len(pairs)}")
    for pr in pairs:
        print(f"  - {pr['first']}->{pr['second']} med={pr['medial']}")
    if not apply:
        print("Kho chay (them --apply de ghi that)")
        return
    rep = strip(cfg)
    save_config(cfg, cfg_path)
    back = load_config(cfg_path)
    d2, p2, _ = scan(back)
    print(f"Da don: {rep['pairs_cleaned']} pairs, "
          f"xoa dividers {rep['dividers_deleted']}, "
          f"giu {rep['dividers_kept']}")
    print(f"Xac nhan: con {len(d2)} dividers, {len(p2)} pairs co medial")


if __name__ == "__main__":
    main()

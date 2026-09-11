"""Menu chon loi cho tool ve (pure logic, test headless duoc).

Phim 1-5 chon loi -> tool chi hien/nhan cac cong cu duoc phep cua loi do.
Them loi 6 sau nay: them 1 dong vao VIOLATION_MODES (khong sua tool).
"""
from .rules.registry import CANONICAL_TYPES

# tools: line (directed don) | polygon (ve dinh) | pair (gan tay)
#        | fields (nhap terminal) | roi (hop den) | intersection | calib (H)
VIOLATION_MODES = {
    "1": {"violation": "wrong_way",
          "label": "1=wrong_way (nguoc chieu)",
          "rules": ["wrong_way"],
          "tools": ["line"],
          "auto": None},  # line doc lap, khong can container
    "2": {"violation": "no_uturn",
          "label": "2=no_uturn (cam quay dau)",
          "rules": ["no_uturn"],
          "tools": ["polygon", "line", "pair"],
          "auto": "uturn_zone"},  # polygon + 2 lines + 2 pairs
    "3": {"violation": "no_entry_road",
          "label": "3=no_entry (duong cam)",
          "rules": ["no_entry_road"],
          "tools": ["polygon", "fields"],
          "auto": "banned_zone"},  # kind banned + classes/hours/dwell
    "4": {"violation": "red_light",
          "label": "4=red_light (den do + dung vach)",
          "rules": ["red_light_running", "stop_line_violation"],
          "tools": ["polygon", "line", "roi", "intersection"],
          "auto": "red_zone"},  # polygon lane + stop-line + ROI + clearance
    "5": {"violation": "speeding",
          "label": "5=speeding (toc do)",
          "rules": ["speeding"],
          "tools": ["polygon", "calib"],
          "auto": "speed_zone"},  # polygon + H + road_dir
}

# Phim con trong tung loi -> cong cu (hien tren help theo loi dang chon).
SUBKEY_HELP = {
    "l": "ve line",
    "p": "ve dinh polygon",
    "a": "gan pair tay",
    "r": "keo ROI den",
    "i": "ve vung nga tu",
    "c": "hieu chuan H",
    "k": "gan signal vao line",
}


def menu_text():
    """Dong banner menu chinh."""
    return "chon loi: " + "  ".join(
        m["label"] for m in VIOLATION_MODES.values()) + "  (0/Esc: thoat)"


def tools_help(key):
    """List 'phim=mo ta' cho tung cong cu duoc phep (de hien banner)."""
    out = []
    for tool in allowed_tools(key):
        if tool == "fields":
            # khong co phim bam, tu hoi terminal khi chot polygon
            out.append("fields=(tu dong hoi classes/hours/dwell)")
            continue
        out.append(f"{_tool_key(tool)}={SUBKEY_HELP[_tool_key(tool)]}")
        # Loi den do: them phim gan signal (k) khi co roi
        if tool == "roi":
            out.append(f"k={SUBKEY_HELP['k']}")
    return out


def _tool_key(tool):
    """Phim con dai dien cong cu (on dinh de test)."""
    mapping = {
        "line": "l",
        "polygon": "p",
        "pair": "a",
        "fields": "(tu dong hoi)",
        "roi": "r",
        "intersection": "i",
        "calib": "c",
        "roi_link": "k",
    }
    return mapping[tool]


def get_mode(key):
    """Tra ve dict mode hoac None neu phim la."""
    return VIOLATION_MODES.get(str(key))


def allowed_tools(key):
    """List cong cu duoc phep cua loi."""
    m = get_mode(key)
    return list(m["tools"]) if m else []


def default_rules(key):
    """Map rules enable cho polygon moi: loi duoc chon True, con lai False."""
    m = get_mode(key)
    if m is None:
        raise ValueError(f"loi la: {key!r}")
    on = set(m["rules"])
    return {r: {"enable": r in on} for r in CANONICAL_TYPES}


def rules_off():
    """Tat het rules (cho polygon phu nhu intersection)."""
    return {r: {"enable": False} for r in CANONICAL_TYPES}


def validate_tool(key, tool):
    """(ok, ly_do): cong cu co duoc phep trong loi dang chon khong."""
    m = get_mode(key)
    if m is None:
        return False, "chua chon loi (nhan 1-5 truoc)"
    # 'k' gan signal la alias cua 'roi' (chi loi den do co roi)
    if tool == "roi_link":
        if "roi" in m["tools"]:
            return True, ""
    elif tool in m["tools"]:
        return True, ""
    return False, (f"loi {m['violation']} khong dung '{tool}' "
                   f"(chi duoc: {', '.join(m['tools'])})")


def subkey_tool(subkey):
    """Phim con -> ten cong cu (None neu khong phai phim cong cu)."""
    return SUBKEYS.get(str(subkey).lower())


# Phim con trong tung loi (tach rieng de test + hien help).
SUBKEYS = {
    "l": "line",
    "p": "polygon",
    "a": "pair",
    "r": "roi",
    "i": "intersection",
    "c": "calib",
    "k": "roi_link",
}

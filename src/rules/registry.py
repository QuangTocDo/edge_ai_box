"""Registry anh xa ten rule (trong config) -> class Rule.

Them loi moi = tao file rule moi + 1 dong import + dang ky o day.
Khong can sua pipeline.py hay config_loader.py.
"""
from .base import BaseRule, cooldown_ok
from .no_entry_road import NoEntryRule
from .no_uturn import NoUTurnRule
from .wrong_way import WrongWayRule

RULE_REGISTRY = {
    WrongWayRule.TYPE: WrongWayRule,
    NoUTurnRule.TYPE: NoUTurnRule,
    NoEntryRule.TYPE: NoEntryRule,
}

# Ten da biet nhung chua co class Rule -> loader warn, khong crash.
PLANNED_TYPES = {"no_parking", "no_gathering", "red_light", "stop_line",
                 "speeding"}


def known_types():
    """Ten cac rule da implement (dung thay config_loader.RULES)."""
    return tuple(RULE_REGISTRY)


def create(name, params):
    """Dung 1 instance rule tu ten + params dict.

    - Ten la -> KeyError ke ten hop le.
    - Key thua trong params (vd key cu da bo) -> tu dong bo, khong crash.
    """
    if name not in RULE_REGISTRY:
        raise KeyError(
            f"rule la '{name}'. Hop le: {sorted(RULE_REGISTRY)}")
    cls = RULE_REGISTRY[name]
    clean = {k: v for k, v in (params or {}).items() if k in cls.PARAMS}
    try:
        return cls(**clean)
    except TypeError as e:
        raise TypeError(f"Khoi tao rule '{name}': {e}") from e


__all__ = ["BaseRule", "WrongWayRule", "NoUTurnRule", "NoEntryRule",
           "RULE_REGISTRY", "PLANNED_TYPES", "known_types", "create",
           "cooldown_ok"]

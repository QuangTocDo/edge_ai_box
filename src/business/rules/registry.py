"""Registry anh xa ten rule (trong config) -> class Rule.

Them loi moi = tao file rule moi + 1 dong import + dang ky o day.
Khong can sua pipeline.py hay config_loader.py.
"""
from .base import BaseRule, cooldown_ok
from .no_entry_road import NoEntryRule
from .no_parking import NoParkingRule
from .no_uturn import NoUTurnRule
from .red_light_running import RedLightRunningRule
from .speeding import SpeedingRule
from .stop_line import StopLineRule
from .wrong_way import WrongWayRule

RULE_REGISTRY = {
    WrongWayRule.TYPE: WrongWayRule,
    NoUTurnRule.TYPE: NoUTurnRule,
    NoEntryRule.TYPE: NoEntryRule,
    NoParkingRule.TYPE: NoParkingRule,
    RedLightRunningRule.TYPE: RedLightRunningRule,
    StopLineRule.TYPE: StopLineRule,
    SpeedingRule.TYPE: SpeedingRule,
    "stop_line": StopLineRule,
    "red_light": RedLightRunningRule,
}

# Danh sach cac loai rule chuan hoa (dung cho config_loader.RULES)
CANONICAL_TYPES = (
    WrongWayRule.TYPE,
    NoUTurnRule.TYPE,
    NoEntryRule.TYPE,
    NoParkingRule.TYPE,
    RedLightRunningRule.TYPE,
    StopLineRule.TYPE,
    SpeedingRule.TYPE,
)

# Ten da biet nhung chua co class Rule -> loader warn, khong crash.
PLANNED_TYPES = {"no_gathering"}


def known_types():
    """Ten cac rule da implement (dung thay config_loader.RULES)."""
    return CANONICAL_TYPES


def create(name, params):
    """Dung 1 instance rule tu ten + params dict.

    - Ten la -> KeyError ke ten hop le.
    - Key la (typo / key cu da bo) -> KeyError ro rang, khong lang le bo
      (fail-fast: loi config phai vo ngay luc khoi dong, khong chay sai im lang).
    """
    if name not in RULE_REGISTRY:
        raise KeyError(
            f"rule la '{name}'. Hop le: {sorted(RULE_REGISTRY)}")
    cls = RULE_REGISTRY[name]
    unknown = [k for k in (params or {}) if k not in cls.PARAMS]
    if unknown:
        raise KeyError(
            f"rule '{name}': param la {unknown}. "
            f"Hop le: {sorted(cls.PARAMS)}")
    clean = {k: v for k, v in (params or {}).items() if k in cls.PARAMS}
    try:
        return cls(**clean)
    except TypeError as e:
        raise TypeError(f"Khoi tao rule '{name}': {e}") from e


__all__ = ["BaseRule", "WrongWayRule", "NoUTurnRule", "NoEntryRule",
           "NoParkingRule",
           "RedLightRunningRule", "StopLineRule", "SpeedingRule",
           "RULE_REGISTRY", "PLANNED_TYPES", "known_types", "create",
           "cooldown_ok"]

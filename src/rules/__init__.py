"""LEGACY shim (P2 restructure): use src.business.rules instead.

Import cũ vẫn chạy:
    from src.rules import WrongWayRule, ...
"""
from src.business.rules import (  # noqa: F401
    PLANNED_TYPES, RULE_REGISTRY, BaseRule, NoEntryRule, NoParkingRule,
    NoUTurnRule, RedLightRunningRule, SpeedingRule, StopLineRule,
    WrongWayRule, cooldown_ok, create, known_types,
)

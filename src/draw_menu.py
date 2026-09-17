"""LEGACY shim (P2 restructure): use src.calibration instead."""
from src.calibration.draw_menu import (  # noqa: F401
    SUBKEY_HELP, SUBKEYS, VIOLATION_MODES, allowed_tools, default_rules,
    get_mode, menu_text, rules_off, subkey_tool, tools_help, validate_tool,
)

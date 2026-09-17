"""LEGACY shim (P2 restructure): use src.config instead."""
from src.config.loader import (  # noqa: F401
    IMPLICIT_ID, RULES, UNIMPLEMENTED, ConfigError, deep_merge,
    effective_params, entries_for, is_enabled, load_camera_config, resolve_plan,
)

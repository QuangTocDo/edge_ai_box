"""Config layer: load/merge/validate camera YAML + zone CRUD."""
from .loader import ConfigError, deep_merge, effective_params, entries_for, is_enabled, load_camera_config, resolve_plan
from .zones import iter_all_lines

__all__ = ["ConfigError", "deep_merge", "effective_params", "entries_for", "is_enabled", "load_camera_config", "resolve_plan", "iter_all_lines"]

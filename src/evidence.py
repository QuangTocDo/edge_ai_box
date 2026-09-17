"""LEGACY shim (P2 restructure): use src.storage instead."""
from src.storage.evidence import prune_old_dates, save_event, save_triptych  # noqa: F401

__all__ = ["prune_old_dates", "save_event", "save_triptych"]

"""LEGACY shim (P2 restructure): use src.storage instead."""
from src.storage.sinks import AsyncEvidenceSaver, handle_event, maybe_prune  # noqa: F401

__all__ = ["AsyncEvidenceSaver", "handle_event", "maybe_prune"]

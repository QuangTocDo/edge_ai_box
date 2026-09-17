"""LEGACY shim (P2 restructure): use src.inference instead."""
from src.inference.detector import create_tracker  # noqa: F401

__all__ = ["create_tracker"]

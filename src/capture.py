"""LEGACY shim (P2 restructure): use src.camera instead. Kept for compat."""
from src.camera.capture import AsyncStreamReader, _is_stream, _mask_source, _open_capture  # noqa: F401

__all__ = ["AsyncStreamReader", "_is_stream", "_mask_source", "_open_capture"]

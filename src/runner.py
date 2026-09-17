"""LEGACY shim (P2 restructure): use src.pipeline instead."""
from src.pipeline.runner import FrameContext, build_runners, run_first_event, wanted_entries  # noqa: F401

__all__ = ["FrameContext", "build_runners", "run_first_event", "wanted_entries"]

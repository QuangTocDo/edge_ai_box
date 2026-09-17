"""Pipeline layer: rule runners per frame (testable w/o video/model)."""
from .runner import FrameContext, build_runners, run_first_event, wanted_entries

__all__ = ["FrameContext", "build_runners", "run_first_event", "wanted_entries"]

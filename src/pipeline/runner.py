"""Chay rule engine tren tracks: loc entries -> event dau tien thang.

Tach rieng khoi pipeline.main() de test duoc ma khong can video/model.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np

from ..business.rules import create as create_rule
from ..config.loader import entries_for
from ..utils.geometry import compass8, point_in_polygon


@dataclass
class FrameContext:
    """Ngu canh frame truyen cho cac rule kiem tra vi pham."""
    frame_idx: int
    t: float
    wall_min: Optional[int] = None
    frame: Optional[np.ndarray] = None
    signals: Optional[Any] = None


def build_runners(plan):
    """1 instance rule cho moi (polygon x rule). Ten rule anh xa sang class
    qua registry (them loi moi khong can sua pipeline)."""
    return [(e, create_rule(e["rule"], e["params"])) for e in plan]


def wanted_entries(track, plan_entries):
    """Cac plan entry ap dung cho track (rong = ngoai moi polygon: skip)."""
    return entries_for(track.pts[-1], plan_entries, point_in_polygon,
                       track=track)


def run_first_event(track, wanted, rule_of, frame_idx=0, t=0.0, wall_min=None,
                    frame=None, signals=None, *, ctx: Optional[FrameContext] = None):
    """Chay tung rule, event dau tien thang. Tra ve event dict hoac None.
    Ho tro ca FrameContext (khuyen nghi) hoac truyen tham so roi rac.
    """
    if ctx is not None:
        frame_idx = ctx.frame_idx
        t = ctx.t
        wall_min = ctx.wall_min
        frame = ctx.frame
        signals = ctx.signals

    for entry in wanted:
        rule = rule_of[id(entry)]
        e = rule.run(entry, track, frame_idx, t, wall_min,
                     frame=frame, signals=signals)
        if e:
            hd = getattr(track, "heading", None)
            if hd is not None:
                e["heading_deg"] = round(hd, 1)
                e["compass"] = compass8(hd)
            return e
    return None

"""Chay rule engine tren tracks: loc entries -> event dau tien thang.

Tach rieng khoi pipeline.main() de test duoc ma khong can video/model.
"""
from .config_loader import entries_for
from .geometry import point_in_polygon
from .rules import create as create_rule


def build_runners(plan):
    """1 instance rule cho moi (polygon x rule). Ten rule anh xa sang class
    qua registry (them loi moi khong can sua pipeline)."""
    return [(e, create_rule(e["rule"], e["params"])) for e in plan]


def wanted_entries(track, plan_entries):
    """Cac plan entry ap dung cho track (rong = ngoai moi polygon: skip)."""
    return entries_for(track.pts[-1], plan_entries, point_in_polygon,
                       track=track)


def run_first_event(track, wanted, rule_of, frame_idx, t, wall_min,
                    frame, signals):
    """Chay tung rule, event dau tien thang. Tra ve event dict hoac None."""
    for entry in wanted:
        rule = rule_of[id(entry)]
        e = rule.run(entry, track, frame_idx, t, wall_min,
                     frame=frame, signals=signals)
        if e:
            return e
    return None

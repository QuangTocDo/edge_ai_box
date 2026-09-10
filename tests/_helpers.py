"""Helper dung chung cho cac test rule (khong phai test)."""
from src.tracking import TrackState

FPS = 30.0


def drive(rule_lines, pts, rule, pairs=None, min_hits=3):
    """Gia lap track di qua cac diem pts, tra ve list events."""
    st = TrackState(1, 2, 0.9, pts[0])
    st.hits = min_hits
    evs = []
    for i in range(1, len(pts)):
        st.update(2, 0.9, pts[i], [0, 0, 10, 10], i)
        t = i / FPS
        if pairs is None:
            e = rule.update(st, rule_lines, i, t)
        else:
            e = rule.update(st, rule_lines, pairs, i, t)
        if e:
            evs.append(e)
    return evs

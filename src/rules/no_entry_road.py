"""Loi vao duong cam (§4.2, CHOT don gian).

- Ngoai active_hours hoac class khong cam -> bo qua ngay.
- Vao (ngoai->trong) hoac moc san trong zone: bat dau tinh dwell.
  Khong yeu cau entry line, khong xet huong chuyen dong.
- O lien tuc >= dwell_s -> bao 1 lan/dot hien dien. Ra ngoai -> reset.
- t: giay video (frame_idx/fps). wall_min: phut hien tai theo gio edge.
"""
from ..geometry import in_active_hours, parse_window, point_in_polygon
from .base import BaseRule, cooldown_ok


class NoEntryRule(BaseRule):
    """Zone duong cam (CHOT don gian): vao zone + o du dwell -> VIOLATION."""

    TYPE = "no_entry_road"
    PARAMS = {"dwell_s": 2.0, "min_hits": 3, "cooldown_s": 10.0}

    def __init__(self, dwell_s=2.0, min_hits=3, cooldown_s=10.0):
        super().__init__(min_hits=min_hits, cooldown_s=cooldown_s)
        self.dwell_s = dwell_s

    @staticmethod
    def _windows(polygon):
        if polygon.get("_windows") is not None:
            return polygon["_windows"]
        return [parse_window(w) for w in polygon.get("active_hours", [])]

    def update(self, track, polygon, wall_min, frame_idx, t):
        pid = polygon["id"]
        if self._windows(polygon) and not in_active_hours(
                wall_min, self._windows(polygon)):
            track.zones.pop(pid, None)  # ngoai gio cam -> reset
            return None
        dwell = float(polygon.get("dwell_s", self.dwell_s))
        if track.cls not in polygon.get("banned_classes", []):
            track.zones.pop(pid, None)
            return None
        if len(track.pts) < 1 or track.hits < self.min_hits:
            return None
        curr = track.pts[-1]
        if not point_in_polygon(curr, polygon.get("polygon", [])):
            track.zones.pop(pid, None)  # ra ngoai -> reset
            return None
        zs = track.zones.get(pid)
        if zs is None or not zs["inside"]:
            track.zones[pid] = {"inside": True, "enter_t": t,
                                "fired": False}
            return None
        if not zs["fired"] and t - zs["enter_t"] >= dwell \
                and cooldown_ok(track, self.TYPE, t):
            zs["fired"] = True
            track.cooldowns[self.TYPE] = t + self.cooldown_s
            return {"type": self.TYPE, "track_id": track.tid,
                    "cls": track.cls, "conf": track.conf,
                    "bbox": track.bbox, "bc": curr,
                    "line_id": pid, "frame_idx": frame_idx, "t": t,
                    "extra": {"zone_id": pid,
                              "dwell_s": round(t - zs["enter_t"], 2),
                              "banned_classes": polygon.get("banned_classes", [])}}
        return None

    def run(self, entry, track, frame_idx, t, wall_min=None):
        """Chay rule tren 1 plan entry (pipeline goi ham nay)."""
        return self.update(track, entry["polygon"], wall_min,
                           frame_idx, t)

    def explain(self, track, t=None, polygon=None, wall_min=None, **ctx):
        """Ly do trang thai hien tai (khong doi state)."""
        pid = (polygon or {}).get("id", "?")
        if polygon is not None and self._windows(polygon) \
                and wall_min is not None and not in_active_hours(
                    wall_min, self._windows(polygon)):
            return f"no_entry tid={track.tid}: ngoai gio cam ({pid})"
        if polygon is not None and \
                track.cls not in polygon.get("banned_classes", []):
            return (f"no_entry tid={track.tid}: class {track.cls} "
                    f"khong cam ({pid})")
        if len(track.pts) < 1 or track.hits < self.min_hits:
            return (f"no_entry tid={track.tid}: track moi "
                    f"(hits={track.hits}<{self.min_hits})")
        if polygon is not None and not point_in_polygon(
                track.pts[-1], polygon.get("polygon", [])):
            return f"no_entry tid={track.tid}: ngoai zone ({pid})"
        zs = track.zones.get(pid)
        if zs and zs.get("inside"):
            dwell = float((polygon or {}).get("dwell_s", self.dwell_s))
            el = (t - zs["enter_t"]) if t is not None else 0.0
            if zs.get("fired"):
                return (f"no_entry tid={track.tid}: da bao, "
                        f"doi ra-vao lai ({pid})")
            return (f"no_entry tid={track.tid}: trong zone "
                    f"{el:.1f}/{dwell:.0f}s ({pid})")
        return f"no_entry tid={track.tid}: chua vao zone ({pid})"

"""Map id class YOLO (day/night) -> ten xe gon cho UI overlay.

Model train 8 class ngay/dem (data_v1) + pedestrian (id 8):
  0=motorbike_day, 1=car_day, 2=bus_day, 3=truck_day,
  4=motorbike_night, 5=car_night, 6=bus_night, 7=truck_night,
  8=pedestrian.

PHAM VI: chi hien thi (visualizer overlay / evidence UI).
Moi noi nhap/xu ly idx (rules, banned_classes, configs)
giu nguyen id goc.
"""
VEHICLE_NAMES = {
    0: "motorbike",
    1: "car",
    2: "bus",
    3: "truck",
    4: "motorbike",
    5: "car",
    6: "bus",
    7: "truck",
    8: "pedestrian",
}


def vehicle_name(cls, raw_names=None):
    """Ten xe gon cho UI (gop day/night thanh 1). Id la -> fallback ten raw cua model / 'class {id}'."""
    if raw_names is not None:
        if isinstance(raw_names, dict):
            raw = raw_names.get(cls)
        elif isinstance(raw_names, (list, tuple)) and isinstance(cls, int) and 0 <= cls < len(raw_names):
            raw = raw_names[cls]
        else:
            raw = None

        if raw is not None:
            raw_str = str(raw)
            for suffix in ("_day", "_night", "-day", "-night"):
                if raw_str.endswith(suffix):
                    return raw_str[:-len(suffix)]
            return raw_str

    if cls in VEHICLE_NAMES:
        return VEHICLE_NAMES[cls]

    return f"class {cls}"

"""Map id class YOLO (day/night) -> ten xe gon cho UI overlay.

Model train 8 class ngay/dem (data_v1):
  0=motorbike_day, 1=car_day, 2=bus_day, 3=truck_day,
  4=motorbike_night, 5=car_night, 6=bus_night, 7=truck_night.

PHAM VI: chi hien thi (visualizer overlay). Khong phai co che VLM.
Moi noi nhap/xu ly idx (rules, banned_classes, configs, evidence JSON)
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
}


def vehicle_name(cls, raw_names=None):
    """Ten xe gon cho UI. Id la -> fallback ten raw cua model / 'class {id}'."""
    if cls in VEHICLE_NAMES:
        return VEHICLE_NAMES[cls]
    if raw_names is None:
        return f"class {cls}"
    if isinstance(raw_names, dict):
        return raw_names.get(cls, f"class {cls}")
    return raw_names[cls] if cls < len(raw_names) else f"class {cls}"

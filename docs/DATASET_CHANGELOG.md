# Dataset Changelog (immutable: version đã release không sửa tại chỗ)

## data_v1 — 2026-09-08
- Nguồn: archive/daytime-dataset/daytime (15.396 ảnh) + archive/nighttime-dataset/nighttime (26.709 ảnh)
- Chia 8:1:1 RIÊNG từng nguồn (seed 42) rồi gộp:
  - train: 33.683 (day 12.316 + night 21.367)
  - val: 4.209 (day 1.539 + night 2.670)
  - test: 4.213 (day 1.541 + night 2.672)
- 8 class: 0 motorbike_day, 1 car_day, 2 bus_day, 3 truck_day,
  4 motorbike_night, 5 car_night, 6 bus_night, 7 truck_night
- Lưu ý: 1 ảnh night không có txt nằm ở train (làm background)
- Quy ước thêm class mới: tạo data_v2 (không sửa v1), id tiếp theo = 8,
  chia lại cùng seed 42, nc +1, thêm tên vào data.yaml

## data_v2 — 2026-09-21 (person-only, doc lap v1)
- Nguon: archive/VisDrone (train 6.471 + val 548 + test-dev 1.610 ann)
- Convert scripts/convert_visdrone.py: chi class 0 (pedestrian) + 1 (people)
  -> id 8; bo score=0 (ignore), bo 6,7,9 + bicycle/xe (chi lay nguoi);
  loc rider (person nam gon >=80% trong motor/bicycle); chuan hoa YOLO.
- Ket qua: train 5.365 anh / 79.154 box; val 520 / 8.833; test 1.197 / 20.923
  (anh khong person bi loai; test-challenge khong label -> bo qua)
- data_v2/data.yaml: nc=9, names giong v1 + pedestrian (id 0-7 de trong,
  tuong thich merge sau). Kiem tra mat: box om khit nguoi, khong dinh xe.
- v1 nguyen ven (khong doc-ghi them sau 2026-09-08).

## data_cctv — 2026-09-22 (person-only, doc lap v1/v2)
- Nguon: cctv.v2-no-augment.yolov8 (train 3.060 + valid 526 + test 151 anh,
  640x640, CC BY 4.0). Copy nguyen + sua loi.
- Sua: train/labels/01-08-2022__08-48-05AM_....txt co 2 dong polygon
  (33/41 cot) -> chuyen bbox min/max (LƯU Y: da sua truc tiep ca file goc
  trong cctv.v2-no-augment.yolov8/; zip goc trong Trash van giu ban loi).
- Audit 19 txt rong bang contact-sheet: toan bo la phong nhiet indoor
  khong nguoi (chair/table/heater) -> giu lam background.
- data_cctv/data.yaml: nc=1, names=[person]. 14.176 box id 0 (tb 3.8/anh).
- data_cctv/data.yaml: nc=9, names giong data_v1 + pedestrian id 8
  (labels goc id 0 da relabel -> 8).
- Chua loc indoor/outdoor (ten file generic 92%, can duyet thumbnail neu can).

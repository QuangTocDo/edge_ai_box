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

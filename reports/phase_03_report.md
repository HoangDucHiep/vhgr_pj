# Phase 03 — Parse infobox + chuẩn hóa ngày (A4)

- Ngày: 2026-11-14
- Trạng thái: ✅ đạt Gate (5/5)
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-03.md`
- Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-03-infobox-stats.json`

## Đã làm

1. **`configs/infobox_mapping.yaml`** (mới) — nguồn sự thật cho toàn bộ mapping:
   - `fields`: 60+ trường infobox → quan hệ KG (kèm `kind`, `direction`, `value_type`).
   - `date_templates`: 20 template ngày (`ngày mất và tuổi`, `birth date and age`, `circa`…).
   - `type_map`: 170+ tên loại infobox → 7 loại node KG.
   - `aliases`, `node_props`, `gender_keys`/`gender_values`, `battle_result`.

2. **`src/preprocess/parse_infobox.py`** (mới):
   - Trích tham số bằng `wikitextparser` (chính) + `infobox_parser.parse_infobox` (dự phòng, hành vi Phase 1).
   - `clean_value()` gỡ comment / `<ref>` / template / HTML, thay `[[đích|anchor]]` → anchor.
   - `split_items()` tách giá trị nhiều mục **giữ nguyên wikitext** (để không mất link).
   - `parse_date_field()` đọc template ngày, suy cả mốc sinh từ tham số phụ của template "X và tuổi".
   - Sinh `data/interim/infobox_triples.jsonl` (10.394 triple) + `data/interim/infobox_entities.jsonl` (1.764 entity).

3. **`src/preprocess/infobox_entity_types.py`** (mới):
   - `normalize_type()` — tra `type_map` (khớp chính xác trước, rồi mới bỏ tiền tố "Infobox"/"Thông tin").
   - `detect_gender()` — trường `gioi tinh` → tiền tố tiêu đề → marker trong tên.
   - `infer_object_type()` — suy loại đối tượng; nhận diện **tổ chức** (phe phái/quân đội) để loại thay vì gán nhầm `person`.
   - Suy loại chủ thể theo thứ tự: **tên template → tín hiệu Wikidata → `article`** (trung tính, không mặc định `person`).

4. **`src/preprocess/extract_lead_dates.py`** (mới) — fallback đoạn dẫn:
   - Chỉ xét **ngoặc đầu tiên** của câu dẫn; kiểm tra khoảng cách sinh–mất ≤ 120 năm.
   - Chỉ áp dụng cho bài `person`; bỏ qua bài đã có ngày từ infobox (không trùng lặp).
   - Sinh `data/interim/lead_triples.jsonl` (736 triple, `method="rule"`, `confidence=0.85`).

5. **`src/common/normalize.py`** — mở rộng `parse_vi_date`:
   - Khoảng ngày (`"25–26 tháng 12 năm 1944"`, `"1884–1913"`) → chỉ lấy năm.
   - Năm âm lịch `"năm Ất Tý (938)"` → 938, **chỉ khi khớp bảng đã đối chiếu**.
   - Khoảng năm (`"khoảng năm 1000"`, `"sau năm 1230"`).
   - Dạng gạch nối `"15-3-1028"`; năm < 1000 viết đủ 4 chữ số (`0939-02-01`).

6. **`src/common/schemas.py`** — căn `RELATION_SUBJECT_TYPES` theo `docs/04` §3.1:
   `thuoc_trieu_dai` → `{person, dynasty, event}`; `sinh_tai`/`mat_tai` → `{person}`;
   `dong_doi_tai` → `{dynasty}`. *Tập 18 quan hệ không đổi.*

7. **Test + script**:
   - `tests/fixtures/dates.jsonl` — 30 chuỗi ngày mẫu (VI + EN + template + âm lịch + circa).
   - `tests/test_normalize.py` — 39 test, Gate ≥ 95%.
   - `tests/test_infobox.py` — 44 test, đủ 5 Gate + 6 test regression cho lỗi loại node.
   - `scripts/stats_infobox.py` — đo 5 Gate + phân bố quan hệ.

## Lệnh đã chạy

```bash
python -m src.preprocess.parse_infobox --config configs/default.yaml
→ 1.764/1.764 bài có infobox → 10.394 triple, 1.764 entity

python -m src.preprocess.extract_lead_dates --config configs/default.yaml
→ 736 triple từ đoạn dẫn của 376 bài

pytest -q tests/
→ 268 passed (185 từ Phase 1–2 + 83 mới của Phase 3)

python scripts/stats_infobox.py
→ Gate 1: 100,0% · Gate 2: 92,4% · Gate 3: 100,0% · Gate 4: 100,0% · Gate 5: 0

# assert Gate chính thức trong docs/09 Phase 3
python - <<'PY' ...
PY
→ OK triples 10394
→ OK quan hệ trong danh mục
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| **Gate 1** — bài `person` parse thành công | ≥ 95% | **100,0%** (1.061 / 1.061) | ✅ |
| **Gate 2** — bài `person` có ≥ 1 ngày hoặc quan hệ gia đình | ≥ 90% | **92,4%** (980 / 1.061) | ✅ |
| &nbsp;&nbsp;└ chỉ từ infobox | — | 67,3% (714) | tham chiếu |
| &nbsp;&nbsp;└ + đoạn dẫn | — | **92,4%** (980) | ✅ |
| &nbsp;&nbsp;└ có ngày sinh/mất | — | 90,5% | tham chiếu |
| &nbsp;&nbsp;└ có quan hệ gia đình | — | 42,3% | tham chiếu |
| **Gate 3** — chuẩn hóa ngày trên 30 mẫu | ≥ 95% | **100,0%** (30 / 30) | ✅ |
| **Gate 4** — triple đủ 9 trường bắt buộc, `method="infobox"`, `confidence ≥ 0.95` | 100% | **100,0%** (10.394 / 10.394) | ✅ |
| **Gate 5** — quan hệ ngoài danh mục 18 quan hệ | 0 | **0** | ✅ |
| &nbsp;&nbsp;└ vi phạm ràng buộc loại chủ thể (`RELATION_SUBJECT_TYPES`) | 0 | **0** | ✅ |

### Phân bố quan hệ

| Quan hệ | Số triple | | Quan hệ | Số triple |
|---|---|---|---|---|
| `chi_huy_tran` | 1.760 | | `thuoc_trieu_dai` | 639 |
| `sinh_tai` | 1.435 | | `mat_nam` | 635 |
| `cha_cua` | 1.097 | | `dien_ra_tai` | 522 |
| `giu_chuc_vu` | 1.020 | | `ke_vi` | 455 |
| `sinh_nam` | 985 | | `tham_gia_tran` | 353 |
| `mat_tai` | 952 | | `me_cua` | 295 |
| `vo_cua` | 159 | | `chong_cua` | 68 |
| `lap_ra` | 19 | | | |

**15 / 18** quan hệ được sinh. Ba quan hệ không sinh: `anh_em_cua` (trường `anh em` không có dữ liệu trong corpus), `danh_bai` (chỉ trích khi câu kết quả trận đánh có cấu trúc rõ), `dong_doi_tai` (thuộc về triều đại — chưa có infobox triều đại trong corpus).

### Phân bố loại node (1.764 entity)

| Loại | Số entity | | Loại | Số entity |
|---|---|---|---|---|
| `person` | 1.205 | | `dynasty` | 2 |
| `event` | 309 | | `article` | 0 |
| `place` | 248 | | | |

### Phân bố loại đối tượng (10.394 triple)

| Loại | Số | | Loại | Số |
|---|---|---|---|---|
| `place` | 2.924 | | `year` | 1.620 |
| `event` | 2.122 | | `title` | 1.020 |
| `person` | 2.069 | | `dynasty` | 639 |

## Gate

- [x] **Gate 1** — ≥ 95% bài có infobox `person` parse thành công → **100,0%**
- [x] **Gate 2** — ≥ 90% bài nhân vật có ≥ 1 trường ngày sinh/mất hoặc quan hệ gia đình → **92,4%**
- [x] **Gate 3** — chuẩn hóa ngày ≥ 95% trên 30 chuỗi mẫu → **100,0%**
- [x] **Gate 4** — 100% triple đủ 9 trường bắt buộc, `method="infobox"`, `confidence ≥ 0.95` → **100,0%**
- [x] **Gate 5** — 0 quan hệ ngoài danh mục → **0**

## Sai lệch so với kế hoạch

| Mã | Nội dung |
|---|---|
| D-019 | `RELATION_SUBJECT_TYPES` trong `src/common/schemas.py` lệch `docs/04` — đã sửa 4 dòng, **tập 18 quan hệ không đổi** |
| D-020 | `battle` trong `INFOBOX_TYPE_MAP` (Phase 1) trả `"battle"` — không phải loại node KG; Phase 3 map sang `event` trong config riêng, không sửa file Phase 1 |
| D-021 | 146/1.061 bài `person` có template infobox **rỗng** → Gate 1 đo "nhận diện được khối template" (100%), coverage đo ở Gate 2 |
| D-022 | `parse_vi_date` trả ISO 4 chữ số cho năm < 1000 (`0939-02-01`) — `date.isoformat()` trả `939-02-01`, thiếu số 0 |
| D-023 | 3 artifact mới (`infobox_triples.jsonl`, `lead_triples.jsonl`, `infobox_entities.jsonl`) — cập nhật `AGENTS.md` §7 + `docs/09` |
| D-024 | Loại infobox lạ **không** mặc định `person` nữa → `article` (trung tính) + dùng tín hiệu Wikidata; sửa lỗi node "Hà Nội"/"Cần Thơ" bị gán `person` |

## Việc tiếp theo

**Phase 4** — Gán nhãn bạc NER: sinh `data/interim/ner_silver.jsonl` từ link + thực thể infobox
(vừa tạo ở Phase 3) → `docs/09` §Phase 4.

## Ghi chú cho Phase sau

- `data/interim/infobox_entities.jsonl` đã có sẵn **1.764 entity** với `props` (birth_year, death_year,
  reign_start/end, temple_name, posthumous_name, courtesy_name, gender, aliases) — đây là nguồn
  cho entity linking ở Phase 8 và node props ở Phase 10.
- Bảng `_LUNAR_YEAR_MAP` trong `src/common/normalize.py` chỉ chứa năm âm lịch **đã đối chiếu**
  với Wikipedia — nếu cần mở rộng, phải bổ sung nguồn (xem `docs/CONTEXT.md` §2.6).

# Phase 03 — Parse infobox + chuẩn hóa ngày (A4)

- Ngày: 2026-11-14 (lần 1) · **Audit đóng phase: 2026-11-14 (lần 2)**
- Trạng thái: ✅ đạt Gate (5/5) — sau audit: ✅ đạt Gate (5/5) + 3 Gate bổ sung
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-03.md`
- Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-03-infobox-stats.json`

## Đã làm

1. **`configs/infobox_mapping.yaml`** (mới) — nguồn sự thật cho toàn bộ mapping:
   - `fields`: 60+ trường infobox → quan hệ KG (kèm `kind`, `direction`, `value_type`).
   - `date_templates`: 20 template ngày (`ngày mất và tuổi`, `birth date and age`, `circa`…).
   - `type_map`: 170+ tên loại infobox → 7 loại node KG.
   - `aliases`, `node_props`, `gender_keys`/`gender_values`.

2. **`src/preprocess/parse_infobox.py`** (mới):
   - Trích tham số bằng `wikitextparser` (chính) + `infobox_parser.parse_infobox` (dự phòng, hành vi Phase 1).
   - `clean_value()` gỡ comment / `<ref>` / template / HTML, thay `[[đích|anchor]]` → anchor.
   - `split_items()` tách giá trị nhiều mục **giữ nguyên wikitext** (để không mất link).
   - `parse_date_field()` đọc template ngày, suy cả mốc sinh từ tham số phụ của template "X và tuổi".
   - Sinh `data/interim/infobox_triples.jsonl` (10.078 triple) + `data/interim/infobox_entities.jsonl` (1.764 entity).

3. **`src/preprocess/infobox_entity_types.py`** (mới):
   - `normalize_type()` — tra `type_map` (khớp chính xác trước, rồi mới bỏ tiền tố "Infobox"/"Thông tin");
     **ưu tiên tín hiệu Wikidata** cho template mơ hồ (xem Audit §2).
   - `detect_gender()` — trường `gioi tinh` → tiền tố tiêu đề → marker trong tên.
   - `infer_object_type()` — suy loại đối tượng; nhận diện **tổ chức** (phe phái/quân đội) để loại thay vì gán nhầm `person`.
   - Suy loại chủ thể theo thứ tự: **tên template → tín hiệu Wikidata → `article`** (trung tính, không mặc định `person`).
   - Hai mặc định tách biệt: `DEFAULT_TYPE="article"` (chủ thể) vs `DEFAULT_OBJECT_TYPE="person"` (đối tượng).

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
   - `tests/test_infobox.py` — 50 test, đủ 5 Gate + 10 test regression.
   - `scripts/stats_infobox.py` — đo 5 Gate + phân bố quan hệ.

---

# Audit đóng phase (14/11/2026)

Audit độc lập Phase 2–3 phát hiện **4 lỗi thật** trong bản triển khai đầu. Tất cả đã sửa.

## 1. Trùng triple + self-loop + stale artifact (D-027)

**Ba lỗi, cùng một hệ quả**: số liệu Gate đếm trùng → tỉ lệ trông đẹp hơn thực tế.

| Lỗi | Ở HEAD | Sau khi sửa | Nguyên nhân gốc |
|---|---|---|---|
| Triple trùng trong 1 doc | **347** triple thừa / 341 nhóm | **0** | Wikipedia có **hai** trường cùng nội dung (`Ngày sinh` + `Ngày sinh (từ Ngày mất)`) → mỗi trường sinh 1 triple, không có bước gộp |
| Self-loop (`subject == object`) | **4** | **0** | Infobox ghi nhầm (bài của chính người là "Tiền nhiệm" của họ) |
| Trùng ngày lead ∩ infobox | **81** trên **47** bài | **0** | `lead_triples.jsonl` sinh lúc 04:38, `infobox_triples.jsonl` sinh lại lúc 04:40 → danh sách `docs_with_dates` **stale** |

**Cách sửa**:
- `build_triples()` thêm `seen: set[tuple[str, str, str]]` — giữ bản **đầu tiên** (thứ tự trường infobox = bản có bằng chứng trực tiếp), đếm bằng `skipped_duplicate`.
- `add_triple()` loại `subject == object` → bộ đếm `skipped_self_loop`.
- Ràng buộc **thứ tự chạy** `parse_infobox.py` → `extract_lead_dates.py` ghi rõ trong `docs/09` §Phase 3.

> **Lưu ý khi đọc số liệu:** đo **không** khoá `doc_id` cho ra **527** triple thừa / 518 nhóm — nhưng phần chênh là các quan hệ **đối xứng hợp lệ** giữa 2 bài (vd "Quang Trung → Nguyễn Nhạc" và "Nguyễn Nhạc → Quang Trung"). **Không** phải lỗi.

## 2. Template mơ hồ `infobox former country` (D-030)

Wikipedia dùng `{{infobox former country}}` cho **cả** quốc gia **và** triều đại:

| Nhóm | Ví dụ | Loại đúng | Số bài |
|---|---|---|---|
| Quốc gia / địa danh | "Việt Nam Cộng hòa", "Nam Kỳ", "Trung Kỳ" | `place` | 26 |
| **Triều đại** | "Nhà Nguyễn", "Nhà Trần", "Nhà Lý", "Nhà Hồ", "Nhà Mạc"… | `dynasty` | **13** |

Tên template ép `place` → 13 bài triều đại bị gán nhầm → `dong_doi_tai` = **0** triple (vì `docs/04` §3.1 yêu cầu chủ thể `dong_doi_tai` là `dynasty`).

**Cách sửa**: thêm `AMBIGUOUS_TEMPLATES` — khi template mơ hồ **và** có tín hiệu Wikidata (`house`/`dynasty`) thì tín hiệu được ưu tiên; không có tín hiệu → rơi về `type_map`.

> Đo trên corpus: **không** có template riêng cho triều đại (đã quét 2.441 bài) — cả 13 bài "Nhà X" đều dùng `infobox former country`.

## 3. Gộp khoá tham số `_` ↔ khoảng trắng (D-029)

Wikipedia dùng **hai** cách viết khoá tham số: `| noi_sinh =` và `| noi sinh =`. `normalize_name()` giữ nguyên `_` → hai **khoá khác nhau** → bảng mapping viết một biến thể **không bao giờ** được gọi với biến thể kia.

**Cách sửa**: thêm `_collapse_key()` — gộp **cả hai phía** (khoá tham số *và* bảng config) → không mất khoá nào.

## 4. `danh_bai` không được trích từ infobox trận đánh (D-028)

`docs/04` §3.1 quy định `danh_bai`: chủ thể = **người** đánh bại. Thực tế trường `ket qua`/`result` là **câu văn** nêu tên **quốc gia / triều đại / liên minh** → không phải `person`.

Đo trên **207** trận đánh: trích được **4** cặp, **1 cặp sai** (bài "Trận Đông Dương": suy ra "Campuchia đánh bại Đông Dương", đúng ra bên thắng là "Việt Nam Dân chủ Cộng hòa"), và **4/4** vi phạm `RELATION_SUBJECT_TYPES["danh_bai"] = {person}`.

→ Xoá hẳn khối cấu hình `battle_result` + hàm `extract_battle_result()`. `danh_bai` sẽ sinh ở **Phase 8** (mô hình RE/LLM), nơi bằng chứng ở mức câu văn.

## Thang số liệu so sánh (đo bằng ablation)

| Biến thể | Tổng triple | `sinh_nam` | `sinh_tai` | `dong_doi_tai` |
|---|---|---|---|---|
| **FINAL** (đủ 4 fix) | **10.078** | **732** | **1.432** | **31** |
| − `_collapse_key` (D-029) | 10.074 | 732 | 1.429 | 31 |
| − `AMBIGUOUS_TEMPLATES` (D-030) | 10.047 | 732 | 1.432 | **0** |
| − trường thủ đô (A1) | 10.047 | 732 | 1.432 | **0** |
| HEAD (bản đầu, trước audit) | **10.394** | **985** | 1.435 | **0** |

**Đọc bảng:** `sinh_nam` giảm 985 → 732 (−253, **−25,7%**) là do **khử trùng**, không phải mất dữ liệu — 722/732 bài có **đúng 1** `sinh_nam`. `dong_doi_tai` 0 → 31 là **thu hồi** quan hệ bị mất do template mơ hồ.

## Lệnh đã chạy

```bash
python -m src.preprocess.parse_infobox --config configs/default.yaml
→ 1.764/1.764 bài có infobox → 10.078 triple, 1.764 entity

python -m src.preprocess.extract_lead_dates --config configs/default.yaml
→ 736 triple từ đoạn dẫn của 376 bài

pytest -q tests/
→ 280 passed (274 trước audit + 6 test regression mới)

python scripts/stats_infobox.py
→ Gate 1: 100,0% · Gate 2: 92,4% · Gate 3: 100,0% · Gate 4: 100,0% · Gate 5: 0

# assert Gate chính thức trong docs/09 Phase 3
python - <<'PY' ...
PY
→ OK triples 10078
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
| **Gate 4** — triple đủ 9 trường bắt buộc, `method="infobox"`, `confidence ≥ 0.95` | 100% | **100,0%** (10.078 / 10.078) | ✅ |
| **Gate 5** — quan hệ ngoài danh mục 18 quan hệ | 0 | **0** | ✅ |
| &nbsp;&nbsp;└ vi phạm ràng buộc loại chủ thể (`RELATION_SUBJECT_TYPES`) | 0 | **0** | ✅ |
| **Gate 6** (audit) — triple trùng trong 1 doc | 0 | **0** | ✅ |
| **Gate 7** (audit) — self-loop | 0 | **0** | ✅ |
| **Gate 8** (audit) — trùng ngày lead ∩ infobox | 0 | **0** | ✅ |

### Phân bố quan hệ (10.078 triple)

| Quan hệ | Số triple | | Quan hệ | Số triple |
|---|---|---|---|---|
| `chi_huy_tran` | 1.744 | | `dien_ra_tai` | 519 |
| `sinh_tai` | 1.432 | | `ke_vi` | 453 |
| `cha_cua` | 1.094 | | `tham_gia_tran` | 345 |
| `giu_chuc_vu` | 976 | | `me_cua` | 294 |
| `mat_tai` | 953 | | `vo_cua` | 159 |
| `sinh_nam` | 732 | | `chong_cua` | 68 |
| `thuoc_trieu_dai` | 631 | | `dong_doi_tai` | 31 |
| `mat_nam` | 628 | | `lap_ra` | 19 |

**16 / 18** quan hệ được sinh. Hai quan hệ không sinh:

- `anh_em_cua` = **0** — **không bài nào** trong corpus có trường anh em / sibling (đã quét wikitext thô: **0** lần xuất hiện) → **hạn chế dữ liệu**, không phải lỗi code.
- `danh_bai` = **0** — **quyết định có chủ đích** (D-028) → sinh ở Phase 8.

### Phân bố loại chủ thể (10.078 triple)

| Loại | Số triple | | Loại | Số triple |
|---|---|---|---|---|
| `person` | 9.527 | | `dynasty` | 31 |
| `event` | 520 | | | |

### Phân bố loại đối tượng (10.078 triple)

| Loại | Số | | Loại | Số |
|---|---|---|---|---|
| `place` | 2.950 | | `year` | 1.360 |
| `event` | 2.098 | | `title` | 976 |
| `person` | 2.063 | | `dynasty` | 631 |

### Phân bố loại node (1.764 entity)

| Loại | Số entity | | Loại | Số entity |
|---|---|---|---|---|
| `person` | 1.205 | | `dynasty` | 16 |
| `event` | 309 | | `article` | 0 |
| `place` | 234 | | | |

### Phân bố thuộc tính node (`props`)

11 thuộc tính đã chốt tại `docs/09` §Phase 3 — tất cả đều **có dữ liệu thật**:

| Prop | Số entity | | Prop | Số entity |
|---|---|---|---|---|
| `birth_year` | 833 | | `temple_name` | 89 |
| `death_year` | 736 | | `courtesy_name` | 79 |
| `birth_place` | 644 | | `reign_title` | 104 |
| `death_place` | 517 | | `gender` | 23 |
| `posthumous_name` | 217 | | `founded_year` | 23 |
| `reign_start` | 220 | | | |
| `reign_end` | 211 | | | |

`aliases` (top-level, không nằm trong `props` theo hợp đồng entity): **248** entity / **311** alias
(`other` 166 · `birth` 126 · `honorific` 19).

### Truy vết artifact

Cả 3 artifact đều ghi `dump_version` (`20261101`) + `model_name` (`vinai/phobert-base`) —
bắt buộc theo `AGENTS.md` §5.6.

## Gate

- [x] **Gate 1** — ≥ 95% bài có infobox `person` parse thành công → **100,0%**
- [x] **Gate 2** — ≥ 90% bài nhân vật có ≥ 1 trường ngày sinh/mất hoặc quan hệ gia đình → **92,4%**
- [x] **Gate 3** — chuẩn hóa ngày ≥ 95% trên 30 chuỗi mẫu → **100,0%**
- [x] **Gate 4** — 100% triple đủ 9 trường bắt buộc, `method="infobox"`, `confidence ≥ 0.95` → **100,0%**
- [x] **Gate 5** — 0 quan hệ ngoài danh mục → **0**
- [x] **Gate 6** — 0 triple trùng trong 1 doc → **0**
- [x] **Gate 7** — 0 self-loop → **0**
- [x] **Gate 8** — 0 trùng ngày lead ∩ infobox → **0**

## Sai lệch so với kế hoạch

| Mã | Nội dung |
|---|---|
| D-019 | `RELATION_SUBJECT_TYPES` trong `src/common/schemas.py` lệch `docs/04` — đã sửa 4 dòng, **tập 18 quan hệ không đổi** |
| D-020 | `battle` trong `INFOBOX_TYPE_MAP` (Phase 1) trả `"battle"` — không phải loại node KG; Phase 3 map sang `event` trong config riêng, không sửa file Phase 1 |
| D-021 | 146/1.061 bài `person` có template infobox **rỗng** → Gate 1 đo "nhận diện được khối template" (100%), coverage đo ở Gate 2 |
| D-022 | `parse_vi_date` trả ISO 4 chữ số cho năm < 1000 (`0939-02-01`) — `date.isoformat()` trả `939-02-01`, thiếu số 0 |
| D-023 | 3 artifact mới (`infobox_triples.jsonl`, `lead_triples.jsonl`, `infobox_entities.jsonl`) — cập nhật `AGENTS.md` §7 + `docs/09` |
| D-024 | Loại infobox lạ **không** mặc định `person` nữa → `article` (trung tính) + dùng tín hiệu Wikidata; sửa lỗi node "Hà Nội"/"Cần Thơ" bị gán `person` |
| D-025 | Bổ sung `birth_place`/`death_place` vào 11 thuộc tính node; `prop` chỉ ghi khi triple **thực sự** được sinh |
| D-026 | Mọi artifact Phase 3 ghi `dump_version` + `model_name` |
| **D-027** | **Khử trùng triple + loại self-loop + ràng buộc thứ tự chạy** (audit) |
| **D-028** | **Không trích `danh_bai` từ infobox trận đánh** — 4/4 cặp vi phạm schema, 1 cặp sai (audit) |
| **D-029** | **Gộp khoá tham số `_` ↔ khoảng trắng** (`_collapse_key`) (audit) |
| **D-030** | **Template mơ hồ → ưu tiên tín hiệu Wikidata** (`AMBIGUOUS_TEMPLATES`) (audit) |

## Việc tiếp theo

**Phase 4** — Gán nhãn bạc NER: sinh `data/interim/ner_silver.jsonl` từ link + thực thể infobox
(vừa tạo ở Phase 3) → `docs/09` §Phase 4.

## Ghi chú cho Phase sau

- `data/interim/infobox_entities.jsonl` đã có sẵn **1.764 entity** với `props` (birth_year, death_year,
  reign_start/end, temple_name, posthumous_name, courtesy_name, gender, aliases) — đây là nguồn
  cho entity linking ở Phase 8 và node props ở Phase 10.
- Bảng `_LUNAR_YEAR_MAP` trong `src/common/normalize.py` chỉ chứa năm âm lịch **đã đối chiếu**
  với Wikipedia — nếu cần mở rộng, phải bổ sung nguồn (xem `docs/CONTEXT.md` §2.6).
- **`extract_lead_dates.py` phải chạy SAU `parse_infobox.py`** — nó đọc `infobox_triples.jsonl` để biết
  bài nào đã có ngày. Chạy sai thứ tự → `lead_triples.jsonl` stale → trùng ngày (D-027).
- `infobox_entities.jsonl` chỉ có **16** entity loại `dynasty` — dùng làm nguồn nhãn `DYNASTY` ở Phase 4
  nhưng **không** đủ rộng; Phase 4 cần dựa chủ yếu vào tín hiệu Wikidata.

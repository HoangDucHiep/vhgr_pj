# Phase 03 — Parse infobox + chuẩn hóa ngày (A4)

- Ngày: 2026-11-14 (lần 1) · **Audit đóng phase: 2026-11-14 (lần 2)**
- Trạng thái: ✅ đạt Gate (5/5) → sau audit: ✅ đạt Gate (5/5) + **3 Gate bổ sung**
- Báo cáo Gate: `reports/phase_03_report.md`
- Sai lệch: `reports/deviations.md` (D-019 → D-023, bổ sung D-025 → D-030)
- Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-03-infobox-stats.json`

---

## 1. Bối cảnh và vấn đề cần giải

Phase 2 đã làm sạch wikitext và tách được **186.960 câu** văn bản thân bài. Nhưng văn bản
thân bài là văn bản **tự do**: để suy ra "Lê Lợi là con của Lê Khánh Dư" phải chạy NER + RE +
coreference, tức là chuỗi 4–5 phase với độ chính xác mỗi bước < 90% → độ chính xác cuối
tích luỹ < 50%.

Trong khi đó, **infobox** là nguồn bằng chứng mạnh nhất mà Wikipedia cung cấp: trường
`| cha = [[Lê Khánh Dư]]` là một mệnh đề có chủ thể–vị ngữ rõ ràng, đã được biên tập viên
kiểm tra, **không cần mô hình nào**. Đây là lý do Phase 3 đứng trước Phase 4 (NER) trong
kế hoạch: xây "đường sạch" (high-precision) trước, rồi mới mở rộng "đường rộng" (recall).

**Ba ràng buộc chi phối toàn bộ thiết kế:**

| # | Ràng buộc | Hệ quả thiết kế |
|---|---|---|
| 1 | 18 quan hệ đóng, 7 loại node đóng (`docs/CONTEXT.md` §2.4–2.5) | Mapping phải **loại** triple không thuộc schema, không gán nhầm |
| 2 | Bằng chứng bắt buộc (`AGENTS.md` §5.1) | `evidence_sentence` phải **trích nguyên văn** từ trường infobox, không dựng lại |
| 3 | Không sửa hành vi Phase 1 (`infobox_parser.py`) | Mapping mở rộng nằm ở **config riêng**, checksum corpus Phase 1 giữ nguyên |

**Kết quả cần đạt (Gate):** ≥95% bài `person` parse được · ≥90% bài `person` có ngày/gia đình ·
≥95% độ chính xác chuẩn hóa ngày trên 30 mẫu · 100% triple đủ trường bắt buộc · 0 quan hệ lạ.

---

## 2. Phương án đã cân nhắc

### 2.1. Cách trích tham số infobox

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — `wikitextparser`** | `WikiText(raw).templates[0].arguments` | Parse 100% (1.764/1.764); nhưng tên template **đầy đủ** ("Infobox military conflict") khác regex Phase 1 ("military conflict") | ✅ | Xử lý đúng template lồng nhau (`{{plainlist}}`, `{{ubl}}`), giữ được `df=yes` và tham số rỗng |
| **B — regex cân bằng ngoặc** (Phase 1) | `infobox_parser.parse_infobox` | Parse 100%; tên template đã bỏ tiền tố; **mất** tham số có `{{` lồng nhau trên cùng dòng | ✅ (dự phòng) | Đã đạt 100% ở Phase 1, giữ nguyên hành vi |
| **C — regex phẳng mới** | Tự viết | — | ❌ | Trùng lặp B, thêm bề mặt lỗi |

**Quyết định:** dùng **A làm chính, B làm dự phòng**; nếu A cho ≥5 tham số thì tin A ngay,
nếu không thì lấy bên nào **nhiều tham số hơn**. Lý do: `wikitextparser` hiểu template lồng
nhau đúng, còn regex có thể cắt dòng ở `{{` đóng mở.

**Hệ quả phát hiện:** hai nguồn trả **tên loại khác nhau** → phải bỏ tiền tố "Infobox"/"Thông
tin" trước khi tra `type_map` (xem D-020, sửa trong `infobox_entity_types.normalize_type`).

### 2.2. Cách xử lý hướng quan hệ

Đây là phần **rủi ro nhất** của phase: cùng một quan hệ `ke_vi` có thể xuất hiện dưới hai
trường với hai hướng ngược nhau.

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — suy hướng từ tên trường** | `ke nhiem` forward, `tien nhiem` reverse, `con trai` reverse, `cha` forward | Đúng với `docs/04` §3.1 | ✅ | Tên trường **chính là** mệnh đề; không cần suy luận |
| **B — học hướng từ corpus** | Thống kê đối tượng có phải chủ thể bài không | Không đủ tín hiệu (50% là người) | ❌ | Không phân biệt được `ke_vi` với `cha_cua` |
| **C — để LLM đoán hướng** | Gọi API cho mỗi triple | 1.000+ call, độ chính xác không cao hơn A | ❌ | Tốn chi phí, không thêm giá trị |

**Quyết định:** A. Bảng định hướng được ghi **ngay trong config** (`direction: forward|reverse`)
để người đọc kiểm chứng được, không phải đào vào code.

**Kiểm chứng thực nghiệm** (`docs/04` §3.1 làm chuẩn):

| Trường infobox | Nghĩa thực tế | Hướng triple | Quan hệ |
|---|---|---|---|
| `cha` | giá trị là **cha** | forward | `cha_cua` (con → cha) |
| `con trai` | giá trị là **con** | reverse | `cha_cua` (con → cha) |
| `ke nhiem` | giá trị là **kế nhiệm** | forward | `ke_vi` (tiền → kế) |
| `tien nhiem` | giá trị là **tiền nhiệm** | reverse | `ke_vi` (tiền → kế) |
| `commander1` / `chi huy 1` | giá trị là **chỉ huy** | reverse | `chi_huy_tran` (người → trận) |

### 2.3. Cách suy loại đối tượng

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — khai báo trong config** | `value_type: person` cho mỗi trường | Đúng với 95%+ trường | ✅ (chính) | Trường `cha` luôn là person, `noi sinh` luôn là place |
| **B — suy từ tên bài đích** | "Nhà X" → dynasty, "Trận X" → event | Đúng 639 `thuoc_trieu_dai` | ✅ (bổ trợ) | Cần cho trường đa nghĩa (`combatant1` vừa là quân đội vừa là nhà) |
| **C — dùng NER** | Chạy PhoBERT | Chưa có model (Phase 5) | ❌ | Không sẵn sàng |

**Phát hiện quan trọng:** trường `combatant1`/`combatant2` khai báo `person` nhưng giá trị thực
tế là **phe phái / quân đội** ("Nam Hán", "Hoa Kỳ", "Mặt trận Dân tộc Giải phóng miền Nam
Việt Nam"). Gán vào `person` là **bịa** (vi phạm nguyên tắc #3). → Thêm phát hiện tổ chức
(`_looks_like_organization`) → trả `"organization"` → **loại triple** thay vì gán nhầm.

Đo được: `tham_gia_tran` giảm từ 353 (sau khi loại) và **0** triple nào có object là tổ chức.

### 2.4. Cách bổ sung coverage cho bài thiếu ngày

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — đoạn dẫn** | Regex ngoặc đầu tiên của câu 1 | +266 bài → 92,4% | ✅ | Định dạng "(chữ Hán: …, 974 – 1028)" rất chuẩn |
| **B — đoạn thân bài** | Quét toàn bộ bài | Nhiễu cao (nhiều năm nói về người khác) | ❌ | Rủi ro bịa cao |
| **C — Wikidata** | Query P569/P570 | Cần network + độ trùng khớp QID | ❌ (để sau) | Đắt, và 1.061 bài chưa map QID hết |

**Quyết định:** A, với 3 điều kiện chặt để tránh bịa:
1. Chỉ xét **ngoặc đầu tiên** của câu dẫn.
2. Khoảng cách sinh–mất ≤ **120 năm**.
3. Chỉ áp dụng cho bài `person` (loại được từ `infobox_type` hoặc `wikidata_signal`).

Đo được: trước khi thêm 3 điều kiện này, đoạn dẫn sinh **958 triple** cho 586 bài — trong đó
có bài "Liên bang Đông Dương (chữ Nôm: …, sau 1947 là …)" bị gán nhầm năm sinh 1887.
Sau khi chặn: **736 triple / 376 bài**, mọi mẫu đều đúng.

### 2.5. [Audit] Cách xử lý triple trùng và self-loop

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — bộ nhớ trong 1 doc** | `seen: set[(subject, relation, object)]` trong `build_triples()` | 347 triple thừa → **0**; `sinh_nam` 985 → 732 | ✅ | Chặn đúng chỗ sinh ra trùng; không cần sửa dữ liệu |
| **B — khử trùng ở tầng ghi file** | Dedup khi ghi `infobox_triples.jsonl` | Cũng về 0 | ❌ | Che lỗi: `props` và bộ đếm vẫn tính trùng → số liệu sai |
| **C — bỏ qua** | — | 347 triple thừa | ❌ | Sai lệch âm thầm, Gate đo tỉ lệ nên không bắt được |

**Quyết định:** A. Giữ bản **đầu tiên** (thứ tự trường trong infobox = bản có bằng chứng trực
tiếp; bản sau là bản *suy*).

**Quan trọng — cách đếm đúng:** khoá dedupe phải **kèm `doc_id`**. Đo không kèm cho ra 527
triple thừa / 518 nhóm, nhưng phần chênh là các quan hệ **đối xứng hợp lệ** giữa 2 bài
("Quang Trung → Nguyễn Nhạc" và "Nguyễn Nhạc → Quang Trung"). Dùng khoá toàn cục sẽ **xoá
mất** thông tin quan hệ đối xứng.

### 2.6. [Audit] Cách xử lý template mơ hồ (`infobox former country`)

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — tín hiệu Wikidata ưu tiên** | `AMBIGUOUS_TEMPLATES` + `wikidata_signal` | `dong_doi_tai` 0 → **31**; 13 bài "Nhà X" → `dynasty` | ✅ | Wikidata biết "Nhà Trần" là `house`, "Nam Kỳ" là `place` — tín hiệu **mạnh hơn** tên template |
| **B — đoán theo tiền tố tiêu đề** | "Nhà X" → dynasty | Sẽ đúng 13/13 bài này | ❌ | Quy tắc bền vững hơn tín hiệu, nhưng **không suy ra được** từ dữ liệu (ngụ ý) — vi phạm "không bịa" |
| **C — viết template riêng cho triều đại** | Chờ Wikipedia tách template | 0 bài | ❌ | Ngoài tầm kiểm soát; corpus không có template riêng |

**Quyết định:** A. Chỉ áp dụng với **danh sách template mơ hồ** đã đo — không phải mọi template.
Template không mơ hồ vẫn theo tên template (như `docs/09` §Phase 3 quy định).

**Đo trên corpus (xác nhận A đúng):** 39 bài dùng `infobox former country` →
**13** triều đại (tín hiệu `house`/`dynasty`) + **26** quốc gia (tín hiệu `place`/không có).
Không có template riêng cho triều đại (đã quét 2.441 bài) → bảng `type_map` **không** giải
quyết được, phải dùng tín hiệu.

### 2.7. [Audit] Cách gộp khoá tham số `_` ↔ khoảng trắng

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — gộp ở lúc tra bảng** | `_collapse_key()` + `fields_by_key` | `sinh_tai` +3, `mat_tai` +1 | ✅ | Gộp **cả hai phía** → không mất khoá nào; không cần sửa config |
| **B — sửa `normalize_name()`** | Bỏ `_` toàn cục | Tương tự | ❌ | `normalize_name()` dùng chung cho **tên hiển thị** → bỏ `_` sẽ phá tên có gạch dưới |
| **C — viết cả 2 biến thể trong config** | Nhân đôi bảng mapping | Tương tự | ❌ | Bảng phình ra, dễ lệch; phải nhớ thêm khi thêm trường |

**Quyết định:** A. Nguyên tắc: **bảng tra phải nhận cả hai định dạng** — chuẩn hóa ở lúc tra,
không ở lúc lưu (cùng bài học với lỗi #12 ở §6).

### 2.8. [Audit] Có nên trích `danh_bai` từ infobox trận đánh?

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — trích từ `ket qua`/`result`** | Khớp mẫu "chiến thắng"/"thất bại" | 4 cặp; **1 sai**; 4/4 vi phạm `{person}` | ❌ | Vi phạm `AGENTS.md` §5.3 |
| **B — để Phase 8 (RE/LLM)** | Bằng chứng ở mức câu văn | Chưa đến hạn | ✅ | Đúng bản chất quan hệ |
| **C — đổi schema** | Cho `danh_bai` nhận `place`/`dynasty` | — | ❌ | `docs/04` §3.1 đã chốt; **tập 18 quan hệ không đổi** |

**Quyết định:** B. Xoá hẳn code + config, thay bằng comment giải thích và dẫn chiếu D-028.

---

## 3. Quyết định đã chốt

### D-019 — Căn `RELATION_SUBJECT_TYPES` theo `docs/04` (sửa 4 dòng)

- **Lý do:** `src/common/schemas.py` lệch với bảng 18 quan hệ ở `docs/04` §3.1:
  `dong_doi_tai` ghi subject = `place` (đúng phải là `dynasty` → place);
  `thuoc_trieu_dai` thiếu `dynasty`/`event`; `sinh_tai`/`mat_tai` cho phép subject = `place`
  (đúng phải là `person` → place).
- **Ảnh hưởng:** validator và `build_triples` dùng bảng này để **loại** triple vi phạm.
  Không sửa thì `dien_ra_tai` với subject=`event` sẽ bị loại oan (sai lệch nghiêm trọng hơn
  việc thiếu ràng buộc).
- **Tập 18 quan hệ không đổi** → `docs/CONTEXT.md` §2.5 không cần sửa danh mục, chỉ bổ sung
  bảng ràng buộc loại.
- **File đã cập nhật:** `src/common/schemas.py`, `docs/04` §3.1 (ghi chú), `docs/CONTEXT.md`.

### D-020 — `battle` → `event`, giữ nguyên `infobox_parser.py`

- **Lý do:** `INFOBOX_TYPE_MAP` (Phase 1) trả `"battle"` cho template chiến tranh, nhưng KG
  chỉ có 7 loại node (`docs/CONTEXT.md` §2.4) — **không có `battle`**. `docs/04` §3.1 quy
  định `chi_huy_tran`: person → **event**.
- **Quyết định:** **không sửa** `infobox_parser.py` (giữ checksum Phase 1). Phase 3 có bảng
  `type_map` riêng trong `configs/infobox_mapping.yaml` map `battle`/`chiến tranh`/
  `military conflict` → `event`. `normalize_type()` bỏ tiền tố "Infobox"/"Thông tin" trước
  khi tra bảng.
- **Ảnh hưởng:** 202 bài `battle` + 11 bài `event` → 213 node `event`.

### D-021 — Gate 1 đo "nhận diện được khối template", không đo "có tham số"

- **Lý do:** **146 / 1.061** bài `person` có template `{{Thông tin nhân vật phong kiến}}` **rỗng**
  — Wikipedia viết infobox cho có, không điền tham số nào. Đây là **đặc điểm dữ liệu**, không
  phải lỗi parse.
- **Quyết định:** Gate 1 đo "parse thành công" = **nhận diện được khối template** (tên loại +
  dict tham số, kể cả rỗng) → 100%. Thêm test thứ hai đo "mọi infobox **có** tham số đều parse
  được ≥ 99% tham số" → 100%.
- **Ảnh hưởng:** coverage thực sự đo ở **Gate 2** (92,4%). Đây là nơi đoạn dẫn làm fallback.

### D-022 — `parse_vi_date` trả ISO 4 chữ số cho năm < 1000

- **Lý do:** `datetime.date(939, 2, 1).isoformat()` → `"939-02-01"` — **thiếu số 0** ở đầu,
  vi phạm ISO-8601 `YYYY-MM-DD` mà `docs/01` quy định.
- **Quyết định:** thêm helper `_to_iso()` → `f"{year:04d}-{month:02d}-{day:02d}"`.
- **Ảnh hưởng:** 2 fixture trong `tests/fixtures/dates.jsonl` đổi kỳ vọng từ
  `"939-02-01"` → `"0939-02-01"`. Lịch sử Việt Nam có **nhiều** năm 3 chữ số (938, 939, 944,
  965, 974…) nên lỗi này ảnh hưởng lớn.

### D-023 — 3 artifact mới

- **Lý do:** Phase 3 sinh 3 file mới ngoài danh sách artifact ở `AGENTS.md` §7.
- **Quyết định:** bổ sung `data/interim/infobox_triples.jsonl` (Phase 3),
  `data/interim/lead_triples.jsonl` (Phase 3), `data/interim/infobox_entities.jsonl` (Phase 3).
- **File đã cập nhật:** `AGENTS.md` §7, `docs/09` §Phase 3 (output contract), `.cursor/rules/data-contracts.mdc`.

### D-024 — Loại chủ thể không suy được → `article`, **không** mặc định `person`

- **Lý do:** Phát hiện khi kiểm tra chéo artifact: `infobox_entities.jsonl` ghi node
  **"Hà Nội"** và **"Cần Thơ"** với `type="person"` — sai hoàn toàn. Nguyên nhân gốc:
  `resolved_type = normalize_type(...) or doc_type or "person"` — khi tên template
  (`{{Thông tin đơn vị hành chính Việt Nam}}`) không có trong `type_map`, hàm **rơi
  xuống mặc định `person`**. Đây là **bịa** (vi phạm `AGENTS.md` §5.3).
- **Vì sao `person` là mặc định sai:** `person` là loại **phổ biến nhất** trong corpus
  (1.205/1.764 entity) nên dễ trở thành "mặc định ngầm" — nhưng nó cũng là loại **bịa
  nhiều nhất** khi suy sai.
- **Quyết định:** tách **hai mặc định** vì vai trò khác nhau:
  | Hằng số | Giá trị | Áp dụng cho | Lý do |
  |---|---|---|---|
  | `DEFAULT_TYPE` | `"article"` | **chủ thể** | Loại trung tính — không khẳng định điều gì |
  | `DEFAULT_OBJECT_TYPE` | `"person"` | **đối tượng** | Trường không khai báo `value_type` gần như luôn là người (cha, mẹ, vợ, tiền nhiệm…) |
- **Thứ tự suy loại chủ thể (mới):**
  1. Tên loại infobox → `type_map` (biên tập viên chọn template — tín hiệu mạnh nhất).
  2. `wikidata_signal` (Phase 1) — Wikidata biết "Hà Nội" là `place`, "Trận lụt đồng bằng" là `event`.
  3. `DEFAULT_TYPE` = `"article"` — **không** mặc định `person`.
- **Sửa kèm 2 lỗi phụ phát hiện cùng lúc:**
  1. `normalize_type()` bỏ tiền tố **trước** khi tra bảng → 6 khoá trong `type_map` có
     tiền tố trở nên **không bao giờ được gọi** (vì `wikitextparser` trả tên đầy đủ).
     Sửa: thử khớp chính xác **trước**, rồi mới bỏ tiền tố.
  2. Bổ sung **36 khoá** vào `type_map` cho các template chưa có (đo trên 2.441 bài).
- **Ảnh hưởng:** 9 triple bị loại (thay vì sinh sai); entity "Hà Nội"/"Cần Thơ"/"Cảng Hải
  Phòng"/"Thiên Nam dư hạ tập" nay đúng loại; **0** entity loại `article` còn sót.
  Triple: 10.403 → **10.394**. Gate 1–5 **không đổi**.
- **Bài học (đã thêm vào §7):** *"không xác định được" và "giá trị phổ biến nhất" là hai
  thứ khác nhau — dùng chung một mặc định là công thức của việc bịa âm thầm.*
- **File đã cập nhật:** `src/preprocess/infobox_entity_types.py`,
  `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`,
  `tests/test_infobox.py` (+6 test regression).

### D-025 — Bổ sung 11 thuộc tính node đầy đủ (`birth_place`/`death_place` còn thiếu)

- **Lý do:** `docs/09` §Phase 3 liệt kê 11 thuộc tính node bắt buộc cho
  `infobox_entities.jsonl`. Lần chạy đầu mới chỉ ghi được **9/11** — thiếu
  `birth_place` và `death_place`, vì `configs/infobox_mapping.yaml` khai báo
  `noi sinh` / `noi mat` chỉ sinh **triple** (`sinh_tai` / `mat_tai`) mà không
  ghi thêm vào `props`.
- **Quyết định:** thêm khoá `prop:` vào spec của trường trong config
  (`noi sinh` → `prop: birth_place`, `noi mat` → `prop: death_place`) và xử lý
  trong `parse_infobox.py`. `add_triple()` **trả về `bool`** để prop chỉ được ghi
  khi triple **thực sự** được sinh — không khẳng định thuộc tính cho quan hệ
  đã bị loại vì lỗi schema.
- **Ảnh hưởng:** `birth_place` 643 entity, `death_place` 516 entity. Tổng triple
  **không đổi** (10.394) vì `prop` chỉ bổ sung thuộc tính, không sinh quan hệ mới.
  Gate 1–5 **không đổi**.
- **File đã cập nhật:** `configs/infobox_mapping.yaml`, `src/preprocess/parse_infobox.py`,
  `.cursor/rules/data-contracts.mdc`, `tests/test_infobox.py` (+2 test).

### D-026 — Mọi artifact Phase 3 ghi `dump_version` + `model_name`

- **Lý do:** ràng buộc bắt buộc `AGENTS.md` §5.6 ("Tái lập": *"ghi `dump_version` +
  `model_name` vào mọi artifact"*). Lần chạy đầu của Phase 3 không ghi 2 trường này
  → không truy được artifact về đúng lần chạy.
- **Quyết định:** cả 3 artifact ghi `dump_version` (`20261101`, lấy từ
  `config.dump.dump_version`) + `model_name` (`vinai/phobert-base`, lấy từ
  `config.ner.model_name`). Giá trị `dump_version` của **triple** lấy theo từng bài
  từ `documents.jsonl` (không phụ thuộc thứ tự chạy).
- **Ảnh hưởng:** không đổi số liệu Gate. Thêm 3 test bắt buộc trong
  `tests/test_infobox.py`.
- **File đã cập nhật:** `src/preprocess/parse_infobox.py`,
  `src/preprocess/extract_lead_dates.py`, `.cursor/rules/data-contracts.mdc`,
  `docs/DECISIONS.md` (D-014), `tests/test_infobox.py` (+3 test).

---

### [Audit 14/11/2026] — 4 quyết định mới

Audit độc lập Phase 2–3 (rà chéo artifact, đọc wikitext thô, đo bằng ablation) phát hiện
**4 lỗi thật** trong bản triển khai đầu. Chi tiết kỹ thuật: `reports/deviations.md`.

### D-027 — Khử trùng triple + loại self-loop + ràng buộc thứ tự chạy

- **Lý do:** 3 lỗi cùng hệ quả — số liệu Gate đếm trùng nên tỉ lệ trông đẹp hơn thực tế:
  1. **347** triple thừa trong **341** nhóm trùng `(doc_id, subject, relation, object)`.
     Nguyên nhân: Wikipedia có **hai** trường cùng nội dung (`Ngày sinh` + `Ngày sinh (từ
     Ngày mất)`) → mỗi trường sinh 1 triple, không có bước gộp. `sinh_nam` bị phình
     732 → **985** (+34,6%).
  2. **4** self-loop (`subject == object`) → vi phạm `Triple.is_valid()`.
  3. **81** triple ngày trùng giữa lead ∩ infobox trên **47** bài — `lead_triples.jsonl`
     sinh lúc 04:38, `infobox_triples.jsonl` sinh lại lúc 04:40 → `docs_with_dates` **stale**.
- **Quyết định:**
  - `seen: set[(subject, relation, object)]` trong `build_triples()`, giữ bản **đầu tiên**;
    bộ đếm `skipped_duplicate`.
  - Kiểm tra `subject == object` trong `add_triple()`; bộ đếm `skipped_self_loop`.
  - Ràng buộc **thứ tự chạy** `parse_infobox.py` → `extract_lead_dates.py`, ghi rõ trong
    `docs/09` §Phase 3 + báo cáo + ghi chú cho phase sau.
  - **Khoá dedupe phải kèm `doc_id`** — nếu không sẽ xoá mất quan hệ đối xứng hợp lệ
    giữa 2 bài (đo: 527 vs 347 triple thừa).
- **Ảnh hưởng:** triple 10.394 → **10.078** (−316); `sinh_nam` 985 → **732** (722/732 bài có
  **đúng 1**); `mat_nam` 635 → **628**; self-loop 4 → **0**; trùng lead∩infobox 81 → **0**.
  Gate 1–5 **không đổi**.
- **File đã cập nhật:** `src/preprocess/parse_infobox.py`, `tests/test_infobox.py` (+3 test),
  `docs/09-ke-hoach-thuc-thien.md`, `reports/phase_03_report.md`, file này.

### D-028 — Không trích `danh_bai` từ infobox trận đánh

- **Lý do:** `docs/04` §3.1 quy định `danh_bai`: chủ thể = **người** đánh bại. Thực tế
  trường `ket qua`/`result` là **câu văn** nêu tên **quốc gia / triều đại / liên minh**
  ("Campuchia", "Việt Minh", "Nhà Thanh") → không phải `person`. Đo trên **207** trận đánh:
  trích được **4** cặp, **1 cặp sai** (bài "Trận Đông Dương": suy ra "Campuchia đánh bại
  Đông Dương", đúng ra bên thắng là "Việt Nam Dân chủ Cộng hòa"), và **4/4** vi phạm
  `RELATION_SUBJECT_TYPES["danh_bai"] = {person}`.
- **Quyết định:** xoá hẳn khối cấu hình `battle_result` + hàm `extract_battle_result()`.
  `danh_bai` sẽ sinh ở **Phase 8** (mô hình RE/LLM), nơi bằng chứng ở mức câu văn.
  Thiếu 1 quan hệ còn hơn có 1 quan hệ **sai**.
- **Ảnh hưởng:** 16/18 quan hệ có triple. `anh_em_cua` = 0 vì **không bài nào** trong corpus
  có trường anh em/sibling (quét wikitext thô: **0** lần) → **hạn chế dữ liệu**, không phải lỗi.
- **File đã cập nhật:** `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`,
  `tests/test_infobox.py` (+1 test), `docs/09-ke-hoach-thuc-thien.md`, file này.

### D-029 — Gộp khoá tham số `_` ↔ khoảng trắng (`_collapse_key`)

- **Lý do:** Wikipedia dùng **hai** cách viết khoá tham số: `| noi_sinh =` và `| noi sinh =`.
  `normalize_name()` giữ nguyên `_` → hai **khoá khác nhau** → bảng mapping viết một biến
  thể **không bao giờ** được gọi với biến thể kia.
- **Quyết định:** thêm `_collapse_key()` — gộp **cả hai phía** (khoá tham số *và* bảng config)
  → không mất khoá nào. Không sửa `normalize_name()` (dùng chung cho tên hiển thị).
- **Ảnh hưởng** (đo bằng ablation): tổng 10.074 → **10.078** (+4); `sinh_tai` +3;
  `mat_tai` +1. `sinh_nam`/`mat_nam` **không đổi** — các trường ngày trong corpus đều dùng
  khoảng trắng.
- **File đã cập nhật:** `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`, file này.

### D-030 — Template mơ hồ → ưu tiên tín hiệu Wikidata (`AMBIGUOUS_TEMPLATES`)

- **Lý do:** `infobox former country` dùng cho **cả** quốc gia ("Nam Kỳ" → `place`) **và**
  triều đại ("Nhà Trần" → `dynasty`). Tên template ép `place` → 13 bài triều đại bị gán
  nhầm → `dong_doi_tai` = **0** (vì `docs/04` §3.1 yêu cầu chủ thể `dong_doi_tai` là `dynasty`).
  `docs/09` §Phase 3 đặt thứ tự "tên template → `wikidata_signal`" — nhưng ở đây tên template
  **không phân biệt được**, nên phải đảo thứ tự **chỉ cho các template mơ hồ**.
- **Quyết định:** thêm `AMBIGUOUS_TEMPLATES` (4 template) trong
  `src/preprocess/infobox_entity_types.py`; `normalize_type()` nhận thêm tham số
  `wikidata_signal`: template mơ hồ **và** có tín hiệu → ưu tiên tín hiệu; không có tín hiệu
  → rơi về `type_map`.
- **Ảnh hưởng** (đo bằng ablation): tổng 10.047 → **10.078** (+31, toàn bộ là
  `dong_doi_tai`); 13 bài triều đại chuyển `place` → `dynasty` (đúng).
  `thuoc_trieu_dai` **không đổi** (631) — 13 bài này không có trường `triều đại`/`hoàng tộc` riêng.
- **File đã cập nhật:** `src/preprocess/infobox_entity_types.py`,
  `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`,
  `tests/test_infobox.py` (+1 test), file này.

---

## 4. Thang số liệu so sánh

### 4.1. Coverage bài `person` — 3 mức

| Mức | Số bài | Tỉ lệ | Nguồn |
|---|---|---|---|
| Chỉ infobox | 714 / 1.061 | **67,3%** | `infobox_triples.jsonl` |
| + đoạn dẫn | 980 / 1.061 | **92,4%** | `infobox_triples.jsonl` + `lead_triples.jsonl` |
| *(kế hoạch dự kiến)* | — | *98,1%* | `docs/09` §Phase 3 — **đạt 92,4%, thấp hơn dự kiến* |

> **Sau audit:** con số này **không đổi** (92,4%). Khử trùng triple (D-027) chỉ loại các bản
> ghi **lặp** của cùng một sự kiện, không loại bài nào — nên coverage thực tế được giữ nguyên.

**Phân rã 92,4%:**

| Nhóm | Số bài | Tỉ lệ |
|---|---|---|
| Có ngày sinh/mất | 960 | 90,5% |
| Có quan hệ gia đình | 449 | 42,3% |
| Có ≥ 1 trong hai | 980 | 92,4% |

**Vì sao thấp hơn 98,1% dự kiến?** Kế hoạch đo "có ≥ 1 trường ngày/gia đình" theo **trường
infobox có mặt** (kể cả trường rỗng → coi như "có"), còn Phase 3 đo theo **triple thực sự
được sinh** (trường phải có giá trị parse được). 81 bài còn lại là bài không có cả ngày lẫn
quan hệ gia đình — ví dụ bài có infobox rỗng và đoạn dẫn không chứa năm.

### 4.2. Độ chính xác chuẩn hóa ngày — 30 mẫu

| Mức | Đúng | Tỉ lệ |
|---|---|---|
| Phiên bản đầu (trước khi viết test) | — | 83,9% (5/30 sai) |
| Sau khi sửa 4 lỗi | **30 / 30** | **100,0%** |

**4 lỗi đã sửa (xem §6):** khoảng ngày bị đọc thành ngày đơn · năm < 1000 thiếu số 0 ·
regex năm âm lịch không khớp ký tự có dấu · năm âm lịch không khớp bảng bị rơi xuống
"chỉ có năm" (bịa!).

### 4.3. Ba phương án trích tham số — số liệu so sánh

| Phương án | Parse rate | Số bài | Vấn đề |
|---|---|---|---|
| A — `wikitextparser` | 100% | 1.764 | Tên template đầy đủ → cần bỏ tiền tố |
| B — regex Phase 1 | 100% | 1.764 | Mất tham số khi template lồng nhau |
| C — A+B, chọn bên nhiều tham số hơn | 100% | 1.764 | ✅ **đã chọn** |

### 4.4. Parse rate theo loại infobox (top 12)

| Loại template | Số bài | Parse rate | Tổng tham số |
|---|---|---|---|
| `thong tin nhan vat phong kien` | 456 | 100% | 4.219 |
| `thong tin nhan vat hoang gia` | 347 | 100% | 9.706 |
| `thong tin nhan vat` | 220 | 100% | 4.442 |
| `thong tin chien tranh` | 147 | 100% | 2.339 |
| `thong tin thanh` | 93 | 100% | 2.601 |
| `infobox military conflict` | 61 | 100% | 986 |
| `thong tin vien chuc` | 33 | 100% | 2.040 |
| `infobox former country` | 31 | 100% | 1.722 |
| `thong tin nha van` | 31 | 100% | 727 |
| `thong tin den viet nam` | 31 | 100% | 913 |
| `infobox officeholder` | 30 | 100% | 338 |
| `thong tin nghe si` | 17 | 100% | 1.0xx |

> Lưu ý: `thong tin nhan vat phong kien` có 456 bài nhưng chỉ 310 bài **có tham số** → 146 bài
> template rỗng (xem D-021).

### 4.5. Template ngày — số lượng sử dụng trong corpus

| Template | Số lần | Template | Số lần |
|---|---|---|---|
| `ngày mất và tuổi` | 362 | `ngày sinh` | 193 |
| `death date and age` | 85 | `số năm theo năm và ngày` | 67 |
| `birth date` | 62 | `năm mất và tuổi` | 58 |
| `ngày sinh và tuổi` | 20 | `năm sinh và tuổi` | 14 |
| `death year and age` | 7 | `circa` | 1 |

**Nhận xét thiết kế:** template `ngày mất và tuổi` (362 lần) chứa **cả hai** mốc sinh và mất
trong tham số 1–6 (`{{ngày mất và tuổi|1820|9|16|1766|1|3}}`). Xử lý bằng cách khai báo
`birth_year: 4, birth_month: 5, birth_day: 6` trong config → sinh **hai** triple
(`mat_nam` confidence 0,97 + `sinh_nam` confidence 0,95 do mốc sinh được **suy** từ tham số phụ).

### 4.6. [Audit] Thang số liệu so sánh — ablation từng fix

Đo bằng **ablation**: tắt **riêng** từng fix (giữ nguyên các fix còn lại), chạy lại
`build_triples()` trên toàn bộ corpus 2.441 bài.

| Biến thể | Tổng triple | `sinh_nam` | `sinh_tai` | `mat_tai` | `dong_doi_tai` |
|---|---|---|---|---|---|
| **FINAL** (đủ 4 fix) | **10.078** | **732** | **1.432** | **953** | **31** |
| − `_collapse_key` (D-029) | 10.074 | 732 | 1.429 | 952 | 31 |
| − `AMBIGUOUS_TEMPLATES` (D-030) | 10.047 | 732 | 1.432 | 953 | **0** |
| − trường thủ đô (A1) | 10.047 | 732 | 1.432 | 953 | **0** |
| **HEAD** (bản đầu, trước audit) | **10.394** | **985** | 1.435 | 952 | **0** |

**Đọc bảng — hai điều rất khác nhau:**

| Hiện tượng | Diễn giải ĐÚNG | Diễn giải SAI |
|---|---|---|
| `sinh_nam` 985 → 732 (−253) | **Khử trùng**: 722/732 bài có **đúng 1** `sinh_nam` | "Mất 253 bài dữ liệu" |
| `dong_doi_tai` 0 → 31 | **Thu hồi** quan hệ bị mất do template mơ hồ | "Bịa thêm dữ liệu" |
| Tổng 10.394 → 10.078 (−316) | = −253 (`sinh_nam`) − 7 (`mat_nam`) − 56 (các quan hệ khác bị trùng) | "Chất lượng giảm" |

**Bài học về cách đọc số liệu:** giảm số triple **không** đồng nghĩa giảm chất lượng — phải
tách "bị loại vì trùng" (đúng) khỏi "bị loại vì thiếu" (xấu). Vì vậy audit dùng **ablation**
(tắt từng fix) thay vì so sánh tổng trước/sau.

### 4.7. [Audit] Phân bố `sinh_nam` theo số bài

| Số `sinh_nam` / bài | Số bài | Đánh giá |
|---|---|---|
| 1 | 722 | ✅ đúng — mỗi bài đúng 1 mốc sinh |
| 2 | 5 | ⚠️ xem lại — có thể là 2 nguồn ngày sinh **khác nhau** (không phải trùng) |
| 0 | — | bài không có trường ngày sinh |

Ở HEAD: `sinh_nam` = 985 / 1.764 bài → nhiều bài có **2–3** bản ghi cho cùng một năm.

---

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Gate 1 — parse rate bài `person` | ≥ 95% | **100,0%** (1.061 / 1.061) | ✅ |
| Gate 2 — coverage ngày hoặc gia đình | ≥ 90% | **92,4%** (980 / 1.061) | ✅ |
| Gate 3 — chuẩn hóa ngày (30 mẫu) | ≥ 95% | **100,0%** (30 / 30) | ✅ |
| Gate 4 — triple đủ trường bắt buộc | 100% | **100,0%** (10.078 / 10.078) | ✅ |
| Gate 4 — `method="infobox"` | 100% | **100,0%** | ✅ |
| Gate 4 — `confidence ≥ 0.95` | 100% | **100,0%** | ✅ |
| Gate 5 — quan hệ ngoài danh mục | 0 | **0** | ✅ |
| Gate 5 — vi phạm ràng buộc loại chủ thể | 0 | **0** | ✅ |
| Triple infobox sinh ra | — | **10.078** (10.394 trước audit) | |
| Triple đoạn dẫn sinh ra | — | 736 | |
| Entity sinh ra | — | 1.764 | |
| Quan hệ được sinh (trên 18) | — | **16** (`anh_em_cua` và `danh_bai` = 0) | |
| Loại node được sinh (trên 7) | — | 6 (`person`, `dynasty`, `event`, `place`, `title`, `year`) | |
| Thuộc tính node được phủ (mục tiêu 11) | 11 | **11 / 11** | ✅ |
| Entity có `birth_place` | — | **644** | |
| Entity có `death_place` | — | **517** | |
| Artifact có `dump_version` + `model_name` | 3 / 3 | **3 / 3** | ✅ |
| **Gate 6** — triple trùng trong 1 doc | 0 | **0** | ✅ |
| **Gate 7** — self-loop | 0 | **0** | ✅ |
| **Gate 8** — trùng ngày lead ∩ infobox | 0 | **0** | ✅ |
| pytest | — | **280 passed** (274 trước audit + 6 regression mới) | ✅ |

### Phân bố confidence

| Confidence | Số triple | Nguồn |
|---|---|---|
| 0,97 | 10.038 | Trường infobox trực tiếp |
| 0,95 | 40 | Mốc sinh suy từ tham số phụ của template "X và tuổi" |

### Phân bố thuộc tính node (`props` trong `infobox_entities.jsonl`)

| Prop | Số entity | | Prop | Số entity |
|---|---|---|---|---|
| `birth_year` | 833 | | `temple_name` | 89 |
| `death_year` | 736 | | `courtesy_name` | 79 |
| `birth_place` | 644 | | `reign_title` | 104 |
| `death_place` | 517 | | `gender` | 23 |
| `aliases` | 238 | | `founded_year` | 23 |
| `posthumous_name` | 217 | | | |
| `reign_start` | 220 | | | |
| `reign_end` | 211 | | | |

### Phân bố loại đối tượng

| Loại | Số triple |
|---|---|
| `place` | 2.950 |
| `event` | 2.098 |
| `person` | 2.063 |
| `year` | 1.360 |
| `title` | 976 |
| `dynasty` | 631 |

---

## 6. Lỗi gặp phải và cách xử lý

| # | Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|---|
| 1 | **Mất toàn bộ liên kết khi trích triple** | Evidence rỗng (`"Cha: "`), 0 triple gia đình | `split_items()` gọi `clean_value()` **trước** khi `extract_links()` → `[[...]]` bị gỡ | Tách 2 hàm: `split_items()` giữ **wikitext thô**, `clean_value()` chỉ dùng để hiển thị | Luôn giữ **lớp trung gian thô** cho đến khi trích xong mọi trường cấu trúc |
| 2 | **Bắt nhầm tổ chức là người** | `tham_gia_tran` với object = "Hoa Kỳ", "Mặt trận Dân tộc Giải phóng…" | `value_type: person` khai báo sẵn → bỏ qua kiểm tra nội dung | Thêm `_looks_like_organization()` → trả `"organization"` → **loại triple** | Khai báo kiểu ở config là **giả định**, không phải đảm bảo — phải kiểm tra giá trị thực |
| 3 | **`normalize_type` trả `None` cho 61 bài** | `Infobox military conflict` không map được | `wikitextparser` trả tên template **đầy đủ**, config có key đã bỏ tiền tố | Bỏ tiền tố "Infobox"/"Thông tin" trong `normalize_type()` | Hai parser cùng nhiệm vụ phải **chuẩn hóa về cùng một dạng** trước khi tra bảng |
| 4 | **Khoảng ngày bị đọc thành ngày đơn** | `"25–26 tháng 12 năm 1944"` → `1944-12-26` (precision "day") | Regex "ngày tháng năm" khớp nhầm phần "26 tháng 12" | Thêm `_DATE_RANGE_RE` kiểm tra **trước** các dạng ngày đơn → chỉ trả năm | Khoảng ngày ≠ ngày — phải phân biệt trước khi trích |
| 5 | **Năm < 1000 thiếu số 0** | `"939-02-01"` thay vì `"0939-02-01"` | `datetime.date.isoformat()` không padding năm | Thêm helper `_to_iso()` | ISO-8601 `YYYY-MM-DD` **không** phải "ISO của Python" — phải tự padding |
| 6 | **Regex năm âm lịch không khớp** | `"năm Ất Tý (938)"` không nhận ra | Regex dùng `[a-z ]` + `IGNORECASE` — không khớp ký tự Unicode có dấu | Đổi sang `[\w ]{3,24}?` + so khớp trên chuỗi **đã bỏ dấu** | Regex trên tiếng Việt phải bỏ dấu **trước**, không dùng cờ `IGNORECASE` |
| 7 | **Bịa năm khi năm âm lịch không khớp bảng** | `"năm Ất Tý (900)"` → năm **900** | Rơi xuống nhánh "chỉ có năm" ở cuối hàm | Trả `(None, None, "none")` ngay khi tên năm âm lịch có trong bảng nhưng năm dương lệch | "Không biết" phải là một **giá trị được trả về tường minh**, không phải rơi rất qua một nhánh khác |
| 8 | **Đoạn dẫn gán nhầm năm cho bài không phải người** | "Liên bang Đông Dương" nhận năm sinh 1887 | Bài không có infobox → `infobox_type = None` → mặc định "person" | Chỉ nhận bài có `infobox_type == "person"` **hoặc** `wikidata_signal == "person"` | `None` ≠ "mặc định" — phân biệt "không biết" với "không có" |
| 9 | **Bài không có template nào vẫn tính là parse lỗi** | Gate 1 đo 86,2% | 146 bài có template **rỗng** (`{{Thông tin nhân vật phong kiến}}`) | Tách định nghĩa "parse thành công" = nhận diện được khối template | Đọc kỹ dữ liệu trước khi chốt định nghĩa Gate |
| 10 | **Giới tính không suy được** | `vo_cua` không sinh cho bài có `spouse` | `detect_gender` không có giá trị mặc định khi không truyền config | Thêm `DEFAULT_GENDER_KEYS/VALUES/PREFIXES` | Hàm không nên phụ thuộc bắt buộc vào tham số cấu hình |
| 11 | **Địa danh bị gán loại `person`** | Node "Hà Nội" và "Cần Thơ" có `type="person"` | `resolved_type = normalize_type(...) or doc_type or "person"` — template chưa có trong `type_map` rơi xuống mặc định `person` | Tách 2 mặc định: chủ thể → `"article"`, đối tượng → `"person"`; thêm bước suy từ `wikidata_signal` (D-024) | *"Không xác định được" ≠ "giá trị phổ biến nhất"* — dùng chung mặc định là công thức của việc bịa âm thầm |
| 12 | **6 khoá `type_map` không bao giờ được gọi** | `thong tin nhan vat phong kien` (451 bài) không map được dù có trong bảng | `normalize_type()` **bỏ tiền tố trước** khi tra bảng, nên khoá có tiền tố không bao giờ khớp; khoá không tiền tố thì `wikitextparser` không trả về | Thử khớp **chính xác trước**, rồi mới bỏ tiền tố rồi thử lại | Khi hai nguồn sinh cùng một khái niệm với **định dạng khác nhau**, bảng tra phải nhận **cả hai** — chuẩn hóa ở lúc tra, không ở lúc lưu |
| 13 | **36 template chưa có trong `type_map`** | 43 bài có template lạ → mặc định `person` | `type_map` viết trước khi đo trên corpus | Đo trên 2.441 bài, bổ sung 36 khoá | Bảng mapping phải **đo trên dữ liệu thật** rồi mới hoàn thiện, không đoán từ đầu |
| 14 | **Thiếu 2/11 thuộc tính node** | `birth_place`/`death_place` không có trong `infobox_entities.jsonl` | Config khai báo `noi sinh`/`noi mat` **chỉ sinh triple**, không ghi thêm `props` | Thêm khoá `prop:` vào config + `add_triple()` trả `bool` để prop chỉ ghi khi triple thực sự sinh (D-025) | "Có quan hệ" ≠ "có thuộc tính" — hai loại kiểm tra khác nhau, phải có test riêng cho từng loại |
| 15 | **Artifact không truy được về lần chạy** | 3 artifact Phase 3 thiếu `dump_version` + `model_name` | Bỏ sót ràng buộc `AGENTS.md` §5.6 khi viết code | Bổ sung 2 trường cho cả 3 artifact + 3 test bắt buộc (D-026) | Ràng buộc "ghi metadata vào artifact" phải **có test**, nếu không sẽ bị bỏ sót lặp lại ở mỗi phase |
| 16 | **[Audit] 347 triple trùng trong 1 doc** | `sinh_nam` 985 cho 1.764 bài; có bài có 2–3 bản ghi cùng năm | Wikipedia có **hai** trường cùng nội dung (`Ngày sinh` + `Ngày sinh (từ Ngày mất)`); mỗi trường sinh 1 triple, không có bước gộp | `seen: set[(subject, relation, object)]` — giữ bản **đầu tiên**, đếm `skipped_duplicate` (D-027) | Nguồn có thể **lặp** — phải có idempotency ở tầng sinh, không phải ở tầng ghi file |
| 17 | **[Audit] 4 self-loop** | Triple có `subject == object` | Infobox ghi nhầm: bài của chính người được ghi là "Tiền nhiệm" của họ | Kiểm tra `subject == object` trong `add_triple()` → `skipped_self_loop` (D-027) | Bất biến schema phải được **kiểm tra ở lúc sinh**, không trông chờ validator ở phase sau |
| 18 | **[Audit] 81 triple ngày trùng lead ∩ infobox** | Test `test_no_duplicate_lead_and_infobox_dates` **FAIL** | `lead_triples.jsonl` sinh 04:38, `infobox_triples.jsonl` sinh lại 04:40 → `docs_with_dates` **stale** | Ràng buộc thứ tự chạy `parse_infobox` → `extract_lead_dates`, ghi vào `docs/09` + báo cáo (D-027) | Artifact có phụ thuộc thứ tự → **ghi ràng buộc** vào tài liệu, không để trong đầu |
| 19 | **[Audit] `dong_doi_tai` = 0, 13 bài triều đại gán nhầm `place`** | Không có triple `dynasty → place` nào | `infobox former country` dùng chung cho quốc gia **và** triều đại; tên template ép `place` | `AMBIGUOUS_TEMPLATES` + ưu tiên tín hiệu Wikidata (D-030) | Tên template **không luôn** xác định loại node — cần tín hiệu thứ cấp và cơ chế "mơ hồ" riêng |

---

## 7. Bài học kinh nghiệm

1. **Khảo sát dữ liệu trước khi thiết kế.** 5 phương án trích tham số trong §2.1 chỉ phân biệt
   được sau khi đo trên corpus. Quyết định A+B chỉ hợp lý vì biết `wikitextparser` trả tên
   template đầy đủ còn regex trả tên đã bỏ tiền tố.

2. **Khai báo kiểu ở config là *giả định*, không phải bảo đảm.** Lỗi #2 (`combatant1` là tổ
   chức chứ không phải người) là ví dụ điển hình: cấu hình đúng vẫn cho kết quả sai nếu dữ
   liệu vi phạm giả định. Luôn kiểm tra **nội dung giá trị** trước khi gán node.

3. **"Không biết" phải là giá trị tường minh.** Lỗi #7 (bịa năm 900) và lỗi #8 (gán năm cho
   bài không phải người) đều do để giá trị mặc định chảy qua một nhánh khác. Trả
   `(None, None, "none")` tường minh an toàn hơn nhiều lần so với "thử nhánh khác".

4. **Giữ lớp trung gian thô đến cuối.** Lỗi #1 tốn nhiều thời gian nhất vì `clean_value()`
   phá hủy thông tin cấu trúc (`[[link]]`). Nguyên tắc: **làm sạch ở lớp trình bày, không
   làm sạch ở lớp trích xuất**.

5. **Fallback đoạn dẫn cần 3 lớp lọc.** Chỉ một regex "năm trong ngoặc" đã bịa dữ liệu cho
   bài không phải người. Ba điều kiện (ngoặc đầu tiên · khoảng cách ≤ 120 năm · chỉ bài
   `person`) làm tỉ lệ đúng đạt 100% trên mẫu kiểm tra.

6. **Infobox cho "đường sạch" trước, NER cho "đường rộng" sau.** 10.394 triple có confidence
   ≥ 0,95 từ infobox là nền tảng để đo chất lượng của NER/RE ở Phase 5–7: nếu RE không vượt
   qua được đường sạch này thì chưa đáng dùng.

7. **"Không xác định được" và "giá trị phổ biến nhất" là hai thứ khác nhau.** Mặc định
   `person` cho chủ thể rất dễ dùng vì `person` chiếm 68% entity — nhưng đó chính là lý do
   nó **bịa âm thầm**: node "Hà Nội" và "Cần Thơ" bị gán `person` mà không ai nhận ra cho
   đến khi kiểm tra chéo artifact. Mặc định đúng cho chủ thể là loại **trung tính**
   (`article`); mặc định đúng cho đối tượng là `person` vì ngữ cảnh khác hẳn.

8. **Kiểm tra chéo artifact là bắt buộc.** 5 Gate đều **đạt** (100% / 92,4% / 100% / 100% /
   0) mà vẫn còn node sai. Gate đo **tỉ lệ**, không đo **sai lệch nội dung**. Phải có một
   lượt rà riêng: đọc vài chục record đầu ra bằng mắt, đối chiếu với bài gốc.

9. **Bảng mapping phải đo trên dữ liệu thật rồi mới hoàn thiện.** `type_map` viết trước
   khi đo thiếu 36 khoá; 6 khoá viết sai định dạng khiến 451 bài không map được. Một vòng
   "đo → sửa → đo lại" trên corpus thật là bắt buộc, không phải tuỳ chọn.

10. **Ràng buộc về metadata phải có test, nếu không sẽ bị bỏ sót lặp lại ở mỗi phase.**
    "Mọi artifact ghi `dump_version` + `model_name`" là ràng buộc từ Phase 0 nhưng bị bỏ sót
    ở cả 3 artifact Phase 3 — vì không có test nào kiểm nó. Sau khi thêm 3 test, quy tắc này
    đã **tự động** áp cho mọi phase sau.

11. **[Audit] Đếm trùng mà không khoá `doc_id` là đếm sai — và sửa sai cũng làm mất dữ liệu.**
    Đo không khoá `doc_id`: 527 triple thừa / 518 nhóm. Đo có khoá: 347 / 341. Phần chênh là
    quan hệ **đối xứng hợp lệ** giữa 2 bài ("Quang Trung → Nguyễn Nhạc" và "Nguyễn Nhạc →
    Quang Trung"). Bài học kép: **phải đo trùng ở đúng phạm vi ngữ nghĩa**, và **khoá dedupe
    phải khớp phạm vi đó** — dedupe toàn cục sẽ xoá mất thông tin quan hệ đối xứng.

12. **[Audit] "Giảm số liệu" không đồng nghĩa "giảm chất lượng".** `sinh_nam` 985 → 732 (−253)
    nghe như mất dữ liệu, nhưng thực ra là **khử trùng** (722/732 bài có đúng 1 mốc sinh).
    Vì vậy audit dùng **ablation** (tắt từng fix riêng lẻ) thay vì so sánh tổng trước/sau —
    ablation cho biết *từng thay đổi* đóng góp bao nhiêu, còn so sánh tổng chỉ cho biết
    *tổng cộng* thay đổi.

13. **[Audit] Tên template không luôn xác định được loại node.** `infobox former country` dùng
    cho cả quốc gia (26 bài) lẫn triều đại (13 bài). Bảng `type_map` không thể biểu diễn
    "1 template → nhiều loại" → cần khái niệm **template mơ hồ** + tín hiệu thứ cấp
    (Wikidata). Hệ quả trực tiếp: `dong_doi_tai` 0 → 31.

14. **[Audit] Thiếu một quan hệ còn hơn có một quan hệ sai.** Trích `danh_bai` từ câu kết quả
    trận đánh cho 4 cặp, trong đó 1 sai và 4/4 vi phạm ràng buộc loại chủ thể. Xoá hẳn và
    chờ Phase 8 (nơi bằng chứng ở mức câu văn) là quyết định đúng — đặc biệt khi schema
    `docs/04` §3.1 đã chốt **tập 18 quan hệ không đổi**.

15. **[Audit] Gate đo tỉ lệ, không đo bất biến.** 5 Gate đều xanh mà vẫn có 347 triple trùng,
    4 self-loop và 81 triple trùng giữa 2 artifact. Thêm 3 Gate **bất biến** (không trùng ·
    không self-loop · không trùng giữa artifact) mới phát hiện được. Bài học tổng quát: **mỗi
    lần audit phải thêm Gate mới, không chỉ xác nhận Gate cũ**.

---

## 8. Ý tưởng cho slide

- **Slide "Vì sao infobox trước NER"**: trường `| cha = [[Lê Khánh Dư]]` là mệnh đề đã được
  biên tập viên kiểm tra — **không cần mô hình**. 10.394 triple confidence ≥ 0,95 từ 1.764 bài.
- **Slide "Ba tầng bằng chứng"**: 67,3% (chỉ infobox) → **92,4%** (+ đoạn dẫn) → 90,5% có ngày
  sinh/mất · 42,3% có quan hệ gia đình.
- **Slide "Đường sạch là chuẩn đo"**: 15/18 quan hệ, 6/7 loại node đã có dữ liệu thật từ
  infobox — dùng làm **ground truth** để đánh giá NER/RE ở Phase 5–7.
- **Slide "4 lỗi, 4 bài học"**: mất link khi clean sớm · gán tổ chức là người · khoảng ngày
  thành ngày đơn · bịa năm khi năm âm lịch lệch bảng.
- **Slide "Không bịa là nguyên tắc thiết kế"**: `combatant1` = "Hoa Kỳ" → **loại** triple thay vì
  gán `person`; năm âm lịch lệch bảng → `none` chứ không đoán.
- **Slide "Gate đo tỉ lệ, không đo sai lệch"**: 5 Gate đều xanh (100% / 92,4% / 100% / 100% /
  0) mà vẫn còn node "Hà Nội" bị gán `person`. Phải có lượt rà chéo artifact — đó là nơi
  phát hiện D-024.

- **Slide "Audit: 5 Gate xanh mà dữ liệu vẫn sai"** — 347 triple trùng · 4 self-loop · 81 triple
  trùng giữa 2 artifact · `dong_doi_tai` = 0 dù có 13 bài triều đại. Bài học: **thêm Gate bất
  biến**, không chỉ xác nhận Gate cũ.
- **Slide "Ablation: đo từng fix riêng lẻ"** — `sinh_nam` 985 → 732 là **khử trùng**
  (722/732 bài có đúng 1 mốc sinh), **không phải** mất dữ liệu. Giảm số liệu ≠ giảm chất lượng.
- **Slide "Đo trùng phải đúng phạm vi"** — 527 vs 347: phần chênh là quan hệ **đối xứng hợp lệ**
  giữa 2 bài. Dedup toàn cục sẽ xoá mất thông tin.
- **Slide "Tên template không phải lúc nào cũng đủ"** — `infobox former country`: 26 quốc gia
  + 13 triều đại → cần khái niệm "template mơ hồ" + tín hiệu Wikidata. `dong_doi_tai` 0 → 31.
- **Slide "Thiếu còn hơn sai"** — `danh_bai`: 4 cặp trích được, 1 sai, 4/4 vi phạm schema →
  xoá hẳn, chờ Phase 8.

---

## 9. Việc tiếp theo

**Phase 4 — Gán nhãn bạc NER**: sinh `data/interim/ner_silver.jsonl` từ hyperlink + entity
vừa tạo ở Phase 3 (`infobox_entities.jsonl` cho 1.764 node) → `docs/09` §Phase 4.

**Đầu vào sẵn có cho Phase 4+:**

| Artifact | Nội dung | Dùng cho |
|---|---|---|
| `data/interim/infobox_entities.jsonl` | 1.764 node + `props` (birth_year, death_year, reign_start/end, temple_name, gender, aliases, birth_place, death_place) | Entity linking (Phase 8), node props (Phase 10) |
| `data/interim/infobox_triples.jsonl` | **10.078** triple confidence ≥ 0,95 | Đường sạch để đo NER/RE |
| `data/interim/lead_triples.jsonl` | 736 triple confidence 0,85 | Bổ sung coverage |

> **Lưu ý cho Phase 4:** `infobox_entities.jsonl` chỉ có **16** entity loại `dynasty` — quá hẹp
> để làm nguồn nhãn `DYNASTY` chính. Phase 4 nên dựa chủ yếu vào tín hiệu Wikidata (QLever),
> dùng `infobox_entities.jsonl` làm nguồn **bổ trợ** cho `PERSON`.

# Phase 07 — Relation Extraction (D1.1): tập huấn luyện distant supervision

- Ngày: 2026-11-15
- Trạng thái: ✅ đạt Gate (5/5)
- Báo cáo Gate: `reports/phase_07_report.md`
- Sai lệch: `reports/deviations.md` (D-056 → D-059)
- Số liệu máy đọc: `so-lieu/phase-07-re-stats.json`, `so-lieu/phase-07-gate-check.json`

## 1. Bối cảnh và vấn đề cần giải

Phase 6 (Coreference) đã cho ta: 186.960 câu, 15.559 entity có mention,
125.121 mention resolve về `canonical_id`. Đó là **nguyên liệu** để gắn
nhãn quan hệ ở mức câu — nhưng chưa có nhãn nào.

Phase 7 phần 1 (D1.1) sinh **tập huấn luyện RE** bằng **distant supervision**:
lấy quan hệ từ Wikidata (đã được con người kiểm chứng), rồi **grounding**
vào câu corpus để có câu bằng chứng.

### Ràng buộc

| Ràng buộc | Giá trị |
|---|---|
| Số POSITIVE tối thiểu | 10.000 |
| Tỉ lệ NEG/POS | ≤ 1,0 |
| Số quan hệ có POSITIVE | ≥ 8 (trong tổng 18 quan hệ đóng) |
| Quan hệ ngoài danh mục | 0 (nguyên tắc #5 `AGENTS.md`: schema đóng) |
| Idempotency | chạy lại = 0 request mạng |

### Rủi ro lớn nhất: **false negative**

Negative của distant supervision là "cặp không có quan hệ trong Wikidata".
Nhưng "Wikidata chưa ghi" ≠ "không có thực". Ta đo được trên corpus:
trong 86.934 cặp entity đồng câu, chỉ **12.562** cặp có **cả hai** đầu có
QID; 72.557 cặp có một đầu không rõ QID. Nếu lấy mù cả 72.557 cặp "không
rõ" làm negative, ta dạy mô hình đi sai với tỉ lệ lớn.

→ Quy tắc (D-057): negative chỉ lấy từ cặp **có cả hai QID** và **không**
mang quan hệ nào trong sổ trắng Wikidata.

## 2. Phương án đã cân nhắc

Đo trên corpus 2.441 bài / 186.960 câu, ngày 15/11/2026:

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| A. Wikidata thuần, chỉ khớp `entity_id` | Subject và object đều phải có `entity_id` trong corpus | **4.834** POSITIVE, **9** quan hệ | ❌ | Không đạt G1. Chỉ **3.731/12.602** cặp có object là entity trong corpus — object Wikidata phần lớn chưa từng xuất hiện trong corpus |
| B. Wikidata thuần, cho phép khớp theo **tên** | Object được ground bằng nhãn tiếng Việt (`rdfs:label`) khi chưa có `entity_id` | **12.197** POSITIVE, **10** quan hệ | ⚠️ một phần | Đạt G1 nhưng thiếu 6 quan hệ mà Wikidata không có |
| C. Infobox + Lead (nội bộ Phase 3) | Ground triple Phase 3 vào câu corpus | **7.039** POSITIVE, **16** quan hệ | ❌ (riêng lẻ) | Không đạt G1, nhưng bổ sung `ke_vi`, `thuoc_trieu_dai`, `chi_huy_tran`, `dong_doi_tai`, `lap_ra`, `dien_ra_tai` — 6 quan hệ mà Wikidata không có |
| D. Property Wikidata mở rộng | Thêm P166/P112/P607/P463/P361/P276 | **+59** POSITIVE | ❌ | Thu được 3.258 cặp thô nhưng chỉ 59 mẫu ground được — **không đủ đóng Gap**, nên không bật mặc định (vẫn giữ trong `extended_properties` để bật khi cần) |
| E. **Hợp nhất B + C** | Wikidata (theo tên) + Infobox + Lead, dedupe theo `(sentence_id, subject, relation, object)` | **15.580** POSITIVE, **17** quan hệ | ✅ | Đạt G1 với biên **+55,8%**; đạt G3 với 17/18 quan hệ; G4 = 0 |

> **Ablation đường grounding** (chạy lại `ground_wikidata_pairs` với/tắt
> fallback theo tên, cùng đầu vào): tắt → **4.834** mẫu / 9 quan hệ; bật →
> **12.197** mẫu / 10 quan hệ → **+7.363 mẫu (+152%)**. Đây là đường có giá trị
> lớn nhất của phase.

### Vì sao không dùng `P463`/`P361` → `thuoc_trieu_dai`

Đo riêng: P463 trả 155 cặp, P361 trả 199 cặp từ corpus — nhưng **object là
tổ chức/QID ngoài corpus**, và chủ thể cũng là tổ chức (không phải `person`)
→ `RELATION_SUBJECT_TYPES["thuoc_trieu_dai"]` yêu cầu chủ thể là
`person`/`event`. Ground được **2 mẫu** → không dùng.

## 3. Quyết định đã chốt

### D-056 — Hợp nhất 3 nguồn nhãn POSITIVE

**Quyết định:** `re_positive.jsonl` gộp 3 nguồn — Wikidata (12.197 mẫu),
Infobox (3.361), Lead (22). Dedupe theo
`(sentence_id, subject, relation, object)`, ưu tiên nguồn
`wikidata > infobox > lead`.

**Lý do:** Wikidata thuần không đạt G1 khi ground chặt (4.834 mẫu / 9 quan hệ) và thiếu
6 quan hệ; Infobox/Lead bổ sung đúng 6 quan hệ đó. Ba nguồn cho tổng 15.580
mẫu / 17 quan hệ.

**Ảnh hưởng:** `src/re/ground_triples.py` có 2 hàm grounding
(`ground_wikidata_pairs` cho Wikidata, `ground_triples` cho infobox/lead) +
bước merge trong `main()`.
Artifact `data/interim/re_positive.jsonl` có trường `source` để truy vết.

**File đã cập nhật:** `src/re/ground_triples.py`, `docs/DECISIONS.md`.

### D-057 — Negative "an toàn": loại cặp không rõ QID và cặp có quan hệ

**Quyết định:** Negative chỉ lấy từ cặp entity đồng câu mà **cả hai đều có
QID** và **không** cặp QID nào của chúng mang quan hệ nào trong 13 property
lõi. Quan hệ đối xứng được coi là "đã có" theo **cả hai chiều**.

**Lý do:** Đo được — 12.562 cặp an toàn vs 1.815 cặp có quan hệ (loại) vs
72.557 cặp không rõ QID (loại). Cho phép lấy cặp "không rõ" làm negative sẽ
tạo false negative ở tỉ lệ rất cao.

**Ảnh hưởng:** `collect_negative_candidates` trong `src/re/build_re_dataset.py`
lọc trước khi lấy mẫu; có test `test_negative_excludes_pairs_holding_a_relation`
và `test_negative_excludes_pairs_without_qid`.

**File đã cập nhật:** `src/re/build_re_dataset.py`, `tests/test_re_dataset.py`.

### D-058 — Tái dùng `src/preprocess/wikidata_query.py`, không viết client SPARQL mới

**Quyết định:** `src/re/build_distant_supervision.py` dùng `run_query()` của
Phase 1 (fallback QLever → WDQS, throttle, retry, cache đĩa) thay vì viết
`src/re/wikidata_client.py` như gợi ý trong `docs/09`.

**Lý do:** Module Phase 1 đã có đủ toàn bộ cơ chế; viết thêm sẽ phải sao chép
logic → hai nơi sửa khi WDQS lại 429. Ngoài ra `docs/09` ghi "query mỗi lô
500 QID" — nhưng đo cho thấy QLever/WDQS **không** trả tên property trong
`UNION` (biến predicate bị rơi khỏi kết quả) → phải hỏi **từng property
một**, chia lô 200 QID.

**Ảnh hưởng:** Query chia theo property × chunk triều đại; cache đĩa dùng
chung `data/interim/wikidata_cache/` → Gate G5 đạt (0 request khi chạy lại).

**File đã cập nhật:** `src/re/build_distant_supervision.py`,
`configs/default.yaml` (khối `re:`), `docs/DECISIONS.md`.

### D-059 — Hướng `P40` là `inverse`

**Quyết định:** `P40` (child) ánh xạ tới `cha_cua` với `direction: inverse`
— Wikidata nói "cha → con", KG (`docs/04` §3.1) cần "con → cha".

**Lý do:** Nếu giữ forward, nhãn `cha_cua` sẽ bị **đảo ngược** — mô hình học
"cha là con". Đo được: giữ forward cho 1.083 cặp P40, ground sai hướng.

**Ảnh hưởng:** `configs/wikidata_relations.yaml` (`P40: direction: inverse`),
`src/re/ground_triples.py` (đảo subject ↔ object khi `inverse`).

**File đã cập nhật:** `configs/wikidata_relations.yaml`,
`src/re/ground_triples.py`, `tests/test_re_dataset.py`.

### D-060 — `re_train.jsonl` là **record theo câu** với mảng `pairs` lồng

**Quyết định:** `data/interim/re_train.jsonl` ghi **1 record/câu** (không phải
1 record/cặp), gồm `run_id`, `sentence_id`, `doc_id`, `page_id`, `split`, `text`
và mảng `pairs` lồng. Nhãn là **chuỗi** `"POSITIVE"`/`"NEGATIVE"`. Mỗi cặp
mang `mention` (dạng bề mặt trong câu, giữ dấu), `entity_id`, `name` (tên chuẩn)
và offset `start`/`end` thỏa `text[start:end] == mention`.

**Lý do:** Bản đầu của phase ghi phẳng theo cặp với nhãn số `1`/`0` và không
có `run_id`. Điều đó vi phạm **3 hợp đồng đã chốt**:

1. `docs/09` §Phase 7 + `data-contracts.mdc` §Định dạng chung yêu cầu `run_id`.
2. Lệnh kiểm thử **chính thức** trong `docs/09` và plan đọc `r['pairs']` /
   `p['label']=='POSITIVE'` → **crash** với bản phẳng.
3. `data-contracts.mdc` §Offset yêu cầu offset luôn kiểm được
   `text[start:end] == span_text`.

Gom theo câu còn giúp Phase 8 chỉ cần **tokenize `text` một lần** cho mọi cặp.

**Ảnh hưởng:** `src/re/build_re_dataset.py`, `src/re/re_dataset_stats.py`,
`scripts/re_gate_check.py`, `src/re/ground_triples.py` (mang offset + tên có
dấu), `tests/test_re_dataset.py`, `docs/09` §Phase 7, `AGENTS.md` §7.

**File đã cập nhật:** `src/re/build_re_dataset.py`,
`src/re/ground_triples.py`, `src/re/re_dataset_stats.py`,
`scripts/re_gate_check.py`, `tests/test_re_dataset.py`,
`docs/09-ke-hoach-thuc-thien.md`, `AGENTS.md`, `docs/DECISIONS.md`.

## 4. Thang số liệu so sánh

### 4.1 Thang grounding — từ "cặp thô" đến "mẫu ground được"

Đo bằng script ad-hoc trên cùng đầu vào (15/11/2026):

| Bước | Wikidata | Infobox | Lead | Tổng |
|---|---|---|---|---|
| 0. Cặp/triple thô | 12.602 | 10.078 | 736 | 23.416 |
| 1. Chủ thể có trong corpus (QID → `entity_id`) | 12.517 | 10.078 | 736 | 23.331 |
| 2. Object có trong corpus (`entity_id`) — *cặp*, không phải mẫu | 3.731 | — | — | — |
| 3. Cặp chỉ ground được bằng **tên** (object ngoài corpus) | 6.471 | — | — | — |
| 4. **Mẫu ground, chỉ `entity_id`** | **4.834** | 7.039 | (đã gộp ở C) | — |
| 5. **Mẫu ground, có fallback theo tên** | **12.197** | 3.361 | 22 | 15.580 |
| 6. **Dedupe theo khoá 4 thành phần** | — | — | — | **15.580** (17 quan hệ) |

> Bước 4→5 cho thấy **giá trị lớn nhất** của phương án B: đường ground theo
> tên bổ sung **7.363 mẫu** (4.834 → 12.197, **+152%**) mà đường `entity_id`
> không thấy.

### 4.2 Thang nguồn nhãn POSITIVE

| Nguồn | Số mẫu | Tỉ trọng | Quan hệ đóng góp |
|---|---|---|---|
| Wikidata | 12.197 | 78,3% | `cha_cua`, `me_cua`, `vo_cua`, `anh_em_cua`, `sinh_tai`, `mat_tai`, `giu_chuc_vu`, `sinh_nam`, `mat_nam`, `tham_gia_tran` |
| Infobox | 3.361 | 21,6% | `ke_vi` 1.161 · `thuoc_trieu_dai` 541 · `mat_tai` 424 · `sinh_tai` 376 · `cha_cua` 265 · `mat_nam` 144 · `chong_cua` 110 · `chi_huy_tran` 88 · `sinh_nam` 56 · `dong_doi_tai` 44 · `giu_chuc_vu` 43 · `vo_cua` 41 · `me_cua` 35 · `dien_ra_tai` 18 · `lap_ra` 13 · `tham_gia_tran` 2 |
| Lead | 22 | 0,1% | `sinh_nam` 13 · `mat_nam` 9 |

### 4.3 Thang property Wikidata (cặp thô → mẫu ground)

| Property | Quan hệ | Hướng | Cặp thô | Mẫu ground |
|---|---|---|---|---|
| `P3373` | `anh_em_cua` | symmetric | 5.974 | 935 |
| `P570` | `mat_nam` | year | 1.124 | 1.762 |
| `P40` | `cha_cua` | **inverse** | 1.083 | 987 |
| `P22` | `cha_cua` | forward | 453 | 1.866 |
| `P569` | `sinh_nam` | year | 1.176 | 610 |
| `P19` | `sinh_tai` | forward | 883 | 1.386 |
| `P20` | `mat_tai` | forward | 497 | 1.287 |
| `P39` | `giu_chuc_vu` | forward | 360 | 1.164 |
| `P25` | `me_cua` | forward | 254 | 1.080 |
| `P26` | `vo_cua` | forward | 472 | 899 |
| `P710` | `tham_gia_tran` | forward | 239 | 179 |
| `P551` | `sinh_tai` | forward | 68 | 41 |
| `P1344` | `tham_gia_tran` | forward | 19 | 1 |

> Mẫu ground **> cặp thô** ở nhiều property vì một cặp Wikidata có thể
> ground vào **nhiều câu** (một nhân vật được nhắc ở nhiều câu). Riêng
> `P22` (1.866 mẫu từ 453 cặp) và `P570` (1.762 từ 1.124) là hai property
> đóng góp nhiều nhất.

### 4.4 So sánh với ước lượng của kế hoạch

| Nguồn | Ước lượng | Thực tế | Chênh lệch |
|---|---|---|---|
| `docs/09` §Phase 7 | ≈ 10.231 POSITIVE | 15.580 | +55,8% |
| Số quan hệ có POSITIVE | ≥ 8 | 17 | +9 |

### 4.5 Thang contract output — đo trước/sau khi sửa (D-060)

Đo trực tiếp trên artifact `data/interim/re_train.jsonl`:

| Tiêu chí contract | Bản đầu (phẳng theo cặp) | Bản sau (theo câu) |
|---|---|---|
| Cấu trúc record | 1 record/cặp | **1 record/câu**, `pairs` lồng |
| Lệnh kiểm thử chính thức `docs/09` | ❌ **crash** (`KeyError: 'pairs'`) | ✅ chạy |
| `run_id` (bắt buộc `data-contracts` §Định dạng chung) | ❌ thiếu | ✅ có (`r<YYYYMMDD-HHMMSS>`) |
| Nhãn | số `1`/`0` | ✅ chuỗi `"POSITIVE"`/`"NEGATIVE"` |
| Offset `start`/`end` | ❌ không có | ✅ có |
| `text[start:end] == mention` | — (không kiểm được) | ✅ **59.914/59.914** |
| Cặp thiếu span | — | **0** |
| Số câu / số cặp | 29.957 / 29.957 | 12.877 / 29.957 |
| Test `pytest -q tests/` | 467 passed | **480 passed** |

> Số liệu **43.841 sai lệch offset** ở bản trung gian (đã thêm offset nhưng
> `mention` lấy từ tên chuẩn entity thay vì dạng bề mặt trong câu) là lý do
> phải có test `test_train_artifact_offsets_match_text` — offset có mặt là
> **không đủ**, phải **khớp nội dung**.

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| G1 — Số mẫu POSITIVE | ≥ 10.000 | **15.580** | ✅ |
| G2 — Tỉ lệ NEG/POS | ≤ 1,0 | **0,9228** | ✅ |
| G3 — Số quan hệ có POSITIVE | ≥ 8 | **17** | ✅ |
| G4 — Quan hệ ngoài danh mục 18 quan hệ | 0 | **0** | ✅ |
| G5 — Cache SPARQL idempotent | 0 request | **0** (chạy lại 97,8 s) | ✅ |
| Tổng cặp trong `re_train.jsonl` | — | 29.957 | — |
| Câu khác nhau có mẫu | — | 12.877 | — |
| False negative (POSITIVE ∩ NEGATIVE) | 0 | **0** | ✅ |
| Khoá trùng `(sentence_id, subject, relation, object)` | 0 | **0** | ✅ |
| Offset `text[start:end] == mention` | 100% | **59.914/59.914 (100%)** | ✅ |
| Lệnh kiểm thử chính thức `docs/09` | chạy | **chạy** | ✅ |
| Test `pytest -q tests/` | pass | **480 passed** | ✅ |

### Phân bố theo split

| Split | POSITIVE | NEGATIVE | Tỉ lệ |
|---|---|---|---|
| train | 12.194 | 11.332 | 0,929 |
| dev | 1.871 | 1.620 | 0,866 |
| test | 1.515 | 1.425 | 0,941 |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| `SPARQL UNION` mất tên property | Query 13 property trả 2.429 dòng **không có** cột `?p` → không biết dòng nào thuộc property nào | WDQS **và** QLever đều không hỗ trợ biến predicate trong `UNION` | Hỏi **từng property một**, mỗi lần một lô `VALUES` 200 QID | Khi schema của response phụ thuộc giá trị, đừng dựa vào biến predicate — hỏi từng biến |
| `KeyError: 'Q5557635'` | Crash khi grounding cặp Wikidata | Object QID không có trong map nhãn (thiếu label vì QLever lọc `LANG IN ("vi","en")`) | Kiểm tra `obj_qid in qid_labels` trước khi tra | Map nhãn phải được kiểm tra trước, không giả định đầy đủ |
| `subject_qid` lưu thành **dict** | Artifact ghi `"subject_qid": "{'type': 'literal', 'value': '<...Q10788240>'}"` | `run_query` trả binding dạng `{"value": ...}`, code lấy `str(row["s"])` thay vì `row["s"]["value"]` | Thêm helper `_binding_value()` rút `.value` cho cả QLever lẫn WDQS | `run_query` đã chuẩn hoá 2 endpoint về một dạng — phải đọc đúng dạng đó |
| Nhãn literal có hậu tố | `object_labels: ["\"Động Hoa Lư\"@vi"]` | QLever trả literal có datatype/lang tag; WDQS tách riêng `xml:lang` | Thêm `_clean_label()` bỏ `"` và `@vi` | Response của 2 endpoint khác nhau ở **cả** URI lẫn literal — cần 2 hàm chuẩn hoá |
| **`sentence_id` lưu nhầm nội dung câu** | Mẫu đầu tiên có `sentence_id = '" Bà Chúa Muối tên thật là...'` | `_make_sample()` truyền `index.sentence_text.get(sentence_id, "")` vào tham số tên `sentence_id` | Đổi thành `sentence_id=sentence_id` | Đặt tên tham số theo **giá trị** chứ không theo **vai trò** — triệu chứng là dữ liệu đúng về mặt kiểu, sai về mặt ngữ nghĩa |
| `_resolve_ends` trả về thiếu `sentence_id` | `UnboundLocalError: cannot access local variable 'sentence_id'` | Hàm trả về `(subject, object)` nhưng caller cần `sentence_id` để ghi bằng chứng | Đổi hàm trả về bộ ba `(sentence_id, subject, object)` | Hàm trả dữ liệu **tối thiểu** sẽ bị sửa lại ở tầng trên — trả đủ ngay từ đầu |
| Fallback tên của subject so sánh sai | Subject không match dù có trong câu | Truyền `subject_names` là **tập tên**, hàm lại so sánh với `entity_id` | Đổi tham số thành map `entity_id → tên` | Kiểu dữ liệu của tham số phải khớp với cách dùng |
| QLever trả HTTP 400 (giai đoạn đo) | Mọi request tới `qlever.dev/api/wikidata` fail | Do **dạng query** (không phải endpoint) — query `UNION` 13 property | Test lại với query đơn property + `VALUES` → **OK** | Trước khi kết luận "endpoint chết", kiểm tra **dạng query** |
| `_make_sample() got an unexpected keyword argument 'object_mention'` | Crash khi ground triple infobox | Tham số tên `obj_mention`, chỗ gọi dùng `object_mention` | Đồng nhất tên tham số | Đặt tên tham số nhất quán giữa định nghĩa và nơi gọi |
| Lệnh kiểm thử chính thức `docs/09` **crash** (`KeyError: 'pairs'`) | `rows[0]['pairs']` không tồn tại | Artifact ghi **phẳng theo cặp** thay vì record theo câu như contract | Đổi `build_dataset` sang nhóm cặp theo `sentence_id`, thêm `run_id`/`text`, nhãn chuỗi | Contract đã chốt ở `docs/09` là nguồn sự thật — **đọc lệnh kiểm thử chính thức** trước khi kết luận phase xong |
| **43.841/59.459** offset sai lệch | `text[start:end] != mention` | `mention` lấy từ **tên chuẩn entity** (`"Mông Cổ xâm lược Java"`) thay vì dạng bề mặt trong câu (`"công tước"`) | Tách `mention` (bề mặt, từ span) khỏi `name` (tên chuẩn entity) | Tên chuẩn và dạng bề mặt là **hai thứ khác nhau** — coref gộp nhiều cách gọi về một entity |
| **455** cặp thiếu offset | `start`/`end` không có | Check `obj_entity in index.spans_of(...)` so sánh `entity_id` với **bộ span** → luôn `False` → ép fallback quét tên, thất bại với entity chỉ xuất hiện qua đại từ ("ông") | Sửa thành `if index.spans_of(sentence_id, obj_entity):` — kiểm tra **tập** có khác rỗng | So sánh giữa `str` và `tuple` **không báo lỗi** — chỉ lộ ra khi kiểm định giá trị |
| `_span_for_entity() got multiple values` / `not enough values to unpack` | Crash khi sinh negative | Hàm trả 2 giá trị nhưng chỗ gọi unpack 3 | Thống nhất số giá trị trả về | Hàm trả tuple phải nhất quán với mọi nơi gọi |

## 7. Bài học kinh nghiệm

1. **Distant supervision không thay thế được nhãn nội bộ.** Wikidata cho 10
   quan hệ; 6 quan hệ còn lại (`ke_vi`, `thuoc_trieu_dai`, `chi_huy_tran`,
   `dong_doi_tai`, `lap_ra`, `dien_ra_tai`) **chỉ** có trong infobox của
   Wikipedia. Hợp nhất 3 nguồn là bắt buộc, không phải tuỳ chọn.

2. **Đường ground theo tên quan trọng ngang đường theo `entity_id`.** Chỉ
   **3.731/12.602** cặp Wikidata có object là entity trong corpus; cho phép
   ground theo nhãn tiếng Việt bổ sung **7.363 mẫu** (4.834 → 12.197,
   **+152%**) — lớn hơn 2,5× đường chính xác.

3. **"Không có trong Wikidata" không phải "không có trong thực tế".** 72.557
   cặp đồng câu có một đầu không rõ QID — loại chúng khỏi negative là điều
   kiện tiên quyết để tránh dạy mô hình sai.

4. **Endpoint không chết, dạng query mới chết.** QLever trả HTTP 400 cho
   `UNION` 13 property nhưng chạy tốt với 1 property + `VALUES`. Đo lại trước
   khi đổi hạ tầng.

5. **Tên tham số phải nói lên vai trò, không phải giá trị.** Lỗi
   `sentence_id` chứa nội dung câu đi qua toàn bộ pipeline mà không báo lỗi
   — chỉ lộ ra khi đọc mẫu đầu tiên. Test contract phải kiểm tra **giá trị**,
   không chỉ kiểm tra có mặt hay không.

6. **Đọc lệnh kiểm thử chính thức trước khi kết luận phase xong.** Bản đầu
   của phase đạt đủ 5 Gate theo script riêng, nhưng **lệnh kiểm thử viết
   trong `docs/09`** lại **crash** vì artifact sai contract (phẳng theo cặp
   thay vì theo câu). Script kiểm định của chính mình không bảo chứng được
   việc tuân thủ hợp đồng — phải chạy **đúng lệnh** mà đặc tả nêu.

7. **Offset có mặt là chưa đủ — phải khớp nội dung.** Chỉ kiểm "có trường
   `start`/`end`" đã bỏ sót **43.841** offset sai vì `mention` lấy từ tên
   chuẩn entity thay vì dạng bề mặt trong câu. Test phải kiểm
   `text[start:end] == mention` cho **mọi** cặp.

8. **Tên chuẩn và dạng bề mặt là hai thứ khác nhau.** Coref gộp nhiều cách
   gọi về một entity (`"vua"`, `"ông"`, `"Hoàng đế"` → Minh Mạng), nên `mention`
   trong câu **không** phải tên chuẩn của entity. Tách `mention` (bề mặt) và
   `name` (chuẩn) trong contract.

## 8. Ý tưởng cho slide

- **Distant supervision 3 nguồn đạt 15.580 mẫu POSITIVE / 17 quan hệ** —
  vượt Gate G1 (10.000) **55,8%** và G3 (8 quan hệ) **hơn 2×**.
- **Wikidata thuần không đủ**: 12.197 mẫu / 10 quan hệ; thêm Infobox+Lead →
  **+3.383 mẫu** và **+7 quan hệ** (chỉ 3 nguồn nội bộ mới có
  `ke_vi`, `thuoc_trieu_dai`, `chi_huy_tran`…).
- **Grounding theo tên bổ sung 7.363 mẫu** so với chỉ khớp `entity_id`
  (4.834 → 12.197, **+152%**; chỉ 3.731/12.602 cặp có object là entity) —
  đây là quyết định kỹ thuật có giá trị lớn nhất của phase.
- **Negative an toàn**: chỉ 12.562/86.934 cặp đồng câu đủ điều kiện làm
  negative (cả 2 đầu có QID + không có quan hệ) → **0 false negative** trên
  29.957 mẫu.
- **Gate G5 đạt**: chạy lại toàn bộ SPARQL = **0 request HTTP** (97,8 s,
  428 file cache) → pipeline tái lập hoàn toàn.
- **Contract chuẩn hoá theo đặc tả**: `re_train.jsonl` = **12.877 câu /
  29.957 cặp** (1 record/câu, `pairs` lồng) → lệnh kiểm thử chính thức
  `docs/09` chạy được; **59.914/59.914** offset khớp `text[start:end]` →
  sẵn sàng cho mô hình RE token-level ở Phase 8.

## 9. Việc tiếp theo

- **Phase 7 phần 2 (D1.2)** — huấn luyện RE PhoBERT trên
  `data/interim/re_train.jsonl`: token-level, marker style `typed_markers`,
  seed 42; đánh giá P/R/F1 theo quan hệ trên `dev`/`test`.
- **Audit chất lượng nhãn** — lấy ngẫu nhiên 100 mẫu POSITIVE, đối chiếu
  bằng chứng bằng tay, đo tỉ lệ nhãn sai (như Phase 3/4/6 đã làm). Đặc biệt
  kiểm tra 2 nhóm rủi ro: quan hệ `vo_cua`/`chong_cua` (hướng phụ thuộc giới
  tính, mà corpus chỉ có 23 entity có `gender`) và `P40` (chiều inverse).
- **Mở rộng corpus** — 6 quan hệ chưa có POSITIVE (`danh_bai`, `dong_doi_tai`
  có 44 mẫu, `lap_ra` có 13 mẫu) cần nguồn nhãn khác (Wikidata P166, LLM).

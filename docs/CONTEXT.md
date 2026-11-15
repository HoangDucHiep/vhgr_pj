# CONTEXT.md — Context sống của dự án

> File này là **nguồn sự thật** cho các quyết định đã chốt. Agent đọc file này thay vì đoán.
> Cập nhật file này **mỗi khi** có quyết định mới hoặc thay đổi kỹ thuật.

## 1. Trạng thái hiện tại

| Hạng mục | Trạng thái |
|---|---|
| Giai đoạn | **Đang triển khai** — Phase 1–12 xong (16/11/2026) |
| Phase hiện tại | **Phase 8 — Mô hình RE, LLM bulk, hợp nhất triple (D1/D2/D3)** — 🟢 **đã đóng** (19/19 Gate, 12/12 mục objective đối chiếu PASS) |
| Phase đã xong | 0 Bootstrap · 1 Lọc bài · 2 Làm sạch+tách câu · 3 Infobox · 4 Nhãn bạc NER · 5 Huấn luyện+suy luận NER · **6 Coreference (C1/C2)** · **7 Wikidata DS + tập train RE (D1.1)** · **8 Mô hình RE + LLM + hợp nhất triple (D1/D2/D3)** · 9 Entity linking · 10 Đồ thị + Neo4j · 11 Text-to-Cypher backend · 12 Giao diện web |
| Tài liệu | `docs/00` … `docs/09` đã hoàn thành · `docs/10-nhat-ky/` nhật ký triển khai chi tiết theo phase |
| Môi trường | Python 3.12.3, Docker 29.9.2, Node 24.15, RAM 23GB, đĩa 2.5TB, **không GPU local** |
| Hạ tầng | `.venv` đã tạo + cài `requirements.txt` ✅ · Neo4j 5.26.32 Community ở `:7474`/`:7687` ✅ · user `reader` đã tạo ✅ |
| Backend | FastAPI chạy ở `:8000` — `/api/health` → `{"status":"ok","neo4j":"up"}` ✅ |
| Frontend | Vite + React 18 + TS — `npm run build` 0 lỗi ✅ |
| Kaggle | `KAGGLE_USERNAME=hoangduchiep` + `KAGGLE_KEY` trong `.env` ✅ (auth bằng `Authorization: Bearer`) — ⚠️ CLI ≥ 2.2: `~/.kaggle/access_token` **đè** env ⇒ phải `env -u KAGGLE_USERNAME -u KAGGLE_KEY KAGGLE_API_TOKEN=<tok>` (D-089) |
| API key | `GEMINI_API_KEY`, `GROQ_API_KEY` trong `.env` ✅ |
| Test | `pytest -q tests/` → **625 passed** (480 Phase 7 + 76 Phase 8 + 7 entity linker + 8 kaggle LLM notebook + 1 `alt_evidence` regression) |
| Số liệu hiện tại | 2.441 bài · 186.960 câu · 10.078 triple infobox · 143.108 entity NER · **197.610 mention coref** (resolve 69,62%) · **15.580 mẫu POSITIVE RE** / 17 quan hệ · **25.947** ví dụ train RE (19 đầu) · **13.379** triple hợp nhất (13 trường) · KG **19.548 node / 13.379 edge** |

## 2. Quyết định đã chốt (KHÔNG đổi nếu không có lý do ghi vào DECISIONS.md)

### 2.1. Kiến trúc

| Quyết định | Giá trị | Lý do |
|---|---|---|
| Backend | FastAPI + Neo4j Community qua Docker Compose | nhẹ, phổ biến, hỗ trợ Cypher đúng mục tiêu đề tài |
| Frontend | React 18 + TypeScript + Vite + Cytoscape.js | Cytoscape.js xử lý tốt đồ thị vài trăm node |
| Tách tầng | Offline (Kaggle) / Online (máy local) | máy i3 không có GPU, không cần mô hình lớn lúc demo |
| Hợp đồng dữ liệu | Artifact JSONL giữa 2 tầng | mỗi phase nạp lại được, không phụ thuộc thứ tự |
| Ngôn ngữ lập trình | Python 3.12 (pipeline + backend), TypeScript (frontend) | |
| Cấu hình | `configs/*.yaml` | không hard-code |

### 2.2. Mô hình & LLM

| Hạng mục | Quyết định | Ghi chú |
|---|---|---|
| NER | `vinai/phobert-base` token classification, BIOES | 13 lớp = 6 nhãn × BIOES + O |
| RE | `vinai/phobert-base` + entity marker, 19 lớp (18 quan hệ + NA) | **đa nhãn sigmoid**, không phải softmax — D-061 |
| Embedding | `BAAI/bge-m3`, dim 1024, float16 | sinh trên Kaggle, máy local chỉ load |
| LLM bulk | model mở lượng tử hóa trên Kaggle GPU (`Qwen/Qwen3-8B` 4-bit) | **không tốn quota** |
| LLM API chính | Gemini `gemini-3.5-flash-lite` | 15 RPM / 500 RPD |
| LLM API dự phòng | Groq `openai/gpt-oss-20b` | 30 RPM / 1000 RPD |
| Adapter | interface chung `LLMClient.complete(...)`, fallback tự động, cache SQLite | |

**Model KHÔNG dùng được (đã deprecated/retire):**
- `gemini-2.0-flash` — mất toàn bộ quota free (RPM/TPM/RPD = 0)
- `gemini-2.5-flash`, `gemini-2.5-flash-lite` — deprecated, key mới trả 404
- Groq `llama-3.1-8b-instant`, `llama-3.3-70b-versatile` — retire 16/08/2026

**Quy tắc phân bổ quota:** quota API free ≈ 3.500 req/ngày, corpus có 150k–400k câu →
API **chỉ** dùng cho: (1) baseline LLM trên tập con ~1.500 câu, (2) Text-to-Cypher lúc demo, (3) LLM-judge faithfulness.
Trích xuất LLM trên toàn corpus → **Kaggle GPU**.

### 2.3. Dữ liệu

| Quyết định | Giá trị |
|---|---|
| Nguồn chính | dump Wikimedia chính thức (`dumps.wikimedia.org/viwiki/latest/`) — KHÔNG dùng bản HF `wikimedia/wikipedia` vì thiếu metadata cần thiết |
| File dump cần | `pages-articles.xml.bz2` + `pages-meta-current.xml.bz2` + `redirects.xml.bz2` |
| Phạm vi | 9 triều đại đã chốt, 2.000–5.000 bài |
| Chia tập | theo **bài** (80/10/10), seed 42, lưu `data/splits/splits.json` |
| Nhãn bạc | hyperlink nội bộ → QID → `P31` → nhãn |
| Nguồn nhãn RE | **3 nguồn**: Wikidata distant supervision (cache JSONL, chunk theo triều đại) + Infobox Phase 3 + Lead Phase 3 |

**Relation Extraction — distant supervision (Phase 7) — các quyết định đã chốt:**

| Quyết định | Giá trị | Mã |
|---|---|---|
| Mapping property ↔ quan hệ | `configs/wikidata_relations.yaml` — 13 property lõi + 6 property mở rộng (mở rộng **không** bật mặc định) | — |
| Hướng mapping | `forward` (P22/P25/P26/P19/P20/P39/P710) · `inverse` (P40 → `cha_cua`) · `symmetric` (P3373) · `year` (P569/P570 → `sinh_nam`/`mat_nam`) | D-059 |
| Nguồn nhãn POSITIVE | hợp nhất **3 nguồn**, dedupe theo `(sentence_id, subject, relation, object)`, ưu tiên `wikidata > infobox > lead` | D-056 |
| Grounding | khớp `entity_id` **và** fallback theo tên (nhãn tiếng Việt của Wikidata) → 4.834 → 12.197 mẫu (+152%) | D-056 |
| Negative "an toàn" | chỉ cặp **có cả hai QID** và **không** mang quan hệ nào (đối xứng kiểm cả 2 chiều) | D-057 |
| Tỉ lệ NEG/POS | cân bằng theo **hạn ngạch mỗi quan hệ** (tỉ lệ theo số POSITIVE của quan hệ đó) | D-057 |
| SPARQL client | tái dùng `run_query()` của `src/preprocess/wikidata_query.py` (QLever → WDQS, cache đĩa dùng chung) | D-058 |
| Dạng query | **từng property một** (`UNION` làm mất tên predicate trên cả QLever lẫn WDQS), lô 200 QID | D-058 |
| Contract output RE | **1 record/câu** (`run_id`/`text` + mảng `pairs` lồng), nhãn **chuỗi** `POSITIVE`/`NEGATIVE`, mỗi cặp có offset `start`/`end` thỏa `text[start:end] == mention` | D-060 |
| Artifact | `data/interim/re_train.jsonl` — **12.877 câu / 29.957 cặp** (POS 15.580 / NEG 14.377), split theo `page_id`; contract: 1 record/câu, `pairs` lồng, nhãn chuỗi `POSITIVE`/`NEGATIVE`, có `run_id` | D-060 |
| Số quan hệ còn thiếu POSITIVE | `danh_bai` (0) — cần nguồn nhãn khác (Wikidata P166, LLM) | — |

**Mô hình RE (Phase 8) — các quyết định đã chốt:**

| Quyết định | Giá trị | Mã |
|---|---|---|
| Hình thức đầu ra | **đa nhãn sigmoid**: 18 đầu quan hệ (1 sigmoid/quan hệ) + 1 đầu `NA` | D-061 |
| Lỗi huấn luyện | **masked BCE** — slot chưa biết = `-100.0` (bị bỏ qua, **không** phải 0.0) | D-061 |
| Đầu `NA` | luôn có supervision: `1.0` nếu input không có quan hệ POSITIVE nào, ngược lại `0.0` | D-061 |
| Marker | có **kiểu + vai trò**: `«PERSON:SUBJ:Lê Lợi»` / `«PERSON:OBJ:Nguyễn Phúc Chu»` | D-062 |
| Chuỗi mô hình | `<s> subj </s> câu có «…» và «…» </s> obj </s>` — nhãn ở `[CLS]` | D-062 |
| Tên hiển thị | `infobox_entities` → mode mention không phải đại từ → mention thô | D-062 |
| Bảng type entity | NER vote đa số (93,5%) → `infobox_entities` → tiền tố `year_` → `unknown` | D-063 |
| Cặp ứng viên (suy luận) | 2 mention cùng câu, **≤ 60 token** khoảng cách (đo bằng token khoảng trắng), `canonical_id` khác nhau | — |
| Số cặp ứng viên | **113.917** cặp (99.348 cặp `canonical_id` khác nhau — dùng để suy luận) | — |
| Hợp nhất triple | dedupe `(subject, relation, object)` giữ **confidence cao nhất**, bằng chứng còn lại → `alt_evidence` | — |
| Quan hệ đối xứng | `anh_em_cua`, `tham_gia_tran` → chuẩn hoá `subject_id < object_id` | — |
| Số nguồn gộp | **5**: `infobox` · `rule` (lead) · `distant_supervision` · `phobert_re` · `llm` | — |
| LLM bulk | Kaggle GPU, `Qwen/Qwen3-8B` 4-bit, chunk **15 câu/request** | — |
| LLM API baseline | Gemini `gemini-3.5-flash-lite` → fallback Groq `openai/gpt-oss-20b`, tập con **1.500 câu** (tập `test`) | — |
| Ràng buộc evidence | `evidence` phải là **substring** nguyên văn của câu → nếu không, **loại** và **đếm** số lượt loại | — |
| Cache LLM | SQLite `data/interim/llm_cache.sqlite`, key = sha256(model + prompt + params) → **idempotent** (chạy lại = **0 request**) — nhưng **không bền**: DB bị thay thế giữa các lần chạy ⇒ tốn request thật; tái lập tuyệt đối cần lưu kèm `n_requests`/`elapsed_s` | D-094 |
| Trường output triple | **13 trường** (`docs/09` §Phase 8) — gồm `alt_evidence` (bằng chứng thay thế sau dedupe). Bỏ trường này ⇒ mất dữ liệu **âm thầm** | D-093 |
| Chất lượng RE | metric theo đặc tả (bỏ qua slot mask) **che mất** lỗi over-firing ⇒ thêm `scripts/eval_re_strict.py` (P 0,0854 · R 0,9652 · F1 0,1569) và chuyển ràng buộc sang **bộ lọc hậu xử lý 4 lớp** | D-080 → D-086 |
| QA năm sinh/mất | dùng `OPTIONAL MATCH` + `coalesce(thuộc_tính, quan_hệ)` — thuộc tính `birth_year` chỉ có ở **721/11.021** node, quan hệ `sinh_nam`/`mat_nam` phủ **1.126/1.059** cạnh | D-087, D-088 |
| Payload LLM mở | chuẩn hoá **mọi** hình dạng (array top-level, dict thay thế, object đơn) → `{"triples": [...]}`; "parse không lỗi" ≠ "parse đúng schema" | D-091 |
| Ngân sách thời gian kernel | `LLM_TIME_BUDGET_S` + `flush()`/`os.fsync()` từng request ⇒ hết quota không mất output | D-090 |

**Coreference (Phase 6) — các quyết định đã chốt:**

| Quyết định | Giá trị | Mã |
|---|---|---|
| Nguồn `canonical_id` | gazetteer hợp nhất: `infobox_entities.jsonl` (1.764 entity, nguồn A) ∪ tiêu đề bài `documents.jsonl` (1.687 bài, nguồn B) | D-045 |
| Mint `entity_id` | sớm ở Phase 6, dùng **đúng** `make_entity_id(type_ner, name)` mà Phase 9 dùng → id giống hệt | D-044 |
| Chủ thể bài | file riêng `data/interim/article_subjects.jsonl` (1 record/doc, 2.441 bài) | D-045 |
| Thứ tự ưu tiên quy tắc R | **cấu hình** qua `coref.pronoun_rule_order` = `[r3, r1a, r1b, r5, r6]` (đo trên gold 100 câu) | D-052 |
| Điều kiện R3 | dùng như **tiên đề** (không giới hạn "đoạn không có `PERSON`") — biến thể bám sát đặc tả chỉ đạt G5 0,6864 | D-047 |
| Điều kiện R3 (loại) | chỉ dùng khi `subject.type == "person"` | D-049 |
| Điều kiện R3 (giới tính) | entity đích phải khớp giới tính đại từ, nếu không → `null` + `ambiguous` | D-051 |
| Điều kiện R6 (giới tính) | tương tự R3 | D-051 |
| Đại từ số nhiều | "các ông", "các vua Trần" → `null` + `ambiguous` (5.201 mention) | D-048 |
| Chốt an toàn R5-pre | đại từ số nhiều luôn được chặn **trước** mọi quy tắc cạnh tranh, bất kể thứ tự cấu hình | D-052 |
| Tín hiệu chủ thể bài | `infobox_type` → `wikidata_signal` → `qid_types` → `p31_direct` (**cuối**) | D-050 |
| Cờ dự phòng | `coref.r1b_unique_only` (mặc định `false`) · `coref.r3_requires_no_person` (mặc định `false`) | D-053, D-047 |

### 2.4. Đánh giá

| Quyết định | Giá trị |
|---|---|
| Nguồn gold chính | **auto-gold từ Wikidata** (độc lập với mô hình, không vòng tròn) |
| Gán tay | **tối thiểu 100 câu NER** (1–2 người), dùng để đối chiếu người–máy |
| Nếu có 2 người gán | agreement rate trên ≥ 30 câu + Cohen's kappa (nếu đủ) |
| Bộ câu hỏi QA | sinh tự động từ facts Wikidata (200–400 câu, ≥ 5 dạng) + 40–60 câu viết tay |
| Đo faithfulness | LLM-judge trên 30 câu, tỉ lệ "không bịa" ≥ 0.90 |
| Báo cáo | số liệu thực tế + phân tích lỗi top 20; **không sửa số liệu** để đạt mục tiêu |
| Bộ gold coref | **100 câu dev** gán tay (`data/eval/coref_gold_100.jsonl`, 137 mention) — chỉ giữ mention `source ∈ {pronoun, pronoun_name}` để đo đúng AC C1 |
| Kiểm định khác biệt | khi so sánh 2 phương án trên bộ nhỏ: **McNemar exact** + **bootstrap theo câu** (CI 95%) — không kết luận từ chênh lệch điểm số đơn thuần |
| Ablation | phải chạy trên **đúng đường dẫn code thật** — cấu hình tham số để đo, **không monkeypatch** |

### 2.5. Schema KG

18 quan hệ cố định (tên chữ thường, không dấu gạch dưới):
```
cha_cua, me_cua, vo_cua, chong_cua, anh_em_cua,
thuoc_trieu_dai, ke_vi, giu_chuc_vu, lap_ra,
chi_huy_tran, tham_gia_tran, danh_bai, dien_ra_tai,
sinh_tai, mat_tai, sinh_nam, mat_nam, dong_doi_tai
```
Quan hệ đối xứng: `anh_em_cua`, `tham_gia_tran` → chuẩn hóa orientation (subject_id < object_id) trước khi nạp.

7 label node: `Person`, `Dynasty`, `Event`, `Place`, `Title`, `Year`, `Article`.

**Ràng buộc loại chủ thể** (`RELATION_SUBJECT_TYPES` trong `src/common/schemas.py`, căn theo
`docs/04` §3.1 — đã sửa ở Phase 3, xem `reports/deviations.md` D-019):

| Quan hệ | Loại chủ thể được phép |
|---|---|
| `cha_cua`, `me_cua`, `vo_cua`, `chong_cua`, `anh_em_cua` | `person` |
| `ke_vi`, `giu_chuc_vu`, `chi_huy_tran`, `tham_gia_tran`, `danh_bai` | `person` |
| `sinh_tai`, `mat_tai`, `sinh_nam`, `mat_nam` | `person` |
| `thuoc_trieu_dai` | `person`, `dynasty`, `event` |
| `lap_ra` | `person`, `event` |
| `dien_ra_tai` | `person`, `event` |
| `dong_doi_tai` | `dynasty` |

> **Quy tắc suy loại chủ thể** (Phase 3, D-024): tên loại infobox (`type_map`) → tín hiệu
> `wikidata_signal` (Phase 1) → loại trung tính `article`. **Không** mặc định `person`.

Chi tiết đầy đủ: `docs/04-schema-knowledge-graph.md`.

### 2.6. QID đã verify (10/11/2026)

**9 triều đại** (tất cả `P31 = Q164950`):

| Triều đại | QID |
|---|---|
| Nhà Ngô | `Q703919` |
| Nhà Đinh | `Q1372154` |
| Nhà Tiền Lê | `Q1317884` |
| nhà Lý | `Q878309` |
| nhà Trần | `Q3111454` ⚠️ không phải `Q62454` (đó là nhà Trần Trung Quốc) |
| Nhà Hồ | `Q1209047` |
| nhà Lê sơ | `Q878276` ⚠️ không phải `Q10800791` (nhà Lê trung hưng, ngoài phạm vi) |
| nhà Tây Sơn | `Q1034173` |
| nhà Nguyễn | `Q6500483` |

**Lớp thực thể:**
`Q164950` triều đại · `Q178561` trận đánh · `Q1656682` sự kiện · `Q486972` khu định cư · `Q5` người · `Q116` quân chủ · `Q706208` miếu hiệu · `Q696100` thụy hiệu · `Q256408` niên hiệu (`Q2420465` niên hiệu VN) · `Q4164871` chức vụ · `Q840178` tông tộc · `Q881` Việt Nam · `Q430309` Đại Việt · `Q10841085` Đại Cồ Việt · `Q11514315` thời kỳ lịch sử

**Cảnh báo:** `P17` chỉ có trên 3/9 triều đại (Lý, Hồ, Tây Sơn) → **không lọc bằng `?x wdt:P17 wd:Q881`**, sẽ mất 6 triều đại. Lọc bằng `P31 = Q164950` + `P463`/`P361` + heuristic nhãn.

### 2.7. Hạ tầng đã kiểm chứng (11/2026)

| Hạng mục | Kết quả kiểm chứng | Hệ quả cho thiết kế |
|---|---|---|
| Neo4j 5.26 Community | **Không có RBAC.** `CREATE USER … SET ROLE reader` và `GRANT … ON GRAPH` đều lỗi cú pháp; user `reader` vẫn ghi được | Lớp bảo vệ DB dựa vào **session `READ_ACCESS`** (server từ chối ghi, kể cả superuser) — xem D-008 |
| `mwparser` trên PyPI | Chỉ có bản `0.1` (bản `0.6.2` chưa publish) | Đọc dump bằng `lxml.etree.iterparse` (nhanh hơn, hỗ trợ streaming) |
| `viwiki` dump | **Không có** file `redirects.xml.bz2` riêng (chỉ enwiki có) | Redirect nằm trong `pages-articles.xml.bz2` dưới thẻ `<redirect>` |
| `neo4j` driver | `READ_ACCESS_MODE` không tồn tại → dùng `READ_ACCESS` | |
| `pysbd` | Cài được trên Python 3.12 | Dùng `pysbd` cho tách câu; `underthesea` **không** bắt buộc (D-005) |
| `wikitextparser` | Bản 3.0.0 cài được | Dùng cùng `lxml` cho parse wikitext |
| `transformers` | Bản 5.23.0 cài được | Dùng cho PhoBERT / BGE-M3 ở tầng offline |
| Máy local | 8 core · 23 GB RAM · 2.5 TB đĩa · Docker 29.9 · Node 24 · **không GPU** · **không có Kaggle credentials** | Các bước nặng (fine-tune NER/RE, embedding BGE-M3, LLM bulk) **phải** chạy trên Kaggle GPU rồi tải artifact về — máy local chỉ đọc artifact |
| Wikidata SPARQL | `query.wikidata.org` trả HTTP 200 với User-Agent định danh | Dùng làm nguồn auto-gold (độc lập với KG) |
| Phiên bản dump viwiki | `20251101` là bản mới nhất tại `dumps.wikimedia.org/viwiki/` | Khớp `dump_version` mặc định trong `configs/default.yaml` |
| `READ_ACCESS` chặn ghi | ✅ **Đã kiểm chứng 13/11/2026:** session `default_access_mode=READ_ACCESS` → đọc OK, `CREATE` bị từ chối bởi server với `Neo.ClientError.Statement.AccessMode` | Dùng làm cơ chế bảo vệ chính (D-002) |
| Ngày âm lịch | ⚠️ Không quy đổi âm → dương trong code (D-007) | Chỉ nhận diện `is_lunar`; quy đổi tuyệt đối cần thư viện chuyên dụng + múi giờ |
| Frontend build | ✅ Vite 5.4.21 + TS 5.6, `tsc --noEmit` 0 lỗi | Không dùng project reference (TS6310) — xem D-006 |
| Corpus Phase 1 | ✅ **2.441 bài** trong `data/interim/documents.jsonl` (dump `20261101`), QID 97,3%, RAM peak 1,16 GB, 31 phút | Chuẩn 2.441 bài cho mọi phase sau; xem `reports/phase_01_report.md` |
| Cây category viwiki | ⚠️ `categorylinks.cl_from` là `page_id` của trang category, `cl_target_id` là `lt_id` trong bảng `linktarget` | Phải khóa cây theo **title**, không theo `page_id`/`lt_id` — xem D-010 |
| Lọc T2/T5 | ⚠️ Infobox `battle`/`dynasty` chung + tín hiệu Wikidata `P31=Q178561`/`Q164950` không đủ để kết luận "lịch sử Việt Nam" | Bắt buộc thêm category trong phạm Việt Nam (chứa "Việt" **hoặc** nhóm "nhà vua") — xem D-008, D-012 |

## 3. Chỉ số mục tiêu

| Chỉ số | Mục tiêu | Thực tế |
|---|---|---|
| NER F1 (token-level) | ≥ 0.85 | 0,6832 (Phase 5) |
| RE F1 | ≥ 0.70 | — |
| Số mẫu POSITIVE RE (distant supervision) | ≥ 10.000 | **15.580** (Phase 7) |
| Tỉ lệ NEG/POS (RE) | ≤ 1,0 | **0,9228** (Phase 7) |
| Số quan hệ có POSITIVE | ≥ 8 | **17** / 18 (Phase 7) |
| Quan hệ ngoài danh mục 18 quan hệ | 0 | **0** (Phase 7) |
| Entity linking accuracy | ≥ 0.85 | — |
| Text-to-Cypher execution accuracy | ≥ 0.70 |
| Cypher p95 | < 2s |
| End-to-end p50 | < 10s |
| % cạnh có bằng chứng | 100% |

## 4. Câu hỏi đang mở

| # | Câu hỏi | Chặn ở đâu | Gợi ý xử lý |
|---|---|---|---|
| 1 | Key Gemini/Groq tạo được model nào còn quota? | Phase 8, 11, 13 | dùng `gemini-3.5-flash-lite`; nếu 404 → kiểm tra tên model qua AI Studio |
| 6 | Nhãn POSITIVE RE có đủ tin cậy để huấn luyện? | Phase 8 | audit 100 mẫu tay; rủi ro cao: `vo_cua`/`chong_cua` (hướng phụ thuộc giới tính — corpus chỉ 23 entity có `gender`) và `P40` (chiều inverse) |
| 7 | Quan hệ `danh_bai` (0 POSITIVE) và 5 quan hệ có <50 mẫu lấy nhãn ở đâu? | Phase 8 | Wikidata `P166`/`P1344` hoặc LLM bulk trên Kaggle |
| 2 | Kaggle có dataset mirror sẵn để tránh tải dump 2GB? | Phase 1 | tải dump ở local (đủ RAM 23GB) rồi upload artifact |
| 3 | Có tạo được `reader` user Neo4j trong container không? | Phase 10 | ✅ **Đã kiểm chứng 11/2026: KHÔNG.** Neo4j Community không có RBAC → `CREATE USER … SET ROLE reader` lỗi cú pháp. User `reader` tạo được nhưng vẫn ghi được. Cơ chế bảo vệ thật là **session `default_access_mode=READ_ACCESS`** (server từ chối ghi, kể cả superuser) — xem §2.7 và D-008 |
| 4 | Có kịp gán 100 câu tay? | Phase 13 | không kịp → chỉ auto-gold, nêu rõ trong báo cáo |
| 5 | Có dùng Label Studio hay gán trực tiếp file JSONL? | Phase 13 | Label Studio local (`pip install label-studio`) |

## 5. Rủi ro đã biết

| Rủi ro | Đã biết | Giảm thiểu |
|---|---|---|
| Quota LLM không đủ cho corpus | ✅ | bulk trên Kaggle GPU |
| `P17` lọc mất triều đại | ✅ | dùng `P31 = Q164950` |
| Nhãn bạc nhiễu (link sai nghĩa) | ⚠️ | lọc bằng QID + `P31`; báo cáo phân bố nguồn nhãn |
| Số bài lịch sử trong dump ít hơn 2.000 | ⚠️ | tăng BFS depth 3, nới whitelist category |
| NER F1 không đạt 0.85 | ⚠️ | thêm nhãn từ Wikidata `P31`, thử `phobert-large`, báo cáo minh bạch |
| `pysbd`/`underthesea` lỗi trên Python 3.12 | ⚠️ | fallback regex + `configs/name_exceptions.yaml` |
| `mwparser` không cài được (PyPI chỉ có bản `0.1`) | ✅ đã xác nhận | parse dump bằng `lxml.etree.iterparse` (streaming, nhanh hơn cho file 2GB+) |
| Dump viwiki không có `redirects.xml.bz2` riêng | ✅ đã xác nhận | redirect nằm trong `pages-articles.xml.bz2` dưới thẻ `<redirect>` |
| **Máy local không có GPU / không có Kaggle credentials** | ✅ đã xác nhận 11/2026 | fine-tune PhoBERT NER/RE và embedding BGE-M3 **phải** chạy trên Kaggle (có GPU) rồi tải artifact về; phần LLM bulk cân nhắc dùng API free tier trên tập con thay vì toàn corpus — cần người dùng chốt phạm vi |

## 6. Liên kết nhanh

| Cần biết | Đọc |
|---|---|
| Quyết định kiến trúc chi tiết | `docs/DECISIONS.md` |
| Nhật ký triển khai chi tiết (để làm báo cáo / slide) | `docs/10-nhat-ky/README.md` |
| Phase cần làm tiếp | `docs/PROGRESS.md` |
| Định nghĩa schema node/edge | `docs/04-schema-knowledge-graph.md` |
| Thuật ngữ | `docs/GLOSSARY.md` |

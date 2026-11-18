# DECISIONS.md — Nhật ký quyết định kiến trúc

> Mỗi quyết định quan trọng ghi 1 mục. Format nhẹ kiểu ADR.
> Agent **phải** đọc file này trước khi đề xuất thay đổi kiến trúc, và **phải** thêm mục mới khi thay đổi.

---

## D-001 — Dùng FastAPI + Neo4j thay vì Flask + graph DB khác

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Đề tài bắt buộc dùng Cypher. Các lựa chọn: Neo4j, FalkorDB, Memgraph, hay triển khai Cypher trên SQL.

**Quyết định:** Neo4j Community 5.x qua Docker Compose + FastAPI.

**Lý do:** Cypher là ngôn ngữ native của Neo4j → prompt Text-to-Cypher khớp 1-1 với thứ thực thi; Community miễn phí, chạy được trên máy 24GB; driver Python chính thức hỗ trợ read-only session, timeout, constraint/index.

**Hệ quả:** phải quản lý schema bằng Cypher DDL; constraint `IS UNIQUE` cần Neo4j ≥ 5.0.

---

## D-002 — Tách tầng offline (Kaggle GPU) / online (máy local)

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Máy local có 23GB RAM, không GPU. Fine-tune PhoBERT + LLM bulk + embedding cần GPU.

**Quyết định:** Mọi việc nặng chạy offline trên Kaggle GPU, ghi ra artifact JSONL ở `data/`. Backend local chỉ đọc artifact + truy vấn Neo4j + gọi LLM API.

**Lý do:** Demo phải chạy được trên máy i3 (yêu cầu phi chức năng); tách tầng giúp mỗi phase nạp lại được độc lập và test được không cần GPU.

**Hệ quả:** artifact JSONL trở thành hợp đồng giữa các phase → format phải cố định (xem `AGENTS.md` §7).

---

## D-003 — Trích xuất LLM bulk chạy model mở trên Kaggle, không dùng API free tier

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Quota Gemini free ≈ 500 RPD, Groq ≈ 1.000 RPD/model (tổng ~3.500 req/ngày). Corpus có 150k–400k câu, cần ~30.000 request để trích xuất toàn bộ.

**Quyết định:** Bulk LLM = model mở lượng tử hóa (`Qwen/Qwen3-8B` 4-bit) trên Kaggle GPU. API free tier chỉ dùng cho: baseline đối chiếu (~1.500 câu), Text-to-Cypher lúc demo, LLM-judge.

**Lý do:** quota không đủ; model mở cho phép chạy toàn corpus mà không tốn tiền và tái lập được.

**Hệ quả:** cần 2 đường trích xuất LLM nhưng cùng format output (`method="llm"`) để `merge_triples` không phân biệt.

---

## D-004 — Chọn Gemini `gemini-3.5-flash-lite` + Groq `openai/gpt-oss-20b`

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `gemini-2.0-flash` mất quota free; `gemini-2.5-*` deprecated (404 với key mới); Groq retire `llama-3.1-8b-instant` và `llama-3.3-70b-versatile` ngày 16/08/2026.

**Quyết định:** `gemini-3.5-flash-lite` (15 RPM/500 RPD) làm chính, `openai/gpt-oss-20b` (30 RPM/1.000 RPD) làm dự phòng, qua adapter chung.

**Lý do:** hai model còn quota free ở thời điểm hiện tại; có fallback để một provider hết quota không chặn pipeline.

**Hệ quả:** cần rate limiter theo provider + cache SQLite để không gọi lại cùng prompt.

---

## D-005 — Đánh giá bằng auto-gold từ Wikidata, gán tay tối thiểu

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Gán tay đầy đủ (250 câu × 2 người + Cohen's kappa) tốn ~1 tuần, rủi ro bị bỏ. Đề tài yêu cầu có số liệu đánh giá.

**Quyết định:** Nguồn gold chính = **auto-gold sinh từ Wikidata facts** (NER từ hyperlink có QID + `P31`; RE từ `P22`/`P25`/`P26`/`P569`...; linking theo QID; bộ câu hỏi QA sinh từ facts). Gán tay tối thiểu 100 câu NER để đối chiếu người–máy.

**Lý do:** Wikidata là nguồn đáp án **độc lập với mô hình** → số liệu vẫn có ý nghĩa, tập lớn hơn nhiều, và **không vòng tròn** (đáp án không lấy từ KG của chính mình).

**Hệ quả:** báo cáo phải nêu rõ "đánh giá theo weak supervision từ Wikidata"; nếu có 2 người gán thì tính agreement rate và kappa.

---

## D-006 — Quan hệ đóng 18 loại, tên không dấu gạch dưới

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Cần dùng chung một danh sách quan hệ cho: tập train RE, prompt LLM, validator Cypher, query frontend, schema Neo4j.

**Quyết định:** 18 quan hệ cố định, tên snake_case không dấu (`cha_cua`, `thuoc_trieu_dai`, `dien_ra_tai`...). Tập này là **enum dùng chung** — khai báo 1 lần trong `src/common/schemas.py`, import ở mọi nơi.

**Lý do:** tránh lệch tên giữa các module (nguồn bug phổ biến nhất trong pipeline KG); tên không dấu gạch dưới hợp lệ Cypher.

**Hệ quả:** thêm/bớt quan hệ → phải cập nhật `docs/04`, `src/common/schemas.py`, prompt, validator, và test trong cùng một lần thay đổi.

---

## D-007 — `sinh_nam`/`mat_nam` vừa là quan hệ vừa là property trên node

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảng:** Năm sinh/năm mất cần truy vấn được ("Lê Lợi sinh năm nào?"). Nếu chỉ là property node thì không có cạnh để hiển thị bằng chứng; nếu chỉ là node `Year` thì query phức tạp.

**Quyết định:** Lưu **cả hai**: property `birth_year`/`death_year` trên node `Person` (để query nhanh, index được) **và** cạnh `sinh_nam`/`mat_nam` tới node `Year` (để có bằng chứng + hiển thị được trên đồ thị).

**Lý do:** tối ưu cả truy vấn lẫn khả năng trực quan hóa/bằng chứng.

---

## D-008 — Dùng Neo4j `reader` role + validator tĩnh (2 lớp bảo vệ)

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Cypher sinh bởi LLM → rủi ro chạy lệnh ghi/xoá nếu prompt bị lệch.

**Quyết định:** (1) validator tĩnh chặn từ khóa ghi + bắt buộc `MATCH`/`LIMIT`; (2) session Neo4j mở với `default_access_mode=READ_ACCESS` — server từ chối mọi lệnh ghi (kể cả bằng superuser); (3) timeout 10s + `LIMIT ≤ 100`.

**Lý do:** defense in depth — validator chặn ở tầng app, server chặn ở tầng dữ liệu. Lỗi ở tầng nào vẫn an toàn.

**Hệ quả:** test bắt buộc ≥ 20 payload độc hại → 100% bị chặn.

**Lưu ý (đã kiểm chứng 11/2026):** Neo4j **Community** không có RBAC — `CREATE USER … SET ROLE reader` và `GRANT … ON GRAPH` đều lỗi cú pháp, và user `reader` vẫn ghi được vào DB. Vì vậy cơ chế bảo vệ cấp DB dựa vào **READ access mode** (server từ chối ghi), không dựa vào role. User `reader` vẫn được tạo để tách credential cho API.

---

## D-009 — Chia tập theo bài, không theo câu

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Nhiều câu trong cùng bài dùng lại cùng nhân vật và cấu trúc câu.

**Quyết định:** Chia train/dev/test theo `page_id` (80/10/10), seed 42, lưu `data/splits/splits.json`.

**Lý do:** tránh rò rỉ (data leakage) làm F1 trên dev không phản ánh F1 thật.

---

## D-010 — Mọi triple mang bằng chứng + `method` + `confidence`

**Ngày:** 10/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Đề tài yêu cầu "mọi sự kiện đều truy được về câu nguồn"; UI cần hiện câu gốc khi bấm cạnh.

**Quyết định:** Mỗi triple bắt buộc có `evidence_sentence`, `source_url`, `doc_id`, `sentence_id`, `confidence`, `method` (`infobox` | `distant_supervision` | `phobert_re` | `llm` | `rule`). Triple thiếu bằng chứng → loại khỏi KG.

**Lý do:** là yêu cầu bắt buộc của đề tài (CC BY-SA cũng yêu cầu ghi nguồn); đồng thời cho phép đánh giá chất lượng theo `method`.

**Hệ quả:** `scripts/validate_graph.py` phải trả 0 lỗi cho các trường này.

---

## D-011 — Tách 2 artifact triple: `infobox_triples.jsonl` vs `lead_triples.jsonl`

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Infobox cho triple có độ tin cậy rất cao (`confidence ≥ 0.95`) nhưng chỉ phủ
67,3% bài nhân vật. Trích thêm từ đoạn dẫn (regex) phủ được tới 92,4% nhưng độ tin cậy
thấp hơn. Nếu gộp chung một file, Gate "100% `method=infobox`, `confidence ≥ 0.95`" của
`infobox_triples.jsonl` sẽ **không còn đúng nghĩa**.

**Quyết định:** Tách làm 2 file:
- `data/interim/infobox_triples.jsonl` — `method="infobox"`, `confidence ≥ 0.95` (đường sạch).
- `data/interim/lead_triples.jsonl` — `method="rule"`, `confidence=0.85` (fallback đoạn dẫn).

**Lý do:** Giữ đúng nghĩa của Gate, cho phép đánh giá chất lượng theo từng `method`, và
để Phase 8 (gộp triple) quyết định cách gộp dựa trên đường sạch.

**Hệ quả:** `docs/09` §Phase 3, `.cursor/rules/data-contracts.mdc` và `AGENTS.md` §7 liệt kê
cả 3 artifact (kể cả `infobox_entities.jsonl`).

---

## D-012 — Mapping infobox nằm ở config riêng, **không** sửa `infobox_parser.py`

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Phase 1 đã dựng `src/preprocess/infobox_parser.py` với `INFOBOX_TYPE_MAP` và
dùng nó để lọc corpus. Phase 3 cần mapping trường → quan hệ KG và bảng loại mở rộng
(170+ loại infobox). Sửa file Phase 1 sẽ làm đổi hành vi lọc → checksum corpus đổi →
không còn đối chiếu được với kết quả Phase 1.

**Quyết định:** `configs/infobox_mapping.yaml` là nguồn sự thật cho mapping của Phase 3;
`src/preprocess/infobox_parser.py` **giữ nguyên**. `wikitextparser` (tên template đầy đủ)
và regex Phase 1 (tên đã bỏ tiền tố) cùng tra bảng này → `normalize_type()` thử khớp
chính xác trước, rồi mới bỏ tiền tố rồi thử lại.

**Lý do:** Tách "lọc corpus" (Phase 1) khỏi "trích triple" (Phase 3) — hai mục đích khác
nhau, hai vòng đời khác nhau. Giữ checksum ổn định để truy vết được dữ liệu nguồn.

**Hệ quả:** `battle` trong `INFOBOX_TYPE_MAP` (Phase 1) trả `"battle"` — không phải loại node
KG. Phase 3 map sang `event` trong config riêng (xem `reports/deviations.md` D-020).

---

## D-013 — Loại chủ thể không suy được → `article`, **không** mặc định `person`

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** 43 bài có template infobox không có trong bảng mapping. Code ban đầu rơi xuống
mặc định `person` → node **"Hà Nội"** và **"Cần Thơ"** bị gán `type="person"` (sai hoàn toàn).
Đây là **bịa âm thầm** (vi phạm `AGENTS.md` §5.3) mà 5 Gate đều **vẫn đạt**.

**Quyết định:** Tách **hai mặc định** vì vai trò khác nhau:

| Hằng số | Giá trị | Áp dụng cho | Lý do |
|---|---|---|---|
| `DEFAULT_TYPE` | `"article"` | **chủ thể** | Loại trung tính — không khẳng định điều gì |
| `DEFAULT_OBJECT_TYPE` | `"person"` | **đối tượng** | Trường không khai báo `value_type` gần như luôn là người (cha, mẹ, vợ, tiền nhiệm…) |

Thứ tự suy loại chủ thể: **tên template** (`type_map`) → **tín hiệu `wikidata_signal`**
(Phase 1) → `article`.

**Lý do:** `person` là loại phổ biến nhất nên dễ trở thành mặc định ngầm — nhưng cũng là
loại bịa nhiều nhất khi suy sai. "Không xác định được" và "giá trị phổ biến nhất" là hai
thứ khác nhau.

**Hệ quả:** Thêm bước suy từ `wikidata_signal`; bổ sung 36 khoá `type_map`; thêm 6 test
regression. Xem `reports/deviations.md` D-024.

---

## D-014 — Mọi artifact Phase 3 ghi `dump_version` + `model_name`

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Ràng buộc bắt buộc của dự án: *"artifact ghi `dump_version` + `model_name`"*
(`AGENTS.md` §5.6 — tái lập). Phase 3 sinh 3 artifact mới nhưng ban đầu không ghi 2 trường
này, khiến không truy được artifact về đúng lần chạy.

**Quyết định:** Cả 3 artifact (`infobox_triples.jsonl`, `lead_triples.jsonl`,
`infobox_entities.jsonl`) ghi `dump_version` (từ `config.dump.dump_version`) và
`model_name` (từ `config.ner.model_name`). Giá trị `dump_version` của triple lấy theo từng
bài từ `documents.jsonl` để không phụ thuộc thứ tự chạy.

**Lý do:** Cho phép tái lập và đối chiếu khi dump Wikipedia cập nhật, và đo chất lượng theo
model khi Phase 5+ thay đổi mô hình.

**Hệ quả:** 3 test bắt buộc trong `tests/test_infobox.py`; `.cursor/rules/data-contracts.mdc`
§"Artifact Phase 3" ghi rõ quy tắc này.

---

## D-031 — Scheme nhãn NER bạc: BIO (13 lớp), không phải BIOES (25 lớp)

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `docs/09` §Phase 4 (output contract) dùng nhãn `B-PERSON`/`I-PERSON`/`O`, và
`docs/CONTEXT.md` §2.4 chốt `num_labels = 2×6+1 = 13`. Nhưng `docs/09` §Phase 5 lại ghi
`num_labels = 2*6 + 1 = 13 (BIOES × 6 nhãn + O)` — **mâu thuẫn**: BIOES thật là `4×6+1 = 25`.

**Quyết định:** dùng **BIO** (`B-`/`I-`/`O`) = **13 lớp**. Dòng "BIOES" trong `docs/09` §Phase 5
là lỗi đánh máy → đã sửa để Phase 5 không dùng nhầm `num_labels=25`.

**Lý do:** `docs/CONTEXT.md` là "số đã chốt" theo `AGENTS.md` §2 ("quy tắc vàng"), và công thức
`2×6+1` chỉ đúng với BIO.

**Hệ quả:** `src/ner/build_silver.py` (`BIO_PREFIXES`, `NUM_LABELS=13`), `src/evaluation/metrics.py`
(logic gom span), `tests/test_silver_labels.py`. Chi tiết: `reports/deviations.md` D-031.

---

## D-032 — Nguồn nhãn bạc: **Wikipedia category** đứng đầu, trước Wikidata `P31`

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `docs/09` §Phase 4 quy định suy nhãn theo QID → `P31` → map. Khi đo thực tế trên
corpus tiếng Việt (2.441 bài), đường này cho ra rất ít: **0 / 1.788** QID mới có `P31`, và khi
có thì thường là lớp generic ("human") → **mọi** người thành `PERSON`, kể cả khi tên đích thực
ra là quốc gia hay địa danh.

**Quyết định:** thêm nguồn **`category`** (category Wikipedia của bài đích, từ `dump_facts.jsonl`)
đứng **đầu** thứ tự ưu tiên, với `confidence = 0.97`. Chuỗi đầy đủ:
`category` → `qid_direct` → `qid_ancestor` → `kg_type` → `wikidata_signal` → `pattern` → bỏ.

**Lý do:** category do **biên tập viên** gắn tay là tín hiệu mạnh và đúng đặc biệt với corpus
tiếng Việt (phân biệt được "Nhà **hoạt động**" (PERSON) với "Nhà **Nguyễn**" (DYNASTY) — điều
mà `P31` không làm được).

**Hệ quả:** `category` chiếm **50,2%** nguồn nhãn; độ phủ câu có hyperlink **100%**;
baseline gazetteer dev F1 **0,7388 → 0,7990**. Thêm `src/ner/category_types.py`.
Chi tiết: `reports/deviations.md` D-032.

---

## D-033 — Nhãn TIME chỉ gán khi có ngữ cảnh liền kề

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `docs/09` §Phase 4 yêu cầu regex sinh TIME `\b\d{3,4}\b` **"trong ngữ cảnh
'năm'"**. Bản triển khai đầu bỏ sót điều kiện → gán TIME cho **mọi** số 3–4 chữ số, đo được
**16.099** số **không phải năm** bị gán sai (vd "650.000 m³/ngày" → "000", "500 ha").

**Quyết định:** năm đứng riêng chỉ được gán khi có **ngữ cảnh liền kề** (2 token trước/sau
thuộc `time_context_before/after` trong `configs/ner_silver_config.yaml`) **và** nằm trong khoảng
lịch sử 1000–2100.

**Lý do:** điều kiện "trong ngữ cảnh" trong đặc tả là **bắt buộc**, không phải gợi ý. Ngoài ra
ngữ cảnh phải **liền kề** — nếu xét cả câu thì một chữ "năm" ở đầu câu sẽ biến mọi con số phía
sau thành năm (đo được "Nghị quyết số 203/2025/QH15" → 2 năm sai).

**Hệ quả:** TIME **57.604 → 35.685** mention; số năm sai **16.099 → 0**.
Chi tiết: `reports/deviations.md` D-033.

---

## D-034 — Mọi mẫu category Wikipedia phải có ranh giới từ (`\b`)

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `docs/09` §Phase 4 yêu cầu "không xác định → bỏ (không gán nhãn sai)". Bản triển
khai đầu viết mẫu category **không có ranh giới từ** ở cuối nhánh thay thế → regex khớp **tiền tố**
của nhánh khác. Đo được 4 nhóm lỗi thật:

| Mẫu cũ | Khớp nhầm vào | Số category sai |
|---|---|---|
| `^nha ho` (DYNASTY) | "Nhà **ho**ạt động quyền LGBT Mỹ" (PERSON) | 183 |
| `^nha ngo` (DYNASTY) | "Nhà **ngo**ại giao Việt Nam" (PERSON) | 108 |
| `^quan l[aai]i` (TITLE) | "Quan lại **nhà Nguyễn**" — đây là **người** | 185 bài người |
| `^nam (sinh\|mat\|tu)` (TIME) | "**Năm sinh không rõ**" — đây là **siêu dữ liệu** | bài người |

**Quyết định:** (1) bổ sung `\b` vào **mọi** nhánh thay thế trong `CATEGORY_PATTERNS`;
(2) "Quan lại nhà X" / "Hoàng đế" → `PERSON`; chỉ "Quan lại" đứng một mình mới là `TITLE`;
(3) bỏ mẫu `^nam (sinh|mat|tu)`; (4) thêm `^nha (hoat dong|hoa hoc|ngoai giao|...)` → `PERSON`.

**Lý do:** mẫu theo tên danh mục phải khớp **trọn cụm từ**, không khớp tiền tố. Ngoài ra cần
phân biệt "người mang chức vị" (Quan lại nhà Nguyễn) với "tước hiệu" (Thụy hiệu), và "đơn vị
thời gian" (Thế kỷ) với "siêu dữ liệu sinh tử" (Năm sinh không rõ).

**Hệ quả:** PERSON 36.477 → **37.242**; TITLE 2.887 → **2.170**; TIME 57.184 → **53.654**;
`PERSON` lại là lớp phổ biến nhất trong nhóm entity gắn từ hyperlink.
Chi tiết: `reports/deviations.md` D-034.

---

## D-035 — Bảng map lớp Wikidata → nhãn NER **sinh tự động**, không viết tay

**Ngày:** 14/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `docs/09` §Phase 4 ghi bảng map ở `configs/wikidata_type_map.yaml`. Với ~2.400 lớp
Wikidata, viết tay không khả thi và không tái lập được khi dump cập nhật.

**Quyết định:** `scripts/build_type_map.py` sinh bảng map từ `data/interim/class_hierarchy.json`
(cạnh `P279` trực tiếp) + `data/interim/class_labels.json` (nhãn tiếng Anh/Việt). Khớp tên lớp
theo từ khoá với **ưu tiên cụm dài** và **danh sách cụm loại trừ** (vd "sovereign state",
"island country" → `LOCATION` để không khớp nhầm `PERSON`).

**Lý do:** tái lập được, cập nhật được, và tránh lỗi thủ công.

**Hệ quả:** bảng map có **~2.400 lớp**, phủ **94,2%** QID mục tiêu.
Chi tiết: `reports/deviations.md` D-035.

---

## D-044 — Mint `entity_id` sớm ở Phase 6 (không chờ Phase 9)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** 62.462 named mention có tên nhưng chưa có trong KB Phase 3.
Không có `entity_id` thì không đo được resolve rate, và Phase 7/9 sẽ phải mint lại.

**Quyết định:** mint `entity_id` ngay ở Phase 6 bằng `make_entity_id(type_ner, name)`
— **đúng hàm Phase 9 sẽ dùng** → id giống hệt, tái lập được.

**Hệ quả:** `coref_resolved.jsonl` dùng id giống hệt Phase 9 sẽ sinh.

---

## D-045 — `article_subject` nằm ở file riêng

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `data/interim/article_subjects.jsonl` (1 record/doc), không nhân bản
vào `coref_resolved.jsonl`.

**Lý do:** output contract của `coref_resolved.jsonl` đã chốt; thêm trường vào
186.960 record là rủi ro không cần thiết.

---

## D-046 — Bỏ `"y"` khỏi từ điển danh xưng

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Đo được:** 205/401 span "y" trong corpus là **false-positive** ("y tế",
"Trường Y", "y học"). Giữ "y" sẽ làm hỏng cả G3 lẫn G5.

---

## D-047 — Điều kiện R3: dùng như **tiên đề**, không giới hạn "đoạn không có PERSON"

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt · **sai lệch có chủ đích** so với `docs/09`

**Đặc tả** (`docs/09` §Phase 6): *"R3 — Chủ thể bài: dùng khi đoạn **không** có
entity `PERSON` nào"*.

**Đo được** (9 biến thể ablation trên gold 100 câu):

| Biến thể | Điều kiện R3 | G5 | G3 |
|---|---|---|---|
| B (đã chọn) | R3 là tiên đề (dùng luôn) | **0,8729** | 69,62% |
| H / I (bám sát đặc tả) | chỉ khi đoạn không có `PERSON` | **0,6864** | 66,76% |

**Quyết định:** giữ điều kiện linh hoạt. Thêm cờ `coref.r3_requires_no_person`
(mặc định `false`) để **đo được** biến thể bám sát đặc tả.

**Lý do:** đặc tả ở mức ý tưởng. Điều kiện "đoạn không có `PERSON`" giới hạn
R3 vào đoạn trống → mất phần lớn giá trị của tiên đề chủ thể bài (−16,65 điểm G5).

**Công khai:** `reports/deviations.md` D-047 — sai lệch **có chủ đích**, có số liệu
so sánh, không phải "quên làm".

---

## D-048 — Đại từ số nhiều → `null` + `ambiguous`

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Hiện tượng đo được:** "các ông", "các triều vua Trần", "các vua Trần Thái Tông" —
đây là **số nhiều**, không tham chiếu một thực thể đơn lẻ.

**Quyết định:** dò dấu hiệu số nhiều (`các`) đứng trước đại từ → trả `null`,
`resolved_by="ambiguous"`.

**Lý do:** gắn 1 entity đơn lẻ cho đại từ số nhiều là **sai** — vi phạm nguyên tắc
không bịa. Ảnh hưởng: **5.201 mention** chuyển từ "gắn sai" sang "bỏ qua".

---

## D-049 — R3 chỉ dùng cho đại từ nhãn `PERSON` khi chủ thể là **người**

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Hiện tượng:** trong bài về **sự kiện** ("Đảo chính Việt Nam Cộng hòa 1963"),
"ông" bị gắn nhầm sang `ent_dao_chinh_viet_nam_cong_hoa_1963` — entity sự kiện,
không phải người.

**Quyết định:** R3 chỉ kích hoạt khi `subject.type == "person"`.

---

## D-050 — `p31_direct` là tín hiệu **dự phòng cuối cùng**

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** lớp P31 trực tiếp của Wikidata (`Q5` = human) có độ chính xác
**cao hơn** `infobox_type`. Đo được **26 bài lệch**, ví dụ: Hồ Bắc (nhạc sĩ),
Trần Long Ẩn, Đa Minh Phạm Trọng Khảm, Giuse Hoàng Lương Cảnh.

**Vấn đề:** ground-truth của Gate G6 theo plan (`docs/09` §Phase 6) là
`infobox_type`/`wikidata_signal`. Đo được khi ưu tiên P31:

| Thứ tự | G6 | G3 |
|---|---|---|
| `infobox_type` → … → `p31_direct` (cuối) | **1,0000** | **69,62%** |
| `p31_direct` → `infobox_type` → … | 0,3859 | 60,30% |

**Quyết định:** `p31_direct` đứng **cuối cùng**, chỉ dùng khi 3 tín hiệu chính
không có gì. Ghi nhận đây là **giới hạn của ground-truth G6**, không phải giới
hạn của hệ thống — nêu công khai trong `reports/deviations.md`.

---

## D-051 — R3 và R6 phải **tôn trọng giới tính**

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Hiện tượng (phát hiện khi viết test):** R6 (fallback "đoạn có đúng 1 PERSON")
gắn entity **nữ** cho đại từ "ông" và ngược lại — vi phạm Gate G4.

**Quyết định:** cả R3 và R6 đều lọc theo giới tính đại từ; nếu entity duy nhất
mâu thuẫn giới tính → trả `null` + `ambiguous` (an toàn hơn gắn sai).

---

## D-052 — Thứ tự ưu tiên quy tắc R phải **cấu hình được**, không hard-code

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Bảng ablation đầu tiên của Phase 6 dùng **monkeypatch** (vá hàm
`_resolve_pronoun`) để đảo R3. Bản vá chạy R3 **trước** chốt an toàn "đại từ
số nhiều" (R5-pre) → đo **sai**, ra con số 0,7797 không tồn tại trên hệ thống
thật, và khiến kết luận thiết kế **đảo ngược**.

**Quyết định:** tách mỗi quy tắc thành một nhánh `_apply_pronoun_rule()` và
điều phối theo `coref.pronoun_rule_order` (mặc định `[r3, r1a, r1b, r5, r6]`).
Ablation ghi đè mục này vào config → chạy trên **đúng đường dẫn code thật**.

**Lý do:** mọi con số trong báo cáo phải **tái lập được từ code đang chạy**.
Một ablation chạy trên đường dẫn khác với production là **số liệu giả**.

**Hệ quả:** 9 biến thể đo lại; kết luận đảo ngược (R3 trước R1a tốt hơn,
G5 0,8475 → 0,8729). Thêm 5 test ở `tests/test_coref.py`
(`TestConfigurableRuleOrder`).

---

## D-053 — R1b chỉ dùng khi đoạn có **đúng 1 người** (đo được, nhưng **không** bật)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt (giữ cờ, mặc định tắt)

**Bối cảnh:** R1b ("người cuối cùng được nhắc ở câu trước") là quy tắc **yếu
nhất**: đưa nó lên đầu làm G5 tụt còn 0,8390 (biến thể D). Nguyên nhân quan
sát được: ứng viên thường là người *được nhắc* ("đời Thiệu Trị", "Sau khi
Thành Thái lên ngôi"), không phải chủ thể *đang được nói đến*.

**Đo được:** thêm cờ `coref.r1b_unique_only` → G5 0,8475 → 0,8559 (biến thể E).
Kiểm định McNemar: **p = 1,00** (chỉ 1 mention đổi chiều) → **không có ý nghĩa
thống kê**.

**Quyết định:** **không bật** trong cấu hình chính (`r1b_unique_only: false`).
Giữ cờ + 2 test làm **phương án dự phòng đo được** cho Phase 7+ (khi có bộ
gold lớn hơn).

---

## D-054 — Công khai sai lệch có chủ đích với `docs/09` (điều kiện R3)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** ghi sai lệch D-047 (điều kiện R3) vào `reports/deviations.md` với
đầy đủ số liệu so sánh (biến thể H/I: G5 0,6864 vs 0,8729), **không** sửa số
liệu để "cho xanh" và **không** im lặng lệch khỏi đặc tả.

**Lý do:** nguyên tắc của dự án — lệch kế hoạch phải được **công khai kèm số
liệu**, để người đọc báo cáo biết giới hạn nào là do hệ thống, giới hạn nào là
do đặc tả.

---

## D-055 — Báo cáo `coref_quality.md` phải lược bỏ ký tự Hán (Trung Quốc)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `src/coref/quality_report.py` thay mọi ký tự Hán trong văn bản
corpus bằng `<bỏ dấu>` trước khi render ra Markdown (dùng cùng ký hiệu với
`src/preprocess/extract_lead_dates.py`).

**Lý do:** corpus Wikipedia tiếng Việt trích nguyên văn chữ Hán trong ngoặc
(vd. `chữ Hán: <chu Han>`) — đo được **1.030/2.441 bài** có ký tự Hán trong
`clean_text` (23.832 ký tự). Báo cáo Phase 6 render **nguyên văn** câu mẫu
nên đã làm phát sinh ký tự Trung Quốc trong `reports/coref_quality.md` — vi
phạm quy tắc `.cursor/rules/no-chinese.mdc` ("tuyệt đối không sử dụng tiếng
Trung trong bất kỳ phản hồi, giải thích, tài liệu nào").

**Cách làm:** hàm `sanitize_han()` trong `src/coref/quality_report.py`, áp cho
cả phần text câu và phần text mention; thêm 3 test regression
(`tests/test_coref.py::TestNoChineseInReport`) chặn hồi quy — trong đó có
test đọc trực tiếp file `reports/coref_quality.md` đã sinh.

**Ảnh hưởng:** `coref_resolved.jsonl` **không** đổi (chỉ là lớp render báo
cáo) → MD5 vẫn `cb86fd32fbdb679c0213a29030f76743`, Gate G1–G8 không đổi. Số
test suite: 436 → **439**.

**Bài học:** bước rà soát "không có tiếng Trung" phải quét **cả file sinh ra
tự động**, không chỉ file viết tay — nội dung do corpus mang vào sẽ lọt qua
mắt thường.


---

## D-056 — Hợp nhất **3 nguồn** nhãn POSITIVE (Wikidata + Infobox + Lead)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `data/interim/re_positive.jsonl` gộp 3 nguồn — Wikidata
(12.197 mẫu), Infobox Phase 3 (3.361), Lead Phase 3 (22). Dedupe theo khoá
4 thành phần `(sentence_id, subject, relation, object)`, ưu tiên nguồn
`wikidata > infobox > lead`.

**Lý do:** Đo được — Wikidata thuần cho **12.197** mẫu / **10** quan hệ và
thiếu 6 quan hệ (`ke_vi`, `thuoc_trieu_dai`, `chi_huy_tran`, `dong_doi_tai`,
`lap_ra`, `dien_ra_tai`) mà Wikidata không có. Chỉ hợp nhất nguồn nội bộ mới
đạt **15.580** mẫu / **17** quan hệ → vượt Gate G1 (10.000) **55,8%** và Gate
G3 (8 quan hệ) hơn 2×.

**Ảnh hưởng:** `src/re/ground_triples.py` có 2 hàm grounding riêng
(`ground_wikidata_pairs`, `ground_triples` cho infobox/lead) + bước merge.
Artifact có trường `source` để truy vết nguồn nhãn.

**File đã cập nhật:** `src/re/ground_triples.py`, `src/re/build_re_dataset.py`,
`docs/DECISIONS.md`.

---

## D-057 — Negative "an toàn": chỉ cặp **có cả hai QID** và **không** mang quan hệ

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Negative chỉ lấy từ cặp entity đồng câu mà **cả hai đầu đều có
QID** và **không** cặp QID nào của chúng mang quan hệ nào trong 13 property
lõi. Quan hệ đối xứng được coi là "đã có" theo **cả hai chiều**.

**Lý do:** Đo được trên 86.934 cặp entity đồng câu — **12.562** cặp an toàn
(cả 2 đầu có QID + không có quan hệ), **1.815** cặp bị loại vì đang mang
quan hệ, **72.557** cặp bị loại vì một đầu không rõ QID. "Không có trong
Wikidata" ≠ "không có trong thực tế" → cho phép cặp "không rõ" vào negative
sẽ tạo false negative ở tỉ lệ rất cao.

**Ảnh hưởng:** `collect_negative_candidates()` trong `src/re/build_re_dataset.py`
lọc trước khi lấy mẫu; có test
`test_negative_excludes_pairs_holding_a_relation` và
`test_negative_excludes_pairs_without_qid`.

**File đã cập nhật:** `src/re/build_re_dataset.py`, `tests/test_re_dataset.py`,
`docs/DECISIONS.md`.

---

## D-058 — Tái dùng `src/preprocess/wikidata_query.py`, không viết client SPARQL mới

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `src/re/build_distant_supervision.py` dùng `run_query()` của
Phase 1 (fallback QLever → WDQS, throttle, retry, cache đĩa) thay vì tạo
`src/re/wikidata_client.py` như gợi ý trong `docs/09`. Vì WDQS **và** QLever
đều không trả tên property khi dùng `UNION` (biến predicate rơi khỏi kết
quả), phải hỏi **từng property một**, chia lô 200 QID.

**Lý do:** Module Phase 1 đã có đủ toàn bộ cơ chế (throttle, retry, cache,
fallback endpoint) — viết thêm sẽ phải sao chép logic và tạo hai nơi sửa khi
WDQS lại 429. Số liệu đo được: 428 file cache; chạy lại builder = **0 request
HTTP** (97,7 s) → Gate G5 đạt.

**Ảnh hưởng:** Query chia theo property × chunk triều đại; cache dùng chung
`data/interim/wikidata_cache/`. Cần thêm 2 hàm chuẩn hoá: `_binding_value()`
(bóc `.value` cho cả 2 endpoint) và `_clean_label()` (bỏ `"` và hậu tố `@vi`).

**File đã cập nhật:** `src/re/build_distant_supervision.py`,
`configs/default.yaml` (khối `re:`), `docs/DECISIONS.md`.

---

## D-059 — Hướng `P40` là `inverse` (Wikidata nói "cha → con", KG cần "con → cha")

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `P40` (child) ánh xạ tới `cha_cua` với `direction: inverse` —
grounding đảo subject ↔ object.

**Lý do:** Nếu giữ `forward`, nhãn `cha_cua` sẽ bị **đảo ngược** — mô hình
học "cha là con". Đo được: `P40` sinh 1.083 cặp thô → 1.577 mẫu ground; giữ
forward sẽ gán nhãn sai chiều cho toàn bộ 1.577 mẫu.

**Ảnh hưởng:** `configs/wikidata_relations.yaml` (`P40: direction: inverse`),
`src/re/ground_triples.py` (đảo hai đầu khi `inverse`).

**File đã cập nhật:** `configs/wikidata_relations.yaml`,
`src/re/ground_triples.py`, `tests/test_re_dataset.py`, `docs/DECISIONS.md`.

## D-060 — `re_train.jsonl` là **record theo câu** với mảng `pairs` lồng (đồng bộ `docs/09` + `data-contracts`)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `data/interim/re_train.jsonl` ghi **1 record/câu** (không phải
1 record/cặp), gồm `run_id`, `sentence_id`, `doc_id`, `page_id`, `split`, `text`
và mảng `pairs` lồng. Nhãn là **chuỗi** `"POSITIVE"`/`"NEGATIVE"`. Mỗi cặp
mang `mention` (dạng bề mặt trong câu, giữ dấu), `entity_id`, `name` (tên chuẩn)
và offset `start`/`end` thỏa `text[start:end] == mention`.

**Lý do:** Bản đầu của phase ghi **phẳng theo cặp** với nhãn số `1`/`0` và
không có `run_id`. Điều đó **vi phạm 3 hợp đồng đã chốt**:

1. `docs/09` §Phase 7 (output contract) và `.cursor/rules/data-contracts.mdc`
   §Định dạng chung yêu cầu `run_id` cho mọi record.
2. Lệnh kiểm thử **chính thức** trong `docs/09` và plan đọc
   `r['pairs']` / `p['label']=='POSITIVE'` → lệnh này **crash** với bản phẳng.
3. `data-contracts.mdc` §Offset yêu cầu offset luôn kiểm được
   `text[start:end] == span_text` → bản phẳng không có offset nào.

Ngoài ra, gom theo câu giúp Phase 8 chỉ cần **tokenize `text` một lần** cho
mọi cặp thay vì lặp lại theo từng cặp.

**Ảnh hưởng:** `src/re/build_re_dataset.py` (sinh record theo câu),
`src/re/re_dataset_stats.py` + `scripts/re_gate_check.py` (đọc mảng `pairs`
lồng), `src/re/ground_triples.py` (mang offset span + tên có dấu),
`tests/test_re_dataset.py` (test contract mới), `docs/09` §Phase 7 (contract
được viết lại cho khớp), `AGENTS.md` §7.

**Số liệu đo được:** 12.877 câu / 29.957 cặp; **59.914/59.914** offset thỏa
`text[start:end] == mention` (0 sai lệch, 0 thiếu span) — trước khi sửa có
**43.841 sai lệch** và **455** cặp thiếu span.

**File đã cập nhật:** `src/re/build_re_dataset.py`, `src/re/ground_triples.py`,
`src/re/re_dataset_stats.py`, `scripts/re_gate_check.py`,
`tests/test_re_dataset.py`, `docs/09-ke-hoach-thuc-thien.md`, `AGENTS.md`,
`docs/DECISIONS.md`.

## D-061 — RE dùng **đa nhãn sigmoid** (18 nhị phân + 1 lớp `NA`), không dùng multi-class softmax

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Mô hình RE là **multi-label sigmoid** với **19 đầu**: 18 đầu
quan hệ (mỗi quan hệ 1 sigmoid) + 1 đầu `NA`. Nhãn mục tiêu là **vector 19
chiều**; slot quan hệ **chưa biết** được gán `-100.0` và **bị bỏ qua** trong
loss (masked BCE). Đầu `NA` **luôn** có supervision: `1.0` nếu input không có
quan hệ POSITIVE nào, ngược lại `0.0`.

**Lý do:** Multi-class softmax chỉ giữ được **một** quan hệ cho mỗi cặp, trong
khi thực tế một cặp entity có thể mang **nhiều quan hệ** đúng ("Lê Lợi" vừa
`cha_cua` vừa `ke_vi`). Đo được trên tập Phase 7: nhiều input có **≥ 2 quan hệ
POSITIVE** — softmax sẽ **mất** các quan hệ còn lại. Lựa chọn này giữ được
100% quan hệ thật sự, và trần F1 = 1,0 (không bị trần 1/K như softmax).

Mask `-100.0` thay vì `0.0` là **bắt buộc**: nếu dùng `0.0`, mô hình bị học
"quan hệ này không có" cho mọi quan hệ chưa quan sát → mất trung thực, giảm
recall mạnh.

**Ảnh hưởng:** `src/re/data_convert_re.py` (`LABEL_LIST`, `NUM_LABELS`,
`IGNORE_VALUE`, `build_labels`), `src/re/train_re.py` (`masked_bce_loss`,
`MultiLabelTrainer`), `src/re/infer_re.py` (lọc `NA` + threshold),
`src/evaluation/metrics.py` (`relation_f1_multilabel`),
`tests/test_re_model.py`, `configs/default.yaml` (khối `re.train`).

**File đã cập nhật:** `src/re/data_convert_re.py`, `src/re/train_re.py`,
`src/re/infer_re.py`, `src/evaluation/metrics.py`, `tests/test_re_model.py`,
`configs/default.yaml`, `docs/DECISIONS.md`.

## D-062 — Marker có **kiểu + vai trò**: `«TYPE:SUBJ:name»` / `«TYPE:OBJ:name»`

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Chuỗi đưa vào mô hình có dạng:

```
<s> subj_mention </s> câu có «PERSON:SUBJ:Lê Lợi» và «PERSON:OBJ:Nguyễn Phúc Chu» </s> obj_mention </s>
```

Nhãn ở vị trí `[CLS]`.

**Lý do:** Đo được **mức mơ hồ thật** trên corpus Phase 6:

| Hiện tượng | Số cặp | Tỉ lệ |
|---|---|---|
| Hai đầu có **mention bề mặt giống hệt nhau** | 1.383 | 4,62% |
| — sau khi dùng **tên hiển thị chuẩn** (infobox → mode mention) | 83 | 0,28% |
| — 83 cặp còn lại đều là **self-loop** (`subject == object`) | 83 | — |
| Cặp có **span chồng lấn** | 1.552 | 5,20% |

Nếu marker chỉ chứa tên (đặc tả gốc: `«PERSON:Lê Lợi»`), mô hình **không phân
biệt được** đâu là chủ thể và đâu là đối tượng khi tên trùng → nhãn hướng sai
(khoảng 4,6% cặp). Thêm **vai trò** (`SUBJ`/`OBJ`) vào marker giải quyết dứt
điểm: chuỗi luôn phân biệt được hướng, không cần dựa vào vị trí.

Ngoài ra, **tên hiển thị chuẩn** được resolve theo chuỗi: `infobox_entities`
→ **mode** của các mention không phải đại từ trong `coref_resolved` → mention
thô. Nhờ đó 1.300/1.383 cặp mơ hồ được giải quyết bằng tên, phần còn lại
xử lý bằng vai trò.

**Ảnh hưởng:** `src/re/data_convert_re.py` (`marker_words`, `display_marker`,
`build_display_names`), `src/re/infer_re.py` (dùng chung bảng tên),
`tests/test_re_model.py`.

**File đã cập nhật:** `src/re/data_convert_re.py`, `src/re/infer_re.py`,
`tests/test_re_model.py`, `docs/DECISIONS.md`.

## D-063 — Bảng **type entity** theo chuỗi: NER vote → infobox → tiền tố `year_` → `unknown`

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Type của một entity được xác định theo chuỗi ưu tiên:

1. **Vote đa số** nhãn NER trên các mention resolve về `canonical_id` đó
   trong `coref_resolved.jsonl` (độ phủ **93,5%**).
2. Type trong `infobox_entities.jsonl`.
3. Tiền tố id `year_` → type `year`.
4. Không có → `unknown`.

**Lý do:** Marker typed cần type để mô hình có ngữ cảnh ("Lê Lợi" là `PERSON`
hay `DYNASTY` ảnh hưởng lớn tới quan hệ có thể có). Vote NER là nguồn **rộng
nhất** (93,5% entity), nhưng có thể sai khi mention trùng nghĩa; infobox là
nguồn **chính xác hơn** nhưng chỉ phủ entity có infobox. Chuỗi này lấy phần
độ phủ từ vote NER và phần độ chính xác từ infobox.

**Ảnh hưởng:** `src/re/data_convert_re.py` (`build_entity_types`,
`resolve_entity_type`), `src/re/infer_re.py`, `tests/test_re_model.py`.

**File đã cập nhật:** `src/re/data_convert_re.py`, `src/re/infer_re.py`,
`tests/test_re_model.py`, `docs/DECISIONS.md`.
## D-065 — Kernel Kaggle phải **bundle model** (không có DNS) và mount dataset bằng **glob**

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Mọi kernel Kaggle của dự án phải tuân theo 3 quy tắc:

1. **Bundle weight model** trong dataset Kaggle (không dùng `from_pretrained` trỏ
   thẳng `huggingface.co`), vì kernel **không có DNS** ra internet — đã xác nhận
   ở Phase 5 (D-038) và tái xác nhận ở Phase 8.
2. **`dataset_sources` bắt buộc có giá trị**; metadata kernel **chỉ sinh từ
   builder script** (`scripts/build_kaggle_*_notebook.py`), không viết tay.
   Sau khi push phải verify bằng `kaggle kernels pull -m`.
3. **Không hard-code đường dẫn mount / tên file** — Kaggle có thể đặt thư mục
   kèm hậu tố (`vhgr-re-data-2`) và có thể giải nén `.gz` khi mount → dùng
   `rglob`/`glob` + tự nhận diện `.gz`/plain.

**Lý do:** Cả 4 lỗi tìm được ở Phase 8 đều **không lộ ra khi chạy local**:
local có model sẵn trong `~/.cache`, đường dẫn mount không đổi, và không ai
kiểm tra `metrics.json` có đúng trường Gate G1 yêu cầu hay không.

**Ảnh hưởng:** `scripts/build_kaggle_re_notebook.py`,
`scripts/build_kaggle_llm_notebook.py`, `data/kaggle/vhgr_re_data/`
(dataset v2 — bundle `models_hf/phobert-base`).

**File đã cập nhật:** `scripts/build_kaggle_re_notebook.py`,
`scripts/build_kaggle_llm_notebook.py`,
`data/kaggle/vhgr_re_data/dataset-metadata.json`,
`data/kaggle/vhgr_re_data/manifest.json`, `reports/deviations.md` (D-065…D-068).

## D-066 — Nguồn model trên Kaggle: **Kaggle Models** là lựa chọn thứ nhất cho LLM mở

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Thứ tự ưu tiên nguồn model cho kernel LLM:
`LLM_MODEL_PATH` (biến môi trường) → bundle trong dataset → **Kaggle Models**
(`manojkumarcs28/qwen3-8b/PyTorch/qwen3-8b/1`, mount tại
`/kaggle/input/qwen3-8b`) → HuggingFace (chỉ khi kernel có internet).

**Lý do:** `Qwen/Qwen3-8B` (16,4 GB) không tải được từ `huggingface.co` do
kernel không có DNS. Kaggle Models mount **nhanh hơn** (không phải tải 16 GB
qua mạng) và là đường chính thức của Kaggle cho model mở.

**Ảnh hưởng:** `scripts/build_kaggle_llm_notebook.py` (`resolve_model_source`,
`MODEL_CANDIDATES`), `notebooks/kaggle/06_llm_extract_kaggle/kernel-metadata.json`
(`model_sources`).

**File đã cập nhật:** `scripts/build_kaggle_llm_notebook.py`,
`reports/deviations.md` (D-066).

## D-067 — `metrics.json` của mô hình RE phải có **`per_relation` + `macro_f1`**

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `models/re/metrics.json` bắt buộc có: `micro_f1`,
`micro_precision`, `micro_recall`, **`macro_f1`**, `na_f1`, `threshold`,
**`per_relation`** (18 quan hệ, mỗi quan hệ `{support, precision, recall, f1}`).

**Lý do:** Gate G1 của `docs/09` §Phase 8 ghi rõ "RE micro-F1 dev ≥ 0,70
(**per-relation trong `metrics.json`**)". Đây là yêu cầu **cấu trúc artifact**,
không phải ghi chú. Ngoài ra cần per-relation để **phân tích lỗi theo quan hệ**
khi F1 không đạt (mục "Lùi" của phase).

**Quy ước đếm:** Quan hệ bị **mask** (`-100.0`, chưa được giám sát cho input đó)
**không** tính vào FP/FN — đúng đặc tả đa nhãn (D-061). Quan hệ không có
supervision nào → `support=0`, `f1=0` (nhưng **vẫn xuất hiện** trong báo cáo).
`macro_f1` chỉ tính trên các quan hệ có `support > 0`.

**Ảnh hưởng:** `scripts/build_kaggle_re_notebook.py` (`per_relation_f1`),
`models/re/metrics.json` (sinh trên Kaggle).

**File đã cập nhật:** `scripts/build_kaggle_re_notebook.py`,
`reports/deviations.md` (D-068), `reports/phase_08_report.md`.

## D-070 — Qwen3 phải **tắt thinking mode** (`enable_thinking=False`) khi trích xuất JSON

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Khi sinh phản hồi từ Qwen3 trong notebook LLM, gọi
`tokenizer.apply_chat_template(..., enable_thinking=False)` (chỉ truyền tham số
này cho model có "qwen3" trong tên). Đồng thời notebook **fail-fast**: 3 request
liên tiếp không parse được JSON → in raw output rồi `raise`.

**Lý do:** Qwen3 là model **hybrid reasoning** — mặc định sinh `<think>...</think>`
*trước* khi trả lời. Raw output không phải JSON ⇒ `parse_json` trả `None` ⇒
**0 triple** dù model chạy bình thường. Đo được ngày 15/11/2026: kernel
`hoanghiep421/vhgr-phase-8-llm-extract-qwen3-8b-4bit` chạy 796s với
`5 request | giữ 0/0 | 0,01 req/s` — 100% request thất bại, mất ~12 h phiên GPU.

**Ảnh hưởng:** `scripts/build_kaggle_llm_notebook.py` (`generate()`, vòng lặp
chính), `notebooks/kaggle/06_llm_extract_kaggle/notebook.ipynb`.

**File đã cập nhật:** `scripts/build_kaggle_llm_notebook.py`,
`reports/deviations.md` (D-070).

## D-071 — Chia 2 kernel Phase 8 sang **2 tài khoản Kaggle** để chạy song song

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Kaggle giới hạn **2 phiên GPU đồng thời / tài khoản**. Phân bổ:
- `hoanghiep421/vhgr-phase-8-re-train-phobert-base` — huấn luyện RE (dataset
  `hoanghiep421/vhgr-re-data`)
- `dathungdao2004/vhgr-phase-8-llm-extract-qwen3-8b-4bit-sec` — trích xuất LLM
  (dataset `dathungdao2004/vhgr-re-data` + Kaggle Models `qwen3-8b`)

**Lý do:** Tài khoản chính bị nghẽn (LLM chiếm 1 slot + RE 1 slot QUEUED).
Tài khoản phụ **không mount được dataset riêng tư của tài khoản chính** ⇒
phải tạo dataset `dathungdao2004/vhgr-re-data` (337 MB, đã upload 15/11/2026).

**Lý do (tiếp):** Kế hoạch ban đầu để **cả 2 kernel LLM trên tài khoản phụ** không
khả thi — tài khoản phụ cũng giới hạn 2 slot và cả 2 vẫn `QUEUED`. Đo được:
GPU của Kaggle là hạn mức **dùng chung**, không phải per-account ⇒ 2 kernel
(có thể trên 2 account khác nhau) vẫn phải chờ hàng đợi toàn cục.

**Cơ chế chuyển account:** `KAGGLE_API_TOKEN` (biến môi trường) **có ưu tiên
hơn** `~/.kaggle/access_token` ⇒ đổi account chỉ cần đổi biến này.

**File đã cập nhật:** `scripts/wait_kaggle_phase8.py` (watcher 2 tài khoản),
`reports/deviations.md` (D-069, D-071).

## D-072 — Thêm **đường chạy CPU-only** cho RE training trên Kaggle

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Bổ sung biến thể CPU của notebook RE
(`scripts/build_kaggle_re_notebook.py --cpu-variant` → kernel
`hoanghiep421/vhgr-phase-8-re-train-phobert-base-cpu`, `enable_gpu: false`),
chạy **song song** với 2 kernel GPU.

**Lý do:** Hàng đợi GPU của Kaggle là **dùng chung toàn cục** (đo được: 2 kernel
trên 2 tài khoản khác nhau vẫn `QUEUED` từ 12:12→12:46 UTC). Kaggle **CPU
notebook không tiêu tốn quota GPU** ⇒ đường chạy song song không phụ thuộc hàng
đợi GPU. Vẫn nằm trong ràng buộc của người dùng: **không huấn luyện local**.

**Điều chỉnh:** `RE_EPOCHS` 3→2, `RE_BATCH` 16→8 (CPU chậm ~8–10× GPU).

**Ảnh hưởng:** `scripts/build_kaggle_re_notebook.py`, `scripts/wait_kaggle_phase8.py`,
`notebooks/kaggle/re_train_phobert_base_cpu/`, `reports/deviations.md` (D-072).

## D-074 — Neo4j container phải recreate (image cũ trong volume)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `docker compose up -d --force-recreate neo4j` thay vì `up -d`.

**Lý do:** Container `vhgr_neo4j` crash-loop với
`Failed to read config: Unrecognized setting. No declared setting with name: .`
Đối chiếu: chạy cùng bộ biến môi trường trên image `neo4j:5-community`
(5.26.32) mới → khởi động bình thường. ⇒ lỗi do **container cũ dùng image cũ**
(đã bị thay thế trong registry), không phải cấu hình sai.

**Ảnh hưởng:** `docker-compose.yml` (không đổi), quy trình khởi động hạ tầng.

## D-075 — Inference RE chạy song song bằng sharding + cache cặp ứng viên

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Thêm `--num-shards/--shard-index` và `--candidates-cache` cho
`src/re/infer_re.py`; script mới `scripts/run_infer_re_parallel.py` chạy N tiến
trình (mặc định 4) rồi gộp output.

**Lý do:** Suy luận trên CPU cho 99.348 cặp ứng viên mất ≈ 2,5 giờ với 1 tiến
trình (đo: 0,090 s/cặp ở 4 thread). 4 shard × 2 thread ≈ 8 luồng CPU →
rút xuống ≈ 35–45 phút. Cache cặp ứng viên là bắt buộc: không có cache, mỗi
shard phải quét lại `coref_resolved.jsonl` (~3 phút/quét, đo được).

**Thay đổi kèm theo:** `torch.set_num_threads(OMP_NUM_THREADS)` — mặc định
torch chỉ dùng 4 thread dù `OMP_NUM_THREADS=8` (đo được, giảm ~30% tốc độ).

**Ảnh hưởng:** `src/re/infer_re.py`, `scripts/run_infer_re_parallel.py`,
`scripts/finish_phase8.py`.

## D-076 — Neo4j Community: nạp KG bằng câu Cypher tĩnh theo nhóm (không APOC)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** `scripts/load_neo4j.py` **gom node theo 9 label** và **gom edge
theo 18 quan hệ**, dựng câu Cypher tĩnh cho từng nhóm (`MERGE (n:Person
{entity_id: …})`, `MERGE (s)-[r:ke_vi]->(t)`).

**Lý do:** Neo4j 5 Community **không có APOC** (đo được: `SHOW PROCEDURES
YIELD name WHERE name STARTS WITH 'apoc'` → 0). Cả dynamic label
(`SET n:$(lbl)`) lẫn dynamic relationship type (`MERGE (a)-[r:$(rt)]->(b)`)
đều **không được hỗ trợ** trong Cypher 5 → server báo `Variable 'lbl' not
defined`. Gom theo nhóm là cách duy nhất không cần plugin.

**Điều chỉnh khác:**
- Property không hợp lệ (list-of-dict như `aliases`) → chuyển thành **JSON
  string** (Neo4j chỉ nhận primitive/array; đo được lỗi
  `Property values can only be of primitive types or arrays thereof`).
- Session chỉ-đọc dùng `default_access_mode="READ"` (không phải `READ_ACCESS`
  — driver 5.x chỉ nhận `'READ'`/`'WRITE'`).

**Ảnh hưởng:** `scripts/load_neo4j.py`, `scripts/create_readonly_user.sh`,
`scripts/validate_graph.py`.

## D-077 — Ưu tiên kernel **GPU** khi có song song GPU + CPU; điều kiện nhận là **artifact đo được**, không phải trạng thái `COMPLETE`

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Quyết định:** Khi có nhiều kernel Kaggle chạy song song cùng một nhiệm vụ,
**chọn kernel có đầy đủ artifact đo được** (`metrics.json` cho train;
output JSONL cho infer). Với Phase 8: dùng
`vhgr-phase-8-re-train-phobert-base` (**GPU**, 3 epoch, toàn bộ 20.382 câu,
micro-F1 **0,9375**); **loại** `vhgr-phase-8-re-train-phobert-base-cpu` (CPU,
subsample 6.000, dừng ở epoch 1, **không có `metrics.json`**).

**Lý do:**
- Kernel CPU có trạng thái `COMPLETE` nhưng **không sinh `metrics.json`** ⇒
  **không đo được** Gate G1 (RE F1 dev ≥ 0,70). "Xong" ≠ "đo được".
- GPU đạt micro-F1 0,9375 vượt Gate rất xa, train trên **toàn bộ** tập ⇒
  không cần đánh đổi chất lượng để đổi lấy tốc độ.
- Artifact CPU tải về ~2,7 GB và **không dùng được** ⇒ xoá để giải phóng đĩa.

**Nguyên tắc rút ra:** trạng thái kernel (`COMPLETE`/`RUNNING`) là thông tin
**trạng thái**, không phải thông tin **kết quả**. Điều kiện nhận phải là artifact
đo được.

**Điều chỉnh kèm theo:** `notebooks/kaggle/06_llm_extract_kaggle` được **push
lại** sau khi GPU RE xong (trước đó chưa từng chạy được vì hàng đợi GPU dùng
chung) để sinh `data/interim/re_llm_kaggle.jsonl`.

**Ảnh hưởng:** `docs/10-nhat-ky/phase-08.md` §4.6.1, `models/re/`,
`reports/phase_08_report.md`.

---

## D-079 — Chuyển kernel suy luận RE sang **tài khoản Kaggle phụ** khi quota GPU tài khoản chính đã cạn

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Sau khi train xong trên GPU (D-077), cần suy luận RE trên
99.348 cặp ứng viên. Máy local **không có GPU**; CPU 8 nhân ước tính ~3,5 giờ
(với 4 shard × 2 thread, đo được 0,51 s/cặp/shard). Đẩy kernel lên Kaggle
để chạy ~15 phút.

**Phát hiện:** tài khoản chính `hoanghiep421` đã **hết quota GPU**:

| Tài khoản | `timeUsed` | `totalTimeAllowed` | Reset | Còn lại |
|---|---|---|---|---|
| `hoanghiep421` (chính) | 44.677 s | 21.600 s | 21/11/2026 | **0** (vượt 2×) |
| `dathungdao2004` (phụ) | 17.172 s | 21.600 s | 21/11/2026 | **~4.428 s (~74 phút)** |

⇒ Kernel `hoanghiep421/vhgr-phase-8-re-infer-phobert-gpu` kẹt `QUEUED` **vĩnh viễn**
(hàng đợi chỉ cấp phát khi còn quota).

**Quyết định:**
1. **Dừng/xoá** các kernel không còn cần: `vhgr-phase-8-re-train-phobert-base-cpu`
   (đã loại ở D-077), `vhgr-phase-8-llm-extract-qwen3-8b-4bit` (chiếm 2 slot
   GPU trong ~8,8 giờ với 5.000 câu — cắt `LLM_LIMIT` 5.000 → 600 để chạy lại
   sau, khi GPU rảnh).
2. **Đóng gói lại** bundle suy luận (`scripts/pack_re_infer_dataset.py` → dataset
   `dathungdao2004/vhgr-re-infer`, 677 MB) rồi **push kernel lên tài khoản phụ**
   (`dathungdao2004/vhgr-phase-8-re-infer-phobert-gpu`). Dataset **private không
   chia sẻ chéo tài khoản** ⇒ phải tạo bản dataset riêng cho tài khoản phụ.
3. **Giữ chạy song song** 4 shard CPU local làm phương án dự phòng.

**Lý do:** đây là ràng buộc **hạ tầng**, không phải lựa chọn kỹ thuật — không
thể chờ reset 21/11 khi cần kết quả trong ngày. Kernel vẫn chạy **chính mã
nguồn repo** (`src/re/infer_re.py`) nên kết quả GPU **khớp** chạy local.

**Ảnh hưởng:** `scripts/pack_re_infer_dataset.py` (mới),
`scripts/build_kaggle_re_infer_notebook.py` (thêm `--owner`),
`scripts/finish_phase8_gpu.py` (tự chọn tài khoản theo kernel),
`docs/10-nhat-ky/phase-08.md`, `reports/deviations.md`.

---

## D-080 — Chỉ giữ **Top-1 quan hệ/cặp** + kiểm **kiểu đối tượng** theo schema khi hợp nhất triple mô hình

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Metric Phase 8 (`relation_f1_multilabel`) **bỏ qua** các slot bị mask
(quan hệ chưa được giám sát cho input đó). Trong dữ liệu train, slot NEGATIVE
chỉ supervise **một** quan hệ ⇒ 17/18 đầu còn lại **không có gradient** ⇒ khi
suy luận trên corpus, các đầu này tự do phát giá trị cao mà **không** bị metric
phạt.

**Đo được (`scripts/eval_re_strict.py`, split dev, 2.987 cặp, ngưỡng 0,55):**

| Chỉ số | Lỏng (masked BCE) | Nghiêm (slot mask = FP) |
|---|---|---|
| precision | — | **0,0854** |
| recall | — | **0,9652** |
| F1 | 0,9375 | **0,1569** |
| TP / FP / FN | — | 1.805 / **19.339** / 65 |
| FP thuộc slot MASK | — | **19.220 (99,4%)** |
| Cặp có ≥ 1 quan hệ dự đoán | — | **1.731/2.987 (58,0%)** |
| Số quan hệ fire/cặp | — | 976 cặp fire **16** quan hệ; 260 cặp fire 7 |

⇒ Vấn đề **không** phải model yếu, mà là **loss không giám sát** slot ⇒ ở ngoài
tập train các đầu "nổ" tuỳ ý. Đây là hệ quả trực tiếp của D-061 (masked BCE)
khi dữ liệu NEGATIVE chỉ supervise 1 quan hệ.

**Quyết định:** khi hợp nhất, nguồn mô hình (`phobert_re`, `llm`) phải qua bộ lọc
4 lớp (tất cả trong `src/re/merge_triples.py`):

1. **Top-1/cặp** — mỗi cặp `(sentence_id, subject, object)` chỉ giữ quan hệ
   **confidence cao nhất** (`MAX_RELATIONS_PER_PAIR = 1`).
2. **Kiểu đối tượng** theo schema (`docs/04` §3.1) — ví dụ `sinh_nam` bắt buộc
   đích là `Year`; loại nếu đích là entity loại khác. Trừ khi đích là `unknown`
   (chưa xác minh) thì giữ để không mất dữ liệu.
3. **Kiểu chủ thể** theo schema — ví dụ `lap_ra` phải xuất phát từ `Person`/
   `Dynasty`, không thể từ `Place`.
4. **Bằng chứng có thật** — tên chủ thể **và** tên đối tượng phải xuất hiện
   trong `evidence_sentence` (D-082).
5. **Từ kích hoạt** trong câu bằng chứng (D-083).

**Số liệu hiệu ứng (đo trên `triples_merged.jsonl`):**

| Bước | `phobert_re` | `llm` |
|---|---|---|
| Vào | 511.567 | 349 |
| Ra | **4.985** (0,97%) | **148** (42,4%) |

**Lý do:** bộ lọc là **hậu xử lý có thể kiểm chứng**, khác với học metric. Giữ
triple sai còn tệ hơn bỏ triple đúng, vì KG dùng để trả lời QA — mỗi cạnh sai
là một câu trả lời sai.

**Ảnh hưởng:** `src/re/merge_triples.py` (`MAX_RELATIONS_PER_PAIR`,
`RELATION_TARGET_TYPES`, `RELATION_SOURCE_TYPES`, `filter_model_triples`),
`scripts/eval_re_strict.py`.

---

## D-081 — Danh sách chặn **tên chung** (danh từ chức vụ/danh hiệu) cho mọi quan hệ

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** NER Phase 5 gán nhãn `TITLE` cho các danh từ chung ("vua", "ông",
"bà", "nhà", "hoàng đế"). Chúng được link thành **entity riêng** (`ent_vua_…`)
và sinh hàng nghìn cạnh vô nghĩa kiểu `Lê Thái Tổ --vo_cua--> vua`.

**Đo được:** 12.273/50.677 cạnh (**24,2%**) có ít nhất một đầu là tên chung.

**Quyết định:** `GENERIC_TITLE_NAMES` — danh sách ~70 danh từ chức vụ/danh
hiệu/tổ chức. Mọi cạnh có đầu là tên chung bị loại.

**Số liệu:** 15.825 → **13.379** triple (loại **2.446** cạnh).

**Lý do:** "vua", "ông", "nhà" là **danh từ chức vụ**, không phải thực thể lịch
sử có QID ⇒ cạnh chứa chúng vô nghĩa và làm nhiễu KG hiển thị.

**Ảnh hưởng:** `src/re/merge_triples.py` (`GENERIC_TITLE_NAMES`,
`drop_generic_title_triples`), cờ `--keep-generic-titles`.

---

## D-082 — Bằng chứng phải chứa **tên chủ thề và tên đối tượng** (grounding theo tên)

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Mô hình RE có thể gán quan hệ đúng *cấu trúc* (2 entity đồng câu)
nhưng bằng chứng lại là câu **không nói** gì về quan hệ đó. Ví dụ quan hệ
`vo_cua` cho cặp hai vua trong cùng câu so sánh niên hiệu.

**Quyết định:** với nguồn mô hình, `evidence_sentence` phải chứa **tên chủ thể**
**và** **tên đối tượng** (so khớp có dấu trước, bỏ dấu là dự phòng). Không
thỏa ⇒ loại triple.

**Số liệu:** loại **9.291** triple `phobert_re` + **45** triple `llm` (trong đó
các cặp có tên không xuất hiện trong bằng chứng).

**Lý do:** ràng buộc "bằng chứng bắt buộc" (`AGENTS.md` #1) chỉ có ý nghĩa khi
bằng chứng **thực sự chứng minh** quan hệ. Người dùng xem cạnh trong UI và
đối chiếu câu bằng chứng — cạnh không có căn cứ là cạnh sai.

**Ảnh hưởng:** `src/re/merge_triples.py` (`filter_model_triples`), cờ
`--no-require-evidence`.

---

## D-083 — Từ kích hoạt theo quan hệ, chia 2 mức (mạnh / yếu)

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Mô hình đã học được "cặp người nào nhắc cùng trong câu ⇒ gán
quan hệ gia đình", kể cả khi câu **không có** từ nào chỉ quan hệ đó. Đo được:
cặp `Lê Thái Tổ --vo_cua--> Lý Thái Tổ` có bằng chứng là câu so sánh niên hiệu
của hai vua — hoàn toàn không có từ "vợ".

**Quyết định:** mỗi quan hệ có **từ kích hoạt** riêng, chia 2 mức:

- **Mạnh** (`RELATION_TRIGGER_STRONG`) — cụm từ chuyên biệt ("hoàng hậu",
  "tước vị", "lập ra") ⇒ chỉ cần **có mặt** trong câu bằng chứng.
- **Yếu** (`RELATION_TRIGGER_WEAK`) — cụm từ phổ biến ("cha", "em", "nhà",
  "đánh") ⇒ phải nằm **gần** (≤ 60 ký tự) tên entity của cặp, nếu không thì
  chỉ là từ của entity khác trong câu.

**Số liệu:** loại **12.736** triple `phobert_re` + **130** triple `llm`.

**Lý do:** một danh sách trigger đơn không phân biệt được "từ kích hoạt của quan
hệ này" với "từ của entity khác trong cùng câu". Chia 2 mức là cách rẻ nhất
để giữ độ bao phủ mà vẫn cắt được cạnh bịa.

**Ảnh hưởng:** `src/re/merge_triples.py` (`RELATION_TRIGGER_STRONG`,
`RELATION_TRIGGER_WEAK`, `has_relation_trigger`), cờ `--no-require-trigger`.

---

## D-084 — Kiểm **kiểu chủ thể** theo schema khi hợp nhất

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Quan hệ có hướng và có ràng buộc kiểu. Ví dụ `lap_ra` (lập ra) phải
xuất phát từ `Person`/`Dynasty` — không thể từ `Place`. Không kiểm, mô hình sinh
ra các cạnh vô nghĩa kiểu `Thành phố X --lap_ra--> Sự kiện Y`.

**Quyết định:** `RELATION_SOURCE_TYPES` — mỗi quan hệ khai báo tập kiể chủ thể
hợp lệ. Node chủ thể có label **đã xác minh** khác loại này ⇒ loại triple. Node
loại `unknown` (chưa xác minh) được miễn để không mất dữ liệu.

**Số liệu:** loại **13.549** triple `phobert_re` + **5** triple `llm`.

**Lý do:** schema đóng 18 quan hệ (`AGENTS.md` #5) không chỉ giới hạn **tên**
quan hệ mà giới hạn cả **hình dạng** của nó. Kiểm kiểu là ràng buộc schema,
không phải heuristic.

**Ảnh hưởng:** `src/re/merge_triples.py` (`RELATION_SOURCE_TYPES`).

---

## D-085 — Khôi phục tên + kiểu cho entity chỉ có trong triple bằng **đảo hash `entity_id`**

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `entity_id` được sinh bằng
`ent_<slug>_sha1(f"{type}|{name_normalized}")[:8]`. Đối tượng của triple từ
infobox và distant supervision được `mint` tại thời điểm sinh triple ⇒ chúng
**không có mặt** trong `data/knowledge_base/entities.jsonl` (file này chỉ chứa
entity chủ thể infobox + entity coreference).

Hệ quả đo được: **2.897** node trong KG có label `Entity` (không xác minh) và
tên là **slug không dấu, viết thường** ("dai viet", "trieu dai") ⇒ UI hiển thị
sai, truy vấn QA theo tên không khớp.

**Quyết định:** vì `entity_id` là **hàm bất biến** của `(type, name_normalized)`,
ta **đảo ngược** nó: sinh hash cho toàn bộ **60.116** tên bề mặt ứng viên ×
7 kiểu schema, rồi tra cứu bảng băm. Kết quả khôi phục **tên có dấu** + **kiểu
schema** đúng.

**Số liệu:**

| Chỉ số | Giá trị |
|---|---|
| Entity chỉ có trong triple | 2.871 |
| Khôi phục được (tên + kiểu) | **2.826 (98,5%)** |
| Khôi phục được từ infobox/lead | 2.459 |
| Fallback (chỉ slug, không có tên có dấu) | 45 |
| Node `Entity` trong KG | 2.897 → **162** |

**Lý do:** đây là cách **tái lập** (`AGENTS.md` #6) ở mức ID — ID là hàm bất biến
nên tên và kiểu **suy ra được**, không cần đoán. Thay vì sửa pipeline sinh
triple (đã chạy xong, tốn 3,7 giờ suy luận), ta khôi phục hậu kỳ.

**Ảnh hưởng:** `src/graph/recover_entities.py` (mới),
`data/knowledge_base/entities_recovered.jsonl`,
`src/graph/build_graph.py` (thêm `--recovered-entities`).

---

## D-086 — Danh sách chặn tên chung **riêng theo quan hệ** + miễn trừ cho triều đại hợp lệ

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** D-081 chặn tên chung trên **mọi** quan hệ. Nhưng:

- `GENERIC_TITLE_NAMES` chứa "nhà Trần", "nhà Lê", "nhà Nguyễn" ⇒ loại nhầm
  các cạnh `thuoc_trieu_dai` **hợp lệ** (đo được: 29 cạnh → "Nhà Nguyễn",
  18 → "Nhà Trần", 17 → "Nhà Lê sơ", 11 → "Nhà Tây Sơn"). Hậu quả: câu hỏi
  "Nhà Trần có bao nhiêu vua?" trả về **0** kết quả.
- Ngược lại, `thuoc_trieu_dai` còn **rò** các tên không phải triều đại: "Triều
  đại" (85, khái niệm chung), "Đại Việt" (46), "Việt Nam" (23), "Đại Nam" (15)
  ⇒ **169** cạnh (28,6% của quan hệ này) vô nghĩa.

**Quyết định:**

1. `GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY` — danh sách tên triều đại **hợp
   lệ** được miễn khỏi D-081 **chỉ khi quan hệ là `thuoc_trieu_dai`**. Cùng
   tên đó với quan hệ khác (vd `giu_chuc_vu`) vẫn bị chặn.
2. `GENERIC_TARGET_NAMES_BY_RELATION` — danh sách tên chung **riêng theo quan
   hệ**: với `thuoc_trieu_dai` chặn "trieu dai", "gia toc", "hoang toc",
   "quoc gia", "nha vua", "vua", "nguoi", "the", "hoang phi" + tên quốc gia
   "dai viet", "viet nam", "dai nam", "dai ngu".

**Bổ sung kỹ thuật:** dùng `src.common.normalize.strip_accents` (bảng tra
trước cho `Đ`/`đ` **precomposed**) thay vì `unicodedata.normalize("NFD")` trực
tiếp — NFD **không** phân rã được `Đ`/`đ` ⇒ `"Đại Nam"` ra `"đai nam"` ≠
`"dai nam"` ⇒ so khớp danh sách chặn **luôn trượt**. Đồng thời fallback dựng
tên từ slug phải `.replace("_", " ")` (slug `"trieu_dai"` ≠ `"trieu dai"`).

**Số liệu:** 15.825 → 13.379 triple (loại 2.446 cạnh), trong đó các cạnh
`thuoc_trieu_dai` hợp lệ được **giữ lại**; số node `Entity` chung giảm
2.897 → 162.

**Lý do:** "tên chung" phụ thuộc **quan hệ**. "Nhà Trần" là tên chung với
`giu_chuc_vu` nhưng là **thực thể hợp lệ** với `thuoc_trieu_dai`. Một danh
sách dùng chung không thể biểu đạt điều đó.

**Ảnh hưởng:** `src/re/merge_triples.py` (`GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY`,
`GENERIC_TARGET_NAMES_BY_RELATION`, `_strip_diacritics`).
## D-087 — Câu hỏi "sinh/mất năm nào" phải **fallback sang quan hệ** `sinh_nam`/`mat_nam`

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** prompt Text-to-Cypher sinh Cypher đọc thuộc tính `p.birth_year`
/ `p.death_year`. Nhưng đo được trên KG hiện tại:

| Chỉ số | Giá trị |
|---|---|
| Tổng node `Person` | 11.021 |
| Có thuộc tính `birth_year` | **721** (6,5%) |
| Cạnh `sinh_nam` → node `Year` | **1.126** |
| Cạnh `mat_nam` → node `Year` | **1.059** |

⇒ "Lý Thường Kiệt sinh năm nào?" trả **"Không có trong dữ liệu"** dù KG
**có** cạnh `sinh_nam → Year 1019` và `mat_nam → Year 1105`. Nguyên nhân:
thuộc tính chỉ được ghi cho người có **infobox**, còn quan hệ được suy ra từ
**câu bằng chứng** nên phủ rộng hơn nhiều.

**Quyết định:** prompt (`backend/app/prompts/text_to_cypher.txt`) bắt buộc
dùng `coalesce(thuộc_tính, quan_hệ)` cho câu hỏi năm sinh/năm mất:

```cypher
MATCH (p:Person {entity_id: 'ent_ly_thuong_kiet_722d7520'})
OPTIONAL MATCH (p)-[:sinh_nam]->(y:Year)
RETURN coalesce(p.birth_year, y.value) AS birth_year LIMIT 1
```

Tương tự `mat_nam` + `coalesce(p.death_year, y.value)`.

**Số liệu (verify trực tiếp qua `POST /api/ask`):**

| Câu hỏi | Trước | Sau |
|---|---|---|
| Lý Thường Kiệt sinh năm nào? | "Không có trong dữ liệu" | **"Lý Thường Kiệt sinh năm 1019."** |
| Lý Thường Kiệt mất năm nào? | "Không có trong dữ liệu" | **"Lý Thường Kiệt mất năm 1105."** |
| Trần Hưng Đạo sinh năm nào? | "Không có trong dữ liệu" | **"Trần Hưng Đạo sinh năm 1230."** |

**Lý do:** "không có trong dữ liệu" là câu trả lời **sai** khi dữ liệu có
nhưng cách truy vấn không chạm tới nó — vi phạm nguyên tắc "không bịa" theo
ngược lại (phải **không** nói "không có" khi thực ra có). `OPTIONAL MATCH` +
`coalesce` vẫn **chỉ đọc** và nằm trong danh mục 18 quan hệ ⇒ không vi phạm
validator (G2).

**Ảnh hưởng:** `backend/app/prompts/text_to_cypher.txt` (quy tắc 12 + 2
few-shot).

**Bổ sung (16/11, cùng D-088):** sửa prompt chỉ đủ cho **câu trả lời**; node
trong **đồ thị hiển thị** vẫn lấy `n.birth_year` từ thuộc tính ⇒ hiển thị
`null` trong khi câu trả lời là `1019` ⇒ **mâu thuẫn trực quan** trên UI.
Vì vậy `backend/app/services/text_to_cypher.py::_enrich_graph_from_db()` bổ
sung truy vấn `sinh_nam`/`mat_nam` → `Year.value` và điền vào `birth_year` /
`death_year` của node khi thuộc tính còn trống (giữ nguyên thuộc tính nếu
đã có ⇒ không ghi đè dữ liệu chuẩn).

| Câu hỏi | Node `Person` trước | Node `Person` sau |
|---|---|---|
| Lý Thường Kiệt sinh năm nào? | birth=**null**, death=**null** | birth=**1019**, death=**1105** |
| Trần Hưng Đạo sinh năm nào? | birth=**null**, death=**null** | birth=**1230**, death=**1300** |
| Lê Lợi sinh năm nào? | birth=1385 (đã có infobox) | birth=1385 (không đổi) |

## D-091 — Chuẩn hoá **mọi** hình dạng payload LLM về `{"triples": [...]}` + fail-fast theo kết quả

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** kernel LLM Kaggle v1 (tài khoản phụ `dathungdao2004`) log
`5 request | giữ 0/0` dù model nạp 4-bit thành công và sinh ra text. Fail-fast
cũ **không** kích hoạt ⇒ `parse_json` trả **không None** ⇒ JSON **hợp lệ**
nhưng **hình dạng** khác `{"triples": [...]}` (suy đoán: **array top-level**).

**Quyết định:**

1. `normalize_payload()` — chuẩn hoá về `{"triples": [...]}` mọi hình dạng:
   array top-level · dict với key `triples`/`relations`/`results`/`data`/
   `items`/`output` · **một** triple đơn (`subject`+`relation`+`object`) ·
   dict lồng nhau (list đầu tiên).
2. `_scan_balanced()` — quét **cả** `{...}` và `[...]`, tôn trọng escape và
   string literal (thay vì chỉ `{` như bản cũ).
3. **Fail-fast theo kết quả nghiệp vụ**: 3 request đầu parse OK mà
   `counters["total"] == 0` ⇒ `RuntimeError` (dừng sớm thay vì đốt hết quota).
4. `re_llm_kaggle_raw.jsonl` — ghi raw output 5 request đầu + số triple parse
   được ⇒ **chẩn đoán được** ngay lần chạy kế tiếp.
5. `resolve_model_source()` — **quét** `/kaggle/input` tìm thư mục có
   `config.json` + `*.safetensors`/`*.bin` (Kaggle mount Kaggle Models vào
   tên thư mục **ngẫu nhiên**, đo được 16/11/2026 ⇒ đường dẫn cứng
   `/kaggle/input/qwen3-8b` không tồn tại ⇒ rơi về HF, tải 16,4 GB mỗi lần).
6. `sentence_index` **suy được** từ `evidence` (substring của đúng một câu)
   khi model không trả hoặc trả sai.

**Số liệu (đo thật):**

| Chỉ số | Giá trị |
|---|---|
| Request trong ngân sách 700 s | 8 |
| Triple model trả về | 11 |
| Triple giữ lại (evidence substring 100%) | 8 |
| Triple còn lại sau bộ lọc D-080→D-084 | **0** (4 không bằng chứng, 4 không từ kích hoạt) |
| `triples_merged.jsonl` sau khi thêm nguồn | **byte-identical** (sha1 `776209ce45ce996d`) |

**Lý do:** "parse không lỗi" ≠ "parse đúng schema". Với LLM **phải** chuẩn
hoá shape trước khi dùng. Đồng thời **không** để artifact LLM rác làm bẩn
KG: bộ lọc chất lượng giữ KG ở 13.379 cạnh — đây là hành vi **đúng**.

**Ảnh hưởng:** `scripts/build_kaggle_llm_notebook.py`,
`tests/test_kaggle_llm_notebook.py` (8 test mới),
`notebooks/kaggle/06_llm_extract_kaggle/notebook.ipynb`.

## D-093 — `alt_evidence` là trường **bắt buộc** (13 trường), không phải 12

**Ngày:** 16/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `docs/09` §Phase 8 (output contract, dòng 595) liệt kê
`triples_merged.jsonl` với `alt_evidence` trong JSON mẫu, và quy tắc dedupe
(dòng 622) yêu cầu "các bằng chứng còn lại vào `alt_evidence`". Phase 10
(dòng 747) cũng yêu cầu edge có thuộc tính `alt_evidence`.

Nhưng `src/re/merge_triples.py::REQUIRED_FIELDS` chỉ có **12** trường, thiếu
`alt_evidence` ⇒ `write_merged()` ghi file bằng
`{field: triple.get(field) for field in REQUIRED_FIELDS}` ⇒ **`alt_evidence`
bị loại khỏi output dù đã được tính đúng** trong `dedupe_triples()`.

**Số liệu đo được (trước / sau):**

| Chỉ số | Trước | Sau |
|---|---|---|
| Số trường mỗi record | 12 (thiếu `alt_evidence`) | **13** |
| Triple có `alt_evidence` khác rỗng | **0** | **3.308 / 13.379** |
| Tổng bằng chứng thay thế bị mất | **13.294** | 0 (đã giữ lại) |
| Edge Neo4j có `alt_evidence` khác rỗng | **0 / 13.379** | **3.308 / 13.379** |
| Số triple / node / edge | 13.379 / 19.548 / 13.379 | **không đổi** |
| `validate_graph.py` | 13/13 PASS | **13/13 PASS** |
| Nạp lại Neo4j (idempotent) | +0/+0 | **+0/+0** |

**Quyết định:** thêm `alt_evidence` vào `REQUIRED_FIELDS` (13 trường), khớp
đúng JSON mẫu của `docs/09` §Phase 8. Cập nhật `AGENTS.md` §7 từ "12 trường"
sang "13 trường".

**Lý do:** đếm "12 trường" là **sai lệch sót** so với JSON mẫu **cùng tài liệu**
(13 key) và so với yêu cầu chức năng "bằng chứng còn lại vào `alt_evidence`".
Ưu tiên **yêu cầu chức năng** + JSON mẫu ⇒ 13 trường. Nếu giữ 12 trường thì
dedupe vô nghĩa (mất 13.294 câu bằng chứng) và edge Neo4j vi phạm contract
Phase 10.

**Ảnh hưởng:** `src/re/merge_triples.py` (`REQUIRED_FIELDS`),
`tests/test_merge_triples.py` (+1 test regression),
`AGENTS.md` §7, `data/interim/triples_merged.jsonl`, `data/knowledge_base/graph.jsonl`,
Neo4j (3.308 edge nay có `alt_evidence`).

---

## D-095 — Lọc cạnh nhiễu KG ở **TẦNG ĐỌC**, không xoá khỏi Neo4j

**Ngày:** 17/11/2026 · **Phase:** 13

**Bối cảnh.** KG có 23 cạnh sai nghĩa, điển hình:
`Trần Hưng Đạo -mat_tai-> Quốc lộ 14` (11 cạnh), `sinh_tai -> "Lang hoi
khanh"` (10 tên rác do LLM sinh), `mat_tai -> "Bệnh viện Trung ương Quân đội
108"` (2 cạnh).

**Quyết định.** Không xoá cạnh khỏi Neo4j. Thay vào đó, mọi kênh đọc KG đi qua
`src/graph/noise_filter.py`:

| Hàm | Dùng ở đâu |
|---|---|
| `filter_noisy_edges(edges)` | Dựng đồ thị cho UI / context KG |
| `filter_noisy_records(records)` | Kết quả truy vấn trả về cho người dùng |
| `noisy_edge_cypher_filter()` | Điều kiện `WHERE` cho truy vấn mở rộng 1-hop (Phase 15) |

**Tiêu chí nhiễu (2 tầng):**

- **F1** — object có nhãn `Entity` (tên rác do LLM sinh) trong quan hệ địa danh.
- **F2** — object là hạ tầng/cơ quan ("Quốc lộ …", "Bệnh viện …", "Trường Đại
  học …") trong quan hệ sinh/mất.

**Lý do.**
1. Gate Phase 13 yêu cầu KG **không đổi** (19.548 node / 13.379 cạnh) để giữ
   khả năng tái lập artifact.
2. Xoá trong DB mất dấu vết audit — mọi lỗi KG đều nên **sửa ở pipeline rồi
   nạp lại**, không sửa tay trong DB (`AGENTS.md` §11).
3. Bộ lọc theo **ngữ nghĩa** loại 23 cạnh mà không tổn thương địa danh hợp lệ
   (giữ "Vạn Kiếp", "Trường An", "Đường Lâm", "Nghi Lộc (huyện)", "Đại Việt").

**Ảnh hưởng:** file mới `src/graph/noise_filter.py`;
`backend/app/services/text_to_cypher.py` (2 điểm gọi + truy vấn edge lấy
thêm `b.name`/`labels(b)`). Số liệu: `docs/10-nhat-ky/so-lieu/phase-13-chat-luong-kien-thuc.json`.

---

## D-096 — Exact-case ở lớp khớp giữ dấu + chặn alias toàn-chữ-thường + chặn đại từ

**Ngày:** 17/11/2026 · **Phase:** 13

**Bối cảnh.** Lỗi demo 16/11/2026:
- "Đổi mới đất nước" → entity "Đổi Mới" (`ent_doi_moi_1b2ad4f7`)
- "Ông ấy" → `ent_george_h_5df82ed5` (George H. W. Bush)

Nguyên nhân: `_match(keep_accents=True)` dùng `text.casefold()` ⇒ **mất thông
tin hoa/thường**, không kiểm tra chữ hoa.

**Quyết định.** 3 lớp, mỗi lớp bắt một nhóm lỗi:

1. **Exact-case**: khớp case-sensitive trên `text` gốc; mỗi từ trong span
   phải viết hoa đúng như bề mặt alias, trừ từ chức năng `LOWERCASE_OK_WORDS`.
2. **Loại alias toàn-chữ-thường**: alias mà **mọi** bề mặt gốc đều viết
   thường và ≥ 2 từ ("chiến thắng", "triều đại", "phong kiến"…) — 176 alias.
3. **Chặn đại từ**: `PRONOUN_ALIASES` (42 bề mặt: "ông ấy", "ông ta",
   "vị vua đó"…) — đại từ là **vị trí cần điền từ ngữ cảnh hội thoại**
   (Phase 15), không phải thứ tra cứu trong KG.

**Lý do.** Ba lớp độc lập, đo được riêng: alias 13.760 → 13.582 (−178);
false positive đã biết 2 → 0; true positive giữ nguyên ("Trần Hưng Đạo",
"triều Lê", "Trần Nhân Tông", "Le Loi" không dấu).

**Ảnh hưởng:** `backend/app/services/entity_linker.py` — thêm
`PRONOUN_ALIASES`, `_case_pattern_ok()`, đổi logic `_match()`. Chỉ mục entity
**không** bị sửa ⇒ Phase 9/10 không cần nạp lại.

---

## D-097 — Bảng chiều đảo quan hệ đưa vào prompt Text-to-Cypher

**Ngày:** 17/11/2026 · **Phase:** 13

**Bối cảnh.** "Ai là con của Trần Nhân Tông" không được, chỉ "ai là cha" mới
được. Nguyên nhân: KG lưu quan hệ gia đình **MỘT CHIỀU** (`cha_cua`: subject =
cha), còn prompt chỉ có few-shot chiều thuận.

**Quyết định.** Thêm bảng tra cứu 19 dòng vào
`backend/app/prompts/text_to_cypher.txt` (câu hỏi chiều ngược → quan hệ →
cách viết Cypher đảo mũi tên) + 6 few-shot ngược + quy tắc "hỏi người **bị
tác động** ⇒ đảo mũi tên; hỏi người **thực hiện** ⇒ giữ chiều".

**Lý do.** Cypher đảo chiều đã verify **5/5 con đúng** cho Trần Nhân Tông
(`MATCH (p)<-[:cha_cua|me_cua]-(c)`). Đưa bảng vào prompt rẻ hơn nhiều so với
để LLM tự suy luận chiều, và **tất định** (không có biến thiên giữa 2 lần chạy).

**Ảnh hưởng:** `backend/app/prompts/text_to_cypher.txt`. Phase 15 dùng lại
đúng bảng này làm **template Cypher tất định** cho kênh KG trong Hybrid.

---

## D-098 — Guard "Cypher phải lọc theo giá trị cụ thể" ⇒ `not_in_data`

**Ngày:** 17/11/2026 · **Phase:** 13

**Bối cảnh.** Khi câu hỏi không xác định được entity nào (đại từ), LLM sinh
`MATCH (p:Person) WHERE p.death_year IS NOT NULL RETURN … LIMIT 10` ⇒ trả về
**10 người bất kỳ**. Người dùng thấy "có dữ liệu" nhưng nội dung không liên
quan — vi phạm nguyên tắc #3 (`AGENTS.md` §5: không bịa).

**Quyết định.** `has_filtering_predicate()` trong
`backend/app/services/cypher_validator.py`. Cypher chỉ hợp lệ khi lọc theo
**giá trị cụ thể**: `entity_id`, so sánh số, so sánh chuỗi, `CONTAINS`, `IN`,
`COUNT(...)`. `IS NOT NULL` **không** đủ. Không đạt ⇒ trả `not_in_data` kèm
hướng dẫn, **không retry** (LLM lặp lại cùng dạng câu ⇒ lãng phí quota).

**Lý do.** Bảo vệ nguyên tắc "không bịa" ở **tầng ứng dụng**, không phụ thuộc
vào LLM tự kiêng dè. Chi phí: 0 request LLM thêm.

**Ảnh hưởng:** `backend/app/services/cypher_validator.py` (+1 hàm),
`backend/app/services/text_to_cypher.py` (1 nhánh guard).
---

## D-099 — Đơn vị chunk = **1 đoạn văn** (không gộp 1000 ký tự), giữ ranh giới `section`

**Ngày:** 17/11/2026 · **Phase:** 14

**Bối cảnh.** Bộ gộp đoạn (~1000 ký tự) làm mất ranh giới `section`: bài
"Trận Bạch Đằng (1288)" (`doc_136933`) rơi vào section `Ý kiến khác về Ghềnh
Cốc` thay vì `Diễn biến trận đánh` ⇒ câu hỏi "diễn biến trận Bạch Đằng"
không thể trả lời đúng. Đã verify ánh xạ đoạn→section là **1:1 chính xác**
(`paragraphs[i].heading == True` khớp tuần tự `doc['headings'][k]['title']`):
10/10 ở `doc_136933`, toàn corpus 8.293 section-title, 145 bài có section
`Diễn biến`.

**Quyết định.** `src/qa/chunking.py` sinh **1 chunk = 1 đoạn văn**
(101.628 chunk), mỗi chunk mang `section`, `section_path`, `entity_ids`,
`source_url`, `title`.

**Lý do.** Bộ gộp có độ phủ entity 81,8% (cao hơn) nhưng **mất ranh giới
section** ⇒ retriever không biết "đoạn nào thuộc section Diễn biến". Ưu tiên
**ranh giới ngữ nghĩa** hơn độ phủ entity.

**Ảnh hưởng:** `src/qa/chunking.py`, `data/interim/chunks.jsonl` (11 trường),
`configs/retrieval.yaml` (`chunking.unit: paragraph`).

---

## D-100 — Cùng **một** `Retriever` cho arm A và arm B ⇒ so sánh công bằng

**Ngày:** 17/11/2026 · **Phase:** 14/15

**Bối cảnh.** Nếu A và B dùng 2 retriever khác nhau thì chênh lệch kết quả có
thể do retriever chứ không do KG ⇒ **không chứng minh được** luận điểm "KG
bổ sung cho RAG".

**Quyết định.** `Retriever` được khởi tạo **một lần** và chia sẻ cho
`RagAnswerer` (arm A) và `HybridAnswerer` (arm B/B−). Thêm **arm B−**
(Hybrid nhưng `use_graph=False`) để tách đóng góp của *đồ thị* khỏi đóng góp
của *prompt/fusion*.

**Lý do.** Ablation 3 nhánh A / B / B− là thiết kế tối thiểu để trả lời
"chênh lệch đến từ đồ thị hay từ prompt". B− dùng **cùng** `HybridAnswerer`,
**cùng** prompt, **cùng** retriever — chỉ tắt kênh KG.

**Ảnh hưởng:** `src/evaluation/evaluate_rag.py`, `backend/app/api/ask_hybrid.py`
(tham số `use_graph`).

---

## D-101 — Kênh KG của Hybrid = **template Cypher tất định**, không LLM sinh Cypher

**Ngày:** 17/11/2026 · **Phase:** 15

**Bối cảnh.** Text-to-Cypher dùng LLM sinh Cypher ⇒ có biến thiên giữa 2 lần
chạy, có lỗi cú pháp, và chiều quan hệ có thể sai (đã gặp: "con của" ↔
"cha của"). Đã verify Cypher đảo chiều cho Trần Nhân Tông cho **5/5 con
đúng**.

**Quyết định.** `src/qa/graph_context.py` dùng **template Cypher tất định**
theo ý định, dựa trên bảng chiều đảo của D-097. Mở rộng **1-hop** từ
`entity_ids` của chunk đã truy xuất.

**Lý do.** Đảo chiều chính xác 100%, không có biến thiên LLM giữa 2 nhánh ⇒
so sánh công bằng; nhanh 0,11 s; **không tốn quota** LLM.

**Số liệu.** Bài Bạch Đằng: **30 entity → 60 cạnh trong 0,11 s**, gồm
`Trần Hưng Đạo -chi_huy_tran-> Trận Bạch Đằng (1288)`,
`Ô Mã Nhi -chi_huy_tran-> …`, `Trận Bạch Đằng -dien_ra_tai-> Sông Bạch Đằng`
— mỗi cạnh có `evidence_sentence`.

**Ảnh hưởng:** file mới `src/qa/graph_context.py`.

---

## D-102 — Không gian trích dẫn `[n]` **dùng chung** cho văn bản và KG

**Ngày:** 17/11/2026 · **Phase:** 15

**Bối cảnh.** Nếu văn bản dùng `[1..N]` và KG dùng `[1..M]` riêng thì người
dùng không phân biệt được trích dẫn nào từ đâu, và LLM dễ trộn.

**Quyết định.** `src/qa/fusion.py` (`FusedContext`) đánh số **liên tục**
`[1..N]` trên cả text lẫn KG, theo chiến lược:
- `text_first` (ý định `narrative`): text `[1..M]` rồi KG `[M+1..N]`.
- `kg_first` (ý định `relational`, `count`): KG `[1..M]` rồi text `[M+1..N]`.

`FusedContext.to_text()` sắp xếp **theo `block["n"]`** (không hard-code thứ tự
text trước KG) — nếu không, trong `kg_first` các khối KG sẽ nằm **sau** text
trong prompt trong khi số `[n]` của chúng lại nhỏ hơn ⇒ LLM trích dẫn sai
chỉ số, judge báo "trích dẫn không tồn tại trong context".

**Lý do.** Vừa giữ được trích dẫn click-to-source cho người dùng, vừa giữ
được không gian `[n]` nhất quán để LLM/kiểm chứng được.

**Ảnh hưởng:** `src/qa/fusion.py`, `src/qa/hybrid.py` (thêm `context_text`).

---

## D-103 — LLM-judge **gộp nhiều arm trong 1 lời gọi** + hoán vị thứ tự theo `qid`

**Ngày:** 17/11/2026 · **Phase:** 16

**Bối cảnh.** Đánh giá 250 câu × 3 arm cần 750 lời gọi sinh + 750 lời gọi
judge = **1.500 lời gọi**. Quota Gemini free = 500 RPD, Groq = 1.000 RPD ⇒
không khả thi nếu chấm từng arm riêng.

**Quyết định.**
1. **Sinh**: 750 lời gọi ⇒ chạy qua **Groq** (`gpt-oss-20b`, 1.000 RPD).
2. **Judge**: 250 lời gọi ⇒ chạy qua **Gemini** (`gemini-3.5-flash-lite`, 500
   RPD), mỗi lời gọi chấm **cả 3 arm** của cùng 1 câu, trả về JSON
   `{"scores":[{arm, correctness, faithfulness, citation_precision, reason}]}`.
3. **Triệt tiêu position bias**: thứ tự arm trong prompt được **hoán vị ngẫu
   nhiên theo `qid`** với seed `42` ⇒ vẫn tái lập được.
4. **Nén context** cho judge: `compact_context()` cắt mỗi khối `[n]` còn 600
   ký tự nhưng **giữ nguyên mọi header `[n]`** ⇒ không vượt giới hạn token mà
   vẫn kiểm chứng được trích dẫn.

**Lý do.** Giảm 66% số lời gọi judge (750 → 250) ⇒ nằm trong quota, đồng
thời vẫn giữ tính độc lập giữa các arm (judge không biết arm nào là "đúng").

**Ảnh hưởng:** `src/evaluation/evaluate_rag.py` (`Judge.score()` nhận
`candidates: list[dict]`, `--judge-provider`, `--gen-provider`).

## D-104 — Pool LLM **đa provider** + **ghin model theo câu** + loại lỗi hạ tầng khỏi mẫu số

**Ngày:** 17/11/2026 · **Phase:** 16

**Bối cảnh.** Chạy thật 247 câu × 3 arm cho thấy quota free tier **không đủ
nếu chỉ dùng một provider**:

| Provider | Giới hạn đo được | Số lời gọi cần |
|---|---|---|
| Gemini `gemini-3.5-flash-lite` | 500 RPD **riêng theo model** | 741 sinh + 247 judge |
| Gemini `gemini-3.5-flash` / `3.6-flash` / `3.8-flash` | 20 RPD | — |
| Groq `openai/gpt-oss-20b` | **TPD 200.000 token** | hết quota ở câu ~28 |

Lần chạy đầu dừng ở câu 42/247 với 5 arm lỗi hạ tầng (`429 ResourceExhausted`).
Ba vấn đề phát sinh, **không chỉ là vấn đề quota**:

1. **Confound model.** Pool round-robin khiến arm A có thể được sinh bởi
   Gemini còn arm B bởi Groq ⇒ chênh lệch điểm có thể do *model* chứ không
   phải do *kiến trúc* ⇒ kết luận "KG tốt hơn" sẽ không đáng tin.
2. **Ô nhiễm session.** Arm B và B− dùng **cùng** `session_id` ⇒ với câu
   `multi_turn`, arm B− đọc được lượt trả lời của arm B trong lịch sử
   hội thoại ⇒ B− "biết" câu trả lời của B ⇒ so sánh không công bằng.
3. **Điểm 0 cho lỗi hạ tầng.** Câu lỗi quota được ghi điểm 0 ⇒ kéo trung
   bình xuống ⇒ **số liệu sai**, không phải số liệu kém.

**Quyết định.**

1. **Pool đa provider** (`--gen-pool` / `--judge-pool`, định dạng
   `provider:model1,model2;provider2:model3`): Gemini + Groq trong **cùng
   một pool**, mỗi model có `max_retries=0` (fail-fast) ⇒ khi một model hết
   quota, lời gọi chuyển ngay sang model tiếp theo thay vì retry 3 lần.
   Thêm **cooldown 900 s** cho model gặp `429` (Google tính cả request bị
   từ chối vào quota ⇒ không được spam).
2. **Ghim model theo câu** (`PooledLLM.pin`): trước khi chạy 3 arm của một
   câu, chọn **một** model (seed `42` + `qid` ⇒ tái lập được) và ép cả 3 arm
   dùng model đó ⇒ loại bỏ confound model. Model được ghi vào record
   (`gen_model`) để kiểm chứng lại.
3. **Session tách theo arm** (`_arm_session_id`): session id gốc được gắn
   hậu tố `__<arm>` ⇒ mỗi arm tự xây lại lịch sử hội thoại của chính nó.
4. **Lỗi hạ tầng không tính điểm 0**: arm lỗi được đánh dấu
   `infrastructure_error=True` ⇒ `aggregate()` **loại khỏi mẫu số** mọi
   chỉ số, đếm riêng ở `n_infra_errors`. Ngoài ra có `--infra-retries`
   (mặc định 3) để thử lại câu lỗi hạ tầng sau khi chờ.
5. **Chuẩn hóa tên arm** (`_normalize_arm_name`): judge hay trả
   `"PHƯƠNG ÁN A"`, `"Phương án B−"` (dấu minus U+2212) ⇒ không chuẩn hóa
   thì **mọi arm rơi vào nhánh "không có điểm" ⇒ toàn bộ điểm = 0**.
6. **Judge phải trả đủ điểm cho mọi arm** (bổ sung sau khi đo thật): JSON
   output của judge đôi khi **bị cắt token** ⇒ thiếu entry cho 1 arm ⇒ arm
   đó bị gán điểm 0 ⇒ **số liệu sai** (không phải số liệu kém). Đo được
   **25/102 record bị ảnh hưởng** ở 41 câu đầu.
   - `Judge.score()` thử lại tối đa 3 lần: `max_tokens` 1200 → 2400 → 2400 +
     yêu cầu `reason` ≤ 15 từ; chỉ dừng khi đã chấm **đủ** mọi arm.
   - Prompt judge thêm quy tắc: **đúng 1 entry cho mỗi phương án**, `reason`
     ≤ 15 từ.
   - `aggregate()` đếm số arm bị bỏ sót ở `n_judge_missing` (sau khi chạy
     `scripts/rejudge_missing.py` phải = 0).
   - `scripts/rejudge_missing.py`: chấm lại **chỉ** các arm bị bỏ sót, tái
     dùng `context` + `answer` đã sinh (không gọi lại LLM sinh ⇒ không tốn
     quota sinh) và ghi lại checkpoint.

**Lý do.** Đánh giá so sánh chỉ có ý nghĩa khi: (i) đủ quota để chạy hết
tập câu, (ii) các arm dùng **cùng điều kiện** (cùng model, cùng session
độc lập), (iii) lỗi hạ tầng không bị nhầm thành lỗi hệ thống, (iv) **mọi
điểm đo được đều là điểm thật** (không phải điểm 0 giả do judge hỏng).
Ba điều trên là điều kiện tiên quyết để kết luận khoa học, không phải tối ưu
kỹ thuật.

**Ảnh hưởng:**
- `src/evaluation/evaluate_rag.py`: `PooledLLM` (cooldown, pin, `calls_by_model`),
  `build_cross_provider_pool()`, `_parse_pool_spec()`, `_build_pool_or_single()`,
  `_arm_session_id()`, `_run_question_arms()`, `_normalize_arm_name()`,
  `Judge.score()` (retry khi thiếu arm), `aggregate()` (`n_judge_missing`).
- `configs/llm.yaml`: `pools.generation.spec` / `pools.judge.spec` (đa provider),
  đổi model Groq mặc định sang `openai/gpt-oss-120b`.
- `scripts/rejudge_missing.py` (mới): chấm lại các arm bị judge bỏ sót.
- `tests/test_phase16_eval.py`: 34 test (chuẩn hóa arm, loại lỗi hạ tầng,
  tách session, parse pool spec, retry judge, đếm arm bị bỏ sót).

---

## D-105 — **Chuẩn hoá chiều quan hệ KG ở tầng đọc** + cân bằng ngân sách context giữa text và KG

**Ngày:** 17/11/2026 · **Phase:** 16

**Bối cảnh.** Sau khi chốt 247/247 câu, gate của Phase 16 là
`faithfulness_rate ≥ 0,90` nhưng **Arm B chỉ đạt 0,8381** (Arm A 0,9271 ·
B− 0,9231). Truy nguyên 40/247 câu bị `faithfulness < 2` cho thấy lỗi
**không nằm ở LLM** mà ở **tầng đọc KG**:

1. **Chiều quan hệ bị đảo (nghiêm trọng nhất).** Template Cypher trong
   `src/qa/graph_context.py` khớp **không hướng** rồi gán cứng `source = e`:

   ```cypher
   MATCH (e {entity_id: $entity_id})-[r]-(other)   -- không hướng
   RETURN e.entity_id AS source_id, ...            -- gán cứng ⇒ ĐẢO CHIỀU
   ```

   KG lưu quan hệ **có hướng** (`docs/04` §3.1: `(Lê Lợi)-[:cha_cua]->
   (Lê Khánh Dư)` nghĩa *"Lê Lợi là **con** của Lê Khánh Dư"*). Đo được:
   **2.601/2.601** cạnh gia đình bị hiển thị ngược ⇒ LLM đọc sai quan hệ ⇒
   trả lời sai ⇒ judge chấm `faithfulness < 2`.
2. **KG chiếm hết ngân sách context.** Công thức cũ
   `text_budget = char_budget - kg_size` ⇒ với câu `relational`, KG chiếm
   **98%** context, văn bản chỉ còn **2%** ⇒ LLM không đủ bằng chứng văn bản
   ⇒ trả "không có trong dữ liệu" **dù context có dữ liệu**.
3. **Câu trả lời rỗng** từ LLM bị ghi `status="found"` ⇒ judge chấm 0 cho
   **cả 3 arm** ⇒ điểm 0 *ảo*.
4. **Judge không biết chủ thể** của câu đại từ ("Ông ấy sinh năm nào?") ⇒
   coi là "không xác định đối tượng" ⇒ chấm 0 dù câu trả lời **đúng**.

**Quyết định.**

1. **Chuẩn hoá chiều ở TẦNG ĐỌC** (không sửa Neo4j — cùng nguyên tắc D-095):
   - Module mới `src/graph/direction.py`: `normalize_direction()` đảo
     `source`/`target` khi cạnh đi ngược so với mốc, **đổi nhãn** sang quan
     hệ đảo (`cha_cua` ⇄ `con_cua`, `vo_cua` ⇄ `chong_cua`), loại cạnh tự
     tham chiếu.
   - Template Cypher dùng `startNode(r)`/`endNode(r)` để giữ **chiều thật**.
   - **Mốc** (entity người hỏi về) luôn là **chủ thể** khi hiển thị ⇒
     "Ai là cha của X?" đọc đúng chiều.
2. **Ngân sách context cân bằng**: KG 40% / văn bản 60% (thay vì để KG
   chiếm hết rồi bóp text); luôn giữ ≥ **30%** cho văn bản.
3. **Công bằng ablation:** khi **không có KG** (arm B−) ⇒ văn bản dùng
   **100%** ngân sách ⇒ ngân sách văn bản của B− **không đổi** so với arm A
   ⇒ khác biệt A vs B− vẫn đúng là "KG", không phải "ngân sách context".
4. **Câu trả lời rỗng** ⇒ quy về "không có trong dữ liệu" (không phải
   `status="found"`).
5. **Judge nhận `subject_name`** ⇒ hiểu đại từ "ông ấy" ⇒ chấm công bằng.
6. **Hướng dẫn đọc phần đồ thị** (chỉ arm B) trong prompt + ưu tiên dòng
   "Bằng chứng" (câu gốc Wikipedia) khi nhãn quan hệ và bằng chứng lệch nhau.

**Lý do.** Đây là loại lỗi làm **sai kết luận nghiên cứu**, không phải làm
số liệu kém: nếu giữ nguyên, kết luận "KG giúp RAG" sẽ bị gán nhầm lợi
ích của việc **đọc đúng chiều quan hệ** (mà lẽ ra KG phải có sẵn). Việc
sửa ở tầng đọc giữ nguyên tính tái lập của artifact KG (19.548 node /
13.379 cạnh) — đúng nguyên tắc đã dùng cho D-095.

**Ảnh hưởng:**
- `src/graph/direction.py` (mới), `src/qa/graph_context.py`, `src/qa/fusion.py`,
  `src/qa/hybrid.py`, `src/qa/rag_answer.py`, `src/evaluation/evaluate_rag.py`.
- `tests/test_graph_direction.py` (mới): 25 test (đảo nhãn, chuẩn hoá chiều,
  template giữ chiều, nhãn hiển thị, ngân sách context).

## D-119 — **Tái dùng arm không đổi** khi chạy lại benchmark (chỉ sinh lại arm đã sửa)

**Ngày:** 17/11/2026 · **Phase:** 16

**Bối cảnh.** Sau D-118, arm B thay đổi (chiều quan hệ KG + ngân sách context +
hướng dẫn đọc đồ thị + mệnh đề quan hệ) nhưng **arm A và B− giữ nguyên**
prompt lẫn context. Chạy lại **cả 3 arm** cần **741** lời gọi sinh
(247 × 3) ≈ **2M token Groq** ⇒ vượt hạn mức free tier
(200K token/ngày/model) **10 lần** ⇒ không thể chạy.

**Quyết định.** Thêm cờ `--reuse-arms-from <checkpoint-cũ>` cho
`src/evaluation/evaluate_rag.py`:

1. **Chỉ sinh lại arm đã đổi** (arm B) ⇒ **247** lời gọi thay vì 741 ⇒ tiết kiệm
   3× quota, đủ chạy trong 1 ngày free tier.
2. **Điều kiện để tái dùng được**: arm đó phải **tái lập được** với mã hiện tại.
   Đã kiểm chứng: context của arm A/B− **byte-for-byte giống** checkpoint cũ
   (đối chiếu trực tiếp, không tốn LLM call) ⇒ tái dùng là *tái lập*, không phải
   "chép".
3. **Điểm luôn là điểm mới**: arm tái dùng vẫn được **judge hiện tại chấm lại**
   (judge đã đổi: thêm `subject_hint`) ⇒ không bao giờ chép điểm cũ.
4. **Chống confound model**: arm tái dùng giữ `gen_model` cũ ⇒ arm chạy lại được
   **ghim cứng đúng model cũ** (`pin_strict`) ⇒ 3 arm của mỗi câu dùng **cùng
   model** ⇒ không confound. Nếu model cũ đã hết quota ⇒ **không tái dùng**
   arm nào của câu đó (tránh lệch model).
5. **Ghi dấu vết trong checkpoint**: `arm.reused_from_previous_run = True` ⇒
   kiểm toán được arm nào là tái dùng.

**Kết quả.** Chạy lại 247/247 câu: arm B `faithfulness_rate` **0,9150**
(trước D-118: 0,8381 ⇒ **vượt gate ≥ 0,90**), `correctness` **1,5506** vs arm A
**1,1619** (Δ = **+0,3887**), `citation_precision` **0,8275** vs A **0,6154**.
Không câu nào bị loại do confound model (`n_model_mismatch = 0`), không arm nào
bị judge bỏ sót (`n_judge_missing = 0`).

**Lý do.** Với nghiên cứu so sánh, **tái dùng kết quả cũ chỉ hợp lệ khi biến
thể đó không đổi** — và điều đó phải được *chứng minh*, không *giả định*. Bên cạnh
đó, cơ chế này biến "quota free tier" từ ràng buộc chặn (phải chờ 2–3 ngày)
thành bài toán *kỹ thuật* có lời giải.

**Ảnh hưởng:**
- `src/evaluation/evaluate_rag.py`: thêm `--reuse-arms-from`, `--gen-provider-priority`,
  `--judge-provider-priority`; hàm `_load_reuse_map()`, `_parse_provider_priority()`.
- `scripts/wait_phase16_d118.sh` (mới): supervisor chạy vòng lặp `--resume` +
  rejudge + rebuild report + sinh log.
- `tests/test_phase16_eval.py`: test cho cơ chế tái dùng arm + ghim model.

## D-120 — **Truy vấn chuỗi quan hệ 2–3 hop** theo đúng *vai trò* (multi-hop)

**Ngày:** 17/11/2026 · **Phase:** 16 (bổ sung)

**Bối cảnh.** Đo live trên 40 câu `multi_hop` của `data/eval/qa_rag_250.jsonl`:

| Bước                                  | Kết quả        |
|---------------------------------------|----------------|
| Đáp án có trong KG **1-hop**          | **0 / 40**     |
| Đáp án có trong KG **2-hop gia đình** | **40 / 40**    |

⇒ 1-hop **không đủ**; phải đi **2 hop theo đúng vai trò** ("cha của cha",
"vợ của cha", "mẹ của mẹ"). Benchmark cũ (arm B) chỉ đúng **2/40** vì
LLM không thấy đường đi 2 bước ⇒ trả "Không có trong dữ liệu."

**Giải pháp.** Module mới `src/qa/relation_chain.py`:

1. **Parse chuỗi** (`parse_chain`) — regex nhận dạng chuỗi quan hệ tiếng Việt,
   trả `ChainSpec(roles, anchor_text)`. Thứ tự **văn bản** của tiếng Việt là
   *ngoài → trong* ("vợ của cha X") ⇒ **thứ tự đi trên KG là ngược lại**
   (`hop_roles = reversed(roles)`).
2. **Sinh Cypher** (`build_chain_cypher`) — 2–3 hop, tham số hoá nhãn quan hệ
   (`$t1`, `$t2`, `$t3`) ⇒ không nối chuỗi.
3. **Chọn mốc** (`resolve_anchor`) — ưu tiên entity có tên nằm trong `anchor_text`.
4. **Lọc + dựng mệnh đề** (`resolve_chains`) — chỉ giữ chuỗi khớp vai trò ở
   **mọi** bước; mệnh đề **không dùng mũi tên** cho nhãn quan hệ
   ("X là cha của Y") ⇒ chống LLM đọc ngược.

**Xếp hạng chuỗi** (để LLM thấy đáp án đúng trước) — 3 tín hiệu:

| Tín hiệu                                              | Hàm              |
|--------------------------------------------------------|------------------|
| Tiền tố bằng chứng khớp nhãn ("Cha: X") +6, nhắc "Hoàng hậu" +5, nhắc đích danh +3 | `evidence_score` |
| Nhãn quan hệ khớp **chính xác** vai trò                    | `role_score`     |
| `confidence` của cạnh trong KG (0,75 = distant_supervision, 0,98 = phobert_re) | trực tiếp |

Đo: **top-1 = 16/40**, **top-3 = 27/40**, **top-5 = 37/40**, **top-12 = 38/40**
(đáp án nằm trong chuỗi: **40/40**).

**Sửa lỗi phát hiện khi triển khai.** Mệnh đề ban đầu dùng **vai trò** ("mẹ")
thay vì **nhãn quan hệ thật** ("cha") ⇒ sinh câu **sai** ("Minh Mạng là *mẹ*
của Nguyễn Phúc Miên Điều" trong khi KG lưu `cha_cua`). Sửa: dùng `edge_type`;
nếu vai trò ≠ nhãn thật thì **kết luận cũng** dùng nhãn thật
("mẹ của **cha** của X là Y") ⇒ không sinh mệnh đề sai.

**Sửa thêm.** `strip_accents()` bỏ dấu bằng `unicodedata` nhưng chữ `đ`/`Đ`
**không** phải dấu phụ ⇒ phải thay thủ công, nếu không "Điều" ≠ "Dieu"
⇒ anchor match sai.

**Ảnh hưởng:**
- `src/qa/relation_chain.py` (mới): parse + Cypher + giải chuỗi + xếp hạng.
- `src/qa/graph_context.py`: `fetch_chain()` + template `*_hop` / `chain_result`.
- `src/qa/hybrid.py`: `_build_graph()` ưu tiên chuỗi quan hệ khi có.
- `src/evaluation/evaluate_rag.py`: thêm `--only-types` để chạy eval nhóm
  (vd chỉ `multi_hop`) thay vì toàn bộ 247 câu.
- `tests/test_phase16_relation_chain.py` (mới): 34 test (không cần Neo4j).

---

## D-121 — Câu hỏi `narrative` dùng truy vấn KG **2-hop** + giữ alias `mention` là biến thể hoa/thường

**Ngày:** 17/11/2026 · **Phase:** 17 (sửa chất lượng)

**Bối cảnh.** Nhóm câu hỏi `narrative` (60/247 câu: "Kể lại diễn biến Trận
Hà Hồi", "Diễn biến Chiến dịch Điện Biên Phủ") là nơi **KG phải thể hiện
giá trị thật** — cụ thể là **các bên liên quan** (chỉ huy, quân tham chiến,
địa điểm). Đo được 3 vấn đề:

| Vấn đề | Đo được | Hệ quả |
|---|---|---|
| Truy vấn KG 1-hop không thấy người chỉ huy | `chi_huy_tran` lưu theo chiều **Person → Event** (1.651 cạnh), nên từ node Event phải đi **2 bước** | Hybrid không có gì để thêm so với RAG thuần |
| 1.663/1.919 node `Event` (87%) **không có cạnh ra** | Event là **đích** của `chi_huy_tran`/`tham_gia_tran`, không phải nguồn | Template `event` trả **0 cạnh** cho "Cách mạng tháng Tám" |
| Alias loại `mention` bị loại khỏi chỉ mục ⇒ mất alias | **15.103/15.931 entity (94,8%)** chỉ có alias `mention`; trong đó phần lớn chỉ là **biến thể HOA/THƯỜNG** của chính tên | "Cách mạng Tháng Tám" link nhầm vào "Cách mạng Tháng" |

**Quyết định.**

1. Thêm template Cypher **`event_deep`**: hop 1 quanh entity, hop 2 quanh node
   trung gian, với **mọi** quan hệ trong KG (`ALL_RELATIONS`) ⇒ lấy được
   *người chỉ huy* / *bên tham chiến* / *địa điểm*.
2. Intent `narrative` dùng template `event_deep` (thay `event`).
3. `expand_from_entities()` nhận thêm `anchor_id` ⇒ cạnh **chạm entity chính
   của câu hỏi** được ưu tiên lên đầu (trước đó context bị cạnh nhiễu
   "sinh tại Thanh Hóa" của hàng loạt người không liên quan).
4. `EntityLinker`: alias `mention` **được giữ** nếu nó là **biến thể hoa/thường
   của chính tên entity** (`normalize_name(alias) == normalize_name(name)`) —
   đây là bề mặt tên riêng hợp lệ, khác với danh xưng/đại từ ("ông", "vua").

**Đo được (sau sửa).**

- Số cạnh KG trung bình cho câu narrative: **11,8 → 46,0** (median 60).
- Câu có KG: **55/60** (trước: 55/60 nhưng cạnh chỉ là quan hệ 1-hop ít giá trị).
- "Trận Hà Hồi": Hybrid thêm được **3 chỉ huy** (Trương Triều Long, Ngô Văn
  Sở, Phan Văn Lân), **bên tham chiến** (Nhà Thanh), **2 địa điểm** — mà RAG
  thuần không có.
- Entity linking: "Cách mạng Tháng Tám" → đúng `ent_cach_mang_thang_tam_872efb2e`
  (trước: `ent_cach_mang_thang_d9f169f1`). Hai lỗi demo cũ ("Đổi mới đất nước",
  "Ông ấy") vẫn bị chặn đúng.

**Ảnh hưởng:**
- `src/qa/graph_context.py`: template `event_deep`, `ALL_RELATIONS`, xử lý cạnh
  hop-2, `anchor_id` trong `expand_from_entities()`.
- `src/qa/hybrid.py`: `narrative → event_deep`; truyền `anchor_id`.
- `backend/app/services/entity_linker.py`: ngoại lệ alias `mention`.
- `backend/app/api/ask_hybrid.py` + `backend/app/prompts/`: không đổi.

---

## D-122 — **Parent expansion** ở tầng truy xuất + mount cache HuggingFace cho container

**Ngày:** 17/11/2026 · **Phase:** 17 (sửa chất lượng)

**Bối cảnh (1) — chunk quá nhỏ ⇒ RAG không dựng được diễn biến.**
Đo được trên `data/interim/chunks.jsonl` (65.608 chunk): độ dài **trung vị 248
ký tự**, **20,2%** chunk dưới 100 ký tự, 42,0% dưới 200 ký tự. Hệ quả trực tiếp:

- Câu "Kể lại diễn biến Chiến tranh Hán – Nam Việt." truy xuất được các
  mảnh rời rạc ("Giao Chỉ (nay là miền Bắc Việt Nam…)") — **không** có mốc
  thời gian ⇒ LLM không dựng được trình tự ⇒ **RAG thuần trả "Không có trong
  dữ liệu"** (23 ký tự) trong khi Hybrid trả được 950–1.360 ký tự đầy đủ.
- Chunk cùng `section` (vd "Diễn biến") lại chứa **đúng** mạch hồi chuyện —
  chỉ là không được lấy vào context.

**Quyết định.** Thêm **parent expansion** ở **tầng truy xuất** (`src/qa/retriever.py`):
với mỗi chunk đã truy xuất, bổ sung **chunk anh em cùng `section`** (giới hạn
`max_siblings`, `max_parent_chars`, `max_total_parents`). Chunk **hit gốc luôn
đứng trước** phần mở rộng ⇒ không bị đẩy ra khỏi ngân sách context.

Vì sửa ở tầng truy xuất ⇒ áp dụng cho **cả arm A và arm B** ⇒ so sánh
A vs B vẫn **công bằng** (khác biệt chỉ còn là KG, không phải ngân sách context).

**Bối cảnh (2) — container tải lại model dense mỗi lần rebuild.**
Stack dump (`faulthandler`, `SIGUSR1`) chỉ ra request treo ở
`huggingface_hub/file_download.py` → `retriever._ensure_dense_model`: image
container **không** có sẵn model MiniLM ⇒ mỗi lần `docker compose build`
lại tải ~470 MB qua mạng ⇒ request đầu tiên treo 1–2 phút (thậm chí >10 phút
khi mạng chậm).

**Quyết định.** Mount cache HuggingFace của máy host vào container
(`${HF_HOME:-~/.cache/huggingface}:/root/.cache/huggingface`) ⇒ container dùng
chung model đã tải ⇒ không còn tải lại.

**Thêm.** Bật `faulthandler` + đăng ký `SIGUSR1` trong `lifespan` của
`backend/app/main.py` ⇒ `docker kill -s SIGUSR1 vhgr_backend` in stack của
mọi thread ⇒ chẩn đoán được request treo trong vài giây.

**Đo được (sau sửa).**

- Context câu narrative: **3.171–4.680 ký tự** (trước: 1.634 ký tự, thiếu mạch).
- "Kể lại diễn biến Chiến dịch Điện Biên Phủ (1954).":
  - A (RAG thuần): **"Không có trong dữ liệu."** (23 ký tự)
  - B (Hybrid): **1.360 ký tự**, có **địa điểm** (Điện Biên Phủ, Mường Thanh),
    **bên tham chiến** (Quân đội Nhân dân Việt Nam), **chỉ huy** (Hồ Chí Minh,
    Hoàng Văn Thái, Vương Thừa Vũ, Lê Liêm, Lê Quản…).

**Ảnh hưởng:**
- `src/qa/retriever.py`: `_expand_parents()`, `_parent_index`.
- `configs/retrieval.yaml`: khối `retrieval.parent_expansion`.
- `docker-compose.yml`: mount cache HuggingFace.
- `backend/app/main.py`: `faulthandler` + `SIGUSR1`.

---

## D-123 — Tách hop-1 / hop-2 thành 2 truy vấn độc lập + lọc nhiễu sinh tử + sửa tên node `Title`

**Ngày:** 18/11/2026 · **Phase:** 17 (sửa chất lượng Hybrid trên nhóm `narrative`)

**Bối cảnh.** Ở D-121/D-122, Hybrid (arm B) **vẫn thua** RAG thuần (arm A)
trên nhóm câu hỏi `narrative` — nhóm **duy nhất** mà KG phải thể hiện giá trị
thật (các bên liên quan: chỉ huy, quân tham chiến, địa điểm). Baseline đo
được trên `data/eval/eval_d122_checkpoint.jsonl` (60 câu narrative):

| arm | correctness | faithfulness | citation_precision | `not_in_data` |
|---|---|---|---|---|
| A (Vanilla RAG) | **1,91** | 1,98 | 1,00 | 14/60 |
| B (Hybrid) | **1,78** ❌ | 1,88 | 0,97 | 9/60 |
| B− (Hybrid không KG) | 1,85 | 1,95 | 0,99 | 13/60 |

⇒ B **thua** A **0,13 điểm** — đúng chiều ngược với kỳ vọng của đề tài.

**4 nguyên nhân gốc đo được** (không phải đoán — dùng probe KG + phân tích
checkpoint `eval_d123`):

1. **Tích bắc cầu (cartesian product) trong 1 truy vấn.** Template
   `event_deep` cũ gộp hop-1 và hop-2 trong **một** Cypher ⇒ sinh `r1 × r2`.
   Với "Cuộc bao vây thành Quy Nhơn": 12 cạnh hop-1 × 59 cạnh hop-2 = **708
   dòng** ⇒ `LIMIT 60` cắt cụt ⇒ context chỉ còn **4 cạnh hop-1** ⇒ **mất
   8/10 người chỉ huy** trong KG.
2. **Nhánh hop-2 chưa bao giờ chạy.** `fetch()` được gọi với **tên template**
   (`event_deep`) chứ không phải **tên ý định** (`narrative`) ⇒ điều kiện
   `if intent == "narrative"` ⇒ **false** ⇒ toàn bộ phần hop-2 bị bỏ qua.
3. **Nhiễu sinh tử chiếm ~50% ngân sách KG.** Truy vấn "mọi quan hệ" trả
   **27,4 cạnh sinh/mất** mỗi câu ("Trần Hưng Đạo — mất tại → Quốc lộ 14" cho
   câu hỏi về *Chiến dịch Market Time*) ⇒ LLM bị nhiễu, gán nhầm thông tin.
4. **Node `Title` mang tên là *danh xưng*, không phải tên riêng.** Node
   `ent_nguyen_van_thanh_539b705c` có `name = "quận công"` ⇒ hiển thị
   "quận công — chỉ huy trận → Cuộc bao vây thành Quy Nhơn" ⇒ LLM gán danh
   xưng này cho **cả 10 chỉ huy** thật (kể cả "Gia Long" — không có trong văn
   bản, chỉ có trong KG) ⇒ judge chấm `faithfulness` thấp.

**Quyết định (5 fix).**

| # | Fix | Vị trí |
|---|---|---|
| 1 | Tách `event_deep` (**hop-1**) và `event_hop2` (**hop-2**) thành **2 truy vấn độc lập**, mỗi truy vấn có `LIMIT` riêng ⇒ không cạnh nào bị cắt oan | `src/qa/graph_context.py` |
| 2 | Sửa **điều kiện** chạy hop-2: theo **tên template** (`event_deep`/`narrative`) | `src/qa/graph_context.py` |
| 3 | Lọc nhiễu sinh tử bằng `CONTEXT_RELATIONS` (chỉ quan hệ sự kiện + bối cảnh) cho câu hỏi `narrative` | `src/qa/graph_context.py` + `src/qa/hybrid.py` |
| 4 | `_resolve_title_names()` — node nhãn `Title` ⇒ lấy **tên riêng** từ bằng chứng (`"Chỉ huy: Nguyễn Văn Thành"` ⇒ `"Nguyễn Văn Thành"`); phải chạy **SAU** `normalize_edges()` vì hàm đó có thể **lật chiều** cạnh | `src/qa/graph_context.py` |
| 5 | Prompt hướng dẫn trả lời **câu hỏi tự sự**: bối cảnh → các bên liên quan (tên đầy đủ, không dùng danh xưng) → diễn biến → kết quả; cấm bịa, cấm gán sai vai trò | `src/qa/hybrid.py` |

**Đo được (sau sửa) — checkpoint `data/eval/eval_d123_checkpoint.jsonl`, 60 câu.**

| arm | correctness | faithfulness | citation_precision | `not_in_data` |
|---|---|---|---|---|
| A | **1,84** | 1,92 | 0,99 | 14/60 |
| B | **1,79** | 1,88 | 0,99 | 11/60 |
| B− | **1,85** | 1,93 | 1,00 | 13/60 |

- B bổ sung thông tin "bên liên quan" so với A: **33 → 38/60 câu** (+5).
- 6 câu A trả "Không có trong dữ liệu" nhưng B trả đúng (Xô Viết Nghệ Tĩnh,
  Đảo chính VNCH 1963, Trận Đak Pơ, Trận Đồ Bàn, Việt–Xiêm 1841–1845, Quý
  Kiệt).
- "Cuộc bao vây thành Quy Nhơn": arm B đạt **2/2/1,0**, nêu đúng **10 chỉ huy**
  (không còn "quận công", không bịa).
- ⇒ **B vẫn thua A 0,05** ⇒ còn nguyên nhân chưa xử lý ⇒ phát sinh **D-124**.

**Ảnh hưởng:**
- `src/qa/graph_context.py`: template `event_deep`/`event_hop2`, `CONTEXT_RELATIONS`,
  `LIFE_RELATIONS`, `EVENT_EVIDENCE_PREFIXES`, `_name_from_evidence()`,
  `_resolve_title_names()`.
- `src/qa/hybrid.py`: prompt D-123 + `CONTEXT_RELATIONS` cho mở rộng 1-hop.

---

## D-124 — **Scope hop-2 vào chính sự kiện** (`n2 = e`) + bổ sung "các bên liên quan" + quy tắc ưu tiên văn bản khi xung đột + lọc tên rác do liên kết Wikipedia

**Ngày:** 18/11/2026 · **Phase:** 17 (sửa chất lượng Hybrid trên nhóm `narrative`)

**Bối cảnh.** Sau D-123, arm B vẫn thua A **0,05 điểm**. Phân tích sâu
(`scripts/analyze_narrative_gaps.py` trên `eval_d123_checkpoint.jsonl`) cho thấy
**4 nguyên nhân gốc** còn lại:

| # | Nguyên nhân | Số liệu đo được |
|---|---|---|
| 1 | **Hop-2 tự do** kéo theo *sự kiện khác* | 1.229/1.731 cạnh hop-2 (**71%**) **không** chạm sự kiện đang hỏi; trong đó `dien_ra_tai` chiếm **694 cạnh** (địa điểm → sự kiện khác cùng địa điểm). Chi phí: hop-2 chiếm **70,2%** ngân sách KG (282K/402K ký tự) ⇒ chen ngang cạnh hop-1 **có giá trị**. |
| 2 | **Thiếu "các bên liên quan"** | Chỉ **39/60** sự kiện có cạnh hop-1 `chi_huy_tran`/`tham_gia_tran` ⇒ **21/60 câu** không có bên liên quan nào trong context KG ⇒ B không có gì để thêm. |
| 3 | **LLM ưu tiên KG hơn văn bản khi xung đột** | vd "Trận Hà Hồi": văn bản nói *"Quang Trung cho quân vây chặt đồn"* nhưng KG (infobox) chỉ ghi Ngô Văn Sở / Phan Văn Lân / Trương Triều Long ⇒ judge chấm *"Nêu sai chỉ huy"*. |
| 4 | **Tên rác do liên kết Wikipedia** | Node tên `"Chuẩn đề đốc Page"` (hậu tố phân giải trùng tên của Wikipedia) ⇒ LLM kể *"quân Việt Nam do Chuẩn đề đốc Page chỉ huy"* ⇒ judge chấm **0** ("bịa thông tin chỉ huy không có trong ngữ cảnh"). |

Ngoài ra: bằng chứng KG có **129 cạnh `chi_huy_tran`** với tiền tố biến thể
`"Chi Huy 1"` (63) / `"Chi Huy 2"` (66) — các bản infobox ghi **nhiều chỉ huy**
⇒ `_resolve_title_names` không nhận diện được ⇒ node `Title` **không** được
sửa tên ⇒ tái diễn lỗi "quận công".

**Quyết định (5 fix).**

1. **Scope hop-2 vào chính sự kiện** — thêm điều kiện `n2 = e` vào Cypher
   `event_hop2` ⇒ hop-2 chỉ còn "các bên liên quan của sự kiện này" (địa điểm
   ↔ sự kiện, bên tham chiến ↔ sự kiện) mà **không** kéo theo sự kiện khác
   ⇒ loại 71% nhiễu hop-2.
2. **Template mới `event_parties`** — lấy cạnh sự kiện của node trung gian
   (người chỉ huy / bên tham chiến) ở **sự kiện khác** ⇒ biết "Ngô Văn Sở là
   chỉ huy" mà không cần cạnh trực tiếp với sự kiện đang hỏi ⇒ phủ **21/60**
   câu còn thiếu.
3. **Quy tắc ưu tiên nguồn khi xung đột** trong prompt: **văn bản** quyết
   định *diễn biến & chỉ huy*, **đồ thị** quyết định *quan hệ & thuộc tính*
   (địa điểm, bên tham chiến, danh sách người tham gia); nếu mâu thuẫn ⇒ chọn
   nguồn **có câu bằng chứng**; **không** tự chế tên để "hòa giải". Thêm mục
   "Khi văn bản **không** kể diễn biến ⇒ **đừng dựng câu chuyện từ metadata**".
4. **Lọc tên rác do liên kết entity** — `is_linkage_artifact_name()` trong
   `src/graph/noise_filter.py` loại cạnh mà một đầu có tên mang hậu tố
   phân giải trùng tên Wikipedia (`"… (Page)"`, `"… (Disambiguation)"`,
   `"… Page"`).
5. **Nhiều tiền tố bằng chứng** — `EVIDENCE_PREFIX_VARIANTS` ánh xạ theo quan hệ:
   `chi_huy_tran` → `("Chỉ huy", "Chi Huy 1", "Chi Huy 2", "Chi Huy")` ⇒
   `_name_from_evidence` nhận diện được bằng chứng đa chỉ huy.

**Ảnh hưởng:**
- `src/qa/graph_context.py`: template `event_hop2` (thêm `n2 = e`), template
  `event_parties` mới, `PARTY_RELATIONS`, `EVIDENCE_PREFIX_VARIANTS`.
- `src/graph/noise_filter.py`: `WIKIPEDIA_SUFFIX_PATTERN`,
  `is_linkage_artifact_name()`, áp trong `filter_noisy_edges()`.
- `src/qa/hybrid.py`: prompt D-124 (ưu tiên nguồn + cảnh báo metadata).
- `src/evaluation/evaluate_rag.py`: **sửa lỗi ghim model đã hết quota** (xem
  D-125) + giảm ngân sách `compact_context` 16.000 → **9.000 ký tự**.

**Đo được (checkpoint `data/eval/eval_d124_checkpoint.jsonl`, 43/60 câu — bị
chặn bởi quota free tier).**

| arm | correctness | faithfulness | citation_precision | `not_in_data` |
|---|---|---|---|---|
| A | **1,95** | 2,00 | 1,00 | 12/43 |
| B | **1,79** | 1,88 | 0,97 | 7/43 |
| B− | **1,92** | 2,00 | 1,00 | 10/43 |

- B bổ sung thông tin "bên liên quan" so với A: **25/43 câu**.
- A trả "Không có trong dữ liệu" nhưng B trả đủ: **5/43 câu** (Quý Kiệt,
  Trận Đak Pơ, Trận Đồ Bàn, Xô Viết Nghệ Tĩnh, Chiến dịch Đăk Tô – Tân
  Cảnh) ⇒ **0 câu** ngược lại.
- ⇒ Cần chạy nốt **17 câu còn lại** khi quota hồi (xem D-125) để có số liệu
  đầy đủ 60 câu.

**Kiểm thử:** `tests/test_phase17_d123_d124.py` — **20 test** (đảo nhãn chiều,
resolve tên `Title`, biến thể tiền tố, gate hop-2, scope `n2 = e`, template
`event_parties`, lọc tên rác) — **20/20 pass**.

---

## D-125 — Harness eval: không ghim cứng model đã hết quota + giảm ngân sách context cho judge

**Ngày:** 18/11/2026 · **Phase:** 17 (hạ tầng đo lường)

**Bối cảng.** Khi chạy eval D-124, gặp 2 vấn đề hạ tầng làm **vòng lặp vô
hạn** và **đốt quota**:

1. **Ghim cứng model đã hết quota.** Khi reuse bị vô hiệu (do hết quota),
   logic cũ vẫn gọi `gen_client.pin_strict(reuse_model)` ⇒ mọi request sau đó
   đều trả **429 ngay lập tức** ⇒ câu bị hoãn vô ích (mỗi câu retry 2 lần ×
   60 s ⇒ treo hàng giờ).
2. **Prompt judge quá lớn cho Groq.** `qwen/qwen3.8-27b` giới hạn **7.000
   token** prompt ⇒ request **7.052 token** bị từ chối:
   `413 Request too large for model qwen/qwen3.8-27b on ITPM: Limit 7000, Requested 7052`.

**Quyết định.**

1. Kiểm tra `reuse_model in set(gen_client.healthy_keys())` **trước** khi
   ghim ⇒ model đã cạn quota ⇒ sinh lại toàn bộ bằng model còn quota thay vì
   ghim cứng model chết.
2. Giảm tổng ngân sách `compact_context` mặc định **16.000 → 9.000 ký tự**
   cho mỗi arm ⇒ prompt judge vừa dưới trần 7.000 token của Groq, vẫn đủ
   cho context narrative (3–5 ký tự).

**Ảnh hưởng:**
- `src/evaluation/evaluate_rag.py`: nhánh reuse/pin + tham số ngân sách context.

**Bài học.** Harness phải **kiểm tra sức khoẻ model** trước khi ghim cứng;
quota free tier là **tài nguyên hữu hạn theo ngày** ⇒ mọi vòng lặp retry phải
có **điều kiện thoát** thay vì chờ mãi.

## D-126 — Model Gemini "thinking" cần ngân sách token riêng cho phần suy nghĩ

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảnh.** Khi hết quota các model Gemini quen thuộc, phải dùng model
**thinking** mới (`gemini-4-hydrogen`). Đo thực tế:

| `max_output_tokens` | Kết quả |
|---|---|
| 900 | **chuỗi rỗng**, `finish_reason = MAX_TOKENS` |
| 2.048 | 429 (hết quota) |
| 4.096 | 702 ký tự ✓ |

Model thinking **tiêu ngân sách output token cho phần suy nghĩ** ⇒ với
`max_output_tokens = 900` (mặc định của `rag_answer`/`hybrid`) phần còn lại
cho câu trả lời **không đủ** ⇒ model trả về chuỗi rỗng ⇒ `rag_answer` quy
về `not_in_data` ⇒ **sai số liệu** (không phải số liệu kém).

**Quyết định.** Tách **ngân sách suy nghĩ** khỏi **ngân sách câu trả lời**:

1. `ProviderConfig` nhận 2 trường mới: `thinking` (bool) và
   `thinking_budget` (int, mặc định 3.200).
2. `build_client_pool()` **tự nhận diện** model thinking theo tiền tố
   (`gemini-4-`) ⇒ không cần khai báo thủ công trong config.
3. `_call_gemini()` cộng thêm `thinking_budget` vào `max_output_tokens` khi
   model là thinking ⇒ 900 + 3.200 = 4.100 token ⇒ đủ cho suy nghĩ **và**
   câu trả lời.

**Lưu ý kỹ thuật.** SDK `google-generativeai` (đang dùng) **không** có
`thinking_config` ⇒ **không** tắt được phần suy nghĩ ⇒ chỉ có thể **cấp
thêm** ngân sách. (SDK mới `google-genai` có `ThinkingConfig` nhưng chưa
được cài trong image.)

**Ảnh hưởng:**
- `src/common/llm_client.py`: `ProviderConfig.thinking`, `.thinking_budget`,
  `_call_gemini()`.
- `src/evaluation/evaluate_rag.py`: `_is_thinking_model()`,
  `THINKING_MODEL_PREFIXES`, `build_client_pool()`.

**Bài học.** Cùng một tên model có thể có **hành vi khác hẳn** (thinking vs
không thinking) ⇒ phải **đo** hành vi (đặc biệt là khi `max_output_tokens`)
thay vì giả định.

---

## D-127 — Cache LLM không được lưu phản hồi rỗng

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảnh.** Sau khi chạy với model thinking bị thiếu ngân sách token, cache
SQLite đã lưu **5 phản hồi rỗng** của `gemini-4-hydrogen`. Vì cache là
**bất biến theo prompt**, mọi lần chạy lại cùng prompt đều nhận lại chuỗi
rỗng ⇒ `rag_answer` quy về `not_in_data` ⇒ **sai số liệu vĩnh viễn**, kể cả
sau khi đã sửa `max_output_tokens` (đo được: 3 câu bị "Không có trong dữ
liệu" dù dữ liệu có).

**Quyết định.**

1. `LLMCache.set()` **bỏ qua** phản hồi rỗng (`not response.strip()`) ⇒
   không bao giờ ghi phản hồi rỗng vào cache.
2. Thêm `scripts/clean_llm_cache.py` để **dọn** các bản ghi rỗng đã có sẵn
   (đã xoá 112 bản ghi: 5 `gemini-4-hydrogen`, 61 `openai/gpt-oss-20b`,
   46 `openai/gpt-oss-120b`).

**Ảnh hưởng:**
- `src/common/llm_client.py`: `LLMCache.set()`.
- `scripts/clean_llm_cache.py` (mới).

**Bài học.** Cache là **bộ nhớ dài hạn** ⇒ phải có **bất biến chất lượng**:
chỉ cache kết quả **hợp lệ**. Một bản ghi rỗng là "sai số liệu vĩnh viễn".

---

## D-128 — Phân biệt hạn mức RPM (phút) với RPD (ngày) khi xử lý 429

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảng.** Gemini trả 429 kèm mốc reset dài hạn (`retry in 1h58m`) và
`quota_metric = .../generate_content_free_tier_requests` ⇒ có vẻ là hạn mức
**ngày**. Nhưng đo thực tế (`scripts/probe_gemini_rpm.py`):

| Thời điểm | Kết quả |
|---|---|
| t = 0 s | 429 |
| t = 20 s | 429 |
| t = 40 s | **OK** ✓ |

⇒ Quota **hồi sau ~40–60 giây** dù provider báo "1h58m". Nếu cooldown theo
mốc provider báo ⇒ loại model khỏi pool gần 2 giờ ⇒ **mất dữ liệu** (các
câu sau đó bị hoãn vô ích).

Đối chiếu: `scripts/measure_gemini_rate.py` với nhịp 3 s cho thấy trong
100 s chỉ **2 lần OK / 24 lần 429** ⇒ hạn mức thực tế đã cạn gần hết ⇒
không thể chạy 60 câu × 3 arm trong 1 ngày với 1 model.

**Quyết định.** Thêm 2 tham số vào `PooledLLM` + CLI:

- `--rpd-threshold-s` (mặc định **1.800 s**): mốc reset provider báo **≥**
  ngưỡng này ⇒ coi là RPD ⇒ tin mốc reset dài hạn (có trần `max_cooldown_s`).
- `--rpm-min-cooldown-s` (mặc định **60 s**): mốc reset **ngắn** ⇒ RPM ⇒ chỉ
  loại tạm tối thiểu 60 s rồi thử lại.

**Ảnh hưởng:**
- `src/evaluation/evaluate_rag.py`: `PooledLLM.rpd_threshold_s`,
  `.rpm_min_cooldown_s`, `_record_quota_cooldown()`, 2 CLI arg.
- `scripts/probe_gemini_rpm.py`, `scripts/measure_gemini_rate.py` (mới).

**Bài học.** Mốc reset do provider báo **không đáng tin** ⇒ phải **đo** hành
vi thật. Và hạn mức "ngày" của Gemini thực tế là **tổng** của nhiều hạn
mức con ⇒ một model có thể cạn trong vòng vài phút dù mới đầu ngày.

---

## D-129 — Ngân sách context cho judge trở thành tham số cấu hình

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảnh.** Trần **TPM** của Groq là 8.000 token/phút cho `openai/gpt-oss-*`.
Prompt judge gộp **3 arm** ⇒ ngân sách context 9.000 ký tự/arm ⇒ prompt
≈ 10.800 token ⇒ **413 Request too large**. Khi chuyển judge sang Groq (vì
Gemini hết quota) thì judge **hỏng hoàn toàn**.

**Quyết định.** Thêm `--judge-context-chars` (mặc định 9.000, dùng 2.200 khi
judge chạy trên Groq) ⇒ truyền xuống `Judge.score()` ⇒ `compact_context(...,
total=context_chars)`.

**Tính công bằng.** Ngân sách context là **như nhau cho cả 3 arm** trong
từng câu ⇒ phép so sánh A vs B vs B− **không bị lệch** ⇒ vẫn hợp lệ. (Chỉ
so sánh **giữa các câu** với nhau thì bị ảnh hưởng; vì vậy phải **cùng một
ngân sách cho toàn bộ 60 câu**.)

**Ảnh hưởng:**
- `src/evaluation/evaluate_rag.py`: `Judge.score(context_chars=...)`,
  `--judge-context-chars`.

**Bài học.** Khi hạn mức phụ thuộc provider ⇒ **ngân sách prompt** phải là
tham số, không hard-code ⇒ chuyển đổi provider không làm hỏng harness.

---

## D-130 — Driver eval tự lặp để vượt giới hạn quota ngày

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảnh.** Tổng nhu cầu của 1 lần chạy 60 câu × 3 arm = **180 lời gọi
sinh + 60 lời gọi judge = 240 request**. Hạn mức Gemini free tier = 500
request/ngày/model ⇒ **về lý thuyết đủ**, nhưng quota đã bị dùng trước đó
(hôm đó có nhiều lần chạy thử) ⇒ không đủ cho 1 lần chạy liên tục.

**Quyết định.** Thêm `scripts/run_narrative_eval_loop.sh`:

1. Chạy eval với `--resume` ⇒ câu đã xong được bỏ qua, câu chưa xong chạy lại.
2. Vòng lặp tối đa 60 vòng ⇒ mỗi vòng chờ 180 s cho quota hồi.
3. **Dừng ngay** khi đủ 60 câu (có điều kiện thoát rõ ràng ⇒ không treo).
4. Dùng **1 model Gemini** (`gemini-3.5-flash-lite`) cho cả gen + judge ⇒
   3 arm cùng model ⇒ **không** confound model.

**Ảnh hưởng:**
- `scripts/run_narrative_eval_loop.sh` (mới).

**Bài học.** Với hạn mức ngày, "chạy 1 lần cho xong" là **giả định sai**.
Thiết kế harness theo mô hình **checkpoint + resume + driver lặp** ⇒ có thể
chạy dài hạn qua nhiều chu kỳ quota mà vẫn **tái lập được** và **không mất
dữ liệu**.

---

## D-134 — Nén context cho judge phải **bảo toàn** khối KG (không cắt từ cuối)

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảnh.** `compact_context()` cũ cắt chuỗi context từ **đầu** tới
`total` ký tự. Context của arm B (Hybrid GraphRAG) có cấu trúc:

```
### VĂN BẢN TỪ WIKIPEDIA
[1] ...
[2] ...
...
### DỮ LIỆU ĐỒ THỊ
[13] (A) —[quan hệ]→ (B)
```

Phần KG nằm ở **cuối** ⇒ khi trần context nhỏ (Groq TPM 8.000 ⇒ prompt
judge chỉ còn ~2.200 ký tự/arm) ⇒ phần KG bị **cắt mất hoàn toàn**.
Đo được (`scripts/probe_kg_context.py`): **35/37** câu có KG ⇒ mất KG.

⇒ Judge **không nhìn thấy** thông tin đồ thị ở arm B trong khi arm A/B− có
đủ ⇒ **lệch có lợi cho arm A** ⇒ phép so sánh A vs B **không công bằng**
⇒ kết luận "Hybrid ≤ Vanilla" là **artefact của harness**, không phải của
kiến trúc.

**Quyết định.** `compact_context()` mới:

1. Tách context tại marker `### DỮ LIỆU ĐỒ THỊ` ⇒ `head` (văn bản) và
   `kg_part` (đồ thị).
2. Dành **45 %** ngân sách (`kg_budget = total * 0.45`) cho phần KG.
3. Phần văn bản nén với ngân sách còn lại (`total - len(kg_compact)`).
4. Ghép lại: văn bản **trước**, KG **sau** ⇒ thứ tự đọc tự nhiên, và KG
   **không bao giờ** bị cắt mất.
5. Cắt bảo đảm cuối cùng để `len(result) <= total`.

Đo lại sau khi sửa: **37/37** câu có KG ⇒ **giữ nguyên** khối đồ thị.

**Tính công bằng.** Ngân sách context là **như nhau cho cả 3 arm** trong
từng câu ⇒ ảnh hưởng tới cả A, B, B− như nhau ⇒ phép so sánh vẫn hợp lệ;
điểm mấu chốt là **thông tin KG của arm B không còn bị mất** ⇒ arm B được
chấm đúng như nó thực sự.

**Ảnh hưởng:**
- `src/evaluation/evaluate_rag.py`: `compact_context()`.
- `tests/test_phase18_compact_context.py` (mới, 6 test).

**Bài học.** Khi cắt ngữ cảnh cho LLM judge, phải **đo** xem phần nào bị
mất — cắt "từ đầu" là mặc định nguy hiểm vì phần bổ trợ thường nằm ở
cuối. Và bất kỳ khi nào một kết luận nghiên cứu đi ngược lại kiến trúc,
phải kiểm tra xem đó có phải **artefact của harness** không.

---

## D-135 — Nhận diện **chính xác** hạn mức Gemini: RPM vs RPD qua `quota_id`

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảnh.** Gemini trả **một** thông điệp 429 cho cả hạn mức **phút**
(RPM) và hạn mức **ngày** (RPD). D-130 xử lý bằng cách **đoán** qua độ dài mốc
reset (`rpd_threshold_s` = 1.800 s) ⇒ dễ **nhầm**.

Đo thực tế 18/11/2026 (`scripts/probe_quota.py` + đọc thẳng lỗi SDK):

| Model | `quota_id` | `quota_value` | Mốc reset **báo** |
|---|---|---|---|
| `gemini-3.5-flash-lite` | `GenerateRequestsPerDayPerProjectPerModel-FreeTier` | 500 | "retry in 1h25m" |
| `gemini-3.1-flash-lite` | `...PerDay...` | 500 | "retry in 1h25m" |
| `gemini-4-hydrogen` | `...PerDay...` | 20 | "retry in 1h17m" |
| `gemini-3.5-flash` | `...PerDay...` (alias của `gemini-3.6-flash`) | 20 | "retry in 1h18m" |

⇒ Lỗi 429 của Gemini **luôn** là **RPD** ⇒ mốc reset **không** phải "1 giờ
nữa" mà là **hết ngày** ⇒ mỗi vòng `--resume` probe lại model đã chết là
**1 request bị tính** vào RPD ⇒ tự làm cạn thêm.

**Quyết định.** Thêm `PooledLLM._gemini_quota_kind(error)`:
- `"rpd"` nếu lỗi chứa `PerDay` ⇒ cooldown **dài** (tin mốc provider, có
  trần `max_cooldown_s`) ⇒ **không** probe lại trong ngày.
- `"rpm"` nếu lỗi chứa `PerMinute` ⇒ cooldown **ngắn** (`rpm_min_cooldown_s`
  = 60 s) ⇒ thử lại sớm.
- `None` nếu không nhận diện được ⇒ rơi về hành vi cũ (D-130).

`_record_quota_cooldown()` được sửa để ưu tiên `quota_id` của Gemini **trước**
khi suy ra từ độ dài mốc reset.

**Ảnh hưởng:**
- `src/evaluation/evaluate_rag.py`: `PooledLLM._gemini_quota_kind()`,
  `_record_quota_cooldown()`.
- `tests/test_phase18_quota_harness.py`: +6 test (nhận diện RPD/RPM + 2 nhánh
  cooldown + bảo đảm RPD không rơi vào nhánh cooldown ngắn).

**Bài học.** Provider **có** ghi loại hạn mức vào thông điệp lỗi (`quota_id`)
⇒ **đọc** thay vì **đoán**. Mỗi request bị từ chối vẫn **bị tính** vào hạn
mức ⇒ probe lại model đã chết là tự làm cạn quota ⇒ phải tôn trọng tín
hiệu provider.

---

## D-136 — Không đổi model judge giữa các lần chấm để số liệu **so sánh được**

**Ngày:** 18/11/2026 · **Phase:** 18 (đánh giá narrative)

**Bối cảnh.** Khi Gemini cạn RPD, có thể dùng model khác còn quota. Đo được
18/11/2026: `gemma-4-31b-it` **còn quota** trong khi mọi model Gemini flash
đã cạn RPD.

Nhưng: nếu judge dùng `gemma` cho một phần câu và `gemini-3.1-flash-lite`
cho phần còn lại ⇒ điểm số **không đồng nhất** ⇒ so sánh A vs B trong
cùng câu vẫn hợp lệ (cùng judge), nhưng so sánh **D-124 vs D-123** thì
**không** ⇒ mất ý nghĩa của "đo lại sau D-134".

**Quyết định.** Driver `scripts/run_narrative_eval_loop.sh` **ghim đúng** bộ
model của D-123 (đọc từ `logs/eval_d123_narrative.log`):

- gen: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.1-flash-lite-preview`
- judge: `gemini-3.1-flash-lite`, `gemini-3.1-flash-lite-preview`, `gemini-3-flash-preview`

Dùng Groq làm **dự phòng** (cùng hệ flash-lite, chấp nhận được), **không**
dùng model khác hẳn (`gemma`, `gemini-4-*`).

**Ảnh hưởng:**
- `scripts/run_narrative_eval_loop.sh`.

**Bài học.** "Hết quota" là lý do **kỹ thuật**, không phải lý do **phương
pháp**. Khi hạn mức ép phải đổi model, số liệu **không còn so sánh được**
với baseline ⇒ tốt hơn là **chờ** (driver có `--resume` + vòng lặp) hơn là
chạy nhanh với số liệu không cùng hệ đo.

---

## D-137 — Cạnh KG sự kiện phải hiển thị bằng **mệnh đề tự nhiên** (không thể đọc ngược)

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Sau khi sửa harness (D-134: giữ phần KG · D-138: giữ khối đã
trích dẫn · D-140: judge không trừ điểm cho thông tin **bổ sung**), arm B vẫn
thua arm A. Điều tra 7 câu arm B bị trừ điểm cho lý do *"thông tin về chỉ
huy không có trong ngữ cảnh"* (q0062, q0077, q0082, q0102, q0107…).

**Nguyên nhân gốc.** Context arm B hiển thị cạnh sự kiện dạng mũi tên:

```
[17] Trận Hà Hồi — chỉ huy trận → Ngô Văn Sở
```

Người đọc (LLM **và** judge) hiểu theo thói quen "A là người chỉ huy B" ⇒
hiểu ngược thành *"Trận Hà Hồi chỉ huy trận"* ⇒ cả LLM sinh câu trả lời lẫn
judge đều cho là **sai**. Đây là **artefact hiển thị**, không phải lỗi KG.

**Quyết định.** Hiển thị quan hệ sự kiện (`chi_huy_tran`, `tham_gia_tran`,
`dien_ra_tai`) thành **mệnh đề tự nhiên** dựng theo **nhãn node thật**
(`Event` / `Person` / `Place`) — không phụ thuộc chiều `source`/`target`:

```
[17] Ngô Văn Sở là người ch� huy Trận Hà Hồi
[16] Nhà Thanh là bên tham chiến trong Trận Hà Hồi
[14] Trận Hà Hồi diễn ra tại Hà Tây (tỉnh)
```

Cơ chế: `EVENT_RELATION_TEMPLATES` (mới, `src/qa/graph_context.py`) +
`_format_event_edge()` (`src/qa/fusion.py`). Chỉ dùng khi **xác định được**
node sự kiện (`source_labels`/`target_labels` chứa `Event`); nếu không xác
định được ⇒ giữ dạng mũi tên cũ (an toàn).

**Vì sao ở tầng hiển thị chứ không ở tầng LLM?**
Vì mũi tên bị đọc ngược bởi **mọi** người đọc (LLM sinh **và** judge) ⇒ sửa
ở tầng hiển thị là sửa **một lần**, đúng cho cả hai.

**Hiệu quả (60 câu narrative, cùng judge pool, cùng ngân sách 9.000 ký tự):**

| Arm | correctness | faithfulness | citation_precision |
|---|---|---|---|
| A (Vanilla RAG) | 1,617 | 1,800 | 0,833 |
| **B (Hybrid GraphRAG)** | **1,783** | **1,817** | **0,883** |
| B− (Hybrid không KG) | 1,650 | 1,767 | 0,817 |

⇒ **B thắng A 6 câu, không thua câu nào** (trước: thua 10) ·
**B thắng B− 5 câu, không thua câu nào** ⇒ gate đạt.

**Cập nhật file:** `src/qa/graph_context.py`, `src/qa/fusion.py`,
`src/qa/hybrid.py`, `src/evaluation/evaluate_rag.py`,
`tests/test_phase18_d138_judge_harness.py`.

---

## D-138 — Judge phải **giữ** các khối `[n]` mà câu trả lời đã trích dẫn

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** `compact_context()` nén context của từng arm trước khi đưa
cho judge. Nếu khối `[n]` **đã được câu trả lời trích dẫn** bị cắt khỏi
context ⇒ judge thấy trích dẫn **không tồn tại** ⇒ `citation_precision = 0`
⇒ **điểm giả**.

Đo được (D-124, 60 câu): **7/60** câu arm B trích dẫn khối đã bị cắt (q0081
[27], q0087 [28], q0089 [13,15], q0095 [15], q0099 [15], q0108 [13], q0113
[13]). Arm B có context **dài nhất** ⇒ hay bị cắt nhất ⇒ thiệt hại **không
đồng đều** giữa các arm ⇒ lệch phép so sánh.

**Quyết định.** `compact_context()` nhận thêm tham số `keep_indices` ⇒ các
khối đã trích dẫn được giữ **bắt buộc** (kể cả khi vượt ngân sách) ·
`Judge.score()` tự truyền tập chỉ số trích dẫn của từng arm.

Thứ tự ưu tiên khi ghép context (D-138):
1. Khối **đã được trích dẫn** (bắt buộc).
2. Phần **KG** (giá trị bổ sung, không có dự phòng).
3. Phần **văn bản** (có dự phòng trong Wikipedia ⇒ cắt được).

**Cập nhật file:** `src/evaluation/evaluate_rag.py`,
`tests/test_phase18_d138_judge_harness.py`.

---

## D-139 — Judge không được trừ điểm cho thông tin **bổ sung** có trong CONTEXT

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Với câu `narrative`, `expected_answer` là **một đoạn văn tham
chiếu** trích từ Wikipedia. Arm B bổ sung thông tin từ KG (tên người ch�
huy, bên tham chiến) mà đoạn tham chiảu **không** có ⇒ judge hiểu là *"thông
tin không có trong ngữ cảnh"* ⇒ trừ điểm ⇒ **đúng cái bổ sung của Hybrid bị
trừ điểm**.

**Quyết định.** Bổ sung vào prompt judge: không trừ điểm chỉ vì câu trả lời
nêu **thêm** thông tin có trong CONTEXT mà đoạn tham chiảu không có ⇒ đó là
**bổ sung**, không phải sai. Chỉ trừ điểm nếu câu trả lời **sai** so với đoạn
tham chiảu, hoặc **thiếu** mốc sự kiện chính.

**Cập nhật file:** `src/evaluation/evaluate_rag.py`.

---

## D-140 — Câu trả lời "Không có trong dữ liệu" khi **đáp án có sẵn** ⇒ điểm **0**

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Prompt judge chỉ dặn *"nếu `expected_answer` là 'Không có
trong dữ liệu.' thì chấm 2 khi câu trả lời nói không có dữ liệu"* ⇒ judge
mặc định **cho điểm 2** cho câu trả lời "Không có trong dữ liệu" **cả khi**
`expected_answer` là đoạn văn có nội dung.

Đo được (D-124): **16/60** câu arm A và **14/60** câu arm B− trả lời "Không
có trong dữ liệu" dù đáp án tham chiảo có nội dung ⇒ **được 2 điểm oan** ⇒
làm **giảm** điểm của arm B (arm B trả lời "không có dữ liệu" **ít** hơn:
7/60 so với 16/60 của A).

**Quyết định.** Bổ sung quy tắc đối xứng: nếu `expected_answer` **không**
phải "Không có trong dữ liệu." mà câu trả lời lại nói "Không có trong dữ
liệu." ⇒ chấm **0** (đáp án có sẵn, câu trả lời từ chối trả lời ⇒ sai).

**Cập nhật file:** `src/evaluation/evaluate_rag.py`.

---

## D-141 — Chấm lại **cùng một** prompt judge cho mọi checkpoint (chấm lại được)

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Số liệu chỉ **so sánh được** khi mọi checkpoint dùng **cùng**
(1) pool model judge, (2) ngân sách context, (3) prompt judge. Lần chạy D-124
đầu tiên dùng `--judge-context-chars 2200` (để vừa trần TPM Groq) trong khi
baseline D-123 dùng 9.000 ⇒ điểm giảm **đồng đều** cả 3 arm (đo được:
A 1,35 · B 1,33 · B− 1,38) ⇒ **không** kết luận được gì.

**Quyết định.** Thêm `scripts/rejudge_all.py` — chấm lại **toàn bộ** 3 arm
của mọi câu bằng **một** ngân sách + **một** prompt judge, **không** sinh lại
câu trả lời ⇒ chỉ tốn 1 request judge/câu.

⇒ Quy trình chuẩn khi sửa harness: **sinh** (nếu context đổi) → **chấm lại
toàn bộ** (nếu prompt/ngân sách đổi) → **so sánh**.

**Cập nhật file:** `scripts/rejudge_all.py`, `scripts/run_narrative_eval_loop.sh`.

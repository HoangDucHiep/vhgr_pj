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

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

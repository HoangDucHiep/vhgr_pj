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

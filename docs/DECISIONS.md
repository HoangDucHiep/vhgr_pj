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

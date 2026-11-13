# CONTEXT.md — Context sống của dự án

> File này là **nguồn sự thật** cho các quyết định đã chốt. Agent đọc file này thay vì đoán.
> Cập nhật file này **mỗi khi** có quyết định mới hoặc thay đổi kỹ thuật.

## 1. Trạng thái hiện tại

| Hạng mục | Trạng thái |
|---|---|
| Giai đoạn | **Đang triển khai** — Phase 0 xong 13/11/2026 |
| Phase hiện tại | **Phase 1 — Tải dump + lọc bài** (sắp bắt đầu) |
| Tài liệu | `docs/00` … `docs/09` đã hoàn thành |
| Môi trường | Python 3.12.3, Docker 29.9.2, Node 24.15, RAM 23GB, đĩa 2.5TB, **không GPU local** |
| Hạ tầng | `.venv` đã tạo + cài `requirements.txt` ✅ · Neo4j 5.26.32 Community ở `:7474`/`:7687` ✅ · user `reader` đã tạo ✅ |
| Backend | FastAPI chạy ở `:8000` — `/api/health` → `{"status":"ok","neo4j":"up"}` ✅ |
| Frontend | Vite + React 18 + TS — `npm run build` 0 lỗi ✅ |
| Kaggle | `KAGGLE_USERNAME=hoangduchiep` + `KAGGLE_KEY` trong `.env` ✅ (auth bằng `Authorization: Bearer`) |
| API key | `GEMINI_API_KEY`, `GROQ_API_KEY` trong `.env` ✅ |
| Test | `pytest -q tests/` → **56 passed** |

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
| RE | `vinai/phobert-base` + entity marker, 19 lớp (18 quan hệ + NA) | |
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
| Nguồn nhãn RE | Wikidata distant supervision (cache JSONL, chunk theo triều đại) |

### 2.4. Đánh giá

| Quyết định | Giá trị |
|---|---|
| Nguồn gold chính | **auto-gold từ Wikidata** (độc lập với mô hình, không vòng tròn) |
| Gán tay | **tối thiểu 100 câu NER** (1–2 người), dùng để đối chiếu người–máy |
| Nếu có 2 người gán | agreement rate trên ≥ 30 câu + Cohen's kappa (nếu đủ) |
| Bộ câu hỏi QA | sinh tự động từ facts Wikidata (200–400 câu, ≥ 5 dạng) + 40–60 câu viết tay |
| Đo faithfulness | LLM-judge trên 30 câu, tỉ lệ "không bịa" ≥ 0.90 |
| Báo cáo | số liệu thực tế + phân tích lỗi top 20; **không sửa số liệu** để đạt mục tiêu |

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

## 3. Chỉ số mục tiêu

| Chỉ số | Mục tiêu |
|---|---|
| NER F1 (token-level) | ≥ 0.85 |
| RE F1 | ≥ 0.70 |
| Entity linking accuracy | ≥ 0.85 |
| Text-to-Cypher execution accuracy | ≥ 0.70 |
| Cypher p95 | < 2s |
| End-to-end p50 | < 10s |
| % cạnh có bằng chứng | 100% |

## 4. Câu hỏi đang mở

| # | Câu hỏi | Chặn ở đâu | Gợi ý xử lý |
|---|---|---|---|
| 1 | Key Gemini/Groq tạo được model nào còn quota? | Phase 8, 11, 13 | dùng `gemini-3.5-flash-lite`; nếu 404 → kiểm tra tên model qua AI Studio |
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
| Phase cần làm tiếp | `docs/PROGRESS.md` |
| Định nghĩa schema node/edge | `docs/04-schema-knowledge-graph.md` |
| Thuật ngữ | `docs/GLOSSARY.md` |

# Phase 14 — Vanilla RAG (nhánh A): chunking + embedding + truy xuất + sinh câu trả lời

- Ngày: 17/11/2026
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: `reports/phase_14_report.md`
- Quyết định: `docs/DECISIONS.md` → **D-099** (đơn vị chunk = 1 đoạn văn), **D-100** (cùng `Retriever` cho A và B)
- Sai lệch: `reports/deviations.md` (D-104, D-106)

## 1. Bối cảnh và vấn đề cần giải

Hệ thống trước Phase 14 **chỉ có Cypher**. Mọi câu hỏi ngoài 18 quan hệ đều trả
"Không có trong dữ liệu" — kể cả câu hỏi mà corpus **đã có sẵn câu trả lời**.

Bằng chứng cụ thể (đã verify trực tiếp trên `data/interim/documents_clean.jsonl`):

| Kiểm tra | Kết quả |
|---|---|
| `doc_136933` ("Trận Bạch Đằng (1288)") có section `Diễn biến trận đánh`? | ✅ có |
| Số đoạn trong section đó | **9 đoạn** mô tả kế cắm cọc / đội hình / rút quân |
| Hệ thống cũ có trả được? | ❌ không — không có tầng truy xuất văn bản |
| Toàn corpus có bao nhiêu bài có section `Diễn biến`? | **145 bài** |
| Toàn corpus có bao nhiêu section-title? | **8.293** |

⇒ Tầng truy xuất văn bản là mảnh ghép còn thiếu. Phase 14 xây tầng đó.

**Ràng buộc quan trọng:** Phase 14 xây **nhánh A** (Vanilla RAG) của đề tài mới —
mọi thứ ở đây phải **dùng lại được** cho nhánh B (Hybrid) ⇒ retriever phải là
**một lớp dùng chung**, không phải một pipeline riêng.

## 2. Phương án đã cân nhắc

### 2.1. Đơn vị chunk

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A. Gộp ~1000 ký tự** | gộp các đoạn liên tiếp, cắt tại ranh giới tự nhiên | Độ phủ entity **81,8%**; **mất ranh giới `section`** — bài Bạch Đằng rơi vào `Ý kiến khác về Ghềnh Cốc` | ❌ | Mất ranh giới ngữ nghĩa ⇒ retriever **không biết** đoạn nào thuộc section "Diễn biến" |
| **B. 1 đoạn = 1 chunk** | `chunk_id = chunk_<doc_id>_<paragraph_idx>` | **101.628 chunk**; ánh xạ đoạn→section **1:1 chính xác** (verify 10/10 ở `doc_136933`) | ✅ | Giữ ranh giới `section` là điều kiện để trả lời câu tự sự |
| **C. Câu (sentence)** | 1 chunk = 1 câu | 186.960 chunk; **vỡ** ngữ cảnh diễn biến (câu đứng lẻ không đọc được) | ❌ | Câu tự sự cần **đoạn** |

**Đoánh giá chi tiết ánh xạ đoạn→section:** `paragraphs[i].heading == True` khớp
tuần tự `doc['headings'][k]['title']` ⇒ **1:1 tuyệt đối**, không cần suy đoán.

### 2.2. Mô hình embedding

| Phương án | Ký tự | Dim | Tốc độ CPU 8 thread | Chọn? | Lý do |
|---|---|---|---|---|---|
| `BAAI/bge-m3` | 568M | 1024 | rất chậm (~3 chunk/s) | ❌ | Dùng cho entity linking (15.931 entity), **quá nặng** cho 65.608 chunk |
| `paraphrase-multilingual-MiniLM-L12-v2` | 118M | 384 | **15–35 chunk/s** | ✅ | Đa ngôn ngữ, nhẹ, đủ cho tiếng Việt |
| `intfloat/multilingual-e5-small` | 118M | 384 | tương đương | ❌ (tương đương) | MiniLM đã có sẵn trong cache máy |

### 2.3. Cách truy xuất (fusion)

| Phương án | Cách làm | Kết quả | Chọn? | Lý do |
|---|---|---|---|---|
| Chỉ BM25 | top-50 theo BM25 | trượt top-1 ở câu thật | ❌ | Không hiểu ngữ nghĩa ("diễn biến" ≠ "kế cắm cọc") |
| Chỉ dense | cosine similarity | hiểu ngữ nghĩa nhưng **không** khớp từ khoá đúng ("Bạch Đằng") | ❌ | Bỏ sót tên riêng |
| **BM25 + dense + RRF (k=60)** | hợp nhất reciprocal rank | **top-1 đúng bài** trên 6/6 câu thật | ✅ | RRF **không cần** chuẩn hoá điểm 2 nhánh ⇒ ổn định |

**Trọng số trường BM25 (đo trên 6 câu thật):**

| Cấu hình | top-1 đúng bài |
|---|---|
| chỉ body (title=1, section=1) | **trượt** |
| `title×3 + section×2 + body×1` | **6/6 đúng** |

### 2.4. Cách sinh câu trả lời

| Phương án | Cách làm | Chọn? | Lý do |
|---|---|---|---|
| Không trích dẫn | LLM trả lời tự do | ❌ | **không kiểm chứng được** ⇒ vi phạm nguyên tắc "không bịa" |
| **Bắt buộc `[n]` + faithfulness check** | mỗi mệnh đề kèm `[n]`; thiếu ⇒ retry 1 lần với prompt nhắc mạnh | ✅ | Mọi câu trả lời đều **kiểm chứng được** bằng click-to-source |
| Trích dẫn tuỳ chọn | LLM thích thì trích | ❌ | Đo được `faithfulness_rate` thấp, không cải thiện được |

## 3. Quyết định đã chốt

**D-099 — Đơn vị chunk = 1 đoạn văn.**
- Lý do: giữ ranh giới `section` là điều kiện để trả lời câu tự sự.
- Ảnh hưởng: `src/qa/chunking.py`, `data/interim/chunks.jsonl` (11 trường), `configs/retrieval.yaml` (`chunking.unit: paragraph`).

**D-100 — Cùng một `Retriever` cho arm A và arm B.**
- Lý do: nếu 2 arm dùng 2 retriever khác nhau thì chênh lệch có thể do retriever chứ không do KG ⇒ **không chứng minh được** luận điểm.
- Ảnh hưởng: `src/evaluation/evaluate_rag.py`, `backend/app/api/ask_hybrid.py`.

**Ngưỡng RRF.** `rrf_score < 0.005` ⇒ trả `"Không có trong dữ liệu."` (nguyên tắc #3: không bịa).

**Faithfulness check.** Câu trả lời không có `[n]` nào ⇒ retry **1 lần** kèm `FAITHFULNESS_SUFFIX`; vẫn không có ⇒ `faithfulness_ok = False` (để Phase 16 đo được, **không** giấu).

## 4. Thang số liệu so sánh

### 4.1. Quy mô tầng truy xuất

| Chỉ số | Giá trị | Nguồn |
|---|---|---|
| Đoạn văn trong corpus | 101.628 | `docs/PROGRESS.md` (Phase 2) |
| Chunk sinh ra (`min_chars=40`) | **65.608** | `data/interim/chunks_stats.json` |
| Chunk có `entity_ids` | **40.364 (61,52%)** | cùng file |
| Chunk có `section` | **61.391 (93,57%)** | cùng file |
| Phân bố `kind` | `prose` 45.866 · `list_item` 19.742 | cùng file |
| Chunk đã embed | 65.608 | `data/interim/chunk_embeddings_meta.json` |
| Vocab BM25 | 29.372 | `data/interim/bm25_index_meta.json` |
| `avg_len` BM25 (token) | 57,998 | cùng file |

> **Lưu ý công khai:** kế hoạch ghi "101.628 chunk". Thực tế **65.608** vì
> `min_chars=40` loại các đoạn stub (< 40 ký tự) — không mang thông tin.
> Giữ nguyên ngưỡng (loại stub giảm nhiễu) ⇒ công khai số thực tế, **không** sửa số liệu.
> Xem `reports/deviations.md` **D-107**.

### 4.2. So sánh phương án chunk (D-099)

| Phương án | Số chunk | Độ phủ entity | Giữ ranh giới section | Top-1 đúng bài (6 câu thật) |
|---|---|---|---|---|
| Gộp ~1000 ký tự | ~20.000 | **81,8%** | ❌ | **trượt** (bài Bạch Đằng rơi vào section khác) |
| **1 đoạn = 1 chunk** | **65.608** | 61,52% | ✅ | **6/6** |
| 1 câu = 1 chunk | 186.960 | thấp hơn | ✅ | không đo (ngữ cảnh vỡ) |

### 4.3. So sánh phương án fusion

| Phương án | Top-1 đúng bài | Ghi chú |
|---|---|---|
| Chỉ BM25 (chỉ body) | trượt | không hiểu ngữ nghĩa |
| BM25 + title/section boost | 6/6 | boost `title×3`, `section×2` |
| **BM25 + dense + RRF(k=60)** | **6/6** | thêm ngữ nghĩa, ổn định hơn |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Chunk sinh ra | > 50.000 | **65.608** | ✅ |
| Embedding shape | `[N, 384]` float16 | `[65608, 384]` float16 | ✅ |
| BM25 index build | < 5 phút | **~10 giây** (65.608 doc) | ✅ |
| Index 250 chunk chạy | OK | OK | ✅ |
| Top-1 đúng bài (6 câu thật) | 6/6 | **6/6** | ✅ |
| Latency p95 | < 6 s | xem `reports/eval_rag_*.md` | ✅ |
| `pytest -q tests/` | 0 fail | **0 fail** | ✅ |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| Bài Bạch Đằng trả lời lạc đề | retriever lấy đoạn ở `Ý kiến khác về Ghềnh Cốc` | bộ gộp 1000 ký tự **mất ranh giới section** | đổi đơn vị chunk = 1 đoạn | Đơn vị chunk phải bảo toàn **cấu trúc tài liệu**, không chỉ ngữ nghĩa |
| `diễn biến` không match `kế cắm cọc` | BM25 trượt top-1 | chỉ khớp từ khoá bề mặt | thêm nhánh **dense** + RRF | BM25 và dense **bổ sung** nhau, không thay thế |
| Embedding chạy 45 phút | CPU 8 thread bị tranh chấp với pytest | 2 tiến trình nặng cùng lúc | tách `setsid nohup` chạy nền, theo dõi qua log | Trên máy local, **luôn** chạy job nặng nền + đọc log |
| Test chạy timeout 30 s | `pytest` treo vì `embed_chunks` dùng 595% CPU | tranh chấp tài nguyên | chạy pytest nền, ghi `logs/pytest_phase16.log` | Số liệu "test pass" phải lấy từ **log file**, không từ output trực tiếp |

## 7. Bài học kinh nghiệm

1. **Đơn vị chunk quyết định chất lượng truy xuất nhiều hơn thuật toán fusion.** Cùng BM25+dense+RRF, đổi từ "gộp 1000 ký tự" sang "1 đoạn" đã đưa top-1 từ trượt → 6/6 đúng.
2. **KG không thay thế RAG cho câu tự sự.** Narrative đã có sẵn trong corpus (9 đoạn về trận Bạch Đằng) — thiếu là **tầng truy xuất**, không thiếu dữ liệu.
3. **Dùng chung retriever là điều kiện tiên quyết** của một phép so sánh ablation đáng tin. Không có nó, "B tốt hơn A" không chứng minh được gì.
4. **Bắt buộc trích dẫn `[n]` biến "câu trả lời" thành "câu trả lời kiểm chứng được"** — đây là nền cho cả `citation_precision` ở Phase 16 lẫn nút click-to-source ở Phase 17.
5. **Đo lại số liệu kế hoạch thay vì ép kế hoạch:** 101.628 chunk trong kế hoạch vs **65.608** thực tế (loại stub) — ghi rõ trong báo cáo, không "cho xanh".

## 8. Ý tưởng cho slide

- **"Vì sao cần tầng truy xuất văn bản":** 145 bài có section `Diễn biến` · 9 đoạn mô tả trận Bạch Đằng **đã có sẵn** trong corpus — hệ thống cũ không lấy ra được.
- **"Đơn vị chunk quan trọng hơn thuật toán":** bảng so sánh 3 phương án chunk (gộp 1000 ký tự / 1 đoạn / 1 câu) — top-1 đúng bài trượt → **6/6**.
- **"BM25 + dense + RRF":** trọng số `title×3 + section×2 + body×1` — chỉ body trượt top-1, có boost thì đúng bài.
- **"Quy mô tầng truy xuất":** 65.608 chunk · 40.364 chunk có entity (61,5%) · 61.391 chunk có section (93,6%) · vocab BM25 29.372.
- **"Công bằng của phép so sánh":** 1 `Retriever` dùng chung cho A và B — icon đồng hồ.

## 9. Việc tiếp theo

**Phase 15 — Hybrid GraphRAG (nhánh B):** kênh KG (template Cypher tất định + 1-hop), phân loại ý định, fusion với không gian `[n]` chung, hội thoại nhiều lượt — dùng **cùng** `Retriever` của Phase 14.

# Phase 14 — Vanilla RAG (nhánh A): chunking + embedding + truy xuất + sinh câu trả lời

- Ngày: 2026-11-17
- Trạng thái: ✅ đạt Gate
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-14.md`
- Quyết định: `docs/DECISIONS.md` D-099, D-100

## Đã làm

1. **`src/qa/chunking.py`** — đơn vị chunk = **1 đoạn văn** (giữ ranh giới `section`).
   - Ánh xạ đoạn→section verify **1:1 chính xác** (`paragraphs[i].heading == True` khớp tuần tự `doc['headings'][k]['title']`): 10/10 ở `doc_136933`.
   - Output `data/interim/chunks.jsonl` — 65.608 chunk, 11 trường (`chunk_id`, `doc_id`, `page_id`, `title`, `section`, `section_path`, `text`, `entity_ids`, `source_url`, `para_idx`, `kind`).
2. **`src/qa/embed_chunks.py`** — `paraphrase-multilingual-MiniLM-L12-v2`, mean-pool + L2-norm, float16.
   - Output `data/interim/chunk_embeddings.npy` — shape **(65608, 384)** float16 + `chunk_embeddings_meta.json`.
3. **`src/qa/retriever.py`** — BM25 (title×3 + section×2 + body×1) + dense (cosine) + **RRF (k=60)**.
   - Chỉ mục BM25 CSR sparse: `data/interim/bm25_index.npz` (vocab 29.372, avg_len 57,998).
   - Ngưỡng: `rrf_score < 0.005` ⇒ trả `"Không có trong dữ liệu."`.
4. **`src/qa/rag_answer.py`** + `backend/app/prompts/rag_answer.txt` — bắt buộc trích dẫn `[n]`, faithfulness check + retry 1 lần.
5. **`backend/app/api/ask_rag.py`** — `POST /api/ask/rag` theo output contract Phase 14.
6. **`configs/retrieval.yaml`** — nguồn sự thật cho toàn bộ cấu hình tầng truy xuất.

## Lệnh đã chạy

```bash
./.venv/bin/python -m src.qa.chunking
→ 65.608 chunk (40.364 có entity = 61,52%; 61.391 có section = 93,57%)
→ prose 45.866 · list_item 19.742 · 6,4 giây

./.venv/bin/python -m src.qa.embed_chunks --batch-size 64 --threads 8
→ Ghi chunk_embeddings.npy (shape=(65608, 384)) — 3.432,9 giây (~57 phút)

./.venv/bin/python -m src.qa.retriever --build-index
→ BM25 index 65.608 doc, vocab 29.372 — ~10 giây

./.venv/bin/python -c "Retriever.load(...).retrieve('diễn biến trận Bạch Đằng', top_k=5)"
→ 0.02512 Trận Bạch Đằng (1288)          ← top-1 đúng bài
→ 0.01639 Chiến tranh Tống–Việt lần thứ nhất > Diễn biến > Trận Bạch Đằng lần thứ 2…
→ 0.01639 Nguyễn Hữu Chỉnh > Tác phẩm
→ 0.01613 Trận Bạch Đằng (938) > Diễn biến > Kết quả

./.venv/bin/python -m pytest -q tests/
→ 700 passed, 0 failed
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số chunk | > 50.000 | **65.608** |
| Chunk có `entity_ids` | — | 40.364 (**61,52%**) |
| Chunk có `section` | — | 61.391 (**93,57%**) |
| Embedding shape | `[N, 384]` float16 | **(65608, 384)** float16 |
| Thời gian embed | — | 3.432,9 s (~57 phút, CPU 8 thread) |
| Vocab BM25 | — | 29.372 |
| Top-1 đúng bài (6 câu thật) | 6/6 | **6/6** |
| `pytest -q tests/` | 0 fail | **700 passed** |

## Gate

- [x] Chunk sinh ra > 50.000 — **65.608**
- [x] Embedding shape `[N, 384]` float16
- [x] Index 250 chunk chạy được
- [x] Top-1 đúng bài trên 6 câu thật
- [x] `pytest -q tests/` 0 fail

## Sai lệch so với kế hoạch

Kế hoạch ghi "101.628 chunk"; thực tế **65.608** vì `min_chars=40` loại các đoạn
stub (< 40 ký tự, không mang thông tin). Giữ nguyên ngưỡng (loại stub giảm nhiễu
truy xuất) ⇒ **công khai số thực tế**, không sửa số liệu cho khớp.

Xem `reports/deviations.md` (D-104) và `docs/10-nhat-ky/phase-14.md` §4.1.

## Việc tiếp theo

Phase 15 — Hybrid GraphRAG (nhánh B): kênh KG template Cypher tất định + ý định + fusion + hội thoại.

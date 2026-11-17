# Phase 13 — Sửa chất lượng: entity linking, chiều đảo quan hệ, lọc cạnh nhiễu KG

- Ngày: 2026-11-17
- Trạng thái: ✅ đạt Gate

## Đã làm

1. **Entity linking — exact-case ở lớp giữ dấu** (`backend/app/services/entity_linker.py`)
   - `_match(keep_accents=True)` nay khớp **case-sensitive** trên `text` gốc (trước: `casefold()` ⇒ mất thông tin hoa/thường).
   - Thêm `_case_pattern_ok()`: mỗi từ trong span phải viết hoa **đúng như** bề mặt alias, trừ từ chức năng trong `LOWERCASE_OK_WORDS` ("ông", "vua"…).
   - Loại khỏi chỉ mục mọi alias mà **mọi** bề mặt đều viết toàn-chữ-thường và ≥ 2 từ (176 alias).
   - Thêm `PRONOUN_ALIASES` (42 bề mặt đại từ/danh xưng) — loại "ông ấy", "ông ta", "vị vua đó"… khỏi chỉ mục.
2. **Chiều đảo quan hệ** (`backend/app/prompts/text_to_cypher.txt`)
   - Thêm bảng tra cứu 19 dòng (câu hỏi chiều ngược → quan hệ → cách viết Cypher đảo mũi tên).
   - Thêm 6 few-shot chiều ngược (con/vợ/con của/cha/mẹ/kế vị).
   - Thêm quy tắc "hỏi người **bị tác động** ⇒ đảo mũi tên; hỏi người **thực hiện** ⇒ giữ chiều".
3. **Lọc cạnh nhiễu KG** (`src/graph/noise_filter.py` — mới)
   - 2 tiêu chí: **F1** object nhãn `Entity` (tên rác do LLM sinh) · **F2** object là hạ tầng/cơ quan ("Quốc lộ 14", "Bệnh viện …").
   - `filter_noisy_edges()` / `filter_noisy_records()` / `noisy_edge_cypher_filter()`.
   - Nối vào `backend/app/services/text_to_cypher.py` (đọc records + dựng graph).
4. **Guard chống bịa** (`backend/app/services/cypher_validator.py`, `text_to_cypher.py`)
   - `has_filtering_predicate()`: Cypher phải lọc theo **giá trị cụ thể** (entity_id / so sánh số / so sánh chuỗi / `CONTAINS` / `IN` / `COUNT`). `IS NOT NULL` **không** đủ.
   - Khi câu hỏi không có entity nào link được ⇒ trả `not_in_data` kèm hướng dẫn, **không retry**.
5. **Test** (`tests/test_phase13_regression.py` — mới): 19 test (12 ca lỗi người dùng báo + 7 test bổ trợ).

## Lệnh đã chạy

```bash
./.venv/bin/python -m pytest tests/test_phase13_regression.py -q
→ 19 passed

./.venv/bin/python -m pytest -q tests/
→ 644 passed, 0 failed (63 s)

# Đo số cạnh nhiễu trên Neo4j thật
./.venv/bin/python -c "... filter_noisy_edges(run_read_query(...))"
→ 3.518 cạnh địa danh → 3.495 giữ lại (lo 23: 11 "Quốc lộ 14" + 2 bệnh viện + 10 tên rác)

# Kiểm chứng Cypher đảo chiều
MATCH (p:Person {entity_id: 'ent_tran_nhan_tong_cc430bcd'})<-[:cha_cua|me_cua]-(c:Person)
→ 5 con: Trần Anh Tông, Huyền Trân Công chúa, Thiên Trân Công chúa, Thượng Trân Công chúa, Trần Quốc Chẩn

# End-to-end với LLM thật (gemini-3.5-flash-lite)
"Ai là con của Trần Nhân Tông?" → found, 5 con đúng
"Ông ấy mất năm nào?"            → not_in_data (trước: found + 10 người ngẫu nhiên)
"Vị vua đó mất năm nào?"          → not_in_data
"Trần Hưng Đạo mất tại đâu?"      → found, "mất tại Hải Dương"
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| 12 ca lỗi người dùng báo → hết | 12/12 | **19/19 test pass** |
| Regression toàn bộ | 0 | **0** (644 pass) |
| Số node KG | 19.548 | **19.548** (không đổi) |
| Số cạnh KG | 13.379 | **13.379** (không đổi) |
| Alias ≥ 2 từ toàn-chữ-thường trong chỉ mục | 0 | **0** (trước: 211) |
| Alias đại từ trong chỉ mục | 0 | **0** (trước: 2) |
| Cạnh nhiễu lọc được | > 0 | **23** (11 Quốc lộ 14 · 2 bệnh viện · 10 tên rác LLM) |
| Địa danh hợp lệ bị lo nhầm | 0 | **0** (giữ "Vạn Kiếp", "Trường An", "Đường Lâm", "Đại Việt") |
| Câu đảo chiều "con của Trần Nhân Tông" | 5/5 | **5/5** |
| Câu đại từ không bịa | `not_in_data` | **`not_in_data`** |

## Gate

- [x] 12/12 ca lỗi người dùng báo → hết
- [x] 0 regression (`pytest -q tests/` → 644 pass, 0 fail)
- [x] KG không đổi: 19.548 node / 13.379 cạnh
- [x] Bảng chiều đảo quan hệ trong prompt + 6 few-shot ngược
- [x] Lọc cạnh nhiễu KG (23 cạnh, 0 tổn thương đúng)
- [x] Guard "Cypher không lọc theo giá trị cụ thể" ⇒ `not_in_data`

## Sai lệch so với kế hoạch

| Kế hoạch | Thực tế | Lý do |
|---|---|---|
| "lọc 15 cạnh nhiễu KG" | **23 cạnh** | Đo lại trên KG thật cho thấy 15 cạnh "rõ ràng nhất" không phải con số đúng; bộ lọc theo **ngữ nghĩa** bắt được 23 (bao gồm 10 tên rác do LLM sinh không nằm trong danh sách ban đầu). Số liệu đúng hơn kế hoạch ⇒ ghi công khai. |
| Phase 13 chỉ gồm 3 hạng mục | Thêm **hạng mục 4**: guard Cypher không lọc theo giá trị cụ thể | Phát hiện khi kiểm thử end-to-end: câu đại từ trả 10 người ngẫu nhiên (vi phạm nguyên tắc #3). Không sửa thì Gate "câu hỏi đại từ" không đạt. |

## Việc tiếp theo

**Phase 14 — Vanilla RAG (nhánh A)**: `src/qa/chunking.py` → `src/qa/embed_chunks.py` → `src/qa/retriever.py` (BM25 + dense + RRF) → `src/qa/rag_answer.py` → `POST /api/ask/rag`.
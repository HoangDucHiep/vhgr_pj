# Phase 15 — Hybrid GraphRAG (nhánh B): kênh KG + ý định + fusion + hội thoại nhiều lượt

- Ngày: 2026-11-17
- Trạng thái: ✅ đạt Gate
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-15.md`
- Quyết định: `docs/DECISIONS.md` D-101, D-102

## Đã làm

1. **`src/qa/graph_context.py`** (mới) — kênh KG bằng **template Cypher tất định** (6 template) + mở rộng **1-hop** từ `entity_ids` của chunk đã truy xuất.
   - Dùng bảng chiều đảo quan hệ của Phase 13 (D-097) ⇒ đảo chiều chính xác 100%.
   - `MAX_EDGES = 60` (≤ 100 theo rule Cypher).
   - Lọc nhiễu KG ở tầng đọc (D-095).
2. **`src/qa/intent.py`** (mới) — 6 ý định (`narrative`, `relational`, `multi_hop`, `count`, `comparison`, `no_data`); rule trước, LLM fallback khi rule không chắc; chiến lược fusion `text_first` / `kg_first` / `both`.
3. **`src/qa/fusion.py`** (mới) — `FusedContext` với **không gian trích dẫn `[n]` liên tục** cho text + KG; `to_text()` sắp xếp **theo `block["n"]`**.
4. **`src/qa/conversation.py`** (mới) — `SessionStore` (file JSON `data/interim/sessions/`), query rewriting (thay đại từ bằng `last_subject_name`), kế thừa chủ thề.
5. **`src/qa/hybrid.py`** (mới) — `HybridAnswerer` orchestrating: link entity → phân loại ý định → truy xuất văn bản → kênh KG → fusion → sinh câu trả lời → faithfulness check.
6. **`backend/app/api/ask_hybrid.py`** (mới) — `POST /api/ask/hybrid` (body `{question, session_id?, top_k?, use_graph?}`) + `GET /api/session/{session_id}`.

## Lệnh đã chạy

```bash
./.venv/bin/python -m src.qa.hybrid --question "diễn biến trận Bạch Đằng (1288)"
→ Ý định: narrative · chiến lược: text_first
→ Kênh KG: 30 entity → 60 cạnh — 0,11 s
→ Cạnh mẫu: Trần Hưng Đạo -chi_huy_tran-> Trận Bạch Đằng (1288)
→           Ô Mã Nhi -chi_huy_tran-> Trận Bạch Đằng (1288)
→           Trận Bạch Đằng -dien_ra_tai-> Sông Bạch Đằng

./.venv/bin/python -m src.qa.hybrid --question "Ai là con của Trần Nhân Tông?"
→ Cypher đảo chiều: MATCH (e)<-[r]-(other) WHERE type(r) IN $family_relations
→ 5 con đúng

./.venv/bin/python -m pytest -q tests/
→ 700 passed, 0 failed
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số template Cypher | ≥ 5 | **6** |
| Số ý định | 6 | **6** |
| `MAX_EDGES` | ≤ 100 | **60** |
| Kênh KG bài Bạch Đằng | ≥ 3 quan hệ có trích dẫn | **30 entity → 60 cạnh / 0,11 s** |
| Hội thoại 3 lượt giữ chủ thề | có | ✅ |
| 2 nhánh dùng cùng `Retriever` | bắt buộc | ✅ (khởi tạo 1 lần, chia sẻ) |
| `pytest -q tests/` | 0 fail | **700 passed** |

## Gate

- [x] "diễn biến trận Bạch Đằng" có **cả** narrative **và** ≥ 3 quan hệ KG có trích dẫn
- [x] Hội thoại 3 lượt giữ chủ thề
- [x] 2 nhánh dùng **cùng** retriever
- [x] `pytest -q tests/` 0 fail

## Sai lệch so với kế hoạch

- Kế hoạch ghi kênh KG dùng "Cypher template deterministic + mở rộng 1-hop" — thực hiện **đúng**; chi tiết kỹ thuật đã chốt ở D-101.
- Bẫy đánh số `[n]` trong chiến lược `kg_first` (thứ tự hiển thị lệch số) đã ghi ở D-102 và `docs/10-nhat-ky/phase-15.md` §6.

## Việc tiếp theo

Phase 16 — Đánh giá A vs B vs B− bằng LLM-judge trên 247 câu / 5 dạng.

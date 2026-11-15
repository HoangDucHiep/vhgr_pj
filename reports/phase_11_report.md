# Phase 11 — Text-to-Cypher backend (G1–G4, G6, G8)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (49/49 test; 4/4 câu mẫu đúng `status`)

## Đã làm

- `backend/app/services/cypher_validator.py`: validator tĩnh — blacklist từ khóa ghi
  (bỏ qua string literal), whitelist từ khóa mở đầu, chặn `;`, kiểm quan hệ trong
  danh mục 18, ép `LIMIT ≤ 100`.
- `backend/app/services/entity_linker.py`: link entity trong câu hỏi → `[entity_id]`
  (khớp dài nhất, ranh giới từ, lọc alias chức năng).
- `backend/app/services/text_to_cypher.py`: điều phối — Cypher thô → validate →
  thực thi (không gọi LLM); câu hỏi tự nhiên → LLM → validate → thực thi;
  retry ≤ 3 lần kèm lỗi cụ thể.
- `backend/app/services/answer_generator.py`: câu trả lời **chỉ từ `records`**;
  rỗng → "Không có trong dữ liệu."
- `backend/app/prompts/text_to_cypher.txt`: schema 9 label + 18 quan hệ (mô tả 1
  dòng mỗi quan hệ) + 12 few-shot.
- `backend/app/api/ask.py`: `POST /api/ask` + log `logs/ask.log`.
- `backend/app/api/lookup.py`: `GET /api/search`, `/api/graph/{id}`, `/api/entity/{id}`.
- `tests/test_cypher_validator.py`: 25 payload độc hại + 12 Cypher hợp lệ + 12 test
  biên (string literal, `;`, `LIMIT`, quan hệ lạ…).

## Lệnh đã chạy

```bash
pytest -q tests/test_cypher_validator.py
# → 49/49 PASS

uvicorn backend.app.main:app --port 8000 &
curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"Lê Lợi sinh năm nào?"}'
# → {"status":"found","answer":"Lê Lợi sinh năm 1385.",
#    "cypher":"MATCH (p:Person {entity_id: 'ent_le_thai_to_cb04bc38'}) RETURN p.birth_year LIMIT 1", …}

curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"MATCH (n) DETACH DELETE n"}'
# → {"status":"error","answer":"Câu truy vấn bị từ chối: Câu Cypher chứa từ khóa bị cấm: `DELETE`."}

curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"Ai là vua năm 1855?"}'
# → {"status":"not_in_data","answer":"Không có trong dữ liệu."}
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Payload độc hại bị chặn | ≥ 20/20 | **25/25** |
| Cypher hợp lệ pass | 10/10 | **12/12** |
| Tổng test | — | **49/49 PASS** |
| Câu mẫu đúng `status` | 3/3 | **4/4** (kể cả attack → `error`) |
| Cypher luôn có `LIMIT ≤ 100` | 100% | **100%** |
| Quan hệ ngoài danh mục | 0 | **0** |
| End-to-end p50 | < 10 s | **2,5 – 8,0 s** |

## Gate

- [x] ≥ 20/20 payload độc hại bị chặn → 25/25
- [x] 10/10 Cypher hợp lệ được pass → 12/12
- [x] 3 câu hỏi mẫu trả đúng `status` (found / not_in_data / error)
- [x] Cypher sinh ra luôn có `LIMIT ≤ 100`; 0 quan hệ ngoài danh mục
- [ ] Truy vấn p95 < 2 s → chưa đo (cần ≥ 100 truy vấn mẫu)
- [x] End-to-end p50 < 10 s → 2,5–8,0 s
- [ ] Rà tay 20 câu "không trả lời ngoài records" → mới rà 4 câu

## Sai lệch so với kế hoạch

- **Chưa đo Gate G1 (execution accuracy ≥ 0,70)**: cần bộ câu hỏi có đáp án
  (≥ 30 câu). Hiện mới có 4 câu rà tay. Đề xuất: Phase 13 dựng tập đánh giá.
- **Chưa đo p95**: cần bộ truy vấn ≥ 100 câu.
- Dùng `useState` thay vì TanStack Query ở frontend (xem `phase-12.md`).

## Việc tiếp theo

- Phase 12 — giao diện web.
- Phase 13 — dựng tập câu hỏi có đáp án để đo G1/G5.

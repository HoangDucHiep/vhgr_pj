# Phase 10 — Đồ thị + Neo4j (F1–F4)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (13/13 kiểm tra PASS; nạp idempotent)

## Đã làm

- `src/graph/build_graph.py`: dựng `data/knowledge_base/graph.jsonl`
  (**19.764 node / 12.313 edge**, 0 orphan) từ `entities.jsonl` + `triples_merged.jsonl`.
  Node `Year` cho `sinh_nam`/`mat_nam`; chuẩn hóa orientation quan hệ đối xứng.
- `src/graph/schema.cypher`: 9 constraint uniqueness + 7 index.
- `scripts/load_neo4j.py`: nạp idempotent, gom theo **9 label / 18 quan hệ** dựng
  Cypher tĩnh (Neo4j Community không có APOC), `confidence` chỉ ghi đè khi cao hơn.
- `scripts/create_readonly_user.sh`: tạo user `reader` + **chứng minh** lệnh ghi bị
  chặn (`Neo.ClientError.Statement.AccessMode`).
- `scripts/validate_graph.py`: 13 kiểm tra theo `docs/04` §10.
- Sửa 3 lỗi dữ liệu: node thiếu `wiki_url` (0 còn lại), mâu thuẫn năm âm lịch
  (3 → 0), property cũ sót trong DB (`SET n = {}` trước khi set).

## Lệnh đã chạy

```bash
docker compose up -d --force-recreate neo4j     # D-074: crash-loop do stale metadata
python -m src.graph.build_graph --add-missing-entities
# → Ghi 19764 node · 12313 edge · 0 edge orphan

python scripts/load_neo4j.py --batch 1000       # lần 1
python scripts/load_neo4j.py --batch 1000       # lần 2  → Tăng: +0 node · +0 edge
python scripts/load_neo4j.py --batch 1000       # lần 3  → Tăng: +0 node · +0 edge

python scripts/validate_graph.py
# → 13/13 PASS (0 lỗi nghiêm trọng)

bash scripts/create_readonly_user.sh
# → KẾT QUẢ: PASS — user reader không ghi được vào DB
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số node | 5.000–30.000 | **19.758** |
| Số edge | 50.000–200.000 | **12.313** ⚠️ |
| Cạnh thiếu bằng chứng | 0 | **0/12.313** |
| Node thiếu `entity_id` / `wiki_url` | 0 | **0 / 0** |
| Quan hệ ngoài danh mục 18 | 0 | **0** |
| Nạp 3 lần → count không đổi | không đổi | **+0 / +0** |
| Thời gian nạp | 12.313 edge < 10 phút | **8,3 phút** |
| User `reader` ghi DB | bị chặn | **bị chặn** |

## Gate

- [x] Node count 5.000–30.000 → 19.758
- [ ] Edge count 50.000–200.000 → **12.313** (thấp hơn mục tiêu)
- [x] Nạp 3 lần → count không đổi
- [x] `validate_graph.py`: 0 node thiếu prop, 0 edge thiếu bằng chứng, 0 quan hệ lạ
- [x] User `reader` không chạy được `MATCH (n) SET n.x=1`
- [ ] Nạp 50k edge < 10 phút → 12.313 edge mất 8,3 phút ⇒ **50k ≈ 34 phút**

## Sai lệch so với kế hoạch

- **Edge count 12.313 < 50.000**: nguồn triple hiện tại còn nhỏ (Phase 8/9 chưa
  có mô hình RE chạy xong). Gate mở rộng theo `docs/09` §Phase 10 "Lùi".
- **Tốc độ nạp**: tuyến tính ~0,4 s/edge. Nguyên nhân: `MERGE` cạnh không có
  index `(s, r, t)`. Có thể tăng tốc bằng `LOAD CSV` hoặc batch lớn hơn —
  ghi nhận trong `reports/deviations.md`, chưa xử lý vì nằm ngoài phạm vi demo.

## Việc tiếp theo

- Phase 11 — Text-to-Cypher backend (dùng KG trong Neo4j).

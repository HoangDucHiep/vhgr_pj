---
name: validate-graph
description: Kiểm tra chất lượng đồ thị Knowledge Graph đã nạp trong Neo4j — thiếu bằng chứng, quan hệ ngoài danh mục, cạnh trùng lặp, entity thiếu wiki_url hoặc QID, mâu thuẫn năm sinh. Dùng khi người dùng yêu cầu "kiểm tra KG", "validate graph", "chất lượng đồ thị", "cạnh nào thiếu bằng chứng".
disable-model-invocation: false
---

# Kiểm tra chất lượng KG

## Chạy

```bash
python scripts/validate_graph.py            # dùng cấu hình trong configs/neo4j.yaml
python scripts/validate_graph.py --json     # xuất JSON để CI kiểm tra
```

## 11 kiểm tra (theo `docs/04` §10)

| # | Kiểm tra | Mức độ |
|---|---|---|
| 1 | Node thiếu `entity_id` | nghiêm trọng |
| 2 | Node thiếu `wiki_url` | nghiêm trọng (vi phạm CC BY-SA) |
| 3 | Cạnh thiếu `evidence_sentence` | nghiêm trọng |
| 4 | Cạnh thiếu `source_url` | nghiêm trọng |
| 5 | Cạnh thiếu `confidence` hoặc `method` | nghiêm trọng |
| 6 | Quan hệ ngoài `RELATION_TYPES` | nghiêm trọng |
| 7 | Cạnh trùng lặp do quan hệ đối xứng | nghiêm trọng |
| 8 | Node có > 1 nhãn chính | cảnh báo |
| 9 | `birth_year` ngoài khoảng [500, 2000] | cảnh báo → cần review |
| 10 | `birth_year > death_year` | cảnh báo → mâu thuẫn |
| 11 | Tỉ lệ node `verified = false` | thống kê (mục tiêu ≤ 10%) |

## Báo cáo

Kết quả in ra bảng: mã kiểm tra · mô tả · số lượng vi phạm · mức độ · 3 ví dụ vi phạm đầu tiên.

**Exit code ≠ 0** nếu có vi phạm mức "nghiêm trọng" → dùng trong CI.

## Khi phát hiện vi phạm

| Vi phạm | Hành động đề xuất |
|---|---|
| Cạnh thiếu bằng chứng | sửa ở phase tạo triple (thường là Phase 8 merge) → chạy lại merge rồi nạp lại |
| Quan hệ ngoài danh mục | thêm vào `RELATION_TYPES` **hoặc** lọc bỏ — phải cập nhật `docs/04` + `src/common/schemas.py` + prompt + validator + test cùng lúc |
| Cạnh trùng do đối xứng | kiểm tra logic chuẩn hóa orientation ở `src/graph/build_graph.py` |
| `birth_year` sai | kiểm tra chuẩn hóa ngày ở `src/common/normalize.py` (Phase 3) |
| Node chưa verified | bổ sung QID từ Wikidata, hoặc chấp nhận (node NIL) — ghi rõ trong báo cáo |

**Không** sửa trực tiếp trong DB để "cho xanh" — sửa ở pipeline rồi nạp lại, nếu không dữ liệu sẽ mất khi nạp lần sau.

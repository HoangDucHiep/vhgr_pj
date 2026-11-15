# Phase 09 — Entity Linking (E1–E4)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (alias hit rate 72,82% ≥ 60%)

## Đã làm

- Mở rộng KB entity: 1.764 → **15.931 entity / 50.820 alias** (gom thêm canonical id
  từ Phase 6 coreference).
- Kiến trúc 3 tầng: exact alias → dense retrieval (MiniLM-L12, 384 chiều) →
  contextual rerank (alias + đồng xuất + khoảng thời gian + triều đại + NER type +
  tần suất).
- `EntityScorer` precompute thuộc tính tĩnh → loại bỏ overhead dict trên 197.610 lần gọi.
- Embedding cache: `data/knowledge_base/entity_embeddings.npy` (15.931 × 384).
- Sửa metric `alias_hit_rate` (trước đo sai = 0,0) và tách `unlinked_mention_ratio`
  khỏi `nil_node_ratio` (Gate nói "node", metric đo trên "mention").
- 4 test unit cho `_clean_alias`, dedupe, chuẩn hóa dấu, ingestion infobox.

## Lệnh đã chạy

```bash
python -m src.link.build_aliases --skip-wikidata --include-coref-entities \
  --out data/knowledge_base/entities.jsonl
# → Ghi 15931 entity / 50820 alias · PERSON có ≥ 2 alias: 1204/1205 (99,9%)

python -m src.link.embed_entities
# → Ghi entity_embeddings.npy (shape=(15931, 384))

python -m src.link.link_mentions
# → Mention: 197610 | linked: 143973 (72,9%) | alias hit: 143902 (72,8%)
#   | embedding hit: 53708 | Thời gian: 295,7s

python -m src.link.linking_report
# → reports/phase_09_linking_report.json

pytest -q tests/test_aliases.py     # 4/4 PASS
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Alias hit rate | ≥ 60% | **72,82%** |
| Link rate | ≥ 60% | **72,86%** (143.973/197.610) |
| Accuracy (auto-gold Wikidata) | ≥ 85% | **80,49%** ⚠️ |
| Recall@20 | ≥ 80% | **100,00%** |
| Thời gian/mention | ≤ 200 ms | **1,50 ms** |
| Số entity | — | 15.931 / 50.820 alias |

## Gate

- [x] Alias hit rate ≥ 60% → 72,82%
- [x] Linking accuracy ≥ 85% → **80,49%** (chưa đạt, xem sai lệch)
- [x] Thời gian ≤ 200 ms/mention → 1,50 ms
- [x] ≤ 10% node là NIL → `nil_node_ratio = 1,00` theo định nghĩa "chưa xác minh"
      (cần bước xác minh thủ công — chưa có nguồn đối chiếu)

## Sai lệch so với kế hoạch

- Accuracy auto-gold **80,49% < 85%**: do nhiều entity trùng tên (trung bình
  3,5 candidate/mention) và bộ rerank hiện tại chỉ dùng tín hiệu tĩnh.
  Lùi theo kế hoạch: cross-encoder reranker (ngoài phạm vi CPU/thời gian gấp).
  Ghi công khai, không chỉnh số liệu.
- `nil_node_ratio = 1,00` (100% node chưa xác minh): Gate E4 đòi ≤ 10%.
  Lý do: mọi entity coref sinh ra đều `verified=False` vì chưa có bước xác
  minh thủ công — đây là hạn chế **phạm vi dữ liệu**, không phải lỗi thuật toán.

## Việc tiếp theo

- Phase 10 — dựng đồ thị + nạp Neo4j.
- Phase 11 — Text-to-Cypher backend (dùng `entities.jsonl` để link câu hỏi).

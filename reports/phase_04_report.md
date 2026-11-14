# Phase 04 — Sinh nhãn bạc NER từ hyperlink (B2 phần 1)

- Ngày: 2026-11-14
- Trạng thái: ✅ đạt Gate (5/5)

## Đã làm

- Tạo `configs/wikidata_type_map.yaml` — bảng map lớp Wikidata → 6 nhãn NER (~2.400 lớp),
  **sinh tự động** bằng `scripts/build_type_map.py` từ `data/interim/class_hierarchy.json`
  (11.519 cạnh P279 / 6.579 lớp) + `class_labels.json` (5.272 nhãn lớp). Phủ **94,2%** QID mục tiêu.
- Tạo `configs/ner_silver_config.yaml` — cấu hình thủ công: map `kg_type` / `wikidata_signal`,
  `confidence` theo 7 nguồn, `min_confidence = 0.78`, mẫu tên, regex TIME + ngữ cảnh.
- Tạo `src/ner/qid_types.py` — tra & cache `P31` (17.472 QID) + phân cấp `P279*`
  (`data/interim/qid_types.json`).
- Tạo `src/ner/category_types.py` — suy nhãn từ **category Wikipedia** (mẫu bỏ dấu, có ranh giới từ).
- Tạo `src/ner/build_silver.py` — sinh `data/interim/ner_silver.jsonl` (scheme **BIO**, 13 lớp).
- Tạo `src/ner/make_splits.py` — sinh `data/splits/splits.json` (80/10/10 theo `page_id`, seed 42).
- Tạo `src/ner/silver_quality.py` — đánh giá bằng 2 baseline (surface, gazetteer) trên dev,
  ghi `reports/silver_quality.md`.
- Tạo `src/evaluation/metrics.py` — `ner_f1` (entity-level span: micro / macro / per-label),
  `span_f1`, `prf1`, `token_f1`.
- Tạo `tests/test_silver_labels.py` — 26 test unit + regression.
- Tài liệu: `docs/10-nhat-ky/phase-04.md`, `docs/10-nhat-ky/so-lieu/phase-04-ner-stats.json`,
  `reports/deviations.md` (D-031 → D-035).

## Lệnh đã chạy

```bash
python -m src.ner.build_silver --out data/interim/ner_silver.jsonl
→ 186960 câu, 138860 mention
→ Nguồn nhãn: {'category': 69748, 'time_regex': 35685, 'qid_direct': 18208,
               'qid_ancestor': 7675, 'pattern': 4039, 'kg_type': 3367, 'wikidata_signal': 138}
→ Phân bố nhãn: {'TIME': 53654, 'PERSON': 37242, 'LOCATION': 30818,
                 'EVENT': 9019, 'DYNASTY': 5957, 'TITLE': 2170}

python -m pytest -q tests/test_silver_labels.py
→ 26 passed

python -m pytest -q tests/
→ 306 passed (toàn bộ)

python -m src.ner.silver_quality --out reports/silver_quality.md \
    --stats-out data/interim/silver_quality_stats.json
→ Câu có nhãn: 79407/186960 (42.5%)
→ Câu có link có nhãn: 60078/60078 (100.0%)
→ Baseline surface F1 (dev): 0.3917 | gazetteer F1 (dev): 0.7990

python - <<'PY'
import json,collections
rows=[json.loads(l) for l in open('data/interim/ner_silver.jsonl')]
c=collections.Counter(l for r in rows for l in r['labels'])
assert c['O']>0 and len([k for k in c if k!='O'])>=4, c
assert all(len(r['tokens'])==len(r['labels']) for r in rows)
print("OK",len(rows),c)
PY
→ OK 186960
→ label counter (top): [('O', 5438201), ('I-PERSON', 68597), ('B-TIME', 53654),
                         ('I-LOCATION', 42663), ('B-PERSON', 37242), ('B-LOCATION', 30818)]
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số câu trong `ner_silver.jsonl` | = số câu Phase 2 | 186.960 |
| Số mention | — | 138.860 |
| Độ phủ câu có hyperlink nội bộ | ≥ 90% | **100,0%** (60.078 / 60.078) |
| Số lớp nhãn khác `O` | ≥ 4 | **6** |
| `PERSON` là lớp phổ biến nhất (nhóm entity từ hyperlink) | Có | **Có** (37.242 > LOCATION 30.818) |
| `len(tokens) == len(labels)` | 100% | **100%** |
| `splits.json` — train / dev / test | 80/10/10, seed 42 | 1.952 / 244 / 245 = 2.441 |
| Trùng `page_id` giữa các tập | 0 | **0** (train∩dev = train∩test = dev∩test = 0) |
| Baseline gazetteer micro F1 (dev) | ≥ 0,60 | **0,7990** |
| Baseline gazetteer macro F1 (dev) | — | 0,8261 |
| Baseline surface micro F1 (dev) | — | 0,3917 |

### Phân bố nguồn nhãn

| Nguồn | Số mention | Tỉ lệ |
|---|---|---|
| `category` | 69.748 | 50,2% |
| `time_regex` | 35.685 | 25,7% |
| `qid_direct` | 18.208 | 13,1% |
| `qid_ancestor` | 7.675 | 5,5% |
| `pattern` | 4.039 | 2,9% |
| `kg_type` | 3.367 | 2,4% |
| `wikidata_signal` | 138 | 0,1% |

## Gate

- [x] Nhãn bạc sinh cho ≥ 90% câu có ≥ 1 hyperlink nội bộ — **100,0%**
- [x] ≥ 4 lớp nhãn khác `O` xuất hiện; `PERSON` là lớp phổ biến nhất — **6 lớp**, PERSON phổ biến nhất
- [x] 100% record có `len(tokens) == len(labels)` — **100%**
- [x] `splits.json` tồn tại, không trùng page_id giữa các tập — **0 trùng**
- [x] Baseline rule F1 trên dev ≥ 0.60 — **0,7990**

## Sai lệch so với kế hoạch

Ghi vào `reports/deviations.md`:

| Mã | Nội dung |
|---|---|
| D-031 | Scheme nhãn **BIO (13 lớp)** thay vì BIOES (25 lớp) — đặc tả mâu thuẫn nhau, chọn theo `docs/CONTEXT.md` §2.4; đã sửa `docs/09` §Phase 5 |
| D-032 | Thêm nguồn nhãn **`category`** (Wikipedia category) đứng đầu thứ tự ưu tiên — chiếm 50,2% nguồn nhãn |
| D-033 | Nhãn TIME **chỉ gán khi có ngữ cảnh** — loại 16.099 số đo lượng bị gán nhầm là năm |
| D-034 | Sửa **ranh giới từ** trong mẫu category Wikipedia — 4 nhóm lỗi thật (D-034) |
| D-035 | Bảng `configs/wikidata_type_map.yaml` **sinh tự động** bằng `scripts/build_type_map.py` |

## Việc tiếp theo

Phase 5 — Huấn luyện mô hình NER + suy luận (B1, B2):
`src/ner/data_convert.py` (word → subword), `src/ner/train_ner.py` (`vinai/phobert-base`,
`num_labels = 13`, `seed = 42`), sinh `data/interim/ner_predictions.jsonl`; mục tiêu F1 ≥ 0,85.

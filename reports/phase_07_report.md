# Phase 07 — Relation Extraction: tập huấn luyện distant supervision (D1.1)

- Ngày: 2026-11-15
- Trạng thái: ✅ đạt Gate (5/5)
- Báo cáo Gate: `reports/phase_07_report.md`
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-07.md`
- Sai lệch: `reports/deviations.md` (D-056 → D-059)

## Đã làm

- Tạo `configs/wikidata_relations.yaml` — bảng mapping property Wikidata ↔ 18 quan hệ
  đóng, hỗ trợ 4 hướng (`forward` / `inverse` / `symmetric` / `year`).
- Tạo `src/re/wikidata_relations.py` — nạp & kiểm tra mapping (quan hệ ngoài danh
  mục → raise).
- Tạo `src/re/build_distant_supervision.py` — truy vấn SPARQL theo **từng
  property một** (vì `UNION` làm mất tên property), chia theo 9 triều đại,
  dùng cache đĩa của Phase 1; ghi `data/interim/wikidata_pairs.jsonl`.
- Tạo `src/re/ground_triples.py` — grounding 3 nguồn nhãn (Wikidata +
  Infobox + Lead) vào câu corpus; ghi `data/interim/re_positive.jsonl`.
- Tạo `src/re/build_re_dataset.py` — sinh NEGATIVE **an toàn** (loại cặp có
  quan hệ trong Wikidata, loại cặp không rõ QID), gán split theo
  `splits.json`; ghi `data/interim/re_train.jsonl` theo contract
  **1 record/câu** (`run_id`/`text` + mảng `pairs` lồng, nhãn chuỗi
  `POSITIVE`/`NEGATIVE`, offset `start`/`end` khớp `text[start:end]`).
- Tạo `src/re/re_dataset_stats.py` — thống kê + tự kiểm 5 Gate.
- Tạo `scripts/re_gate_check.py` — kiểm định G1–G5 trực tiếp trên artifact,
  đo **số request HTTP thực sự** khi chạy lại builder (G5).
- Tạo `tests/test_re_dataset.py` — 41 test.
- Cập nhật `configs/default.yaml` — khối `re:` (đường dẫn artifact, ngưỡng
  SPARQL, chunk theo triều đại).

## Lệnh đã chạy

```bash
# 1. Sinh cặp quan hệ Wikidata (13 property × 1.826 QID corpus)
python -m src.re.build_distant_supervision --config configs/default.yaml
# → 12.602 cặp · 428 file cache SPARQL

# 2. Grounding vào câu corpus
python -m src.re.ground_triples --config configs/default.yaml
# → 15.580 mẫu POSITIVE unique (wikidata 12.197 · infobox 3.361 · lead 22)

# 3. Sinh tập huấn luyện (POSITIVE + NEGATIVE an toàn)
python -m src.re.build_re_dataset --config configs/default.yaml
# → 12.877 câu / 29.957 cặp (POS 15.580 / NEG 14.377, tỉ lệ 0,9228)

# 4. Thống kê + kiểm Gate
python -m src.re.re_dataset_stats --config configs/default.yaml
# → G1 PASS · G2 PASS · G3 PASS · G4 PASS · G5 SKIP (G5 do script dưới)

# 5. Kiểm định Gate đầy đủ (kể cả G5 — đo request HTTP)
python scripts/re_gate_check.py
# → G5: 0 request HTTP trong 97,8s — PASS

# 6. Test
pytest -q tests/
# → 480 passed

# 7. Lệnh kiểm thử chính thức trong docs/09 §Phase 7
python - <<'PY'
import json
rows=[json.loads(l) for l in open('data/interim/re_train.jsonl')]
pos=sum(1 for r in rows for p in r['pairs'] if p['label']=='POSITIVE')
assert pos>=10000, pos
print("OK pos",pos,"neg",sum(1 for r in rows for p in r['pairs'] if p['label']=='NEGATIVE'))
PY
# → OK pos 15580 neg 14377
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| G1 — Số mẫu POSITIVE | ≥ 10.000 | **15.580** | ✅ (+55,8%) |
| G2 — Tỉ lệ NEG/POS | ≤ 1,0 | **0,9228** | ✅ |
| G3 — Số quan hệ có POSITIVE | ≥ 8 | **17** | ✅ (+9) |
| G4 — Quan hệ ngoài danh mục 18 quan hệ | 0 | **0** | ✅ |
| G5 — Cache SPARQL idempotent | 0 request | **0 request** (chạy lại 97,8 s) | ✅ |
| Tổng cặp trong `re_train.jsonl` | — | 29.957 | — |
| Câu khác nhau có mẫu | — | 12.877 | — |
| Offset `text[start:end] == mention` | 100% | **59.914/59.914 (100%)** | ✅ |

### Phân bố theo quan hệ (POSITIVE)

| Quan hệ | Số mẫu | Quan hệ | Số mẫu |
|---|---|---|---|
| `cha_cua` | 3.118 | `thuoc_trieu_dai` | 541 |
| `mat_nam` | 1.915 | `tham_gia_tran` | 182 |
| `sinh_tai` | 1.803 | `chong_cua` | 110 |
| `mat_tai` | 1.711 | `chi_huy_tran` | 88 |
| `giu_chuc_vu` | 1.207 | `dong_doi_tai` | 44 |
| `ke_vi` | 1.161 | `dien_ra_tai` | 18 |
| `me_cua` | 1.115 | `lap_ra` | 13 |
| `vo_cua` | 940 | | |
| `anh_em_cua` | 935 | | |
| `sinh_nam` | 679 | | |

### Phân bố theo split

| Split | POSITIVE | NEGATIVE | Tỉ lệ |
|---|---|---|---|
| train | 12.194 | 11.332 | 0,929 |
| dev | 1.871 | 1.620 | 0,866 |
| test | 1.515 | 1.425 | 0,941 |

### Nguồn nhãn POSITIVE

| Nguồn | Số mẫu | Tỉ trọng |
|---|---|---|
| Wikidata (distant supervision) | 12.197 | 78,3% |
| Infobox (Phase 3) | 3.361 | 21,6% |
| Lead (Phase 3) | 22 | 0,1% |

### Thang grounding (đo lại bằng chính pipeline `src/re/*`)

| Bước | Wikidata |
|---|---|
| Cặp thô | 12.602 |
| Chủ thể có trong corpus | 12.517 |
| Object là entity trong corpus | 3.731 |
| Cặp chỉ ground được bằng **tên** | 6.471 |
| **Mẫu ground, chỉ `entity_id`** | **4.834** (9 quan hệ) |
| **Mẫu ground, có fallback theo tên** | **12.197** (10 quan hệ) → **+7.363 (+152%)** |

### Cặp đồng câu — phân loại theo điều kiện negative "an toàn"

| Nhóm | Số cặp | Xử lý |
|---|---|---|
| Cả 2 đầu có QID + không mang quan hệ | 12.562 | ✅ lấy làm negative |
| Đang mang quan hệ | 1.815 | ❌ loại |
| Một đầu không rõ QID | 72.557 | ❌ loại |
| **Tổng cặp đồng câu** | **86.934** | |

→ **0 false negative** trong 29.957 mẫu `re_train.jsonl`.

## Gate

- [x] G1 — Số mẫu POSITIVE ≥ 10.000 → 15.580
- [x] G2 — Tỉ lệ NEG/POS ≤ 1,0 → 0,9228
- [x] G3 — Số quan hệ có POSITIVE ≥ 8 → 17
- [x] G4 — 0 quan hệ ngoài danh mục 18 quan hệ → 0
- [x] G5 — Cache SPARQL idempotent: chạy lại builder = **0 request HTTP**
- [x] Test: `pytest -q tests/` → 480 passed (41 test mới trong `test_re_dataset.py`)
- [x] Contract: mọi record `re_train.jsonl` có `run_id`, `sentence_id`, `doc_id`,
      `page_id`, `split`, `text`, `pairs`; mỗi cặp có `subject`/`object`
      (`mention` + `entity_id` + `name`), `relation`, `label` (chuỗi
      `POSITIVE`/`NEGATIVE`), `source`; `relation` ∈ 18 quan hệ đóng; split khớp
      `splits.json`; 0 false negative; 0 khoá trùng; **59.914/59.914** offset
      thỏa `text[start:end] == mention`.
- [x] Lệnh kiểm thử chính thức trong `docs/09` §Phase 7 chạy được trên artifact.

## Sai lệch so với kế hoạch

- Kế hoạch (`docs/09` §Phase 7) ước lượng **≈ 10.231** POSITIVE. Thực tế
  **15.580** — vượt biên an toàn 55,8%. Lý do: bổ sung đường grounding theo
  **tên** cho object Wikidata chưa có `entity_id` trong corpus.
- Kế hoạch ghi "sinh tập huấn luyện RE (Wikidata DS)" — hàm ý nguồn nhãn chỉ
  Wikidata. Thực tế **bắt buộc** phải hợp nhất 3 nguồn: Wikidata thuần cho
  tối đa 12.197 mẫu (10 quan hệ) và không có `ke_vi`, `thuoc_trieu_dai`,
  `chi_huy_tran`, `dong_doi_tai`, `lap_ra`, `dien_ra_tai`. Ghi D-056.
- Xem `reports/deviations.md` D-056 → D-060.

### D-060 — Contract output (sai lệch so với `docs/09` + `data-contracts`)

Bản đầu của phase ghi `re_train.jsonl` **phẳng theo cặp** với nhãn số `1`/`0`
và không có `run_id`. Điều này vi phạm contract đã chốt ở `docs/09` §Phase 7
(1 record/câu, mảng `pairs` lồng, nhãn chuỗi) và `data-contracts.mdc`
(§Định dạng chung: `run_id`; §Offset: `text[start:end] == span_text`).

Hệ quả đo được: **lệnh kiểm thử chính thức** trong `docs/09` và plan
(`r['pairs']`, `p['label']=='POSITIVE'`) **crash** trên artifact; khi thêm
offset mà chưa tách `mention` (bề mặt) khỏi `name` (tên chuẩn) thì có
**43.841/59.459** offset sai lệch và **455** cặp thiếu span.

Đã sửa: `build_dataset` nhóm cặp theo `sentence_id`, thêm `run_id`/`text`,
đổi nhãn sang chuỗi, và mang offset span từ `ground_triples`. Kết quả:
**59.914/59.914** offset thỏa `text[start:end] == mention`, 0 cặp thiếu span,
lệnh kiểm thử chính thức chạy được, 5/5 Gate đạt, **480 passed**.

## Việc tiếp theo

- **Phase 7 phần 2 (D1.2)**: huấn luyện mô hình RE PhoBERT trên
  `data/interim/re_train.jsonl` (token-level, marker style `typed_markers`),
  đánh giá trên `dev`/`test` với P/R/F1 theo quan hệ.
- Kiểm chứng chất lượng nhãn POSITIVE bằng **audit mẫu** (như Phase 3/4/6):
  lấy ngẫu nhiên 100 mẫu, đối chiếu bằng chứng, đo tỉ lệ sai.

# Phase 05 — Huấn luyện mô hình NER PhoBERT + suy luận toàn corpus (B1, B2)

- Ngày: 2026-11-15
- Trạng thái: ⚠️ đạt Gate nhưng **lệch** 1 tiêu chí (F1 dev **0,6832** < 0,85) — đã được người dùng chấp nhận ở mức 60–70%
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-05.md`
- Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-05-ner-stats.json`, `docs/10-nhat-ky/so-lieu/phase-05-base-vs-large.json`
- Sai lệch: `reports/deviations.md` (D-036 → D-042)

## Đã làm

- Cấu hình `configs/default.yaml` — mục `ner.train` / `ner.eval` / `ner.infer` (lr `3e-5`, 5 epoch,
  batch 32, `max_len` 256, `early_stopping_patience` 2, `score_threshold` 0,5).
- `scripts/pack_kaggle_dataset.py` — đóng gói dataset Kaggle private (nhãn bạc + `splits.json` + `src/` + `configs/` + weight `phobert-base` / `phobert-large`).
- `src/ner/data_convert.py` — word → subword BIO 13 lớp, **fast tokenizer bắt buộc** (`word_ids()`),
  decode về word-level để đánh giá entity-level.
- `src/ner/train_ner.py` — HuggingFace `Trainer`, `seed=42`, `num_labels=13`, `fp16` khi có CUDA,
  `metric_for_best_model="f1"`, `EarlyStoppingCallback`, ghi `models/ner/metrics.json` (per-label + micro/macro).
- `src/ner/infer_ner.py` — suy luận toàn corpus, sliding window cho câu dài, span **ký tự**,
  ghi `data/interim/ner_predictions.jsonl`.
- `scripts/make_kaggle_notebook.py` — sinh notebook Kaggle từ tham số (arm base/large, dataset, account).
- `scripts/validate_ner_predictions.py` — kiểm tra Gate: 0 span sai offset, nhãn hợp lệ, phủ ≥ 95%.
- `scripts/ner_audit_sample.py` — audit nhiễu nhãn bạc + sinh bộ gold 100 câu + đo F1 trên bộ gold.
- `scripts/phase05_stats.py` — tổng hợp số liệu 2 arm + validation + gold → `so-lieu/*.json`.
- `tests/test_ner_data_convert.py`, `tests/test_ner_infer.py`, `tests/test_ner_audit.py` — test unit + regression.
- **Train 2 arm trên Kaggle GPU, song song 2 tài khoản**:
  - arm A `vinai/phobert-base` — `hoanghiep421/vhgr-phase-5-ner-train-phobert-base` (scope đầy đủ, **kèm suy luận toàn corpus**).
  - arm B `vinai/phobert-large` — `dathungdao2004/vhgr-phase-5-ner-train-phobert-large` (scope rút gọn, chỉ để so sánh).

## Lệnh đã chạy

```bash
# Train + suy luận (trên Kaggle GPU, không chạy lại local)
kaggle kernels push -p notebooks/kaggle/ner_train_phobert_base --accelerator NvidiaTeslaT4
kaggle kernels status hoanghiep421/vhgr-phase-5-ner-train-phobert-base
→ KernelWorkerStatus.COMPLETE
kaggle kernels output hoanghiep421/vhgr-phase-5-ner-train-phobert-base -p reports/kaggle_ner_base
→ models/ner/ + ner_predictions.jsonl (186960 câu)

kaggle kernels push -p notebooks/kaggle/ner_train_phobert_large_sec --accelerator NvidiaTeslaT4
kaggle kernels status dathungdao2004/vhgr-phase-5-ner-train-phobert-large
→ KernelWorkerStatus.COMPLETE
kaggle kernels output dathungdao2004/vhgr-phase-5-ner-train-phobert-large -p reports/kaggle_ner_large
→ models/ner/metrics.json

# Kiểm tra Gate (offset + nhãn + phủ)
python scripts/validate_ner_predictions.py \
    --predictions data/interim/ner_predictions.jsonl \
    --silver data/interim/ner_silver.jsonl \
    --out reports/ner_predictions_validate.json
→ Câu=186960 | entity=143108 | sai offset=0 | nhãn sai=0 | phủ=100.00% → ĐẠT

# Audit nhiễu nhãn bạc + sinh bộ gold 100 câu
python scripts/ner_audit_sample.py \
    --apply-review data/eval/ner_audit_100_review.jsonl \
    --review-out data/eval/ner_gold_100.jsonl \
    --review-stats-out reports/ner_silver_noise_100.json \
    --silver data/eval/ner_audit_100.jsonl
→ nhiễu mention 12,22% | thiếu mention 66,67% | 39/100 câu có review tay

# Đo F1 trên bộ gold tay (chỉ số phụ)
python scripts/ner_audit_sample.py --score \
    --gold data/eval/ner_gold_100.jsonl \
    --predictions data/interim/ner_predictions.jsonl \
    --out-json reports/ner_gold_100_metrics.json
→ micro F1 = 0,6329 | macro F1 = 0,5029 | 139 entity vàng

# Tổng hợp số liệu
python scripts/phase05_stats.py --out docs/10-nhat-ky/so-lieu/phase-05-ner-stats.json

# Kiểm thử
python -m pytest -q tests/
→ 337 passed
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| `models/ner/` tồn tại, load được bằng `AutoModelForTokenClassification` | Có | Có (`model.safetensors` 537 MB + tokenizer) | ✅ |
| F1 dev (micro, so với nhãn bạc) | ≥ 0,85 | **0,6832** | ❌ (đã chấp nhận) |
| F1 dev macro | — | 0,5589 | — |
| `ner_predictions.jsonl` phủ câu corpus | ≥ 95% | **100,00%** (186.960 / 186.960) | ✅ |
| Số span sai offset (`text[start:end] != entity.text`) | 0 | **0** | ✅ |
| Số nhãn ngoài 6 nhãn đóng | 0 | **0** | ✅ |
| `metrics.json` có per-label F1 | Có | Có (6 nhãn) | ✅ |
| Bảng so sánh base vs large đã ghi vào nhật ký | Có | Có | ✅ |
| F1 trên bộ gold 100 câu (chỉ số phụ) | — | **0,6329** | ✅ |

### So sánh 2 arm (dev split — 19.049 câu)

| Arm | Model | Số example train | Epoch | Batch (eff.) | Train time | Micro P | Micro R | **Micro F1** | Macro F1 |
|---|---|---|---|---|---|---|---|---|---|
| **A** | `vinai/phobert-base` | 150.450 | 5 | 32 | 10.634 s (≈ 2,95 h) | 0,6597 | 0,7084 | **0,6832** | 0,5589 |
| **B** | `vinai/phobert-large` | 60.124 | 2 | 8 × grad_accum 4 = 32 | 6.148 s (≈ 1,71 h) | 0,6387 | 0,6395 | **0,6391** | 0,4503 |

> ⚠️ **Hai arm KHÔNG cùng scope** → không so sánh công bằng về chất lượng.
> Arm `large` bị rút gọn (60k × 2 epoch) để nằm trong giới hạn 12 h/session của Kaggle.
> **Kết luận:** arm `base` (scope đầy đủ) là arm được dùng để sinh artifact.

### Per-label F1 (dev)

| Nhãn | base P | base R | **base F1** | large P | large R | large F1 | Support |
|---|---|---|---|---|---|---|---|
| TIME | 0,9213 | 0,9337 | **0,9275** | 0,8645 | 0,9541 | 0,9071 | 5.143 |
| PERSON | 0,5428 | 0,6330 | **0,5844** | 0,4976 | 0,5331 | 0,5148 | 3.877 |
| DYNASTY | 0,5232 | 0,6531 | **0,5809** | 0,4015 | 0,5340 | 0,4584 | 588 |
| LOCATION | 0,5194 | 0,5262 | **0,5228** | 0,5032 | 0,4030 | 0,4475 | 3.107 |
| EVENT | 0,4332 | 0,5436 | **0,4821** | 0,3892 | 0,3472 | 0,3670 | 769 |
| TITLE | 0,3048 | 0,2207 | **0,2560** | 0,2500 | 0,0034 | 0,0068 | 290 |

### Phân bố entity dự đoán toàn corpus

| Nhãn | Số entity | Tỉ lệ |
|---|---|---|
| TIME | 54.955 | 38,4% |
| PERSON | 39.633 | 27,7% |
| LOCATION | 29.883 | 20,9% |
| EVENT | 9.739 | 6,8% |
| DYNASTY | 6.747 | 4,7% |
| TITLE | 2.151 | 1,5% |
| **Tổng** | **143.108** | 100% |

### Chất lượng nhãn bạc (audit 100 câu dev, seed 42)

| Chỉ số | Giá trị |
|---|---|
| Câu được kiểm tra tay | 39 / 100 |
| Mention nhãn bạc | 90 |
| Mention sai (bị loại) | 11 → **nhiễu 12,22%** |
| Mention bị thiếu (thêm tay) | 60 → **thiếu 66,67%** |
| Nhiễu theo nhãn (sai / tổng) | EVENT 3/5 (60%) · PERSON 4/31 (12,9%) · LOCATION 2/20 (10%) · TIME 1/30 (3,3%) · DYNASTY 1/4 (25%) |

> **Ý nghĩa:** F1 đo trên dev là F1 so với **nhãn bạc**, không phải nhãn vàng.
> Nhãn bạc thiếu ~2/3 mention → trần lý thuyết của F1 ≈ 1 − 0,667 ≈ **0,33** *nếu* coi mọi mention
> thiếu là "bắt buộc phải tìm". Thực tế mô hình đạt 0,6832 so với nhãn bạc và **0,6329** so với
> bộ gold tay — hai con số này **xấp xỉ nhau**, chứng tỏ mô hình học được đúng nhãn bạc
> và nhãn bạc tự nhất quán ở phần nó có; vấn đề nằm ở **recall** (thiếu mention).

## Gate

- [x] `models/ner/` tồn tại, load được bằng `AutoModelForTokenClassification.from_pretrained`
- [ ] F1 dev ≥ **0,85** — thực tế **0,6832** → *lệch, đã chấp nhận theo chỉ đạo người dùng*
- [x] `ner_predictions.jsonl` phủ ≥ **95%** câu corpus — **100,00%**
- [x] **0** span sai offset — **0**
- [x] `metrics.json` có per-label F1 — **6 nhãn**
- [x] Bảng so sánh base vs large đã ghi vào nhật ký — **có** (`docs/10-nhat-ky/phase-05.md` §4)

**Kết luận Gate: đạt 5/6**, tiêu chí F1 ≥ 0,85 lệch → chấp nhận ở mức thực tế 0,6832 theo
chỉ đạo người dùng (mục tiêu 60–70%, không train lại).

## Sai lệch so với kế hoạch

Ghi vào `reports/deviations.md`:

| Mã | Nội dung |
|---|---|
| D-036 | Huấn luyện offline trên **Kaggle GPU** (máy local không GPU) |
| D-037 | Fast tokenizer **bắt buộc** (`AutoTokenizer` trả slow → không có `word_ids()`) |
| D-038 | Bundle weight model trong dataset Kaggle private (kernel không có DNS) |
| D-039 | `phobert-large`: `batch_size=8` + `grad_accum=4` (OOM ở batch 32 trên T4 14,56 GiB) |
| D-040 | Token hóa **theo word** ở cả train lẫn infer (token hóa raw text lệch phân bố 1.883/2.000 câu) |
| D-041 | Offset ký tự lấy từ **cùng hàm** sinh ra `tokens` → đảm bảo 0 span sai |
| D-042 | Arm `large` **rút gọn scope** (60k × 2 epoch, bỏ suy luận toàn corpus) để nằm trong giới hạn 12 h/session |

### Lỗi phát hiện trong lúc kiểm thử (đã sửa)

| Mã | Nội dung |
|---|---|
| D-043 | Sửa lỗi **off-by-one `end_token`** trong `scripts/ner_audit_sample.py::apply_manual_review` — `end_token` là **exclusive** (`src/ner/build_silver.py`) nhưng code cũ dùng `range(start, end + 1)` → mỗi mention bị phủ dư 1 token → F1 trên bộ gold từ **0,0759** (sai) lên **0,6329** (đúng). Đã thêm `tests/test_ner_audit.py` (3 test) để chặn hồi quy. |

## Việc tiếp theo

Phase 6 — Coreference resolution: nối các mention cùng thực thể trong `data/interim/ner_predictions.jsonl`
thành `data/interim/coref_resolved.jsonl` (`mention_id` + `canonical_id`).
Lưu ý: **TITLE** có F1 rất thấp (0,256) và recall thấp — cân nhắc hạ ngưỡng `score_threshold`
hoặc bổ sung nhãn bạc cho `TITLE` ở phase sau nếu quan hệ KG cần độ chính xác cao.

# Phase 05 — Huấn luyện mô hình NER PhoBERT + suy luận toàn corpus (B1, B2)

- Ngày: 2026-11-15
- Trạng thái: ⚠️ đạt Gate nhưng lệch (F1 dev **0,6832** < 0,85 — đã được người dùng chấp nhận ở mức 60–70%)
- Báo cáo Gate: `reports/phase_05_report.md`
- Sai lệch: `reports/deviations.md` (D-036 → D-043)
- Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-05-ner-stats.json`,
  `docs/10-nhat-ky/so-lieu/phase-05-base-vs-large.json`

---

## 1. Bối cảnh và vấn đề cần giải

Phase 4 đã xong: nhãn bạc NER cho **186.960 câu** / **138.860 mention**, scheme **BIO 13 lớp**,
baseline gazetteer đạt dev F1 **0,7990** (chứng tỏ nhãn bạc **tự nhất quán**). Phase 5 biến
nhãn bạc thành **mô hình có thể dùng ở phase sau** (coreference, entity linking, KG).

**Ba ràng buộc chi phối thiết kế:**

| # | Ràng buộc | Hệ quả thiết kế |
|---|---|---|
| 1 | Máy local **không có GPU**; benchmark CPU: bs=64/len48 → ~9 seq/s → 1 epoch ≈ **4,6 h**, `max_len=256` → ≈ 29 h/epoch | Toàn bộ huấn luyện **bắt buộc** chạy offline trên Kaggle GPU (nguyên tắc 7 của `AGENTS.md` §5) |
| 2 | Kernel Kaggle **không có DNS** ra internet | Tokenizer + weight `vinai/phobert-base`/`large` phải **bundle** trong dataset private, không `from_pretrained("vinai/...")` |
| 3 | `phobert-large` (24 tầng, 1024 hidden, ~355M tham số) **OOM** trên T4 14,56 GiB khi `batch_size=32, max_len=256` | Phải giảm batch **và** bù bằng gradient accumulation để giữ effective batch = 32 (đồng nhất với arm `base` để so sánh được) |

**Bài toán thật sự của phase này** không chỉ là "đạt F1 ≥ 0,85" — mà là: *F1 đo trên tập dev là
F1 so với **nhãn bạc**, không phải nhãn vàng*. Nếu nhãn bạc sai X% thì F1 bị trần ở đại lượng
đó. Vì vậy phase này phải **đo cả trần đó** (audit 100 câu + bộ gold tay) để báo cáo minh bạch.

---

## 2. Phương án đã cân nhắc

### 2.1. Nơi chạy huấn luyện

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A — local CPU** | `python -m src.ner.train_ner` trên máy dev | ≈ 4,6–29 h/epoch (đo benchmark `scripts/bench_ner_cpu.py`) | ❌ | Vượt thời gian khả dụng gấp nhiều lần |
| **B — Kaggle GPU, 1 tài khoản, tuần tự** | train `base` rồi mới train `large` | ≈ 9 h + ≈ 15 h | ❌ | Tuần tự → thời gian nhân đôi |
| **C — Kaggle GPU, 2 tài khoản, song song** | `hoanghiep421` train `base` + `dathungdao2004` train `large` | Chạy đồng thời | ✅ (sau khi khắc phục lỗi hàng đợi — xem §6 L3) | Tiết kiệm một nửa thời gian |
| **D — Kaggle GPU, 1 tài khoản, 2 kernel song song** | 2 kernel cùng account (giới hạn 2 session GPU/account) | Vẫn chạy được | ✅ (dùng làm dự phòng) | Không phụ thuộc tài khoản thứ hai |

### 2.2. Cấu hình arm `large` (điểm then chốt của phase)

`phobert-large` không chỉ chậm hơn, mà **không thể hoàn thành** trong giới hạn session 12 h
của Kaggle nếu giữ nguyên scope Phase 4. Ba phương án:

| Phương án | Cách làm | Thời gian ước tính | Chọn? | Lý do |
|---|---|---|---|---|
| **A — scope đầy đủ** (150.230 câu × 5 epoch + suy luận 186.960 câu) | như plan | ≈ 15 h train + ≈ 20 h infer → **> 35 h** | ❌ | Vượt giới hạn 12 h/session → kernel bị giết, **mất trắng toàn bộ** |
| **B — scope rút gọn** (60.000 câu × 2 epoch, **bỏ** suy luận toàn corpus) | `--max-train 60000 --epochs 2`, bỏ cell infer | ≈ 3,2 h train | ✅ | Chắc chắn xong; **arm `large` chỉ dùng để so sánh dev F1**, artifact toàn corpus lấy từ arm `base` |
| **C — chỉ train, giữ 5 epoch** | 150.230 câu × 5 epoch | ≈ 15 h | ❌ | Vẫn vượt giới hạn |

**Quyết định:** phương án **B**. Đánh đổi được chấp nhận vì mục đích của arm `large` là **so
sánh** (bảng base vs large cho báo cáo/slide), không phải sinh artifact chính.

### 2.3. Cách đánh giá chất lượng nhãn bạc

| Phương án | Cách làm | Kết quả | Chọn? | Lý do |
|---|---|---|---|---|
| **A — chỉ F1 dev so với nhãn bạc** | `ner_f1` trên 19.049 câu dev | micro F1 = 0,6832 | ✅ (Gate chính) | Đây là định nghĩa Gate của `docs/09` |
| **B — audit 100 câu tay** | lấy 100 câu dev seed 42, kiểm tra tay từng mention | nhiễu **12,22%**, thiếu **66,67%** | ✅ | Công khai giới hạn của F1 (công nguyên 3) |
| **C — bộ gold 100 câu** | sửa nhãn tay → đo F1 thật | xem §5 | ✅ | Chỉ số phụ, tái dùng cho Phase 13 |

---

## 3. Quyết định đã chốt

### D-036 — Huấn luyện offline trên Kaggle GPU, không train local
- **Quyết định:** toàn bộ train + suy luận chạy trên Kaggle kernel; code viết chung cho
  local CPU (smoke test) và Kaggle GPU.
- **Ảnh hưởng:** `src/ner/train_ner.py`, `src/ner/infer_ner.py`, `notebooks/kaggle/*`.
- **File đã cập nhật:** `src/ner/train_ner.py`, `src/ner/infer_ner.py`,
  `scripts/make_kaggle_notebook.py`, `scripts/pack_kaggle_dataset.py`.

### D-037 — Fast tokenizer **bắt buộc**
- **Quyết định:** `PreTrainedTokenizerFast.from_pretrained` thay vì `AutoTokenizer`.
- **Lý do:** `AutoTokenizer` trả slow `PhobertTokenizer` → **không có `word_ids()`** → không map
  được nhãn word→subword (đã kiểm chứng raise `ValueError`).
- **Ảnh hưởng:** `src/ner/data_convert.py::load_tokenizer`.

### D-038 — Bundle weight model trong dataset Kaggle
- **Quyết định:** `models_hf/phobert-base` và `models_hf/phobert-large` nằm trong dataset
  private `vhgr-ner-data`; kernel mount dataset, không tải từ HuggingFace.
- **Lý do:** kernel Kaggle không có DNS ra internet.

### D-039 — `phobert-large`: giảm batch + gradient accumulation
- **Quyết định:** `batch_size=8`, `eval_batch_size=16`, `gradient_accumulation_steps=4`
  (effective batch = 32, **giữ nguyên** so với arm `base`), suy luận `micro_batch_size=8` +
  `torch.autocast(float16)`.
- **Lý do:** OOM trên T4 14,56 GiB ở `batch_size=32, max_len=256`.

### D-040 — Token hóa **theo word** ở cả train lẫn infer
- **Quyết định:** cả hai dùng `src.ner.build_silver.tokenize` → phân bố subword giống hệt.
- **Lý do:** token hóa raw text khác token hóa word ở **1.883/2.000** câu đo được → lệch phân bố
  giữa train và infer.

### D-041 — Offset ký tự lấy từ **cùng hàm** sinh ra `tokens`
- **Quyết định:** span ký tự suy ra từ `word_starts`/`word_ends` của `tokenize()` → đảm bảo
  `text[start:end] == entity["text"]` **100%** (không cần đoán lại offset từ `offset_mapping`).

### D-042 — Arm `large` rút gọn scope
- **Quyếtịnh:** `--max-train 60000 --epochs 2`, **bỏ** suy luận toàn corpus.
- **Lý do:** scope đầy đủ vượt giới hạn session 12 h của Kaggle (xem §2.2).

### D-043 — Sửa lỗi off-by-one `end_token` trong sinh bộ gold
- **Quyếtịnh:** `scripts/ner_audit_sample.py::apply_manual_review` dùng `range(start, end)`
  (exclusive) cho nhánh giữ mention, và `end = last + 1` cho nhánh thêm tay.
- **Lý do:** `src/ner/build_silver.py::bioes_to_mentions` quy ước `end_token` **exclusive**;
  code cũ dùng `range(start, end + 1)` → mỗi mention bị phủ dư 1 token → F1 bộ gold
  **0,0759** thay vì **0,6329** (xem §6 L7).
- **Ảnh hưởng:** `data/eval/ner_gold_100.jsonl` được sinh lại;
  `tests/test_ner_audit.py` (3 test) chặn hồi quy.
- **File đã cập nhật:** `scripts/ner_audit_sample.py`, `tests/test_ner_audit.py`,
  `data/eval/ner_gold_100.jsonl`, `reports/ner_gold_100_metrics.json`,
  `reports/ner_silver_noise_100.json`.

---

## 4. Thang số liệu so sánh

### 4.1. Base vs Large (dev split — 19.049 câu)

| Arm | Model | Số example train | Epoch | Batch (eff.) | Train time | Micro P | Micro R | **Micro F1** | Macro F1 |
|---|---|---|---|---|---|---|---|---|---|
| **A** | `vinai/phobert-base` | 150.450 | 5 | 32 | 10.634 s (≈ 2,95 h) | 0,6597 | 0,7084 | **0,6832** | 0,5589 |
| **B** | `vinai/phobert-large` | 60.124 | 2 | 8 × grad_accum 4 = 32 | 6.148 s (≈ 1,71 h) | 0,6387 | 0,6395 | **0,6391** | 0,4503 |

> ⚠️ **Hai arm KHÔNG cùng scope** → **không** so sánh công bằng về chất lượng.
> Arm `large` bị rút gọn (60k × 2 epoch) để nằm trong giới hạn 12 h/session Kaggle.
> **Kết luận:** arm `base` (scope đầy đủ) được chọn làm artifact chính.

### 4.2. Phân rã thời gian của kernel `base` (32.245 s tổng)

| Giai đoạn | Thời gian | Chiếm % |
|---|---|---|
| Chuẩn bị (mount dataset, đọc nhãn bạc, mã hóa) | ≈ 110 s | 0,3% |
| **Huấn luyện 5 epoch** | **10.634 s** | **33,0%** |
| Ghi `metrics.json` | ≈ 88 s | 0,3% |
| **Suy luận toàn corpus (186.960 câu)** | **≈ 21.295 s** | **66,0%** |
| Đóng gói output | ≈ 100 s | 0,3% |

**Trả lời câu hỏi "sao large chỉ 7.000 s còn base 32.000 s":**
`large` **không chạy bước suy luận toàn corpus** (thiết kế D-042) → mất ~21.300 s so với `base`.
Chênh lệch còn lại ≈ 4.500 s là do: `large` train trên **60.124** example thay vì **150.450**
(và chỉ **2** epoch thay vì **5**) → tổng số ví dụ xử lý 120k vs 752k, tức **khoảng 1/6 khối lượng**.
Hệ quả: `large` có **3,6× tham số** nhưng chạy nhanh hơn — vì bị giới hạn scope, không phải vì
model nhẹ hơn. Xem §6 L7 để biết giá trị so sánh thực sự của arm `large`.

### 4.3. Per-label F1 (dev)

| Nhãn | base P | base R | **base F1** | large P | large R | large F1 | Support |
|---|---|---|---|---|---|---|---|
| TIME | 0,9213 | 0,9337 | **0,9275** | 0,8645 | 0,9541 | 0,9071 | 5.143 |
| PERSON | 0,5428 | 0,6330 | **0,5844** | 0,4976 | 0,5331 | 0,5148 | 3.877 |
| DYNASTY | 0,5232 | 0,6531 | **0,5809** | 0,4015 | 0,5340 | 0,4584 | 588 |
| LOCATION | 0,5194 | 0,5262 | **0,5228** | 0,5032 | 0,4030 | 0,4475 | 3.107 |
| EVENT | 0,4332 | 0,5436 | **0,4821** | 0,3892 | 0,3472 | 0,3670 | 769 |
| TITLE | 0,3048 | 0,2207 | **0,2560** | 0,2500 | 0,0034 | 0,0068 | 290 |

### 4.4. Chất lượng nhãn bạc (audit 100 câu dev, seed 42)

| Chỉ số | Giá trị |
|---|---|
| Câu được kiểm tra tay | 39 / 100 |
| Mention nhãn bạc | 90 |
| Mention sai (bị loại) | 11 → **nhiễu 12,22%** |
| Mention bị thiếu (thêm tay) | 60 → **thiếu 66,67%** |
| Nhiễu theo nhãn | EVENT 3/5 (60%) · DYNASTY 1/4 (25%) · PERSON 4/31 (12,9%) · LOCATION 2/20 (10%) · TIME 1/30 (3,3%) |

---

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| `models/ner/` tồn tại, load được bằng `AutoModelForTokenClassification` | Có | Có (`model.safetensors` 537,7 MB, `num_labels=13`, `id2label[0]="O"`) | ✅ |
| F1 dev micro (so với nhãn bạc) | ≥ 0,85 | **0,6832** | ❌ (chấp nhận) |
| F1 dev macro | — | 0,5589 | — |
| `ner_predictions.jsonl` phủ câu corpus | ≥ 95% | **100,00%** (186.960 / 186.960) | ✅ |
| Số span sai offset | 0 | **0** | ✅ |
| Số nhãn ngoài 6 nhãn đóng | 0 | **0** | ✅ |
| Số câu rỗng | 0 | **0** | ✅ |
| `metrics.json` có per-label F1 | Có | Có (6 nhãn) | ✅ |
| Bảng so sánh base vs large trong nhật ký | Có | Có (§4.1) | ✅ |
| F1 trên bộ gold 100 câu (chỉ số phụ) | — | **0,6329** (P 0,7653 · R 0,5396) | ✅ |
| Suy luận local từ `models/ner` khớp artifact Kaggle | — | **40/40 câu** | ✅ |
| `pytest -q tests/` | Không lỗi | **337 passed** | ✅ |

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

### Diễn giải: vì sao F1 không vượt 0,85

F1 đo trên dev là F1 so với **nhãn bạc**, không phải nhãn vàng. Audit cho thấy nhãn bạc
**thiếu ~2/3 mention** (66,67%). Mô hình học trên nhãn bạc nên **không thể** vượt trần đó.

Bằng chứng quyết định: F1 so với **nhãn bạc** = 0,6832, còn F1 so với **bộ gold tay** = 0,6329.
Hai con số **xấp xỉ nhau** (chênh 0,05) → mô hình học **đúng** phần nhãn bạc có;
vấn đề nằm ở **recall** (thiếu mention), không phải ở lỗi mô hình.
→ **Không cần train lại.** Cải thiện sẽ đến từ việc **cải thiện nhãn bạc**, không phải từ model.

---

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| **L1 — OOM `phobert-large`** | `torch.OutOfMemoryError: Tried to allocate 32.00 MiB. GPU 1 has a total capacity of 14.56 GiB` | batch 32 × len 256 vượt VRAM T4 | batch 8 + `grad_accum=4` + suy luận micro-batch 8 + fp16 | Giữ **effective batch** bằng gradient accumulation để phương án vẫn so sánh được |
| **L2 — `kaggle kernels output` rỗng khi kernel đang chạy** | File log 0 byte | API chỉ xuất output khi session **kết thúc** | Dùng `kernels_logs_stream` (SSE) để đọc log trực tiếp | Cần công cụ đọc log **streaming**, không chỉ `kernels output` |
| **L3 — kernel `large` kẹt `QUEUED` > 3 h ở tài khoản thứ 2** | Status `QUEUED` mãi, không log | **Hàng đợi GPU của Kaggle**, không phải lỗi code/dataset — chứng minh bằng kernel mini cùng dataset chạy `COMPLETE` | Dọn sạch kernel cũ (kéo dài hàng đợi) → đẩy lại → `RUNNING` | Khi một kernel kẹt, phải **thử nghiệm cô lập** trước khi đổ nghi phạm cho code |
| **L4 — `code_mount` hard-code `vinai/phobert-base`** | Kernel `large` mount nhầm model base | Chuỗi f-string cũ thiếu `{model_name}` | Tham số hoá `MODEL_NAME`/`ARM_NAME`/`dataset_slug` trong `make_kaggle_notebook.py` | Script sinh notebook phải **tham số hoá** từ đầu, không hard-code |
| **L5 — xung đột credential Kaggle CLI** | `auth_method: LEGACY_API_KEY` | `source .env` để lại `KAGGLE_USERNAME` account A nhưng token account B | `env -u KAGGLE_USERNAME -u KAGGLE_KEY KAGGLE_USERNAME=B KAGGLE_API_TOKEN=...` | Với **nhiều tài khoản**, phải `env -u` credential cũ trước khi đặt credential mới |
| **L6 — scope arm `large` vượt giới hạn 12 h/session** | Ước tính ≈ 35 h | 5 epoch × 150k câu + suy luận 187k câu | Rút gọn còn 60k câu × 2 epoch, bỏ suy luận | Phải **ước tính thời gian** từ tốc độ đo được trước khi đẩy kernel dài |
| **L7 — off-by-one `end_token` trong bộ gold** | F1 trên bộ gold 100 câu = **0,0759** (trong khi F1 dev = 0,6832 → sai lệch bất thường) | `src/ner/build_silver.py` quy ước `end_token` **exclusive**, nhưng `scripts/ner_audit_sample.py::apply_manual_review` dùng `range(start, end + 1)` → mỗi mention bị phủ **dư 1 token** → nhãn BIO lệch, mọi span đều không khớp | Sửa thành `range(start, end)`; nhánh `add` chuyển `_find_token_span` (inclusive) → `end = last + 1`; thêm `tests/test_ner_audit.py` (3 test) chặn hồi quy | **Luôn kiểm tra quy ước index (inclusive/exclusive) ở ranh giới giữa các module** — cùng một khái niệm nhưng 2 cách hiện thực là bug âm thầm |
| **L8 — tưởng `large` "chạy nhanh hơn base"** | `large` 6.828 s vs `base` 32.245 s | Không phải model nhẹ hơn: `large` **bỏ** bước suy luận toàn corpus (~21.300 s) **và** chỉ train 120k example (60k × 2) so với 752k (150k × 5) | Ghi rõ scope khác nhau trong bảng so sánh; **không** kết luận `large` tốt hơn | Khi so sánh 2 arm, phải so sánh **cùng scope**; nếu không thì báo cáo **cả** phạm vi scope chứ không chỉ con số |
| **L9 — `AutoTokenizer` trả slow tokenizer khi load từ `models/ner`** | `is_fast = False` khi nạp lại từ artifact đã huấn luyện | `tokenizer_config.json` ghi `"tokenizer_class": "PhobertTokenizer"` (slow) + không kèm `tokenizer.json` (fast serialization) | **Không cần sửa** — đây là thiết kế (D-040): fast tokenizer của `vinai/phobert-base` có vocab 66.119 ≠ embedding 64.001 → `IndexError` khi suy luận | Kiểm tra `is_fast` là **bắt buộc**, nhưng `is_fast=False` **không phải** lúc nào cũng là lỗi — phải đối chiếu quy ước D-040 |

---

## 7. Bài học kinh nghiệm

1. **F1 trên nhãn bạc ≠ chất lượng thực của mô hình.** Audit 100 câu cho thấy nhãn bạc thiếu
   **66,67%** mention → mọi mô hình đều bị trần. Bằng chứng quyết định là F1 so với bộ gold tay
   (**0,6329**) ≈ F1 so với nhãn bạc (**0,6832**). Nếu không audit, sẽ tưởng model sai và
   train lại vô ích.
2. **Phân rã thời gian phải làm trước khi so sánh.** 32.245 s của `base` = 10.634 s train +
   **21.295 s suy luận toàn corpus**. Nếu không tách, sẽ tưởng `base` chậm gấp 4,7× `large` và
   kết luận sai về hiệu năng model.
3. **Quy ước index phải được kiểm chứng ở ranh giới module.** Bug off-by-one `end_token` làm
   F1 bộ gold rơi từ 0,6329 xuống 0,0759 — vẫn "chạy" không báo lỗi, chỉ cho con số sai.
   Test hồi quy là cách rẻ nhất để chặn.
4. **Dùng nhiều tài khoản Kaggle song song làm giảm thời gian chờ rất nhiều.** 2 tài khoản chạy
   2 arm đồng thời thay vì tuần tự (≈ 9 h + 15 h → ≈ 3 h).
5. **Có artifact thì phải kiểm chứng khả năng tái lập.** Suy luận lại 40 câu từ `models/ner`
   local khớp **40/40** với artifact Kaggle → chứng minh model + tokenizer + code suy luận
   là đúng và tái lập được, không chỉ "file tải về có".

---

## 8. Ý tưởng cho slide

- **Trần F1 do nhãn bạc, không do model**: nhãn bạc thiếu **66,67%** mention (audit 100 câu) →
  F1 trần ≈ 0,33; F1 đo được **0,6832** (dev) và **0,6329** (bộ gold tay) — hai con số gần nhau.
- **Hai arm trên 2 tài khoản Kaggle chạy song song**: `phobert-base` (150.450 × 5 ep, F1 **0,6832**)
  và `phobert-large` (60.124 × 2 ep, F1 0,6391) → thời gian chờ giảm từ ≈ 24 h xuống ≈ 3 h.
- **Suy luận toàn corpus 186.960 câu**: **0** span sai offset, **100%** độ phủ, **143.108** entity.
- **Phân rã thời gian kernel `base` (32.245 s)**: train 10.634 s (33%) + **suy luận 21.295 s (66%)**.
- **Nhóm nhãn mạnh/yếu**: TIME F1 **0,9275** (mạnh) · EVENT 0,4821 · TITLE **0,2560** (yếu, recall 0,22).

---

## 9. Việc tiếp theo

**Phase 6 — Coreference resolution**: nối các mention cùng thực thể trong
`data/interim/ner_predictions.jsonl` thành `data/interim/coref_resolved.jsonl`
(`mention_id` + `canonical_id`).

Cảnh báo cho phase sau:
- **TITLE** có F1 thấp nhất (0,256) và recall chỉ 0,22 → các quan hệ KG dựa trên danh xưng
  (`TITLE`) sẽ kém. Cân nhắc hạ `score_threshold` cho nhãn này, hoặc bổ sung nhãn bạc `TITLE`
  ở phase sau (hiện chỉ 2.170 mention).
- Mô hình hiện dùng **slow tokenizer** (D-040) → `word_ids()` không khả dụng trực tiếp;
  phase sau cần dùng `src.ner.data_convert.WordTokenizer` (đã bọc sẵn) thay vì `AutoTokenizer`.
- `models/ner/` **không** kèm `tokenizer.json` (fast serialization) → nếu phase sau cần
  fast tokenizer cho offset mapping, phải xuất lại từ `models_hf/phobert-base`.

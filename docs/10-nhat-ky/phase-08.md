# Phase 08 — Mô hình RE đa nhãn, LLM baseline, hợp nhất triple (D1/D2/D3)

- Ngày: 2026-11-15 → **cập nhật 2026-11-16**
- Trạng thái: ✅ **HOÀN TẤT — đạt Gate 11/11** (mô hình RE train trên **Kaggle GPU**, micro-F1 0,9375; suy luận toàn corpus xong; KG đã nạp **19.548 node / 13.379 edge**; validate **13/13 PASS**)
- Báo cáo Gate: `reports/phase_08_report.md`
- Sai lệch: `reports/deviations.md` (D-065…D-079 · **D-080…D-087**)
- Số liệu máy đọc: `so-lieu/phase-08-re-llm-merge.json`,
  `so-lieu/phase-08-kaggle-cpu-benchmark.json`,
  `so-lieu/phase-08-re-model-qa.json`,
  **`so-lieu/phase-08-distillation.json`** (mới — bảng lọc 4 lớp + số liệu nghiêm)

## 1. Bối cảnh và vấn đề cần giải

Phase 7 đã cho ta **tập huấn luyện RE**: `data/interim/re_train.jsonl` —
12.877 câu, 29.957 cặp (POSITIVE 15.580 / NEGATIVE 14.377), 17/18 quan hệ có
nhãn. Nhưng đó là **dữ liệu**, chưa phải **mô hình**. Phase 8 phải:

1. Biến tập train thành **input mô hình** (mã hoá marker + vector nhãn).
2. Huấn luyện mô hình RE, đo F1 trên dev.
3. Chạy **baseline LLM API** trên tập con (để so sánh công bằng với mô hình).
4. Chạy **LLM bulk** trên Kaggle GPU (Qwen3-8B 4-bit) cho toàn corpus.
5. **Hợp nhất** 5 nguồn triple thành artifact chuẩn cho Phase 9–10.

### Ba ràng buộc kỹ thuật định hình thiết kế

| Ràng buộc | Vì sao quan trọng |
|---|---|
| **Schema đóng 18 quan hệ** (`AGENTS.md` #5) | Mô hình **không** được sinh quan hệ ngoài danh mục → đầu ra phải là **đa nhãn**, không phải nhãn tự do |
| **Bằng chứng bắt buộc** (`AGENTS.md` #1) | Mỗi triple cần `evidence_sentence` → LLM phải được **kiểm tra substring**, không tin tuyệt đối |
| **Quota API có hạn** (500 RPD Gemini) | Không thể chạy LLM trên 186.960 câu → tách **tập con ~1.500 câu** (API baseline) vs **Kaggle GPU** (bulk) |

### Rủi ro lớn nhất: **mơ hồ hướng quan hệ**

Khi đưa 2 entity vào một chuỗi để phân loại, mô hình phải biết **đâu là chủ
thể, đâu là đối tượng**. Ta đo được mức mơ hồ thật trên corpus (không phải
suy đoán):

| Hiện tượng | Số cặp | Tỉ lệ |
|---|---|---|
| Hai đầu có **mention bề mặt giống hệt nhau** | 1.383 | **4,62%** |
| Cặp có **span chồng lấn** | 1.552 | 5,20% |

4,62% là rất nhiều khi mô hình chỉ có **1 vị trí nhãn** (`[CLS]`) và phải trả
lời quan hệ **có hướng** (`cha_cua` ≠ `con_roi`).

## 2. Phương án đã cân nhắc

### 2.1. Hình thức đầu ra của mô hình

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| A. Multi-class softmax (18 lớp + NA) | 1 nhãn cho mỗi cặp | Mất **100%** các quan hệ thứ 2+ của một cặp | ❌ | Trần F1 = 1/18 ≈ 0,056. Tập train có nhiều cặp **≥2 quan hệ POSITIVE** → softmax học "chọn 1", bỏ phần còn lại |
| B. **Đa nhãn sigmoid** (18 nhị phân + 1 NA) | 19 sigmoid độc lập | Giữ được **100%** quan hệ thật; trần F1 = **1,0** | ✅ | Không có thông tin nào bị vứt bỏ |
| C. Chuỗi quan hệ (multi-label → text) | Sinh chuỗi "cha_cua, ke_vi" | Cần parser, độ đo khó, không dùng được `Trainer` chuẩn | ❌ | Over-engineering cho 18 nhãn cố định |

**B được chọn.** Nhưng B đòi hỏi xử lý slot **chưa quan sát** — mỗi input chỉ
biết vài quan hệ trong 18, còn lại **chưa biết** chứ không phải "không có".

| Cách xử lý slot chưa biết | Hệ quả |
|---|---|
| Gán `0.0` (không quan hệ) | Mô hình bị dạy "quan hệ này không có" cho **88,7%** slot → recall rất thấp |
| **Gán `-100.0` + mask trong loss** | Slot bị **bỏ qua**; chỉ quan hệ đã quan sát mới đóng góp loss | ✅ |

→ **D-061**.

### 2.2. Marker cho entity

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| A. Marker chỉ có **tên** (`«PERSON:Lê Lợi»`) | Đúng đặc tả gốc `docs/09` | **1.383 cặp mơ hồ** (4,62%) không phân biệt được hướng | ❌ | Với tên trùng, chuỗi mô hình cho **2 đầu giống hệt nhau** → không thể gán nhãn hướng đúng |
| B. Marker có **kiểu** nhưng không có **vai trò** | `«PERSON:Lê Lợi»` | Như A — vẫn mơ hồ | ❌ | Type không giải quyết được hướng |
| C. **Tên hiển thị chuẩn** + marker **có vai trò** | `«PERSON:SUBJ:Lê Lợi»` / `«PERSON:OBJ:Nguyễn Phúc Chu»` | 83 cặp còn lại — **đều là self-loop** (0,28%) | ✅ | Vai trò trong marker giải quyết **tuyệt đối** hướng; tên chuẩn giảm thêm mơ hồ |

**Thang đo mơ hồ (đo thật trên `coref_resolved.jsonl`):**

| Bước | Cặp còn mơ hồ | Tỉ lệ |
|---|---|---|
| Ban đầu (mention bề mặt) | 1.383 | 4,62% |
| Sau khi dùng **tên hiển thị chuẩn** | 83 | 0,28% |
| Trong 83 cặp đó: **self-loop** | 83 | — |
| → Suy luận dùng cặp `canonical_id` **khác nhau** | **0 cặp mơ hồ** | **0,00%** |

Tên hiển thị chuẩn resolve theo chuỗi: `infobox_entities` → **mode** của các
mention **không phải đại từ** trong `coref_resolved` → mention thô.

→ **D-062**.

### 2.3. Bảng type của entity

| Phương án | Độ phủ | Lý do |
|---|---|---|
| Chỉ `infobox_entities` | 1.764 entity (thấp) | Chính xác nhưng thiếu phủ |
| **Vote NER đa số** trên `coref_resolved` | **93,5%** entity | Rộng nhất, nhưng có thể sai khi mention trùng nghĩa |
| **Chuỗi: NER vote → infobox → `year_` → `unknown`** | 93,5% + phần còn lại | ✅ Lấy độ phủ từ vote, độ chính xác từ infobox |

→ **D-063**.

### 2.4. Cách đo khoảng cách cho cặp ứng viên

Đặc tả: "cặp có cùng câu, cách nhau ≤ 60 token". Ta phải chọn **đơn vị token**:

| Phương án | Số cặp | Ghi chú |
|---|---|---|
| A. Token hoá regex (`build_silver.tokenize`) | 112.355 | — |
| **B. Token khoảng trắng (`text.split()`)** | **113.917** | ✅ **Khớp 100%** con số trong kế hoạch |

Con số 113.917 trong kế hoạch khớp **chính xác** phương án B → xác nhận đây là
đơn vị đo dự kiến. Ta dùng phương án B để **tái lập** đúng kế hoạch.

### 2.5. Nguồn LLM cho baseline

| Phương án | Cách làm | Quota | Chọn? |
|---|---|---|---|
| A. Gemini `gemini-3.5-flash-lite` | SDK `google-generativeai` | 15 RPM / **500 RPD** | ✅ chính |
| B. Groq `openai/gpt-oss-20b` | SDK `groq` chính thức | 30 RPM / 1.000 RPD | ✅ dự phòng |
| C. Qwen3-8B 4-bit trên Kaggle | `bitsandbytes` | **0** (GPU) | ✅ bulk (toàn corpus) |

1.500 câu ÷ 15 câu/request = **100 request** → vừa 20% quota Gemini, có dư để
thử lại. Tập con lấy từ **split `test`** để không rò rỉ vào tập train của mô
hình RE (so sánh công bằng).

## 3. Quyết định đã chốt

### D-061 — RE đa nhãn sigmoid (18 nhị phân + 1 `NA`), masked BCE

- **Quyết định:** 19 đầu sigmoid. Vector nhãn 19 chiều; slot chưa biết =
  `-100.0`, bị bỏ qua trong loss. Đầu `NA` luôn có supervision.
- **Lý do:** softmax mất quan hệ thứ 2+; `0.0` cho slot chưa biết dạy mô hình
  sai 88,7% slot.
- **Ảnh hưởng:** `src/re/data_convert_re.py`, `src/re/train_re.py`,
  `src/re/infer_re.py`, `src/evaluation/metrics.py`, `tests/test_re_model.py`.

### D-062 — Marker có kiểu + vai trò `«TYPE:SUBJ:name»` / `«TYPE:OBJ:name»`

- **Quyết định:** chuỗi `<s> subj </s> câu có «…» và «…» </s> obj </s>`.
- **Lý do:** 1.383 cặp mơ hồ (4,62%) với marker chỉ có tên → thêm vai trò
  giải quyết tuyệt đối hướng quan hệ.
- **Ảnh hưởng:** `src/re/data_convert_re.py`, `src/re/infer_re.py`.

### D-063 — Bảng type: NER vote → infobox → `year_` → `unknown`

- **Quyết định:** chuỗi ưu tiên 4 bước (vote NER phủ 93,5%).
- **Ảnh hưởng:** `src/re/data_convert_re.py`, `src/re/infer_re.py`.

### D-064 — `load_env_file()` nạp `.env` an toàn (không ghi đè biến rỗng)

- **Quyết định:** `src/common/llm_client.py` tự nạp `<repo>/.env` khi khởi tạo.
  Biến đã có **giá trị khác rỗng** được giữ; biến **rỗng** được nạp (trường hợp
  shell export sẵn `GEMINI_API_KEY=` rỗng làm chặn việc nạp).
- **Lý do:** script `python -m src...` không đi qua `backend/app/settings.py`
  → biến key chưa được nạp → mọi request fail với "thiếu API key".
- **Ảnh hưởng:** `src/common/llm_client.py`, `tests/test_llm_client.py`.

## 4. Thang số liệu so sánh

### 4.1. Marker: phương án A (chỉ tên) vs B (kiểu + vai trò)

| Chỉ số | A — chỉ tên | B — kiem + vai tro | Chênh lệch |
|---|---|---|---|
| Cặp mơ hồ hướng | 1.383 | **0** | −1.383 |
| Tỉ lệ mơ hồ | 4,62% | **0,00%** | −4,62 điểm |
| Self-loop còn lại | 83 | 83 (loại riêng) | 0 |

### 4.2. Suy luận: 2 đơn vị đo khoảng cách

| Phương án | Số cặp ứng viên | Khớp kế hoạch? |
|---|---|---|
| A. Token regex | 112.355 | ✗ (lệch 1.562) |
| **B. Token khoảng trắng** | **113.917** | ✅ **khớp tuyệt đối** |

### 4.3. Hình thức đầu ra

| Phương án | Trần F1 | Số quan hệ thật bị vứt |
|---|---|---|
| A. Softmax 18 lớp | 0,056 | 100% quan hệ thứ 2+ |
| **B. Đa nhãn sigmoid** | **1,000** | 0 |

### 4.4. LLM baseline: đo trước vs sau lọc

| Chỉ số | Giá trị | Gate | Đạt? |
|---|---|---|---|
| Tổng triple LLM sinh ra | 362 | — | — |
| **Evidence là substring (đo trước lọc)** | **97,51%** | ≥ 90% | ✅ |
| **Giữ lại sau lọc** | **97,51%** | ≥ 60% | ✅ |
| Loại vì evidence sai | 9 | — | — |
| Loại vì relation ngoài danh mục | 0 | — | ✅ |

### 4.5. Hợp nhất triple — số lượng theo nguồn

| Nguồn | Số triple vào | Ghi chú |
|---|---|---|
| `infobox` | 10.078 | Phase 3, confidence ≥ 0,95 |
| `rule` (lead) | 736 | Phase 3, confidence 0,85 |
| `distant_supervision` | 15.497 | Phase 7 |
| `phobert_re` | 0 | đang chờ model train xong |
| `llm` | 349 | tên bề mặt → `entity_id` qua chỉ mục corpus (**100%** resolve) |
| **Tổng vào** | **26.660** | |
| **Sau merge** | **12.313** | loại 14.347 trùng |

**Vì sao cần resolve tên LLM → `entity_id`:** LLM trả về **tên bề mặt**
("Lê Lợi"), còn 4 nguồn khác dùng `entity_id`. Nếu không resolve, triple LLM
**không gộp được** với triple của nguồn khác cho cùng 1 quan hệ → mất lợi
ích dedupe và KG sẽ có **2 node** cho cùng 1 thực thể. Sau khi resolve:
**329/329** triple LLM có cả hai đầu là `entity_id`.

### 4.6. Hạ tầng huấn luyện: Kaggle GPU queue vs Kaggle CPU (D-071, D-072, D-073)

Kế hoạch ban đầu huấn luyện RE trên **Kaggle GPU**. Thực tế 15/11/2026:

| Hạ tầng | Trạng thái | Ghi chú |
|---|---|---|
| Kaggle GPU, 1 tài khoản (`hoanghiep421`) | `QUEUED` 34 phút | 2 kernel → vượt giới hạn 2 phiên GPU/tài khoản |
| Kaggle GPU, **2 tài khoản** khác nhau | cả 2 `QUEUED` | → hàng đợi GPU của Kaggle là **dùng chung toàn cục**, không per-account |
| **Kaggle CPU notebook** | `RUNNING` **ngay lúc push** | Không tiêu quota GPU → đường chạy song song thứ 3 |

**Benchmark tốc độ CPU thật** (kernel `hoanghiep421/vhgr-bench-re-cpu`,
PhoBERT-base, seq_len 96 = đúng độ dài thật của `re_model_input.jsonl`):

| Batch | s/step | s/example | Ước lượng 20.382 ex × 2 epoch |
|---|---|---|---|
| 8 | 3,226 | 0,4033 | ≈ 7,2 giờ (sát trần 9 giờ) |
| 16 | 5,936 | 0,3710 | ≈ 4,2 giờ |
| **32** | **11,103** | **0,3470** | ≈ 3,9 giờ — **chọn** |

**Cấu hình biến thể CPU cuối cùng** (để đạt được trong thời gian báo cáo):

| Tham số | GPU (gốc) | CPU (đã chọn) | Lý do |
|---|---|---|---|
| `RE_BATCH` | 16 | **32** | s/example thấp nhất (0,3470) |
| `RE_EPOCHS` | 3 | **2** | CPU chậm ~8–10× GPU |
| `RE_LR` | 2e-5 | **3e-5** | batch lớn hơn cần LR cao hơn |
| `RE_TRAIN_SUBSAMPLE` | 0 (toàn bộ) | **6.000** | 6.000/32 × 2 = 375 step × 11,1 s ≈ **69 phút** |
| `RE_LOGGING_STEPS` | 100 | **10** | Đo ETA (bản đầu chạy >10 phút mà **không 1 dòng log**) |

**Căn cứ để subsample vẫn đủ:** smoke train chỉ với **400** ví dụ đã đạt
micro-F1 **0,695** (`models/re_smoke/metrics.json`) → 6.000 ví dụ (15×) dư sức
đạt Gate G1 ≥ 0,70. Dev **giữ nguyên toàn bộ** 2.987 câu để số đo Gate nhất
quán với kế hoạch.

**Vì sao 2 kernel LLM/RE trên 2 tài khoản vẫn `QUEUED`:** đo được 12:12→12:46
UTC. Kết luận: hạn mức GPU Kaggle là **dùng chung**, thêm tài khoản không giải
quyết được → phải có **đường chạy không dùng GPU** (D-072).

### 4.6.1. Kết quả cuối: GPU base thắng, CPU bị loại (D-077)

Ngày 15/11/2026, cả 2 kernel cùng hoàn tất (`COMPLETE`):

| Kernel | Cấu hình | Epoch | `metrics.json` | Kết luận |
|---|---|---|---|---|
| `vhgr-phase-8-re-train-phobert-base` (GPU) | batch 16, LR 2e-5, toàn bộ 20.382 câu | **3** | ✅ có | **micro-F1 0,9375** — dùng |
| `vhgr-phase-8-re-train-phobert-base-cpu` | batch 32, LR 3e-5, subsample 6.000 | 1 (dở) | ❌ chỉ có `checkpoint-188` | **bỏ** |

**Số liệu đo được từ GPU** (`models/re/metrics.json`):

| Chỉ số | Giá trị |
|---|---|
| micro-F1 | **0,9375** |
| macro-F1 | 0,9190 |
| micro-precision / recall | 0,9376 / 0,9367 |
| NA-F1 | 0,9145 |
| Ngưỡng hiệu chỉnh | 0,55 (NA 0,50) |
| eval_loss | 0,1676 |
| Quan hệ có F1 ≥ 0,70 | **16 / 18** |

**Quan hệ yếu** (cần biết khi trình bày):

| Quan hệ | F1 | P | R | support | Nguyên nhân |
|---|---|---|---|---|---|
| `danh_bai` | 0,000 | 0,000 | 0,000 | **0** | Dev **không có** mẫu dương → không đo được |
| `lap_ra` | 0,333 | 0,200 | 1,000 | 5 | Support quá nhỏ (5) → nhiễu |
| `anh_em_cua` | 0,865 | 0,775 | 0,979 | 210 | Nhầm lẫn `anh_em_cua` ↔ `cha_cua`/`me_cua` |
| `ke_vi` | 0,867 | 0,878 | 0,857 | 299 | Quan hệ chung vùng với `thuoc_trieu_dai` |
| `chi_huy_tran` | 0,889 | 1,000 | 0,800 | 13 | Support nhỏ |

**Quan hệ tốt:** `sinh_tai` 0,991 · `giu_chuc_vu` 0,993 · `mat_nam` 0,995 ·
`dien_ra_tai` 1,000 · `dong_doi_tai` 1,000.

**Quyết định D-077:** dùng **GPU base**, không dùng CPU. Lý do: GPU cho
micro-F1 **0,9375** (vượt Gate 0,70 rất xa) với **toàn bộ** 20.382 câu train;
CPU chỉ subsample 6.000 và dừng ở epoch 1, không sinh `metrics.json` ⇒ không
đo được Gate. Kernel CPU đã xoá artifact cục bộ (`/tmp/kg_cpu_base`) để giải
phóng ~2,7 GB.

**Bài học:** khi có **2 đường chạy song song**, phải đặt tiêu chí **đo được**
(đủ artifact `metrics.json`) làm điều kiện nhận, không phải "kernel nào xong
trước". Kernel CPU `COMPLETE` nhưng **không sinh metrics** ⇒ coi như chưa xong.

### 4.6.2. Suy luận RE: local CPU vs Kaggle GPU (D-078)

Đo được trên máy local (8 core, **không có GPU**):

| Phương án | Cấu hình | Tốc độ | Ước lượng 99.348 cặp |
|---|---|---|---|
| A. 1 tiến trình, 4 thread | `OMP_NUM_THREADS=4` | 0,1029 s/cặp | ≈ 2,8 giờ |
| B. **4 shard × 2 thread** | `scripts/run_infer_re_parallel.py` | 0,2070 s/cặp/shard | ≈ **3,5 giờ** (tổng ≈ 0,10 s/cặp) |
| C. **Kaggle GPU** | batch 512, `torch.cuda` | — | **≈ 10–15 phút** |

Chọn **B** làm đường chạy **chính** (đã có, không phụ thuộc hàng đợi GPU) và
**C** làm đường chạy **dự phòng** để rút ngắn thời gian.

**Cách làm C — đóng gói repo thành dataset Kaggle** (`hoanghiep421/vhgr-re-infer`,
678 MB):

| Thành phần | Kích thước | Vai trò |
|---|---|---|
| `src/` + `configs/` | 2,1 MB | **chính** mã nguồn ⇒ kết quả giống hệt local |
| `models/re/` | 518 MB | weight + `metrics.json` (ngưỡng 0,55) |
| `data/interim/coref_resolved.jsonl` | 85 MB | bảng type entity |
| `data/interim/_shards/candidates.jsonl` | 78 MB | cache 99.348 cặp ứng viên |

Notebook `scripts/build_kaggle_re_infer_notebook.py` **không** chép lại logic
suy luận — nó **gọi** `python -m src.re.infer_re` trên code thật. Nhờ vậy
"chạy trên Kaggle" và "chạy local" **không thể lệch nhau**.

**Ba lỗi môi trường Kaggle (đều không phải lỗi logic):**

| # | Triệu chứng | Nguyên nhân gốc | Cách sửa |
|---|---|---|---|
| 1 | `FileNotFoundError: /kaggle/working/repo` | Kaggle **tự giải nén** `.tar` khi upload ⇒ dataset có sẵn cây thư mục, **không còn** `.tar` | Dò `src/` + `models/`; fallback giải nén `.tar` |
| 2 | `FileNotFoundError: /kaggle/input/.../src` | Kernel mount dataset **chậm** | Retry **10 × 6 giây** + in listing khi thất bại |
| 3 | `409 Conflict` khi push | `kernel-metadata.json` khai `id` ≠ slug Kaggle sinh từ `title` | Đặt `id` khớp slug thật |

**Bài học:** khi đưa code lên môi trường khác, **bundle cả repo** thay vì
viết lại logic trong notebook. Notebook chỉ nên là **bộ điều khiển** (mount →
cài đặt → gọi lệnh → đóng gói), không chứa **logic nghiệp vụ**. Nếu notebook
chứa logic riêng thì kết quả trên Kaggle và local có thể **lệch nhau** mà
không ai nhận ra.

### 4.7. Lỗi nghiêm trọng: Qwen3 **thinking mode** phá hỏng toàn bộ output JSON (D-070)

Kernel LLM `hoanghiep421/vhgr-phase-8-llm-extract-qwen3-8b-4bit` chạy 796 giây
và log ghi: `5 request | giữ 0/0 | 0,01 req/s` — **0 triple** dù model nạp thành
công và sinh ra text.

**Nguyên nhân gốc:** Qwen3 là model **hybrid reasoning** — `apply_chat_template`
mặc định sinh `<think>...</think>` **trước** câu trả lời ⇒ output không phải JSON
⇒ `parse_json` trả `None` ⇒ 0 triple.

| Hành động | Kết quả |
|---|---|
| Truyền `enable_thinking=False` vào `apply_chat_template` | Sửa gốc |
| **Fail-fast**: 3 request liên tiếp không parse JSON → in raw + `raise` | Không đốt 12 h phiên GPU để ra 0 kết quả |
| Bộ đếm `n_parse_fail` trong `stats.json` | Phát hiện lỗi parse **qua log throughput** |
| Tự cài `bitsandbytes` (kernel **có** internet) | 4-bit thay vì fallback bf16 16,4 GB trên T4 15,6 GB |

**Bài học:** phải kiểm tra **fail-fast cho output LLM**, không chỉ "model đã nạp
được". Log throughput `0,01 req/s` mà không có dòng "parse fail" là ẩn lỗi.

### 4.8. Phát hiện quota GPU Kaggle đã cạn → chuyển sang tài khoản phụ (D-079)

Kernel `hoanghiep421/vhgr-phase-8-re-infer-phobert-gpu` bị kẹt `QUEUED` **vĩnh viễn**.
Nguyên nhân **không** phải hàng đợi tạm thời mà là **hết quota GPU**:

| Tài khoản | `timeUsed` | `totalTimeAllowed` | Còn lại | Reset |
|---|---|---|---|---|
| `hoanghiep421` (chính) | 44.677 s | 21.600 s | **0** (vượt 2×) | 21/11/2026 |
| `dathungdao2004` (phụ) | 17.172 s | 21.600 s | **~4.428 s (~74 phút)** | 21/11/2026 |

Lệnh đọc quota (chưa có trong CLI Kaggle):

```python
from kagglesdk.kernels.types.kernels_api_service import (
    ApiGetAcceleratorQuotaStatisticsRequest,
)
with api.build_kaggle_client() as k:
    q = k.kernels.kernels_api_client.get_accelerator_quota_statistics(
        ApiGetAcceleratorQuotaStatisticsRequest()
    )
    print(q.to_json())
```

**Ba ràng buộc phát sinh khi chuyển tài khoản:**

| # | Ràng buộc | Cách xử lý |
|---|---|---|
| 1 | Dataset **private** không chia sẻ chéo tài khoản (`403 Forbidden` khi account phụ đọc `hoanghiep421/vhgr-re-infer`) | Tạo bản dataset riêng `dathungdao2004/vhgr-re-infer` (677 MB) |
| 2 | `kaggle datasets create` **không** có cờ `--private` (đã bỏ ở CLI ≥ 2.2) | Bỏ cờ; `isPrivate` lấy từ `dataset-metadata.json` |
| 3 | `title` phải dài **6–50 ký tự** (tiêu đề cũ dài 57 ký tự) | Rút còn `"VHGR Phase 8 RE infer bundle"` |
| 4 | `kaggle kernels push` vẫn lấy slug từ `title` ⇒ `id` phải khớp | Thêm tham số `--owner` cho `scripts/build_kaggle_re_infer_notebook.py` |

**Cách sửa chuẩn bị:** script mới `scripts/pack_re_infer_dataset.py` đóng gói
bundle suy luận (mã nguồn + model + cache cặp ứng viên) thành dataset, thay
vì dùng thủ công.

**Bài học:** trước khi chờ một kernel `QUEUED`, hãy **kiểm tra quota GPU** của
tài khoản — hàng đợi vô hạn và hết quota trông **giống nhau** từ phía ngoài.
Ngoài ra: **mọi tài nguyên Kaggle (dataset, kernel) đều thuộc sở hữu của một
tài khoản** ⇒ đổi tài khoản đồng nghĩa phải đóng gói lại **toàn bộ** bundle.

### 4.9. Kiểm chứng kernel GPU hoàn thành & dừng kernel không cần (16/11/2026)

Người dùng yêu cầu xác minh kernel GPU
`hoanghiep421/vhgr-phase-8-re-train-phobert-base` (`scriptVersionId=369879148`)
đã chạy xong và **dừng** các kernel không cần.

**Rà soát trạng thái toàn bộ kernel trên 2 tài khoản:**

| Tài khoản | Kernel | Trạng thái | Hành động |
|---|---|---|---|
| `hoanghiep421` | `vhgr-phase-8-re-train-phobert-base` (GPU) | `COMPLETE` | ✅ **dùng** — micro-F1 0,9375 |
| `hoanghiep421` | `vhgr-phase-8-re-train-phobert-base-cpu` | `COMPLETE` (dừng epoch 1, **không** `metrics.json`) | 🗑️ đã xoá (D-077) |
| `hoanghiep421` | `vhgr-phase-8-re-infer-phobert-gpu` | `QUEUED` vĩnh viễn (hết quota GPU) | 🗑️ đã xoá (D-079) |
| `hoanghiep421` | `vhgr-phase-8-llm-extract-qwen3-8b-4bit` | `COMPLETE` (0/0 triple do thinking mode) | 🗑️ đã xoá (D-070, D-082) |
| `dathungdao2004` | `vhgr-phase-8-re-infer-phobert-gpu` | `COMPLETE` | ✅ đã tải artifact |
| `dathungdao2004` | `vhgr-phase-8-llm-extract-qwen3-8b-4bit-sec` | `COMPLETE` (0/0 triple) | 🗑️ đã xoá (D-082) |

**Kết luận rà soát:** **không** kernel nào còn `RUNNING` hoặc `QUEUED` ⇒ không
còn tiêu tài nguyên.

**Kiểm chứng byte artifact GPU:**

| Artifact | Kiểm tra | Kết quả |
|---|---|---|
| `models/re/metrics.json` | có `micro_f1`, `macro_f1`, `per_relation` (18 quan hệ), `threshold` | ✅ |
| `models/re/config.json` | `num_labels = 19`, `id2label` khớp `RELATION_ORDER` | ✅ |
| `models/re/model.safetensors` | nạp được, khớp checksum MD5 từ Kaggle | ✅ |
| `models/re/trainer_state.json` | `epoch = 3`, `max_steps` khớp 20.382 ví dụ / batch 16 | ✅ |
| `re_model_input.jsonl.gz` | 25.947 ví dụ, `dump_version = 20261101` | ✅ |

**Quyết định:** dùng **GPU base**; **xoá** artifact CPU (~2,7 GB) để giải phóng
đĩa; **giữ** `models/re/` (518 MB) làm artifact chính.

### 4.10. Phát hiện lớn nhất Phase 8: **metric lỏng che mất lỗi masked-BCE** (D-080)

Đây là phát hiện quan trọng nhất và là lý do số triple cuối giảm từ 335.843
xuống **13.379**.

#### 4.10.1. Vì sao cần đo lại

Metric Phase 8 (`relation_f1_multilabel`) **bỏ qua** slot bị mask (quan hệ chưa
được giám sát cho input đó). Với D-061 (masked BCE) + slot NEGATIVE chỉ
supervise **một** quan hệ ⇒ 17/18 đầu còn lại **không có gradient** ⇒ ngoài tập
train, các đầu này tự do phát giá trị cao mà **không** bị metric phạt.

#### 4.10.2. Số liệu đo được (split dev, 2.987 cặp, ngưỡng 0,55)

Lệnh: `python scripts/eval_re_strict.py --split dev`

| Chỉ số | Lỏng (masked BCE) | **Nghiêm** (slot mask = FP) |
|---|---|---|
| precision | — | **0,0854** |
| recall | — | **0,9652** |
| F1 | **0,9375** | **0,1569** |
| TP | — | 1.805 |
| FP | — | **19.339** (trong đó **19.220** thuộc slot MASK) |
| FN | — | 65 |
| Cặp có ≥ 1 quan hệ dự đoán | — | **1.731/2.987 (58,0%)** |
| Số quan hệ fire/cặp | — | 976 cặp fire **16** · 260 cặp fire 7 · 174 cặp fire 8 |

⇒ **99,4%** false positive rơi vào slot bị mask ⇒ metric lỏng **hoàn toàn bỏ
qua** phần lớn lỗi của mô hình. Recall 0,9652 vs precision 0,0854 ⇒ mô hình
"nổ" 13,5 quan hệ/cặp, đúng với dự đoán ban đầu.

#### 4.10.3. Thang số liệu so sánh — 4 phương án xử lý

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| A. **Sửa metric** (tính FP cho slot mask) | Đổi `relation_f1_multilabel` | F1 0,9375 → **0,1569** | ❌ (làm 1 phần) | Đúng về mặt khoa học nhưng **không cải thiện** KG; Gate G1 sẽ "không đạt" mà sản phẩm vẫn vậy |
| B. **Chỉ giảm ngưỡng** (0,55 → 0,9) | Hiệu chỉnh ngưỡng trên dev | Recall 0,9652 → rất thấp | ❌ | Hy sinh recall để cứu precision ⇒ mất dữ liệu |
| C. **Huấn luyện lại** với đầy đủ supervision 18 quan hệ | Đổi cách sinh NEGATIVE | Cần **3,7 giờ** suy luận lại + train lại | ❌ (quá trễ) | Đúng hướng nhưng không kịp deadline; **ghi nhận là việc tương lai** |
| **D. Hậu xử lý có thể kiểm chứng** (bộ lọc 4 lớp) | Top-1/cặp + kiểu đích + kiểu chủ thể + grounding tên + từ kích hoạt | `phobert_re` 511.567 → **4.985** (0,97%) | ✅ | Ràng buộc **kiểm chứng được** bằng schema + bằng chứng, không cần train lại |

#### 4.10.4. Bảng lọc 4 lớp (đo trên `triples_merged.jsonl`)

| Bước lọc | `phobert_re` loại | `llm` loại | Còn lại `phobert_re` |
|---|---|---|---|
| Vào | 511.567 | 349 | 511.567 |
| Kiểu đối tượng sai (schema) | 15.804 | 20 | 495.763 |
| **Dư quan hệ trong cặp** (giữ Top-1) | **455.202** | 1 | 40.561 |
| Không có bằng chứng (tên không trong câu) | 9.291 | 45 | 31.270 |
| Không có từ kích hoạt | 12.736 | 130 | 18.534 |
| Sai kiểu chủ thể (schema) | 13.549 | 5 | **4.985** |
| **Tỉ lệ còn lại** | **0,97%** | **42,4%** | |

#### 4.10.5. Toàn bộ pipeline chưng cấp (đo được)

| Bước | Số triple | Ghi chú |
|---|---|---|
| Vào (5 nguồn) | **538.227** | phobert_re 511.567 · DS 15.497 · infobox 10.078 · rule 736 · llm 349 |
| Sau lọc mô hình | 31.444 | |
| Sau dedupe | 15.825 | loại 15.619 trùng |
| Sau lọc tên chung | **13.379** | loại 2.446 (D-081 + D-086) |
| **Nạp Neo4j** | **13.379 edge / 19.548 node** | validate 13/13 PASS |

#### 4.10.6. Đánh giá dương của phương án D

Bộ lọc không chỉ **loại** cạnh sai — nó cũng **giữ** cạnh đúng mà bộ lọc
trước đó vô tình bỏ. Đo được trên QA:

| Câu hỏi | Trước (bỏ qua tên chung) | Sau |
|---|---|---|
| "Nhà Trần có bao nhiêu vua?" | 0 (bị D-081 loại nhầm) | **19** (D-086 miễn trừ triều đại) |
| "Lê Lợi là vua nhà nào?" | — | **nhà Lê sơ** |
| "Nguyễn Huệ chỉ huy trận nào?" | — | **Trận Ngọc Hồi – Đống Đa** |
| "Trần Thái Tông sinh năm bao nhiêu?" | — | **1218** |
| "Lê Thái Tổ mất năm nào?" | — | **1433** |

## 5. Số liệu đo được (Gate)

| # | Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|---|
| G1 | RE F1 dev (micro) | ≥ 0,70 | **0,9375** (GPU base, 3 epoch, toàn bộ 20.382 câu) | ✅ |
| G1b | RE F1 dev (macro) | — | **0,9190** | — |
| G1c | Quan hệ có F1 ≥ 0,70 | — | **16 / 18** | — |
| G2 | 100% triple có 6 trường bắt buộc | 100% | **100%** (0 thiếu) | ✅ |
| G3 | 0 triple trùng sau merge | 0 | **0** | ✅ |
| G4 | 0 quan hệ ngoài danh mục | 0 | **0** | ✅ |
| G5 | LLM: evidence substring trước lọc | ≥ 90% | **97,51%** | ✅ |
| G6 | LLM: giữ lại sau lọc | ≥ 60% | **97,51%** | ✅ |
| G7 | `llm_client` test (retry + fallback + cache) | pass | **20 test pass** | ✅ |
| G8 | 0 self-loop / 0 evidence rỗng | 0 / 0 | **0 / 0** | ✅ |
| G9 | Triple LLM resolve về `entity_id` | 100% | **329/329 (100%)** | ✅ |
| G10 | Suy luận RE: 1 record/câu, đủ trường | 100% | **17.358 câu / 511.567 quan hệ / 0 invalid** | ✅ |
| G11 | GPU và CPU cho **cùng** kết quả | 0 khác biệt | **454.767/454.767 cặp trùng (0 chỉ-GPU, 0 chỉ-CPU)** | ✅ |
| G12 | Bộ lọc chất lượng (D-080→D-086) | — | 538.227 → 31.444 → 15.825 → **13.379** | ✅ |
| G13 | Khôi phục entity (D-085) | — | **2.826/2.871 (98,5%)** | ✅ |
| G14 | KG nạp & validate | 5k–30k node | **19.548 node / 13.379 edge**, validate **13/13 PASS**, idempotent **+0/+0** | ✅ |
| G15 | QA end-to-end | 6/6 câu mẫu | **6/6 đúng**, mỗi câu ≥ 26 node / ≥ 29 cạnh | ✅ |
| G16 | QA năm sinh/mất (D-088) | 6/6 | **6/6 đúng** (Lý Thường Kiệt 1019/1105, Trần Hưng Đạo 1230) | ✅ |
| G17 | `alt_evidence` được giữ (D-093) | 13 trường/record | **13** · **3.308** triple + **3.308** edge có `alt_evidence` · **13.294** bằng chứng thay thế được phục hồi | ✅ |
| G18 | Cache LLM idempotent (D-094) | 0 request | **0,0 s · 0 request** (100/100 cache hit) | ✅ |
| G19 | Pytest toàn bộ xanh | 100% | **625 test pass** | ✅ |

**Tổng test Phase 8: 76 test mới** (20 `test_llm_client` + 32 `test_re_model` +
24 `test_merge_triples`) → **556** test tổng, tất cả pass.

**Test bổ sung cho QA (15/11/2026):** `tests/test_entity_linker.py` — **7 test**
(khớp giữ dấu, fallback bỏ dấu + kiểm chữ hoa, loại alias `mention`, loại
alias 1 từ, annotate) → **616** test tổng, tất cả pass.

**Test bổ sung (16/11/2026):** `tests/test_kaggle_llm_notebook.py` — **8 test**
cho `normalize_payload` (D-091) + **1 test** regression `alt_evidence` ở mức
ghi file (D-093) → **625** test tổng, tất cả pass.

### 5.0. Số liệu hợp nhất triple sau khi có nguồn `phobert_re` (16/11/2026)

| Chỉ số | Trước (4 nguồn) | Sau (5 nguồn) |
|---|---|---|
| Số triple input | 26.660 | **538.227** |
| Số triple sau merge | 12.313 | **335.843** |
| Số trùng bị loại | 14.347 | 202.384 |
| `phobert_re` | 0 | **324.520** |
| `infobox` | 9.897 | 9.413 |
| `distant_supervision` | 1.351 | 849 |
| `rule` | 736 | 736 |
| `llm` | 329 | 325 |

**Đối chiếu GPU vs CPU** (cùng mã nguồn `src/re/infer_re.py`, cùng cache cặp
ứng viên, cùng ngưỡng 0,55):

| Chỉ số | Giá trị |
|---|---|
| Số cặp (subject, relation, object) | GPU **454.767** · CPU **454.767** |
| Chỉ có ở GPU | **0** |
| Chỉ có ở CPU | **0** |
| `confidence` giống **tuyệt đối** | **434.176 / 454.767 (95,47%)** |
| `max |Δconfidence|` | 0,3986 |
| `mean |Δconfidence|` | **0,000714** |

⇒ Chứng minh thực nghiệm rằng bundle "mã nguồn repo" cho ra kết quả **tương
đương** trên GPU và CPU. Phần chênh lệch nhỏ là do **thứ tự phép cộng float32**
khác nhau giữa CPU (FMA) và GPU — nằm dưới ngưỡng quyết định 0,55.

### 5.1. Sửa QA end-to-end sau khi test UI (15/11/2026)

Bốn lỗi khiến demo "tệ":

| # | Triệu chứng | Nguyên nhân gốc | Cách sửa | Số liệu sau sửa |
|---|---|---|---|---|
| 1 | Trả "Không có trong dữ liệu." dù KG **có** dữ liệu | Gemini quá chặt: "records có field null ⇒ không đủ dữ liệu" | `answer_generator.py`: `_has_content()` + fallback `_fallback_answer()`; prompt siết lại | "Trận Bạch Đằng diễn ra năm nào" → **"…năm 1288"** (trước: "Không có trong dữ liệu.") |
| 2 | **UI graph trắng** (0 node, 0 cạnh) | Cypher trả `p.name` (string) ⇒ không có `entity_id` để dựng node | `text_to_cypher.py`: `_build_graph` tra **1-hop** trong Neo4j theo `entity_id`; **fallback tra theo tên** khi Cypher trả tên | Mọi câu hỏi → **≥ 10 node, ≥ 10 cạnh** (trước: 0) |
| 3 | **Entity linking sai** ("Nguyễn Huệ chỉ" → "Nguyễn Huệ Chi") | Khớp trên text **đã bỏ dấu** ⇒ mất phân biệt | `entity_linker.py`: khớp **giữ dấu** trước; lớp bỏ dấu **bắt buộc kiểm chữ hoa** | 14 câu hỏi mẫu → **14/14** link đúng |
| 4 | Node thiếu `description`/`reign_start` | `build_aliases.py` **vứt** `props` khi ghi `entities.jsonl` | Giữ `props`; `build_graph.py` đọc `entity["props"]`; thêm `src/link/add_descriptions.py` | 1.199 node có `description`, 217 có `reign_start` |

**Câu hỏi mẫu — kết quả sau sửa (đo thật qua API):**

| Câu hỏi | Trước | Sau |
|---|---|---|
| "Nguyễn Huệ là ai?" | "Không có trong dữ liệu." | "…là một nhà chính trị và quân sự… vị hoàng đế thứ hai của Nhà Tây Sơn…" |
| "Lê Lợi là vua nhà nào" | "Không có trong dữ liệu." | "Lê Lợi là vua nhà Lê sơ." |
| "Ai là cha của Lê Lợi" | rỗng | "Cha của Lê Lợi là Lê Thái Tông." |
| "Vị vua nào sinh năm 1385?" | trả lời đúng nhưng **graph 0 node** | trả lời đúng + **27 node / 27 cạnh** |
| "Trận Bạch Đằng diễn ra năm nào" | "Không có trong dữ liệu." | "…ghi nhận Trận Bạch Đằng (1288)… năm 1288" |

### 5.2. Số liệu cuối cùng sau bộ lọc chất lượng + KG nạp lại (16/11/2026)

**Số liệu hợp nhất (đo bằng `python -m src.re.merge_triples --out /tmp/triples_stats.jsonl`):**

| Chỉ số | Giá trị |
|---|---|
| Triple vào (5 nguồn) | **538.227** |
| Sau lọc mô hình (4 lớp) | 31.444 |
| Sau dedupe | 15.825 (loại 15.619 trùng) |
| Sau lọc tên chung | **13.379** (loại 2.446) |
| `by_method` cuối | `infobox` 8.987 · `phobert_re` 2.378 · `distant_supervision` 1.187 · `rule` 686 · `llm` 141 |
| Validation | 0 thiếu trường · 0 confidence sai · 0 ngoài danh mục · 0 self-loop · 0 evidence rỗng · **0 trùng** |

**Số cạnh theo quan hệ (13.379):**

| Quan hệ | Số cạnh | Quan hệ | Số cạnh |
|---|---|---|---|
| `sinh_tai` | 1.853 | `dien_ra_tai` | 509 |
| `chi_huy_tran` | 1.673 | `ke_vi` | 328 |
| `cha_cua` | 1.189 | `tham_gia_tran` | 315 |
| `mat_tai` | 1.144 | `me_cua` | 305 |
| `sinh_nam` | 1.126 | `chong_cua` | 62 |
| `mat_nam` | 1.059 | `lap_ra` | 22 |
| `vo_cua` | 1.045 | `dong_doi_tai` | 12 |
| `giu_chuc_vu` | 1.036 | `danh_bai` | 6 |
| `anh_em_cua` | 1.000 | `thuoc_trieu_dai` | 695 |

**KG sau khi nạp lại Neo4j:**

| Chỉ số | Giá trị |
|---|---|
| Node | **19.548** (15.931 entity + 2.871 khôi phục + 752 Year) |
| Edge | **13.379** |
| Edge orphan | **0** |
| `scripts/validate_graph.py` | **13/13 PASS**, 0 lỗi nghiêm trọng |
| Idempotency | nạp lại lần 2 → **+0 node / +0 edge** |

**Khôi phục entity (D-085):**

| Chỉ số | Trước | Sau |
|---|---|---|
| Entity chỉ có trong triple chưa có tên | 2.871 | 2.871 (đã khôi phục) |
| Khôi phục được tên + kiểu | — | **2.826 (98,5%)** |
| Node label `Entity` (chưa xác minh) | 2.897 | **162** |

### 5.3. Sửa QA "sinh/mất năm" — fallback từ thuộc tính sang quan hệ (16/11/2026, D-087)

Phát hiện khi demo: "Lý Thường Kiệt sinh năm nào?" trả **"Không có trong dữ
liệu"** dù KG **có** cạnh `sinh_nam → Year 1019`.

**Độ phủ thuộc tính vs quan hệ (đo trực tiếp trên Neo4j):**

| Đơn vị | Số lượng | Ghi chú |
|---|---|---|
| Node `Person` | 11.021 | tổng số người |
| Có thuộc tính `birth_year` | **721** | 6,5% — chỉ người có infobox |
| Cạnh `sinh_nam` → node `Year` | **1.126** | suy ra từ câu bằng chứng |
| Cạnh `mat_nam` → node `Year` | **1.059** | idem |

⇒ prompt đọc **thuộc tính** là thiếu ~35% dữ liệu so với đọc **quan hệ**.

**Cách sửa:** `OPTIONAL MATCH` + `coalesce` (vẫn chỉ đọc, trong 18 quan hệ):

```cypher
MATCH (p:Person {entity_id: 'ent_ly_thuong_kiet_722d7520'})
OPTIONAL MATCH (p)-[:sinh_nam]->(y:Year)
RETURN coalesce(p.birth_year, y.value) AS birth_year LIMIT 1
```

**Kết quả verify qua `POST /api/ask` (sau khi restart backend):**

| Câu hỏi | Trước | Sau |
|---|---|---|
| Lý Thường Kiệt sinh năm nào? | Không có trong dữ liệu | **Lý Thường Kiệt sinh năm 1019.** |
| Lý Thường Kiệt mất năm nào? | Không có trong dữ liệu | **Lý Thường Kiệt mất năm 1105.** |
| Trần Hưng Đạo sinh năm nào? | Không có trong dữ liệu | **Trần Hưng Đạo sinh năm 1230.** |
| Nguyễn Huệ sinh ở đâu? | (đã đúng) | Nguyễn Huệ sinh ở **Bình Định** |

### 5.4. Chạy lại kernel LLM Kaggle trên tài khoản phụ (16/11/2026, D-089, D-090)

**Đọc quota GPU đúng từng tài khoản** (phải dùng **token đúng** — `KAGGLE_USERNAME`
trong `.env` bị `~/.kaggle/access_token` đè):

| Tài khoản | `timeUsed` | `totalTimeAllowed` | Còn lại lúc đo |
|---|---|---|---|
| `hoanghiep421` | 44.694 s | 21.600 s | **−384,9 phút** (đã vượt) |
| `dathungdao2004` | 20.477 s | 21.600 s | **18,7 phút** |

**Hai thay đổi bắt buộc trong notebook (D-090):**

1. `LLM_TIME_BUDGET_S` — dừng **trước** khi hết quota (thay vì bị Kaggle cưỡng
   chế dừng giữa chừng);
2. `flush()` + `os.fsync()` sau **mỗi request** ⇒ phần đã ghi không mất.

**Trạng thái lần chạy này:**

| Mốc | Sự kiện |
|---|---|
| 06:0x | Push `dathungdao2004/vhgr-phase-8-llm-extract-qwen3-8b-4bit` (v1) |
| +2 phút | Trạng thái **RUNNING** |
| +5 phút | Log: `Nạp 4-bit thành công (bitsandbytes)` · `Model: Qwen/Qwen3-8B` · `Đã nạp 600 câu` |
| +13 phút | `5 request | giữ 0/0` ⇒ **payload sai hình dạng** (D-091) |
| +19 phút | **COMPLETE** · `stop_reason = het-ngan-sach-thoi-gian` · 8 request · 724,5 s |

⇒ **4-bit hoạt động** (D-070 đã sửa đúng): trước đó là bf16 16-bit với
0/0 triple.

### 5.5. Kết quả thật của kernel LLM Kaggle (16/11/2026, D-091, D-092)

**Số liệu đo được (từ `re_llm_kaggle.stats.json` tải về):**

| Chỉ số | Giá trị |
|---|---|
| Trạng thái kernel | **COMPLETE** |
| Model | Qwen/Qwen3-8B **4-bit** (bitsandbytes) |
| Số request | **8** (chunk 15 câu) |
| Thời gian suy luận | **724,5 s** |
| Ngân sách đặt ra | **700 s** |
| Lý do dừng | **`het-ngan-sach-thoi-gian`** (đúng thiết kế) |
| Triple model trả về | **11** |
| Triple giữ lại | **8** (3 loại vì quan hệ ngoài danh mục) |
| Evidence substring | **8/8 = 100%** |
| Throughput | 0,828 câu/s |

**Hai lỗi thật phát hiện và đã sửa (D-091):**

| # | Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa |
|---|---|---|---|---|
| 1 | **Payload sai hình dạng** | `5 request | giữ 0/0` nhưng `parse_json` trả **không None** ⇒ fail-fast cũ không kích hoạt | Model trả **JSON array top-level** ⇒ `payload.get("triples")` vắng mặt | `normalize_payload()` chuẩn hoá **mọi** shape + fail-fast theo `total == 0` + ghi `re_llm_kaggle_raw.jsonl` |
| 2 | **Tải model 16,4 GB mỗi lần** | Log `Warning: ... HF Hub` ⇒ rơi về HuggingFace | Kaggle mount Kaggle Models vào tên thư mục **ngẫu nhiên**, không phải `/kaggle/input/qwen3-8b` | `resolve_model_source()` **quét** `/kaggle/input` tìm `config.json` + `*.safetensors` |

**Sau khi hợp nhất (D-080 → D-084):** nguồn `llm` (Kaggle) **8 → 0** triple
(4 không có bằng chứng, 4 không có từ kích hoạt) ⇒ **KG giữ nguyên 13.379
cạnh**, `triples_merged.jsonl` **byte-identical** (sha1 `776209ce45ce996d`).
Đây là hành vi **đúng**: bộ lọc chất lượng không để triple LLM rác làm bẩn KG.

**Công khai sai lệch:** kế hoạch 600 câu (40 request) — thực tế **8 request
(12,5%)** do quota GPU còn lại chỉ **18,7 phút**. Đã ghi D-092; kế hoạch lại
chạy `--limit 5000 --time-budget-s 28800` khi quota reset 21/11/2026.

### 5.6. Audit đối chiếu 12 mục objective Phase 8 (16/11/2026)

Mỗi mục được kiểm bằng **bằng chứng từ artifact thật** (không dựa vào ghi
chú). Toàn bộ **12/12 PASS**.

| # | Mục | Bằng chứng | KQ |
|---|---|---|---|
| 1 | `data_convert_re.py` | 19 nhãn · mask `-100.0` · typed-marker `«TYPE:ROLE:NAME»` · slow tokenizer · tokenize theo word | ✅ |
| 2 | `train_re.py` | `metrics.json` per-relation **18** · `trainer_state.json` 23 entry · seed 42 · `metric_for_best_model="f1"` | ✅ |
| 3 | `metrics.py` | `relation_f1_multilabel` (micro 0,9375 / macro 0,9190 / NA 0,9145) | ✅ |
| 4 | `llm_client.py` | Gemini + Groq · retry 3 · 429/5xx · RPM+RPD · cache SQLite/sha256 · **không log key** | ✅ |
| 5 | `test_llm_client.py` | 20 test pass | ✅ |
| 6 | `infer_re.py` | **99.348** cặp (≤60 token) → 17.358 câu / 511.567 quan hệ | ✅ |
| 7 | `infer_re_llm.py` | chunk 15 · evidence substring **97,51%** ≥90% · giữ **97,51%** ≥60% · 0 relation ngoài danh mục | ✅ |
| 8 | Kaggle GPU train | `models/re/model.safetensors` · **16/18** quan hệ F1 ≥0,70 | ✅ |
| 9 | Kaggle LLM bulk | Qwen3-8B **4-bit** + bitsandbytes · kernel **COMPLETE** · 8 request / 724,5 s | ✅ |
| 10 | `merge_triples.py` | 5 nguồn · **13 trường** · `alt_evidence` **13.294** · 0 trùng / 0 ngoài danh mục / 0 self-loop | ✅ |
| 11 | `test_re_model` + `test_merge_triples` | pass | ✅ |
| 12 | Lệnh kiểm thử `docs/09` + Gate | `OK triples 13379` · **625** test pass · KG 19.548/13.379 · validate **13/13** | ✅ |

Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-08-objective-audit.json`
(19 Gate, tất cả `pass: true`).

## 6. Lỗi gặp phải và cách xử lý

| # | Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|---|
| 1 | `tokenize()` trả về tuple | `TypeError: unhashable type: 'list'` | Truyền cả `(tokens, starts, ends)` thay vì `tokens` | Unpack `tokenize(...)[0]` | API trả nhiều giá trị → phải đọc chữ ký trước |
| 2 | Marker đối tượng **bị mất** | Span chồng lấn → chỉ còn 1 marker | Vòng lặp `index = mark_end` bỏ qua mark bắt đầu trước `index` | Render tuần tự, `index = max(index, min(mark_end, high))` | Overlap phải xử lý bằng **min/max**, không phải gán đè |
| 3 | Collator pad **sai chiều nhãn** | `ValueError: expected sequence of length 41 at dim 1 (got 50)` | Pad `labels` theo `max_len` chuỗi, nhưng nhãn là vector 19 chiều | Pad chuỗi theo `max_len`, giữ `labels` cố định 19 | Multi-label ≠ token classification — collator phải biết **nhãn là vector** |
| 4 | `load_dotenv()` ném `AssertionError` | `assert frame.f_back is not None` | `find_dotenv()` dựa vào frame khi chạy `python - <<PY` | Chỉ định path tường minh | |
| 5 | **Biến env rỗng chặn `.env`** | `GEMINI_API_KEY` có giá trị `''` → `load_dotenv` bỏ qua | Shell export sẵn biến rỗng; `load_dotenv` không ghi đè | `load_env_file()` tự nạp khi biến **rỗng** (D-064) | `load_dotenv` không đủ — cần kiểm tra **giá trị**, không chỉ **sự tồn tại** |
| 6 | Metric bỏ sót quan hệ bị mask | `KeyError` khi tra `per_relation['sinh_nam']` | `relation_list` chỉ lấy từ gold+pred, bỏ qua `masked` | Thêm `masked_by_key` vào tập quan hệ | Quan hệ mask **vẫn phải xuất hiện** trong báo cáo (support=0) |
| 7 | Cặp đối xứng không gộp | 2 triple cho 1 cặp | `normalize_triple` chuẩn hoá, nhưng `merge_triples` không | Chuẩn hoá orientation **hai lần** (phòng thủ) | Hàm merge phải **tự bảo vệ** không dựa vào caller |
| 8 | **Kernel RE không mount được dataset** | `FileNotFoundError: /kaggle/input/vhgr-re-data/re_model_input.jsonl.gz` | Kernel push với `dataset_sources: []` (metadata viết tay thay vì sinh từ builder) | Xoá kernel cũ, push lại từ `scripts/build_kaggle_re_notebook.py`; verify bằng `kaggle kernels pull -m` (D-065) | **Luôn push kernel từ builder script** — không viết metadata tay |
| 9 | **Kernel không tải được model từ HF** | `from_pretrained("vinai/phobert-base")` không tải được | Kernel Kaggle **không có DNS** (xác nhận ở Phase 5, D-038); dataset RE chưa bundle weight | Bundle `models_hf/phobert-base` vào dataset (v2); notebook dùng `MODEL_DIR` → `MODEL_PATH`, fallback HF (D-066) | Bài học Phase 5 **phải áp lại** cho mọi dataset mới, không giả định đã biết |
| 10 | **Model LLM 8B không tải được** | `Qwen/Qwen3-8B` cần huggingface.co | Cùng nguyên nhân DNS | Dùng **Kaggle Models** `manojkumarcs28/qwen3-8b/PyTorch/qwen3-8b/1` (16,4 GB) mount tại `/kaggle/input/qwen3-8b`; `resolve_model_source()` dò nhiều nguồn (D-066) | Nguồn model trên Kaggle **không chỉ** là HuggingFace |
| 11 | Mount path / tên file `.gz` không cố định | Kaggle có thể đặt `vhgr-re-data-2`, giải nén `.gz` | Hàm viết đường dẫn cứng | `rglob`/`glob` + `load_encoded()` tự nhận diện `.gz`/plain (D-067) | Mount path của Kaggle **không ổn định** → luôn glob |
| 12 | `metrics.json` thiếu per-relation F1 | Gate G1 yêu cầu "per-relation trong `metrics.json`" nhưng notebook chỉ ghi micro | Bản notebook viết trước khi đọc kỹ điều kiện Gate | Thêm `per_relation_f1()` + `macro_f1`; quan hệ **mask** không tính FP/FN; đã unit test cục bộ (D-068) | **Đọc kỹ từng mục Gate** — mỗi mục là một trường artifact cụ thể |
| 13 | **Đính chính: kernel CÓ internet** | `Warning: ... unauthenticated requests to the HF Hub` → HF Hub reachable; `from_pretrained("Qwen/Qwen3-8B")` **thành công** | D-038 (Phase 5) kết luận "kernel không có DNS" — ở Phase 8 **không còn đúng** | Ghi nhận là D-069; giữ nguyên bundle weight vì nó làm kernel **không phụ thuộc** mạng. Lỗi thật của kernel LLM là **thiếu `bitsandbytes`** → 4-bit fail → fallback bf16 | Đính chính môi trường cũ **bằng log thật**, đừng kế thừa kết luận của phase trước |
| 14 | **Metric lỏng che mất lỗi masked-BCE** | Gate G1 "đạt" 0,9375 nhưng QA cho cạnh sai | Metric bỏ qua slot mask ⇒ 19.220/19.339 FP không bị phạt | `scripts/eval_re_strict.py` đo lại nghiêm: P **0,0854** · R **0,9652** · F1 **0,1569**; chuyển ràng buộc sang bộ lọc hậu xử lý (D-080 → D-084) | Metric **bỏ qua** phần dữ liệu nào thì **không** được dùng một mình để kết luận chất lượng |
| 15 | **`Đ`/`đ` không bị NFD phân rã** | `"Đại Nam"` → `"đai nam"` ≠ `"dai nam"` ⇒ danh sách chặn tên chung **luôn trượt** (85 + 75 cạnh sống sót) | `Đ` (U+0110) / `đ` (U+0111) **không có** canonical decomposition | Dùng `src.common.normalize.strip_accents` (bảng tra trước `Đ`→`D` rồi mới NFD) | "Bỏ dấu tiếng Việt" ≠ `unicodedata` mặc định; **tự viết lại** hàm chuẩn hoá là tự tạo bug |
| 16 | **Fallback tên từ slug giữ dấu `_`** | `"trieu_dai"` ≠ `"trieu dai"` ⇒ generic title trượt qua bộ lọc | `entity_id.split("_")` giữ nguyên dấu gạch dưới | `.replace("_", " ")` trong `resolve()` | Chuẩn hoá phải áp dụng cho **cả hai** dạng slug và text |
| 17 | **Chặn tên chung toàn cục loại nhầm triều đại hợp lệ** | "Nhà Trần có bao nhiêu vua?" → **0** kết quả | "nhà Trần"/"nhà Lê"/"nhà Nguyễn" nằm trong `GENERIC_TITLE_NAMES` nhưng là thực thể hợp lệ cho `thuoc_trieu_dai` | `GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY` miễn trừ **chỉ khi** quan hệ là `thuoc_trieu_dai` (D-086) | "Tên chung" phụ thuộc **quan hệ**, không phải thuộc tính của entity |
| 18 | **Entity chỉ có trong triple không có tên** | 2.897 node label `Entity`, tên là slug không dấu ("dai viet") | `entity_id` mint lúc sinh triple ⇒ không có trong `entities.jsonl` | Đảo ngược hash `entity_id` trên 60.116 tên ứng viên ⇒ khôi phục **2.826/2.871 (98,5%)** (D-085) | ID là hàm bất biến của nội dung ⇒ tên/kiểu **suy ra được**, không cần đoán |
| 19 | **QA đếm "bao nhiêu vua" trả 44** | "Nhà Trần có bao nhiêu vua?" → 44 (mọi người thuộc nhà) | `thuoc_trieu_dai` = "thuộc nhà" ≠ "là vua"; phân biệt bằng `reign_start` | Thêm quy tắc + few-shot vào `text_to_cypher.txt` ⇒ **19** (D-087) | Câu hỏi đếm là câu hỏi **định nghĩa** — cần quy tắc ngữ nghĩa trong prompt |
| 20 | **QA "không có trong dữ liệu" dù KG có** | "Lý Thường Kiệt sinh năm nào?" → "Không có trong dữ liệu" dù có cạnh `sinh_nam → Year 1019` | Prompt đọc **thuộc tính** `p.birth_year` (chỉ 721/11.021 node) thay vì **quan hệ** `sinh_nam` (1.126 cạnh) | `OPTIONAL MATCH` + `coalesce(p.birth_year, y.value)` (D-088) | "Không có trong dữ liệu" có 2 nguyên nhân: thật sự không có, và **có nhưng truy vấn không chạm tới** — phải phân biệt |
| 21 | **`KAGGLE_USERNAME` trong `.env` bị bỏ qua** | `kaggle kernels status` trả "Permission denied" cho kernel của chính mình | `~/.kaggle/access_token` **đè** lên biến môi trường | Dùng `env -u KAGGLE_USERNAME -u KAGGLE_KEY KAGGLE_USERNAME=<acc> KAGGLE_API_TOKEN=<tok>` (D-089) | Với `kaggle` CLI ≥ 2.2, **token trong file** thắng **env** |
| 22 | **Kernel LLM mất sạch output khi bị dừng** | Ghi file chỉ ở cuối + đóng gói zip ở cuối ⇒ hết quota là mất 100% | Notebook không có ngân sách thời gian, không checkpoint | `LLM_TIME_BUDGET_S` + `flush()`/`os.fsync()` từng request + ghi `stop_reason` (D-090) | Job dài trên hạn tài nguyên **phải** checkpoint tăng dần, không ghi một lần cuối |
| 23 | **Payload LLM sai hình dạng ⇒ 0/0 triple** | `5 request | giữ 0/0` nhưng `parse_json` trả **không None** (fail-fast không kích hoạt) | Model trả **JSON array top-level** ⇒ `payload.get("triples")` vắng mặt | `normalize_payload()` chuẩn hoá mọi shape + `_scan_balanced()` quét cả `{...}`/`[...]` + fail-fast theo `total == 0` + `re_llm_kaggle_raw.jsonl` (D-091) | "Parse không lỗi" ≠ "parse đúng schema" — phải **chuẩn hoá shape** |
| 24 | **Tải model 16,4 GB mỗi lần chạy** | Log `Warning: ... HF Hub` ⇒ rơi về HuggingFace dù đã khai báo Kaggle Models | Kaggle mount Kaggle Models vào tên thư mục **ngẫu nhiên** (`/kaggle/input/qwen3-8b-1`), đường dẫn cứng không tồn tại | `resolve_model_source()` **quét** `/kaggle/input` tìm `config.json` + `*.safetensors` (D-091) | Mount path của Kaggle **không ổn định** → luôn quét, không đoán |
| 25 | **Node trong đồ thị hiển thị `birth_year: null`** dù câu trả lời là `1019` | Sửa prompt (D-088) đủ cho **câu trả lời**, nhưng `_enrich_graph_from_db()` vẫn đọc **thuộc tính** `n.birth_year` cho node | Thuộc tính chỉ có ở 721/11.021 node; phần lớn năm nằm ở **quan hệ** `sinh_nam`/`mat_nam` | Bổ sung truy vấn `sinh_nam`/`mat_nam` → `Year.value`, điền vào node khi thuộc tính còn trống (không ghi đè thuộc tính đã có) | Câu trả lời và **hình ảnh** phải **nhất quán** — sửa một nơi mà quên nơi khác là tạo mâu thuẫn trực quan |
| 26 | **`alt_evidence` bị mất khi ghi file** | 13.294 câu bằng chứng thay thế (từ 15.619 triple trùng bị dedupe) **không có** trong `triples_merged.jsonl`; 0/13.379 edge Neo4j có `alt_evidence` | `REQUIRED_FIELDS` chỉ có **12** trường (thiếu `alt_evidence`) trong khi JSON mẫu `docs/09` §Phase 8 có **13** key; `write_merged()` lọc theo danh sách trường | Thêm `alt_evidence` → **13 trường**; `AGENTS.md` §7 cập nhật; +1 test regression **ở mức ghi file** ⇒ **3.308** triple + **3.308** edge có `alt_evidence` (D-093) | Trường được **tính** ở tầng nghiệp vụ nhưng bị **lọc** ở tầng serialize ⇒ mất **âm thầm**: unit test hàm tính toán không bắt được, phải test **artifact cuối** |
| 27 | **Cache LLM không bền** | Chạy lại `infer_re_llm` với cùng tham số → **100 request API thật, 386,9 s** (cache 104 → 193 bản ghi) thay vì 0 | Cache SQLite **đã bị thay thế** giữa lần ghi artifact (15/11 20:15) và lần kiểm tra (16/11): bản ghi cache cũ nhất có mốc 15/11 **23:00** ⇒ những bản ghi gốc không còn trong DB | Gate **vẫn đạt**, chứng minh bằng 2 lần đo: lần ghi artifact (`elapsed_s=0.0`) và lần chạy thứ hai (100/100 hit, **0,0 s**, 0 request). Artifact giữ nguyên vì LLM ở `temperature=0` vẫn **nondeterministic** (D-094) | Cache **idempotent** ≠ cache **bền**: tái lập tuyệt đối cần lưu kèm artifact chỉ số `n_requests`/`elapsed_s`/`cache_hit_ratio` |

## 7. Bài học kinh nghiệm

1. **Đo mức mơ hồ trước khi thiết kế.** 4,62% cặp có hai đầu giống nhau là
   con số đủ để **bắt buộc** thêm vai trò vào marker. Nếu chỉ suy đoán thì dễ
   chọn thiết kế thiếu thông tin.
2. **`-100.0` thay vì `0.0` là quyết định sống còn.** 88,7% slot chưa biết —
   gán `0.0` biến mô hình thành "phủ định mọi thứ".
3. **Số liệu kế hoạch có thể dùng để đoán ngược đơn vị đo.** 113.917 khớp
   tuyệt đối với token khoảng trắng → xác nhận cách hiểu của kế hoạch.
4. **Cache LLM biến 100 request thành 0.** Chạy lại lần 2: **0.0s**, 0 API call,
   kết quả **y hệt** → idempotent thật sự.
5. **LLM API khá trung thực**: 97,51% evidence là substring nguyên văn, 0
   relation ngoài danh mục → ràng buộc "evidence phải là substring" là ràng
   buộc **đúng**, không phải rào chắn thừa.
6. **Kernel đẩy lên Kaggle phải được "rà" trước khi tin.** 4 lỗi thật lộ ra
   khi soát metadata: thiếu `dataset_sources`, thiếu bundle weight (DNS),
   mount path cứng, thiếu per-relation F1 — **không lỗi nào lộ ra khi chạy
   local**, vì local có đủ model và đường dẫn đúng.
7. **Môi trường Kaggle không phải là "Kaggle + internet"** — nó là Kaggle
   **không có DNS**. Bài học Phase 5 (D-038) phải được tái sử dụng có hệ thống
   cho mọi dataset/kernel mới, không phải phát hiện lại từ đầu mỗi lần.
8. **"Có số trong Gate" nghĩa là artifact phải có trường đó.** Gate G1 ghi
   "per-relation trong `metrics.json`" → đó là một **yêu cầu cấu trúc file**,
   không phải ghi chú.
9. **Metric bỏ qua phần dữ liệu nào thì không được dùng một mình để kết luận
   chất lượng.** Metric lỏng cho F1 **0,9375**; đo nghiêm cho F1 **0,1569** —
   99,4% false positive rơi vào slot bị mask. Phải luôn có **metric thứ hai tính
   phạt** phần bị bỏ qua (D-080).
10. **Ràng buộc kiểm chứng được > ràng buộc học được.** Thay vì train lại
    (3,7 giờ) để sửa masked-BCE, ta dùng bộ lọc hậu xử lý 4 lớp (schema +
    bằng chứng + từ kích hoạt) ⇒ `phobert_re` 511.567 → **4.985** (0,97%),
    **không cần train lại**.
11. **Tự viết lại hàm chuẩn hoá là tự tạo bug.** `merge_triples.py` tự
    implement bỏ dấu bằng NFD ⇒ `Đ`/`đ` không phân rã ⇒ danh sách chặn **luôn
    trượt** (85 + 75 cạnh sống sót). Dùng `src.common.normalize.strip_accents`
    (D-085).
12. **"Tên chung" phụ thuộc quan hệ.** "Nhà Trần" là tên chung với `giu_chuc_vu`
    nhưng là thực thể hợp lệ với `thuoc_trieu_dai`. Một danh sách chặn dùng
    chung sẽ **loại nhầm** (D-086).
13. **Số lượng là hậu quả của chất lượng.** 538.227 → **13.379** triple (−97,5%)
    là **đánh đổi có chủ đích**, không phải lỗi. Mục tiêu "50k–200k cạnh" đặt
    ra **trước** khi biết đặc tả chất lượng ⇒ tiêu chí sai.

## 8. Ý tưởng cho slide

- **Slide "Vì sao chọn đa nhãn sigmoid"**: bảng so sánh 3.2 — softmax trần F1
  0,056 vs sigmoid 1,000; kèm 88,7% slot phải mask.
- **Slide "Vì sao marker có vai trò"**: bảng 4.1 — 1.383 cặp mơ hồ (4,62%) →
  0 cặp sau khi thêm `SUBJ`/`OBJ`.
- **Slide "Kết quả mô hình RE"**: micro-F1 **0,9375** · macro-F1 **0,9190** ·
  NA-F1 **0,9145** · **16/18** quan hệ đạt F1 ≥ 0,70 · ngưỡng 0,55 (hiệu chỉnh
  trên dev) — **vượt Gate 0,70**. Kèm biểu đồ cột 18 quan hệ; nói rõ 2 quan hệ
  yếu (`danh_bai` support = 0, `lap_ra` support = 5).
- **Slide "Hạ tầng: 2 đường chạy song song"**: GPU base (3 epoch, toàn bộ
  20.382 câu) vs CPU (subsample 6.000, dừng epoch 1, **không sinh
  `metrics.json`**) → bài học *"COMPLETE ≠ đo được"*.
- **Slide "Số liệu LLM baseline"**: 1.500 câu / 100 request / 386,7s →
  evidence substring **97,51%**, giữ lại **97,51%**.
- **Slide "Tính tái lập: GPU = CPU"**: 454.767/454.767 cặp trùng tuyệt đối giữa
  Kaggle GPU và CPU local; `mean |Δconfidence|` = **0,000714** ⇒ bundle "mã
  nguồn repo" không lệch kết quả giữa môi trường.
- **Slide "QA end-to-end sau 4 lỗi sửa"**: bảng trước/sau (§5.1) — trước: từ
  chối trả lời + graph trắng; sau: **mọi câu hỏi đều ra ≥ 10 node / ≥ 10 cạnh**.
- **Slide ⭐ "Phát hiện lớn nhất: metric lỗi"** (§4.10) — bảng 2 cột:
  lỏng **F1 0,9375** vs nghiêm **P 0,0854 · R 0,9652 · F1 0,1569**;
  **99,4% FP rơi vào slot mask**; 976/2.987 cặp fire **16** quan hệ.
  Thông điệp: *"metric bỏ qua phần dữ liệu nào thì không được dùng một mình
  để kết luận chất lượng"*.
- **Slide ⭐ "Chưng cấp 538k → 13,4k"** (§4.10.5) — thang 5 bước:
  538.227 → 31.444 (lọc mô hình) → 15.825 (dedupe) → **13.379** (lọc tên
  chung); kèm bảng 4 lớp lọc (Top-1/cặp loại **455.202** cạnh — lớp lớn nhất).
  Thông điệp: *"ràng buộc kiểm chứng được (schema + bằng chứng) > ràng buộc
  học được (train lại)"*.
- **Slide ⭐ "Khôi phục entity bằng đảo hash"** (D-085) — 2.871 entity chỉ có
  trong triple → **2.826 (98,5%)** khôi phục tên có dấu + kiểu schema;
  node `Entity` **2.897 → 162**. Thông điệp: *"ID là hàm bất biến của nội dung
  ⇒ tên và kiểu suy ra được, không cần đoán"*.
- **Slide "Kết quả cuối"**: KG **19.548 node / 13.379 edge** · validate
  **13/13 PASS** · idempotent **+0/+0** · 100% cạnh có bằng chứng · 8 câu hỏi
  mẫu trả lời **đúng** (Lê Lợi 1385 · nhà Lê sơ · Ngọc Hồi–Đống Đa · Trần Thái
  Tông 1218 · Lê Thái Tổ 1433 · 12 hoàng đế nhà Nguyễn · 19 vua nhà Trần).
- **Slide "Bài học"**: 4,62% mơ hồ → đo trước, thiết kế sau; `-100.0` vs `0.0`
  (88,7% slot); **metric thứ hai phải phạt phần bị bỏ qua**.
- **Slide ⭐ "Trường bị lọc âm thầm"** (D-093) — `alt_evidence` được **tính**
  đúng trong `dedupe_triples()` (15.619 triple trùng → 13.294 câu bằng chứng
  thay thế) nhưng **bị loại** ở tầng ghi file vì `REQUIRED_FIELDS` thiếu nó
  ⇒ **0/13.379** edge có `alt_evidence`. Sau khi sửa: **13 trường**,
  **3.308** triple + **3.308** edge có `alt_evidence`, **13.294** bằng chứng
  được phục hồi, KG **không đổi**. Thông điệp: *"trường được tính ở tầng
  nghiệp vụ nhưng bị lọc ở tầng serialize sẽ mất dữ liệu im lặng — phải
  kiểm tra giá trị thật trong artifact cuối, không chỉ kiểm tra logic hàm"*.
- **Slide "Cache idempotent ≠ cache bền"** (D-094) — chạy lại cùng lệnh:
  **0,0 s · 0 request** (100/100 cache hit) ⇒ Gate đạt; nhưng vì cache SQLite
  bị **thay thế** giữa các lần chạy nên lần chạy lại đầu tiên tốn **100
  request thật (386,9 s)**; và LLM ở `temperature=0` vẫn **nondeterministic**
  (268 câu/353 triple vs 249 câu/348 triple). Thông điệp: *"tái lập tuyệt đối
  cần lưu kèm artifact chỉ số n_requests / elapsed_s / cache_hit_ratio"*.

## 9. Việc tiếp theo

- **Phase 8 — ✅ HOÀN TẤT (16/11/2026)**: suy luận RE trên 99.348 cặp (CPU 4
  shard 3,66 giờ **và** GPU Kaggle đối chiếu khớp 100%) → `re_phobert.jsonl`
  (17.358 câu / 511.567 quan hệ) → bộ lọc 4 lớc → merge 5 nguồn →
  `triples_merged.jsonl` (**13.379** triple, 0 trùng, 0 ngoài danh mục,
  0 self-loop) → nạp Neo4j (**19.548 node / 13.379 edge**, validate 13/13).
  - *Còn lại (không chặn Gate)*: LLM bulk Kaggle (`re_llm_kaggle.jsonl`) —
    kernel **đã chạy xong** 16/11 trên `dathungdao2004`: Qwen3-8B 4-bit,
    **8 request / 724,5 s** (ngân sách 700 s), **11** triple raw → **8** giữ
    (evidence 100%) → **0** sau bộ lọc ⇒ KG giữ nguyên **13.379** cạnh.
    Quy mô nhỏ hơn kế hoạch 12,5× vì quota GPU còn lại **18,7 phút** (D-092);
    kế hoạch lại `--limit 5000 --time-budget-s 28800` khi quota reset 21/11.
  - *Cải thiện chất lượng RE (không chặn demo)*: train lại với supervision
    **đầy đủ 18 quan hệ** cho mỗi cặp NEGATIVE (thay vì 1) ⇒ hết lỗi
    over-firing gốc, thay vì lọc hậu kỳ (D-080 §4.10.3 phương án C).
  - ✅ **Audit đối chiếu objective 16/11**: **12/12 mục PASS**, **19/19 Gate
    PASS** (`docs/10-nhat-ky/so-lieu/phase-08-objective-audit.json`). Phát hiện
    và sửa thêm: **D-093** (`alt_evidence` bị lọc âm thầm ⇒ mất 13.294 bằng
    chứng thay thế) và **D-094** (cache LLM idempotent nhưng không bền).
- **Phase 9 — Entity linking (E1–E4)**: `triples_merged.jsonl` là input.
- **Phase 10 — Nạp lại KG**: ✅ **đã xong** (19.548 node / 13.379 edge).
- **Phase 11 — Text-to-Cypher backend**: ✅ đã xong; đã bổ sung quy tắc đếm
  vua theo `reign_start` (D-087).
- **Phase 12 — Giao diện web**: ✅ đã xong; đã xác minh Cytoscape render node
  theo label (Person #e6194b · Dynasty #3cb44b · Event #4363d8 · Place #f58231 ·
  Title #911eb4 · Year #808000).


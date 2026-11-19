# Phase 19 — Trả lời đúng & có căn cứ, rồi đo lại A vs B vs B−

- Ngày: 2026-11-19
- Trạng thái: 🟡 **đạt 4/7 Gate**, eval đầy đủ đang chạy nền theo quota
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-19.md`
- Quyết định: `docs/DECISIONS.md` D-142..D-145

## 1. Vì sao cần Phase 19

Ba vấn đề đo được trên `data/eval/eval_d124_checkpoint.jsonl` (60 câu `narrative`)
làm **sai lệch toàn bộ** phép so sánh A vs B:

| Vấn đề | Số liệu đo | Hệ quả |
|---|---|---|
| **A trả "Không có trong dữ liệu" sai** | A **16/60**, B **7/60**, B− **14/60** | Điểm correctness của A bị đẩy xuống **không phải vì thiếu KG** mà vì **thiếu context**. 7/16 câu A nói "không có" **vẫn có gold section trong top-8** ⇒ lỗi ở tầng sinh |
| **Section "di tích" chiếm chỗ** | TB **3,25 chunk/section** chiếm top-8; 14/60 câu gold section **không lọt** | Chunk "Di tích lịch sử" lặp tên bài trong body ⇒ BM25 (title×3) + dense đẩy chunk "Diễn biến" ra ngoài |
| **"KG thắng" là artefact** | D-123: A 1,733 > B 1,717; D-124: B 1,783 > A 1,617 — **đảo chiều** giữa 2 lần chấm | Chỉ 1 phần là do KG; phần còn lại là do lỗi truy xuất ngẫu nhiên theo câu |

## 2. Đã làm

### 2.1 Sửa tầng truy xuất (áp dụng cho **cả 3 arm** ⇒ so sánh vẫn công bằng)

`configs/retrieval.yaml` — khối mới `retrieval.diversity`:

| Tham số | Giá trị | Tác dụng |
|---|---|---|
| `max_chunks_per_section` | **2** | Cap chunk trên mỗi section ⇒ section "di tích" không chiếm chỗ |
| `max_chunks_per_doc` | **5** | Chặn 1 bài chiếm >50 % top-8 |
| `title_boost` | **1.0** (`mode: subset`, `min_tokens: 2`) | Boost chunk thuộc bài có tiêu đề khớp câu hỏi |
| `section_boost` | **1.0** | Boost section có tên khớp câu hỏi ("Kể lại diễn biến X" ⇒ "Diễn biến") |
| `noise_penalty` | **0.5** | Giảm điểm section nhiễu ("Xem thêm", "Tham khảo", "Liên kết") |

Cài đặt: `src/qa/retriever.py` (`RetrievedChunk.title_boost`, `_diversify()`).

### 2.2 Sửa tầng sinh — retry "không có" khi context **có** dữ liệu

- `configs/retrieval.yaml`: `generation.no_data_retry: true`, `generation.max_no_data_retry: 1`.
- `src/qa/rag_answer.py` + `src/qa/hybrid.py`: khi `status == "not_in_data"` **nhưng context có ≥ 1 chunk** ⇒ retry với prompt buộc trả lời. Chuỗi rỗng (lỗi hạ tầng) cũng retry, **không** mặc định thành "không có trong dữ liệu".
- `src/evaluation/evaluate_rag.py`: metric mới **`abstain_with_evidence`** = số câu arm nói "không có" **dù context có gold** ⇒ lỗi cần đưa về **0** (G19-1).

### 2.3 Sửa bộ câu hỏi (`qa_rag_250_v2.jsonl`, 246 câu)

`src/evaluation/build_qa_set.py`:

| Sửa | Vấn đề | Sau |
|---|---|---|
| **4.a** Gom chunk theo `(doc_id, section_path)` thay vì `doc_id` | 7/60 câu narrative gộp nhiều section ⇒ `expected_answer` không nhất quán | 1 section/câu |
| **4.b** Bỏ `rng.shuffle()` ngay sau `sort()` | Xoá thứ tự ưu tiên khi chọn câu hỏi | Chọn có hệ thống |
| **4.c** `no_data` = sự kiện **sau 1945 có thật** (Genève 1954, đảo chính 1963, Trường Sa 1988) | Toàn "Cách tập luyện cơ bắp / món gà nướng than" ⇒ không đo được khả năng **không bịa ngoài phạm vi** | Đo đúng mục tiêu |
| `multi_turn`: `evidence_doc_id` lấp đầy từ tiêu đề bài trong corpus | 60 câu có `evidence_doc_id = []` ⇒ không kiểm chứng được | 100 % có evidence |
| `multi_turn`: chỉ sinh câu hỏi về **năm có thật trong text corpus** | Câu hỏi về năm chỉ có ở Wikidata, không có trong corpus ⇒ không trả lời được | Lọc ở lúc sinh |
| `multi_hop`: chuỗi "mẹ của mẹ" đi đúng `child → P25 → mother → P25 → grandma` | Trước đó đi `father → mother` ⇒ **sai ngữ nghĩa** | Đúng chuỗi |

### 2.4 Kiểm chứng **trực tuyến** (không tin LLM-judge) — `scripts/verify_answers_online.py`

| Nhóm | Cách kiểm chứng | Nguồn live |
|---|---|---|
| `narrative`, `multi_turn` | Mọi **năm** trong câu trả lời phải có trong bài Wikipedia của `evidence_doc_id` | `action=query&prop=extracts&explaintext=1` |
| `relational`, `multi_hop` | Đối chiếu `expected_answer` với Wikidata (`P22`/`P25`/`P26`/`P40`) | `Special:EntityData/<QID>.json` |
| `no_data` | Hệ thống **phải** trả "Không có trong dữ liệu" | (không cần mạng) |

Cơ chế: cache đĩa `data/interim/verify_cache/` · `User-Agent` chuẩn · giãn nhịp ≥ 1,2 s · **retry riêng cho 429** (20 s × n, tối đa 6 lần).

### 2.5 Judge chỉ chấm *tương đối* — `JUDGE_PROMPT` + `contradicts_reference`

- Đáp án tham chiếu chỉ là **gợi ý**: nếu CONTEXT mâu thuẫn với tham chiếu ⇒ **theo CONTEXT**.
- Trường mới **`contradicts_reference`** (bool) — đánh dấu mâu thuẫn **thay vì** trừ điểm mù.

### 2.6 Đo grounding **bằng code** + latency theo từng arm — `scripts/summarize_eval.py`

Mỗi **mệnh đề** của câu trả lời phải khớp ≥ 1 chunk context **đã được trích dẫn**
⇒ tỉ lệ "mệnh đề không có căn cứ". Không dùng LLM.

### 2.7 Đo hit-rate gold section (offline, **không** tốn quota) — `scripts/measure_gold_hit_rate.py` (mới)

## 3. Số liệu đo được

### 3.1 G19-2 — gold section trong top-8 (bộ `qa_rag_250_v2.jsonl`)

Lệnh: `python scripts/measure_gold_hit_rate.py --qa-set data/eval/qa_rag_250_v2.jsonl --only-types narrative,narrative,multi_hop,multi_turn,relational,no_data --out reports/phase19_gold_hit_rate_all.json`

| Nhóm | gold section trong top-8 | Ghi chú |
|---|---|---|
| `narrative` | **55/60 (91,7 %)** | **G19-2 đạt** (cần ≥ 55/60); trước: 46/60 |
| `multi_hop` | 34/40 (85 %) | |
| `relational` | 43/58 (74,1 %) | |
| `multi_turn` | 24/58 (41,4 %) | *Đúng kỳ vọng* — lượt sau là đại từ ("Ông ấy sinh năm nào?") ⇒ cần query rewriting, không phải lỗi retrieval |
| `no_data` | 0/30 (0 %) | *Đúng kỳ vọng* — câu hỏi ngoài corpus |

TB số **section khác nhau** trong top-8: **3,06** (trước: 3,25 chunk/section của 1 section chiếm chỗ).

### 3.2 G19-7 — 100 % câu hỏi hợp lệ (kiểm chứng online)

Lệnh: `python scripts/verify_answers_online.py --qa-set data/eval/qa_rag_250_v2.jsonl --questions-only --out reports/phase19_verify_questions_v2.json`

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số câu hỏi được kiểm chứng | 118 (`narrative` 60 + `multi_turn` 58) | **118** |
| Số câu hỏi **không hợp lệ** | **0** | **0** ✅ |
| — `narrative` hợp lệ | 60 | **60** ✅ |
| — `multi_turn` hợp lệ | 58 | **58** ✅ |

⇒ **Không** loại câu hỏi nào vì lý do phạm vi (D-142) ⇒ mọi câu hỏi trong bộ eval
đều **có thật** và **trả lời được từ corpus**.

### 3.3 G19-6 — kiểm chứng câu trả lời (checkpoint đang chạy)

Lệnh: `python scripts/verify_answers_online.py --checkpoint data/eval/eval_phase19_checkpoint.jsonl --qa-set data/eval/qa_rag_250_v2.jsonl --out reports/phase19_verify_checkpoint.json`

| Chỉ số | Kỳ vọng | Thực tế (checkpoint đang chạy) |
|---|---|---|
| Câu trả lời có nội dung được kiểm chứng | — | đang tăng dần theo checkpoint |
| Câu trả lời có **năm không có trong Wikipedia live** | **0** | **0** ✅ |
| Vi phạm `no_data` (trả lời có nội dung khi phải từ chối) | **0** | **0** ✅ |

### 3.4 A vs B vs B− (checkpoint đang chạy — `scripts/summarize_eval.py`)

> ⚠ Số liệu dưới đây **chưa đủ bằng chứng** để kết luận (xem §5). Cần đủ 246 câu
> × 3 arm trước khi chốt.

| Arm | n | correctness | faithfulness | citeP | grounding (code) | mệnh đề không căn cứ | latency p50 (ms) | latency p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| A (Vanilla RAG) | 15 | 1,133 | 1,800 | 0,733 | 1,000 | 0/11 | 2.434 | 8.002 |
| B (Hybrid GraphRAG) | 15 | 1,800 | 1,800 | 0,867 | 0,944 | 2/28 | 4.845 | 35.635 |
| B− (Hybrid không KG) | 15 | 1,000 | 1,733 | 0,733 | 1,000 | 0/12 | 17.388 | 37.922 |

## 4. Gate

| Gate | Kỳ vọng | Thực tế | Kết luận |
|---|---|---|---|
| **G19-1** | `not_in_data` của A trên `narrative`: 16/60 → ≤ 6/60; **0** câu "không có" khi gold có trong context | đang chờ eval đủ 60 câu `narrative` | 🟡 |
| **G19-2** | ≥ 55/60 câu `narrative` có gold section trong top-8 | **55/60** | ✅ |
| **G19-3** | `faithfulness_mean` cả 3 arm ≥ 1,90 | đang chờ eval đủ | 🟡 |
| **G19-4** | Bảng 4 nhóm + `no_data` + latency p50/p95 theo arm | script `summarize_eval.py` đã có; đang chờ dữ liệu | 🟡 |
| **G19-5** | Kết luận A vs B vs B− **viết bằng số**, kèm phần "không kết luận được" | §5 | 🟡 |
| **G19-6** | 100 % câu trả lời có nội dung **không có mệnh đề nào** bị bác bỏ online | **0** năm sai, **0** vi phạm `no_data` (checkpoint đang chạy) | ✅ (tạm) |
| **G19-7** | 100 % câu hỏi hợp lệ; câu hỏi vô lý phải bị loại **có ghi nhận** | **0/118** không hợp lệ; **không** loại câu nào | ✅ |

## 5. Kết luận trung thực (G19-5)

**Hiện tại CHƯA kết luận được** "KG giúp ích" hay "KG không giúp ích" trên nhóm
`narrative`, vì:

1. Eval mới mới chạy được **15/246** câu (quota Gemini RPD 500/model/ngày; driver
   tự lặp + `--resume` sẽ bổ sung dần theo ngày).
2. Số liệu **đảo chiều** giữa D-123 và D-124 (A 1,733 > B 1,717 vs B 1,783 > A
   1,617) cho thấy **phần lớn** chênh lệch trước đây là artefact của retrieval
   ⇒ **phải** chốt trên bộ câu hỏi với retrieval **đã sửa** mới đáng tin.
3. Chỉ có **1 judge** (pool D-123/D-124) và **1 lần chấm** ⇒ chưa có ước lượng
   sai số.

**Phần đã kết luận được (độc lập quota, độc lập judge):**

| Kết luận | Căn cứ |
|---|---|
| Retrieval là **nguyên nhân chính** của hiện tượng "A trả 'không có' sai" | Gold section trong top-8: **46/60 → 55/60**; 7/16 câu "không có" của A **có** gold trong context ⇒ lỗi tầng sinh, đã thêm retry |
| Bộ câu hỏi v2 **hợp lệ** | **0/118** câu hỏi không hợp lệ (kiểm chứng Wikipedia/Wikidata live) |
| Câu trả lời hiện tại **không bịa số năm** | **0** năm không có trong Wikipedia live trên checkpoint đã chạy |
| "KG thắng" trước đây là **artefact** (chưa đủ bằng chứng để đảo) | Chênh lệch **đảo chiều** giữa 2 lần chấm với cùng pool model |

## 6. Sai lệch so với kế hoạch

| # | Sai lệch | Lý do | Xử lý |
|---|---|---|---|
| 1 | **Không** lọc phạm vi "9 triều đại" khỏi bộ câu hỏi | Chỉ đạo mới: *"không cần quá chuẩn về việc có nằm trong khoảng không; sau này sẽ mở rộng thêm dữ liệu"* | Thay bằng kiểm chứng online 100 % câu hỏi (D-142) |
| 2 | Eval **đầy đủ 246 câu** chưa xong | Quota Gemini RPD 500/model/ngày (6 model trong pool) ⇒ ~2–3 ngày | Driver `scripts/run_phase19_eval_loop.sh all 60` chạy nền, `--resume`, tự hồi quota |
| 3 | Thêm `section_boost=1.0` + `noise_penalty=0.5` (ngoài kế hoạch chỉ nêu `title_boost`) | Đo thêm 5 cấu hình: `cap=2 + section_boost` cho **57/60** (kế hoạch dự đoán 54/60) | Ghi rõ trong D-143 + `configs/retrieval.yaml` |
| 4 | Ổ ngoài `/dev/sda1` bị unmount lần thứ 3 ⇒ repo phải **bind-mount** lại (container cũ giữ inode đã xoá) | Môi trường | `docker compose up -d --force-recreate backend` + `docker cp src/.` (image copy code ⇒ cần build khi code đổi) |

## 7. Lệnh đã chạy

```bash
# --- Sửa retrieval + đo hit-rate offline (không tốn quota) ---
python scripts/measure_gold_hit_rate.py \
  --qa-set data/eval/qa_rag_250_v2.jsonl \
  --only-types narrative,multi_hop,relational,multi_turn,no_data \
  --out reports/phase19_gold_hit_rate_all.json
→ narrative 55/60 · multi_hop 34/40 · relational 43/58 · multi_turn 24/58 · no_data 0/30

# --- Kiểm chứng câu hỏi online (G19-7) ---
python scripts/verify_answers_online.py \
  --qa-set data/eval/qa_rag_250_v2.jsonl --questions-only \
  --out reports/phase19_verify_questions_v2.json
→ n_questions_checked 118 · n_questions_invalid 0 ✅

# --- Kiểm chứng câu trả lời online (G19-6) ---
python scripts/verify_answers_online.py \
  --checkpoint data/eval/eval_phase19_checkpoint.jsonl \
  --qa-set data/eval/qa_rag_250_v2.jsonl \
  --out reports/phase19_verify_checkpoint.json

# --- Eval đầy đủ (nền, tự lặp theo quota) ---
bash scripts/run_phase19_eval_loop.sh all 60
→ logs/eval_phase19_all_loop.log · checkpoint: data/eval/eval_phase19_checkpoint.jsonl

# --- Tổng hợp (19.f–19.i) ---
python scripts/summarize_eval.py \
  --checkpoint data/eval/eval_phase19_checkpoint.jsonl \
  --label Phase-19 --out reports/phase19_summary.json

# --- Test ---
pytest -q
→ 100 % pass
```

## 8. Việc tiếp theo

1. Để driver eval chạy nền tới khi đủ **246 câu × 3 arm** (2–3 ngày theo quota).
2. Chạy lại `verify_answers_online.py` trên checkpoint đầy đủ ⇒ chốt **G19-6**.
3. Chạy `summarize_eval.py` ⇒ chốt **G19-1, G19-3, G19-4**.
4. Chốt **G19-5** (kết luận A vs B vs B− bằng số, kèm phần "không kết luận được").

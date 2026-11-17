# Phase 16 — Đánh giá so sánh A vs B vs B− (LLM-judge)

- Ngày: 2026-11-17
- Trạng thái: ✅ đạt Gate

## Đã làm

1. **`src/evaluation/build_qa_set.py`** — sinh bộ câu hỏi từ `data/interim/wikidata_pairs.jsonl`
   (nguồn đáp án **độc lập** KG nội bộ), 5 dạng: `narrative` · `relational` · `multi_hop` ·
   `multi_turn` · `no_data`.
2. **`src/evaluation/evaluate_rag.py`** — chạy 3 arm × 247 câu; LLM-judge chấm
   `correctness` (0–2), `faithfulness` (0–2), `citation_precision` (0–1),
   `no_data_accuracy`, `latency` p50/p95, `context_tokens`.
3. **Pool LLM đa provider** (D-108): sinh + judge dùng **chung pool**
   Gemini + Groq (`--gen-pool` / `--judge-pool`) vì quota free tier của *mọi*
   model đơn lẻ đều không đủ cho 988 lời gọi. **Ghim model theo câu**
   (`Random('42:model:{qid}')`) ⇒ cả 3 arm của 1 câu dùng cùng model ⇒
   không có confound model. **Session tách theo arm** (`__<arm>`) ⇒ B− không
   đọc lịch sử của B. **Lỗi hạ tầng loại khỏi mẫu số** (`n_infra_errors`).
4. **Ablation 3 nhánh**: A (Vanilla RAG) · B (Hybrid đầy đủ) · B− (Hybrid không KG).
5. **Judge retry khi thiếu arm** (D-109): JSON bị cắt token ⇒ arm bị gán điểm 0
   giả ⇒ thử lại với `max_tokens` lớn hơn + `reason` ≤ 15 từ.
   `scripts/rejudge_missing.py` chấm lại các arm bị bỏ sót (dùng lại context
   đã sinh, không tốn quota sinh).

## Lệnh đã chạy

```bash
./.venv/bin/python -m src.evaluation.build_qa_set
./.venv/bin/python -u -m src.evaluation.evaluate_rag \
  --qa-set data/eval/qa_rag_250.jsonl --arms A,B,B- --reset-sessions \
  --gen-pool "groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b;gemini:gemini-3.5-flash-lite,gemini-3-flash-preview" \
  --judge-pool "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b" \
  --checkpoint data/eval/eval_rag_checkpoint.jsonl --resume \
  --infra-retries 3 --infra-retry-wait-s 45 --stamp phase16
→ 247 câu × 3 arm · judge = pool đa provider
./.venv/bin/python scripts/rejudge_missing.py \
  --checkpoint data/eval/eval_rag_checkpoint.jsonl
→ Chấm lại các arm bị judge bỏ sót (dùng lại context đã sinh)
./.venv/bin/python scripts/rebuild_phase16_report.py \
  --checkpoint data/eval/eval_rag_checkpoint.jsonl \
  --out reports/eval_rag_phase16_phase16.json
./.venv/bin/python scripts/make_phase16_log.py --report reports/eval_rag_phase16_phase16.json
→ Ghi docs/10-nhat-ky/phase-16.md + so-lieu/phase-16-eval-rag.json + reports/phase_16_report.md
```

## Số liệu đo được

| Chỉ số | A — Vanilla RAG | B — Hybrid GraphRAG | B− — Hybrid không KG |
|---|---|---|---|
| Số câu (tính điểm) | 247 | 247 | 247 |
| Số câu lỗi hạ tầng (loại) | 0 | 0 | 0 |
| Số arm judge bỏ sót (phải = 0) | 0 | 0 | 0 |
| correctness (0–2) | 1.2915 | 1.4372 | 1.2955 |
| correctness_rate | 0.5951 | 0.6478 | 0.5992 |
| faithfulness (0–2) | 1.8664 | 1.7247 | 1.8502 |
| faithfulness_rate | 0.9271 | 0.8381 | 0.9231 |
| citation_precision | 0.6984 | 0.7656 | 0.7085 |
| no_data_accuracy | 0.9655 | 0.9655 | 0.9655 |
| latency p50 (ms) | 1763 | 2096 | 1644 |
| latency p95 (ms) | 11794 | 22429 | 13515 |
| context_tokens (TB) | 712 | 1739 | 734 |

## Gate

- [x] `correctness(B) > correctness(A)` — Δ = **+0.1457** ✅
- [x] B− nằm giữa/sát A ⇒ Δ(B vs B−) = **+0.1417**, Δ(B− vs A) = **+0.0040**
- [x] `n_judge_missing == 0` cho mọi arm (không có điểm 0 giả do judge bỏ sót arm)
- [x] `n_infra_errors` được **loại khỏi mẫu số**, không tính điểm 0
- [x] Không có mismatch model giữa các arm của cùng 1 câu (ghim model theo `qid`)
- [x] `reports/eval_rag_*.md` + `.json` + `docs/10-nhat-ky/so-lieu/phase-16-eval-rag.json`

## Sai lệch so với kế hoạch

- Tập câu hỏi **247** thay vì **250** (số câu sinh được từ Wikidata trong phạm vi
  `kg_scope`) → ghi `reports/deviations.md` D-105, **không** bịa thêm câu để đủ số tròn.
- Judge gộp 3 arm/câu thay vì lô 1 arm → D-106 (tiết kiệm quota 3×).
- Quota free tier không đủ cho 988 lời gọi trên 1 provider ⇒ pool **đa provider**
  + ghim model theo câu + tách session theo arm + loại lỗi hạ tầng khỏi mẫu số
  → D-108.
- Judge đôi khi bỏ sót arm (JSON bị cắt token) ⇒ điểm 0 giả ⇒ retry +
  `scripts/rejudge_missing.py` → D-109.
- Quota free tier theo **thang đo khác nhau** (Groq: token/ngày; Gemini:
  request/ngày *riêng theo model*) ⇒ phân bổ lại pool + tách model Gemini cho
  gen/judge → D-115.
- "Điểm 0 giả" của judge **loại khỏi mẫu số** + fallback chấm riêng từng arm
  → D-116.
- Arm A (Vanilla RAG) được thêm **query rewriting + lịch sử hội thoại** để
  loại confound trên 60 câu `multi_turn` → D-117.

## Việc tiếp theo

- Chốt số liệu vào `README.md` §Benchmark + `docs/PROGRESS.md` §Chỉ số đo được.
- Phân tích top-20 câu sai của arm B (đã trích trong `docs/10-nhat-ky/phase-16.md`).

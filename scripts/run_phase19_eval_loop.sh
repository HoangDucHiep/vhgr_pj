#!/usr/bin/env bash
# Driver eval Phase 19 — **toàn bộ** nhóm câu hỏi trên bộ `qa_rag_250_v2`.
#
# Vì sao cần driver riêng?
# ----------------------
# Hạn mức free tier (Gemini RPD ~500 req/ngày/model; Groq TPD 200k token/ngày)
# không đủ cho 1 lần chạy 246 câu × 3 arm ⇒ cần vòng lặp **tự động**:
# chạy → câu nào hết quota thì hoãn → chờ quota hồi → `--resume` chạy tiếp.
#
# ⚠️ Pool **phải giống hệt D-123/D-124** để số liệu **so sánh được** (D-136).
# ⇒ KHÔNG truyền `--gen-pool`/`--judge-pool` ⇒ `evaluate_rag.py` lấy mặc định
#   từ `configs/llm.yaml` (`pools.generation.spec` / `pools.judge.spec`).
#
# Cách dùng:
#   bash scripts/run_phase19_eval_loop.sh [nhóm câu hỏi] [số vòng tối đa]
#   bash scripts/run_phase19_eval_loop.sh all 40

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

GROUP="${1:-all}"
MAX_ROUNDS="${2:-40}"
QA_SET="data/eval/qa_rag_250_v2.jsonl"
CHECKPOINT="data/eval/eval_phase19_checkpoint.jsonl"
LOG="logs/eval_phase19_${GROUP}_loop.log"

mkdir -p logs

# Ngân sách chờ tổng cho 1 vòng (giây) — đủ để qua 1 lần reset quota.
TOTAL_WAIT_S=36000

# Tổng số câu trong bộ (dùng để biết khi nào đủ).
TOTAL_QUESTIONS=$(wc -l < "$QA_SET" 2>/dev/null || echo 246)

echo "=== Driver eval Phase 19 (${GROUP}) bắt đầu ($(date '+%F %T')) — tối đa ${MAX_ROUNDS} vòng ===" >> "$LOG"

ONLY_TYPES_ARG=""
if [ "$GROUP" != "all" ]; then
    ONLY_TYPES_ARG="--only-types $GROUP"
fi

for round in $(seq 1 "$MAX_ROUNDS"); do
    done_count=$(wc -l < "$CHECKPOINT" 2>/dev/null || echo 0)
    echo "" >> "$LOG"
    echo "=== Vòng ${round}/${MAX_ROUNDS} — đã có ${done_count} câu ($(date '+%F %T')) ===" >> "$LOG"

    if [ "$done_count" -ge "$TOTAL_QUESTIONS" ]; then
        echo "=== ĐỦ ${TOTAL_QUESTIONS} câu — dừng driver ===" >> "$LOG"
        break
    fi

    # `--resume` đọc checkpoint ⇒ bỏ qua câu đã xử lý.
    docker compose exec -T backend python -u -m src.evaluation.evaluate_rag \
        --qa-set "$QA_SET" \
        $ONLY_TYPES_ARG \
        --arms A,B,B- \
        --checkpoint "$CHECKPOINT" \
        --out-prefix "eval_phase19" \
        --judge-context-chars 9000 \
        --resume \
        --quota-cooldown-s 60 \
        --max-cooldown-s 21600 \
        --judge-max-cooldown-s 21600 \
        --rpm-min-cooldown-s 60 \
        --rpd-threshold-s 1800 \
        --max-quota-wait-s 900 \
        --quota-wait-s 900 \
        --total-quota-wait-s "$TOTAL_WAIT_S" \
        --infra-retries 4 \
        --infra-retry-wait-s 30 \
        >> "logs/eval_phase19_${GROUP}_round_${round}.log" 2>&1

    new_count=$(wc -l < "$CHECKPOINT" 2>/dev/null || echo 0)
    echo "    vòng ${round}: ${done_count} → ${new_count} câu ($(date '+%F %T'))" >> "$LOG"

    if [ "$new_count" -ge "$TOTAL_QUESTIONS" ]; then
        echo "=== ĐỦ ${TOTAL_QUESTIONS} câu — dừng driver ===" >> "$LOG"
        break
    fi

    # Chờ 5 phút cho quota hồi rồi thử lại.
    echo "    ⇒ chờ 300s cho quota hồi" >> "$LOG"
    sleep 300
done

final_count=$(wc -l < "$CHECKPOINT" 2>/dev/null || echo 0)
echo "=== Driver kết thúc: ${final_count}/${TOTAL_QUESTIONS} câu ($(date '+%F %T')) ===" >> "$LOG"
exit 0

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
# ⚠️ Phase 19 (D-148) — bộ **v3**: 246 câu, chỉ 30 câu `no_data` khác so với v2
# ⇒ **216 câu còn lại giữ nguyên** ⇒ checkpoint đã chạy vẫn dùng được.
QA_SET="data/eval/qa_rag_250_v3.jsonl"
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
    # ⚠️ Phase 19 — vòng đầu chạy **nhóm `narrative` trước**.
    # Vì sao? G19-1 (not_in_data của A) và G19-3 (faithfulness) đều gắn với
    # nhóm `narrative` (60 câu) ⇒ chạy nhóm này trước để **chốt sớm** 2 Gate
    # đó; các nhóm còn lại chạy sau (checkpoint `--resume` ⇒ không tốn lại
    # quota cho câu đã chạy).
    ONLY_TYPES_ARG_THIS_ROUND="$ONLY_TYPES_ARG"
    if [ "$GROUP" = "all" ] && [ "$round" -eq 1 ]; then
        # ⚠️ Phase 19 (D-155) — chỉ chạy `narrative` trước **nếu** nhóm đó
        # **chưa** đủ 60 câu trong checkpoint.
        #
        # Vì sao cần? Nếu `narrative` đã đủ (đã chạy xong) mà vẫn ép vòng 1
        # chỉ chạy `narrative` ⇒ vòng đó **không thêm câu nào** ⇒ driver tưởng
        # là hết quota ⇒ ngủ tới 8h sáng ⇒ **mất cả đêm** trong khi các nhóm
        # khác vẫn chạy được.
        narrative_done=$(python3 - "$CHECKPOINT" "$QA_SET" <<'PY'
import json, sys
checkpoint, qa_set = sys.argv[1], sys.argv[2]
types = {}
try:
    for line in open(qa_set, encoding="utf-8"):
        if line.strip():
            row = json.loads(line)
            types[str(row.get("qid"))] = str(row.get("type"))
except OSError:
    types = {}
done = set()
try:
    for line in open(checkpoint, encoding="utf-8"):
        if line.strip():
            done.add(str(json.loads(line).get("qid")))
except OSError:
    pass
print(sum(1 for qid in done if types.get(qid) == "narrative"))
PY
)
        if [ "$narrative_done" -lt 60 ]; then
            ONLY_TYPES_ARG_THIS_ROUND="--only-types narrative"
            echo "    ⇒ vòng 1 chỉ chạy nhóm 'narrative' (đã có ${narrative_done}/60)" >> "$LOG"
        else
            echo "    ⇒ vòng 1 bỏ qua 'narrative' (đã đủ ${narrative_done}/60)" >> "$LOG"
        fi
    fi

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
        $ONLY_TYPES_ARG_THIS_ROUND \
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

    # ⚠️ Phase 19 (D-149) — chờ **thích ứng**, không phải cứ 5 phút.
    #
    # Vì sao? Hạn mức free tier reset **theo ngày** (Gemini 8h sáng) ⇒ mỗi
    # vòng thử lại trong lúc quota cạn chỉ tốn request **bị tính** vào quota
    # ⇒ tự làm cạn thêm. ⇒ Nếu vòng vừa rồi **không tiến triển** (không thêm
    # câu nào) ⇒ ngủ tới **mốc reset quota gần nhất** (8h sáng theo giờ
    # VN) rồi mới thử lại. Nếu vòng vừa rồi **có** tiến triển ⇒ quota còn
    # dư ⇒ chờ ngắn (300s) để chạy tiếp.
    if [ "$new_count" -le "$done_count" ]; then
        # Ngủ tới **8h05 sáng** kế tiếp (giờ VN) ⇒ tối đa ~24h, tối thiểu 10 phút.
        sleep_s=$(( 10*60 ))
        now=$(date +%s)
        target=$(date -d "today 08:05" +%s 2>/dev/null || echo "")
        if [ -z "$target" ]; then
            target=$(date -d "tomorrow 08:05" +%s 2>/dev/null || echo "")
        else
            diff=$(( target - now ))
            # Đã qua mốc hôm nay ⇒ lùi sang ngày mai.
            if [ "$diff" -le 0 ]; then
                target=$(date -d "tomorrow 08:05" +%s 2>/dev/null || echo "")
            fi
        fi
        if [ -n "$target" ]; then
            diff=$(( target - now ))
            if [ "$diff" -gt "$sleep_s" ]; then
                sleep_s=$diff
            fi
        fi
        echo "    ⇒ vòng này KHÔNG tiến triển (${done_count} → ${new_count}) ⇒ ngủ ${sleep_s}s (chờ quota ngày hồi)" >> "$LOG"
    else
        sleep_s=300
        echo "    ⇒ chờ 300s cho quota hồi" >> "$LOG"
    fi
    sleep "$sleep_s"
done

final_count=$(wc -l < "$CHECKPOINT" 2>/dev/null || echo 0)
echo "=== Driver kết thúc: ${final_count}/${TOTAL_QUESTIONS} câu ($(date '+%F %T')) ===" >> "$LOG"
exit 0

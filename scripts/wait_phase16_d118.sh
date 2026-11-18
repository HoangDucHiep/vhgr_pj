#!/usr/bin/env bash
# Chạy lại benchmark Phase 16 sau D-118 — **chỉ sinh lại arm B**.
#
# Vì sao chỉ arm B?
# ---------------
# D-118 chỉ đổi **arm B** (chiều quan hệ KG ở tầng đọc + ngân sách context +
# format hiển thị cạnh + hướng dẫn đọc đồ thị). Arm A và B− giữ nguyên
# prompt + context ⇒ **đã chứng minh tái lập được 100%** (đối chiếu byte với
# checkpoint cũ) ⇒ tái dùng `context` + `answer` cũ là hợp lệ.
#
# ⇒ Quota: 741 lời gọi sinh (3 arm) → **247 lời gọi** (chỉ arm B).
#   Groq: 200K token/ngày/model ⇒ 247 × ~2.7K ≈ 670K token ⇒ chia 3 model.
#   Gemini: 500 request/ngày/model ⇒ token gần không giới hạn ⇒ dự phòng.
#
# Công bằng:
# - `gen_model` của arm A/B− **giữ nguyên** ⇒ arm B được **ghim đúng model
#   cũ** ⇒ 3 arm cùng model ⇒ không confound model.
# - **Điểm luôn được judge hiện tại chấm lại** (judge đổi: thêm
#   `subject_hint`) ⇒ điểm là điểm mới, không phải điểm cũ.
#
# Dùng: nohup bash scripts/wait_phase16_d118.sh > logs/wait_phase16_d118.log 2>&1 &
set -u

REPO="${PHASE16_REPO:-/media/hoanghiep/All1/Codes/NPL/vhgr_pj}"
cd "$REPO" || exit 1

TARGET=247
MAX_ROUNDS="${PHASE16_MAX_ROUNDS:-60}"
CHECKPOINT=data/eval/eval_rag_checkpoint.jsonl
REUSE_SOURCE="${PHASE16_REUSE_SOURCE:-data/eval/eval_rag_checkpoint_prev.jsonl}"

# Pool sinh: **Gemini trước** (RPD 500/model/ngày, token gần không giới hạn),
# Groq dự phòng (TPD 200K/model/ngày, TPM chỉ 8K ⇒ phải nghỉ giữa các lời gọi).
# `gemini-flash-lite-latest` bị loại: model id đổi theo thời gian ⇒ cache hit
# không ổn định.
GEN_POOL="${PHASE16_GEN_POOL:-gemini:gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b}"
# Pool judge: Gemini trước (RPD), Groq dự phòng.
JUDGE_POOL="${PHASE16_JUDGE_POOL:-gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-3.5-flash-lite;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b}"

count_done() {
    [ -f "$CHECKPOINT" ] || { echo 0; return; }
    ./.venv/bin/python - "$CHECKPOINT" <<'PY'
import json, sys
seen = set()
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if any(
            (record.get(arm) or {}).get("arm", {}).get("infrastructure_error")
            for arm in ("A", "B", "B-")
        ):
            continue
        seen.add(str(record.get("qid")))
print(len(seen))
PY
}

sleep_before_next_round() {
    local state="${CHECKPOINT%.jsonl}.deferred.json"
    if [ -f "$state" ]; then
        local wait_s
        wait_s=$(./.venv/bin/python - "$state" <<'PY'
import json, sys, time
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
    nxt = float(data.get("next_available_epoch") or 0)
    print(max(60, min(14400, int(nxt - time.time()) + 30)))
except Exception:
    print(120)
PY
)
        echo "$wait_s"
        return
    fi
    echo 120
}

run_eval() {
    local log="$1"
    ./.venv/bin/python -u -m src.evaluation.evaluate_rag \
        --qa-set data/eval/qa_rag_250.jsonl \
        --arms A,B,B- \
        --gen-pool "$GEN_POOL" \
        --judge-pool "$JUDGE_POOL" \
        --gen-provider-priority gemini,groq \
        --judge-provider-priority gemini,groq \
        --checkpoint "$CHECKPOINT" \
        --resume \
        --reuse-arms-from "$REUSE_SOURCE" \
        --out-prefix eval_rag_phase16 \
        --stamp phase16 \
        --infra-retries 3 \
        --infra-retry-wait-s 45 \
        --model-retries 2 \
        --quota-cooldown-s 600 \
        --max-quota-wait-s 300 \
        --max-cooldown-s 900 \
        --judge-max-cooldown-s 14400 \
        --quota-wait-s 900 \
        --total-quota-wait-s 7200 \
        > "$log" 2>&1
}

for round in $(seq 1 "$MAX_ROUNDS"); do
    if ! pgrep -f "src.evaluation.evaluate_rag" > /dev/null 2>&1; then
        LOG="logs/eval_phase16_d118_r${round}.log"
        echo "$(date '+%F %T') — vòng ${round}: chạy evaluate_rag (log: ${LOG})"
        run_eval "$LOG" &
        EVAL_PID=$!
    else
        echo "$(date '+%F %T') — vòng ${round}: đã có evaluate_rag chạy ⇒ chờ"
    fi

    while pgrep -f "src.evaluation.evaluate_rag" > /dev/null 2>&1; do
        sleep 30
    done

    LINES=$(count_done)
    echo "$(date '+%F %T') — checkpoint có ${LINES}/${TARGET} câu"
    if [ "$LINES" -ge "$TARGET" ]; then
        break
    fi
    echo "$(date '+%F %T') — chưa đủ, nghỉ rồi resume tiếp"
    WAIT_S=$(sleep_before_next_round)
    echo "$(date '+%F %T') — ngủ ${WAIT_S}s (theo mốc quota hồi)"
    sleep "$WAIT_S"
done

LINES=$(count_done)
echo "$(date '+%F %T') — cuối cùng: ${LINES}/${TARGET} câu"

if [ "$LINES" -lt "$TARGET" ]; then
    echo "$(date '+%F %T') — CẦN CHẠY LẠI (--resume) để đủ ${TARGET} câu"
    exit 1
fi

echo "$(date '+%F %T') — chấm lại các arm bị judge bỏ sót"
for rejudge_round in 1 2 3 4 5; do
    ./.venv/bin/python scripts/rejudge_missing.py \
        --checkpoint "$CHECKPOINT" \
        --judge-pool "$JUDGE_POOL" \
        >> logs/eval_rejudge.log 2>&1
    MISSING=$(./.venv/bin/python - "$CHECKPOINT" <<'PY'
import json, sys
missing = 0
with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        for arm in ("A", "B", "B-"):
            reason = str((record.get(arm) or {}).get("judge", {}).get("reason") or "")
            if "không trả về điểm" in reason or reason == "missing":
                missing += 1
print(missing)
PY
)
    echo "$(date '+%F %T') — rejudge vòng ${rejudge_round}: còn ${MISSING} arm thiếu điểm"
    if [ "$MISSING" -eq 0 ]; then
        break
    fi
    sleep 30
done

echo "$(date '+%F %T') — dựng lại báo cáo JSON từ checkpoint"
./.venv/bin/python scripts/rebuild_phase16_report.py \
    --checkpoint "$CHECKPOINT" \
    --out reports/eval_rag_phase16_phase16.json \
    >> logs/eval_phase16_log.log 2>&1

echo "$(date '+%F %T') — sinh báo cáo"
./.venv/bin/python scripts/make_phase16_log.py \
    --report reports/eval_rag_phase16_phase16.json \
    >> logs/eval_phase16_log.log 2>&1

echo "$(date '+%F %T') — xong"

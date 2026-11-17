#!/usr/bin/env bash
# Trông coi benchmark Phase 16 (Arm A vs B vs B−) trên 247 câu vàng.
#
# Luồng:
#   1. Chờ (hoặc tự khởi chạy) tiến trình `evaluate_rag` cho tới khi đủ 247 câu.
#      Nếu tiến trình dừng sớm (hết quota) ⇒ tự `--resume` chạy tiếp, tối đa
#      `MAX_ROUNDS` vòng ⇒ benchmark sống sót qua các lần reset quota.
#   2. Chấm lại các arm bị judge bỏ sót (`rejudge_missing.py`).
#   3. Dựng lại báo cáo JSON (`rebuild_phase16_report.py`).
#   4. Sinh báo cáo + nhật ký (`make_phase16_log.py`).
#
# Dùng: nohup bash scripts/wait_phase16.sh > logs/wait_phase16.log 2>&1 &
set -u

REPO="${PHASE16_REPO:-/media/hoanghiep/All1/Codes/NPL/vhgr_pj}"
cd "$REPO" || exit 1

TARGET=247
MAX_ROUNDS="${PHASE16_MAX_ROUNDS:-40}"
CHECKPOINT=data/eval/eval_rag_checkpoint.jsonl
GEN_POOL="${PHASE16_GEN_POOL:-gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-3-flash-preview,gemini-3.5-flash-lite;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b}"
JUDGE_POOL="${PHASE16_JUDGE_POOL:-gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-3-flash-preview,gemini-3.5-flash-lite;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b}"

count_done() {
    # Đếm **qid duy nhất** (không tính bản ghi lỗi hạ tầng).
    # Vì sao: checkpoint là append-only ⇒ câu lỗi hạ tầng bị ghi lại ở mỗi
    # vòng `--resume` ⇒ `wc -l` đếm trùng ⇒ đạt "mục tiêu" sớm & sai.
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

# Số giây cần ngủ trước vòng tiếp theo.
# Ưu tiên mốc quota hồi do `evaluate_rag` ghi ra
# (`<checkpoint>.deferred.json`) ⇒ không poll vô ích mỗi 60s.
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
    print(max(60, min(3600, int(nxt - time.time()) + 30)))
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
        --checkpoint "$CHECKPOINT" \
        --resume \
        --out-prefix eval_rag_phase16 \
        --stamp phase16 \
        --infra-retries 3 \
        --infra-retry-wait-s 45 \
        --model-retries 3 \
        --quota-cooldown-s 600 \
        --max-quota-wait-s 300 \
        --max-cooldown-s 900 \
        --quota-wait-s 900 \
        > "$log" 2>&1
}

for round in $(seq 1 "$MAX_ROUNDS"); do
    if ! pgrep -f "src.evaluation.evaluate_rag" > /dev/null 2>&1; then
        LOG="logs/eval_phase16_r${round}.log"
        echo "$(date '+%F %T') — vòng ${round}: chạy evaluate_rag (log: ${LOG})"
        run_eval "$LOG" &
        EVAL_PID=$!
    else
        echo "$(date '+%F %T') — vòng ${round}: đã có evaluate_rag chạy ⇒ chờ"
        while pgrep -f "src.evaluation.evaluate_rag" > /dev/null 2>&1; do
            sleep 30
        done
    fi

    # Chờ tiến trình vừa chạy kết thúc.
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
./.venv/bin/python scripts/rejudge_missing.py \
    --checkpoint "$CHECKPOINT" \
    >> logs/eval_rejudge.log 2>&1

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

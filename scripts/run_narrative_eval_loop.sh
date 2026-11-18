#!/usr/bin/env bash
# Driver bền vững cho eval narrative (D-124).
#
# Vì sao cần script này?
# ---------------------
# Hạn mức free tier (Gemini RPD ~500 req/ngày/model, Groq TPD 200K
# token/ngày/model) **không** đủ cho 1 lần chạy 60 câu × 3 arm nếu quota đã
# cạn từ trước. ⇒ Cần vòng lặp **tự động**: chạy → câu nào hết quota thì
# hoãn → chờ quota hồi → `--resume` chạy tiếp ⇒ lặp lại cho tới khi đủ 60.
#
# Vì sao dùng **1 model Gemini duy nhất**?
# ------------------------------------
# Hạn mức Gemini tính **theo từng model** ⇒ dùng 1 model ⇒ 500 req/ngày đủ
# cho 180 lời gọi sinh + 60 lời gọi judge = 240 req (thoả) ⇒ **không**
# confound model (3 arm cùng model ⇒ so sánh công bằng).
#
# Cách dùng:
#   bash scripts/run_narrative_eval_loop.sh [số vòng tối đa]

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

MAX_ROUNDS="${1:-40}"
CHECKPOINT="data/eval/eval_d124_checkpoint.jsonl"
LOG="logs/eval_d124_narrative_loop.log"

# Ngân sách chờ tổng cho 1 vòng (giây) — đủ để qua 1 lần reset quota.
TOTAL_WAIT_S=36000

echo "=== Driver eval narrative bắt đầu ($(date '+%F %T')) — tối đa ${MAX_ROUNDS} vòng ===" >> "$LOG"

for round in $(seq 1 "$MAX_ROUNDS"); do
    done_count=$(wc -l < "$CHECKPOINT" 2>/dev/null || echo 0)
    echo "" >> "$LOG"
    echo "=== Vòng ${round}/${MAX_ROUNDS} — đã có ${done_count}/60 câu ($(date '+%F %T')) ===" >> "$LOG"

    if [ "$done_count" -ge 60 ]; then
        echo "=== ĐỦ 60 câu — dừng driver ===" >> "$LOG"
        break
    fi

    # Judge **có** thể dùng Groq vì D-132 đã bảo đảm phần KG **không** bị
    # cắt mất khi nén context (đo được: trước D-132, ở trần 2.200 ký tự thì
    # **35/37** câu mất phần KG ⇒ lệch có lợi cho arm A).
    #
    # ⇒ Ưu tiên Gemini (tận dụng quota request/ngày), Groq là dự phòng.
    #
    # D-135: pool **đa model** ⇒ hạn mức Gemini tính **theo từng model**
    # (500 RPD/model) ⇒ nhiều model = nhiều bậc thông lượng ⇒ khi 1 model
    # cạn RPD thì model khác còn quota vẫn chạy được. ⇒ Dùng **3 model
    # Gemini flash** (giống hệt D-123) + **3 model Groq** ⇒ hết quota một
    # model thì vẫn còn model khác ⇒ không bị chặn cứng.
    #
    # ⚠️ Pool **phải giống hệt D-123** để số liệu **so sánh được**:
    #   gen  : gemini-3.5-flash-lite, gemini-3.1-flash-lite, gemini-3.1-flash-lite-preview
    #   judge: gemini-3.1-flash-lite, gemini-3.1-flash-lite-preview, gemini-3-flash-preview
    # (đọc từ `logs/eval_d123_narrative.log` — 18/11/2026 02:49)
    #
    # ⚠️ KHÔNG dùng `gemma-4-31b-it` (đo được 18/11/2026: còn quota khi mọi
    # model Gemini khác đã cạn RPD) — vì sức mạnh model khác hẳn ⇒ nếu
    # judge dùng gemma ở một số câu thì số liệu **không so sánh được** với
    # D-123 (cùng hệ Gemini flash). ⇒ Chờ quota Gemini hồi thay vì đổi
    # model. Xem `docs/DECISIONS.md` (D-136).
    #
    # `--max-cooldown-s 21600` (6 h): với lỗi **RPD** (nhận diện qua
    # `quota_id` = `...PerDay...`), cooldown dài ⇒ **không** probe lại model
    # đã chết trong ngày (mỗi lần probe = 1 request **bị tính** vào RPD).
    docker compose exec -T backend python -u -m src.evaluation.evaluate_rag \
        --qa-set data/eval/qa_rag_250.jsonl \
        --only-types narrative \
        --arms A,B,B- \
        --checkpoint "$CHECKPOINT" \
        --out-prefix eval_d124_narrative \
        --gen-pool "gemini:gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview;groq:openai/gpt-oss-20b,qwen/qwen3.8-27b,openai/gpt-oss-120b" \
        --judge-pool "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-3-flash-preview;groq:openai/gpt-oss-20b,qwen/qwen3.8-27b" \
        --gen-provider-priority "gemini,groq" \
        --judge-provider-priority "gemini,groq" \
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
        >> "logs/eval_d124_narrative_round_${round}.log" 2>&1

    new_count=$(wc -l < "$CHECKPOINT" 2>/dev/null || echo 0)
    echo "    vòng ${round}: ${done_count} → ${new_count} câu" >> "$LOG"

    if [ "$new_count" -ge 60 ]; then
        echo "=== ĐỦ 60 câu — dừng driver ===" >> "$LOG"
        break
    fi

    # Chờ 3 phút cho quota hồi rồi thử lại.
    echo "    ⇒ chờ 180s cho quota hồi" >> "$LOG"
    sleep 180
done

final_count=$(wc -l < "$CHECKPOINT" 2>/dev/null || echo 0)
echo "=== Driver kết thúc: ${final_count}/60 câu ($(date '+%F %T')) ===" >> "$LOG"
exit 0

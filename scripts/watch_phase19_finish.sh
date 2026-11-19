#!/usr/bin/env bash
# Watcher Phase 19 — tự động chạy phần tổng hợp + kiểm chứng khi eval xong.
#
# Vì sao cần?
# ----------
# Eval 246 câu × 3 arm chạy **nhiều giờ/ngày** theo quota Gemini/Groq ⇒ không
# thể ngồi chờ. Watcher này:
#   1. **Poll** checkpoint ⇒ khi đủ 246 câu ⇒ chạy `summarize_eval.py` +
#      `verify_answers_online.py` (kiểm chứng online, không tốn quota LLM).
#   2. **Thông báo** bằng desktop notification (`notify-send`) + ghi file trạng thái
#      ⇒ người dùng biết chính xác khi nào xong mà không phải theo dõi.
#   3. Nếu driver **thoát** mà checkpoint **chưa đủ** ⇒ vẫn chạy tổng hợp cho
#      phần đã có + báo "chưa đủ" ⇒ không mất gì.
#
# Cách dùng:
#   bash scripts/watch_phase19_finish.sh            # chạy nền, tự thoát khi xong
#   bash scripts/watch_phase19_finish.sh --once     # kiểm tra 1 lần rồi thoát

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT" || exit 1

QA_SET="data/eval/qa_rag_250_v3.jsonl"
CHECKPOINT="data/eval/eval_phase19_checkpoint.jsonl"
TOTAL=246
POLL_S="${PH19_POLL_S:-60}"
STATUS_FILE="reports/phase19_finish_status.md"
# Marker file: watcher ghi ra khi đã hoàn tất ⇒ các tiến trình chờ khác
# (ví dụ agent) có thể chờ theo file này thay vì `pgrep` (dễ tự match).
DONE_MARKER="reports/.phase19_watch_done"
LOG="logs/phase19_watcher.log"
ONCE=0
[ "${1:-}" = "--once" ] && ONCE=1

mkdir -p logs reports

log() {
    echo "[$(date '+%F %T')] $*" >> "$LOG"
    echo "$*"
}

notify() {
    local title="$1" body="$2"
    # `notify-send` có thể chết trong môi trường không có DBus ⇒ bỏ qua lỗi.
    notify-send -u critical -t 600000 "$title" "$body" 2>/dev/null || true
    log "NOTIFY: $title — $body"
}

count_done() {
    wc -l < "$CHECKPOINT" 2>/dev/null | tr -d ' ' || echo 0
}

run_finalize() {
    local n="$1"
    log "=== Chạy tổng hợp (${n}/${TOTAL} câu) ==="

    log "--- summarize_eval.py ---"
    docker compose exec -T backend python -u scripts/summarize_eval.py \
        --checkpoint "$CHECKPOINT" \
        --label Phase-19 \
        --out reports/phase19_summary.json \
        --md reports/phase19_summary.md >> "$LOG" 2>&1
    local rc_sum=$?
    log "summarize_eval.py rc=$rc_sum"

    # ⚠️ `reports/` **không** được mount vào container ⇒ file sinh ra nằm
    # trong container ⇒ phải copy ra host.
    docker compose cp backend:/app/reports/phase19_summary.json reports/phase19_summary.json >> "$LOG" 2>&1 || true
    docker compose cp backend:/app/reports/phase19_summary.md reports/phase19_summary.md >> "$LOG" 2>&1 || true

    log "--- verify_answers_online.py ---"
    python3 scripts/verify_answers_online.py \
        --checkpoint "$CHECKPOINT" \
        --qa-set "$QA_SET" \
        --out reports/phase19_verify_final.json >> "$LOG" 2>&1
    local rc_ver=$?
    log "verify_answers_online.py rc=$rc_ver"

    # Bảng tóm tắt để đọc nhanh.
    python3 scripts/phase19_final_table.py >> "$LOG" 2>&1 || true

    local summary_line
    summary_line=$(python3 scripts/phase19_final_table.py --oneline 2>/dev/null || echo "")
    [ -z "$summary_line" ] && summary_line="Xem reports/phase19_summary.md"

    {
        echo "# Phase 19 — trạng thái hoàn tất"
        echo
        echo "- Thời điểm: $(date '+%F %T')"
        echo "- Số câu: **${n}/${TOTAL}**"
        echo "- `summarize_eval.py`: rc=$rc_sum"
        echo "- `verify_answers_online.py`: rc=$rc_ver"
        echo
        echo "## Tóm tắt"
        echo
        echo '```'
        echo "$summary_line"
        echo '```'
        echo
        echo "Báo cáo: \`reports/phase_19_report.md\` · \`reports/phase19_summary.md\`"
        echo "Kiểm chứng: \`reports/phase19_verify_final.json\`"
    } > "$STATUS_FILE"

    if [ "$n" -ge "$TOTAL" ]; then
        notify "Phase 19 ✅ XONG (${n}/${TOTAL})" "Đã tổng hợp + kiểm chứng online xong. Báo cáo: reports/phase_19_report.md"
    else
        notify "Phase 19 ⚠️ driver đã dừng (${n}/${TOTAL})" "Còn thiếu $((TOTAL - n)) câu — xem reports/phase19_finish_status.md"
    fi
    log "=== Xong (${n}/${TOTAL}) ==="
}

if [ "$ONCE" -eq 1 ]; then
    n=$(count_done)
    log "kiểm tra 1 lần: ${n}/${TOTAL}"
    if [ "$n" -ge "$TOTAL" ]; then
        run_finalize "$n"
        : > "$DONE_MARKER"
    fi
    exit 0
fi

# Dọn marker cũ (nếu có) để lần chạy sau không bị coi là đã xong.
rm -f "$DONE_MARKER"

log "=== Watcher Phase 19 bắt đầu (${TOTAL} câu, poll ${POLL_S}s) ==="
notify "Phase 19 watcher 🟢 đang chạy" "Theo dõi eval tới ${TOTAL} câu — sẽ tự tổng hợp + báo bạn."

last=0
stagnant=0
while true; do
    n=$(count_done)
    if [ "$n" -ne "$last" ]; then
        log "tiến triển: ${last} → ${n}/${TOTAL}"
        last="$n"
    fi

    if [ "$n" -ge "$TOTAL" ]; then
        log "ĐỦ ${TOTAL} câu ⇒ tổng hợp + kiểm chứng."
        run_finalize "$n"
        : > "$DONE_MARKER"
        exit 0
    fi

    # Driver đã thoát mà vẫn chưa đủ ⇒ tổng hợp phần đã có rồi báo.
    # ⚠️ Dùng `pgrep -f` với pattern **không** xuất hiện trong cmdline của
    # chính watcher ⇒ tránh tự match (đã gây treo ở bản đầu).
    if ! pgrep -f "bash scripts/run_phase19_eval_loop.sh" > /dev/null 2>&1; then
        # Driver có thể đang ngủ ⇒ chỉ coi là "thoát" nếu không còn tiến triển
        # trong 2 lần poll liên tiếp.
        stagnant=$(( ${stagnant:-0} + 1 ))
        if [ "${stagnant:-0}" -ge 2 ]; then
            log "driver không còn chạy và checkpoint đứng ở ${n}/${TOTAL} ⇒ tổng hợp phần đã có."
            run_finalize "$n"
            : > "$DONE_MARKER"
            exit 0
        fi
    else
        stagnant=0
    fi

    sleep "$POLL_S"
done

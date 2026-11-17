#!/usr/bin/env bash
# Chờ benchmark Phase 16 kết thúc rồi tự sinh nhật ký + số liệu JSON.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PID="${1:-102417}"
STAMP="${2:-20261117_0148}"

while kill -0 "$PID" 2>/dev/null; do
  sleep 30
done

echo "[wait] PID $PID đã kết thúc lúc $(date)"
REPORT="reports/eval_rag_${STAMP}.json"
if [[ ! -f "$REPORT" ]]; then
  echo "[wait] KHÔNG tìm thấy $REPORT — cần kiểm tra log"
  ls -la reports/eval_rag_*.json 2>/dev/null
  exit 1
fi

echo "[wait] Sinh nhật ký Phase 16 từ $REPORT"
./.venv/bin/python scripts/make_phase16_log.py --report "$REPORT"
echo "[wait] Xong lúc $(date)"

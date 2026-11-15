#!/usr/bin/env bash
# Theo dõi NHIỀU kernel Kaggle NER (Phase 5) trên NHIỀU tài khoản song song.
#
# Dùng:
#   bash scripts/poll_kaggle_ner_multi.sh
#
# Mỗi tài khoản lấy credential riêng từ `.env`:
#   - primary   → KAGGLE_USERNAME / KAGGLE_KEY
#   - secondary → SEC_KAGGLE_USERNAME / SEC_KAGGLE_KEY
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

LOG="reports/kaggle_ner_poll.log"
mkdir -p reports

# "user|slug|output_dir"
TARGETS=(
  "$KAGGLE_USERNAME|vhgr-phase-5-ner-train-phobert-base|reports/kaggle_ner_base"
  "$SEC_KAGGLE_USERNAME|vhgr-phase-5-ner-train-phobert-large|reports/kaggle_ner_large"
)

declare -A DONE=()

while true; do
  all_done=1
  for target in "${TARGETS[@]}"; do
    IFS='|' read -r user slug outdir <<<"$target"
    key="$user/$slug"
    if [[ "${DONE[$key]:-0}" == "1" ]]; then
      all_done=0
      continue
    fi

    token_var="KAGGLE_KEY"
    [[ "$user" == "$SEC_KAGGLE_USERNAME" ]] && token_var="SEC_KAGGLE_KEY"

    status="$(env -u KAGGLE_USERNAME -u KAGGLE_KEY \
      KAGGLE_USERNAME="$user" KAGGLE_API_TOKEN="${!token_var}" \
      kaggle kernels status "$key" 2>/dev/null | tail -n 1 | tr -d '\r')"
    echo "[$(date '+%H:%M:%S')] $key: $status" | tee -a "$LOG"

    case "$status" in
      *COMPLETE*|*Complete*|*complete*)
        echo "[$(date '+%H:%M:%S')] $key DONE → tải output" | tee -a "$LOG"
        mkdir -p "$outdir"
        env -u KAGGLE_USERNAME -u KAGGLE_KEY \
          KAGGLE_USERNAME="$user" KAGGLE_API_TOKEN="${!token_var}" \
          kaggle kernels output "$key" -p "$outdir" >>"$LOG" 2>&1
        for archive in "$outdir"/*.zip; do
          [[ -e "$archive" ]] || continue
          unzip -o -q "$archive" -d "$outdir" && echo "[$(date '+%H:%M:%S')] $key giải nén $archive" | tee -a "$LOG"
        done
        DONE[$key]=1
        ;;
      *ERROR*|*Error*|*CANCEL*|*Cancel*|*FAIL*|*Fail*)
        echo "[$(date '+%H:%M:%S')] $key LỖI → tải log" | tee -a "$LOG"
        mkdir -p "$outdir"
        env -u KAGGLE_USERNAME -u KAGGLE_KEY \
          KAGGLE_USERNAME="$user" KAGGLE_API_TOKEN="${!token_var}" \
          kaggle kernels output "$key" -p "$outdir" >>"$LOG" 2>&1 || true
        DONE[$key]=1
        ;;
      *)
        all_done=0
        ;;
    esac
  done
  if (( all_done == 1 )); then
    echo "[$(date '+%H:%M:%S')] Tất cả kernel đã kết thúc." | tee -a "$LOG"
    break
  fi
  sleep 120
done

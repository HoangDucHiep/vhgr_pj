#!/usr/bin/env bash
# Chạy kernel Kaggle NER (Phase 5) với 1 trong 2 tài khoản trong `.env`.
#
# Dùng:
#   bash scripts/run_kaggle_ner.sh base            # tài khoản chính
#   bash scripts/run_kaggle_ner.sh large           # tài khoản chính
#   KAGGLE_ACCOUNT=secondary bash scripts/run_kaggle_ner.sh large
#
# `KAGGLE_ACCOUNT=secondary` dùng `SEC_KAGGLE_USERNAME`/`SEC_KAGGLE_KEY`.
# Vì `kaggle` CLI đọc credential từ biến môi trường, script **unset** các
# biến của tài khoản còn lại để tránh xung đột (đã gặp lỗi auth fail).
set -euo pipefail

ARM="${1:-base}"
ACCOUNT="${KAGGLE_ACCOUNT:-primary}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

case "$ARM" in
  base)
    KERNEL_DIR="notebooks/kaggle/ner_train_phobert_base"
    MODEL_NAME="vinai/phobert-base"
    ;;
  large)
    KERNEL_DIR="notebooks/kaggle/ner_train_phobert_large"
    MODEL_NAME="vinai/phobert-large"
    ;;
  *)
    echo "Arm không hợp lệ: '$ARM' (chỉ nhận 'base' hoặc 'large')" >&2
    exit 1
    ;;
esac

# Nạp .env (chứa credential của cả 2 tài khoản).
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ "$ACCOUNT" == "secondary" ]]; then
  if [[ -z "${SEC_KAGGLE_KEY:-}" ]]; then
    echo "Thiếu SEC_KAGGLE_KEY trong .env" >&2
    exit 1
  fi
  export KAGGLE_USERNAME="$SEC_KAGGLE_USERNAME"
  export KAGGLE_API_TOKEN="$SEC_KAGGLE_KEY"
  unset KAGGLE_KEY
else
  if [[ -z "${KAGGLE_KEY:-}" ]]; then
    echo "Thiếu KAGGLE_KEY trong .env" >&2
    exit 1
  fi
  export KAGGLE_API_TOKEN="$KAGGLE_KEY"
  unset SEC_KAGGLE_KEY SEC_KAGGLE_USERNAME
fi

KERNEL_SLUG="${KAGGLE_USERNAME}/${KERNEL_DIR##*/}"
# Kaggle tự sinh slug từ `title` → phải khớp với `kernel-metadata.json`.
KERNEL_SLUG="hoanghiep421/vhgr-phase-5-ner-train-phobert-${ARM}"
if [[ "$ACCOUNT" == "secondary" ]]; then
  KERNEL_SLUG="dathungdao2004/vhgr-phase-5-ner-train-phobert-${ARM}"
fi

OUTPUT_DIR="reports/kaggle_ner_${ARM}"
mkdir -p "$OUTPUT_DIR"

echo "==> Tài khoản: $ACCOUNT ($KAGGLE_USERNAME)"
echo "==> Đẩy kernel: $KERNEL_SLUG ($MODEL_NAME)"
kaggle kernels push -p "$KERNEL_DIR" --accelerator NvidiaTeslaT4

echo "==> Chờ kernel hoàn tất (poll mỗi 120s, timeout 12h)"
DEADLINE=$(( $(date +%s) + 12 * 3600 ))
while true; do
  STATUS="$(kaggle kernels status "$KERNEL_SLUG" 2>/dev/null | tail -n 1 | tr -d '\r')"
  echo "    [$(date '+%H:%M:%S')] status: $STATUS"
  case "$STATUS" in
    *Complete*|*complete*|*Finished*|*finished*)
      echo "==> Kernel hoàn tất."
      break
      ;;
    *Error*|*error*|*Cancel*|*cancel*|*Fail*|*fail*)
      echo "==> Kernel lỗi: $STATUS" >&2
      kaggle kernels output "$KERNEL_SLUG" -p "$OUTPUT_DIR" || true
      exit 1
      ;;
  esac
  if (( $(date +%s) > DEADLINE )); then
    echo "==> Timeout — kernel vẫn đang chạy." >&2
    exit 1
  fi
  sleep 120
done

echo "==> Tải output kernel"
kaggle kernels output "$KERNEL_SLUG" -p "$OUTPUT_DIR"

echo "==> Giải nén model + predictions"
for archive in "$OUTPUT_DIR"/*.zip; do
  [[ -e "$archive" ]] || continue
  unzip -o -q "$archive" -d "$OUTPUT_DIR"
done

echo "==> Kết quả trong $OUTPUT_DIR:"
find "$OUTPUT_DIR" -maxdepth 3 -type f | sed 's/^/    /'

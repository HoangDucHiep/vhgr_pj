#!/usr/bin/env bash
# Tải các file SQL cần thiết cho Phase 1 từ dump Wikimedia viwiki.
#
# Vì sao cần SQL: bản export XML của MediaWiki **không** chứa thẻ
# `<page_props><wikibase_item>` (đã kiểm chứng 13/11/2026) → không dựng được
# ánh xạ `page_id → QID` từ XML. Ngoài ra bảng `categorylinks` cho sẵn quan hệ
# "bài → category" và "category → subcategory" nhanh hơn nhiều so với quét
# wikitext 1.1 GB.
#
# Cách chạy:
#   bash scripts/download_sql_tables.sh [dump_version]

set -euo pipefail

DUMP_VERSION="${1:-20261101}"
BASE_URL="https://dumps.wikimedia.org/viwiki/${DUMP_VERSION}"
RAW_DIR="data/raw"

mkdir -p "${RAW_DIR}"

FILES=(
  "page.sql.gz"
  "page_props.sql.gz"
  "category.sql.gz"
  "categorylinks.sql.gz"
)

for file in "${FILES[@]}"; do
  target="${RAW_DIR}/viwiki-${DUMP_VERSION}-${file}"
  if [[ -f "${target}" ]]; then
    echo "✓ đã có ${target}"
    continue
  fi
  echo "↓ tải ${file} ..."
  curl -fsSL --retry 3 --retry-delay 5 \
    -o "${target}" "${BASE_URL}/viwiki-${DUMP_VERSION}-${file}"
  echo "  → ${target}"
done

echo ""
echo "Kiểm tra sha1 (so với sha1sums.txt chính thức):"
expected_file="$(mktemp)"
curl -fsSL "${BASE_URL}/viwiki-${DUMP_VERSION}-sha1sums.txt" -o "${expected_file}"

for file in "${FILES[@]}"; do
  target="${RAW_DIR}/viwiki-${DUMP_VERSION}-${file}"
  if [[ ! -f "${target}" ]]; then
    continue
  fi
  actual="$(sha1sum "${target}" | cut -d' ' -f1)"
  expected="$(grep -F "viwiki-${DUMP_VERSION}-${file}" "${expected_file}" | cut -d' ' -f1 || true)"
  if [[ "${actual}" == "${expected}" ]]; then
    echo "  ✓ ${file} ${actual}"
  else
    echo "  ✗ ${file} expected=${expected} actual=${actual}"
  fi
done
rm -f "${expected_file}"

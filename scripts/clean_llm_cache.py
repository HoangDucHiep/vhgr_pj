#!/usr/bin/env python
"""Dọn cache LLM: xoá các bản ghi phản hồi **rỗng** (D-127).

Vì sao cần?
------------
Model thinking có thể trả về chuỗi rỗng khi `max_output_tokens` không đủ
(`finish_reason = MAX_TOKENS`). Bản ghi rỗng **đã** nằm trong cache ⇒ mọi
lần gọi lại cùng prompt đều nhận lại chuỗi rỗng ⇒ `rag_answer` quy về
`not_in_data` ⇒ **sai số liệu vĩnh viễn**, kể cả sau khi đã sửa cấu hình.

Cách dùng:
    python scripts/clean_llm_cache.py --path data/interim/llm_cache.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        default=str(REPO_ROOT / "data" / "interim" / "llm_cache.sqlite"),
        help="Đường dẫn file cache SQLite.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ báo cáo, không xoá.",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"Không tìm thấy cache: {path}")
        return 0

    with sqlite3.connect(path) as connection:
        total = connection.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        empty = connection.execute(
            "SELECT COUNT(*) FROM responses WHERE TRIM(response) = ''"
        ).fetchone()[0]
        print(f"Cache: {path}")
        print(f"  tổng bản ghi : {total}")
        print(f"  phản hồi rỗng: {empty}")
        for model, count in connection.execute(
            "SELECT model, COUNT(*) FROM responses "
            "WHERE TRIM(response) = '' GROUP BY model ORDER BY 2 DESC"
        ):
            print(f"    - {count:5d}  {model}")
        if empty and not args.dry_run:
            connection.execute("DELETE FROM responses WHERE TRIM(response) = ''")
            connection.commit()
            print(f"  ⇒ đã xoá {empty} bản ghi rỗng")
        elif empty:
            print("  ⇒ (dry-run) chưa xoá")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

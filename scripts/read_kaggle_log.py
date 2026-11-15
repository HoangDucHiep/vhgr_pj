"""Đọc log kernel Kaggle (định dạng JSON-lines của `kaggle kernels output`).

Log Kaggle là một mảng JSON, mỗi phần tử là
``{"stream_name": "stdout"|"stderr", "time": ..., "data": "..."}``.

Cách dùng
---------
```bash
python scripts/read_kaggle_log.py /tmp/kprobe2/vhgr-phase-5-ner-environment-probe.log
python scripts/read_kaggle_log.py <log> --stderr
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def read_log(path: str | Path) -> list[dict]:
    """Parse log kernel Kaggle.

    Args:
        path: Đường dẫn file log.

    Returns:
        Danh sách record (dict) theo thứ tự thời gian.
    """
    raw = Path(path).read_text(encoding="utf-8", errors="replace").strip()

    # Log Kaggle là mảng JSON hợp lệ → parse thẳng.
    try:
        payload = json.loads(raw)
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass

    # Fallback: JSON-lines (một record mỗi dòng).
    records: list[dict] = []
    for line in raw.splitlines():
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Đọc log kernel Kaggle")
    parser.add_argument("log", help="Đường dẫn file log")
    parser.add_argument("--stdout", action="store_true", default=True)
    parser.add_argument("--stderr", action="store_true", help="In cả stderr")
    parser.add_argument("--grep", default=None, help="Chỉ in dòng khớp regex")
    args = parser.parse_args(argv)

    records = read_log(args.log)
    pattern = re.compile(args.grep) if args.grep else None

    for record in records:
        stream = record.get("stream_name")
        if stream == "stderr" and not args.stderr:
            continue
        data = str(record.get("data", ""))
        if pattern and not pattern.search(data):
            continue
        sys.stdout.write(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())

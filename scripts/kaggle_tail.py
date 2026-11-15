"""Đọc log kernel Kaggle đang chạy và lưu ra file (streaming SSE, dừng theo thời gian).

Dùng:
    python scripts/kaggle_tail.py <owner/slug> --save /tmp/base.log --seconds 30 --lines 60
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kaggle.api.kaggle_api_extended import KaggleApi  # noqa: E402


def tail(slug: str, n_lines: int, seconds: int, save: str | None) -> None:
    api = KaggleApi()
    api.authenticate()
    collected: list[str] = []
    stop = threading.Event()

    def worker() -> None:
        try:
            for record in api.kernels_logs_stream(slug):
                data = (record.get("data") or "").rstrip()
                if data.strip():
                    collected.append(data)
                if stop.is_set():
                    break
        except Exception:  # noqa: BLE001 - chỉ để thread dừng êm
            pass

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=seconds)
    stop.set()

    if save:
        out = Path(save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(collected) + "\n", encoding="utf-8")

    print(f"--- {slug}: {len(collected)} dòng log" + (f" → {save}" if save else "") + " ---")
    for line in collected[-n_lines:]:
        print(line[:400])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("slugs", nargs="+")
    parser.add_argument("--lines", type=int, default=40)
    parser.add_argument("--seconds", type=int, default=25)
    parser.add_argument("--save", default=None)
    args = parser.parse_args()
    for slug in args.slugs:
        try:
            tail(slug, args.lines, args.seconds, args.save)
        except Exception as exc:  # noqa: BLE001
            print(f"ERR {slug}: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

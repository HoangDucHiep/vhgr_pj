#!/usr/bin/env python3
"""Phase 19 — bảng tóm tắt A vs B vs B− cho báo cáo/watcher.

In:
  * ``--oneline``  → 1 dòng tóm tắt toàn checkpoint (dùng cho notification).
  * mặc định     → bảng markdown đầy đủ theo nhóm + toàn checkpoint.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
ARMS = ("A", "B", "B-")


def _fmt(value: Any) -> str:
    return f"{value:.3f}" if isinstance(value, (int, float)) else "—"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oneline", action="store_true")
    parser.add_argument("--summary", default="reports/phase19_summary.json")
    args = parser.parse_args()

    path = REPO_ROOT / args.summary
    if not path.exists():
        print("chưa có reports/phase19_summary.json")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    groups = data.get("by_group") or {}
    overall = data.get("arms") or data.get("overall") or {}

    if args.oneline:
        parts: list[str] = []
        for arm in ARMS:
            rec = overall.get(arm) or {}
            n = int(rec.get("n") or 0)
            parts.append(f"{arm}: n={n} corr={_fmt(rec.get('correctness'))} faith={_fmt(rec.get('faithfulness'))}")
        print(" · ".join(parts))
        return 0

    print("## A vs B vs B− — Phase 19\n")
    print("| Nhóm | Arm | n | correctness | faithfulness | not_in_data | latency p50 | latency p95 |")
    print("|---|---|---|---|---|---|---|---|")
    for gname in sorted(groups):
        arms = groups[gname] or {}
        for arm in ARMS:
            rec = arms.get(arm) or {}
            n = int(rec.get("n") or 0)
            if n == 0:
                continue
            print(
                f"| `{gname}` | {arm} | {n} | {_fmt(rec.get('correctness'))} "
                f"| {_fmt(rec.get('faithfulness'))} | {rec.get('not_in_data', 0)} "
                f"| {rec.get('latency_p50', 0)} | {rec.get('latency_p95', 0)} |"
            )

    print("\n### Toàn checkpoint\n")
    print("| Arm | n | correctness | faithfulness | not_in_data | latency p50 | latency p95 |")
    print("|---|---|---|---|---|---|---|")
    for arm in ARMS:
        rec = overall.get(arm) or {}
        n = int(rec.get("n") or 0)
        print(
            f"| {arm} | {n} | {_fmt(rec.get('correctness'))} | {_fmt(rec.get('faithfulness'))} "
            f"| {rec.get('not_in_data', 0)} | {rec.get('latency_p50', 0)} | {rec.get('latency_p95', 0)} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

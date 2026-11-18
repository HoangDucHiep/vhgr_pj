#!/usr/bin/env python
"""Chấm lại **toàn bộ** 3 arm của mọi câu bằng một ngân sách context cho trước.

Vì sao cần script này?
----------------------
D-123 (baseline) chấm với `--judge-context-chars 9000`. Bản D-124 lần đầu
chấm với `2200` (để vừa trần TPM của Groq) ⇒ **ngân sách context khác nhau**
⇒ điểm số **không so sánh được** giữa 2 bản ⇒ phải **chấm lại toàn bộ** bằng
**cùng một** ngân sách.

Mấu chốt: chấm lại **không** sinh lại câu trả lời ⇒ **không** tốn quota sinh.
Chỉ tốn **1 request judge/câu**.

Lưu ý (D-134): `compact_context()` **mới** giữ phần KG ⇒ khi chấm lại với
ngân sách lớn (9.000) thì arm B **có** đủ KG trong context ⇒ phép so sánh
A vs B vs B− **công bằng**.

Cách dùng:
    ./.venv/bin/python scripts/rejudge_all.py \\
        --checkpoint data/eval/eval_d124_checkpoint.jsonl \\
        --judge-pool "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-3-flash-preview" \\
        --context-chars 9000 \\
        --out data/eval/eval_d124_checkpoint.jsonl
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.evaluate_rag import (  # noqa: E402
    Judge,
    PooledLLM,
    _parse_pool_spec,
    build_cross_provider_pool,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("rejudge_all")

ARMS = ("A", "B", "B-")


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, help="File checkpoint JSONL.")
    parser.add_argument(
        "--judge-pool",
        default=(
            "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,"
            "gemini-3-flash-preview"
        ),
        help="Pool judge (phải **giống** baseline để số liệu so sánh được).",
    )
    parser.add_argument(
        "--context-chars",
        type=int,
        default=9000,
        help="Ngân sách context cho judge (mặc định 9.000 = của D-123).",
    )
    parser.add_argument(
        "--provider-priority",
        default="gemini,groq",
        help="Thứ tự ưu tiên provider cho judge.",
    )
    parser.add_argument(
        "--quota-cooldown-s", type=float, default=60.0, help="Cooldown sau 429."
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ báo cáo.")
    args = parser.parse_args()

    path = REPO_ROOT / args.checkpoint
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    logger.info("Đọc %d câu từ %s", len(rows), path)

    groups = _parse_pool_spec(args.judge_pool)
    if not groups:
        logger.error("Không parse được --judge-pool")
        return 1
    clients = build_cross_provider_pool(groups)
    if not clients:
        logger.error("Không dựng được pool judge")
        return 1

    judge_pool = PooledLLM(
        clients,
        quota_cooldown_s=args.quota_cooldown_s,
        max_cooldown_s=21600.0,
        rpm_min_cooldown_s=60.0,
    )
    judge_pool.provider_priority = tuple(
        p.strip() for p in args.provider_priority.split(",") if p.strip()
    )
    judge = Judge(judge_pool)

    fixed = 0
    missing = 0
    for index, row in enumerate(rows, start=1):
        qid = row.get("qid")
        candidates = [
            {
                "arm": arm,
                "context": (row.get(arm, {}).get("arm") or {}).get("context", ""),
                "answer": (row.get(arm, {}).get("arm") or {}).get("answer", ""),
            }
            for arm in ARMS
            if row.get(arm)
        ]
        if not candidates:
            continue
        try:
            scores = judge.score(
                question=str(row.get("question") or ""),
                expected_answer=str(row.get("expected_answer") or ""),
                candidates=candidates,
                question_type=str(row.get("type") or ""),
                context_chars=args.context_chars,
            )
        except Exception as error:  # noqa: BLE001 - 1 câu lỗi không dừng cả lượt
            logger.warning("[%d/%d] %s — judge lỗi: %s", index, len(rows), qid, error)
            missing += len(candidates)
            continue
        for arm in ARMS:
            if not row.get(arm):
                continue
            new_score = scores.get(arm)
            if not new_score:
                missing += 1
                continue
            row[arm]["judge"] = new_score
            row[arm]["judge_context_chars"] = args.context_chars
            fixed += 1
        logger.info(
            "[%d/%d] %s — %s",
            index, len(rows), qid,
            " · ".join(
                f"{arm}={scores.get(arm, {}).get('correctness', '-')}" for arm in ARMS
            ),
        )

    logger.info(
        "Đã chấm lại %d arm, còn %d arm thiếu điểm (context_chars=%d)",
        fixed, missing, args.context_chars,
    )
    if args.dry_run:
        logger.info("DRY-RUN — không ghi file")
        return 0

    tmp = path.with_suffix(".rejudged.jsonl")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)
    logger.info("Đã ghi lại %s", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

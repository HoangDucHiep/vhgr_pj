#!/usr/bin/env python
"""Chấm lại (re-judge) các câu mà LLM-judge **không trả về điểm** cho mọi arm.

Vấn đề: JSON output của judge đôi khi bị cắt token ⇒ arm bị thiếu entry ⇒ bị
gán điểm 0 ⇒ **số liệu sai** (không phải số liệu kém). Script này:

1. Đọc checkpoint `data/eval/eval_rag_checkpoint.jsonl`.
2. Tìm các câu có arm nào bị thiếu điểm (reason chứa "không trả về điểm").
3. Chấm lại **chỉ những arm đó** — dùng lại `context` + `answer` đã sinh
   (không gọi lại LLM sinh câu trả lời ⇒ không tốn quota sinh).
4. Ghi lại checkpoint (cập nhật entry của các arm bị sửa).

Dùng:
    ./.venv/bin/python scripts/rejudge_missing.py \\
        --checkpoint data/eval/eval_rag_checkpoint.jsonl \\
        --judge-pool "gemini:...,..."
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
    _build_pool_or_single,
    _parse_pool_spec,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("rejudge")

MISSING_MARKER = "không trả về điểm"


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        default="data/eval/eval_rag_checkpoint.jsonl",
        help="File checkpoint JSONL.",
    )
    parser.add_argument(
        "--judge-pool",
        default=(
            "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,"
            "gemini-3-flash-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b"
        ),
        help="Pool judge đa provider.",
    )
    parser.add_argument(
        "--quota-cooldown-s", type=float, default=900.0, help="Cooldown sau lỗi quota."
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ báo cáo, không ghi.")
    args = parser.parse_args()

    path = REPO_ROOT / args.checkpoint
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    logger.info("Đọc %d câu từ %s", len(rows), path)

    todo: list[tuple[dict[str, Any], list[str]]] = []
    for row in rows:
        arms = [k for k in row if k != "qid"]
        missing = [
            arm
            for arm in arms
            if MISSING_MARKER in str((row[arm].get("judge") or {}).get("reason", ""))
        ]
        if missing:
            todo.append((row, missing))
    logger.info("Có %d câu cần chấm lại", len(todo))
    if not todo:
        return 0

    groups = _parse_pool_spec(args.judge_pool)
    if not groups:
        logger.error("Không parse được --judge-pool")
        return 1

    from src.evaluation.evaluate_rag import PooledLLM, build_cross_provider_pool

    clients = build_cross_provider_pool(groups)
    if not clients:
        logger.error("Không dựng được pool judge")
        return 1

    judge_pool = PooledLLM(clients, quota_cooldown_s=args.quota_cooldown_s)
    # Judge **gọn** (1 request/câu) ⇒ ưu tiên Gemini (giới hạn request/ngày)
    # để **giữ** quota token/ngày của Groq cho sinh câu trả lời.
    judge_pool.provider_priority = ("gemini", "groq")
    judge = Judge(judge_pool)

    fixed = 0
    still_missing = 0
    for index, (row, missing_arms) in enumerate(todo, start=1):
        qid = row.get("qid")
        # Chỉ đưa các arm **bị thiếu** vào prompt ⇒ tiết kiệm token + tránh
        # judge xáo trộn điểm giữa các arm.
        candidates = [
            {
                "arm": arm,
                "context": (row[arm].get("arm") or {}).get("context", ""),
                "answer": (row[arm].get("arm") or {}).get("answer", ""),
            }
            for arm in missing_arms
        ]
        scores = judge.score(
            question=str(row.get("question") or ""),
            expected_answer=str(row.get("expected_answer") or ""),
            candidates=candidates,
            question_type=str(row.get("type") or ""),
        )
        for arm in missing_arms:
            new_score = scores.get(arm) or {}
            if MISSING_MARKER in str(new_score.get("reason", "")):
                still_missing += 1
                continue
            row[arm]["judge"] = new_score
            fixed += 1
        logger.info(
            "[%d/%d] %s — arm %s · đã sửa %d",
            index, len(todo), qid, ",".join(missing_arms), len(missing_arms),
        )

    logger.info("Đã sửa %d arm, còn %d arm thiếu điểm", fixed, still_missing)
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

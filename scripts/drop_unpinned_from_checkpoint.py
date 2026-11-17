#!/usr/bin/env python
"""Lọc khỏi checkpoint các câu **không ghim được model** để chạy lại.

Câu sinh bởi phiên bản cũ (trước D-111) có `gen_model` rỗng ⇒ không biết
model nào sinh ⇒ có thể đã bị **confound model** (arm A và arm B dùng khác
model) ⇒ không đáng tin cho phép so sánh.

Cũng loại các câu mà **các arm dùng khác model** (model ghim hết quota giữa
lúc arm đang chạy) — cùng lý do confound.

Script này **xoá** các câu đó khỏi checkpoint ⇒ chạy lại `evaluate_rag
--resume` sẽ sinh lại chúng bằng code đã vá (ghim model ⇒ 3 arm cùng model).

Dùng:
    ./.venv/bin/python scripts/drop_unpinned_from_checkpoint.py \\
        --checkpoint data/eval/eval_rag_checkpoint.jsonl [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("drop-unpinned")


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        default="data/eval/eval_rag_checkpoint.jsonl",
        help="File checkpoint JSONL.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Chỉ báo cáo.")
    args = parser.parse_args()

    path = REPO_ROOT / args.checkpoint
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    keep: list[dict] = []
    dropped: list[str] = []
    for row in rows:
        arms = [k for k in row if k != "qid"]
        models = {row[a].get("gen_model") for a in arms if a in row}
        if not models or not all(models):
            # Không ghim được model ⇒ có thể đã bị confound model.
            dropped.append(str(row.get("qid")))
        elif len(models) > 1:
            # Các arm dùng **khác model** ⇒ confound ⇒ không đáng tin.
            dropped.append(str(row.get("qid")))
        else:
            keep.append(row)

    logger.info(
        "Giữ %d câu, xoá %d câu không ghim model: %s",
        len(keep), len(dropped), dropped[:20],
    )
    if args.dry_run:
        logger.info("DRY-RUN — không ghi file")
        return 0
    if not dropped:
        logger.info("Không có câu nào cần xoá")
        return 0

    tmp = path.with_suffix(".filtered.jsonl")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in keep:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)
    logger.info("Đã ghi lại %s — chạy lại `evaluate_rag --resume` để sinh lại", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

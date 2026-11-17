#!/usr/bin/env python
"""Dựng lại báo cáo JSON Phase 16 từ checkpoint (sau khi chấm lại).

`src.evaluation.evaluate_rag` ghi `reports/eval_rag_<prefix>_<stamp>.json` ở
cuối run. Nhưng nếu sau đó có **chấm lại** các arm bị judge bỏ sót
(`scripts/rejudge_missing.py`) thì số liệu trong file đó là **cũ**.

Script này tính lại chỉ số từ `data/eval/eval_rag_checkpoint.jsonl` (sau
chấm lại) và ghi đè file báo cáo JSON ⇒ số liệu luôn khớp checkpoint.

Dùng:
    ./.venv/bin/python scripts/rebuild_phase16_report.py \\
        --checkpoint data/eval/eval_rag_checkpoint.jsonl \\
        --out reports/eval_rag_phase16_phase16.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.evaluate_rag import aggregate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("rebuild")


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        default="data/eval/eval_rag_checkpoint.jsonl",
        help="File checkpoint JSONL.",
    )
    parser.add_argument(
        "--out",
        default="reports/eval_rag_phase16_phase16.json",
        help="Đường dẫn báo cáo JSON đầu ra.",
    )
    parser.add_argument("--qa-set", default="data/eval/qa_rag_250.jsonl")
    parser.add_argument("--stamp", default="phase16")
    parser.add_argument(
        "--gen-pool",
        default=(
            "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,"
            "gemini-3-flash-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,"
            "openai/gpt-oss-20b"
        ),
    )
    parser.add_argument(
        "--judge-pool",
        default=(
            "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,"
            "gemini-3-flash-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b"
        ),
    )
    args = parser.parse_args()

    path = REPO_ROOT / args.checkpoint
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    arms = [key for key in rows[0] if key != "qid"]
    metrics = {
        arm: aggregate([row[arm] for row in rows if arm in row]) for arm in arms
    }

    # Phân bố model sinh câu trả lời (kiểm chứng "ghim model theo câu").
    models: dict[str, int] = {}
    mismatched: list[str] = []
    for row in rows:
        used = {
            arm: row[arm].get("gen_model") for arm in arms if arm in row
        }
        distinct = {m for m in used.values() if m}
        for model in distinct:
            models[model] = models.get(model, 0) + 1
        if len(distinct) > 1:
            mismatched.append(str(row.get("qid")))
    logger.info(
        "Câu có arm dùng khác model (confound): %d / %d %s",
        len(mismatched), len(rows), mismatched[:10],
    )

    # **Loại các câu có confound khỏi mẫu số chính**: khi model ghim hết quota
    # giữa lúc arm đang chạy ⇒ arm này sinh bằng model khác ⇒ chênh lệch
    # điểm có thể do *model* chứ không phải do *kiến trúc* ⇒ câu đó không
    # dùng được cho phép so sánh. Vẫn công khai số lượng trong `_meta`.
    fair_rows = [row for row in rows if str(row.get("qid")) not in set(mismatched)]
    metrics = {
        arm: aggregate([row[arm] for row in fair_rows if arm in row]) for arm in arms
    }
    metrics_all = {
        arm: aggregate([row[arm] for row in rows if arm in row]) for arm in arms
    }

    payload = {
        "_meta": {
            "phase": 16,
            "mo_ta": "Kết quả đánh giá RAG: A vs B vs B− (dựng lại từ checkpoint)",
            "qa_set": args.qa_set,
            "n_questions": len(fair_rows),
            "n_questions_tong": len(rows),
            "n_questions_loai_confound": len(mismatched),
            "arms": arms,
            "judge_model": "pool đa provider (Gemini + Groq)",
            "gen_pool": {"models": sorted(models), "spec": args.gen_pool},
            "judge_pool": {"spec": args.judge_pool},
            "n_model_mismatch": len(mismatched),
            "qid_model_mismatch": mismatched[:50],
            "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        "metrics": metrics,
        "metrics_keu_loai_confound": metrics_all,
    }

    out_path = REPO_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info(
        "Đã ghi %s (%d câu tính điểm, %d câu loại do confound)",
        out_path, len(fair_rows), len(mismatched),
    )
    for arm in arms:
        m = metrics[arm]
        logger.info(
            "  %s: n=%s correctness=%s faith=%s cit=%s infra=%s judge_missing=%s",
            arm, m.get("n"), m.get("correctness_mean"), m.get("faithfulness_mean"),
            m.get("citation_precision"), m.get("n_infra_errors"),
            m.get("n_judge_missing"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python
"""Tổng hợp & so sánh kết quả eval narrative (D-122 / D-123 / D-124).

Cách dùng:
    python scripts/summarize_narrative_eval.py \
        --checkpoint data/eval/eval_d124_checkpoint.jsonl \
        --label D-124
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
ARMS = ("A", "B", "B-")


#: Mẫu nhận diện câu trả lời kiểu **"không có trong dữ liệu"**.
#:
#: Vì sao dò trong **văn bản câu trả lời** chứ không phải trong `reason` của
#: judge? Vì `reason` là lời giải thích của judge (nó có thể chỉ ra arm nào
#: trả lời rỗng), còn **dấu hiệu thật** nằm ở câu trả lời mà hệ thống sinh ra.
NOT_IN_DATA_PATTERN = re.compile(
    r"không có (?:trong |bất kỳ )?dữ liệu|không tìm thấy (?:thông tin )?dữ liệu"
    r"|dữ liệu (?:hiện có )?không (?:có |chứa )?(?:thông tin )?về",
    re.IGNORECASE,
)


def _is_not_in_data(answer: str) -> bool:
    """Câu trả lời là "không có trong dữ liệu" hay không."""
    return bool(NOT_IN_DATA_PATTERN.search(answer or ""))


def summarize(path: Path) -> dict:
    """Tính chỉ số cho 1 file checkpoint."""
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    out: dict = {"n_questions": len(rows), "arms": {}}
    for arm in ARMS:
        usable = [
            row
            for row in rows
            if row.get(arm)
            and not (row[arm].get("arm") or {}).get("infrastructure_error")
        ]
        scores = [
            row[arm]["judge"]
            for row in usable
            if row[arm].get("judge")
            and "correctness" in (row[arm].get("judge") or {})
        ]
        not_in_data = sum(
            1
            for row in usable
            if _is_not_in_data(str((row[arm].get("arm") or {}).get("answer") or ""))
        )
        models = Counter(str(row[arm].get("gen_model") or "") for row in usable)
        out["arms"][arm] = {
            "n": len(usable),
            "correctness": round(mean([s["correctness"] for s in scores]), 3)
            if scores
            else None,
            "faithfulness": round(mean([s["faithfulness"] for s in scores]), 3)
            if scores
            else None,
            "citation_precision": round(
                mean([float(s.get("citation_precision", 0.0)) for s in scores]), 3
            )
            if scores
            else None,
            "not_in_data": not_in_data,
            "models": dict(models),
        }
    # Câu có 3 arm dùng **khác model** ⇒ confound ⇒ loại khỏi mẫu số.
    mismatch = [
        row["qid"]
        for row in rows
        if len({row.get(a, {}).get("gen_model") for a in ARMS}) > 1
    ]
    out["model_mismatch_qids"] = mismatch
    return out


def compare(old: dict, new: dict) -> dict:
    """So sánh 2 bản tổng hợp."""
    result: dict = {"label_old": old.get("label"), "label_new": new.get("label")}
    for arm in ARMS:
        o = old["arms"].get(arm, {})
        n = new["arms"].get(arm, {})
        result[arm] = {
            "correctness": {"old": o.get("correctness"), "new": n.get("correctness")},
            "faithfulness": {"old": o.get("faithfulness"), "new": n.get("faithfulness")},
            "not_in_data": {"old": o.get("not_in_data"), "new": n.get("not_in_data")},
            "delta_correctness": (
                round(n["correctness"] - o["correctness"], 3)
                if o.get("correctness") is not None and n.get("correctness") is not None
                else None
            ),
        }
    return result


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, help="File checkpoint JSONL.")
    parser.add_argument("--label", default="", help="Nhãn cho bản tổng hợp.")
    parser.add_argument("--compare", default="", help="File checkpoint để so sánh.")
    parser.add_argument("--compare-label", default="", help="Nhãn bản so sánh.")
    parser.add_argument("--out", default="", help="Ghi kết quả ra file JSON.")
    args = parser.parse_args()

    new = summarize(Path(args.checkpoint))
    new["label"] = args.label or Path(args.checkpoint).stem
    payload: dict = {"new": new}
    if args.compare:
        old = summarize(Path(args.compare))
        old["label"] = args.compare_label or Path(args.compare).stem
        payload["old"] = old
        payload["comparison"] = compare(old, new)

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

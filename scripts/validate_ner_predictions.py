"""Kiểm tra Gate Phase 5 cho `data/interim/ner_predictions.jsonl`.

Đo được (Gate trong `docs/09` §Phase 5):
- **0** span có offset sai (`text[start:end] == entity["text"]`);
- **0** nhãn ngoài 6 nhãn đóng;
- độ phủ ≥ 95% câu corpus (so với `ner_silver.jsonl`);
- phân bố entity theo nhãn.

Cách dùng
---------
```bash
python scripts/validate_ner_predictions.py \
    --predictions data/interim/ner_predictions.jsonl \
    --silver data/interim/ner_silver.jsonl \
    --out reports/ner_predictions_validate.json
```

Mã thoát khác 0 nếu có span sai offset hoặc nhãn không hợp lệ.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

#: 6 nhãn NER đóng (`docs/CONTEXT.md` §2.4).
VALID_LABELS = {"PERSON", "DYNASTY", "EVENT", "LOCATION", "TIME", "TITLE"}


def validate(
    predictions_path: str | Path,
    silver_path: str | Path,
) -> dict[str, Any]:
    """Kiểm tra file dự đoán.

    Args:
        predictions_path: Đường dẫn `ner_predictions.jsonl`.
        silver_path: Đường dẫn `ner_silver.jsonl` (nguồn câu của corpus).

    Returns:
        Dict kết quả kiểm tra.
    """
    n_sentences = 0
    n_entities = 0
    n_bad_offset = 0
    n_bad_label = 0
    n_empty_text = 0
    label_counts: Counter[str] = Counter()
    pred_ids: set[str] = set()
    examples_bad: list[dict[str, Any]] = []

    with Path(predictions_path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            n_sentences += 1
            text = str(record.get("text", ""))
            sentence_id = str(record.get("sentence_id", ""))
            pred_ids.add(sentence_id)
            for entity in record.get("entities") or []:
                n_entities += 1
                label = str(entity.get("label"))
                label_counts[label] += 1
                if label not in VALID_LABELS:
                    n_bad_label += 1
                start = int(entity.get("start", -1))
                end = int(entity.get("end", -1))
                span = str(entity.get("text", ""))
                if text[start:end] != span:
                    n_bad_offset += 1
                    if len(examples_bad) < 5:
                        examples_bad.append(
                            {
                                "sentence_id": sentence_id,
                                "start": start,
                                "end": end,
                                "expected": span,
                                "actual": text[start:end],
                            }
                        )
            if not text.strip():
                n_empty_text += 1

    silver_ids: set[str] = set()
    n_silver = 0
    with Path(silver_path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            n_silver += 1
            silver_ids.add(str(record.get("sentence_id", "")))

    covered = len(pred_ids & silver_ids)
    coverage = covered / n_silver if n_silver else 0.0

    return {
        "n_sentences_predicted": n_sentences,
        "n_sentences_corpus": n_silver,
        "n_sentences_covered": covered,
        "coverage": round(coverage, 4),
        "n_entities": n_entities,
        "n_bad_offset": n_bad_offset,
        "n_bad_label": n_bad_label,
        "n_empty_text": n_empty_text,
        "label_distribution": dict(label_counts.most_common()),
        "examples_bad_offset": examples_bad,
        "gate_offsets_ok": n_bad_offset == 0,
        "gate_labels_ok": n_bad_label == 0,
        "gate_coverage_ok": coverage >= 0.95,
    }


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát (0 = đạt, 1 = lỗi Gate).
    """
    parser = argparse.ArgumentParser(description="Kiểm tra Gate Phase 5")
    parser.add_argument(
        "--predictions", default="data/interim/ner_predictions.jsonl"
    )
    parser.add_argument("--silver", default="data/interim/ner_silver.jsonl")
    parser.add_argument("--out", default=None, help="Ghi kết quả ra file JSON")
    args = parser.parse_args(argv)

    result = validate(args.predictions, args.silver)
    payload = json.dumps(result, ensure_ascii=False, indent=1)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
        logger.info("Đã ghi %s", out)
    else:
        print(payload)

    ok = (
        result["gate_offsets_ok"]
        and result["gate_labels_ok"]
        and result["gate_coverage_ok"]
    )
    logger.info(
        "Câu=%d | entity=%d | sai offset=%d | nhãn sai=%d | phủ=%.2f%% → %s",
        result["n_sentences_predicted"],
        result["n_entities"],
        result["n_bad_offset"],
        result["n_bad_label"],
        result["coverage"] * 100,
        "ĐẠT" if ok else "KHÔNG ĐẠT",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

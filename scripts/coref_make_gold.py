"""Sinh bộ gold 100 câu cho đánh giá coreference — Phase 6.

Đặc tả: `docs/01-requirements-chuc-nang.md` §C1 (AC: độ chính xác gán ≥ 0,80
trên tập gold 100 câu có đại từ).

Cách chạy
---------
```bash
# 1. Sinh template (chỉ câu + ứng viên, chưa có nhãn canonical_id)
python scripts/coref_make_gold.py --config configs/default.yaml

# 2. Gán tay: điền trường `canonical_id` + `resolved_by` cho mỗi mention
#    trong data/eval/coref_gold_100.jsonl (đặt null nếu không resolve được).

# 3. Đánh giá
python scripts/coref_eval.py --config configs/default.yaml
```

Nguyên tắc
----------
- Lấy câu từ tập **dev** của `data/splits/splits.json` (không lẫn train/test
  → không rò rỉ khi Phase 7 dùng tập train).
- Chỉ lấy câu có ≥ 1 danh xưng/đại từ (span `source="pronoun"`).
- Seed 42 → tái lập được.
- Mỗi câu kèm `ung_vien` — danh sách entity có thể là đích của đại từ
  (từ span đã resolve trong cùng đoạn + chủ thể bài), để người gán tay chọn
  nhanh thay vì phải tra `entity_id` bằng tay.
- **Không** dùng LLM để gán (giữ 0 chi phí API, đúng nguyên tắc quota của
  `docs/CONTEXT.md` §2.2).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_config, resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

#: Số ứng viên tối đa đính kèm mỗi câu (đủ dùng, không làm file quá lớn).
MAX_CANDIDATES = 8


def _load_dev_pages(splits_path: str | Path) -> set[str]:
    """Lấy danh sách `page_id` của tập dev.

    Args:
        splits_path: Đường dẫn `splits.json`.

    Returns:
        Tập `page_id` (dạng chuỗi) của tập dev.
    """
    with Path(splits_path).open("r", encoding="utf-8") as handle:
        splits = json.load(handle)
    dev = splits.get("dev") or []
    return {str(page_id) for page_id in dev}


def build_gold_template(
    coref_path: str | Path,
    splits_path: str | Path,
    subject_path: str | Path,
    *,
    size: int = 100,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Dựng template gold: câu + mention + ứng viên, chưa có nhãn.

    Args:
        coref_path: Đường dẫn `coref_resolved.jsonl`.
        splits_path: Đường dẫn `splits.json`.
        subject_path: Đường dẫn `article_subjects.jsonl`.
        size: Số câu cần lấy.
        seed: Seed ngẫu nhiên.

    Returns:
        Danh sách template gold (mỗi phần tử là 1 câu).
    """
    dev_pages = _load_dev_pages(splits_path)

    subjects: dict[str, dict[str, Any]] = {}
    with Path(subject_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                record = json.loads(line)
                subjects[str(record.get("doc_id"))] = record

    candidates: list[dict[str, Any]] = []

    with Path(coref_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            # Chỉ câu trong tập dev.
            page_id = str(row.get("sentence_id", "")).split("_")[0].lstrip("s")
            if page_id not in dev_pages:
                continue
            mentions = row.get("mentions") or []
            has_pronoun = any(
                str(mention.get("source")) in ("pronoun", "pronoun_name")
                for mention in mentions
            )
            if not has_pronoun:
                continue

            # Ứng viên: các entity đã resolve trong câu + chủ thể bài.
            options: list[dict[str, Any]] = []
            seen: set[str] = set()
            for mention in mentions:
                canonical_id = mention.get("canonical_id")
                if not canonical_id or canonical_id in seen:
                    continue
                seen.add(str(canonical_id))
                options.append(
                    {
                        "ten": mention.get("text"),
                        "canonical_id": canonical_id,
                        "loi": mention.get("label"),
                    }
                )
            subject = subjects.get(str(row.get("doc_id")))
            if subject and subject.get("entity_id") not in seen:
                options.append(
                    {
                        "ten": subject.get("title"),
                        "canonical_id": subject.get("entity_id"),
                        "loi": subject.get("type"),
                    }
                )
            options = options[:MAX_CANDIDATES]

            candidates.append(
                {
                    "sentence_id": row.get("sentence_id"),
                    "doc_id": row.get("doc_id"),
                    "text": row.get("text"),
                    "ung_vien": options,
                    # Chỉ giữ mention **danh xưng/đại từ** (`source="pronoun"`).
                    # Mention NER có tên được resolve bằng R0/R0' (tra gazetteer)
                    # → không phải việc của coreference, đưa vào gold sẽ làm
                    # sai lệch độ chính xác của G5 (xem `docs/10-nhat-ky/phase-06.md`).
                    "mentions": [
                        {
                            "start": mention.get("start"),
                            "end": mention.get("end"),
                            "text": mention.get("text"),
                            "label": mention.get("label"),
                            # Trường cần gán tay:
                            "canonical_id": None,
                            "resolved_by": None,
                        }
                        for mention in mentions
                        if str(mention.get("source")) in ("pronoun", "pronoun_name")
                    ],
                }
            )

    candidates.sort(key=lambda row: str(row.get("sentence_id")))
    rng = random.Random(seed)
    picked = rng.sample(candidates, min(size, len(candidates)))
    picked.sort(key=lambda row: str(row.get("sentence_id")))
    return picked


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Sinh template gold 100 câu cho coreference (Phase 6)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--input", default=None, help="Đường dẫn coref_resolved.jsonl")
    parser.add_argument("--out", default=None, help="Đường dẫn gold JSONL")
    parser.add_argument("--size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    coref_config = dict(config.get("coref", {}))

    coref_path = resolve_path(
        args.input or coref_config.get("output_path", "data/interim/coref_resolved.jsonl")
    )
    splits_path = resolve_path(
        coref_config.get("splits_path", "data/splits/splits.json")
    )
    subject_path = resolve_path(
        coref_config.get("article_subject_path", "data/interim/article_subjects.jsonl")
    )
    out_path = resolve_path(
        args.out or coref_config.get("gold_path", "data/eval/coref_gold_100.jsonl")
    )
    size = args.size or int(coref_config.get("gold_size", 100))

    template = build_gold_template(
        coref_path,
        splits_path,
        subject_path,
        size=size,
        seed=args.seed,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for row in template:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    n_mentions = sum(len(row["mentions"]) for row in template)
    logger.info(
        "Đã ghi %d câu / %d mention → %s",
        len(template),
        n_mentions,
        out_path,
    )
    logger.info(
        "Bước tiếp theo: gán tay `canonical_id` + `resolved_by` cho mỗi mention "
        "(dùng `ung_vien` làm danh sách đích gợi ý)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

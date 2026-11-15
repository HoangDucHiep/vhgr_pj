"""Đo nhiễu nhãn bạc + tạo bộ gold nhỏ cho NER (Phase 5 — đánh giá bổ sung).

Vì sao cần
----------
F1 đo trên tập dev là F1 so với **nhãn bạc**, không phải so với nhãn vàng.
Nếu nhãn bạc sai X% thì F1 bị trần ở đại lượng đó. Để **công khai giới hạn**
(công nguyên 3 của `AGENTS.md` §5) ta:

1. Lấy **100 câu dev ngẫu nhiên (seed 42)** → đưa ra file
   `data/eval/ner_audit_100.jsonl` để **kiểm tra tay** (người đọc đối chiếu
   với văn bản Wikipedia).
2. Ghi kết quả kiểm tra tay vào `data/eval/ner_audit_100_reviewed.jsonl`
   (cùng format, nhãn đã sửa) → dùng làm **bộ gold 100 câu**.
3. Đo F1 của mô hình trên bộ gold này → **chỉ số phụ** (không thay thế Gate).

Cách dùng
---------
```bash
# Bước 1 — xuất 100 câu dev để kiểm tra tay
python scripts/ner_audit_sample.py --sample 100 --out data/eval/ner_audit_100.jsonl

# Bước 2 — sau khi đã sửa nhãn tay, đo F1 mô hình trên bộ gold
python scripts/ner_audit_sample.py --score \
    --gold data/eval/ner_audit_100_reviewed.jsonl \
    --model models/ner --out reports/ner_gold_100_metrics.json
```

Lưu ý: `data/eval/` chứa dữ liệu đánh giá (gitignored) — xem `.gitignore`.
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

from src.common.config import resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402
from src.ner.data_convert import iter_silver_by_split, read_jsonl  # noqa: E402

logger = get_logger(__name__)

#: Số câu lấy mẫu (theo yêu cầu Phase 5).
DEFAULT_SAMPLE_SIZE = 100

#: Seed cố định (AGENTS.md §5.6).
SEED = 42


def sample_sentences(
    silver_path: str | Path,
    splits_path: str | Path,
    split: str,
    sample_size: int,
    seed: int = SEED,
) -> list[dict[str, Any]]:
    """Lấy mẫu ngẫu nhiên câu từ một tập.

    Args:
        silver_path: Đường dẫn `ner_silver.jsonl`.
        splits_path: Đường dẫn `splits.json`.
        split: Tên tập.
        sample_size: Số câu lấy.
        seed: Seed random.

    Returns:
        Danh sách record được chọn (đã shuffle theo seed).
    """
    records = list(iter_silver_by_split(silver_path, splits_path, split))
    random.Random(seed).shuffle(records)
    return records[:sample_size]


def write_audit_sample(records: list[dict[str, Any]], out_path: str | Path) -> Path:
    """Ghi mẫu câu ra file JSONL để kiểm tra tay.

    Args:
        records: Danh sách record.
        out_path: Đường dẫn output.

    Returns:
        Đường dẫn file vừa ghi.
    """
    path = resolve_path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            payload = {
                "sentence_id": record.get("sentence_id"),
                "doc_id": record.get("doc_id"),
                "page_id": record.get("page_id"),
                "text": record.get("text"),
                "tokens": record.get("tokens"),
                "labels": record.get("labels"),
                "mentions": record.get("mentions"),
                # Người kiểm tra tay điền vào đây:
                # - sửa `labels` nếu nhãn bạc sai
                # - hoặc thêm field `review_notes` ghi lý do
                "reviewed": False,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return path


def score_on_gold(
    gold_path: str | Path,
    predictions_path: str | Path,
) -> dict[str, Any]:
    """Tính F1 của mô hình trên bộ gold đã kiểm tra tay.

    Args:
        gold_path: File JSONL bộ gold (cùng format nhãn bạc).
        predictions_path: File JSONL dự đoán (`ner_predictions.jsonl`).

    Returns:
        Dict kết quả đánh giá.
    """
    from src.evaluation.metrics import ner_f1

    predictions: dict[str, list[dict[str, Any]]] = {}
    for record in read_jsonl(resolve_path(predictions_path)):
        predictions[str(record.get("sentence_id"))] = list(record.get("entities") or [])

    gold_records: list[dict[str, Any]] = []
    pred_records: list[dict[str, Any]] = []
    n_matched = 0

    for record in read_jsonl(resolve_path(gold_path)):
        sentence_id = str(record.get("sentence_id"))
        gold_records.append(
            {
                "sentence_id": sentence_id,
                "tokens": list(record.get("tokens") or []),
                "labels": list(record.get("labels") or []),
            }
        )
        entities = predictions.get(sentence_id, [])
        if entities:
            n_matched += 1
        # Dự đoán đã ở mức span ký tự → cần chuyển về mức word để so sánh.
        labels = _spans_to_labels(
            str(record.get("text", "")),
            list(record.get("tokens") or []),
            entities,
        )
        pred_records.append(
            {"sentence_id": sentence_id, "tokens": list(record.get("tokens") or []), "labels": labels}
        )

    result = ner_f1(pred_records, gold_records)
    result["n_gold_sentences"] = len(gold_records)
    result["n_matched_sentences"] = n_matched
    return result


def _spans_to_labels(
    text: str,
    tokens: list[str],
    entities: list[dict[str, Any]],
) -> list[str]:
    """Chuyển span ký tự → nhãn BIO ở mức word.

    Args:
        text: Văn bản câu.
        tokens: Word của câu.
        entities: Span ký tự.

    Returns:
        Danh sách nhãn BIO ở mức word.
    """
    from src.ner.build_silver import tokenize

    _words, starts, ends = tokenize(text)
    labels = ["O"] * len(starts)
    for entity in sorted(entities, key=lambda item: item["start"]):
        entity_type = str(entity.get("label"))
        covered = [
            index
            for index, (start, end) in enumerate(zip(starts, ends))
            if start >= entity["start"] and end <= entity["end"]
        ]
        if not covered:
            continue
        for position, index in enumerate(covered):
            prefix = "B" if position == 0 else "I"
            labels[index] = f"{prefix}-{entity_type}"
    return labels


def apply_manual_review(
    review_path: str | Path,
    out_path: str | Path,
    silver_path: str | Path,
) -> dict[str, Any]:
    """Áp dụng kết quả kiểm tra tay và sinh bộ gold + thống kê nhiễu.

    File review là JSONL, mỗi dòng là một kết quả kiểm tra tay cho một câu:

    ```json
    {"sentence_id": "s123_0_0",
     "keep": ["0", "2"],              // index mention trong `mentions` giữ nguyên
     "drop": ["1"],                   // index mention sai → bị loại
     "add": [{"label": "PERSON", "text": "Nguyễn Trãi"}],  // mention bị thiếu
     "notes": "sai loại"}
    ```

    Câu **không** có trong file review được giữ nguyên nhãn bạc (coi như đã
    kiểm tra và đúng).

    Args:
        review_path: File JSONL kết quả kiểm tra tay.
        out_path: File JSONL bộ gold đầu ra.
        silver_path: File JSONL nguồn (bộ audit 100 câu) chứa `mentions` gốc.

    Returns:
        Thống kê nhiễu nhãn bạc.
    """
    path = resolve_path(review_path)
    out = resolve_path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    silver_records = list(read_jsonl(resolve_path(silver_path)))
    silver = {str(record.get("sentence_id")): record for record in silver_records}
    reviews = {
        str(review.get("sentence_id")): review for review in read_jsonl(path)
    }

    stats = {
        "n_sentences_total": len(silver_records),
        "n_sentences_reviewed": len(reviews),
        "n_mentions_silver": 0,
        "n_mentions_kept": 0,
        "n_mentions_dropped": 0,
        "n_mentions_added": 0,
        "by_label": {},
    }
    out_lines: list[str] = []

    for sentence_id, source in silver.items():
        review = reviews.get(sentence_id, {})
        mentions = list(source.get("mentions") or [])
        tokens = list(source.get("tokens") or [])
        text = str(source.get("text") or "")

        drop = {int(index) for index in (review.get("drop") or [])}
        keep = (
            {int(index) for index in (review.get("keep") or [])}
            if review.get("keep") is not None
            else None
        )
        add = list(review.get("add") or [])

        labels = ["O"] * len(tokens)
        kept_mentions: list[dict[str, Any]] = []
        for index, mention in enumerate(mentions):
            label = str(mention.get("label"))
            bucket = stats["by_label"].setdefault(
                label, {"silver": 0, "wrong": 0}
            )
            bucket["silver"] += 1
            stats["n_mentions_silver"] += 1

            if index in drop:
                bucket["wrong"] += 1
                stats["n_mentions_dropped"] += 1
                continue
            if keep is not None and index not in keep:
                bucket["wrong"] += 1
                stats["n_mentions_dropped"] += 1
                continue

            kept_mentions.append(mention)
            stats["n_mentions_kept"] += 1
            # `end_token` là **exclusive** (xem `src/ner/build_silver.py::bioes_to_mentions`).
            start = int(mention.get("start_token", 0))
            end = int(mention.get("end_token", 0))
            for position, token_index in enumerate(range(start, end)):
                if 0 <= token_index < len(labels):
                    prefix = "B" if position == 0 else "I"
                    labels[token_index] = f"{prefix}-{label}"

        for mention in add:
            label = str(mention.get("label"))
            span = str(mention.get("text") or "")
            start, last = _find_token_span(tokens, span)
            if start is None:
                logger.warning("Không tìm thấy span trong token: %r (%s)", span, sentence_id)
                continue
            # `_find_token_span` trả về chỉ số token **cuối** (inclusive).
            end = last + 1  # quy ước `end_token` exclusive.
            for position, token_index in enumerate(range(start, end)):
                prefix = "B" if position == 0 else "I"
                labels[token_index] = f"{prefix}-{label}"
            kept_mentions.append(
                {
                    "start_token": start,
                    "end_token": end,
                    "label": label,
                    "text": span,
                    "target": span,
                    "qid": mention.get("qid"),
                    "source": "manual_review",
                    "target_type_confidence": 1.0,
                }
            )
            stats["n_mentions_added"] += 1

        out_lines.append(
            json.dumps(
                {
                    "sentence_id": sentence_id,
                    "doc_id": source.get("doc_id"),
                    "page_id": source.get("page_id"),
                    "text": text,
                    "tokens": tokens,
                    "labels": labels,
                    "mentions": kept_mentions,
                    "reviewed": sentence_id in reviews,
                    "review_notes": review.get("notes", ""),
                },
                ensure_ascii=False,
            )
        )

    out.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    stats["noise_rate_mention"] = (
        stats["n_mentions_dropped"] / stats["n_mentions_silver"]
        if stats["n_mentions_silver"]
        else 0.0
    )
    stats["missing_rate_mention"] = (
        stats["n_mentions_added"] / stats["n_mentions_silver"]
        if stats["n_mentions_silver"]
        else 0.0
    )
    logger.info("Đã ghi bộ gold: %s", out)
    return stats


def _find_token_span(tokens: list[str], span: str) -> tuple[int | None, int | None]:
    """Tìm vị trí token của một chuỗi con trong danh sách token.

    Args:
        tokens: Danh sách token.
        span: Chuỗi cần tìm.

    Returns:
        Cặp `(start, end)` hoặc `(None, None)` nếu không tìm thấy.
    """
    words = span.split()
    if not words:
        return None, None
    for start in range(len(tokens)):
        if tokens[start : start + len(words)] == words:
            return start, start + len(words) - 1
    return None, None


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Đo nhiễu nhãn bạc / tạo bộ gold NER")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--out", default="data/eval/ner_audit_100.jsonl")
    parser.add_argument("--score", action="store_true", help="Chế độ đo F1 trên bộ gold")
    parser.add_argument("--gold", default=None, help="File bộ gold (chế độ --score)")
    parser.add_argument(
        "--predictions",
        default="data/interim/ner_predictions.jsonl",
        help="File dự đoán (chế độ --score)",
    )
    parser.add_argument("--out-json", default=None, help="Ghi kết quả JSON (chế độ --score)")
    parser.add_argument(
        "--apply-review",
        default=None,
        help="File JSONL kết quả kiểm tra tay → sinh bộ gold + thống kê nhiễu",
    )
    parser.add_argument(
        "--review-out",
        default="data/eval/ner_gold_100.jsonl",
        help="File bộ gold đầu ra (chế độ --apply-review)",
    )
    parser.add_argument(
        "--review-stats-out",
        default=None,
        help="Ghi thống kê nhiễu ra file JSON (chế độ --apply-review)",
    )
    parser.add_argument(
        "--silver",
        default=None,
        help="File nguồn chứa `mentions` gốc (chế độ --apply-review)",
    )
    args = parser.parse_args(argv)

    from src.common.config import load_config

    config = load_config(args.config)
    ner_config = config.get("ner", {})
    silver_path = ner_config.get("silver_path", "data/interim/ner_silver.jsonl")
    splits_path = ner_config.get("splits_path", "data/splits/splits.json")

    if args.apply_review:
        stats = apply_manual_review(
            args.apply_review,
            args.review_out,
            args.silver or args.out,
        )
        payload = json.dumps(stats, ensure_ascii=False, indent=1)
        if args.review_stats_out:
            out = resolve_path(args.review_stats_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(payload + "\n", encoding="utf-8")
            logger.info("Đã ghi thống kê nhiễu: %s", out)
        else:
            print(payload)
        return 0

    if args.score:
        if not args.gold:
            parser.error("Chế độ --score cần --gold")
        result = score_on_gold(args.gold, args.predictions)
        payload = json.dumps(result, ensure_ascii=False, indent=1)
        if args.out_json:
            out = resolve_path(args.out_json)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(payload + "\n", encoding="utf-8")
            logger.info("Đã ghi %s", out)
        else:
            print(payload)
        return 0

    records = sample_sentences(
        silver_path, splits_path, args.split, args.sample, args.seed
    )
    path = write_audit_sample(records, args.out)
    logger.info(
        "Đã xuất %d câu %s → %s (kiểm tra tay, sửa `labels` rồi lưu lại)",
        len(records),
        args.split,
        path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

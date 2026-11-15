"""Suy luận NER trên toàn corpus (Phase 5 — B2).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 5.

Cách chạy
---------
```bash
python -m src.ner.infer_ner --model models/ner --out data/interim/ner_predictions.jsonl
```

Output contract (`docs/09` §Phase 5)
------------------------------------
```json
{"sentence_id": "s80_0_0", "doc_id": "doc_80", "text": "...",
 "entities": [{"start": 0, "end": 10, "text": "Lê Lợi", "label": "PERSON", "score": 0.99}]}
```

- Offset là **chỉ số ký tự Python** trong `text` — bắt buộc
  `text[start:end] == entity["text"]` (kiểm tra 100% khi chạy).
- Nhãn ∈ 6 nhãn của `src.common.schemas.NER_LABELS`.

Nhất quán với huấn luyện
-----------------------
Cả train lẫn infer đều token hóa theo **word** (`src.ner.build_silver.tokenize`
+ `WordTokenizer.tokenize_word`) → phân bố subword giống hệt (D-039: token hóa
raw text khác token hóa word ở 1.883/2.000 câu).

Offset ký tự lấy từ `src.ner.build_silver.tokenize` — **cùng hàm** đã sinh ra
`tokens` trong artifact nhãn bạc → `text[start:end] == span_text` luôn đúng.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator, Sequence

from src.common.config import load_config, resolve_path
from src.common.logger import get_logger
from src.ner.build_silver import tokenize
from src.ner.data_convert import (
    LABEL2ID,
    LABEL_LIST,
    NUM_LABELS,
    encode_words,
    load_tokenizer,
    read_jsonl,
    subword_windows,
)

logger = get_logger(__name__)


def word_labels_to_entities(
    text: str,
    word_labels: Sequence[int],
    word_starts: Sequence[int],
    word_ends: Sequence[int],
    *,
    score_threshold: float,
    scores: Sequence[float] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Chuyển nhãn BIO ở mức word → span ký tự.

    Args:
        text: Văn bản câu.
        word_labels: Nhãn id ở mức word.
        word_starts: Vị trí ký tự bắt đầu của từng word.
        word_ends: Vị trí ký tự kết thúc (exclusive) của từng word.
        score_threshold: Ngưỡng điểm tối thiểu để giữ span.
        scores: Điểm của từng word (nếu có).

    Returns:
        Cặp ``(entities, n_invalid)`` — danh sách span và số span bị loại
        vì offset không khớp văn bản.
    """
    entities: list[dict[str, Any]] = []
    invalid = 0
    index = 0
    total = len(word_labels)
    while index < total:
        label = LABEL_LIST[word_labels[index]]
        if label == "O":
            index += 1
            continue
        prefix, _, entity_type = label.partition("-")
        if prefix != "B":
            index += 1
            continue
        start_word = index
        end_word = index + 1
        while end_word < total:
            nxt = LABEL_LIST[word_labels[end_word]]
            if nxt == "O" or "-" not in nxt:
                break
            nxt_prefix, _, nxt_type = nxt.partition("-")
            if nxt_type != entity_type or nxt_prefix != "I":
                break
            end_word += 1

        char_start = word_starts[start_word]
        char_end = word_ends[end_word - 1]
        span_text = text[char_start:char_end]

        if scores is not None and end_word - 1 < len(scores):
            span_scores = [float(value) for value in scores[start_word:end_word]]
            score = sum(span_scores) / len(span_scores) if span_scores else 0.0
        else:
            score = 1.0

        if not span_text.strip() or char_end <= char_start:
            invalid += 1
        elif score < score_threshold:
            pass
        else:
            entities.append(
                {
                    "start": char_start,
                    "end": char_end,
                    "text": span_text,
                    "label": entity_type,
                    "score": round(score, 4),
                }
            )
        index = end_word
    return entities, invalid


def predict_batch(
    model: Any,
    tokenizer: Any,
    records: Sequence[dict[str, Any]],
    *,
    max_len: int = 256,
    stride: int = 64,
    score_threshold: float = 0.5,
    device: Any = None,
    micro_batch_size: int = 32,
    use_fp16: bool = False,
) -> Iterator[dict[str, Any]]:
    """Dự đoán NER cho một lô câu.

    Args:
        model: Mô hình đã nạp (ở chế độ eval).
        tokenizer: `WordTokenizer`.
        records: Record có `text`, `sentence_id`, `doc_id`.
        max_len: Độ dài tối đa (kể cả ``<s>``/``</s>``).
        stride: Bước nhảy giữa hai cửa sổ.
        score_threshold: Ngưỡng điểm tối thiểu để giữ span.
        device: Thiết bị torch (nếu None → lấy từ model).
        micro_batch_size: Số cửa sổ suy luận tối đa mỗi lần forward.
            Chia nhỏ để tránh OOM với `phobert-large`.
        use_fp16: Ép `float16` khi có CUDA.

    Yields:
        Record kết quả theo Output contract.
    """
    import torch

    if device is None:
        device = next(model.parameters()).device

    prepared: list[dict[str, Any]] = []
    for record in records:
        text = str(record.get("text", ""))
        words, word_starts, word_ends = tokenize(text)
        item: dict[str, Any] = {
            "record": record,
            "text": text,
            "words": words,
            "word_starts": word_starts,
            "word_ends": word_ends,
        }
        if words:
            encoded = encode_words(tokenizer, words, ["O"] * len(words))
            item["encoded"] = encoded
            item["windows"] = subword_windows(len(encoded["input_ids"]), max_len, stride)
        prepared.append(item)

    cls_id = tokenizer.cls_token_id
    sep_id = tokenizer.sep_token_id

    flat_input_ids: list[list[int]] = []
    flat_word_ids: list[list[int]] = []
    owner: list[int] = []
    for index, item in enumerate(prepared):
        encoded = item.get("encoded")
        if not encoded:
            continue
        for window_start, window_end in item["windows"]:
            flat_input_ids.append(
                [cls_id, *encoded["input_ids"][window_start:window_end], sep_id]
            )
            flat_word_ids.append([-1, *encoded["word_ids"][window_start:window_end], -1])
            owner.append(index)

    if not flat_input_ids:
        for item in prepared:
            record = item["record"]
            yield {
                "sentence_id": str(record.get("sentence_id", "")),
                "doc_id": str(record.get("doc_id", "")),
                "text": item["text"],
                "entities": [],
            }
        return

    max_batch_len = max(len(ids) for ids in flat_input_ids)
    input_ids = torch.full(
        (len(flat_input_ids), max_batch_len), tokenizer.pad_token_id, dtype=torch.long
    )
    attention_mask = torch.zeros((len(flat_input_ids), max_batch_len), dtype=torch.long)
    for row, ids in enumerate(flat_input_ids):
        input_ids[row, : len(ids)] = torch.tensor(ids, dtype=torch.long)
        attention_mask[row, : len(ids)] = 1

    # Suy luận theo micro-batch để không OOM (đo được 14/11/2026:
    # `phobert-large` OOM khi forward cả lô 64 câu ~ 200 cửa sổ).
    micro_batch_size = max(1, int(micro_batch_size))
    use_amp = bool(use_fp16) and device is not None and str(device).startswith("cuda")

    all_logits: list[Any] = []
    with torch.no_grad():
        for start in range(0, len(flat_input_ids), micro_batch_size):
            end = min(start + micro_batch_size, len(flat_input_ids))
            chunk_ids = input_ids[start:end].to(device)
            chunk_mask = attention_mask[start:end].to(device)
            if use_amp:
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    chunk_out = model(input_ids=chunk_ids, attention_mask=chunk_mask)
            else:
                chunk_out = model(input_ids=chunk_ids, attention_mask=chunk_mask)
            all_logits.append(chunk_out.logits.float().cpu())
    logits = torch.cat(all_logits, dim=0) if all_logits else torch.zeros((0, 0))
    probabilities = torch.softmax(logits, dim=-1)

    # Gom nhãn dự đoán theo word cho từng câu (cửa sổ đầu được ưu tiên).
    word_predictions: dict[int, dict[int, int]] = {}
    word_confidences: dict[int, dict[int, float]] = {}
    for row, item_index in enumerate(owner):
        item = prepared[item_index]
        sub_word_ids = flat_word_ids[row]
        best: dict[int, tuple[int, float]] = {}
        for position in range(len(sub_word_ids)):
            word_id = sub_word_ids[position]
            if word_id is None or word_id < 0:
                continue
            if word_id in best:
                continue
            row_logits = logits[row, position]
            label_id = int(
                max(range(NUM_LABELS), key=lambda index: float(row_logits[index]))
            )
            probability = float(probabilities[row, position, label_id])
            best[word_id] = (label_id, probability)
        current = word_predictions.setdefault(item_index, {})
        current_conf = word_confidences.setdefault(item_index, {})
        for word_id, (label_id, probability) in best.items():
            if word_id not in current:
                current[word_id] = label_id
                current_conf[word_id] = probability
            elif probability > current_conf[word_id]:
                current[word_id] = label_id
                current_conf[word_id] = probability

    for index, item in enumerate(prepared):
        record = item["record"]
        n_words = len(item["words"])
        if n_words == 0:
            yield {
                "sentence_id": str(record.get("sentence_id", "")),
                "doc_id": str(record.get("doc_id", "")),
                "text": item["text"],
                "entities": [],
            }
            continue

        prediction_map = word_predictions.get(index, {})
        confidence_map = word_confidences.get(index, {})
        word_labels = [LABEL2ID["O"]] * n_words
        word_scores = [0.0] * n_words
        for word_id, label_id in prediction_map.items():
            if 0 <= word_id < n_words:
                word_labels[word_id] = label_id
                word_scores[word_id] = confidence_map.get(word_id, 0.0)

        entities, invalid = word_labels_to_entities(
            item["text"],
            word_labels,
            item["word_starts"],
            item["word_ends"],
            score_threshold=score_threshold,
            scores=word_scores,
        )
        if invalid:
            logger.warning(
                "Câu %s: %d span bị loại vì offset không khớp",
                record.get("sentence_id"),
                invalid,
            )

        yield {
            "sentence_id": str(record.get("sentence_id", "")),
            "doc_id": str(record.get("doc_id", "")),
            "text": item["text"],
            "entities": entities,
        }


def load_model(model_dir: str) -> tuple[Any, Any]:
    """Nạp model + tokenizer từ thư mục đã huấn luyện.

    Args:
        model_dir: Thư mục model (chứa `config.json`, `model.safetensors`).

    Returns:
        Cặp ``(model, tokenizer)``.
    """
    from transformers import AutoModelForTokenClassification

    resolved = resolve_path(model_dir)
    config_path = resolved / "config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Không tìm thấy model tại {resolved}")

    model = AutoModelForTokenClassification.from_pretrained(str(resolved))
    model.eval()

    tokenizer = load_tokenizer(str(resolved))
    return model, tokenizer


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Suy luận NER toàn corpus (Phase 5)")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--model", default=None, help="Thư mục model")
    parser.add_argument("--input", default=None, help="Đường dẫn nhãn bạc (nguồn câu)")
    parser.add_argument("--out", default=None, help="Đường dẫn output JSONL")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-len", type=int, default=None)
    parser.add_argument("--stride", type=int, default=None)
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument(
        "--micro-batch-size",
        type=int,
        default=None,
        help="Số cửa sổ suy luận tối đa mỗi forward (tránh OOM)",
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        help="Ép float16 khi có CUDA",
    )
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số câu (0 = tất cả)")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    ner_config = config.get("ner", {})
    infer_config = dict(ner_config.get("infer", {}))

    model_dir = args.model or infer_config.get("model_dir", "models/ner")
    input_path = args.input or ner_config.get(
        "silver_path", "data/interim/ner_silver.jsonl"
    )
    output_path = resolve_path(
        args.out
        or ner_config.get("predictions_path", "data/interim/ner_predictions.jsonl")
    )
    batch_size = args.batch_size or int(infer_config.get("batch_size", 64))
    max_len = args.max_len or int(infer_config.get("max_len", 256))
    stride = args.stride or int(infer_config.get("stride", 64))
    score_threshold = (
        args.score_threshold
        if args.score_threshold is not None
        else float(infer_config.get("score_threshold", 0.5))
    )
    # `phobert-large` cần micro-batch nhỏ hơn để không OOM (đo 14/11/2026).
    micro_batch_size = args.micro_batch_size or int(
        infer_config.get("micro_batch_size", 16)
    )
    use_fp16 = args.fp16 or bool(infer_config.get("fp16", False))

    model, tokenizer = load_model(model_dir)
    logger.info(
        "Model %s | batch=%d | max_len=%d | stride=%d | ngưỡng=%.2f",
        model_dir,
        batch_size,
        max_len,
        stride,
        score_threshold,
    )

    records = read_jsonl(resolve_path(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_sentences = 0
    n_entities = 0
    batch: list[dict[str, Any]] = []

    def flush(items: list[dict[str, Any]]) -> None:
        """Ghi kết quả một lô câu ra file.

        Args:
            items: Danh sách câu cần ghi.
        """
        nonlocal n_sentences, n_entities
        for result in predict_batch(
            model,
            tokenizer,
            items,
            max_len=max_len,
            stride=stride,
            score_threshold=score_threshold,
            micro_batch_size=micro_batch_size,
            use_fp16=use_fp16,
        ):
            n_sentences += 1
            n_entities += len(result["entities"])
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")

    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            if args.limit and n_sentences >= args.limit:
                break
            batch.append(record)
            if len(batch) < batch_size:
                continue
            flush(batch)
            batch = []
            if n_sentences % 10000 < batch_size:
                logger.info("Đã xử lý %d câu, %d entity", n_sentences, n_entities)
        if batch:
            flush(batch)

    logger.info(
        "Hoàn tất: %d câu, %d entity → %s",
        n_sentences,
        n_entities,
        output_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Suy luận mô hình RE trên toàn corpus (Phase 8 — D1.2).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 8.

Cách chạy
---------
```bash
python -m src.re.infer_re --model models/re --out data/interim/re_phobert.jsonl
```

Sinh cặp ứng viên
------------------
Theo đặc tả: "sinh cặp ứng viên từ mention trong câu (cặp có cùng câu, cách
nhau ≤ 60 token)".

Đo được trên `coref_resolved.jsonl` (186.960 câu, 137.584 mention có
`canonical_id`):

| Cách đếm | Số cặp |
|---|---|
| Mọi cặp mention, ≤ 60 token (kể cả cùng `canonical_id`) | **113.917** |
| — trong đó cùng `canonical_id` (self-pair) | 14.569 |
| — **cặp `canonical_id` khác nhau** (dùng để suy luận) | **99.348** |

→ Module này dùng **99.348** cặp có `canonical_id` **khác nhau** (self-pair là
self-loop, sẽ bị loại ở `merge_triples` theo bất kỳ đường nào).

Khoảng cách được đo bằng **số token khoảng trắng** (``text.split()``) — cùng
cách đo đã dùng để đạt con số 113.917 trong kế hoạch.

Lọc kết quả
------------
Mô hình có 19 đầu sigmoid (18 quan hệ + ``NA``). Quan hệ ``r`` được giữ khi:

- ``sigmoid(r) > threshold`` (mặc định 0,5, hiệu chỉnh trên dev), **và**
- ``sigmoid(NA) < na_threshold`` (mặc định 0,5).

Output contract (`docs/09` §Phase 8)
------------------------------------
```json
{"sentence_id":"s1_0_3","text":"...","pairs":[
  {"subject":"ent_...","relation":"cha_cua","object":"ent_...",
   "confidence":0.97,"evidence_sentence":"...","method":"phobert_re"}]}
```
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger
from src.common.schemas import RELATION_ORDER
from src.re.data_convert_re import (
    NA_INDEX,
    NUM_LABELS,
    build_display_names,
    build_entity_types,
    encode_pair,
    resolve_entity_type,
)
from src.re.train_re import sigmoid

logger = get_logger(__name__)

#: Ngưỡng kích hoạt quan hệ (mặc định — có thể ghi đè qua `configs/default.yaml`).
DEFAULT_THRESHOLD = 0.5

#: Ngưỡng đầu ``NA`` — dưới ngưỡng này mới coi cặp là "có quan hệ".
DEFAULT_NA_THRESHOLD = 0.5

#: Khoảng cách tối đa (token) giữa hai mention để sinh cặp ứng viên.
DEFAULT_MAX_DISTANCE = 60


def token_index(text: str, char_start: int) -> int:
    """Tính chỉ số token (khoảng trắng) tương ứng với một vị trí ký tự.

    Args:
        text: Văn bản câu.
        char_start: Vị trí ký tự bắt đầu.

    Returns:
        Chỉ số token (0-based).
    """
    return len(text[:char_start].split())


def iter_candidate_pairs(
    coref_path: str | Path,
    *,
    max_distance: int = DEFAULT_MAX_DISTANCE,
) -> Iterator[dict[str, Any]]:
    """Sinh cặp ứng viên từ `coref_resolved.jsonl`.

    Mỗi cặp có hai mention **khác `canonical_id`**, cùng câu, cách nhau không
    quá `max_distance` token.

    Args:
        coref_path: Đường dẫn `coref_resolved.jsonl`.
        max_distance: Khoảng cách tối đa (token).

    Yields:
        Dict thông tin cặp ứng viên.
    """
    with Path(coref_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            text = str(record.get("text", ""))
            mentions = [
                mention
                for mention in record.get("mentions") or []
                if mention.get("canonical_id")
            ]
            if len(mentions) < 2:
                continue
            indexed = []
            for mention in mentions:
                indexed.append(
                    (
                        token_index(text, int(mention.get("start", 0))),
                        mention,
                    )
                )
            for i in range(len(indexed)):
                for j in range(i + 1, len(indexed)):
                    distance = abs(indexed[i][0] - indexed[j][0])
                    if distance > max_distance:
                        continue
                    left = indexed[i][1]
                    right = indexed[j][1]
                    if str(left["canonical_id"]) == str(right["canonical_id"]):
                        continue
                    yield {
                        "sentence_id": str(record.get("sentence_id", "")),
                        "doc_id": str(record.get("doc_id", "")),
                        "text": text,
                        "left": left,
                        "right": right,
                        "distance": distance,
                    }


def build_batch(
    candidates: Sequence[dict[str, Any]],
    tokenizer: Any,
    types: dict[str, str],
    names: dict[str, str],
    *,
    max_len: int = 256,
    context_words: int = 48,
) -> tuple[list[list[int]], list[list[int]], list[dict[str, Any]]]:
    """Mã hoá một batch cặp ứng viên.

    Args:
        candidates: Danh sách cặp ứng viên.
        tokenizer: `WordTokenizer`.
        types: Bảng ``entity_id`` → type KG.
        names: Bảng ``entity_id`` → tên hiển thị.
        max_len: Độ dài tối đa.
        context_words: Số word ngữ cảnh mỗi bên.

    Returns:
        Bộ ba ``(input_ids, attention_mask, metadata)``.
    """
    input_ids: list[list[int]] = []
    attention_mask: list[list[int]] = []
    metadata: list[dict[str, Any]] = []
    for candidate in candidates:
        left = candidate["left"]
        right = candidate["right"]
        subject = {
            "mention": str(left.get("text", "")),
            "start": int(left.get("start", 0)),
            "end": int(left.get("end", 0)),
        }
        object_ = {
            "mention": str(right.get("text", "")),
            "start": int(right.get("start", 0)),
            "end": int(right.get("end", 0)),
        }
        subject_id = str(left.get("canonical_id", ""))
        object_id = str(right.get("canonical_id", ""))
        ids, mask = encode_pair(
            tokenizer,
            candidate["text"],
            subject,
            object_,
            resolve_entity_type(subject_id, types),
            resolve_entity_type(object_id, types),
            subject_name=names.get(subject_id, ""),
            object_name=names.get(object_id, ""),
            max_len=max_len,
            context_words=context_words,
        )
        if not ids:
            continue
        input_ids.append(ids)
        attention_mask.append(mask)
        metadata.append(
            {
                "sentence_id": candidate["sentence_id"],
                "doc_id": candidate["doc_id"],
                "text": candidate["text"],
                "subject": subject_id,
                "object": object_id,
                "subject_mention": subject["mention"],
                "object_mention": object_["mention"],
            }
        )
    return input_ids, attention_mask, metadata


def pad_batch(
    input_ids: list[list[int]],
    attention_mask: list[list[int]],
    pad_token_id: int,
) -> tuple[Any, Any]:
    """Pad một batch về cùng độ dài.

    Args:
        input_ids: Danh sách id subword.
        attention_mask: Danh sách mặt nạ.
        pad_token_id: Id token padding.

    Returns:
        Cặp tensor ``(input_ids, attention_mask)``.
    """
    import torch

    max_len = max(len(ids) for ids in input_ids)
    padded_ids = [
        ids + [pad_token_id] * (max_len - len(ids)) for ids in input_ids
    ]
    padded_mask = [
        mask + [0] * (max_len - len(mask)) for mask in attention_mask
    ]
    return (
        torch.tensor(padded_ids, dtype=torch.long),
        torch.tensor(padded_mask, dtype=torch.long),
    )


def select_relations(
    row: Sequence[float],
    *,
    threshold: float,
    na_threshold: float,
) -> list[tuple[str, float]]:
    """Chọn các quan hệ vượt ngưỡng cho một hàng xác suất.

    Args:
        row: Xác suất 19 chiều.
        threshold: Ngưỡng kích hoạt quan hệ.
        na_threshold: Ngưỡng đầu ``NA``.

    Returns:
        Danh sách ``(relation, confidence)``.
    """
    if float(row[NA_INDEX]) >= na_threshold:
        return []
    selected: list[tuple[str, float]] = []
    for index, relation in enumerate(RELATION_ORDER):
        score = float(row[index])
        if score > threshold:
            selected.append((relation, round(score, 4)))
    return selected


def write_predictions(
    path: str | Path,
    predictions: dict[str, list[dict[str, Any]]],
    texts: dict[str, str] | None = None,
) -> int:
    """Ghi kết quả suy luận ra JSONL (1 record/câu).

    Args:
        path: Đường dẫn đích.
        predictions: Map ``sentence_id`` → danh sách pair dự đoán.
        texts: Map ``sentence_id`` → nội dung câu (dùng cho trường ``text``).

    Returns:
        Số câu đã ghi.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for sentence_id, pairs in predictions.items():
            if not pairs:
                continue
            text = ""
            if texts:
                text = texts.get(sentence_id, "")
            if not text:
                text = str(pairs[0].get("evidence_sentence", ""))
            handle.write(
                json.dumps(
                    {
                        "sentence_id": sentence_id,
                        "text": text,
                        "pairs": [
                            {
                                key: value
                                for key, value in pair.items()
                                if not key.startswith("_")
                            }
                            for pair in pairs
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Suy luận mô hình RE trên toàn corpus (Phase 8)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--model", default=None, help="Thư mục model (mặc định models/re)")
    parser.add_argument("--out", default=None, help="Đường dẫn file đầu ra")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--na-threshold", type=float, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--max-len", type=int, default=None)
    parser.add_argument("--max-distance", type=int, default=None)
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số cặp (smoke test)")
    parser.add_argument(
        "--num-shards", type=int, default=1,
        help="Chia cặp ứng viên cho N tiến trình (chạy song song trên CPU)",
    )
    parser.add_argument(
        "--shard-index", type=int, default=0,
        help="Chỉ số shard (0..num-shards-1)",
    )
    parser.add_argument(
        "--candidates-cache", default=None,
        help="File cache cặp ứng viên (chia sẻ giữa các shard)",
    )
    args = parser.parse_args(argv)

    config = load_default_config()
    re_config = config.get("re", {})
    infer_config = dict(re_config.get("infer", {}))
    convert_config = dict(re_config.get("convert", {}))

    model_dir = resolve_path(
        args.model or infer_config.get("model_dir", "models/re")
    )
    out_path = resolve_path(
        args.out or re_config.get("predictions_path", "data/interim/re_phobert.jsonl")
    )
    threshold = (
        args.threshold
        if args.threshold is not None
        else float(infer_config.get("threshold", DEFAULT_THRESHOLD))
    )
    na_threshold = (
        args.na_threshold
        if args.na_threshold is not None
        else float(infer_config.get("na_threshold", DEFAULT_NA_THRESHOLD))
    )
    batch_size = args.batch_size or int(infer_config.get("batch_size", 64))
    max_len = args.max_len or int(infer_config.get("max_len", 256))
    context_words = int(convert_config.get("context_words", 48))
    max_distance = args.max_distance or int(
        infer_config.get("max_pair_distance_tokens", DEFAULT_MAX_DISTANCE)
    )

    metrics_path = model_dir / "metrics.json"
    if metrics_path.exists():
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        meta = payload.get("_meta", {})
        if "threshold" in meta:
            threshold = float(meta["threshold"])
            logger.info("Dùng ngưỡng hiệu chỉnh từ metrics.json: %.2f", threshold)
        if "na_threshold" in meta:
            na_threshold = float(meta["na_threshold"])

    from transformers import AutoModelForSequenceClassification

    from src.ner.data_convert import load_tokenizer

    logger.info("Nạp model: %s", model_dir)
    tokenizer = load_tokenizer(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
    model.eval()

    import torch

    # Số thread: theo `OMP_NUM_THREADS` (shard runner đặt 2 mỗi tiến trình).
    # Đo được: mặc định torch chỉ dùng 4 thread dù OMP=8 → tốc độ giảm ~30%.
    thread_env = os.environ.get("OMP_NUM_THREADS")
    if thread_env:
        torch.set_num_threads(max(1, int(thread_env)))
    logger.info("Torch threads: %d", torch.get_num_threads())

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    types = build_entity_types(
        re_config.get("coref_path", "data/interim/coref_resolved.jsonl"),
        re_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl"),
    )
    names = build_display_names(
        re_config.get("coref_path", "data/interim/coref_resolved.jsonl"),
        re_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl"),
    )

    logger.info(
        "Sinh cặp ứng viên (≤ %d token) từ %s",
        max_distance,
        re_config.get("coref_path", "data/interim/coref_resolved.jsonl"),
    )

    predictions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    texts: dict[str, str] = {}
    n_candidates = 0
    n_kept = 0
    started = time.time()

    def flush(batch_candidates: list[dict[str, Any]]) -> None:
        """Mã hoá + suy luận một batch cặp ứng viên.

        Args:
            batch_candidates: Danh sách cặp ứng viên trong batch.
        """
        nonlocal n_kept
        if not batch_candidates:
            return
        input_ids, attention_mask, metadata = build_batch(
            batch_candidates,
            tokenizer,
            types,
            names,
            max_len=max_len,
            context_words=context_words,
        )
        if not input_ids:
            return
        ids_tensor, mask_tensor = pad_batch(
            input_ids, attention_mask, tokenizer.pad_token_id
        )
        with torch.no_grad():
            outputs = model(
                input_ids=ids_tensor.to(device),
                attention_mask=mask_tensor.to(device),
            )
        probabilities = sigmoid(outputs.logits.detach().cpu().numpy())
        for index, meta in enumerate(metadata):
            texts[meta["sentence_id"]] = meta["text"]
            row = probabilities[index]
            for relation, confidence in select_relations(
                row, threshold=threshold, na_threshold=na_threshold
            ):
                n_kept += 1
                predictions[meta["sentence_id"]].append(
                    {
                        "subject": meta["subject"],
                        "relation": relation,
                        "object": meta["object"],
                        "confidence": confidence,
                        "evidence_sentence": meta["text"],
                        "method": "phobert_re",
                    }
                )

    batch: list[dict[str, Any]] = []
    num_shards = max(1, int(args.num_shards))
    shard_index = int(args.shard_index) % num_shards
    # Cache cặp ứng viên 1 lần rồi mới chia shard — nếu không, mỗi shard phải
    # quét lại toàn bộ `coref_resolved.jsonl` (đo được: 4 shard × ~3 phút quét
    # trước khi bắt đầu suy luận).
    cache_path = args.candidates_cache or None
    if cache_path and Path(cache_path).exists():
        with Path(cache_path).open("r", encoding="utf-8") as handle:
            all_candidates = [json.loads(line) for line in handle if line.strip()]
        logger.info("Nạp %d cặp ứng viên từ cache %s", len(all_candidates), cache_path)
    else:
        all_candidates = list(
            iter_candidate_pairs(
                re_config.get("coref_path", "data/interim/coref_resolved.jsonl"),
                max_distance=max_distance,
            )
        )
        if cache_path:
            with Path(cache_path).open("w", encoding="utf-8") as handle:
                for candidate in all_candidates:
                    handle.write(json.dumps(candidate, ensure_ascii=False) + "\n")
            logger.info("Đã cache %d cặp ứng viên → %s", len(all_candidates), cache_path)

    for pair_index, candidate in enumerate(all_candidates):
        if num_shards > 1 and pair_index % num_shards != shard_index:
            continue
        n_candidates += 1
        batch.append(candidate)
        if len(batch) >= batch_size:
            flush(batch)
            batch = []
            if n_candidates % (batch_size * 5) == 0:
                elapsed = time.time() - started
                logger.info(
                    "Đã xử lý %d cặp | giữ %d quan hệ | %.1fs (%.4fs/cặp)",
                    n_candidates,
                    n_kept,
                    elapsed,
                    elapsed / max(n_candidates, 1),
                )
            if args.limit and n_candidates >= args.limit:
                break
    flush(batch)

    logger.info(
        "Xong: %d cặp ứng viên | %d quan hệ giữ lại | %.1fs",
        n_candidates,
        n_kept,
        time.time() - started,
    )

    n_sentences = write_predictions(out_path, predictions, texts)
    logger.info("Đã ghi %d câu ra %s", n_sentences, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

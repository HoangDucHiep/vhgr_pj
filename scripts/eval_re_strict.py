#!/usr/bin/env python3
"""Đo chất lượng **nghiêm ngặt** của mô hình RE trên tập dev/test.

Vì sao cần
-----------
Metric Phase 8 (`relation_f1_multilabel`) **bỏ qua** các slot bị mask
(quan hệ chưa được giám sát cho input đó). Trong dữ liệu train, slot NEGATIVE
chỉ supervise **một** quan hệ ⇒ 17/18 đầu còn lại **không** có gradient ⇒
khi suy luận trên corpus, các đầu này tự do phát ra giá trị cao (đo được
13,5 quan hệ/cặp) mà **không** bị metric phạt.

Script này đo lại trên tập dev với quy tắc **nghiêm**: mọi quan hệ dự đoán
ngoài tập gold đều tính là false positive (kể cả slot bị mask).

Cách dùng:
    python scripts/eval_re_strict.py --split dev
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.common.schemas import RELATION_ORDER
from src.re.data_convert_re import NA_INDEX
from src.re.train_re import sigmoid


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="dev")
    parser.add_argument("--model", default="models/re")
    parser.add_argument("--input", default="data/interim/re_model_input.jsonl")
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--na-threshold", type=float, default=0.5)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForSequenceClassification

    model = AutoModelForSequenceClassification.from_pretrained(args.model)
    model.eval()

    rows = []
    with Path(args.input).open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if str(record.get("split", "")) != args.split:
                continue
            rows.append(record)
    print(f"Số input ({args.split}): {len(rows)}")

    tp = fp = fn = 0
    n_pairs = 0
    n_fired_pairs = 0
    fp_masked = 0
    fired_counts: list[int] = []
    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]
        max_len = max(len(record["input_ids"]) for record in batch)
        pad = 0
        input_ids = torch.tensor(
            [
                list(record["input_ids"]) + [pad] * (max_len - len(record["input_ids"]))
                for record in batch
            ]
        )
        attention_mask = torch.tensor(
            [
                list(record["attention_mask"])
                + [0] * (max_len - len(record["attention_mask"]))
                for record in batch
            ]
        )
        with torch.no_grad():
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
        probabilities = sigmoid(outputs.logits.numpy())
        for index, record in enumerate(batch):
            gold = set(record.get("gold_relations") or [])
            masked = set(record.get("masked_relations") or [])
            row = probabilities[index]
            fired = []
            if float(row[NA_INDEX]) < args.na_threshold:
                for relation_index, relation in enumerate(RELATION_ORDER):
                    if float(row[relation_index]) > args.threshold:
                        fired.append(relation)
            n_pairs += 1
            if fired:
                n_fired_pairs += 1
            fired_counts.append(len(fired))
            fired_set = set(fired)
            tp += len(fired_set & gold)
            fn += len(gold - fired_set)
            fp += len(fired_set - gold)
            fp_masked += len((fired_set - gold) & masked)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    print(f"NGHIÊM — precision={precision:.4f} recall={recall:.4f} f1={f1:.4f}")
    print(f"  TP={tp} FP={fp} (trong đó {fp_masked} thuộc slot MASK) FN={fn}")
    print(
        f"  cặp có quan hệ dự đoán: {n_fired_pairs}/{n_pairs} "
        f"({n_fired_pairs / max(n_pairs, 1):.1%})"
    )
    print(f"  số quan hệ fire/cặp: {Counter(fired_counts).most_common(8)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

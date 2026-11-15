"""Đo throughput train NER trên CPU local (dùng để lên kế hoạch fallback).

Không thuộc pipeline chính — script benchmark dùng một lần cho Phase 5.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ner.data_convert import (  # noqa: E402
    ID2LABEL,
    LABEL2ID,
    NUM_LABELS,
    build_examples,
    load_tokenizer,
)
from src.ner.train_ner import DynamicPadCollator, NerDataset  # noqa: E402
from transformers import AutoModelForTokenClassification  # noqa: E402


def main() -> int:
    """Chạy benchmark."""
    max_len = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    bs = int(sys.argv[2]) if len(sys.argv) > 2 else 32
    n_sample = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
    threads = int(sys.argv[4]) if len(sys.argv) > 4 else 8

    torch.set_num_threads(threads)
    tokenizer = load_tokenizer("vinai/phobert-base")
    records: list[dict] = []
    with Path("data/interim/ner_silver.jsonl").open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if index >= n_sample:
                break
            records.append(json.loads(line))

    t0 = time.time()
    examples = build_examples(records, tokenizer, max_len=max_len, stride=32)
    encode_s = time.time() - t0
    lengths = [len(example.input_ids) for example in examples]
    total_tokens = sum(lengths)

    model = AutoModelForTokenClassification.from_pretrained(
        "vinai/phobert-base",
        num_labels=NUM_LABELS,
        id2label=dict(ID2LABEL),
        label2id=dict(LABEL2ID),
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-5)
    collator = DynamicPadCollator(tokenizer.pad_token_id)
    dataset = NerDataset(examples)

    # Length-grouped: sắp xếp theo độ dài → batch không phải pad nhiều.
    order = sorted(range(len(examples)), key=lambda i: lengths[i])
    model.train()
    t0 = time.time()
    n_seq = 0
    n_real_tokens = 0
    for start in range(0, len(order), bs):
        batch = [dataset[i] for i in order[start : start + bs]]
        batch_out = collator(batch)
        output = model(
            input_ids=batch_out["input_ids"],
            attention_mask=batch_out["attention_mask"],
            labels=batch_out["labels"],
        )
        output.loss.backward()
        optimizer.step()
        optimizer.zero_grad()
        n_seq += len(batch)
        n_real_tokens += int(batch_out["attention_mask"].sum())
    train_s = time.time() - t0

    corpus_tokens = 6_29_000_000  # xấp xỉ: 186.960 câu × ~33.7 token
    seq_per_s = n_seq / train_s
    tok_per_s = n_real_tokens / train_s
    print(
        json.dumps(
            {
                "max_len": max_len,
                "batch_size": bs,
                "threads": threads,
                "n_examples": len(examples),
                "encode_s": round(encode_s, 1),
                "mean_len": round(total_tokens / len(examples), 1),
                "train_s": round(train_s, 1),
                "seq_per_s": round(seq_per_s, 2),
                "tok_per_s": round(tok_per_s, 0),
                "epoch_hours_full_corpus": round(corpus_tokens / tok_per_s / 3600, 2),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

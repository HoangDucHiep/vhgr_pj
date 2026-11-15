#!/usr/bin/env python3
"""Chẩn đoán nhanh chất lượng mô hình RE trên corpus (mẫu nhỏ).

Mục tiêu: kiểm tra giả thuyết "1 cặp ứng viên bị fire quá nhiều quan hệ"
và đo phân phối đầu `NA` trên dữ liệu corpus (ngoài tập dev).

Cách dùng:
    python scripts/diag_re_quality.py --n 300
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.re.data_convert_re import NA_INDEX, build_display_names, build_entity_types
from src.re.infer_re import build_batch, iter_candidate_pairs, pad_batch
from src.re.train_re import sigmoid


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=300)
    parser.add_argument("--model", default="models/re")
    parser.add_argument("--coref", default="data/interim/coref_resolved.jsonl")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForSequenceClassification

    from src.ner.data_convert import load_tokenizer
    from src.common.config import load_default_config, resolve_path

    config = load_default_config()
    re_config = config.get("re", {})
    tokenizer = load_tokenizer(args.model)
    model = AutoModelForSequenceClassification.from_pretrained(args.model)
    model.eval()

    types = build_entity_types(
        re_config.get("coref_path", args.coref),
        re_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl"),
    )
    names = build_display_names(
        re_config.get("coref_path", args.coref),
        re_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl"),
    )

    # Nạp kết quả đã lưu để đối chiếu.
    stored: dict[tuple[str, str, str], list[tuple[str, float]]] = defaultdict(list)
    for line in Path("data/interim/re_phobert.jsonl").open(encoding="utf-8"):
        record = json.loads(line)
        for pair in record.get("pairs") or []:
            key = (
                str(record.get("sentence_id", "")),
                str(pair.get("subject", "")),
                str(pair.get("object", "")),
            )
            stored[key].append((str(pair.get("relation", "")), float(pair.get("confidence", 0))))

    candidates = []
    for candidate in iter_candidate_pairs(args.coref, max_distance=60):
        candidates.append(candidate)
        if len(candidates) >= args.n:
            break

    na_values: list[float] = []
    top_matches = 0
    n_pairs_with_na_low = 0
    fired_counts: list[int] = []
    for start in range(0, len(candidates), args.batch_size):
        batch = candidates[start : start + args.batch_size]
        input_ids, attention_mask, metadata = build_batch(
            batch, tokenizer, types, names, max_len=256, context_words=48
        )
        if not input_ids:
            continue
        ids_tensor, mask_tensor = pad_batch(
            input_ids, attention_mask, tokenizer.pad_token_id
        )
        with torch.no_grad():
            outputs = model(input_ids=ids_tensor, attention_mask=mask_tensor)
        probabilities = sigmoid(outputs.logits.numpy())
        for index, meta in enumerate(metadata):
            row = probabilities[index]
            na = float(row[NA_INDEX])
            na_values.append(na)
            if na < 0.5:
                n_pairs_with_na_low += 1
            fired = [i for i in range(len(row) - 1) if float(row[i]) > 0.55]
            fired_counts.append(len(fired))
            key = (meta["sentence_id"], meta["subject"], meta["object"])
            saved = stored.get(key)
            if saved:
                best = max(
                    range(len(row) - 1),
                    key=lambda i: float(row[i]),
                )
                from src.common.schemas import RELATION_ORDER
                if RELATION_ORDER[best] == saved[0][0]:
                    top_matches += 1

    n = len(na_values)
    print(f"Số cặp đo: {n}")
    print(f"NA < 0.5 (coi là 'có quan hệ'): {n_pairs_with_na_low} ({n_pairs_with_na_low / max(n, 1):.1%})")
    print(f"NA trung vị: {sorted(na_values)[n // 2] if n else 0:.4f}")
    print(f"Số quan hệ fire/cặp (>0.55): {Counter(fired_counts).most_common()}")
    print(f"Top-1 khớp với quan hệ đã lưu: {top_matches}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

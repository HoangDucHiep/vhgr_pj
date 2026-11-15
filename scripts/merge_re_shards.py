#!/usr/bin/env python3
"""Gộp các shard `re_phobert.shard*.jsonl` (đã xong) thành 1 file.

Tách riêng khỏi `run_infer_re_parallel.py` để có thể gộp lại **không cần
chạy lại** suy luận (suy luận mất ~3,7 giờ CPU).

Dùng:
    python scripts/merge_re_shards.py --out data/interim/re_phobert.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    """Gộp shard suy luận RE.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Gộp shard re_phobert")
    parser.add_argument("--shards-dir", default="data/interim/_shards")
    parser.add_argument("--out", default="data/interim/re_phobert.jsonl")
    parser.add_argument("--shard-count", type=int, default=4)
    args = parser.parse_args()

    shards_dir = REPO / args.shards_dir if not args.shards_dir.startswith("/") else Path(args.shards_dir)
    out_path = REPO / args.out if not args.out.startswith("/") else Path(args.out)

    predictions: dict[str, list[dict]] = defaultdict(list)
    texts: dict[str, str] = {}
    n_shards = 0
    for index in range(args.shard_count):
        path = shards_dir / f"re_phobert.shard{index}.jsonl"
        if not path.exists():
            print(f"Bỏ qua (không có): {path}")
            continue
        n_shards += 1
        for line in path.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            texts[row["sentence_id"]] = row.get("text", "")
            predictions[row["sentence_id"]].extend(row.get("pairs", []))

    if not n_shards:
        print("Không tìm thấy shard nào — dừng.")
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_pairs = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for sentence_id in sorted(predictions):
            pairs = predictions[sentence_id]
            if not pairs:
                continue
            n_pairs += len(pairs)
            handle.write(
                json.dumps(
                    {
                        "sentence_id": sentence_id,
                        "text": texts.get(sentence_id, ""),
                        "pairs": pairs,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    print(
        f"Đã gộp {n_shards} shard → {len(predictions)} câu / {n_pairs} quan hệ "
        f"→ {out_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

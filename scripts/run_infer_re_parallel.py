#!/usr/bin/env python3
"""Chạy `infer_re` song song bằng N shard rồi gộp kết quả.

CPU-only: mỗi tiến trình xử lý 1/N cặp ứng viên → tốc độ gần tuyến tính theo số
tiến trình (đo được: 0,0745 s/cặp với 1 tiến trình / 8 thread).

Dùng:
    python scripts/run_infer_re_parallel.py --model models/re --shards 4 \
        --out data/interim/re_phobert.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/re")
    parser.add_argument("--out", default="data/interim/re_phobert.jsonl")
    parser.add_argument("--shards", type=int, default=4)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn cặp (kiểm thử)")
    args = parser.parse_args()

    cache_file = REPO / "data" / "interim" / "_shards" / "candidates.jsonl"
    tmp_dir = REPO / "data" / "interim" / "_shards"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    shard_paths = [tmp_dir / f"re_phobert.shard{i}.jsonl" for i in range(args.shards)]

    procs = []
    started = time.time()
    for index, path in enumerate(shard_paths):
        env = dict(os.environ)
        env["OMP_NUM_THREADS"] = str(args.threads)
        env["MKL_NUM_THREADS"] = str(args.threads)
        cmd = [
            sys.executable, "-m", "src.re.infer_re",
            "--config", args.config,
            "--model", args.model,
            "--out", str(path),
            "--batch-size", str(args.batch_size),
            "--num-shards", str(args.shards),
            "--shard-index", str(index),
            "--candidates-cache", str(cache_file),
        ]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        log = (tmp_dir / f"shard{index}.log").open("w", encoding="utf-8")
        procs.append((index, subprocess.Popen(cmd, cwd=str(REPO), env=env,
                                             stdout=log, stderr=subprocess.STDOUT), log))
        print(f"[shard {index}] đã khởi chạy", flush=True)

    failed = 0
    for index, proc, log in procs:
        code = proc.wait()
        log.close()
        status = "OK" if code == 0 else f"LỖI rc={code}"
        if code != 0:
            failed += 1
            tail = (tmp_dir / f"shard{index}.log").read_text(encoding="utf-8")[-1500:]
            print(f"[shard {index}] {status}\n{tail}", flush=True)
        else:
            print(f"[shard {index}] {status}", flush=True)

    if failed:
        print("Có shard lỗi — dừng.")
        return 1

    print(f"Gộp {args.shards} shard → {args.out}", flush=True)
    predictions: dict[str, list[dict]] = defaultdict(list)
    texts: dict[str, str] = {}
    for path in shard_paths:
        if not path.exists():
            continue
        for line in path.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            texts[row["sentence_id"]] = row.get("text", "")
            predictions[row["sentence_id"]].extend(row.get("pairs", []))

    out_path = REPO / args.out if not args.out.startswith("/") else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for sentence_id in sorted(predictions):
            pairs = predictions[sentence_id]
            if not pairs:
                continue
            handle.write(json.dumps({
                "sentence_id": sentence_id,
                "text": texts.get(sentence_id, ""),
                "pairs": pairs,
            }, ensure_ascii=False) + "\n")
    n_pairs = sum(len(v) for v in predictions.values())
    print(f"Đã ghi {len(predictions)} câu / {n_pairs} quan hệ → {out_path} "
          f"({time.time() - started:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

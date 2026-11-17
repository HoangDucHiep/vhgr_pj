"""Phase 14 — Bước 2: mã hoá chunk bằng mô hình câu (dense retrieval).

Đầu ra
-------
- `data/interim/chunk_embeddings.npy` — float16 `[N, 384]`, **thứ tự khớp
  tuyệt đối** với `data/interim/chunks.jsonl` (dòng i ↔ chunk i).
- `data/interim/chunk_embeddings_meta.json` — metadata (`model`, `dim`,
  `count`, `order` = `chunk_id` theo thứ tự).

Mô hình
--------
`paraphrase-multilingual-MiniLM-L12-v2` (384-dim, mean-pooling + L2 norm).
Đã có sẵn trong cache HuggingFace ⇒ chạy **offline**, không tốn quota Kaggle.

Vì sao dùng `transformers` trực tiếp thay vì `sentence-transformers`?
Repo không cài `sentence-transformers` (chỉ `transformers` + `torch`) — xem
`src/link/embed_entities.py` (cùng pattern, đã verify hoạt động).

Tối ưu tốc độ
--------------
1. **Sắp xếp theo độ dài token** trước khi chia batch ⇒ padding tối thiểu.
   Sau khi embed, **khôi phục lại thứ tự gốc** (bắt buộc để vector i khớp
   chunk i).
2. Batch size 64, `max_length=256`, `torch.set_num_threads` theo CPU.

Ghi chú: đây là artifact **offline một lần**, không chạy trong request path.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from src.common.config import load_config, resolve_path
from src.common.logger import get_logger

logger = get_logger("src.qa.embed_chunks")


def read_chunks(path: Path) -> tuple[list[str], list[str], list[str]]:
    """Đọc chunks và dựng chuỗi đại diện cho embedding.

    Chuỗi đại diện = ``"<title> | <section> | <text>"`` (theo thiết kế đã
    đo: title×3 + section×2 boost giúp BM25 top-1 đúng bài; dense cũng hưởng
    lợi khi có title trong chuỗi).

    Args:
        path: Đường dẫn `chunks.jsonl`.

    Returns:
        Tuple `(chunk_ids, texts, embed_texts)`.
    """
    chunk_ids: list[str] = []
    texts: list[str] = []
    embed_texts: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            chunk_ids.append(str(record.get("chunk_id") or ""))
            text = str(record.get("text") or "")
            texts.append(text)
            title = str(record.get("title") or "")
            section = str(record.get("section_path") or record.get("section") or "")
            head = " | ".join(part for part in (title, section) if part)
            embed_texts.append(f"{head} | {text}" if head else text)
    return chunk_ids, texts, embed_texts


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Mã hoá chunk cho dense retrieval (Phase 14 — bước 2)."
    )
    parser.add_argument("--config", default="configs/retrieval.yaml")
    parser.add_argument("--chunks", default=None, help="Ghi đè đường dẫn chunks.jsonl.")
    parser.add_argument("--out", default=None, help="Ghi đè đường dẫn .npy.")
    parser.add_argument("--model", default=None, help="Ghi đè mô hình.")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--limit", type=int, default=0, help="Chỉ embed N chunk đầu (debug).")
    args = parser.parse_args()

    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer

    config = load_config(resolve_path(args.config))
    embed_cfg = config.get("embedding") or {}

    model_name = args.model or str(embed_cfg.get("model"))
    batch_size = int(args.batch_size or embed_cfg.get("batch_size", 64))
    max_length = int(embed_cfg.get("max_length", 256))
    threads = int(args.threads)
    torch.set_num_threads(threads)

    chunks_path = resolve_path(args.chunks or embed_cfg.get("chunks", "data/interim/chunks.jsonl"))
    out_path = resolve_path(args.out or embed_cfg.get("out", "data/interim/chunk_embeddings.npy"))
    meta_path = resolve_path(
        embed_cfg.get("meta_out", "data/interim/chunk_embeddings_meta.json")
    )

    chunk_ids, _texts, embed_texts = read_chunks(chunks_path)
    if args.limit:
        chunk_ids = chunk_ids[: args.limit]
        embed_texts = embed_texts[: args.limit]
    logger.info("Nạp %d chunk từ %s", len(chunk_ids), chunks_path)

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    # Sắp xếp theo độ dài (ký tự) để giảm padding.
    order = sorted(range(len(embed_texts)), key=lambda i: len(embed_texts[i]))
    vectors = np.zeros((len(embed_texts), 384), dtype=np.float16)

    started = time.time()
    with torch.no_grad():
        for start in range(0, len(order), batch_size):
            batch_idx = order[start : start + batch_size]
            batch = [embed_texts[i] for i in batch_idx]
            encoded = tokenizer(
                batch, padding=True, truncation=True,
                max_length=max_length, return_tensors="pt",
            )
            output = model(**encoded)
            hidden = output.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors[batch_idx] = pooled.to(torch.float16).cpu().numpy()
            done = start + len(batch)
            if (start // batch_size) % 50 == 0:
                elapsed = time.time() - started
                rate = done / elapsed if elapsed else 0.0
                eta = (len(order) - done) / rate if rate else 0.0
                logger.info(
                    "%d/%d chunk — %.1f chunk/s — còn %.1f phút",
                    done, len(order), rate, eta / 60,
                )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, vectors)
    meta = {
        "_meta": {
            "phase": 14,
            "mo_ta": "Embedding chunk cho dense retrieval",
            "model": model_name,
            "dim": int(vectors.shape[1]),
            "count": int(vectors.shape[0]),
            "dtype": str(vectors.dtype),
            "pooling": "mean + L2 normalize",
            "max_length": max_length,
            "batch_size": batch_size,
            "threads": threads,
            "thu_tu_khop": "chunk_embeddings.npy dòng i <-> chunks.jsonl dòng i",
            "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "elapsed_s": round(time.time() - started, 1),
        },
        "model": model_name,
        "dim": int(vectors.shape[1]),
        "order": chunk_ids,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "Ghi %s (shape=%s) + %s — %.1fs",
        out_path, vectors.shape, meta_path, time.time() - started,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

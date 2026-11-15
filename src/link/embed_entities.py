"""Phase 9 — Bước 2: embed entity bằng mô hình câu (BGE-M3 / MiniLM CPU).

Mỗi entity được mã hoá bằng chuỗi:

    "<tên>. <alias1>; <alias2>; <mô tả 200 ký tự>"

Kết quả lưu ở `data/knowledge_base/entity_embeddings.npy` (float16) kèm
`entity_embeddings_meta.json` (`entity_id`, `model`, `dim`, `order`).

Vì sao dùng `transformers` trực tiếp thay vì `sentence-transformers`?
Repo không cài `sentence-transformers` (chỉ có `transformers` + `torch`), và
mô hình fallback `paraphrase-multilingual-MiniLM-L12-v2` đã có sẵn trong
cache HF ⇒ chạy được hoàn toàn offline, không tốn quota Kaggle.

Ghi chú: `docs/09` ghi `[KAGGLE-GPU]` cho bước này; nếu chưa chạy Kaggle thì
dùng `sentence-transformers` MiniLM CPU và **ghi rõ trong báo cáo** — đây
chính là đường lùi đang áp dụng.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger

logger = get_logger("src.link.embed_entities")

#: Mô hình fallback CPU (đã có trong cache HuggingFace).
FALLBACK_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

#: Số ký tự mô tả tối đa.
MAX_DESC_CHARS = 200


def build_entity_text(entity: dict[str, Any], descriptions: dict[str, str]) -> str:
    """Dựng chuỗi đại diện cho một entity.

    Args:
        entity: Record entity.
        descriptions: Map `entity_id` → mô tả (tóm tắt từ Wikipedia).

    Returns:
        Chuỗi văn bản để mã hoá.
    """
    name = str(entity.get("name") or "")
    aliases = [
        str(a.get("alias") or "")
        for a in (entity.get("aliases") or [])
        if isinstance(a, dict)
    ]
    aliases = [a for a in aliases if a][:10]
    parts = [name]
    if aliases:
        parts.append("; ".join(aliases))
    desc = descriptions.get(str(entity.get("entity_id") or ""), "")
    if desc:
        parts.append(desc[:MAX_DESC_CHARS])
    return ". ".join(p for p in parts if p)


def load_descriptions(documents_path: Path, limit: int = 0) -> dict[str, str]:
    """Lấy đoạn dẫn (lead) làm mô tả cho entity.

    Args:
        documents_path: Đường dẫn `documents.jsonl`.
        limit: Giới hạn số tài liệu đọc (0 = tất cả).

    Returns:
        Map `entity_id` → đoạn dẫn đã rút gọn.
    """
    from src.common.ids import make_entity_id

    out: dict[str, str] = {}
    for index, line in enumerate(documents_path.open("r", encoding="utf-8")):
        if limit and index >= limit:
            break
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        text = str(doc.get("clean_text") or "")
        if not text:
            sentences = doc.get("sentences") or []
            text = " ".join(str(s) for s in sentences[:2])
        if not text:
            continue
        signal = str(doc.get("wikidata_signal") or "article")
        entity_id = make_entity_id(signal, str(doc.get("title") or ""))
        out.setdefault(entity_id, text[:MAX_DESC_CHARS])
    return out


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Embed entity cho entity linking (Phase 9 — bước 2)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--entities", default="data/knowledge_base/entities.jsonl",
        help="Input entity (output của build_aliases).",
    )
    parser.add_argument(
        "--documents", default="data/interim/documents.jsonl",
        help="Artifact Phase 1 (nguồn mô tả).",
    )
    parser.add_argument("--model", default=None, help="Ghi đè mô hình embedding.")
    parser.add_argument(
        "--out", default="data/knowledge_base/entity_embeddings.npy",
        help="Đường dẫn file .npy.",
    )
    parser.add_argument(
        "--meta-out", default="data/knowledge_base/entity_embeddings_meta.json",
        help="Đường dẫn file meta.",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=192)
    args = parser.parse_args()

    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer

    config = load_default_config()
    link_cfg = config.get("link") or {}
    model_name = args.model or FALLBACK_MODEL

    entities_path = resolve_path(args.entities)
    documents_path = resolve_path(args.documents)

    entities: list[dict[str, Any]] = []
    with entities_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                entities.append(json.loads(line))
    logger.info("Nạp %d entity từ %s", len(entities), entities_path)

    descriptions = load_descriptions(documents_path)
    texts = [build_entity_text(entity, descriptions) for entity in entities]
    logger.info("Ví dụ text: %s", texts[0][:160] if texts else "(rỗng)")

    logger.info("Nạp mô hình %s", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    # Mean-pooling + chuẩn hóa (giống sentence-transformers).
    vectors: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(texts), args.batch_size):
            batch = texts[start : start + args.batch_size]
            encoded = tokenizer(
                batch, padding=True, truncation=True,
                max_length=args.max_length, return_tensors="pt",
            )
            output = model(**encoded)
            hidden = output.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors.append(pooled.to(torch.float16).cpu().numpy())
            if (start // args.batch_size) % 10 == 0:
                logger.info("Đã embed %d/%d", start + len(batch), len(texts))

    matrix = (
        np.concatenate(vectors, axis=0)
        if vectors
        else np.zeros((0, 1024), dtype=np.float16)
    )
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(out_path, matrix)

    meta = {
        "_meta": {
            "phase": 9,
            "mo_ta": "Embedding entity cho entity linking",
            "model": model_name,
            "dim": int(matrix.shape[1]) if matrix.size else 0,
            "count": int(matrix.shape[0]) if matrix.size else 0,
            "dtype": str(matrix.dtype),
            "pooling": "mean + L2 normalize",
            "max_length": args.max_length,
            "ngay_do": __import__("time").strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
        "entity_ids": [str(e.get("entity_id")) for e in entities],
        "order": [str(e.get("entity_id")) for e in entities],
        "model": model_name,
        "dim": int(matrix.shape[1]) if matrix.size else 0,
    }
    meta_path = Path(args.meta_out)
    if not meta_path.is_absolute():
        meta_path = Path.cwd() / meta_path
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "Ghi %s (shape=%s) + %s",
        out_path, matrix.shape, meta_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

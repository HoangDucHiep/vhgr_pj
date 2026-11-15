"""Phase 9 — Bước 3: liên kết mention → entity canonical.

Ba tầng (theo `docs/09-ke-hoach-thuc-thien.md` §Phase 9):

- **Stage 1 — alias exact**: tra dict chuẩn hóa (`name_normalized` +
  `aliases_normalized`) → ứng viên.
- **Stage 2 — embedding**: cosine similarity vs top-k (k=20) trên
  `entity_embeddings.npy`.
- **Stage 3 — rerank theo ngữ cảnh**:

      score = w_alias*alias + w_ctx*context + w_temp*temporal
            + w_dyn*dynasty + w_type*type + w_freq*freq

  Trọng số lấy từ `configs/default.yaml` (`link.context_weight`).

Nếu `score < threshold` → `canonical_id = null` (chưa xác minh), đánh dấu
`ambiguous`.

Đầu ra:
- `data/interim/linked_mentions.jsonl` — mỗi mention → `entity_id`/`null`
  + `score` + `candidates`.
- `data/interim/triples_merged.jsonl` — **cập nhật** `entity_id` của subject
  và object theo canonical mới (Phase 8 dùng entity_id tạm).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger
from src.common.normalize import normalize_name

logger = get_logger("src.link.link_mentions")

#: Ngưỡng mặc định để coi là "chưa xác minh".
DEFAULT_THRESHOLD = 0.55

#: Ngưỡng embedding tối thiểu để đưa vào ứng viên.
MIN_EMBED_COSINE = 0.30

#: Chuỗi báo "không biết" cho triều đại.
UNKNOWN_DYNASTY = "unknown"


def iter_jsonl(path: Path) -> Any:
    """Đọc JSONL.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng dict.
    """
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_alias_index(
    entities: list[dict[str, Any]],
) -> dict[str, list[str]]:
    """Chuyển danh sách entity thành dict alias chuẩn hóa → entity_id.

    Args:
        entities: Danh sách entity.

    Returns:
        Dict `name_normalized` → list `entity_id`.
    """
    index: dict[str, list[str]] = defaultdict(list)
    for entity in entities:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id:
            continue
        keys = {str(entity.get("name_normalized") or "")}
        keys.update(str(a) for a in (entity.get("aliases_normalized") or []))
        for key in keys:
            if key and entity_id not in index[key]:
                index[key].append(entity_id)
    return dict(index)


def embed_texts(
    texts: list[str],
    model_name: str,
    *,
    batch_size: int = 64,
    max_length: int = 192,
    model: Any = None,
    tokenizer: Any = None,
) -> Any:
    """Mã hoá chuỗi bằng mô hình câu (mean-pooling + L2 normalize).

    Args:
        texts: Danh sách chuỗi.
        model_name: Tên mô hình HuggingFace.
        batch_size: Kích thước batch.
        max_length: Độ dài tối đa (token).
        model: Model đã nạp (nếu có) — tránh nạp lại.
        tokenizer: Tokenizer đã nạp (nếu có).

    Returns:
        Ma trận numpy float32 (n, dim).
    """
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer

    if model is None or tokenizer is None:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        model.eval()
    vectors: list[Any] = []
    with torch.no_grad():
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            encoded = tokenizer(
                batch, padding=True, truncation=True,
                max_length=max_length, return_tensors="pt",
            )
            hidden = model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
            vectors.append(pooled.to(torch.float32).cpu().numpy())
    if not vectors:
        return np.zeros((0, 0), dtype=np.float32)
    return np.concatenate(vectors, axis=0)


def load_embeddings(
    npy_path: Path, meta_path: Path,
) -> tuple[Any, list[str], dict[str, int]]:
    """Nạp ma trận embedding + thứ tự entity.

    Args:
        npy_path: Đường dẫn `.npy`.
        meta_path: Đường dẫn meta JSON.

    Returns:
        Tuple `(matrix, entity_ids, entity_id → chỉ số hàng)`.
    """
    import numpy as np

    matrix = np.load(npy_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    entity_ids = list(meta.get("order") or meta.get("entity_ids") or [])
    row_of = {entity_id: index for index, entity_id in enumerate(entity_ids)}
    return matrix, entity_ids, row_of


#: Nhãn NER → các loại entity được phép.
NER_TYPE_MAP: dict[str, set[str]] = {
    "PERSON": {"person"},
    "LOCATION": {"place"},
    "ORG": {"organization", "dynasty"},
    "EVENT": {"event"},
    "TITLE": {"person", "title"},
}


class EntityScorer:
    """Tính điểm rerank cho ứng viên (Stage 3).

    Attributes:
        entities_by_id: Map `entity_id` → entity.
        alias_keys: Map `entity_id` → set khóa chuẩn hóa.
        type_of: Map `entity_id` → loại entity.
        birth: Map `entity_id` → năm sinh.
        death: Map `entity_id` → năm mất.
        dynasty_of: Map `entity_id` → triều đại.
        freq: Map `entity_id` → `mention_count`.
    """

    def __init__(self, entities: list[dict[str, Any]]) -> None:
        """Precompute mọi thuộc tính cần cho scoring.

        Args:
            entities: Danh sách entity.
        """
        import math

        self.entities_by_id = {str(e["entity_id"]): e for e in entities}
        self.alias_keys: dict[str, set[str]] = {}
        self.type_of: dict[str, str] = {}
        self.birth: dict[str, int] = {}
        self.death: dict[str, int] = {}
        self.dynasty_of: dict[str, str] = {}
        self.freq: dict[str, float] = {}
        for entity in entities:
            entity_id = str(entity["entity_id"])
            keys = {str(entity.get("name_normalized") or "")}
            keys.update(str(a) for a in (entity.get("aliases_normalized") or []))
            self.alias_keys[entity_id] = keys
            self.type_of[entity_id] = str(entity.get("type") or "")
            if entity.get("birth_year"):
                self.birth[entity_id] = int(entity["birth_year"])
            if entity.get("death_year"):
                self.death[entity_id] = int(entity["death_year"])
            self.dynasty_of[entity_id] = str(entity.get("dynasty") or "")
            count = int(entity.get("mention_count") or 0)
            self.freq[entity_id] = min(1.0, math.log1p(count) / math.log(101))

    def score(
        self,
        mention_key: str,
        mention_type: str,
        candidates: list[str],
        weights: dict[str, float],
        context_ids: set[str],
        dynasty: str,
        temporal_years: list[int],
    ) -> list[tuple[str, float, dict[str, float]]]:
        """Rerank ứng viên theo ngữ cảnh.

        Args:
            mention_key: Tên bề mặt đã chuẩn hóa.
            mention_type: Nhãn NER.
            candidates: Danh sách `entity_id` ứng viên.
            weights: Trọng số từ config.
            context_ids: Set `entity_id` xuất hiện trong cùng câu.
            dynasty: Triều đại của bài.
            temporal_years: Các mốc năm trong câu.

        Returns:
            Danh sách `(entity_id, score, chi tiết điểm)` — giảm dần.
        """
        allowed = NER_TYPE_MAP.get(mention_type, set())
        w_alias = weights.get("alias", 0.0)
        w_ctx = weights.get("context", 0.0)
        w_temp = weights.get("temporal", 0.0)
        w_dyn = weights.get("dynasty", 0.0)
        w_type = weights.get("type", 0.0)
        w_freq = weights.get("freq", 0.0)
        scored: list[tuple[str, float, dict[str, float]]] = []
        for entity_id in candidates:
            alias_hit = 1.0 if mention_key in self.alias_keys.get(entity_id, ()) else 0.0
            ctx_hit = 1.0 if entity_id in context_ids else 0.0
            birth = self.birth.get(entity_id)
            death = self.death.get(entity_id)
            if birth or death:
                lo = birth if birth is not None else death - 100
                hi = death if death is not None else birth + 100
                temp_hit = 1.0 if any(lo <= y <= hi for y in temporal_years) else 0.0
            else:
                temp_hit = 0.0
            dyn_hit = (
                1.0
                if dynasty and self.dynasty_of.get(entity_id) == dynasty
                else 0.0
            )
            type_hit = 1.0 if self.type_of.get(entity_id, "") in allowed else 0.0
            freq = self.freq.get(entity_id, 0.0)
            score = (
                w_alias * alias_hit
                + w_ctx * ctx_hit
                + w_temp * temp_hit
                + w_dyn * dyn_hit
                + w_type * type_hit
                + w_freq * freq
            )
            scored.append((entity_id, score, {
                "alias": alias_hit,
                "context": ctx_hit,
                "temporal": temp_hit,
                "dynasty": dyn_hit,
                "type": type_hit,
                "freq": freq,
            }))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Liên kết mention → entity canonical (Phase 9 — bước 3)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--entities", default="data/knowledge_base/entities.jsonl",
    )
    parser.add_argument(
        "--embeddings", default="data/knowledge_base/entity_embeddings.npy",
    )
    parser.add_argument(
        "--embeddings-meta", default="data/knowledge_base/entity_embeddings_meta.json",
    )
    parser.add_argument(
        "--mentions", default="data/interim/coref_resolved.jsonl",
    )
    parser.add_argument(
        "--triples", default="data/interim/triples_merged.jsonl",
        help="File triple cần cập nhật entity_id.",
    )
    parser.add_argument(
        "--out", default="data/interim/linked_mentions.jsonl",
    )
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--embed-model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="Mô hình dùng cho Stage 2 (mã hoá tên bề mặt của mention).",
    )
    parser.add_argument(
        "--update-triples", action="store_true",
        help="Ghi lại triples_merged.jsonl với entity_id canonical.",
    )
    args = parser.parse_args()

    import numpy as np

    config = load_default_config()
    link_cfg = config.get("link") or {}
    weights = dict(link_cfg.get("context_weight") or {})
    top_k = int(link_cfg.get("top_k", args.top_k))
    threshold = args.threshold

    entities = list(iter_jsonl(resolve_path(args.entities)))
    scorer = EntityScorer(entities)
    alias_index = build_alias_index(entities)
    logger.info(
        "Nạp %d entity · %d khóa alias", len(entities), len(alias_index)
    )

    matrix, entity_ids, row_of = load_embeddings(
        resolve_path(args.embeddings), resolve_path(args.embeddings_meta)
    )
    logger.info("Embedding matrix %s (%d entity)", matrix.shape, len(entity_ids))
    entity_rows = np.array(
        [row_of.get(entity_id, -1) for entity_id in entity_ids], dtype=np.int64
    )

    mentions_path = resolve_path(args.mentions)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Chuẩn bị Stage 2: ma trận embedding entity ---
    entity_matrix = None
    entity_ids_order: list[str] = []
    if matrix.size:
        valid_rows = [
            index for index, entity_id in enumerate(entity_ids)
            if index < matrix.shape[0]
        ]
        entity_ids_order = [entity_ids[i] for i in valid_rows]
        entity_matrix = matrix[valid_rows].astype(np.float32)
    logger.info(
        "Stage 2 sẵn sàng: %d entity có embedding", len(entity_ids_order)
    )

    n_mention = 0
    n_linked = 0
    n_ambiguous = 0
    n_alias_hit = 0
    n_embed_hit = 0
    started = time.time()
    # Cache ứng viên embedding theo surface (nhiều mention dùng chung tên).
    embed_cache: dict[str, list[tuple[str, float]]] = {}

    # Map: entity_id (Phase 8, tạm) → entity_id canonical.
    canonical_map: dict[str, str] = {}

    # --- Giai đoạn 0: gom toàn bộ surface mention để mã hoá 1 lần ---
    surface_list: list[str] = []
    surface_index: dict[str, int] = {}
    for record in iter_jsonl(mentions_path):
        for mention in record.get("mentions") or []:
            surface = str(mention.get("text") or "")
            if surface and surface not in surface_index:
                surface_index[surface] = len(surface_list)
                surface_list.append(surface)
    logger.info("Mã hoá %d surface mention duy nhất...", len(surface_list))

    surface_vectors: Any = None
    if entity_matrix is not None and entity_matrix.size and surface_list:
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(args.embed_model)
        embed_model = AutoModel.from_pretrained(args.embed_model)
        embed_model.eval()
        surface_vectors = embed_texts(
            surface_list, args.embed_model, model=embed_model, tokenizer=tokenizer
        )
        logger.info("Surface embedding: %s", surface_vectors.shape)

    with out_path.open("w", encoding="utf-8") as handle:
        for record in iter_jsonl(mentions_path):
            sentence_id = str(record.get("sentence_id") or "")
            text = str(record.get("text") or "")
            mentions = record.get("mentions") or []
            # Ngữ cảnh: các entity đã resolve trong cùng câu.
            context_ids = {
                str(m.get("canonical_id"))
                for m in mentions
                if m.get("canonical_id")
            }
            dynasty = str(record.get("dynasty") or "")
            temporal_years = [
                int(y) for y in (record.get("years") or []) if isinstance(y, int)
            ]
            for mention in mentions:
                n_mention += 1
                surface = str(mention.get("text") or "")
                key = normalize_name(surface)
                candidates: list[str] = list(alias_index.get(key, []))
                if candidates:
                    n_alias_hit += 1
                else:
                    # Stage 2 — embedding: ứng viên gần nhất theo cosine.
                    if surface_vectors is not None and surface_vectors.size:
                        row = surface_index.get(surface)
                        if row is not None:
                            # Cache theo surface: nhiều mention dùng chung tên.
                            if surface not in embed_cache:
                                sims = entity_matrix @ surface_vectors[row]
                                # `argpartition` O(n) thay vì `argsort` O(n log n)
                                # (đo được: 148k mention × argsort(15.931) là nút
                                # thắt cổ chai ~30 phút).
                                part = np.argpartition(-sims, min(top_k, len(sims) - 1))
                                top = part[:top_k]
                                top = top[np.argsort(-sims[top])]
                                embed_cache[surface] = [
                                    (entity_ids_order[int(i)], float(sims[int(i)]))
                                    for i in top
                                    if sims[int(i)] >= MIN_EMBED_COSINE
                                ]
                            for cand_id, _sim in embed_cache[surface]:
                                candidates.append(cand_id)
                            if candidates:
                                n_embed_hit += 1

                scored = scorer.score(
                    key, str(mention.get("label") or ""), candidates, weights,
                    context_ids, dynasty, temporal_years,
                )
                if not scored:
                    handle.write(json.dumps({
                        "mention_id": mention.get("mention_id"),
                        "sentence_id": sentence_id,
                        "doc_id": record.get("doc_id"),
                        "text": surface,
                        "label": mention.get("label"),
                        "entity_id": None,
                        "score": 0.0,
                        "status": "ambiguous",
                        "candidates": [],
                    }, ensure_ascii=False) + "\n")
                    n_ambiguous += 1
                    continue

                best_id, best_score, parts = scored[0]
                status = "linked" if best_score >= threshold else "ambiguous"
                if status == "linked":
                    n_linked += 1
                    old_id = str(mention.get("canonical_id") or "")
                    if old_id:
                        canonical_map[old_id] = best_id
                else:
                    n_ambiguous += 1
                handle.write(json.dumps({
                    "mention_id": mention.get("mention_id"),
                    "sentence_id": sentence_id,
                    "doc_id": record.get("doc_id"),
                    "text": surface,
                    "label": mention.get("label"),
                    "entity_id": best_id if status == "linked" else None,
                    "score": round(best_score, 4),
                    "status": status,
                    "score_parts": {k: round(v, 3) for k, v in parts.items()},
                    "candidates": [
                        {"entity_id": eid, "score": round(score, 4)}
                        for eid, score, _ in scored[:5]
                    ],
                }, ensure_ascii=False) + "\n")

    logger.info(
        "Mention: %d | linked: %d (%.1f%%) | ambiguous: %d | alias hit: %d (%.1f%%) "
        "| embedding hit: %d",
        n_mention, n_linked,
        (n_linked / n_mention * 100) if n_mention else 0,
        n_ambiguous, n_alias_hit,
        (n_alias_hit / n_mention * 100) if n_mention else 0,
        n_embed_hit,
    )
    logger.info("Thời gian: %.1fs", time.time() - started)

    # --- Cập nhật triples_merged ---
    if args.update_triples:
        triples_path = resolve_path(args.triples)
        if triples_path.exists():
            n_updated = 0
            n_triples = 0
            tmp_path = triples_path.with_suffix(".jsonl.tmp")
            with triples_path.open("r", encoding="utf-8") as src, \
                    tmp_path.open("w", encoding="utf-8") as dst:
                for line in src:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    n_triples += 1
                    for role in ("subject", "object"):
                        value = str(row.get(role) or "")
                        if value in canonical_map:
                            row[role] = canonical_map[value]
                            n_updated += 1
                    dst.write(json.dumps(row, ensure_ascii=False) + "\n")
            tmp_path.replace(triples_path)
            logger.info(
                "Cập nhật %d/%d trường entity trong %d triple",
                n_updated, n_triples * 2, n_triples,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

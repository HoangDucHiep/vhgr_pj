"""Phase 14 — Bước 3: tầng truy xuất (BM25 + dense + RRF).

**Dùng chung cho cả arm A (Vanilla RAG) và arm B (Hybrid GraphRAG)** ⇒ so
sánh công bằng: khác biệt giữa 2 nhánh chỉ nằm ở chỗ có dùng KG hay không.

Kiến trúc
---------
```
question
   │
   ├──► BM25 (token không dấu; title×3 + section×2 + body×1)
   │
   ├──► Dense (cosine trên chunk_embeddings.npy — MiniLM-L12 384-dim)
   │
   └──► RRF (k=60)  ──► top_k chunk ──► context
```

Vì sao BM25 trọng số trường?
-----------------------------
Đo trên 6 câu hỏi thật: dùng **chỉ body** → trượt top-1 (trả về bài sai
về cùng chủ đề); thêm boost `title×3 + section×2` → **top-1 đúng bài**.

Vì sao RRF?
-----------
Hai nhánh có thang điểm khác nhau (BM25 không chuẩn hoá, cosine ∈ [-1,1])
nên không so sánh trực tiếp được. RRF chỉ dùng **thứ hạng** ⇒ công bằng
và không cần hiệu chỉnh trọng số.

Chỉ mục BM25
------------
`rank_bm25.BM25Okapi` giữ **toàn bộ corpus trong RAM** và tokenize lại mỗi
lần khởi động ⇒ chậm (~5–10 s). Vì vậy dựng **chỉ mục postings ngược**
một lần offline (`--build-index`), lưu `data/interim/bm25_index.npz`:
- `term_ids` / `term_ptr` : postings của từng term
- `term_doc_ids` / `term_freqs` : (doc_id, tf×trọng số trường)
- `doc_len` : số token mỗi chunk
- `vocab_keys` / `vocab_values` : từ ↔ id

Truy vấn chỉ duyệt postings của các từ trong câu hỏi ⇒ **< 50 ms** cho
101.627 chunk.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from src.common.config import load_config, resolve_path
from src.common.logger import get_logger

logger = get_logger("src.qa.retriever")

#: Từ dừng tiếng Việt + tiếng Anh (không dấu).
DEFAULT_STOPWORDS: frozenset[str] = frozenset({
    "cua", "va", "la", "co", "nhung", "voi", "cho", "trong", "ngoai", "khi",
    "den", "tu", "mot", "nhu", "theo", "ve", "tai", "nam", "nguoi", "vua",
    "ong", "bai", "do", "o", "bi", "de", "thi", "day", "nen", "sau", "truoc",
    "hai", "ba", "gan", "the", "vao", "ra", "len", "xuong", "phia", "giua",
    "cung", "boi", "vi", "nua", "ma", "thu", "dem", "duoi", "tren", "hay",
    "hoac", "nhieu", "it",     "cai", "moi", "cac", "co_the", "khong", "chua",
    "roi", "van", "lai", "tua", "da", "se", "dang", "lam", "noi", "thi",
    "ma", "vi", "nen", "rat", "lon", "nho", "ca", "cung", "the", "cu",
    "neu", "hay", "chi", "phai", "muon", "hoac", "noi", "dung",
    "thuoc", "ve", "giua", "khu", "toan", "bo", "phan", "nhom", "tieu",
})
#: Regex tách từ: chữ (kể cả dấu) + số.
_TOKEN_RE = re.compile(r"[0-9a-zA-ZÀ-ỹĐđ]+")


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường.

    Args:
        text: Chuỗi gốc.

    Returns:
        Chuỗi đã bỏ dấu, viết thường.
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    return without_marks.replace("đ", "d").replace("Đ", "D").lower()


def tokenize(text: str, stopwords: frozenset[str] | None = None) -> list[str]:
    """Tách câu thành token đã bỏ dấu, loại stopword.

    Args:
        text: Chuỗi gốc.
        stopwords: Tập stopword (None ⇒ `DEFAULT_STOPWORDS`).

    Returns:
        Danh sách token.
    """
    if not text:
        return []
    stop = stopwords if stopwords is not None else DEFAULT_STOPWORDS
    return [
        token
        for token in _TOKEN_RE.findall(strip_accents(text))
        if token not in stop and len(token) > 1
    ]


@dataclass
class Chunk:
    """Một chunk trong chỉ mục truy xuất.

    Attributes:
        chunk_id: Id chunk.
        doc_id: Id tài liệu.
        page_id: Page id.
        title: Tên bài.
        section: Tiêu đề mục hiện tại.
        section_path: Đường dẫn mục lồng nhau.
        text: Nội dung đoạn.
        entity_ids: Entity của đoạn.
        source_url: URL nguồn.
        para_idx: Chỉ số đoạn.
        kind: Loại đoạn.
    """

    chunk_id: str
    doc_id: str
    page_id: int
    title: str
    section: str
    section_path: str
    text: str
    entity_ids: list[str] = field(default_factory=list)
    source_url: str = ""
    para_idx: int = 0
    kind: str = "prose"

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict (serialize).

        Returns:
            Dict chunk.
        """
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "page_id": self.page_id,
            "title": self.title,
            "section": self.section,
            "section_path": self.section_path,
            "text": self.text,
            "entity_ids": list(self.entity_ids),
            "source_url": self.source_url,
            "para_idx": self.para_idx,
            "kind": self.kind,
        }

    def cite_label(self) -> str:
        """Nhãn hiển thị cho trích dẫn.

        Returns:
            Chuỗi nhãn, ví dụ ``"Trận Bạch Đằng > Diễn biến trận đánh"``.
        """
        if self.section_path:
            return f"{self.title} > {self.section_path}"
        return self.title


def load_chunks(
    path: Path,
    *,
    exclude_kinds: frozenset[str] | None = None,
) -> list[Chunk]:
    """Đọc `chunks.jsonl` thành danh sách `Chunk`.

    Args:
        path: Đường dẫn file.
        exclude_kinds: Các loại đoạn cần loại khỏi corpus truy xuất
            (mặc định `{"heading"}` — đoạn tiêu đề chỉ chứa tên mục, không
            có thông tin nội dung nên chỉ gây nhiễu kết quả).

    Returns:
        Danh sách chunk (thứ tự khớp dòng trong file).
    """
    skip = exclude_kinds if exclude_kinds is not None else frozenset({"heading"})
    chunks: list[Chunk] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            kind = str(record.get("kind") or "prose")
            if kind in skip:
                continue
            chunks.append(
                Chunk(
                    chunk_id=str(record.get("chunk_id") or ""),
                    doc_id=str(record.get("doc_id") or ""),
                    page_id=int(record.get("page_id") or 0),
                    title=str(record.get("title") or ""),
                    section=str(record.get("section") or ""),
                    section_path=str(record.get("section_path") or ""),
                    text=str(record.get("text") or ""),
                    entity_ids=[str(e) for e in (record.get("entity_ids") or [])],
                    source_url=str(record.get("source_url") or ""),
                    para_idx=int(record.get("para_idx") or 0),
                    kind=kind,
                )
            )
    return chunks


class BM25Index:
    """Chỉ mục BM25 Okapi dạng postings ngược (build 1 lần, truy vấn nhanh).

    Attributes:
        k1: Tham số saturation.
        b: Tham số length normalization.
        vocab: Từ → term id.
        doc_len: Số token mỗi chunk.
        term_ptr: Con trỏ postings (`term_ptr[i]..term_ptr[i+1]`).
        term_doc_ids: Doc id của mỗi posting.
        term_freqs: Tf đã nhân trọng số trường.
        idf: IDF theo term id.
        n_docs: Số chunk.
        avg_len: Độ dài trung bình.
    """

    def __init__(
        self,
        vocab: dict[str, int],
        doc_len: Any,
        term_ptr: Any,
        term_doc_ids: Any,
        term_freqs: Any,
        idf: Any,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        """Khởi tạo chỉ mục.

        Args:
            vocab: Map từ → term id.
            doc_len: Mảng độ dài mỗi doc.
            term_ptr: Con trỏ postings theo term.
            term_doc_ids: Doc id của mỗi posting.
            term_freqs: Tf đã nhân trọng số trường.
            idf: IDF theo term id.
            k1: Tham số `k1`.
            b: Tham số `b`.
        """
        self.vocab = vocab
        self.doc_len = doc_len
        self.term_ptr = term_ptr
        self.term_doc_ids = term_doc_ids
        self.term_freqs = term_freqs
        self.idf = idf
        self.k1 = k1
        self.b = b
        self.n_docs = int(len(doc_len))
        self.avg_len = float(sum(doc_len) / self.n_docs) if self.n_docs else 0.0

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        chunks: list[Chunk],
        *,
        field_weights: dict[str, int] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> "BM25Index":
        """Dựng chỉ mục từ danh sách chunk.

        Args:
            chunks: Danh sách chunk.
            field_weights: Trọng số trường (`title`/`section`/`body`).
            k1: Tham số `k1`.
            b: Tham số `b`.

        Returns:
            Chỉ mục đã dựng.
        """
        import numpy as np

        weights = field_weights or {"title": 3, "section": 2, "body": 1}
        vocab: dict[str, int] = {}
        postings: dict[int, list[tuple[int, float]]] = {}
        doc_len = np.zeros(len(chunks), dtype=np.float32)

        for index, chunk in enumerate(chunks):
            title_tokens = tokenize(chunk.title)
            section_tokens = tokenize(chunk.section_path or chunk.section)
            body_tokens = tokenize(chunk.text)
            counts: dict[int, float] = {}
            for tokens, field_name in (
                (title_tokens, "title"),
                (section_tokens, "section"),
                (body_tokens, "body"),
            ):
                weight = float(weights.get(field_name, 1))
                for token in tokens:
                    term_id = vocab.get(token)
                    if term_id is None:
                        term_id = len(vocab)
                        vocab[token] = term_id
                    counts[term_id] = counts.get(term_id, 0.0) + weight
            doc_len[index] = float(
                len(title_tokens) + len(section_tokens) + len(body_tokens)
            )
            for term_id, freq in counts.items():
                postings.setdefault(term_id, []).append((index, freq))

        term_ptr = [0]
        term_doc_ids: list[int] = []
        term_freqs: list[float] = []
        idf_values = np.zeros(len(vocab), dtype=np.float32)
        n_docs = len(chunks)
        for term_id in range(len(vocab)):
            entries = postings.get(term_id, [])
            doc_ids = np.asarray([doc for doc, _ in entries], dtype=np.int32)
            freqs = np.asarray([freq for _, freq in entries], dtype=np.float32)
            term_doc_ids.append(doc_ids)
            term_freqs.append(freqs)
            df = len(entries)
            idf_values[term_id] = math.log(
                1.0 + (n_docs - df + 0.5) / (df + 0.5)
            )
            term_ptr.append(term_ptr[-1] + df)

        logger.info(
            "BM25 index: %d chunk × %d từ vựng, %d posting",
            len(chunks), len(vocab), term_ptr[-1],
        )
        return cls(
            vocab=vocab,
            doc_len=doc_len,
            term_ptr=np.asarray(term_ptr, dtype=np.int64),
            term_doc_ids=term_doc_ids,
            term_freqs=term_freqs,
            idf=idf_values,
            k1=k1,
            b=b,
        )

    # ------------------------------------------------------------------
    # Save / load
    # ------------------------------------------------------------------

    def save(self, path: Path, meta_path: Path) -> None:
        """Lưu chỉ mục + metadata xuống đĩa.

        Args:
            path: Đường dẫn `.npz`.
            meta_path: Đường dẫn metadata `.json`.
        """
        import numpy as np

        path.parent.mkdir(parents=True, exist_ok=True)
        flat_doc_ids = np.concatenate(self.term_doc_ids) if self.term_doc_ids else np.zeros(0, np.int32)
        flat_freqs = np.concatenate(self.term_freqs) if self.term_freqs else np.zeros(0, np.float32)
        offsets = np.zeros(len(self.term_doc_ids) + 1, dtype=np.int64)
        for index, docs in enumerate(self.term_doc_ids):
            offsets[index + 1] = offsets[index] + len(docs)
        np.savez_compressed(
            path,
            term_ptr=np.asarray(self.term_ptr, dtype=np.int64),
            offsets=offsets,
            flat_doc_ids=flat_doc_ids,
            flat_freqs=flat_freqs,
            doc_len=np.asarray(self.doc_len, dtype=np.float32),
            idf=np.asarray(self.idf, dtype=np.float32),
            vocab_keys=np.asarray(list(self.vocab.keys()), dtype=object),
            vocab_values=np.asarray(list(self.vocab.values()), dtype=np.int32),
            k1=np.asarray([self.k1], dtype=np.float32),
            b=np.asarray([self.b], dtype=np.float32),
        )
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(
                {
                    "_meta": {
                        "phase": 14,
                        "mo_ta": "Chỉ mục BM25 postings ngược cho truy xuất chunk",
                        "n_docs": self.n_docs,
                        "vocab_size": len(self.vocab),
                        "k1": self.k1,
                        "b": self.b,
                        "avg_len": round(self.avg_len, 3),
                        "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    },
                    "n_docs": self.n_docs,
                    "vocab_size": len(self.vocab),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        logger.info("Ghi %s + %s", path, meta_path)

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        k1: float | None = None,
        b: float | None = None,
    ) -> "BM25Index":
        """Nạp chỉ mục từ đĩa.

        Args:
            path: Đường dẫn `.npz`.
            k1: Ghi đè `k1`.
            b: Ghi đè `b`.

        Returns:
            Chỉ mục.
        """
        import numpy as np

        with np.load(path, allow_pickle=True) as data:
            keys = list(data["vocab_keys"])
            values = list(data["vocab_values"])
            vocab = {str(k): int(v) for k, v in zip(keys, values)}
            offsets = data["offsets"]
            flat_doc_ids = data["flat_doc_ids"]
            flat_freqs = data["flat_freqs"]
            term_doc_ids = [
                flat_doc_ids[offsets[i] : offsets[i + 1]] for i in range(len(offsets) - 1)
            ]
            term_freqs = [
                flat_freqs[offsets[i] : offsets[i + 1]] for i in range(len(offsets) - 1)
            ]
            k1_value = float(k1 if k1 is not None else data["k1"][0])
            b_value = float(b if b is not None else data["b"][0])
            return cls(
                vocab=vocab,
                doc_len=data["doc_len"],
                term_ptr=data["term_ptr"],
                term_doc_ids=term_doc_ids,
                term_freqs=term_freqs,
                idf=data["idf"],
                k1=k1_value,
                b=b_value,
            )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def search(self, query_tokens: Iterable[str], top_k: int = 50) -> list[tuple[int, float]]:
        """Truy vấn BM25 (công thức Okapi chuẩn).

        Args:
            query_tokens: Token của câu hỏi.
            top_k: Số kết quả trả về.

        Returns:
            Danh sách `(chunk_index, score)` giảm dần theo điểm.
        """
        import numpy as np

        scores = np.zeros(self.n_docs, dtype=np.float32)
        avg_len = self.avg_len or 1.0
        seen: set[int] = set()
        for token in query_tokens:
            term_id = self.vocab.get(token)
            if term_id is None or term_id in seen:
                continue
            seen.add(term_id)
            doc_ids = self.term_doc_ids[term_id]
            if doc_ids is None or len(doc_ids) == 0:
                continue
            freqs = self.term_freqs[term_id]
            lengths = self.doc_len[doc_ids]
            denominator = freqs + self.k1 * (
                1.0 - self.b + self.b * lengths / avg_len
            )
            contribution = (
                self.idf[term_id] * (freqs * (self.k1 + 1.0)) / denominator
            )
            scores[doc_ids] += contribution
        if not scores.any():
            return []
        count = min(top_k, self.n_docs)
        top = np.argpartition(-scores, count - 1)[:count]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top if scores[i] > 0.0]


@dataclass
class RetrievedChunk:
    """Chunk đã truy xuất + điểm số.

    Attributes:
        chunk: Nội dung chunk.
        index: Chỉ số trong corpus.
        rrf_score: Điểm RRF cuối cùng.
        bm25_rank: Hạng của nhánh BM25 (None nếu không có).
        dense_rank: Hạng của nhánh dense (None nếu không có).
        bm25_score: Điểm BM25 thô.
        dense_score: Điểm cosine thô.
    """

    chunk: Chunk
    index: int
    rrf_score: float = 0.0
    bm25_rank: int | None = None
    dense_rank: int | None = None
    bm25_score: float = 0.0
    dense_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict (serialize).

        Returns:
            Dict kết quả truy xuất.
        """
        return {
            "chunk_id": self.chunk.chunk_id,
            "doc_id": self.chunk.doc_id,
            "title": self.chunk.title,
            "section": self.chunk.section,
            "section_path": self.chunk.section_path,
            "text": self.chunk.text,
            "source_url": self.chunk.source_url,
            "entity_ids": list(self.chunk.entity_ids),
            "rrf_score": round(self.rrf_score, 6),
            "bm25_rank": self.bm25_rank,
            "dense_rank": self.dense_rank,
            "bm25_score": round(self.bm25_score, 4),
            "dense_score": round(self.dense_score, 4),
        }


class Retriever:
    """Tầng truy xuất dùng chung cho arm A và arm B.

    Attributes:
        chunks: Danh sách chunk.
        bm25: Chỉ mục BM25.
        embeddings: Ma trận float32 `[N, dim]` (None nếu tắt dense).
        config: Cấu hình lấy từ `configs/retrieval.yaml`.
        _model: Mô hình dense (lazy load).
        _tokenizer: Tokenizer dense (lazy load).
    """

    def __init__(
        self,
        chunks: list[Chunk],
        bm25: BM25Index,
        *,
        embeddings: Any | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Khởi tạo retriever.

        Args:
            chunks: Danh sách chunk.
            bm25: Chỉ mục BM25.
            embeddings: Ma trận embedding (float32).
            config: Cấu hình retrieval.
        """
        self.chunks = chunks
        self.bm25 = bm25
        self.embeddings = embeddings
        self.config = config or {}
        self._model: Any | None = None
        self._tokenizer: Any | None = None

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, config_path: str | Path = "configs/retrieval.yaml") -> "Retriever":
        """Nạp retriever từ cấu hình + artifact trên đĩa.

        Args:
            config_path: Đường dẫn cấu hình.

        Returns:
            `Retriever` đã sẵn sàng.
        """
        import numpy as np

        config = load_config(resolve_path(config_path))
        retrieval = config.get("retrieval") or {}
        chunking = config.get("chunking") or {}
        embedding = config.get("embedding") or {}

        chunks = load_chunks(
            resolve_path(chunking.get("chunks", "data/interim/chunks.jsonl"))
        )
        logger.info("Nạp %d chunk", len(chunks))

        bm25_cfg = retrieval.get("bm25") or {}
        bm25 = BM25Index.load(
            resolve_path(bm25_cfg.get("index", "data/interim/bm25_index.npz")),
            k1=float(bm25_cfg.get("k1", 1.5)),
            b=float(bm25_cfg.get("b", 0.75)),
        )

        embeddings = None
        dense_cfg = retrieval.get("dense") or {}
        if dense_cfg.get("enabled", True):
            emb_path = resolve_path(
                embedding.get("out", "data/interim/chunk_embeddings.npy")
            )
            if emb_path.exists():
                embeddings = np.load(emb_path).astype(np.float32)
                logger.info("Nạp embedding %s", embeddings.shape)
            else:
                logger.warning("Không có %s — tắt nhánh dense", emb_path)

        return cls(chunks, bm25, embeddings=embeddings, config=config)

    # ------------------------------------------------------------------
    # Dense
    # ------------------------------------------------------------------

    def _ensure_dense_model(self) -> None:
        """Lazy-load mô hình dense (chỉ khi cần truy vấn)."""
        if self._model is not None:
            return
        import torch
        from transformers import AutoModel, AutoTokenizer

        embedding_cfg = self.config.get("embedding") or {}
        model_name = str(embedding_cfg.get("model"))
        torch.set_num_threads(int(embedding_cfg.get("threads", 4)))
        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModel.from_pretrained(model_name)
        self._model.eval()

    def embed_query(self, query: str) -> Any:
        """Mã hoá câu hỏi thành vector.

        Args:
            query: Câu hỏi.

        Returns:
            Vector float32 `[dim]` (đã L2 chuẩn hoá) hoặc ``None``.
        """
        if self.embeddings is None:
            return None
        import numpy as np
        import torch

        self._ensure_dense_model()
        dense_cfg = (self.config.get("retrieval") or {}).get("dense") or {}
        max_chars = int(dense_cfg.get("max_query_chars", 512))
        max_length = int((self.config.get("embedding") or {}).get("max_length", 256))
        with torch.no_grad():
            encoded = self._tokenizer(
                [query[:max_chars]],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            output = self._model(**encoded)
            hidden = output.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-9)
            pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
        return pooled[0].cpu().numpy().astype(np.float32)

    def dense_search(self, query: str, top_k: int = 50) -> list[tuple[int, float]]:
        """Truy vấn dense bằng cosine similarity.

        Args:
            query: Câu hỏi.
            top_k: Số kết quả.

        Returns:
            Danh sách `(index, score)`.
        """
        if self.embeddings is None:
            return []
        import numpy as np

        vector = self.embed_query(query)
        if vector is None:
            return []
        scores = self.embeddings @ vector
        count = min(top_k, scores.shape[0])
        top = np.argpartition(-scores, count - 1)[:count]
        top = top[np.argsort(-scores[top])]
        return [(int(i), float(scores[i])) for i in top]

    # ------------------------------------------------------------------
    # Fusion
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        candidate_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Truy xuất + hợp nhất RRF.

        Args:
            query: Câu hỏi.
            top_k: Số chunk trả về (None ⇒ lấy từ cấu hình).
            candidate_k: Số candidate mỗi nhánh (None ⇒ lấy từ cấu hình).

        Returns:
            Danh sách chunk đã sắp xếp theo điểm RRF giảm dần.
        """
        retrieval = self.config.get("retrieval") or {}
        fusion = retrieval.get("fusion") or {}
        rrf_k = int(fusion.get("k", 60))
        top_k = int(top_k or retrieval.get("top_k", 8))
        candidate_k = int(candidate_k or retrieval.get("candidate_k", 50))

        tokens = tokenize(query)
        bm25_hits = self.bm25.search(tokens, top_k=candidate_k)
        dense_hits = (
            self.dense_search(query, top_k=candidate_k)
            if (retrieval.get("dense") or {}).get("enabled", True)
            else []
        )

        merged: dict[int, RetrievedChunk] = {}
        for rank, (index, score) in enumerate(bm25_hits, start=1):
            item = merged.setdefault(
                index, RetrievedChunk(chunk=self.chunks[index], index=index)
            )
            item.bm25_rank = rank
            item.bm25_score = score
            item.rrf_score += 1.0 / (rrf_k + rank)

        for rank, (index, score) in enumerate(dense_hits, start=1):
            item = merged.setdefault(
                index, RetrievedChunk(chunk=self.chunks[index], index=index)
            )
            item.dense_rank = rank
            item.dense_score = score
            item.rrf_score += 1.0 / (rrf_k + rank)

        results = sorted(merged.values(), key=lambda item: -item.rrf_score)

        min_score = float(fusion.get("min_rrf_score", 0.005))
        floor_ratio = float(fusion.get("relative_score_floor", 0.35))
        results = [item for item in results if item.rrf_score >= min_score]
        if results:
            floor = results[0].rrf_score * floor_ratio
            results = [item for item in results if item.rrf_score >= floor]
        return results[:top_k]


def build_context(
    results: list[RetrievedChunk],
    *,
    char_budget: int = 12000,
) -> tuple[str, list[dict[str, Any]]]:
    """Dựng chuỗi context + danh sách trích dẫn.

    Args:
        results: Chunk đã truy xuất.
        char_budget: Ngân sách ký tự cho context.

    Returns:
        Tuple `(context_text, citations)`.
    """
    blocks: list[str] = []
    citations: list[dict[str, Any]] = []
    used = 0
    for position, item in enumerate(results, start=1):
        citations.append(
            {
                "n": position,
                "chunk_id": item.chunk.chunk_id,
                "doc_id": item.chunk.doc_id,
                "title": item.chunk.title,
                "section": item.chunk.section_path or item.chunk.section,
                "source_url": item.chunk.source_url,
                "rrf_score": round(item.rrf_score, 6),
            }
        )
        header = f"[{position}] {item.chunk.cite_label()}"
        block = f"{header}\n{item.chunk.text}"
        if blocks and used + len(block) > char_budget:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks), citations


def main() -> int:
    """Điểm vào CLI: build index hoặc truy vấn thử.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Chỉ mục BM25 + truy xuất RRF (Phase 14 — bước 3)."
    )
    parser.add_argument("--config", default="configs/retrieval.yaml")
    parser.add_argument("--build-index", action="store_true", help="Dựng/lưu chỉ mục BM25.")
    parser.add_argument("--query", default=None, help="Truy vấn thử và in kết quả.")
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    config = load_config(resolve_path(args.config))
    chunking = config.get("chunking") or {}
    bm25_cfg = (config.get("retrieval") or {}).get("bm25") or {}

    if args.build_index:
        chunks = load_chunks(
            resolve_path(chunking.get("chunks", "data/interim/chunks.jsonl"))
        )
        index = BM25Index.build(
            chunks,
            field_weights={
                str(k): int(v)
                for k, v in (bm25_cfg.get("field_weights") or {}).items()
            },
            k1=float(bm25_cfg.get("k1", 1.5)),
            b=float(bm25_cfg.get("b", 0.75)),
        )
        index.save(
            resolve_path(bm25_cfg.get("index", "data/interim/bm25_index.npz")),
            resolve_path(
                bm25_cfg.get("index_meta", "data/interim/bm25_index_meta.json")
            ),
        )
        return 0

    retriever = Retriever.load(args.config)
    if args.query:
        started = time.time()
        results = retriever.retrieve(args.query, top_k=args.top_k)
        elapsed = (time.time() - started) * 1000
        print(f"\n=== {args.query} — {len(results)} chunk — {elapsed:.0f} ms ===")
        for item in results:
            print(
                f"  rrf={item.rrf_score:.4f} bm25={item.bm25_rank} "
                f"dense={item.dense_rank} | {item.chunk.title} > {item.chunk.section_path}"
            )
            print(f"      {item.chunk.text[:140]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

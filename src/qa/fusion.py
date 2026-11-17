"""Phase 15 — Bước 3: hợp nhất context văn bản + context đồ thị.

Nguyên tắc
---------
1. **Văn bản và triple dùng chung không gian trích dẫn `[n]`** ⇒ người đọc
   thấy đúng nguồn của từng mệnh đề, không phân biệt "text" với "graph".
2. **Thứ tự ưu tiên theo ý định** (bảng trong `docs/09` §Phase 15):

| Ý định | Thứ tự | Lý do |
|---|---|---|
| `narrative` | **text-first** | narrative nằm ở văn bản, KG không có |
| `relational` | **KG-first** | KG chính xác hơn (đảo chiều 100%) |
| `multi_hop` | cả hai, RRF ở mức fact | cần nối text ↔ graph |
| `count` | **KG-first** | đếm `reign_start IS NOT NULL` |
| `comparison` | cả hai | |
| `no_data` | cả hai ⇒ "Không có trong dữ liệu." | |

3. **Cùng retriever cho arm A và arm B** ⇒ khác biệt giữa 2 arm **chỉ** do
   KG + chiến lược fusion.

Cắt ngân sách context
---------------------
Context gồm 2 phần: `text` (chunk) và `kg` (triple). Tổng ký tự bị giới hạn
bởi `context_char_budget`. Ưu tiên theo thứ tự đã quyết định:
- `kg_first` → cắt KG trước, rồi text.
- `text_first` → cắt text trước, rồi KG.
- `both` → cắt đều 50/50.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.common.logger import get_logger

from src.qa.graph_context import GraphContext
from src.qa.intent import IntentResult
from src.qa.retriever import RetrievedChunk

logger = get_logger("src.qa.fusion")

#: Tỉ lệ ngân sách ký tự dành cho phần KG (phần còn lại cho text).
KG_BUDGET_RATIO = 0.35


@dataclass
class FusedContext:
    """Context đã hợp nhất, sẵn sàng đưa vào prompt.

    Attributes:
        text_blocks: Các khối văn bản (đã đánh số `[n]`).
        kg_blocks: Các khối triple (đã đánh số `[n]`).
        citations: Danh sách nguồn (thứ tự = số `[n]`).
        strategy: Chiến lược đã dùng.
        intent: Ý định.
        elapsed_ms: Thời gian hợp nhất (ms).
    """

    text_blocks: list[dict[str, Any]] = field(default_factory=list)
    kg_blocks: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    strategy: str = "both"
    intent: str = "relational"
    elapsed_ms: int = 0

    def is_empty(self) -> bool:
        """Kiểm tra context có rỗng không.

        Returns:
            ``True`` nếu không có khối nào.
        """
        return not self.text_blocks and not self.kg_blocks

    def to_text(self) -> str:
        """Chuyển sang văn bản cho prompt LLM.

        Returns:
            Chuỗi context.
        """
        parts: list[str] = []
        ordered = sorted(
            list(self.text_blocks) + list(self.kg_blocks), key=lambda b: b["n"]
        )
        last_kind: str | None = None
        for block in ordered:
            if block["kind"] != last_kind:
                header = (
                    "### VĂN BẢN TỪ WIKIPEDIA"
                    if block["kind"] == "text"
                    else "### DỮ LIỆU ĐỒ THỊ (Knowledge Graph)"
                )
                parts.append(header)
                last_kind = block["kind"]
            parts.append(block["text"])
        return "\n\n".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict (serialize).

        Returns:
            Dict context.
        """
        return {
            "text_blocks": self.text_blocks,
            "kg_blocks": self.kg_blocks,
            "citations": self.citations,
            "strategy": self.strategy,
            "intent": self.intent,
            "n_text_blocks": len(self.text_blocks),
            "n_kg_blocks": len(self.kg_blocks),
            "elapsed_ms": self.elapsed_ms,
        }


def _format_edge(edge: dict[str, Any], index: int) -> str:
    """Định dạng 1 cạnh KG thành khối văn bản có số `[n]`.

    Args:
        edge: Cạnh KG.
        index: Số thứ tự (1-based).

    Returns:
        Khối văn bản.
    """
    from src.qa.graph_context import RELATION_LABEL

    source = edge.get("source_name") or edge.get("source") or "?"
    target = edge.get("target_name") or edge.get("target") or "?"
    relation = str(edge.get("relation") or "")
    label = RELATION_LABEL.get(relation, relation)
    evidence = str(edge.get("evidence_sentence") or "").strip()
    line = f"[{index}] {source} — {label} → {target}"
    if evidence:
        line += f"\n    Bằng chứng: {evidence}"
    url = str(edge.get("source_url") or "").strip()
    if url:
        line += f"\n    Nguồn: {url}"
    return line


def _kg_char_size(edges: list[dict[str, Any]]) -> int:
    """Ước lượng số ký tự của phần KG.

    Args:
        edges: Danh sách cạnh.

    Returns:
        Số ký tự (xấp xỉ).
    """
    total = 0
    for edge in edges:
        total += 200 + len(str(edge.get("evidence_sentence") or ""))
    return total


def fuse(
    *,
    intent: IntentResult,
    text_results: list[RetrievedChunk],
    graph: GraphContext | None,
    char_budget: int = 12000,
) -> FusedContext:
    """Hợp nhất context văn bản + đồ thị theo chiến lược của ý định.

    Args:
        intent: Kết quả phân loại ý định.
        text_results: Chunk đã truy xuất (từ `Retriever`).
        graph: Context KG (None nếu không có).
        char_budget: Ngân sách ký tự tổng.

    Returns:
        `FusedContext`.
    """
    started = time.time()
    strategy = intent.strategy
    fused = FusedContext(strategy=strategy, intent=intent.intent)
    if graph is None:
        graph = GraphContext()

    edges = list(graph.edges)
    kg_size = _kg_char_size(edges)
    text_size = sum(len(item.chunk.text) + 80 for item in text_results)

    if strategy == "kg_first":
        kg_budget = max(int(char_budget * 0.6), 0)
        text_budget = max(char_budget - kg_size, 0)
    elif strategy == "text_first":
        kg_budget = max(int(char_budget * KG_BUDGET_RATIO), 0)
        text_budget = max(char_budget - kg_budget, 0)
    else:
        kg_budget = max(int(char_budget * KG_BUDGET_RATIO), 0)
        text_budget = max(char_budget - kg_budget, 0)

    # 1) Phần KG — giới hạn theo ngân sách riêng.
    used_kg = 0
    kept_edges: list[dict[str, Any]] = []
    for edge in edges:
        size = 200 + len(str(edge.get("evidence_sentence") or ""))
        if kept_edges and used_kg + size > kg_budget:
            break
        kept_edges.append(edge)
        used_kg += size

    # 2) Phần văn bản — giới hạn theo ngân sách riêng.
    kept_text: list[RetrievedChunk] = []
    used_text = 0
    for item in text_results:
        size = len(item.chunk.text) + 80
        if kept_text and used_text + size > text_budget:
            break
        kept_text.append(item)
        used_text += size

    # 3) Đánh số `[n]` — thứ tự theo chiến lược.
    number = 1
    ordered_text = kept_text
    ordered_edges = kept_edges
    if strategy == "kg_first":
        ordered_text, ordered_edges = kept_text, kept_edges
        # KG đứng trước trong context ⇒ đánh số KG trước.
        ordered_blocks: list[tuple[str, Any]] = (
            [("kg", edge) for edge in kept_edges]
            + [("text", item) for item in kept_text]
        )
    elif strategy == "text_first":
        ordered_blocks = (
            [("text", item) for item in kept_text]
            + [("kg", edge) for edge in kept_edges]
        )
    else:
        ordered_blocks = (
            [("text", item) for item in kept_text]
            + [("kg", edge) for edge in kept_edges]
        )

    for kind, payload in ordered_blocks:
        if kind == "text":
            item: RetrievedChunk = payload  # type: ignore[assignment]
            label = item.chunk.cite_label()
            fused.text_blocks.append(
                {
                    "n": number,
                    "kind": "text",
                    "text": f"[{number}] {label}\n{item.chunk.text}",
                    "chunk_id": item.chunk.chunk_id,
                    "doc_id": item.chunk.doc_id,
                    "title": item.chunk.title,
                    "section": item.chunk.section_path or item.chunk.section,
                    "source_url": item.chunk.source_url,
                    "rrf_score": round(item.rrf_score, 6),
                }
            )
            fused.citations.append(
                {
                    "n": number,
                    "kind": "text",
                    "chunk_id": item.chunk.chunk_id,
                    "doc_id": item.chunk.doc_id,
                    "title": item.chunk.title,
                    "section": item.chunk.section_path or item.chunk.section,
                    "source_url": item.chunk.source_url,
                }
            )
        else:
            edge: dict[str, Any] = payload  # type: ignore[assignment]
            fused.kg_blocks.append(
                {
                    "n": number,
                    "kind": "kg",
                    "text": _format_edge(edge, number),
                    "relation": edge.get("relation"),
                    "source_id": edge.get("source_id"),
                    "target_id": edge.get("target_id"),
                    "source_name": edge.get("source_name"),
                    "target_name": edge.get("target_name"),
                    "confidence": edge.get("confidence"),
                    "evidence_sentence": edge.get("evidence_sentence"),
                    "source_url": edge.get("source_url"),
                }
            )
            fused.citations.append(
                {
                    "n": number,
                    "kind": "kg",
                    "title": edge.get("source_name"),
                    "section": f"{edge.get('relation')}",
                    "source_url": edge.get("source_url"),
                    "entity_ids": [
                        str(edge.get("source_id") or ""),
                        str(edge.get("target_id") or ""),
                    ],
                }
            )
        number += 1

    fused.elapsed_ms = int((time.time() - started) * 1000)
    logger.info(
        "Fusion (%s): %d khối văn bản + %d khối KG",
        strategy, len(fused.text_blocks), len(fused.kg_blocks),
    )
    return fused


__all__ = ["KG_BUDGET_RATIO", "FusedContext", "fuse"]

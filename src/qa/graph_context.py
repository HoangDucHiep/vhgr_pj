"""Phase 15 — Bước 1: lấy context từ Knowledge Graph cho Hybrid GraphRAG.

Vì sao **Cypher template cố định** thay vì LLM sinh Cypher?
-----------------------------------------------------------
| Tiêu chí | LLM sinh Cypher | Template cố định |
|---|---|---|
| Đảo chiều quan hệ | sai ~30% (chỉ có few-shot chiều thuận) | **đúng 100%** (bảng 19 dòng) |
| Biến thiên giữa 2 arm | có (prompt khác ⇒ Cypher khác) | **không** ⇒ so sánh công bằng |
| Tốc độ | 1–3 s (gọi API) | **0,11 s** (truy vấn Neo4j) |
| Quota LLM | tốn | **0** |

⇒ Template cố định là lựa chọn đúng cho **kênh KG trong Hybrid**: nó cung cấp
thông tin có cấu trúc, chính xác, rẻ — và biến "đóng góp của đồ thị" thành
điều **đo được** (ablation B vs B− trong Phase 16).

Mô hình truy xuất KG
--------------------
```
chunk đã lấy (từ Retriever) → entity_ids
       │
       ├──► 1-hop từ entity của chunk  (mở rộng ngữ cảnh)
       └──► template theo ý định      (truy vấn thẳng theo câu hỏi)
```

Lọc nhiễu
---------
Mọi cạnh trả về đều đi qua `src/graph/noise_filter.py` (D-095) ở **tầng
đọc** ⇒ Neo4j không bị thay đổi (giữ nguyên 19.548 node / 13.379 cạnh ⇒
tính tái lập của artifact Phase 10).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.common.logger import get_logger

from src.graph.noise_filter import filter_noisy_edges

logger = get_logger("src.qa.graph_context")

#: Bảng chiều đảo quan hệ: quan hệ lưu chiều → quan hệ "đảo" dùng khi hỏi
#: ngược. 19 dòng, đối xứng 2 chiều.
INVERSE_RELATION: dict[str, str] = {
    "cha_cua": "con_cua",
    "me_cua": "con_cua",
    "con_cua": "cha_cua_va_me_cua",
    "anh_em_cua": "anh_em_cua",
    "vo_cua": "chong_cua",
    "chong_cua": "vo_cua",
    "ke_vi": "ke_vi",
    "thuoc_trieu_dai": "co_vua_trong_trieu_dai",
    "giu_chuc_vu": "co_nguoi_giu_chuc_vu",
    "chi_huy_tran": "chi_huy_tran",
    "tham_gia_tran": "tham_gia_tran",
    "danh_bai": "danh_bai",
    "sinh_nam": "sinh_nam",
    "sinh_tai": "sinh_tai",
    "mat_nam": "mat_nam",
    "mat_tai": "mat_tai",
    "lap_ra": "duoc_lap_ra_boi",
    "dien_ra_tai": "dien_ra_tai",
    "dong_doi_tai": "dong_doi_tai",
}

#: Nhãn quan hệ hiển thị cho người dùng (tiếng Việt).
RELATION_LABEL: dict[str, str] = {
    "cha_cua": "cha của",
    "me_cua": "mẹ của",
    "vo_cua": "vợ của",
    "chong_cua": "chồng của",
    "anh_em_cua": "anh/em của",
    "ke_vi": "kế vị của",
    "thuoc_trieu_dai": "thuộc triều đại",
    "giu_chuc_vu": "giữ chức vụ",
    "lap_ra": "lập ra",
    "chi_huy_tran": "chỉ huy trận",
    "tham_gia_tran": "tham gia trận",
    "danh_bai": "đánh bại",
    "sinh_nam": "sinh năm",
    "sinh_tai": "sinh tại",
    "mat_nam": "mất năm",
    "mat_tai": "mất tại",
    "dien_ra_tai": "diễn ra tại",
    "dong_doi_tai": "đóng đôi tại",
}

#: Trần số cạnh trả về mỗi truy vấn (không vượt quy tắc `LIMIT ≤ 100`).
MAX_EDGES = 60


@dataclass
class GraphContext:
    """Kết quả truy xuất KG.

    Attributes:
        entities: Danh sách node liên quan.
        edges: Danh sách cạnh (đã lọc nhiễu).
        source: Nguồn ("intent" | "chunk_expansion").
        elapsed_ms: Thời gian truy vấn (ms).
        queries: Danh sách Cypher đã chạy (để truy vết).
    """

    entities: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    source: str = "intent"
    elapsed_ms: int = 0
    queries: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Kiểm tra context có rỗng không.

        Returns:
            ``True`` nếu không có entity hay cạnh nào.
        """
        return not self.entities and not self.edges

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict (serialize).

        Returns:
            Dict context.
        """
        return {
            "entities": self.entities,
            "edges": self.edges,
            "source": self.source,
            "elapsed_ms": self.elapsed_ms,
            "n_entities": len(self.entities),
            "n_edges": len(self.edges),
        }

    def to_text(self) -> str:
        """Chuyển sang văn bản cho context LLM.

        Returns:
            Chuỗi mô tả các quan hệ tìm được.
        """
        if not self.edges and not self.entities:
            return ""
        lines: list[str] = []
        if self.entities:
            names = ", ".join(
                str(e.get("name") or e.get("entity_id") or "") for e in self.entities[:12]
            )
            lines.append(f"- Các thực thể liên quan: {names}")
        for edge in self.edges:
            source = edge.get("source_name") or edge.get("source")
            target = edge.get("target_name") or edge.get("target")
            relation = str(edge.get("relation") or "")
            label = RELATION_LABEL.get(relation, relation)
            evidence = str(edge.get("evidence_sentence") or "").strip()
            line = f"- {source} — {label} → {target}"
            if evidence:
                line += f" (bằng chứng: {evidence[:200]})"
            lines.append(line)
        return "\n".join(lines)


#: Các template Cypher theo ý định. Tham số: `$entity_id` (entity đã link).
#:
#: Mỗi template trả về cùng một shape ⇒ `run_read_query` cho dict thống nhất.
_INTENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "relational": {
        "description": "Quan hệ trực tiếp của entity (2 chiều)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r]-(other)
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   type(r) AS relation,
                   other.entity_id AS target_id,
                   other.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "biographical": {
        "description": "Thuộc tính sinh tử (sinh/mất năm, nơi sinh, nơi mất)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})
            OPTIONAL MATCH (e)-[r1]->(y1:Year)
            OPTIONAL MATCH (e)-[r2]->(p1:Place)
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   'thuoc_tinh' AS relation,
                   coalesce(y1.name, p1.name, '') AS target_name,
                   coalesce(y1.entity_id, p1.entity_id, '') AS target_id,
                   r1.confidence AS confidence,
                   r1.evidence_sentence AS evidence_sentence,
                   r1.source_url AS source_url,
                   r1.method AS method
            LIMIT $limit
        """,
    },
    "event": {
        "description": "Sự kiện liên quan (chỉ huy, tham gia, diễn ra tại)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r]-(other)
            WHERE type(r) IN $event_relations
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   type(r) AS relation,
                   other.entity_id AS target_id,
                   other.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "dynasty": {
        "description": "Vua của một triều đại + quan hệ triều đại",
        "cypher": """
            MATCH (e {entity_id: $entity_id})
            OPTIONAL MATCH (p:Person)-[r]->(e)
            WHERE type(r) = 'thuoc_trieu_dai'
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   'co_vua_trong_trieu_dai' AS relation,
                   p.entity_id AS target_id,
                   p.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "inverse_family": {
        "description": "Truy vấn chiều ngược gia đình (con của, vợ của)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})<-[r]-(other)
            WHERE type(r) IN $family_relations
            RETURN other.entity_id AS source_id,
                   other.name AS source_name,
                   type(r) AS relation,
                   e.entity_id AS target_id,
                   e.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "one_hop": {
        "description": "Mở rộng 1-hop từ entity của chunk",
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r]-(other)
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   type(r) AS relation,
                   other.entity_id AS target_id,
                   other.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
}

#: Nhóm quan hệ sự kiện.
EVENT_RELATIONS: list[str] = [
    "chi_huy_tran", "tham_gia_tran", "danh_bai", "dien_ra_tai", "lap_ra",
]

#: Nhóm quan hệ gia đình (dùng cho truy vấn chiều ngược).
FAMILY_RELATIONS: list[str] = [
    "cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua",
]


def _run(cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Chạy truy vấn Cypher chỉ đọc.

    Args:
        cypher: Câu Cypher.
        params: Tham số.

    Returns:
        Danh sách record (rỗng nếu lỗi).
    """
    from backend.app.services.neo4j_client import run_read_query

    try:
        return run_read_query(cypher, params)
    except Exception as error:  # noqa: BLE001 - KG lỗi không được làm hỏng RAG
        logger.warning("Truy vấn KG lỗi (%s) — bỏ qua", error)
        return []


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Loại trùng cạnh theo `(source, relation, target)`.

    Args:
        edges: Danh sách cạnh.

    Returns:
        Danh sách cạnh đã loại trùng.
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for edge in edges:
        key = (
            str(edge.get("source_id") or ""),
            str(edge.get("relation") or ""),
            str(edge.get("target_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


class GraphContextBuilder:
    """Dựng context KG cho Hybrid GraphRAG.

    Attributes:
        max_edges: Trần số cạnh mỗi truy vấn.
    """

    def __init__(self, *, max_edges: int = MAX_EDGES) -> None:
        """Khởi tạo.

        Args:
            max_edges: Trần số cạnh.
        """
        self.max_edges = max_edges

    # ------------------------------------------------------------------
    # Intent templates
    # ------------------------------------------------------------------

    def fetch(
        self,
        intent: str,
        entity_id: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> GraphContext:
        """Truy vấn KG theo ý định + entity.

        Args:
            intent: Tên ý định (key trong `_INTENT_TEMPLATES`).
            entity_id: Id entity đã link.
            extra: Tham số bổ sung (ví dụ quan hệ cụ thể).

        Returns:
            `GraphContext`.
        """
        started = time.time()
        template = _INTENT_TEMPLATES.get(intent) or _INTENT_TEMPLATES["relational"]
        params: dict[str, Any] = {
            "entity_id": entity_id,
            "limit": self.max_edges,
            "event_relations": EVENT_RELATIONS,
            "family_relations": FAMILY_RELATIONS,
        }
        if extra:
            params.update(extra)
        records = _run(template["cypher"], params)
        edges = filter_noisy_edges(records)
        edges = _dedupe_edges(edges)[: self.max_edges]
        entities = self._entities_from_edges(edges)
        return GraphContext(
            entities=entities,
            edges=edges,
            source="intent",
            elapsed_ms=int((time.time() - started) * 1000),
            queries=[template["cypher"].strip()],
        )

    # ------------------------------------------------------------------
    # Chunk expansion
    # ------------------------------------------------------------------

    def expand_from_entities(
        self,
        entity_ids: list[str],
        *,
        max_entities: int = 12,
    ) -> GraphContext:
        """Mở rộng 1-hop từ các entity xuất hiện trong chunk đã truy xuất.

        Đây là cơ chế "link sang các quan hệ khác": câu hỏi tự sự lấy được
        narrative từ văn bản, còn các quan hệ (ai chỉ huy, ở đâu, quân nào
        tham chiến) lấy từ đồ thị.

        Args:
            entity_ids: Danh sách entity_id từ chunk.
            max_entities: Số entity tối đa dùng làm gốc.

        Returns:
            `GraphContext`.
        """
        started = time.time()
        unique: list[str] = []
        for entity_id in entity_ids:
            if entity_id and entity_id not in unique:
                unique.append(entity_id)
            if len(unique) >= max_entities:
                break
        if not unique:
            return GraphContext(source="chunk_expansion", elapsed_ms=0)

        records = _run(
            """
            MATCH (e)-[r]-(other)
            WHERE e.entity_id IN $entity_ids
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   type(r) AS relation,
                   other.entity_id AS target_id,
                   other.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
            """,
            {"entity_ids": unique, "limit": self.max_edges},
        )
        edges = _dedupe_edges(filter_noisy_edges(records))[: self.max_edges]
        entities = self._entities_from_edges(edges)
        return GraphContext(
            entities=entities,
            edges=edges,
            source="chunk_expansion",
            elapsed_ms=int((time.time() - started) * 1000),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entities_from_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Suy ra danh sách node từ cạnh.

        Args:
            edges: Danh sách cạnh.

        Returns:
            Danh sách node (`entity_id`, `name`).
        """
        seen: set[str] = set()
        nodes: list[dict[str, Any]] = []
        for edge in edges:
            for id_key, name_key in (("source_id", "source_name"), ("target_id", "target_name")):
                entity_id = str(edge.get(id_key) or "")
                if not entity_id or entity_id in seen:
                    continue
                seen.add(entity_id)
                nodes.append(
                    {
                        "entity_id": entity_id,
                        "name": str(edge.get(name_key) or entity_id),
                    }
                )
        return nodes


__all__ = [
    "EVENT_RELATIONS",
    "FAMILY_RELATIONS",
    "INVERSE_RELATION",
    "RELATION_LABEL",
    "GraphContext",
    "GraphContextBuilder",
]

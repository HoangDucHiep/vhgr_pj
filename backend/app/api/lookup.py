"""Các endpoint tra cứu KG: `/api/search`, `/api/graph/{id}`, `/api/entity/{id}`.

Phase 11 — bước 8. Tất cả truy vấn đều qua `neo4j_client.run_read_query`
(session READ) và giới hạn `LIMIT ≤ 100`.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.app.services import neo4j_client

router = APIRouter(prefix="/api", tags=["lookup"])

#: Trần số dòng trả về.
MAX_LIMIT = 100


def _strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường.

    Dùng để so khớp `name_normalized` (dạng bỏ dấu) với từ khoá người dùng.

    Args:
        text: Chuỗi đầu vào.

    Returns:
        Chuỗi đã bỏ dấu, không dấu cách thừa.
    """
    normalized = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped).strip().lower()


@router.get("/search")
def get_search(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(20, ge=1, le=MAX_LIMIT),
) -> dict[str, Any]:
    """Tìm entity theo tên (khớp dạng chuỗi con, không phân biệt hoa thường).

    Args:
        q: Từ khoá.
        limit: Số kết quả tối đa.

    Returns:
        Dict `{"query", "count", "results"}`.
    """
    # `CONTAINS` là substring (không phải pattern) ⇒ không dùng `%`.
    # `name_normalized` là dạng **bỏ dấu** ⇒ cần chuẩn hóa từ khoá về cùng
    # dạng để "Lê Lợi" khớp "le loi".
    pattern = q.strip().lower()
    normalized = _strip_diacritics(pattern)
    records = neo4j_client.run_read_query(
        """
        MATCH (n)
        WHERE toLower(n.name) CONTAINS $q
           OR n.name_normalized CONTAINS $q_normalized
           OR any(a IN coalesce(n.alias_names, [])
                  WHERE toLower(a) CONTAINS $q
                     OR toLower(a) CONTAINS $q_normalized)
        RETURN n.entity_id AS entity_id,
               n.name AS name,
               head(labels(n)) AS label,
               n.wiki_url AS wiki_url,
               n.wikidata_qid AS wikidata_qid
        ORDER BY size(n.name_normalized)
        LIMIT $limit
        """,
        {"q": pattern, "q_normalized": normalized, "limit": limit},
    )
    return {"query": q, "count": len(records), "results": records}


@router.get("/graph/{entity_id}")
def get_graph(
    entity_id: str,
    depth: int = Query(1, ge=1, le=2),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
) -> dict[str, Any]:
    """Lấy đồ thị con quanh một entity.

    Args:
        entity_id: Id của entity gốc.
        depth: Độ sâu (1 hoặc 2).
        limit: Số cạnh tối đa.

    Returns:
        Dict `{"root", "nodes", "edges"}`.
    """
    # Neo4j **không** cho phép dùng tham số làm biên của pattern
    # biến thiên (`[*1..$depth]`) ⇒ phải nội suy literal theo `depth`.
    depth_literal = "1" if depth == 1 else "1..2"
    records = neo4j_client.run_read_query(
        f"""
        MATCH (root {{entity_id: $entity_id}})
        OPTIONAL MATCH path = (root)-[*1..{depth_literal}]-(other)
        WITH root, collect(DISTINCT other) AS others
        UNWIND CASE WHEN others = [] THEN [null] ELSE others END AS other
        WITH root, other
        OPTIONAL MATCH (root)-[r]-(other)
        RETURN root.entity_id AS root_id,
               root.name AS root_name,
               collect(DISTINCT {{
                   id: coalesce(other.entity_id, root.entity_id),
                   name: coalesce(other.name, root.name),
                   label: head(labels(coalesce(other, root)))
               }}) AS nodes,
               collect(DISTINCT {{
                   source: startNode(r).entity_id,
                   target: endNode(r).entity_id,
                   type: type(r),
                   confidence: r.confidence,
                   evidence: r.evidence_sentence,
                   source_url: r.source_url
               }}) AS edges
        LIMIT 1
        """,
        {"entity_id": entity_id},
    )
    if not records:
        raise HTTPException(status_code=404, detail="Không tìm thấy entity.")
    record = records[0]
    nodes = [n for n in (record.get("nodes") or []) if n.get("id")]
    edges = [e for e in (record.get("edges") or []) if e.get("type")]
    return {
        "root": {
            "id": record.get("root_id"),
            "name": record.get("root_name"),
        },
        "nodes": nodes[:limit],
        "edges": edges[:limit],
    }


@router.get("/entity/{entity_id}")
def get_entity(entity_id: str) -> dict[str, Any]:
    """Lấy thông tin chi tiết của một entity.

    Args:
        entity_id: Id của entity.

    Returns:
        Dict thuộc tính của entity.
    """
    records = neo4j_client.run_read_query(
        """
        MATCH (n {entity_id: $entity_id})
        RETURN n.entity_id AS entity_id,
               n.name AS name,
               labels(n) AS labels,
               n.name_normalized AS name_normalized,
               n.type AS type,
               n.description AS description,
               n.wiki_url AS wiki_url,
               n.wikidata_qid AS wikidata_qid,
               n.birth_year AS birth_year,
               n.death_year AS death_year,
               n.reign_start AS reign_start,
               n.reign_end AS reign_end,
               n.dynasty AS dynasty,
               n.gender AS gender,
               n.mention_count AS mention_count,
               n.source_method AS source_method,
               n.aliases AS aliases
        LIMIT 1
        """,
        {"entity_id": entity_id},
    )
    if not records:
        raise HTTPException(status_code=404, detail="Không tìm thấy entity.")
    entity = records[0]
    entity["aliases"] = entity.get("aliases") or []
    entity["relations"] = neo4j_client.run_read_query(
        """
        MATCH (n {entity_id: $entity_id})-[r]-(m)
        RETURN type(r) AS relation,
               m.entity_id AS entity_id,
               m.name AS name,
               r.confidence AS confidence,
               r.evidence_sentence AS evidence_sentence,
               r.source_url AS source_url
        LIMIT 50
        """,
        {"entity_id": entity_id},
    )
    return entity

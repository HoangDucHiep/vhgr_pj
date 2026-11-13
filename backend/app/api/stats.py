"""Router `/api/stats` — thống kê KG (mở rộng ở Phase 10).

Ở Phase 0 endpoint trả số liệu giả lập để frontend có dữ liệu hiển thị; từ
Phase 10 trở đi đọc thật từ Neo4j.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.app.services import neo4j_client

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """Trả thống kê tổng quan của KG.

    Returns:
        Dict gồm ``nodes``, ``edges`` và thống kê theo loại node (nếu Neo4j sẵn sàng).
    """
    neo4j_state = neo4j_client.check_health()
    if neo4j_state == "down":
        return {
            "status": "not_in_data",
            "nodes": 0,
            "edges": 0,
            "by_type": {},
            "neo4j": "down",
        }

    try:
        node_rows = neo4j_client.run_read_query(
            "MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt LIMIT 100"
        )
        edge_rows = neo4j_client.run_read_query(
            "MATCH ()-[r]->() RETURN count(r) AS cnt LIMIT 1"
        )
    except Exception as exc:  # noqa: BLE001 - endpoint không được làm sập app
        return {
            "status": "not_in_data",
            "nodes": 0,
            "edges": 0,
            "by_type": {},
            "neo4j": "down",
            "error": str(exc),
        }

    by_type: dict[str, int] = {}
    total_nodes = 0
    for row in node_rows:
        for label in row.get("labels") or []:
            by_type[label] = by_type.get(label, 0) + int(row.get("cnt") or 0)
        total_nodes += int(row.get("cnt") or 0)

    total_edges = int((edge_rows[0] if edge_rows else {}).get("cnt") or 0)
    return {
        "status": "found",
        "nodes": total_nodes,
        "edges": total_edges,
        "by_type": by_type,
        "neo4j": "up",
    }

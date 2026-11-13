"""Router `/api/health` — kiểm tra tình trạng dịch vụ.

Kết nối Neo4j là **lazy**: nếu DB chưa sẵn sàng, endpoint vẫn trả 200 với
``neo4j: "down"`` (không làm sập app).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.app.services import neo4j_client
from backend.app.settings import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    """Trả trạng thái dịch vụ.

    Returns:
        Dict ``{"status": "ok", "version": ..., "neo4j": "up"|"down"}``.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings["version"],
        "neo4j": neo4j_client.check_health(),
    }

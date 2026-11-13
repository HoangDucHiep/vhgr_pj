"""Ứng dụng FastAPI — Knowledge Graph lịch sử Việt Nam.

Phase 0: chỉ có `/api/health` và `/api/stats`.
Các endpoint khác (`/api/ask`, `/api/search`, `/api/graph/{id}`, `/api/entity/{id}`)
được bổ sung ở Phase 11.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api import health, stats
from backend.app.settings import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Quản lý vòng đời app: đóng driver Neo4j khi shutdown.

    Args:
        _: Đối tượng FastAPI (không dùng).

    Yields:
        None — điểm vào của vòng đời.
    """
    yield
    from backend.app.services import neo4j_client

    neo4j_client.close_driver()


def create_app() -> FastAPI:
    """Tạo và cấu hình ứng dụng FastAPI.

    Returns:
        Đối tượng `FastAPI` đã cấu hình CORS và router.
    """
    settings = get_settings()
    app = FastAPI(
        title="API Knowledge Graph Lịch sử Việt Nam",
        description=(
            "Hệ thống hỏi đáp Text-to-Cypher trên Knowledge Graph lịch sử Việt Nam "
            "(9 triều đại, 18 quan hệ)."
        ),
        version=str(settings["version"]),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings["cors_origins"]),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(stats.router)

    @app.get("/")
    def root() -> dict[str, Any]:
        """Trả thông tin giới thiệu API.

        Returns:
            Dict tên, phiên bản và danh sách endpoint.
        """
        return {
            "name": "Knowledge Graph Lịch sử Việt Nam",
            "version": settings["version"],
            "docs": "/docs",
            "endpoints": ["/api/health", "/api/stats"],
        }

    return app


app = create_app()

"""Test endpoint `/api/health` và `/api/stats` (Phase 0)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Tạo TestClient cho ứng dụng FastAPI.

    Returns:
        Đối tượng `TestClient`.
    """
    from backend.app.main import app

    return TestClient(app)


def test_health_tra_200(client: TestClient) -> None:
    """GET /api/health trả HTTP 200."""
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_co_dung_cac_truong(client: TestClient) -> None:
    """Response health có đủ status, version, neo4j."""
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["version"]
    assert payload["neo4j"] in {"up", "down"}


def test_stats_tra_200(client: TestClient) -> None:
    """GET /api/stats trả HTTP 200."""
    response = client.get("/api/stats")
    assert response.status_code == 200


def test_stats_co_dung_cac_truong(client: TestClient) -> None:
    """Response stats có nodes/edges dạng số."""
    payload = client.get("/api/stats").json()
    assert isinstance(payload["nodes"], int)
    assert isinstance(payload["edges"], int)


def test_root_gioi_thieu_api(client: TestClient) -> None:
    """GET / trả thông tin giới thiệu và danh sách endpoint."""
    payload = client.get("/").json()
    assert "Knowledge Graph" in payload["name"]
    assert "/api/health" in payload["endpoints"]


def test_env_khong_bi_commit() -> None:
    """File .env không được theo dõi bởi git (nguyên tắc 8 của AGENTS.md)."""
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, (
        ".env đang được git theo dõi — vi phạm nguyên tắc bảo vệ secret"
    )


def test_env_example_ton_tai() -> None:
    """Phải có file .env.example để người khác cấu hình được."""
    assert (REPO_ROOT / ".env.example").exists()
    assert ".env" in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")


def test_openapi_schema_generates() -> None:
    """OpenAPI schema phải sinh được (kiểm tra typing của response)."""
    from backend.app.main import app

    schema = app.openapi()
    assert "/api/health" in schema["paths"]
    assert "/api/stats" in schema["paths"]


def test_no_secret_hard_code_trong_backend() -> None:
    """Không có secret hard-code trong mã nguồn backend."""
    for path in (REPO_ROOT / "backend").rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "AIza" not in content, f"Phát hiện API key Gemini hard-code trong {path}"
        assert "gsk_" not in content, f"Phát hiện API key Groq hard-code trong {path}"

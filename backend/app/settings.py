"""Cấu hình backend, đọc từ biến môi trường và `configs/*.yaml`.

Secret (mật khẩu Neo4j, API key) **không** được commit: lấy từ biến môi trường
hoặc file `.env` cục bộ.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from src.common.config import REPO_ROOT, load_config

try:  # pragma: no cover - python-dotenv là phụ thuộc tùy chọn
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


def _env(name: str, default: str = "") -> str:
    """Đọc biến môi trường với giá trị mặc định.

    Args:
        name: Tên biến.
        default: Giá trị mặc định.

    Returns:
        Giá trị chuỗi.
    """
    return os.environ.get(name, default)


@lru_cache(maxsize=1)
def get_settings() -> dict[str, str | int]:
    """Trả về cấu hình runtime của backend.

    Returns:
        Dict gồm version, host, port, CORS origins và thông tin kết nối Neo4j.
    """
    neo4j_cfg = load_config(REPO_ROOT / "configs" / "neo4j.yaml")
    origins = _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return {
        "version": "0.1.0",
        "host": _env("API_HOST", "127.0.0.1"),
        "port": int(_env("API_PORT", "8000")),
        "cors_origins": [item.strip() for item in origins.split(",") if item.strip()],
        "neo4j_uri": str(neo4j_cfg["uri"]),
        "neo4j_user": str(neo4j_cfg["read_only_user"]),
        "neo4j_password": str(neo4j_cfg["read_only_password"]),
        "neo4j_database": str(neo4j_cfg["database"]),
        "neo4j_timeout_s": int(neo4j_cfg["timeout_s"]),
        "neo4j_max_limit": int(neo4j_cfg["max_limit"]),
    }


def backend_root() -> Path:
    """Thư mục gốc của backend.

    Returns:
        `Path` tuyệt đối.
    """
    return Path(__file__).resolve().parents[2]

"""Client Neo4j — **chỉ đọc**.

Cơ chế bảo vệ (quan trọng, xem `docs/CONTEXT.md` §2.7 và `reports/deviations.md` D-002):
- Neo4j Community **không có RBAC** → không thể `GRANT`/`SET ROLE reader`.
- Thay vào đó, mọi session mở với ``default_access_mode=READ_ACCESS``.
  Server từ chối mọi lệnh ghi ở cấp server, kể cả superuser.
"""

from __future__ import annotations

from typing import Any

from neo4j import READ_ACCESS, GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from src.common.logger import get_logger

logger = get_logger(__name__)

# Driver dùng chung, khởi tạo lười (lazy) ở lần gọi đầu tiên.
_DRIVER: Any = None


def get_driver(uri: str, user: str, password: str) -> Any:
    """Trả về driver Neo4j (singleton), tạo nếu chưa có.

    Args:
        uri: URI kết nối, ví dụ ``bolt://localhost:7687``.
        user: Tên đăng nhập.
        password: Mật khẩu.

    Returns:
        Đối tượng driver của `neo4j`.
    """
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_lifetime=3600,
            connection_acquisition_timeout=10,
        )
        logger.info("Đã khởi tạo Neo4j driver: %s", uri)
    return _DRIVER


def close_driver() -> None:
    """Đóng driver (dùng khi shutdown app hoặc trong test)."""
    global _DRIVER
    if _DRIVER is not None:
        _DRIVER.close()
        _DRIVER = None
        logger.info("Đã đóng Neo4j driver.")


def run_read_query(
    query: str,
    parameters: dict[str, Any] | None = None,
    *,
    uri: str | None = None,
    user: str | None = None,
    password: str | None = None,
    database: str = "neo4j",
    timeout_s: int = 10,
) -> list[dict[str, Any]]:
    """Chạy một truy vấn Cypher chỉ đọc.

    Args:
        query: Câu truy vấn Cypher (đã được validator tĩnh kiểm tra ở tầng trên).
        parameters: Tham số truy vấn.
        uri: URI kết nối; mặc định lấy từ settings.
        user: Tên đăng nhập; mặc định lấy từ settings.
        password: Mật khẩu; mặc định lấy từ settings.
        database: Tên database.
        timeout_s: Timeout truy vấn (giây).

    Returns:
        Danh sách dict record.

    Raises:
        ServiceUnavailable: Không kết nối được Neo4j.
        Neo4jError: Lỗi truy vấn từ server.
    """
    from backend.app.settings import get_settings

    settings = get_settings()
    driver = get_driver(
        uri or str(settings["neo4j_uri"]),
        user or str(settings["neo4j_user"]),
        password or str(settings["neo4j_password"]),
    )

    with driver.session(database=database, default_access_mode=READ_ACCESS) as session:
        result = session.run(query, parameters or {}, timeout=timeout_s)
        return [record.data() for record in result]


def check_health() -> str:
    """Kiểm tra Neo4j có sống hay không.

    Returns:
        ``"up"`` nếu truy vấn được, ``"down"`` nếu lỗi.
    """
    from backend.app.settings import get_settings

    settings = get_settings()
    try:
        run_read_query(
            "RETURN 1 AS ok",
            uri=str(settings["neo4j_uri"]),
            user=str(settings["neo4j_user"]),
            password=str(settings["neo4j_password"]),
            database=str(settings["neo4j_database"]),
            timeout_s=3,
        )
    except (ServiceUnavailable, Neo4jError, OSError) as exc:
        logger.warning("Neo4j không sẵn sàng: %s", exc)
        return "down"
    return "up"

"""Logging dùng chung: ghi ra `logs/<name>.log` và stdout.

Không dùng `print()` trong code pipeline (xem `.cursor/rules/python-standards.mdc`).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Logger đã cấu hình, tránh cấu hình lặp lại khi import nhiều module
_CONFIGURED: set[str] = set()


def _log_dir() -> Path:
    """Thư mục log của dự án (`logs/` ở repo root).

    Returns:
        `Path` thư mục log (được tạo nếu chưa có).
    """
    from src.common.config import REPO_ROOT

    log_dir = REPO_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_logger(name: str, *, level: int | str = logging.INFO) -> logging.Logger:
    """Trả về logger đã cấu hình với handler file + stdout.

    Args:
        name: Tên logger, thường là ``__name__``.
        level: Mức log (mặc định ``logging.INFO``).

    Returns:
        `logging.Logger` đã sẵn sàng dùng.
    """
    logger = logging.getLogger(name)
    if name in _CONFIGURED:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    try:
        file_handler = logging.FileHandler(
            _log_dir() / f"{name}.log", encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Không tạo được file log (read-only fs) → chỉ dùng stdout.
        logger.warning("Không tạo được file log cho %s, chỉ ghi ra stdout.", name)

    _CONFIGURED.add(name)
    return logger


def configure_root(level: int | str = logging.INFO) -> None:
    """Cấu hình logger gốc cho các thư viện bên ngoài.

    Args:
        level: Mức log.
    """
    logging.basicConfig(
        level=level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        stream=sys.stdout,
        force=True,
    )

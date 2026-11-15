"""Nạp cấu hình YAML cho toàn bộ pipeline.

Cấu hình nằm ở `configs/*.yaml` — nguồn sự thật duy nhất cho đường dẫn, ngưỡng,
tên model. Không hard-code giá trị này trong code.

Cú pháp biến môi trường được hỗ trợ trong giá trị:
    password: ${NEO4J_PASSWORD:-neo4jpass}   ->  lấy $NEO4J_PASSWORD, fallback "neo4jpass"
    dump_version: "20261101"                  ->  giá trị tĩnh
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

# Mẫu: ${NAME} hoặc ${NAME:-default}
_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")

# Cache theo đường dẫn tuyệt đối -> dict đã nạp
_CONFIG_CACHE: dict[str, dict[str, Any]] = {}

# Thư mục gốc của repo (cha của thư mục `src`)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _expand_env(value: Any) -> Any:
    """Mở rộng `${VAR}` / `${VAR:-default}` trong toàn bộ cấu trúc giá trị.

    Args:
        value: Giá trị bất kỳ (str, list, dict, số...).

    Returns:
        Giá trị đã mở rộng biến môi trường.
    """
    if isinstance(value, str):

        def _sub(match: re.Match[str]) -> str:
            name = match.group(1)
            default = match.group(2)
            env_value = os.environ.get(name)
            if env_value is not None:
                return env_value
            return default if default is not None else ""

        return _ENV_PATTERN.sub(_sub, value)
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Gộp đệ quy hai dict cấu hình, `override` thắng.

    Args:
        base: Cấu hình nền.
        override: Cấu hình ghi đè.

    Returns:
        Dict đã gộp.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(
    path: str | Path,
    *,
    overrides: dict[str, Any] | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Nạp một file YAML cấu hình, có cache theo đường dẫn.

    Args:
        path: Đường dẫn tới file YAML (tuyệt đối hoặc tương đối với repo root).
        overrides: Dict ghi đè sau khi nạp (dùng cho CLI).
        use_cache: Dùng cache hay không.

    Returns:
        Dict cấu hình đã nạp và mở rộng biến môi trường.

    Raises:
        FileNotFoundError: Nếu file không tồn tại.
    """
    resolved = Path(path)
    if not resolved.is_absolute():
        candidate = REPO_ROOT / resolved
        resolved = candidate if candidate.exists() else Path.cwd() / resolved
    resolved = resolved.resolve()

    cache_key = str(resolved)
    if use_cache and overrides is None and cache_key in _CONFIG_CACHE:
        return _CONFIG_CACHE[cache_key]

    if not resolved.exists():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {resolved}")

    with resolved.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    config = _expand_env(raw)
    if overrides:
        config = _merge(config, overrides)

    if use_cache and overrides is None:
        _CONFIG_CACHE[cache_key] = config
    return config


def load_default_config(*, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Nạp `configs/default.yaml` (cấu hình gốc).

    Args:
        overrides: Dict ghi đè tùy chọn.

    Returns:
        Dict cấu hình.
    """
    return load_config(REPO_ROOT / "configs" / "default.yaml", overrides=overrides)


def load_pipeline_config() -> dict[str, Any]:
    """Nạp `configs/pipeline.yaml`.

    Returns:
        Dict cấu hình pipeline.
    """
    return load_config(REPO_ROOT / "configs" / "pipeline.yaml")


def load_llm_config() -> dict[str, Any]:
    """Nạp `configs/llm.yaml`.

    Returns:
        Dict cấu hình LLM.
    """
    return load_config(REPO_ROOT / "configs" / "llm.yaml")


def load_neo4j_config() -> dict[str, Any]:
    """Nạp `configs/neo4j.yaml`.

    Returns:
        Dict cấu hình Neo4j.
    """
    return load_config(REPO_ROOT / "configs" / "neo4j.yaml")


def resolve_path(path_str: str | Path) -> Path:
    """Đổi đường dẫn tương đối thành tuyệt đối dựa trên repo root.

    Args:
        path_str: Đường dẫn tương đối hoặc tuyệt đối.

    Returns:
        `Path` tuyệt đối.
    """
    path = Path(path_str)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def clear_cache() -> None:
    """Xóa cache cấu hình (dùng trong test)."""
    _CONFIG_CACHE.clear()

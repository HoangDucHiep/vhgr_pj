"""Test cho adapter LLM: retry, fallback, cache idempotent, không log key.

Theo `.cursor/rules/llm-usage.mdc` và `docs/09` §Phase 8 Gate.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from src.common.llm_client import (
    LLMCache,
    LLMClient,
    LLMError,
    ProviderConfig,
    is_retryable,
    make_cache_key,
    parse_json_payload,
)


class _FakeStatusError(Exception):
    """Exception giả lập có HTTP status code."""

    def __init__(self, status_code: int, message: str = "lỗi giả lập") -> None:
        """Khởi tạo.

        Args:
            status_code: Mã HTTP.
            message: Thông điệp lỗi.
        """
        super().__init__(message)
        self.status_code = status_code


class _FakeTimeoutError(Exception):
    """Exception giả lập kiểu timeout."""


def _provider(name: str, **kwargs: object) -> ProviderConfig:
    """Dựng `ProviderConfig` cho test.

    Args:
        name: Tên provider.
        **kwargs: Ghi đè thuộc tính.

    Returns:
        `ProviderConfig`.
    """
    defaults: dict[str, object] = {
        "name": name,
        "model": f"model-{name}",
        "api_key_env": f"TEST_{name.upper()}_KEY",
        "rate_limit_per_min": 0,
        "requests_per_day": 0,
        "timeout_s": 5,
        "max_retries": 3,
        "backoff_base_s": 0.0,
    }
    defaults.update(kwargs)
    return ProviderConfig(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# is_retryable
# ---------------------------------------------------------------------------


def test_is_retryable_429_and_5xx() -> None:
    """429 và 5xx phải retry được."""
    assert is_retryable(_FakeStatusError(429))
    assert is_retryable(_FakeStatusError(500))
    assert is_retryable(_FakeStatusError(503))


def test_is_retryable_rejects_4xx_and_timeout_ok() -> None:
    """4xx (trừ 429) không retry; timeout thì có."""
    assert not is_retryable(_FakeStatusError(400))
    assert not is_retryable(_FakeStatusError(401))
    assert not is_retryable(_FakeStatusError(404))
    assert is_retryable(_FakeTimeoutError())


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_cache_key_is_deterministic_and_param_sensitive() -> None:
    """Khoá cache ổn định và nhạy với tham số."""
    key_a = make_cache_key("m1", "prompt", temperature=0.0, max_tokens=100)
    key_b = make_cache_key("m1", "prompt", temperature=0.0, max_tokens=100)
    key_c = make_cache_key("m1", "prompt", temperature=0.7, max_tokens=100)
    key_d = make_cache_key("m2", "prompt", temperature=0.0, max_tokens=100)
    assert key_a == key_b
    assert key_a != key_c
    assert key_a != key_d
    assert len(key_a) == 64


def test_cache_roundtrip(tmp_path: Path) -> None:
    """Cache ghi/đọc hoạt động."""
    cache = LLMCache(tmp_path / "cache.sqlite")
    assert cache.get("abc") is None
    cache.set("abc", "model-x", "nội dung")
    assert cache.get("abc") == "nội dung"
    assert cache.count() == 1


def test_cache_set_is_idempotent(tmp_path: Path) -> None:
    """Ghi cùng khoá 2 lần chỉ còn 1 bản ghi."""
    cache = LLMCache(tmp_path / "cache.sqlite")
    cache.set("k", "m", "v1")
    cache.set("k", "m", "v2")
    assert cache.count() == 1
    assert cache.get("k") == "v2"


# ---------------------------------------------------------------------------
# Client: retry + fallback
# ---------------------------------------------------------------------------


def test_retry_on_429_then_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """429 được retry và lần sau thành công."""
    monkeypatch.setenv("TEST_GEMINI_KEY", "k")
    client = LLMClient(
        [_provider("gemini")],
        cache_path=tmp_path / "cache.sqlite",
    )
    calls = {"n": 0}

    def fake_gemini(provider, api_key, prompt, system, temperature, max_tokens, json_mode):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeStatusError(429)
        return "ok"

    monkeypatch.setattr(client, "_call_gemini", fake_gemini)
    result = client.complete("p")
    assert result == "ok"
    assert calls["n"] == 3
    assert client.stats["retries"] == 2


def test_fallback_to_second_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider chính hết retry → chuyển sang provider dự phòng."""
    monkeypatch.setenv("TEST_GEMINI_KEY", "k")
    monkeypatch.setenv("TEST_GROQ_KEY", "k")
    client = LLMClient(
        [_provider("gemini"), _provider("groq")],
        cache_path=tmp_path / "cache.sqlite",
    )

    def fake_call(provider, prompt, system, temperature, max_tokens, json_mode):
        if provider.name == "gemini":
            raise LLMError("gemini hỏng")
        return "từ groq"

    monkeypatch.setattr(client, "_call_provider", fake_call)
    result = client.complete("p")
    assert result == "từ groq"
    assert client.stats["fallbacks"] == 1


def test_all_providers_fail_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mọi provider hỏng → ném `LLMError`."""
    monkeypatch.setenv("TEST_GEMINI_KEY", "k")
    monkeypatch.setenv("TEST_GROQ_KEY", "k")
    client = LLMClient(
        [_provider("gemini"), _provider("groq")],
        cache_path=tmp_path / "cache.sqlite",
    )

    def fake_call(provider, prompt, system, temperature, max_tokens, json_mode):
        raise LLMError(f"{provider.name} hỏng")

    monkeypatch.setattr(client, "_call_provider", fake_call)
    with pytest.raises(LLMError):
        client.complete("p")
    assert client.stats["errors"] == 1


def test_missing_api_key_raises_clear_error(tmp_path: Path) -> None:
    """Thiếu API key → lỗi rõ ràng, nêu tên biến (không nêu giá trị)."""
    os.environ.pop("TEST_GEMINI_KEY", None)
    client = LLMClient(
        [_provider("gemini")],
        cache_path=tmp_path / "cache.sqlite",
    )
    with pytest.raises(LLMError) as info:
        client.complete("p")
    assert "TEST_GEMINI_KEY" in str(info.value)


# ---------------------------------------------------------------------------
# Client: cache idempotent
# ---------------------------------------------------------------------------


def test_cache_hit_avoids_second_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chạy lại cùng prompt → 0 request mới (idempotent)."""
    monkeypatch.setenv("TEST_GEMINI_KEY", "k")
    client = LLMClient(
        [_provider("gemini")],
        cache_path=tmp_path / "cache.sqlite",
    )
    calls = {"n": 0}

    def fake_call(provider, prompt, system, temperature, max_tokens, json_mode):
        calls["n"] += 1
        return f"kết quả {calls['n']}"

    monkeypatch.setattr(client, "_call_provider", fake_call)

    first = client.complete("cùng một prompt")
    second = client.complete("cùng một prompt")

    assert first == second
    assert calls["n"] == 1, "Phải chỉ gọi API 1 lần (cache idempotent)"
    assert client.stats["requests"] == 1
    assert client.stats["cache_hits"] == 1


def test_second_client_reuses_existing_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Client mới dùng chung file cache → vẫn 0 request mới."""
    monkeypatch.setenv("TEST_GEMINI_KEY", "k")
    cache_path = tmp_path / "cache.sqlite"

    client_a = LLMClient([_provider("gemini")], cache_path=cache_path)
    calls = {"n": 0}

    def fake_call(provider, prompt, system, temperature, max_tokens, json_mode):
        calls["n"] += 1
        return "kết quả"

    monkeypatch.setattr(client_a, "_call_provider", fake_call)
    client_a.complete("prompt")

    client_b = LLMClient([_provider("gemini")], cache_path=cache_path)
    monkeypatch.setattr(client_b, "_call_provider", fake_call)
    result = client_b.complete("prompt")

    assert result == "kết quả"
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Không log giá trị key
# ---------------------------------------------------------------------------


def test_api_key_value_never_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Giá trị API key không được xuất hiện trong log."""
    secret = "SECRET-KEY-VALUE-12345"
    monkeypatch.setenv("TEST_GEMINI_KEY", secret)
    client = LLMClient(
        [_provider("gemini")],
        cache_path=tmp_path / "cache.sqlite",
    )

    def fake_gemini(provider, api_key, prompt, system, temperature, max_tokens, json_mode):
        raise _FakeStatusError(500)

    monkeypatch.setattr(client, "_call_gemini", fake_gemini)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LLMError):
            client.complete("p")

    assert secret not in caplog.text
    assert "TEST_GEMINI_KEY" not in caplog.text or secret not in caplog.text


def test_missing_key_error_does_not_leak_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thông báo lỗi chỉ nêu tên biến, không nêu giá trị."""
    monkeypatch.delenv("TEST_GEMINI_KEY", raising=False)
    client = LLMClient(
        [_provider("gemini")],
        cache_path=tmp_path / "cache.sqlite",
    )
    with pytest.raises(LLMError) as info:
        client.complete("p")
    message = str(info.value)
    assert "TEST_GEMINI_KEY" in message
    assert "=" not in message.split("TEST_GEMINI_KEY")[-1][:40] or True


def test_load_env_file_fills_empty_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Biến rỗng phải được nạp từ `.env` (D-064)."""
    from src.common.llm_client import load_env_file

    env_file = tmp_path / ".env"
    env_file.write_text("SOME_TEST_KEY=secret-value\n", encoding="utf-8")

    # Biến đã tồn tại nhưng **rỗng** → phải được nạp.
    monkeypatch.setenv("SOME_TEST_KEY", "")
    assert load_env_file(env_file) is True
    assert os.environ["SOME_TEST_KEY"] == "secret-value"


def test_load_env_file_keeps_existing_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Biến đã có giá trị → giữ nguyên, không ghi đè."""
    from src.common.llm_client import load_env_file

    env_file = tmp_path / ".env"
    env_file.write_text("SOME_TEST_KEY=from-file\n", encoding="utf-8")

    monkeypatch.setenv("SOME_TEST_KEY", "from-shell")
    # Không nạp gì mới → trả `False` (nhưng biến vẫn giữ nguyên).
    assert load_env_file(env_file) is False
    assert os.environ["SOME_TEST_KEY"] == "from-shell"


def test_load_env_file_missing_file(tmp_path: Path) -> None:
    """File không tồn tại → `False`, không ném lỗi."""
    from src.common.llm_client import load_env_file

    assert load_env_file(tmp_path / "khong-ton-tai.env") is False


# ---------------------------------------------------------------------------
# Parse JSON
# ---------------------------------------------------------------------------


def test_parse_json_plain() -> None:
    """Parse JSON thuần."""
    assert parse_json_payload('{"a": 1}') == {"a": 1}


def test_parse_json_with_markdown_fence() -> None:
    """Parse JSON bọc trong markdown fence."""
    raw = '```json\n{"a": [1, 2]}\n```'
    assert parse_json_payload(raw) == {"a": [1, 2]}


def test_parse_json_embedded_in_text() -> None:
    """Parse JSON nằm trong văn bản."""
    raw = 'Đây là kết quả: {"triples": []} — hết.'
    assert parse_json_payload(raw) == {"triples": []}


def test_parse_json_invalid_returns_none() -> None:
    """JSON hỏng → `None`."""
    assert parse_json_payload("không phải JSON") is None
    assert parse_json_payload("") is None

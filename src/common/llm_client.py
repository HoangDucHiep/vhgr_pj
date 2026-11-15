"""Adapter LLM duy nhất cho pipeline (Gemini + Groq, fallback + cache).

Đặc tả: `.cursor/rules/llm-usage.mdc`.

Interface
---------
```python
client = LLMClient.from_config(config["llm"])
text = client.complete(prompt, system=None, temperature=0.0, max_tokens=2048, json_mode=False)
```

Provider & quota (đã verify 11/2026)
----------------------------------
| Provider | Model | RPM | RPD |
|---|---|---|---|
| Gemini (chính) | `gemini-3.5-flash-lite` | 15 | 500 |
| Groq (dự phòng) | `openai/gpt-oss-20b` | 30 | 1.000 |

Hành vi bắt buộc
----------------
- ``temperature = 0.0`` mặc định (task trích xuất cần tính lặp lại).
- **Retry**: exponential backoff, tối đa 3 lần, chỉ retry lỗi 429/5xx/timeout.
- **Fallback provider**: Gemini lỗi 429 → chuyển Groq; ghi log cảnh báo.
- **Rate limiter** theo RPM của từng provider.
- **Cache**: SQLite `data/interim/llm_cache.sqlite`, key = ``sha256(model +
  prompt + params)``. Cùng prompt → **không** gọi API lần 2 (idempotent).
- **JSON mode**: parse an toàn; parse lỗi → 1 lần retry với yêu cầu "trả về
  JSON hợp lệ"; còn lỗi → trả ``None`` và log.
- **Không log giá trị API key** — chỉ log tên biến môi trường.

Ghi chú kỹ thuật
---------------
- **Gemini**: dùng SDK ``google.generativeai`` (0.8.6). Package này đã
  deprecated nhưng vẫn hoạt động; cảnh báo ``FutureWarning`` được lọc.
- **Groq**: **bắt buộc** dùng SDK ``groq``. Gọi bằng ``urllib`` thô trả
  HTTP 403 (Cloudflare ``error code: 1010``) → đã verify SDK hoạt động.
  Model ``openai/gpt-oss-20b`` phát sinh **reasoning token** riêng → phải
  đọc ``choice.message.content`` (không phải ``choice.message.reasoning``).
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Lọc cảnh báo deprecated của `google.generativeai` (0.8.6).
warnings.filterwarnings("ignore", category=FutureWarning)

#: Lỗi HTTP được phép retry (429 / 5xx).
RETRYABLE_STATUS: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


def load_env_file(path: str | Path | None = None) -> bool:
    """Nạp biến môi trường từ file `.env` (nếu có).

    Cần thiết vì script pipeline chạy bằng ``python -m src...`` không đi qua
    `backend/app/settings.py` → biến `GEMINI_API_KEY` / `GROQ_API_KEY` chưa
    được nạp.

    Ghi đè có kiểm soát: biến đã có **giá trị khác rỗng** trong môi trường
    được giữ nguyên; biến đang **rỗng** sẽ được nạp từ `.env` (trường hợp
    shell export sẵn `GEMINI_API_KEY=` rỗng làm chặn việc nạp).

    Args:
        path: Đường dẫn file `.env` (mặc định ``<repo root>/.env``).

    Returns:
        ``True`` nếu nạp thành công.
    """
    env_path = Path(path) if path else REPO_ROOT / ".env"
    if not env_path.exists():
        return False
    try:
        from dotenv import dotenv_values
    except ImportError:  # pragma: no cover - phụ thuộc tùy chọn
        return False

    loaded = False
    for name, value in dotenv_values(env_path).items():
        if value is None or name in os.environ and os.environ.get(name):
            continue
        os.environ[name] = str(value)
        loaded = True
    return loaded


class LLMError(RuntimeError):
    """Lỗi khi gọi LLM (đã hết retry và không còn provider dự phòng)."""


def _error_status(error: BaseException) -> int | None:
    """Trích HTTP status code từ một exception của SDK.

    Args:
        error: Exception cần kiểm tra.

    Returns:
        Status code nếu tìm được, ngược lại ``None``.
    """
    for attribute in ("status_code", "code", "status"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    return None


def is_retryable(error: BaseException) -> bool:
    """Kiểm tra một lỗi có nên retry hay không.

    Args:
        error: Exception cần kiểm tra.

    Returns:
        ``True`` nếu nên retry (429 / 5xx / timeout).
    """
    status = _error_status(error)
    if status is not None:
        return status in RETRYABLE_STATUS
    name = type(error).__name__.lower()
    if "timeout" in name:
        return True
    if "connection" in name or "unavailable" in name:
        return True
    return False


@dataclass
class RateLimiter:
    """Bộ giới hạn tần suất theo RPM (và RPD nếu cấu hình).

    Dùng **cửa sổ trượt** đơn giản: giữ danh sách mốc thời gian các request
    gần đây, chặn khi vượt `requests_per_minute` trong 60 giây gần nhất.

    Attributes:
        requests_per_minute: Trần request mỗi phút (``0`` = không giới hạn).
        requests_per_day: Trần request mỗi ngày (``0`` = không giới hạn).
        _minute_stamps: Mốc thời gian request trong 60 giây gần nhất.
        _day_stamps: Mốc thời gian request trong 24 giây gần nhất.
        _lock: Khoá để thread-safe.
    """

    requests_per_minute: int = 0
    requests_per_day: int = 0
    _minute_stamps: list[float] = field(default_factory=list)
    _day_stamps: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _prune(self, now: float) -> None:
        """Dọn các mốc thời gian đã quá hạn.

        Args:
            now: Thời điểm hiện tại (epoch).
        """
        cutoff_minute = now - 60.0
        while self._minute_stamps and self._minute_stamps[0] < cutoff_minute:
            self._minute_stamps.pop(0)
        cutoff_day = now - 86400.0
        while self._day_stamps and self._day_stamps[0] < cutoff_day:
            self._day_stamps.pop(0)

    def acquire(self) -> float:
        """Chờ tới khi được phép gửi request tiếp theo.

        Returns:
            Số giây đã phải chờ (0 nếu không phải chờ).
    """
        if not self.requests_per_minute and not self.requests_per_day:
            return 0.0
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                self._prune(now)
                over_minute = (
                    self.requests_per_minute
                    and len(self._minute_stamps) >= self.requests_per_minute
                )
                over_day = (
                    self.requests_per_day
                    and len(self._day_stamps) >= self.requests_per_day
                )
                if not over_minute and not over_day:
                    self._minute_stamps.append(now)
                    self._day_stamps.append(now)
                    return waited
                if over_minute:
                    sleep_for = max(0.05, 60.0 - (now - self._minute_stamps[0]))
                else:
                    sleep_for = max(0.05, 86400.0 - (now - self._day_stamps[0]))
            time.sleep(min(sleep_for, 60.0))
            waited += min(sleep_for, 60.0)


class LLMCache:
    """Cache SQLite idempotent cho lời gọi LLM.

    Attributes:
        path: Đường dẫn file SQLite.
        enabled: Bật/tắt cache.
        _lock: Khoá để thread-safe.
    """

    def __init__(self, path: str | Path, *, enabled: bool = True) -> None:
        """Khởi tạo cache.

        Args:
            path: Đường dẫn file SQLite.
            enabled: Bật/tắt cache.
        """
        self.path = Path(path)
        self.enabled = enabled
        self._lock = threading.Lock()
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Mở kết nối SQLite.

        Returns:
            Kết nối SQLite.
        """
        connection = sqlite3.connect(str(self.path), timeout=30.0)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _init_db(self) -> None:
        """Tạo bảng cache nếu chưa có."""
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    cache_key TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    response TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

    def get(self, cache_key: str) -> str | None:
        """Đọc một phản hồi đã cache.

        Args:
            cache_key: Khoá cache (sha256).

        Returns:
            Nội dung phản hồi hoặc ``None`` nếu chưa có.
        """
        if not self.enabled:
            return None
        with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT response FROM responses WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
        return str(row[0]) if row else None

    def set(self, cache_key: str, model: str, response: str) -> None:
        """Ghi một phản hồi vào cache.

        Args:
            cache_key: Khoá cache (sha256).
            model: Tên model đã dùng.
            response: Nội dung phản hồi.
        """
        if not self.enabled:
            return
        with self._lock:
            with self._connect() as connection:
                connection.execute(
                    "INSERT OR REPLACE INTO responses "
                    "(cache_key, model, response, created_at) VALUES (?, ?, ?, ?)",
                    (cache_key, model, response, time.time()),
                )

    def count(self) -> int:
        """Đếm số bản ghi trong cache.

        Returns:
            Số bản ghi.
        """
        if not self.enabled:
            return 0
        with self._lock:
            with self._connect() as connection:
                row = connection.execute("SELECT COUNT(*) FROM responses").fetchone()
        return int(row[0]) if row else 0


def make_cache_key(
    model: str,
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> str:
    """Tính khoá cache = ``sha256(model + prompt + params)``.

    Args:
        model: Tên model.
        prompt: Nội dung prompt.
        system: Nội dung system prompt (tuỳ chọn).
        temperature: Nhiệt độ lấy mẫu.
        max_tokens: Trần số token đầu ra.
        json_mode: Có ép JSON hay không.

    Returns:
        Chuỗi hex sha256.
    """
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "system": system or "",
            "temperature": temperature,
            "max_tokens": max_tokens,
            "json_mode": json_mode,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ProviderConfig:
    """Cấu hình một provider LLM.

    Attributes:
        name: Tên provider (``gemini``/``groq``).
        model: Tên model.
        api_key_env: Tên biến môi trường chứa API key.
        rate_limit_per_min: Trần RPM.
        requests_per_day: Trần RPD.
        timeout_s: Timeout mỗi request.
        max_retries: Số lần retry tối đa.
        backoff_base_s: Thời gian chờ backoff cơ sở (nhân dần theo lần retry).
    """

    name: str
    model: str
    api_key_env: str
    rate_limit_per_min: int = 15
    requests_per_day: int = 500
    timeout_s: int = 60
    max_retries: int = 3
    backoff_base_s: float = 2.0


class LLMClient:
    """Adapter LLM: Gemini (chính) + Groq (dự phòng), retry + cache + rate limit.

    Attributes:
        providers: Danh sách provider theo thứ tự ưu tiên.
        cache: Cache SQLite.
        temperature: Nhiệt độ mặc định.
        max_tokens: Trần token mặc định.
        stats: Bộ đếm thống kê lời gọi.
    """

    def __init__(
        self,
        providers: list[ProviderConfig],
        *,
        cache_path: str | Path = "data/interim/llm_cache.sqlite",
        cache_enabled: bool = True,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> None:
        """Khởi tạo client.

        Args:
            providers: Danh sách provider theo thứ tự ưu tiên.
            cache_path: Đường dẫn cache SQLite.
            cache_enabled: Bật/tắt cache.
            temperature: Nhiệt độ mặc định.
            max_tokens: Trần token mặc định.
        """
        self.providers = providers
        self.cache = LLMCache(cache_path, enabled=cache_enabled)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._limiters: dict[str, RateLimiter] = {
            provider.name: RateLimiter(
                requests_per_minute=provider.rate_limit_per_min,
                requests_per_day=provider.requests_per_day,
            )
            for provider in providers
        }
        self.stats: dict[str, int] = {
            "requests": 0,
            "cache_hits": 0,
            "retries": 0,
            "fallbacks": 0,
            "errors": 0,
        }

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LLMClient":
        """Dựng client từ cấu hình `configs/llm.yaml`.

        Args:
            config: Dict cấu hình (khối ``llm``).

        Returns:
            `LLMClient`.
        """
        providers_config = config.get("providers") or {}
        primary = str(config.get("primary", "gemini"))
        fallback_order = list(config.get("fallback_order") or [])

        names = [primary] + [name for name in fallback_order if name != primary]
        providers: list[ProviderConfig] = []
        for name in names:
            spec = providers_config.get(name)
            if not spec:
                continue
            providers.append(
                ProviderConfig(
                    name=name,
                    model=str(spec.get("model", "")),
                    api_key_env=str(spec.get("api_key_env", "")),
                    rate_limit_per_min=int(spec.get("rate_limit_per_min", 15)),
                    requests_per_day=int(spec.get("requests_per_day", 500)),
                    timeout_s=int(spec.get("timeout_s", 60)),
                    max_retries=int(spec.get("max_retries", 3)),
                    backoff_base_s=float(spec.get("backoff_base_s", 2.0)),
                )
            )

        cache_config = config.get("cache") or {}
        load_env_file()
        return cls(
            providers,
            cache_path=str(
                cache_config.get("path", "data/interim/llm_cache.sqlite")
            ),
            cache_enabled=bool(cache_config.get("enabled", True)),
            temperature=float(config.get("temperature", 0.0)),
            max_tokens=int(config.get("max_tokens", 2048)),
        )

    # ------------------------------------------------------------------
    # Provider adapter
    # ------------------------------------------------------------------

    def _api_key(self, provider: ProviderConfig) -> str:
        """Đọc API key từ biến môi trường (không log giá trị).

        Args:
            provider: Cấu hình provider.

        Returns:
            API key (chuỗi rỗng nếu thiếu).
        """
        return os.environ.get(provider.api_key_env, "").strip()

    def _call_gemini(
        self,
        provider: ProviderConfig,
        api_key: str,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        """Gọi Gemini qua SDK `google-generativeai`.

        Args:
            provider: Cấu hình provider.
            api_key: API key.
            prompt: Nội dung prompt.
            system: System prompt (tuỳ chọn).
            temperature: Nhiệt độ.
            max_tokens: Trần token.
            json_mode: Ép JSON.

        Returns:
            Nội dung phản hồi.
        """
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            provider.model,
            system_instruction=system if system else None,
        )
        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(**generation_config),
        )
        return str(response.text or "")

    def _call_groq(
        self,
        provider: ProviderConfig,
        api_key: str,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        """Gọi Groq qua SDK `groq` (**bắt buộc**, raw HTTP bị Cloudflare 403).

        Args:
            provider: Cấu hình provider.
            api_key: API key.
            prompt: Nội dung prompt.
            system: System prompt (tuỳ chọn).
            temperature: Nhiệt độ.
            max_tokens: Trần token.
            json_mode: Ép JSON.

        Returns:
            Nội dung phản hồi.
        """
        from groq import Groq

        client = Groq(api_key=api_key, timeout=provider.timeout_s)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        completion = client.chat.completions.create(
            model=provider.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"} if json_mode else None,
        )
        choice = completion.choices[0]
        # `gpt-oss-20b` phát sinh reasoning token riêng → đọc `content`.
        return str(getattr(choice.message, "content", "") or "")

    def _call_provider(
        self,
        provider: ProviderConfig,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> str:
        """Gọi một provider với retry + fallback.

        Args:
            provider: Cấu hình provider.
            prompt: Nội dung prompt.
            system: System prompt (tuỳ chọn).
            temperature: Nhiệt độ.
            max_tokens: Trần token.
            json_mode: Ép JSON.

        Returns:
            Nội dung phản hồi.

        Raises:
            LLMError: Nếu hết retry hoặc thiếu API key.
        """
        api_key = self._api_key(provider)
        if not api_key:
            raise LLMError(
                f"Thiếu API key cho provider '{provider.name}' "
                f"(biến môi trường {provider.api_key_env} chưa được đặt)"
            )

        last_error: BaseException | None = None
        for attempt in range(provider.max_retries + 1):
            limiter = self._limiters.get(provider.name)
            if limiter is not None:
                limiter.acquire()
            try:
                if provider.name == "gemini":
                    return self._call_gemini(
                        provider, api_key, prompt, system, temperature,
                        max_tokens, json_mode,
                    )
                if provider.name == "groq":
                    return self._call_groq(
                        provider, api_key, prompt, system, temperature,
                        max_tokens, json_mode,
                    )
                raise LLMError(f"Provider chưa được hỗ trợ: {provider.name!r}")
            except LLMError:
                raise
            except Exception as error:  # noqa: BLE001 - bọc lỗi SDK bất kỳ
                last_error = error
                if attempt >= provider.max_retries or not is_retryable(error):
                    break
                self.stats["retries"] += 1
                delay = provider.backoff_base_s * (2**attempt)
                logger.warning(
                    "Provider %s lỗi (%s: %s) — retry %d/%d sau %.1fs",
                    provider.name,
                    type(error).__name__,
                    _error_status(error) or "n/a",
                    attempt + 1,
                    provider.max_retries,
                    delay,
                )
                time.sleep(delay)

        raise LLMError(
            f"Provider '{provider.name}' thất bại sau "
            f"{provider.max_retries} lần retry: {type(last_error).__name__}: {last_error}"
        )

    # ------------------------------------------------------------------
    # Interface chính
    # ------------------------------------------------------------------

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        """Gọi LLM và trả về nội dung phản hồi.

        Thứ tự xử lý:
        1. Kiểm tra cache (idempotent — chạy lại **không** gọi API).
        2. Gọi provider chính; lỗi retryable → retry; lỗi hết retry →
           **fallback** sang provider dự phòng.
        3. Ghi kết quả vào cache.

        Args:
            prompt: Nội dung prompt.
            system: System prompt (tuỳ chọn).
            temperature: Nhiệt độ lấy mẫu.
            max_tokens: Trần số token đầu ra.
            json_mode: Ép trả về JSON.

        Returns:
            Nội dung phản hồi (chuỗi rỗng nếu provider trả rỗng).

        Raises:
            LLMError: Nếu mọi provider đều thất bại.
        """
        if not self.providers:
            raise LLMError("Không có provider LLM nào được cấu hình")

        primary = self.providers[0]
        cache_key = make_cache_key(
            primary.model,
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
        )
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            logger.info("Cache hit (%s)", primary.model)
            return cached

        errors: list[str] = []
        for index, provider in enumerate(self.providers):
            if index > 0:
                self.stats["fallbacks"] += 1
                logger.warning(
                    "Chuyển fallback sang provider '%s' (model %s)",
                    provider.name,
                    provider.model,
                )
            try:
                response = self._call_provider(
                    provider, prompt, system, temperature, max_tokens, json_mode
                )
            except LLMError as error:
                errors.append(f"{provider.name}: {error}")
                continue
            self.stats["requests"] += 1
            self.cache.set(cache_key, provider.model, response)
            return response

        self.stats["errors"] += 1
        raise LLMError("Mọi provider LLM đều thất bại — " + " | ".join(errors))

    def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> Any | None:
        """Gọi LLM ở chế độ JSON và parse kết quả.

        Parse lỗi → **1 lần retry** với yêu cầu "trả về JSON hợp lệ"; còn lỗi
        → trả ``None`` và log (theo `.cursor/rules/llm-usage.mdc`).

        Args:
            prompt: Nội dung prompt.
            system: System prompt (tuỳ chọn).
            temperature: Nhiệt độ lấy mẫu.
            max_tokens: Trần số token đầu ra.

        Returns:
            Object đã parse (dict/list) hoặc ``None`` nếu parse thất bại.
        """
        raw = self.complete(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        parsed = parse_json_payload(raw)
        if parsed is not None:
            return parsed
        logger.warning("JSON không hợp lệ — retry 1 lần yêu cầu JSON thuần")
        retry_prompt = (
            f"{prompt}\n\n"
            "YÊU CẦU: Trả về **duy nhất** JSON hợp lệ, không markdown, "
            "không giải thích."
        )
        raw = self.complete(
            retry_prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        parsed = parse_json_payload(raw)
        if parsed is None:
            logger.error("Không parse được JSON sau 2 lần thử")
        return parsed


def parse_json_payload(raw: str) -> Any | None:
    """Parse một chuỗi JSON, chịu được markdown fence.

    Args:
        raw: Chuỗi thô trả về từ LLM.

    Returns:
        Object đã parse, hoặc ``None`` nếu không hợp lệ.
    """
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Thử tìm object/array đầu tiên trong chuỗi.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


__all__ = [
    "LLMCache",
    "LLMClient",
    "LLMError",
    "ProviderConfig",
    "RateLimiter",
    "is_retryable",
    "make_cache_key",
    "parse_json_payload",
]

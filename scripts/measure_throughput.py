#!/usr/bin/env python
"""Đo thông lượng thực tế (requests/phút) theo provider + model + kích thước context.

Gửi burst request với context kích thước thực tế của RAG, đếm số request thành
công trong 60 giây ⇒ suy ra RPM khả dụng (là giới hạn thực tế để lên kế hoạch).

Dùng:
    ./.venv/bin/python scripts/measure_throughput.py --provider gemini --models gemini-3.5-flash-lite --ctx-tokens 3000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

FILLER = "Trần Hưng Đạo là tướng quân nhà Trần, chỉ huy quân đội Đại Việt đánh giặc Ngô Mông. "


def load_env() -> None:
    """Nạp biến môi trường từ `.env` (không ghi đè biến đã có)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _context(ctx_tokens: int) -> str:
    """Dựng context khoảng `ctx_tokens` token."""
    return FILLER * max(1, ctx_tokens // 20)


def call_gemini(model: str, api_key: str, index: int, ctx_tokens: int) -> tuple[int, str]:
    """Gọi Gemini.

    Args:
        model: Tên model.
        api_key: API key.
        index: Số thứ tự request.
        ctx_tokens: Kích thước context.

    Returns:
        Tuple `(mã HTTP, thông báo lỗi)`.
    """
    body = json.dumps(
        {
            "contents": [
                {
                    "parts": [
                        {
                            "text": f"[{index}] {_context(ctx_tokens)}\n\n"
                            "Trả lời ngắn gọn kèm trích dẫn [1]: Trần Hưng Đạo là ai?"
                        }
                    ]
                }
            ],
            "generationConfig": {"maxOutputTokens": 256},
        }
    ).encode()
    request = urllib.request.Request(
        GEMINI_URL.format(model=model),
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "curl/8.5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
        return 200, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(raw)["error"]["message"]
        except Exception:  # noqa: BLE001
            message = raw[:300]
        return exc.code, re.sub(r"\s+", " ", message)[:200]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def call_groq(model: str, api_key: str, index: int, ctx_tokens: int) -> tuple[int, str]:
    """Gọi Groq.

    Args:
        model: Tên model.
        api_key: API key.
        index: Số thứ tự request.
        ctx_tokens: Kích thước context.

    Returns:
        Tuple `(mã HTTP, thông báo lỗi)`.
    """
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": f"[{index}] {_context(ctx_tokens)}\n\n"
                    "Trả lời ngắn gọn kèm trích dẫn [1]: Trần Hưng Đạo là ai?",
                }
            ],
            "max_tokens": 256,
        }
    ).encode()
    request = urllib.request.Request(
        GROQ_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
        return 200, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(raw)["error"]["message"]
        except Exception:  # noqa: BLE001
            message = raw[:300]
        return exc.code, re.sub(r"\s+", " ", message)[:200]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["gemini", "groq"], default="gemini")
    parser.add_argument("--models", required=True)
    parser.add_argument("--ctx-tokens", type=int, default=3000)
    parser.add_argument("--threads", type=int, default=6)
    parser.add_argument("--duration", type=float, default=60.0)
    args = parser.parse_args()

    load_env()
    if args.provider == "gemini":
        api_key = os.environ.get("GEMINI_API_KEY", "")
    else:
        api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("Thiếu API key")
        return 1

    call = call_gemini if args.provider == "gemini" else call_groq

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        ok = 0
        errors: dict[str, int] = {}
        lock = threading.Lock()
        stop = threading.Event()
        started = time.time()

        def worker() -> None:
            nonlocal ok
            index = 0
            while not stop.is_set():
                index += 1
                code, message = call(model, api_key, index, args.ctx_tokens)
                with lock:
                    if code == 200:
                        ok += 1
                    else:
                        key = f"{code}: {message}"
                        errors[key] = errors.get(key, 0) + 1
                time.sleep(0.05)

        threads = [threading.Thread(target=worker) for _ in range(args.threads)]
        for thread in threads:
            thread.start()
        time.sleep(args.duration)
        stop.set()
        for thread in threads:
            thread.join(timeout=30)
        elapsed = time.time() - started
        print(
            f"=== {args.provider}/{model} ctx≈{args.ctx_tokens}: "
            f"OK {ok} request / {elapsed:.0f}s ⇒ {ok / elapsed * 60:.1f} req/phút"
        )
        for message, count in errors.items():
            print(f"    - ({count}×) {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

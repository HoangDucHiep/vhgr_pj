#!/usr/bin/env python
"""Đo RPD thực tế của Gemini theo model bằng burst đồng thời.

Gửi N request *nhỏ* (ít token) song song với nhiều thread, dừng khi gặp 429
⇒ số request thành công chính là RPD thực tế của model đó.

Dùng:
    ./.venv/bin/python scripts/probe_gemini_rpd.py --burst 300 --threads 12 --models gemini-3.5-flash-lite
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
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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


def call(model: str, api_key: str, index: int) -> tuple[int, str]:
    """Gọi 1 request `generateContent` (nhỏ).

    Args:
        model: Tên model.
        api_key: Gemini API key.
        index: Số thứ tự request.

    Returns:
        Tuple `(mã HTTP, thông báo lỗi)`.
    """
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": f"{index}x3=? (chỉ số)"}]}],
            "generationConfig": {"maxOutputTokens": 8},
        }
    ).encode()
    request = urllib.request.Request(
        URL.format(model=model),
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "curl/8.5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response.read()
        return 200, ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(raw)["error"]["message"]
        except Exception:  # noqa: BLE001
            message = raw[:300]
        return exc.code, re.sub(r"\s+", " ", message)[:240]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default="gemini-3.5-flash-lite,gemini-3.5-flash,gemini-3.6-flash",
    )
    parser.add_argument("--burst", type=int, default=200)
    parser.add_argument("--threads", type=int, default=8)
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Thiếu GEMINI_API_KEY")
        return 1

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        ok = 0
        errors: dict[str, int] = {}
        lock = threading.Lock()
        counter = {"i": 0}

        def worker() -> None:
            nonlocal ok
            while True:
                with lock:
                    if counter["i"] >= args.burst:
                        return
                    index = counter["i"]
                    counter["i"] += 1
                code, message = call(model, api_key, index)
                with lock:
                    if code == 200:
                        ok += 1
                    else:
                        errors[f"{code}: {message}"] = errors.get(f"{code}: {message}", 0) + 1

        started = time.time()
        threads = [threading.Thread(target=worker) for _ in range(args.threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        elapsed = time.time() - started
        print(f"=== {model}: OK {ok} / {args.burst} trong {elapsed:.1f}s")
        for message, count in errors.items():
            print(f"    - ({count}×) {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

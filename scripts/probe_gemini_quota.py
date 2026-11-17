#!/usr/bin/env python
"""Dò quota Gemini (RPM/RPD) cho từng model.

Gửi N request rẻ tới `generateContent`, gom lỗi 429 để biết giới hạn thực tế.

Dùng:
    ./.venv/bin/python scripts/probe_gemini_quota.py --models gemini-3.5-flash-lite,gemini-3.5-flash --requests 40
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DEFAULT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


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


def call(model: str, api_key: str, text: str) -> tuple[bool, str, float]:
    """Gọi 1 request `generateContent`.

    Args:
        model: Tên model.
        api_key: Gemini API key.
        text: Nội dung prompt.

    Returns:
        Tuple `(thành công, thông báo lỗi, thời gian giây)`.
    """
    url = BASE.format(model=model)
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"maxOutputTokens": 64},
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "curl/8.5.0",
        },
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            response.read()
        return True, "", time.time() - started
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(raw)
            message = detail["error"]["message"]
        except Exception:  # noqa: BLE001
            message = raw[:400]
        # Rút gọn thông báo quota.
        message = re.sub(r"\s+", " ", message)
        return False, f"{exc.code}: {message[:300]}", time.time() - started
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}", time.time() - started


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.0)
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Thiếu GEMINI_API_KEY")
        return 1

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        ok = 0
        errors: dict[str, int] = {}
        started = time.time()
        for index in range(args.requests):
            success, message, _ = call(
                model, api_key, f"Trả lời ngắn: {index}+{index} bằng một số."
            )
            if success:
                ok += 1
            else:
                errors[message] = errors.get(message, 0) + 1
            if args.interval:
                time.sleep(args.interval)
        elapsed = time.time() - started
        print(f"=== {model}: OK {ok}/{args.requests} trong {elapsed:.1f}s")
        for message, count in errors.items():
            print(f"    - ({count}×) {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

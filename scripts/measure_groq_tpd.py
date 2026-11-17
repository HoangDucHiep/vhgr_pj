#!/usr/bin/env python
"""Đo hạn mức TPD (token/ngày) thực tế của từng model Groq.

Gửi request liên tục (mô phỏng prompt RAG ~3.000 token) tới 1 model cho tới khi
gặp 429 `tokens per day`, đọc `Used X / Limit Y` trong thông báo lỗi ⇒ biết
chính xác TPD còn lại và đã dùng.

Dùng:
    ./.venv/bin/python scripts/measure_groq_tpd.py --models openai/gpt-oss-120b,qwen/qwen3.8-27b --max-calls 80
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
URL = "https://api.groq.com/openai/v1/chat/completions"

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


def call(model: str, api_key: str, index: int, ctx_tokens: int) -> tuple[int, str, int]:
    """Gọi 1 request Groq.

    Args:
        model: Tên model.
        api_key: Groq API key.
        index: Số thứ tự request.
        ctx_tokens: Kích thước context.

    Returns:
        Tuple `(mã HTTP, thông báo, số token đã dùng)`.
    """
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": f"[{index}] " + FILLER * max(1, ctx_tokens // 20),
                }
            ],
            "max_tokens": 32,
        }
    ).encode()
    request = urllib.request.Request(
        URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "curl/8.5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read())
        usage = payload.get("usage") or {}
        return 200, "", int(usage.get("total_tokens") or 0)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(raw)["error"]["message"]
        except Exception:  # noqa: BLE001
            message = raw[:300]
        return exc.code, re.sub(r"\s+", " ", message)[:300], 0
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}", 0


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", required=True)
    parser.add_argument("--max-calls", type=int, default=60)
    parser.add_argument("--ctx-tokens", type=int, default=3000)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("Thiếu GROQ_API_KEY")
        return 1

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        used = 0
        calls = 0
        error = ""
        for index in range(args.max_calls):
            code, message, tokens = call(model, api_key, index, args.ctx_tokens)
            if code == 200:
                used += tokens
                calls += 1
                continue
            error = f"{code}: {message}"
            break
            # tạm dừng nhẹ giữa các call để không chạm TPM
            time.sleep(args.delay)
        match = re.search(r"Used (\d+), Requested (\d+)", error)
        limit = re.search(r"TPD\): Limit (\d+)", error)
        print(f"=== {model}")
        print(f"    call thành công: {calls} · token đã dùng: {used}")
        if limit:
            print(f"    TPD limit: {limit.group(1)}")
        if match:
            print(f"    Used {match.group(1)} / Requested {match.group(2)}")
        print(f"    lỗi: {error[:250]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

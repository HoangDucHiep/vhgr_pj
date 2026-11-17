#!/usr/bin/env python
"""Đo hạn mức thực tế của 1 model Groq trong thời gian dài (tôn trọng TPM).

Chạy ở tốc độ `--rpm` (mặc định 2 req/phút ⇒ chắc chắn dưới TPM 8000 với
context ~3.000 token) cho tới khi gặp 429 `tokens per day` ⇒ biết TPD thực tế.

Dùng:
    ./.venv/bin/python scripts/measure_groq_tpd_long.py --model openai/gpt-oss-120b --minutes 25 --rpm 2
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
        Tuple `(mã HTTP, thông báo, token đã dùng)`.
    """
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "user", "content": f"[{index}] " + FILLER * max(1, ctx_tokens // 20)}
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
        return exc.code, re.sub(r"\s+", " ", message)[:320], 0
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}", 0


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--minutes", type=float, default=20.0)
    parser.add_argument("--rpm", type=float, default=2.0)
    parser.add_argument("--ctx-tokens", type=int, default=3000)
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("Thiếu GROQ_API_KEY")
        return 1

    interval = 60.0 / max(0.1, args.rpm)
    total = int(args.minutes * args.rpm)
    used = 0
    calls = 0
    started = time.time()
    for index in range(total):
        target = started + index * interval
        delay = target - time.time()
        if delay > 0:
            time.sleep(delay)
        code, message, tokens = call(args.model, api_key, index, args.ctx_tokens)
        if code != 200:
            limit = re.search(r"TPD\): Limit (\d+)", message)
            used_match = re.search(r"Used (\d+)", message)
            kind = "TPD" if limit else ("TPM" if "per minute" in message else "khác")
            print(
                f"DỪNG tại call #{calls + 1} — loại giới hạn: {kind} · "
                f"limit={limit.group(1) if limit else '?'} · "
                f"used={used_match.group(1) if used_match else '?'} · "
                f"token tôi đã dùng={used}"
            )
            print(f"  {message[:300]}")
            return 0
        used += tokens
        calls += 1
        print(
            f"[{index + 1}/{total}] OK · token tích luỹ={used} · "
            f"tổng={time.time() - started:.0f}s",
            flush=True,
        )
    print(f"KHÔNG gặp giới hạn sau {calls} call · token={used}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

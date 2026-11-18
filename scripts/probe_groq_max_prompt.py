#!/usr/bin/env python
"""Đo **trần prompt** thực tế của Groq (TPM) cho từng model.

Ý tưởng: prompt judge gộp 3 arm. Groq trả `413 Request too large` khi prompt
vượt trần token/phút (ITPM). ⇒ Cần biết trần **thực tế** (header
`x-ratelimit-limit-tokens` chỉ là trần *phát sinh*, không phải trần prompt).

Cách dùng:
    python scripts/probe_groq_max_prompt.py --model openai/gpt-oss-20b
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, "/app")

import httpx  # noqa: E402

KEY = os.environ["GROQ_API_KEY"]
URL = "https://api.groq.com/openai/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}


def try_prompt(model: str, chars: int) -> int:
    """Gửi prompt dài `chars`; trả về mã HTTP."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "Lịch sử Việt Nam. " * 200 + "x" * chars}],
        "max_tokens": 5,
    }
    resp = httpx.post(URL, headers=HEADERS, json=body, timeout=120)
    return resp.status_code


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="openai/gpt-oss-20b")
    args = parser.parse_args()

    for chars in (2000, 6000, 10000, 14000, 18000, 24000, 30000, 40000):
        code = try_prompt(args.model, chars)
        print(f"  chars≈{chars:6d} (token≈{chars // 3:6d}) -> HTTP {code}", flush=True)
        if code == 413:
            print(f"  ⇒ TRẦN THỰC TẾ của {args.model} ≈ {chars // 3} token")
            break
        time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

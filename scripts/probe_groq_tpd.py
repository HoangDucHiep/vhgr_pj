#!/usr/bin/env python
"""Đo quota **TPD** Groq còn lại cho từng model (bằng request cỡ thật)."""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/app")

import httpx  # noqa: E402

KEY = os.environ["GROQ_API_KEY"]
URL = "https://api.groq.com/openai/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

MODELS = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
)

#: Cỡ prompt thực tế (~2.500 token) để đúng mức tiêu token/ngày.
PROMPT = ("Lịch sử Việt Nam. " * 600) + f"\n\nCâu hỏi #{time.time()}: kể lại."

for model in MODELS:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 500,
    }
    resp = httpx.post(URL, headers=HEADERS, json=body, timeout=120)
    print(f"--- {model} -> HTTP {resp.status_code}")
    if resp.status_code != 200:
        text = resp.text
        for part in ("Limit", "Used", "try again"):
            idx = text.find(part)
            if idx >= 0:
                print("   ", text[idx:idx + 120])
    else:
        print("    OK — còn quota")
    for key, value in sorted(resp.headers.items()):
        if "limit" in key.lower():
            print(f"    {key} = {value}")

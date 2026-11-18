#!/usr/bin/env python
"""Đo quota Groq còn lại (TPM/TPD) cho từng model bằng cách gọi thử."""

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

for model in MODELS:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": f"ping {time.time()}"}],
        "max_tokens": 5,
    }
    resp = httpx.post(URL, headers=HEADERS, json=body, timeout=90)
    print(f"--- {model} -> HTTP {resp.status_code}")
    if resp.status_code != 200:
        print("   ", resp.text[:400])
    for key, value in sorted(resp.headers.items()):
        if "limit" in key.lower():
            print(f"    {key} = {value}")

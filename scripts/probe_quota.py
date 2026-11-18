#!/usr/bin/env python
"""Đo quota Gemini còn lại (dùng prompt KHÔNG có trong cache ⇒ gọi thật)."""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/app")

from google import generativeai  # noqa: E402

KEY = os.environ["GEMINI_API_KEY"]
generativeai.configure(api_key=KEY)

CANDIDATES = [
    "gemini-3.1-flash-lite",
    "gemini-4-hydrogen",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3-flash-preview",
    "gemini-3.6-flash",
]

for name in CANDIDATES:
    # Prompt có dấu thời gian ⇒ **không** trùng cache ⇒ gọi thật.
    prompt = f"ping {time.time()}"
    try:
        model = generativeai.GenerativeModel(name)
        model.generate_content(prompt, generation_config={"max_output_tokens": 5})
        print(f"  {name:32s} OK", flush=True)
    except Exception as error:  # noqa: BLE001
        msg = str(error)[:70].replace("\n", " ")
        print(f"  {name:32s} FAIL {msg}", flush=True)

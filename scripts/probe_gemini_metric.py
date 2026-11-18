#!/usr/bin/env python
"""In **metric quota** của lỗi 429 Gemini (RPD hay RPM?).

Gemini trả về `quota_metric` trong body lỗi:
- `..._free_tier_requests` ⇒ hạn mức **request/ngày** (RPD).
- `..._free_tier_requests_per_minute` ⇒ hạn mức **request/phút** (RPM).
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, "/app")

from google import generativeai  # noqa: E402

KEY = os.environ["GEMINI_API_KEY"]
generativeai.configure(api_key=KEY)

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.5-flash-lite"

for i in range(6):
    try:
        model = generativeai.GenerativeModel(MODEL)
        model.generate_content(
            f"ping {time.time()}", generation_config={"max_output_tokens": 5}
        )
        print(f"[{i}] OK", flush=True)
    except Exception as error:  # noqa: BLE001
        text = str(error)
        metric = ""
        for line in text.splitlines():
            if "quota_metric" in line or "retry in" in line:
                metric += line.strip() + " | "
        print(f"[{i}] FAIL {metric or text[:150]}", flush=True)
    time.sleep(6)

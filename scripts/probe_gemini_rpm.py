#!/usr/bin/env python
"""Phân biệt 429 của Gemini là **RPM** (mỗi phút) hay **RPD** (mỗi ngày).

Cách làm: gọi liên tiếp 1 lần, chờ 65 giây, gọi lại 1 lần.
- Nếu lần 2 **thành công** ⇒ 429 là **RPM** ⇒ chỉ cần giãn tần suất.
- Nếu lần 2 vẫn 429 ⇒ 429 là **RPD** ⇒ hết quota cả ngày.
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


def probe(label: str) -> bool:
    """Gọi 1 request nhỏ; trả về True nếu thành công."""
    try:
        model = generativeai.GenerativeModel(MODEL)
        model.generate_content(
            f"ping {time.time()}", generation_config={"max_output_tokens": 5}
        )
        print(f"  [{label}] {MODEL}: OK", flush=True)
        return True
    except Exception as error:  # noqa: BLE001
        msg = str(error)[:100].replace("\n", " ")
        print(f"  [{label}] {MODEL}: FAIL {msg}", flush=True)
        return False


probe("t=0s")
for wait in (20, 40, 65, 90):
    print(f"  ... chờ {wait}s", flush=True)
    time.sleep(wait)
    probe(f"t≈{wait}s")

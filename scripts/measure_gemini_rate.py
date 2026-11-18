#!/usr/bin/env python
"""Đo **thực tế** quota Gemini còn lại: gọi liên tiếp cho tới khi 429.

Ý tưởng: hạn mức Gemini free tier là **request/phút** (RPM) ⇒ nếu gọi quá
tần suất thì 429, nhưng quota **hồi sau ~1 phút**. ⇒ Đo xem trong 1 phút
mình gọi được **bao nhiêu** request ⇒ biết tần suất an toàn để chạy eval
mà không 429.

Cách dùng:
    python scripts/measure_gemini_rate.py --model gemini-3.5-flash-lite --seconds 90
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, "/app")

from google import generativeai  # noqa: E402

KEY = os.environ["GEMINI_API_KEY"]
generativeai.configure(api_key=KEY)


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--seconds", type=float, default=90.0)
    parser.add_argument("--gap", type=float, default=0.0)
    args = parser.parse_args()

    deadline = time.time() + args.seconds
    ok = 0
    fail = 0
    first_fail_at = None
    model = generativeai.GenerativeModel(args.model)
    while time.time() < deadline:
        try:
            model.generate_content(
                f"ping {time.time()}", generation_config={"max_output_tokens": 5}
            )
            ok += 1
        except Exception as error:  # noqa: BLE001
            fail += 1
            if first_fail_at is None:
                first_fail_at = time.time()
            print(f"  FAIL: {str(error)[:110]}", flush=True)
        if args.gap:
            time.sleep(args.gap)
    print(f"model={args.model} ok={ok} fail={fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

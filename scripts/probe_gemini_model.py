#!/usr/bin/env python
"""Đo RPD/RPM thực tế của một model Gemini và ghi rõ metric bị vượt.

Gửi burst request, phân loại lỗi 429 theo `quotaId` trong payload lỗi:
- `GenerateRequestsPerMinutePerProjectPerModel-FreeTier` ⇒ giới hạn RPM
- `GenerateRequestsPerDayPerProjectPerModel-FreeTier` ⇒ giới hạn RPD

Dùng:
    ./.venv/bin/python scripts/probe_gemini_model.py --model gemini-3.5-flash --burst 40
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


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


def call(model: str, api_key: str, index: int) -> tuple[int, str, str]:
    """Gọi 1 request `generateContent`.

    Args:
        model: Tên model.
        api_key: Gemini API key.
        index: Số thứ tự request.

    Returns:
        Tuple `(mã HTTP, quotaId, thông báo)`.
    """
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": f"{index}x3=?"}]}],
            "generationConfig": {"maxOutputTokens": 8},
        }
    ).encode()
    request = urllib.request.Request(
        URL.format(model=model),
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "curl/8.5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response.read()
        return 200, "", ""
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        quota_id = ""
        message = raw[:200]
        try:
            payload = json.loads(raw)
            message = re.sub(r"\s+", " ", payload["error"]["message"])[:220]
            for detail in payload["error"].get("details", []) or []:
                for violation in detail.get("violations", []) or []:
                    quota_id = violation.get("quotaId", quota_id)
        except Exception:  # noqa: BLE001
            pass
        return exc.code, quota_id, message
    except Exception as exc:  # noqa: BLE001
        return 0, "", f"{type(exc).__name__}: {exc}"


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--burst", type=int, default=40)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--delay", type=float, default=0.0)
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Thiếu GEMINI_API_KEY")
        return 1

    ok = 0
    codes: Counter[str] = Counter()
    quota_ids: Counter[str] = Counter()
    messages: dict[str, str] = {}
    lock = threading.Lock()
    counter = {"i": 0}
    started = time.time()

    def worker() -> None:
        nonlocal ok
        while True:
            with lock:
                if counter["i"] >= args.burst:
                    return
                index = counter["i"]
                counter["i"] += 1
            code, quota_id, message = call(args.model, api_key, index)
            with lock:
                if code == 200:
                    ok += 1
                else:
                    codes[str(code)] += 1
                    if quota_id:
                        quota_ids[quota_id] += 1
                    messages.setdefault(f"{code}|{quota_id}", message)
            if args.delay:
                time.sleep(args.delay)

    threads = [threading.Thread(target=worker) for _ in range(args.threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    elapsed = time.time() - started
    print(f"=== {args.model}: OK {ok}/{args.burst} trong {elapsed:.1f}s")
    print(f"    mã lỗi: {dict(codes)}")
    for quota_id, count in quota_ids.items():
        print(f"    quota bị vượt ({count}×): {quota_id}")
    for key, message in messages.items():
        print(f"    - {key}: {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

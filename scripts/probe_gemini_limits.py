#!/usr/bin/env python
"""Liệt kê hạn mức Gemini thực tế (RPM/RPD) của từng model khả dụng.

Gọi 1 request/model; nếu gặp 429, đọc `quotaId` + `quotaValue` trong payload lỗi
để biết chính xác giới hạn đang bị vượt (RPM hay RPD) và giá trị hạn mức.

Dùng:
    ./.venv/bin/python scripts/probe_gemini_limits.py --models gemini-3.5-flash-lite,gemini-3.5-flash
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DEFAULT_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
]


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


def probe(model: str, api_key: str) -> dict[str, object]:
    """Gọi 1 request và tổng hợp thông tin hạn mức từ lỗi (nếu có).

    Args:
        model: Tên model.
        api_key: Gemini API key.

    Returns:
        Dict mô tả kết quả.
    """
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": "Trả lời: 1+1="}]}],
            "generationConfig": {"maxOutputTokens": 16},
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
    result: dict[str, object] = {"model": model}
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response.read()
        result["status"] = "OK"
        return result
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except Exception:  # noqa: BLE001
            result["message"] = raw[:200]
            return result
        error = payload.get("error") or {}
        result["message"] = re.sub(r"\s+", " ", str(error.get("message", "")))[:200]
        violations: list[dict[str, object]] = []
        for detail in error.get("details", []) or []:
            violations.extend(detail.get("violations", []) or [])
        result["violations"] = violations
        return result
    except Exception as exc:  # noqa: BLE001
        result["status"] = f"{type(exc).__name__}"
        result["message"] = str(exc)[:200]
        return result


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Thiếu GEMINI_API_KEY")
        return 1

    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        result = probe(model, api_key)
        status = result.get("status")
        print(f"=== {model}: {status}")
        violations = result.get("violations") or []
        if violations:
            for violation in violations:
                print(
                    f"    quotaId={violation.get('quotaId')} "
                    f"limit={violation.get('quotaValue')} "
                    f"({violation.get('description', '')[:110]})"
                )
        else:
            print(f"    {str(result.get('message', ''))[:190]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

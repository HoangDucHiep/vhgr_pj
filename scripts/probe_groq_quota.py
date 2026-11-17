#!/usr/bin/env python
"""Dò quota Groq theo model với kích thước context thực tế (mô phỏng RAG).

Gửi N request kích thước ~`--ctx-tokens` token tới từng model, gom lỗi 429
để biết giới hạn TPD/TPM/ITPM của riêng model đó.

Dùng:
    ./.venv/bin/python scripts/probe_groq_quota.py --requests 8 --ctx-tokens 2500
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
API = "https://api.groq.com/openai/v1/chat/completions"

MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "allam-2-7b",
]

FILLER = "Trần Hưng Đạo là tướng quân nhà Trần, chỉ huy quân đội đánh giặc Ngô Mông. "


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


def make_body(model: str, ctx_tokens: int) -> bytes:
    """Dựng body request kích thước xấp xỉ `ctx_tokens` token.

    Args:
        model: Tên model.
        ctx_tokens: Số token context mong muốn.

    Returns:
        Body bytes.
    """
    repeats = max(1, ctx_tokens // 20)
    content = FILLER * repeats
    return json.dumps(
        {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": content
                    + "\n\nDựa trên ngữ cảnh trên, trả lời ngắn gọn: Trần Hưng Đạo là ai?",
                }
            ],
            "max_tokens": 200,
        }
    ).encode()


def probe(
    model: str,
    api_key: str,
    repeats: int,
    ctx_tokens: int,
) -> dict[str, object]:
    """Gửi nhiều request tới 1 model, tổng hợp lỗi quota gặp phải.

    Args:
        model: Tên model.
        api_key: Groq API key.
        repeats: Số lần gửi.
        ctx_tokens: Kích thước context mỗi request.

    Returns:
        Dict kết quả.
    """
    body = make_body(model, ctx_tokens)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "curl/8.5.0",
    }
    ok = 0
    errors: list[str] = []
    for _ in range(repeats):
        request = urllib.request.Request(API, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read())
                usage = payload.get("usage") or {}
                ok += 1
                print(
                    f"    ok prompt_tokens={usage.get('prompt_tokens')} "
                    f"total={usage.get('total_tokens')}"
                )
        except urllib.error.HTTPError as exc:
            errors.append(exc.read().decode("utf-8", "replace")[:500])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{type(exc).__name__}: {exc}")
    return {"model": model, "ok": ok, "errors": errors}


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--ctx-tokens", type=int, default=2500)
    parser.add_argument("--models", default=",".join(MODELS))
    args = parser.parse_args()

    load_env()
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("Thiếu GROQ_API_KEY")
        return 1
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"=== {model} (ctx≈{args.ctx_tokens} tok × {args.requests} lần)")
        result = probe(model, api_key, args.requests, args.ctx_tokens)
        print(f"    → OK {result['ok']} lần")
        seen: set[str] = set()
        for message in result["errors"]:  # type: ignore[union-attr]
            key = message[:150]
            if key in seen:
                continue
            seen.add(key)
            print(f"    - {message[:420]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

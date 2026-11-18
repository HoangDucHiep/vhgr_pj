#!/usr/bin/env python
"""Kiểm tra kỹ model Gemini mới: có suy nghĩ (thinking) không, output có bị cắt không."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app")

from google import generativeai  # noqa: E402

KEY = os.environ["GEMINI_API_KEY"]
generativeai.configure(api_key=KEY)

MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-4-hydrogen"
PROMPT = (
    "Trả lời bằng tiếng Việt, ưu tiên một đoạn văn liền mạch (3–6 câu).\n\n"
    "CONTEXT:\n"
    "[1] Quý Kiệt hoàn dân Thì Trung phát phối là phong trào chống lũy thuế "
    "của người dân Nam Định trong thời kỳ Minh Mạng, nổi ra vào khoảng năm 1822.\n"
    "[2] Thì Trung là một trong những nông dân nổi tiếng ở làng Yên Định.\n\n"
    "CÂU HỎI: Kể lại diễn biến Quý Kiệt hoàn dân Thì Trung phát phối."
)

for max_tokens in (2048, 4096):
    model = generativeai.GenerativeModel(MODEL)
    resp = model.generate_content(
        PROMPT,
        generation_config=generativeai.types.GenerationConfig(
            temperature=0.2, max_output_tokens=max_tokens
        ),
    )
    text = resp.text or ""
    usage = getattr(resp, "usage_metadata", None)
    print(f"--- {MODEL} max_tokens={max_tokens}")
    print("   usage:", usage)
    print("   text len:", len(text))
    print("   ", text[:600].replace("\n", " "))
    print()

#!/usr/bin/env python
"""Kiểm tra model thinking: `max_output_tokens` tối thiểu để có câu trả lời."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app")

import google.generativeai as genai  # noqa: E402

KEY = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=KEY)

MODEL = "gemini-4-hydrogen"
PROMPT = (
    "Trả lời bằng tiếng Việt, ưu tiên một đoạn văn liền mạch (3–6 câu).\n\n"
    "CONTEXT:\n[1] Quý Kiệt hoàn dân Thì Trung phát phối là phong trào chống "
    "lũy thuế của người dân Nam Định trong thời kỳ Minh Mạng, nổi ra khoảng "
    "năm 1822.\n[2] Thì Trung là nông dân nổi tiếng ở làng Yên Định.\n\n"
    "CÂU HỎI: Kể lại diễn biến Quý Kiệt hoàn dân Thì Trung phát phối."
)

for max_out in (900, 2048, 4096):
    model = genai.GenerativeModel(MODEL)
    cfg = genai.types.GenerationConfig(temperature=0.2, max_output_tokens=max_out)
    try:
        resp = model.generate_content(PROMPT, generation_config=cfg)
        text = resp.text or ""
        usage = getattr(resp, "usage_metadata", None)
        cand = None
        try:
            cand = resp.candidates[0].finish_reason
        except Exception:  # noqa: BLE001
            pass
        print(f"max_out={max_out}: len={len(text)} finish={cand} usage={usage}")
    except Exception as error:  # noqa: BLE001
        print(f"max_out={max_out}: FAIL {str(error)[:180]}")

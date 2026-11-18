#!/usr/bin/env python
"""Kiểm tra model Gemini mới có chấm được prompt judge thật hay không."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/app")

from google import generativeai  # noqa: E402

from src.evaluation.evaluate_rag import JUDGE_PROMPT, compact_context  # noqa: E402

KEY = os.environ["GEMINI_API_KEY"]
generativeai.configure(api_key=KEY)

rows = [
    json.loads(line)
    for line in open("/app/data/eval/eval_d124_checkpoint.jsonl", encoding="utf-8")
]
row = rows[0]
cands = "\n\n".join(
    f"### PHƯƠNG ÁN {arm}\n"
    f"CONTEXT:\n{compact_context(str(row[arm]['arm'].get('context') or '')) or '(không có context)'}\n\n"
    f"CÂU TRẢ LỜI:\n{str(row[arm]['arm'].get('answer') or '')[:3000]}"
    for arm in ("A", "B", "B-")
)
prompt = JUDGE_PROMPT.format(
    question_type="tự sự",
    question=row["B"]["question"],
    expected_answer=str(row["B"].get("expected_answer") or "")[:2000],
    subject_hint="",
    candidates=cands,
)
print("prompt chars:", len(prompt), "~tokens:", len(prompt) // 3)

for name in ("gemini-3.6-flash", "gemini-4-hydrogen"):
    try:
        model = generativeai.GenerativeModel(name)
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0.0, "max_output_tokens": 800},
        )
        text = resp.text or ""
        print(f"--- {name}: OK, len={len(text)}")
        print("   ", text[:400].replace("\n", " "))
    except Exception as error:  # noqa: BLE001
        print(f"--- {name}: FAIL {str(error)[:200]}")

#!/usr/bin/env python
"""Thử các mô hình Groq với prompt judge thật (đo trần TPM/ITPM)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/app")

from groq import Groq  # noqa: E402

from src.evaluation.evaluate_rag import JUDGE_PROMPT, compact_context  # noqa: E402

rows = [json.loads(line) for line in open("/app/data/eval/eval_d124_checkpoint.jsonl", encoding="utf-8")]
row = rows[0]
cands = "\n\n".join(
    f"### PHƯƠNG ÁN {row[arm]['arm']}\n"
    f"CONTEXT:\n{compact_context(str(row[arm].get('context') or '')) or '(không có context)'}\n\n"
    f"CÂU TRẢ LỜI:\n{str(row[arm].get('answer') or '')[:3000]}"
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

client = Groq(api_key=os.environ["GROQ_API_KEY"])
for model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"):
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
        )
        print(model, "OK", len(resp.choices[0].message.content or ""))
    except Exception as error:  # noqa: BLE001
        print(model, "FAIL", str(error)[:260])

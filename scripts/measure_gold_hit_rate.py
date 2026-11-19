#!/usr/bin/env python
"""Đo **hit-rate gold section** trong top-k context (G19-2) — offline, **không tốn quota LLM**.

Vì sao cần script này?
---------------------
G19-2 yêu cầu: *"≥ 55/60 câu `narrative` có gold section trong top-8 context"*.
Đây là số đo **tầng truy xuất** — không cần gọi LLM ⇒ đo offline được.

Cách đo
--------
1. Nạp bộ câu hỏi (`qa_rag_250_v2.jsonl`) — lấy `evidence_doc_id` (bài chứa đáp án).
2. Với mỗi câu, gọi `Retriever.retrieve()` ⇒ danh sách chunk top-k.
3. Gold = chunk có `doc_id` ∈ `evidence_doc_id` **và** `section` khớp `evidence_section`
   (nếu `evidence_section` rỗng ⇒ chỉ cần đúng `doc_id`).
4. Báo cáo: tỉ lệ hit theo nhóm + trung bình số section khác nhau trong top-k
   (đo tác động của `max_chunks_per_section`).

Cách dùng
---------
```bash
python scripts/measure_gold_hit_rate.py \
    --qa-set data/eval/qa_rag_250_v2.jsonl \
    --out reports/phase19_gold_hit_rate.json
```
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _norm(value: str) -> str:
    """Chuẩn hoá chuỗi để so khớp (bỏ dấu cách thừa, hạ chữ thường)."""
    return " ".join(str(value or "").strip().lower().split())


def main() -> int:
    """Điểm chính.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa-set", default="data/eval/qa_rag_250_v2.jsonl")
    parser.add_argument("--top-k", type=int, default=0, help="0 = lấy từ configs/retrieval.yaml")
    parser.add_argument("--only-types", default="narrative")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from src.qa.retriever import Retriever  # noqa: PLC0415 — import động để chạy nhanh

    qa_path = REPO_ROOT / args.qa_set
    rows = [json.loads(line) for line in qa_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    wanted = {t.strip() for t in args.only_types.split(",") if t.strip()}
    rows = [row for row in rows if not wanted or row.get("type") in wanted]

    retriever = Retriever.load("configs/retrieval.yaml")
    top_k = args.top_k or int(retriever.config.get("top_k", 8))

    per_group: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "hit": 0})
    sections_per_topk: list[float] = []
    misses: list[dict[str, str]] = []

    for row in rows:
        query = str(row.get("question") or "")
        doc_ids = {str(d) for d in (row.get("evidence_doc_id") or [])}
        gold_section = _norm(row.get("evidence_section") or "")
        chunks = retriever.retrieve(query, top_k=top_k)
        retrieved = [
            {
                "doc_id": str(getattr(chunk.chunk, "doc_id", "") or ""),
                "section": str(getattr(chunk.chunk, "section", "") or ""),
                "title": str(getattr(chunk.chunk, "title", "") or ""),
            }
            for chunk in chunks
        ]

        hit = False
        for item in retrieved:
            if item["doc_id"] not in doc_ids:
                continue
            if not gold_section:
                hit = True
                break
            if gold_section in _norm(item["section"]):
                hit = True
                break

        group = str(row.get("type") or "?")
        per_group[group]["n"] += 1
        per_group[group]["hit"] += int(hit)
        if hit:
            sections_per_topk.append(len({item["section"] for item in retrieved}))
        else:
            misses.append(
                {
                    "qid": str(row.get("qid") or ""),
                    "type": group,
                    "question": query,
                    "expected_doc_id": ",".join(sorted(doc_ids)),
                    "expected_section": str(row.get("evidence_section") or ""),
                }
            )

    summary = {
        "qa_set": args.qa_set,
        "top_k": top_k,
        "only_types": sorted(wanted),
        "groups": {
            group: {
                "n": stats["n"],
                "hit": stats["hit"],
                "hit_rate": round(stats["hit"] / stats["n"], 4) if stats["n"] else None,
            }
            for group, stats in sorted(per_group.items())
        },
        "mean_distinct_sections_in_topk": round(mean(sections_per_topk), 3) if sections_per_topk else None,
        "misses": misses,
    }

    print("\n=== Hit-rate gold section trong top-k ===")
    for group, stats in summary["groups"].items():
        print(f"  {group}: {stats['hit']}/{stats['n']} ({stats['hit_rate']})")
    print(f"  TB số section khác nhau trong top-{top_k}: {summary['mean_distinct_sections_in_topk']}")

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        out_path = REPO_ROOT / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"Ghi: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

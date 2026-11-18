#!/usr/bin/env python
"""Soi context KG của một danh sách câu hỏi (D-124).

Cách dùng:
    python scripts/probe_kg_context.py q0062 q0068 q0075 ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.entity_linker import EntityLinker  # noqa: E402
from src.qa.graph_context import GraphContextBuilder  # noqa: E402


def main() -> int:
    """In context KG của các câu hỏi yêu cầu.

    Returns:
        Mã thoát (0 = thành công).
    """
    qids = sys.argv[1:]
    if not qids:
        print("Cần ít nhất một qid.")
        return 1
    linker = EntityLinker()
    builder = GraphContextBuilder()
    qa = {}
    with (REPO_ROOT / "data" / "eval" / "qa_rag_250.jsonl").open(
        "r", encoding="utf-8"
    ) as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                qa[str(row.get("qid"))] = row
    for qid in qids:
        row = qa.get(qid)
        if row is None:
            print(f"[{qid}] không có trong bộ câu hỏi")
            continue
        question = str(row.get("question") or "")
        linked = linker.link(question)
        print("=" * 70)
        print(f"[{qid}] {question}")
        if not linked:
            print("  (không link được entity)")
            continue
        eid = linked[0][1]
        context = builder.fetch("event_deep", eid)
        print(f"  entity={linked[0][2]} ({eid})  n_edges={len(context.edges)} "
              f"n_queries={len(context.queries)}")
        for edge in context.edges:
            print(f"    - {edge.get('source_name')} — {edge.get('relation')} → "
                  f"{edge.get('target_name')}  | {edge.get('evidence_sentence')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

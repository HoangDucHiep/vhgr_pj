#!/usr/bin/env python
"""Đo **đóng góp thực** của hop-2 cho câu hỏi `narrative` (D-123).

Vì sao cần đo lại?
-----------------
D-121 giả định: "cần đi **2 bước** từ Event mới tới được người chỉ huy" ⇒
thêm template hop-2. Nhưng D-123 đã chứng minh `chi_huy_tran` được lưu theo
chiều **Person → Event**, nên truy vấn **1-hop không hướng** (`(e)-[r]-(n1)`)
**đã** gặp được người chỉ huy ⇒ hop-2 **không còn cần** cho mục tiêu đó.

⇒ Câu hỏi: hop-2 còn giữ được thông tin gì **mà hop-1 không có**, và cái
giá của nó (nhiễu + chiếm ngân sách context) là bao nhiêu?

Cách dùng:
    python scripts/probe_hop2_value.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.qa.graph_context import GraphContextBuilder  # noqa: E402


def _edge_key(edge: dict) -> tuple[str, str, str]:
    """Khoá của một cạnh.

    Args:
        edge: Cạnh KG.

    Returns:
        Tuple `(source_id, relation, target_id)`.
    """
    return (
        str(edge.get("source_id") or ""),
        str(edge.get("relation") or ""),
        str(edge.get("target_id") or ""),
    )


def _sample_events() -> list[tuple[str, str]]:
    """Danh sách `(qid, entity_id)` của các sự kiện trong 60 câu narrative.

    Vì sao link tại chỗ?
    -------------------
    Bộ câu hỏi `narrative` **không** có `expected_entities` (đo được: 60/60
    rỗng) ⇒ phải **link** câu hỏi thật để lấy entity sự kiện.

    Returns:
        Danh sách cặp `(qid, entity_id)`.
    """
    from backend.app.services.entity_linker import EntityLinker

    linker = EntityLinker()
    qa_path = REPO_ROOT / "data" / "eval" / "qa_rag_250.jsonl"
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    with qa_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("type") != "narrative":
                continue
            try:
                linked = linker.link(str(row.get("question") or ""))
            except Exception:  # noqa: BLE001 - probe, bỏ qua lỗi linking
                linked = []
            for _span, eid, _name in linked:
                if not eid or eid in seen:
                    continue
                seen.add(eid)
                out.append((str(row.get("qid")), eid))
    return out


def main() -> int:
    """Đo và in kết quả.

    Returns:
        Mã thoát (0 = thành công).
    """
    builder = GraphContextBuilder()

    rows = []
    for qid, eid in _sample_events():
        context = builder.fetch("event_deep", eid)
        edges = context.edges
        anchor_touch = [
            e
            for e in edges
            if e.get("source_id") == eid or e.get("target_id") == eid
        ]
        anchor_keys = {_edge_key(e) for e in anchor_touch}
        others = [e for e in edges if _edge_key(e) not in anchor_keys]
        rows.append((qid, eid, edges, anchor_touch, others))

    total_edges = sum(len(r[2]) for r in rows)
    total_anchor = sum(len(r[3]) for r in rows)
    total_other = sum(len(r[4]) for r in rows)
    print(f"=== Số sự kiện lấy mẫu: {len(rows)} ===")
    print(f"Tổng cạnh KG            : {total_edges}")
    print(f"  cạnh chạm anchor (hop-1): {total_anchor} "
          f"({total_anchor / max(total_edges, 1):.1%})")
    print(f"  cạnh KHÔNG chạm anchor  : {total_other} "
          f"({total_other / max(total_edges, 1):.1%})")

    rel_counter: Counter[str] = Counter()
    for _qid, _eid, _edges, _anchor, others in rows:
        for edge in others:
            rel_counter[str(edge.get("relation") or "")] += 1
    print("\n=== Quan hệ của các cạnh hop-2 ===")
    for rel, count in rel_counter.most_common():
        print(f"  {rel:20s} {count:4d}")

    kg_chars = sum(
        200 + len(str(e.get("evidence_sentence") or ""))
        for r in rows
        for e in r[4]
    )
    anchor_chars = sum(
        200 + len(str(e.get("evidence_sentence") or ""))
        for r in rows
        for e in r[3]
    )
    print("\n=== Chi phí ngân sách context (ước lượng) ===")
    print(f"  hop-1: {anchor_chars:6d} ký tự")
    print(f"  hop-2: {kg_chars:6d} ký tự "
          f"({kg_chars / max(anchor_chars + kg_chars, 1):.1%} tổng KG)")
    print("  Ngân sách KG của arm B = 35% context ⇒ hop-2 "
          f"{'CHIẾM' if kg_chars > anchor_chars else 'không chiếm quá mức'} "
          "phần lớn ngân sách KG")
    return 0


if __name__ == "__main__":
    sys.exit(main())

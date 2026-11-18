#!/usr/bin/env python3
"""Đo **độ phủ KG** cho 60 câu hỏi `narrative` (D-123).

Vì sao cần script này?
---------------------
Sau khi eval 60 câu narrative (D-122) cho thấy Hybrid **thua** Vanilla RAG
(correctness 1,60 vs 1,68), ta cần biết chính xác:

1. Câu hỏi **link được entity nào** (anchor) — có đúng sự kiện không?
2. Với anchor đó, **hop-1** (cạnh trực tiếp) trả về bao nhiêu cạnh, trong đó
   bao nhiêu là **chỉ huy / bên tham chiến / địa điểm** (3 loại "bên liên quan")?
3. **hop-2** có thêm được thông tin gì **mà hop-1 chưa có**?
4. Có bao nhiêu cạnh nhiễu (node `Title` = danh xưng, cạnh "sinh tại"/"mất tại"
   của người không liên quan)?

Kết quả quyết định: giữ hay bỏ hop-2, có cần lọc `Title` không.

Cách dùng:
    python scripts/probe_narrative_kg.py [--limit 60] [--json-out <file>]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Quan hệ chứa **thông tin bên liên quan** (điểm cốt lõi của đề tài).
PARTY_RELATIONS = ("chi_huy_tran", "tham_gia_tran", "dien_ra_tai")

#: Quan hệ **sinh/mất** — hay gây nhiễu cho câu hỏi tự sự.
LIFE_RELATIONS = ("sinh_tai", "mat_tai")


def _label_of(record: dict[str, Any]) -> str:
    """Lấy nhãn node của một record (nếu template có trả về).

    Args:
        record: Record từ Neo4j.

    Returns:
        Nhãn node (ví dụ `"Person"`), hoặc `""` nếu không có.
    """
    for key in ("source_labels", "target_labels"):
        value = record.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
        if isinstance(value, str) and value:
            return value
    return ""


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Đo độ phủ KG cho câu hỏi narrative.")
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    from backend.app.services.entity_linker import get_linker
    from backend.app.services.neo4j_client import run_read_query

    from src.qa.graph_context import ALL_RELATIONS, EVENT_RELATIONS

    linker = get_linker()
    questions = [
        json.loads(line)
        for line in (REPO_ROOT / "data" / "eval" / "qa_rag_250.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    questions = [q for q in questions if q.get("type") == "narrative"][: args.limit]

    totals: Counter[str] = Counter()
    per_question: list[dict[str, Any]] = []

    for question in questions:
        text = str(question.get("question") or "")
        try:
            linked = linker.link(text)
        except Exception as error:  # noqa: BLE001 - linking lỗi không chặn đo
            print(f"LINK LỖI: {error}", file=sys.stderr)
            linked = []
        if not linked:
            totals["no_link"] += 1
            per_question.append({"qid": question.get("qid"), "linked": 0})
            continue

        anchor_id = linked[0][1]
        anchor_name = linked[0][2]
        totals["linked"] += 1

        hop1 = run_read_query(
            """
            MATCH (e {entity_id: $entity_id})-[r]-(o)
            WHERE type(r) IN $event_relations OR type(r) IN $any_relations
            WITH startNode(r) AS s, endNode(r) AS t, r
            RETURN s.entity_id AS source_id,
                   s.name AS source_name,
                   labels(s) AS source_labels,
                   type(r) AS relation,
                   t.entity_id AS target_id,
                   t.name AS target_name,
                   labels(t) AS target_labels,
                   r.evidence_sentence AS evidence_sentence
            LIMIT 60
            """,
            {
                "entity_id": anchor_id,
                "limit": 60,
                "event_relations": EVENT_RELATIONS,
                "any_relations": ALL_RELATIONS,
            },
        )
        hop2 = run_read_query(
            """
            MATCH (e {entity_id: $entity_id})-[r1]-(n1)
            WHERE type(r1) IN $event_relations OR type(r1) IN $any_relations
            MATCH (n1)-[r2]-(n2)
            WHERE type(r2) IN $event_relations OR type(r2) IN $any_relations
            WITH startNode(r2) AS s2, endNode(r2) AS t2, r2
            RETURN s2.entity_id AS source_id,
                   s2.name AS source_name,
                   labels(s2) AS source_labels,
                   type(r2) AS relation,
                   t2.entity_id AS target_id,
                   t2.name AS target_name,
                   labels(t2) AS target_labels,
                   r2.evidence_sentence AS evidence_sentence
            LIMIT 60
            """,
            {
                "entity_id": anchor_id,
                "limit": 60,
                "event_relations": EVENT_RELATIONS,
                "any_relations": ALL_RELATIONS,
            },
        )

        def _party_edges(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
            return {
                (str(r.get("relation")), str(r.get("target_name")))
                for r in rows
                if str(r.get("relation")) in PARTY_RELATIONS
            }

        party1 = _party_edges(hop1)
        party2 = _party_edges(hop2)
        new_party = party2 - party1
        title_edges = [
            r for r in hop1 + hop2
            if "Title" in (_label_of(r),)
        ]
        life_noise = [
            r for r in hop1 + hop2
            if str(r.get("relation")) in LIFE_RELATIONS
        ]

        totals["hop1_edges"] += len(hop1)
        totals["hop2_edges"] += len(hop2)
        totals["party_hop1"] += len(party1)
        totals["party_hop2_new"] += len(new_party)
        totals["title_edges"] += len(title_edges)
        totals["life_noise"] += len(life_noise)
        totals["hop2_empty"] += 1 if not hop2 else 0

        per_question.append(
            {
                "qid": question.get("qid"),
                "question": text,
                "anchor": anchor_name,
                "anchor_id": anchor_id,
                "n_hop1": len(hop1),
                "n_hop2": len(hop2),
                "n_party_hop1": len(party1),
                "n_party_hop2_new": len(new_party),
                "n_title_edges": len(title_edges),
                "n_life_noise": len(life_noise),
                "hop2_adds_nothing": not new_party and not (
                    set(str(r.get("relation")) for r in hop2)
                    - set(str(r.get("relation")) for r in hop1)
                ),
            }
        )

        print(
            f"{question.get('qid')} | {text[:44]:46s} | anchor={anchor_name[:26]:28s}"
            f" | hop1={len(hop1):3d} party={len(party1):3d}"
            f" | hop2={len(hop2):3d} new={len(new_party):3d}"
            f" | title={len(title_edges):2d} life={len(life_noise):2d}"
        )

    print("\n=== TỔNG ===")
    n = max(totals["linked"], 1)
    print(f"link được entity:      {totals['linked']}/{len(questions)}")
    print(f"hop1 edges/câu:        {totals['hop1_edges'] / n:.1f}")
    print(f"hop2 edges/câu:        {totals['hop2_edges'] / n:.1f}")
    print(f"bên liên quan (hop1):  {totals['party_hop1'] / n:.1f}")
    print(f"bên liên quan MỚI (hop2): {totals['party_hop2_new'] / n:.1f}")
    print(f"cạnh node Title:       {totals['title_edges'] / n:.1f}")
    print(f"cạnh sinh/mất (nhiễu): {totals['life_noise'] / n:.1f}")
    print(f"hop2 rỗng:             {totals['hop2_empty']}/{n}")

    if args.json_out:
        out = REPO_ROOT / args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {"totals": dict(totals), "per_question": per_question},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nGhi {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

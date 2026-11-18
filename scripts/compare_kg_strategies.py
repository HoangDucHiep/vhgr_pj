#!/usr/bin/env python3
"""Chọn **chiến lược truy vấn KG** tối ưu cho câu hỏi `narrative` (D-123).

Bối cảnh
---------
D-121 thêm template 2-hop (`event_deep`) để lấy "các bên liên quan". Nhưng
template đó **nhân bản** 2 hop ⇒ cartesian product ⇒ `LIMIT` cắt cụt cả
cạnh hop-1 ⇒ mất 8/10 chỉ huy (đo được với "Cuộc bao vây thành Quy Nhơn").

Eval 60 câu narrative (D-122) cho thấy Hybrid **thua** Vanilla RAG
(correctness 1,60 vs 1,68) ⇒ cần chọn lại chiến lược truy vấn.

Script này đo **6 chiến lược** trên đúng 60 câu narrative, theo 4 tiêu chí:

| Tiêu chí | Ý nghĩa |
|---|---|
| `party` | số cạnh **chỉ huy / bên tham chiến / địa điểm** (giá trị của KG) |
| `noise` | số cạnh **sinh/mất tại** của người không liên quan (rác) |
| `total` | tổng số cạnh đưa vào context (càng nhiều càng loãng) |
| `dup` | số cạnh **trùng nội dung** với hop-1 (hop-2 vô ích) |

Cách dùng:
    python scripts/compare_kg_strategies.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Quan hệ chứa thông tin "bên liên quan" (giá trị thật của KG).
PARTY_RELATIONS = ("chi_huy_tran", "tham_gia_tran", "dien_ra_tai")

#: Quan hệ sinh/mất — nhiễu cho câu hỏi tự sự.
LIFE_RELATIONS = ("sinh_tai", "mat_tai", "dong_doi_tai")

#: Quan hệ **sự kiện**.
R_EVENT = ["chi_huy_tran", "tham_gia_tran", "danh_bai", "dien_ra_tai", "lap_ra"]

#: Quan hệ **bối cảnh** (triều đại, chức vụ, kế vị) — hữu ích cho câu tự sự.
R_CTX = R_EVENT + ["thuoc_trieu_dai", "giu_chuc_vu", "ke_vi"]

#: Quan hệ **sinh tử** — nhiễu.
R_LIFE = ["sinh_tai", "mat_tai", "sinh_nam", "mat_nam", "dong_doi_tai"]

#: Quan hệ **gia đình**.
R_FAM = ["cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua"]

#: Toàn bộ quan hệ.
R_ALL = R_CTX + R_LIFE + R_FAM

#: 6 chiến lược: (tên, quan hệ hop-1, có hop-2 không, quan hệ hop-2).
STRATEGIES: list[tuple[str, list[str], bool, list[str]]] = [
    ("S1 R_ALL +hop2(R_ALL)", R_ALL, True, R_ALL),
    ("S2 R_ALL hop1", R_ALL, False, []),
    ("S3 R_EVENT hop1", R_EVENT, False, []),
    ("S4 R_EVENT hop1 +hop2", R_EVENT, True, R_EVENT),
    ("S5 R_CTX hop1 +hop2(R_EVENT)", R_CTX, True, R_EVENT),
    ("S6 R_CTX hop1", R_CTX, False, []),
]


def _query(entity_id: str, rels: list[str], *, hop: int) -> list[dict]:
    """Chạy truy vấn hop-1 hoặc hop-2 quanh entity.

    Args:
        entity_id: Id entity.
        rels: Danh sách quan hệ được phép.
        hop: 1 hoặc 2.

    Returns:
        Danh sách cạnh (dict).
    """
    from backend.app.services.neo4j_client import run_read_query

    if hop == 1:
        cypher = """
            MATCH (e {entity_id: $entity_id})-[r]-(o)
            WHERE type(r) IN $rels
            WITH startNode(r) AS s, endNode(r) AS t, r
            RETURN s.entity_id AS source_id, s.name AS source_name,
                   type(r) AS relation,
                   t.entity_id AS target_id, t.name AS target_name
            LIMIT 60
        """
    else:
        cypher = """
            MATCH (e {entity_id: $entity_id})-[r1]-(n1)
            WHERE type(r1) IN $rels
            MATCH (n1)-[r2]-(n2)
            WHERE type(r2) IN $rels
            WITH startNode(r2) AS s2, endNode(r2) AS t2, r2
            RETURN s2.entity_id AS source_id, s2.name AS source_name,
                   type(r2) AS relation,
                   t2.entity_id AS target_id, t2.name AS target_name
            LIMIT 60
        """
    return run_read_query(cypher, {"entity_id": entity_id, "rels": rels})


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    from backend.app.services.entity_linker import get_linker

    linker = get_linker()
    questions = [
        json.loads(line)
        for line in (REPO_ROOT / "data" / "eval" / "qa_rag_250.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    questions = [q for q in questions if q.get("type") == "narrative"]

    acc: dict[str, dict[str, list[float]]] = {
        name: {"total": [], "party": [], "noise": [], "dup": []}
        for name, *_ in STRATEGIES
    }

    for question in questions:
        text = str(question.get("question") or "")
        try:
            linked = linker.link(text)
        except Exception:  # noqa: BLE001
            linked = []
        if not linked:
            continue
        anchor_id = linked[0][1]
        for name, rels1, use_hop2, rels2 in STRATEGIES:
            edges1 = _query(anchor_id, rels1, hop=1)
            edges2 = _query(anchor_id, rels2, hop=2) if use_hop2 else []
            # Cạnh hop-2 trùng hop-1 (cùng cặp nguồn→đích) ⇒ vô ích.
            keys1 = {
                (e["source_id"], e["relation"], e["target_id"]) for e in edges1
            }
            keys2 = {
                (e["source_id"], e["relation"], e["target_id"]) for e in edges2
            }
            dup = len(keys1 & keys2)
            all_edges = edges1 + edges2
            acc[name]["total"].append(len(all_edges))
            acc[name]["party"].append(
                sum(1 for e in all_edges if e["relation"] in PARTY_RELATIONS)
            )
            acc[name]["noise"].append(
                sum(1 for e in all_edges if e["relation"] in LIFE_RELATIONS)
            )
            acc[name]["dup"].append(dup)

    print(
        f"{'chiến lược':30s} {'tổng cạnh':>10s} {'bên liên quan':>14s} "
        f"{'nhiễu':>8s} {'trùng':>8s}"
    )
    print("-" * 74)
    for name, *_ in STRATEGIES:
        row = acc[name]
        print(
            f"{name:30s} {mean(row['total']):10.1f} {mean(row['party']):14.1f}"
            f" {mean(row['noise']):8.1f} {mean(row['dup']):8.1f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

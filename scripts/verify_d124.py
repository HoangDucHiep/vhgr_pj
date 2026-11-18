#!/usr/bin/env python
"""Kiểm chứng 5 fix D-124 trong container (truy vấn KG thật)."""

from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from src.qa.graph_context import (  # noqa: E402
    CONTEXT_RELATIONS,
    EVIDENCE_PREFIX_VARIANTS,
    GraphContextBuilder,
    _INTENT_TEMPLATES,
)
from src.graph.noise_filter import is_linkage_artifact_name  # noqa: E402

print("=== 1. Template hop-2 có scope `n2 = e` ===")
hop2 = _INTENT_TEMPLATES["event_hop2"]["cypher"]
print("   có `n2 = e`:", "n2 = e" in hop2)

print("=== 2. Template `event_parties` tồn tại ===")
print("   có:", "event_parties" in _INTENT_TEMPLATES)

print("=== 3. Quan hệ sinh tử KHÔNG nằm trong CONTEXT_RELATIONS ===")
life = {"sinh_tai", "mat_tai", "sinh_nam", "mat_nam", "dong_doi_tai"}
print("   giao:", life & set(CONTEXT_RELATIONS) or "(rỗng) ✓")

print("=== 4. Biến thể tiền tố bằng chứng ===")
print("   chi_huy_tran:", EVIDENCE_PREFIX_VARIANTS.get("chi_huy_tran"))

print("=== 5. Lọc tên rác liên kết Wikipedia ===")
for name in ("Chuẩn đề đốc Page", "Chuẩn đề đốc (Page)", "Quang Trung", "X (Disambiguation)"):
    print(f"   {name!r:30s} → artifact={is_linkage_artifact_name(name)}")

print("=== 6. Truy vấn KG thật: sự kiện 'Trận Hà Hồi' ===")
builder = GraphContextBuilder()
# Tìm entity id của "Trận Hà Hồi" trong KG.
from backend.app.services.neo4j_client import run_read_query  # noqa: E402

try:
    rows = run_read_query(
        "MATCH (e:Event) WHERE e.name CONTAINS $kw "
        "RETURN e.entity_id AS id, e.name AS name LIMIT 5",
        {"kw": "Hà Hồi"},
    )
    print("   tìm thấy:", rows)
    for row in rows[:1]:
        ctx = builder.fetch("event_deep", row["id"])
        print(f"   edges={len(ctx.edges)} queries={len(ctx.queries)}")
        names = {e.get("source_name") for e in ctx.edges}
        print("   artifact names:", [n for n in names if is_linkage_artifact_name(str(n))] or "(không có) ✓")
except Exception as error:  # noqa: BLE001
    print("   probe lỗi:", str(error)[:300])

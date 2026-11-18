#!/usr/bin/env python
"""Probe: cạnh KG có sẵn `source_labels`/`target_labels` không? (D-139)

Mục tiêu: xác định **node nào là sự kiện** để hiển thị quan hệ sự kiện
(`chi_huy_tran`, `tham_gia_tran`) bằng **mệnh đề tự nhiên** không thể đọc
ngược (D-139).

Cách dùng:
    docker compose exec -T backend python scripts/probe_kg_labels.py \
        --entity "Trận Hà Hồi"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.entity_linker import EntityLinker  # noqa: E402
from src.qa.graph_context import GraphContextBuilder  # noqa: E402


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity", default="Trận Hà Hồi")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    linker = EntityLinker()
    linked = linker.link(args.entity)
    print("linked:", linked[:3])
    if not linked:
        print("Không link được entity")
        return 1

    builder = GraphContextBuilder()
    ctx = builder.fetch("event_deep", linked[0][1])
    for edge in ctx.edges[: args.limit]:
        print(
            json.dumps(
                {
                    "relation": edge.get("relation"),
                    "source_name": edge.get("source_name"),
                    "source_labels": edge.get("source_labels"),
                    "target_name": edge.get("target_name"),
                    "target_labels": edge.get("target_labels"),
                    "reversed": edge.get("reversed"),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

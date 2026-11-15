"""Tra cứu ngược entity_id → tên, phục vụ gán tay bộ gold coreference.

Cách chạy
---------
```bash
python scripts/coref_entity_lookup.py ent_quang_trung_242ef52d ent_tran_91d2302e
```
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.coref.gazetteer import build_gazetteer  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """Tra cứu ngược danh sách `entity_id`.

    Args:
        argv: Danh sách `entity_id` cần tra.

    Returns:
        Mã thoát.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    gazetteer = build_gazetteer(
        REPO_ROOT / "data/interim/infobox_entities.jsonl",
        REPO_ROOT / "data/interim/documents.jsonl",
    )
    reverse: dict[str, str] = {}
    for entry in gazetteer.entries.values():
        reverse.setdefault(entry.entity_id, f"{entry.name} [{entry.type}/{entry.source}]")

    # Bổ sung: các entity đã mint trong `coref_resolved.jsonl`.
    coref_path = REPO_ROOT / "data/interim/coref_resolved.jsonl"
    if coref_path.exists():
        with coref_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                for mention in row.get("mentions") or []:
                    entity_id = mention.get("canonical_id")
                    if entity_id and entity_id not in reverse:
                        reverse[entity_id] = f"{mention.get('text')} [minted/{mention.get('label')}]"

    for entity_id in args:
        print(f"{entity_id} -> {reverse.get(entity_id, 'KHÔNG RÕ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

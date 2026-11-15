"""Tra entity_id cho danh sách tên (dùng khi gán tay gold)."""

from __future__ import annotations

import json
import sys
from collections import defaultdict


def main() -> int:
    names = set(sys.argv[1:])
    seen: dict[str, set[str]] = defaultdict(set)
    for line in open("data/interim/coref_resolved.jsonl", encoding="utf-8"):
        row = json.loads(line)
        for m in row.get("mentions") or []:
            if m.get("source") != "ner" or not m.get("canonical_id"):
                continue
            text = str(m.get("text") or "")
            if names and text not in names:
                continue
            seen[text].add(str(m["canonical_id"]))
    for name in sorted(names):
        ids = sorted(seen.get(name, []))
        print(f"{name!r:42} {ids if ids else 'NONE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

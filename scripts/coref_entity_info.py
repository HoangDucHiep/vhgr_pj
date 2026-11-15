"""Tra cứu chi tiết entity theo entity_id hoặc tên."""

from __future__ import annotations

import json
import sys


def main() -> int:
    targets = set(sys.argv[1:])
    seen = set()
    for path in (
        "data/interim/infobox_entities.jsonl",
        "data/interim/article_subjects.jsonl",
    ):
        for line in open(path, encoding="utf-8"):
            row = json.loads(line)
            eid = str(row.get("entity_id") or "")
            name = str(row.get("name") or row.get("title") or "")
            if eid in targets or name in targets:
                key = (eid, path)
                if key in seen:
                    continue
                seen.add(key)
                print(f"[{path.split('/')[-1]}] id={eid} name={name!r} "
                      f"type={row.get('type')} qid={row.get('wikidata_qid') or row.get('qid')} "
                      f"method={row.get('method')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

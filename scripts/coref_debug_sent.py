"""Debug: in ra mention NER + coref của một câu và các câu trước trong đoạn."""

from __future__ import annotations

import json
import sys

TARGETS = set(sys.argv[1:])


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    want = set()
    for r in load_jsonl("data/eval/coref_gold_100.jsonl"):
        if r["sentence_id"] in TARGETS:
            want.add(r["doc_id"])
            want.add(r["sentence_id"].split("_")[1])

    for row in load_jsonl("data/interim/coref_resolved.jsonl"):
        sid = row["sentence_id"]
        parts = sid.split("_")
        if row["doc_id"] not in want or parts[1] not in want:
            continue
        mark = ">>" if sid in TARGETS else "  "
        print(f"{mark} {sid}: {row['text'][:110]}")
        for m in row["mentions"]:
            print(f"     [{m['start']}:{m['end']}] {m['text']!r:32} "
                  f"{m['label']:9} {m['source']:8} -> {m['canonical_id']} ({m['resolved_by']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""In đoạn văn đầy đủ cho các câu cần xem xét kỹ."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    targets = set(sys.argv[1:])
    gold = load_jsonl("data/eval/coref_gold_100.jsonl")
    need = set()
    for g in gold:
        if g["sentence_id"] in targets:
            need.add((g["doc_id"], g["sentence_id"].split("_")[1]))
    if not need:
        return 1
    paras = {}
    for doc in load_jsonl("data/interim/documents.jsonl"):
        did = doc["doc_id"]
        if not any(t[0] == did for t in need):
            continue
        for s in doc.get("sentences") or []:
            sid = str(s.get("sentence_id") or "")
            parts = sid.split("_")
            if len(parts) >= 3 and (did, parts[1]) in need:
                paras.setdefault((did, parts[1]), []).append(s)
    for g in gold:
        sid = g["sentence_id"]
        if sid not in targets:
            continue
        print(f"##### {sid} ({g['doc_id']})")
        for s in paras.get((g["doc_id"], sid.split("_")[1]), []):
            mark = ">>" if s.get("sentence_id") == sid else "  "
            print(f"  {mark} {s.get('sentence_id')}: {s.get('text')}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

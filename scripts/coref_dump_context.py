"""In bối cảnh đầy đủ cho các mention cần gán tay (gold coref).

Cách chạy:
    python scripts/coref_dump_context.py > /tmp/gold_ctx.txt
"""

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
    gold = load_jsonl("data/eval/coref_gold_100.jsonl")
    preds = {r["sentence_id"]: r for r in load_jsonl("data/interim/coref_resolved.jsonl")}
    subjects = {r["doc_id"]: r for r in load_jsonl("data/interim/article_subjects.jsonl")}

    # Gom text đoạn theo (doc, para) từ documents.jsonl
    need = set()
    for g in gold:
        sid = g["sentence_id"]
        parts = sid.split("_")
        need.add((g["doc_id"], parts[1]))
    paras = {}
    for doc in load_jsonl("data/interim/documents.jsonl"):
        did = doc["doc_id"]
        for para in doc.get("paragraphs") or []:
            pidx = str(para.get("para_idx"))
            if (did, pidx) in need:
                paras[(did, pidx)] = para
        if len(paras) >= len(need):
            break

    for i, g in enumerate(gold):
        sid = g["sentence_id"]
        parts = sid.split("_")
        key = (g["doc_id"], parts[1])
        para = paras.get(key, {})
        subj = subjects.get(g["doc_id"], {})
        print(f"===== [{i}] {sid} | doc={g['doc_id']} | subj={subj.get('title')!r} "
              f"({subj.get('type')}) id={subj.get('entity_id')}")
        for s in para.get("sentences") or []:
            mark = ">>" if s.get("sentence_id") == sid else "  "
            print(f"  {mark} {s.get('sentence_id')}: {s.get('text')}")
        p = preds.get(sid, {})
        pm = {(m["start"], m["end"]): m for m in p.get("mentions") or []}
        for m in g["mentions"]:
            s, e = m["start"], m["end"]
            before = g["text"][max(0, s - 45):s]
            after = g["text"][e:e + 45]
            sys_m = pm.get((s, e))
            sys_id = sys_m.get("canonical_id") if sys_m else "<MISS>"
            sys_by = sys_m.get("resolved_by") if sys_m else "<MISS>"
            print(f"    - [{s}:{e}] {m['text']!r} label={m['label']}")
            print(f"        ctx: ...{before}[[{m['text']}]]{after}...")
            print(f"        SYS: {sys_id} ({sys_by})")
        # danh sách ứng viên
        print("    candidates:")
        for c in g.get("ung_vien") or []:
            print(f"        {c.get('ten')!r:40} {c.get('canonical_id')} ({c.get('loi')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

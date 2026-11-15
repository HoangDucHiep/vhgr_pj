"""Bảng phân tích: với mỗi mention cần gán tay, in ứng viên PERSON
trong cùng câu và ở các câu trước của đoạn (kèm vị trí và cách giới thiệu).
"""

from __future__ import annotations

import json
import re

FRAME_WORDS = {"đời", "thời", "triều", "nhà", "vua", "từ", "sau", "khi", "của", "với"}


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
    ids = {g["sentence_id"] for g in gold}
    docs = {g["doc_id"] for g in gold}

    # Gom câu theo (doc, para)
    paras: dict[tuple[str, str], list[dict]] = {}
    for row in load_jsonl("data/interim/coref_resolved.jsonl"):
        if row["doc_id"] not in docs:
            continue
        p = row["sentence_id"].split("_")[1]
        paras.setdefault((row["doc_id"], p), []).append(row)

    subjects = {r["doc_id"]: r for r in load_jsonl("data/interim/article_subjects.jsonl")}

    for g in gold:
        sid = g["sentence_id"]
        rows = paras[(g["doc_id"], sid.split("_")[1])]
        idx = next(i for i, r in enumerate(rows) if r["sentence_id"] == sid)
        subj = subjects[g["doc_id"]]
        print(f"##### {sid} | subj={subj['title']!r} type={subj['type']} id={subj['entity_id']}")
        for m in g["mentions"]:
            s, e = m["start"], m["end"]
            before = g["text"][max(0, s - 40):s]
            after = g["text"][e:e + 40]
            print(f"  MENTION [{s}:{e}] {m['text']!r}  ...{before}[[{m['text']}]]{after}...")
        # ứng viên PERSON trong cùng câu
        cur = rows[idx]
        cur_p = [m for m in cur["mentions"]
                 if m["label"] == "PERSON" and m["source"] == "ner" and m["canonical_id"]]
        print(f"  same-sentence PERSON: "
              f"{[(m['text'], m['canonical_id']) for m in cur_p]}")
        # ứng viên PERSON ở câu trước
        for j in range(idx - 1, max(-1, idx - 3), -1):
            ps = [m for m in rows[j]["mentions"]
                  if m["label"] == "PERSON" and m["source"] == "ner" and m["canonical_id"]]
            if ps:
                print(f"  prev[{rows[j]['sentence_id']}] PERSON: "
                      f"{[(m['text'], m['canonical_id']) for m in ps]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

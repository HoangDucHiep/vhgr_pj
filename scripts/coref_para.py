"""In toàn bộ đoạn văn cho các câu gold được chỉ định (debug).

Cách chạy:
    python scripts/coref_para.py s1336333_0_1 s321161_1_2
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
    targets = set(sys.argv[1:])
    wanted_docs = {f"doc_{sid.split('_')[0].lstrip('s')}" for sid in targets}
    for doc in load_jsonl("data/interim/documents.jsonl"):
        if doc["doc_id"] not in wanted_docs:
            continue
        print(f"##### {doc.get('title')} ({doc['doc_id']})")
        for sent in doc.get("sentences") or []:
            sid = sent.get("sentence_id")
            if not any(sid == t for t in targets):
                # in cả đoạn chứa câu đích
                pass
            print(f"  {sid} [p{sent.get('para_idx')}] {sent.get('text')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

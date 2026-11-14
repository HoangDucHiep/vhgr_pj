#!/usr/bin/env python3
"""Tra nhãn (tiếng Việt/Anh) cho tập lớp Wikidata — tiện ích nội bộ.

Dùng cho Phase 4: cần nhãn của các lớp `P31` và lớp cha (`P279`) để suy
loại entity → nhãn NER.

Chạy::

    python scripts/fetch_class_labels.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.preprocess.wikidata_query import PREFIXES, QLEVER_ENDPOINT, run_query

REPO_ROOT = Path(__file__).resolve().parents[1]
HIERARCHY_PATH = REPO_ROOT / "data" / "interim" / "class_hierarchy.json"
QID_CACHE_PATH = REPO_ROOT / "data" / "interim" / "qid_types.json"
OUT_PATH = REPO_ROOT / "data" / "interim" / "class_labels.json"

BATCH = 150
SLEEP_S = 0.4


def _qid(value: str) -> str:
    """Trích QID từ URI.

    Args:
        value: URI (có thể bọc ``<>``).

    Returns:
        QID.
    """
    return value.strip().strip("<>").rsplit("/", 1)[-1]


def needed_classes() -> list[str]:
    """Tính tập lớp cần nhãn.

    Returns:
        Danh sách QID lớp.
    """
    hierarchy = json.loads(HIERARCHY_PATH.read_text(encoding="utf-8"))
    cache = json.loads(QID_CACHE_PATH.read_text(encoding="utf-8"))
    p31 = cache.get("p31") or {}
    classes = sorted({c for values in p31.values() for c in values})
    parents: set[str] = set()
    for cls in classes:
        parents.update(hierarchy.get(cls) or [])
    return sorted(set(classes) | parents)


def main() -> int:
    """Điểm vào chính.

    Returns:
        Mã thoát.
    """
    labels: dict[str, str] = (
        json.loads(OUT_PATH.read_text(encoding="utf-8")) if OUT_PATH.exists() else {}
    )
    todo = [cls for cls in needed_classes() if cls not in labels]
    print(f"Cần nhãn: {len(todo)} lớp", flush=True)

    for index in range(0, len(todo), BATCH):
        chunk = todo[index : index + BATCH]
        values = " ".join(f"wd:{cls}" for cls in chunk)
        query = (
            PREFIXES
            + f"""
SELECT ?item ?lbl WHERE {{
  VALUES ?item {{ {values} }}
  ?item rdfs:label ?lbl .
  FILTER(LANG(?lbl) IN ('vi', 'en'))
}}
"""
        )
        try:
            rows = run_query(query, endpoints=(QLEVER_ENDPOINT,))
        except Exception as exc:  # noqa: BLE001
            print(f"  lỗi batch {index}: {exc}", flush=True)
            continue
        for row in rows:
            item = _qid(row.get("?item", {}).get("value", ""))
            text = row.get("?lbl", {}).get("value", "")
            if item and text:
                labels.setdefault(item, text)
        if index % (BATCH * 10) == 0:
            OUT_PATH.write_text(
                json.dumps(labels, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
            )
            print(f"  {index}/{len(todo)} → {len(labels)} nhãn", flush=True)
        time.sleep(SLEEP_S)

    OUT_PATH.write_text(
        json.dumps(labels, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"XONG: {len(labels)} nhãn", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Quét dump một lần, cache **facts** tối thiểu của mọi bài namespace 0.

Mục đích: chỉ sử dụng một lần để tinh chỉnh ngưỡng bộ lọc Phase 1 mà không
phải quét lại dump 1.1 GB (mỗi lượt ~7 phút).

## Fact lưu mỗi bài

```json
{"page_id": 123, "title": "Lê Lợi", "revision_id": 99,
 "cats": ["Vua Việt Nam"], "ib": "person", "ibf": 2, "yrs": [1385, 1433],
 "qid": "Q...", "sig": "person", "nlinks": 87}
```

- `ib`: loại infobox đã chuẩn hóa (`person`/`dynasty`/`battle`/`event`/`place`).
- `ibf`: số trường lịch sử chuẩn hóa trong infobox.
- `yrs`: các năm (3–4 chữ số) xuất hiện trong tham số infobox.
- `qid`: QID từ `pageid_to_qid.json`.
- `sig`: tín hiệu Wikidata T0 của bài (nếu có).
- `nlinks`: số hyperlink nội bộ.

Cách chạy:
    python scripts/cache_dump_facts.py
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.logger import get_logger  # noqa: E402
from src.preprocess.dump_reader import iter_dump_pages  # noqa: E402
from src.preprocess.infobox_parser import (  # noqa: E402
    history_fields,
    normalize_infobox_type,
    parse_infobox,
)

logger = get_logger("cache_facts")

DUMP = Path("data/raw/viwiki-20261101-pages-articles.xml.bz2")
OUT = Path("data/interim/dump_facts.jsonl")
INTERIM = Path("data/interim")

YEAR_RE = re.compile(r"\b(\d{3,4})\b")
MIN_WIKITEXT_LEN = 200


def main() -> None:
    """Quét dump và ghi cache facts."""
    seeds = json.loads((INTERIM / "wikidata_seed_articles.json").read_text("utf-8"))
    seed_qids = {e["qid"] for e in seeds["entries"].values() if e.get("qid")}
    qid_map = json.loads((INTERIM / "pageid_to_qid.json").read_text("utf-8"))
    category_members = json.loads((INTERIM / "category_members.json").read_text("utf-8"))
    category_page_ids: set[str] = set()
    for pages in category_members.values():
        category_page_ids.update(pages)

    started = time.monotonic()
    total = 0
    written = 0
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        for page in iter_dump_pages(DUMP):
            total += 1
            if total % 200_000 == 0:
                print(
                    f"  {total} trang / {time.monotonic() - started:.0f}s",
                    flush=True,
                )
            if page.ns != 0 or page.is_redirect:
                continue
            if len(page.wikitext) < MIN_WIKITEXT_LEN:
                continue

            qid = qid_map.get(str(page.page_id), "")
            signal = ""
            if qid and qid in seed_qids:
                signal = "wikidata"

            infobox_type = ""
            history_count = 0
            years: list[int] = []
            head = page.wikitext[:8000]
            if "Infobox" in head or "Thông tin" in head:
                infobox = parse_infobox(page.wikitext)
                if infobox is not None:
                    infobox_type = normalize_infobox_type(infobox.loai) or ""
                    history_count = len(history_fields(infobox))
                    for value in infobox.params.values():
                        years.extend(int(m.group(1)) for m in YEAR_RE.finditer(value))

            fact = {
                "page_id": page.page_id,
                "title": page.title,
                "revision_id": page.revision_id,
                "cats": page.categories,
                "ib": infobox_type,
                "ibf": history_count,
                "yrs": sorted(set(years))[:12],
                "qid": qid,
                "sig": signal,
                "cat": str(page.page_id) in category_page_ids,
                "nlinks": len(page.links),
            }
            handle.write(json.dumps(fact, ensure_ascii=False))
            handle.write("\n")
            written += 1

    print(f"Xong {total} trang trong {time.monotonic() - started:.0f}s")
    print(f"Đã ghi {written} fact vào {OUT}")


if __name__ == "__main__":
    main()

"""Đo đạc một lượt quét dump: đếm số ứng viên theo từng tầng tín hiệu.

Chạy 1 lần trên toàn bộ `pages-articles.xml.bz2` (1.1 GB) và in số liệu để
chốt ngưỡng bộ lọc Phase 1.

Cách chạy:
    python scripts/measure_filter.py
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.logger import get_logger  # noqa: E402
from src.preprocess.dump_reader import iter_dump_pages  # noqa: E402
from src.preprocess.infobox_parser import (  # noqa: E402
    history_fields,
    normalize_infobox_type,
    parse_infobox,
)

logger = get_logger("measure")

INTERIM = Path("data/interim")
DUMP = Path("data/raw/viwiki-20261101-pages-articles.xml.bz2")

MIN_WIKITEXT_LEN = 200
HISTORY_INFBOX_TYPES = {"person", "dynasty", "battle", "event"}


def main() -> None:
    """Chạy đo đạc và in số liệu."""
    seeds = json.loads((INTERIM / "wikidata_seed_articles.json").read_text("utf-8"))
    seed_qids = set(seeds["qid_by_title"].values())
    seed_titles = {t.lower() for t in seeds["signals"]}
    print(f"seed: {len(seed_qids)} QID, {len(seed_titles)} tiêu đề", flush=True)

    pageid_to_qid = json.loads((INTERIM / "pageid_to_qid.json").read_text("utf-8"))
    print(f"pageid→qid: {len(pageid_to_qid)}", flush=True)

    category_members = json.loads((INTERIM / "category_members.json").read_text("utf-8"))
    category_page_ids: set[str] = set()
    for pages in category_members.values():
        category_page_ids.update(pages)
    print(f"category members: {len(category_page_ids)} page_id", flush=True)

    counts: Counter[str] = Counter()
    infobox_types: Counter[str] = Counter()
    linked_from_seed: set[str] = set()
    seed_links: set[str] = set()
    started = time.monotonic()
    total = 0

    for page in iter_dump_pages(DUMP):
        total += 1
        if total % 200_000 == 0:
            elapsed = time.monotonic() - started
            print(
                f"  {total} trang / {elapsed:.0f}s "
                f"({total / max(elapsed, 1e-9):.0f} trang/s)",
                flush=True,
            )
        if page.ns != 0 or page.is_redirect:
            continue
        if len(page.wikitext) < MIN_WIKITEXT_LEN:
            continue
        counts["ns0_valid"] += 1

        qid = pageid_to_qid.get(str(page.page_id))
        has_qid = bool(qid)
        is_seed_title = page.title.lower() in seed_titles
        is_seed_qid = bool(qid) and qid in seed_qids
        is_category = str(page.page_id) in category_page_ids

        if is_seed_qid:
            counts["T0_by_qid"] += 1
        if is_seed_title:
            counts["T0_by_title"] += 1
        if is_category:
            counts["T1_category"] += 1
        if has_qid:
            counts["has_qid"] += 1

        # Infobox: kiểm tra chuỗi trước (rẻ) rồi mới parse (đắt).
        head = page.wikitext[:8000]
        if "Infobox" in head or "Thông tin" in head:
            infobox = parse_infobox(page.wikitext)
            if infobox is not None:
                node_type = normalize_infobox_type(infobox.loai)
                fields = history_fields(infobox)
                if node_type:
                    infobox_types[f"{node_type}:{len(fields)}"] += 1
                if node_type in HISTORY_INFBOX_TYPES and len(fields) >= 2:
                    counts["T2_infobox_hist"] += 1
                    if has_qid:
                        counts["T2_infobox_hist_qid"] += 1
                    if is_seed_qid or is_seed_title:
                        counts["T2_and_T0"] += 1

        # Link từ bài seed (dùng cho T2 mở rộng và T3 BFS).
        if is_seed_qid or is_seed_title or is_category:
            seed_links.update(page.links)

    elapsed = time.monotonic() - started
    print(f"\nXong {total} trang trong {elapsed:.0f}s")
    print("\n=== Số liệu ===")
    for key, value in sorted(counts.items()):
        print(f"  {key:26s} {value}")
    print(f"  seed_links (unique)      {len(seed_links)}")
    print("\n=== Infobox type:số trường lịch sử ===")
    for key, value in infobox_types.most_common(30):
        print(f"  {key:26s} {value}")


if __name__ == "__main__":
    main()

"""Đánh giá chính xác hợp nhất T0+T1+T2 (không cần quét lại dump).

Dùng cache:
- `data/interim/dump_facts.jsonl` — facts nhẹ của mọi bài ns0.
- `data/interim/wikidata_seed_articles.json` — tín hiệu T0.
- `data/interim/category_members.json` — tín hiệu T1 (đã mở rộng đệ quy).
- `data/interim/pageid_to_qid.json` — ánh xạ page_id → QID.

Cách chạy:
    python scripts/eval_final_filter.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from src.common.normalize import normalize_name  # noqa: E402

FACTS = Path("data/interim/dump_facts.jsonl")
SEEDS = Path("data/interim/wikidata_seed_articles.json")
CATS = Path("data/interim/category_members.json")
QIDS = Path("data/interim/pageid_to_qid.json")
SEED_CONFIG = Path("configs/seed_articles.yaml")

#: Regex "có liên quan tới Việt Nam" — dùng cho T2.
VIET_RE = re.compile(r"viet|dai viet")


def main() -> None:
    """Chạy đánh giá."""
    cfg = yaml.safe_load(SEED_CONFIG.read_text("utf-8"))
    exclude_categories = {normalize_name(c) for c in cfg["exclude_categories"]}
    exclude_prefixes = list(cfg["exclude_title_prefixes"])
    whitelist = set(cfg["infobox_whitelist"])

    person_year_max = int(cfg.get("person_year_max", 1900))
    history_min = int(cfg.get("history_year_min", 850))
    history_max = int(cfg.get("history_year_max", 1945))
    min_fields = dict(cfg.get("infobox_min_history_fields", {}))

    seeds = json.loads(SEEDS.read_text("utf-8"))["entries"]
    seed_qids = {e["qid"] for e in seeds.values() if e.get("qid")}

    category_pages: set[str] = set()
    for pages in json.loads(CATS.read_text("utf-8")).values():
        category_pages.update(pages)

    qid_map = json.loads(QIDS.read_text("utf-8"))

    kept: dict[int, str] = {}
    info: dict[int, dict] = {}

    def excluded(fact: dict) -> bool:
        if any(fact["title"].startswith(p) for p in exclude_prefixes):
            return True
        cats = {normalize_name(c) for c in fact["cats"]}
        return any(c in cats for c in exclude_categories)

    def t0(fact: dict) -> bool:
        qid = qid_map.get(str(fact["page_id"]), "")
        if not (qid and qid in seed_qids):
            return False
        entry = seeds.get(fact["title"])
        if entry is None:
            return True
        year = entry.get("year")
        if year is None:
            return True
        signal = entry.get("signal")
        limit = person_year_max if signal == "person" else history_max
        return year <= limit

    def t1(fact: dict) -> bool:
        return int(fact["page_id"]) in category_pages

    def t2(fact: dict) -> bool:
        if fact["ib"] not in whitelist:
            return False
        need = min_fields.get(fact["ib"], 2)
        if fact["ibf"] < need:
            return False
        if not any(history_min <= y <= history_max for y in fact["yrs"]):
            return False
        return any(VIET_RE.search(normalize_name(c)) for c in fact["cats"])

    for line in FACTS.open(encoding="utf-8"):
        if not line.strip():
            continue
        fact = json.loads(line)
        if excluded(fact):
            continue
        if t0(fact):
            kept[fact["page_id"]] = "wikidata"
        elif t1(fact):
            kept[fact["page_id"]] = "category"
        elif t2(fact):
            kept[fact["page_id"]] = "infobox"
        else:
            continue
        info[fact["page_id"]] = fact

    facts = [info[pid] for pid in kept]
    with_qid = sum(1 for f in facts if f["qid"])
    print(f"TỔNG: {len(kept)}")
    print(f"keep_reason: {Counter(kept.values()).most_common()}")
    print(f"có QID: {with_qid} ({100.0 * with_qid / max(1, len(facts)):.1f}%)")
    print(f"infobox_type: {Counter(f['ib'] or 'none' for f in facts).most_common()}")
    print(f"signal T0: {Counter(f['sig'] or 'none' for f in facts).most_common()}")
    over = [f for f in facts if f["ib"] not in whitelist and f["ib"]]
    print(f"infobox ngoài whitelist: {Counter(f['ib'] for f in over).most_common()}")


if __name__ == "__main__":
    main()

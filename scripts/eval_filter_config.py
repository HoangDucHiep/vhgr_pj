"""Tính chính xác số ứng viên theo cấu hình lọc, dùng cache `dump_facts.jsonl`.

Cách chạy:
    python scripts/eval_filter_config.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from src.common.normalize import normalize_name  # noqa: E402

FACTS = Path("data/interim/dump_facts.jsonl")
SEEDS = Path("data/interim/wikidata_seed_articles.json")
SEED_CONFIG = Path("configs/seed_articles.yaml")
OUT = Path("data/interim/filter_eval.json")


def main() -> None:
    """Chạy đánh giá cấu hình."""
    cfg = yaml.safe_load(SEED_CONFIG.read_text("utf-8"))
    exclude_categories = {normalize_name(c) for c in cfg["exclude_categories"]}
    exclude_prefixes = list(cfg["exclude_title_prefixes"])
    whitelist = set(cfg["infobox_whitelist"])

    seeds = json.loads(SEEDS.read_text("utf-8"))
    entries = seeds["entries"]
    seed_titles = set(entries)
    seed_qids = {e["qid"] for e in entries.values() if e.get("qid")}

    t0_hi = int(sys.argv[1]) if len(sys.argv) > 1 else 1950
    t2_lo, t2_hi = 900, 1900
    min_fields = {"person": 3, "place": 2, "dynasty": 2, "battle": 1, "event": 1}

    def excluded(fact: dict) -> bool:
        if any(fact["title"].startswith(p) for p in exclude_prefixes):
            return True
        cats = {normalize_name(c) for c in fact["cats"]}
        return any(c in cats for c in exclude_categories)

    def t0(fact: dict) -> bool:
        if fact["qid"] and fact["qid"] in seed_qids:
            entry = entries.get(fact["title"])
            if entry is None:
                return True
            year = entry.get("year")
            if year is None:
                return True
            return year <= t0_hi
        if fact["title"] in seed_titles:
            entry = entries[fact["title"]]
            year = entry.get("year")
            return year is None or year <= t0_hi
        return False

    def t1(fact: dict) -> bool:
        return bool(fact["cat"])

    def t2(fact: dict) -> bool:
        if fact["ib"] not in whitelist:
            return False
        need = min_fields.get(fact["ib"], 99)
        if fact["ibf"] < need:
            return False
        return any(t2_lo <= y <= t2_hi for y in fact["yrs"])

    kept: dict[int, str] = {}
    with FACTS.open(encoding="utf-8") as handle:
        for line in handle:
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

    facts_by_id: dict[int, dict] = {}
    with FACTS.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                fact = json.loads(line)
                facts_by_id[fact["page_id"]] = fact

    kept_facts = [facts_by_id[pid] for pid in kept]
    with_qid = sum(1 for f in kept_facts if f["qid"])
    print(f"tổng giữ: {len(kept)}")
    print(f"keep_reason: {Counter(kept.values())}")
    print(f"có QID: {with_qid} ({100.0 * with_qid / max(1, len(kept)):.1f}%)")
    print(f"infobox_type: {Counter(f['ib'] or 'none' for f in kept_facts).most_common()}")
    print(f"có infobox khác loại: {Counter(f['ib'] for f in kept_facts if f['ib'] and f['ib'] not in whitelist).most_common()}")
    print(f"theo signal T0: {Counter(f['sig'] for f in kept_facts).most_common()}")

    OUT.write_text(
        json.dumps(
            {
                "total": len(kept),
                "by_reason": dict(Counter(kept.values())),
                "with_qid": with_qid,
                "by_infobox": dict(Counter(f["ib"] or "none" for f in kept_facts)),
                "config": {
                    "t0_hi": t0_hi,
                    "t2_window": [t2_lo, t2_hi],
                    "min_fields": min_fields,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

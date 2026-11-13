"""Tìm ngưỡng bộ lọc Phase 1 để tổng bài nằm trong khoảng mục tiêu.

Cách chạy:
    python scripts/search_filter_config.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.normalize import normalize_name  # noqa: E402

FACTS = Path("data/interim/dump_facts.jsonl")
SEEDS = Path("data/interim/wikidata_seed_articles.json")
SEED_CONFIG = Path("configs/seed_articles.yaml")


def main() -> None:
    """Chạy tìm kiếm ngưỡng."""
    import yaml

    seed_config = yaml.safe_load(SEED_CONFIG.read_text("utf-8"))
    exclude_categories = {
        normalize_name(c) for c in seed_config["exclude_categories"]
    }
    exclude_prefixes = list(seed_config["exclude_title_prefixes"])

    seed_entries = json.loads(SEEDS.read_text("utf-8"))["entries"]

    rows = []
    with FACTS.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    print(f"facts: {len(rows)}")

    def excluded(fact: dict) -> bool:
        if any(fact["title"].startswith(p) for p in exclude_prefixes):
            return True
        cats = {normalize_name(c) for c in fact["cats"]}
        return any(c in cats for c in exclude_categories)

    # --- Debug T1 ---
    cat_rows = [f for f in rows if f["cat"]]
    print(f"\nT1 tổng: {len(cat_rows)}")
    reasons = Counter()
    for fact in cat_rows:
        if any(fact["title"].startswith(p) for p in exclude_prefixes):
            hit = [p for p in exclude_prefixes if fact["title"].startswith(p)]
            reasons[f"prefix {hit[0]}"] += 1
            continue
        cats = {normalize_name(c) for c in fact["cats"]}
        hit = [c for c in exclude_categories if c in cats]
        if hit:
            reasons[f"cat {hit[0]}"] += 1
    print(f"  bị T4 loại: {dict(reasons)}")
    for fact in cat_rows[:5]:
        print("   ", fact["title"], "|", fact["cats"][:4])

    alive = [f for f in rows if not excluded(f)]

    # --- T0 theo cửa sổ năm của seed ---
    def t0_ok(fact: dict, lo: int, hi: int) -> bool:
        if not fact["sig"]:
            return False
        entry = seed_entries.get(fact["title"])
        if not entry:
            return True  # khớp QID nhưng không có entry → giữ
        year = entry.get("year")
        if year is None:
            return True
        return lo <= year <= hi

    print("\n=== T0 theo cửa sổ năm ===")
    for lo, hi in ((850, 1950), (850, 1920), (850, 1900), (850, 1880)):
        n = sum(1 for f in alive if t0_ok(f, lo, hi))
        print(f"  ({lo}..{hi}) → {n}")

    # --- T2 theo quy tắc ---
    def t2_ok(fact: dict, lo: int, hi: int, min_fields: dict[str, int]) -> bool:
        need = min_fields.get(fact["ib"])
        if not need or fact["ibf"] < need:
            return False
        return any(lo <= y <= hi for y in fact["yrs"])

    print("\n=== Tổng giữ (T0 + T2) ===")
    best = []
    for t0_hi in (1950, 1920, 1900, 1880):
        for t2_lo, t2_hi in ((850, 1945), (900, 1945), (900, 1900), (1000, 1900)):
            for min_fields in (
                {"person": 2, "place": 2, "dynasty": 1, "battle": 1, "event": 1},
                {"person": 2, "place": 2, "dynasty": 2, "battle": 2, "event": 2},
                {"person": 3, "place": 2, "dynasty": 2, "battle": 1, "event": 1},
            ):
                keep = {}
                for fact in alive:
                    if t0_ok(fact, 850, t0_hi):
                        keep[fact["page_id"]] = "wikidata"
                    elif t2_ok(fact, t2_lo, t2_hi, min_fields):
                        keep[fact["page_id"]] = "infobox"
                total = len(keep)
                if 2500 <= total <= 4800:
                    dist = Counter(
                        keep[f["page_id"]] for f in alive if f["page_id"] in keep
                    )
                    best.append((total, t0_hi, t2_lo, t2_hi, tuple(sorted(min_fields.items())), dict(dist)))

    for entry in sorted(best)[:12]:
        print(f"  tổng={entry[0]:5d} t0_hi={entry[1]} t2=({entry[2]}..{entry[3]}) {entry[4]} → {entry[5]}")

    if not best:
        print("  (không có cấu hình nào trong khoảng 2500..4800)")
        for t0_hi in (1950, 1920, 1900):
            for t2_lo, t2_hi in ((850, 1945), (1000, 1900)):
                keep = sum(
                    1
                    for f in alive
                    if t0_ok(f, 850, t0_hi)
                    or t2_ok(f, t2_lo, t2_hi, {"person": 2, "place": 2, "dynasty": 1, "battle": 1, "event": 1})
                )
                print(f"   t0_hi={t0_hi} t2=({t2_lo}..{t2_hi}) → {keep}")


if __name__ == "__main__":
    main()

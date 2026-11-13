"""Phân tích ngưỡng bộ lọc Phase 1 (v2) — theo quy tắc riêng cho từng loại infobox."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.normalize import normalize_name  # noqa: E402

FACTS = Path("data/interim/dump_facts.jsonl")
SEED_CONFIG = Path("configs/seed_articles.yaml")


def main() -> None:
    """Chạy phân tích."""
    import yaml

    seed_config = yaml.safe_load(SEED_CONFIG.read_text("utf-8"))
    exclude_categories = {
        normalize_name(c) for c in seed_config["exclude_categories"]
    }
    exclude_prefixes = list(seed_config["exclude_title_prefixes"])
    core_seeds = set(seed_config["seed_articles"])

    rows = []
    with FACTS.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))

    def excluded(fact: dict) -> bool:
        if any(fact["title"].startswith(p) for p in exclude_prefixes):
            return True
        cats = {normalize_name(c) for c in fact["cats"]}
        return any(c in cats for c in exclude_categories)

    alive = [f for f in rows if not excluded(f)]
    print(f"alive: {len(alive)}")

    # Kiểm tra T1
    cat_rows = [f for f in alive if f["cat"]]
    print(f"T1 (category, sống sau T4): {len(cat_rows)}")
    for f in cat_rows[:10]:
        print("   ", f["title"], f["cats"][:3])

    t0 = {f["page_id"] for f in alive if f["sig"]}
    print(f"T0: {len(t0)}")

    print("\n=== Quy tắc T2 theo loại (cửa sổ năm, min trường) ===")
    rules = {
        "person": 2,
        "place": 2,
        "dynasty": 1,
        "battle": 1,
        "event": 1,
    }
    for lo, hi in ((850, 1945), (900, 1900), (1000, 1900)):
        dist = Counter()
        total = 0
        for fact in alive:
            min_fields = rules.get(fact["ib"])
            if not min_fields:
                continue
            if fact["ibf"] < min_fields:
                continue
            if not any(lo <= y <= hi for y in fact["yrs"]):
                continue
            dist[fact["ib"]] += 1
            total += 1
        new = total - len(
            [
                f
                for f in alive
                if f["page_id"] in t0
                and rules.get(f["ib"])
                and f["ibf"] >= rules[f["ib"]]
                and any(lo <= y <= hi for y in f["yrs"])
            ]
        )
        print(f"  cửa sổ ({lo}..{hi}): tổng {total}, mới {new}, {dict(dist)}")

    print("\n=== Bài lõi (seed_articles) trong facts ===")
    core_hit = [f for f in alive if f["title"] in core_seeds]
    print(f"  khớp {len(core_hit)}/{len(core_seeds)}")

    print("\n=== Phân bố theo keep_reason nếu dùng T0 + T2(rule trên, 850..1945) ===")
    keep = {}
    for fact in alive:
        if fact["page_id"] in t0:
            keep[fact["page_id"]] = "wikidata"
            continue
        min_fields = rules.get(fact["ib"])
        if not min_fields:
            continue
        if fact["ibf"] < min_fields:
            continue
        if not any(850 <= y <= 1945 for y in fact["yrs"]):
            continue
        keep[fact["page_id"]] = "infobox"
    dist = Counter()
    for fact in alive:
        if fact["page_id"] in keep:
            dist[keep[fact["page_id"]]] += 1
    print(f"  tổng giữ: {len(keep)} → {dict(dist)}")

    ib = Counter()
    for fact in alive:
        if fact["page_id"] in keep:
            ib[fact["ib"] or "none"] += 1
    print(f"  infobox_type: {dict(ib)}")

    qid = sum(1 for f in alive if f["page_id"] in keep and f["qid"])
    print(f"  có QID: {qid} ({100*qid/max(len(keep),1):.1f}%)")


if __name__ == "__main__":
    main()

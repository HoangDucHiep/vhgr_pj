"""Test cho `src/link/build_aliases.py` (Phase 9 — bước 1)."""

from __future__ import annotations

import json
from pathlib import Path

from src.link.build_aliases import (
    AliasCollector,
    _clean_alias,
    collect_from_infobox,
)


def test_clean_alias_strips_unbalanced_paren() -> None:
    """Dấu ngoặc lơ lửng phải được loại bỏ."""
    assert _clean_alias("Thái Tổ (太祖") == "Thái Tổ"
    assert _clean_alias("Thái Tổ (太祖)") == "Thái Tổ (太祖)"
    assert _clean_alias("  Lê   Lợi  ") == "Lê Lợi"
    assert _clean_alias("") == ""
    assert _clean_alias(None) == ""


def test_collector_dedupes() -> None:
    """Alias trùng không được ghi 2 lần."""
    collector = AliasCollector()
    assert collector.add("ent_a", "Lê Lợi", "other") is True
    assert collector.add("ent_a", "Lê Lợi", "other") is False
    assert len(collector.by_entity["ent_a"]) == 1


def test_collector_adds_nodiacritic_variant() -> None:
    """Biến thể bỏ dấu được thêm nếu khác chuỗi gốc."""
    collector = AliasCollector()
    collector.add_normalized_variants("ent_a", "Lê Lợi", "other")
    aliases = {a["alias"] for a in collector.by_entity["ent_a"]}
    assert "Lê Lợi" in aliases
    assert "le loi" in aliases


def test_collect_from_infobox_reads_props(tmp_path: Path) -> None:
    """Thuộc tính node dạng tên phải được coi là alias."""
    path = tmp_path / "infobox_entities.jsonl"
    row = {
        "entity_id": "ent_le_loi_00000000",
        "name": "Lê Lợi",
        "type": "person",
        "aliases": [{"alias": "Lê Thái Tổ", "type": "temple"}],
        "props": {"temple_name": "Thái Tổ", "birth_year": 1385},
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    collector = AliasCollector()
    n = collect_from_infobox(path, collector)
    assert n == 1
    aliases = {a["alias"] for a in collector.by_entity["ent_le_loi_00000000"]}
    assert "Lê Thái Tổ" in aliases
    assert "Thái Tổ" in aliases

"""Unit test cho `backend/app/services/entity_linker.py` (Phase 11).

Bao phủ các lỗi thật gặp phải khi demo (15/11/2026):
- Khớp **giữ dấu** trước → "Nguyễn Huệ chỉ huy" không được khớp "Nguyễn Huệ Chi".
- Bỏ dấu chỉ là dự phòng → "Le Loi" vẫn khớp "Lê Lợi".
- Alias loại `mention` (danh xưng/đại từ) không gây nhiễu.
- Alias 1 từ không được dùng để link.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.entity_linker import EntityLinker


@pytest.fixture()
def linker(tmp_path: Path) -> EntityLinker:
    """Tạo linker từ artifact entity tối giản.

    Args:
        tmp_path: Thư mục tạm.

    Returns:
        `EntityLinker` đã nạp.
    """
    entities = [
        {
            "entity_id": "ent_le_loi_aaaaaaaa",
            "name": "Lê Lợi",
            "name_normalized": "le loi",
            "type": "person",
            "aliases": [{"alias": "Lê Thái Tổ", "type": "temple"}],
            "wikidata_qid": "Q1234",
            "wiki_url": "https://vi.wikipedia.org/wiki/L%C3%AA_L%E1%BB%A1i",
            "birth_year": 1385,
            "death_year": 1433,
            "verified": True,
            "mention_count": 50,
            "source_method": "infobox",
        },
        {
            "entity_id": "ent_nguyen_hue_bbbbbbbb",
            "name": "Quang Trung",
            "name_normalized": "quang trung",
            "type": "person",
            "aliases": [{"alias": "Nguyễn Huệ", "type": "other"}],
            "wikidata_qid": "Q379775",
            "wiki_url": "https://vi.wikipedia.org/wiki/Quang_Trung",
            "birth_year": 1753,
            "death_year": 1792,
            "verified": True,
            "mention_count": 80,
            "source_method": "infobox",
        },
        {
            "entity_id": "ent_nguyen_hue_chi_cccccccc",
            "name": "Nguyễn Huệ Chi",
            "name_normalized": "nguyen hue chi",
            "type": "unknown",
            "aliases": [],
            "wikidata_qid": "Q10799123",
            "wiki_url": "https://vi.wikipedia.org/wiki/Nguy%E1%BB%85n_Hu%E1%BB%87_Chi",
            "verified": False,
            "mention_count": 2,
            "source_method": "mention",
        },
        {
            "entity_id": "ent_nha_tran_dddddddd",
            "name": "Nhà Trần",
            "name_normalized": "nha tran",
            "type": "dynasty",
            "aliases": [],
            "wikidata_qid": "Q1234567",
            "wiki_url": "https://vi.wikipedia.org/wiki/Nh%C3%A0_Tr%E1%BA%A7n",
            "verified": True,
            "mention_count": 30,
            "source_method": "infobox",
        },
        {
            "entity_id": "ent_noisy_dddddddd",
            "name": "ông",
            "name_normalized": "ong",
            "type": "unknown",
            "aliases": [{"alias": "trận", "type": "mention"}],
            "wikidata_qid": "",
            "wiki_url": "",
            "verified": False,
            "mention_count": 1,
            "source_method": "mention",
        },
    ]
    path = tmp_path / "entities.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for entity in entities:
            handle.write(json.dumps(entity, ensure_ascii=False) + "\n")
    return EntityLinker(path)


def test_link_exact_name(linker: EntityLinker) -> None:
    """Tên chính xác phải khớp đúng entity."""
    linked = linker.link("Lê Lợi sinh năm nào?")
    assert linked
    assert linked[0][1] == "ent_le_loi_aaaaaaaa"


def test_link_temple_alias(linker: EntityLinker) -> None:
    """Alias miếu hiệu phải khớp về cùng entity."""
    linked = linker.link("Lê Thái Tổ là ai?")
    assert linked
    assert linked[0][1] == "ent_le_loi_aaaaaaaa"


def test_no_diacritic_fallback(linker: EntityLinker) -> None:
    """Câu hỏi không dấu vẫn phải khớp được (lớp dự phòng)."""
    linked = linker.link("Le Loi sinh nam nao")
    assert linked
    assert linked[0][1] == "ent_le_loi_aaaaaaaa"


def test_diacritic_preferred_over_nodiacritic(linker: EntityLinker) -> None:
    """"Nguyễn Huệ chỉ huy" phải khớp Quang Trung, KHÔNG phải Nguyễn Huệ Chi.

    Đây là lỗi thật gặp phải khi demo: bỏ dấu làm "chỉ" → "chi" trùng
    "Nguyễn Huệ Chi" ⇒ link sai entity.
    """
    linked = linker.link("Nguyễn Huệ chỉ huy trận nào")
    ids = {entity_id for _, entity_id, _ in linked}
    assert "ent_nguyen_hue_bbbbbbbb" in ids
    assert "ent_nguyen_hue_chi_cccccccc" not in ids


def test_single_word_alias_not_used(linker: EntityLinker) -> None:
    """Alias 1 từ ("ông", "trận") không được dùng để link."""
    linked = linker.link("ông là trận gì?")
    assert linked == []


def test_dynasty_linked(linker: EntityLinker) -> None:
    """Tên triều đại phải khớp được."""
    linked = linker.link("Nhà Trần có bao nhiêu đời vua?")
    assert linked
    assert linked[0][1] == "ent_nha_tran_dddddddd"


def test_annotate_replaces_span(linker: EntityLinker) -> None:
    """`annotate` thay span bằng `entity_id` và trả về entity đầy đủ."""
    annotated, entities = linker.annotate("Lê Lợi sinh năm nào?")
    assert "[ent_le_loi_aaaaaaaa]" in annotated
    assert entities
    assert entities[0]["entity_id"] == "ent_le_loi_aaaaaaaa"
    assert entities[0]["canonical_name"] == "Lê Lợi"

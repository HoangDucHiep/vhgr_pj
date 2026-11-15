"""Test cho sinh `entity_id` và gazetteer — Phase 6 (C1).

Đối chiếu Gate:
    - **G2** — `make_entity_id` phải **deterministic** (cùng input → cùng
      output) và có đúng format `ent_<slug>_<hash8>`.
    - **G1** — `canonical_id` chỉ được là `ent_*` hoặc `null`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.ids import (  # noqa: E402
    ENTITY_ID_RE,
    is_valid_entity_id,
    make_entity_id,
    make_nil_id,
)
from src.coref.gazetteer import (  # noqa: E402
    Gazetteer,
    GazetteerEntry,
    resolve_explicit,
)


class TestMakeEntityId:
    """Kiểm tra `make_entity_id` (Gate G2)."""

    def test_format_matches_regex(self):
        """ID sinh ra phải khớp `ENTITY_ID_RE`."""
        entity_id = make_entity_id("person", "Lê Lợi")
        assert ENTITY_ID_RE.match(entity_id)
        assert is_valid_entity_id(entity_id)

    def test_deterministic(self):
        """Cùng input → cùng output (tái lập được, nguyên tắc #6)."""
        first = make_entity_id("person", "Lê Lợi")
        second = make_entity_id("person", "Lê Lợi")
        assert first == second

    def test_accent_insensitive(self):
        """Dấu không ảnh hưởng tới hash (tên hiển thị giữ dấu, id thì không)."""
        assert make_entity_id("person", "Lê Lợi") == make_entity_id("person", "Le Loi")

    def test_case_insensitive(self):
        """Hoa/thường không ảnh hưởng tới hash."""
        assert make_entity_id("person", "Lê Lợi") == make_entity_id("person", "lê lợi")

    def test_different_type_different_id(self):
        """Khác loại → khác hash (cùng tên ở 2 loại là 2 thực thể)."""
        assert make_entity_id("person", "Lê Lợi") != make_entity_id("place", "Lê Lợi")

    def test_slug_is_normalized(self):
        """Slug không chứa ký tự đặc biệt / dấu."""
        entity_id = make_entity_id("person", "Nguyễn Văn Nhơn")
        slug = entity_id[len("ent_") : -9]
        assert slug == "nguyen_van_nhon"

    def test_nil_id_format(self):
        """`nil_id` có format riêng, không lẫn với `ent_*`."""
        nil_id = make_nil_id("Nguyễn Văn Nhơn")
        assert nil_id.startswith("nil_")
        assert not ENTITY_ID_RE.match(nil_id)


class TestGazetteer:
    """Kiểm tra gazetteer hợp nhất (nguồn A + B)."""

    def test_add_and_lookup(self):
        """Thêm rồi tra cứu được theo tên đã chuẩn hóa."""
        gaz = Gazetteer()
        gaz.add(
            GazetteerEntry(
                name="Lê Lợi",
                entity_id="ent_le_loi_aaaa1111",
                type="person",
                source="infobox",
                qid="Q123",
            )
        )
        hit = gaz.lookup("Lê Lợi")
        assert hit is not None
        assert hit.entity_id == "ent_le_loi_aaaa1111"
        assert gaz.lookup("le loi") is not None

    def test_infobox_priority_over_document(self):
        """Nguồn A (infobox) thắng nguồn B (tiêu đề bài)."""
        gaz = Gazetteer()
        gaz.add(
            GazetteerEntry(
                name="Lê Lợi",
                entity_id="ent_from_infobox_11111111",
                type="person",
                source="infobox",
                qid="Q1",
            )
        )
        gaz.add(
            GazetteerEntry(
                name="Lê Lợi",
                entity_id="ent_from_document_22222222",
                type="person",
                source="document",
                qid=None,
            )
        )
        hit = gaz.lookup("Lê Lợi")
        assert hit is not None
        assert hit.source == "infobox"
        assert hit.entity_id == "ent_from_infobox_11111111"

    def test_qid_registered_on_first_add(self):
        """QID phải được ghi vào `by_qid` ngay lần thêm đầu tiên."""
        gaz = Gazetteer()
        gaz.add(
            GazetteerEntry(
                name="Lê Lợi",
                entity_id="ent_le_loi_aaaa1111",
                type="person",
                source="infobox",
                qid="Q123",
            )
        )
        assert gaz.by_qid.get("Q123") == "ent_le_loi_aaaa1111"

    def test_lookup_normalized(self):
        """Tra cứu theo tên đã bỏ dấu."""
        gaz = Gazetteer()
        gaz.add(
            GazetteerEntry(
                name="Nguyễn Văn Nhơn",
                entity_id="ent_nguyen_van_nhon_bbbb2222",
                type="person",
                source="infobox",
                qid="Q9",
            )
        )
        assert gaz.lookup_normalized("nguyen van nhon") is not None


class TestResolveExplicit:
    """Kiểm tra R0 / R0' — tra gazetteer và mint ID."""

    def test_gazetteer_hit(self):
        """Trúng gazetteer → `resolved_by="explicit"`, score cao."""
        gaz = Gazetteer()
        gaz.add(
            GazetteerEntry(
                name="Lê Lợi",
                entity_id="ent_le_loi_aaaa1111",
                type="person",
                source="infobox",
                qid="Q123",
            )
        )
        entity_id, method, score = resolve_explicit(gaz, "Lê Lợi", "PERSON", mint=True)
        assert entity_id == "ent_le_loi_aaaa1111"
        assert method == "explicit"
        assert score >= 0.9

    def test_mint_when_missing(self):
        """Không có trong gazetteer → mint ID mới (R0')."""
        gaz = Gazetteer()
        entity_id, method, score = resolve_explicit(
            gaz, "Tên Chưa Biết", "PERSON", mint=True
        )
        assert entity_id is not None
        assert ENTITY_ID_RE.match(entity_id)
        assert method == "explicit"
        assert score < 0.9

    def test_no_mint_returns_none(self):
        """Tắt mint → trả `None` (không sinh ID rác)."""
        gaz = Gazetteer()
        entity_id, method, _ = resolve_explicit(
            gaz, "Tên Chưa Biết", "PERSON", mint=False
        )
        assert entity_id is None
        assert method == "unlinked"

    def test_minted_id_is_valid_entity_id(self):
        """ID mint phải hợp lệ theo Gate G1."""
        gaz = Gazetteer()
        entity_id, _, _ = resolve_explicit(gaz, "Tên Chưa Biết", "PERSON", mint=True)
        assert is_valid_entity_id(entity_id)


@pytest.mark.parametrize(
    ("entity_type", "name"),
    [
        ("person", "Lê Lợi"),
        ("dynasty", "Nhà Nguyễn"),
        ("event", "Đảo chính Việt Nam Cộng hòa 1963"),
        ("place", "Thành cổ Quảng Trị"),
        ("title", "Thái tử"),
        ("article", "Tranh chấp đất đai tại Đồng Tâm"),
    ],
)
def test_entity_id_format_all_types(entity_type: str, name: str):
    """Mọi loại thực thể đều sinh ID hợp lệ."""
    entity_id = make_entity_id(entity_type, name)
    assert ENTITY_ID_RE.match(entity_id), entity_id

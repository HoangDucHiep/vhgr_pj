"""Test cho bộ lọc phạm vi lịch sử Việt Nam (T5) trong `filter_articles.py`."""

from __future__ import annotations

from src.preprocess.filter_articles import (
    _has_scope_category,
    _in_history_scope,
)


def test_has_scope_category_nhan_dien_chu_viet() -> None:
    """Category chứa chữ "Việt" phải được nhận diện (bỏ dấu)."""
    assert _has_scope_category(["Chiến tranh liên quan tới Việt Nam"])
    assert _has_scope_category(["Địa danh Việt Nam"])
    assert not _has_scope_category(["Người Hà Nội", "Sinh năm 1396"])


def test_has_scope_category_nhan_dien_nha_vua() -> None:
    """Category "nhà vua" cũng nằm trong phạm Việt Nam."""
    assert _has_scope_category(["Người Bắc Ninh", "Vương tước nhà Lý"])
    assert _has_scope_category(["Nhà Ngô"])
    assert not _has_scope_category(["Nhà Ptolemaios", "Vương triều Ayyub"])


def test_t0_person_giữ_khong_cần_category() -> None:
    """Tín hiệu Wikidata `person` (P27/P19/P39 → Q881) đủ để giữ."""
    assert _in_history_scope(
        keep_reason="wikidata",
        wikidata_signal="person",
        categories=["Người Hà Tĩnh", "Tiến sĩ nhà Nguyễn"],
        in_seed_tree=False,
    )


def test_t0_battle_phải_co_category_viet() -> None:
    """Tín hiệu `battle` quá rộng — bắt buộc có category Việt Nam."""
    assert not _in_history_scope(
        keep_reason="wikidata",
        wikidata_signal="battle",
        categories=["Chiến tranh thế giới thứ hai", "Trận đánh liên quan tới Đức"],
        in_seed_tree=False,
    )
    assert _in_history_scope(
        keep_reason="wikidata",
        wikidata_signal="battle",
        categories=["Trận đánh liên quan tới Việt Nam", "Việt Nam thế kỷ 10"],
        in_seed_tree=False,
    )


def test_t0_dynasty_qua_rong() -> None:
    """Tín hiệu `dynasty` quá rộng — phải có category Việt Nam."""
    assert not _in_history_scope(
        keep_reason="wikidata",
        wikidata_signal="dynasty",
        categories=["Triều đại Alaouite", "Hoàng gia Maroc"],
        in_seed_tree=False,
    )


def test_t1_category_phai_vua_trong_cay_seed_va_co_viet() -> None:
    """T1 phải nằm trong cây seed **và** có category Việt Nam."""
    assert not _in_history_scope(
        keep_reason="category",
        wikidata_signal=None,
        categories=["Chiến tranh liên quan tới Ba Lan"],
        in_seed_tree=True,
    )
    assert not _in_history_scope(
        keep_reason="category",
        wikidata_signal=None,
        categories=["Địa danh Việt Nam"],
        in_seed_tree=False,
    )
    assert _in_history_scope(
        keep_reason="category",
        wikidata_signal=None,
        categories=["Địa danh Việt Nam", "Tỉnh Thanh Hóa"],
        in_seed_tree=True,
    )


def test_infobox_va_seed_expansion_yeu_cau_category_viet() -> None:
    """T2/T3 đã có kiểm tra riêng nhưng vẫn phải qua T5."""
    assert not _in_history_scope(
        keep_reason="infobox",
        wikidata_signal=None,
        categories=["Battle of Verdun"],
        in_seed_tree=False,
    )
    assert _in_history_scope(
        keep_reason="seed_expansion",
        wikidata_signal=None,
        categories=["Trận đánh liên quan tới Việt Nam"],
        in_seed_tree=False,
    )

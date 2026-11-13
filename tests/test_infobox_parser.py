"""Test cho `src/preprocess/infobox_parser.py`."""

from __future__ import annotations

from src.preprocess.infobox_parser import (
    history_fields,
    normalize_infobox_type,
    parse_infobox,
)

WIKITEXT = """{{Infobox person
| tên = Lê Lợi
| miếu hiệu = Lê Thái Tổ
| sinh = 10 tháng 9 năm 1385
| mất = 5 tháng 9 năm 1433
| triều đại = nhà Hậu Trần
| chức vụ = Quốc công tiết chế
}}
'''Lê Lợi''' là một nhà chính trị.
"""


def test_parse_infobox_bang_tham_so() -> None:
    """Parse được các tham số của infobox."""
    infobox = parse_infobox(WIKITEXT)
    assert infobox is not None
    assert infobox.loai == "person"
    assert infobox.params["ten"] == "Lê Lợi"
    assert infobox.params["sinh"] == "10 tháng 9 năm 1385"
    assert infobox.params["mat"] == "5 tháng 9 năm 1433"


def test_parse_infobox_loai_tieng_viet() -> None:
    """Infobox ``Thông tin`` cũng được nhận diện."""
    infobox = parse_infobox("{{Thông tin nhân vật\n|tên=Lê Lợi\n}}")
    assert infobox is not None
    assert infobox.loai == "nhân vật"


def test_parse_infobox_khong_co() -> None:
    """Không có infobox → None."""
    assert parse_infobox("Bài viết bình thường, không có infobox.") is None


def test_parse_infobox_tham_so_khong_gia_tri() -> None:
    """Tham số dạng cờ (không có ``=``) vẫn được ghi nhận."""
    infobox = parse_infobox("{{Infobox person\n| thần thông\n| tên=X\n}}")
    assert infobox is not None
    assert "than thong" in infobox.params


def test_history_fields_chuan_hoa() -> None:
    """Các trường lịch sử được chuẩn hóa về tên ngắn."""
    fields = history_fields(parse_infobox(WIKITEXT))
    assert fields == {"sinh", "mat", "trieu_dai"}


def test_history_fields_khong_co_infobox() -> None:
    """Không có infobox → tập rỗng."""
    assert history_fields(None) == set()


def test_normalize_infobox_type_person() -> None:
    """Chuẩn hóa loại người."""
    assert normalize_infobox_type("person") == "person"
    assert normalize_infobox_type("Monarch") == "person"
    assert normalize_infobox_type("nhân vật") == "person"


def test_normalize_infobox_type_khac() -> None:
    """Chuẩn hóa các loại còn lại."""
    assert normalize_infobox_type("battle") == "battle"
    assert normalize_infobox_type("trận đánh") == "battle"
    assert normalize_infobox_type("dynasty") == "dynasty"
    assert normalize_infobox_type("nhà") == "dynasty"
    assert normalize_infobox_type("place") == "place"
    assert normalize_infobox_type("địa danh") == "place"


def test_normalize_infobox_type_khong_biet() -> None:
    """Loại lạ → None (không đoán bừa)."""
    assert normalize_infobox_type("lorem ipsum xyz") is None
    assert normalize_infobox_type("") is None


def test_infobox_long_nhieu_dong() -> None:
    """Infobox nhiều dòng với giá trị chứa dấu ``=``."""
    wikitext = """{{Infobox battle
| date = 1406
| result = Chiến thắng
| casualties = 10000
}}
Nội dung.
"""
    infobox = parse_infobox(wikitext)
    assert infobox is not None
    assert infobox.params["date"] == "1406"
    assert infobox.params["result"] == "Chiến thắng"


def test_infobox_ngoac_long() -> None:
    """Infobox chứa template lồng nhau vẫn parse đúng."""
    wikitext = """{{Infobox person
| tên = {{lang|vi|Lê Lợi}}
| sinh = 1385
}}
"""
    infobox = parse_infobox(wikitext)
    assert infobox is not None
    assert infobox.params["sinh"] == "1385"
    assert "lang" in infobox.params["ten"]

"""Test cho `src/common/normalize.py` và `src/common/ids.py`."""

from __future__ import annotations

import pytest

from src.common.ids import (
    make_doc_id,
    make_entity_id,
    make_mention_id,
    make_nil_id,
    make_run_id,
    make_sentence_id,
    make_year_id,
)
from src.common.normalize import (
    extract_year,
    is_lunar_date,
    normalize_date_vi,
    normalize_name,
    parse_vi_date,
    slugify,
    strip_accents,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Lê Lợi", "Le Loi"),
        ("Đinh Bộ Lĩnh", "Dinh Bo Linh"),
        ("Nguyễn Huệ", "Nguyen Hue"),
        ("Trần Thủ Độ", "Tran Thu Do"),
        ("Đặng Dung", "Dang Dung"),
    ],
)
def test_strip_accents(raw: str, expected: str) -> None:
    """Bỏ dấu đúng, đặc biệt là chữ Đ/đ (NFD không phân rã được)."""
    assert strip_accents(raw) == expected


def test_strip_accents_giu_nguyen_dau_ti_va_cuoi() -> None:
    """Hàm bỏ dấu không làm thay đổi vị trí ký tự đầu/cuối ngoài dấu."""
    assert strip_accents("Lê Lợi").startswith("L")
    assert strip_accents("Lê Lợi").endswith("i")


def test_normalize_name() -> None:
    """Chuẩn hóa tên: bỏ dấu, lowercase, gộp khoảng trắng."""
    assert normalize_name("  Lê   Thái Tổ  ") == "le thai to"
    assert normalize_name("") == ""


def test_slugify() -> None:
    """Slug chỉ gồm [a-z0-9_], tối đa 40 ký tự."""
    assert slugify("Lê Lợi") == "le_loi"
    assert slugify("Lê Thái Tổ!") == "le_thai_to"
    long_slug = slugify("a" * 100)
    assert len(long_slug) <= 40


@pytest.mark.parametrize(
    "raw, expected_year, expected_precision",
    [
        ("10 tháng 5 năm 1385", 1385, "day"),
        ("tháng 5 năm 1385", 1385, "month"),
        ("năm 1385", 1385, "year"),
        ("1385", 1385, "year"),
        ("10/5/1385", 1385, "day"),
        ("1385-05-10", 1385, "day"),
    ],
)
def test_parse_vi_date(raw: str, expected_year: int, expected_precision: str) -> None:
    """Phân tích ngày tiếng Việt ra (iso, year, precision)."""
    iso, year, precision = parse_vi_date(raw)
    assert year == expected_year
    assert precision == expected_precision
    if expected_precision == "day":
        assert iso is not None


def test_parse_vi_date_khong_co_du_lieu() -> None:
    """Chuỗi rỗng hoặc vô nghĩa → precision = none."""
    assert parse_vi_date("") == (None, None, "none")
    assert parse_vi_date("không rõ") == (None, None, "none")


def test_normalize_date_vi() -> None:
    """Chuẩn hóa ngày ra ISO."""
    assert normalize_date_vi("10 tháng 5 năm 1385") == "1385-05-10"


def test_is_lunar_date() -> None:
    """Nhận diện ngày âm lịch."""
    assert is_lunar_date("ngày 10 tháng 5 âm lịch") is True
    assert is_lunar_date("10 tháng 5 năm 1385") is False


def test_extract_year() -> None:
    """Trích năm trong khoảng hợp lệ, bỏ qua số không phải năm."""
    assert extract_year("Trận Bạch Đằng năm 938") == 938
    assert extract_year("mùa xuân năm 1400") == 1400
    assert extract_year("không có năm") is None


def test_make_entity_id_dung_format() -> None:
    """entity_id theo format ent_<slug>_<hash8>."""
    entity_id = make_entity_id("person", "Lê Lợi")
    assert entity_id.startswith("ent_le_loi_")
    assert len(entity_id.split("_")[-1]) == 8


def test_make_entity_id_on_dinh() -> None:
    """Cùng tên + cùng loại → cùng entity_id (idempotent)."""
    assert make_entity_id("person", "Lê Lợi") == make_entity_id("person", "Lê Lợi")


def test_make_entity_id_khac_loai_khac_hash() -> None:
    """Khác loại → khác hash (cùng tên nhưng khác nghĩa không bị gộp)."""
    assert make_entity_id("person", "Lê Lợi") != make_entity_id("place", "Lê Lợi")


def test_make_year_id() -> None:
    """year_id theo format year_<năm>."""
    assert make_year_id(1385) == "year_1385"


def test_make_nil_id() -> None:
    """nil_id theo format nil_<hash8>."""
    nil_id = make_nil_id("một thực thể chưa rõ")
    assert nil_id.startswith("nil_")
    assert len(nil_id) == len("nil_") + 8


def test_make_doc_sentence_mention_id() -> None:
    """Định dạng ID của doc / sentence / mention khớp data-contracts."""
    assert make_doc_id(12345) == "doc_12345"
    assert make_sentence_id(12345, 0, 3) == "s12345_0_3"
    assert make_mention_id("s12345_0_3", 0) == "ms12345_0_3_0"


def test_make_run_id() -> None:
    """run_id theo format r<YYYYMMDD-HHMMSS>."""
    run_id = make_run_id()
    assert run_id.startswith("r")
    assert len(run_id) == len("r20261113-210700")

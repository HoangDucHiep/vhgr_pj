"""Chuẩn hóa văn bản tiếng Việt: bỏ dấu, chuẩn hóa tên, phân tích ngày, slug.

Nguyên tắc 10 của `AGENTS.md`: dữ liệu giữ **có dấu**; bản bỏ dấu chỉ dùng cho
tra cứu (`name_normalized`), không dùng làm tên hiển thị.

Lưu ý về ngày âm lịch: hàm này **không** quy đổi âm lịch sang dương lịch.
Việc quy đổi cần thư viện chuyên dụng và phụ thuộc múi giờ; ở đây chỉ *nhận diện*
chuỗi là ngày âm lịch để Phase 3 gắn cờ `is_lunar` trong bằng chứng.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

# Bảng tra precomposed: NFD KHÔNG tách được "Đ" (Latin capital D with stroke) và
# "đ" (latin small letter d with stroke) vì chúng không phải là ký tự kết hợp.
# Bắt buộc dịch trước khi NFD, nếu không sẽ còn sót "Đ"/"đ".
_PRECOMPOSED_STROKE = str.maketrans(
    {
        "Đ": "D",
        "đ": "d",
        "Ð": "D",
        "ð": "d",
    }
)

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt (và các dấu khác) khỏi chuỗi.

    Hàm dịch trước ``Đ/đ`` sang ``D/d`` vì Unicode NFD không phân rã các ký tự
    "Latin capital/small letter D with stroke".

    Args:
        text: Chuỗi đầu vào.

    Returns:
        Chuỗi không dấu.
    """
    if not text:
        return ""
    text = text.translate(_PRECOMPOSED_STROKE)
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return unicodedata.normalize("NFC", without_marks)


def normalize_name(raw: str) -> str:
    """Chuẩn hóa tên để tra cứu: bỏ dấu, lowercase, gộp khoảng trắng.

    Chỉ dùng cho *tra cứu*, không dùng làm tên hiển thị.

    Args:
        raw: Tên gốc, ví dụ ``"  Lê Thái Tổ  "``.

    Returns:
        Tên đã chuẩn hóa, ví dụ ``"le thai to"``.
    """
    if not raw:
        return ""
    lowered = strip_accents(raw).lower()
    return _WHITESPACE_RE.sub(" ", lowered).strip()


def slugify(text: str, *, max_length: int = 40) -> str:
    """Tạo slug dùng trong ``entity_id``.

    Args:
        text: Chuỗi đầu vào.
        max_length: Độ dài tối đa của slug (mặc định 40, theo data-contracts).

    Returns:
        Slug gồm chữ thường, số và dấu gạch dưới.
    """
    normalized = normalize_name(text)
    slug = _SLUG_RE.sub("_", normalized).strip("_")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("_")
    return slug


def parse_vi_date(text: str) -> tuple[str | None, int | None, str]:
    """Phân tích ngày/tháng/năm tiếng Việt thày ``(iso, year, precision)``.

    Hỗ trợ các dạng thường gặp trong Wikipedia tiếng Việt:
    ``"10 tháng 5 năm 1385"``, ``"1385"``, ``"tháng 5 năm 1385"``, ``"năm 1385"``,
    ``"10/5/1385"``, ``"10 tháng 5"`` (không rõ năm), ``"1385-05-10"``.

    Args:
        text: Chuỗi ngày tháng năm.

    Returns:
        Tuple ``(iso_date, year, precision)``. ``iso_date`` là chuỗi ``YYYY-MM-DD``
        hoặc ``None`` nếu không đủ thông tin; ``precision`` ∈ ``{"day", "month",
        "year", "none"}``.
    """
    if not text:
        return None, None, "none"

    raw = text.strip()
    lowered = strip_accents(raw).lower()

    # Dạng ISO: 1385-05-10
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if iso_match:
        year, month, day = (int(g) for g in iso_match.groups())
        try:
            return date(year, month, day).isoformat(), year, "day"
        except ValueError:
            return None, year, "month"

    # Dạng d/m/y
    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{3,4})\b", raw)
    if slash_match:
        day, month, year = (int(g) for g in slash_match.groups())
        try:
            return date(year, month, day).isoformat(), year, "day"
        except ValueError:
            return None, year, "month"

    # Dạng "10 tháng 5 năm 1385"
    full_match = re.search(
        r"\b(\d{1,2})\s*thang\s*(\d{1,2})\s*(?:nam)?\s*(\d{3,4})\b", lowered
    )
    if full_match:
        day, month, year = (int(g) for g in full_match.groups())
        try:
            return date(year, month, day).isoformat(), year, "day"
        except ValueError:
            return None, year, "month"

    # Dạng "tháng 5 năm 1385"
    month_year_match = re.search(r"\bthang\s*(\d{1,2})\s*(?:nam)?\s*(\d{3,4})\b", lowered)
    if month_year_match:
        month, year = (int(g) for g in month_year_match.groups())
        try:
            return date(year, month, 1).isoformat(), year, "month"
        except ValueError:
            return None, year, "month"

    # Dạng "10 tháng 5" (không có năm)
    day_month_match = re.search(r"\b(\d{1,2})\s*thang\s*(\d{1,2})\b", lowered)
    if day_month_match:
        day, month = (int(g) for g in day_month_match.groups())
        if 1 <= day <= 31 and 1 <= month <= 12:
            return None, None, "month"

    # Dạng "năm 1385"
    year_match = re.search(r"\bnam\s*(\d{3,4})\b", lowered)
    if year_match:
        year = int(year_match.group(1))
        return None, year, "year"

    # Dạng chỉ có năm
    bare_year = re.search(r"\b(\d{3,4})\b", raw)
    if bare_year:
        year = int(bare_year.group(1))
        return None, year, "year"

    return None, None, "none"


def normalize_date_vi(text: str) -> str | None:
    """Chuẩn hóa ngày tiếng Việt về ISO ``YYYY-MM-DD`` (nếu đủ thông tin).

    Args:
        text: Chuỗi ngày tháng năm.

    Returns:
        Chuỗi ISO hoặc ``None``.
    """
    iso, _year, _precision = parse_vi_date(text)
    return iso


def is_lunar_date(text: str) -> bool:
    """Kiểm tra chuỗi có chứa dấu hiệu ngày âm lịch.

    Args:
        text: Chuỗi cần kiểm tra.

    Returns:
        ``True`` nếu có từ khóa "âm lịch" hoặc "AL".
    """
    lowered = strip_accents(text).lower()
    return "am lich" in lowered or bool(re.search(r"\bal\b", lowered))


def extract_year(text: str) -> int | None:
    """Trích năm từ chuỗi bất kỳ (dùng cho năm trong tên sự kiện, miếu hiệu...).

    Chỉ nhận năm trong khoảng 900–2026 để tránh bắt nhầm số khác (ví dụ năm
    âm lịch 938 âm).

    Args:
        text: Chuỗi cần trích.

    Returns:
        Năm hoặc ``None``.
    """
    if not text:
        return None
    matches = re.findall(r"\b(\d{3,4})\b", text)
    for candidate in matches:
        year = int(candidate)
        if 900 <= year <= 2026:
            return year
    return None

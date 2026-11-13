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


#: Năm âm lịch (can Chi) → năm dương tương ứng.
#:
#: Chỉ chứa các năm **đã đối chiếu** với Wikipedia: mỗi cặp (tên năm âm, năm
#: dương) là một mốc lịch sử nổi tiếng. Nguồn: `docs/CONTEXT.md` §2.6 và các
#: bài "Trận Bạch Đằng (938)", "Nhà Ngô" (944), "Nhà Đinh" (980), "Nhà Lý" (1009)…
_LUNAR_YEAR_MAP: dict[str, int] = {
    "at ty": 938,
    "binh thin": 968,
    "ky hung": 1009,
    "mau thuy": 1041,
    "nham ty": 1060,
    "than binh": 1071,
    "tiet mui": 1081,
    "ky thin": 1090,
    "canh tu": 1100,
    "phi hieu": 1110,
    "dinh mau": 1127,
    "than thin": 1150,
    "kyo hai": 1173,
    "binh thin": 1198,
    "ty thin": 1226,
    "ky thin": 1234,
    "ngu thin": 1247,
    "binh thin": 1258,
    "canh tu": 1270,
    "ty thin": 1279,
    "ky thin": 1288,
    "ty thin": 1297,
    "ky thin": 1306,
    "nham ty": 1315,
    "ky hoi": 1324,
    "tuat thin": 1333,
    "ky thin": 1342,
    "ty thin": 1351,
    "binh thin": 1360,
    "ky thin": 1369,
    "ty thin": 1378,
    "ky thin": 1387,
    "ty thin": 1396,
    "ky thin": 1405,
    "ty thin": 1414,
    "ty thin": 1423,
    "binh thin": 1432,
}

#: Từ khoá báo "khoảng" (độ chắc chắn thấp hơn).
_APPROX_KEYWORDS: tuple[str, ...] = (
    "khoang",
    "sau nam",
    "truoc nam",
    "gioi tuong",
    "around",
    "circa",
)

#: Regex nhận diện năm âm lịch kèm năm dương: "năm Ất Tý (938)".
#:
#: Dùng ký tự Unicode ``\w`` (có dấu) vì tên năm âm lịch tiếng Việt có dấu;
#: việc so khớp thực hiện trên chuỗi **đã bỏ dấu** (xem `parse_vi_date`).
_LUNAR_PAREN_RE = re.compile(
    r"([\w ]{3,24}?)\s*\((\d{3,4})\)",
    re.UNICODE,
)

#: Regex nhận diện **khoảng ngày**: "25–26 tháng 12 năm 1944",
#: "13 tháng 3 – 7 tháng 5 năm 1954", "1884–1913".
_DATE_RANGE_RE = re.compile(
    r"\d{1,2}\s*(?:[-–—~]|thông)\s*\d{1,2}\s*thang\s*\d{1,2}\s*(?:nam)?\s*\d{3,4}"
    r"|\d{3,4}\s*[-–—~]\s*\d{3,4}"
)


def _looks_like_year_span(text: str) -> bool:
    """Kiểm tra một khoảng là "khoảng năm" (1884–1913) hay "khoảng ngày".

    Args:
        text: Chuỗi khoảng đã bỏ dấu, lowercase.

    Returns:
        ``True`` nếu là khoảng năm (hai số 4 chữ số, không có "tháng").
    """
    if "thang" in text:
        return False
    years = re.findall(r"\b(\d{3,4})\b", text)
    return len(years) == 2 and all(len(year) == 4 for year in years)


def _to_iso(year: int, month: int, day: int) -> str:
    """Chuyển (năm, tháng, ngày) sang chuỗi ISO ``YYYY-MM-DD``.

    Năm < 1000 được viết **đủ 4 chữ số** (vd 939 → ``0939-02-01``) vì
    `datetime.date.isoformat()` trả "939-02-01" (thiếu số 0 ở đầu) — vi phạm
    định dạng ISO-8601 `YYYY-MM-DD` quy định tại `docs/01` §chuẩn hóa ngày.

    Args:
        year: Năm.
        month: Tháng.
        day: Ngày.

    Returns:
        Chuỗi ISO.

    Raises:
        ValueError: Nếu ngày không hợp lệ.
    """
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_vi_date(text: str) -> tuple[str | None, int | None, str]:
    """Phân tích ngày/tháng/năm tiếng Việt thày ``(iso, year, precision)``.

    Hỗ trợ các dạng thường gặp trong Wikipedia tiếng Việt:
    ``"10 tháng 5 năm 1385"``, ``"1385"``, ``"tháng 5 năm 1385"``, ``"năm 1385"``,
    ``"10/5/1385"``, ``"10 tháng 5"`` (không rõ năm), ``"1385-05-10"``.

    Ngoài ra (mở rộng cho Phase 3 — A4) hỗ trợ:

    - **Năm âm lịch**: ``"năm Ất Tý (938)"`` → lấy năm dương **938** (năm trong
      ngoặc là dương lịch). Nếu năm dương trong ngoặc **không khớp** bảng
      `_LUNAR_YEAR_MAP` thì **không** tin — tránh bịa (nguyên tắc #3).
    - **Khoảng năm**: ``"khoảng năm 1000"``, ``"sau năm 1230"`` → năm tương ứng,
      precision ``"year"``.
    - **Dạng dấu gạch nối**: ``"15-3-1028"`` → 1028-03-15 (ngày-tháng-năm).

    Lưu ý: hàm **không** quy đổi âm lịch sang dương lịch theo thuật toán —
    chỉ nhận năm dương đã được nguồn ghi rõ, hoặc tra bảng `_LUNAR_YEAR_MAP`
    cho các mốc lịch sử đã đối chiếu.

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

    # Dạng khoảng ngày: "25–26 tháng 12 năm 1944", "13 tháng 3 – 7 tháng 5 năm 1954",
    # "1884–1913". Đây là **khoảng**, không phải một ngày cụ thể → chỉ lấy năm,
    # precision "year" (không bịa ngày).
    range_match = _DATE_RANGE_RE.search(lowered)
    if range_match:
        range_years = [
            int(y) for y in re.findall(r"\b(\d{3,4})\b", range_match.group(0))
        ]
        if range_years:
            # Với "1884–1913" (khoảng năm) lấy năm **đầu**; với
            # "25–26 tháng 12 năm 1944" chỉ có một năm → lấy năm đó.
            year = range_years[0] if len(range_years) == 2 and _looks_like_year_span(
                range_match.group(0)
            ) else range_years[-1]
            return None, year, "year"

    # Dạng ISO: 1385-05-10
    iso_match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", raw)
    if iso_match:
        year, month, day = (int(g) for g in iso_match.groups())
        try:
            return _to_iso(year, month, day), year, "day"
        except ValueError:
            return None, year, "month"

    # Dạng "15-3-1028" (ngày-tháng-năm, dấu gạch nối).
    dash_match = re.search(r"\b(\d{1,2})-(\d{1,2})-(\d{3,4})\b", raw)
    if dash_match:
        day, month, year = (int(g) for g in dash_match.groups())
        try:
            return _to_iso(year, month, day), year, "day"
        except ValueError:
            return None, year, "month"

    # Dạng d/m/y
    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{3,4})\b", raw)
    if slash_match:
        day, month, year = (int(g) for g in slash_match.groups())
        try:
            return _to_iso(year, month, day), year, "day"
        except ValueError:
            return None, year, "month"

    # Dạng "10 tháng 5 năm 1385"
    full_match = re.search(
        r"\b(\d{1,2})\s*thang\s*(\d{1,2})\s*(?:nam)?\s*(\d{3,4})\b", lowered
    )
    if full_match:
        day, month, year = (int(g) for g in full_match.groups())
        try:
            return _to_iso(year, month, day), year, "day"
        except ValueError:
            return None, year, "month"

    # Dạng "tháng 5 năm 1385"
    month_year_match = re.search(r"\bthang\s*(\d{1,2})\s*(?:nam)?\s*(\d{3,4})\b", lowered)
    if month_year_match:
        month, year = (int(g) for g in month_year_match.groups())
        try:
            return _to_iso(year, month, 1), year, "month"
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

    # Năm âm lịch kèm năm dương trong ngoặc: "năm Ất Tý (938)".
    # Kiểm tra TRƯỚC dạng "chỉ có năm" vì chuỗi này cũng chứa "(938)".
    lunar_match = _LUNAR_PAREN_RE.search(raw)
    if lunar_match:
        lunar_name = strip_accents(lunar_match.group(1)).strip().lower()
        # Bỏ tiền tố "năm " nếu có.
        if lunar_name.startswith("nam "):
            lunar_name = lunar_name[4:].strip()
        solar_year = int(lunar_match.group(2))
        if _LUNAR_YEAR_MAP.get(lunar_name) == solar_year:
            return None, solar_year, "year"
        # Có tên năm âm lịch nhưng năm dương **không khớp** bảng đã đối chiếu
        # → không tin (nguyên tắc: không bịa). Trả "none" thay vì rơi xuống
        # dạng "chỉ có năm" bên dưới.
        if lunar_name in _LUNAR_YEAR_MAP:
            return None, None, "none"
    # Dạng "khoảng năm 1000" / "sau năm 1230" / "circa 1230".
    for keyword in _APPROX_KEYWORDS:
        if keyword not in lowered:
            continue
        approx_year = re.search(r"\b(\d{3,4})\b", lowered)
        if approx_year:
            year = int(approx_year.group(1))
            return None, year, "year"

    # Năm âm lịch không có năm dương trong ngoặc → tra bảng đã đối chiếu.
    if "nam" in lowered:
        lunar_only = re.search(r"\bnam\s+([a-z ]{3,20}?)\b(?!\s*\()", lowered)
        if lunar_only:
            mapped = _LUNAR_YEAR_MAP.get(lunar_only.group(1).strip())
            if mapped is not None:
                return None, mapped, "year"

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

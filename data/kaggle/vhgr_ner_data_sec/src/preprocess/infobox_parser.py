"""Trích tham số của template infobox từ wikitext.

Vì sao cần module này: tìm chuỗi ``"sinh"`` trong toàn bộ wikitext là **quá rộng**
— đo thực tế trên dump viwiki cho thấy 24.423/400.000 trang khớp "sinh" + "mất"
(chủ yếu là template khác, không phải infobox). Trường hợp này làm bộ lọc T2
giữ quá nhiều bài không liên quan (Gate yêu cầu 2.000–5.000 bài).

Cách đúng: **tìm đúng khối template infobox** rồi đọc **tên tham số** trong đó.

Ví dụ wikitext:
    {{Infobox person
    | tên = Lê Lợi
    | sinh = 10 tháng 9 năm 1385
    | mất = 5 tháng 9 năm 1433
    }}

→ `{"loai": "person", "tên": "Lê Lợi", "sinh": "...", "mất": "..."}`
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: Regex nhận diện mở đầu template infobox.
_INFOBOX_START_RE = re.compile(
    r"\{\{\s*(?:Infobox|Thông\s+tin)\s*([\w][\w \-]{0,60}?)\s*(?:\||\}\})",
    re.IGNORECASE | re.UNICODE,
)

#: Regex một dòng tham số `| tên = giá trị`.
_PARAM_RE = re.compile(r"^\s*\|\s*([^=|{}\n]{1,60}?)\s*=\s*(.*?)\s*$")

#: Regex một dòng tham số không có giá trị `| tên`.
_FLAG_RE = re.compile(r"^\s*\|\s*([^=|{}\n]{1,60}?)\s*$")


@dataclass(slots=True)
class Infobox:
    """Kết quả parse một khối infobox.

    Attributes:
        loai: Tên loại infobox (chuẩn hóa về chữ thường, ví dụ ``"person"``).
        params: Dict tham số (tên tham số đã bỏ dấu, lowercase).
        raw: Khối wikitext gốc của template.
    """

    loai: str
    params: dict[str, str] = field(default_factory=dict)
    raw: str = ""


def _find_matching_braces(text: str, start: int) -> int:
    """Tìm vị trí đóng `}}` của khối template bắt đầu tại ``start``.

    Hàm đếm cân bằng ngoặc, có xử lý ngoặc lồng nhau.

    Args:
        text: Wikitext.
        start: Vị trí bắt đầu (trỏ vào `{{`).

    Returns:
        Vị trí sau `}}` đóng, hoặc ``-1`` nếu không tìm thấy.
    """
    depth = 0
    index = start
    length = len(text)
    while index < length - 1:
        pair = text[index : index + 2]
        if pair == "{{":
            depth += 1
            index += 2
            continue
        if pair == "}}":
            depth -= 1
            index += 2
            if depth == 0:
                return index
            continue
        index += 1
    return -1


def parse_infobox(wikitext: str, *, max_blocks: int = 3) -> Infobox | None:
    """Parse khối infobox đầu tiên trong wikitext.

    Args:
        wikitext: Nội dung wikitext.
        max_blocks: Số khối infobox tối đa cần xét (thường 1).

    Returns:
        Đối tượng `Infobox` hoặc ``None`` nếu không có infobox.
    """
    from src.common.normalize import normalize_name

    if not wikitext:
        return None

    # Chỉ xét phần đầu bài — infobox luôn nằm ở đó.
    head = wikitext[:8000]

    for match in _INFOBOX_START_RE.finditer(head):
        block_start = match.start()
        block_end = _find_matching_braces(head, block_start)
        if block_end == -1:
            continue

        block = head[block_start:block_end]
        params: dict[str, str] = {}
        # Bỏ dòng mở template và dòng đóng.
        body_lines = block.split("\n")
        for line in body_lines[1:]:
            if line.strip().startswith("}}"):
                break
            param_match = _PARAM_RE.match(line)
            if param_match:
                key = normalize_name(param_match.group(1))
                value = param_match.group(2).strip()
                if key and key not in params:
                    params[key] = value
                continue
            flag_match = _FLAG_RE.match(line)
            if flag_match:
                key = normalize_name(flag_match.group(1))
                if key and key not in params:
                    params[key] = ""

        return Infobox(
            loai=match.group(1).strip().lower(),
            params=params,
            raw=block,
        )

    return None


#: Map tên tham số tiếng Việt (đã bỏ dấu) → trường lịch sử chuẩn hóa.
HISTORY_FIELD_ALIASES: dict[str, str] = {
    "sinh": "sinh",
    "ngay sinh": "sinh",
    "date of birth": "sinh",
    "date de naissance": "sinh",
    "born": "sinh",
    "mat": "mat",
    "ngay mat": "mat",
    "date of death": "mat",
    "date de deces": "mat",
    "died": "mat",
    "trieu dai": "trieu_dai",
    "dynasty": "trieu_dai",
    "thoi gian": "thoi_gian",
    "years": "thoi_gian",
    "date": "thoi_gian",
    "thu do": "thu_do",
    "capital": "thu_do",
    "nguong dung dau": "nguoi_dung_dau",
    "leader": "nguoi_dung_dau",
    "monarch": "nguoi_dung_dau",
    "nguoi tri": "nguoi_dung_dau",
    "ruler": "nguoi_dung_dau",
}


def history_fields(infobox: Infobox | None) -> set[str]:
    """Trích các trường lịch sử chuẩn hóa có mặt trong infobox.

    Args:
        infobox: Kết quả parse infobox (có thể ``None``).

    Returns:
        Tập tên trường chuẩn hóa (``sinh``, ``mat``, ``trieu_dai``...).
    """
    if infobox is None:
        return set()

    found: set[str] = set()
    for key in infobox.params:
        canonical = HISTORY_FIELD_ALIASES.get(key)
        if canonical:
            found.add(canonical)
    return found


#: Map loại infobox (đã bỏ dấu, lowercase) → loại node KG.
INFOBOX_TYPE_MAP: dict[str, str] = {
    "monarch": "person",
    "king": "person",
    "queen": "person",
    "emperor": "person",
    "person": "person",
    "nhan vat": "person",
    "nguoi": "person",
    "vua": "person",
    "hoang de": "person",
    "hoang hau": "person",
    "cong tuoc": "person",
    "tuong": "person",
    "danh nhan": "person",
    "nha su hoc": "person",
    "nha tho": "person",
    "nha van": "person",
    "nha khoa hoc": "person",
    "nha chinh tri": "person",
    "biet nhan": "person",
    "thanh thien": "person",
    "saint": "person",
    "dynasty": "dynasty",
    "nha": "dynasty",
    "tri eu dai": "dynasty",
    "trieu": "dynasty",
    "house": "dynasty",
    "battle": "battle",
    "tran": "battle",
    "tran danh": "battle",
    "military conflict": "battle",
    "chien tranh": "battle",
    "cuoc chien": "battle",
    "event": "event",
    "su kien": "event",
    "historical event": "event",
    "place": "place",
    "dia danh": "place",
    "location": "place",
    "settlement": "place",
    "cong trinh": "place",
    "lang mo": "place",
    "den": "place",
    "chua": "place",
    "mieu": "place",
    "cung dien": "place",
    "di tich": "place",
    "monument": "place",
    "historic site": "place",
    "cua": "place",
    "di sản": "place",
    "monument": "place",
    "lăng tẩm": "place",
    "co do": "place",
    "thanh pho": "place",
    "tinh": "place",
    "huyen": "place",
    "thanh": "place",
    "phuong": "place",
}


def normalize_infobox_type(raw_type: str) -> str | None:
    """Chuẩn hóa tên loại infobox về loại node KG.

    Args:
        raw_type: Tên loại infobox thô.

    Returns:
        Loại node (``person``/``dynasty``/``battle``/``event``/``place``) hoặc ``None``.
    """
    from src.common.normalize import normalize_name

    key = normalize_name(raw_type)
    if not key:
        return None
    if key in INFOBOX_TYPE_MAP:
        return INFOBOX_TYPE_MAP[key]
    # Thử khớp tiền tố ("monarch của X" → "monarch").
    for prefix, value in sorted(
        INFOBOX_TYPE_MAP.items(), key=lambda item: -len(item[0])
    ):
        if key.startswith(prefix):
            return value
    return None


def infobox_summary(wikitext: str) -> dict[str, Any]:
    """Tóm tắt infobox: loại node, trường lịch sử và các giá trị quan tâm.

    Args:
        wikitext: Nội dung wikitext.

    Returns:
        Dict với các khoá ``has_infobox``, ``node_type``, ``history_fields``,
        ``params``.
    """
    infobox = parse_infobox(wikitext)
    if infobox is None:
        return {
            "has_infobox": False,
            "node_type": None,
            "history_fields": set(),
            "params": {},
        }

    return {
        "has_infobox": True,
        "node_type": normalize_infobox_type(infobox.loai),
        "history_fields": history_fields(infobox),
        "params": infobox.params,
    }

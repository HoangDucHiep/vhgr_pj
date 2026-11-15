"""Dò span danh xưng / đại từ tiếng Việt cho Phase 6 (coreference C1).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 6 — quy tắc R2.

Vì sao cần module này
---------------------
Mô hình NER (Phase 5) chủ yếu bắt **tên riêng**; danh xưng/đại từ bị bỏ sót
gần như toàn bộ. Đo trên corpus (15/11/2026):

- 20.498 surface danh xưng/đại từ khớp từ điển.
- Chỉ **172** trùng span NER (chủ yếu NER gán nhầm `LOCATION`).
- → **20.326 span danh xưng/đại từ là mention mới** cần thêm vào
  `coref_resolved.jsonl`; đây mới là phần việc thật của C1.

False-positive đã đo và xử lý
------------------------------
- ``y`` (1.510 lần): "y tế", "Trường Y", "Y khoa" → **không** đưa vào từ điển
  (D-046). 205/401 standalone "y" đứng trước "tế"/"học"/"khoa".
- ``ba`` (không dấu, 4.957 lần): đứng trước tên riêng 1.337 lần và gần như
  toàn bộ là **địa danh** (Ba Vì, Ba Đình, Ba Lan, Ba Xuyên, Ba Giồng,
  Ba Thắc, Ba Việt) → loại khỏi từ điển (khác với ``bà`` có dấu).
- ``ông`` + tên riêng (8.274 lần): "ông Nguyễn Xuân Kỳ" → **hợp lệ**, mẫu
  danh xưng + tên; span danh xưng được tách riêng và chiếu sang entity của tên.

Mẫu "danh xưng + tên"
---------------------
``vua Lê``, ``ông Nguyễn``, ``tể tướng Trần Quốc Tuấn``:
- span danh xưng (``vua`` / ``ông`` / ``tể tướng``) → nhãn theo từ điển.
- span tên phía sau → do NER bắt; nếu NER **không** bắt, module này tự tạo
  span tên (nhãn `PERSON`) để không bỏ sót thực thể.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import yaml

from src.common.logger import get_logger
from src.common.normalize import normalize_name

logger = get_logger(__name__)

#: Ký tự chữ cái tiếng Việt (bao gồm Đ/đ) — dùng cho ranh giới từ.
_WORD_CHARS = "a-zA-Z0-9À-ỹĐđ"

#: Regex ranh giới từ: surface không được dính vào chữ/số khác.
_BOUNDARY = r"(?<![\wÀ-ỹĐđ])({surface})(?![\wÀ-ỹĐđ])"

#: Regex nhận diện tên riêng đứng ngay sau danh xưng.
#: Dùng `match(text, pos)` nên **không** được neo `^` (đó là ranh giới đầu
#: chuỗi, không phải ranh giới tại `pos`).
#:
#: Chữ cái đầu phải là **chữ hoa** tiếng Việt: `A-Z`, `À-Ỹ` (gồm `Đ`, `Ơ`,
#: `Ư`...) hoặc `Đ`/`Đ` — tuyệt đối không dùng `À-ỹ` vì `à-đ` gồm cả chữ
#: thường (`đ` của "được", `đã") → sẽ khớp nhầm rất nhiều từ thường.
_NAME_AFTER = re.compile(
    r"\s*([A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*(?:\s+[A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*)*)"
)

#: Bộ nối cho phép tên riêng đứng **sau** danh xưng (có giãn cách ngắn):
#: "vua, tức là Lê Ý Tông", "ông là Nguyễn Huệ", "vua Lê Thánh Tông".
_CONNECTOR = (
    r"(?:\s*[,;:]\s*|\s+)(?:tức là\s+|tên là\s+|gọi là\s+|chính là\s+|"
    r"cũng là\s+|tức\s+)?"
)

#: Regex nhận diện tên riêng đứng **sau** danh xưng (có nối).
_NAME_FORWARD = re.compile(
    _CONNECTOR + r"([A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*(?:\s+[A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*)*)"
)

#: Từ chỉ quan hệ họ tập — dùng làm "tầng nối" giữa danh xưng và tên riêng:
#: "vua em Lê Long Đĩnh", "ông nội Trần Thủ Độ".
KINSHIP_WORDS: tuple[str, ...] = (
    "cha",
    "mẹ",
    "tổ",
    "nội",
    "ngoại",
    "em",
    "anh",
    "chị",
    "con",
    "cô",
    "chú",
    "bác",
    "dì",
    "mụ",
    "chúa",
    "vợ",
    "chồng",
)

#: Regex tên riêng đứng sau danh xưng **qua tầng quan hệ họ tập**.
_NAME_KINSHIP = re.compile(
    r"\s+(?:" + "|".join(KINSHIP_WORDS) + r")\s+"
    r"([A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*(?:\s+[A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*)*)"
)

#: Regex tên riêng đứng trong **ngoặc** ngay sau danh xưng:
#: "Đại Tông Văn Hoàng đế (Chu Đệ)".
_NAME_PAREN = re.compile(
    r"\s*\(\s*([A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*(?:\s+[A-ZÀ-ÖØ-ÞĐ][\wÀ-ỹĐđ]*)*)"
)

#: Regex tìm một từ trong văn bản (dùng để dò từ trước/sau danh xưng).
_WORD_RE = re.compile(r"[\wÀ-ỹĐđ]+", re.UNICODE)

#: Từ báo hiệu **số nhiều / tập hợp** đứng trước danh xưng:
#: "các vua Trần", "các triều vua Trần", "các ông dành cho tôi...".
#: Đại từ/danh xưng số nhiều **không** tham chiếu được một thực thể đơn lẻ
#: → ``canonical_id = null`` (xem `docs/10-nhat-ky/phase-06.md` §3, D-049).
PLURAL_MARKERS: frozenset[str] = frozenset({"các"})

#: Số từ được xét khi dò dấu hiệu số nhiều (2 từ trước danh xưng).
PLURAL_LOOKBACK = 2


@dataclass(slots=True)
class Honorific:
    """Một mục trong từ điển danh xưng.

    Attributes:
        surface: Chuỗi khớp (ví dụ ``"ông ấy"``).
        label: Nhãn NER của span danh xưng.
        gender: ``male``/``female``/``None``.
        requires_name_next: Có bắt buộc tên riêng đi sau không.
        pattern: Regex đã biên dịch.
    """

    surface: str
    label: str
    gender: str | None
    requires_name_next: bool
    pattern: re.Pattern[str]


@dataclass(slots=True)
class PronounSpan:
    """Một span danh xưng/đại từ được dò ra.

    Attributes:
        start: Offset ký tự bắt đầu (bao gồm).
        end: Offset ký tự kết thúc (không bao gồm).
        text: Văn bản span.
        label: Nhãn NER suy ra.
        gender: Giới tính suy ra (``male``/``female``/``None``).
        honorific: Surface của danh xưng khớp được.
        name_start: Offset bắt đầu tên riêng đi kèm (nếu có).
        name_end: Offset kết thúc tên riêng đi kèm (nếu có).
        name_text: Văn bản tên riêng đi kèm (nếu có).
        is_plural: Đại từ/danh xưng đứng sau dấu hiệu số nhiều ("các ông").
    """

    start: int
    end: int
    text: str
    label: str
    gender: str | None
    honorific: str
    name_start: int | None = None
    name_end: int | None = None
    name_text: str | None = None
    is_plural: bool = False


def load_honorifics(path: str | Path) -> list[Honorific]:
    """Nạp từ điển danh xưng từ YAML.

    Args:
        path: Đường dẫn `configs/honorifics.yaml`.

    Returns:
        Danh sách `Honorific` **đã sắp xếp theo độ dài giảm dần** để khớp
        longest-match (tránh ``ông`` ăn mất ``ông ấy``).
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}

    honorifics: list[Honorific] = []
    for item in raw.get("honorifics") or []:
        surface = str(item.get("surface") or "").strip()
        if not surface:
            continue
        label = str(item.get("label") or "PERSON")
        gender = item.get("gender")
        pattern = re.compile(
            _BOUNDARY.format(surface=re.escape(surface)),
            re.IGNORECASE,
        )
        honorifics.append(
            Honorific(
                surface=surface,
                label=label,
                gender=gender if isinstance(gender, str) else None,
                requires_name_next=bool(item.get("requires_name_next")),
                pattern=pattern,
            )
        )
    honorifics.sort(key=lambda item: len(item.surface), reverse=True)
    logger.info("Nạp %d danh xưng từ %s", len(honorifics), path)
    return honorifics


def _overlaps(start: int, end: int, spans: Sequence[tuple[int, int]]) -> bool:
    """Kiểm tra một khoảng có chồng lấn span nào không.

    Args:
        start: Offset bắt đầu.
        end: Offset kết thúc (không bao gồm).
        spans: Danh sách cặp ``(start, end)`` đã biết.

    Returns:
        ``True`` nếu chồng lấn ít nhất một span.
    """
    for other_start, other_end in spans:
        if start < other_end and other_start < end:
            return True
    return False


def _find_name_after(
    text: str,
    end: int,
    *,
    max_name_words: int,
) -> tuple[int, int, str] | None:
    """Tìm tên riêng đứng ngay sau danh xưng.

    Thử lần lượt các mẫu, theo thứ tự **giảm độ tin cậy**:

    1. Tên liền kề — "vua Lê", "ông Nguyễn".
    2. Tên sau nối — "vua, tức là Lê Ý Tông", "ông là Nguyễn Huệ".
    3. Tên sau **từ quan hệ họ tập** — "vua em Lê Long Đĩnh".
    4. Tên trong **ngoặc** — "Đại Tông Văn Hoàng đế (Chu Đệ)".

    Args:
        text: Văn bản câu.
        end: Offset kết thúc danh xưng.
        max_name_words: Số tối đa từ của tên riêng.

    Returns:
        Bộ ba ``(start, end, text)`` hoặc ``None``.
    """
    for pattern in (_NAME_AFTER, _NAME_FORWARD, _NAME_KINSHIP, _NAME_PAREN):
        match = pattern.match(text, end)
        if match is None:
            continue
        candidate = match.group(1)
        words = candidate.split()
        if len(words) > max_name_words:
            candidate = " ".join(words[:max_name_words])
        name_start = match.start(1)
        name_end = name_start + len(candidate)
        return name_start, name_end, text[name_start:name_end]
    return None


def _is_plural(text: str, start: int) -> bool:
    """Kiểm tra danh xưng có đứng sau dấu hiệu số nhiều không.

    Args:
        text: Văn bản câu.
        start: Offset bắt đầu danh xưng.

    Returns:
        ``True`` nếu có từ "các" trong vài từ trước danh xưng.
    """
    words = _WORD_RE.findall(text[:start])
    for word in words[-PLURAL_LOOKBACK:]:
        if word.lower() in PLURAL_MARKERS:
            return True
    return False


def detect_pronouns(
    text: str,
    known_spans: Sequence[tuple[int, int]],
    honorifics: Sequence[Honorific],
    *,
    max_name_words: int = 4,
) -> list[PronounSpan]:
    """Dò các span danh xưng/đại từ trong một câu.

    Args:
        text: Văn bản câu.
        known_spans: Danh sách ``(start, end)`` của span NER đã biết — span
            danh xưng trùng với chúng sẽ bị loại (không tạo mention trùng).
        honorifics: Từ điển danh xưng (xem `load_honorifics`).
        max_name_words: Số tối đa từ của tên riêng đi kèm danh xưng.

    Returns:
        Danh sách `PronounSpan` sắp theo `start` tăng dần.
    """
    if not text:
        return []

    results: list[PronounSpan] = []
    consumed: list[tuple[int, int]] = []
    blocked = list(known_spans)

    for honorific in honorifics:
        for match in honorific.pattern.finditer(text):
            start, end = match.span()
            if _overlaps(start, end, blocked):
                continue

            name_start: int | None = None
            name_end: int | None = None
            name_text: str | None = None
            found = _find_name_after(text, end, max_name_words=max_name_words)
            if found is not None:
                name_start, name_end, name_text = found
                # Tên riêng **có thể trùng** span NER — trong trường hợp đó NER
                # đã bắt được tên và R2 sẽ chiếu sang entity của span NER đó.
                # Vì vậy KHÔNG loại tên khi chồng lấn; chỉ loại nếu tên trùng
                # một span danh xưng khác (đã bị `blocked` chặn).

            results.append(
                PronounSpan(
                    start=start,
                    end=end,
                    text=text[start:end],
                    label=honorific.label,
                    gender=honorific.gender,
                    honorific=honorific.surface,
                    name_start=name_start,
                    name_end=name_end,
                    name_text=name_text,
                    is_plural=_is_plural(text, start),
                )
            )
            consumed.append((start, end))
            blocked.append((start, end))

    results.sort(key=lambda item: item.start)
    return results


def split_honorific_and_name(
    pronoun: PronounSpan,
) -> tuple[tuple[int, int, str], tuple[int, int, str] | None]:
    """Tách span danh xưng và span tên riêng đi kèm.

    Args:
        pronoun: Span danh xưng đã dò.

    Returns:
        Cặp ``(danh_xưng, tên)``; phần tên là ``None`` nếu không có tên đi kèm.
        Mỗi phần là bộ ba ``(start, end, text)``.
    """
    honorific_part = (pronoun.start, pronoun.end, pronoun.text)
    if pronoun.name_start is None or pronoun.name_end is None:
        return honorific_part, None
    name_part = (pronoun.name_start, pronoun.name_end, pronoun.name_text or "")
    return honorific_part, name_part


def is_person_honorific(label: str) -> bool:
    """Kiểm tra nhãn của span danh xưng có phải `PERSON` không.

    Args:
        label: Nhãn NER.

    Returns:
        ``True`` nếu nhãn là `PERSON`.
    """
    return label == "PERSON"


def infer_gender_from_name(name: str) -> str | None:
    """Suy giới tính từ tiền tố tên (fallback khi không có `props.gender`).

    Quy tắc: tên bắt đầu bằng "Bà", "Báu", "Thái hậu", "Thái phi" → nữ; bắt
    đầu bằng "Ông", "Lão", "Trẻ" → nam.

    Args:
        name: Tên hiển thị của entity.

    Returns:
        ``male``/``female``/``None``.
    """
    normalized = normalize_name(name)
    if not normalized:
        return None
    female_prefixes = ("ba ", "bau ", "thai hau ", "thai phi ", "hoang thi ")
    male_prefixes = ("ong ", "lao ", "tre ")
    if normalized.startswith(female_prefixes):
        return "female"
    if normalized.startswith(male_prefixes):
        return "male"
    return None

"""Parse infobox → triple chất lượng cao + thuộc tính node (Phase 3 — A4).

## Vì sao cần module này

Infobox là nguồn bằng chứng **mạnh nhất** của Wikipedia: trường ``cha = Lê Khánh
Dư`` là một mệnh đề có chủ thể–vị ngữ rõ ràng, không cần mô hình NER/RE. Phase 3
biến những trường đó thành triple có `confidence ≥ 0.95` với bằng chứng đầy đủ.

## Kiến trúc

```
documents.jsonl (Phase 2)
   │  infobox_raw
   ▼
extract_params()          ← wikitextparser (chính) + regex cân bằng ngoặc (dự phòng)
   │  {loai, params}
   ▼
build_context()           ← infobox_entity_types: loại node + giới tính chủ thể
   │
   ▼
for each field in params:
   ├─ kind=date    → parse_vi_date → node prop + triple sinh_nam/mat_nam
   ├─ kind=period  → 2 mốc năm → node prop (reign_start/reign_end)
   └─ kind=entity  → extract_links/clean_value → triple theo mapping
   ▼
infobox_triples.jsonl   (method="infobox", confidence ≥ 0.95)
infobox_entities.jsonl  (node props + alias)
```

## Nguyên tắc bất di bất dịch

1. **Chỉ 18 quan hệ đóng** (`src/common/schemas.RELATION_TYPES`).
2. **Có bằng chứng** — mọi triple đều có `evidence_sentence` + `source_url`.
3. **Không bịa** — giá trị không parse được thì bỏ, không suy đoán.
4. **Tuân thủ hướng quan hệ** — `RELATION_SUBJECT_TYPES` được kiểm tra trước khi
   ghi; triple vi phạm bị loại và đếm trong báo cáo.
5. **Không sửa `infobox_parser.py`** (hành vi Phase 1) — mapping mở rộng nằm ở
   `configs/infobox_mapping.yaml`.

## Cách chạy

```bash
python -m src.preprocess.parse_infobox --config configs/default.yaml
```
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.common.config import REPO_ROOT, load_config, resolve_path
from src.common.ids import make_entity_id, make_year_id
from src.common.logger import get_logger
from src.common.normalize import normalize_name, parse_vi_date, strip_accents
from src.common.schemas import (
    NODE_TYPES,
    RELATION_SUBJECT_TYPES,
    RELATION_TYPES,
)
from src.common.text_utils import read_jsonl, write_jsonl
from src.preprocess.infobox_entity_types import (
    DEFAULT_TYPE,
    WIKIDATA_SIGNAL_TYPES,
    build_context,
    infer_object_type,
    normalize_type,
    relation_for_gender,
)

logger = get_logger(__name__)

#: 7 loại node KG hợp lệ (`docs/CONTEXT.md` §2.4).
KG_NODE_TYPES = NODE_TYPES

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------

#: Confidence cho triple từ infobox (Gate yêu cầu ≥ 0.95).
CONFIDENCE_INFOBOX = 0.97

#: Confidence cho triple suy ra từ template "X và tuổi" (thấp hơn một chút vì
#: mốc sinh được suy từ tham số phụ).
CONFIDENCE_DERIVED = 0.95

#: Nhãn tiếng Việt cho trường, dùng làm tiền tố của `evidence_sentence`.
FIELD_LABELS: dict[str, str] = {
    "sinh": "Ngày sinh",
    "ngay sinh": "Ngày sinh",
    "ngay sinh va tuoi": "Ngày sinh",
    "nam sinh va tuoi": "Năm sinh",
    "nam sinh": "Năm sinh",
    "birth_date": "Ngày sinh",
    "birthdate": "Ngày sinh",
    "date of birth": "Ngày sinh",
    "born": "Ngày sinh",
    "mat": "Ngày mất",
    "ngay mat": "Ngày mất",
    "ngay mat va tuoi": "Ngày mất",
    "nam mat va tuoi": "Năm mất",
    "death_date": "Ngày mất",
    "deathdate": "Ngày mất",
    "date of death": "Ngày mất",
    "died": "Ngày mất",
    "noi sinh": "Nơi sinh",
    "birth_place": "Nơi sinh",
    "birthplace": "Nơi sinh",
    "place of birth": "Nơi sinh",
    "noi mat": "Nơi mất",
    "death_place": "Nơi mất",
    "deathplace": "Nơi mất",
    "place of death": "Nơi mất",
    "cha": "Cha",
    "father": "Cha",
    "me": "Mẹ",
    "mother": "Mẹ",
    "vo": "Vợ",
    "wife": "Vợ",
    "chong": "Chồng",
    "husband": "Chồng",
    "phu quan": "Phu quân",
    "queen consort": "Hậu thân",
    "spouse": "Vợ/Chồng",
    "consort": "Vợ/Chồng",
    "phoi ngau": "Phối ngẫu",
    "anh em": "Anh em",
    "sibling": "Anh em",
    "em": "Anh em",
    "con trai": "Con trai",
    "son": "Con trai",
    "con gai": "Con gái",
    "daughter": "Con gái",
    "con": "Con",
    "trieu dai": "Triều đại",
    "dynasty": "Triều đại",
    "the": "Triều đại",
    "hoang toc": "Hoàng tộc",
    "ke nhiem": "Kế nhiệm",
    "successor": "Kế nhiệm",
    "tien nhiem": "Tiền nhiệm",
    "predecessor": "Tiền nhiệm",
    "chuc vi": "Chức vụ",
    "chuc quan": "Chức quan",
    "office": "Chức vụ",
    "position": "Chức vụ",
    "tuoc vi": "Tước vị",
    "nghe nghiep": "Nghề nghiệp",
    "occupation": "Nghề nghiệp",
    "nguoi sang lap": "Người sáng lập",
    "founder": "Người sáng lập",
    "sang lap": "Người sáng lập",
    "place": "Địa điểm",
    "location": "Địa điểm",
    "dia diem": "Địa điểm",
    "commander1": "Chỉ huy",
    "commander2": "Chỉ huy",
    "combatant1": "Bên tham chiến",
    "combatant2": "Bên tham chiến",
    "thu do": "Thủ đô",
    "capital": "Thủ đô",
    "dong do": "Đô thành",
    "doi thu do": "Đô thành",
}

#: Regex các năm trong khoảng lịch sử VN (dùng cho trường kỳ thời gian).
_YEAR_IN_RANGE_RE = re.compile(r"\b(9\d{2}|1\d{3}|20[0-2]\d)\b")

#: Regex liên kết wiki.
_WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")

#: Template dùng để liệt kê nhiều mục trong một trường.
_LIST_TEMPLATES = ("plainlist", "unbulleted list", "ubl", "flatlist", "br list", "collapsible list")


# ---------------------------------------------------------------------------
# Làm sạch giá trị
# ---------------------------------------------------------------------------


def _strip_templates(text: str) -> str:
    """Gỡ mọi template `{{...}}` còn lại trong chuỗi (lồng nhau).

    Args:
        text: Chuỗi wikitext.

    Returns:
        Chuỗi đã gỡ template.
    """
    result = text
    for _ in range(10):
        start = result.find("{{")
        if start == -1:
            break
        depth = 0
        end = -1
        index = start
        while index < len(result) - 1:
            if result[index : index + 2] == "{{":
                depth += 1
                index += 2
                continue
            if result[index : index + 2] == "}}":
                depth -= 1
                index += 2
                if depth == 0:
                    end = index
                    break
                continue
            index += 1
        if end == -1:
            result = result[:start]
            break
        result = result[:start] + " " + result[end:]
    return result


def clean_value(text: str) -> str:
    """Chuyển giá trị infobox thô thành văn bản thuần.

    Bỏ: comment, `<ref>`, template, thẻ HTML (nhưng **giữ** nội dung trong thẻ),
    liên kết wiki (giữ phần hiển thị), ký tự thực thể HTML.

    Args:
        text: Giá trị thô.

    Returns:
        Văn bản thuần đã rút gọn khoảng trắng.
    """
    if not text:
        return ""

    result = text

    # Comment wikitext — bỏ hẳn.
    result = re.sub(r"<!--.*?-->", " ", result, flags=re.DOTALL)
    # <ref>...</ref> và <ref ... />
    result = re.sub(r"<ref[^>]*>.*?</ref>", " ", result, flags=re.DOTALL | re.IGNORECASE)
    result = re.sub(r"<ref[^>]*/>", " ", result, flags=re.IGNORECASE)
    # Thẻ HTML: bỏ thẻ, giữ nội dung.
    result = re.sub(r"<br\s*/?>", " ", result, flags=re.IGNORECASE)
    result = re.sub(r"<[^>]+>", " ", result)
    # Template.
    result = _strip_templates(result)
    # Liên kết wiki → phần hiển thị.
    result = _WIKILINK_RE.sub(lambda m: (m.group(2) or m.group(1)), result)
    # Liên kết ngoài.
    result = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", result)
    result = re.sub(r"\[https?://\S+\]", " ", result)
    # Định dạng chữ.
    result = result.replace("'''", "").replace("''", "")
    # Ký tự thực thể.
    result = (
        result.replace("&ndash;", "–")
        .replace("&mdash;", "—")
        .replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#91;", "[")
        .replace("&#93;", "]")
    )
    result = result.replace("{", " ").replace("}", " ")
    result = re.sub(r"\s+", " ", result).strip()
    return result.strip(" ,;·-–—|")


def extract_links(text: str) -> list[tuple[str, str]]:
    """Trích các liên kết wiki trong một giá trị.

    Args:
        text: Giá trị thô.

    Returns:
        Danh sách cặp ``(đích_bài, chữ_hiển_thị)``.
    """
    links: list[tuple[str, str]] = []
    for match in _WIKILINK_RE.finditer(text or ""):
        target = match.group(1).strip()
        anchor = (match.group(2) or "").strip()
        if not target:
            continue
        links.append((target, anchor or target))
    return links


def split_items(text: str) -> list[str]:
    """Tách một giá trị thành nhiều mục **thô** (chưa làm sạch).

    Tách theo: template danh sách (`plainlist`, `ubl`...), `<br>`, và `*` nếu có.

    Quan trọng: hàm giữ nguyên wikitext để `extract_links()` còn thấy được
    liên kết wiki — nếu làm sạch trước thì mất toàn bộ `[[...]]`.

    Args:
        text: Giá trị thô.

    Returns:
        Danh sách mục thô (đã rút gọn khoảng trắng, bỏ mục rỗng).
    """
    if not text:
        return []

    working = text
    for tpl_name in _LIST_TEMPLATES:
        pattern = re.compile(
            r"\{\{\s*" + re.escape(tpl_name) + r"\s*\|(.*?)\}\}", re.DOTALL | re.IGNORECASE
        )
        match = pattern.search(working)
        if match:
            working = match.group(1)
            break

    parts = re.split(r"<br\s*/?>|\n|\*", working, flags=re.IGNORECASE)
    items: list[str] = []
    for part in parts:
        stripped = part.strip()
        if stripped:
            items.append(stripped)
    return items


#: Regex nhận diện một cụm tên riêng (chữ hoa đầu từng từ, không có chữ số).
_PROPER_NAME_RE = re.compile(r"^[A-ZÀ-ỹĐđ][\wÀ-ỹĐđ.'-]*(?:\s+[A-ZÀ-ỹĐđ][\wÀ-ỹĐđ.'-]*){0,4}$")


def looks_like_proper_name(text: str) -> bool:
    """Kiểm tra chuỗi có giống tên riêng (dùng khi không có liên kết wiki).

    Args:
        text: Chuỗi đã làm sạch.

    Returns:
        ``True`` nếu giống tên riêng.
    """
    if not text or any(char.isdigit() for char in text):
        return False
    return bool(_PROPER_NAME_RE.match(text))


# ---------------------------------------------------------------------------
# Trích tham số infobox
# ---------------------------------------------------------------------------


def _params_from_wikitextparser(raw: str) -> tuple[str, dict[str, str]] | None:
    """Trích tham số bằng `wikitextparser`.

    Args:
        raw: Khối wikitext infobox.

    Returns:
        Cặp ``(tên_loại, tham_số)`` hoặc ``None`` nếu thất bại.
    """
    try:
        from wikitextparser import WikiText
    except ImportError:  # pragma: no cover - phụ thuộc tuỳ chọn
        return None

    try:
        wikitext = WikiText(" " + raw)
        templates = list(wikitext.templates)
    except Exception:  # pragma: no cover - wikitextparser rất hiếm khi lỗi
        return None

    if not templates:
        return None

    template = templates[0]
    params: dict[str, str] = {}
    for argument in template.arguments:
        key = normalize_name(str(argument.name))
        if not key or key.isdigit():
            continue
        value = str(argument.value).strip()
        if key not in params:
            params[key] = value
    return str(template.name), params


def _params_from_regex(raw: str) -> tuple[str, dict[str, str]] | None:
    """Trích tham số bằng regex cân bằng ngoặc (dự phòng).

    Dùng `src.preprocess.infobox_parser.parse_infobox` — hành vi Phase 1, đã đạt
    100% trên corpus.

    Args:
        raw: Khối wikitext infobox.

    Returns:
        Cặp ``(tên_loại, tham_số)`` hoặc ``None``.
    """
    from src.preprocess.infobox_parser import parse_infobox

    infobox = parse_infobox(raw)
    if infobox is None:
        return None
    return infobox.loai, dict(infobox.params)


def extract_params(raw: str) -> tuple[str, dict[str, str]] | None:
    """Trích tham số infobox, ưu tiên `wikitextparser`.

    Nếu `wikitextparser` cho ít tham số hơn regex (do template lồng nhau cắt
    dòng), dùng kết quả regex.

    Args:
        raw: Khối wikitext infobox.

    Returns:
        Cặp ``(tên_loại_chuẩn_hoá, tham_số)`` hoặc ``None``.
    """
    if not raw:
        return None

    candidates: list[tuple[str, dict[str, str]]] = []
    for extractor in (_params_from_wikitextparser, _params_from_regex):
        result = extractor(raw)
        if result is None:
            continue
        name, params = result
        candidates.append((normalize_name(name), params))
        if len(params) >= 5:
            # Đủ tham số → tin ngay, khỏi thử tiếp.
            return candidates[-1]

    if not candidates:
        return None
    return max(candidates, key=lambda item: len(item[1]))


# ---------------------------------------------------------------------------
# Ngày tháng
# ---------------------------------------------------------------------------


def _format_date(info: dict[str, Any], year_text: str) -> str:
    """Định dạng thông tin ngày thành chuỗi hiển thị có dấu.

    Args:
        info: Dict thông tin ngày (``year``/``month``/``day``/``qualifier``).
        year_text: Năm dạng chuỗi (fallback).

    Returns:
        Chuỗi ngày, ví dụ ``"10 tháng 9 năm 1385"`` hoặc ``"khoảng năm 1230"``.
    """
    year = info.get("year")
    if year is None:
        return year_text
    month = info.get("month")
    day = info.get("day")
    qualifier = info.get("qualifier")
    prefix = f"{qualifier} " if qualifier else ""
    if month is not None and day is not None:
        return f"{prefix}{day} tháng {month} năm {year}"
    if month is not None:
        return f"{prefix}tháng {month} năm {year}"
    return f"{prefix}năm {year}"


def _template_args(value: str) -> tuple[str, dict[str, str]] | None:
    """Trích template ngày đầu tiên trong một giá trị.

    Args:
        value: Giá trị thô.

    Returns:
        Cặp ``(tên_template_chuẩn_hoá, tham_số)`` hoặc ``None``.
    """
    try:
        from wikitextparser import WikiText
    except ImportError:  # pragma: no cover
        return None

    try:
        wikitext = WikiText(" " + value)
        templates = list(wikitext.templates)
    except Exception:  # pragma: no cover
        return None

    if not templates:
        return None

    template = templates[0]
    args: dict[str, str] = {}
    for argument in template.arguments:
        args[str(argument.name).strip()] = str(argument.value).strip()
    return normalize_name(str(template.name)), args


def _int_arg(args: dict[str, str], position: int) -> int | None:
    """Lấy tham số theo vị trí (1-based) dạng số nguyên.

    Args:
        args: Dict tham số.
        position: Vị trí (1-based).

    Returns:
        Số nguyên hoặc ``None``.
    """
    if position <= 0:
        return None
    raw = args.get(str(position), "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def parse_date_field(
    value: str,
    *,
    date_templates: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Phân tích một trường ngày.

    Hỗ trợ:
    - template ngày chuẩn (``{{ngày mất và tuổi|1820|9|16|1766|1|3}}``);
    - văn bản thuần (``"25 tháng 12 năm 1933"``, ``"[[25 tháng 12]] năm [[1933]]"``).

    Args:
        value: Giá trị thô của trường.
        date_templates: Bảng mapping template ngày từ config.

    Returns:
        Cặp ``(thông_tin_ngày, danh_sách_ngày_phụ)``. Thông tin ngày gồm các
        khoá ``year``/``month``/``day``/``iso``/``precision``/``qualifier``;
        danh sách ngày phụ là các mốc sinh suy thêm từ tham số phụ (ví dụ
        ``death date and age`` có cả ngày sinh).
    """
    info: dict[str, Any] = {}
    extra: list[dict[str, Any]] = []

    template_result = _template_args(value)
    if template_result is not None:
        template_name, args = template_result
        spec = date_templates.get(template_name)
        if spec is not None:
            year = _int_arg(args, int(spec.get("year", 1)))
            month = _int_arg(args, int(spec.get("month", 2)))
            day = _int_arg(args, int(spec.get("day", 3)))
            if year is not None:
                info["year"] = year
                info["month"] = month
                info["day"] = day
                info["precision"] = "day" if day is not None else ("month" if month is not None else "year")
                info["qualifier"] = "khoảng" if spec.get("qualifier") else None
                info["template"] = template_name

            birth_year = _int_arg(args, int(spec.get("birth_year", 0)))
            birth_month = _int_arg(args, int(spec.get("birth_month", 0)))
            birth_day = _int_arg(args, int(spec.get("birth_day", 0)))
            if birth_year is not None:
                extra.append(
                    {
                        "year": birth_year,
                        "month": birth_month,
                        "day": birth_day,
                        "precision": "day" if birth_day is not None else ("month" if birth_month is not None else "year"),
                        "qualifier": None,
                        "template": template_name,
                    }
                )

            end_year = _int_arg(args, int(spec.get("end_year", 0)))
            if end_year is not None:
                info["end_year"] = end_year

            if not info:
                # Template "circa|sau năm 1230": tham số không phải số → parse
                # bằng `parse_vi_date` (nhận "sau năm 1230" → 1230).
                arg_text = args.get(str(int(spec.get("year", 1))), "")
                iso, year, precision = parse_vi_date(arg_text)
                if year is None:
                    return {}, extra
                info["year"] = year
                info["iso"] = iso
                info["precision"] = precision
                info["qualifier"] = "khoảng" if spec.get("qualifier") else None
                info["template"] = template_name
            return info, extra

    # Văn bản thuần.
    plain = clean_value(value)
    iso, year, precision = parse_vi_date(plain)
    if year is None:
        return {}, extra
    info["year"] = year
    info["precision"] = precision
    info["iso"] = iso
    # Trích tháng/ngày nếu chuỗi có dạng "25 tháng 12 năm 1933".
    lowered_plain = strip_accents(plain).lower()
    full_match = re.search(
        r"\b(\d{1,2})\s*thang\s*(\d{1,2})\s*(?:nam)?\s*\d{3,4}\b", lowered_plain
    )
    if full_match:
        info["month"] = int(full_match.group(2))
        info["day"] = int(full_match.group(1))
    qualifier = None
    lowered = lowered_plain
    for keyword in ("khoang", "sau nam", "truoc nam", "circa"):
        if keyword in lowered:
            qualifier = "khoảng"
            break
    info["qualifier"] = qualifier
    return info, extra


def parse_period_field(value: str) -> tuple[int | None, int | None]:
    """Trích hai mốc năm (đầu, cuối) từ một trường kỳ thời gian.

    Args:
        value: Giá trị thô.

    Returns:
        Cặp ``(năm_đầu, năm_cuối)``; có thể chứa ``None``.
    """
    plain = clean_value(value)
    years = [int(y) for y in _YEAR_IN_RANGE_RE.findall(plain)]
    if not years:
        return None, None
    start = years[0]
    end = years[-1] if len(years) > 1 else None
    return start, end


# ---------------------------------------------------------------------------
# Sinh triple
# ---------------------------------------------------------------------------


def _entity(type_name: str, name: str) -> tuple[str, str]:
    """Sinh ``(entity_id, tên hiển thị)`` cho một node.

    Args:
        type_name: Loại node.
        name: Tên hiển thị.

    Returns:
        Cặp ``(entity_id, name)``.
    """
    return make_entity_id(type_name, name), name


def _year_entity(year: int) -> tuple[str, str]:
    """Sinh ``(year_id, năm dạng chuỗi)``.

    Args:
        year: Năm.

    Returns:
        Cặp ``(year_id, "1385")``.
    """
    return make_year_id(year), str(year)


def _subject_allowed(relation: str, subject_type: str) -> bool:
    """Kiểm tra loại chủ thể có hợp lệ với quan hệ không.

    Args:
        relation: Tên quan hệ.
        subject_type: Loại node chủ thể.

    Returns:
        ``True`` nếu hợp lệ.
    """
    allowed = RELATION_SUBJECT_TYPES.get(relation)
    if allowed is None:
        return relation in RELATION_TYPES
    return subject_type in allowed


def build_triples(
    doc: dict[str, Any],
    *,
    infobox_type: str,
    params: dict[str, str],
    mapping: dict[str, Any],
    model_name: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, int]]:
    """Sinh triple + thuộc tính node từ một bài có infobox.

    Args:
        doc: Record document (Phase 2).
        infobox_type: Tên loại infobox (đã chuẩn hóa).
        params: Tham số infobox.
        mapping: Config mapping đã nạp.
        model_name: Tên mô hình đã dùng (ghi vào mọi triple).

    Returns:
        Bộ ba ``(triples, node_props, counters)``.
    """
    fields: dict[str, dict[str, Any]] = mapping.get("fields", {})
    date_templates: dict[str, dict[str, Any]] = mapping.get("date_templates", {})
    type_map: dict[str, str] = mapping.get("type_map", {})
    aliases_map: dict[str, str] = mapping.get("aliases", {})
    node_props_map: dict[str, str] = mapping.get("node_props", {})
    gender_keys: list[str] = mapping.get("gender_keys", [])
    gender_values: dict[str, str] = mapping.get("gender_values", {})
    title_prefixes: dict[str, str] = mapping.get("title_gender_prefixes", {})

    # Bảng tra **đã gộp khoá** — tra bằng khoá gộp ở cả hai phía nên không
    # mất khoá nào giữa `noi_sinh` và `noi sinh` (xem `_collapse_key`).
    fields_by_key = {_collapse_key(key): spec for key, spec in fields.items()}
    aliases_by_key = {_collapse_key(key): value for key, value in aliases_map.items()}
    node_props_by_key = {_collapse_key(key): value for key, value in node_props_map.items()}

    title = doc.get("title", "")
    doc_id = doc.get("doc_id", "")
    page_id = doc.get("page_id", "")
    source_url = doc.get("url", "")

    context = build_context(
        infobox_type=infobox_type,
        title=title,
        params=params,
        type_map=type_map,
        gender_keys=gender_keys,
        gender_values=gender_values,
        title_prefixes=title_prefixes,
        wikidata_signal=doc.get("wikidata_signal"),
    )
    subject_type = context.subject_type
    subject_id, _ = _entity(subject_type, title)

    triples: list[dict[str, Any]] = []
    props: dict[str, Any] = {}
    counters: dict[str, int] = {
        "fields_mapped": 0,
        "fields_skipped": 0,
        "triples": 0,
        "skipped_schema": 0,
        "skipped_gender": 0,
        "skipped_empty": 0,
        "skipped_duplicate": 0,
        "skipped_self_loop": 0,
    }

    field_index = 0

    #: Khoá chống trùng: `(subject, relation, object)`.
    #:
    #: Wikipedia hay có **hai** trường cùng nội dung (vd `Ngày sinh` và
    #: `Ngày sinh (từ Ngày mất)` trong template "sinh và mất") → cùng một
    #: quan hệ bị ghi 2 lần. Giữ bản **đầu tiên** (thứ tự trường trong
    #: infobox) là bản có bằng chứng trực tiếp.
    seen_triples: set[tuple[str, str, str]] = set()

    def add_triple(
        *,
        relation: str,
        subject: str,
        subject_type_value: str,
        object_value: str,
        object_type_value: str,
        evidence: str,
        confidence: float,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> bool:
        """Ghi một triple nếu hợp lệ theo schema.

        Returns:
            ``True`` nếu triple **được** ghi, ``False`` nếu bị loại.
        """
        if relation not in RELATION_TYPES:
            counters["skipped_schema"] += 1
            return False
        if not _subject_allowed(relation, subject_type_value):
            counters["skipped_schema"] += 1
            return False
        if not subject or not object_value:
            counters["skipped_empty"] += 1
            return False
        # Self-loop: chủ thể = đối tượng → vi phạm `Triple.is_valid()`
        # trong `src/common/schemas.py`. Hay xảy ra khi infobox ghi nhầm
        # (vd "Kế nhiệm: Nguyễn Phúc Chú" trong bài của chính Nguyễn Phúc Chú).
        if subject == object_value:
            counters["skipped_self_loop"] += 1
            return False
        # Trùng lặp: cùng (subject, relation, object) đã ghi → bỏ.
        key = (subject, relation, object_value)
        if key in seen_triples:
            counters["skipped_duplicate"] += 1
            return False
        seen_triples.add(key)
        triples.append(
            {
                "doc_id": doc_id,
                "sentence_id": f"ibx_{page_id}_{field_index}",
                "subject": subject,
                "subject_type": subject_type_value,
                "relation": relation,
                "object": object_value,
                "object_type": object_type_value,
                "evidence_sentence": evidence,
                "source_url": source_url,
                "doc_title": title,
                "confidence": confidence,
                "method": "infobox",
                "start_year": start_year,
                "end_year": end_year,
                "alt_evidence": [],
                "dump_version": doc.get("dump_version", ""),
                "model_name": model_name,
            }
        )
        counters["triples"] += 1
        return True

    for key, raw_value in params.items():
        if not raw_value or not raw_value.strip():
            continue

        # Khoá tham số trong wikitext có thể dùng `_` (`noi_sinh`) lẫn khoảng
        # trắng (`noi sinh`) → gộp về một dạng để tra bảng (xem D-027).
        lookup_key = _collapse_key(key)

        # --- Thuộc tính node (không sinh triple) ---
        if lookup_key in node_props_by_key:
            prop_name = node_props_by_key[lookup_key]
            if prop_name == "gender":
                if context.subject_gender:
                    props["gender"] = context.subject_gender
                continue
            if prop_name in {"reign_period", "founded_year"}:
                start, end = parse_period_field(raw_value)
                if prop_name == "reign_period":
                    if start is not None:
                        props["reign_start"] = start
                    if end is not None:
                        props["reign_end"] = end
                elif start is not None:
                    props["founded_year"] = start
                continue
            cleaned = clean_value(raw_value)
            if cleaned:
                props[prop_name] = cleaned
            continue

        # --- Alias ---
        if lookup_key in aliases_by_key:
            alias_type = aliases_by_key[lookup_key]
            cleaned = clean_value(raw_value)
            if cleaned:
                props.setdefault("aliases", []).append({"alias": cleaned, "type": alias_type})
            continue

        spec = fields_by_key.get(lookup_key)
        if spec is None:
            continue
        counters["fields_mapped"] += 1
        field_index += 1

        relation = spec.get("relation")
        kind = spec.get("kind", "entity")
        direction = spec.get("direction", "forward")
        declared_type = spec.get("value_type")
        needs_gender = bool(spec.get("needs_gender"))
        #: Tên thuộc tính node gắn thêm từ trường này (vd `noi sinh` →
        #: `birth_place`). Trường này **không** sinh triple riêng — triple đã
        #: có sẵn từ `relation`; ở đây chỉ ghi **tên hiển thị** vào props.
        prop_name = spec.get("prop")
        label = FIELD_LABELS.get(key, key.title())

        # --- Trường ngày ---
        if kind == "date":
            info, extra_dates = parse_date_field(raw_value, date_templates=date_templates)
            if not info:
                counters["fields_skipped"] += 1
                continue
            year = info.get("year")
            if year is None:
                counters["fields_skipped"] += 1
                continue
            prop_name = spec.get("prop")
            if prop_name:
                props[prop_name] = year
            if relation:
                year_id, year_text = _year_entity(year)
                date_text = _format_date(info, year_text)
                add_triple(
                    relation=relation,
                    subject=subject_id,
                    subject_type_value=subject_type,
                    object_value=year_id,
                    object_type_value="year",
                    evidence=f"{label}: {date_text}",
                    confidence=CONFIDENCE_INFOBOX,
                    start_year=year,
                    end_year=year,
                )
            # Mốc sinh suy thêm từ tham số phụ của template "X và tuổi".
            for extra in extra_dates:
                extra_year = extra.get("year")
                if extra_year is None:
                    continue
                props.setdefault("birth_year", extra_year)
                if relation == "mat_nam":
                    extra_id, _ = _year_entity(extra_year)
                    add_triple(
                        relation="sinh_nam",
                        subject=subject_id,
                        subject_type_value=subject_type,
                        object_value=extra_id,
                        object_type_value="year",
                        evidence=f"Ngày sinh (từ {label}): {_format_date(extra, str(extra_year))}",
                        confidence=CONFIDENCE_DERIVED,
                        start_year=extra_year,
                        end_year=extra_year,
                    )
            continue

        # --- Trường kỳ thời gian ---
        if kind == "period":
            start, end = parse_period_field(raw_value)
            prop_name = spec.get("prop")
            if prop_name and start is not None:
                props[prop_name] = f"{start}-{end}" if end else str(start)
            counters["fields_skipped"] += 1
            continue

        # --- Trường thực thể ---
        if needs_gender and context.subject_gender is None:
            counters["skipped_gender"] += 1
            continue

        relation = relation_for_gender(relation, context.subject_gender)

        items = split_items(raw_value)
        if not items:
            counters["skipped_empty"] += 1
            continue

        for item in items:
            links = extract_links(item)
            if links:
                candidates = links
            else:
                # Không có link wiki → dùng văn bản thuần nếu giống tên riêng.
                plain_item = clean_value(item)
                if not plain_item or not looks_like_proper_name(plain_item):
                    counters["skipped_empty"] += 1
                    continue
                candidates = [(plain_item, plain_item)]

            for target, anchor in candidates:
                if not target or target.startswith("#"):
                    continue
                # Bỏ file/hình ảnh ("Tập tin:Flag of ...svg").
                if target.startswith("Tập tin:") or target.startswith("File:"):
                    continue
                object_type = infer_object_type(
                    target,
                    declared_type=declared_type,
                    type_map=type_map,
                )
                # "organization" không phải loại node KG → loại triple, không gán
                # nhầm vào `person` (nguyên tắc: không bịa).
                if object_type not in KG_NODE_TYPES:
                    counters["skipped_schema"] += 1
                    continue
                if not context.allows_object(object_type):
                    counters["skipped_schema"] += 1
                    continue

                # Tên hiển thị: dùng anchor nếu config yêu cầu, ngược lại tên bài.
                display = anchor if spec.get("link_mode") == "anchor" else target
                display = clean_value(display) or target
                object_id, _ = _entity(object_type, display)

                if direction == "reverse":
                    sub_id, sub_type = object_id, object_type
                    obj_id, obj_type = subject_id, subject_type
                else:
                    sub_id, sub_type = subject_id, subject_type
                    obj_id, obj_type = object_id, object_type

                added = add_triple(
                    relation=relation,
                    subject=sub_id,
                    subject_type_value=sub_type,
                    object_value=obj_id,
                    object_type_value=obj_type,
                    evidence=f"{label}: {display}",
                    confidence=CONFIDENCE_INFOBOX,
                )

                # Ghi thuộc tính node (vd `birth_place`, `death_place`).
                # Chỉ ghi khi triple **thực sự** được sinh — nếu bị loại vì
                # schema thì không được ghi prop (tránh khẳng định điều không
                # có bằng chứng).
                if added and prop_name and prop_name not in props:
                    props[prop_name] = display

    # --- Quan hệ `danh_bai` (winner → loser) ---
    # Cố ý **không** trích ở Phase 3.
    #
    # `docs/04` §3.1 quy định `danh_bai`: chủ thể = **người** đánh bại
    # (winner → loser). Thực tế trong Wikipedia, trường `ket qua`/`result`
    # là **câu văn** nêu tên **quốc gia / triều đại / liên minh** ("Campuchia",
    # "Việt Minh", "Nhà Thanh") — không phải `person`. Đo trên 207 trận đánh
    # trong corpus: trích được 4 cặp, 1 cặp sai, 4/4 vi phạm
    # `RELATION_SUBJECT_TYPES["danh_bai"] = {person}`.
    #
    # `danh_bai` sẽ được sinh ở Phase 8 (mô hình RE / LLM), nơi bằng chứng
    # ở mức câu văn. Xem `reports/deviations.md` D-028.

    return triples, props, counters


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _collapse_key(key: str) -> str:
    """Gộp khoá tham số về dạng duy nhất để tra bảng.

    Wikipedia dùng **cả hai** cách viết khoá tham số:
    `| noi_sinh = ...` (gạch dưới) và `| noi sinh = ...` (khoảng trắng);
    tương tự `birth_date` vs `birth date`. `normalize_name` giữ nguyên dấu
    gạch dưới → hai biến thể trở thành **hai khoá khác nhau**, khiến bảng
    mapping viết bằng một biến thể không bao giờ được gọi với biến thể kia.

    Hàm này gộp cả hai về **một** khoá: thay `_` bằng khoảng trắng rồi gộp
    khoảng trắng. Tra bảng bằng khoá đã gộp ở **cả hai** phía
    (tham số lẫn bảng config) → không mất khoá nào.

    Args:
        key: Khoá tham số thô (đã bỏ dấu, viết thường).

    Returns:
        Khoá đã gộp, ví dụ ``"noi sinh"``.
    """
    return " ".join(key.replace("_", " ").split())


def load_mapping(path: str | Path) -> dict[str, Any]:
    """Nạp cấu hình mapping infobox.

    Args:
        path: Đường dẫn tới `configs/infobox_mapping.yaml`.

    Returns:
        Dict cấu hình.
    """
    import yaml

    resolved = resolve_path(path)
    with resolved.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _entity_record(
    doc: dict[str, Any],
    props: dict[str, Any],
    subject_type: str,
    *,
    dump_version: str = "",
    model_name: str = "",
) -> dict[str, Any]:
    """Dựng record entity cho `infobox_entities.jsonl`.

    Args:
        doc: Record document.
        props: Thuộc tính node đã trích.
        subject_type: Loại node của chủ thể.
        dump_version: Phiên bản dump nguồn (để truy vết).
        model_name: Tên mô hình đã dùng (Phase 3 không dùng mô hình → giá trị
            mặc định của config để hợp đồng artifact thống nhất).

    Returns:
        Dict theo hợp đồng entity.
    """
    title = doc.get("title", "")
    entity_id = make_entity_id(subject_type, title)
    aliases = props.get("aliases", [])
    return {
        "entity_id": entity_id,
        "name": title,
        "name_normalized": normalize_name(title),
        "type": subject_type,
        "aliases": aliases,
        "aliases_normalized": [normalize_name(a["alias"]) for a in aliases],
        "wikidata_qid": doc.get("wikibase_item"),
        "wiki_url": doc.get("url"),
        "verified": False,
        "mention_count": 0,
        "source_method": "infobox",
        "dump_version": dump_version or doc.get("dump_version", ""),
        "model_name": model_name,
        "props": {k: v for k, v in props.items() if k != "aliases"},
    }


def run(
    *,
    documents_path: str | Path,
    triples_path: str | Path,
    entities_path: str | Path,
    mapping_path: str | Path,
    limit: int | None = None,
    dump_version: str = "",
    model_name: str = "",
) -> dict[str, Any]:
    """Chạy pipeline parse infobox.

    Args:
        documents_path: Đường dẫn `documents.jsonl`.
        triples_path: Đường dẫn output triple.
        entities_path: Đườn dẫn output entity.
        mapping_path: Đường dẫn config mapping.
        limit: Giới hạn số bài (để test nhanh).
        dump_version: Phiên bản dump nguồn (ghi vào mọi artifact).
        model_name: Tên mô hình đã dùng (ghi vào mọi artifact).

    Returns:
        Dict thống kê.
    """
    mapping = load_mapping(mapping_path)
    type_map = mapping.get("type_map", {})

    stats: dict[str, Any] = {
        "documents_total": 0,
        "documents_with_infobox": 0,
        "documents_parsed": 0,
        "documents_failed": 0,
        "by_infobox_type": {},
        "person_total": 0,
        "person_parsed": 0,
        "person_with_date_or_family": 0,
        "triples_total": 0,
        "triples_by_relation": {},
        "entities_total": 0,
        "skipped_schema": 0,
        "skipped_gender": 0,
        "skipped_empty": 0,
    }

    triple_buffer: list[dict[str, Any]] = []
    entity_buffer: list[dict[str, Any]] = []

    date_relations = {"sinh_nam", "mat_nam"}
    family_relations = {
        "cha_cua",
        "me_cua",
        "vo_cua",
        "chong_cua",
        "anh_em_cua",
    }

    for doc in read_jsonl(documents_path):
        stats["documents_total"] += 1
        if limit is not None and stats["documents_total"] > limit:
            break

        raw = doc.get("infobox_raw") or ""
        doc_type = doc.get("infobox_type")
        if not raw:
            if doc_type == "person":
                stats["person_total"] += 1
            continue

        stats["documents_with_infobox"] += 1
        extracted = extract_params(raw)
        if extracted is None:
            stats["documents_failed"] += 1
            if doc_type == "person":
                stats["person_total"] += 1
            continue

        infobox_type, params = extracted
        stats["documents_parsed"] += 1
        stats["by_infobox_type"][infobox_type] = stats["by_infobox_type"].get(infobox_type, 0) + 1

        # Loại chủ thể: tên template → `wikidata_signal` → `article` (trung tính).
        # KHÔNG mặc định `person` — bài "Hà Nội" có infobox
        # `{{Thông tin đơn vị hành chính Việt Nam}}` không map được, mặc định
        # `person` sẽ tạo node *Hà Nội* loại `person` (bịa).
        resolved_type = normalize_type(
            infobox_type,
            type_map,
            wikidata_signal=doc.get("wikidata_signal"),
        )
        if resolved_type is None:
            resolved_type = WIKIDATA_SIGNAL_TYPES.get(doc.get("wikidata_signal") or "")
        if resolved_type is None:
            resolved_type = doc_type if doc_type in NODE_TYPES else DEFAULT_TYPE

        triples, props, counters = build_triples(
            doc,
            infobox_type=infobox_type,
            params=params,
            mapping=mapping,
            model_name=model_name,
        )

        stats["skipped_schema"] += counters["skipped_schema"]
        stats["skipped_gender"] += counters["skipped_gender"]
        stats["skipped_empty"] += counters["skipped_empty"]

        triple_buffer.extend(triples)
        for triple in triples:
            relation = triple["relation"]
            stats["triples_by_relation"][relation] = stats["triples_by_relation"].get(relation, 0) + 1

        entity_buffer.append(
            _entity_record(
                doc,
                props,
                resolved_type,
                dump_version=dump_version,
                model_name=model_name,
            )
        )

        # Gate 2: bài person có ≥1 trường ngày hoặc quan hệ gia đình.
        if doc_type == "person" or resolved_type == "person":
            stats["person_total"] += 1
            has_date = any(t["relation"] in date_relations for t in triples)
            has_family = any(t["relation"] in family_relations for t in triples)
            if has_date or has_family or props.get("birth_year") or props.get("death_year"):
                stats["person_with_date_or_family"] += 1

    stats["triples_total"] = len(triple_buffer)
    stats["entities_total"] = len(entity_buffer)

    write_jsonl(triples_path, triple_buffer)
    write_jsonl(entities_path, entity_buffer)

    return stats


def main(argv: Iterable[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh (mặc định lấy từ `sys.argv`).

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Parse infobox → triple (Phase 3)")
    parser.add_argument("--config", default="configs/default.yaml", help="Đường dẫn config chính")
    parser.add_argument(
        "--mapping", default="configs/infobox_mapping.yaml", help="Đường dẫn config mapping"
    )
    parser.add_argument("--input", default=None, help="Đường dẫn documents.jsonl")
    parser.add_argument("--out-triples", default=None, help="Đường dẫn output triple")
    parser.add_argument("--out-entities", default=None, help="Đường dẫn output entity")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số bài")
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = load_config(args.config)
    interim_dir = resolve_path(config.get("paths", {}).get("interim_dir", "data/interim"))

    documents_path = resolve_path(args.input) if args.input else interim_dir / "documents.jsonl"
    triples_path = (
        resolve_path(args.out_triples) if args.out_triples else interim_dir / "infobox_triples.jsonl"
    )
    entities_path = (
        resolve_path(args.out_entities) if args.out_entities else interim_dir / "infobox_entities.jsonl"
    )

    stats = run(
        documents_path=documents_path,
        triples_path=triples_path,
        entities_path=entities_path,
        mapping_path=args.mapping,
        limit=args.limit,
        dump_version=str(config.get("dump", {}).get("dump_version", "")),
        model_name=str(config.get("ner", {}).get("model_name", "")),
    )

    logger.info(
        "Đã parse %d/%d bài có infobox → %d triple, %d entity",
        stats["documents_parsed"],
        stats["documents_with_infobox"],
        stats["triples_total"],
        stats["entities_total"],
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Suy `subject_type` / `object_type` cho node KG từ infobox (Phase 3 — A4).

Vì sao cần module riêng: `docs/09` §Phase 3 yêu cầu
`src/preprocess/infobox_entity_types.py` làm nhiệm vụ *"suy subject_type /
object_type từ infobox type + giá trị"*. Tách riêng để `parse_infobox.py`
không phình to và để test được độc lập.

Nguồn sự thật cho mapping loại:
- `configs/infobox_mapping.yaml` → `type_map` (Phase 3, mở rộng Phase 1)
- `src/preprocess/infobox_parser.py` → `INFOBOX_TYPE_MAP` (Phase 1, fallback)

Quy tắc:
1. **Loại node chỉ gồm 7 giá trị** trong `src/common/schemas.NODE_TYPES`:
   ``person``, ``dynasty``, ``event``, ``place``, ``title``, ``year``, ``article``.
   Infobox loại "battle" → **event** (KG không có node battle, `docs/04` §3.1
   quy định ``chi_huy_tran``: person → event).
2. **Suy giới tính** chủ thể từ: trường ``gioi tinh`` → tiền tố tiêu đề →
   marker trong tên. Chỉ dùng để chọn ``vo_cua`` vs ``chong_cua``.
3. **Suy loại đối tượng** từ giá trị trường: link wiki trỏ tới bài có tiền tố
   "nhà X" → ``dynasty``; "miếu/đền/chùa" → ``place``; "trận X" → ``event``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.common.schemas import NODE_TYPES

#: Loại node cho node `Year` (năm) — không phải entity thường.
YEAR_TYPE = "year"

#: Loại node cho chức vụ / tước hiệu.
TITLE_TYPE = "title"

#: Loại node trung tính khi **không** suy được loại thật.
#:
#: Vì sao không dùng ``person`` làm mặc định: đó là **bịa**. Bài "Hà Nội" /
#: "Cần Thơ" có infobox ``{{Thông tin đơn vị hành chính Việt Nam}}`` — nếu mặc
#: định là ``person`` thì KG sẽ có node *Hà Nội* loại ``person`` (sai).
#: ``article`` là loại node trung tính trong `src/common/schemas.NODE_TYPES`,
#: được dùng khi không có đủ bằng chứng để khẳng định loại thật.
DEFAULT_TYPE = "article"

#: Ánh xạ tín hiệu Wikidata (Phase 1) → loại node KG.
#:
#: `wikidata_signal` là tín hiệu **mạnh** hơn tên template: Wikidata biết
#: "Hà Nội" là `place`, "Trận lụt đồng bằng" là `event`.
WIKIDATA_SIGNAL_TYPES: dict[str, str] = {
    "person": "person",
    "place": "place",
    "dynasty": "dynasty",
    "house": "dynasty",
    "battle": "event",
    "event": "event",
}

#: Loại node mặc định cho **đối tượng** khi không suy được.
#:
#: Khác với chủ thể: đối tượng của một trường infobox không khai báo
#: `value_type` hầu như luôn là **người** (cha, mẹ, vợ, chồng, tiền nhiệm,
#: kế nhiệm…). Trường địa danh luôn được khai báo tường minh trong config.
#: Nếu để mặc định `"article"` thì triple sẽ bị loại hàng loạt (quá khắt khe),
#: nếu để mặc định `"person"` cho **chủ thể** thì node "Hà Nội" bị gán
#: `person` (bịa). Vì vậy hai mặc định này **khác nhau**.
DEFAULT_OBJECT_TYPE = "person"

#: Mặc định khi không truyền config.
DEFAULT_GENDER_KEYS: tuple[str, ...] = ("gioi tinh", "gender", "sex")

#: Bảng giá trị → giới tính (mặc định).
DEFAULT_GENDER_VALUES: dict[str, str] = {
    "nam": "male",
    "nu": "female",
    "gioi tinh nam": "male",
    "gioi tinh nu": "female",
    "male": "male",
    "female": "female",
}

#: Tiền tố tiêu đề → giới tính (mặc định).
DEFAULT_TITLE_GENDER_PREFIXES: dict[str, str] = {
    "ba": "female",
    "ong": "male",
    "bac": "female",
    "cu": "female",
    "co": "female",
    "chu": "male",
    "lady": "female",
    "mrs": "female",
    "ms": "female",
    "miss": "female",
    "mr": "male",
    "sir": "male",
    "dame": "female",
}


@dataclass(slots=True)
class TypeContext:
    """Ngữ cảnh suy loại cho một bài Wikipedia.

    Attributes:
        subject_type: Loại node của chủ thể (bài đang xét).
        subject_gender: Giới tính của chủ thể (``"male"``/``"female"``/``None``).
        object_types: Danh sách loại node được phép cho đối tượng (nếu config
            giới hạn theo trường).
    """

    subject_type: str = DEFAULT_TYPE
    subject_gender: str | None = None
    object_types: list[str] = field(default_factory=list)

    def allows_object(self, object_type: str) -> bool:
        """Kiểm tra loại đối tượng có được phép không.

        Args:
            object_type: Loại node của đối tượng.

        Returns:
            ``True`` nếu hợp lệ (hoặc không có ràng buộc).
        """
        if not self.object_types:
            return True
        return object_type in self.object_types


#: Tiền tố tên template cần bỏ trước khi tra bảng mapping.
#:
#: `wikitextparser` trả về tên template **đầy đủ** ("Infobox military conflict",
#: "Thông tin chiến tranh"), còn `infobox_parser` (Phase 1) đã bỏ tiền tố.
#: Hai nguồn phải hòa về một dạng để bảng `type_map` dùng được cho cả hai.
_TYPE_PREFIXES: tuple[str, ...] = (
    "infobox",
    "thong tin",
    "ban tin",
)


def normalize_type(raw_type: str | None, type_map: dict[str, str] | None = None) -> str | None:
    """Chuẩn hóa tên loại infobox → loại node KG.

    Args:
        raw_type: Tên loại infobox thô (đã bỏ dấu, lowercase).
        type_map: Bảng mapping loại. Nếu ``None`` thì dùng bảng Phase 1.

    Returns:
        Loại node KG hoặc ``None`` nếu không xác định được.
    """
    from src.preprocess.infobox_parser import INFOBOX_TYPE_MAP, normalize_infobox_type
    from src.common.normalize import normalize_name

    if not raw_type:
        return None

    key = normalize_name(raw_type)
    if not key:
        return None

    if type_map:
        # (1) Khớp chính xác trước — bảng `type_map` chứa cả dạng có tiền tố
        #     ("thong tin nhan vat phong kien") lẫn dạng đã bỏ tiền tố
        #     ("nhan vat phong kien"). `wikitextparser` trả tên **đầy đủ**,
        #     `infobox_parser` (Phase 1) trả tên **đã bỏ tiền tố** → thử cả hai.
        if key in type_map:
            return type_map[key]

    # (2) Bỏ tiền tố "infobox" / "thong tin" rồi thử lại.
    stripped = key
    for prefix in _TYPE_PREFIXES:
        if stripped.startswith(prefix + " "):
            stripped = stripped[len(prefix) + 1 :].strip()
            break

    if type_map:
        if stripped in type_map:
            return type_map[stripped]
        # Khớp tiền tố ("monarch của X" → "monarch").
        for prefix, value in sorted(type_map.items(), key=lambda item: -len(item[0])):
            if stripped.startswith(prefix):
                return value

    fallback = normalize_infobox_type(stripped)
    if fallback and fallback in NODE_TYPES:
        return fallback
    if fallback == "battle":
        return "event"
    return None


def _tokenize(text: str) -> list[str]:
    """Tách chuỗi thành các từ (bỏ dấu ngoặc wiki).

    Args:
        text: Chuỗi đã bỏ dấu.

    Returns:
        Danh sách từ.
    """
    cleaned = text.replace("[[", " ").replace("]]", " ").replace("|", " ")
    return [token for token in cleaned.split() if token]


def detect_gender(
    *,
    title: str,
    params: dict[str, str],
    gender_keys: list[str] | None = None,
    gender_values: dict[str, str] | None = None,
    title_prefixes: dict[str, str] | None = None,
) -> str | None:
    """Suy giới tính của chủ thể.

    Thứ tự ưu tiên:
    1. Trường infobox ``gioi tinh`` (nếu có giá trị khớp bảng).
    2. Tiền tố tiêu đề ("Bà Huyện Thanh Quan" → ``female``).
    3. Tên trong infobox ("ten that") — dùng marker "thị" → ``female``.

    Args:
        title: Tiêu đề bài.
        params: Tham số infobox đã chuẩn hóa key.
        gender_keys: Danh sách key chứa giới tính.
        gender_values: Bảng giá trị → giới tính.
        title_prefixes: Bảng tiền tố tiêu đề → giới tính.

    Returns:
        ``"male"``, ``"female"`` hoặc ``None`` nếu không xác định được.
    """
    from src.common.normalize import normalize_name

    keys = gender_keys or DEFAULT_GENDER_KEYS
    values = gender_values or DEFAULT_GENDER_VALUES
    prefixes = title_prefixes or DEFAULT_TITLE_GENDER_PREFIXES

    # 1. Trường infobox
    for key in keys:
        raw = params.get(key)
        if not raw or not raw.strip():
            continue
        normalized = normalize_name(raw)
        if normalized in values:
            return values[normalized]
        # Giá trị có thể là link wiki: "[[Nữ]]" → "nu".
        for token in _tokenize(normalized):
            if token in values:
                return values[token]

    # 2. Tiền tố tiêu đề
    title_norm = normalize_name(title)
    for prefix, gender in sorted(prefixes.items(), key=lambda item: -len(item[0])):
        if title_norm.startswith(f"{prefix} "):
            return gender

    # 3. Tên trong infobox
    for name_key in ("ten that", "ten", "ten khai sinh"):
        raw_name = params.get(name_key)
        if not raw_name or not raw_name.strip():
            continue
        normalized = normalize_name(raw_name)
        if "thị" in normalized.split():
            return "female"
        break

    return None


def infer_object_type(
    value: str,
    *,
    declared_type: str | None = None,
    type_map: dict[str, str] | None = None,
) -> str:
    """Suy loại node của một giá trị trong infobox.

    Thứ tự ưu tiên:
    1. Loại khai báo trong config (``value_type``) — đáng tin nhất.
    2. Suy từ nội dung giá trị (link wiki, tiền tố "nhà X", "trận X"...).

    Lưu ý: hàm có thể trả về ``"organization"`` — đây **không** phải loại node KG
    (KG chỉ có 7 loại). Việc trả về giá trị này giúp phát hiện và **loại bỏ**
    triple không đúng schema thay vì gán nhầm vào `person`.

    Args:
        value: Giá trị thô của trường.
        declared_type: Loại đã khai báo trong config.
        type_map: Bảng mapping loại (dùng khi suy từ tên bài đích).

    Returns:
        Loại node KG (hoặc ``"organization"`` nếu là tổ chức).
    """
    text = (value or "").strip()

    if declared_type:
        # Vẫn phải loại tổ chức trước: `combatant1` khai báo `person` nhưng
        # giá trị thực tế là phe phái / quân đội ("Nam Hán", "Hoa Kỳ") — gán vào
        # `person` là bịa.
        from src.common.normalize import normalize_name

        if declared_type == "person":
            for candidate in _wikilink_targets(text) or [text]:
                if _looks_like_organization(normalize_name(candidate)):
                    return "organization"
        return declared_type

    if not text:
        return DEFAULT_OBJECT_TYPE

    from src.common.normalize import normalize_name

    # Link wiki trỏ tới bài "Nhà Lý" → dynasty
    for candidate in _wikilink_targets(text):
        normalized = normalize_name(candidate)
        if normalized.startswith("nha "):
            return "dynasty"
        if normalized.startswith("tran ") or normalized.startswith("chien tranh"):
            return "event"
        if normalized.startswith(("dai hoc ", "truong ", "cong trinh ")):
            return "place"

    # Văn bản thuần (không có link)
    normalized = normalize_name(text)
    if normalized.startswith("nha "):
        return "dynasty"
    if normalized.startswith(("tran ", "chien tranh ")):
        return "event"
    if normalized.startswith(("dai hoc ", "truong ", "cong trinh ")):
        return "place"
    if _looks_like_organization(normalized):
        return "organization"

    return DEFAULT_OBJECT_TYPE


#: Tiền tố chỉ **tổ chức / quân đội / phe phái** — không phải cá nhân.
_ORGANIZATION_PREFIXES: tuple[str, ...] = (
    "mat tran",
    "doi ",
    "quan doi",
    "quan ",
    "lien hiep",
    "chua ",
    "phe",
    "doi doi",
    "gia dinh hoang gia",
    "toan quyen",
    "chi vien",
    "nha nuoc",
    "chinh phu",
    "co quan",
    "phap vichy",
    "tinh bao",
    "viện ",
    "hội ",
    "đội ",
    "nhà ",
)

#: Tiền tố chỉ **quốc gia / chủ tịch nước** — không phải cá nhân.
_COUNTRY_SUFFIXES: tuple[str, ...] = (
    "hoa ky",
    "phap",
    "nhat ban",
    "trung quoc",
    "viet nam",
    "laos",
    "campuchia",
    "thong tri nuoc",
    "nuoc",
    "dong duong",
    "viet minh",
    "nuoc dai hoc phap",
)

#: Từ khoá chỉ **tổ chức** xuất hiện ở giữa tên ("Pháp Vichy", "Hoa Kỳ").
_ORGANIZATION_KEYWORDS: tuple[str, ...] = (
    "vichy",
    "gia minh",
    "dai hoc phap",
    "chieu khong",
)


def _looks_like_organization(normalized: str) -> bool:
    """Kiểm tra tên đã bỏ dấu có phải tổ chức hay không.

    Args:
        normalized: Tên đã bỏ dấu, lowercase.

    Returns:
        ``True`` nếu là tổ chức/quân đội.
    """
    for prefix in _ORGANIZATION_PREFIXES:
        if normalized.startswith(prefix):
            return True
    for suffix in _COUNTRY_SUFFIXES:
        if normalized == suffix or normalized.endswith(f" {suffix}"):
            return True
    for keyword in _ORGANIZATION_KEYWORDS:
        if keyword in normalized:
            return True
    return False


def _wikilink_targets(text: str) -> list[str]:
    """Trích các đích của liên kết wiki trong chuỗi.

    Args:
        text: Chuỗi wikitext.

    Returns:
        Danh sách tên bài đích (giữ dấu).
    """
    import re

    targets: list[str] = []
    for match in re.finditer(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", text):
        targets.append(match.group(1).strip())
    return targets


def build_context(
    *,
    infobox_type: str | None,
    title: str,
    params: dict[str, str],
    type_map: dict[str, str] | None = None,
    gender_keys: list[str] | None = None,
    gender_values: dict[str, str] | None = None,
    title_prefixes: dict[str, str] | None = None,
    object_types: list[str] | None = None,
    wikidata_signal: str | None = None,
) -> TypeContext:
    """Dựng `TypeContext` cho một bài.

    Thứ tự ưu tiên khi xác định loại chủ thể:

    1. Tên loại infobox → `type_map` (mạnh nhất, biên tập viên chọn template).
    2. `wikidata_signal` (Phase 1) — Wikidata biết "Hà Nội" là `place`,
       "Trận lụt đồng bằng" là `event`.
    3. `DEFAULT_TYPE` (``"article"``) — loại trung tính, **không phải** ``person``.

    Args:
        infobox_type: Tên loại infobox thô.
        title: Tiêu đề bài.
        params: Tham số infobox (key đã chuẩn hóa).
        type_map: Bảng mapping loại.
        gender_keys: Key chứa giới tính.
        gender_values: Bảng giá trị giới tính.
        title_prefixes: Bảng tiền tố tiêu đề → giới tính.
        object_types: Ràng buộc loại đối tượng (nếu có).
        wikidata_signal: Tín hiệu loại từ Wikidata (Phase 1).

    Returns:
        Đối tượng `TypeContext`.
    """
    subject_type = normalize_type(infobox_type, type_map)
    if subject_type is None:
        subject_type = WIKIDATA_SIGNAL_TYPES.get(wikidata_signal or "")
    if subject_type is None:
        subject_type = DEFAULT_TYPE
    gender = detect_gender(
        title=title,
        params=params,
        gender_keys=gender_keys,
        gender_values=gender_values,
        title_prefixes=title_prefixes,
    )
    return TypeContext(
        subject_type=subject_type,
        subject_gender=gender,
        object_types=list(object_types or []),
    )


def relation_for_gender(relation: str, gender: str | None) -> str:
    """Điều chỉnh quan hệ theo giới tính chủ thể.

    Quan hệ ``vo_cua`` / ``chong_cua`` cần biết chủ thể là nam hay nữ:
    - nam → ``vo_cua`` (anh là vợ của bà ấy)
    - nữ → ``chong_cua`` (bà ấy là chồng của anh ấy)

    Quan hệ khác giữ nguyên.

    Args:
        relation: Quan hệ gốc.
        gender: Giới tính chủ thể.

    Returns:
        Quan hệ đã điều chỉnh.
    """
    if gender == "female" and relation == "vo_cua":
        return "chong_cua"
    if gender == "male" and relation == "chong_cua":
        return "vo_cua"
    return relation

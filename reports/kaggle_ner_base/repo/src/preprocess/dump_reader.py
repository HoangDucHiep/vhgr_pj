"""Đọc dump Wikipedia theo luồng (streaming) bằng `lxml.etree.iterparse`.

Vì sao không dùng `mwparser`: PyPI chỉ có bản 0.1 (bản 0.6.2 chưa publish) —
xem `reports/deviations.md` D-003/D-004. `lxml` nhanh hơn và hỗ trợ streaming
nên không cần nạp toàn bộ file 1.1 GB vào RAM.

Cấu trúc dump viwiki (đã kiểm chứng 13/11/2026):

```xml
<page>
  <title>Lê Lợi</title>
  <ns>0</ns>
  <id>12345</id>
  <redirect title="..." />            <!-- nếu là redirect -->
  <revision>
    <id>99000000</id>
    <timestamp>2026-01-01T00:00:00Z</timestamp>
    <text xml:space="preserve">...wikitext...</text>
  </revision>
</page>
```

Redirect **không** có file riêng ở viwiki — nằm trong `pages-articles.xml.bz2`
dưới thẻ `<redirect>` (đã kiểm chứng: `dumps.wikimedia.org/viwiki/20261101/`
chỉ có `pages-articles` và `pages-meta-current`).
"""

from __future__ import annotations

import bz2
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from lxml import etree

# Namespace của MediaWiki export
MW_NS = "{http://www.mediawiki.org/xml/export-0.11/}"

#: Thẻ namespace có tiền tố trong wikitext — các link tới đây KHÔNG phải bài viết.
NON_ARTICLE_PREFIXES: frozenset[str] = frozenset(
    {
        "thể loại",
        "thể loại chung",
        "wikipedia",
        "tập tin",
        "tập tin điện tử",
        "chủ đề",
        "portal",
        "wikiproject",
        "help",
        "mediawiki",
        "đầu vào",
        "module",
        "sơ đồ",
        "bản mẫu",
        "đặc biệt",
        "từ điển",
        "thư viện",
    }
)

#: Regex trích link nội bộ `[[Tiêu đề|nhãn]]` hoặc `[[Tiêu đề#đoạn|nhãn]]`.
_LINK_RE = re.compile(r"\[\[([^\[\]\|]{1,300})(?:\|[^\[\]]*)?\]\]")

#: Regex trích category `[[Thể loại:Tên]]`.
_CATEGORY_RE = re.compile(r"\[\[\s*Thể\s+loại\s*:\s*([^\]\|\n]{1,200})\]\]", re.IGNORECASE)

#: Regex nhận diện template infobox: `{{Infobox person|...}}` hoặc `{{Thông tin ...}}`.
#: Tên template có thể chứa dấu tiếng Việt (vd "Thông tin nhân vật") nên lớp ký tự
#: cho phép chữ Unicode.
_INFOBOX_RE = re.compile(
    r"\{\{\s*(?:Infobox|Thông\s+tin)\s*"
    r"([\w][\w \-]{0,60}?)\s*(?:\||\}\})",
    re.IGNORECASE | re.UNICODE,
)

#: Các tiền tố template infobox được chuẩn hóa về loại node.
_INFOBOX_TYPE_MAP: dict[str, str] = {
    "monarch": "person",
    "king": "person",
    "queen": "person",
    "emperor": "person",
    "person": "person",
    "nhân vật": "person",
    "người": "person",
    "vua": "person",
    "hoàng đế": "person",
    "hoàng hậu": "person",
    "công tước": "person",
    "tướng": "person",
    "danh nhân": "person",
    "bí thư": "person",
    "thủ tướng": "person",
    "nhà sử học": "person",
    "nhà thơ": "person",
    "nhà văn": "person",
    "nhà khoa học": "person",
    "nhà chính trị": "person",
    "thần thông": "person",
    "saint": "person",
    "dynasty": "dynasty",
    "nhà": "dynasty",
    "triều đại": "dynasty",
    "triều": "dynasty",
    "house": "dynasty",
    "battle": "battle",
    "trận": "battle",
    "trận đánh": "battle",
    "military conflict": "battle",
    "chiến tranh": "battle",
    "cuộc chiến": "battle",
    "event": "event",
    "sự kiện": "event",
    "historical event": "event",
    "place": "place",
    "địa danh": "place",
    "location": "place",
    "settlement": "place",
    "công trình": "place",
    "lăng mộ": "place",
    "đền": "place",
    "chùa": "place",
    "miếu": "place",
    "cung điện": "place",
    "dynasty timeline": "dynasty",
    "lịch sử": "dynasty",
    "timeline": "dynasty",
}


@dataclass(slots=True)
class DumpPage:
    """Một trang trong dump.

    Attributes:
        page_id: ID trang.
        title: Tiêu đề bài.
        ns: Namespace (0 = bài viết).
        revision_id: ID phiên bản.
        timestamp: Thời điểm sửa đổi (ISO-8601).
        is_redirect: Có phải trang redirect không.
        redirect_target: Tiêu đề đích của redirect.
        wikitext: Nội dung wikitext thô.
        categories: Danh sách category (không có tiền tố "Thể loại:").
        links: Danh sách tiêu đề bài viết nội bộ được link tới.
        infobox_type: Loại infobox đã chuẩn hóa (vd ``person``).
        qid: QID Wikidata lấy từ ``page_props/wikibase_item`` (nếu có).
    """

    page_id: int
    title: str
    ns: int
    revision_id: int
    timestamp: str
    is_redirect: bool
    redirect_target: str | None
    wikitext: str
    categories: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    infobox_type: str | None = None
    qid: str | None = None


def _clean_title(raw: str) -> str:
    """Chuẩn hóa tiêu đề link nội bộ.

    Args:
        raw: Tiêu đề thô lấy từ wikitext.

    Returns:
        Tiêu đề đã bỏ khoảng trắng thừa và phần sau dấu ``#``.
    """
    title = raw.strip()
    if "#" in title:
        title = title.split("#", 1)[0].strip()
    return title


def extract_categories(wikitext: str) -> list[str]:
    """Trích danh sách category từ wikitext.

    Args:
        wikitext: Nội dung wikitext.

    Returns:
        Danh sách tên category (giữ nguyên dấu, không có tiền tố namespace).
    """
    seen: list[str] = []
    known: set[str] = set()
    for match in _CATEGORY_RE.finditer(wikitext):
        name = match.group(1).strip()
        if name and name not in known:
            known.add(name)
            seen.append(name)
    return seen


def extract_links(wikitext: str) -> list[str]:
    """Trích danh sách link nội bộ tới bài viết (namespace 0).

    Args:
        wikitext: Nội dung wikitext.

    Returns:
        Danh sách tiêu đề bài viết (không trùng lặp, giữ nguyên thứ tự xuất hiện).
    """
    seen: list[str] = []
    known: set[str] = set()
    for match in _LINK_RE.finditer(wikitext):
        raw = match.group(1)
        title = _clean_title(raw)
        if not title:
            continue
        # Link dạng ":Thể loại:X" (tiền tố ":" để ép liên kết không phân loại).
        if title.startswith(":"):
            title = title[1:].strip()
            if not title:
                continue
        if ":" in title:
            prefix = title.split(":", 1)[0].strip().lower()
            if prefix in NON_ARTICLE_PREFIXES:
                continue
            # Link ngôn ngữ khác ("en:Foo") → không phải bài viết tiếng Việt.
            if re.fullmatch(r"[a-z]{2,3}", prefix):
                continue
            # Link có namespace lạ (ví dụ "Học:") → bỏ qua cho an toàn.
            if prefix.startswith("http") or prefix.startswith("www"):
                continue
        if title.lower() in known:
            continue
        known.add(title.lower())
        seen.append(title)
    return seen


def extract_infobox_type(wikitext: str) -> str | None:
    """Suy ra loại infobox từ wikitext.

    Args:
        wikitext: Nội dung wikitext.

    Returns:
        Loại đã chuẩn hóa (``person``/``dynasty``/``battle``/``event``/``place``)
        hoặc ``None`` nếu không có infobox nhận diện được.
    """
    head = wikitext[:6000]
    for match in _INFOBOX_RE.finditer(head):
        raw = match.group(1).strip().lower()
        if not raw:
            continue
        if raw in _INFOBOX_TYPE_MAP:
            return _INFOBOX_TYPE_MAP[raw]
        # Thử khớp tiền tố ("monarch của X" -> "monarch").
        for key, value in _INFOBOX_TYPE_MAP.items():
            if raw.startswith(key):
                return value
    return None


def _tag_text(element: etree._Element, tag: str) -> str | None:
    """Lấy nội dung text của một thẻ con.

    Args:
        element: Phần tử cha.
        tag: Tên thẻ (không kèm namespace).

    Returns:
        Nội dung text hoặc ``None``.
    """
    child = element.find(f"{MW_NS}{tag}")
    if child is None:
        return None
    return child.text


def iter_dump_pages(path: str | Path) -> Iterator[DumpPage]:
    """Duyệt các trang trong file dump theo luồng.

    Hàm **generator**: chỉ giữ một trang trong RAM tại mỗi thời điểm, nên có thể
    xử lý file 1.1 GB với RAM rất nhỏ.

    Args:
        path: Đường dẫn file `.xml.bz2`.

    Yields:
        Đối tượng `DumpPage` cho từng trang (kể cả namespace khác 0 —
        bộ lọc ở tầng trên sẽ loại).
    """
    file_path = Path(path)
    # `lxml` không đọc trực tiếp file .bz2 → dùng XMLPullParser và đẩy chunk
    # giải nén vào. `parser.read_events()` trả về các sự kiện đã hoàn tất.
    parser = etree.XMLPullParser(
        events=("end",), tag=f"{MW_NS}page", huge_tree=True, resolve_entities=False
    )

    with bz2.open(file_path, "rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            parser.feed(chunk)
            for _event, element in parser.read_events():
                page = _page_from_element(element)
                if page is not None:
                    yield page
                element.clear()
                while element.getprevious() is not None:
                    del element.getparent()[0]

    for _event, element in parser.read_events():
        page = _page_from_element(element)
        if page is not None:
            yield page
        element.clear()
        while element.getprevious() is not None:
            del element.getparent()[0]


def _page_from_element(element: etree._Element) -> DumpPage | None:
    """Chuyển thẻ ``<page>`` thành đối tượng `DumpPage`.

    Args:
        element: Phần tử ``<page>``.

    Returns:
        `DumpPage` hoặc ``None`` nếu thiếu trường bắt buộc.
    """
    title = _tag_text(element, "title")
    ns_text = _tag_text(element, "ns")
    id_text = _tag_text(element, "id")
    if not title or ns_text is None or id_text is None:
        return None

    redirect_el = element.find(f"{MW_NS}redirect")
    is_redirect = redirect_el is not None
    redirect_target = redirect_el.get("title") if is_redirect else None

    revision = element.find(f"{MW_NS}revision")
    if revision is None:
        return None

    revision_id_text = _tag_text(revision, "id") or "0"
    timestamp = _tag_text(revision, "timestamp") or ""
    text_el = revision.find(f"{MW_NS}text")
    wikitext = text_el.text if text_el is not None and text_el.text else ""

    # QID nằm ở <page_props><wikibase_item>Q...</wikibase_item></page_props>
    qid: str | None = None
    page_props = element.find(f"{MW_NS}page_props")
    if page_props is not None:
        item_el = page_props.find(f"{MW_NS}wikibase_item")
        if item_el is not None and item_el.text:
            qid = item_el.text.strip()

    return DumpPage(
        page_id=int(id_text),
        title=title,
        ns=int(ns_text),
        revision_id=int(revision_id_text),
        timestamp=timestamp,
        is_redirect=is_redirect,
        redirect_target=redirect_target,
        wikitext=wikitext,
        categories=extract_categories(wikitext),
        links=extract_links(wikitext),
        infobox_type=extract_infobox_type(wikitext),
        qid=qid,
    )

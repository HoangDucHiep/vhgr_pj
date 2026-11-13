"""Làm sạch wikitext thành văn bản thuần (Module A2 — Phase 2).

## Thứ tự thao tác (quan trọng)

1. Tách `{{Infobox ...}}` / `{{Thông tin ...}}` ra trước → lưu vào `infobox_raw`
   (Phase 3 dùng).
2. Xoá mọi template còn lại (cân bằng ngoặc kép) — bao gồm `{{cite...}}`,
   `{{tham khảo}}`, `{{chú thích}}`.
3. Xoá thẻ `<ref>...</ref>`, `<ref .../>`, `<ref ...>`.
4. Xoá `[[File:...]]`, `[[Tập tin:...]]`, `[[Image:...]]`.
5. Xoá link category `[[Thể loại:...]]`.
6. Xoá bảng `{| ... |}` (cân bằng `{|` / `|}`) + các dòng bảng còn sót.
7. Xoá HTML còn lại (`<br>`, `<span ...>`, `</span>`, `<!-- -->`).
8. Chuyển link nội bộ `[[Đích|anchor]]` → `anchor` **và ghi lại mục `links`
   trước khi thay thế**; `[[Đích]]` → `Đích` với `anchor == target`.
9. Giữ tiêu đề `== X ==` → dòng riêng, đánh dấu `heading`.
10. Chuẩn hóa whitespace, gỡ markup danh sách, nối dòng xuống dòng cứng.

## Ba lỗi thực đo được trên corpus 2.441 bài (đã sửa ở đây)

1. **Offset của link bị lệch ở 502 bài** — `_strip_stray_markers` chạy *sau* khi
   đã ghi offset nên mọi ký tự `[[`/`]]` bị xoá đều dịch các link phía sau.
   → Sửa: xoá ngoặc lạc **trước** khi thay link.
2. **Văn bản bị vỡ câu ở mỗi dòng** — Wikipedia xuống dòng cứng ~80 ký tự,
   `pysbd` tách câu tại mỗi `\n` nên "Ông sinh năm\\n1385 ở Lam Sơn" thành 2 câu.
   → Sửa: nối các dòng thuộc cùng đoạn bằng khoảng trắng.
3. **Markup danh sách `*` `#` `:` `;` còn sót** và còn dòng bảng `|-`, `| x`.
   → Sửa: gỡ marker, tách mỗi item thành đoạn riêng, xoá dòng bảng.

## Vì sao ghi `links` trước khi thay thế

Phase 4 dùng hyperlink làm nguồn nhãn NER bạc; nếu thay link trước rồi trích
sau thì mất hoàn toàn thông tin đích. Vì vậy bước 8 ghi đè mọi link nội bộ
vào danh sách `links` kèm offset trong `clean_text` **sau khi** thay thế.

Cách chạy:
    python -m src.preprocess.clean_text --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT, load_config
from src.common.logger import get_logger
from src.common.text_utils import paragraph_spans, read_jsonl

logger = get_logger(__name__)

#: Regex thẻ HTML cần xoá (kể cả nội dung cho `<ref>`).
_REF_BLOCK_RE = re.compile(r"<ref\b[^>/]*>.*?</ref>", re.IGNORECASE | re.DOTALL)
_REF_SELF_RE = re.compile(r"<ref\b[^>]*/>", re.IGNORECASE)
#: Thẻ `<ref>` **không đóng** — chỉ xoá tới khi gặp thẻ `<ref>`/`</ref>` kế
#: tiếp, KHÔNG xoá tới cuối văn bản.
#:
#: Bản cũ dùng `.*?(?=<ref\b|</ref>|$)` → khi văn bản không còn `</ref>` nào,
#: nhánh `$` khớp và **xoá sạch phần còn lại của bài**. Đo được ở bài "Hà Nội":
#: 95 dòng danh sách bị mất, chỉ còn 15.
_REF_OPEN_RE = re.compile(r"<ref\b[^>]*>.*?(?=<ref\b|</ref>)", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")

#: Link tới tập tin (ns 6) hoặc thể loại (ns 14) — xoá hẳn khi thay link.
_EXCLUDED_LINK_RE = re.compile(
    r"^(?:File|Tập tin|Image|Hình|Thể loại)\s*:", re.IGNORECASE
)

#: Link nội bộ: `[[Đích|anchor]]` hoặc `[[Đích]]`, có thể kèm `#anchor`.
#:
#: Vì wikitext thật có **link lồng nhau**
#: (vd `[[Tập tin:X.jpg|nhỏ|[[Đê sông Hồng]] và [[Dãy núi Ba Vì]]]]`),
#: regex phẳng không xử lý được → dùng bộ quét cân bằng ngoặc.
_WIKILINK_START_RE = re.compile(r"\[\[")

#: Đầu dòng tiêu đề `== X ==` (2–4 dấu `=`).
_HEADING_RE = re.compile(r"^\s*(={2,4})\s*(.+?)\s*\1\s*$", re.MULTILINE)

#: Khoảng trắng liên tiếp.
_MULTISPACE_RE = re.compile(r"[ \t ]+")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")

#: Dấu in đậm/nghiêng của wikitext (2 hoặc nhiều dấu nháy đơn).
_BOLD_ITALIC_RE = re.compile(r"'{2,}")

#: Link ngoài: `[nhãn](http://...)` hoặc `[http://...]` — giữ phần nhãn.
_EXTERNAL_LINK_RE = re.compile(r"\[([^\[\]]*?)\]\((?:https?:|//)[^()\s]+\)")

#: Link ngoài dạng thô: `[http://...]` (không có nhãn).
_BARE_URL_RE = re.compile(r"\[(https?://[^\[\]\s]+)\]")

#: Anchor "mồ côi" của link hỏng: `|nhãn]]` (mở `[[` đã bị nuốt mất).
_ORPHAN_ANCHOR_RE = re.compile(r"\|([^|\[\]\n]{1,120})\]\]")

#: Đuôi `|nhãn` bám vào cuối một đoạn văn — dấu hiệu anchor mồ côi.
_TRAILING_ORPHAN_RE = re.compile(r"\|([^|\[\]\n]{1,120})$")

#: Markup danh sách ở đầu dòng: `*`, `#`, `;`, `:` (có thể lặp để tạo thụt lề).
#:
#: Bắt buộc phải gỡ trước khi tách câu — nếu không, mỗi item danh sách bị
#: tính thành một "câu" không kết thúc bằng dấu câu (đo được: 15,8% câu
#: trong corpus là item danh sách).
_LIST_MARK_RE = re.compile(r"^[ \t]*([*#:;]+)[ \t]*(.*)$")

#: Dòng bảng còn sót sau khi xoá `{| ... |}`: `|-`, `|`, `!`, `|}`, `|+`.
_TABLE_ROW_RE = re.compile(r"^[ \t]*[|!][^\n]*$")

#: Link trong tiêu đề: `[[Đích|anchor]]` → `anchor`, `[[Đích]]` → `Đích`.
_WIKILINK_TEXT_RE = re.compile(r"\[\[(?:[^\[\]|]*\|)?([^\[\]|]*)\]\]")

#: Ký tự đánh dấu mục danh sách (Private Use Area — không xuất hiện trong text).
#:
#: Vì sao cần sentinel thay vì so khớp theo nội dung
#: --------------------------------------------------
#: Nội dung mục danh sách **thay đổi** trong quá trình xử lý: `[[Bắc Ninh]]`
#: thành `Bắc Ninh` sau bước thay link. Nếu so khớp nội dung trước/sau
#: bước thay link thì không khớp (đo được: mọi mục danh sách ở bài "Hà Nội"
#: bị tính nhầm là văn xuôi). Sentinel đi cùng văn bản qua mọi bước nên
#: luôn chính xác; cuối cùng bị gỡ bằng `_strip_sentinel`.
_LIST_SENTINEL = "\ue000"


@dataclass(slots=True)
class CleanResult:
    """Kết quả làm sạch một bài.

    Attributes:
        clean_text: Văn bản thuần đã làm sạch.
        infobox_raw: Khối infobox gốc (nếu có).
        links: Danh sách hyperlink nội bộ với offset trong `clean_text`.
        headings: Danh sách tiêu đề mục đã trích.
        paragraph_kinds: Nhãn từng đoạn — ``"prose"`` (văn xuôi) hoặc
            ``"list_item"`` (mục danh sách). Thứ tự khớp với các đoạn mà
            `split_sentences` sẽ tách ra.
    """

    clean_text: str = ""
    infobox_raw: str = ""
    links: list[dict[str, Any]] = field(default_factory=list)
    headings: list[dict[str, Any]] = field(default_factory=list)
    paragraphs: list[dict[str, Any]] = field(default_factory=list)
    paragraph_kinds: list[str] = field(default_factory=list)


def _find_matching_braces(text: str, start: int) -> int:
    """Tìm vị trí đóng `}}` của khối template bắt đầu tại `start`.

    Args:
        text: Văn bản.
        start: Vị trí bắt đầu (trỏ vào `{{`).

    Returns:
        Vị trí sau `}}` đóng, hoặc `-1` nếu không tìm thấy.
    """
    depth = 0
    index = start
    length = len(text)
    while index < length - 1:
        pair = text[index : index + 2]
        if pair == "{{":
            depth += 1
            index += 2
            # `{{{...}}}` — tham số chứa tham số: ngoặc thứ 3 thuộc về nội dung.
            if index < length and text[index] == "{":
                index += 1
            continue
        if pair == "}}":
            depth -= 1
            index += 2
            if depth == 0:
                return index
            continue
        index += 1
    return -1


def _extract_infobox(wikitext: str) -> tuple[str, str]:
    """Tách khối infobox đầu tiên ra khỏi wikitext.

    Args:
        wikitext: Wikitext gốc.

    Returns:
        Tuple ``(wikitext_without_infobox, infobox_raw)``.
    """
    head = wikitext[:12000]
    match = re.search(
        r"\{\{\s*(?:Infobox|Thông\s+tin)\s*[\w][\w \-]{0,60}?\s*(?:\||\}\})",
        head,
        re.IGNORECASE | re.UNICODE,
    )
    if match is None:
        return wikitext, ""

    block_start = match.start()
    block_end = _find_matching_braces(head, block_start)
    if block_end == -1:
        return wikitext, ""

    infobox_raw = head[block_start:block_end]
    return wikitext[:block_start] + wikitext[block_end:], infobox_raw


def _remove_templates(text: str) -> str:
    """Xoá toàn bộ template còn lại (cân bằng ngoặc kép).

    Args:
        text: Văn bản.

    Returns:
        Văn bản đã bỏ template.
    """
    result: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        start = text.find("{{", index)
        if start == -1:
            result.append(text[index:])
            break
        result.append(text[index:start])
        end = _find_matching_braces(text, start)
        if end == -1:
            # Template không đóng → bỏ phần còn lại (an toàn).
            break
        index = end
    return "".join(result)


def _remove_tables(text: str) -> str:
    """Xoá bảng wiki `{| ... |}` (cân bằng `{|` và `|}`).

    Args:
        text: Văn bản.

    Returns:
        Văn bản đã bỏ bảng.
    """
    result: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        start = text.find("{|", index)
        if start == -1:
            result.append(text[index:])
            break
        result.append(text[index:start])
        end = text.find("|}", start)
        if end == -1:
            break
        index = end + 2
    return "".join(result)


def _remove_table_rows(text: str) -> str:
    """Xoá các dòng bảng còn sót sau khi đã xoá khối `{| ... |}`.

    Wikitext thật có bảng **lồng nhau** (bảng ngoài chứa bảng trong), nên bộ
    quét `{|`/`|}` đơn giản bỏ sót phần đuôi. Đo được trên corpus: 77.882
    dòng bắt đầu bằng `|` và 2.198 dòng bắt đầu bằng `!` còn sót lại.

    Args:
        text: Văn bản.

    Returns:
        Văn bản đã bỏ dòng bảng.
    """
    lines = text.split("\n")
    kept = [line for line in lines if not _TABLE_ROW_RE.match(line)]
    return "\n".join(kept)


def _strip_list_markers(text: str) -> tuple[str, list[str]]:
    """Gỡ markup danh sách ở đầu dòng, tách mỗi item thành đoạn riêng.

    Wikitext dùng ``*``, ``#``, ``;``, ``:`` ở đầu dòng để đánh dấu danh
    sách. Ba hệ quả nếu không gỡ:

    1. Mỗi item bị `pysbd` coi là một câu riêng không kết thúc bằng dấu câu.
    2. Marker `:` đầu dòng làm nhiễu mốc "câu dẫn danh sách" (vd "Các điểm
       cực của thủ đô Hà Nội là:") — câu dẫn này vốn hợp lệ.
    3. Dòng tiếp nối (thụt lề bằng khoảng trắng) phải được nối vào item
       trước, nếu không sẽ thành văn xuôi "mồ côi".

    Mỗi item được tách bằng dòng trống để `split_sentences` coi là đoạn riêng.

    Vì sao cần trả về `kinds`
    -----------------------
    Mục danh sách **không phải câu** — nó là một mệnh đề ngắn, không có dấu
    kết thúc. Đo được trên corpus: 3.656 câu (2,2% trong 167.493) kết thúc
    bằng chữ cái vì là mục danh sách. Để đo tỉ lệ "câu kết thúc bằng dấu câu"
    một cách trung thực, cần biết đoạn nào là văn xuôi và đoạn nào là mục
    danh sách → trả về nhãn theo thứ tự đoạn.

    Args:
        text: Văn bản.

    Returns:
        Tuple ``(văn bản đã gỡ marker, nội dung các mục danh sách)``.
    """
    blocks: list[str] = []
    item_texts: list[str] = []
    prose: list[str] = []
    item: str | None = None

    def flush_prose() -> None:
        if prose:
            blocks.append(" ".join(prose))
            prose.clear()

    def flush_item() -> None:
        nonlocal item
        if item is not None:
            if item:
                # Đánh dấu bằng sentinel để nhận biết mục danh sách sau khi
                # thay link (nội dung đã thay đổi).
                blocks.append(f"{_LIST_SENTINEL}{item}")
                item_texts.append(item)
            item = None

    for raw_line in text.split("\n"):
        stripped = raw_line.strip()
        if not stripped:
            flush_prose()
            flush_item()
            continue

        match = _LIST_MARK_RE.match(raw_line)
        if match:
            flush_prose()
            flush_item()
            item = match.group(2).strip()
            continue

        # Dòng thụt lề (bắt đầu bằng khoảng trắng) là phần tiếp của item.
        if item is not None and raw_line[:1] in (" ", "\t"):
            item = f"{item} {stripped}".strip()
            continue

        flush_item()
        prose.append(stripped)

    flush_prose()
    flush_item()

    # Mỗi khối (đoạn văn xuôi hoặc mục danh sách) là MỘT đoạn riêng, ngăn
    # cách bằng dòng trống — `split_sentences` tách đoạn theo `\n\n`.
    result = "\n\n".join(blocks)
    return result, item_texts


def _resolve_wikilink(raw_target: str, raw_anchor: str | None) -> tuple[str, str]:
    """Tách đích và anchor của một link nội bộ.

    Args:
        raw_target: Phần trước `|` (có thể chứa `#`).
        raw_anchor: Phần sau `|` hoặc `None`.

    Returns:
        Tuple ``(target, anchor)``.
    """
    target = raw_target.strip()
    if target.startswith(":"):
        target = target[1:].strip()
    if "#" in target:
        target = target.split("#", 1)[0].strip()
    anchor = (raw_anchor or "").strip()
    if not anchor:
        anchor = target
    return target, anchor


def _find_link_end(text: str, start: int) -> int:
    """Tìm vị trí đóng `]]` của một link bắt đầu tại `start`.

    Quét có đếm độ sâu `[[` để xử lý link lồng nhau.

    Args:
        text: Văn bản.
        start: Vị trí bắt đầu (trỏ vào `[[`).

    Returns:
        Vị trí sau `]]` đóng, hoặc `-1` nếu không tìm thấy.
    """
    depth = 0
    index = start
    length = len(text)
    while index < length - 1:
        if text[index : index + 2] == "[[":
            depth += 1
            index += 2
            continue
        if text[index : index + 2] == "]]":
            depth -= 1
            index += 2
            if depth == 0:
                return index
            continue
        index += 1
    return -1


def _innermost_links(text: str) -> list[tuple[int, int, str]]:
    """Tìm các link **không chứa** link khác bên trong.

    Args:
        text: Văn bản.

    Returns:
        Danh sách ``(start, end, raw)`` — ``raw`` là nội dung giữa `[[` và `]]`.
    """
    found: list[tuple[int, int, str]] = []
    for match in _WIKILINK_START_RE.finditer(text):
        if match.start() < 0:
            continue
        end = _find_link_end(text, match.start())
        if end == -1:
            continue
        raw = text[match.start() + 2 : end - 2]
        if "[[" in raw:
            continue
        found.append((match.start(), end, raw))
    return found


def _find_top_level_pipe(raw: str) -> int:
    """Tìm vị trí dấu ``|`` phân tách đích/anchor, bỏ qua ``|`` trong link lồng nhau.

    Args:
        raw: Nội dung giữa `[[` và `]]`.

    Returns:
        Vị trí của ``|`` phân tách đầu tiên, hoặc ``-1`` nếu không có.
    """
    depth = 0
    index = 0
    length = len(raw)
    while index < length:
        if raw.startswith("[[", index):
            depth += 1
            index += 2
            continue
        if raw.startswith("]]", index):
            depth -= 1
            index += 2
            continue
        if depth == 0 and raw[index] == "|":
            return index
        index += 1
    return -1


def _replace_wikilinks(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Thay link nội bộ bằng anchor, đồng thời ghi lại thông tin link.

    Vì sao phải viết theo kiểu quét một lần + đệ quy
    -------------------------------------------------
    Bản cũ chạy **nhiều vòng**: mỗi vòng thay các link "trong cùng" (không chứa
    link khác). Vấn đề: link thuộc loại *bị xoá* (`[[File:...]]`,
    `[[Thể loại:...]]`) ở vòng sau làm **dịch toàn bộ văn bản phía sau**, còn
    offset của link đã ghi ở vòng trước thì không được cập nhật. Đo được trên
    corpus 2.441 bài: **502 bài** có link sai offset, tới 578/650 link trong
    bài "Hà Nội".

    Cách sửa: quét **một lần**, xử lý link lồng nhau bằng đệ quy. Offset được
    tính theo đúng thứ tự chèn vào chuỗi kết quả nên luôn khớp.

    Args:
        text: Văn bản đã gỡ template/bảng/HTML.

    Returns:
        Tuple ``(text_mới, links)``.
    """
    links: list[dict[str, Any]] = []
    parts: list[str] = []
    out_len = 0

    def emit(chunk: str) -> int:
        """Ghép chuỗi vào kết quả, trả về offset đầu của chunk."""
        nonlocal out_len
        base = out_len
        parts.append(chunk)
        out_len += len(chunk)
        return base

    index = 0
    length = len(text)
    while index < length:
        if not text.startswith("[[", index):
            # Tìm marker kế tiếp: `[[` (mở link) hoặc `]]` (ngoặc đóng lạc).
            # Phải kiểm tra CẢ `]]` ở giữa chunk, không chỉ ở đầu chunk —
            # nếu không, `... Chương Mỹ]]` sẽ bị emit nguyên xi kèm `]]`.
            next_open = text.find("[[", index)
            next_close = text.find("]]", index)
            if next_open == -1 and next_close == -1:
                emit(text[index:])
                break
            if next_open == -1 or (next_close != -1 and next_close < next_open):
                # `]]` lạc (không có `[[` nào mở) → xoá, và gỡ "anchor mồ côi"
                # `|nhãn` bám ngay trước nó.
                if parts:
                    last = parts[-1]
                    match = _TRAILING_ORPHAN_RE.search(last)
                    if match:
                        trimmed = last[: match.start()]
                        out_len -= len(last) - len(trimmed)
                        parts[-1] = trimmed
                index = next_close + 2
                continue
            emit(text[index:next_open])
            index = next_open
            continue

        end = _find_link_end(text, index)
        if end == -1:
            # Ngoặc `[[` không đóng → coi là ký tự rác và BỎ HẲN marker.
            # PHẢI tiếp tục quét (không `break`), nếu không toàn bộ phần văn bản
            # còn lại sẽ bị giữ nguyên xi kèm ký tự `[[` (lỗi quan sát ở 7 bài
            # của corpus: "Đặng Tất", "Chiến tranh Đông Dương", ...).
            #
            # Lưu ý: bỏ marker (thay vì giữ) là cần thiết vì `[[` là ký tự
            # wiki — giữ lại sẽ vi phạm Gate "0 ký tự wiki còn sót". Nội dung
            # chữ bên trong vẫn được giữ nguyên.
            index += 2
            continue

        raw = text[index + 2 : end - 2]
        pipe = _find_top_level_pipe(raw)
        if pipe == -1:
            target_raw, anchor_raw = raw, None
        else:
            target_raw, anchor_raw = raw[:pipe], raw[pipe + 1:]

        target, _anchor = _resolve_wikilink(
            target_raw, anchor_raw if anchor_raw is not None else None
        )
        # Link tới mục trong cùng bài (`[[#Mục|nhãn]]`) → chỉ giữ nhãn.
        if not target and target_raw.lstrip().startswith("#"):
            target = target_raw.lstrip()[1:].strip()

        # Link tới tập tin / thể loại: xoá hẳn (kể cả link lồng bên trong).
        #
        # PHẢI giữ lại số dòng trống bên trong link: link tập tin trong
        # Wikipedia thường chứa cả đoạn caption nhiều dòng; xoá liền sẽ làm
        # hai đoạn văn xuôi bị gộp làm một. Đo được ở bài "Hà Nội": số đoạn
        # giảm từ 142 xuống 116.
        if _EXCLUDED_LINK_RE.match(target):
            removed = text[index:end]
            blank_lines = removed.count("\n\n")
            if blank_lines:
                emit("\n\n" * blank_lines)
            index = end
            continue

        anchor_source = anchor_raw if anchor_raw else target_raw
        anchor_text, nested_links = _replace_wikilinks(anchor_source)

        if not target:
            target = anchor_text
        elif "[[" in target:
            target = target.replace("[[", "").replace("]]", "").strip()

        if not anchor_text.strip():
            index = end
            continue

        base = emit(anchor_text)
        for nested in nested_links:
            links.append(
                {
                    **nested,
                    "start": nested["start"] + base,
                    "end": nested["end"] + base,
                }
            )
        links.append(
            {
                "target": target,
                "anchor": anchor_text,
                "start": base,
                "end": base + len(anchor_text),
            }
        )
        index = end

    links.sort(key=lambda item: item["start"])
    return "".join(parts), links



def _strip_sentinel(text: str, links: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Gỡ ký tự sentinel đánh dấu mục danh sách, dịch lại offset của link.

    Args:
        text: Văn bản còn chứa sentinel.
        links: Danh sách link với offset trong `text` (còn sentinel).

    Returns:
        Tuple ``(văn bản đã gỡ sentinel, link với offset đã dịch)``.
    """
    if _LIST_SENTINEL not in text:
        return text, links

    positions: list[int] = []
    index = text.find(_LIST_SENTINEL)
    while index != -1:
        positions.append(index)
        index = text.find(_LIST_SENTINEL, index + 1)

    def shift(offset: int) -> int:
        """Trả về offset sau khi gỡ các sentinel nằm trước `offset`."""
        return offset - sum(1 for position in positions if position < offset)

    cleaned = text.replace(_LIST_SENTINEL, "")
    adjusted = [
        {**link, "start": shift(link["start"]), "end": shift(link["end"])}
        for link in links
    ]
    return cleaned, adjusted


def _strip_stray_markers(text: str) -> str:
    """Dọn nốt dấu ngoặc vuông còn sót từ wikitext hỏng.

    Wikitext thật có link không cân bằng ngoặc (vd `[[23 tháng 9 năm 1945 …
    thành lập [[Cộng hòa Tự trị Nam Kỳ|Nam Kỳ]]` — mở ngoài không đóng),
    và có trường hợp mở `[[` bị nuốt khiến chỉ còn `|nhãn]]`.

    Args:
        text: Văn bản sau khi thay link.

    Returns:
        Văn bản không còn `[[` hay `]]`.
    """
    text = _ORPHAN_ANCHOR_RE.sub(r"\1", text)
    return text.replace("[[", "").replace("]]", "")


def _remove_stray_template_braces(text: str) -> str:
    """Xoá dấu ngoặc template lạc (ngoặc không cân bằng).

    Vì sao cần
    ----------
    Wikitext thật có template bị hở ngoặc: một `}}` thừa sẽ làm bộ quét
    cân bằng ngoặc của `_remove_templates` kết thúc **sớm hơn** thực tế, khiến
    phần văn bản còn lại bị nuốt hoặc để lại ký tự `}}` trong `clean_text`.

    Đo được trên corpus 2.441 bài: bài "Elizabeth II" có 237 `{{` và 238 `}}`
    — một `}}` thừa tại vị trí 16.492, và sau khi xoá template vẫn còn sót
    `}}` trong `clean_text` (vi phạm Gate "0 ký tự wiki còn sót").

    Cách sửa: quét và đếm độ sâu ngoặc; mọi `}}` xuất hiện khi độ sâu đã về 0
    là ngoặc lạc → xoá. `{{` không bao giờ đóng cũng bị xoá.

    Args:
        text: Văn bản.

    Returns:
        Văn bản không còn ngoặc template lạc.
    """
    out: list[str] = []
    depth = 0
    index = 0
    length = len(text)
    while index < length:
        if text.startswith("{{", index):
            if depth == 0:
                out.append("{{")
                depth = 1
            else:
                out.append("{{")
                depth += 1
            index += 2
            # `{{{...}}}` — ngoặc thứ 3 thuộc về nội dung tham số.
            if index < length and text[index] == "{":
                out.append("{")
                index += 1
            continue
        if text.startswith("}}", index):
            if depth == 0:
                # Ngoặc đóng lạc → xoá.
                index += 2
                continue
            depth -= 1
            out.append("}}")
            index += 2
            continue
        out.append(text[index])
        index += 1

    if depth > 0:
        # Còn dư `{{` chưa đóng: xoá nốt các ngoặc mở còn lại.
        result = "".join(out)
        for _ in range(depth):
            position = result.rfind("{{")
            if position == -1:
                break
            result = result[:position] + result[position + 2 :]
        return result

    return "".join(out)


def _remove_unbalanced_brackets(text: str) -> str:
    """Xoá các cặp ngoặc vuông **không cân bằng** trước khi thay link.

    Vì sao cần bước này
    ------------------
    `_strip_stray_markers` (xoá ký tự `[[`/`]]` còn sót) chạy **sau** khi đã
    ghi offset của link nên mỗi ký tự bị xoá đều làm lệch offset của các
    link phía sau. Đo được trên corpus 2.441 bài: **502 bài** có link sai
    offset.

    Giải pháp: xoá ngoặc lạc **trước** khi thay link, bằng cách quét từ
    cuối về đầu và ghép cặp `[[` ↔ `]]` theo ngăn xếp (LIFO). Cặp nào không
    khớp được thì cả hai bị xoá.

    Args:
        text: Văn bản.

    Returns:
        Văn bản không còn ngoặc vuông lạc.
    """
    opens: list[int] = []
    closes: list[int] = []
    index = 0
    length = len(text)
    while index < length - 1:
        pair = text[index : index + 2]
        if pair == "[[":
            opens.append(index)
            index += 2
            continue
        if pair == "]]":
            closes.append(index)
            index += 2
            continue
        index += 1

    if not opens and not closes:
        return text

    # Ghép cặp LIFO: `]]` gần nhất đóng `[[` gần nhất chưa dùng.
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    close_stack = list(reversed(closes))
    for open_index in opens:
        while close_stack:
            close_index = close_stack.pop()
            if close_index > open_index and close_index not in used:
                used.add(close_index)
                pairs.append((open_index, close_index))
                break

    matched_opens = {start for start, _ in pairs}
    matched_closes = {end for _, end in pairs}

    # Các ngoặc không khớp được → xoá.
    drop: set[int] = set()
    for open_index in opens:
        if open_index not in matched_opens:
            drop.add(open_index)
            drop.add(open_index + 1)
    for close_index in closes:
        if close_index not in matched_closes:
            drop.add(close_index)
            drop.add(close_index + 1)

    if not drop:
        return text

    pieces: list[str] = []
    cursor = 0
    for position in sorted(drop):
        pieces.append(text[cursor:position])
        cursor = position + 1
    pieces.append(text[cursor:])
    return "".join(pieces)


def _normalize_whitespace(text: str) -> str:
    """Chuẩn hóa whitespace và gộp dòng trống.

    Args:
        text: Văn bản.

    Returns:
        Văn bản đã chuẩn hóa.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTISPACE_RE.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = _MULTINEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _join_soft_wrapped_lines(text: str) -> str:
    """Nối các dòng thuộc cùng đoạn văn xuôi bằng khoảng trắng.

    Vì sao cần
    ----------
    Wikipedia xuống dòng cứng ở khoảng 80 ký tự (để hiển thị mã nguồn). Bộ tách
    câu `pysbd` coi mỗi `\n` là ranh giới câu, nên câu gốc bị vỡ thành nhiều
    "câu" không có dấu kết thúc. Đo được trên corpus: `"Ông sinh năm\\n1385 ở
    Lam Sơn"` bị tách thành 2 câu.

    Cách sửa: dòng nào **không** phải đầu đoạn (trước đó không có dòng trống)
    và không phải item danh sách thì nối vào dòng trước bằng một khoảng trắng.

    Dòng trống (ranh giới đoạn) và item danh sách được giữ nguyên làm ranh giới.

    Args:
        text: Văn bản đã gỡ markup danh sách.

    Returns:
        Văn bản có đoạn văn xuôi nằm trên một dòng.
    """
    lines = text.split("\n")
    out: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            out.append("")
            continue
        # Dòng đầu đoạn (sau dòng trống) → tách khối mới.
        if not out or not out[-1].strip():
            out.append(line)
            continue
        # Item danh sách đã được tách thành đoạn riêng ở `_strip_list_markers`
        # → không nối vào dòng trước.
        if _LIST_MARK_RE.match(raw_line):
            out.append(line)
            continue
        out[-1] = f"{out[-1]} {line}"
    return "\n".join(out)



def _label_paragraphs(text: str) -> list[str]:
    """Gắn nhãn cho từng đoạn của `text`: ``"prose"`` hoặc ``"list_item"``.

    Nhận biết bằng **sentinel** (`_LIST_SENTINEL`) đặt ở đầu mỗi mục danh sách.

    Vì sao không so khớp theo nội dung
    ---------------------------------
    Nội dung mục danh sách thay đổi trong quá trình xử lý: `[[Bắc Ninh]]` →
    `Bắc Ninh` sau bước thay link. So khớp nội dung trước/sau bước thay link
    sẽ không khớp (đo được: mọi mục danh sách ở bài "Hà Nội" bị tính nhầm là
    văn xuôi).

    Vì sao không dựa vào chỉ số
    -----------------------
    Số khối sinh ra ở `_strip_list_markers` và số đoạn tách ra từ `text` (theo
    `\n\n`) **không nhất thiết bằng nhau**: `_normalize_whitespace` gộp các
    dòng trống liên tiếp, còn `_join_soft_wrapped_lines` nối dòng. Đo được với
    bài "Hà Nội": 142 khối nhưng chỉ 116 đoạn.

    Sentinel đi cùng văn bản qua mọi bước nên vừa khớp nội dung, vừa khớp
    chỉ số.

    Args:
        text: Văn bản sau khi xử lý (còn chứa sentinel).

    Returns:
        Danh sách nhãn, cùng độ dài với số đoạn của `text`.
    """
    labels: list[str] = []
    for start, end in paragraph_spans(text):
        body = text[start:end].strip()
        is_item = body.startswith(_LIST_SENTINEL)
        labels.append("list_item" if is_item else "prose")
    return labels


def prepare_text(wikitext: str) -> tuple[str, str, list[dict[str, Any]], list[str]]:
    """Chạy toàn bộ bước tiền xử lý, dừng **ngay trước** khi thay link.

    Hàm này tách phần "làm sạch văn bản" khỏi phần "trích hyperlink" để
    `scripts/stats_text.py` dùng được **đúng** mẫu số đối chiếu (link còn
    sót trong wikitext sau khi gỡ template/ref/infobox/bảng/markup).

    Args:
        wikitext: Wikitext gốc.

    Returns:
        Tuple ``(text_sau_khi_gỡ_markup, infobox_raw, headings, paragraph_kinds)``.
    """
    text, infobox_raw = _extract_infobox(wikitext)
    # Sửa ngoặc template lạc TRƯỚC khi xoá template — nếu không, một `}}`
    # thừa sẽ khiến bộ quét dừng sớm và để lại ký tự wiki trong `clean_text`.
    text = _remove_stray_template_braces(text)
    text = _remove_templates(text)
    text = _REF_BLOCK_RE.sub(" ", text)
    text = _REF_SELF_RE.sub(" ", text)
    text = _REF_OPEN_RE.sub(" ", text)
    text = _remove_tables(text)
    text = _remove_table_rows(text)
    text = _COMMENT_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _EXTERNAL_LINK_RE.sub(r"\1", text)
    text = _BARE_URL_RE.sub(r"\1", text)
    text = _BOLD_ITALIC_RE.sub("", text)

    headings: list[dict[str, Any]] = []

    def _heading_marker(match: re.Match[str]) -> str:
        level = len(match.group(1))
        title = match.group(2).strip()
        # Tiêu đề có thể chứa link (`== Thời [[nhà Nguyễn]] và [[Pháp thuộc]] ==`).
        # Bản gốc giữ nguyên `[[...]]` nên **không khớp** với dòng trong
        # `clean_text` sau khi link đã được thay → đoạn tiêu đề bị tính nhầm là
        # văn xuôi (đo được: các tiêu đề phụ của bài "Hà Nội").
        plain = _WIKILINK_TEXT_RE.sub(r"\1", title)
        headings.append({"level": level, "title": title, "plain_title": plain})
        return f"\n{title}\n"

    text = _HEADING_RE.sub(_heading_marker, text)

    # Gỡ markup danh sách TRƯỚC khi chuẩn hóa whitespace — `_normalize_whitespace`
    # xoá khoảng trắng đầu dòng, làm mất dấu hiệu "dòng tiếp nối của item".
    text, item_texts = _strip_list_markers(text)
    text = _normalize_whitespace(text)
    # Nối dòng xuống dòng cứng (Wikipedia ngắt dòng ở ~80 ký tự — nếu giữ
    # nguyên, `pysbd` sẽ tách câu tại mỗi dòng).
    text = _join_soft_wrapped_lines(text)
    return text, infobox_raw, headings


def clean_document(wikitext: str) -> CleanResult:
    """Làm sạch toàn bộ wikitext của một bài.

    Args:
        wikitext: Wikitext gốc.

    Returns:
        Đối tượng `CleanResult`.
    """
    if not wikitext:
        return CleanResult()

    text, infobox_raw, headings = prepare_text(wikitext)
    # Thay link + dọn ngoặc lạc trong CÙNG một lượt quét, nên offset của link
    # luôn khớp với `clean_text` (đo được trước đây: 502/2.441 bài lỗi).
    text, links = _replace_wikilinks(text)
    # Gắn nhãn đoạn SAU khi thay link — số đoạn chỉ ổn định ở thời điểm này
    # (xoá link tập tin có thể làm thay đổi ranh giới đoạn).
    paragraph_kinds = _label_paragraphs(text)

    # Gỡ sentinel — nó chỉ là ký tự đánh dấu nội bộ, không được xuất hiện
    # trong `clean_text`. Mỗi sentinel là 1 ký tự nên phải **dịch offset** của
    # các link phía sau lại tương ứng, nếu không offset sẽ lệch.
    text, links = _strip_sentinel(text, links)

    # Sau khi thay link, chi cat khoang trang dau/cuoi (khong gop them,
    # de offset cua link khong bi lech).
    lead = len(text) - len(text.lstrip())
    tail = len(text) - len(text.rstrip())
    if lead:
        text = text[lead:]
    if tail:
        text = text[: len(text) - tail]
    if lead:
        links = [
            {**link, "start": link["start"] - lead, "end": link["end"] - lead}
            for link in links
            if link["start"] >= lead
        ]


    return CleanResult(
        clean_text=text,
        infobox_raw=infobox_raw,
        links=links,
        headings=headings,
        paragraph_kinds=paragraph_kinds,
    )


def clean_file(
    input_path: Path,
    output_path: Path,
    *,
    keep_wikitext: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Làm sạch mọi bài trong `documents.jsonl` và ghi ra file mới.

    Args:
        input_path: Đường dẫn `documents.jsonl` (Phase 1).
        output_path: Đường dẫn output.
        keep_wikitext: Giữ lại trường `wikitext` trong output.

    Returns:
        Tuple ``(số bài, thống kê)``.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    total_links = 0
    total_sentences = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in read_jsonl(input_path):
            result = clean_document(record.get("wikitext", ""))
            new_record: dict[str, Any] = dict(record)
            new_record["infobox_raw"] = result.infobox_raw
            new_record["clean_text"] = result.clean_text
            new_record["links"] = result.links
            new_record["headings"] = result.headings
            new_record["paragraph_kinds"] = result.paragraph_kinds
            if not keep_wikitext:
                new_record.pop("wikitext", None)
            handle.write(json.dumps(new_record, ensure_ascii=False))
            handle.write("\n")
            total += 1
            total_links += len(result.links)
    stats = {
        "documents": total,
        "links": total_links,
        "avg_links_per_doc": round(total_links / total, 2) if total else 0.0,
    }
    logger.info("Đã làm sạch %d bài, giữ %d link", total, total_links)
    return total, stats


def main(argv: list[str] | None = None) -> int:
    """Điểm vào của CLI.

    Args:
        argv: Danh sách tham số dòng lệnh.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Làm sạch wikitext")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--drop-wikitext",
        action="store_true",
        help="Không giữ trường wikitext trong output (tiết kiệm dung lượng)",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    interim_dir = REPO_ROOT / str(config["paths"]["interim_dir"])
    input_path = interim_dir / "documents.jsonl"
    output_path = interim_dir / "documents_clean.jsonl"

    if not input_path.exists():
        logger.error("Không tìm thấy %s — chạy Phase 1 trước", input_path)
        return 1

    _total, stats = clean_file(
        input_path, output_path, keep_wikitext=not args.drop_wikitext
    )
    logger.info("Thống kê: %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

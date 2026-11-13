"""Làm sạch wikitext thành văn bản thuần (Module A2 — Phase 2).

## Thứ tự thao tác (quan trọng)

1. Tách `{{Infobox ...}}` / `{{Thông tin ...}}` ra trước → lưu vào `infobox_raw`
   (Phase 3 dùng).
2. Xoá mọi template còn lại (cân bằng ngoặc kép) — bao gồm `{{cite...}}`,
   `{{tham khảo}}`, `{{chú thích}}`.
3. Xoá thẻ `<ref>...</ref>`, `<ref .../>`, `<ref ...>`.
4. Xoá `[[File:...]]`, `[[Tập tin:...]]`, `[[Image:...]]`.
5. Xoá link category `[[Thể loại:...]]`.
6. Xoá bảng `{| ... |}` (cân bằng `{|` / `|}`).
7. Xoá HTML còn lại (`<br>`, `<span ...>`, `</span>`, `<!-- -->`).
8. Chuyển link nội bộ `[[Đích|anchor]]` → `anchor` **và ghi lại mục `links`
   trước khi thay thế**; `[[Đích]]` → `Đích` với `anchor == target`.
9. Giữ tiêu đề `== X ==` → dòng riêng, đánh dấu `heading`.
10. Chuẩn hóa whitespace, gộp dòng trống.

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
from src.common.text_utils import read_jsonl

logger = get_logger(__name__)

#: Regex thẻ HTML cần xoá (kể cả nội dung cho `<ref>`).
_REF_BLOCK_RE = re.compile(r"<ref\b[^>/]*>.*?</ref>", re.IGNORECASE | re.DOTALL)
_REF_SELF_RE = re.compile(r"<ref\b[^>]*/>", re.IGNORECASE)
_REF_OPEN_RE = re.compile(r"<ref\b[^>]*>.*?(?=<ref\b|</ref>|$)", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")

#: Link tới tập tin (namespace 6) — không phải bài viết.
_FILE_LINK_RE = re.compile(
    r"\[\[\s*(?:File|Tập tin|Image|Hình)\s*:[^\]]*\]\]", re.IGNORECASE
)

#: Link tới category (namespace 14).
_CATEGORY_LINK_RE = re.compile(r"\[\[\s*Thể\s*loại\s*:[^\]]*\]\]", re.IGNORECASE)

#: Link nội bộ: `[[Đích|anchor]]` hoặc `[[Đích]]`, có thể kèm `#anchor`.
_WIKILINK_RE = re.compile(r"\[\[([^\[\]\|]{1,300})(?:\|([^\[\]]*))?\]\]")

#: Đầu dòng tiêu đề `== X ==` (2–4 dấu `=`).
_HEADING_RE = re.compile(r"^\s*(={2,4})\s*(.+?)\s*\1\s*$", re.MULTILINE)

#: Khoảng trắng liên tiếp.
_MULTISPACE_RE = re.compile(r"[ \t ]+")
_MULTINEWLINE_RE = re.compile(r"\n{3,}")


@dataclass(slots=True)
class CleanResult:
    """Kết quả làm sạch một bài.

    Attributes:
        clean_text: Văn bản thuần đã làm sạch.
        infobox_raw: Khối infobox gốc (nếu có).
        links: Danh sách hyperlink nội bộ với offset trong `clean_text`.
        headings: Danh sách tiêu đề mục đã trích.
    """

    clean_text: str = ""
    infobox_raw: str = ""
    links: list[dict[str, Any]] = field(default_factory=list)
    headings: list[dict[str, Any]] = field(default_factory=list)
    paragraphs: list[dict[str, Any]] = field(default_factory=list)


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


def _replace_wikilinks(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Thay link nội bộ bằng anchor, đồng thời ghi lại thông tin link.

    Offset ghi trong `links` là offset **sau khi thay thế** — đó cũng là offset
    trong `clean_text` cuối cùng (vì các bước còn lại chỉ xoá ký tự điều khiển
    và chuẩn hóa whitespace ở cuối; để chắc chắn offset khớp, hàm này chạy
    *sau* khi đã chuẩn hóa whitespace — xem `clean_document`).

    Args:
        text: Văn bản đã bỏ template/bảng/HTML.

    Returns:
        Tuple ``(text_mới, links)``.
    """
    links: list[dict[str, Any]] = []
    out: list[str] = []
    cursor = 0
    position = 0
    for match in _WIKILINK_RE.finditer(text):
        target, anchor = _resolve_wikilink(match.group(1), match.group(2))
        if not target:
            continue
        out.append(text[cursor : match.start()])
        position += len(out[-1])
        out.append(anchor)
        links.append(
            {
                "target": target,
                "anchor": anchor,
                "start": position,
                "end": position + len(anchor),
            }
        )
        position += len(anchor)
        cursor = match.end()
    out.append(text[cursor:])
    return "".join(out), links


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


def clean_document(wikitext: str) -> CleanResult:
    """Làm sạch toàn bộ wikitext của một bài.

    Args:
        wikitext: Wikitext gốc.

    Returns:
        Đối tượng `CleanResult`.
    """
    if not wikitext:
        return CleanResult()

    text, infobox_raw = _extract_infobox(wikitext)
    text = _remove_templates(text)
    text = _REF_BLOCK_RE.sub(" ", text)
    text = _REF_SELF_RE.sub(" ", text)
    text = _REF_OPEN_RE.sub(" ", text)
    text = _FILE_LINK_RE.sub(" ", text)
    text = _CATEGORY_LINK_RE.sub(" ", text)
    text = _remove_tables(text)
    text = _COMMENT_RE.sub(" ", text)
    text = _HTML_TAG_RE.sub(" ", text)

    # Tiêu đề mục: giữ dòng, ghi vào danh sách headings.
    headings: list[dict[str, Any]] = []

    def _heading_marker(match: re.Match[str]) -> str:
        level = len(match.group(1))
        title = match.group(2).strip()
        headings.append({"level": level, "title": title})
        return f"\n{title}\n"

    text = _HEADING_RE.sub(_heading_marker, text)

    text = _normalize_whitespace(text)
    text, links = _replace_wikilinks(text)

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

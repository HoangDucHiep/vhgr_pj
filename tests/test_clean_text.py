"""Test cho `src/preprocess/clean_text.py` (Phase 2)."""

from __future__ import annotations

import re

import pytest

from src.preprocess.clean_text import (
    CleanResult,
    _extract_infobox,
    clean_document,
    _normalize_whitespace,
    _remove_tables,
    _remove_templates,
)

WIKI_RE = re.compile(r"\{\{|\}\}|<ref|\[\[File:|\[\[Image:|\[\[Tập tin:|\[\[Thể loại:")


def test_extract_infobox_keeps_raw() -> None:
    """Infobox phải được tách ra, không xoá vĩnh viễn."""
    wikitext = "{{Infobox person\n| tên = Lê Lợi\n}}\nNội dung bài."
    _, infobox_raw = _extract_infobox(wikitext)
    assert "Lê Lợi" in infobox_raw
    assert infobox_raw.startswith("{{Infobox")


def test_remove_templates_balanced() -> None:
    """Template lồng nhau phải bị xoá hết."""
    text = "A {{cite web|url=http://x}} B {{foo|{{bar}}}} C"
    assert _remove_templates(text).strip() == "A  B  C".strip()


def test_remove_tables_balanced() -> None:
    """Bảng wiki phải bị xoá."""
    text = "A\n{| class=\"wikitable\"\n|-\n| x\n|}\nB"
    assert "{|" not in _remove_tables(text)


def test_normalize_whitespace_collapses() -> None:
    """Whitespace phải được gộp, dòng trống thành 1."""
    text = "  a   b \n\n\n\n c  "
    assert _normalize_whitespace(text) == "a b\n\nc"


def test_clean_removes_all_wiki_markup() -> None:
    """Không còn ký tự wiki nào trong `clean_text`."""
    wikitext = (
        "{{Infobox person\n|tên=Lê Lợi\n}}\n"
        "{{chú thích}}Nội dung<ref>Xem thêm</ref> với [[Lê Lợi]].\n"
        "[[Thể loại:Vua Việt Nam]][[File:abc.jpg|thumb]]\n"
        "{| class=\"wikitable\"\n|-\n| x\n|}\n"
        "== Tiêu đề ==\n"
        "Đoạn cuối."
    )
    result = clean_document(wikitext)
    assert not WIKI_RE.search(result.clean_text)
    assert "Nội dung" in result.clean_text
    assert "Tiêu đề" in result.clean_text


def test_links_offsets_point_to_anchor() -> None:
    """Offset của link phải trỏ đúng vào anchor trong `clean_text`."""
    wikitext = "Xin chào [[Lê Lợi]] và [[Trần Hưng Đạo|Trần Quốc Tuấn]] nhé."
    result = clean_document(wikitext)
    assert len(result.links) == 2
    for link in result.links:
        assert result.clean_text[link["start"] : link["end"]] == link["anchor"]
    assert result.links[0]["target"] == "Lê Lợi"
    assert result.links[0]["anchor"] == "Lê Lợi"
    assert result.links[1]["target"] == "Trần Hưng Đạo"
    assert result.links[1]["anchor"] == "Trần Quốc Tuấn"


def test_headings_recorded() -> None:
    """Tiêu đề mục phải được ghi vào `headings`."""
    result = clean_document("== Mục một ==\nNội dung.\n=== Mục hai ===\nThêm.")
    titles = {item["title"] for item in result.headings}
    assert "Mục một" in titles
    assert "Mục hai" in titles


def test_clean_empty_input() -> None:
    """Wikitext rỗng → kết quả rỗng, không lỗi."""
    result = clean_document("")
    assert isinstance(result, CleanResult)
    assert result.clean_text == ""
    assert result.links == []


@pytest.mark.parametrize(
    "wikitext",
    [
        "Dòng một\nDòng hai.",
        "'''Đậm''' và ''nghiêng''.",
        "A <br> B <span class=\"x\">C</span> D.",
    ],
)
def test_clean_no_html_residue(wikitext: str) -> None:
    """Thẻ HTML phải bị xoá hết."""
    result = clean_document(wikitext)
    assert "<" not in result.clean_text
    assert ">" not in result.clean_text

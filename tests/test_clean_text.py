"""Test cho `src/preprocess/clean_text.py` (Phase 2)."""

from __future__ import annotations

import re

import pytest

from src.preprocess.clean_text import (
    CleanResult,
    _extract_infobox,
    _join_soft_wrapped_lines,
    _remove_stray_template_braces,
    _remove_table_rows,
    _remove_templates,
    _strip_list_markers,
    clean_document,
    _normalize_whitespace,
    _remove_tables,
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


# --------------------------------------------------------------------------
# Các lỗi thực đo được trên corpus 2.441 bài (Phase 2) — test hồi quy
# --------------------------------------------------------------------------


def test_soft_wrapped_lines_are_joined() -> None:
    """Dòng xuống dòng cứng của Wikipedia phải được nối lại.

    Wikipedia ngắt dòng ở ~80 ký tự; `pysbd` coi mỗi `\\n` là ranh giới câu
    nên câu bị vỡ. Đây là một trong ba nguyên nhân gốc của tỉ lệ câu hợp lệ
    chỉ đạt 74,34% trước khi sửa.
    """
    text = "Lê Lợi là một nhà lãnh đạo Việt Nam. Ông sinh năm\n1385 ở Lam Sơn."
    joined = _join_soft_wrapped_lines(text)
    assert joined == "Lê Lợi là một nhà lãnh đạo Việt Nam. Ông sinh năm 1385 ở Lam Sơn."


def test_soft_wrap_preserves_paragraph_break() -> None:
    """Dòng trống (ranh giới đoạn) không được bị nối."""
    text = "Dòng một.\n\nDòng hai."
    joined = _join_soft_wrapped_lines(text)
    assert joined == "Dòng một.\n\nDòng hai."


def test_list_markers_are_stripped() -> None:
    """Markup danh sách `*` `#` `;` `:` phải được gỡ."""
    text = "* Phía đông giáp Bắc Ninh\n# Mục một\n: ghi chú\n; định nghĩa"
    stripped, items = _strip_list_markers(text)
    assert not re.search(r"^[ \t]*[*#:;]", stripped, re.MULTILINE)
    assert len(items) == 4


def test_list_item_continuation_is_merged() -> None:
    """Dòng thụt lề phải được nối vào item trước, không thành văn xuôi mồ côi."""
    text = "* Phía đông giáp\n  thành phố Bắc Ninh"
    stripped, items = _strip_list_markers(text)
    assert "Phía đông giáp thành phố Bắc Ninh" in stripped
    assert items == ["Phía đông giáp thành phố Bắc Ninh"]


def test_list_items_become_separate_paragraphs() -> None:
    """Mỗi item danh sách phải là một đoạn riêng để tách câu đúng."""
    text = "* Một\n* Hai\n* Ba"
    stripped, items = _strip_list_markers(text)
    assert stripped.count("\n\n") == 2
    assert items == ["Một", "Hai", "Ba"]


def test_prose_and_list_kinds_are_labelled() -> None:
    """Đoạn văn xuôi và mục danh sách phải được phân biệt."""
    text = "Đoạn văn xuôi bình thường.\n\n* Một\n* Hai"
    stripped, items = _strip_list_markers(text)
    assert items == ["Một", "Hai"]
    assert stripped.startswith("Đoạn văn xuôi bình thường.")


def test_table_rows_are_removed() -> None:
    """Dòng bảng còn sót sau khi xoá `{| ... |}` phải bị xoá hết.

    Đo được trên corpus: 77.882 dòng bắt đầu bằng `|` và 2.198 dòng bắt đầu
    bằng `!` còn sót lại do bảng **lồng nhau**.
    """
    text = "A\n|-\n| x\n! y\n| z\nB"
    cleaned = _remove_table_rows(text)
    assert "|" not in cleaned
    assert "!" not in cleaned
    assert "A" in cleaned and "B" in cleaned


def test_stray_template_brace_is_removed() -> None:
    """`}}` thừa phải được xoá (bài "Elizabeth II" có 237 `{{` và 238 `}}`)."""
    text = "A }} B"
    assert "}}" not in _remove_stray_template_braces(text)


def test_unbalanced_open_brace_is_removed() -> None:
    """`{{` không đóng cũng phải bị xoá."""
    text = "A {{ chưa đóng"
    cleaned = _remove_stray_template_braces(text)
    assert "{{" not in cleaned
    assert "chưa đóng" in cleaned


def test_nested_link_offsets_stay_correct() -> None:
    """Link lồng nhau phải có offset đúng.

    Trước khi sửa, bộ thay link chạy nhiều vòng nên link bị xoá ở vòng sau
    làm lệch offset của link ghi ở vòng trước — 502/2.441 bài lỗi.
    """
    wikitext = "Xem [[Tập tin:X.jpg|nhỏ|[[Đê sông Hồng]] và [[Dãy núi Ba Vì]]]] nhé."
    result = clean_document(wikitext)
    for link in result.links:
        assert result.clean_text[link["start"] : link["end"]] == link["anchor"]


def test_unclosed_link_marker_is_dropped() -> None:
    """Link không đóng phải không để lại ký tự `[[` trong `clean_text`."""
    wikitext = "Ngoài hai em là [[Đặng Đức, Đặng Quý (Trấn thủ Hóa Châu), các con ông cũng đều tham gia."
    result = clean_document(wikitext)
    assert "[[" not in result.clean_text
    assert not WIKI_RE.search(result.clean_text)


def test_stray_closing_bracket_is_dropped() -> None:
    """`]]` thừa phải bị xoá (bài "Chùa Bối Khê" có `... Chương Mỹ]]`)."""
    wikitext = "Ngày nay, ở Quán Thánh, Lương Xá (xã [[Quảng Bị|Lam Điền]], Chương Mỹ]]), vẫn còn."
    result = clean_document(wikitext)
    assert "]]" not in result.clean_text


def test_clean_keeps_link_to_excluded_target_removed() -> None:
    """Link tới File/Thể loại phải bị xoá hẳn, kể cả khi lồng nhau."""
    wikitext = "Trước [[Thể loại:Vua Việt Nam]] và [[File:a.jpg|thumb|[[Lê Lợi]]]] sau."
    result = clean_document(wikitext)
    assert "Thể loại" not in result.clean_text
    assert "a.jpg" not in result.clean_text

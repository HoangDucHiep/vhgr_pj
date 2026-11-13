"""Test cho `src/preprocess/split_sentences.py` (Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.preprocess.split_sentences import (
    SENTENCE_ENDINGS,
    assign_links_to_sentences,
    build_paragraphs,
    build_sentences,
)

FIXTURES = Path(__file__).parent / "fixtures"

DOC = {
    "doc_id": "doc_123",
    "page_id": 123,
    "clean_text": (
        "Lê Lợi là một nhà lãnh đạo Việt Nam. Ông sinh năm 1385 ở Lam Sơn.\n"
        "\n"
        "Năm 1418, ông lên đường đánh giặc. Cuộc khởi nghĩa thành công."
    ),
    "headings": [],
}


def test_sentence_ids_follow_contract() -> None:
    """`sentence_id` phải theo format `s<page_id>_<para_idx>_<sent_idx>`."""
    sentences = build_sentences(DOC)
    assert sentences
    for sentence in sentences:
        parts = sentence["sentence_id"].split("_")
        assert parts[0] == "s123"
        assert parts[1] == str(sentence["para_idx"])
        assert parts[2] == str(sentence["sent_idx"])


def test_offsets_point_to_exact_substring() -> None:
    """`clean_text[start:end] == text` — điều kiện bắt buộc của Gate."""
    sentences = build_sentences(DOC)
    for sentence in sentences:
        start = sentence["char_start"]
        end = sentence["char_end"]
        assert 0 <= start < end <= len(DOC["clean_text"])
        assert DOC["clean_text"][start:end] == sentence["text"]


def test_paragraphs_split_on_blank_line() -> None:
    """Đoạn tách theo dòng trống."""
    paragraphs = build_paragraphs(DOC["clean_text"], DOC["headings"])
    assert len(paragraphs) == 2
    assert paragraphs[0]["para_idx"] == 0
    assert paragraphs[1]["para_idx"] == 1
    assert paragraphs[0]["char_end"] < paragraphs[1]["char_start"]


def test_paragraph_heading_flag() -> None:
    """Đoạn là tiêu đề phải được đánh dấu."""
    text = "Mục một\n\nNội dung."
    paragraphs = build_paragraphs(text, [{"level": 2, "title": "Mục một"}])
    assert paragraphs[0]["heading"] is True
    assert paragraphs[1]["heading"] is False


def test_links_assigned_to_sentences() -> None:
    """Link phải được gán đúng `sentence_id`."""
    doc = dict(DOC)
    doc["clean_text"] = "Lê Lợi là người đã lật đổ nhà Hồ. Ông rất vĩ đại."
    doc["headings"] = []
    sentences = build_sentences(doc)
    links = [
        {
            "target": "Lê Lợi",
            "anchor": "Lê Lợi",
            "start": doc["clean_text"].index("Lê Lợi"),
            "end": doc["clean_text"].index("Lê Lợi") + len("Lê Lợi"),
        }
    ]
    assigned = assign_links_to_sentences(sentences, links)
    assert len(assigned) == 1
    assert assigned[0]["sentence_id"] == sentences[0]["sentence_id"]
    assert assigned[0]["para_idx"] == 0


def test_name_with_comma_not_split() -> None:
    """Tên có dấu phẩy không được vỡ thành hai câu."""
    doc = {
        "doc_id": "doc_9",
        "page_id": 9,
        "clean_text": (
            "Trần Công Hiến, tướng quân nhà Trần, đã lập công lớn trong trận Bạch Đằng."
        ),
        "headings": [],
    }
    sentences = build_sentences(doc)
    assert len(sentences) == 1
    assert "Trần Công Hiến, tướng quân nhà Trần" in sentences[0]["text"]


def test_empty_text_no_sentences() -> None:
    """Văn bản rỗng → không có câu nào."""
    doc = {"doc_id": "doc_1", "page_id": 1, "clean_text": "", "headings": []}
    assert build_sentences(doc) == []


# --------------------------------------------------------------------------
# Gate 5 — 30 tên có dấu phẩy lấy từ corpus thật
# --------------------------------------------------------------------------


def _load_comma_names() -> list[dict[str, str]]:
    """Nạp fixture 30 tên có dấu phẩy.

    Returns:
        Danh sách dict có `name` và `sentence`.
    """
    path = FIXTURES / "comma_names_30.jsonl"
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def test_comma_names_fixture_has_30_rows() -> None:
    """Fixture phải có đúng 30 tên như Gate yêu cầu."""
    rows = _load_comma_names()
    assert len(rows) == 30
    assert all("," in row["name"] for row in rows)


@pytest.mark.parametrize("row", _load_comma_names(), ids=lambda r: r["name"])
def test_comma_name_sentence_not_broken(row: dict[str, str]) -> None:
    """Tên có dấu phẩy không được vỡ thành nhiều câu."""
    doc = {
        "doc_id": "doc_0",
        "page_id": 0,
        "clean_text": row["sentence"],
        "headings": [],
    }
    sentences = build_sentences(doc)
    assert len(sentences) == 1, f"vỡ câu: {sentences}"
    assert row["name"] in sentences[0]["text"]
    assert sentences[0]["text"].rstrip().endswith(SENTENCE_ENDINGS)


# --------------------------------------------------------------------------
# Heading không sinh câu + nhãn đoạn
# --------------------------------------------------------------------------


def test_heading_paragraph_does_not_produce_sentences() -> None:
    """Đoạn là tiêu đề không được sinh câu.

    Đo được trước khi sửa: 9,5% "câu" trong corpus là tiêu đề mục
    ("Tiểu sử", "Tham khảo") — không có dấu kết thúc.
    """
    doc = {
        "doc_id": "doc_5",
        "page_id": 5,
        "clean_text": "Tiểu sử\n\nLê Lợi sinh năm 1385. Ông mất năm 1410.",
        "headings": [{"level": 2, "title": "Tiểu sử"}],
    }
    paragraphs = build_paragraphs(doc["clean_text"], doc["headings"])
    assert len(paragraphs) == 2
    assert paragraphs[0]["heading"] is True

    sentences = build_sentences(doc)
    assert len(sentences) == 2
    assert all("Tiểu sử" not in s["text"] for s in sentences)


def test_paragraph_kind_is_propagated_to_sentences() -> None:
    """Nhãn `prose` / `list_item` phải được truyền xuống câu."""
    doc = {
        "doc_id": "doc_6",
        "page_id": 6,
        "clean_text": "Đoạn văn xuôi bình thường.\n\nMột mục danh sách",
        "headings": [],
        "paragraph_kinds": ["prose", "list_item"],
    }
    sentences = build_sentences(doc)
    assert [s["para_kind"] for s in sentences] == ["prose", "list_item"]


def test_list_item_paragraph_produces_one_sentence() -> None:
    """Mục danh sách là một đoạn riêng → một câu riêng."""
    doc = {
        "doc_id": "doc_7",
        "page_id": 7,
        "clean_text": "Đoạn văn xuôi bình thường.\n\nPhía đông giáp Bắc Ninh",
        "headings": [],
        "paragraph_kinds": ["prose", "list_item"],
    }
    sentences = build_sentences(doc)
    assert len(sentences) == 2
    assert sentences[1]["text"] == "Phía đông giáp Bắc Ninh"
    assert sentences[1]["para_kind"] == "list_item"

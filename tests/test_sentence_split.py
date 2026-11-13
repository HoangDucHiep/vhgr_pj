"""Test cho `src/preprocess/split_sentences.py` (Phase 2)."""

from __future__ import annotations

from src.preprocess.split_sentences import (
    assign_links_to_sentences,
    build_paragraphs,
    build_sentences,
)

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

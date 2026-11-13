"""Test hồi quy Phase 2 trên 10 bài thật.

So sánh kết quả `clean_document` + `build_sentences` với snapshot
`tests/fixtures/expected_clean.jsonl`.

Cách tạo lại snapshot (khi code cố ý đổi hành vi):
    python scripts/make_text_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.preprocess.clean_text import clean_document
from src.preprocess.split_sentences import build_paragraphs, build_sentences

FIXTURES = Path(__file__).parent / "fixtures"


def _load(path: Path) -> list[dict[str, Any]]:
    """Nạp một file JSONL.

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách record.
    """
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


SAMPLES = _load(FIXTURES / "sample_docs_10.jsonl")
EXPECTED = {row["doc_id"]: row for row in _load(FIXTURES / "expected_clean.jsonl")}


def test_fixture_has_10_documents() -> None:
    """Fixture phải có đúng 10 bài như Gate yêu cầu."""
    assert len(SAMPLES) == 10
    assert len(EXPECTED) == 10


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda r: r["title"])
def test_regression_matches_snapshot(sample: dict[str, Any]) -> None:
    """Kết quả phải khớp snapshot."""
    expected = EXPECTED[sample["doc_id"]]
    result = clean_document(sample["wikitext"])

    assert result.clean_text == expected["clean_text"]
    assert result.headings == expected["headings"]
    assert result.paragraph_kinds == expected["paragraph_kinds"]
    assert result.links == expected["links"]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda r: r["title"])
def test_regression_sentences_match_snapshot(sample: dict[str, Any]) -> None:
    """Câu tách được phải khớp snapshot."""
    expected = EXPECTED[sample["doc_id"]]
    result = clean_document(sample["wikitext"])
    doc = {
        "doc_id": sample["doc_id"],
        "page_id": sample["page_id"],
        "clean_text": result.clean_text,
        "headings": result.headings,
        "paragraph_kinds": result.paragraph_kinds,
    }
    assert build_sentences(doc) == expected["sentences"]
    assert build_paragraphs(
        result.clean_text, result.headings, result.paragraph_kinds
    ) == expected["paragraphs"]


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda r: r["title"])
def test_regression_offsets_and_no_wiki_chars(sample: dict[str, Any]) -> None:
    """Offset phải đúng và không còn ký tự wiki."""
    result = clean_document(sample["wikitext"])
    text = result.clean_text

    assert "{{" not in text and "}}" not in text
    assert "<ref" not in text
    assert "[[" not in text and "]]" not in text

    for link in result.links:
        assert text[link["start"] : link["end"]] == link["anchor"]

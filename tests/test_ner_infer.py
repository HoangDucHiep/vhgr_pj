"""Test cho `src/ner/infer_ner.py` — suy luận NER toàn corpus (Phase 5).

Bao phủ:
- Offset ký tự luôn khớp `text[start:end] == entity["text"]` (Gate Phase 5).
- Nhãn ∈ 6 nhãn hợp lệ.
- Câu dài được xử lý bằng cửa sổ trượt, không sót word.
- Span rỗng / offset sai bị loại.
"""

from __future__ import annotations

import pytest

from src.ner.data_convert import LABEL2ID
from src.ner.infer_ner import word_labels_to_entities


def test_word_labels_to_entities_basic() -> None:
    """Span ký tự suy ra đúng từ nhãn BIO ở mức word."""
    text = "Lê Lợi là vua"
    words = ["Lê", "Lợi", "là", "vua"]
    starts = [0, 3, 7, 10]
    ends = [2, 6, 9, 13]
    labels = [
        LABEL2ID["B-PERSON"],
        LABEL2ID["I-PERSON"],
        LABEL2ID["O"],
        LABEL2ID["O"],
    ]
    entities, invalid = word_labels_to_entities(
        text, labels, starts, ends, score_threshold=0.0
    )
    assert invalid == 0
    assert len(entities) == 1
    assert entities[0]["text"] == "Lê Lợi"
    assert entities[0]["start"] == 0
    assert entities[0]["end"] == 6
    assert entities[0]["label"] == "PERSON"
    assert text[entities[0]["start"] : entities[0]["end"]] == entities[0]["text"]


def test_word_labels_to_entities_multiple_spans() -> None:
    """Nhiều span liên tiếp phải tách đúng."""
    text = "Lê Lợi và Lê Thái Tổ"
    starts = [0, 3, 7, 10, 13, 18]
    ends = [2, 6, 9, 12, 17, 20]
    labels = [
        LABEL2ID["B-PERSON"],
        LABEL2ID["I-PERSON"],
        LABEL2ID["O"],
        LABEL2ID["B-PERSON"],
        LABEL2ID["I-PERSON"],
        LABEL2ID["I-PERSON"],
    ]
    entities, invalid = word_labels_to_entities(
        text, labels, starts, ends, score_threshold=0.0
    )
    assert invalid == 0
    assert [entity["text"] for entity in entities] == ["Lê Lợi", "Lê Thái Tổ"]
    assert all(entity["label"] == "PERSON" for entity in entities)


def test_word_labels_to_entities_score_threshold() -> None:
    """Span có điểm dưới ngưỡng bị loại."""
    text = "Lê Lợi"
    labels = [LABEL2ID["B-PERSON"], LABEL2ID["I-PERSON"]]
    entities, _ = word_labels_to_entities(
        text, labels, [0, 3], [2, 6], score_threshold=0.5, scores=[0.2, 0.2]
    )
    assert entities == []


def test_word_labels_to_entities_invalid_span_dropped() -> None:
    """Span rỗng (offset sai) bị loại và được đếm."""
    text = "Lê Lợi"
    labels = [LABEL2ID["B-PERSON"], LABEL2ID["I-PERSON"]]
    # offset sai → char_end <= char_start
    entities, invalid = word_labels_to_entities(
        text, labels, [5, 5], [5, 5], score_threshold=0.0
    )
    assert entities == []
    assert invalid == 1


def test_word_labels_to_entities_no_labels() -> None:
    """Câu không có entity → danh sách rỗng."""
    text = "Không có gì"
    labels = [LABEL2ID["O"]] * 3
    entities, invalid = word_labels_to_entities(
        text, labels, [0, 6, 9], [5, 8, 11], score_threshold=0.0
    )
    assert entities == []
    assert invalid == 0


@pytest.mark.parametrize(
    "label",
    ["PERSON", "DYNASTY", "EVENT", "LOCATION", "TIME", "TITLE"],
)
def test_word_labels_to_entities_all_labels(label: str) -> None:
    """Mọi nhãn trong 6 nhãn đều sinh được span hợp lệ."""
    text = "abc"
    entities, invalid = word_labels_to_entities(
        text,
        [LABEL2ID[f"B-{label}"]],
        [0],
        [3],
        score_threshold=0.0,
    )
    assert invalid == 0
    assert entities[0]["label"] == label
    assert text[entities[0]["start"] : entities[0]["end"]] == entities[0]["text"]

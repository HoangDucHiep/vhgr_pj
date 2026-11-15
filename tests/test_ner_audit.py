"""Test cho `scripts/ner_audit_sample.py` — audit nhiễu nhãn bạc & bộ gold (Phase 5).

Bao phủ:
- Quy ước `end_token` **exclusive** của `src/ner/build_silver.py` được tôn trọng
  khi sinh nhãn BIO từ mention (hồi quy cho lỗi off-by-one `range(start, end + 1)`).
- Mention được thêm tay (`add`) cũng sinh nhãn đúng số token.
- `score_on_gold` đo F1 đúng khi dự đoán trùng nhãn vàng.
"""

from __future__ import annotations

import json

from scripts.ner_audit_sample import apply_manual_review, score_on_gold


def _write_jsonl(path, rows) -> None:
    """Ghi danh sách dict ra file JSONL.

    Args:
        path: Đường dẫn file.
        rows: Danh sách record.
    """
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_apply_review_uses_exclusive_end_token(tmp_path) -> None:
    """`end_token` exclusive → nhãn BIO chỉ phủ đúng số token của mention."""
    silver = [
        {
            "sentence_id": "s1_0_0",
            "doc_id": "doc_1",
            "page_id": 1,
            "text": "Năm 1741 , Trịnh Doanh lên ngôi",
            "tokens": ["Năm", "1741", ",", "Trịnh", "Doanh", "lên", "ngôi"],
            "labels": [
                "O",
                "B-TIME",
                "I-TIME",
                "B-PERSON",
                "I-PERSON",
                "I-PERSON",
                "O",
            ],
            "mentions": [
                {
                    "start_token": 1,
                    "end_token": 3,
                    "label": "TIME",
                    "text": "1741 ,",
                },
                {
                    "start_token": 3,
                    "end_token": 5,
                    "label": "PERSON",
                    "text": "Trịnh Doanh",
                },
            ],
        }
    ]
    silver_path = tmp_path / "silver.jsonl"
    review_path = tmp_path / "review.jsonl"
    out_path = tmp_path / "gold.jsonl"

    _write_jsonl(silver_path, silver)
    _write_jsonl(review_path, [])

    stats = apply_manual_review(review_path, out_path, silver_path)

    record = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert stats["n_mentions_kept"] == 2
    # `1741 ,` chiếm token 1..2 (exclusive end=3) → token 3 phải là B-PERSON.
    assert record["labels"] == [
        "O",
        "B-TIME",
        "I-TIME",
        "B-PERSON",
        "I-PERSON",
        "O",
        "O",
    ]
    # Mention giữ nguyên `end_token` exclusive của nguồn.
    assert record["mentions"][0]["end_token"] == 3


def test_apply_review_add_mention_spans_exact_tokens(tmp_path) -> None:
    """Mention thêm tay phải phủ đúng số token tương ứng."""
    silver = [
        {
            "sentence_id": "s2_0_0",
            "doc_id": "doc_2",
            "page_id": 2,
            "text": "Nhà Nguyễn lập ra nhà Hậu Lê",
            "tokens": ["Nhà", "Nguyễn", "lập", "ra", "nhà", "Hậu", "Lê"],
            "labels": ["O"] * 7,
            "mentions": [],
        }
    ]
    silver_path = tmp_path / "silver.jsonl"
    review_path = tmp_path / "review.jsonl"
    out_path = tmp_path / "gold.jsonl"

    _write_jsonl(silver_path, silver)
    _write_jsonl(
        review_path,
        [
            {
                "sentence_id": "s2_0_0",
                "keep": [],
                "drop": [],
                "add": [{"label": "DYNASTY", "text": "Nguyễn"}],
                "notes": "thiếu triều đại",
            }
        ],
    )

    stats = apply_manual_review(review_path, out_path, silver_path)

    record = json.loads(out_path.read_text(encoding="utf-8").strip())
    assert stats["n_mentions_added"] == 1
    # "Nguyễn" là 1 token (index 1) → chỉ token 1 mang nhãn.
    assert record["labels"] == [
        "O",
        "B-DYNASTY",
        "O",
        "O",
        "O",
        "O",
        "O",
    ]
    assert record["mentions"][0]["start_token"] == 1
    assert record["mentions"][0]["end_token"] == 2


def test_score_on_gold_perfect_prediction(tmp_path) -> None:
    """Dự đoán trùng khít nhãn vàng → F1 = 1,0."""
    gold = [
        {
            "sentence_id": "s3_0_0",
            "text": "Năm 1741 , Trịnh Doanh lên ngôi",
            "tokens": ["Năm", "1741", ",", "Trịnh", "Doanh", "lên", "ngôi"],
            "labels": [
                "O",
                "B-TIME",
                "O",
                "B-PERSON",
                "I-PERSON",
                "O",
                "O",
            ],
            "mentions": [
                {"start_token": 1, "end_token": 2, "label": "TIME", "text": "1741"},
                {
                    "start_token": 3,
                    "end_token": 5,
                    "label": "PERSON",
                    "text": "Trịnh Doanh",
                },
            ],
        }
    ]
    gold_path = tmp_path / "gold.jsonl"
    predictions_path = tmp_path / "pred.jsonl"

    _write_jsonl(gold_path, gold)
    _write_jsonl(
        predictions_path,
        [
            {
                "sentence_id": "s3_0_0",
                "text": "Năm 1741 , Trịnh Doanh lên ngôi",
                "entities": [
                    {"start": 4, "end": 8, "text": "1741", "label": "TIME", "score": 0.9},
                    {
                        "start": 11,
                        "end": 22,
                        "text": "Trịnh Doanh",
                        "label": "PERSON",
                        "score": 0.9,
                    },
                ],
            }
        ],
    )

    result = score_on_gold(gold_path, predictions_path)

    assert result["micro"]["f1"] == 1.0
    assert result["n_matched_sentences"] == 1

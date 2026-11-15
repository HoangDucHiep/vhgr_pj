"""Test cho script kiểm định Gate Phase 6 — `scripts/coref_gate_check.py`.

Đối chiếu Gate:
    - **G1** — 100% `canonical_id` là `ent_*` hợp lệ hoặc `null`.
    - **G2** — `make_entity_id` deterministic.
    - **G7** — 100% offset đúng.

Nguyên tắc kiểm thử
-------------------
- Test trên **fixture nhỏ**, không phụ thuộc artifact toàn corpus.
- Kiểm tra logic phát hiện lỗi, không chỉ kiểm tra trường hợp hợp lệ.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.coref_gate_check import (  # noqa: E402
    check_g1,
    check_g2,
    check_g3,
    check_g5,
    check_g7,
)


def _row(sentence_id: str, text: str, mentions: list[dict]) -> dict:
    """Dựng record giống `coref_resolved.jsonl`."""
    return {
        "sentence_id": sentence_id,
        "doc_id": "doc_1",
        "text": text,
        "mentions": mentions,
    }


class TestG1CanonicalIdFormat:
    """G1 — định dạng `canonical_id`."""

    def test_valid_ids_pass(self):
        """`ent_<slug>_<hash8>` hợp lệ → đạt."""
        rows = [
            _row(
                "s1_0_0",
                "Lê Lợi lên ngôi.",
                [
                    {
                        "mention_id": "m1",
                        "canonical_id": "ent_le_loi_1a2b3c4d",
                        "start": 0,
                        "end": 6,
                        "text": "Lê Lợi",
                    },
                    {
                        "mention_id": "m2",
                        "canonical_id": None,
                        "start": 10,
                        "end": 13,
                        "text": "lên",
                    },
                ],
            )
        ]
        result = check_g1(rows)
        assert result["dat"] is True
        assert result["so_vi_pham"] == 0
        assert result["so_mention"] == 2

    def test_invalid_id_fails(self):
        """`nil_*` hoặc chuỗi tự do → không đạt."""
        rows = [
            _row(
                "s1_0_0",
                "Lê Lợi lên ngôi.",
                [
                    {
                        "mention_id": "m1",
                        "canonical_id": "nil_9f2c1a7b",
                        "start": 0,
                        "end": 6,
                        "text": "Lê Lợi",
                    }
                ],
            )
        ]
        result = check_g1(rows)
        assert result["dat"] is False
        assert result["so_vi_pham"] == 1
        assert result["vi_pham_mau"][0]["canonical_id"] == "nil_9f2c1a7b"

    def test_non_string_id_fails(self):
        """`canonical_id` không phải chuỗi → không đạt."""
        rows = [
            _row(
                "s1_0_0",
                "Lê Lợi lên ngôi.",
                [
                    {
                        "mention_id": "m1",
                        "canonical_id": 12345,
                        "start": 0,
                        "end": 6,
                        "text": "Lê Lợi",
                    }
                ],
            )
        ]
        assert check_g1(rows)["dat"] is False


class TestG2Deterministic:
    """G2 — `make_entity_id` deterministic."""

    def test_deterministic(self):
        """Cùng đầu vào → cùng id."""
        result = check_g2()
        assert result["dat"] is True
        for detail in result["chi_tiet"]:
            assert len(detail["ids"]) == 1


class TestG3ResolveRate:
    """G3 — tỉ lệ mention resolve."""

    def test_above_threshold(self):
        """Tỉ lệ ≥ 60% → đạt."""
        mentions = []
        for i in range(10):
            mentions.append(
                {
                    "mention_id": f"m{i}",
                    "canonical_id": "ent_le_loi_1a2b3c4d" if i < 8 else None,
                    "label": "PERSON",
                    "start": 0,
                    "end": 3,
                    "text": "abc",
                }
            )
        result = check_g3([_row("s1_0_0", "abc", mentions)])
        assert result["dat"] is True
        assert result["ty_le"] == 0.8

    def test_below_threshold_fails(self):
        """Tỉ lệ < 60% → không đạt."""
        mentions = [
            {
                "mention_id": f"m{i}",
                "canonical_id": "ent_le_loi_1a2b3c4d" if i < 3 else None,
                "label": "PERSON",
                "start": 0,
                "end": 3,
                "text": "abc",
            }
            for i in range(10)
        ]
        result = check_g3([_row("s1_0_0", "abc", mentions)])
        assert result["dat"] is False
        assert result["ty_le"] == 0.3

    def test_time_excluded_from_non_time_rate(self):
        """Mention `TIME` không tính vào tỉ lệ không-tính-TIME."""
        mentions = [
            {
                "mention_id": "m0",
                "canonical_id": None,
                "label": "TIME",
                "start": 0,
                "end": 3,
                "text": "abc",
            },
            {
                "mention_id": "m1",
                "canonical_id": "ent_le_loi_1a2b3c4d",
                "label": "PERSON",
                "start": 4,
                "end": 7,
                "text": "def",
            },
        ]
        result = check_g3([_row("s1_0_0", "abc def", mentions)])
        assert result["ty_le"] == 0.5
        assert result["ty_le_khong_tinh_time"] == 1.0


class TestG5Accuracy:
    """G5 — độ chính xác gán đại từ."""

    def test_correct_predictions(self):
        """Dự đoán khớp → độ chính xác 1,0."""
        gold = [
            {
                "sentence_id": "s1_0_0",
                "mentions": [
                    {
                        "start": 10,
                        "end": 13,
                        "canonical_id": "ent_le_loi_1a2b3c4d",
                    }
                ],
            }
        ]
        predictions = {
            "s1_0_0": _row(
                "s1_0_0",
                "Lê Lợi lên ngôi.",
                [
                    {
                        "mention_id": "m0",
                        "canonical_id": "ent_le_loi_1a2b3c4d",
                        "start": 10,
                        "end": 13,
                        "text": "ông",
                    }
                ],
            )
        }
        result = check_g5(gold, predictions)
        assert result["do_chinh_xac"] == 1.0
        assert result["so_mention_co_nhan_vang"] == 1
        assert result["dat"] is True

    def test_wrong_predictions_below_threshold(self):
        """Dự đoán sai toàn bộ → không đạt."""
        gold = [
            {
                "sentence_id": "s1_0_0",
                "mentions": [
                    {
                        "start": 10,
                        "end": 13,
                        "canonical_id": "ent_le_loi_1a2b3c4d",
                    }
                ],
            }
        ]
        predictions = {
            "s1_0_0": _row(
                "s1_0_0",
                "Lê Lợi lên ngôi.",
                [
                    {
                        "mention_id": "m0",
                        "canonical_id": "ent_nguyen_quyen_00000000",
                        "start": 10,
                        "end": 13,
                        "text": "ông",
                    }
                ],
            )
        }
        result = check_g5(gold, predictions)
        assert result["do_chinh_xac"] == 0.0
        assert result["dat"] is False

    def test_gold_without_canonical_id_is_skipped(self):
        """Mention gold không có nhãn → không tính vào mẫu."""
        gold = [
            {
                "sentence_id": "s1_0_0",
                "mentions": [{"start": 10, "end": 13, "canonical_id": None}],
            }
        ]
        result = check_g5(gold, {})
        assert result["so_mention_co_nhan_vang"] == 0
        assert result["do_chinh_xac"] == 0.0


class TestG7Offsets:
    """G7 — offset mention."""

    def test_correct_offsets_pass(self):
        """Offset khớp `text[start:end]` → đạt."""
        rows = [
            _row(
                "s1_0_0",
                "Lê Lợi lên ngôi.",
                [
                    {
                        "mention_id": "m0",
                        "canonical_id": None,
                        "start": 0,
                        "end": 6,
                        "text": "Lê Lợi",
                    }
                ],
            )
        ]
        result = check_g7(rows)
        assert result["dat"] is True
        assert result["so_loi"] == 0

    def test_wrong_offset_fails(self):
        """Offset lệch → không đạt."""
        rows = [
            _row(
                "s1_0_0",
                "Lê Lợi lên ngôi.",
                [
                    {
                        "mention_id": "m0",
                        "canonical_id": None,
                        "start": 0,
                        "end": 5,
                        "text": "Lê Lợi",
                    }
                ],
            )
        ]
        result = check_g7(rows)
        assert result["dat"] is False
        assert result["so_loi"] == 1
        assert result["loi_mau"][0]["actual"] == "Lê Lợ"

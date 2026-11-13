"""Test cho `parse_vi_date` (Phase 3 — A4).

Gate: chuẩn hóa ngày đúng ≥ 95% trên tập 30 chuỗi mẫu trong
`tests/fixtures/dates.jsonl`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.common.normalize import is_lunar_date, parse_vi_date

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "dates.jsonl"

#: Ngưỡng Gate của Phase 3.
GATE_THRESHOLD = 0.95


def _load_fixtures() -> list[dict]:
    """Nạp các chuỗi ngày mẫu.

    Returns:
        Danh sách dict fixture.
    """
    records = []
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


FIXTURES = _load_fixtures()


def test_fixture_count():
    """Tập mẫu phải có đúng 30 chuỗi (theo `docs/09` §Phase 3)."""
    assert len(FIXTURES) == 30


@pytest.mark.parametrize("case", FIXTURES, ids=[c["input"] or "<empty>" for c in FIXTURES])
def test_parse_vi_date(case):
    """Mỗi chuỗi mẫu phải parse đúng iso/year/precision."""
    iso, year, precision = parse_vi_date(case["input"])
    assert iso == case["expected_iso"], f"iso sai cho {case['input']!r}"
    assert year == case["expected_year"], f"year sai cho {case['input']!r}"
    assert precision == case["expected_precision"], f"precision sai cho {case['input']!r}"


def test_gate_accuracy_at_least_95_percent():
    """Gate: ≥ 95% chuỗi mẫu parse đúng (đo trên toàn bộ 3 kết quả)."""
    total = 0
    correct = 0
    failures = []
    for case in FIXTURES:
        total += 1
        iso, year, precision = parse_vi_date(case["input"])
        if (
            iso == case["expected_iso"]
            and year == case["expected_year"]
            and precision == case["expected_precision"]
        ):
            correct += 1
        else:
            failures.append(
                {
                    "input": case["input"],
                    "expected": [
                        case["expected_iso"],
                        case["expected_year"],
                        case["expected_precision"],
                    ],
                    "actual": [iso, year, precision],
                }
            )

    accuracy = correct / total
    assert accuracy >= GATE_THRESHOLD, (
        f"Độ chính xác {accuracy:.1%} < {GATE_THRESHOLD:.0%}. Sai: {failures}"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 tháng 5 năm 1385", ("1385-05-10", 1385, "day")),
        ("1385", (None, 1385, "year")),
        ("tháng 5 năm 1284", ("1284-05-01", 1284, "month")),
        ("", (None, None, "none")),
    ],
)
def test_parse_vi_date_basic(text, expected):
    """Các dạng cơ bản phải trả về đúng."""
    assert parse_vi_date(text) == expected


def test_lunar_year_requires_verified_mapping():
    """Năm âm lịch chỉ được tin khi khớp bảng đã đối chiếu."""
    # Khớp bảng → tin.
    assert parse_vi_date("năm Ất Tý (938)") == (None, 938, "year")
    # Không khớp → không bịa (nguyên tắc #3).
    assert parse_vi_date("năm Ất Tý (900)") == (None, None, "none")


def test_approx_keywords():
    """Từ khoá 'khoảng' vẫn trả về năm nhưng không có ngày."""
    for text in ("khoảng năm 1000", "sau năm 1230", "trước năm 1400"):
        iso, year, precision = parse_vi_date(text)
        assert iso is None
        assert year is not None
        assert precision == "year"


def test_is_lunar_date():
    """`is_lunar_date` phải nhận diện chuỗi âm lịch."""
    assert is_lunar_date("năm Ất Tý (938) âm lịch") is True
    assert is_lunar_date("10 tháng 5 năm 1385") is False

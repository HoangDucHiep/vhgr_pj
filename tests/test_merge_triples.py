"""Test cho hợp nhất triple Phase 8 (D3): dedupe, orientation, evidence, Gate.

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 8.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.re.merge_triples import (
    REQUIRED_FIELDS,
    ensure_entity_id,
    merge_triples,
    normalize_triple,
    validate_merged,
    write_merged,
)


def _triple(**kwargs: Any) -> dict[str, Any]:
    """Dựng một triple chuẩn hoá đầy đủ.

    Args:
        **kwargs: Ghi đè trường.

    Returns:
        Dict triple.
    """
    base: dict[str, Any] = {
        "doc_id": "doc_1",
        "sentence_id": "s1_0_0",
        "subject": "ent_a_aaaaaaaa",
        "relation": "cha_cua",
        "object": "ent_b_bbbbbbbb",
        "evidence_sentence": "Lê Lợi là cha của Lê Thái Tổ.",
        "source_url": "https://vi.wikipedia.org/wiki/Lê_Lợi",
        "doc_title": "Lê Lợi",
        "confidence": 0.9,
        "method": "infobox",
        "start_year": None,
        "end_year": None,
        "alt_evidence": [],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# ensure_entity_id
# ---------------------------------------------------------------------------


def test_ensure_entity_id_keeps_existing_ids() -> None:
    """Id `ent_*` và `year_*` được giữ nguyên."""
    assert ensure_entity_id("ent_le_loi_1a2b3c4d") == "ent_le_loi_1a2b3c4d"
    assert ensure_entity_id("year_1019") == "year_1019"


def test_ensure_entity_id_mints_new_id() -> None:
    """Tên thô → `ent_<slug>_<hash8>`."""
    result = ensure_entity_id("Lê Lợi", "person")
    assert result.startswith("ent_")
    assert result.endswith("_" + result.rsplit("_", 1)[1])
    assert len(result.rsplit("_", 1)[1]) == 8


def test_ensure_entity_id_empty() -> None:
    """Chuỗi rỗng → chuỗi rỗng."""
    assert ensure_entity_id("") == ""
    assert ensure_entity_id("   ") == ""


# ---------------------------------------------------------------------------
# normalize_triple
# ---------------------------------------------------------------------------


def test_normalize_triple_drops_self_loop() -> None:
    """Self-loop bị loại."""
    result = normalize_triple(
        _triple(subject="ent_a_aaaaaaaa", object="ent_a_aaaaaaaa"),
        method="infobox",
        documents={},
        default_confidence=0.9,
    )
    assert result is None


def test_normalize_triple_drops_invalid_relation() -> None:
    """Quan hệ ngoài danh mục 18 quan hệ bị loại."""
    result = normalize_triple(
        _triple(relation="khong_ton_tai"),
        method="infobox",
        documents={},
        default_confidence=0.9,
    )
    assert result is None


def test_normalize_triple_drops_empty_evidence() -> None:
    """Evidence rỗng bị loại."""
    result = normalize_triple(
        _triple(evidence_sentence="   "),
        method="infobox",
        documents={},
        default_confidence=0.9,
    )
    assert result is None


def test_normalize_triple_drops_empty_endpoints() -> None:
    """Subject/object rỗng bị loại."""
    result = normalize_triple(
        _triple(subject=""),
        method="infobox",
        documents={},
        default_confidence=0.9,
    )
    assert result is None


def test_normalize_triple_normalizes_symmetric_orientation() -> None:
    """Quan hệ đối xứng → subject < object."""
    result = normalize_triple(
        _triple(
            subject="ent_z_zzzzzzzz",
            object="ent_a_aaaaaaaa",
            relation="anh_em_cua",
        ),
        method="infobox",
        documents={},
        default_confidence=0.9,
    )
    assert result is not None
    assert result["subject"] == "ent_a_aaaaaaaa"
    assert result["object"] == "ent_z_zzzzzzzz"


def test_normalize_triple_keeps_directed_orientation() -> None:
    """Quan hệ có hướng giữ nguyên thứ tự."""
    result = normalize_triple(
        _triple(
            subject="ent_z_zzzzzzzz",
            object="ent_a_aaaaaaaa",
            relation="cha_cua",
        ),
        method="infobox",
        documents={},
        default_confidence=0.9,
    )
    assert result is not None
    assert result["subject"] == "ent_z_zzzzzzzz"
    assert result["object"] == "ent_a_aaaaaaaa"


def test_normalize_triple_clamps_confidence() -> None:
    """Confidence ngoài [0,1] → clamp."""
    result = normalize_triple(
        _triple(confidence=1.7),
        method="infobox",
        documents={},
        default_confidence=0.9,
    )
    assert result is not None
    assert result["confidence"] == 1.0


def test_normalize_triple_fills_source_url_from_documents() -> None:
    """`source_url`/`doc_title` lấy từ metadata bài viết khi thiếu."""
    documents = {
        "doc_1": {"url": "https://vi.wikipedia.org/wiki/X", "title": "X"}
    }
    result = normalize_triple(
        _triple(source_url="", doc_title=""),
        method="infobox",
        documents=documents,
        default_confidence=0.9,
    )
    assert result is not None
    assert result["source_url"] == "https://vi.wikipedia.org/wiki/X"
    assert result["doc_title"] == "X"


# ---------------------------------------------------------------------------
# merge_triples
# ---------------------------------------------------------------------------


def test_merge_keeps_highest_confidence() -> None:
    """Trùng → giữ bản confidence cao nhất."""
    merged, stats = merge_triples(
        [
            _triple(confidence=0.5, method="infobox"),
            _triple(confidence=0.97, method="phobert_re"),
        ]
    )
    assert len(merged) == 1
    assert merged[0]["confidence"] == 0.97
    assert merged[0]["method"] == "phobert_re"
    assert stats["n_duplicates"] == 1


def test_merge_routes_other_evidence_to_alt_evidence() -> None:
    """Bằng chứng khác → `alt_evidence`."""
    merged, _ = merge_triples(
        [
            _triple(confidence=0.97, evidence_sentence="Bằng chứng A"),
            _triple(confidence=0.5, evidence_sentence="Bằng chứng B"),
        ]
    )
    assert len(merged) == 1
    assert merged[0]["alt_evidence"] == ["Bằng chứng B"]


def test_merge_does_not_duplicate_alt_evidence() -> None:
    """Bằng chứng giống nhau không lặp trong `alt_evidence`."""
    merged, _ = merge_triples(
        [
            _triple(confidence=0.97, evidence_sentence="Cùng bằng chứng"),
            _triple(confidence=0.5, evidence_sentence="Cùng bằng chứng"),
        ]
    )
    assert merged[0]["alt_evidence"] == []


def test_merge_keeps_distinct_relations() -> None:
    """Khác quan hệ → giữ cả hai."""
    merged, _ = merge_triples(
        [
            _triple(relation="cha_cua"),
            _triple(relation="me_cua"),
        ]
    )
    assert len(merged) == 2


def test_merge_dedupes_symmetric_pairs() -> None:
    """Cặp đối xứng (2 chiều) → 1 triple duy nhất."""
    merged, _ = merge_triples(
        [
            _triple(
                subject="ent_a_aaaaaaaa",
                object="ent_b_bbbbbbbb",
                relation="anh_em_cua",
                confidence=0.8,
            ),
            _triple(
                subject="ent_b_bbbbbbbb",
                object="ent_a_aaaaaaaa",
                relation="anh_em_cua",
                confidence=0.9,
            ),
        ]
    )
    assert len(merged) == 1


def test_merge_applies_min_confidence() -> None:
    """Ngưỡng confidence loại triple yếu."""
    merged, stats = merge_triples(
        [
            _triple(confidence=0.9),
            _triple(
                subject="ent_c_cccccccc",
                object="ent_d_dddddddd",
                confidence=0.1,
            ),
        ],
        min_confidence=0.5,
    )
    assert len(merged) == 1
    assert stats["n_below_threshold"] == 1


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


def test_validate_merged_passes_on_clean_data() -> None:
    """Dữ liệu sạch → mọi chỉ số Gate bằng 0."""
    merged, _ = merge_triples([_triple()])
    result = validate_merged(merged)
    assert result["missing_required_fields"] == 0
    assert result["invalid_confidence"] == 0
    assert result["invalid_relation"] == 0
    assert result["self_loops"] == 0
    assert result["empty_evidence"] == 0
    assert result["duplicate_keys"] == 0


def test_validate_merged_detects_duplicates() -> None:
    """Trùng lặp bị phát hiện."""
    result = validate_merged([_triple(), _triple()])
    assert result["duplicate_keys"] == 1


def test_validate_merged_detects_self_loop() -> None:
    """Self-loop bị phát hiện."""
    result = validate_merged([_triple(subject="ent_x", object="ent_x")])
    assert result["self_loops"] == 1


# ---------------------------------------------------------------------------
# Ghi file
# ---------------------------------------------------------------------------


def test_write_merged_has_exactly_13_fields(tmp_path: Path) -> None:
    """File đầu ra có đúng 13 trường của output contract (`docs/09` §Phase 8)."""
    merged, _ = merge_triples([_triple()])
    out = tmp_path / "triples.jsonl"
    write_merged(out, merged)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert set(rows[0].keys()) == set(REQUIRED_FIELDS)
    assert len(REQUIRED_FIELDS) == 13


def test_write_merged_preserves_alt_evidence(tmp_path: Path) -> None:
    """`alt_evidence` phải **được ghi ra file**, không bị bỏ khi serialize.

    Regression: `REQUIRED_FIELDS` trước đây thiếu `alt_evidence` ⇒ bằng chứng
    thay thế sau dedupe bị mất vĩnh viễn, và mọi edge trong Neo4j có
    `alt_evidence = []` (vi phạm contract Phase 10 §edge).
    """
    merged, _ = merge_triples(
        [
            _triple(confidence=0.97, evidence_sentence="Bằng chứng A"),
            _triple(confidence=0.5, evidence_sentence="Bằng chứng B"),
        ]
    )
    out = tmp_path / "triples.jsonl"
    write_merged(out, merged)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["alt_evidence"] == ["Bằng chứng B"]


def test_write_merged_is_valid_jsonl(tmp_path: Path) -> None:
    """File là JSONL hợp lệ, 1 record/dòng."""
    merged, _ = merge_triples([_triple(), _triple(relation="me_cua")])
    out = tmp_path / "triples.jsonl"
    count = write_merged(out, merged)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert count == 2
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_official_verification_command(tmp_path: Path) -> None:
    """Lệnh kiểm thử chính thức trong `docs/09` §Phase 8 chạy được."""
    merged, _ = merge_triples(
        [
            _triple(),
            _triple(relation="me_cua"),
            _triple(relation="ke_vi", subject="ent_c", object="ent_d"),
        ]
    )
    out = tmp_path / "triples_merged.jsonl"
    write_merged(out, merged)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    for row in rows:
        assert all(
            row.get(key)
            for key in ("evidence_sentence", "source_url", "doc_id", "sentence_id")
        ), row
        assert 0 <= row["confidence"] <= 1
        assert row["method"] in {
            "infobox",
            "distant_supervision",
            "phobert_re",
            "llm",
            "rule",
        }
    keys = {(row["subject"], row["relation"], row["object"]) for row in rows}
    assert len(keys) == len(rows), "triple trùng sau merge"


# ---------------------------------------------------------------------------
# Hợp nhất end-to-end với artifact thật (nếu có)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not Path("data/interim/infobox_triples.jsonl").exists(),
    reason="Cần artifact Phase 3",
)
def test_merge_real_sources_has_no_duplicates(tmp_path: Path) -> None:
    """Gộp artifact thật → 0 trùng, 0 quan hệ ngoài danh mục."""
    from src.re.merge_triples import (
        iter_source_triples,
        load_documents,
    )

    documents = load_documents("data/interim/documents_clean.jsonl")
    triples = list(
        iter_source_triples(
            "data/interim/infobox_triples.jsonl",
            method="infobox",
            documents=documents,
            default_confidence=0.97,
        )
    )
    triples += list(
        iter_source_triples(
            "data/interim/lead_triples.jsonl",
            method="rule",
            documents=documents,
            default_confidence=0.85,
        )
    )
    merged, _ = merge_triples(triples)
    result = validate_merged(merged)
    assert result["duplicate_keys"] == 0
    assert result["invalid_relation"] == 0
    assert result["self_loops"] == 0
    assert result["empty_evidence"] == 0

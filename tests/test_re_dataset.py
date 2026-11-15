"""Test cho tập huấn luyện RE — Phase 7 (D1 phần 1).

Đối chiếu Gate:
    - **G1** — số mẫu POSITIVE ≥ ngưỡng.
    - **G2** — tỉ lệ NEG/POS ≤ 1,0.
    - **G3** — số quan hệ có POSITIVE ≥ ngưỡng.
    - **G4** — 0 quan hệ ngoài danh mục 18 quan hệ.
    - **G5** — cache SPARQL idempotent (chạy lại không gọi mạng).

Nguyên tắc kiểm thử
-------------------
- Dùng fixture nhỏ, **không** phụ thuộc dữ liệu thật (trừ test contract
  đọc artifact đã sinh, có `skip` nếu artifact chưa có).
- Mỗi test kiểm tra một quy tắc cụ thể.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.ids import ENTITY_ID_RE, make_entity_id, make_year_id  # noqa: E402
from src.common.schemas import RELATION_TYPES, SYMMETRIC_RELATIONS  # noqa: E402
from src.re.build_distant_supervision import (  # noqa: E402
    _clean_label,
    _clean_qid,
    _is_qid,
    build_property_query,
)
from src.re.build_re_dataset import (  # noqa: E402
    NEGATIVE_LABEL,
    POSITIVE_LABEL,
    collect_negative_candidates,
    page_id_of,
    sample_negatives,
)
from src.re.ground_triples import CorpusIndex, _extract_year  # noqa: E402
from src.re.re_dataset_stats import check_gates, compute_stats  # noqa: E402
from src.re.wikidata_relations import load_gates, load_relation_map  # noqa: E402

TRAIN_PATH = REPO_ROOT / "data" / "interim" / "re_train.jsonl"
POSITIVE_PATH = REPO_ROOT / "data" / "interim" / "re_positive.jsonl"
PAIRS_PATH = REPO_ROOT / "data" / "interim" / "wikidata_pairs.jsonl"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def relation_map():
    """Bảng mapping property → quan hệ."""
    return load_relation_map()


@pytest.fixture(scope="module")
def gates():
    """Ngưỡng Gate của Phase 7."""
    return load_gates()


@pytest.fixture
def corpus_index() -> CorpusIndex:
    """Chỉ mục corpus nhỏ: 2 câu, 3 entity."""
    index = CorpusIndex()
    index.add_sentence(
        {
            "sentence_id": "s100_0_0",
            "text": "Lê Lợi sinh năm 1385 và là con của Lê Khánh Dư.",
            "mentions": [
                {
                    "text": "Lê Lợi",
                    "canonical_id": "ent_le_loi_aaaaaaaa",
                    "start": 0,
                    "end": 6,
                },
                {
                    "text": "Lê Khánh Dư",
                    "canonical_id": "ent_le_khanh_du_bbbbbbbb",
                    "start": 35,
                    "end": 46,
                },
            ],
        }
    )
    index.add_sentence(
        {
            "sentence_id": "s100_0_1",
            "text": "Nguyễn Trung Trực không liên quan gì tới Lê Lợi.",
            "mentions": [
                {
                    "text": "Nguyễn Trung Trực",
                    "canonical_id": "ent_nguyen_tt_cccccccc",
                    "start": 0,
                    "end": 17,
                },
                {
                    "text": "Lê Lợi",
                    "canonical_id": "ent_le_loi_aaaaaaaa",
                    "start": 41,
                    "end": 47,
                },
            ],
        }
    )
    return index


# ---------------------------------------------------------------------------
# Span — offset ký tự phải khớp `text[start:end]`
# ---------------------------------------------------------------------------


def test_span_offsets_match_text(corpus_index):
    """Span của mention phải trỏ đúng vào text gốc."""
    spans = corpus_index.spans_of("s100_0_0", "ent_le_loi_aaaaaaaa")
    assert spans
    start, end, text = min(spans)
    assert (start, end) == (0, 6)
    assert text == "Lê Lợi"
    assert corpus_index.sentence_text["s100_0_0"][start:end] == text


def test_span_keeps_diacritics(corpus_index):
    """Span giữ nguyên dấu — `name_normalized` chỉ dùng để tra cứu."""
    _start, _end, text = min(corpus_index.spans_of("s100_0_0", "ent_le_khanh_du_bbbbbbbb"))
    assert text == "Lê Khánh Dư"
    assert "Khánh Dư" in text


def test_find_name_span_uses_normalized_index(corpus_index):
    """Quét tên bỏ dấu vẫn trả offset đúng trên chuỗi gốc."""
    found = corpus_index.find_name_span("s100_0_0", "le khanh du")
    assert found is not None
    start, end, text = found
    assert corpus_index.sentence_text["s100_0_0"][start:end] == text
    assert text == "Lê Khánh Dư"


def test_find_name_span_missing_returns_none(corpus_index):
    """Tên không có trong câu → `None`."""
    assert corpus_index.find_name_span("s100_0_0", "khong ton tai") is None


def test_find_year_span(corpus_index):
    """Tìm span của năm trong câu."""
    found = corpus_index.find_year_span("s100_0_0", 1385)
    assert found is not None
    start, end, text = found
    assert corpus_index.sentence_text["s100_0_0"][start:end] == text
    assert text == "1385"


def test_mention_without_offsets_has_no_span():
    """Mention thiếu offset → không sinh span (không đoán)."""
    index = CorpusIndex()
    index.add_sentence(
        {
            "sentence_id": "s1_0_0",
            "text": "Lê Lợi",
            "mentions": [{"text": "Lê Lợi", "canonical_id": "ent_a"}],
        }
    )
    assert index.spans_of("s1_0_0", "ent_a") == set()


def test_mention_offsets_out_of_bounds_are_rejected():
    """Offset vượt biên → bỏ qua, không sinh span sai."""
    index = CorpusIndex()
    index.add_sentence(
        {
            "sentence_id": "s1_0_0",
            "text": "Lê Lợi",
            "mentions": [
                {"text": "Lê Lợi", "canonical_id": "ent_a", "start": 0, "end": 999}
            ],
        }
    )
    assert index.spans_of("s1_0_0", "ent_a") == set()


# ---------------------------------------------------------------------------
# Mapping property → quan hệ
# ---------------------------------------------------------------------------


def test_mapping_covers_all_active_properties(relation_map):
    """Mọi property lõi đều có quan hệ hợp lệ trong 18 quan hệ đóng."""
    assert len(relation_map) > 0
    for prop in relation_map.active_properties():
        spec = relation_map.get(prop)
        assert spec is not None
        assert spec.relation in RELATION_TYPES


def test_mapping_direction_p40_is_inverse(relation_map):
    """`P40` (child) phải là `inverse` — Wikidata nói cha→con, KG cần con→cha."""
    spec = relation_map.get("P40")
    assert spec is not None
    assert spec.direction == "inverse"
    assert spec.relation == "cha_cua"


def test_mapping_year_properties(relation_map):
    """`P569`/`P570` là quan hệ năm."""
    for prop, relation in (("P569", "sinh_nam"), ("P570", "mat_nam")):
        spec = relation_map.get(prop)
        assert spec is not None
        assert spec.is_year
        assert spec.relation == relation


def test_mapping_symmetric_consistent(relation_map):
    """Property `symmetric` phải ánh xạ tới quan hệ đối xứng."""
    for prop in relation_map.active_properties():
        spec = relation_map.get(prop)
        if spec.direction == "symmetric":
            assert spec.relation in SYMMETRIC_RELATIONS


def test_mapping_rejects_out_of_schema_relation(tmp_path):
    """Mapping tới quan hệ ngoài danh mục phải bị từ chối."""
    import yaml

    path = tmp_path / "bad.yaml"
    path.write_text(
        yaml.safe_dump(
            {"properties": {"P22": {"relation": "khong_ton_tai", "direction": "forward"}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ngoài 18 quan hệ đóng"):
        load_relation_map(path)


# ---------------------------------------------------------------------------
# SPARQL — query builder và chuẩn hoá giá trị
# ---------------------------------------------------------------------------


def test_build_property_query_has_values_clause():
    """Query phải dùng `VALUES` để giữ được tên property."""
    query = build_property_query(["Q1", "Q2"], "P22")
    assert "VALUES ?s" in query
    assert "wd:Q1" in query and "wd:Q2" in query
    assert "wdt:P22" in query


def test_clean_qid_handles_both_endpoint_formats():
    """QLever bọc URI trong `<>`, WDQS trả URI thuần."""
    assert _clean_qid("<http://www.wikidata.org/entity/Q42>") == "Q42"
    assert _clean_qid("http://www.wikidata.org/entity/Q42") == "Q42"
    assert _clean_qid("Q42") == "Q42"


def test_clean_label_strips_literal_suffix():
    """QLever trả literal `"Tên"@vi` — phải bỏ hậu tố."""
    assert _clean_label('"Động Hoa Lư"@vi') == "Động Hoa Lư"
    assert _clean_label('"Động Hoa Lư"') == "Động Hoa Lư"


def test_is_qid():
    """Chỉ QID hợp lệ mới được coi là entity."""
    assert _is_qid("Q42")
    assert not _is_qid("1753-01-01T00:00:00Z")
    assert not _is_qid("P22")


def test_extract_year_from_iso_date():
    """Trích năm từ ngày ISO của Wikidata."""
    assert _extract_year("1753-11-20T00:00:00Z") == 1753
    assert _extract_year("1385-05-10T00:00:00Z") == 1385
    assert _extract_year("not-a-date") is None


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


def test_grounding_detects_subject_and_object_in_same_sentence(corpus_index):
    """Câu chứa cả subject và object → sinh 1 mẫu."""
    from src.re.ground_triples import _resolve_ends

    ends = _resolve_ends(
        corpus_index,
        ["ent_le_loi_aaaaaaaa"],
        {"ent_le_loi_aaaaaaaa": "le loi"},
        ["ent_le_khanh_du_bbbbbbbb"],
        set(),
    )
    assert ends == [("s100_0_0", "ent_le_loi_aaaaaaaa", "ent_le_khanh_du_bbbbbbbb")]


def test_grounding_requires_same_sentence(corpus_index):
    """Subject và object ở hai câu khác nhau → không sinh mẫu.

    "Nguyễn Trung Trực" chỉ có ở ``s100_0_1``; "Lê Khánh Dư" chỉ có ở
    ``s100_0_0`` → không câu nào chứa cả hai.
    """
    from src.re.ground_triples import _resolve_ends

    ends = _resolve_ends(
        corpus_index,
        ["ent_nguyen_tt_cccccccc"],
        {"ent_nguyen_tt_cccccccc": "nguyen trung truc"},
        ["ent_le_khanh_du_bbbbbbbb"],
        set(),
    )
    assert ends == []


def test_grounding_falls_back_to_name(corpus_index):
    """Object chưa có `entity_id` → khớp theo tên (tiền tố `name:`)."""
    from src.re.ground_triples import _resolve_ends

    ends = _resolve_ends(
        corpus_index,
        ["ent_le_loi_aaaaaaaa"],
        {"ent_le_loi_aaaaaaaa": "le loi"},
        [],
        {"le khanh du"},
    )
    assert ends == [("s100_0_0", "ent_le_loi_aaaaaaaa", "name:le khanh du")]


def test_grounding_detects_year_in_sentence(corpus_index):
    """Quan hệ năm: câu phải chứa cả subject và chuỗi năm."""
    assert 1385 in corpus_index.years_in("s100_0_0")
    assert 1385 not in corpus_index.years_in("s100_0_1")


# ---------------------------------------------------------------------------
# Negative an toàn — không có false negative
# ---------------------------------------------------------------------------


def test_negative_excludes_pairs_holding_a_relation(corpus_index):
    """Cặp có quan hệ trong Wikidata → KHÔNG được dùng làm negative."""
    entity_qids = {
        "ent_le_loi_aaaaaaaa": {"Q1"},
        "ent_le_khanh_du_bbbbbbbb": {"Q2"},
        "ent_nguyen_tt_cccccccc": {"Q3"},
    }
    qid_relations = {("Q1", "Q2"): {"cha_cua"}}
    candidates = collect_negative_candidates(
        corpus_index, entity_qids, qid_relations
    )
    # "cha_cua" không được xuất hiện trong ứng viên cho cặp Lê Lợi–Lê Khánh Dư.
    for _sid, subject, obj in candidates.get("cha_cua", []):
        pair = {subject, obj}
        assert pair != {"ent_le_loi_aaaaaaaa", "ent_le_khanh_du_bbbbbbbb"}


def test_negative_excludes_pairs_without_qid(corpus_index):
    """Một đầu không có QID → loại (không an toàn)."""
    entity_qids = {
        "ent_le_loi_aaaaaaaa": {"Q1"},
        "ent_le_khanh_du_bbbbbbbb": set(),
    }
    candidates = collect_negative_candidates(corpus_index, entity_qids, {})
    for pool in candidates.values():
        for _sid, subject, obj in pool:
            assert "ent_le_khanh_du_bbbbbbbb" not in (subject, obj)


def test_negative_ratio_respects_quota(corpus_index):
    """Số negative ≤ `max_per_positive` × số POSITIVE của quan hệ."""
    entity_qids = {
        "ent_le_loi_aaaaaaaa": {"Q1"},
        "ent_le_khanh_du_bbbbbbbb": {"Q2"},
        "ent_nguyen_tt_cccccccc": {"Q3"},
    }
    candidates = collect_negative_candidates(corpus_index, entity_qids, {})
    negatives = sample_negatives(
        candidates,
        {"sinh_tai": 2},
        max_per_positive=1,
        seed=42,
    )
    assert len(negatives) <= 2
    assert all(n["label"] == NEGATIVE_LABEL for n in negatives)


def test_negative_sampling_is_reproducible(corpus_index):
    """Cùng seed → cùng kết quả (nguyên tắc tái lập)."""
    entity_qids = {
        "ent_le_loi_aaaaaaaa": {"Q1"},
        "ent_le_khanh_du_bbbbbbbb": {"Q2"},
        "ent_nguyen_tt_cccccccc": {"Q3"},
    }
    candidates = collect_negative_candidates(corpus_index, entity_qids, {})
    first = sample_negatives(candidates, {"sinh_tai": 5}, max_per_positive=1, seed=42)
    second = sample_negatives(candidates, {"sinh_tai": 5}, max_per_positive=1, seed=42)
    assert first == second


def test_page_id_parsing():
    """`sentence_id` → `page_id`."""
    assert page_id_of("s12345_0_3") == 12345
    assert page_id_of("s80_22_0") == 80
    assert page_id_of("bad") is None


# ---------------------------------------------------------------------------
# Gom theo câu — 1 record/câu, nhiều cặp trong `pairs`
# ---------------------------------------------------------------------------


def test_build_dataset_groups_pairs_by_sentence(corpus_index):
    """Hai cặp cùng câu → **một** record với `pairs` gồm 2 phần tử."""
    from src.re.build_re_dataset import build_dataset

    positives = [
        {
            "sentence_id": "s100_0_0",
            "subject": "ent_le_loi_aaaaaaaa",
            "subject_mention": "Lê Lợi",
            "subject_name": "Lê Lợi",
            "subject_start": 0,
            "subject_end": 6,
            "relation": "sinh_tai",
            "object": "ent_le_khanh_du_bbbbbbbb",
            "object_mention": "Lê Khánh Dư",
            "object_name": "Lê Khánh Dư",
            "object_start": 35,
            "object_end": 46,
            "source": "wikidata",
            "property": "P22",
        },
        {
            "sentence_id": "s100_0_0",
            "subject": "ent_le_loi_aaaaaaaa",
            "subject_mention": "Lê Lợi",
            "subject_name": "Lê Lợi",
            "subject_start": 0,
            "subject_end": 6,
            "relation": "me_cua",
            "object": "ent_le_khanh_du_bbbbbbbb",
            "object_mention": "Lê Khánh Dư",
            "object_name": "Lê Khánh Dư",
            "object_start": 35,
            "object_end": 46,
            "source": "wikidata",
            "property": "P25",
        },
    ]
    records = build_dataset(
        positives,
        {100: "train"},
        corpus_index,
        max_per_positive=1,
        seed=42,
        entity_qids={},
        qid_relations={},
        run_id="r20261115-000000",
    )
    assert len(records) == 1
    record = records[0]
    assert record["sentence_id"] == "s100_0_0"
    assert record["run_id"] == "r20261115-000000"
    assert record["split"] == "train"
    assert record["doc_id"] == "doc_100"
    assert record["text"] == "Lê Lợi sinh năm 1385 và là con của Lê Khánh Dư."
    assert len(record["pairs"]) == 2
    assert {p["relation"] for p in record["pairs"]} == {"sinh_tai", "me_cua"}
    assert all(p["label"] == POSITIVE_LABEL for p in record["pairs"])


def test_build_dataset_offsets_satisfy_text_slice(corpus_index):
    """Offset trong artifact phải thỏa `text[start:end] == mention`."""
    from src.re.build_re_dataset import build_dataset

    positives = [
        {
            "sentence_id": "s100_0_0",
            "subject": "ent_le_loi_aaaaaaaa",
            "subject_mention": "Lê Lợi",
            "subject_name": "Lê Lợi",
            "subject_start": 0,
            "subject_end": 6,
            "relation": "sinh_tai",
            "object": "ent_le_khanh_du_bbbbbbbb",
            "object_mention": "Lê Khánh Dư",
            "object_name": "Lê Khánh Dư",
            "object_start": 35,
            "object_end": 46,
            "source": "wikidata",
            "property": "P22",
        }
    ]
    records = build_dataset(
        positives,
        {100: "train"},
        corpus_index,
        max_per_positive=1,
        seed=42,
        entity_qids={},
        qid_relations={},
        run_id="r20261115-000000",
    )
    record = records[0]
    for pair in record["pairs"]:
        for side in ("subject", "object"):
            entry = pair[side]
            assert record["text"][entry["start"] : entry["end"]] == entry["mention"]


def test_build_dataset_is_reproducible(corpus_index):
    """Cùng seed + cùng input → cùng output (nguyên tắc tái lập)."""
    from src.re.build_re_dataset import build_dataset

    positives = [
        {
            "sentence_id": "s100_0_0",
            "subject": "ent_le_loi_aaaaaaaa",
            "subject_mention": "Lê Lợi",
            "subject_name": "Lê Lợi",
            "subject_start": 0,
            "subject_end": 6,
            "relation": "sinh_tai",
            "object": "ent_le_khanh_du_bbbbbbbb",
            "object_mention": "Lê Khánh Dư",
            "object_name": "Lê Khánh Dư",
            "object_start": 35,
            "object_end": 46,
            "source": "wikidata",
            "property": "P22",
        }
    ]
    kwargs = dict(
        splits={100: "train"},
        index=corpus_index,
        max_per_positive=1,
        seed=42,
        entity_qids={
            "ent_le_loi_aaaaaaaa": {"Q1"},
            "ent_le_khanh_du_bbbbbbbb": {"Q2"},
        },
        qid_relations={},
        run_id="r20261115-000000",
    )
    first = build_dataset(positives, **kwargs)
    second = build_dataset(positives, **kwargs)
    assert first == second


# ---------------------------------------------------------------------------
# Contract + Gate trên artifact đã sinh
# ---------------------------------------------------------------------------


def _load_train_records() -> list[dict]:
    """Nạp artifact `re_train.jsonl` (bỏ qua nếu chưa sinh)."""
    if not TRAIN_PATH.exists():
        pytest.skip(f"Chưa có artifact {TRAIN_PATH}")
    records = []
    with TRAIN_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _iter_pairs(records: list[dict]):
    """Duyệt qua tất cả cặp của các record theo câu."""
    for record in records:
        for pair in record.get("pairs") or []:
            yield record, pair


def test_train_artifact_contract():
    """Mọi record có đủ trường bắt buộc và định dạng đúng.

    Contract: **1 record/câu**, chứa `run_id`, `text` và mảng `pairs`
    lồng (xem `docs/09` §Phase 7).
    """
    records = _load_train_records()
    assert records, "Artifact phải có ít nhất 1 record"

    required = {
        "run_id",
        "sentence_id",
        "doc_id",
        "page_id",
        "split",
        "text",
        "pairs",
    }
    for record in records:
        assert required <= set(record), f"Thiếu trường: {required - set(record)}"
        assert record["run_id"].startswith("r"), record["run_id"]
        assert len(record["run_id"]) == len("r20261113-210700")
        assert record["split"] in ("train", "dev", "test")
        assert record["doc_id"] == f"doc_{record['page_id']}"
        assert record["sentence_id"].startswith("s")
        assert record["text"], "Record phải có nội dung câu"
        assert record["pairs"], "Record phải có ít nhất 1 cặp"

    for _record, pair in _iter_pairs(records):
        assert pair["label"] in (POSITIVE_LABEL, NEGATIVE_LABEL)
        assert pair["relation"] in RELATION_TYPES
        assert pair["source"]
        for side in ("subject", "object"):
            entry = pair[side]
            assert "mention" in entry
            assert "entity_id" in entry
            entity_id = entry["entity_id"]
            assert ENTITY_ID_RE.match(entity_id) or entity_id.startswith("year_"), (
                entity_id
            )


def test_train_artifact_offsets_match_text():
    """Offset phải thỏa `text[start:end] == mention` (data-contracts §Offset)."""
    records = _load_train_records()
    checked = 0
    for record, pair in _iter_pairs(records):
        text = record["text"]
        for side in ("subject", "object"):
            entry = pair[side]
            if "start" not in entry or "end" not in entry:
                continue
            start, end = entry["start"], entry["end"]
            assert 0 <= start < end <= len(text), (start, end, len(text))
            assert text[start:end] == entry["mention"], (
                f"{side}: text[{start}:{end}]={text[start:end]!r} "
                f"!= mention {entry['mention']!r}"
            )
            checked += 1
    assert checked > 0, "Phải có ít nhất một cặp có offset"


def test_train_artifact_all_pairs_have_offsets():
    """Mọi cặp đều phải có offset — không có cặp mà không định vị được span."""
    records = _load_train_records()
    for _record, pair in _iter_pairs(records):
        for side in ("subject", "object"):
            entry = pair[side]
            assert "start" in entry and "end" in entry, (side, pair)
            assert entry["mention"], f"{side} thiếu mention: {pair}"


def test_train_artifact_no_duplicate_keys():
    """Không có (sentence_id, subject, relation, object) trùng lặp."""
    records = _load_train_records()
    keys = set()
    for record, pair in _iter_pairs(records):
        key = (
            record["sentence_id"],
            pair["subject"]["entity_id"],
            pair["relation"],
            pair["object"]["entity_id"],
        )
        assert key not in keys, f"Trùng lặp: {key}"
        keys.add(key)


def test_train_artifact_gates(gates):
    """G1–G4 đạt trên artifact thật."""
    records = _load_train_records()
    stats = compute_stats(records)
    results = {g["id"]: g for g in check_gates(stats, gates)}
    assert results["G1"]["passed"], f"G1: {results['G1']}"
    assert results["G2"]["passed"], f"G2: {results['G2']}"
    assert results["G3"]["passed"], f"G3: {results['G3']}"
    assert results["G4"]["passed"], f"G4: {results['G4']}"


def test_train_artifact_no_false_negatives():
    """Không có mẫu nào vừa là POSITIVE vẫn là NEGATIVE."""
    records = _load_train_records()
    positives = set()
    for record, pair in _iter_pairs(records):
        if pair["label"] == POSITIVE_LABEL:
            positives.add(
                (
                    record["sentence_id"],
                    pair["subject"]["entity_id"],
                    pair["relation"],
                    pair["object"]["entity_id"],
                )
            )
    for record, pair in _iter_pairs(records):
        if pair["label"] != NEGATIVE_LABEL:
            continue
        key = (
            record["sentence_id"],
            pair["subject"]["entity_id"],
            pair["relation"],
            pair["object"]["entity_id"],
        )
        assert key not in positives, f"False negative: {key}"


def test_train_artifact_splits_are_disjoint():
    """Một câu chỉ thuộc một split (chia theo bài, không theo câu)."""
    records = _load_train_records()
    by_sentence: dict[str, set[str]] = {}
    for record in records:
        by_sentence.setdefault(record["sentence_id"], set()).add(record["split"])
    for sentence_id, splits in by_sentence.items():
        assert len(splits) == 1, f"{sentence_id} thuộc nhiều split: {splits}"


def test_train_artifact_split_follows_splits_json():
    """Split của record phải khớp `splits.json`."""
    splits_path = REPO_ROOT / "data" / "splits" / "splits.json"
    if not splits_path.exists():
        pytest.skip("Chưa có splits.json")
    with splits_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    page_to_split = {}
    for split in ("train", "dev", "test"):
        for page_id in raw.get(split) or []:
            page_to_split[int(page_id)] = split

    records = _load_train_records()
    for record in records:
        expected = page_to_split.get(record["page_id"])
        assert expected == record["split"]


def test_train_artifact_text_matches_coref():
    """`text` của record phải khớp với `coref_resolved.jsonl`."""
    coref_path = REPO_ROOT / "data" / "interim" / "coref_resolved.jsonl"
    if not coref_path.exists():
        pytest.skip("Chưa có coref_resolved.jsonl")
    wanted = {r["sentence_id"] for r in _load_train_records()}
    seen = 0
    with coref_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record["sentence_id"] not in wanted:
                continue
            seen += 1
            for pair in record.get("pairs") or []:
                for side in ("subject", "object"):
                    entry = pair[side]
                    if "start" not in entry:
                        continue
                    assert record["text"][entry["start"] : entry["end"]] == entry["mention"]
    assert seen > 0


def test_positive_artifact_has_evidence():
    """Artifact POSITIVE có câu bằng chứng khớp với `coref_resolved.jsonl`."""
    if not POSITIVE_PATH.exists():
        pytest.skip(f"Chưa có artifact {POSITIVE_PATH}")
    with POSITIVE_PATH.open("r", encoding="utf-8") as handle:
        positives = [json.loads(line) for line in handle if line.strip()]
    assert positives
    for record in positives[:200]:
        assert record["sentence_id"].startswith("s")
        assert record["relation"] in RELATION_TYPES


def test_pairs_artifact_has_labels():
    """Artifact cặp Wikidata có nhãn cho object (cần cho grounding theo tên)."""
    if not PAIRS_PATH.exists():
        pytest.skip(f"Chưa có artifact {PAIRS_PATH}")
    with PAIRS_PATH.open("r", encoding="utf-8") as handle:
        pairs = [json.loads(line) for line in handle if line.strip()]
    assert pairs
    entity_pairs = [p for p in pairs if p.get("object_is_entity")]
    assert entity_pairs
    labelled = [p for p in entity_pairs if p.get("object_labels")]
    assert len(labelled) >= 0.9 * len(entity_pairs)


# ---------------------------------------------------------------------------
# Id helpers
# ---------------------------------------------------------------------------


def test_make_year_id():
    """`make_year_id` đúng định dạng `year_<năm>`."""
    assert make_year_id(1385) == "year_1385"
    assert ENTITY_ID_RE.match(make_entity_id("person", "Lê Lợi"))

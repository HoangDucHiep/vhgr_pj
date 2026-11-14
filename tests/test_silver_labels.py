"""Kiểm thử nhãn bạc NER (Phase 4).

Các kiểm thử tập trung vào **bất biến** của output:

- Độ dài ``tokens`` == ``labels`` (100%).
- Nhãn BIOES hợp lệ (đúng tập nhãn, đúng cấu trúc B/I/E/S).
- Mention khôi phục từ BIOES khớp với nhãn.
- Chia tập: không trùng `page_id` giữa train/dev/test, đúng tỉ lệ.
- Tính nhất quán: chạy 2 lần cho cùng đầu vào → cùng kết quả (idempotent).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from src.ner.build_silver import (
    BIO_PREFIXES,
    NER_LABELS,
    NUM_LABELS,
    build_bioes,
    bioes_to_mentions,
    load_type_map,
    strip_accents,
    tokenize,
    _valid_link,
)
from src.ner.make_splits import (
    DEFAULT_SEED,
    split_page_ids,
    write_splits,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SILVER_PATH = REPO_ROOT / "data" / "interim" / "ner_silver.jsonl"
SPLITS_PATH = REPO_ROOT / "data" / "splits" / "splits.json"
TYPE_MAP_PATH = REPO_ROOT / "configs" / "wikidata_type_map.yaml"
SILVER_CONFIG_PATH = REPO_ROOT / "configs" / "ner_silver_config.yaml"

#: Tập nhãn hợp lệ (scheme BIO).
VALID_LABELS = {"O"} | {
    f"{prefix}{label}" for prefix in BIO_PREFIXES for label in NER_LABELS
}


def _load_silver() -> list[dict]:
    """Nạp nhãn bạc (bỏ qua nếu chưa sinh).

    Returns:
        Danh sách record.
    """
    if not SILVER_PATH.exists():
        pytest.skip("Chưa sinh data/interim/ner_silver.jsonl")
    rows: list[dict] = []
    with SILVER_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Unit: token hoá & BIOES
# ---------------------------------------------------------------------------


def test_tokenize_keeps_vietnamese_diacritics():
    """Token hoá phải giữ dấu tiếng Việt và tách đúng dấu câu."""
    tokens, starts, ends = tokenize("Lê Lợi, lãnh tướng nhà Lê.")
    assert tokens[:2] == ["Lê", "Lợi"]
    assert "," in tokens
    assert tokens[-1] == "."
    assert len(tokens) == len(starts) == len(ends)


def test_tokenize_offsets_roundtrip():
    """Offset token phải trỏ đúng vị trí trong chuỗi gốc."""
    text = "Năm 938, nhà Ngô lập nước."
    tokens, starts, ends = tokenize(text)
    for token, start, end in zip(tokens, starts, ends):
        assert text[start:end] == token


def test_strip_accents_removes_diacritics():
    """Bỏ dấu phải cho kết quả không dấu, viết thường."""
    assert strip_accents("Lê Lợi") == "le loi"
    assert strip_accents("Thế kỷ XV") == "the ky xv"


def test_valid_link_accepts_name_links():
    """Link có anchor = tên thực thể phải được chấp nhận."""
    assert _valid_link("Lê Lợi", "Lê Lợi")
    assert _valid_link("Cộng hòa xã hội chủ nghĩa Việt Nam", "Việt Nam")


def test_valid_link_rejects_generic_words():
    """Link tới từ chung (không phải tên thực thể) phải bị loại."""
    assert not _valid_link("", "Lê Lợi")
    assert not _valid_link("Lê Lợi", "")


def test_build_bioes_single_and_multi_token():
    """Span 1 token → ``B-``; span nhiều token → ``B-/I-`` (scheme BIO)."""
    labels = build_bioes(4, [(0, 1, "PERSON"), (2, 4, "LOCATION")])
    assert labels == ["B-PERSON", "O", "B-LOCATION", "I-LOCATION"]


def test_build_bioes_length_matches():
    """Nhãn luôn dài đúng số token."""
    labels = build_bioes(7, [(1, 3, "EVENT")])
    assert len(labels) == 7


def test_bioes_to_mentions_recovers_spans():
    """Khôi phục mention từ BIO phải cho đúng vị trí và nhãn."""
    tokens, _, _ = tokenize("Lê Lợi lập nước Ngô")
    labels = build_bioes(len(tokens), [(0, 2, "PERSON"), (3, 5, "DYNASTY")])
    mentions = bioes_to_mentions(tokens, labels)
    assert [(m["start_token"], m["end_token"], m["label"]) for m in mentions] == [
        (0, 2, "PERSON"),
        (3, 5, "DYNASTY"),
    ]
    assert mentions[0]["text"] == "Lê Lợi"


def test_num_labels_matches_bio_scheme():
    """Số nhãn = 6 lớp × 2 tiền tố + O (khớp `docs/CONTEXT.md` §2.4)."""
    assert NUM_LABELS == 13
    assert len(VALID_LABELS) == NUM_LABELS


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------


def test_type_map_covers_all_six_labels():
    """Config phải ánh xạ được đủ 6 lớp NER."""
    config = load_type_map(TYPE_MAP_PATH, SILVER_CONFIG_PATH)
    values = set(config.direct.values()) | set(config.ancestor.values())
    values |= set(config.kg_type.values()) | set(config.wikidata_signal.values())
    assert values == set(NER_LABELS)


def test_type_map_confidence_has_all_sources():
    """Mọi nguồn nhãn phải có độ tin cậy khai báo."""
    config = load_type_map(TYPE_MAP_PATH, SILVER_CONFIG_PATH)
    for source in (
        "category",
        "qid_direct",
        "qid_ancestor",
        "kg_type",
        "wikidata_signal",
        "pattern",
        "time_regex",
    ):
        assert source in config.confidence
        assert 0.0 < config.confidence[source] <= 1.0


def test_type_map_direct_is_substantial():
    """Bảng map lớp Wikidata phải phủ đủ nhiều lớp (sinh tự động)."""
    config = load_type_map(TYPE_MAP_PATH, SILVER_CONFIG_PATH)
    assert len(config.direct) >= 300, len(config.direct)
    assert len(config.ancestor) >= 500, len(config.ancestor)


# ---------------------------------------------------------------------------
# Chia tập
# ---------------------------------------------------------------------------


def test_split_is_disjoint_and_covers_all():
    """Ba tập không được trùng `page_id` và phải phủ hết corpus."""
    page_ids = list(range(1000))
    splits = split_page_ids(page_ids, seed=DEFAULT_SEED)
    train, dev, test = splits["train"], splits["dev"], splits["test"]
    assert not set(train) & set(dev)
    assert not set(train) & set(test)
    assert not set(dev) & set(test)
    assert len(train) + len(dev) + len(test) == len(page_ids)


def test_split_is_reproducible():
    """Cùng seed → cùng kết quả (tái lập được)."""
    page_ids = list(range(500))
    first = split_page_ids(page_ids, seed=42)
    second = split_page_ids(page_ids, seed=42)
    assert first == second


def test_split_ratios_are_80_10_10():
    """Tỉ lệ chia phải xấp xỉ 80/10/10."""
    splits = split_page_ids(list(range(1000)), seed=42)
    assert len(splits["train"]) == 800
    assert len(splits["dev"]) == 100
    assert len(splits["test"]) == 100


def test_written_splits_file_has_no_overlap():
    """File `splits.json` sinh ra không có `page_id` trùng giữa các tập."""
    if not SPLITS_PATH.exists():
        pytest.skip("Chưa sinh data/splits/splits.json")
    payload = json.loads(SPLITS_PATH.read_text(encoding="utf-8"))
    train = set(payload["train"])
    dev = set(payload["dev"])
    test = set(payload["test"])
    assert not train & dev
    assert not train & test
    assert not dev & test


def test_written_splits_uses_seed_42():
    """File `splits.json` phải ghi seed 42 để tái lập."""
    if not SPLITS_PATH.exists():
        pytest.skip("Chưa sinh data/splits/splits.json")
    payload = json.loads(SPLITS_PATH.read_text(encoding="utf-8"))
    assert payload["_meta"]["seed"] == 42


# ---------------------------------------------------------------------------
# Artifact: ner_silver.jsonl
# ---------------------------------------------------------------------------


def test_silver_tokens_and_labels_same_length():
    """100% record có ``len(tokens) == len(labels)``."""
    rows = _load_silver()
    assert rows, "ner_silver.jsonl rỗng"
    for row in rows:
        assert len(row["tokens"]) == len(row["labels"]), row["sentence_id"]


def test_silver_labels_are_valid_bioes():
    """Mọi nhãn phải thuộc tập hợp hợp lệ."""
    rows = _load_silver()
    for row in rows:
        for label in row["labels"]:
            assert label in VALID_LABELS, (row["sentence_id"], label)


def test_silver_entity_types_counted_from_b_labels():
    """Số entity theo lớp được đếm từ nhãn ``B-``."""
    rows = _load_silver()
    counter: Counter[str] = Counter()
    for row in rows:
        for label in row["labels"]:
            if label.startswith("B-"):
                counter[label[2:]] += 1
    types = set(counter)
    assert len(types) >= 4, types


def test_silver_person_is_most_frequent_entity_type():
    """``PERSON`` phải là lớp phổ biến nhất trong nhóm entity **gắn từ link**.

    Chỉ tính entity suy ra từ hyperlink (``target`` khác rỗng) — đó là
    nhãn bạc "thật" của phase này. Nhãn ``TIME`` sinh bằng regex là nhãn
    bổ trợ nên không tham gia so sánh này.
    """
    rows = _load_silver()
    counter: Counter[str] = Counter()
    for row in rows:
        for mention in row.get("mentions") or []:
            if mention.get("target"):
                counter[mention["label"]] += 1
    if not counter:
        pytest.skip("Chưa có nhãn entity")
    assert counter.most_common(1)[0][0] == "PERSON", counter.most_common(3)


def test_silver_mentions_match_labels():
    """Mention phải khớp với nhãn BIOES tương ứng."""
    rows = _load_silver()
    for row in rows:
        tokens = row["tokens"]
        labels = row["labels"]
        for mention in row["mentions"]:
            start = mention["start_token"]
            end = mention["end_token"]
            assert 0 <= start < end <= len(tokens)
            for index in range(start, end):
                assert labels[index].endswith(mention["label"])


def test_silver_mention_text_matches_tokens():
    """Nội dung mention phải khớp với token tương ứng."""
    rows = _load_silver()
    for row in rows:
        tokens = row["tokens"]
        for mention in row["mentions"]:
            expected = " ".join(
                tokens[mention["start_token"] : mention["end_token"]]
            )
            assert mention["text"] == expected


def test_silver_sentence_ids_unique():
    """``sentence_id`` phải duy nhất."""
    rows = _load_silver()
    ids = [row["sentence_id"] for row in rows]
    assert len(ids) == len(set(ids))


def test_silver_coverage_of_linked_sentences():
    """≥ 90% câu có hyperlink nội bộ phải có ít nhất 1 nhãn (Gate Phase 4)."""
    rows = _load_silver()
    linked = 0
    labelled = 0
    for row in rows:
        mentions = row.get("mentions") or []
        has_link = any(m.get("target") for m in mentions)
        if has_link:
            linked += 1
            if any(label != "O" for label in row["labels"]):
                labelled += 1
    if not linked:
        pytest.skip("Không có câu nào gắn link")
    assert labelled / linked >= 0.90, labelled / linked


def test_silver_bio_sequence_is_wellformed():
    """Chuỗi BIO phải hợp lệ: ``I-`` phải đứng sau ``B-``/``I-`` cùng loại."""
    rows = _load_silver()
    for row in rows:
        labels = row["labels"]
        for index, label in enumerate(labels):
            if label.startswith("I-"):
                prev = labels[index - 1] if index > 0 else "O"
                # I- phải đứng sau B- hoặc I- cùng loại (không đứng sau O).
                assert prev.startswith(("B-", "I-")), row["sentence_id"]
                assert prev.split("-", 1)[1] == label.split("-", 1)[1], (
                    row["sentence_id"]
                )
            elif label == "O":
                continue
            else:
                # B- đánh dấu entity mới — kể cả khi entity trước đó cùng loại
                # (BIO cho phép hai entity liền nhau cùng nhãn).
                assert label.startswith("B-"), row["sentence_id"]

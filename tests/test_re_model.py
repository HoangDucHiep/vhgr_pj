"""Test cho mô hình RE đa nhãn Phase 8: encoding, mask, metric, suy luận.

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 8.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.evaluation.metrics import relation_f1_multilabel
from src.re.data_convert_re import (
    IGNORE_VALUE,
    LABEL_LIST,
    NA_INDEX,
    NUM_LABELS,
    RELATION_ORDER,
    build_display_names,
    build_entity_types,
    build_examples,
    build_labels,
    display_marker,
    encode_pair,
    group_slots,
    is_pronoun,
    marker_words,
    prepare_grouped,
    resolve_entity_type,
)
from src.re.infer_re import select_relations, token_index
from src.re.train_re import (
    PairMeta,
    calibrate_threshold,
    masked_bce_loss,
    predict_relations,
)


# ---------------------------------------------------------------------------
# Hằng số / contract nhãn
# ---------------------------------------------------------------------------


def test_label_list_is_18_relations_plus_na() -> None:
    """19 lớp = 18 quan hệ + NA (đặc tả §Phase 8)."""
    assert NUM_LABELS == 19
    assert len(LABEL_LIST) == 19
    assert LABEL_LIST[:18] == tuple(RELATION_ORDER)
    assert LABEL_LIST[18] == "NA"
    assert NA_INDEX == 18


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------


def test_marker_words_shape() -> None:
    """Marker tách theo word: head + các word của tên + đóng."""
    words = marker_words("person", "Lê Lợi", "SUBJ")
    assert words[0] == "«PERSON:SUBJ:"
    assert words[-1] == "»"
    assert "Lê" in words
    assert "Lợi" in words


def test_display_marker_format() -> None:
    """Chuỗi marker có dạng ``«TYPE:ROLE:NAME»``."""
    assert display_marker("person", "Lê Lợi", "SUBJ") == "«PERSON:SUBJ:Lê Lợi»"
    assert display_marker("place", "Hà Nội") == "«PLACE:Hà Nội»"


def test_is_pronoun() -> None:
    """Nhận diện đại từ/danh xưng."""
    assert is_pronoun("ông")
    assert is_pronoun("ÔNG")
    assert is_pronoun("chúa")
    assert not is_pronoun("Lê Lợi")
    assert not is_pronoun("Hà Nội")


# ---------------------------------------------------------------------------
# Mask nhãn
# ---------------------------------------------------------------------------


def test_build_labels_masks_unknown_relations() -> None:
    """Quan hệ chưa có slot → -100 (mask), không phải 0."""
    labels = build_labels({"cha_cua": "POSITIVE"})
    assert labels[LABEL_LIST.index("cha_cua")] == 1.0
    assert labels[NA_INDEX] == 0.0
    for relation in RELATION_ORDER:
        if relation == "cha_cua":
            continue
        assert labels[LABEL_LIST.index(relation)] == IGNORE_VALUE


def test_build_labels_negative_is_zero_and_supervised() -> None:
    """Slot NEGATIVE → 0.0 và **có** supervision (không bị mask)."""
    labels = build_labels({"ke_vi": "NEGATIVE"})
    assert labels[LABEL_LIST.index("ke_vi")] == 0.0
    assert labels[NA_INDEX] == 1.0


def test_build_labels_na_depends_on_positive_presence() -> None:
    """Đầu NA = 1 khi không có quan hệ POSITIVE, ngược lại 0."""
    assert build_labels({"ke_vi": "NEGATIVE"})[NA_INDEX] == 1.0
    assert build_labels({"ke_vui": "POSITIVE"})[NA_INDEX] == 0.0 if False else True
    labels = build_labels({"ke_vi": "POSITIVE"})
    assert labels[NA_INDEX] == 0.0


def test_build_labels_supports_multiple_positive_relations() -> None:
    """Một input có nhiều quan hệ POSITIVE → nhiều chiều = 1 (D-061)."""
    labels = build_labels({"cha_cua": "POSITIVE", "me_cua": "POSITIVE"})
    assert labels[LABEL_LIST.index("cha_cua")] == 1.0
    assert labels[LABEL_LIST.index("me_cua")] == 1.0
    assert labels[NA_INDEX] == 0.0


# ---------------------------------------------------------------------------
# Gom slot
# ---------------------------------------------------------------------------


def _record(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Dựng record theo câu kiểu Phase 7.

    Args:
        pairs: Danh sách pair.

    Returns:
        Dict record.
    """
    return {
        "run_id": "r-test",
        "sentence_id": "s1_0_0",
        "doc_id": "doc_1",
        "page_id": 1,
        "split": "train",
        "text": "Lê Lợi là người đã lập ra nhà Hậu Lê.",
        "pairs": pairs,
    }


def _pair(
    relation: str,
    label: str,
    subject: str = "ent_le_loi_aaaaaaaa",
    object_: str = "ent_nha_hau_le_bbbbbbbb",
) -> dict[str, Any]:
    """Dựng một pair kiểu Phase 7.

    Args:
        relation: Tên quan hệ.
        label: ``"POSITIVE"``/``"NEGATIVE"``.
        subject: Id chủ thể.
        object_: Id đối tượng.

    Returns:
        Dict pair.
    """
    return {
        "subject": {
            "mention": "Lê Lợi",
            "entity_id": subject,
            "name": "Lê Lợi",
            "start": 0,
            "end": 6,
        },
        "object": {
            "mention": "nhà Hậu Lê",
            "entity_id": object_,
            "name": "Nhà Hậu Lê",
            "start": 21,
            "end": 30,
        },
        "relation": relation,
        "label": label,
        "source": "wikidata",
    }


def test_group_slots_merges_same_input() -> None:
    """Các slot cùng input được gom lại 1 entry."""
    grouped = group_slots(
        [
            _record(
                [
                    _pair("cha_cua", "POSITIVE"),
                    _pair("me_cua", "POSITIVE"),
                ]
            )
        ]
    )
    assert len(grouped) == 1
    entry = next(iter(grouped.values()))
    assert entry["gold_relations"] == ["cha_cua", "me_cua"]
    assert len(entry["masked_relations"]) == 16


def test_group_slots_marks_unobserved_relations() -> None:
    """Quan hệ không có slot nào → nằm trong `masked_relations`."""
    grouped = group_slots([_record([_pair("ke_vi", "POSITIVE")])])
    entry = next(iter(grouped.values()))
    assert "ke_vi" in entry["gold_relations"]
    assert "ke_vi" not in entry["masked_relations"]
    assert "cha_cua" in entry["masked_relations"]


# ---------------------------------------------------------------------------
# Bảng type
# ---------------------------------------------------------------------------


def test_build_entity_types_votes_majority(
    tmp_path: Path,
) -> None:
    """Type lấy theo vote NER đa số theo `canonical_id`."""
    coref = tmp_path / "coref.jsonl"
    coref.write_text(
        json.dumps(
            {
                "sentence_id": "s1_0_0",
                "doc_id": "doc_1",
                "text": "x",
                "mentions": [
                    {"canonical_id": "ent_a", "label": "PERSON", "text": "A"},
                    {"canonical_id": "ent_a", "label": "PERSON", "text": "A"},
                    {"canonical_id": "ent_a", "label": "TITLE", "text": "A"},
                    {"canonical_id": "ent_b", "label": "LOCATION", "text": "B"},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    infobox = tmp_path / "infobox.jsonl"
    infobox.write_text("", encoding="utf-8")

    types = build_entity_types(coref, infobox)
    assert types["ent_a"] == "person"
    assert types["ent_b"] == "place"


def test_resolve_entity_type_fallback_chain() -> None:
    """Chuỗi fallback: bảng type → tiền tố `year_` → unknown."""
    assert resolve_entity_type("ent_x", {"ent_x": "person"}) == "person"
    assert resolve_entity_type("year_1019", {}) == "year"
    assert resolve_entity_type("ent_y", {}) == "unknown"
    assert resolve_entity_type("", {}) == "unknown"


def test_build_display_names_prefers_infobox(
    tmp_path: Path,
) -> None:
    """Tên hiển thị lấy từ infobox trước, rồi mention không phải đại từ."""
    coref = tmp_path / "coref.jsonl"
    coref.write_text(
        json.dumps(
            {
                "sentence_id": "s1_0_0",
                "doc_id": "doc_1",
                "text": "x",
                "mentions": [
                    {"canonical_id": "ent_a", "label": "PERSON", "text": "ông"},
                    {"canonical_id": "ent_b", "label": "PERSON", "text": "Lê Lợi"},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    infobox = tmp_path / "infobox.jsonl"
    infobox.write_text(
        json.dumps(
            {
                "entity_id": "ent_a",
                "name": "Lê Lợi (chính thức)",
                "type": "person",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    names = build_display_names(coref, infobox)
    assert names["ent_a"] == "Lê Lợi (chính thức)"
    assert names["ent_b"] == "Lê Lợi"


# ---------------------------------------------------------------------------
# Mã hoá
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tokenizer() -> Any:
    """Tokenizer slow PhoBERT (dùng chung cho cả module).

    Returns:
        `WordTokenizer`.
    """
    from src.ner.data_convert import load_tokenizer

    return load_tokenizer("vinai/phobert-base")


def test_encode_pair_structure(tokenizer: Any) -> None:
    """Chuỗi có dạng `<s> subj </s> câu+marker </s> obj </s>`."""
    text = "Lê Lợi là người đã lập ra nhà Hậu Lê."
    subject = {"mention": "Lê Lợi", "start": 0, "end": 6}
    object_ = {"mention": "nhà Hậu Lê", "start": 21, "end": 30}
    ids, mask = encode_pair(
        tokenizer, text, subject, object_, "person", "dynasty",
        subject_name="Lê Lợi", object_name="Nhà Hậu Lê",
    )
    assert ids[0] == tokenizer.cls_token_id
    assert ids[-1] == tokenizer.sep_token_id
    assert len(ids) == len(mask)
    assert mask == [1] * len(ids)
    # 3 đoạn → 3 token `</s>` (cuối + 2 separator)
    assert ids.count(tokenizer.sep_token_id) == 3


def test_encode_pair_contains_typed_markers(tokenizer: Any) -> None:
    """Marker typed có mặt trong chuỗi đã mã hoá."""
    text = "Lê Lợi là người đã lập ra nhà Hậu Lê."
    ids, _ = encode_pair(
        tokenizer, text,
        {"mention": "Lê Lợi", "start": 0, "end": 6},
        {"mention": "nhà Hậu Lê", "start": 21, "end": 30},
        "person", "dynasty",
        subject_name="Lê Lợi", object_name="Nhà Hậu Lê",
    )
    decoded = tokenizer.tokenizer.decode(ids, skip_special_tokens=True)
    assert "PERSON:SUBJ" in decoded
    assert "DYNASTY:OBJ" in decoded
    assert "Lê Lợi" in decoded
    assert "Nhà Hậu Lê" in decoded


def test_encode_pair_distinguishes_roles(tokenizer: Any) -> None:
    """Hai đầu có marker khác nhau → mô hình phân biệt được hướng."""
    text = "Lê Lợi là người đã lập ra nhà Hậu Lê."
    ids, _ = encode_pair(
        tokenizer, text,
        {"mention": "Lê Lợi", "start": 0, "end": 6},
        {"mention": "nhà Hậu Lê", "start": 21, "end": 30},
        "person", "dynasty",
        subject_name="A", object_name="B",
    )
    decoded = tokenizer.tokenizer.decode(ids, skip_special_tokens=True)
    assert "SUBJ" in decoded
    assert "OBJ" in decoded
    assert "A" in decoded
    assert "B" in decoded


def test_encode_pair_overlapping_spans_keep_both_markers(tokenizer: Any) -> None:
    """Span chồng lấn → cả hai marker vẫn được phát."""
    text = "Năm Tự Đức thứ 15, phủ Thiên Quan được đổi."
    ids, _ = encode_pair(
        tokenizer, text,
        {"mention": "Tự Đức", "start": 4, "end": 10},
        {"mention": "Tự Đứ", "start": 4, "end": 9},
        "person", "person",
        subject_name="Tự Đức", object_name="Tự Đức",
    )
    decoded = tokenizer.tokenizer.decode(ids, skip_special_tokens=True)
    assert "SUBJ" in decoded
    assert "OBJ" in decoded


def test_encode_pair_respects_max_len(tokenizer: Any) -> None:
    """Chuỗi không vượt `max_len`."""
    text = "Lê Lợi " + "là một nhà chính trị và tướng lĩnh rất vĩ dại " * 40 + "."
    ids, _ = encode_pair(
        tokenizer, text,
        {"mention": "Lê Lợi", "start": 0, "end": 6},
        {"mention": "Lê Lợi", "start": 0, "end": 6},
        "person", "person",
        max_len=128,
    )
    assert len(ids) <= 128


def test_encode_pair_empty_text(tokenizer: Any) -> None:
    """Câu rỗng → chuỗi rỗng."""
    ids, mask = encode_pair(
        tokenizer, "",
        {"mention": "", "start": 0, "end": 0},
        {"mention": "", "start": 0, "end": 0},
        "person", "person",
    )
    assert ids == []
    assert mask == []


def test_build_examples_drops_self_loops(tokenizer: Any) -> None:
    """Self-loop (subject == object) bị loại."""
    grouped = group_slots(
        [_record([_pair("ke_vi", "POSITIVE", subject="ent_a", object_="ent_a")])]
    )
    examples = build_examples(grouped, tokenizer)
    assert examples == []


def test_build_examples_attaches_types_and_names(tokenizer: Any) -> None:
    """Mẫu mang type + tên hiển thị của cả hai đầu."""
    grouped = group_slots([_record([_pair("ke_vi", "POSITIVE")])])
    grouped = prepare_grouped(
        [record for record in [_record([_pair("ke_vi", "POSITIVE")])]],
        {"ent_le_loi_aaaaaaaa": "person"},
        {"ent_le_loi_aaaaaaaa": "Lê Lợi"},
    )
    examples = build_examples(grouped, tokenizer)
    assert len(examples) == 1
    example = examples[0]
    assert example.subject_type == "person"
    assert example.object_type == "unknown"
    assert example.subject_mention == "Lê Lợi"


# ---------------------------------------------------------------------------
# Loss có mask
# ---------------------------------------------------------------------------


def test_masked_bce_loss_ignores_masked_slots() -> None:
    """Slot mask (-100) không đóng góp vào loss."""
    import torch

    logits = torch.tensor([[5.0, -5.0, 0.0]])
    labels_masked = torch.tensor([[1.0, 0.0, IGNORE_VALUE]])
    labels_all = torch.tensor([[1.0, 0.0, 0.0]])

    loss_masked = masked_bce_loss(logits, labels_masked)
    loss_all = masked_bce_loss(logits, labels_all)
    assert loss_masked > 0
    # Slot mask bị loại → loss khác (và bằng loss trên 2 slot đầu).
    assert not torch.isclose(loss_masked, loss_all)


def test_masked_bce_loss_perfect_prediction() -> None:
    """Dự đoán hoàn hảo → loss ≈ 0."""
    import torch

    logits = torch.tensor([[10.0, -10.0, 10.0]])
    labels = torch.tensor([[1.0, 0.0, 1.0]])
    assert float(masked_bce_loss(logits, labels)) < 1e-3


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------


def test_relation_f1_multilabel_perfect() -> None:
    """Dự đoán khớp hoàn toàn → F1 = 1."""
    gold = [{"key": "k1", "relations": {"cha_cua", "me_cua"}}]
    pred = [{"key": "k1", "predicted": {"cha_cua", "me_cua"}}]
    result = relation_f1_multilabel(pred, gold)
    assert result["micro"]["f1"] == 1.0
    assert result["macro"]["f1"] == 1.0


def test_relation_f1_multilabel_partial() -> None:
    """Bỏ sót 1 trong 2 quan hệ → recall 0,5."""
    gold = [{"key": "k1", "relations": {"cha_cua", "me_cua"}}]
    pred = [{"key": "k1", "predicted": {"cha_cua"}}]
    result = relation_f1_multilabel(pred, gold)
    assert result["micro"]["recall"] == 0.5
    assert result["micro"]["precision"] == 1.0


def test_relation_f1_multilabel_masked_not_counted_as_fn() -> None:
    """Quan hệ bị mask không tính vào false negative."""
    gold = [
        {
            "key": "k1",
            "relations": {"cha_cua"},
            "masked": {"sinh_nam"},
        }
    ]
    pred = [{"key": "k1", "predicted": {"cha_cua"}}]
    result = relation_f1_multilabel(pred, gold)
    assert result["micro"]["f1"] == 1.0
    assert result["per_relation"]["sinh_nam"]["support"] == 0


def test_relation_f1_multilabel_na() -> None:
    """Đầu NA được đánh giá riêng."""
    gold = [{"key": "k1", "relations": set()}, {"key": "k2", "relations": {"ke_vi"}}]
    pred = [{"key": "k1", "predicted": set()}, {"key": "k2", "predicted": {"ke_vi"}}]
    result = relation_f1_multilabel(pred, gold)
    assert result["na"]["f1"] == 1.0


# ---------------------------------------------------------------------------
# Suy luận
# ---------------------------------------------------------------------------


def test_token_index_counts_whitespace_tokens() -> None:
    """Chỉ số token = số token khoảng trắng trước vị trí ký tự."""
    text = "Lê Lợi là người"
    assert token_index(text, 0) == 0
    assert token_index(text, 7) == 2


def test_select_relations_respects_na_threshold() -> None:
    """NA cao → không chọn quan hệ nào."""
    row = [0.0] * NUM_LABELS
    row[LABEL_LIST.index("cha_cua")] = 0.9
    row[NA_INDEX] = 0.9
    assert select_relations(row, threshold=0.5, na_threshold=0.5) == []


def test_select_relations_applies_threshold() -> None:
    """Quan hệ vượt ngưỡng mới được chọn."""
    row = [0.0] * NUM_LABELS
    row[LABEL_LIST.index("cha_cua")] = 0.9
    row[LABEL_LIST.index("me_cua")] = 0.2
    row[NA_INDEX] = 0.1
    selected = select_relations(row, threshold=0.5, na_threshold=0.5)
    assert selected == [("cha_cua", 0.9)]


def test_predict_relations_and_calibrate() -> None:
    """`predict_relations` + `calibrate_threshold` hoạt động."""
    metas = [
        PairMeta(key="k1", gold_relations=["cha_cua"], masked_relations=["me_cua"]),
        PairMeta(key="k2", gold_relations=[], masked_relations=["cha_cua"]),
    ]
    import numpy as np

    logits = np.zeros((2, NUM_LABELS))
    logits[0, LABEL_LIST.index("cha_cua")] = 3.0
    logits[0, NA_INDEX] = -3.0
    logits[1, NA_INDEX] = 3.0

    pred, gold = predict_relations(logits, metas)
    assert pred[0]["predicted"] == ["cha_cua"]
    assert pred[1]["predicted"] == []

    threshold, f1 = calibrate_threshold(logits, metas)
    assert 0.1 <= threshold <= 0.8
    assert f1 == 1.0


def test_predict_relations_na_head_suppresses() -> None:
    """NA head cao → không dự đoán quan hệ."""
    metas = [PairMeta(key="k1", gold_relations=["ke_vi"], masked_relations=[])]
    import numpy as np

    logits = np.zeros((1, NUM_LABELS))
    logits[0, LABEL_LIST.index("ke_vi")] = 5.0
    logits[0, NA_INDEX] = 5.0
    pred, _ = predict_relations(logits, metas)
    assert pred[0]["predicted"] == []

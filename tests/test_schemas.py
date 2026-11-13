"""Test cho hợp đồng dữ liệu dùng chung (`src/common/schemas.py`).

Test kiểm tra **contract** (đúng tập quan hệ, đúng format ID, đủ bằng chứng),
không chỉ kiểm tra "không crash".
"""

from __future__ import annotations

import pytest

from src.common.schemas import (
    EXTRACTION_METHODS,
    NER_LABELS,
    NODE_TYPES,
    RELATION_TYPES,
    SYMMETRIC_RELATIONS,
    Entity,
    Mention,
    Triple,
    normalize_orientation,
)


def test_relation_types_doi_dung_18_quan_he() -> None:
    """Schema đóng: đúng 18 quan hệ, đúng tên đã chốt ở docs/CONTEXT.md §2.5."""
    expected = {
        "cha_cua",
        "me_cua",
        "vo_cua",
        "chong_cua",
        "anh_em_cua",
        "thuoc_trieu_dai",
        "ke_vi",
        "giu_chuc_vu",
        "lap_ra",
        "chi_huy_tran",
        "tham_gia_tran",
        "danh_bai",
        "dien_ra_tai",
        "sinh_tai",
        "mat_tai",
        "sinh_nam",
        "mat_nam",
        "dong_doi_tai",
    }
    assert RELATION_TYPES == expected
    assert len(RELATION_TYPES) == 18


def test_ner_labels_doi_dung_6_nhan() -> None:
    """6 nhãn NER đúng thứ tự đã chốt."""
    assert NER_LABELS == ("PERSON", "DYNASTY", "EVENT", "LOCATION", "TIME", "TITLE")


def test_extraction_methods_doi_dung_5_phuong_phap() -> None:
    """5 phương pháp trích xuất đúng thứ tự đã chốt."""
    assert EXTRACTION_METHODS == {
        "infobox",
        "distant_supervision",
        "phobert_re",
        "llm",
        "rule",
    }


def test_node_types_doi_dung_7_loai() -> None:
    """7 loại node đúng thứ tự đã chốt."""
    assert NODE_TYPES == {
        "person",
        "dynasty",
        "event",
        "place",
        "title",
        "year",
        "article",
    }


def test_symmetric_relations_doi_dung_2() -> None:
    """Chỉ 2 quan hệ đối xứng: anh_em_cua và tham_gia_tran."""
    assert SYMMETRIC_RELATIONS == {"anh_em_cua", "tham_gia_tran"}


def _valid_triple() -> Triple:
    """Tạo một triple hợp lệ để dùng chung cho các test."""
    return Triple(
        doc_id="doc_12345",
        sentence_id="s12345_0_3",
        subject="ent_le_loi_1a2b3c4d",
        relation="cha_cua",
        object="ent_le_khanh_du_9f8e7d6c",
        evidence_sentence="Lê Lợi là con của Lê Khánh Dư.",
        source_url="https://vi.wikipedia.org/wiki/Lê_Lợi",
        doc_title="Lê Lợi",
        confidence=0.97,
        method="infobox",
    )


def test_triple_hop_le() -> None:
    """Triple đủ trường bắt buộc là hợp lệ."""
    assert _valid_triple().is_valid() is True


@pytest.mark.parametrize(
    "field, value",
    [
        ("evidence_sentence", ""),
        ("source_url", ""),
        ("relation", "quan_he_khong_co_trong_schema"),
        ("method", "khong_hop_le"),
        ("confidence", 1.5),
        ("confidence", -0.1),
        ("subject", ""),
        ("object", ""),
    ],
)
def test_triple_thieu_bang_chung_hoac_sai_contract(field: str, value: object) -> None:
    """Thiếu bằng chứng hoặc sai contract → triple không hợp lệ."""
    triple = _valid_triple()
    setattr(triple, field, value)
    assert triple.is_valid() is False


def test_triple_luong_trong_bang_chung() -> None:
    """Subject và object giống nhau → loại (self-loop)."""
    triple = _valid_triple()
    triple.object = triple.subject
    assert triple.is_valid() is False


def test_triple_to_dict_giu_dung_ten_truong() -> None:
    """Dict đầu ra giữ đúng tên trường theo data-contracts."""
    data = _valid_triple().to_dict()
    for key in (
        "doc_id",
        "sentence_id",
        "subject",
        "relation",
        "object",
        "evidence_sentence",
        "source_url",
        "doc_title",
        "confidence",
        "method",
        "start_year",
        "end_year",
        "alt_evidence",
    ):
        assert key in data
    assert isinstance(data["confidence"], float)
    assert data["alt_evidence"] == []


def test_normalize_orientation_cho_quan_he_doi_xung() -> None:
    """Quan hệ đối xứng được sắp xếp lại theo thứ tự lexicographic."""
    subject, object_id, relation = normalize_orientation(
        "ent_b_11111111", "ent_a_22222222", "anh_em_cua"
    )
    assert subject == "ent_a_22222222"
    assert object_id == "ent_b_11111111"
    assert relation == "anh_em_cua"


def test_normalize_orientation_giu_nguyen_quan_he_khong_doi_xung() -> None:
    """Quan hệ có hướng giữ nguyên thứ tự."""
    subject, object_id, _relation = normalize_orientation(
        "ent_b_11111111", "ent_a_22222222", "cha_cua"
    )
    assert subject == "ent_b_11111111"
    assert object_id == "ent_a_22222222"


def test_mention_valid() -> None:
    """Mention hợp lệ: span không rỗng, offset đúng, nhãn thuộc tập."""
    mention = Mention(
        mention_id="ms12345_0_3_0",
        start=0,
        end=7,
        text="Lê Lợi",
        label="PERSON",
    )
    assert mention.is_valid() is True


def test_mention_invalid_khi_label_sai() -> None:
    """Nhãn ngoài tập 6 nhãn → không hợp lệ."""
    mention = Mention(
        mention_id="ms12345_0_3_0",
        start=0,
        end=7,
        text="Lê Lợi",
        label="KHONG_TON_TAI",
    )
    assert mention.is_valid() is False


def test_entity_valid() -> None:
    """Entity hợp lệ khi có tên, loại và nguồn đúng."""
    entity = Entity(
        entity_id="ent_le_loi_1a2b3c4d",
        name="Lê Lợi",
        name_normalized="le loi",
        type="person",
    )
    assert entity.is_valid() is True


def test_entity_invalid_khi_type_sai() -> None:
    """Loại node ngoài 7 loại → không hợp lệ."""
    entity = Entity(
        entity_id="ent_le_loi_1a2b3c4d",
        name="Lê Lợi",
        name_normalized="le loi",
        type="con_nguoi_khong_co",
    )
    assert entity.is_valid() is False

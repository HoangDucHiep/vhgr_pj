"""Regression test cho các lỗi người dùng báo lúc demo (Phase 13).

Ngày phát hiện: 16–17/11/2026 (demo + đối chiếu dữ liệu thật).

12 ca lỗi thật được mã hoá thành test để **chống tái phát**:

| # | Lỗi người dùng báo | Nguyên nhân gốc |
|---|---|---|
| 1 | "Cho tôi chi tiết 17 đời vua triều Lê" → map `tiết`→Tiết, `đời`→Đổi | alias 1 từ / cụm thường |
| 2 | "Triều Lê có bao nhiêu đời vua" → map `bao`→Bảo, `đời`→Đổi | alias 1 từ |
| 3 | `"Đổi mới đất nước"` khớp entity "Đổi Mới" | lớp giữ dấu không kiểm chữ hoa |
| 4 | `"Ông ấy"` khớp George H. W. Bush | coref gom đại từ làm tên entity |
| 5 | "Ai là con của Trần Nhân Tông" không ra | quan hệ lưu chiều `cha_cua` |
| 6 | "diễn biến trận Bạch Đằng 1288" kéo nhầm section | retriever (Phase 14) |
| 7 | "Trần Hưng Đạo mất tại Quốc lộ 14" | cạnh nhiễu KG |
| 8 | "Nhà Trần có bao nhiêu đời vua" | đếm sai (`thuoc_trieu_dai` ≠ là vua) |
| 9 | "Vị vua đó mất năm nào" → link sai | đại từ chưa xử lý |
| 10 | "Le Loi" (không dấu) không khớp | lớp bỏ dấu dự phòng |
| 11 | "Nguyễn Huệ chỉ huy" → khớp "Nguyễn Huệ Chi" | bỏ dấu làm trùng |
| 12 | "Trận Bạch Đằng" năm 1288 vs 938 | cần phân biệt entity theo năm |

Các test dùng **artifact thật** (`data/knowledge_base/entities.jsonl`) khi có,
nếu không thì bỏ qua (`pytest.skip`) để repo vẫn test được khi thiếu dữ liệu.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.services.cypher_validator import has_filtering_predicate
from backend.app.services.entity_linker import EntityLinker
from src.common.config import REPO_ROOT
from src.graph.noise_filter import (
    filter_noisy_edges,
    filter_noisy_records,
    is_infrastructure,
    is_noisy_edge,
)

ENTITIES_PATH = REPO_ROOT / "data" / "knowledge_base" / "entities.jsonl"


@pytest.fixture(scope="module")
def real_linker() -> EntityLinker:
    """Linker nạp từ artifact entity thật (nếu có).

    Returns:
        `EntityLinker` đã nạp.
    """
    if not ENTITIES_PATH.exists():
        pytest.skip("Thiếu artifact data/knowledge_base/entities.jsonl")
    return EntityLinker(ENTITIES_PATH)


def _ids(linked: list[tuple[str, str, str]]) -> set[str]:
    """Trích tập `entity_id` từ kết quả link.

    Args:
        linked: Kết quả `EntityLinker.link`.

    Returns:
        Tập `entity_id`.
    """
    return {entity_id for _, entity_id, _ in linked}


# ---------------------------------------------------------------- ca 1 & 2 ---
def test_case01_no_noise_single_word_alias(real_linker: EntityLinker) -> None:
    """Ca 1: "17 đời vua triều Lê" không được khớp `tiết`/`đời`.

    Trước Phase 13: "tiết" → "Tiết", "đời" → "Đổi".
    """
    linked = real_linker.link("Cho tôi chi tiết 17 đời vua triều Lê")
    assert _ids(linked) == {"ent_nha_le_so_31dcb842"}


def test_case02_count_question_no_noise_alias(real_linker: EntityLinker) -> None:
    """Ca 2: "Triều Lê có bao nhiêu đời vua" không được khớp `bao`/`đời`."""
    linked = real_linker.link("Triều Lê có bao nhiêu đời vua?")
    assert _ids(linked) == {"ent_nha_le_so_31dcb842"}


# ------------------------------------------------------------------- ca 3 ---
def test_case03_exact_case_blocks_false_positive(real_linker: EntityLinker) -> None:
    """Ca 3: "Đổi mới đất nước" KHÔNG được khớp entity "Đổi Mới"."""
    linked = real_linker.link("Đổi mới đất nước")
    assert "ent_doi_moi_1b2ad4f7" not in _ids(linked)
    assert linked == []


# ------------------------------------------------------------------- ca 4 ---
def test_case04_pronoun_not_linked_to_person(real_linker: EntityLinker) -> None:
    """Ca 4: "Ông ấy" KHÔNG được khớp George H. W. Bush."""
    linked = real_linker.link("Ông ấy mất năm nào?")
    assert "ent_george_h_5df82ed5" not in _ids(linked)
    assert linked == []


def test_case04b_demonstrative_not_linked(real_linker: EntityLinker) -> None:
    """Ca 9: "Vị vua đó" (đại từ chỉ định) không được link."""
    linked = real_linker.link("Vị vua đó mất năm nào?")
    assert linked == []


# ------------------------------------------------------------------- ca 5 ---
def test_case05_inverse_relation_subject_found(real_linker: EntityLinker) -> None:
    """Ca 5: "Ai là con của Trần Nhân Tông" phải link được chủ thề.

    Việc đảo chiều Cypher kiểm ở `test_inverse_cypher_returns_children`.
    """
    linked = real_linker.link("Ai là con của Trần Nhân Tông")
    assert "ent_tran_nhan_tong_cc430bcd" in _ids(linked)


# ------------------------------------------------------------------- ca 6 ---
def test_case06_bach_dang_event_disambiguated(real_linker: EntityLinker) -> None:
    """Ca 6 & 12: "trận Bạch Đằng 1288" phải về đúng entity của năm 1288."""
    linked = real_linker.link("diễn biến trận Bạch Đằng 1288")
    assert "ent_tran_bach_dang_1288_b5bf70a3" in _ids(linked)


# ------------------------------------------------------------------- ca 7 ---
def test_case07_infrastructure_place_is_noisy() -> None:
    """Ca 7: "Quốc lộ 14" là hạ tầng ⇒ cạnh `mat_tai` tới nó là nhiễu."""
    assert is_infrastructure("Quốc lộ 14") is True
    assert is_noisy_edge("mat_tai", "Quốc lộ 14", object_type="Place") is True
    assert is_noisy_edge("sinh_tai", "Quốc lộ 14", object_type="Place") is True


def test_case07b_valid_places_are_not_noisy() -> None:
    """Ca 7b: địa danh lịch sử hợp lệ KHÔNG bị loại."""
    for name in ("Trường An", "Đường Lâm", "Hà Nội", "Thăng Long", "Nghệ An"):
        assert is_noisy_edge("sinh_tai", name, object_type="Place") is False
    # Cạnh không có object là địa danh ⇒ không bao giờ là nhiễu.
    assert is_noisy_edge("cha_cua", "Quốc lộ 14", object_type="Place") is False


def test_case07c_filter_removes_noisy_edges() -> None:
    """Ca 7c: bộ lọc cạnh loại đúng cạnh nhiễu, giữ nguyên cạnh sạch.

    "Vạn Kiếp" là địa danh lịch sử **hợp lệ** (Trần Hưng Đạo mất ở Vạn Kiếp) ⇒
    phải được giữ. "Quốc lộ 14" là hạ tầng ⇒ phải bị loại.
    """
    edges = [
        {"relation": "mat_tai", "target_name": "Quốc lộ 14"},
        {"relation": "mat_tai", "target_name": "Vạn Kiếp"},
        {"relation": "mat_tai", "target_name": "Thăng Long"},
        {"relation": "chi_huy_tran", "target_name": "Quốc lộ 14"},
    ]
    kept = filter_noisy_edges(edges)
    assert len(kept) == 3
    assert {edge["target_name"] for edge in kept} == {
        "Vạn Kiếp", "Thăng Long", "Quốc lộ 14",
    }
    assert all(
        edge["target_name"] != "Quốc lộ 14"
        for edge in kept
        if edge["relation"] == "mat_tai"
    )


def test_case07d_filter_records() -> None:
    """Ca 7d: bộ lọc record loại record nhiễu, giữ record sạch."""
    records = [
        {"relation": "mat_tai", "object": "Quốc lộ 14"},
        {"relation": "mat_tai", "object": "Thăng Long"},
        {"name": "Trần Hưng Đạo"},
    ]
    kept = filter_noisy_records(records)
    assert len(kept) == 2


# ------------------------------------------------------------------- ca 8 ---
def test_case08_dynasty_count_uses_reign_start(real_linker: EntityLinker) -> None:
    """Ca 8: "Nhà Trần" link đúng dynasty (đếm chính xác nằm ở prompt)."""
    linked = real_linker.link("Nhà Trần có bao nhiêu đời vua?")
    assert "ent_nha_tran_756be166" in _ids(linked)


# ------------------------------------------------------------------ ca 10 ---
def test_case10_nodiacritic_fallback_still_works(real_linker: EntityLinker) -> None:
    """Ca 10: câu không dấu vẫn khớp được (lớp dự phòng bỏ dấu)."""
    linked = real_linker.link("Le Loi sinh nam nao")
    assert "ent_le_thai_to_cb04bc38" in _ids(linked)


# ------------------------------------------------------------------ ca 11 ---
def test_case11_diacritic_preferred_over_nodiacritic(
    real_linker: EntityLinker,
) -> None:
    """Ca 11: "Nguyễn Huệ chỉ huy" → Quang Trung, KHÔNG phải Nguyễn Huệ Chi."""
    linked = real_linker.link("Nguyễn Huệ chỉ huy trận nào")
    ids = _ids(linked)
    assert "ent_quang_trung_242ef52d" in ids
    assert "ent_nguyen_hue_chi_cccccccc" not in ids


# ------------------------------------------------------------ ca 5 (Cypher) ---
@pytest.mark.integration
def test_inverse_cypher_returns_children() -> None:
    """Ca 5 (kiểm chứng DB): Cypher đảo chiều trả về 5 con của Trần Nhân Tông."""
    from backend.app.services import neo4j_client

    try:
        rows = neo4j_client.run_read_query(
            """
            MATCH (p:Person {entity_id: 'ent_tran_nhan_tong_cc430bcd'})
            <-[:cha_cua|me_cua]-(c:Person)
            RETURN c.name AS child
            LIMIT 50
            """
        )
    except Exception as exc:  # noqa: BLE001 - Neo4j không chạy ⇒ bỏ qua
        pytest.skip(f"Không kết nối được Neo4j: {exc}")
    names = {str(row.get("child")) for row in rows}
    assert len(names) == 5
    assert "Trần Anh Tông" in names


# -------------------------------------------------------- chỉ mục alias sạch ---
def test_no_all_lowercase_multiword_alias_in_index(real_linker: EntityLinker) -> None:
    """Không còn alias ≥ 2 từ **toàn chữ thường** trong chỉ mục link.

    Trước Phase 13 có 176 alias dạng này ("chiến thắng", "triều đại",
    "phong kiến"…) — chúng là cụm từ thường, không phải tên riêng.
    """
    offenders: list[str] = []
    for alias in real_linker.alias_to_ids:
        displays = real_linker.alias_display.get(alias) or set()
        if not displays:
            continue
        if len(alias.split()) < 2:
            continue
        if all(display == display.lower() for display in displays):
            offenders.append(alias)
    assert offenders == []


def test_pronoun_aliases_removed_from_index(real_linker: EntityLinker) -> None:
    """Alias đại từ ("ông ấy") không còn trong chỉ mục."""
    assert "ong ay" not in real_linker.alias_to_ids
    assert "ong ta" not in real_linker.alias_to_ids


def test_true_positives_preserved(real_linker: EntityLinker) -> None:
    """Các bề mặt có dấu đúng vẫn link được sau khi siết chữ hoa."""
    cases = {
        "Trần Hưng Đạo chỉ huy trận nào?": "ent_tran_hung_dao_b1385c3d",
        "Ai là cha của Nguyễn Huệ?": "ent_quang_trung_242ef52d",
        "Trận Bạch Đằng diễn ra năm nào?": "ent_tran_bach_dang_1288_b5bf70a3",
    }
    for question, expected in cases.items():
        assert expected in _ids(real_linker.link(question)), question


def test_linker_fixture_unit_still_passes(tmp_path: Path) -> None:
    """Bản unit cũ (fixture tối giản) vẫn phải chạy được.

    Bảo đảm thay đổi Phase 13 không phá vỡ hành vi nền của entity linker.
    """
    entities = [
        {
            "entity_id": "ent_le_loi_aaaaaaaa",
            "name": "Lê Lợi",
            "name_normalized": "le loi",
            "type": "person",
            "aliases": [{"alias": "Lê Thái Tổ", "type": "temple"}],
            "wikidata_qid": "Q1234",
        },
        {
            "entity_id": "ent_nguyen_hue_bbbbbbbb",
            "name": "Quang Trung",
            "name_normalized": "quang trung",
            "type": "person",
            "aliases": [{"alias": "Nguyễn Huệ", "type": "other"}],
            "wikidata_qid": "Q379775",
        },
    ]
    path = tmp_path / "entities.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for entity in entities:
            handle.write(json.dumps(entity, ensure_ascii=False) + "\n")
    linker = EntityLinker(path)
    assert linker.link("Lê Lợi sinh năm nào?")[0][1] == "ent_le_loi_aaaaaaaa"
    assert linker.link("Lê Thái Tổ là ai?")[0][1] == "ent_le_loi_aaaaaaaa"
    # Không dấu → lớp dự phòng bỏ dấu.
    assert linker.link("Le Loi sinh nam nao")[0][1] == "ent_le_loi_aaaaaaaa"


# ------------------------------------------------- guard Cypher không lọc ---
@pytest.mark.parametrize(
    ("cypher", "expected"),
    [
        ("MATCH (p:Person) RETURN p.name AS name LIMIT 10", False),
        (
            "MATCH (p:Person) WHERE p.death_year IS NOT NULL "
            "RETURN p.name AS name LIMIT 10",
            False,
        ),
        (
            "MATCH (p:Person) WHERE p.reign_start IS NOT NULL "
            "AND p.death_year IS NOT NULL RETURN p.name LIMIT 50",
            False,
        ),
        ("MATCH (p:Person {entity_id: 'ent_x'}) RETURN p.name", True),
        (
            "MATCH (p:Person) WHERE p.birth_year > 1900 RETURN p.name LIMIT 10",
            True,
        ),
        (
            "MATCH (p:Person) WHERE p.name_normalized = 'nha tran' "
            "RETURN p.name",
            True,
        ),
        (
            "MATCH (p:Person)-[:giu_chuc_vu]->(t:Title) "
            "WHERE t.name_normalized CONTAINS 'tuong' RETURN p.name",
            True,
        ),
        ("MATCH (p:Person) RETURN COUNT(p) AS total LIMIT 1", True),
    ],
)
def test_filtering_predicate_detector(cypher: str, expected: bool) -> None:
    """Bộ dò điều kiện lọc: phải lọc theo **giá trị cụ thể**.

    `IS NOT NULL` không đủ — nó chỉ lọc "có giá trị", không định danh được
    đối tượng ⇒ vẫn quét toàn đồ thị.
    """
    assert has_filtering_predicate(cypher) is expected

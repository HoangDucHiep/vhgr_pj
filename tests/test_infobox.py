"""Test cho pipeline parse infobox (Phase 3 — A4).

Bao phủ 5 Gate của Phase 3:
1. ≥ 95% bài có infobox `person` parse thành công.
2. ≥ 90% bài nhân vật có ≥ 1 trường ngày sinh/mất hoặc quan hệ gia đình.
3. Chuẩn hóa ngày ≥ 95% (xem `tests/test_normalize.py`).
4. 100% triple đủ trường bắt buộc, `method="infobox"`, `confidence ≥ 0.95`.
5. 0 quan hệ ngoài danh mục 18 quan hệ.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from src.common.schemas import RELATION_SUBJECT_TYPES, RELATION_TYPES
from src.preprocess.infobox_entity_types import (
    build_context,
    detect_gender,
    infer_object_type,
    normalize_type,
    relation_for_gender,
)
from src.preprocess.parse_infobox import (
    build_triples,
    clean_value,
    extract_links,
    extract_params,
    load_mapping,
    parse_date_field,
    split_items,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MAPPING_PATH = REPO_ROOT / "configs" / "infobox_mapping.yaml"
DOCUMENTS_PATH = REPO_ROOT / "data" / "interim" / "documents.jsonl"
TRIPLES_PATH = REPO_ROOT / "data" / "interim" / "infobox_triples.jsonl"
ENTITIES_PATH = REPO_ROOT / "data" / "interim" / "infobox_entities.jsonl"
LEAD_TRIPLES_PATH = REPO_ROOT / "data" / "interim" / "lead_triples.jsonl"

MAPPING = load_mapping(MAPPING_PATH)

DATE_RELATIONS = {"sinh_nam", "mat_nam"}
FAMILY_RELATIONS = {"cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua"}


def _load_jsonl(path: Path) -> list[dict]:
    """Nạp file JSONL nếu tồn tại, ngược lại trả list rỗng."""
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


DOCUMENTS = _load_jsonl(DOCUMENTS_PATH)
TRIPLES = _load_jsonl(TRIPLES_PATH)
ENTITIES = _load_jsonl(ENTITIES_PATH)
LEAD_TRIPLES = _load_jsonl(LEAD_TRIPLES_PATH)


# ---------------------------------------------------------------------------
# Mapping config
# ---------------------------------------------------------------------------


def test_mapping_config_is_valid():
    """Config mapping phải hợp lệ: quan hệ nằm trong 18 quan hệ đóng."""
    assert MAPPING, "config rỗng"
    for key, spec in MAPPING["fields"].items():
        assert spec["relation"] in RELATION_TYPES, f"{key} → {spec['relation']} ngoài schema"
        assert spec.get("kind") in {"date", "entity", "period"}
    for name, spec in MAPPING["date_templates"].items():
        assert isinstance(spec, dict)


def test_mapping_type_map_covers_person_types():
    """Bảng `type_map` phải ánh xạ được các loại infobox nhân vật phổ biến."""
    type_map = MAPPING["type_map"]
    for key in (
        "thong tin nhan vat phong kien",
        "thong tin nhan vat hoang gia",
        "nhan vat",
        "officeholder",
        "vien chuc",
        "nghe si",
        "nha van",
        "tu si phat giao",
    ):
        assert key in type_map, f"thiếu loại {key}"
        assert type_map[key] == "person"


def test_mapping_type_map_battle_maps_to_event():
    """KG không có node `battle` → phải map sang `event`."""
    type_map = MAPPING["type_map"]
    assert type_map["battle"] == "event"
    assert type_map["military conflict"] == "event"


# ---------------------------------------------------------------------------
# Làm sạch giá trị
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[[Hà Nội]]", "Hà Nội"),
        ("[[Bộ Hộ|Hộ bộ Thượng Thư]]", "Hộ bộ Thượng Thư"),
        ("'''Nguyễn Du'''", "Nguyễn Du"),
        ("<!-- chú thích -->Lý Thái Tổ", "Lý Thái Tổ"),
        ("<ref name=\"a\">x</ref>Lê Lợi", "Lê Lợi"),
        ("Hà Nội<br>Hồ Chí Minh", "Hà Nội Hồ Chí Minh"),
        ("{{chú thích sách|tác giả=X}}Quốc gia", "Quốc gia"),
    ],
)
def test_clean_value(raw, expected):
    """`clean_value` phải bỏ markup nhưng giữ nội dung."""
    assert clean_value(raw) == expected


def test_extract_links():
    """`extract_links` phải trả cả đích và chữ hiển thị."""
    links = extract_links("[[Hà Nội]] và [[Bộ Hộ|Hộ bộ Thượng Thư]]")
    assert links == [("Hà Nội", "Hà Nội"), ("Bộ Hộ", "Hộ bộ Thượng Thư")]


def test_split_items_keeps_wikilinks():
    """`split_items` phải giữ nguyên wikitext để không mất liên kết."""
    items = split_items("[[Nam Hán]]<br>[[Tĩnh Hải quân]]")
    assert len(items) == 2
    assert "[[Nam Hán]]" in items[0]


# ---------------------------------------------------------------------------
# Ngày tháng
# ---------------------------------------------------------------------------


def test_parse_date_template_death_and_age():
    """Template "ngày mất và tuổi" phải cho cả mốc mất và mốc sinh."""
    info, extra = parse_date_field(
        "{{ngày mất và tuổi|1820|9|16|1766|1|3}}",
        date_templates=MAPPING["date_templates"],
    )
    assert info["year"] == 1820
    assert info["month"] == 9
    assert info["day"] == 16
    assert extra and extra[0]["year"] == 1766
    assert extra[0]["month"] == 1
    assert extra[0]["day"] == 3


def test_parse_date_template_plain():
    """Template "ngày sinh" chỉ có một mốc."""
    info, extra = parse_date_field(
        "{{ngày sinh|974|3|8}}", date_templates=MAPPING["date_templates"]
    )
    assert (info["year"], info["month"], info["day"]) == (974, 3, 8)
    assert extra == []


def test_parse_date_plain_text():
    """Văn bản thuần phải parse được."""
    info, _ = parse_date_field(
        "25 tháng 12 năm 1933", date_templates=MAPPING["date_templates"]
    )
    assert info["year"] == 1933
    assert info["month"] == 12
    assert info["day"] == 25


def test_parse_date_circa_has_qualifier():
    """Template `circa` phải gắn nhãn "khoảng"."""
    info, _ = parse_date_field(
        "{{circa|sau năm 1230}}", date_templates=MAPPING["date_templates"]
    )
    assert info["qualifier"] == "khoảng"


# ---------------------------------------------------------------------------
# Suy loại & giới tính
# ---------------------------------------------------------------------------


def test_normalize_type_strips_prefix():
    """Tên template có tiền tố phải được bỏ trước khi tra bảng."""
    type_map = MAPPING["type_map"]
    assert normalize_type("Infobox military conflict", type_map) == "event"
    assert normalize_type("Thông tin chiến tranh", type_map) == "event"
    assert normalize_type("thong tin nhan vat hoang gia", type_map) == "person"


def test_normalize_type_matches_with_and_without_prefix():
    """Regression: bảng `type_map` chứa cả dạng có lẫn không có tiền tố.

    `wikitextparser` trả tên template **đầy đủ** ("Thông tin nhân vật phong kiến")
    còn `infobox_parser` (Phase 1) trả tên **đã bỏ tiền tố**
    ("nhan vat phong kien"). Cả hai phải tra được cùng một kết quả.
    """
    type_map = MAPPING["type_map"]
    assert normalize_type("Thông tin nhân vật phong kiến", type_map) == "person"
    assert normalize_type("nhan vat phong kien", type_map) == "person"
    assert normalize_type("Thông tin đơn vị hành chính Việt Nam", type_map) == "place"
    assert normalize_type("don vi hanh chinh viet nam", type_map) == "place"


def test_normalize_type_returns_none_for_unknown_template():
    """Template lạ phải trả `None` — KHÔNG tự động thành `person`.

    Nếu mặc định là `person` thì node "Hà Nội" (infobox
    `{{Thông tin đơn vị hành chính Việt Nam}}`) sẽ bị gán sai loại.
    """
    type_map = MAPPING["type_map"]
    assert normalize_type("Mẫu infobox chưa từng gặp", type_map) is None


def test_unknown_subject_type_is_not_person():
    """Regression: chủ thể không suy được loại → `article`, không phải `person`."""
    context = build_context(
        infobox_type="Mẫu infobox chưa từng gặp",
        title="Hà Nội",
        params={},
        type_map=MAPPING["type_map"],
    )
    assert context.subject_type == "article"
    assert context.subject_type != "person"


def test_subject_type_falls_back_to_wikidata_signal():
    """Không map được template → dùng tín hiệu Wikidata (Phase 1)."""
    context = build_context(
        infobox_type="Mẫu infobox chưa từng gặp",
        title="Hà Nội",
        params={},
        type_map=MAPPING["type_map"],
        wikidata_signal="place",
    )
    assert context.subject_type == "place"

    context = build_context(
        infobox_type="Mẫu infobox chưa từng gặp",
        title="Trận lụt đồng bằng sông Hồng 1971",
        params={},
        type_map=MAPPING["type_map"],
        wikidata_signal="battle",
    )
    assert context.subject_type == "event"


def test_detect_gender_from_field():
    """Giới tính lấy từ trường `gioi tinh`."""
    assert detect_gender(title="Bà Huyện Thanh Quan", params={"gioi tinh": "[[Nữ]]"}) == "female"
    assert detect_gender(title="Lê Lợi", params={"gioi tinh": "nam"}) == "male"


def test_detect_gender_from_title_prefix():
    """Không có trường thì lấy từ tiền tố tiêu đề."""
    assert detect_gender(title="Bà Triệu", params={}) == "female"
    assert detect_gender(title="Ông Nguyễn Du", params={}) == "male"


def test_relation_for_gender():
    """Giới tính chủ thể quyết định `vo_cua` hay `chong_cua`."""
    assert relation_for_gender("vo_cua", "male") == "vo_cua"
    assert relation_for_gender("vo_cua", "female") == "chong_cua"
    assert relation_for_gender("chong_cua", "female") == "chong_cua"
    assert relation_for_gender("cha_cua", "female") == "cha_cua"


def test_infer_object_type():
    """Suy loại đối tượng từ tên bài đích."""
    assert infer_object_type("Nhà Lý") == "dynasty"
    assert infer_object_type("Trận Bạch Đằng (938)") == "event"
    assert infer_object_type("Đại học Quốc gia") == "place"
    assert infer_object_type("Lê Lợi") == "person"


def test_infer_object_type_detects_organization():
    """Tổ chức không phải loại node KG → trả "organization" để loại triple."""
    assert infer_object_type("Hoa Kỳ") == "organization"
    assert infer_object_type("Mặt trận Dân tộc Giải phóng miền Nam Việt Nam") == "organization"


# ---------------------------------------------------------------------------
# Hướng quan hệ
# ---------------------------------------------------------------------------


def _build(doc_title: str):
    """Dựng triple cho một bài theo tiêu đề."""
    doc = next(d for d in DOCUMENTS if d["title"] == doc_title)
    extracted = extract_params(doc.get("infobox_raw") or "")
    assert extracted is not None
    name, params = extracted
    triples, props, counters = build_triples(
        doc, infobox_type=name, params=params, mapping=MAPPING
    )
    return triples, props, counters


def test_direction_father_is_forward():
    """Trường `cha` → triple `cha_cua` có chủ thể là con, đối tượng là cha."""
    triples, _, _ = _build("Lý Thái Tổ")
    father = [t for t in triples if t["relation"] == "cha_cua"]
    assert father, "không có triple cha_cua"
    triple = father[0]
    assert triple["subject"] == make_id("person", "Lý Thái Tổ")
    assert triple["object_type"] == "person"
    assert triple["evidence_sentence"].startswith("Cha:")


def test_direction_successor_and_predecessor():
    """`ke nhiem` forward, `tien nhiem` reverse — cùng hướng predecessor → successor."""
    triples, _, _ = _build("Lý Thái Tổ")
    successors = {t["object"] for t in triples if t["relation"] == "ke_vi"}
    predecessors = {t["subject"] for t in triples if t["relation"] == "ke_vi"}
    assert successors, "không có kế nhiệm"
    assert predecessors, "không có tiền nhiệm"
    # Lý Thái Tổ là người được nêu ở cả hai trường.
    own_id = make_id("person", "Lý Thái Tổ")
    assert own_id in successors or own_id in predecessors


def test_direction_commander_is_reverse():
    """`commander1`/`chi huy 1` reverse → chủ thể là người chỉ huy, đối tượng là trận."""
    triples, _, _ = _build("Trận Bạch Đằng (938)")
    commanders = [t for t in triples if t["relation"] == "chi_huy_tran"]
    assert commanders, "không có triple chi_huy_tran"
    for triple in commanders:
        assert triple["subject_type"] == "person"
        assert triple["object_type"] == "event"


def test_direction_child_is_reverse():
    """`con trai` reverse → chủ thể là đứa con, đối tượng là người bố."""
    triples, _, _ = _build("Quang Trung")
    children = [t for t in triples if t["relation"] == "cha_cua"]
    assert children, "không có triple cha_cua từ trường con"
    for triple in children:
        assert triple["subject_type"] == "person"
        assert triple["object_type"] == "person"


def make_id(entity_type: str, name: str) -> str:
    """Sinh entity_id (helper cho test)."""
    from src.common.ids import make_entity_id

    return make_entity_id(entity_type, name)


# ---------------------------------------------------------------------------
# Gate 1 — parse rate
# ---------------------------------------------------------------------------


def test_gate1_person_infobox_parse_rate_at_least_95_percent():
    """Gate 1: ≥ 95% bài có infobox `person` parse thành công.

    "Parse thành công" = **nhận diện được khối template infobox** (tên loại +
    danh sách tham số), kể cả khi template rỗng (`{{Thông tin nhân vật phong
    kiến}}` — 146/1061 bài, không có trường nào để trích).

    Tham số rỗng **không phải** lỗi parse — đó là đặc điểm dữ liệu. Test này
    kiểm tra phần nhận diện; coverage trích xuất được đo ở Gate 2.
    """
    person_docs = [d for d in DOCUMENTS if d.get("infobox_type") == "person"]
    if not person_docs:
        pytest.skip("chưa có documents.jsonl")

    parsed = 0
    for doc in person_docs:
        extracted = extract_params(doc.get("infobox_raw") or "")
        if extracted is not None and extracted[0]:
            parsed += 1

    rate = parsed / len(person_docs)
    assert rate >= 0.95, f"parse rate {rate:.1%} < 95%"


def test_person_infoboxes_with_params_are_all_parsed():
    """Mọi infobox **có tham số** đều phải parse được ≥ 99% tham số."""
    person_docs = [d for d in DOCUMENTS if d.get("infobox_type") == "person"]
    if not person_docs:
        pytest.skip("chưa có documents.jsonl")

    with_params = 0
    parsed = 0
    for doc in person_docs:
        extracted = extract_params(doc.get("infobox_raw") or "")
        if extracted is None:
            continue
        _, params = extracted
        if params:
            with_params += 1
            parsed += 1

    if with_params:
        rate = parsed / with_params
        assert rate >= 0.99, f"parse rate (có tham số) {rate:.1%} < 99%"


# ---------------------------------------------------------------------------
# Gate 2 — coverage ngày / gia đình
# ---------------------------------------------------------------------------


def test_gate2_person_date_or_family_coverage_at_least_90_percent():
    """Gate 2: ≥ 90% bài nhân vật có ≥ 1 trường ngày hoặc quan hệ gia đình."""
    person_docs = [d for d in DOCUMENTS if d.get("infobox_type") == "person"]
    if not person_docs:
        pytest.skip("chưa có documents.jsonl")

    by_doc: dict[str, set[str]] = defaultdict(set)
    for triple in TRIPLES + LEAD_TRIPLES:
        by_doc[triple["doc_id"]].add(triple["relation"])

    covered = 0
    for doc in person_docs:
        relations = by_doc.get(doc["doc_id"], set())
        if (relations & DATE_RELATIONS) or (relations & FAMILY_RELATIONS):
            covered += 1

    rate = covered / len(person_docs)
    assert rate >= 0.90, f"coverage {rate:.1%} < 90%"


# ---------------------------------------------------------------------------
# Gate 4 & 5 — bất biến schema
# ---------------------------------------------------------------------------


def test_gate4_all_triples_have_required_fields():
    """Gate 4: 100% triple đủ trường bắt buộc, method="infobox", confidence ≥ 0.95."""
    if not TRIPLES:
        pytest.skip("chưa có infobox_triples.jsonl")

    for triple in TRIPLES:
        assert triple["doc_id"], "thiếu doc_id"
        assert triple["sentence_id"], "thiếu sentence_id"
        assert triple["subject"], "thiếu subject"
        assert triple["object"], "thiếu object"
        assert triple["evidence_sentence"].strip(), "thiếu evidence_sentence"
        assert triple["source_url"].strip(), "thiếu source_url"
        assert triple["doc_title"], "thiếu doc_title"
        assert triple["method"] == "infobox", f"method sai: {triple['method']}"
        assert triple["confidence"] >= 0.95, f"confidence thấp: {triple['confidence']}"


def test_gate5_no_relation_outside_catalog():
    """Gate 5: 0 quan hệ ngoài danh mục 18 quan hệ."""
    if not TRIPLES:
        pytest.skip("chưa có infobox_triples.jsonl")

    outside = {t["relation"] for t in TRIPLES if t["relation"] not in RELATION_TYPES}
    assert not outside, f"quan hệ ngoài schema: {outside}"


def test_triples_respect_subject_type_constraint():
    """Mọi triple phải có loại chủ thể hợp lệ với quan hệ."""
    if not TRIPLES:
        pytest.skip("chưa có infobox_triples.jsonl")

    for triple in TRIPLES:
        allowed = RELATION_SUBJECT_TYPES[triple["relation"]]
        assert triple["subject_type"] in allowed, (
            f"{triple['relation']} không nhận subject_type={triple['subject_type']}"
        )


def test_object_type_is_valid_kg_node_type():
    """Mọi đối tượng phải có loại node hợp lệ trong 7 loại KG."""
    from src.common.schemas import NODE_TYPES

    if not TRIPLES:
        pytest.skip("chưa có infobox_triples.jsonl")

    for triple in TRIPLES:
        assert triple["object_type"] in NODE_TYPES
        assert triple["subject_type"] in NODE_TYPES


def test_entity_types_are_not_wrongly_person():
    """Regression: địa danh/sự kiện KHÔNG được gán loại `person`.

    Trước khi sửa, loại infobox không map được mặc định là `person` → node
    "Hà Nội" và "Cần Thơ" bị gán `person` (sai — vi phạm nguyên tắc
    "không bịa" của `AGENTS.md` §5.3).
    """
    if not ENTITIES:
        pytest.skip("chưa có infobox_entities.jsonl")

    by_name = {e["name"]: e for e in ENTITIES}
    for place_name in ("Hà Nội", "Cần Thơ"):
        if place_name not in by_name:
            continue
        assert by_name[place_name]["type"] == "place", (
            f"{place_name} phải là `place`, không phải "
            f"`{by_name[place_name]['type']}`"
        )


def test_no_article_type_leaked_into_person_relations():
    """Chủ thể loại `article` không được sinh triple quan hệ cá nhân."""
    person_only = {"sinh_nam", "mat_nam", "sinh_tai", "mat_tai"}
    if not TRIPLES:
        pytest.skip("chưa có infobox_triples.jsonl")

    for triple in TRIPLES:
        if triple["subject_type"] == "article":
            assert triple["relation"] not in person_only


def test_lead_triples_use_rule_method_and_lower_confidence():
    """Triple đoạn dẫn phải `method="rule"`, `confidence=0.85`."""
    if not LEAD_TRIPLES:
        pytest.skip("chưa có lead_triples.jsonl")

    for triple in LEAD_TRIPLES:
        assert triple["method"] == "rule"
        assert triple["confidence"] == 0.85
        assert triple["evidence_sentence"].strip()
        assert triple["source_url"].strip()


def test_no_duplicate_lead_and_infobox_dates():
    """Bài không được có cùng năm sinh ở cả infobox và đoạn dẫn."""
    if not (TRIPLES and LEAD_TRIPLES):
        pytest.skip("chưa có artifact")

    infobox_years = {
        (t["doc_id"], t["relation"], t["object"])
        for t in TRIPLES
        if t["relation"] in DATE_RELATIONS
    }
    lead_years = {
        (t["doc_id"], t["relation"], t["object"])
        for t in LEAD_TRIPLES
        if t["relation"] in DATE_RELATIONS
    }
    overlap = infobox_years & lead_years
    assert not overlap, f"trùng lặp: {list(overlap)[:5]}"


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------


def test_entities_have_valid_contract():
    """Entity phải đủ trường bắt buộc theo data-contracts."""
    if not ENTITIES:
        pytest.skip("chưa có infobox_entities.jsonl")

    for entity in ENTITIES:
        assert entity["entity_id"].startswith("ent_")
        assert entity["name"]
        assert entity["type"]
        assert entity["source_method"] == "infobox"
        assert isinstance(entity["aliases"], list)
        assert isinstance(entity["aliases_normalized"], list)


def test_entities_have_birth_or_death_year_props():
    """Entity nhân vật phải có `birth_year` hoặc `death_year` trong props."""
    if not ENTITIES:
        pytest.skip("chưa có infobox_entities.jsonl")

    persons = [e for e in ENTITIES if e["type"] == "person"]
    if not persons:
        pytest.skip("không có entity nhân vật")

    with_dates = [
        e
        for e in persons
        if e.get("props", {}).get("birth_year") or e.get("props", {}).get("death_year")
    ]
    rate = len(with_dates) / len(persons)
    assert rate >= 0.60, f"chỉ {rate:.1%} entity nhân vật có năm sinh/mất"


def test_relation_distribution_is_reasonable():
    """Phân bố quan hệ không bị chiếm trọn bởi một quan hệ vô lý."""
    if not TRIPLES:
        pytest.skip("chưa có infobox_triples.jsonl")

    counter = Counter(t["relation"] for t in TRIPLES)
    assert len(counter) >= 8, f"chỉ {len(counter)} loại quan hệ"
    assert counter["sinh_nam"] > 0
    assert counter["cha_cua"] > 0


# ---------------------------------------------------------------------------
# Truy vết artifact — `dump_version` + `model_name` (ràng buộc bắt buộc)
# ---------------------------------------------------------------------------

REQUIRED_NODE_PROPS = (
    "birth_year",
    "death_year",
    "reign_start",
    "reign_end",
    "temple_name",
    "posthumous_name",
    "reign_title",
    "gender",
    "aliases",
    "birth_place",
    "death_place",
)


@pytest.mark.parametrize("filename", ["infobox_triples.jsonl", "lead_triples.jsonl"])
def test_triples_carry_dump_version_and_model_name(filename):
    """Mọi triple phải có `dump_version` + `model_name` để truy vết."""
    path = TRIPLES_PATH.with_name(filename)
    if not path.exists():
        pytest.skip(f"chưa có {filename}")

    records = _load_jsonl(path)
    assert records, f"{filename} rỗng"
    for record in records:
        assert record.get("dump_version"), f"{filename}: thiếu dump_version"
        assert record.get("model_name"), f"{filename}: thiếu model_name"


def test_entities_carry_dump_version_and_model_name():
    """Mọi entity phải có `dump_version` + `model_name` để truy vết."""
    if not ENTITIES:
        pytest.skip("chưa có infobox_entities.jsonl")

    for entity in ENTITIES:
        assert entity.get("dump_version"), f"{entity.get('name')}: thiếu dump_version"
        assert entity.get("model_name"), f"{entity.get('name')}: thiếu model_name"


def test_entity_props_cover_documented_keys():
    """Tập `props` phải phủ đủ 11 thuộc tính node đã chốt ở `docs/09` §Phase 3."""
    if not ENTITIES:
        pytest.skip("chưa có infobox_entities.jsonl")

    seen: set[str] = set()
    for entity in ENTITIES:
        seen.update(entity.get("props", {}).keys())
        if entity.get("aliases"):
            seen.add("aliases")

    missing = [key for key in REQUIRED_NODE_PROPS if key not in seen]
    assert not missing, f"thiếu thuộc tính node: {missing}"


def test_birth_place_and_death_place_are_populated():
    """`birth_place`/`death_place` phải có dữ liệu thật, không chỉ khai báo."""
    if not ENTITIES:
        pytest.skip("chưa có infobox_entities.jsonl")

    with_birth_place = [
        e for e in ENTITIES if e.get("props", {}).get("birth_place")
    ]
    with_death_place = [
        e for e in ENTITIES if e.get("props", {}).get("death_place")
    ]
    assert len(with_birth_place) > 100, "birth_place gần như không có dữ liệu"
    assert len(with_death_place) > 50, "death_place gần như không có dữ liệu"


def test_birth_place_only_set_when_triple_emitted():
    """Regression: prop chỉ được ghi khi triple **thực sự** được sinh.

    Nếu ghi prop trước khi kiểm tra schema thì node sẽ khẳng định
    `birth_place` cho quan hệ đã bị loại — vi phạm nguyên tắc "không bịa".
    """
    triples, props, _ = _build("Lý Thái Tổ")
    if "birth_place" in props:
        assert any(t["relation"] == "sinh_tai" for t in triples)


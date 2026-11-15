"""Test cho `src.coref.article_subject` — xác định chủ thể bài (Phase 6, AC C2).

Đối chiếu Gate:
    - **G6** — `article_subject` đúng ≥ 90% trên bài nhân vật, đối chiếu
      `infobox_type`/`wikidata_signal`.

Nguyên tắc kiểm thử
-------------------
- Dùng fixture nhỏ, **không** phụ thuộc dữ liệu thật.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.ids import ENTITY_ID_RE  # noqa: E402
from src.coref.article_subject import (  # noqa: E402
    ArticleSubject,
    load_direct_type_map,
    load_qid_types,
    load_type_map,
    resolve_article_subject,
)

TYPE_MAP_PATH = REPO_ROOT / "configs" / "wikidata_type_map.yaml"


def _doc(**overrides) -> dict:
    """Dựng record bài tối thiểu."""
    base = {
        "doc_id": "doc_1",
        "title": "Lê Lợi",
        "wikibase_item": "Q12345",
        "infobox_type": None,
        "wikidata_signal": None,
    }
    base.update(overrides)
    return base


class TestResolveArticleSubject:
    """Kiểm tra suy loại chủ thể từ các tín hiệu."""

    def test_infobox_type_person(self):
        """`infobox_type="person"` → `person`."""
        subject = resolve_article_subject(_doc(infobox_type="person"))
        assert subject.type == "person"
        assert subject.method == "infobox_type"

    def test_infobox_type_place(self):
        """`infobox_type="place"` → `place`."""
        subject = resolve_article_subject(_doc(infobox_type="place"))
        assert subject.type == "place"

    def test_battle_maps_to_event(self):
        """`battle` → `event` (đồng nghĩa theo `SIGNAL_TO_TYPE`)."""
        subject = resolve_article_subject(_doc(infobox_type="battle"))
        assert subject.type == "event"

    def test_house_maps_to_dynasty(self):
        """`house` → `dynasty`."""
        subject = resolve_article_subject(_doc(infobox_type="house"))
        assert subject.type == "dynasty"

    def test_wikidata_signal_fallback(self):
        """Không có `infobox_type` → dùng `wikidata_signal`."""
        subject = resolve_article_subject(_doc(wikidata_signal="person"))
        assert subject.type == "person"
        assert subject.method == "wikidata_signal"

    def test_infobox_type_has_priority_over_signal(self):
        """`infobox_type` thắng `wikidata_signal` (thứ tự theo plan)."""
        subject = resolve_article_subject(
            _doc(infobox_type="place", wikidata_signal="person")
        )
        assert subject.type == "place"
        assert subject.method == "infobox_type"

    def test_fallback_to_article(self):
        """Không có tín hiệu nào → `type="article"`, confidence thấp."""
        subject = resolve_article_subject(_doc(wikibase_item=None))
        assert subject.type == "article"
        assert subject.method == "fallback"
        assert subject.confidence < 0.5

    def test_qid_types_used_when_no_signal(self):
        """Không có tín hiệu → tra `qid_types` theo P31."""
        qid_types = {"p31": {"Q999": ["Q5"]}}
        type_map = {"Q5": "PERSON"}
        subject = resolve_article_subject(
            _doc(wikibase_item="Q999"),
            qid_types,
            type_map=type_map,
        )
        assert subject.type == "person"
        assert subject.method == "qid_types"

    def test_p31_direct_only_when_no_signal(self):
        """`p31_direct` chỉ dùng khi 3 tín hiệu chính không có gì (D-050)."""
        qid_types = {"p31": {"Q999": ["Q5"]}}
        type_map = {"Q5": "PERSON"}
        subject = resolve_article_subject(
            _doc(wikibase_item="Q999", infobox_type="place"),
            qid_types,
            type_map=type_map,
            direct_type_map=type_map,
        )
        assert subject.type == "place"
        assert subject.method == "infobox_type"


class TestEntityId:
    """Kiểm tra `entity_id` của chủ thể."""

    def test_entity_id_format(self):
        """`entity_id` theo format `ent_<slug>_<hash8>`."""
        subject = resolve_article_subject(_doc(infobox_type="person"))
        assert ENTITY_ID_RE.match(subject.entity_id)

    def test_reuses_known_entity_id(self):
        """Nếu QID đã có `entity_id` trong gazetteer → tái dùng, không mint mới."""
        subject = resolve_article_subject(
            _doc(infobox_type="person"),
            known_entity_ids={"Q12345": "ent_le_loi_aaaa1111"},
        )
        assert subject.entity_id == "ent_le_loi_aaaa1111"

    def test_deterministic(self):
        """Cùng input → cùng `entity_id` (tái lập được)."""
        first = resolve_article_subject(_doc(infobox_type="person"))
        second = resolve_article_subject(_doc(infobox_type="person"))
        assert first.entity_id == second.entity_id

    def test_type_affects_entity_id(self):
        """Khác loại → khác `entity_id` (hash có đóng góp `type`)."""
        person = resolve_article_subject(_doc(infobox_type="person"))
        place = resolve_article_subject(_doc(infobox_type="place"))
        assert person.entity_id != place.entity_id


class TestTypeMap:
    """Kiểm tra việc nạp bảng lớp Wikidata."""

    def test_load_type_map(self):
        """Bảng hợp nhất `direct` + `ancestor` phải có mục."""
        mapping = load_type_map(TYPE_MAP_PATH)
        assert isinstance(mapping, dict)
        assert mapping

    def test_load_direct_type_map(self):
        """Khối `direct` phải là tập con của bảng hợp nhất."""
        merged = load_type_map(TYPE_MAP_PATH)
        direct = load_direct_type_map(TYPE_MAP_PATH)
        assert set(direct).issubset(set(merged))
        assert direct

    def test_load_type_map_missing_file(self, tmp_path):
        """File không tồn tại → trả dict rỗng, không ném lỗi."""
        assert load_type_map(tmp_path / "khong_co.yaml") == {}
        assert load_direct_type_map(tmp_path / "khong_co.yaml") == {}

    def test_load_qid_types_missing_file(self, tmp_path):
        """File `qid_types.json` không tồn tại → trả dict rỗng."""
        assert load_qid_types(tmp_path / "khong_co.json") == {}


class TestArticleSubjectRecord:
    """Kiểm tra dataclass `ArticleSubject`."""

    def test_to_dict_fields(self):
        """Dict đầu ra có đủ trường theo output contract."""
        subject = ArticleSubject(
            doc_id="doc_1",
            title="Lê Lợi",
            type="person",
            entity_id="ent_le_loi_aaaa1111",
            method="infobox_type",
            confidence=0.95,
            qid="Q12345",
        )
        payload = subject.to_dict()
        for key in ("doc_id", "title", "type", "entity_id", "method", "confidence"):
            assert key in payload

    def test_to_dict_is_json_serializable(self):
        """Dict đầu ra phải serialize được sang JSON."""
        subject = resolve_article_subject(_doc(infobox_type="person"))
        json.dumps(subject.to_dict(), ensure_ascii=False)

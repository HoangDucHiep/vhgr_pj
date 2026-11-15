"""Test cho bộ giải quyết coreference — Phase 6 (C1).

Đối chiếu Gate:
    - **G1** — `canonical_id` chỉ là `ent_*` hoặc `null`.
    - **G4** — không đại từ nào gắn sai giới tính.
    - **G7** — 100% offset đúng: `text[start:end] == mention_text`.

Nguyên tắc kiểm thử
-------------------
- Dùng fixture nhỏ, **không** phụ thuộc dữ liệu thật.
- Mỗi test kiểm tra một quy tắc R0–R6 cụ thể.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.ids import ENTITY_ID_RE  # noqa: E402
from src.coref.article_subject import ArticleSubject  # noqa: E402
from src.coref.gazetteer import Gazetteer, GazetteerEntry  # noqa: E402
from src.coref.honorifics import load_honorifics  # noqa: E402
from src.coref.resolve_coref import CorefResolver  # noqa: E402
from src.coref.quality_report import sanitize_han  # noqa: E402

HONORIFICS_PATH = REPO_ROOT / "configs" / "honorifics.yaml"


@pytest.fixture(scope="module")
def honorifics():
    """Nạp từ điển danh xưng thật."""
    return load_honorifics(HONORIFICS_PATH)


@pytest.fixture
def gazetteer():
    """Gazetteer nhỏ với 2 nhân vật (nam + nữ) để kiểm tra giới tính."""
    gaz = Gazetteer()
    gaz.add(
        GazetteerEntry(
            name="Lê Lợi",
            entity_id="ent_le_loi_aaaa1111",
            type="person",
            source="infobox",
            qid="Q1",
            gender="male",
        )
    )
    gaz.add(
        GazetteerEntry(
            name="Trương Thị Ngọc Lung",
            entity_id="ent_truong_thi_ngoc_lung_bbbb2222",
            type="person",
            source="infobox",
            qid="Q2",
            gender="female",
        )
    )
    return gaz


def _resolver(gazetteer, honorifics, subjects=None, **overrides) -> CorefResolver:
    """Dựng `CorefResolver` với cấu hình mặc định cho test."""
    config = {
        "detect_pronouns": True,
        "mint_entity_ids": True,
        "score_gazetteer": 0.95,
        "score_mint": 0.75,
        "score_coref_pronoun": 0.70,
        "score_coref_honorific": 0.70,
        "score_article_subject": 0.60,
        "max_persons_in_paragraph": 3,
        "gender_strict": True,
    }
    config.update(overrides)
    return CorefResolver(gazetteer, honorifics, subjects or {}, config)


def _sentence(sentence_id: str, doc_id: str, text: str, entities=None) -> dict:
    """Dựng record giống `ner_predictions.jsonl`."""
    return {
        "sentence_id": sentence_id,
        "doc_id": doc_id,
        "text": text,
        "entities": entities or [],
    }


def _person_entity(text: str, start: int, end: int, label: str = "PERSON") -> dict:
    """Dựng entity NER."""
    return {"start": start, "end": end, "text": text[start:end], "label": label}


class TestR0Explicit:
    """R0 / R0' — named mention có tên."""

    def test_gazetteer_hit(self, gazetteer, honorifics):
        """Tên có trong gazetteer → gắn `canonical_id`."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi năm 1418."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        mentions = resolver.resolve_sentence(record, [])
        assert mentions[0].canonical_id == "ent_le_loi_aaaa1111"
        assert mentions[0].resolved_by == "explicit"

    def test_mint_unknown_name(self, gazetteer, honorifics):
        """Tên chưa có trong gazetteer → mint ID mới, format `ent_*`."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Nguyễn Văn Nhơn là quan triều Nguyễn."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 15)],
        )
        mentions = resolver.resolve_sentence(record, [])
        assert mentions[0].canonical_id is not None
        assert ENTITY_ID_RE.match(mentions[0].canonical_id)

    def test_no_mint_returns_null(self, gazetteer, honorifics):
        """Tắt mint → `canonical_id=None`."""
        resolver = _resolver(gazetteer, honorifics, mint_entity_ids=False)
        text = "Nguyễn Văn Nhơn là quan triều Nguyễn."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 15)],
        )
        mentions = resolver.resolve_sentence(record, [])
        assert mentions[0].canonical_id is None


class TestR1SameSentence:
    """R1a — ứng viên PERSON trong cùng câu, trước đại từ."""

    def test_pronoun_refers_to_same_sentence_person(self, gazetteer, honorifics):
        """"Lê Lợi ... ông ..." → ông = Lê Lợi."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.canonical_id == "ent_le_loi_aaaa1111"
        assert ong.resolved_by == "coref_pronoun"

    def test_pronoun_after_person_in_previous_sentence(self, gazetteer, honorifics):
        """R1b — ứng viên ở câu trước trong cùng đoạn."""
        resolver = _resolver(gazetteer, honorifics)
        first_text = "Lê Lợi lên ngôi năm 1418."
        first = resolver.resolve_sentence(
            _sentence(
                "s1_0_0",
                "doc_1",
                first_text,
                [_person_entity(first_text, 0, 6)],
            ),
            [],
        )
        second_text = "Ông cải cách triều đại cho cả nước."
        second = resolver.resolve_sentence(
            _sentence("s1_0_1", "doc_1", second_text),
            first,
        )
        ong = next(m for m in second if m.text.lower() == "ông")
        assert ong.canonical_id == "ent_le_loi_aaaa1111"


class TestR2Honorific:
    """R2 — danh xưng + tên riêng đi kèm."""

    def test_honorific_with_following_name(self, gazetteer, honorifics):
        """"vua Lê" → gắn entity của "Lê"."""
        gaz = Gazetteer()
        gaz.add(
            GazetteerEntry(
                name="Lê Thái Tông",
                entity_id="ent_le_thai_tong_cccc3333",
                type="person",
                source="infobox",
                qid="Q3",
            )
        )
        resolver = _resolver(gaz, honorifics)
        text = "Vua Lê Thái Tông lên ngôi năm 1460."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 4, 15)],
        )
        mentions = resolver.resolve_sentence(record, [])
        vua = next(m for m in mentions if m.text.lower() == "vua")
        assert vua.canonical_id == "ent_le_thai_tong_cccc3333"
        assert vua.resolved_by == "coref_honorific"


class TestR3ArticleSubject:
    """R3 — chủ thể bài làm tiên đề mạnh."""

    def test_pronoun_falls_back_to_subject(self, gazetteer, honorifics):
        """Không có ứng viên trong đoạn → gắn chủ thể bài."""
        subjects = {
            "doc_1": ArticleSubject(
                doc_id="doc_1",
                title="Lê Lợi",
                type="person",
                entity_id="ent_le_loi_aaaa1111",
                method="infobox_type",
                confidence=0.95,
            )
        }
        resolver = _resolver(gazetteer, honorifics, subjects)
        text = "Ông là người rất tài giỏi."
        record = _sentence("s1_0_0", "doc_1", text)
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.canonical_id == "ent_le_loi_aaaa1111"
        assert ong.resolved_by == "article_subject"

    def test_event_subject_not_used_for_person_pronoun(self, gazetteer, honorifics):
        """Chủ thể là sự kiện → KHÔNG gắn cho đại từ nhãn PERSON (tránh gắn sai)."""
        subjects = {
            "doc_1": ArticleSubject(
                doc_id="doc_1",
                title="Đảo chính 1963",
                type="event",
                entity_id="ent_dao_chinh_dddd4444",
                method="infobox_type",
                confidence=0.95,
            )
        }
        resolver = _resolver(gazetteer, honorifics, subjects)
        text = "Ông là người rất tài giỏi."
        record = _sentence("s1_0_0", "doc_1", text)
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.canonical_id is None


class TestR4Gender:
    """R4 — lọc theo giới tính (Gate G4)."""

    def test_ong_does_not_resolve_to_female(self, gazetteer, honorifics):
        """"ông" không được gắn entity nữ."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Trương Thị Ngọc Lung, ông là nữ nghệ sĩ."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 20)],
        )
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.canonical_id != "ent_truong_thi_ngoc_lung_bbbb2222"

    def test_ba_does_not_resolve_to_male(self, gazetteer, honorifics):
        """"bà" không được gắn entity nam."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi, bà là nữ nghệ sĩ."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        mentions = resolver.resolve_sentence(record, [])
        ba = next(m for m in mentions if m.text.lower() == "bà")
        assert ba.canonical_id != "ent_le_loi_aaaa1111"

    def test_ba_resolves_to_female(self, gazetteer, honorifics):
        """"bà" gắn đúng entity nữ."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Trương Thị Ngọc Lung, bà là nữ nghệ sĩ."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 20)],
        )
        mentions = resolver.resolve_sentence(record, [])
        ba = next(m for m in mentions if m.text.lower() == "bà")
        assert ba.canonical_id == "ent_truong_thi_ngoc_lung_bbbb2222"


class TestR5Ambiguous:
    """R5 — quá nhiều ứng viên → bỏ qua (không bịa)."""

    def test_plural_pronoun_is_ambiguous(self, gazetteer, honorifics):
        """Đại từ số nhiều ("các ông") → `null` + `ambiguous` (D-049)."""
        resolver = _resolver(gazetteer, honorifics)
        text = "tôi yêu cầu các ông dành cho tôi các nghi thức."
        record = _sentence("s1_0_0", "doc_1", text)
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.canonical_id is None
        assert ong.resolved_by == "ambiguous"

    def test_too_many_persons_is_ambiguous(self, gazetteer, honorifics):
        """Đoạn có ≥ 3 PERSON → `ambiguous`."""
        gaz = Gazetteer()
        for index in range(3):
            gaz.add(
                GazetteerEntry(
                    name=f"Người Số {index}",
                    entity_id=f"ent_nguoi_so_{index}_eeee5555",
                    type="person",
                    source="infobox",
                    qid=f"Q{10 + index}",
                )
            )
        resolver = _resolver(gaz, honorifics)
        first_text = "Người Số 0, Người Số 1 và Người Số 2 đều tới."
        first = resolver.resolve_sentence(
            _sentence(
                "s1_0_0",
                "doc_1",
                first_text,
                [
                    _person_entity(first_text, 0, 10),
                    _person_entity(first_text, 12, 22),
                    _person_entity(first_text, 27, 37),
                ],
            ),
            [],
        )
        second_text = "Ông không đồng ý."
        second = resolver.resolve_sentence(
            _sentence("s1_0_1", "doc_1", second_text), first
        )
        ong = next(m for m in second if m.text.lower() == "ông")
        assert ong.canonical_id is None
        assert ong.resolved_by == "ambiguous"


class TestR6Fallback:
    """R6 — nới: đoạn có đúng 1 PERSON → gắng entity đó."""

    def test_single_person_in_paragraph(self, gazetteer, honorifics):
        """Đoạn chỉ có 1 PERSON → gắng entity đó."""
        resolver = _resolver(gazetteer, honorifics)
        first_text = "Lê Lợi lên ngôi năm 1418."
        first = resolver.resolve_sentence(
            _sentence(
                "s1_0_0",
                "doc_1",
                first_text,
                [_person_entity(first_text, 0, 6)],
            ),
            [],
        )
        second_text = "Ông cải cách triều đại cho cả nước."
        second = resolver.resolve_sentence(
            _sentence("s1_0_1", "doc_1", second_text), first
        )
        ong = next(m for m in second if m.text.lower() == "ông")
        assert ong.canonical_id == "ent_le_loi_aaaa1111"


class TestOutputContract:
    """Kiểm tra contract đầu ra (Gate G1, G7)."""

    def test_canonical_id_is_ent_or_null(self, gazetteer, honorifics):
        """Gate G1 — `canonical_id` chỉ là `ent_*` hoặc `None`."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        for mention in resolver.resolve_sentence(record, []):
            assert mention.canonical_id is None or ENTITY_ID_RE.match(
                mention.canonical_id
            )

    def test_offsets_are_exact(self, gazetteer, honorifics):
        """Gate G7 — `text[start:end] == mention.text`."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        for mention in resolver.resolve_sentence(record, []):
            assert text[mention.start : mention.end] == mention.text

    def test_mention_id_format(self, gazetteer, honorifics):
        """`mention_id` theo format `m<sentence_id>_<idx>`."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        mentions = resolver.resolve_sentence(record, [])
        for index, mention in enumerate(mentions):
            assert mention.mention_id == f"ms1_0_0_{index}"

    def test_mentions_sorted_by_offset(self, gazetteer, honorifics):
        """Mention phải sắp theo `start` tăng dần."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        mentions = resolver.resolve_sentence(record, [])
        starts = [m.start for m in mentions]
        assert starts == sorted(starts)

    def test_resolved_by_in_allowed_set(self, gazetteer, honorifics):
        """`resolved_by` nằm trong tập method cho phép."""
        allowed = {
            "explicit",
            "coref_pronoun",
            "coref_honorific",
            "article_subject",
            "ambiguous",
            "unlinked",
        }
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        for mention in resolver.resolve_sentence(record, []):
            assert mention.resolved_by in allowed

    def test_to_dict_has_required_keys(self, gazetteer, honorifics):
        """Dict đầu ra có đủ trường bắt buộc."""
        resolver = _resolver(gazetteer, honorifics)
        text = "Lê Lợi lên ngôi."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        payload = resolver.resolve_sentence(record, [])[0].to_dict()
        for key in (
            "start",
            "end",
            "text",
            "label",
            "mention_id",
            "canonical_id",
            "resolved_by",
            "score",
            "source",
        ):
            assert key in payload


class TestConfigurableRuleOrder:
    """D-052 — thứ tự ưu tiên quy tắc R phải cấu hình được, không hard-code."""

    def test_default_order_is_r1a_r1b_r3_r5_r6(self, gazetteer, honorifics):
        """Mặc định giữ thứ tự đã chốt."""
        resolver = _resolver(gazetteer, honorifics)
        assert resolver.rule_order == ["r1a", "r1b", "r3", "r5", "r6"]

    def test_order_from_config_is_respected(self, gazetteer, honorifics):
        """Đọc `pronoun_rule_order` từ config."""
        resolver = _resolver(
            gazetteer,
            honorifics,
            pronoun_rule_order=["r3", "r1a", "r1b", "r5", "r6"],
        )
        assert resolver.rule_order == ["r3", "r1a", "r1b", "r5", "r6"]

    def test_order_is_case_insensitive(self, gazetteer, honorifics):
        """Tên quy tắc không phân biệt hoa thường."""
        resolver = _resolver(
            gazetteer, honorifics, pronoun_rule_order=["R1A", "R1B", "R3"]
        )
        assert resolver.rule_order == ["r1a", "r1b", "r3"]

    def test_r3_first_changes_resolution(self, gazetteer, honorifics):
        """Đảo R3 lên trước R1a → đại từ gắn chủ thể bài thay vì người trong câu."""
        subjects = {
            "doc_1": ArticleSubject(
                doc_id="doc_1",
                title="Lê Lợi",
                type="person",
                entity_id="ent_le_loi_aaaa1111",
                method="infobox_type",
                confidence=0.95,
            )
        }
        text = "Trần Thủ Độ giúp Lê Lợi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [
                _person_entity(text, 0, 11),
                _person_entity(text, text.index("Lê Lợi"), text.index("Lê Lợi") + 6),
            ],
        )

        # Mặc định (R1a trước R3) → "ông" = Lê Lợi (người trong cùng câu).
        default = _resolver(gazetteer, honorifics, subjects)
        mentions = default.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.canonical_id == "ent_le_loi_aaaa1111"
        assert ong.resolved_by == "coref_pronoun"

        # Đảo (R3 trước R1a) → "ông" = chủ thể bài.
        swapped = _resolver(
            gazetteer,
            honorifics,
            subjects,
            pronoun_rule_order=["r3", "r1a", "r1b", "r5", "r6"],
        )
        mentions = swapped.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.resolved_by == "article_subject"

    def test_unknown_rule_is_ignored(self, gazetteer, honorifics):
        """Quy tắc lạ → bỏ qua, không làm hỏng (không đoán)."""
        resolver = _resolver(
            gazetteer, honorifics, pronoun_rule_order=["r99", "r1a", "r3"]
        )
        text = "Lê Lợi lên ngôi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [_person_entity(text, 0, 6)],
        )
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.canonical_id == "ent_le_loi_aaaa1111"


class TestR1bUniqueGuard:
    """D-053 — R1b chỉ dùng khi đoạn có đúng 1 người."""

    def test_r1b_skipped_when_paragraph_has_many_persons(
        self, gazetteer, honorifics
    ):
        """Đoạn có nhiều người → R1b không dùng."""
        resolver = _resolver(gazetteer, honorifics, r1b_unique_only=True)
        first_text = "Lê Lợi lên ngôi năm 1418."
        first = resolver.resolve_sentence(
            _sentence(
                "s1_0_0",
                "doc_1",
                first_text,
                [_person_entity(first_text, 0, 6)],
            ),
            [],
        )
        second_text = "Trương Thị Ngọc Lung tham dự."
        second = resolver.resolve_sentence(
            _sentence(
                "s1_0_1",
                "doc_1",
                second_text,
                [_person_entity(second_text, 0, 20)],
            ),
            first,
        )
        third_text = "Sau đó ông rời bền."
        third = resolver.resolve_sentence(
            _sentence("s1_0_2", "doc_1", third_text, []),
            list(first) + list(second),
        )
        ong = next(m for m in third if m.text.lower() == "ông")
        # R1b bị chặn → không gắn (an toàn hơn gắn nhầm).
        assert ong.canonical_id is None
        assert ong.resolved_by == "ambiguous"

    def test_r1b_allowed_when_single_person(self, gazetteer, honorifics):
        """Đoạn chỉ có 1 người → R1b vẫn dùng."""
        resolver = _resolver(gazetteer, honorifics, r1b_unique_only=True)
        first_text = "Lê Lợi lên ngôi năm 1418."
        first = resolver.resolve_sentence(
            _sentence(
                "s1_0_0",
                "doc_1",
                first_text,
                [_person_entity(first_text, 0, 6)],
            ),
            [],
        )
        second_text = "Sau đó ông rời bền."
        second = resolver.resolve_sentence(
            _sentence("s1_0_1", "doc_1", second_text, []),
            first,
        )
        ong = next(m for m in second if m.text.lower() == "ông")
        assert ong.canonical_id == "ent_le_loi_aaaa1111"
        assert ong.resolved_by == "coref_pronoun"


class TestR3RequiresNoPerson:
    """R3 theo điều kiện đặc tả `docs/09` §Phase 6 — đoạn không có PERSON."""

    def test_r3_blocked_when_person_present(self, gazetteer, honorifics):
        """Cờ bật → R3 không dùng khi đoạn đã có PERSON."""
        subjects = {
            "doc_1": ArticleSubject(
                doc_id="doc_1",
                title="Lê Lợi",
                type="person",
                entity_id="ent_le_loi_aaaa1111",
                method="infobox_type",
                confidence=0.95,
            )
        }
        resolver = _resolver(
            gazetteer,
            honorifics,
            subjects,
            pronoun_rule_order=["r3", "r1a", "r1b", "r5", "r6"],
            r3_requires_no_person=True,
        )
        text = "Trần Thủ Độ giúp Lê Lợi, ông cải cách triều đại."
        record = _sentence(
            "s1_0_0",
            "doc_1",
            text,
            [
                _person_entity(text, 0, 11),
                _person_entity(
                    text, text.index("Lê Lợi"), text.index("Lê Lợi") + 6
                ),
            ],
        )
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        # R3 bị chặn → R1a dùng người trong cùng câu.
        assert ong.resolved_by == "coref_pronoun"
        assert ong.canonical_id == "ent_le_loi_aaaa1111"

    def test_r3_used_when_no_person_in_paragraph(self, gazetteer, honorifics):
        """Đoạn không có PERSON → R3 dùng chủ thể bài."""
        subjects = {
            "doc_1": ArticleSubject(
                doc_id="doc_1",
                title="Lê Lợi",
                type="person",
                entity_id="ent_le_loi_aaaa1111",
                method="infobox_type",
                confidence=0.95,
            )
        }
        resolver = _resolver(
            gazetteer,
            honorifics,
            subjects,
            pronoun_rule_order=["r3", "r1a", "r1b", "r5", "r6"],
            r3_requires_no_person=True,
        )
        text = "Sau đó ông rời bền."
        record = _sentence("s1_0_0", "doc_1", text, [])
        mentions = resolver.resolve_sentence(record, [])
        ong = next(m for m in mentions if m.text.lower() == "ông")
        assert ong.resolved_by == "article_subject"
        assert ong.canonical_id == "ent_le_loi_aaaa1111"


class TestNoChineseInReport:
    """Báo cáo Phase 6 không được chứa tiếng Trung (quy tắc `no-chinese.mdc`).

    Corpus Wikipedia tiếng Việt trích nguyên văn chữ Hán trong ngoặc
    (vd. ``chữ Hán: <chu Han>``) → phải được thay bằng ``<bỏ dấu>`` trước khi
    render ra Markdown.
    """

    def test_sanitize_han_removes_chinese(self):
        """Ký tự Hán bị thay bằng `<bỏ dấu>`."""
        han = "\u674e\u5e38\u5091"  # <chu Han>
        assert sanitize_han(f"Lý Thường Kiệt (chữ Hán: {han})") == (
            "Lý Thường Kiệt (chữ Hán: <bỏ dấu>)"
        )

    def test_sanitize_han_keeps_vietnamese(self):
        """Tiếng Việt có dấu không bị đụng."""
        text = "Lê Lợi lên ngôi năm 1418, ông cải cách triều đại."
        assert sanitize_han(text) == text

    def test_rendered_report_has_no_chinese(self):
        """File báo cáo đã sinh không chứa ký tự Hán."""
        import re

        report = REPO_ROOT / "reports" / "coref_quality.md"
        if not report.exists():
            pytest.skip("reports/coref_quality.md chưa được sinh")
        content = report.read_text(encoding="utf-8")
        found = re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF]", content)
        assert not found, f"báo cáo chứa {len(found)} ký tự Hán: {''.join(found[:10])}"

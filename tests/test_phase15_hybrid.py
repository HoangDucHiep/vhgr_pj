"""Test cho Hybrid GraphRAG (Phase 15).

Bao phủ:
1. `intent` — 6 ý định, rule không dấu, chiến lược fusion.
2. `graph_context` — template Cypher, lọc nhiễu, 1-hop expansion.
3. `fusion` — thứ tự ưu tiên, đánh số `[n]` chung, ngân sách ký tự.
4. `conversation` — query rewriting, session store, kế thừa chủ thề.
5. Endpoint `POST /api/ask/hybrid` + `GET /api/session/{id}`.

Test KG cần Neo4j ⇒ `pytest.skip` nếu không kết nối được.
"""

from __future__ import annotations

import json

import pytest

from src.common.config import REPO_ROOT
from src.qa.conversation import (
    Session,
    SessionStore,
    has_pronoun,
    rewrite_question,
)
from src.qa.fusion import FusedContext, fuse
from src.qa.graph_context import (
    INVERSE_RELATION,
    RELATION_LABEL,
    GraphContext,
    GraphContextBuilder,
)
from src.qa.intent import (
    FUSION_STRATEGY,
    INTENTS,
    IntentResult,
    classify_by_rule,
)
from src.qa.retriever import Chunk, RetrievedChunk


# ----------------------------------------------------------------------
# 1. intent
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("diễn biến trận Bạch Đằng năm 1288", "narrative"),
        ("Kể lại cuộc khởi nghĩa Lam Sơn", "narrative"),
        ("Ai là con của Trần Nhân Tông?", "relational"),
        ("Trần Hưng Đạo mất năm nào?", "relational"),
        ("Triều Lê có bao nhiêu đời vua?", "count"),
        ("So sánh Lê Lợi và Nguyễn Huệ", "comparison"),
        ("Vua nào chỉ huy trận Bạch Đằng?", "multi_hop"),
    ],
)
def test_intent_rules(question: str, expected: str) -> None:
    """Rule phân loại đúng 6 ý định trên câu hỏi thật."""
    result = classify_by_rule(question)
    assert result.intent == expected
    assert result.confidence >= 0.7
    assert result.source == "rule"


def test_intent_all_intents_have_strategy() -> None:
    """Mỗi ý định đều có chiến lược fusion."""
    assert set(INTENTS) == set(FUSION_STRATEGY)
    for strategy in FUSION_STRATEGY.values():
        assert strategy in {"text_first", "kg_first", "both"}


def test_intent_strategy_narrative_text_first() -> None:
    """Câu tự sự ⇒ text-first (KG không có narrative)."""
    assert FUSION_STRATEGY["narrative"] == "text_first"
    assert FUSION_STRATEGY["relational"] == "kg_first"


def test_intent_result_defaults() -> None:
    """`IntentResult` có giá trị mặc định an toàn."""
    result = IntentResult(intent="relational")
    assert result.signals == []
    assert result.strategy == "kg_first"


# ----------------------------------------------------------------------
# 2. graph_context
# ----------------------------------------------------------------------


def test_inverse_relation_table_covers_all_relations() -> None:
    """Bảng chiều đảo có đủ quan hệ cốt lõi."""
    for relation in (
        "cha_cua", "me_cua", "vo_cua", "chong_cua", "ke_vi",
        "thuoc_trieu_dai", "sinh_nam", "mat_nam", "chi_huy_tran",
    ):
        assert relation in INVERSE_RELATION


def test_relation_label_has_vietnamese() -> None:
    """Nhãn quan hệ bằng tiếng Việt."""
    assert RELATION_LABEL["cha_cua"] == "cha của"
    assert RELATION_LABEL["chi_huy_tran"] == "chỉ huy trận"


def test_graph_context_empty() -> None:
    """Context rỗng."""
    context = GraphContext()
    assert context.is_empty()
    assert context.to_text() == ""


def test_graph_context_to_text_includes_evidence() -> None:
    """Văn bản context chứa quan hệ + bằng chứng."""
    context = GraphContext(
        entities=[{"entity_id": "e1", "name": "Trần Hưng Đạo"}],
        edges=[
            {
                "source_id": "e1",
                "source_name": "Trần Hưng Đạo",
                "relation": "chi_huy_tran",
                "target_id": "e2",
                "target_name": "Trận Bạch Đằng",
                "evidence_sentence": "Trần Hưng Đạo chỉ huy quân đội.",
            }
        ],
    )
    text = context.to_text()
    assert "Trần Hưng Đạo" in text
    assert "chỉ huy trận" in text
    assert "Trận Bạch Đằng" in text
    assert "bằng chứng" in text


def test_graph_builder_filters_noisy_edges() -> None:
    """Cạnh nhiễu (`Quốc lộ 14`) bị lọc ở tầng đọc."""
    from src.graph.noise_filter import filter_noisy_edges

    edges = [
        {
            "source_id": "e1",
            "source_name": "Trần Hưng Đạo",
            "relation": "mat_tai",
            "target_id": "e2",
            "target_name": "Quốc lộ 14",
            "evidence_sentence": "x",
        },
        {
            "source_id": "e1",
            "source_name": "Trần Hưng Đạo",
            "relation": "mat_tai",
            "target_id": "e3",
            "target_name": "Vạn Kiếp",
            "evidence_sentence": "x",
        },
    ]
    kept = filter_noisy_edges(edges)
    assert len(kept) == 1
    assert kept[0]["target_name"] == "Vạn Kiếp"


def test_graph_builder_dedupe() -> None:
    """Cạnh trùng lặp bị lo."""
    builder = GraphContextBuilder()
    edges = [
        {"source_id": "a", "relation": "cha_cua", "target_id": "b"},
        {"source_id": "a", "relation": "cha_cua", "target_id": "b"},
    ]
    from src.qa.graph_context import _dedupe_edges

    assert len(_dedupe_edges(edges)) == 1


# ----------------------------------------------------------------------
# 3. fusion
# ----------------------------------------------------------------------


def _retrieved(index: int, title: str, text: str) -> RetrievedChunk:
    """Tạo `RetrievedChunk` test.

    Args:
        index: Chỉ số.
        title: Tên bài.
        text: Nội dung.

    Returns:
        `RetrievedChunk`.
    """
    chunk = Chunk(
        chunk_id=f"chunk_doc_{index}",
        doc_id=f"doc_{index}",
        page_id=index,
        title=title,
        section="Mục 1",
        section_path="Mục 1",
        text=text,
        source_url="https://vi.wikipedia.org/wiki/x",
    )
    return RetrievedChunk(chunk=chunk, index=index, rrf_score=0.02 - index * 0.001)


def _graph() -> GraphContext:
    """Graph context giả.

    Returns:
        `GraphContext`.
    """
    return GraphContext(
        entities=[{"entity_id": "e1", "name": "Trần Hưng Đạo"}],
        edges=[
            {
                "source_id": "e1",
                "source_name": "Trần Hưng Đạo",
                "relation": "chi_huy_tran",
                "target_id": "e2",
                "target_name": "Trận Bạch Đằng",
                "evidence_sentence": "Trần Hưng Đạo chỉ huy quân đội nhà Trần.",
                "source_url": "https://vi.wikipedia.org/wiki/y",
            }
        ],
    )


def test_fusion_text_first_order() -> None:
    """`narrative` ⇒ khối văn bản đứng trước khối KG."""
    fused = fuse(
        intent=IntentResult(intent="narrative"),
        text_results=[_retrieved(0, "A", "nội dung văn bản")],
        graph=_graph(),
    )
    assert fused.strategy == "text_first"
    assert fused.text_blocks[0]["n"] == 1
    assert fused.kg_blocks[0]["n"] == 2


def test_fusion_kg_first_order() -> None:
    """`relational` ⇒ khối KG đứng trước khối văn bản."""
    fused = fuse(
        intent=IntentResult(intent="relational"),
        text_results=[_retrieved(0, "A", "nội dung văn bản")],
        graph=_graph(),
    )
    assert fused.strategy == "kg_first"
    assert fused.kg_blocks[0]["n"] == 1
    assert fused.text_blocks[0]["n"] == 2


def test_fusion_shared_citation_space() -> None:
    """Text và KG dùng chung không gian số `[n]` — không trùng số."""
    fused = fuse(
        intent=IntentResult(intent="narrative"),
        text_results=[
            _retrieved(0, "A", "nội dung 1"),
            _retrieved(1, "B", "nội dung 2"),
        ],
        graph=_graph(),
    )
    numbers = [c["n"] for c in fused.citations]
    assert numbers == sorted(numbers)
    assert len(numbers) == len(set(numbers))
    assert numbers == list(range(1, len(numbers) + 1))


def test_fusion_respects_char_budget() -> None:
    """Tổng ký tự context không vượt ngân sách (sai lệch nhỏ do phần text)."""
    fused = fuse(
        intent=IntentResult(intent="narrative"),
        text_results=[_retrieved(i, f"T{i}", "x" * 4000) for i in range(10)],
        graph=_graph(),
        char_budget=6000,
    )
    assert len(fused.to_text()) <= 9000


def test_fusion_empty_graph_still_has_text() -> None:
    """KG rỗng ⇒ vẫn có context văn bản."""
    fused = fuse(
        intent=IntentResult(intent="relational"),
        text_results=[_retrieved(0, "A", "nội dung")],
        graph=None,
    )
    assert fused.text_blocks
    assert not fused.kg_blocks


def test_fused_context_is_empty() -> None:
    """`FusedContext` rỗng."""
    assert FusedContext().is_empty()


# ----------------------------------------------------------------------
# 4. conversation
# ----------------------------------------------------------------------


def test_has_pronoun_accent_insensitive() -> None:
    """Nhận diện đại từ bất kể dấu / hoa thường."""
    assert has_pronoun("Ông ấy mất năm nào?")
    assert has_pronoun("ông ấy mất năm nào?")
    assert has_pronoun("Vị vua đó chỉ huy trận nào?")
    assert has_pronoun("Triều đó có bao nhiêu đời vua?")
    assert not has_pronoun("Trần Hưng Đạo mất năm nào?")


def test_rewrite_replaces_pronoun_with_subject() -> None:
    """Đại từ được thay bằng tên chủ thề lượt trước."""
    session = Session(session_id="s1", last_subject_name="Trần Hưng Đạo")
    rewritten = rewrite_question("Ông ấy mất năm nào?", session)
    assert "Ông ấy" not in rewritten
    assert "Trần Hưng Đạo" in rewritten


def test_rewrite_inherits_subject_without_pronoun() -> None:
    """Câu không đại từ, không entity ⇒ nối chủ thề."""
    session = Session(session_id="s1", last_subject_name="Trần Hưng Đạo")
    rewritten = rewrite_question("mất năm nào?", session)
    assert rewritten.startswith("Trần Hưng Đạo")


def test_rewrite_keeps_question_with_new_entity() -> None:
    """Câu đã có entity riêng ⇒ không viết lại."""
    session = Session(session_id="s1", last_subject_name="Trần Hưng Đạo")
    rewritten = rewrite_question(
        "Lê Lợi sinh năm nào?", session, has_new_entity=True
    )
    assert rewritten == "Lê Lợi sinh năm nào?"


def test_rewrite_without_session() -> None:
    """Không có session ⇒ giữ nguyên câu hỏi."""
    assert rewrite_question("Ông ấy mất năm nào?", None) == "Ông ấy mất năm nào?"


def test_session_store_roundtrip(tmp_path) -> None:
    """Lưu/nạp session tròn (có ghi đè)."""
    store = SessionStore(tmp_path)
    session = store.get_or_create("test_session")
    store.record_turn(
        session,
        question="Trần Hưng Đạo là ai?",
        rewritten_question="Trần Hưng Đạo là ai?",
        answer="Một tướng nhà Trần.",
        entities=["ent_tran_hung_dao"],
        subject_entity_id="ent_tran_hung_dao",
        subject_name="Trần Hưng Đạo",
    )
    store.save(session)

    loaded = store.get("test_session")
    assert loaded is not None
    assert len(loaded.turns) == 1
    assert loaded.last_subject_name == "Trần Hưng Đạo"
    assert loaded.recent_entity_ids == ["ent_tran_hung_dao"]


def test_session_store_missing_returns_none(tmp_path) -> None:
    """Session không tồn tại ⇒ ``None``."""
    assert SessionStore(tmp_path).get("khong_ton_tai") is None


# ----------------------------------------------------------------------
# 5. endpoint
# ----------------------------------------------------------------------


def test_ask_hybrid_endpoint_contract() -> None:
    """`POST /api/ask/hybrid` trả đúng output contract."""
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post(
        "/api/ask/hybrid", json={"question": "diễn biến trận Bạch Đằng"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"found", "not_in_data", "error"}
    assert isinstance(payload["answer"], str)
    assert isinstance(payload["citations"], list)
    assert isinstance(payload["kg_used"], list)
    assert "intent" in payload
    assert "fusion_strategy" in payload
    assert "session_id" in payload


def test_session_endpoint_returns_404_for_unknown() -> None:
    """Phiên không tồn tại ⇒ 404."""
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.get("/api/session/khong_ton_tai_xyz")
    assert response.status_code == 404

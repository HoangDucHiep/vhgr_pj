"""Test regression cho D-118 — chuẩn hoá **chiều quan hệ** ở tầng đọc KG.

Bug gốc
-------
Các template Cypher của `src/qa/graph_context.py` khớp **không hướng**
(``MATCH (e)-[r]-(other)``) rồi gán cứng ``source = e``, ``target = other``
⇒ **mọi cạnh bị đảo chiều khi hiển thị**.

    KG thật:      (Ưng Dự)-[:cha_cua]->(Hồng Thiết)
    Hiển thị sai: Hồng Thiết — cha của → Ưng Dự

Đo được trên KG thật: **2.601/2.601** cạnh gia đình bị đảo ⇒ LLM sinh câu
trả lời sai ⇒ judge chấm `faithfulness` < 2 ⇒ Arm B không đạt gate
`faithfulness_rate ≥ 0,90`.

Cách sửa: chuẩn hoá ở **tầng đọc** (giữ nguyên Neo4j — nguyên tắc D-095).
"""

from __future__ import annotations

from src.graph.direction import (
    INVERSE_LABEL,
    invert_relation,
    normalize_direction,
    normalize_edges,
)


class TestInvertRelation:
    """Đảo nhãn quan hệ."""

    def test_cha_cua_becomes_con_cua(self) -> None:
        assert invert_relation("cha_cua") == "con_cua"

    def test_me_cua_becomes_con_cua(self) -> None:
        assert invert_relation("me_cua") == "con_cua"

    def test_vo_cua_becomes_chong_cua(self) -> None:
        assert invert_relation("vo_cua") == "chong_cua"

    def test_chong_cua_becomes_vo_cua(self) -> None:
        assert invert_relation("chong_cua") == "vo_cua"

    def test_symmetric_relation_unchanged(self) -> None:
        assert invert_relation("anh_em_cua") == "anh_em_cua"

    def test_birth_relation_unchanged(self) -> None:
        assert invert_relation("sinh_nam") == "sinh_nam"

    def test_unknown_relation_unchanged(self) -> None:
        assert invert_relation("quan_he_lap") == "quan_he_lap"

    def test_inverse_label_table_is_consistent(self) -> None:
        """Bảng đảo phải đối xứng cho quan hệ gia đình."""
        assert INVERSE_LABEL["cha_cua"] == "con_cua"
        assert INVERSE_LABEL["vo_cua"] == "chong_cua"


class TestNormalizeDirection:
    """Chuẩn hoá chiều của một cạnh."""

    def test_forward_edge_keeps_direction(self) -> None:
        edge = {
            "source_id": "ent_a",
            "source_name": "A",
            "target_id": "ent_b",
            "target_name": "B",
            "relation": "cha_cua",
        }
        out = normalize_direction(edge, anchor_id="ent_a")
        assert out["source_id"] == "ent_a"
        assert out["target_id"] == "ent_b"
        assert out["relation"] == "cha_cua"
        assert out["reversed"] is False

    def test_reverse_edge_is_swapped_and_relabelled(self) -> None:
        """KG: (B)-[:cha_cua]->(A); hỏi về A ⇒ phải hiện A là **con** của B."""
        edge = {
            "source_id": "ent_b",
            "source_name": "B",
            "target_id": "ent_a",
            "target_name": "A",
            "relation": "cha_cua",
        }
        out = normalize_direction(edge, anchor_id="ent_a")
        assert out["source_id"] == "ent_a"
        assert out["source_name"] == "A"
        assert out["target_id"] == "ent_b"
        assert out["target_name"] == "B"
        # Nhãn đổi sang quan hệ đảo để câu đọc đúng nghĩa.
        assert out["relation"] == "con_cua"
        assert out["reversed"] is True

    def test_input_edge_not_mutated(self) -> None:
        edge = {
            "source_id": "ent_b",
            "source_name": "B",
            "target_id": "ent_a",
            "target_name": "A",
            "relation": "cha_cua",
        }
        normalize_direction(edge, anchor_id="ent_a")
        assert edge["source_id"] == "ent_b"
        assert edge["relation"] == "cha_cua"

    def test_no_anchor_keeps_direction(self) -> None:
        edge = {
            "source_id": "ent_b",
            "source_name": "B",
            "target_id": "ent_a",
            "target_name": "A",
            "relation": "cha_cua",
        }
        out = normalize_direction(edge, anchor_id="")
        assert out["source_id"] == "ent_b"
        assert out["relation"] == "cha_cua"

    def test_symmetric_edge_not_relabelled_when_reversed(self) -> None:
        edge = {
            "source_id": "ent_b",
            "source_name": "B",
            "target_id": "ent_a",
            "target_name": "A",
            "relation": "anh_em_cua",
        }
        out = normalize_direction(edge, anchor_id="ent_a")
        assert out["relation"] == "anh_em_cua"
        assert out["reversed"] is True


class TestNormalizeEdges:
    """Chuẩn hoá nhiều cạnh."""

    def test_self_loop_is_dropped(self) -> None:
        edges = [
            {
                "source_id": "ent_a",
                "source_name": "A",
                "target_id": "ent_a",
                "target_name": "A",
                "relation": "cha_cua",
            }
        ]
        assert normalize_edges(edges, anchor_id="ent_a") == []

    def test_self_loop_marker_removed(self) -> None:
        edges = [
            {
                "source_id": "ent_a",
                "source_name": "A",
                "target_id": "ent_a",
                "target_name": "A",
                "relation": "cha_cua",
            }
        ]
        out = normalize_edges(edges, anchor_id="ent_a")
        assert all("_self_loop" not in edge for edge in out)

    def test_multiple_edges_preserved(self) -> None:
        edges = [
            {
                "source_id": "ent_a",
                "source_name": "A",
                "target_id": "ent_x",
                "target_name": "X",
                "relation": "sinh_nam",
            },
            {
                "source_id": "ent_a",
                "source_name": "A",
                "target_id": "ent_y",
                "target_name": "Y",
                "relation": "sinh_tai",
            },
        ]
        out = normalize_edges(edges, anchor_id="ent_a")
        assert len(out) == 2
        assert all(edge["source_id"] == "ent_a" for edge in out)


class TestGraphContextTemplatesKeepDirection:
    """Template Cypher phải trả về chiều **thật** của cạnh (D-118)."""

    def test_templates_use_startnode_endnode(self) -> None:
        from src.qa.graph_context import _INTENT_TEMPLATES

        for name, template in _INTENT_TEMPLATES.items():
            cypher = template["cypher"]
            if "type(r)" not in cypher:
                continue
            if name in ("dynasty", "inverse_family"):
                # Template này match **có hướng** sẵn ⇒ không cần startNode.
                continue
            assert "startNode(r)" in cypher, f"template {name} phải giữ chiều cạnh"
            assert "endNode(r)" in cypher, f"template {name} phải giữ chiều cạnh"

    def test_biographical_template_keeps_direction(self) -> None:
        """Template `biographical` dùng OPTIONAL MATCH có hướng ⇒ không cần đảo."""
        from src.qa.graph_context import _INTENT_TEMPLATES

        cypher = _INTENT_TEMPLATES["biographical"]["cypher"]
        assert "(e)-[r1]->(y1:Year)" in cypher

    def test_inverse_family_template_uses_reverse_match(self) -> None:
        """Truy vấn chiều ngược gia đình phải match ``<-[r]-``."""
        from src.qa.graph_context import _INTENT_TEMPLATES

        cypher = _INTENT_TEMPLATES["inverse_family"]["cypher"]
        assert "<-[r]-(other)" in cypher


class TestRelationLabels:
    """Nhãn hiển thị phải có quan hệ đảo."""

    def test_inverse_labels_present(self) -> None:
        from src.qa.graph_context import RELATION_LABEL

        assert RELATION_LABEL["con_cua"] == "con của"
        assert RELATION_LABEL["chong_cua"] == "chồng của"

    def test_labels_are_unique_per_meaning(self) -> None:
        from src.qa.graph_context import RELATION_LABEL

        # "con của" và "cha của" phải khác nhau.
        assert RELATION_LABEL["con_cua"] != RELATION_LABEL["cha_cua"]
        assert RELATION_LABEL["chong_cua"] != RELATION_LABEL["vo_cua"]


class TestFusionBudget:
    """Ngân sách context phải luôn giữ lại chỗ cho văn bản (D-118)."""

    def test_min_text_ratio_is_positive(self) -> None:
        from src.qa.fusion import MIN_TEXT_RATIO

        assert MIN_TEXT_RATIO > 0

    def test_kg_first_budget_ratio_leaves_room_for_text(self) -> None:
        from src.qa.fusion import KG_FIRST_BUDGET_RATIO, MIN_TEXT_RATIO

        assert KG_FIRST_BUDGET_RATIO + MIN_TEXT_RATIO <= 1.0
        assert KG_FIRST_BUDGET_RATIO < 1.0

    def test_text_is_kept_in_kg_first_strategy(self) -> None:
        """Với `kg_first`, phần text vẫn phải còn ≥ `MIN_TEXT_RATIO`."""
        from src.qa.fusion import MIN_TEXT_RATIO, fuse
        from src.qa.intent import IntentResult
        from src.qa.graph_context import GraphContext

        class _Chunk:
            chunk_id = "chunk_1"
            doc_id = "doc_1"
            title = "T"
            section = ""
            section_path = ""
            source_url = "https://example.org"
            text = "x" * 4000
            entity_ids: list[str] = []

            def cite_label(self) -> str:
                return "[x] T"

        class _Retrieved:
            chunk = _Chunk()
            rrf_score = 1.0

        edges = [
            {
                "source_id": "ent_a",
                "source_name": "A",
                "target_id": f"ent_b{i}",
                "target_name": f"B{i}",
                "relation": "sinh_nam",
                "evidence_sentence": "y" * 200,
                "source_url": "https://example.org",
            }
            for i in range(40)
        ]
        graph = GraphContext(entities=[], edges=edges, source="test")
        intent = IntentResult(intent="relational", confidence=1.0, source="rule")

        fused = fuse(
            intent=intent,
            text_results=[_Retrieved()],
            graph=graph,
            char_budget=12000,
        )
        text_chars = sum(len(block["text"]) for block in fused.text_blocks)
        kg_chars = sum(len(block["text"]) for block in fused.kg_blocks)
        assert text_chars > 0, "phần văn bản không được bị bóp về 0"
        assert text_chars >= int(12000 * MIN_TEXT_RATIO) * 0.5
        assert kg_chars > 0

    def test_no_graph_gives_full_budget_to_text(self) -> None:
        """Không có KG ⇒ văn bản dùng **toàn bộ** ngân sách (công bằng B− vs A)."""
        from src.qa.fusion import fuse
        from src.qa.intent import IntentResult
        from src.qa.graph_context import GraphContext

        class _Chunk:
            chunk_id = "chunk_1"
            doc_id = "doc_1"
            title = "T"
            section = ""
            section_path = ""
            source_url = "https://example.org"
            text = "x" * 20000
            entity_ids: list[str] = []

            def cite_label(self) -> str:
                return "[x] T"

        class _Retrieved:
            chunk = _Chunk()
            rrf_score = 1.0

        intent = IntentResult(intent="relational", confidence=1.0, source="rule")
        fused = fuse(
            intent=intent,
            text_results=[_Retrieved()],
            graph=GraphContext(),
            char_budget=12000,
        )
        text_chars = sum(len(block["text"]) for block in fused.text_blocks)
        assert text_chars >= 12000, "văn bản phải dùng toàn bộ ngân sách"
        assert not fused.kg_blocks

"""Test cho các fix D-123 / D-124 (Phase 17).

Nội dung test
-------------
- **D-123 #1** — `normalize_direction` phải đảo **cả** `source_labels`/
  `target_labels` khi lật chiều cạnh, nếu không `_resolve_title_names` không
  nhận ra node `Title` trên cạnh đã lật ⇒ tên hiển thị là **danh xưng**
  ("quận công") thay vì tên riêng.
- **D-123 #2** — `_resolve_title_names` phải thay tên node `Title` bằng tên
  trong bằng chứng.
- **D-123 #3** — `_name_from_evidence` phải nhận diện được **biến thể** tiền tố
  bằng chứng ("Chi Huy 1:", "Chi Huy 2:" — D-124) và **không** nhận nhầm tiền
  tố của quan hệ khác.
- **D-123 #4** — điều kiện chạy hop-2 phải khớp **tên template**
  (`event_deep`/`narrative`), không chỉ `"narrative"` — nếu không nhánh hop-2
  **không bao giờ** chạy.
- **D-124 #1** — template hop-2 phải ràng buộc `n2 = e` (chỉ giữ cạnh quanh
  **đúng** sự kiện đang hỏi) ⇒ loại được nhiễu "địa điểm → sự kiện khác".
- **D-124 #2** — phải có template `event_parties` để bổ sung "các bên liên
  quan" cho sự kiện không có cạnh trực tiếp.
- **D-124 #3** — `filter_noisy_edges` phải loại cạnh có tên **rác do liên kết
  entity** ("Chuẩn đề đốc Page").
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.graph.direction import normalize_direction  # noqa: E402
from src.graph.noise_filter import filter_noisy_edges  # noqa: E402
from src.qa.graph_context import (  # noqa: E402
    _INTENT_TEMPLATES,
    _name_from_evidence,
    _resolve_title_names,
)


class TestD123DirectionLabelSwap:
    """D-123 #1 — đảo nhãn khi lật chiều."""

    def test_labels_are_swapped_when_reversed(self) -> None:
        """Lật chiều ⇒ `source_labels`/`target_labels` phải đổi chỗ."""
        edge = {
            "source_id": "ent_title",
            "source_name": "quận công",
            "source_labels": ["Title"],
            "relation": "chi_huy_tran",
            "target_id": "ent_event",
            "target_name": "Cuộc bao vây thành Quy Nhơn",
            "target_labels": ["Event"],
        }
        out = normalize_direction(edge, anchor_id="ent_event")
        assert out["reversed"] is True
        # Nhãn phải đi theo node ⇒ node `Title` nằm ở `target_labels`.
        assert "Title" in out["target_labels"]
        assert "Title" not in out["source_labels"]
        assert out["target_name"] == "quận công"
        assert out["source_name"] == "Cuộc bao vây thành Quy Nhơn"

    def test_labels_not_swapped_when_not_reversed(self) -> None:
        """Không lật chiều ⇒ nhãn giữ nguyên."""
        edge = {
            "source_id": "ent_event",
            "source_name": "Cuộc bao vây thành Quy Nhơn",
            "source_labels": ["Event"],
            "relation": "chi_huy_tran",
            "target_id": "ent_person",
            "target_name": "Võ Tánh",
            "target_labels": ["Person"],
        }
        out = normalize_direction(edge, anchor_id="ent_event")
        assert not out.get("reversed")
        assert out["source_labels"] == ["Event"]
        assert out["target_labels"] == ["Person"]


class TestD123TitleResolution:
    """D-123 #2 — sửa tên node `Title` bằng tên trong bằng chứng."""

    def test_title_node_gets_evidence_name(self) -> None:
        """Node `Title` (danh xưng) ⇒ thay bằng tên riêng trong bằng chứng."""
        edges = [
            {
                "source_id": "ent_event",
                "source_name": "Cuộc bao vây thành Quy Nhơn",
                "source_labels": ["Event"],
                "relation": "chi_huy_tran",
                "target_id": "ent_title",
                "target_name": "quận công",
                "target_labels": ["Title"],
                "evidence_sentence": "Chỉ huy: Nguyễn Văn Thành",
            }
        ]
        out = _resolve_title_names(edges)
        assert out[0]["target_name"] == "Nguyễn Văn Thành"

    def test_person_node_name_untouched(self) -> None:
        """Node `Person` ⇒ giữ nguyên tên."""
        edges = [
            {
                "source_id": "ent_event",
                "source_name": "Sự kiện",
                "source_labels": ["Event"],
                "relation": "chi_huy_tran",
                "target_id": "ent_p",
                "target_name": "Võ Tánh",
                "target_labels": ["Person"],
                "evidence_sentence": "Chỉ huy: Nguyễn Văn Thành",
            }
        ]
        out = _resolve_title_names(edges)
        assert out[0]["target_name"] == "Võ Tánh"

    def test_title_resolution_after_direction_swap(self) -> None:
        """Chuỗi đầy đủ: lật chiều **rồi** sửa tên ⇒ phải ra tên riêng.

        Đây chính là lỗi D-123: nếu không đảo nhãn, node `Title` không còn ở
        `target_labels` ⇒ `_resolve_title_names` không sửa ⇒ hiển thị
        "quận công" ⇒ LLM gán nhầm danh xưng cho cả 10 chỉ huy.
        """
        edge = {
            "source_id": "ent_title",
            "source_name": "quận công",
            "source_labels": ["Title"],
            "relation": "chi_huy_tran",
            "target_id": "ent_event",
            "target_name": "Cuộc bao vây thành Quy Nhơn",
            "target_labels": ["Event"],
            "evidence_sentence": "Chỉ huy: Nguyễn Văn Thành",
        }
        out = _resolve_title_names([normalize_direction(edge, anchor_id="ent_event")])
        assert out[0]["target_name"] == "Nguyễn Văn Thành"
        assert out[0]["target_name"] != "quận công"


class TestD123EvidencePrefixVariants:
    """D-123 #3 + D-124 — biến thể tiền tố bằng chứng."""

    @pytest.mark.parametrize(
        "evidence",
        [
            "Chỉ huy: Nguyễn Văn Thành",
            "Chi Huy 1: Nguyễn Văn Thành",
            "Chi Huy 2: Nguyễn Văn Thành",
            "Chi Huy: Nguyễn Văn Thành",
        ],
    )
    def test_commander_prefix_variants(self, evidence: str) -> None:
        """Mọi biến thể tiền tố "chỉ huy" đều phải được nhận diện."""
        assert (
            _name_from_evidence("chi_huy_tran", evidence)
            == "Nguyễn Văn Thành"
        )

    def test_prefix_of_other_relation_not_matched(self) -> None:
        """Bằng chứng "Địa điểm" **không** được dùng cho quan hệ `chi_huy_tran`."""
        assert _name_from_evidence("chi_huy_tran", "Địa điểm: Bình Định") == ""
        assert _name_from_evidence("chi_huy_tran", "Bên tham chiến: Nhà Thanh") == ""

    def test_place_relation_uses_its_own_prefix(self) -> None:
        """Quan hệ địa điểm dùng đúng tiền tố của nó."""
        assert _name_from_evidence("dien_ra_tai", "Địa điểm: Bình Định") == (
            "Bình Định"
        )

    def test_long_evidence_is_ignored(self) -> None:
        """Bằng chứng dài (>80 ký tự) ⇒ không phải mẫu "Vai trò: Tên"."""
        long_evidence = "Chỉ huy: " + "x" * 200
        assert _name_from_evidence("chi_huy_tran", long_evidence) == ""


class TestD123Hop2Gate:
    """D-123 #4 — điều kiện chạy hop-2 phải khớp tên template."""

    def test_hop2_template_exists(self) -> None:
        """Template hop-2 phải tồn tại."""
        assert "event_hop2" in _INTENT_TEMPLATES

    def test_event_deep_triggers_hop2(self) -> None:
        """`hybrid.py` map `"narrative"` → template `"event_deep"`.

        ⇒ Điều kiện chạy hop-2 phải nhận `"event_deep"`, nếu không nhánh này
        **không bao giờ** chạy (đo được trong D-123).
        """
        import inspect

        from src.qa.graph_context import GraphContextBuilder

        source = inspect.getsource(GraphContextBuilder.fetch)
        assert 'intent in ("event_deep", "narrative")' in source


class TestD124Hop2Scoping:
    """D-124 #1 — hop-2 phải ràng buộc quanh đúng sự kiện."""

    def test_hop2_cypher_scopes_to_anchor(self) -> None:
        """Hop-2 phải có điều kiện `n2 = e`."""
        cypher = _INTENT_TEMPLATES["event_hop2"]["cypher"]
        assert "n2 = e" in cypher

    def test_hop2_uses_context_relations_only(self) -> None:
        """Hop-2 không được dùng quan hệ sinh tử (nhiễu)."""
        cypher = _INTENT_TEMPLATES["event_hop2"]["cypher"]
        assert "$context_relations" in cypher
        assert "$event_relations" in cypher


class TestD124EventParties:
    """D-124 #2 — template bổ sung "các bên liên quan"."""

    def test_event_parties_template_exists(self) -> None:
        """Template `event_parties` phải tồn tại."""
        assert "event_parties" in _INTENT_TEMPLATES

    def test_event_parties_uses_party_relations(self) -> None:
        """Template phải lọc theo `party_relations` (chỉ huy / bên tham chiến)."""
        cypher = _INTENT_TEMPLATES["event_parties"]["cypher"]
        assert "$party_relations" in cypher
        assert "n2 <> e" in cypher


class TestD124LinkageArtifactFilter:
    """D-124 #3 — loại tên rác do liên kết entity."""

    def test_artifact_edge_is_filtered(self) -> None:
        """Cạnh có tên "Chuẩn đề đốc Page" phải bị loại."""
        edges = [
            {
                "relation": "chi_huy_tran",
                "source_name": "Trận Định Tường (1861)",
                "target_name": "Chuẩn đề đốc Page",
            },
            {
                "relation": "chi_huy_tran",
                "source_name": "Trận Định Tường (1861)",
                "target_name": "Nguyễn Công Nhàn",
            },
        ]
        kept = filter_noisy_edges(edges)
        assert len(kept) == 1
        assert kept[0]["target_name"] == "Nguyễn Công Nhàn"

    def test_normal_names_are_kept(self) -> None:
        """Tên bình thường phải được giữ."""
        edges = [
            {
                "relation": "chi_huy_tran",
                "source_name": "Trận Hà Hồi",
                "target_name": "Trương Triều Long",
            }
        ]
        assert len(filter_noisy_edges(edges)) == 1

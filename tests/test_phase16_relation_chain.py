"""Test cho D-120 — truy vấn **chuỗi quan hệ** (2-hop) trên KG.

Bối cảnh
---------
Đo được 17/11/2026 trên 40 câu `multi_hop` của `data/eval/qa_rag_250.jsonl`:

| Bước                                  | Kết quả        |
|---------------------------------------|----------------|
| Đáp án có trong KG **1-hop**          | **0 / 40**     |
| Đáp án có trong KG **2-hop gia đình** | **40 / 40**    |

⇒ thiếu đúng **một bước**: đi 2-hop theo **vai trò** quan hệ.

Các test ở đây **không cần Neo4j** (dùng Cypher giả lập) để chạy nhanh và
ổn định trong CI.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.qa.relation_chain import (  # noqa: E402
    ChainSpec,
    build_chain_cypher,
    evidence_score,
    parse_chain,
    resolve_anchor,
    resolve_chains,
    role_score,
    strip_accents,
)


class TestParseChain:
    """Phân tích chuỗi quan hệ trong câu hỏi tiếng Việt."""

    @pytest.mark.parametrize(
        ("question", "roles", "anchor"),
        [
            (
                "Cha của cha Huyền Trân Công chúa là ai?",
                ["cha_cua", "cha_cua"],
                "huyen tran cong chua",
            ),
            (
                "Mẹ của mẹ Nguyễn Phúc Miên Điều là ai?",
                ["me_cua", "me_cua"],
                "nguyen phuc mien dieu",
            ),
            (
                "Vợ của cha Nguyễn Phúc Miên Lương là ai?",
                ["vo_cua", "cha_cua"],
                "nguyen phuc mien luong",
            ),
            (
                "Cha của cha Lý Long Tường là ai?",
                ["cha_cua", "cha_cua"],
                "ly long tuong",
            ),
        ],
    )
    def test_parse(
        self,
        question: str,
        roles: list[str],
        anchor: str,
    ) -> None:
        """Chuỗi quan hệ được nhận diện đúng vai trò + chủ thể."""
        spec = parse_chain(question)
        assert spec is not None
        assert spec.roles == roles
        assert spec.anchor_text == anchor

    def test_parse_single_relation_returns_none(self) -> None:
        """Câu hỏi **1 quan hệ** không phải chuỗi ⇒ `None`."""
        assert parse_chain("Ai là cha của Lê Lợi?") is None

    def test_parse_no_relation_returns_none(self) -> None:
        """Câu hỏi tự do không có quan hệ ⇒ `None`."""
        assert parse_chain("Kể lại diễn biến trận Bạch Đằng.") is None

    def test_parse_ignores_accents(self) -> None:
        """Không dấu / có dấu cho cùng kết quả."""
        with_accents = parse_chain("Cha của cha Lê Hiển Tông là ai?")
        without = parse_chain("cha cua cha le hien tong la ai?")
        assert with_accents is not None and without is not None
        assert with_accents.roles == without.roles
        assert with_accents.anchor_text == without.anchor_text

    def test_parse_all_40_multi_hop(self) -> None:
        """Toàn bộ câu `multi_hop` của bộ đánh giá đều parse được."""
        import json

        path = ROOT / "data" / "eval" / "qa_rag_250.jsonl"
        if not path.exists():
            pytest.skip("bộ câu hỏi đánh giá không có sẵn")
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        multi_hop = [row for row in rows if row.get("type") == "multi_hop"]
        assert multi_hop, "bộ đánh giá phải có câu multi_hop"
        parsed = [parse_chain(row["question"]) for row in multi_hop]
        assert all(spec is not None for spec in parsed)


class TestHopRoles:
    """Thứ tự vai trò theo **bước đi** trên KG."""

    def test_roles_reversed_for_hop(self) -> None:
        """"Vợ của cha X" ⇒ bước đi đầu là `cha_cua`, sau là `vo_cua`."""
        spec = parse_chain("Vợ của cha Nguyễn Phúc Miên Lương là ai?")
        assert spec is not None
        assert spec.roles == ["vo_cua", "cha_cua"]
        assert spec.hop_roles == ["cha_cua", "vo_cua"]

    def test_same_roles_symmetric(self) -> None:
        """"Cha của cha" ⇒ thứ tự không đổi."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        assert spec.hop_roles == spec.roles

    def test_descriptor(self) -> None:
        """Mô tả chuỗi theo thứ tự văn bản."""
        spec = parse_chain("Vợ của cha Nguyễn Phúc Miên Lương là ai?")
        assert spec is not None
        assert spec.descriptor == "vợ của cha"


class TestResolveAnchor:
    """Chọn entity gốc của chuỗi."""

    def test_prefers_entity_inside_anchor(self) -> None:
        """Entity có tên nằm trong `anchor_text` được ưu tiên."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        linked = [
            ("Trần Nhân Tông", "ent_tran_nhan_tong", "Trần Nhân Tông"),
            (
                "Huyền Trân Công chúa",
                "ent_huyen_tran_cong_chua",
                "Huyền Trân Công chúa",
            ),
        ]
        entity_id, name = resolve_anchor(spec, linked)
        assert entity_id == "ent_huyen_tran_cong_chua"
        assert name == "Huyền Trân Công chúa"

    def test_falls_back_to_first(self) -> None:
        """Không entity nào khớp ⇒ lấy entity đầu tiên."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        linked = [("X", "ent_x", "X")]
        entity_id, _name = resolve_anchor(spec, linked)
        assert entity_id == "ent_x"

    def test_no_entity(self) -> None:
        """Không có entity ⇒ trả rỗng."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        assert resolve_anchor(spec, []) == ("", "")


class TestBuildChainCypher:
    """Sinh Cypher cho chuỗi 2–3 hop."""

    def test_two_hop(self) -> None:
        """Cypher 2 hop có 2 quan hệ + `LIMIT`."""
        cypher = build_chain_cypher(2)
        assert "r1" in cypher and "r2" in cypher
        assert "r3" not in cypher
        assert "LIMIT $limit" in cypher
        assert "$t1" in cypher and "$t2" in cypher

    def test_three_hop(self) -> None:
        """Cypher 3 hop có 3 quan hệ."""
        cypher = build_chain_cypher(3)
        assert "r3" in cypher
        assert "$t3" in cypher

    def test_rejects_single_hop(self) -> None:
        """`hop_count < 2` bị từ chối."""
        with pytest.raises(ValueError):
            build_chain_cypher(1)


def _record(
    h1s: tuple[str, str],
    h1t: tuple[str, str],
    h1_rel: str,
    h2s: tuple[str, str],
    h2t: tuple[str, str],
    h2_rel: str,
) -> dict[str, Any]:
    """Dựng record Cypher giả lập (2 hop).

    Args:
        h1s: (id, tên) nguồn cạnh 1.
        h1t: (id, tên) đích cạnh 1.
        h1_rel: Nhãn quan hệ cạnh 1.
        h2s: (id, tên) nguồn cạnh 2.
        h2t: (id, tên) đích cạnh 2.
        h2_rel: Nhãn quan hệ cạnh 2.

    Returns:
        Record dict.
    """
    return {
        "h1s_id": h1s[0], "h1s_name": h1s[1],
        "h1t_id": h1t[0], "h1t_name": h1t[1],
        "h1_rel": h1_rel, "h1_evidence": "Cha: X", "h1_url": "u1",
        "h2s_id": h2s[0], "h2s_name": h2s[1],
        "h2t_id": h2t[0], "h2t_name": h2t[1],
        "h2_rel": h2_rel, "h2_evidence": "Cha: Y", "h2_url": "u2",
    }


class TestResolveChains:
    """Giải chuỗi trên record Cypher giả lập."""

    def test_cha_cua_cha_cua(self) -> None:
        """"Cha của cha" ⇒ 2 bước `cha_cua`."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        record = _record(
            ("ent_chua", "Huyền Trân Công chúa"),
            ("ent_cha", "Trần Nhân Tông"),
            "cha_cua",
            ("ent_cha", "Trần Nhân Tông"),
            ("ent_ong", "Trần Thánh Tông"),
            "cha_cua",
        )
        chains = resolve_chains(
            spec, [record], anchor_id="ent_chua", anchor_name="Huyền Trân Công chúa"
        )
        assert len(chains) == 1
        assert chains[0]["answer"] == "Trần Thánh Tông"
        assert "Trần Thánh Tông" in chains[0]["statement"]
        # Kết luận phải nói đúng vai trò.
        assert "cha của cha" in chains[0]["conclusion"]

    def test_vo_cua_cha_cua_order(self) -> None:
        """"Vợ của cha" ⇒ bước 1 đi theo `cha_cua`, bước 2 theo `vo_cua`."""
        spec = parse_chain("Vợ của cha Nguyễn Phúc Miên Lương là ai?")
        assert spec is not None
        record = _record(
            ("ent_x", "Nguyễn Phúc Miên Lương"),
            ("ent_cha", "Minh Mạng"),
            "cha_cua",
            ("ent_cha", "Minh Mạng"),
            ("ent_vo", "Hồ Thị Hoa"),
            "vo_cua",
        )
        chains = resolve_chains(
            spec, [record], anchor_id="ent_x", anchor_name="Nguyễn Phúc Miên Lương"
        )
        assert len(chains) == 1
        assert chains[0]["answer"] == "Hồ Thị Hoa"
        assert chains[0]["steps"][0]["role"] == "cha_cua"
        assert chains[0]["steps"][1]["role"] == "vo_cua"

    def test_wrong_relation_rejected(self) -> None:
        """Cạnh không khớp vai trò bị loại."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        record = _record(
            ("ent_chua", "Huyền Trân Công chúa"),
            ("ent_cha", "Trần Nhân Tông"),
            "cha_cua",
            ("ent_cha", "Trần Nhân Tông"),
            ("ent_x", "Không liên quan"),
            "ke_vi",
        )
        chains = resolve_chains(
            spec, [record], anchor_id="ent_chua", anchor_name="Huyền Trân Công chúa"
        )
        assert chains == []

    def test_anchor_must_match(self) -> None:
        """Chuỗi không bắt đầu từ entity gốc bị loại."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        record = _record(
            ("ent_khac", "Người Khác"),
            ("ent_cha", "Trần Nhân Tông"),
            "cha_cua",
            ("ent_cha", "Trần Nhân Tông"),
            ("ent_ong", "Trần Thánh Tông"),
            "cha_cua",
        )
        chains = resolve_chains(
            spec, [record], anchor_id="ent_chua", anchor_name="Huyền Trân Công chúa"
        )
        assert chains == []

    def test_dedupe(self) -> None:
        """Cùng một đường đi chỉ giữ 1."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        record = _record(
            ("ent_chua", "Huyền Trân Công chúa"),
            ("ent_cha", "Trần Nhân Tông"),
            "cha_cua",
            ("ent_cha", "Trần Nhân Tông"),
            ("ent_ong", "Trần Thánh Tông"),
            "cha_cua",
        )
        chains = resolve_chains(
            spec, [record, record], anchor_id="ent_chua", anchor_name="Huyền Trân Công chúa"
        )
        assert len(chains) == 1

    def test_statement_is_declarative(self) -> None:
        """Mệnh đề dùng dạng khai báo (không mũi tên) ⇒ không đọc ngược."""
        spec = parse_chain("Cha của cha Huyền Trân Công chúa là ai?")
        assert spec is not None
        record = _record(
            ("ent_chua", "Huyền Trân Công chúa"),
            ("ent_cha", "Trần Nhân Tông"),
            "cha_cua",
            ("ent_cha", "Trần Nhân Tông"),
            ("ent_ong", "Trần Thánh Tông"),
            "cha_cua",
        )
        chains = resolve_chains(
            spec, [record], anchor_id="ent_chua", anchor_name="Huyền Trân Công chúa"
        )
        statement = chains[0]["statement"]
        assert "là cha của" in statement
        # Nhãn quan hệ **không** dùng mũi tên (chỉ đường đi mới dùng).
        assert "cha của →" not in statement


class TestScoring:
    """Điểm khớp vai trò + điểm bằng chứng (dùng để xếp hạng chuỗi)."""

    def test_role_score_prefers_exact(self) -> None:
        """Nhãn khớp chính xác điểm cao hơn nhãn lạ."""
        exact = role_score("cha_cua", "cha_cua")
        other = role_score("cha_cua", "me_cua")
        assert exact > other

    def test_role_score_me_prefers_me(self) -> None:
        """Vai trò "mẹ" ưu tiên nhãn `me_cua`."""
        assert role_score("me_cua", "me_cua") > role_score("me_cua", "cha_cua")

    def test_role_score_unknown(self) -> None:
        """Nhãn không khớp ⇒ điểm 0."""
        assert role_score("vo_cua", "cha_cua") == 0

    def test_evidence_prefix_bonus(self) -> None:
        """Bằng chứng có tiền tố khớp nhãn ⇒ điểm cao."""
        with_prefix = evidence_score("cha_cua", "Cha: Trần Nhân Tông", "Trần Nhân Tông")
        without = evidence_score("cha_cua", "Con trai của vua X", "Trần Nhân Tông")
        assert with_prefix > without

    def test_evidence_name_bonus(self) -> None:
        """Bằng chứng nhắc đích danh ⇒ được thưởng."""
        named = evidence_score("vo_cua", "Bà là vợ của X", "Bà")
        unnamed = evidence_score("vo_cua", "Một số nguồn nói về việc này", "Bà")
        assert named > unnamed

    def test_evidence_queen_bonus(self) -> None:
        """Bằng chứng nhắc "Hoàng hậu" (vợ chính) ⇒ được thưởng.

        So sánh **cùng điều kiện tiền tố** để chỉ đo riêng bonus "Hoàng hậu".
        """
        queen = evidence_score(
            "vo_cua", "Ông sinh năm 1807, mẹ là Tá Thiên Nhân Hoàng hậu Hồ Thị Hoa", "Hồ Thị Hoa"
        )
        plain = evidence_score(
            "vo_cua", "Ông sinh năm 1807, mẹ là Nguyễn Thị Bân", "Nguyễn Thị Bân"
        )
        assert queen > plain

    def test_evidence_score_zero_for_empty(self) -> None:
        """Bằng chứng rỗng ⇒ điểm 0."""
        assert evidence_score("cha_cua", "", "X") == 0


class TestStripAccents:

    def test_strip(self) -> None:
        """Bỏ dấu + hạ chữ thường."""
        assert strip_accents("Trần Nhân Tông") == "tran nhan tong"

    def test_strip_dao(self) -> None:
        """Chữ `đ` không phải dấu phụ ⇒ phải thay thủ công."""
        assert strip_accents("Nguyễn Phúc Miên Điều") == "nguyen phuc mien dieu"

    def test_whitespace(self) -> None:
        """Gộp khoảng trắng liên tiếp."""
        assert strip_accents("A   B") == "a b"


class TestChainSpecDataclass:
    """Dataclass `ChainSpec`."""

    def test_defaults(self) -> None:
        """Giá trị mặc định rỗng."""
        spec = ChainSpec()
        assert spec.roles == []
        assert spec.anchor_text == ""
        assert spec.hop_roles == []

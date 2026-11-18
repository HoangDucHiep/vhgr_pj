"""Test cho D-132 — `compact_context` **không** cắt mất phần KG.

Bối cảnh: context của arm B gồm `### VĂN BẢN TỪ WIKIPEDIA` rồi tới
`### DỮ LIỆU ĐỒ THỊ (Knowledge Graph)`. Nếu cắt theo thứ tự, khi trần
`total` bị đạt ở giữa phần văn bản ⇒ **toàn bộ phần KG biến mất** ⇒ judge
không nhìn thấy thông tin KG của arm B ⇒ phép so sánh **lệch có lợi cho
arm A** (đo được: ở `total = 2.200` mất KG ở 35/37 câu).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.evaluate_rag import compact_context

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = REPO_ROOT / "data" / "eval" / "eval_d124_checkpoint.jsonl.bak"

KG_MARKER = "### DỮ LIỆU ĐỒ THỊ"


def _sample_contexts() -> list[str]:
    """Lấy các context có phần KG từ checkpoint D-124 (nếu có)."""
    if not CHECKPOINT.exists():
        return []
    out: list[str] = []
    for line in CHECKPOINT.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        context = str((row.get("B") or {}).get("arm", {}).get("context") or "")
        if KG_MARKER in context:
            out.append(context)
    return out


class TestCompactContextKeepsGraph:
    """D-132 — phần KG phải **luôn** còn trong context nén."""

    def test_context_rong_tra_ve_chuoi_rong(self) -> None:
        """Context rỗng ⇒ trả về chuỗi rỗng."""
        assert compact_context("", total=2200) == ""

    def test_context_khong_kg_bi_cat_binh_thuong(self) -> None:
        """Context chỉ có văn bản ⇒ vẫn cắt theo trần như cũ."""
        context = "\n\n".join(f"[{i}] " + ("x" * 500) for i in range(1, 30))
        out = compact_context(context, per_block=600, total=2200)
        assert out
        assert len(out) <= 2200

    def test_phan_kg_duoc_giu(self) -> None:
        """Context có KG ⇒ phần KG **luôn** còn sau khi nén."""
        context = (
            "### VĂN BẢN TỪ WIKIPEDIA\n\n"
            + "\n\n".join(f"[{i}] " + ("v" * 400) for i in range(1, 20))
            + "\n\n"
            + KG_MARKER
            + " (Knowledge Graph)\n\n"
            + "\n\n".join(f"[{i}] A — chỉ huy → B" for i in range(20, 30))
        )
        for total in (1200, 2200, 6000, 9000):
            out = compact_context(context, total=total)
            assert KG_MARKER in out, f"mất KG ở total={total}"
            assert "chỉ huy" in out, f"mất cạnh KG ở total={total}"

    def test_khong_vuot_tran(self) -> None:
        """Kết quả nén **không** vượt trần `total`."""
        context = (
            "### VĂN BẢN TỪ WIKIPEDIA\n\n"
            + "\n\n".join(f"[{i}] " + ("v" * 900) for i in range(1, 40))
            + "\n\n"
            + KG_MARKER
            + " (Knowledge Graph)\n\n"
            + "\n\n".join(f"[{i}] A — chỉ huy → B" for i in range(40, 60))
        )
        for total in (1200, 2200, 6000, 9000):
            assert len(compact_context(context, total=total)) <= total

    def test_giu_kg_tren_du_lieu_that(self) -> None:
        """Trên dữ liệu thật (43 câu D-124): **không** câu nào mất KG."""
        contexts = _sample_contexts()
        if not contexts:
            pytest.skip("không có checkpoint D-124 (bản .bak)")
        for total in (2200, 9000):
            for context in contexts:
                out = compact_context(context, total=total)
                assert KG_MARKER in out, f"mất KG ở total={total}"
                tail = out.split(KG_MARKER)[-1]
                assert ("—" in tail) or ("→" in tail), f"mất cạnh KG ở total={total}"

    def test_van_ban_bi_cat_truoc_khi_kg(self) -> None:
        """Phần văn bản bị cắt **trước** phần KG (KG được ưu tiên)."""
        context = (
            "### VĂN BẢN TỪ WIKIPEDIA\n\n"
            + "\n\n".join(f"[{i}] " + ("v" * 400) for i in range(1, 30))
            + "\n\n"
            + KG_MARKER
            + " (Knowledge Graph)\n\n"
            + "\n\n".join(f"[{i}] A — chỉ huy → B" for i in range(30, 40))
        )
        out = compact_context(context, total=1200)
        assert KG_MARKER in out
        # Số khối văn bản còn lại phải **ít hơn** số khối KG còn lại.
        text_part, _, kg_part = out.partition(KG_MARKER)
        assert text_part.count("\n[") < kg_part.count("\n[")

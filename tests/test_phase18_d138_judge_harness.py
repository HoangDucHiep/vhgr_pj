"""Test cho D-138 — sửa 2 artefact của harness khiến arm B bị trừ điểm oan.

Bối cảnh
---------
Sau khi chạy đủ 60 câu narrative với D-134 (giữ phần KG trong context) và
chấm lại với **cùng** ngân sách context (9.000 ký tự) như baseline D-123,
kết quả vẫn cho thấy arm B thua arm A. Điều tra 2 nguyên nhân **không nằm
ở kiến trúc** mà ở **harness**:

1. **Judge đọc ngược chiều cạnh KG.** Context arm B hiển thị cạnh theo dạng
   ``A — quan hệ → B`` (chủ thể → đối tượng) nhưng prompt judge **không**
   giải thích quy ước đó ⇒ judge tưởng "Ngô Văn Sở chỉ huy trận Hà Hồi" là
   sai ⇒ chấm ``faithfulness = 0`` với lý do *"thông tin về chỉ huy không có
   trong ngữ cảnh"* ⇒ **7/60** câu arm B bị trừ oan.

2. **`compact_context()` cắt mất khối đã được trích dẫn.** Câu trả lời
   trích dẫn ``[n]``; nếu khối ``[n]`` bị cắt khỏi context ⇒ judge thấy
   trích dẫn "không tồn tại" ⇒ ``citation_precision = 0`` ⇒ điểm giả.
   Đo được: **7/60** câu arm B (arm B có context dài nhất ⇒ hay bị cắt nhất).

Test ở đây kiểm tra **hành vi của harness**, không gọi LLM thật.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.evaluate_rag import (  # noqa: E402
    JUDGE_PROMPT,
    compact_context,
)

KG_MARKER = "### DỮ LIỆU ĐỒ THỊ (Knowledge Graph)"


def _make_context(n_blocks: int = 30, *, with_kg: bool = True) -> str:
    """Dựng context giả có `n_blocks` khối `[n]` (văn bản + KG)."""
    text_blocks = []
    for i in range(1, n_blocks + 1):
        text_blocks.append(
            f"[{i}] Sự kiện {i} > Diễn biến\n"
            + ("Nội dung văn bản mô tả diễn biến sự kiện. " * 40)
        )
    head = "### VĂN BẢN TỪ WIKIPEDIA\n\n" + "\n\n".join(text_blocks)
    if not with_kg:
        return head
    kg_blocks = []
    for i in range(n_blocks + 1, n_blocks + 21):
        kg_blocks.append(
            f"[{i}] Trận X — chỉ huy trận → Người {i}\n"
            f"Bằng chứng: Chỉ huy: Người {i}\n"
            f"    Nguồn: https://vi.wikipedia.org/wiki/Trận_X"
        )
    return head + "\n\n" + KG_MARKER + "\n\n" + "\n\n".join(kg_blocks)


class TestJudgePromptReadsKgDirection:
    """Prompt judge **phải** giải thích quy ước chiều của cạnh KG (D-138)."""

    def test_prompt_mentions_kg_marker(self) -> None:
        """Prompt phải nhắc tới phần "DỮ LIỆU ĐỒ THỊ"."""
        assert "DỮ LIỆU ĐỒ THỊ" in JUDGE_PROMPT

    def test_prompt_explains_direction(self) -> None:
        """Prompt phải nói rõ quan hệ đọc theo hướng chủ thể → đối tượng."""
        assert "chủ thể" in JUDGE_PROMPT
        assert "đối tượng" in JUDGE_PROMPT

    def test_prompt_warns_against_reverse_reading(self) -> None:
        """Prompt phải cấm kết luận "không có trong ngữ cảnh" do đọc ngược."""
        assert "KHÔNG" in JUDGE_PROMPT
        assert "hướng ngược" in JUDGE_PROMPT

    def test_prompt_keeps_original_rules(self) -> None:
        """Các quy tắc gốc vẫn còn nguyên."""
        assert "correctness" in JUDGE_PROMPT
        assert "faithfulness" in JUDGE_PROMPT
        assert "citation_precision" in JUDGE_PROMPT
        assert "scores" in JUDGE_PROMPT


class TestCompactContextKeepsCitedBlocks:
    """`compact_context()` phải **giữ** khối đã được trích dẫn (D-138)."""

    def test_keeps_cited_index(self) -> None:
        """Khối đã trích dẫn phải còn trong context nén."""
        context = _make_context(n_blocks=40)
        compressed = compact_context(context, per_block=200, total=9000)
        kept = {int(m) for m in re.findall(r"(?m)^\[(\d+)\]", compressed)}
        assert 60 in kept  # khối KG cuối cùng, chỉ giữ được nhờ keep_indices

    def test_all_cited_indices_preserved(self) -> None:
        """Mọi chỉ số được trích dẫn đều phải tồn tại sau khi nén."""
        context = _make_context(n_blocks=40)
        cited = {5, 17, 33, 47, 60}
        compressed = compact_context(
            context, per_block=200, total=9000, keep_indices=cited
        )
        kept = {int(m) for m in re.findall(r"(?m)^\[(\d+)\]", compressed)}
        assert cited <= kept

    def test_keeps_cited_blocks_for_every_arm(self) -> None:
        """Áp dụng cho cả 3 arm (mô phỏng vòng lặp judge)."""
        context = _make_context(n_blocks=30)
        for cited in ({3, 12}, {20, 44}, {1, 50}):
            compressed = compact_context(
                context, per_block=200, total=9000, keep_indices=cited
            )
            kept = {int(m) for m in re.findall(r"(?m)^\[(\d+)\]", compressed)}
            assert cited <= kept, f"mất trích dẫn {cited - kept}"

    def test_without_keep_indices_kg_still_kept(self) -> None:
        """D-134: phần KG vẫn được giữ khi không truyền `keep_indices`."""
        context = _make_context(n_blocks=40)
        compressed = compact_context(context, per_block=200, total=9000)
        assert KG_MARKER in compressed

    def test_budget_respected(self) -> None:
        """Không vượt trần ký tự."""
        context = _make_context(n_blocks=60)
        compressed = compact_context(
            context, per_block=200, total=9000, keep_indices={61, 62}
        )
        assert len(compressed) <= 9000

    def test_empty_context(self) -> None:
        """Context rỗng ⇒ trả chuỗi rỗng (không lỗi)."""
        assert compact_context("", keep_indices={1}) == ""

    def test_no_kg_context(self) -> None:
        """Context không có phần KG ⇒ vẫn nén bình thường."""
        context = _make_context(n_blocks=10, with_kg=False)
        compressed = compact_context(
            context, per_block=200, total=9000, keep_indices={3}
        )
        assert "[3]" in compressed
        assert KG_MARKER not in compressed


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

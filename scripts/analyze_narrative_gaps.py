#!/usr/bin/env python
"""Phân tích **nguyên nhân** arm B còn thua arm A trên nhóm câu hỏi `narrative`.

Vì sao cần script này?
----------------------
Sau D-123, arm B vẫn bằng hoặc thua arm A ở một số câu. Cần **đo đạc**
nguyên nhân thay vì đoán. Hai giả thuyết chính:

1. **KG thiếu người chỉ huy thật** — bài Wikipedia nói "Quang Trung cho quân
   vây chặt đồn" nhưng KG chỉ có `chi_huy_tran` tới Ngô Văn Sở / Phan Văn Lân
   ⇒ LLM trả đúng theo KG nhưng **sai theo bài** ⇒ judge trừ điểm.
2. **KG thêm quan hệ không liên quan tới diễn biến** (hop-2) cho sự kiện mà
   văn bản **không** mô tả ⇒ LLM kể chuyện từ dữ liệu KG ⇒ judge chấm
   "bịa thông tin ngoài ngữ cảnh" ⇒ `faithfulness = 0`.

Cách dùng:
    python scripts/analyze_narrative_gaps.py data/eval/eval_d123_checkpoint.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHECKPOINT = REPO_ROOT / "data" / "eval" / "eval_d123_checkpoint.jsonl"

#: Từ khoá nhận diện người chỉ huy trong **đáp án chuẩn**.
COMMANDER_HINT = re.compile(
    r"(chỉ huy|do\s+\w+\s+\w+\s+\w+\s*(?:chỉ huy|đứng đầu|trực tiếp chỉ huy))",
    re.IGNORECASE,
)


def load_rows(path: Path) -> list[dict]:
    """Đọc checkpoint eval.

    Args:
        path: Đường dẫn file checkpoint.

    Returns:
        Danh sách record.
    """
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def kg_lines(context: str) -> list[str]:
    """Trích các dòng quan hệ KG trong context đã format.

    Args:
        context: Context đã format của arm B.

    Returns:
        Danh sách dòng "A — quan hệ → B".
    """
    out = []
    for line in context.splitlines():
        if " — " in line and "→" in line:
            out.append(line.strip())
    return out


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    checkpoint = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CHECKPOINT
    if not checkpoint.is_absolute() and not checkpoint.exists():
        checkpoint = REPO_ROOT / checkpoint
    rows = load_rows(checkpoint)
    if not rows:
        print(f"Không có dữ liệu tại {checkpoint}")
        return 1

    wins = losses = ties = 0
    print("=== A. CÂU HỎI B THẮNG / THUA / HÒA ===\n")
    for record in rows:
        a = int(record["A"]["judge"]["correctness"])
        b = int(record["B"]["judge"]["correctness"])
        if b > a:
            wins += 1
        elif b < a:
            losses += 1
        else:
            ties += 1
    print(f"B thắng A: {wins} · B thua A: {losses} · hòa: {ties} (tổng {len(rows)})")

    # ------------------------------------------------------------------
    # Nguyên nhân 1: judge nói "bịa" / "sai" ⇒ nội dung KG lệch bài.
    # ------------------------------------------------------------------
    print("\n=== B. LÝ DO JUDGE TRỪ ĐIỂM CỦA ARM B ===\n")
    reasons: dict[str, int] = {}
    for record in rows:
        reason = str(record["B"]["judge"].get("reason") or "").lower()
        for key, needle in (
            ("bịa (ngoài ngữ cảnh)", "bịa"),
            ("sai (sự kiện/chỉ huy)", "sai "),
            ("thiếu thông tin", "thiếu"),
            ("không đầy đủ", "không đầy đủ"),
            ("trích dẫn không hỗ trợ", "trích dẫn không hỗ trợ"),
        ):
            if needle in reason:
                reasons[key] = reasons.get(key, 0) + 1
    for key, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {key:32s} {count:3d} câu")

    # ------------------------------------------------------------------
    # Nguyên nhân 2: hop-2 lấp đầy context bằng quan hệ **không** thuộc
    # sự kiện đang hỏi (vd "Nhà Thanh — tham gia trận → Trận Ngọc Hồi").
    # ------------------------------------------------------------------
    print("\n=== C. ĐỘ NHIỄU CỦA CÁC CẠNH HOP-2 TRONG CONTEXT KG ===\n")
    total_edges = 0
    off_anchor = 0
    per_record: list[tuple[str, int, int]] = []
    for record in rows:
        context = str(record["B"]["arm"].get("context") or "")
        question = str(record["A"]["question"])
        edges = kg_lines(context)
        if not edges:
            continue
        # Cạnh "off-anchor" = quan hệ mà **không** liên quan tới chủ thể
        # của câu hỏi (vd không chứa tên sự kiện trong câu hỏi).
        key_tokens = [
            tok
            for tok in re.findall(r"[A-ZĐÁÀẢÃẠÂẤẦẨẪẬĂẰẮẲẴẶẮÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ][\wÀ-ỹđ]+", question)
            if len(tok) > 3
        ]
        off = 0
        for edge in edges:
            if not any(token in edge for token in key_tokens):
                off += 1
        total_edges += len(edges)
        off_anchor += off
        per_record.append((str(record["qid"]), len(edges), off))
    if total_edges:
        print(f"  Tổng cạnh KG trong 60 câu: {total_edges}")
        print(f"  Cạnh KHÔNG chứa từ khoá chủ thể: {off_anchor} "
              f"({off_anchor / total_edges:.1%})")
    worst = sorted(per_record, key=lambda item: -item[2])[:8]
    print("\n  8 câu nhiễu nặng nhất (qid, tổng cạnh, cạnh nhiễu):")
    for qid, total, off in worst:
        print(f"    {qid}: {total:3d} cạnh, {off:3d} nhiễu ({off / max(total, 1):.0%})")

    # ------------------------------------------------------------------
    # Nguyên nhân 3: bài chuẩn có nhắc người chỉ huy mà KG **không** có.
    # ------------------------------------------------------------------
    print("\n=== D. NGƯỜI CHỈ HUY TRONG ĐÁP ÁN CHUẨN CÓ TRONG KG KHÔNG ===\n")
    missing = 0
    checked = 0
    for record in rows:
        expected = str(record["A"].get("expected_answer") or "")
        context = str(record["B"]["arm"].get("context") or "")
        if not expected or not context:
            continue
        # Tên riêng Việt Nam trong đáp án chuẩn (2–4 từ, viết hoa).
        names = re.findall(
            r"\b[A-ZĐÁÀẢÃẠÂẤẦẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ][\wÀ-ỹđ]+"
            r"(?:\s+[A-ZĐÁÀẢÃẠÂẤẦẨẪẬĂẰẮẲẴẶÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ][\wÀ-ỹđ]+){1,3}\b",
            expected,
        )
        names = [n for n in names if len(n) > 5]
        if not names:
            continue
        checked += 1
        absent = [n for n in names if n not in context]
        if absent:
            missing += 1
            print(f"  {record['qid']} — thiếu trong KG: {', '.join(absent[:3])}")
    print(f"\n  {missing}/{checked} câu có ít nhất một tên trong đáp án chuẩn "
          f"mà KHÔNG xuất hiện trong context KG")

    return 0


if __name__ == "__main__":
    sys.exit(main())

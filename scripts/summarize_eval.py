#!/usr/bin/env python
"""Tổng hợp kết quả eval Phase 19 — 4 nhóm × 3 arm + latency + grounding (19.i).

Vì sao cần script riêng?
------------------------
`summarize_narrative_eval.py` (Phase 18) chỉ tổng hợp **nhóm narrative** và
**không** đo:
- **grounding bằng code** (19.i): mỗi **mệnh đề** trong câu trả lời phải khớp
  ≥1 chunk context **được trích dẫn** ⇒ tỉ lệ "mệnh đề không có căn cứ".
- **latency p50/p95 theo từng arm** (§6): checkpoint cũ gộp latency của cả 3 arm.
- số liệu **4 nhóm** (`relational`, `narrative`, `multi_hop`, `multi_turn`) +
  `no_data` (G19-4).

Grounding **không** dùng LLM (theo chỉ đạo: không tin LLM-judge nói "đúng") ⇒
đo bằng **trùng token** giữa từng mệnh đề của câu trả lời và các khối context
mà câu trả lời **đã trích dẫn** (`[n]`).

Cách dùng
---------
```bash
python scripts/summarize_eval.py \
    --checkpoint data/eval/eval_phase19_checkpoint.jsonl \
    --label Phase-19 \
    --out reports/phase19_summary.json
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from statistics import mean, median

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Các arm trong mọi checkpoint.
ARMS = ("A", "B", "B-")

#: Nhóm câu hỏi (thứ tự hiển thị trong báo cáo).
GROUPS = ("relational", "narrative", "multi_hop", "multi_turn", "no_data")

#: Mẫu nhận diện câu trả lời "không có trong dữ liệu".
NOT_IN_DATA_PATTERN = re.compile(
    r"không có (?:trong |bất kỳ )?dữ liệu|không tìm thấy (?:thông tin )?dữ liệu"
    r"|dữ liệu (?:hiện có )?không (?:có |chứa )?(?:thông tin )?về",
    re.IGNORECASE,
)

#: Regex tách câu (theo dấu kết thúc câu tiếng Việt).
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

#: Từ dừng tiếng Việt (đủ để đo trùng token không bị nhiễu).
STOPWORDS = frozenset(
    {
        "va", "la", "co", "nhung", "voi", "cho", "trong", "ngoai", "khi", "den",
        "tu", "mot", "nhu", "theo", "ve", "tai", "nam", "nguoi", "vua", "ong",
        "bai", "do", "bi", "de", "thi", "day", "nen", "sau", "truoc", "hai", "ba",
        "gan", "the", "vao", "ra", "len", "xuong", "phia", "giua", "cung", "boi",
        "vi", "nua", "ma", "thu", "dem", "duoi", "tren", "hay", "hoac", "nhieu",
        "it", "cai", "moi", "cac", "co_the", "khong", "chua", "roi", "van", "lai",
        "tua", "da", "se", "dang", "lam", "noi", "rat", "lon", "nho", "ca", "neu",
        "chi", "phai", "muon", "dung", "thuoc", "khu", "toan", "phan", "nhom",
        "tieu", "cua", "la", "cua", "the", "ra", "vao", "co", "va",
    }
)

#: Tỉ lệ trùng token tối thiểu để coi là "mệnh đề có căn cứ".
GROUNDING_OVERLAP_THRESHOLD = 0.34


def _norm(text: str) -> str:
    """Chuẩn hoá chuỗi: bỏ dấu, hạ chữ thường.

    Args:
        text: Chuỗi gốc.

    Returns:
        Chuỗi đã chuẩn hoá.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.replace("đ", "d").lower().split())


def _tokens(text: str) -> list[str]:
    """Tách token đã bỏ dấu + bỏ stopword.

    Args:
        text: Văn bản.

    Returns:
        Danh sách token.
    """
    raw = re.findall(r"[0-9a-zA-ZÀ-ỹĐđ]+", _norm(text))
    return [token for token in raw if token not in STOPWORDS and len(token) > 1]


def _is_not_in_data(answer: str) -> bool:
    """Câu trả lời là "không có trong dữ liệu" hay không.

    Args:
        answer: Câu trả lời.

    Returns:
        ``True`` nếu là câu không có dữ liệu.
    """
    return bool(NOT_IN_DATA_PATTERN.search(answer or ""))


def split_context_blocks(context: str) -> dict[int, str]:
    """Tách context thành map `n` → nội dung khối.

    Args:
        context: Chuỗi context (mỗi khối bắt đầu bằng ``[n]``).

    Returns:
        Dict số thứ tự → nội dung khối.
    """
    blocks: dict[int, str] = {}
    if not context:
        return blocks
    current_n: int | None = None
    buffer: list[str] = []
    for line in context.splitlines():
        match = re.match(r"^\[(\d+)\]\s*(.*)$", line.strip())
        if match:
            if current_n is not None:
                blocks[current_n] = "\n".join(buffer).strip()
            current_n = int(match.group(1))
            buffer = [match.group(2)]
        elif current_n is not None:
            buffer.append(line)
    if current_n is not None:
        blocks[current_n] = "\n".join(buffer).strip()
    return blocks


def grounding_ratio(answer: str, context: str) -> tuple[float, int, int]:
    """Đo **grounding bằng code** (không LLM).

    Mỗi **mệnh đề** của câu trả lời phải khớp ≥1 khối context **được trích dẫn**
    (`[n]` trong câu trả lời) ⇒ nếu không ⇒ mệnh đề **không có căn cứ**.

    Args:
        answer: Câu trả lời.
        context: Context của arm.

    Returns:
        Tuple `(tỉ lệ có căn cứ, số mệnh đề, số mệnh đề không có căn cứ)`.
    """
    blocks = split_context_blocks(context)
    if not blocks:
        return (0.0, 0, 0)
    cited = {
        int(value) for value in re.findall(r"\[(\d+)\]", answer or "")
    }
    cited_blocks = [blocks[n] for n in sorted(cited) if n in blocks]
    if not cited_blocks:
        return (0.0, 0, 0)
    cited_tokens = set()
    for block in cited_blocks:
        cited_tokens |= set(_tokens(block))

    sentences = [
        sentence.strip()
        for sentence in SENTENCE_SPLIT.split(answer or "")
        if sentence.strip() and not re.fullmatch(r"\[\d+\]", sentence.strip())
    ]
    sentences = [s for s in sentences if not _is_not_in_data(s)]
    if not sentences:
        return (1.0, 0, 0)

    n_grounded = 0
    for sentence in sentences:
        tokens = set(_tokens(sentence))
        if not tokens:
            continue
        overlap = len(tokens & cited_tokens) / len(tokens)
        if overlap >= GROUNDING_OVERLAP_THRESHOLD:
            n_grounded += 1
    n_sentences = len(sentences)
    n_unsupported = n_sentences - n_grounded
    return (n_grounded / n_sentences if n_sentences else 0.0, n_sentences, n_unsupported)


def _count_abstain_with_evidence(rows: list[dict], arm: str) -> int:
    """Đếm số câu arm **nói "không có"** dù context **có bằng chứng thật**.

    Vì sao cần?
    ----------
    Đây chính là lỗi của Gate **G19-1**: arm A trả "Không có trong dữ liệu"
    **16/60** câu narrative, trong đó **7/16** câu gold section **vẫn có** trong
    top-8 context ⇒ lỗi ở **tầng sinh**, không phải tầng truy xuất.

    ⚠️ Với câu hỏi **quan hệ/năm**, chỉ so `doc_id` là **chưa đủ** ⇒ phải kiểm
    tra **đáp án có thật sự nằm trong context** không (xem
    `src.evaluation.evaluate_rag.context_has_gold`).

    Args:
        rows: Các bản ghi checkpoint.
        arm: Tên arm ("A"/"B"/"B−").

    Returns:
        Số câu bị đếm là lỗi.
    """
    from src.evaluation.evaluate_rag import context_has_gold  # noqa: PLC0415 — import động

    count = 0
    for row in rows:
        arm_data = row.get(arm)
        if not isinstance(arm_data, dict):
            continue
        if str(row.get("type") or "") == "no_data":
            continue
        arm_result = arm_data.get("arm") or {}
        answer = str(arm_result.get("answer") or "")
        if not (NOT_IN_DATA_PATTERN.search(answer) or "không có" in answer.lower()):
            continue
        if context_has_gold(
            arm_result.get("context_blocks"),
            arm_data.get("evidence_doc_id"),
            arm_data.get("evidence_section"),
            arm_result.get("context"),
            arm_data.get("expected_answer"),
        ):
            count += 1
    return count


def _percentile(values: list[int], pct: float) -> int:
    """Tính phân vị (gần nhất).

    Args:
        values: Danh sách giá trị.
        pct: Phân vị (0–1).

    Returns:
        Giá trị phân vị.
    """
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(pct * len(ordered))) - 1))
    return int(ordered[index])


def summarize(path: Path) -> dict:
    """Tổng hợp 1 checkpoint.

    Args:
        path: File checkpoint JSONL.

    Returns:
        Dict kết quả tổng hợp.
    """
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    out: dict = {
        "checkpoint": str(path),
        "n_questions": len(rows),
        "arms": {},
        "by_group": {},
    }
    for arm in ARMS:
        usable = [
            row
            for row in rows
            if isinstance(row.get(arm), dict)
            and not ((row[arm].get("arm") or {}).get("infrastructure_error"))
        ]
        scores = [
            row[arm]["judge"]
            for row in usable
            if isinstance(row[arm].get("judge"), dict)
            and "correctness" in (row[arm].get("judge") or {})
        ]
        latencies = [
            int((row[arm].get("arm") or {}).get("elapsed_ms") or 0)
            for row in usable
        ]
        not_in_data = sum(
            1
            for row in usable
            if _is_not_in_data(str((row[arm].get("arm") or {}).get("answer") or ""))
        )
        no_data_retried = sum(
            1
            for row in usable
            if (row[arm].get("arm") or {}).get("no_data_retried")
        )
        contradict = sum(
            1 for row in usable if (row[arm].get("judge") or {}).get("contradicts_reference")
        )
        grounding_values: list[float] = []
        n_unsupported_total = 0
        n_sentences_total = 0
        for row in usable:
            answer = str((row[arm].get("arm") or {}).get("answer") or "")
            context = str((row[arm].get("arm") or {}).get("context") or "")
            if not answer.strip() or _is_not_in_data(answer):
                continue
            ratio, n_sent, n_unsup = grounding_ratio(answer, context)
            if n_sent:
                grounding_values.append(ratio)
                n_sentences_total += n_sent
                n_unsupported_total += n_unsup
        out["arms"][arm] = {
            "n": len(usable),
            "correctness": round(mean([s["correctness"] for s in scores]), 3)
            if scores
            else None,
            "faithfulness": round(mean([s["faithfulness"] for s in scores]), 3)
            if scores
            else None,
            "citation_precision": round(
                mean([float(s.get("citation_precision", 0.0)) for s in scores]), 3
            )
            if scores
            else None,
            "not_in_data": not_in_data,
            "no_data_retried": no_data_retried,
            # --- Phase 19 — G19-1: "không có" **dù context có bằng chứng** ---
            "abstain_with_evidence": _count_abstain_with_evidence(rows, arm),
            "contradicts_reference": contradict,
            "latency_p50": int(median(latencies)) if latencies else 0,
            "latency_p95": _percentile(latencies, 0.95),
            "latency_mean": int(mean(latencies)) if latencies else 0,
            # --- Grounding đo bằng code (19.i) ---
            "grounding_mean": round(mean(grounding_values), 4)
            if grounding_values
            else None,
            "n_sentences": n_sentences_total,
            "n_sentences_unsupported": n_unsupported_total,
            "grounding_unsupported_rate": (
                round(n_unsupported_total / n_sentences_total, 4)
                if n_sentences_total
                else None
            ),
            "models": dict(
                Counter(str(row[arm].get("gen_model") or "") for row in usable)
            ),
        }

    # --- Bảng theo nhóm câu hỏi -----------------------------------------
    for group in GROUPS:
        bucket: dict[str, dict] = {}
        for arm in ARMS:
            rows_g = [
                row
                for row in rows
                if isinstance(row.get(arm), dict)
                and str(row[arm].get("type") or "") == group
                and not ((row[arm].get("arm") or {}).get("infrastructure_error"))
            ]
            scores_g = [
                row[arm]["judge"]
                for row in rows_g
                if isinstance(row[arm].get("judge"), dict)
                and "correctness" in (row[arm].get("judge") or {})
            ]
            bucket[arm] = {
                "n": len(rows_g),
                "correctness": round(mean([s["correctness"] for s in scores_g]), 3)
                if scores_g
                else None,
                "faithfulness": round(mean([s["faithfulness"] for s in scores_g]), 3)
                if scores_g
                else None,
                "not_in_data": sum(
                    1
                    for row in rows_g
                    if _is_not_in_data(
                        str((row[arm].get("arm") or {}).get("answer") or "")
                    )
                ),
                "abstain_with_evidence": _count_abstain_with_evidence(rows_g, arm),
                "latency_p50": int(
                    median(
                        [
                            int((row[arm].get("arm") or {}).get("elapsed_ms") or 0)
                            for row in rows_g
                        ]
                    )
                )
                if rows_g
                else 0,
                "latency_p95": _percentile(
                    [
                        int((row[arm].get("arm") or {}).get("elapsed_ms") or 0)
                        for row in rows_g
                    ],
                    0.95,
                ),
            }
        out["by_group"][group] = bucket
    return out


def render_markdown(summary: dict, label: str) -> str:
    """Render bảng Markdown từ kết quả tổng hợp.

    Args:
        summary: Kết quả tổng hợp.
        label: Nhãn checkpoint.

    Returns:
        Chuỗi Markdown.
    """
    lines: list[str] = []
    lines.append(f"## Tổng hợp eval — {label}")
    lines.append("")
    lines.append(
        "| Nhóm | Arm | n | correctness | faithfulness | not_in_data | "
        "abstain+căn cứ | latency p50 (ms) | latency p95 (ms) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for group in GROUPS:
        bucket = summary.get("by_group", {}).get(group, {})
        for arm in ARMS:
            data = bucket.get(arm, {})
            lines.append(
                f"| {group} | {arm} | {data.get('n', 0)} | "
                f"{data.get('correctness', '—')} | {data.get('faithfulness', '—')} | "
                f"{data.get('not_in_data', 0)} | "
                f"{data.get('abstain_with_evidence', 0)} | "
                f"{data.get('latency_p50', 0)} | "
                f"{data.get('latency_p95', 0)} |"
            )
    lines.append("")
    lines.append(
        "| Arm | n | correctness | faithfulness | citeP | grounding (code) | "
        "mệnh đề không căn cứ | not_in_data | abstain+căn cứ | latency p50 | latency p95 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for arm in ARMS:
        data = summary.get("arms", {}).get(arm, {})
        lines.append(
            f"| {arm} | {data.get('n', 0)} | {data.get('correctness', '—')} | "
            f"{data.get('faithfulness', '—')} | {data.get('citation_precision', '—')} | "
            f"{data.get('grounding_mean', '—')} | "
            f"{data.get('n_sentences_unsupported', 0)}/"
            f"{data.get('n_sentences', 0)} | {data.get('not_in_data', 0)} | "
            f"{data.get('abstain_with_evidence', 0)} | "
            f"{data.get('latency_p50', 0)} | "
            f"{data.get('latency_p95', 0)} |"
        )
    return "\n".join(lines)


def main() -> int:
    """Điểm vào CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, help="File checkpoint JSONL.")
    parser.add_argument("--label", default="", help="Nhãn checkpoint.")
    parser.add_argument("--out", default="", help="Ghi kết quả ra file JSON.")
    parser.add_argument("--md", default="", help="Ghi bảng Markdown ra file.")
    args = parser.parse_args()

    summary = summarize(REPO_ROOT / args.checkpoint)
    label = args.label or Path(args.checkpoint).stem
    summary["label"] = label
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    print()
    print(render_markdown(summary, label))
    if args.out:
        out_path = REPO_ROOT / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    if args.md:
        md_path = REPO_ROOT / args.md
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(summary, label) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

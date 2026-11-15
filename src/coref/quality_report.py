"""Báo cáo chất lượng coreference — Phase 6.

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 6 (bước 3 — `quality_report.py`).

Cách chạy
---------
```bash
python -m src.coref.quality_report --config configs/default.yaml
```

Sinh ra:
- `reports/coref_quality.md` — báo cáo dạng Markdown cho người đọc.
- `docs/10-nhat-ky/so-lieu/phase-06-coref-stats.json` — số liệu máy đọc được
  (có `_meta` theo `.cursor/rules/data-contracts.mdc`).

Các kiểm tra bắt buộc (Gate G1, G7)
--------------------------------------
- 100% `canonical_id` có dạng `ent_*` hoặc `null`.
- 100% `text[start:end] == mention["text"]` (offset ký tự Python).
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.common.config import load_config, resolve_path
from src.common.ids import ENTITY_ID_RE
from src.common.logger import get_logger
from src.common.schemas import NER_LABELS, RESOLUTION_METHODS

logger = get_logger(__name__)

#: Ký tự Hán (CJK) — corpus Wikipedia tiếng Việt có trích nguyên văn.
#:
#: Dùng **escape Unicode** (``\uXXXX``) thay vì ký tự thật để file nguồn không
#: chứa tiếng Trung (quy tắc ``.cursor/rules/no-chinese.mdc``).
#: - ``\u3400-\u4DBF`` — CJK Extension A
#: - ``\u4E00-\u9FFF`` — CJK Unified Ideographs
#: - ``\uF900-\uFAFF`` — CJK Compatibility Ideographs
_HAN_RE = re.compile(
    "[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]+"
)

#: Nhãn không tạo node trong 6 loại KG (mốc thời gian → node `Year` riêng).
NON_ENTITY_LABELS: frozenset[str] = frozenset({"TIME"})


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Đọc JSONL vào RAM.

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách record.
    """
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def collect_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Tính toàn bộ số liệu chất lượng.

    Args:
        rows: Các record từ `coref_resolved.jsonl`.

    Returns:
        Dict số liệu (dùng cho cả báo cáo Markdown lẫn file JSON).
    """
    n_sentences = len(rows)
    n_mentions = 0
    n_resolved = 0
    n_bad_id = 0
    n_bad_offset = 0
    n_bad_label = 0
    n_bad_method = 0
    n_non_time = 0
    n_non_time_resolved = 0
    n_sent_has_pronoun = 0
    n_pronoun_resolved = 0
    n_pronoun_total = 0

    by_method: Counter[str] = Counter()
    by_label: Counter[str] = Counter()
    resolved_by_label: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    resolved_by_source: Counter[str] = Counter()

    for row in rows:
        text = str(row.get("text") or "")
        mentions = row.get("mentions") or []
        has_pronoun = False
        for mention in mentions:
            n_mentions += 1
            method = str(mention.get("resolved_by") or "")
            label = str(mention.get("label") or "")
            source = str(mention.get("source") or "")
            canonical_id = mention.get("canonical_id")

            by_method[method] += 1
            by_label[label] += 1
            by_source[source] += 1

            if label not in NER_LABELS:
                n_bad_label += 1
            if method not in RESOLUTION_METHODS:
                n_bad_method += 1

            if canonical_id:
                n_resolved += 1
                resolved_by_label[label] += 1
                resolved_by_source[source] += 1
                if not ENTITY_ID_RE.match(str(canonical_id)):
                    n_bad_id += 1

            start = int(mention.get("start", 0))
            end = int(mention.get("end", 0))
            if text[start:end] != mention.get("text"):
                n_bad_offset += 1

            if label not in NON_ENTITY_LABELS:
                n_non_time += 1
                if canonical_id:
                    n_non_time_resolved += 1

            if source in ("pronoun", "pronoun_name"):
                n_pronoun_total += 1
                has_pronoun = True
                if canonical_id:
                    n_pronoun_resolved += 1
        if has_pronoun:
            n_sent_has_pronoun += 1

    def _rate(numerator: int, denominator: int) -> float:
        """Tỉ lệ phần trăm (0 nếu mẫu số bằng 0).

        Args:
            numerator: Tử số.
            denominator: Mẫu số.

        Returns:
            Tỉ lệ phần trăm làm tròn 2 chữ số.
        """
        if not denominator:
            return 0.0
        return round(numerator / denominator * 100, 2)

    return {
        "so_sentence": n_sentences,
        "so_mention": n_mentions,
        "so_mention_resolved": n_resolved,
        "resolve_rate_pct": _rate(n_resolved, n_mentions),
        "resolve_rate_non_time_pct": _rate(n_non_time_resolved, n_non_time),
        "so_mention_non_time": n_non_time,
        "so_mention_non_time_resolved": n_non_time_resolved,
        "phoi_resolved_by": dict(by_method.most_common()),
        "phoi_label": dict(by_label.most_common()),
        "resolved_by_label": dict(resolved_by_label.most_common()),
        "phoi_source": dict(by_source.most_common()),
        "resolved_by_source": dict(resolved_by_source.most_common()),
        "so_sentence_co_danh_xung": n_sent_has_pronoun,
        "so_danh_xung": n_pronoun_total,
        "so_danh_xung_resolved": n_pronoun_resolved,
        "resolve_rate_danh_xung_pct": _rate(n_pronoun_resolved, n_pronoun_total),
        "vi_pham": {
            "canonical_id_sai_dinh_dang": n_bad_id,
            "offset_khong_khop": n_bad_offset,
            "nhan_ngoai_danh_muc": n_bad_label,
            "resolved_by_ngoai_danh_muc": n_bad_method,
        },
    }


def sample_examples(
    rows: list[dict[str, Any]],
    *,
    n: int = 20,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Chọn ngẫu nhiên `n` câu có danh xưng/đại từ để kiểm thử tay.

    Args:
        rows: Các record từ `coref_resolved.jsonl`.
        n: Số ví dụ cần lấy.
        seed: Seed ngẫu nhiên (cố định 42 theo `configs/default.yaml`).

    Returns:
        Danh sách ví dụ đã sắp xếp theo `sentence_id` (tái lập được).
    """
    candidates = [
        row
        for row in rows
        if any(
            str(mention.get("source")) in ("pronoun", "pronoun_name")
            for mention in (row.get("mentions") or [])
        )
    ]
    candidates.sort(key=lambda row: str(row.get("sentence_id")))
    if not candidates:
        return []
    rng = random.Random(seed)
    picked = rng.sample(candidates, min(n, len(candidates)))
    picked.sort(key=lambda row: str(row.get("sentence_id")))
    return picked


def sanitize_han(text: str) -> str:
    """Thay ký tự Hán (Trung Quốc) bằng nhãn trung tính.

    Corpus Wikipedia tiếng Việt có trích nguyên văn chữ Hán trong ngoặc
    (vd. ``chữ Hán: <chu Han>``). Báo cáo Phase 6 **không** được chứa tiếng Trung
    (quy tắc ``.cursor/rules/no-chinese.mdc``) → thay bằng ``<bỏ dấu>`` để vẫn
    giữ được ngữ cảnh mà không vi phạm. Dùng cùng ký hiệu với
    ``src/preprocess/extract_lead_dates.py``.

    Args:
        text: Chuỗi cần làm sạch.

    Returns:
        Chuỗi đã thay ký tự Hán.
    """
    return _HAN_RE.sub("<bỏ dấu>", text)


def _render_markdown(stats: dict[str, Any], examples: list[dict[str, Any]]) -> str:
    """Dựng báo cáo Markdown.

    Args:
        stats: Số liệu từ `collect_stats`.
        examples: Ví dụ ngẫu nhiên.

    Returns:
        Nội dung Markdown.
    """
    violations = stats["vi_pham"]
    total_violation = sum(violations.values())

    lines: list[str] = []
    lines.append("# Báo cáo chất lượng coreference — Phase 6")
    lines.append("")
    lines.append("Nguồn: `data/interim/coref_resolved.jsonl`")
    lines.append("")
    lines.append("## 1. Tổng quan")
    lines.append("")
    lines.append("| Chỉ số | Giá trị |")
    lines.append("|---|---|")
    lines.append(f"| Số câu | {stats['so_sentence']:,} |".replace(",", "."))
    lines.append(f"| Số mention | {stats['so_mention']:,} |".replace(",", "."))
    lines.append(f"| Mention có `canonical_id` | {stats['so_mention_resolved']:,} |".replace(",", "."))
    lines.append(f"| **Tỉ lệ resolve (toàn bộ)** | **{stats['resolve_rate_pct']}%** |")
    lines.append(
        f"| **Tỉ lệ resolve (không tính TIME)** | **{stats['resolve_rate_non_time_pct']}%** |"
    )
    lines.append(f"| Số danh xưng/đại từ | {stats['so_danh_xung']:,} |".replace(",", "."))
    lines.append(
        f"| Tỉ lệ resolve danh xưng | {stats['resolve_rate_danh_xung_pct']}% |"
    )
    lines.append("")
    lines.append("## 2. Phân bố `resolved_by`")
    lines.append("")
    lines.append("| `resolved_by` | Số mention |")
    lines.append("|---|---|")
    for method, count in stats["phoi_resolved_by"].items():
        lines.append(f"| `{method}` | {count:,} |".replace(",", "."))
    lines.append("")
    lines.append("## 3. Phân bố nhãn")
    lines.append("")
    lines.append("| Nhãn | Tổng | Đã resolve |")
    lines.append("|---|---|---|")
    for label, count in stats["phoi_label"].items():
        resolved = stats["resolved_by_label"].get(label, 0)
        lines.append(f"| `{label}` | {count:,} | {resolved:,} |".replace(",", "."))
    lines.append("")
    lines.append("## 4. Kiểm tra contract (Gate G1, G7)")
    lines.append("")
    lines.append("| Kiểm tra | Số lỗi |")
    lines.append("|---|---|")
    for name, count in violations.items():
        lines.append(f"| `{name}` | {count} |")
    lines.append("")
    status = "✅ đạt" if total_violation == 0 else "❌ không đạt"
    lines.append(f"**Tổng vi phạm: {total_violation} — {status}**")
    lines.append("")
    lines.append("## 5. 20 ví dụ ngẫu nhiên để kiểm thử tay")
    lines.append("")
    lines.append("Seed 42, lấy trong các câu có danh xưng/đại từ.")
    lines.append("")
    for row in examples:
        lines.append(f"### `{row.get('sentence_id')}`")
        lines.append("")
        lines.append(f"> {sanitize_han(str(row.get('text') or ''))}")
        lines.append("")
        lines.append("| Mention | Nhãn | `resolved_by` | `canonical_id` |")
        lines.append("|---|---|---|---|")
        for mention in row.get("mentions") or []:
            canonical = mention.get("canonical_id") or "—"
            lines.append(
                f"| `{sanitize_han(str(mention.get('text') or ''))}` | {mention.get('label')} | "
                f"`{mention.get('resolved_by')}` | `{canonical}` |"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Báo cáo chất lượng coreference (Phase 6)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--input", default=None, help="Đường dẫn coref_resolved.jsonl")
    parser.add_argument("--out", default=None, help="Đường dẫn báo cáo Markdown")
    parser.add_argument("--json-out", default=None, help="Đường dẫn số liệu JSON")
    parser.add_argument("--n-examples", type=int, default=20)
    args = parser.parse_args(argv)

    config = load_config(args.config)
    coref_config = dict(config.get("coref", {}))
    dump_config = dict(config.get("dump", {}))

    input_path = resolve_path(
        args.input or coref_config.get("output_path", "data/interim/coref_resolved.jsonl")
    )
    out_path = resolve_path(
        args.out or "reports/coref_quality.md"
    )
    json_out_path = resolve_path(
        args.json_out or "docs/10-nhat-ky/so-lieu/phase-06-coref-stats.json"
    )

    rows = _load_jsonl(input_path)
    logger.info("Đã đọc %d câu từ %s", len(rows), input_path)

    stats = collect_stats(rows)
    examples = sample_examples(rows, n=args.n_examples, seed=42)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_render_markdown(stats, examples), encoding="utf-8")
    logger.info("Đã ghi báo cáo → %s", out_path)

    json_out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {
            "phase": 6,
            "dump_version": dump_config.get("dump_version"),
            "mo_ta": "Số liệu chất lượng coreference Phase 6 (C1/C2)",
            "nguon": (
                "python -m src.coref.quality_report --config configs/default.yaml "
                "→ data/interim/coref_resolved.jsonl"
            ),
            "ngay_do": "2026-11-15",
        },
        "thong_ke": stats,
    }
    json_out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("Đã ghi số liệu máy đọc được → %s", json_out_path)

    logger.info(
        "Resolve: %s/%s (%.2f%%) · không tính TIME: %.2f%% · vi phạm contract: %d",
        stats["so_mention_resolved"],
        stats["so_mention"],
        stats["resolve_rate_pct"],
        stats["resolve_rate_non_time_pct"],
        sum(stats["vi_pham"].values()),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

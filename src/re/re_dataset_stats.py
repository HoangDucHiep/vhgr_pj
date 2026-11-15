"""Thống kê và tự kiểm 5 Gate của Phase 7.

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 7.

5 Gate
------
===========  ==============================================  ==========
Mã          Kiểm tra                                         Kỳ vọng
===========  ==============================================  ==========
G1          Số mẫu POSITIVE                                  ≥ 10.000
G2          Tỉ lệ NEG/POS                                   ≤ 1,0
G3          Số quan hệ có POSITIVE                           ≥ 8
G4          Quan hệ ngoài danh mục 18 quan hệ                 0
G5          Cache SPARQL — chạy lại không gọi mạng            0 request
===========  ==============================================  ==========
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger
from src.common.schemas import RELATION_TYPES
from src.re.wikidata_relations import load_gates

logger = get_logger(__name__)


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """Nạp toàn bộ artifact JSONL.

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách record (mỗi record là **một câu**, chứa mảng ``pairs``).
    """
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def iter_pairs(records: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Duyệt qua tất cả cặp của các record theo câu.

    Mỗi cặp được bổ sung `sentence_id`/`split` để thống kê theo câu mà
    không phải truy ngược lại record.

    Args:
        records: Danh sách record theo câu.

    Yields:
        Từng cặp kèm ngữ cảnh câu.
    """
    for record in records:
        for pair in record.get("pairs") or []:
            enriched = dict(pair)
            enriched["sentence_id"] = record.get("sentence_id", "")
            enriched["split"] = record.get("split", "")
            enriched["text"] = record.get("text", "")
            yield enriched


def compute_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Tính thống kê phân bố của tập huấn luyện.

    Args:
        records: Danh sách record theo câu.

    Returns:
        Dict thống kê: số POSITIVE/NEGATIVE, tỉ lệ, phân bố theo quan hệ,
        theo split, theo nguồn, số quan hệ ngoài danh mục.
    """
    pairs = list(iter_pairs(records))
    positives = [p for p in pairs if p.get("label") == "POSITIVE"]
    negatives = [p for p in pairs if p.get("label") == "NEGATIVE"]

    by_relation = Counter(p["relation"] for p in positives)
    by_split = Counter(p["split"] for p in pairs)
    pos_by_split = Counter(p["split"] for p in positives)
    neg_by_split = Counter(p["split"] for p in negatives)
    by_source = Counter(p.get("source", "") for p in positives)

    out_of_schema = sorted(
        {p["relation"] for p in pairs if p.get("relation") not in RELATION_TYPES}
    )

    return {
        "sentences": len(records),
        "total": len(pairs),
        "positive": len(positives),
        "negative": len(negatives),
        "neg_pos_ratio": (len(negatives) / len(positives)) if positives else 0.0,
        "relations_with_positive": len(by_relation),
        "by_relation": dict(by_relation.most_common()),
        "by_split": dict(by_split),
        "positive_by_split": dict(pos_by_split),
        "negative_by_split": dict(neg_by_split),
        "positive_by_source": dict(by_source),
        "out_of_schema_relations": out_of_schema,
        "out_of_schema_count": sum(
            1 for p in pairs if p.get("relation") not in RELATION_TYPES
        ),
        "distinct_sentences": len({p["sentence_id"] for p in pairs}),
    }


def check_gates(
    stats: dict[str, Any],
    gates: dict[str, Any],
) -> list[dict[str, Any]]:
    """Kiểm tra 5 Gate.

    Args:
        stats: Thống kê từ `compute_stats`.
        gates: Ngưỡng Gate.

    Returns:
        Danh sách kết quả từng Gate.
    """
    results: list[dict[str, Any]] = []

    positive = stats["positive"]
    min_positive = int(gates.get("min_positive", 10000))
    results.append(
        {
            "id": "G1",
            "name": "Số mẫu POSITIVE",
            "expected": f">= {min_positive}",
            "actual": positive,
            "passed": positive >= min_positive,
        }
    )

    ratio = stats["neg_pos_ratio"]
    max_ratio = float(gates.get("max_neg_pos_ratio", 1.0))
    results.append(
        {
            "id": "G2",
            "name": "Tỉ lệ NEG/POS",
            "expected": f"<= {max_ratio}",
            "actual": round(ratio, 4),
            "passed": ratio <= max_ratio,
        }
    )

    n_relations = stats["relations_with_positive"]
    min_relations = int(gates.get("min_relations_with_positive", 8))
    results.append(
        {
            "id": "G3",
            "name": "Số quan hệ có POSITIVE",
            "expected": f">= {min_relations}",
            "actual": n_relations,
            "passed": n_relations >= min_relations,
        }
    )

    n_out = stats["out_of_schema_count"]
    results.append(
        {
            "id": "G4",
            "name": "Quan hệ ngoài danh mục 18 quan hệ",
            "expected": "== 0",
            "actual": n_out,
            "passed": n_out == 0,
        }
    )

    results.append(
        {
            "id": "G5",
            "name": "Cache SPARQL idempotent (0 request khi chạy lại)",
            "expected": "== 0 request",
            "actual": None,
            "passed": None,
            "note": "Kiểm bởi scripts/re_gate_check.py",
        }
    )
    return results


def format_report(stats: dict[str, Any], gate_results: list[dict[str, Any]]) -> str:
    """Định dạng báo cáo dạng văn bản.

    Args:
        stats: Thống kê.
        gate_results: Kết quả Gate.

    Returns:
        Chuỗi báo cáo.
    """
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("PHASE 7 — THỐNG KÊ TẬP HUẤN LUYỆN RE")
    lines.append("=" * 72)
    lines.append("")
    lines.append(
        f"Câu: {stats['sentences']}  |  Tổng cặp: {stats['total']}  |  "
        f"POSITIVE: {stats['positive']}  |  "
        f"NEGATIVE: {stats['negative']}  |  NEG/POS: {stats['neg_pos_ratio']:.4f}"
    )
    lines.append(
        f"Số quan hệ có POSITIVE: {stats['relations_with_positive']}  |  "
        f"Câu khác nhau: {stats['distinct_sentences']}"
    )
    lines.append("")
    lines.append("Phân bố theo quan hệ (POSITIVE):")
    for relation, count in stats["by_relation"].items():
        lines.append(f"  {relation:22s} {count:6d}")
    lines.append("")
    lines.append("Phân bố theo split:")
    for split in ("train", "dev", "test"):
        lines.append(
            f"  {split:6s} POS {stats['positive_by_split'].get(split, 0):6d}  "
            f"NEG {stats['negative_by_split'].get(split, 0):6d}"
        )
    lines.append("")
    lines.append("Nguồn nhãn POSITIVE:")
    for source, count in sorted(stats["positive_by_source"].items()):
        lines.append(f"  {source:22s} {count:6d}")
    lines.append("")
    lines.append("-" * 72)
    lines.append("GATE")
    lines.append("-" * 72)
    for gate in gate_results:
        status = "PASS" if gate["passed"] else ("SKIP" if gate["passed"] is None else "FAIL")
        actual = gate["actual"] if gate["actual"] is not None else "—"
        lines.append(
            f"  [{status:4s}] {gate['id']} {gate['name']}: "
            f"kỳ vọng {gate['expected']}, thực tế {actual}"
        )
    return "\n".join(lines)


def main() -> None:
    """Điểm vào CLI."""
    parser = argparse.ArgumentParser(
        description="Thống kê + kiểm Gate Phase 7."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--train", default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    config = load_default_config()
    re_cfg = config.get("re") or {}

    train_path = Path(args.train) if args.train else resolve_path(
        re_cfg.get("train_path", "data/interim/re_train.jsonl")
    )
    records = load_records(train_path)
    stats = compute_stats(records)
    gates = load_gates(re_cfg.get("relations_config"))
    gate_results = check_gates(stats, gates)

    print(format_report(stats, gate_results))

    if args.json_out:
        payload = {
            "_meta": {
                "phase": 7,
                "mo_ta": (
                    "Thống kê tập huấn luyện RE (Phase 7 — D1.1); "
                    "artifact theo contract docs/09 §Phase 7: 1 record/câu, "
                    "mảng `pairs` lồng, label chuỗi POSITIVE/NEGATIVE"
                ),
                "nguon": (
                    f"{train_path} (sinh bởi: python -m src.re.build_re_dataset "
                    "--config configs/default.yaml)"
                ),
                "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            "stats": stats,
            "gates": gate_results,
        }
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        logger.info("Ghi thống kê → %s", out)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Kiểm định trực tiếp 5 Gate của Phase 7 trên artifact đã sinh.

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 7.

Khác với `src/re/re_dataset_stats.py` (chỉ đọc artifact), script này kiểm
**G5 — cache SPARQL idempotent**: chạy lại `build_distant_supervision` và đo
số request HTTP thực sự gửi đi. Yêu cầu: **0 request** (mọi query đã có
cache đĩa).

Cách đo
-------
`src/preprocess/wikidata_query.py` dùng `urllib.request`. Script này bọc
`urllib.request.urlopen` để **đếm** số lần gọi mạng, rồi chạy lại builder
với cùng tham số. Nếu cache hoạt động, số lần gọi = 0.

Usage:
    python scripts/re_gate_check.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_default_config, resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402
from src.re.re_dataset_stats import (  # noqa: E402
    check_gates,
    compute_stats,
    load_records,
)
from src.re.wikidata_relations import load_gates  # noqa: E402

logger = get_logger("scripts.re_gate_check")


class NetworkCounter:
    """Đếm số request HTTP thực sự gửi đi.

    Attributes:
        count: Số lần gọi ``urlopen``.
    """

    def __init__(self) -> None:
        """Khởi tạo bộ đếm."""
        self.count = 0

    def install(self) -> None:
        """Bọc ``urllib.request.urlopen`` để đếm lần gọi."""
        original = urllib.request.urlopen
        counter = self

        def counting_urlopen(*args: Any, **kwargs: Any) -> Any:
            counter.count += 1
            logger.warning("  → HTTP request #%d", counter.count)
            return original(*args, **kwargs)

        urllib.request.urlopen = counting_urlopen  # type: ignore[assignment]

    def uninstall(self) -> None:
        """Khôi phục ``urlopen`` gốc (nếu cần)."""
        # Không làm gì ở đây — script kết thúc ngay sau khi đo.
        return


def check_gate_g5(config: dict[str, Any]) -> dict[str, Any]:
    """Kiểm Gate G5 — chạy lại builder không gọi mạng.

    Args:
        config: Config đã nạp.

    Returns:
        Dict kết quả Gate.
    """
    from src.re.build_distant_supervision import main as build_main
    import sys as _sys

    counter = NetworkCounter()
    counter.install()
    logger.info("Chạy lại build_distant_supervision (đo số request HTTP)...")
    started = time.monotonic()
    argv = _sys.argv
    _sys.argv = ["build_distant_supervision", "--config", "configs/default.yaml"]
    try:
        build_main()
    except SystemExit:
        pass
    finally:
        _sys.argv = argv
    elapsed = time.monotonic() - started

    passed = counter.count == 0
    logger.info(
        "G5: %d request HTTP trong %.1fs — %s",
        counter.count,
        elapsed,
        "PASS" if passed else "FAIL",
    )
    return {
        "id": "G5",
        "name": "Cache SPARQL idempotent (0 request khi chạy lại)",
        "expected": "== 0 request",
        "actual": counter.count,
        "passed": passed,
        "note": f"chạy lại builder mất {elapsed:.1f}s",
    }


def main() -> None:
    """Điểm vào CLI."""
    parser = argparse.ArgumentParser(
        description="Kiểm định Gate G1–G5 của Phase 7."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--train", default=None)
    parser.add_argument("--skip-g5", action="store_true")
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

    if not args.skip_g5:
        g5 = check_gate_g5(config)
        gate_results = [g for g in gate_results if g["id"] != "G5"] + [g5]

    print("=" * 72)
    print("PHASE 7 — KIỂM ĐỊNH GATE (trên artifact)")
    print("=" * 72)
    print(f"Artifact: {train_path}")
    print(
        f"Câu: {stats['sentences']}  |  Tổng cặp: {stats['total']}  |  "
        f"POSITIVE: {stats['positive']}  |  "
        f"NEGATIVE: {stats['negative']}  |  NEG/POS: {stats['neg_pos_ratio']:.4f}"
    )
    print(
        f"Số quan hệ có POSITIVE: {stats['relations_with_positive']}  |  "
        f"Quan hệ ngoài danh mục: {stats['out_of_schema_count']}"
    )
    print("-" * 72)
    all_passed = True
    for gate in gate_results:
        status = "PASS" if gate["passed"] else ("SKIP" if gate["passed"] is None else "FAIL")
        if gate["passed"] is False:
            all_passed = False
        actual = gate["actual"] if gate["actual"] is not None else "—"
        print(
            f"  [{status:4s}] {gate['id']} {gate['name']}: "
            f"kỳ vọng {gate['expected']}, thực tế {actual}"
        )
    print("-" * 72)
    print(f"KẾT QUẢ: {'✅ ĐẠT TOÀN BỘ GATE' if all_passed else '❌ CÓ GATE KHÔNG ĐẠT'}")

    if args.json_out:
        payload = {
            "_meta": {
                "phase": 7,
                "mo_ta": "Kiểm định Gate G1–G5 Phase 7 trên artifact re_train.jsonl",
                "nguon": str(train_path),
                "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            },
            "stats": stats,
            "gates": gate_results,
            "all_passed": all_passed,
        }
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        logger.info("Ghi kết quả Gate → %s", out)

    if not all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

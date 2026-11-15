"""Tổng hợp số liệu Phase 5 → `docs/10-nhat-ky/so-lieu/phase-05-ner-stats.json`.

Gộp:
- metrics của các arm (base/large) đọc từ `reports/kaggle_ner_<arm>/models/ner/metrics.json`;
- kết quả kiểm tra Gate (`reports/ner_predictions_validate.json`);
- kết quả đo trên bộ gold 100 câu (`reports/ner_gold_100_metrics.json`);
- thống kê nhiễu nhãn bạc (`reports/ner_silver_noise_100.json`).

Cách dùng
---------
```bash
python scripts/phase05_stats.py --out docs/10-nhat-ky/so-lieu/phase-05-ner-stats.json
```
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def _read_json(path: Path) -> dict[str, Any] | None:
    """Đọc file JSON nếu tồn tại.

    Args:
        path: Đường dẫn file.

    Returns:
        Dict nội dung hoặc `None` nếu không có file.
    """
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def collect(repo_root: Path) -> dict[str, Any]:
    """Thu thập số liệu Phase 5.

    Args:
        repo_root: Thư mục gốc repo.

    Returns:
        Dict số liệu tổng hợp.
    """
    arms: dict[str, Any] = {}
    for arm in ("base", "large"):
        metrics = _read_json(
            repo_root / "reports" / f"kaggle_ner_{arm}" / "models" / "ner" / "metrics.json"
        )
        if metrics is None:
            continue
        arms[arm] = metrics

    return {
        "_meta": {
            "phase": 5,
            "description": "Số liệu huấn luyện NER PhoBERT + suy luận toàn corpus",
            "sources": [
                "reports/kaggle_ner_<arm>/models/ner/metrics.json",
                "reports/ner_predictions_validate.json",
                "reports/ner_gold_100_metrics.json",
                "reports/ner_silver_noise_100.json",
            ],
        },
        "arms": arms,
        "comparison": _compare(arms),
        "gate_predictions": _read_json(
            repo_root / "reports" / "ner_predictions_validate.json"
        ),
        "gold_100": _read_json(repo_root / "reports" / "ner_gold_100_metrics.json"),
        "silver_noise_100": _read_json(
            repo_root / "reports" / "ner_silver_noise_100.json"
        ),
    }


def _compare(arms: dict[str, Any]) -> dict[str, Any]:
    """Dựng bảng so sánh giữa các arm.

    Args:
        arms: Map arm → metrics.

    Returns:
        Dict so sánh.
    """
    rows = []
    for arm, metrics in arms.items():
        meta = metrics.get("_meta", {})
        micro = metrics.get("micro", {})
        macro = metrics.get("macro", {})
        rows.append(
            {
                "arm": arm,
                "model_name": meta.get("model_name"),
                "micro_f1": micro.get("f1"),
                "micro_precision": micro.get("precision"),
                "micro_recall": micro.get("recall"),
                "macro_f1": macro.get("f1"),
                "train_seconds": meta.get("train_seconds"),
                "epochs": meta.get("epochs"),
                "batch_size": meta.get("batch_size"),
                "gradient_accumulation_steps": meta.get("gradient_accumulation_steps"),
            }
        )
    rows.sort(key=lambda row: row["micro_f1"] or 0, reverse=True)
    return {"rows": rows, "best_arm": rows[0]["arm"] if rows else None}


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Tổng hợp số liệu Phase 5")
    parser.add_argument(
        "--out", default="docs/10-nhat-ky/so-lieu/phase-05-ner-stats.json"
    )
    args = parser.parse_args(argv)

    payload = collect(REPO_ROOT)
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    logger.info("Đã ghi %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

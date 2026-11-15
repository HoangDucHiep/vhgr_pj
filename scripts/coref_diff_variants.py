"""So sánh 2 thứ tự ưu tiên quy tự R — in ra mention khác nhau (debug).

Cách chạy:
    python scripts/coref_diff_variants.py --order-a r1a,r1b,r3,r5,r6 \
        --order-b r3,r1a,r1b,r5,r6

Dùng `coref.pronoun_rule_order` (D-052) → chạy trên **đúng đường dẫn code
thật**, không monkeypatch.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_config, resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def _run(config_path: str | Path, rule_order: list[str]) -> dict[str, dict]:
    """Chạy pipeline với 1 thứ tự quy tắc, trả về map sentence_id → row.

    Args:
        config_path: Đường dẫn config.
        rule_order: Thứ tự quy tắc.

    Returns:
        Map ``sentence_id`` → record kết quả.
    """
    import yaml

    from scripts import coref_eval as ce
    from src.coref import resolve_coref as rc

    config = load_config(str(config_path))
    coref_config = dict(config.get("coref", {}))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        out_path = tmp_dir / "coref_resolved.jsonl"
        subject_path = tmp_dir / "article_subjects.jsonl"

        cfg = dict(config)
        cfg["coref"] = {
            **coref_config,
            "output_path": str(out_path),
            "article_subject_path": str(subject_path),
            "pronoun_rule_order": list(rule_order),
        }
        tmp_config = tmp_dir / "config.yaml"
        tmp_config.write_text(
            yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8"
        )

        rc.main(["--config", str(tmp_config)])
        result = {row["sentence_id"]: row for row in ce._load_jsonl(out_path)}
    return result


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Diff 2 thứ tự quy tắc R")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--order-a", default="r1a,r1b,r3,r5,r6")
    parser.add_argument("--order-b", default="r3,r1a,r1b,r5,r6")
    parser.add_argument("--gold", default="data/eval/coref_gold_100.jsonl")
    args = parser.parse_args(argv)

    order_a = [item.strip() for item in args.order_a.split(",") if item.strip()]
    order_b = [item.strip() for item in args.order_b.split(",") if item.strip()]

    a = _run(args.config, order_a)
    b = _run(args.config, order_b)

    gold_rows = [
        json.loads(line)
        for line in resolve_path(args.gold)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    diffs = 0
    for row in gold_rows:
        sid = row["sentence_id"]
        am = {
            (m["start"], m["end"]): m for m in (a.get(sid, {}).get("mentions") or [])
        }
        bm = {
            (m["start"], m["end"]): m for m in (b.get(sid, {}).get("mentions") or [])
        }
        for gm in row.get("mentions") or []:
            key = (gm["start"], gm["end"])
            if key not in am or key not in bm:
                continue
            ac = am[key].get("canonical_id")
            bc = bm[key].get("canonical_id")
            if ac == bc:
                continue
            diffs += 1
            gold = gm.get("canonical_id")
            ctx = row["text"][max(0, gm["start"] - 50) : gm["end"] + 30]
            verdict = "A✓" if ac == gold else "A✗"
            verdict_b = "B✓" if bc == gold else "B✗"
            print(
                f"[{sid}] {gm['text']!r} | gold={gold}\n"
                f"    A = {ac} ({am[key].get('resolved_by')}) {verdict}\n"
                f"    B = {bc} ({bm[key].get('resolved_by')}) {verdict_b}\n"
                f"    ctx: ...{ctx}..."
            )
    print(f"\ntotal differing = {diffs}")
    logger.info("order A = %s · order B = %s", order_a, order_b)
    return 0


if __name__ == "__main__":
    sys.exit(main())

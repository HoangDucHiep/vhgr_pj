"""Ablation: đo độ chính xác coreference theo thứ tự ưu tiên R (Phase 6).

Cách chạy:
    python scripts/coref_ablation.py --config configs/default.yaml

Mục đích
--------
Trong `docs/10-nhat-ky/phase-06.md` §4.2, cần **đo** (không đoán) độ chính
xác G5 của các thứ tự ưu tiên quy tắc R.

Thứ tự ưu tiên được **cấu hình** qua `coref.pronoun_rule_order` (D-052) →
ablation chạy trên **đúng đường dẫn code thật**, không monkeypatch
(cách monkeypatch trước đây bỏ qua chốt an toàn "đại từ số nhiều" → đo sai).

Cách đo: với mỗi thứ tự, ghi đè `pronoun_rule_order` vào config tạm, chạy lại
`resolve_coref` rồi chạy lại `coref_eval` và so sánh G5.
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

# Các biến thể thứ tự ưu tiên được so sánh.
# Mỗi biến thể: (nhãn, thứ tự quy tắc, r1b_unique_only, r3_requires_no_person).
VARIANTS: list[tuple[str, list[str], bool, bool]] = [
    ("A · R1a→R1b→R3→R5→R6", ["r1a", "r1b", "r3", "r5", "r6"], False, False),
    ("B · R3→R1a→R1b→R5→R6", ["r3", "r1a", "r1b", "r5", "r6"], False, False),
    ("C · R1a→R3→R1b→R5→R6", ["r1a", "r3", "r1b", "r5", "r6"], False, False),
    ("D · R1b→R1a→R3→R5→R6", ["r1b", "r1a", "r3", "r5", "r6"], False, False),
    (
        "E · R1a→R1b(duy nhất)→R3→R5→R6",
        ["r1a", "r1b", "r3", "r5", "r6"],
        True,
        False,
    ),
    (
        "F · R1a→R3→R1b(duy nhất)→R5→R6",
        ["r1a", "r3", "r1b", "r5", "r6"],
        True,
        False,
    ),
    (
        "G · R3→R1a→R1b(duy nhất)→R5→R6",
        ["r3", "r1a", "r1b", "r5", "r6"],
        True,
        False,
    ),
    (
        "H · R3(đặc tả: đoạn không có PERSON)→R1a→R1b→R5→R6",
        ["r3", "r1a", "r1b", "r5", "r6"],
        False,
        True,
    ),
    (
        "I · R1a→R3(đặc tả)→R1b→R5→R6",
        ["r1a", "r3", "r1b", "r5", "r6"],
        False,
        True,
    ),
]


def _run_variant(
    config_path: str | Path,
    *,
    rule_order: list[str],
    r1b_unique_only: bool,
    r3_requires_no_person: bool,
    label: str,
) -> dict:
    """Chạy resolve + eval cho 1 thứ tự ưu tiên quy tắc.

    Args:
        config_path: Đường dẫn config.
        rule_order: Thứ tự quy tắc (`pronoun_rule_order`).
        r1b_unique_only: Có bật ràng buộc R1b-duy-nhất (D-053) hay không.
        r3_requires_no_person: Có bật điều kiện R3 theo đặc tả hay không.
        label: Nhãn hiển thị.

    Returns:
        Dict số liệu G5 + G3.
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
            "r1b_unique_only": r1b_unique_only,
            "r3_requires_no_person": r3_requires_no_person,
        }
        tmp_config = tmp_dir / "config.yaml"
        tmp_config.write_text(
            yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8"
        )

        rc.main(["--config", str(tmp_config)])
        stats = ce.evaluate_gold(
            [
                json.loads(line)
                for line in resolve_path(
                    coref_config.get(
                        "gold_path", "data/eval/coref_gold_100.jsonl"
                    )
                )
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ],
            {
                row["sentence_id"]: row
                for row in ce._load_jsonl(out_path)
            },
            ce._build_gender_index(
                coref_config.get(
                    "infobox_entities_path",
                    "data/interim/infobox_entities.jsonl",
                )
            ),
        )

        rows = ce._load_jsonl(out_path)
        total = sum(len(row["mentions"]) for row in rows)
        resolved = sum(
            1
            for row in rows
            for mention in row["mentions"]
            if mention.get("canonical_id")
        )

    return {
        "bien_the": label,
        "thu_tu": list(rule_order),
        "r1b_unique_only": r1b_unique_only,
        "r3_requires_no_person": r3_requires_no_person,
        "g5_do_chinh_xac": stats["do_chinh_xac"],
        "g5_so_dung": stats["so_dung"],
        "g5_so_mention_co_nhan_vang": stats["so_mention_co_nhan_vang"],
        "g3_resolve_rate_pct": round(resolved / total * 100, 2) if total else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Ablation thứ tự ưu tiên R cho coreference (Phase 6)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--out",
        default="docs/10-nhat-ky/so-lieu/phase-06-coref-ablation.json",
    )
    args = parser.parse_args(argv)

    variants = [
        _run_variant(
            args.config,
            rule_order=order,
            r1b_unique_only=r1b_unique_only,
            r3_requires_no_person=r3_requires_no_person,
            label=label,
        )
        for label, order, r1b_unique_only, r3_requires_no_person in VARIANTS
    ]

    payload = {
        "_meta": {
            "phase": 6,
            "mo_ta": "Ablation thứ tự ưu tiên quy tắc R (G5) — Phase 6",
            "nguon": "python scripts/coref_ablation.py --config configs/default.yaml",
            "ngay_do": "2026-11-15",
            "ghi_chu": (
                "Thứ tự quy tự được đo trên đúng đường dẫn code thật "
                "(coref.pronoun_rule_order) — không monkeypatch."
            ),
        },
        "thang_so_sanh": variants,
    }
    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    for variant in variants:
        logger.info(
            "%s → G5 = %.4f (%d/%d) · G3 = %.2f%%",
            variant["bien_the"],
            variant["g5_do_chinh_xac"],
            variant["g5_so_dung"],
            variant["g5_so_mention_co_nhan_vang"],
            variant["g3_resolve_rate_pct"],
        )
    logger.info("Đã ghi → %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

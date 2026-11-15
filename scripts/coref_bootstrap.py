"""Bootstrap + McNemar: kiểm tra chênh lệch G5 giữa 2 thứ tự quy tự R.

Cách chạy:
    python scripts/coref_bootstrap.py --order-a r1a,r1b,r3,r5,r6 \
        --order-b r3,r1a,r1b,r5,r6

Vì sao cần: chênh lệch G5 giữa 2 biến thể có thể chỉ là **nhiễu mẫu**.
Script này:
1. Chạy pipeline cho 2 thứ tự (đường dẫn code thật qua config).
2. **Bootstrap theo câu** (resample 100 câu, 10.000 lần) → CI 95% cho G5
   của từng biến thể + xác suất biến thể này tốt hơn.
3. **McNemar** trên các mention *discordant* (một bên đúng, bên sai) → p-value.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_config, resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

#: Số lần bootstrap.
N_BOOTSTRAP = 10_000


def _run(
    config_path: str | Path,
    rule_order: list[str],
    r1b_unique_only: bool = False,
) -> dict[str, dict]:
    """Chạy pipeline với 1 thứ tự quy tự, trả về map sentence_id → row.

    Args:
        config_path: Đường dẫn config.
        rule_order: Thứ tự quy tự.
        r1b_unique_only: Có bật ràng buộc R1b-duy-nhất (D-053) hay không.

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
            "r1b_unique_only": r1b_unique_only,
        }
        tmp_config = tmp_dir / "config.yaml"
        tmp_config.write_text(
            yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8"
        )

        rc.main(["--config", str(tmp_config)])
        return {row["sentence_id"]: row for row in ce._load_jsonl(out_path)}


def _scored_pairs(
    gold_rows: list[dict],
    predictions: dict[str, dict],
) -> list[tuple[str, bool]]:
    """Thu thập cặp (sentence_id, đúng/sai) cho các mention có nhãn vàng.

    Args:
        gold_rows: Các record gold đã gán tay.
        predictions: Map `sentence_id` → record dự đoán.

    Returns:
        Danh sách `(sentence_id, dung)`.
    """
    pairs: list[tuple[str, bool]] = []
    for row in gold_rows:
        sid = str(row.get("sentence_id"))
        pred = predictions.get(sid)
        if pred is None:
            continue
        pred_mentions = {
            (int(m["start"]), int(m["end"])): m
            for m in (pred.get("mentions") or [])
        }
        for gold in row.get("mentions") or []:
            gold_id = gold.get("canonical_id")
            if gold_id is None:
                continue
            key = (int(gold["start"]), int(gold["end"]))
            pred_mention = pred_mentions.get(key)
            if pred_mention is None:
                continue
            pairs.append((sid, pred_mention.get("canonical_id") == gold_id))
    return pairs


def _binomial_two_sided(b: int, c: int) -> float:
    """Tính p-value McNemar (exact, 2 phía).

    Args:
        b: Số mention bên A đúng / B sai.
        c: Số mention bên B đúng / A sai.

    Returns:
        p-value.
    """
    n = b + c
    if n == 0:
        return 1.0
    # X ~ Binomial(n, 0.5) → p-value = P(X <= min(b,c)) * 2
    k = min(b, c)
    tail = sum(_comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def _comb(n: int, k: int) -> float:
    """Tính tổ hợp C(n, k) bằng phép nhân dần (tránh overflow).

    Args:
        n: Tổng số.
        k: Số phần tử.

    Returns:
        Giá trị C(n, k).
    """
    if k < 0 or k > n:
        return 0.0
    k = min(k, n - k)
    result = 1.0
    for i in range(k):
        result = result * (n - i) / (i + 1)
    return result


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Bootstrap + McNemar cho G5")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--order-a", default="r1a,r1b,r3,r5,r6")
    parser.add_argument("--order-b", default="r3,r1a,r1b,r5,r6")
    parser.add_argument(
        "--r1b-unique-a",
        action="store_true",
        help="Bật ràng buộc R1b-duy-nhất cho biến thể A",
    )
    parser.add_argument(
        "--r1b-unique-b",
        action="store_true",
        help="Bật ràng buộc R1b-duy-nhất cho biến thể B",
    )
    parser.add_argument("--gold", default="data/eval/coref_gold_100.jsonl")
    parser.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out",
        default="docs/10-nhat-ky/so-lieu/phase-06-coref-significance.json",
    )
    args = parser.parse_args(argv)

    order_a = [item.strip() for item in args.order_a.split(",") if item.strip()]
    order_b = [item.strip() for item in args.order_b.split(",") if item.strip()]

    gold_rows = [
        json.loads(line)
        for line in resolve_path(args.gold)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]

    pairs_a = _scored_pairs(
        gold_rows, _run(args.config, order_a, args.r1b_unique_a)
    )
    pairs_b = _scored_pairs(
        gold_rows, _run(args.config, order_b, args.r1b_unique_b)
    )

    # --- McNemar trên mention discordant ---
    b_only = sum(1 for (_, da), (_, db) in zip(pairs_a, pairs_b) if da and not db)
    c_only = sum(1 for (_, da), (_, db) in zip(pairs_a, pairs_b) if db and not da)
    p_value = _binomial_two_sided(b_only, c_only)

    # --- Bootstrap theo câu ---
    rng = random.Random(args.seed)
    by_sentence_a: dict[str, list[bool]] = {}
    by_sentence_b: dict[str, list[bool]] = {}
    for (sid, da), (_, db) in zip(pairs_a, pairs_b):
        by_sentence_a.setdefault(sid, []).append(da)
        by_sentence_b.setdefault(sid, []).append(db)
    sentence_ids = sorted(by_sentence_a)

    acc_a_samples: list[float] = []
    acc_b_samples: list[float] = []
    win_count_a = 0
    win_count_b = 0
    ties = 0
    for _ in range(args.n_bootstrap):
        picked = [rng.choice(sentence_ids) for _ in sentence_ids]
        total_a = total_b = 0
        correct_a = correct_b = 0
        for sid in picked:
            flags_a = by_sentence_a[sid]
            flags_b = by_sentence_b[sid]
            total_a += len(flags_a)
            total_b += len(flags_b)
            correct_a += sum(flags_a)
            correct_b += sum(flags_b)
        acc_a = correct_a / total_a if total_a else 0.0
        acc_b = correct_b / total_b if total_b else 0.0
        acc_a_samples.append(acc_a)
        acc_b_samples.append(acc_b)
        if acc_a > acc_b:
            win_count_a += 1
        elif acc_b > acc_a:
            win_count_b += 1
        else:
            ties += 1

    def _ci(samples: list[float]) -> list[float]:
        """Tính CI 95% phân vị.

        Args:
            samples: Mẫu bootstrap.

        Returns:
            [p2.5, p97.5].
        """
        ordered = sorted(samples)
        lo = ordered[int(0.025 * len(ordered))]
        hi = ordered[int(0.975 * len(ordered)) - 1]
        return [round(lo, 4), round(hi, 4)]

    total_scored = len(pairs_a)
    acc_a = sum(1 for _, ok in pairs_a if ok) / total_scored if total_scored else 0.0
    acc_b = sum(1 for _, ok in pairs_b if ok) / total_scored if total_scored else 0.0

    payload = {
        "_meta": {
            "phase": 6,
            "mo_ta": "Kiểm định ý nghĩa chênh lệch G5 giữa 2 thứ tự quy tắc R",
            "nguon": (
                "python scripts/coref_bootstrap.py "
                f"--order-a {args.order_a} --order-b {args.order_b}"
            ),
            "ngay_do": "2026-11-15",
        },
        "bien_the_a": {
            "thu_tu": order_a,
            "r1b_unique_only": args.r1b_unique_a,
            "g5": round(acc_a, 4),
            "g5_ci95": _ci(acc_a_samples),
        },
        "bien_the_b": {
            "thu_tu": order_b,
            "r1b_unique_only": args.r1b_unique_b,
            "g5": round(acc_b, 4),
            "g5_ci95": _ci(acc_b_samples),
        },
        "mcnemar": {
            "a_dung_b_sai": b_only,
            "b_dung_a_sai": c_only,
            "p_value": round(p_value, 4),
            "ket_luan": (
                "khac biet co y nghia thong ke"
                if p_value < 0.05
                else "KHONG co y nghia thong ke"
            ),
        },
        "bootstrap": {
            "n_lan": args.n_bootstrap,
            "seed": args.seed,
            "xac_suat_a_tot_hon_b": round(win_count_a / args.n_bootstrap, 4),
            "xac_suat_b_tot_hon_a": round(win_count_b / args.n_bootstrap, 4),
            "hoa": round(ties / args.n_bootstrap, 4),
        },
    }
    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    logger.info("A (%s) G5 = %.4f %s", order_a, acc_a, payload["bien_the_a"]["g5_ci95"])
    logger.info("B (%s) G5 = %.4f %s", order_b, acc_b, payload["bien_the_b"]["g5_ci95"])
    logger.info(
        "McNemar: A đúng/B sai = %d · B đúng/A sai = %d · p = %.4f (%s)",
        b_only,
        c_only,
        p_value,
        payload["mcnemar"]["ket_luan"],
    )
    logger.info("Đã ghi → %s", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

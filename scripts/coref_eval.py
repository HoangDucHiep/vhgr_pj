"""Đánh giá coreference — Phase 6 (C1, C2).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 6 (bước 4 — đánh giá),
`docs/01-requirements-chuc-nang.md` §C1–C2.

Cách chạy
---------
```bash
python scripts/coref_eval.py --config configs/default.yaml
```

Đo gì
------
1. **G5 — độ chính xác gán đại từ (AC C1)**: trên bộ gold 100 câu đã gán tay,
   so `canonical_id` của hệ thống với nhãn vàng. Báo cáo theo `resolved_by`.
2. **G4 — không gắn sai giới tính**: kiểm tra riêng các mention đại từ có
   giới tính (`ông`/`bà`/...) xem hệ thống có gắn sang entity giới tính
   khác không.
3. **G6 — `article_subject` đúng (AC C2)**: đối chiếu type của chủ thể bài với
   ground-truth `infobox_type` / `wikidata_signal` trong `documents.jsonl`
   (1.687 bài có tín hiệu → đây là ground-truth đáng tin, không cần gán tay).

Output: `reports/coref_eval.md` + số liệu máy đọc được.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_config, resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

#: Nhãn danh xưng có giới tính → giới tính của đại từ.
GENDER_BY_HONORIFIC: dict[str, str] = {
    "ông": "male",
    "ông ấy": "male",
    "ông ta": "male",
    "vua": "male",
    "hoàng đế": "male",
    "đại vương": "male",
    "bà": "female",
    "bà ấy": "female",
    "chàng trai": "male",
    "cô gái": "female",
}

#: Ánh xạ `infobox_type` / `wikidata_signal` → loại node KG (ground-truth).
SIGNAL_TO_TYPE: dict[str, str] = {
    "person": "person",
    "place": "place",
    "dynasty": "dynasty",
    "event": "event",
    "battle": "event",
    "house": "dynasty",
}


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


def _build_gender_index(
    gazetteer_path: str | Path,
) -> dict[str, str]:
    """Dựng map `entity_id` → giới tính từ gazetteer (nguồn A).

    Nguồn: `data/interim/infobox_entities.jsonl` — trường `props.gender`
    (23 entity có, là nguồn **kiểm chứng** từ Wikipedia infobox).

    Vì sao cần index này: `_lookup_gender` cũ suy giới tính từ **tiền tố
    tên trong câu** ("Bà …" → nữ). Cách đó chỉ kiểm tra được vòng tròn với
    chính đại từ đang xét → không phát hiện được lỗi thật. Index này lấy
    giới tính từ **entity đích**, nên mới thực sự kiểm định Gate G4.

    Args:
        gazetteer_path: Đường dẫn `infobox_entities.jsonl`.

    Returns:
        Map ``{entity_id: "male"|"female"}`` (chỉ entity có giới tính).
    """
    index: dict[str, str] = {}
    path = Path(gazetteer_path)
    if not path.exists():
        return index
    for row in _load_jsonl(path):
        props = row.get("props") or {}
        if not isinstance(props, dict):
            continue
        gender = props.get("gender")
        entity_id = str(row.get("entity_id") or "")
        if isinstance(gender, str) and gender in ("male", "female") and entity_id:
            index[entity_id] = gender
    return index


def evaluate_gold(
    gold_rows: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
    gender_index: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Đánh giá độ chính xác resolve trên bộ gold đã gán tay.

    Args:
        gold_rows: Các record gold (có `canonical_id` đã gán tay).
        predictions: Map `sentence_id` → record từ `coref_resolved.jsonl`.
        gender_index: Map `entity_id` → giới tính (từ gazetteer nguồn A).

    Returns:
        Dict số liệu đánh giá.
    """
    n_sentences = 0
    n_mentions = 0
    n_scored = 0
    n_correct = 0
    n_system_resolved = 0
    n_gold_null = 0
    n_system_null_gold_has = 0
    n_false_positive = 0

    by_method: Counter[str] = Counter()
    correct_by_method: Counter[str] = Counter()

    # --- G4: kiểm tra giới tính ---
    gender_checked = 0
    gender_errors: list[dict[str, Any]] = []

    for row in gold_rows:
        sentence_id = str(row.get("sentence_id"))
        prediction = predictions.get(sentence_id)
        if prediction is None:
            continue
        n_sentences += 1
        pred_mentions = {
            (int(m["start"]), int(m["end"])): m
            for m in (prediction.get("mentions") or [])
        }
        for gold_mention in row.get("mentions") or []:
            n_mentions += 1
            gold_id = gold_mention.get("canonical_id")
            key = (int(gold_mention["start"]), int(gold_mention["end"]))
            pred_mention = pred_mentions.get(key)
            if pred_mention is None:
                continue
            pred_id = pred_mention.get("canonical_id")
            method = str(pred_mention.get("resolved_by") or "")
            by_method[method] += 1
            if pred_id:
                n_system_resolved += 1
            if gold_id is None:
                n_gold_null += 1
                if pred_id:
                    n_false_positive += 1
                continue
            n_scored += 1
            if pred_id == gold_id:
                n_correct += 1
                correct_by_method[method] += 1
            elif pred_id is None:
                n_system_null_gold_has += 1

            # G4 — đại từ có giới tính.
            # Nguồn giới tính của entity đích: ưu tiên index gazetteer
            # (kiểm chứng từ infobox), sau đó mới suy từ tiền tố tên.
            text = str(gold_mention.get("text") or "").lower()
            expected_gender = GENDER_BY_HONORIFIC.get(text)
            if expected_gender and pred_id:
                gender_checked += 1
                entity_gender = None
                if gender_index:
                    entity_gender = gender_index.get(pred_id)
                if entity_gender is None:
                    entity_gender = _lookup_gender(
                        predictions, sentence_id, pred_id
                    )
                if entity_gender and entity_gender != expected_gender:
                    gender_errors.append(
                        {
                            "sentence_id": sentence_id,
                            "text": gold_mention.get("text"),
                            "expected_gender": expected_gender,
                            "entity_gender": entity_gender,
                            "canonical_id": pred_id,
                        }
                    )

    accuracy = round(n_correct / n_scored, 4) if n_scored else 0.0
    return {
        "so_sentence_doi_chieu": n_sentences,
        "so_mention_gold": n_mentions,
        "so_mention_co_nhan_vang": n_scored,
        "so_dung": n_correct,
        "do_chinh_xac": accuracy,
        "he_thong_resolve": n_system_resolved,
        "he_thong_bo_sot": n_system_null_gold_has,
        "gold_khong_co_dich_va_he_thong_co": n_false_positive,
        "gold_khong_co_dich": n_gold_null,
        "theo_resolved_by": {
            method: {
                "so_mention": by_method[method],
                "so_dung": correct_by_method[method],
                "do_chinh_xac": (
                    round(correct_by_method[method] / by_method[method], 4)
                    if by_method[method]
                    else 0.0
                ),
            }
            for method in sorted(by_method)
        },
        "kiem_tra_gioi_tinh": {
            "so_mention": gender_checked,
            "so_loi": len(gender_errors),
            "chi_tiet": gender_errors[:20],
        },
    }


def _lookup_gender(
    predictions: dict[str, dict[str, Any]],
    sentence_id: str,
    entity_id: str,
) -> str | None:
    """Suy giới tính của entity từ tiền tố tên trong dữ liệu dự đoán.

    Args:
        predictions: Map `sentence_id` → record dự đoán.
        sentence_id: ID câu đang xét.
        entity_id: ID entity cần tra.

    Returns:
        ``male``/``female``/``None``.
    """
    row = predictions.get(sentence_id)
    if row is None:
        return None
    for mention in row.get("mentions") or []:
        if mention.get("canonical_id") != entity_id:
            continue
        text = str(mention.get("text") or "").lower()
        if text.startswith("bà ") or text.startswith("bà"):
            return "female"
        if text.startswith("ông ") or text.startswith("ông"):
            return "male"
    return None


def evaluate_article_subject(
    subjects: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """Đối chiếu chủ thể bài với ground-truth `infobox_type`/`wikidata_signal`.

    Args:
        subjects: Các record từ `article_subjects.jsonl`.
        documents: Các record từ `documents.jsonl`.

    Returns:
        Dict số liệu đánh giá C2.
    """
    docs = {str(doc.get("doc_id")): doc for doc in documents}
    n_total = 0
    n_with_gt = 0
    n_correct = 0
    n_correct_person = 0
    n_person = 0
    errors: Counter[tuple[str, str]] = Counter()

    for subject in subjects:
        n_total += 1
        doc = docs.get(str(subject.get("doc_id")))
        if doc is None:
            continue
        signal = doc.get("infobox_type") or doc.get("wikidata_signal")
        if not signal:
            continue
        expected = SIGNAL_TO_TYPE.get(str(signal).lower())
        if expected is None:
            continue
        n_with_gt += 1
        actual = str(subject.get("type"))
        if actual == expected:
            n_correct += 1
            if expected == "person":
                n_correct_person += 1
        else:
            errors[(expected, actual)] += 1
        if expected == "person":
            n_person += 1

    return {
        "so_bai": n_total,
        "so_bai_co_ground_truth": n_with_gt,
        "so_dung": n_correct,
        "do_chinh_xac": round(n_correct / n_with_gt, 4) if n_with_gt else 0.0,
        "do_chinh_xac_bai_nhan_vat": (
            round(n_correct_person / n_person, 4) if n_person else 0.0
        ),
        "so_bai_nhan_vat": n_person,
        "sai_lech": [
            {"expected": expected, "actual": actual, "count": count}
            for (expected, actual), count in errors.most_common(10)
        ],
    }


def _render_markdown(
    gold_stats: dict[str, Any],
    subject_stats: dict[str, Any],
) -> str:
    """Dựng báo cáo Markdown.

    Args:
        gold_stats: Số liệu đánh giá gold.
        subject_stats: Số liệu đánh giá chủ thể bài.

    Returns:
        Nội dung Markdown.
    """
    lines: list[str] = []
    lines.append("# Đánh giá coreference — Phase 6")
    lines.append("")
    lines.append("## 1. G5 — độ chính xác gán đại từ (AC C1)")
    lines.append("")
    lines.append("| Chỉ số | Giá trị |")
    lines.append("|---|---|")
    lines.append(f"| Số câu đối chiếu | {gold_stats['so_sentence_doi_chieu']} |")
    lines.append(f"| Số mention trong gold | {gold_stats['so_mention_gold']} |")
    lines.append(
        f"| Số mention có nhãn vàng (`canonical_id`) | {gold_stats['so_mention_co_nhan_vang']} |"
    )
    lines.append(f"| Số dự đoán đúng | {gold_stats['so_dung']} |")
    lines.append(f"| **Độ chính xác** | **{gold_stats['do_chinh_xac']}** |")
    lines.append(
        f"| Hệ thống bỏ sót (gold có, hệ thống null) | {gold_stats['he_thong_bo_sot']} |"
    )
    lines.append(
        f"| Hệ thống gắn thừa (gold null, hệ thống có) | {gold_stats['gold_khong_co_dich_va_he_thong_co']} |"
    )
    lines.append("")
    lines.append("### Theo `resolved_by`")
    lines.append("")
    lines.append("| `resolved_by` | Số mention | Đúng | Độ chính xác |")
    lines.append("|---|---|---|---|")
    for method, stats in gold_stats["theo_resolved_by"].items():
        lines.append(
            f"| `{method}` | {stats['so_mention']} | {stats['so_dung']} | {stats['do_chinh_xac']} |"
        )
    lines.append("")
    lines.append("## 2. G4 — kiểm tra giới tính")
    lines.append("")
    gender = gold_stats["kiem_tra_gioi_tinh"]
    lines.append("| Chỉ số | Giá trị |")
    lines.append("|---|---|")
    lines.append(f"| Số đại từ có giới tính được kiểm tra | {gender['so_mention']} |")
    lines.append(f"| **Số lỗi gắn sai giới tính** | **{gender['so_loi']}** |")
    lines.append("")
    if gender["chi_tiet"]:
        lines.append("Chi tiết lỗi:")
        lines.append("")
        lines.append("| Câu | Đại từ | Giới tính đúng | Giới tính gắn |")
        lines.append("|---|---|---|---|")
        for item in gender["chi_tiet"]:
            lines.append(
                f"| `{item['sentence_id']}` | `{item['text']}` | "
                f"{item['expected_gender']} | {item['entity_gender']} |"
            )
        lines.append("")
    lines.append("## 3. G6 — chủ thể bài (AC C2)")
    lines.append("")
    lines.append("| Chỉ số | Giá trị |")
    lines.append("|---|---|")
    lines.append(f"| Số bài | {subject_stats['so_bai']} |")
    lines.append(
        f"| Số bài có ground-truth | {subject_stats['so_bai_co_ground_truth']} |"
    )
    lines.append(f"| Số đúng | {subject_stats['so_dung']} |")
    lines.append(f"| **Độ chính xác (tất cả)** | **{subject_stats['do_chinh_xac']}** |")
    lines.append(
        f"| **Độ chính xác (bài nhân vật)** | **{subject_stats['do_chinh_xac_bai_nhan_vat']}** |"
    )
    lines.append("")
    if subject_stats["sai_lech"]:
        lines.append("Sai lệch còn lại:")
        lines.append("")
        lines.append("| Kỳ vọng | Thực tế | Số bài |")
        lines.append("|---|---|---|")
        for item in subject_stats["sai_lech"]:
            lines.append(
                f"| {item['expected']} | {item['actual']} | {item['count']} |"
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
        description="Đánh giá coreference (Phase 6)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--gold", default=None, help="Đường dẫn gold JSONL")
    parser.add_argument("--input", default=None, help="Đường dẫn coref_resolved.jsonl")
    parser.add_argument("--out", default=None, help="Đường dẫn báo cáo Markdown")
    parser.add_argument("--json-out", default=None, help="Đường dẫn số liệu JSON")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    coref_config = dict(config.get("coref", {}))
    dump_config = dict(config.get("dump", {}))

    gold_path = resolve_path(
        args.gold or coref_config.get("gold_path", "data/eval/coref_gold_100.jsonl")
    )
    coref_path = resolve_path(
        args.input or coref_config.get("output_path", "data/interim/coref_resolved.jsonl")
    )
    subject_path = resolve_path(
        coref_config.get("article_subject_path", "data/interim/article_subjects.jsonl")
    )
    documents_path = resolve_path(
        coref_config.get("documents_path", "data/interim/documents.jsonl")
    )
    out_path = resolve_path(args.out or "reports/coref_eval.md")
    json_out_path = resolve_path(
        args.json_out or "docs/10-nhat-ky/so-lieu/phase-06-coref-eval.json"
    )

    gold_rows = _load_jsonl(gold_path)
    predictions_list = _load_jsonl(coref_path)
    predictions = {str(row.get("sentence_id")): row for row in predictions_list}

    # Chỉ tính những mention đã được gán tay (`canonical_id` khác None hoặc
    # `resolved_by` khác None) — mention chưa gán thì bỏ qua, không tính sai.
    annotated_rows = [
        row
        for row in gold_rows
        if any(
            mention.get("canonical_id") is not None
            or mention.get("resolved_by") is not None
            for mention in (row.get("mentions") or [])
        )
    ]
    if not annotated_rows:
        logger.warning(
            "Bộ gold chưa được gán tay (mọi `canonical_id` đều null) — "
            "bỏ qua phần đánh giá G5/G4."
        )

    gender_index = _build_gender_index(
        coref_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl")
    )
    gold_stats = (
        evaluate_gold(annotated_rows, predictions, gender_index)
        if annotated_rows
        else {
            "so_sentence_doi_chieu": 0,
            "so_mention_gold": 0,
            "so_mention_co_nhan_vang": 0,
            "so_dung": 0,
            "do_chinh_xac": 0.0,
            "he_thong_resolve": 0,
            "he_thong_bo_sot": 0,
            "gold_khong_co_dich_va_he_thong_co": 0,
            "gold_khong_co_dich": 0,
            "theo_resolved_by": {},
            "kiem_tra_gioi_tinh": {"so_mention": 0, "so_loi": 0, "chi_tiet": []},
        }
    )

    subject_stats = evaluate_article_subject(
        _load_jsonl(subject_path),
        _load_jsonl(documents_path),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_render_markdown(gold_stats, subject_stats), encoding="utf-8")
    logger.info("Đã ghi báo cáo → %s", out_path)

    json_out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {
            "phase": 6,
            "dump_version": dump_config.get("dump_version"),
            "mo_ta": "Đánh giá coreference Phase 6 (G4/G5/G6)",
            "nguon": (
                "python scripts/coref_eval.py --config configs/default.yaml "
                "→ data/eval/coref_gold_100.jsonl + data/interim/coref_resolved.jsonl"
            ),
            "ngay_do": "2026-11-15",
        },
        "gold": gold_stats,
        "chu_the_bai": subject_stats,
    }
    json_out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    logger.info("Đã ghi số liệu máy đọc được → %s", json_out_path)

    logger.info(
        "G5 độ chính xác = %s · G4 lỗi giới tính = %s · G6 chủ thể = %s",
        gold_stats["do_chinh_xac"],
        gold_stats["kiem_tra_gioi_tinh"]["so_loi"],
        subject_stats["do_chinh_xac"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

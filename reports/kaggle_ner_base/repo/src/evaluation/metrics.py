"""Hàm đánh giá dùng chung (Phase 4/5/12).

Hiện có:

- :func:`ner_f1` — F1 cho bài toán NER token-level (seqeval-style), theo
  **entity-level** (span) và theo **type**.
- :func:`span_f1` — F1 span-level tổng quát (dùng cho so sánh span).
- :func:`prf1` — Precision / Recall / F1 từ cặp đếm.

Dùng lại ở Phase 5 (đánh giá mô hình NER) và Phase 12 (đánh giá Text-to-Cypher).

Lưu ý về scheme nhãn: dùng **BIO** (``B-``/``I-``/``O``) — 13 lớp
(6 nhãn × 2 + ``O``), khớp với ``docs/CONTEXT.md`` §2.4.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Sequence


def prf1(true_positive: int, false_positive: int, false_negative: int) -> dict[str, float]:
    """Tính Precision / Recall / F1 từ cặp đếm.

    Args:
        true_positive: Số dự đoán đúng.
        false_positive: Số dự đoán sai (báo dương giả).
        false_negative: Số bỏ sót (âm giả).

    Returns:
        Dict ``{precision, recall, f1, support}``.
    """
    precision = true_positive / (true_positive + false_positive) if (
        true_positive + false_positive
    ) else 0.0
    recall = true_positive / (true_positive + false_negative) if (
        true_positive + false_negative
    ) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "support": true_positive + false_negative,
    }


def _entity_spans(
    tokens: Sequence[str],
    labels: Sequence[str],
) -> list[tuple[int, int, str]]:
    """Chuyển nhãn BIO → danh sách span ``(start, end, type)``.

    Args:
        tokens: Danh sách token (dùng để kiểm tra độ dài).
        labels: Danh sách nhãn BIO.

    Returns:
        Danh sách span, ``end`` exclusive.
    """
    if len(tokens) != len(labels):
        raise ValueError(
            f"Độ dài tokens ({len(tokens)}) != labels ({len(labels)})"
        )

    spans: list[tuple[int, int, str]] = []
    index = 0
    total = len(labels)
    while index < total:
        label = labels[index]
        if label == "O" or "-" not in label:
            index += 1
            continue
        prefix, _, entity_type = label.partition("-")
        if prefix != "B":
            index += 1
            continue
        start = index
        end = index + 1
        while end < total:
            nxt = labels[end]
            if nxt == "O" or "-" not in nxt:
                break
            nxt_prefix, _, nxt_type = nxt.partition("-")
            if nxt_type != entity_type or nxt_prefix != "I":
                break
            end += 1
        spans.append((start, end, entity_type))
        index = end
    return spans


def span_f1(
    gold_spans: Iterable[tuple[int, int, str]],
    pred_spans: Iterable[tuple[int, int, str]],
) -> dict[str, Any]:
    """F1 span-level (entity-level) không phân biệt loại.

    Args:
        gold_spans: Span đúng ``(start, end, type)``.
        pred_spans: Span dự đoán ``(start, end, type)``.

    Returns:
        Dict ``{precision, recall, f1, true_positive, false_positive, false_negative}``.
    """
    gold_set = set(gold_spans)
    pred_set = set(pred_spans)
    true_positive = len(gold_set & pred_set)
    false_positive = len(pred_set - gold_set)
    false_negative = len(gold_set - pred_set)
    result = prf1(true_positive, false_positive, false_negative)
    result.update(
        {
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        }
    )
    return result


def ner_f1(
    pred: Iterable[dict[str, Any]],
    gold: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Tính F1 cho NER token-level (seqeval-style).

    Vì sao entity-level: đánh giá ở mức **span** là cách chuẩn cho NER
    (seqeval mặc định dùng `scheme="I"` — so khớp chuỗi nhãn liên tiếp).
    Dùng mức token sẽ phạt nặng lỗi ranh giới span.

    Args:
        pred: Danh sách record dự đoán, mỗi record có ``tokens`` + ``labels``.
        gold: Danh sách record chuẩn, cùng định dạng.

    Returns:
        Dict gồm ``micro``, ``macro``, ``per_label``, ``n_sentences``.

    Raises:
        ValueError: Nếu ``tokens`` và ``labels`` lệch độ dài.
    """
    pred_list = list(pred)
    gold_list = list(gold)

    # Cặp (span đúng, span dự đoán) theo `sentence_id`.
    pred_by_sid: dict[str, set[tuple[int, int, str]]] = {}
    for record in pred_list:
        sid = record.get("sentence_id")
        spans = _entity_spans(record.get("tokens") or [], record.get("labels") or [])
        pred_by_sid.setdefault(sid, set()).update(spans)

    gold_by_sid: dict[str, set[tuple[int, int, str]]] = {}
    for record in gold_list:
        sid = record.get("sentence_id")
        spans = _entity_spans(record.get("tokens") or [], record.get("labels") or [])
        gold_by_sid.setdefault(sid, set()).update(spans)

    # Gộp theo loại nhãn.
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "fp": 0, "fn": 0}
    )
    for sid in set(gold_by_sid) | set(pred_by_sid):
        gold_spans = gold_by_sid.get(sid, set())
        pred_spans = pred_by_sid.get(sid, set())
        matched = gold_spans & pred_spans
        for span in matched:
            counts[span[2]]["tp"] += 1
        for span in pred_spans - gold_spans:
            counts[span[2]]["fp"] += 1
        for span in gold_spans - pred_spans:
            counts[span[2]]["fn"] += 1

    per_label: dict[str, dict[str, float]] = {}
    for label, count in sorted(counts.items()):
        per_label[label] = prf1(count["tp"], count["fp"], count["fn"])

    total_tp = sum(c["tp"] for c in counts.values())
    total_fp = sum(c["fp"] for c in counts.values())
    total_fn = sum(c["fn"] for c in counts.values())
    micro = prf1(total_tp, total_fp, total_fn)

    f1_values = [stats["f1"] for stats in per_label.values()]
    macro = {
        "precision": round(
            sum(s["precision"] for s in per_label.values()) / len(per_label), 4
        )
        if per_label
        else 0.0,
        "recall": round(
            sum(s["recall"] for s in per_label.values()) / len(per_label), 4
        )
        if per_label
        else 0.0,
        "f1": round(sum(f1_values) / len(f1_values), 4) if f1_values else 0.0,
    }

    return {
        "micro": micro,
        "macro": macro,
        "per_label": per_label,
        "n_sentences": len(set(gold_by_sid) | set(pred_by_sid)),
        "n_gold_entities": sum(len(spans) for spans in gold_by_sid.values()),
        "n_pred_entities": sum(len(spans) for spans in pred_by_sid.values()),
    }


def token_f1(
    pred: Iterable[dict[str, Any]],
    gold: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """F1 ở mức **token** (mọi token ngoài `O` được coi là 1 lớp nhị phân).

    Args:
        pred: Danh sách record dự đoán.
        gold: Danh sách record chuẩn.

    Returns:
        Dict ``{precision, recall, f1}``.
    """
    pred_list = list(pred)
    gold_list = list(gold)
    true_positive = false_positive = false_negative = 0
    for pred_record, gold_record in zip(pred_list, gold_list):
        pred_labels = pred_record.get("labels") or []
        gold_labels = gold_record.get("labels") or []
        for pred_label, gold_label in zip(pred_labels, gold_labels):
            pred_pos = pred_label != "O"
            gold_pos = gold_label != "O"
            if pred_pos and gold_pos:
                true_positive += 1
            elif pred_pos and not gold_pos:
                false_positive += 1
            elif not pred_pos and gold_pos:
                false_negative += 1
    return prf1(true_positive, false_positive, false_negative)

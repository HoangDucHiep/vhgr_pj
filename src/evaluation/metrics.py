"""Hàm đánh giá dùng chung (Phase 4/5/8/12).

Hiện có:

- :func:`ner_f1` — F1 cho bài toán NER token-level (seqeval-style), theo
  **entity-level** (span) và theo **type**.
- :func:`span_f1` — F1 span-level tổng quát (dùng cho so sánh span).
- :func:`prf1` — Precision / Recall / F1 từ cặp đếm.
- :func:`relation_f1_multilabel` — F1 cho bài toán RE **đa nhãn** (Phase 8).

Dùng lại ở Phase 5 (đánh giá mô hình NER), Phase 8 (đánh giá mô hình RE)
và Phase 12 (đánh giá Text-to-Cypher).

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


# ---------------------------------------------------------------------------
# Relation Extraction đa nhãn (Phase 8 — D1.2)
# ---------------------------------------------------------------------------


def relation_f1_multilabel(
    pred: Iterable[dict[str, Any]],
    gold: Iterable[dict[str, Any]],
    *,
    relations: Sequence[str] | None = None,
    na_label: str = "NA",
) -> dict[str, Any]:
    """Tính F1 cho bài toán RE **đa nhãn** (mô hình 18 quan hệ + ``NA``).

    Vì sao cần hàm riêng
    --------------------
    Bài toán RE ở Phase 8 là **đa nhãn**: một cặp (subject, object) trong một
    câu có thể đồng thời thỏa nhiều quan hệ (đo được ở Phase 7: 1.777/26.030
    input có ≥ 2 quan hệ POSITIVE, trong đó 53,7% là cặp ``cha_cua`` +
    ``me_cua`` — quan hệ *song sinh* hợp lệ). Vì vậy:

    - Một input có thể có **nhiều** nhãn đúng → so khớp theo **tập** quan hệ.
    - Quan hệ chưa được giám sát cho input đó là **ẩn (masked)**, không phải
      "không có quan hệ" → không được tính vào false negative.

    Định dạng input
    ---------------
    Mỗi record (một *input*) gồm:

    - ``key``: khóa định danh input (thường là
      ``(sentence_id, subject_entity_id, object_entity_id)``).
    - ``relations``: tập quan hệ **đúng** (gold) — rỗng nghĩa là chỉ có ``NA``.
    - ``masked``: tập quan hệ **ẩn** (chưa giám sát) — không tính vào FN.
    - ``predicted``: tập quan hệ **dự đoán** (model đã lọc ``NA`` rồi).

    Chuẩn hoá orientation được xử lý ở tầng gọi (đảm bảo cùng key cho
    quan hệ đối xứng).

    Args:
        pred: Danh sách record dự đoán.
        gold: Danh sách record gold, cùng định dạng.
        relations: Danh sách quan hệ cần báo cáo per-relation. Mặc định là
            hợp nhất các quan hệ xuất hiện ở gold hoặc pred.
        na_label: Nhãn dùng cho đầu ra "không có quan hệ".

    Returns:
        Dict gồm ``micro``, ``macro``, ``per_relation``, ``na``,
        ``n_inputs``, ``n_gold_pairs``.
    """
    pred_list = list(pred)
    gold_list = list(gold)

    def _key_of(record: dict[str, Any]) -> Any:
        """Lấy khóa input của một record.

        Args:
            record: Record đầu vào.

        Returns:
            Khóa input.
        """
        if "key" in record:
            return record["key"]
        return (
            record.get("sentence_id"),
            record.get("subject"),
            record.get("object"),
        )

    gold_by_key: dict[Any, set[str]] = {}
    masked_by_key: dict[Any, set[str]] = {}
    for record in gold_list:
        key = _key_of(record)
        gold_by_key.setdefault(key, set()).update(record.get("relations") or ())
        masked_by_key.setdefault(key, set()).update(record.get("masked") or ())

    pred_by_key: dict[Any, set[str]] = {}
    for record in pred_list:
        key = _key_of(record)
        pred_by_key.setdefault(key, set()).update(record.get("predicted") or ())

    all_keys = set(gold_by_key) | set(pred_by_key)

    if relations is None:
        relation_set: set[str] = set()
        for key in all_keys:
            relation_set |= gold_by_key.get(key, set())
            relation_set |= pred_by_key.get(key, set())
        relation_list = sorted(relation_set)
    else:
        relation_list = list(relations)

    counts: dict[str, dict[str, int]] = {
        relation: {"tp": 0, "fp": 0, "fn": 0, "support": 0}
        for relation in relation_list
    }

    na_tp = na_fp = na_fn = 0

    for key in all_keys:
        gold_set = gold_by_key.get(key, set())
        masked = masked_by_key.get(key, set())
        pred_set = pred_by_key.get(key, set())

        # Quan hệ đúng mà mô hình bỏ sót → FN (trừ phần bị mask).
        for relation in gold_set:
            if relation in masked:
                continue
            if relation not in pred_set:
                counts.setdefault(
                    relation, {"tp": 0, "fp": 0, "fn": 0, "support": 0}
                )["fn"] += 1

        # Quan hệ mô hình bịa ra → FP (chỉ tính quan hệ có trong tập theo dõi).
        for relation in pred_set:
            if relation in gold_set:
                continue
            if relation in masked:
                continue
            if relation in counts:
                counts[relation]["fp"] += 1

        for relation in gold_set:
            if relation in masked:
                continue
            counts.setdefault(
                relation, {"tp": 0, "fp": 0, "fn": 0, "support": 0}
            )["support"] += 1
            if relation in pred_set:
                counts[relation]["tp"] += 1

        # Đầu NA: đúng khi input không có quan hệ nào trong gold.
        gold_na = not gold_set
        pred_na = not pred_set
        if gold_na and pred_na:
            na_tp += 1
        elif pred_na and not gold_na:
            na_fn += 1
        elif gold_na and not pred_na:
            na_fp += 1

    per_relation: dict[str, dict[str, float]] = {}
    for relation, count in counts.items():
        stats = prf1(count["tp"], count["fp"], count["fn"])
        stats["support"] = count["support"]
        per_relation[relation] = stats

    total_tp = sum(c["tp"] for c in counts.values())
    total_fp = sum(c["fp"] for c in counts.values())
    total_fn = sum(c["fn"] for c in counts.values())
    micro = prf1(total_tp, total_fp, total_fn)

    evaluated = [s["f1"] for s in per_relation.values() if s["support"] > 0]
    macro = {
        "precision": round(
            sum(
                s["precision"]
                for s in per_relation.values()
                if s["support"] > 0
            )
            / len(evaluated),
            4,
        )
        if evaluated
        else 0.0,
        "recall": round(
            sum(
                s["recall"]
                for s in per_relation.values()
                if s["support"] > 0
            )
            / len(evaluated),
            4,
        )
        if evaluated
        else 0.0,
        "f1": round(sum(evaluated) / len(evaluated), 4) if evaluated else 0.0,
    }

    return {
        "micro": micro,
        "macro": macro,
        "per_relation": per_relation,
        "na": prf1(na_tp, na_fp, na_fn),
        "n_inputs": len(all_keys),
        "n_gold_pairs": sum(
            len(gold_by_key.get(key, set()) - masked_by_key.get(key, set()))
            for key in gold_by_key
        ),
        "na_label": na_label,
    }

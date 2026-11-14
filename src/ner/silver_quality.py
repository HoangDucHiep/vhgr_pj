"""Đánh giá chất lượng nhãn bạc NER (Phase 4 — B2.2).

Vì sao cần: nhãn bạc sinh tự động, không có "đáp án" để so. Để đo được
chất lượng thật, dùng **2 rule baseline** đánh giá trên tập dev:

1. **Surface baseline** (``surface``) — chỉ dùng **văn bản thô**: chuỗi tên
   riêng (viết hoa) + hậu tố/tiền tố trong tên + regex năm. Không dùng QID,
   không dùng đích link. Đây là baseline "mù" — đo xem nhãn bạc có bám sát
   **tín hiệu bề mặt** hay không.

2. **Gazetteer baseline** (``gazetteer``) — dựng bảng *tên → loại* từ tập
   **train** (chỉ dùng nhãn bạc của train), rồi dự đoán tập dev bằng bảng
   tra cứu. Đây là baseline **có học** nhưng không cần mô hình — đo xem nhãn
   bạc có **tự nhất quán** đủ để huấn luyện mô hình không. Không bao giờ
   dùng nhãn dev để dựng gazetteer (tránh rò rỉ).

**Cả 2 baseline chỉ dự đoán trên tập ứng viên giống hệt nhãn bạc** — tức là
trên các **span đã gắn hyperlink** (candidate). Nếu không, baseline sẽ dự
đoán mọi cụm tên riêng trong câu (kể cả những cụm không phải entity), dẫn
tới precision thấp vô nghĩa và che mất câu hỏi thật: *"nếu biết trước vị
trí entity, mô hình có đoán đúng loại không?"*.

Ý nghĩa: nếu ``gazetteer`` F1 cao ⇒ nhãn bạc nhất quán, đủ dùng để train
(Gate Phase 4 yêu cầu ≥ 0.60). Nếu ``surface`` thấp hơn nhiều ⇒ nhãn bạc
đang dùng thông tin mà rule bề mặt không có (ví dụ loại suy từ Wikidata),
tức nhãn bạc **có thêm** thông tin, không phải lỗi.

Báo cáo thêm:

- Phân bố nhãn (6 lớp + ``O``).
- Tỉ lệ câu có nhãn.
- Phân bố **nguồn nhãn** (category / qid / kg / pattern / time_regex).
- Độ dài mention theo lớp (phát hiện nhãn quá dài / quá ngắn).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from src.common.config import resolve_path
from src.common.logger import get_logger
from src.evaluation.metrics import ner_f1
from src.ner.build_silver import NER_LABELS, strip_accents, tokenize

logger = get_logger(__name__)

#: Hậu tố (bỏ dấu) cho thấy tên là **tước hiệu**, không phải người.
_TITLE_SUFFIXES: tuple[str, ...] = (
    "(miieu hieu)",
    "(thuy hieu)",
    "(trieu hieu)",
    "(hieu)",
)

#: Tiền tố cho thấy tên là **triều đại**.
_DYNASTY_PREFIXES: tuple[str, ...] = (
    "nha ",
    "trieu dai ",
    "de trieu dai ",
    "vo trieu dai ",
)

#: Tiền tố cho thấy tên là **sự kiện**.
_EVENT_PREFIXES: tuple[str, ...] = ("tran ", "chien tranh ", "cuoc chien ", "le ")

#: Tiền tố cho thấy tên là **địa danh**.
_LOCATION_PREFIXES: tuple[str, ...] = (
    "tinh ",
    "thanh pho ",
    "thanh ",
    "huyen ",
    "xa ",
    "lang ",
    "ap ",
)

#: Từ bị loại (stopword) — không phải tên riêng.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "va",
        "la",
        "cua",
        "cho",
        "voi",
        "trong",
        "tu",
        "den",
        "o",
        "nhung",
        "mot",
        "cac",
        "nhom",
        "nhan",
        "ra",
        "thi",
        "theo",
        "sau",
        "truoc",
        "khi",
        "nay",
        "day",
        "do",
        "bi",
        "duoc",
        "da",
        "se",
        "vao",
        "the",
        "ve",
        "tai",
        "quoc",
        "gia",
        "nam",
        "moi",
        "tat",
        "ca",
        "ke",
        "nen",
        "neu",
        "hoac",
        "ma",
        "cong",
        "gia",
        "xay",
        "dung",
        "da",
        "de",
        "ra",
        "vao",
        "tu",
        "tren",
        "duoi",
        "qua",
        "giua",
        "canh",
        "khu",
        "vung",
        "mien",
        "bac",
        "nam",
        "dong",
        "tay",
        "phuong",
        "mien",
    }
)


def _is_proper_noun(token: str) -> bool:
    """Kiểm tra token có phải tên riêng không (viết hoa, không phải stopword).

    Args:
        token: Token cần kiểm tra.

    Returns:
        `True` nếu có khả năng là tên riêng.
    """
    if not token or not token[0].isupper():
        return False
    if strip_accents(token).lower() in _STOPWORDS:
        return False
    return len(token) >= 2 and any(ch.isalpha() for ch in token)


def surface_spans(tokens: list[str]) -> list[tuple[int, int, str]]:
    """Sinh span nhãn theo **surface baseline** (chỉ dùng văn bản thô).

    Quy tắc:

    1. Chuỗi **tên riêng** (token viết hoa liên tiếp) → `PERSON`.
    2. Năm 3–4 chữ số → `TIME`.
    3. Tên có hậu tố miếu/thuỷ/trieu hiệu → `TITLE`.
    4. Tên bắt đầu bằng tiền tố triều đại → `DYNASTY`.
    5. Tên bắt đầu bằng tiền tố sự kiện → `EVENT`.
    6. Tên bắt đầu bằng tiền tố địa danh → `LOCATION`.

    Args:
        tokens: Danh sách token của câu.

    Returns:
        Danh sách span ``(start, end, label)`` — ``end`` exclusive.
    """
    spans: list[tuple[int, int, str]] = []
    total = len(tokens)
    index = 0

    while index < total:
        token = tokens[index]
        if not _is_proper_noun(token):
            index += 1
            continue

        # Gom chuỗi tên riêng liên tiếp.
        start = index
        end = index + 1
        while end < total and _is_proper_noun(tokens[end]):
            end += 1
        span_text = " ".join(tokens[start:end])
        normalized = strip_accents(span_text)

        label: str
        if any(normalized.endswith(suffix) for suffix in _TITLE_SUFFIXES):
            label = "TITLE"
        elif any(normalized.startswith(prefix) for prefix in _DYNASTY_PREFIXES):
            label = "DYNASTY"
        elif any(normalized.startswith(prefix) for prefix in _EVENT_PREFIXES):
            label = "EVENT"
        elif any(normalized.startswith(prefix) for prefix in _LOCATION_PREFIXES):
            label = "LOCATION"
        else:
            label = "PERSON"

        spans.append((start, end, label))
        index = end

    # Năm → TIME (chỉ khi chưa nằm trong span khác).
    for index, token in enumerate(tokens):
        if not re.fullmatch(r"\d{3,4}", token):
            continue
        if any(start <= index < end for start, end, _ in spans):
            continue
        spans.append((index, index + 1, "TIME"))

    return sorted(spans)


def build_bioes_from_spans(
    n_tokens: int,
    spans: list[tuple[int, int, str]],
) -> list[str]:
    """Chuyển span → nhãn BIOES.

    Args:
        n_tokens: Tổng số token.
        spans: Danh sách span ``(start, end, label)``.

    Returns:
        Danh sách nhãn BIOES.
    """
    from src.ner.build_silver import build_bioes

    return build_bioes(n_tokens, spans)


def _mention_text(record: dict[str, Any], mention: dict[str, Any]) -> str:
    """Lấy text chuẩn hoá (bỏ dấu, thường) của một mention.

    Args:
        record: Record chứa câu.
        mention: Mention cần xử lý.

    Returns:
        Chuỗi khóa (bỏ dấu, viết thường, cách nhau bằng dấu cách).
    """
    tokens = record.get("tokens") or []
    text = " ".join(
        tokens[mention["start_token"] : mention["end_token"]]
    )
    return strip_accents(text)


def build_gazetteer(
    train_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Dựng bảng tra cứu *tên → loại* từ tập train.

    Args:
        train_rows: Các record của tập train (nhãn bạc).

    Returns:
        Map ``{tên (bỏ dấu): loại phổ biến nhất}``.
    """
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for record in train_rows:
        for mention in record.get("mentions") or []:
            key = _mention_text(record, mention)
            label = mention.get("label")
            if key and label:
                votes[key][label] += 1
    return {
        key: counter.most_common(1)[0][0]
        for key, counter in votes.items()
    }


def gazetteer_spans(
    tokens: list[str],
    gazetteer: dict[str, str],
) -> list[tuple[int, int, str]]:
    """Dự đoán span từ gazetteer (khớp cụm tên dài nhất).

    Args:
        tokens: Danh sách token.
        gazetteer: Bảng ``{tên (bỏ dấu): loại}``.

    Returns:
        Danh sách span ``(start, end, label)``.
    """
    spans: list[tuple[int, int, str]] = []
    total = len(tokens)
    index = 0
    while index < total:
        matched = False
        # Thử cụm dài nhất trước (tối đa 6 token).
        for length in range(min(6, total - index), 0, -1):
            candidate = strip_accents(" ".join(tokens[index : index + length]))
            label = gazetteer.get(candidate)
            if label is not None:
                spans.append((index, index + length, label))
                index += length
                matched = True
                break
        if not matched:
            index += 1
    return spans


def candidate_spans(record: dict[str, Any]) -> list[tuple[int, int]]:
    """Lấy tập **ứng viên** (span đã gắn hyperlink) của một câu.

    Đây là tập vị trí mà nhãn bạc đánh dấu. Baseline chỉ được dự đoán trên
    tập này — nếu không, baseline sẽ dự đoán mọi cụm tên riêng trong câu và
    phép so sánh sẽ vô nghĩa.

    Args:
        record: Record của câu.

    Returns:
        Danh sách ``(start_token, end_token)``.
    """
    spans: list[tuple[int, int]] = []
    for mention in record.get("mentions") or []:
        if not mention.get("target"):
            continue  # chỉ ứng viên đến từ hyperlink
        spans.append((int(mention["start_token"]), int(mention["end_token"])))
    return spans


def surface_label_for_span(
    span_text: str,
    tokens: list[str],
) -> str | None:
    """Suy nhãn cho một span ứng viên bằng **rule bề mặt**.

    Args:
        span_text: Text của span (đã tách token bằng dấu cách).
        tokens: Token của span.

    Returns:
        Nhãn, hoặc ``None`` nếu rule không đủ tín hiệu.
    """
    normalized = strip_accents(span_text)
    if any(normalized.endswith(suffix) for suffix in _TITLE_SUFFIXES):
        return "TITLE"
    if any(normalized.startswith(prefix) for prefix in _DYNASTY_PREFIXES):
        return "DYNASTY"
    if any(normalized.startswith(prefix) for prefix in _EVENT_PREFIXES):
        return "EVENT"
    if any(normalized.startswith(prefix) for prefix in _LOCATION_PREFIXES):
        return "LOCATION"
    if len(tokens) == 1 and re.fullmatch(r"\d{3,4}", tokens[0]):
        return "TIME"
    # Chuỗi tên riêng (mọi token viết hoa) → PERSON.
    if tokens and all(_is_proper_noun(token) for token in tokens):
        return "PERSON"
    return None


def surface_labels_on_candidates(
    record: dict[str, Any],
) -> list[tuple[int, int, str]]:
    """Dự đoán nhãn của rule bề mặt trên tập ứng viên.

    Args:
        record: Record của câu.

    Returns:
        Danh sách span ``(start, end, label)``.
    """
    tokens = record.get("tokens") or []
    spans: list[tuple[int, int, str]] = []
    for start, end in candidate_spans(record):
        span_tokens = tokens[start:end]
        if not span_tokens:
            continue
        label = surface_label_for_span(" ".join(span_tokens), span_tokens)
        if label is not None:
            spans.append((start, end, label))
    return spans


def gazetteer_labels_on_candidates(
    record: dict[str, Any],
    gazetteer: dict[str, str],
) -> list[tuple[int, int, str]]:
    """Dự đoán nhãn từ gazetteer trên tập ứng viên.

    Args:
        record: Record của câu.
        gazetteer: Bảng ``{tên (bỏ dấu): loại}``.

    Returns:
        Danh sách span ``(start, end, label)``.
    """
    tokens = record.get("tokens") or []
    spans: list[tuple[int, int, str]] = []
    for start, end in candidate_spans(record):
        key = strip_accents(" ".join(tokens[start:end]))
        label = gazetteer.get(key)
        if label is not None:
            spans.append((start, end, label))
    return spans


def evaluate_silver(
    *,
    silver_path: str | Path,
    splits_path: str | Path,
    out_report: str | Path | None = None,
) -> dict[str, Any]:
    """Đánh giá nhãn bạc: 2 rule baseline trên tập dev + thống kê toàn corpus.

    Args:
        silver_path: Đường dẫn `ner_silver.jsonl`.
        splits_path: Đường dẫn `splits.json`.
        out_report: Đường dẫn báo cáo Markdown (tùy chọn).

    Returns:
        Dict thống kê tổng hợp.
    """
    from src.ner.make_splits import load_splits

    splits = load_splits(splits_path)
    train_pages = set(splits.get("train") or [])
    dev_pages = set(splits.get("dev") or [])

    label_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    mention_len: dict[str, list[int]] = defaultdict(list)
    n_sentences = 0
    n_sentences_labelled = 0
    n_sentences_with_link = 0
    n_sentences_with_link_labelled = 0
    n_mentions = 0

    train_rows: list[dict[str, Any]] = []
    dev_rows: list[dict[str, Any]] = []

    resolved = resolve_path(silver_path)
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            n_sentences += 1
            labels = record.get("labels") or []
            tokens = record.get("tokens") or []
            label_counter.update(labels)

            has_link = any(
                mention.get("target") for mention in (record.get("mentions") or [])
            )
            if has_link:
                n_sentences_with_link += 1

            has_label = any(label != "O" for label in labels)
            if has_label:
                n_sentences_labelled += 1
                if has_link:
                    n_sentences_with_link_labelled += 1

            for mention in record.get("mentions") or []:
                n_mentions += 1
                source_counter[mention.get("source") or "unknown"] += 1
                mention_len[mention.get("label") or "?"].append(
                    int(mention.get("end_token", 0)) - int(mention.get("start_token", 0))
                )

            page_id = record.get("page_id")
            if page_id in train_pages:
                train_rows.append(record)
            elif page_id in dev_pages:
                dev_rows.append(record)

    # --- Baseline 1: surface (chỉ văn bản thô, trên tập ứng viên) ---
    surface_pred = [
        {
            "sentence_id": record.get("sentence_id"),
            "tokens": record.get("tokens") or [],
            "labels": build_bioes_from_spans(
                len(record.get("tokens") or []),
                surface_labels_on_candidates(record),
            ),
        }
        for record in dev_rows
    ]
    surface = ner_f1(surface_pred, dev_rows)

    # --- Baseline 2: gazetteer (dựng từ TRAIN, dự đoán DEV) ---
    gazetteer = build_gazetteer(train_rows)
    gazetteer_pred = [
        {
            "sentence_id": record.get("sentence_id"),
            "tokens": record.get("tokens") or [],
            "labels": build_bioes_from_spans(
                len(record.get("tokens") or []),
                gazetteer_labels_on_candidates(record, gazetteer),
            ),
        }
        for record in dev_rows
    ]
    gazetteer_result = ner_f1(gazetteer_pred, dev_rows)

    stats = {
        "n_sentences": n_sentences,
        "n_mentions": n_mentions,
        "n_sentences_labelled": n_sentences_labelled,
        "n_sentences_with_link": n_sentences_with_link,
        "n_sentences_with_link_labelled": n_sentences_with_link_labelled,
        "coverage": round(n_sentences_labelled / n_sentences, 4) if n_sentences else 0.0,
        "coverage_linked": round(
            n_sentences_with_link_labelled / n_sentences_with_link, 4
        )
        if n_sentences_with_link
        else 0.0,
        "label_distribution": {
            label: label_counter.get(label, 0) for label in ("O", *NER_LABELS)
        },
        "entity_distribution": {
            label: label_counter.get(f"B-{label}", 0) for label in NER_LABELS
        },
        "source_distribution": dict(source_counter.most_common()),
        "mention_length_mean": {
            label: round(sum(values) / len(values), 2) if values else 0.0
            for label, values in sorted(mention_len.items())
        },
        "dev": {
            "n_sentences": len(dev_rows),
            "n_train_sentences": len(train_rows),
            "gazetteer_size": len(gazetteer),
            "baseline_surface": surface,
            "baseline_gazetteer": gazetteer_result,
        },
    }

    if out_report:
        _write_report(resolve_path(out_report), stats)

    logger.info(
        "Câu có nhãn: %d/%d (%.1f%%)",
        n_sentences_labelled,
        n_sentences,
        stats["coverage"] * 100,
    )
    logger.info(
        "Câu có link có nhãn: %d/%d (%.1f%%)",
        n_sentences_with_link_labelled,
        n_sentences_with_link,
        stats["coverage_linked"] * 100,
    )
    logger.info(
        "Baseline surface F1 (dev): %.4f | gazetteer F1 (dev): %.4f",
        surface["micro"]["f1"],
        gazetteer_result["micro"]["f1"],
    )
    logger.info("Phân bố nhãn: %s", stats["entity_distribution"])
    logger.info("Nguồn nhãn: %s", stats["source_distribution"])
    return stats


def _write_report(path: Path, stats: dict[str, Any]) -> None:
    """Ghi báo cáo Markdown.

    Args:
        path: Đường dẫn output.
        stats: Thống kê từ :func:`evaluate_silver`.
    """
    surface = stats["dev"]["baseline_surface"]
    gazetteer = stats["dev"]["baseline_gazetteer"]
    lines: list[str] = [
        "# Báo cáo chất lượng nhãn bạc NER (Phase 4)",
        "",
        "## Tổng quan",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---|",
        f"| Số câu | {stats['n_sentences']:,} |",
        f"| Số mention | {stats['n_mentions']:,} |",
        f"| Câu có nhãn | {stats['n_sentences_labelled']:,} ({stats['coverage']:.1%}) |",
        f"| Câu có link nội bộ | {stats['n_sentences_with_link']:,} |",
        (
            f"| Câu có link **có nhãn** | {stats['n_sentences_with_link_labelled']:,} "
            f"({stats['coverage_linked']:.1%}) |"
        ),
        "",
        "## Phân bố nhãn (entity)",
        "",
        "| Nhãn | Số entity |",
        "|---|---|",
    ]
    for label, count in stats["entity_distribution"].items():
        lines.append(f"| {label} | {count:,} |")
    lines.extend(
        [
            "",
            "## Nguồn nhãn",
            "",
            "| Nguồn | Số mention |",
            "|---|---|",
        ]
    )
    for source, count in stats["source_distribution"].items():
        lines.append(f"| {source} | {count:,} |")
    lines.extend(
        [
            "",
            "## Độ dài mention trung bình (số token)",
            "",
            "| Nhãn | Độ dài TB |",
            "|---|---|",
        ]
    )
    for label, value in stats["mention_length_mean"].items():
        lines.append(f"| {label} | {value} |")

    for name, result, description in (
        (
            "Baseline surface",
            surface,
            "Chỉ dùng văn bản thô (tên riêng viết hoa + hậu tố/tiền tố + regex năm).",
        ),
        (
            "Baseline gazetteer",
            gazetteer,
            "Bảng tra cứu *tên → loại* dựng từ tập **train**, dự đoán tập **dev**.",
        ),
    ):
        lines.extend(
            [
                "",
                f"## {name}",
                "",
                description,
                "",
                "| Chỉ số | Giá trị |",
                "|---|---|",
                f"| micro F1 | {result['micro']['f1']:.4f} |",
                f"| micro P | {result['micro']['precision']:.4f} |",
                f"| micro R | {result['micro']['recall']:.4f} |",
                f"| macro F1 | {result['macro']['f1']:.4f} |",
                "",
                "### F1 theo loại",
                "",
                "| Nhãn | P | R | F1 | Support |",
                "|---|---|---|---|---|",
            ]
        )
        for label, values in result["per_label"].items():
            lines.append(
                f"| {label} | {values['precision']:.4f} | {values['recall']:.4f} "
                f"| {values['f1']:.4f} | {values['support']} |"
            )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Đánh giá nhãn bạc NER (Phase 4)")
    parser.add_argument("--silver", default="data/interim/ner_silver.jsonl")
    parser.add_argument("--splits", default="data/splits/splits.json")
    parser.add_argument("--out", default="reports/silver_quality.md")
    parser.add_argument("--stats-out", default=None)
    args = parser.parse_args(argv)

    stats = evaluate_silver(
        silver_path=args.silver,
        splits_path=args.splits,
        out_report=args.out,
    )
    if args.stats_out:
        out = resolve_path(args.stats_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tách câu và đoạn từ văn bản đã làm sạch (Module A3 — Phase 2).

## Yêu cầu offset chính xác

`char_start` / `char_end` của mỗi câu là **offset ký tự trong `clean_text`**
(cùng chuỗi mà `links` dùng) — Phase 4/5/6 đều dựa vào điều này để ánh xạ
mention về đúng vị trí.

## Vì sao dùng `pysbd` với bộ quy tắc tiếng Anh

`pysbd` 0.3.4 (bản cài được trên Python 3.14) hỗ trợ 23 ngôn ngữ và **không
có tiếng Việt**, cũng không có `Language.MULTI` — đó là API của bản khác.
Bộ quy tắc tiếng Anh vẫn tách đúng tiếng Việt vì dấu kết thúc câu
(`.`/`!`/`?`/`…`) là giống nhau, và tiếng Việt không có dấu phẩy trước
khi kết thúc câu.

Nếu `pysbd` lỗi, fallback sang regex với bảng ngoại lệ tên riêng trong
`configs/name_exceptions.yaml` (mục "Lùi" của Phase 2 trong `docs/09`).

Cách chạy:
    python -m src.preprocess.split_sentences --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT, load_config
from src.common.ids import make_sentence_id
from src.common.logger import get_logger
from src.common.text_utils import paragraph_spans, read_jsonl

logger = get_logger(__name__)

#: Regex fallback tách câu: dấu kết thúc + khoảng trắng + chữ hoa.
_FALLBACK_SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ỹ\"'(])")

#: Tên riêng có dấu phẩy bên trong — không được tách câu ở đó.
_NAME_EXCEPTIONS: tuple[str, ...] = (
    "Lê Lợi",
    "Trần Hưng Đạo",
    "Trần Quốc Tuấn",
    "Nguyễn Trãi",
    "Hồ Chí Minh",
    "Võ Nguyên Giáp",
    "Đặng Thùy Trâm",
    "Nguyễn Du",
    "Trương Vĩnh Ký",
)

#: Dấu kết thúc câu hợp lệ (dùng cho thống kê).
SENTENCE_ENDINGS = (".", "!", "?", "…")

#: Ngôn ngữ truyền cho `pysbd.Segmenter`. `pysbd` 0.3.4 không có "multi".
_PYSBD_LANGUAGE = "en"


#: Segmenter `pysbd` dùng chung cho toàn corpus — tạo lại cho mỗi đoạn sẽ
#: tốn ~3 phút cho 2.441 bài (đo được), nên cache lại ở mức module.
_SEGMENTER: Any = None


def _get_segmenter() -> Any:
    """Trả về segmenter `pysbd` (khởi tạo một lần rồi cache).

    Returns:
        Đối tượng `pysbd.Segmenter`.
    """
    global _SEGMENTER
    if _SEGMENTER is None:
        import pysbd

        _SEGMENTER = pysbd.Segmenter(
            language=_PYSBD_LANGUAGE, clean=False, char_span=True
        )
    return _SEGMENTER


def _load_name_exceptions(path: Path) -> tuple[str, ...]:
    """Nạp danh sách tên riêng từ file YAML (nếu có).

    Args:
        path: Đường dẫn `configs/name_exceptions.yaml`.

    Returns:
        Tuple tên riêng.
    """
    if not path.exists():
        return _NAME_EXCEPTIONS
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = tuple(str(name) for name in data.get("names", []))
    return names or _NAME_EXCEPTIONS


def _segment(text: str) -> list[tuple[int, int]]:
    """Tách câu, trả về danh sách `(start, end)` trong `text`.

    Args:
        text: Văn bản đã làm sạch.

    Returns:
        Danh sách cặp offset (không bao gồm).
    """
    if not text.strip():
        return []

    spans: list[tuple[int, int]] = []
    try:
        import pysbd

        # `pysbd` 0.3.4 **không có** `Language.MULTI` (đó là API của bản khác).
        # Bản cài đặt chỉ hỗ trợ 23 ngôn ngữ, trong đó không có tiếng Việt;
        # bộ quy tắc tiếng Anh vẫn tách đúng tiếng Việt vì dấu kết thúc câu
        # (`.`/`!`/`?`/`…`) là giống nhau. Xem `reports/deviations.md` D-013.
        segmenter = _get_segmenter()
        for sentence in segmenter.segment(text):
            start = sentence.start
            end = sentence.end
            if end > start:
                spans.append((start, end))
        if spans:
            return spans
    except Exception as exc:  # pragma: no cover - phụ thuộc môi trường
        logger.warning("pysbd lỗi, dùng regex fallback: %s", exc)

    position = 0
    for match in _FALLBACK_SENTENCE_RE.finditer(text):
        spans.append((position, match.start()))
        position = match.end()
    spans.append((position, len(text)))
    return [(start, end) for start, end in spans if end > start]


def build_paragraphs(
    text: str,
    headings: list[dict[str, Any]],
    paragraph_kinds: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Tách đoạn theo dòng trống, đánh dấu đoạn là tiêu đề.

    Args:
        text: Văn bản đã làm sạch.
        headings: Danh sách tiêu đề đã trích từ `clean_text.py`.
        paragraph_kinds: Nhãn từng đoạn từ `clean_text.py` (``"prose"`` /
            ``"list_item"``). Nếu `None`, mọi đoạn được coi là văn xuôi.

    Returns:
        Danh sách dict đoạn: ``para_idx``, ``text``, ``char_start``, ``char_end``,
        ``heading``, ``kind``.
    """
    heading_titles = {str(item.get("title", "")).strip() for item in headings}
    # Tiêu đề có thể chứa link (`== Thời [[nhà Nguyễn]] ==`) — `clean_text`
    # đã thay link nên phải so sánh cả bản "rút gọn".
    heading_titles |= {
        str(item.get("plain_title", item.get("title", ""))).strip()
        for item in headings
    }
    kinds = paragraph_kinds or []
    paragraphs: list[dict[str, Any]] = []
    for para_idx, (start, end) in enumerate(paragraph_spans(text)):
        body = text[start:end]
        # Nhãn đoạn do `clean_text.py` gắn theo **nội dung** (xem
        # `_label_paragraphs`), nên chỉ số luôn khớp với đoạn ở đây.
        kind = kinds[para_idx] if para_idx < len(kinds) else "prose"
        paragraphs.append(
            {
                "para_idx": para_idx,
                "text": body,
                "char_start": start,
                "char_end": end,
                "heading": body.strip() in heading_titles,
                "kind": kind,
            }
        )
    return paragraphs


def build_sentences(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Sinh danh sách câu + đoạn cho một document đã làm sạch.

    Args:
        doc: Record document (cần `doc_id`, `page_id`, `clean_text`).

    Returns:
        Danh sách dict câu theo output contract của Phase 2.
    """
    text = doc.get("clean_text", "")
    page_id = int(doc.get("page_id", 0))
    doc_id = doc.get("doc_id", f"doc_{page_id}")

    paragraphs = build_paragraphs(
        text, doc.get("headings", []), doc.get("paragraph_kinds")
    )
    sentences: list[dict[str, Any]] = []

    for para in paragraphs:
        # Đoạn là TIÊU ĐỀ mục (vd "Tiểu sử", "Tham khảo") không phải văn xuôi
        # → không sinh câu. Đo được trên corpus trước khi sửa: 9,5% "câu" là
        # tiêu đề, không có dấu kết thúc → kéo tỉ lệ câu hợp lệ xuống 74,34%.
        # Tiêu đề vẫn được giữ đầy đủ trong `paragraphs` (mục "Tiểu sử" là
        # ranh giới đoạn quan trọng cho Phase 4/5).
        if para.get("heading"):
            continue

        para_text = para["text"]
        for sent_idx, (local_start, local_end) in enumerate(_segment(para_text)):
            start = para["char_start"] + local_start
            end = para["char_start"] + local_end
            body = text[start:end]
            if not body.strip():
                continue
            sentences.append(
                {
                    "sentence_id": make_sentence_id(page_id, para["para_idx"], sent_idx),
                    "doc_id": doc_id,
                    "para_idx": para["para_idx"],
                    "sent_idx": sent_idx,
                    "text": body.strip(),
                    "char_start": start + (len(body) - len(body.lstrip())),
                    "char_end": end - (len(body) - len(body.rstrip())),
                    "para_kind": para.get("kind", "prose"),
                }
            )

    return sentences


def assign_links_to_sentences(
    sentences: list[dict[str, Any]], links: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Gán `sentence_id` cho từng hyperlink theo vị trí offset.

    Args:
        sentences: Danh sách câu (đã sắp xếp theo offset).
        links: Danh sách link có `start`/`end`.

    Returns:
        Danh sách link đã bổ sung `sentence_id` và `para_idx`.
    """
    if not sentences:
        return links

    starts = [sentence["char_start"] for sentence in sentences]
    enriched: list[dict[str, Any]] = []
    for link in links:
        position = link.get("start", 0)
        low, high = 0, len(starts) - 1
        found = -1
        while low <= high:
            mid = (low + high) // 2
            if starts[mid] <= position:
                found = mid
                low = mid + 1
            else:
                high = mid - 1
        if found == -1:
            continue
        sentence = sentences[found]
        if link.get("end", 0) > sentence["char_end"]:
            continue
        item = dict(link)
        item["sentence_id"] = sentence["sentence_id"]
        item["para_idx"] = sentence["para_idx"]
        enriched.append(item)
    return enriched


def process_file(input_path: Path, output_path: Path) -> dict[str, Any]:
    """Tách câu cho mọi bài trong file và ghi ra file mới.

    Args:
        input_path: Đường dẫn input (đã làm sạch).
        output_path: Đường dẫn output.

    Returns:
        Dict thống kê.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    total_docs = 0
    total_sentences = 0
    total_links = 0
    total_paragraphs = 0
    ending_ok = 0
    ending_ok_prose = 0
    sentences_prose = 0

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in read_jsonl(input_path):
            sentences = build_sentences(record)
            links = assign_links_to_sentences(sentences, record.get("links", []))
            paragraphs = build_paragraphs(
                record.get("clean_text", ""),
                record.get("headings", []),
                record.get("paragraph_kinds"),
            )
            total_docs += 1
            total_sentences += len(sentences)
            total_links += len(links)
            total_paragraphs += len(paragraphs)
            ending_ok += sum(
                1
                for sentence in sentences
                if sentence["text"].rstrip().endswith(SENTENCE_ENDINGS)
            )
            prose_sentences = [
                s for s in sentences if s.get("para_kind") == "prose"
            ]
            sentences_prose += len(prose_sentences)
            ending_ok_prose += sum(
                1
                for sentence in prose_sentences
                if sentence["text"].rstrip().endswith(SENTENCE_ENDINGS)
            )
            new_record = dict(record)
            new_record["paragraphs"] = paragraphs
            new_record["sentences"] = sentences
            new_record["links"] = links
            handle.write(json.dumps(new_record, ensure_ascii=False))
            handle.write("\n")

    stats = {
        "documents": total_docs,
        "paragraphs": total_paragraphs,
        "sentences": total_sentences,
        "links": total_links,
        "avg_sentences_per_doc": round(total_sentences / total_docs, 2)
        if total_docs
        else 0.0,
        "sentence_ending_ratio": round(ending_ok / total_sentences, 4)
        if total_sentences
        else 0.0,
        "prose_sentences": sentences_prose,
        "prose_sentence_ending_ratio": round(ending_ok_prose / sentences_prose, 4)
        if sentences_prose
        else 0.0,
    }
    logger.info("Thống kê tách câu: %s", stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    """Điểm vào của CLI.

    Args:
        argv: Danh sách tham số dòng lệnh.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Tách câu và đoạn")
    parser.add_argument("--config", default="configs/default.yaml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    interim_dir = REPO_ROOT / str(config["paths"]["interim_dir"])
    input_path = interim_dir / "documents_clean.jsonl"
    output_path = interim_dir / "documents.jsonl"

    if not input_path.exists():
        logger.error(
            "Không tìm thấy %s — chạy `python -m src.preprocess.clean_text` trước",
            input_path,
        )
        return 1

    stats = process_file(input_path, output_path)
    logger.info("Thống kê: %s", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

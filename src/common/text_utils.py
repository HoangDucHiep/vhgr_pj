"""Tiện ích đọc/ghi JSONL theo luồng và các phép xử lý văn bản wikitext.

Nguyên tắc: artifact JSONL là **hợp đồng** giữa các phase
(xem `.cursor/rules/data-contracts.mdc`). Hàm ở đây luôn:
- UTF-8, không BOM, 1 record mỗi dòng, không dòng rỗng;
- ghi theo luồng (không nạp toàn bộ file vào RAM);
- bỏ qua dòng hỏng khi đọc (log cảnh báo) thay vì crash cả pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.common.logger import get_logger

logger = get_logger(__name__)


def read_jsonl(path: str | Path, *, skip_invalid: bool = True) -> Iterator[dict[str, Any]]:
    """Đọc file JSONL theo luồng.

    Args:
        path: Đường dẫn file JSONL.
        skip_invalid: Bỏ qua dòng JSON hỏng thay vì ném exception.

    Yields:
        Từng dict record.
    """
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Không tìm thấy file JSONL: %s", file_path)
        return

    with file_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                if skip_invalid:
                    logger.warning("Bỏ qua dòng %d không phải JSON hợp lệ: %s", line_no, exc)
                    continue
                raise
            if isinstance(record, dict):
                yield record
            elif skip_invalid:
                logger.warning("Bỏ qua dòng %d: record không phải dict", line_no)
            else:
                raise ValueError(f"Dòng {line_no} không phải dict")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """Ghi danh sách record ra file JSONL theo luồng.

    Args:
        path: Đường dẫn file đích.
        records: Iterable các dict record.

    Returns:
        Số record đã ghi.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with file_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")
            count += 1
    return count


def count_lines(path: str | Path) -> int:
    """Đếm số dòng của file JSONL mà không nạp nội dung.

    Args:
        path: Đường dẫn file.

    Returns:
        Số dòng khác rỗng.
    """
    file_path = Path(path)
    if not file_path.exists():
        return 0
    total = 0
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                total += 1
    return total


def balance_wikitext(text: str) -> str:
    """Cân bằng dấu ngoặc ``{{`` và ``}}`` trong wikitext.

    Wikitext trong dump có thể bị thiếu/thừa dấu ngoặc do lỗi edit cũ; hàm này
    thêm hoặc bớt ngoặc ở cuối để `{{` và `}}` cân bằng, tránh việc template
    "nuốt" toàn bộ phần còn lại của bài.

    Args:
        text: Wikitext đầu vào.

    Returns:
        Wikitext đã cân bằng ngoặc.
    """
    if not text:
        return text

    open_count = text.count("{{")
    close_count = text.count("}}")
    if open_count > close_count:
        text = text + "}}" * (open_count - close_count)
    elif close_count > open_count:
        text = "}}" * (close_count - open_count) + text
    return text


def split_paragraphs(text: str) -> list[str]:
    """Tách văn bản thành các đoạn.

    Dùng regex ``\\n\\s*\\n`` làm dấu phân cách đoạn (fallback khi không dùng
    được `underthesea` — xem mục "Lùi" của Phase 0 trong `docs/09`).

    Args:
        text: Văn bản đã làm sạch.

    Returns:
        Danh sách đoạn đã bỏ khoảng trắng thừa ở hai đầu, đã loại đoạn rỗng.
    """
    if not text:
        return []

    paragraphs: list[str] = []
    for chunk in text.split("\n\n"):
        cleaned = chunk.strip()
        if cleaned:
            paragraphs.append(cleaned)
    return paragraphs


def split_lines_paragraphs(text: str) -> list[str]:
    """Tách đoạn theo dòng (mỗi dòng là một đoạn).

    Một số nguồn wikitext dùng xuống dòng để tách đoạn thay vì dòng trống.

    Args:
        text: Văn bản đầu vào.

    Returns:
        Danh sách đoạn khác rỗng.
    """
    if not text:
        return []
    paragraphs = [line.strip() for line in text.split("\n")]
    return [p for p in paragraphs if p]


def paragraph_spans(text: str) -> list[tuple[int, int]]:
    """Trả về các khoảng offset của từng đoạn (tách theo dòng trống).

    Hàm dùng chung cho `clean_text.py` (để gắn nhãn đoạn) và
    `split_sentences.py` (để tách câu) — nhờ vậy **chỉ số đoạn luôn khớp**
    giữa hai bên.

    Args:
        text: Văn bản.

    Returns:
        Danh sách ``(start, end)`` của các đoạn đã trim.
    """
    spans: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while index <= length:
        separator = text.find("\n\n", index)
        chunk_end = length if separator == -1 else separator
        chunk = text[index:chunk_end]
        stripped = chunk.strip()
        if stripped:
            start = index + (len(chunk) - len(chunk.lstrip()))
            spans.append((start, start + len(stripped)))
        if separator == -1:
            break
        index = separator + 2
    return spans

"""Phase 14 — Bước 1: chia văn bản thành chunk để truy xuất (RAG).

Đơn vị chunk = **1 đoạn văn** (paragraph) của bài Wikipedia đã clean.

Hai loại đoạn **không** sinh chunk:
- đoạn tiêu đề (`kind="heading"`) — chỉ chứa tên mục, không có thông tin nội dung;
  thông tin này đã được lưu vào trường `section` / `section_path` của các đoạn
  sau. Đo trên corpus thật: đoạn tiêu đề chiếm **20.354/101.628** chunk và
  làm nhiễu top-k (ví dụ "Thư mục", "Trong thi ca" lọt vào top-6 cho câu hỏi
  về trận Bạch Đằng).
- đoạn quá ngắn (`< min_chars`, mặc định 40) — stub không có thông tin, ví dụ
  "Xem chi tiết: Trận Bạch Đằng 1288".

Artifact sinh ra
----------------
`data/interim/chunks.jsonl` — 1 record/chunk, **11 trường**:

| # | Trường | Kiểu | Mô tả |
|---|---|---|---|
| 1 | `chunk_id` | str | `chunk_<doc_id>_<para_idx>` |
| 2 | `doc_id` | str | `doc_<page_id>` |
| 3 | `page_id` | int | page id Wikipedia |
| 4 | `title` | str | tên bài (có dấu) |
| 5 | `section` | str | tiêu đề mục hiện tại (chuỗi rỗng nếu đoạn dẫn) |
| 6 | `section_path` | str | đường dẫn mục lồng nhau, phân tách bằng `" > "` |
| 7 | `text` | str | nội dung đoạn (đã bỏ HTML entity) |
| 8 | `entity_ids` | list[str] | entity_id của các mention trong đoạn (coref) |
| 9 | `source_url` | str | URL Wikipedia |
| 10 | `para_idx` | int | chỉ số đoạn trong bài |
| 11 | `kind` | str | `prose` / `list_item` / `heading` |

Vì sao 1 đoạn = 1 chunk (không gộp 1000 ký tự)
----------------------------------------------
Đã đo trên corpus thật (`doc_136933` — Trận Bạch Đằng): bộ gộp theo ký tự
**mất ranh giới section** (đoạn về diễn biến trận rơi vào section
`Ý kiến khác về Ghềnh Cốc`), còn chunk theo đoạn giữ nguyên ranh giới:
`paragraphs[i].heading is True` ⇔ đoạn đó là tiêu đề mục.

Toàn corpus: **2.441 bài · 101.628 đoạn · 20.354 đoạn tiêu đề**; 100%
tiêu đề đoạn khớp một tiêu đề trong `doc['headings']` (đã verify).

Ánh xạ `section`
----------------
Duyệt `paragraphs` theo thứ tự; khi gặp đoạn có `heading=True` thì lấy
`text` làm tiêu đề hiện tại. Cấp (level) tra từ `doc['headings']` theo
`plain_title`; dùng stack để dựng `section_path` lồng nhau.

Entity của đoạn
---------------
Lấy từ `data/interim/coref_resolved.jsonl` (Phase 6): mỗi câu có `mentions[]`
với `canonical_id`; gom theo `(doc_id, para_idx)`.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterator

from src.common.config import resolve_path
from src.common.logger import get_logger

logger = get_logger("src.qa.chunking")

#: Số trường trong 1 record chunk (hợp đồng dữ liệu).
CHUNK_FIELDS: tuple[str, ...] = (
    "chunk_id",
    "doc_id",
    "page_id",
    "title",
    "section",
    "section_path",
    "text",
    "entity_ids",
    "source_url",
    "para_idx",
    "kind",
)


def clean_text(text: str) -> str:
    """Bỏ HTML entity và gọn khoảng trắng thừa.

    Args:
        text: Chuỗi thô.

    Returns:
        Chuỗi đã làm sạch.
    """
    if not text:
        return ""
    return " ".join(html.unescape(text).split())


def build_section_stack(
    paragraphs: list[dict[str, Any]],
    headings: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Dựng danh sách `(section, section_path)` cho từng đoạn.

    Args:
        paragraphs: Danh sách đoạn của bài (có `heading`).
        headings: Danh sách tiêu đề mục của bài.

    Returns:
        Danh sách cùng độ dài với `paragraphs`.
    """
    # title -> level (lấy level nhỏ nhất khi trùng tên)
    level_by_title: dict[str, int] = {}
    for heading in headings:
        title = clean_text(str(heading.get("plain_title") or heading.get("title") or ""))
        if not title:
            continue
        level = int(heading.get("level") or 2)
        if title not in level_by_title or level < level_by_title[title]:
            level_by_title[title] = level

    out: list[tuple[str, str]] = []
    stack: list[tuple[int, str]] = []
    for paragraph in paragraphs:
        text = clean_text(str(paragraph.get("text") or ""))
        if paragraph.get("heading"):
            level = level_by_title.get(text, 2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, text))
        section = stack[-1][1] if stack else ""
        path = " > ".join(title for _, title in stack)
        out.append((section, path))
    return out


def iter_coref_entities(path: Path) -> dict[tuple[str, int], list[str]]:
    """Gom entity_id của các mention theo `(doc_id, para_idx)`.

    Args:
        path: Đường dẫn `coref_resolved.jsonl`.

    Returns:
        Dict `(doc_id, para_idx)` → danh sách `entity_id` (đã loại trùng).
    """
    out: dict[tuple[str, int], list[str]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            doc_id = str(record.get("doc_id") or "")
            sentence_id = str(record.get("sentence_id") or "")
            # sentence_id = s<page_id>_<para_idx>_<sent_idx>
            parts = sentence_id.split("_")
            if len(parts) < 3:
                continue
            try:
                para_idx = int(parts[-2])
            except ValueError:
                continue
            key = (doc_id, para_idx)
            bucket = out.setdefault(key, [])
            for mention in record.get("mentions") or []:
                entity_id = str(mention.get("canonical_id") or "").strip()
                if not entity_id or entity_id.startswith("nil_"):
                    continue
                if entity_id not in bucket:
                    bucket.append(entity_id)
    return out


def iter_chunks(
    documents_path: Path,
    coref_path: Path,
    *,
    min_chars: int = 40,
) -> Iterator[dict[str, Any]]:
    """Sinh dần các chunk từ `documents_clean.jsonl` + `coref_resolved.jsonl`.

    Args:
        documents_path: Đường dẫn `documents_clean.jsonl`.
        coref_path: Đường dẫn `coref_resolved.jsonl`.
        min_chars: Đoạn ngắn hơn ngưỡng này bị lo (stub không có thông tin).

    Yields:
        Dict chunk theo hợp đồng 11 trường.
    """
    entities_by_para = iter_coref_entities(coref_path)
    logger.info("Nạp entity cho %d đoạn", len(entities_by_para))

    with documents_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            doc_id = str(doc.get("doc_id") or "")
            page_id = int(doc.get("page_id") or 0)
            title = clean_text(str(doc.get("title") or ""))
            url = str(doc.get("url") or "")
            paragraphs = doc.get("paragraphs") or []
            sections = build_section_stack(
                paragraphs, doc.get("headings") or []
            )
            for paragraph, (section, path) in zip(paragraphs, sections):
                text = clean_text(str(paragraph.get("text") or ""))
                if not text:
                    continue
                if paragraph.get("heading"):
                    # Đoạn tiêu đề không sinh chunk: nội dung này đã nằm trong
                    # `section` / `section_path` của các đoạn sau.
                    continue
                if len(text) < min_chars:
                    continue
                para_idx = int(paragraph.get("para_idx") or 0)
                kind = str(paragraph.get("kind") or "prose")
                yield {
                    "chunk_id": f"chunk_{doc_id}_{para_idx}",
                    "doc_id": doc_id,
                    "page_id": page_id,
                    "title": title,
                    "section": section,
                    "section_path": path,
                    "text": text,
                    "entity_ids": entities_by_para.get((doc_id, para_idx), []),
                    "source_url": url,
                    "para_idx": para_idx,
                    "kind": kind,
                }


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Chia văn bản thành chunk cho truy xuất RAG (Phase 14 — bước 1)."
    )
    parser.add_argument(
        "--documents", default="data/interim/documents_clean.jsonl",
        help="Input tài liệu đã clean.",
    )
    parser.add_argument(
        "--coref", default="data/interim/coref_resolved.jsonl",
        help="Input mention → canonical_id (Phase 6).",
    )
    parser.add_argument(
        "--out", default="data/interim/chunks.jsonl",
        help="Output chunks (1 record/dòng).",
    )
    parser.add_argument(
        "--stats-out", default="data/interim/chunks_stats.json",
        help="Output thống kê.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số bài (0 = tất cả).")
    parser.add_argument(
        "--min-chars", type=int, default=40,
        help="Bỏ đoạn ngắn hơn ngưỡng này (stub không có thông tin).",
    )
    args = parser.parse_args()

    documents_path = resolve_path(args.documents)
    coref_path = resolve_path(args.coref)
    out_path = resolve_path(args.out)

    started = time.time()
    count = 0
    docs = 0
    with_entity = 0
    sectioned = 0
    kinds: dict[str, int] = {}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for chunk in iter_chunks(
            documents_path, coref_path, min_chars=args.min_chars
        ):
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            count += 1
            if chunk["entity_ids"]:
                with_entity += 1
            if chunk["section"]:
                sectioned += 1
            kinds[chunk["kind"]] = kinds.get(chunk["kind"], 0) + 1
            if count % 20000 == 0:
                logger.info("Đã ghi %d chunk", count)

    stats = {
        "_meta": {
            "phase": 14,
            "mo_ta": "Thống kê chunk Phase 14",
            "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "elapsed_s": round(time.time() - started, 1),
            "fields": list(CHUNK_FIELDS),
        },
        "chunk_count": count,
        "chunk_with_entity": with_entity,
        "chunk_with_entity_ratio": round(with_entity / count, 4) if count else 0.0,
        "chunk_with_section": sectioned,
        "chunk_with_section_ratio": round(sectioned / count, 4) if count else 0.0,
        "kind_distribution": kinds,
    }
    stats_path = resolve_path(args.stats_out)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info(
        "Ghi %d chunk vào %s (%.1fs) — có entity: %.1f%%, có section: %.1f%%",
        count, out_path, time.time() - started,
        100 * stats["chunk_with_entity_ratio"],
        100 * stats["chunk_with_section_ratio"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

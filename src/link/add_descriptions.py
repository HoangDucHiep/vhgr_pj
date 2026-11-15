"""Bổ sung `description` cho entity từ đoạn dẫn (lead) của bài Wikipedia.

Vì sao cần: node `Person` không có `description` ⇒ câu hỏi kiểu "Nguyễn Huệ là
ai?" không có gì để trả lời ⇒ hệ thống báo "Không có trong dữ liệu." dù bài
Wikipedia có đoạn dẫn mô tả rõ.

Nguồn:
    - `data/interim/documents.jsonl` (Phase 2) — đoạn dẫn của 2.441 bài.
    - `data/knowledge_base/entities.jsonl` (Phase 9) — entity + `name_normalized`.

Quy tắc:
    - Chỉ lấy **đoạn dẫn** (paragraph đầu tiên, kind `prose`).
    - **Loại bỏ toàn bộ chữ Hán** (quy tắc `no-chinese.mdc`): "Quang Trung (Chữ
      Hán: 光中, 1753 – …)" → "Quang Trung (1753 – …)".
    - Cắt tối đa 400 ký tự, bỏ qua câu bị dính ngoặc kép lồng.
    - Idempotent: chạy lại cho kết quả giống nhau.

Output:
    `data/knowledge_base/entity_descriptions.jsonl` — 1 record/dòng:
    `{"entity_id": ..., "description": ..., "doc_id": ..., "source_url": ...}`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

from src.common.config import resolve_path
from src.common.logger import get_logger
from src.common.normalize import normalize_name

logger = get_logger("src.link.add_descriptions")

#: Ký tự Hán (CJK) — loại khỏi mọi description sinh ra.
HAN_PATTERN = re.compile(
    r"[　-〿㐀-䶿一-鿿豈-﫿＀-￯]+"
)

#: Dấu ngoặc kép bao nội dung Hán, vd "Chữ Hán: 光中".
HAN_PAREN = re.compile(r"\([^()]*\)")

#: Độ dài tối đa của description.
MAX_LENGTH = 400


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Đọc JSONL.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng dict.
    """
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def clean_description(text: str) -> str:
    """Loại chữ Hán và rút gọn đoạn dẫn.

    Args:
        text: Đoạn dẫn gốc.

    Returns:
        Mô tả đã làm sạch (có thể rỗng).
    """
    # Bỏ ngoặc chứa Hán trước: "Quang Trung (Chữ Hán: 光中, 1753)" → "Quang Trung".
    without_han_paren = HAN_PAREN.sub(
        lambda m: "" if HAN_PATTERN.search(m.group(0)) else m.group(0), text
    )
    cleaned = HAN_PATTERN.sub("", without_han_paren)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Bỏ dấu phẩy/dấu chấm thừa do chỗ Hán vốn đứng.
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"[,;]\s*([,.;:])", r"\1", cleaned)
    if len(cleaned) > MAX_LENGTH:
        cleaned = cleaned[:MAX_LENGTH].rsplit(" ", 1)[0] + "…"
    return cleaned


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Bổ sung description cho entity từ đoạn dẫn Wikipedia."
    )
    parser.add_argument(
        "--documents", default="data/interim/documents.jsonl",
    )
    parser.add_argument(
        "--entities", default="data/knowledge_base/entities.jsonl",
    )
    parser.add_argument(
        "--out", default="data/knowledge_base/entity_descriptions.jsonl",
    )
    args = parser.parse_args()

    # Index: name_normalized → entity_id (chỉ giữ entity type person).
    entity_by_name: dict[str, str] = {}
    for entity in iter_jsonl(resolve_path(args.entities)):
        if str(entity.get("type") or "") != "person":
            continue
        key = str(entity.get("name_normalized") or "")
        if key and key not in entity_by_name:
            entity_by_name[key] = str(entity.get("entity_id") or "")

    logger.info("Index %d entity person", len(entity_by_name))

    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    n_skip = 0
    seen: set[str] = set()

    with out_path.open("w", encoding="utf-8") as handle:
        for doc in iter_jsonl(resolve_path(args.documents)):
            title = str(doc.get("title") or "")
            key = normalize_name(title)
            entity_id = entity_by_name.get(key)
            if not entity_id or entity_id in seen:
                n_skip += 1
                continue
            paragraphs = doc.get("paragraphs") or []
            lead = ""
            for para in paragraphs:
                text = str(para.get("text") or "").strip()
                if len(text) >= 40:
                    lead = text
                    break
            if not lead:
                n_skip += 1
                continue
            description = clean_description(lead)
            if len(description) < 20:
                n_skip += 1
                continue
            seen.add(entity_id)
            handle.write(json.dumps({
                "entity_id": entity_id,
                "description": description,
                "doc_id": doc.get("doc_id"),
                "source_url": doc.get("url"),
                "doc_title": title,
            }, ensure_ascii=False) + "\n")
            n_written += 1

    logger.info("Ghi %d description (bỏ qua %d) → %s", n_written, n_skip, out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

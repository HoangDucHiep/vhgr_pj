"""Thống kê văn bản đã làm sạch (Phase 2 — Gate check).

In ra:
- số câu/bài, phân bố độ dài câu;
- tỉ lệ câu kết thúc bằng dấu câu;
- tỉ lệ câu chứa hyperlink;
- tỉ lệ giữ được hyperlink so với wikitext gốc.

Cách chạy:
    python scripts/stats_text.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_config  # noqa: E402
from src.common.text_utils import read_jsonl  # noqa: E402

#: Ký tự wiki còn sót trong `clean_text` — phải bằng 0.
WIKI_CHARS_RE = re.compile(r"\{\{|\}\}|<ref|\[\[File:|\[\[Thể loại:|\[\[Tập tin:")

#: Regex link nội bộ trong wikitext gốc (để so sánh tỉ lệ giữ link).
RAW_LINK_RE = re.compile(r"\[\[([^\[\]\|]{1,300})(?:\|[^\[\]]*)?\]\]")

#: Link tới tập tin / thể loại — không tính vào mẫu số.
EXCLUDED_LINK_RE = re.compile(
    r"^\s*(?:File|Tập tin|Image|Hình|Thể loại)\s*:", re.IGNORECASE
)

ENDINGS = (".", "!", "?", "…")


def _percentile(values: list[int], ratio: float) -> int:
    """Tính phân vị của một danh sách số.

    Args:
        values: Danh sách giá trị.
        ratio: Tỉ lệ trong [0, 1].

    Returns:
        Giá trị tại phân vị, 0 nếu danh sách rỗng.
    """
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(ratio * len(ordered)))
    return ordered[index]


def main() -> int:
    """Chạy thống kê.

    Returns:
        Mã thoát (0 = thành công).
    """
    config = load_config(REPO_ROOT / "configs/default.yaml")
    interim_dir = REPO_ROOT / str(config["paths"]["interim_dir"])
    documents_path = interim_dir / "documents.jsonl"

    if not documents_path.exists():
        print(f"Không tìm thấy {documents_path}")
        return 1

    total_docs = 0
    total_paragraphs = 0
    total_sentences = 0
    total_links = 0
    sentences_with_link = 0
    ending_ok = 0
    length_buckets: Counter[str] = Counter()
    lengths: list[int] = []
    residual_wiki_docs: list[str] = []
    offset_errors = 0
    raw_links_total = 0
    kept_links_total = 0

    for record in read_jsonl(documents_path):
        total_docs += 1
        clean_text = record.get("clean_text", "")
        paragraphs = record.get("paragraphs", [])
        sentences = record.get("sentences", [])
        links = record.get("links", [])
        wikitext = record.get("wikitext", "")

        total_paragraphs += len(paragraphs)
        total_sentences += len(sentences)
        total_links += len(links)
        kept_links_total += len(links)

        if WIKI_CHARS_RE.search(clean_text):
            residual_wiki_docs.append(record.get("title", "?"))

        for sentence in sentences:
            text = sentence.get("text", "")
            start = sentence.get("char_start", -1)
            end = sentence.get("char_end", -1)
            if not (0 <= start < end <= len(clean_text)):
                offset_errors += 1
            elif clean_text[start:end] != text:
                offset_errors += 1

            length = len(text.split())
            lengths.append(length)
            if length == 0:
                length_buckets["0"] += 1
            elif length <= 5:
                length_buckets["1-5"] += 1
            elif length <= 15:
                length_buckets["6-15"] += 1
            elif length <= 30:
                length_buckets["16-30"] += 1
            elif length <= 60:
                length_buckets["31-60"] += 1
            else:
                length_buckets[">60"] += 1

            if text.rstrip().endswith(ENDINGS):
                ending_ok += 1

        # Tỉ lệ câu có hyperlink: câu có ít nhất 1 link nằm trong khoảng offset.
        for sentence in sentences:
            for link in links:
                if link.get("sentence_id") == sentence.get("sentence_id"):
                    sentences_with_link += 1
                    break

        raw_links = [
            match.group(1)
            for match in RAW_LINK_RE.finditer(wikitext)
            if not EXCLUDED_LINK_RE.match(match.group(1))
        ]
        raw_links_total += len(raw_links)

    print("=== Thống kê văn bản (Phase 2) ===")
    print(f"Số bài            : {total_docs}")
    print(f"Số đoạn           : {total_paragraphs}")
    print(f"Số câu            : {total_sentences}")
    print(f"Trung bình câu/bài: {total_sentences / total_docs:.1f}" if total_docs else "")
    print(f"Hyperlink giữ lại : {total_links} (mẫu gốc {raw_links_total})")
    if raw_links_total:
        print(f"Tỉ lệ giữ link    : {kept_links_total / raw_links_total:.1%}")
    print(f"Câu kết thúc bằng dấu câu: {ending_ok / total_sentences:.1%}"
          if total_sentences else "")
    print(f"Câu có hyperlink  : {sentences_with_link / total_sentences:.1%}"
          if total_sentences else "")
    print(f"Lỗi offset       : {offset_errors}")
    print(f"Bài còn ký tự wiki: {len(residual_wiki_docs)}")
    if residual_wiki_docs:
        print(f"  ví dụ: {residual_wiki_docs[:5]}")

    print("\nPhân bố độ dài câu (số từ):")
    for bucket in ("0", "1-5", "6-15", "16-30", "31-60", ">60"):
        count = length_buckets.get(bucket, 0)
        ratio = count / total_sentences if total_sentences else 0.0
        print(f"  {bucket:>6} từ : {count:>8}  ({ratio:.1%})")

    if lengths:
        print(
            "\nĐộ dài câu (từ): "
            f"p10={_percentile(lengths, 0.10)} "
            f"p50={_percentile(lengths, 0.50)} "
            f"p90={_percentile(lengths, 0.90)} "
            f"max={max(lengths)}"
        )

    stats_path = interim_dir / "text_stats.json"
    stats_path.write_text(
        json.dumps(
            {
                "documents": total_docs,
                "paragraphs": total_paragraphs,
                "sentences": total_sentences,
                "links": total_links,
                "raw_links": raw_links_total,
                "link_retention_ratio": round(
                    kept_links_total / raw_links_total, 4
                )
                if raw_links_total
                else 0.0,
                "sentence_ending_ratio": round(ending_ok / total_sentences, 4)
                if total_sentences
                else 0.0,
                "sentences_with_link_ratio": round(
                    sentences_with_link / total_sentences, 4
                )
                if total_sentences
                else 0.0,
                "offset_errors": offset_errors,
                "residual_wiki_docs": len(residual_wiki_docs),
                "length_buckets": dict(length_buckets),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nĐã ghi {stats_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

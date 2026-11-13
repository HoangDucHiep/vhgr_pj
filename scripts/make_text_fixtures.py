"""Sinh fixture hồi quy cho Phase 2.

Tạo:
- `tests/fixtures/sample_docs_10.jsonl` — 10 bài thật lấy từ corpus
  (`data/interim/documents.jsonl`), chọn để phủ các trường hợp khó:
  nhân vật phong kiến, bài có bảng lồng nhau, template ngoặc hở,
  link không cân bằng, bài trận đánh, bài rất dài.
- `tests/fixtures/expected_clean.jsonl` — snapshot kết quả `clean_document`.

Cách chạy:
    python scripts/make_text_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.preprocess.clean_text import clean_document  # noqa: E402
from src.preprocess.split_sentences import build_paragraphs, build_sentences  # noqa: E402

#: 10 bài mẫu — chọn để phủ các trường hợp lỗi đã gặp.
SAMPLE_TITLES = [
    "Lý Thường Kiệt",  # nhân vật phong kiến, đoạn dẫn có năm sinh/mất
    "Trần Hưng Đạo",  # nhân vật phong kiến
    "Đinh Tiên Hoàng",  # nhân vật phong kiến, infobox dạng cũ
    "Hà Nội",  # bài lớn, nhiều bảng lồng nhau + danh sách
    "Elizabeth II",  # template ngoặc hở (`}}` thừa)
    "Đặng Tất",  # link `[[` không đóng
    "Chùa Bối Khê",  # link `]]` thừa
    "Trận Bạch Đằng (938)",  # bài trận đánh (infobox kiểu event)
    "Quang Trung",  # nhân vật, nhiều danh sách
    "Việt Nam Cộng hòa",  # bài rất dài, nhiều danh sách và bảng
]


def main() -> int:
    """Sinh fixture.

    Returns:
        Mã thoát (0 = thành công).
    """
    from src.common.config import REPO_ROOT as CONFIG_ROOT
    from src.common.config import load_config

    config = load_config(CONFIG_ROOT / "configs/default.yaml")
    interim_dir = CONFIG_ROOT / str(config["paths"]["interim_dir"])
    documents_path = interim_dir / "documents.jsonl"
    fixtures_dir = CONFIG_ROOT / "tests/fixtures"

    if not documents_path.exists():
        print(f"Không tìm thấy {documents_path}")
        return 1

    wanted = set(SAMPLE_TITLES)
    picked: dict[str, dict] = {}
    with documents_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("title") in wanted:
                picked[record["title"]] = record
            if len(picked) == len(wanted):
                break

    missing = wanted - set(picked)
    if missing:
        print(f"Thiếu bài trong corpus: {sorted(missing)}")

    fixtures_dir.mkdir(parents=True, exist_ok=True)
    sample_path = fixtures_dir / "sample_docs_10.jsonl"
    expected_path = fixtures_dir / "expected_clean.jsonl"

    with sample_path.open("w", encoding="utf-8", newline="\n") as sample_handle, \
            expected_path.open("w", encoding="utf-8", newline="\n") as expected_handle:
        for title in SAMPLE_TITLES:
            record = picked.get(title)
            if record is None:
                continue
            # File mẫu chỉ giữ những gì cần cho test (bỏ `wikitext` dài).
            sample_record = {
                "doc_id": record["doc_id"],
                "page_id": record["page_id"],
                "title": record["title"],
                "wikitext": record["wikitext"],
            }
            sample_handle.write(json.dumps(sample_record, ensure_ascii=False))
            sample_handle.write("\n")

            result = clean_document(record["wikitext"])
            doc = {
                "doc_id": record["doc_id"],
                "page_id": record["page_id"],
                "clean_text": result.clean_text,
                "headings": result.headings,
                "paragraph_kinds": result.paragraph_kinds,
            }
            expected_record = {
                "doc_id": record["doc_id"],
                "page_id": record["page_id"],
                "title": record["title"],
                "clean_text": result.clean_text,
                "headings": result.headings,
                "paragraph_kinds": result.paragraph_kinds,
                "links": result.links,
                "paragraphs": build_paragraphs(
                    result.clean_text, result.headings, result.paragraph_kinds
                ),
                "sentences": build_sentences(doc),
            }
            expected_handle.write(json.dumps(expected_record, ensure_ascii=False))
            expected_handle.write("\n")

    print(f"Đã ghi {sample_path} ({len(picked)} bài)")
    print(f"Đã ghi {expected_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

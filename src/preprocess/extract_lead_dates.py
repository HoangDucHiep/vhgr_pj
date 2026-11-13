"""Trích ngày sinh / ngày mất từ **đoạn dẫn** (fallback cho Phase 3 — A4).

## Vì sao cần module này

Khoảng **30%** bài nhân vật không có trường ngày trong infobox (vì nguồn Wikipedia
viết infobox thiếu, hoặc dùng định dạng lạ). Tuy nhiên **đoạn dẫn** thường có
dạng chuẩn:

```
Lý Thái Tổ (chữ Hán: <bỏ dấu>, 8 tháng 3 năm 974 – 31 tháng 3 năm 1028), tên húy là
Lý Công Uẩn, là hoàng đế sáng lập ra nhà Lý trong lịch sử Việt Nam.
```

> Ghi chú: phần "chữ Hán" trong văn bản thật chứa ký tự Hán — ở đây đã **lược bỏ**
> theo quy tắc ngôn ngữ của dự án (`AGENTS.md` §5.9). Regex bỏ qua nội dung này
> nên không ảnh hưởng kết quả trích xuất.

Vì vậy: dùng đoạn dẫn làm **fallback** cho các bài mà infobox không có ngày.

## Nguyên tắc

1. **Chỉ dùng khi infobox không có** — không trùng lặp với `infobox_triples.jsonl`.
2. `method="rule"`, `confidence=0.85` (thấp hơn infobox) — vì regex trên văn bản
   tự do có thể sai.
3. **Bằng chứng là câu thật** — `evidence_sentence` = câu dẫn chứa năm (lấy từ
   `sentences[0..n]` của `documents.jsonl`), không phải chuỗi regex tự dựng.
4. **Không bịa** — nếu không chắc chắn (ví dụ chỉ có 1 năm trong ngoặc) thì bỏ.

## Cách chạy

```bash
python -m src.preprocess.extract_lead_dates --config configs/default.yaml
```
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.common.config import load_config, resolve_path
from src.common.ids import make_entity_id, make_year_id
from src.common.logger import get_logger
from src.common.normalize import normalize_name, parse_vi_date
from src.common.schemas import RELATION_SUBJECT_TYPES, RELATION_TYPES
from src.common.text_utils import read_jsonl, write_jsonl

logger = get_logger(__name__)

#: Confidence cho triple trích từ đoạn dẫn.
CONFIDENCE_LEAD = 0.85

#: Số câu đầu được xét làm "đoạn dẫn".
LEAD_SENTENCES = 3

#: Regex ngoặc chứa khoảng năm dạng "… 974 – 1028 …" hoặc "… 974-1028 …".
_RANGE_RE = re.compile(
    r"\(([^()]*?(?:\d{3,4})\s*(?:[-–—~]|thông|đến)\s*(?:\d{3,4})[^()]*?)\)"
)

#: Regex ngoặc chứa đúng một năm: "(chữ Hán: …, 974)".
_SINGLE_YEAR_RE = re.compile(r"\(([^()]*?)\b(\d{3,4})\b([^()]*?)\)")

#: Dấu hiệu trong ngoặc cho thấy năm là **năm sinh**.
_BIRTH_HINT_RE = re.compile(r"\b(sinh|sinh ra|ra doi|truong khai|born|birth)\b")

#: Dấu hiệu trong ngoặc cho thấy năm là **năm mất**.
_DEATH_HINT_RE = re.compile(r"\b(mat|qua doi|qua doi o|toan ven|died|death)\b")

#: Cửa sổ năm hợp lệ cho lịch sử Việt Nam (tránh bắt nhầm số khác).
MIN_YEAR = 900
MAX_YEAR = 2026

#: Khoảng cách năm lớn nhất giữa năm sinh và năm mất (người thường < 120 tuổi).
MAX_LIFESPAN = 120

#: Chỉ trích ngày cho bài **nhân vật** — bài khác có nhiều số trong ngoặc
#: không liên quan (ví dụ "Liên bang Đông Dương (chữ Nôm: …, sau 1947 là …)").
ALLOWED_SUBJECT_TYPES = frozenset({"person"})


def _find_date_pairs(text: str) -> list[tuple[int, int]]:
    """Tìm các cặp năm (đầu, cuối) trong một đoạn văn.

    Chỉ xét ngoặc **đầu tiên** của câu — đó là nơi Wikipedia đặt ngoặc
    "chữ Hán: …, 974 – 1028". Các ngoặc sau thường là giải thích khác
    ("(nghệm đồng)", "(trường học)").

    Args:
        text: Văn bản đoạn dẫn.

    Returns:
        Danh sách cặp ``(năm_đầu, năm_cuối)``.
    """
    pairs: list[tuple[int, int]] = []

    # Chỉ ngoặc đầu tiên.
    first_paren = text.find("(")
    if first_paren == -1:
        return pairs
    close = text.find(")", first_paren)
    if close == -1:
        return pairs
    inner = text[first_paren + 1 : close]

    # Dạng khoảng: "… 8 tháng 3 năm 974 – 31 tháng 3 năm 1028 …"
    years = [
        int(y)
        for y in re.findall(r"\b(\d{3,4})\b", inner)
        if MIN_YEAR <= int(y) <= MAX_YEAR
    ]
    if len(years) >= 2:
        return [(years[0], years[-1])]
    if len(years) == 1:
        # Dạng đơn: chỉ dùng khi ngoặc có dấu hiệu sinh/mất rõ ràng.
        hint = inner.lower()
        if _BIRTH_HINT_RE.search(hint) or _DEATH_HINT_RE.search(hint):
            return [(years[0], years[0])]
    return pairs


def _lead_sentences(doc: dict[str, Any], limit: int = LEAD_SENTENCES) -> list[dict[str, Any]]:
    """Lấy các câu đầu của bài.

    Args:
        doc: Record document.
        limit: Số câu tối đa.

    Returns:
        Danh sách sentence record.
    """
    sentences = doc.get("sentences") or []
    return list(sentences[:limit])


def extract_lead_dates(doc: dict[str, Any], *, model_name: str = "") -> list[dict[str, Any]]:
    """Trích cặp (sinh_nam, mat_nam) từ đoạn dẫn của một bài.

    Args:
        doc: Record document (Phase 2).
        model_name: Tên mô hình đã dùng (ghi vào mọi triple).

    Returns:
        Danh sách triple (chưa gán `doc_id`/`source_url`).
    """
    sentences = _lead_sentences(doc)
    if not sentences:
        return []

    # Dùng câu đầu tiên — đó là nơi Wikipedia đặt ngoặc năm sinh/mất.
    first = sentences[0]
    text = first.get("text", "")
    if not text:
        return []

    pairs = _find_date_pairs(text)
    if not pairs:
        return []

    title = doc.get("title", "")
    subject_type = doc.get("infobox_type")
    # `infobox_type` có thể là `None` (bài không có infobox) — khi đó dùng
    # `keep_reason`/`wikidata_signal` để đoán, hoặc bỏ qua nếu không rõ.
    if subject_type is None:
        signal = doc.get("wikidata_signal")
        subject_type = "person" if signal == "person" else None
    if subject_type not in ALLOWED_SUBJECT_TYPES:
        return []
    subject_id = make_entity_id(subject_type, title)

    triples: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()

    for start_year, end_year in pairs:
        # Kiểm tra khoảng cách sinh–mất hợp lý (người thường < 120 tuổi).
        if end_year < start_year or (end_year - start_year) > MAX_LIFESPAN:
            continue
        # Năm sinh phải trước năm mất, cả hai đều trong cửa sổ lịch sử.
        for relation, year in (("sinh_nam", start_year), ("mat_nam", end_year)):
            if relation == "mat_nam" and year == start_year:
                continue
            key = (relation, year)
            if key in seen:
                continue
            seen.add(key)
            if relation not in RELATION_TYPES:
                continue
            if subject_type not in RELATION_SUBJECT_TYPES.get(relation, frozenset()):
                continue
            triples.append(
                {
                    "doc_id": doc.get("doc_id", ""),
                    "sentence_id": first.get("sentence_id", ""),
                    "subject": subject_id,
                    "subject_type": subject_type,
                    "relation": relation,
                    "object": make_year_id(year),
                    "object_type": "year",
                    "evidence_sentence": text,
                    "source_url": doc.get("url", ""),
                    "doc_title": title,
                    "confidence": CONFIDENCE_LEAD,
                    "method": "rule",
                    "start_year": year,
                    "end_year": year,
                    "alt_evidence": [],
                    "dump_version": doc.get("dump_version", ""),
                    "model_name": model_name,
                }
            )

    return triples


def run(
    *,
    documents_path: str | Path,
    triples_path: str | Path,
    skip_docs_with_dates: bool = True,
    model_name: str = "",
) -> dict[str, Any]:
    """Chạy pipeline trích ngày từ đoạn dẫn.

    Args:
        documents_path: Đường dẫn `documents.jsonl`.
        triples_path: Đường dẫn output.
        skip_docs_with_dates: Bỏ qua bài đã có ngày trong infobox.
        model_name: Tên mô hình đã dùng (ghi vào mọi triple).

    Returns:
        Dict thống kê.
    """
    # Tập doc đã có ngày từ infobox (để không trùng lặp).
    docs_with_dates: set[str] = set()
    if skip_docs_with_dates:
        for triple in read_jsonl(triples_path.with_name("infobox_triples.jsonl")):
            if triple.get("relation") in {"sinh_nam", "mat_nam"}:
                docs_with_dates.add(triple.get("doc_id", ""))

    stats = {
        "documents_total": 0,
        "documents_skipped_has_date": 0,
        "documents_with_lead_dates": 0,
        "triples_total": 0,
        "by_relation": {},
    }

    buffer: list[dict[str, Any]] = []
    for doc in read_jsonl(documents_path):
        stats["documents_total"] += 1
        doc_id = doc.get("doc_id", "")
        if doc_id in docs_with_dates:
            stats["documents_skipped_has_date"] += 1
            continue
        triples = extract_lead_dates(doc, model_name=model_name)
        if not triples:
            continue
        stats["documents_with_lead_dates"] += 1
        buffer.extend(triples)
        for triple in triples:
            relation = triple["relation"]
            stats["by_relation"][relation] = stats["by_relation"].get(relation, 0) + 1

    stats["triples_total"] = len(buffer)
    write_jsonl(triples_path, buffer)
    return stats


def main(argv: Iterable[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Trích ngày từ đoạn dẫn (Phase 3)")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--input", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = load_config(args.config)
    interim_dir = resolve_path(config.get("paths", {}).get("interim_dir", "data/interim"))
    documents_path = resolve_path(args.input) if args.input else interim_dir / "documents.jsonl"
    triples_path = resolve_path(args.out) if args.out else interim_dir / "lead_triples.jsonl"

    stats = run(
        documents_path=documents_path,
        triples_path=triples_path,
        model_name=str(config.get("ner", {}).get("model_name", "")),
    )
    logger.info(
        "Đã trích %d triple từ đoạn dẫn của %d bài",
        stats["triples_total"],
        stats["documents_with_lead_dates"],
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""Dựng ánh xạ `page_id → QID` cho bài namespace 0.

## Vì sao không đọc từ dump XML

Đã kiểm chứng 13/11/2026 trên `viwiki-20261101`:

| File | Chứa `<page_props><wikibase_item>` ? |
|---|---|
| `pages-articles.xml.bz2` | ❌ (0 / 18.113 trang đầu, 0 / 120 MB đã quét) |
| `pages-meta-current.xml.bz2` | ❌ (0 / 18.113 trang đầu) |

Bản export XML của MediaWiki **không** chứa `page_props`. Nguồn đúng là file SQL
`viwiki-20261101-page_props.sql.gz` (sha1 `bd6b74f04cc616f5811caf263ad972aec0285f83`),
trong đó bảng `page_props` lưu `pp_page` → `pp_propname='wikibase_item'` →
`pp_value` (QID).

Bảng `page` trong cùng bộ dump cho `page_id` ↔ `page_title`, nên ta dựng:

- `page_id → QID` (từ `page_props`)
- `title → QID` (từ `page` + `page_props`)

Cách chạy:
    python -m src.preprocess.wikidata_map --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

from src.common.config import REPO_ROOT, load_config
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Regex bắt tuple của bảng `page_props`:
#: ``(page_id,'propname','value',NULL)`` — cột cuối có thể là ``NULL``.
_PAGE_PROPS_ROW_RE = re.compile(
    r"\(\s*(\d+)\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*(?:NULL|'[^']*')\s*\)"
)

#: Regex bắt tuple của bảng `page`:
#: ``(page_id,page_namespace,'page_title',...)`` — tiêu đề dùng dấu gạch dưới.
_PAGE_ROW_RE = re.compile(r"\(\s*(\d+)\s*,\s*(\d+)\s*,\s*'((?:[^'\\]|\\.|'')*)'")


def _unescape_sql(value: str) -> str:
    """Giải mã chuỗi SQL escape (``''`` → `'`, ``\\'`` → `'`).

    Args:
        value: Chuỗi thô từ file SQL.

    Returns:
        Chuỗi đã giải mã.
    """
    return value.replace("''", "'").replace("\\'", "'").replace("\\\\", "\\")


def parse_page_props(sql_path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Parse `page_props.sql.gz` để lấy `page_id → QID` và `title → QID`.

    Args:
        sql_path: Đường dẫn `page_props.sql.gz`.

    Returns:
        Tuple ``(page_id_to_qid, title_to_qid)``.
    """
    page_id_to_qid: dict[str, str] = {}
    title_to_qid: dict[str, str] = {}

    logger.info("Đọc %s ...", sql_path.name)
    with gzip.open(sql_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if "wikibase_item" not in line:
                continue
            for match in _PAGE_PROPS_ROW_RE.finditer(line):
                page_id, propname, value = match.groups()
                if propname != "wikibase_item":
                    continue
                page_id_to_qid[page_id] = value

    logger.info("page_props: %d trang có QID", len(page_id_to_qid))
    return page_id_to_qid, title_to_qid


def parse_page_table(sql_path: Path) -> dict[str, str]:
    """Parse bảng `page` để lấy `page_id → title`.

    Args:
        sql_path: Đường dẫn `page.sql.gz`.

    Returns:
        Dict ``{"<page_id>": "<title>"}``.
    """
    mapping: dict[str, str] = {}
    if not sql_path.exists():
        logger.warning("Không có %s — bỏ qua ánh xạ page_id → title", sql_path.name)
        return mapping

    logger.info("Đọc %s ...", sql_path.name)
    with gzip.open(sql_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("("):
                continue
            for match in _PAGE_ROW_RE.finditer(line):
                page_id, namespace, title = match.groups()
                if namespace != "0":
                    continue
                mapping[page_id] = _unescape_sql(title).replace("_", " ")
    logger.info("page: %d trang namespace 0", len(mapping))
    return mapping


def build_qid_map(
    page_props_path: Path, page_sql_path: Path | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Dựng đồng thời `page_id → QID` và `title → QID`.

    Args:
        page_props_path: Đường dẫn `page_props.sql.gz`.
        page_sql_path: Đường dẫn `page.sql.gz` (tuỳ chọn).

    Returns:
        Tuple ``(page_id_to_qid, title_to_qid)``.
    """
    page_id_to_qid, _ = parse_page_props(page_props_path)
    if page_sql_path is None:
        return page_id_to_qid, {}
    page_id_to_title = parse_page_table(page_sql_path)
    title_to_qid: dict[str, str] = {}
    for page_id, qid in page_id_to_qid.items():
        title = page_id_to_title.get(page_id)
        if title:
            title_to_qid[title] = qid
    return page_id_to_qid, title_to_qid


def main(argv: list[str] | None = None) -> int:
    """Điểm vào của CLI.

    Args:
        argv: Danh sách tham số dòng lệnh.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Dựng ánh xạ page_id → QID từ page_props.sql.gz"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    dump_version = str(config["dump"]["dump_version"])
    raw_dir = REPO_ROOT / str(config["paths"]["raw_dir"])
    interim_dir = REPO_ROOT / str(config["paths"]["interim_dir"])

    page_props_path = raw_dir / f"viwiki-{dump_version}-page_props.sql.gz"
    page_sql_path = raw_dir / f"viwiki-{dump_version}-page.sql.gz"

    if not page_props_path.exists():
        logger.error("Không tìm thấy %s", page_props_path)
        logger.error(
            "Tải bằng: curl -L -o %s "
            "https://dumps.wikimedia.org/viwiki/%s/viwiki-%s-page_props.sql.gz",
            page_props_path.name,
            dump_version,
            dump_version,
        )
        return 1

    page_id_to_qid, title_to_qid = build_qid_map(page_props_path, page_sql_path)

    interim_dir.mkdir(parents=True, exist_ok=True)
    page_id_path = interim_dir / "pageid_to_qid.json"
    page_id_path.write_text(
        json.dumps(page_id_to_qid, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Đã ghi %d ánh xạ page_id → QID vào %s", len(page_id_to_qid), page_id_path)

    if title_to_qid:
        title_path = interim_dir / "title_to_qid.json"
        title_path.write_text(
            json.dumps(title_to_qid, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Đã ghi %d ánh xạ title → QID vào %s", len(title_to_qid), title_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

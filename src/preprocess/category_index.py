"""Chỉ mục category cho bộ lọc Phase 1 (tín hiệu T1).

## Vì sao không quét wikitext

Bảng `categorylinks.sql.gz` của dump Wikimedia **đã có sẵn** quan hệ
"bài viết → category" và "category → subcategory" cho toàn bộ wiki. Dùng nó
nhanh hơn nhiều so với quét 1.1 GB `pages-articles.xml.bz2` và cho phép mở
rộng đệ quy subcategory mà không phải đọc lại dump.

## Quan hệ giữa các bảng

```
page(page_id, page_namespace, page_title, ...)
    │  page_namespace = 0 → bài viết
    ▼
categorylinks(cl_from, cl_sortkey, cl_timestamp, cl_sortkey_prefix,
              cl_type, cl_collation_id, cl_target_id)
    │  cl_from      = page_id của trang nguồn (bài viết hoặc trang category)
    │  cl_target_id = lt_id trong bảng `linktarget`  ← KHÔNG phải cat_id/page_id
    │  cl_type      ∈ {page, subcat, file}
    ▼
linktarget(lt_id, lt_namespace, lt_title)
    │  lt_namespace = 14 → trang category
    ▼
category(cat_id, cat_title, cat_pages, cat_subcats, cat_files)
```

**Bẫy đã kiểm chứng 13/11/2026:** `cl_target_id` **không** phải `cat_id`
(cũng không phải `page_id`) mà là `lt_id` của bảng `linktarget`. Nếu dùng nhầm
`cat_id`, "Vua Việt Nam" (cat_id 23389) sẽ không khớp bài nào; nếu dùng nhầm
`page_id`, lại gán nhầm "Friedrich Paulus" vào "Vua Việt Nam".

## Sản phẩm

- `data/interim/category_members.json` — `{category_title: [page_id, ...]}`
- `data/interim/category_hierarchy.json` — `{category_title: [subcategory_title, ...]}`

Cách chạy:
    python -m src.preprocess.category_index --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
from pathlib import Path

from src.common.config import REPO_ROOT, load_config
from src.common.logger import get_logger
from src.common.normalize import normalize_name

logger = get_logger(__name__)

#: Regex tuple của bảng `page`:
#: ``(page_id,page_namespace,'page_title',...)``.
_PAGE_ROW_RE = re.compile(r"^\(\s*(\d+)\s*,\s*(\d+)\s*,\s*'((?:[^'\\]|\\.|'')*)'")

#: Regex tuple của bảng `linktarget`:
#: ``(lt_id,lt_namespace,'lt_title')``.
_LINKTARGET_ROW_RE = re.compile(
    r"^\(\s*(\d+)\s*,\s*(\d+)\s*,\s*'((?:[^'\\]|\\.|'')*)'\s*\)"
)

#: Regex tuple của bảng `categorylinks`. `cl_sortkey` là chuỗi binary và
#: `cl_sortkey_prefix` có thể khác rỗng → chỉ khớp **phần đuôi** của tuple
#: (cột `cl_type`, `cl_collation_id`, `cl_target_id`) cùng `cl_from` ở đầu.
_CATEGORYLINK_ROW_RE = re.compile(
    r"^\(\s*(\d+)\s*,.*,\s*'(page|subcat|file)'\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*[;,]?\s*$"
)


def _unescape_sql(value: str) -> str:
    """Giải mã chuỗi SQL escape.

    Args:
        value: Chuỗi thô.

    Returns:
        Chuỗi đã giải mã.
    """
    return value.replace("''", "'").replace("\\'", "'").replace("\\\\", "\\")


def parse_article_page_ids(sql_path: Path) -> set[int]:
    """Parse bảng `page` → tập `page_id` của bài viết (namespace 0).

    Args:
        sql_path: Đường dẫn `page.sql.gz`.

    Returns:
        Tập page_id của bài viết.
    """
    page_ids: set[int] = set()
    logger.info("Đọc %s ...", sql_path.name)
    with gzip.open(sql_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("("):
                continue
            match = _PAGE_ROW_RE.match(line)
            if match is None:
                continue
            page_id, namespace, _title = match.groups()
            if namespace == "0":
                page_ids.add(int(page_id))
    logger.info("page: %d bài viết (ns 0)", len(page_ids))
    return page_ids


def parse_category_page_ids(sql_path: Path) -> dict[int, str]:
    """Parse bảng `page` → `{page_id: title}` cho trang category (ns 14).

    Args:
        sql_path: Đường dẫn `page.sql.gz`.

    Returns:
        Dict ánh xạ page_id → tên trang category.
    """
    mapping: dict[int, str] = {}
    logger.info("Đọc %s (ns 14) ...", sql_path.name)
    with gzip.open(sql_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("("):
                continue
            match = _PAGE_ROW_RE.match(line)
            if match is None:
                continue
            page_id, namespace, title = match.groups()
            if namespace == "14":
                mapping[int(page_id)] = _unescape_sql(title).replace("_", " ")
    logger.info("page: %d trang category (ns 14)", len(mapping))
    return mapping


def parse_linktarget(sql_path: Path) -> dict[int, tuple[int, str]]:
    """Parse bảng `linktarget` → `{lt_id: (namespace, title)}`.

    Args:
        sql_path: Đường dẫn `linktarget.sql.gz`.

    Returns:
        Dict ánh xạ lt_id → (namespace, title).
    """
    mapping: dict[int, tuple[int, str]] = {}
    logger.info("Đọc %s ...", sql_path.name)
    with gzip.open(sql_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("("):
                continue
            match = _LINKTARGET_ROW_RE.match(line)
            if match is None:
                continue
            lt_id, namespace, title = match.groups()
            mapping[int(lt_id)] = (
                int(namespace),
                _unescape_sql(title).replace("_", " "),
            )
    logger.info("linktarget: %d mục", len(mapping))
    return mapping


def parse_categorylinks(
    sql_path: Path,
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Parse bảng `categorylinks`.

    Args:
        sql_path: Đường dẫn `categorylinks.sql.gz`.

    Returns:
        Tuple ``(members, subcats)``:
        - `members`: `{page_id: [lt_id, ...]}` — bài viết thuộc category nào.
        - `subcats`: `{lt_id: [lt_id, ...]}` — category cha chứa subcat nào.
    """
    members: dict[int, list[int]] = {}
    subcats: dict[int, list[int]] = {}
    logger.info("Đọc %s ...", sql_path.name)
    with gzip.open(sql_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("("):
                continue
            match = _CATEGORYLINK_ROW_RE.match(line)
            if match is None:
                continue
            cl_from, cl_type, _collation, cl_target = match.groups()
            source = int(cl_from)
            target = int(cl_target)
            if cl_type == "subcat":
                subcats.setdefault(source, []).append(target)
            elif cl_type == "page":
                members.setdefault(source, []).append(target)
    logger.info(
        "categorylinks: %d nguồn có category, %d nguồn có subcategory",
        len(members),
        len(subcats),
    )
    return members, subcats


def expand_categories(
    seeds: list[str],
    title_to_lt_id: dict[str, int],
    parent_to_children: dict[str, list[str]],
    max_depth: int = 3,
) -> set[str]:
    """Mở rộng đệ quy tập category seed theo cây subcategory.

    Args:
        seeds: Danh sách tên category seed.
        title_to_lt_id: Ánh xạ tên category (đã chuẩn hóa) → lt_id.
        parent_to_children: Ánh xạ tên category cha → danh sách tên con.
        max_depth: Độ sâu mở rộng tối đa.

    Returns:
        Tập tên category (đã chuẩn hóa) sau mở rộng.
    """
    expanded: set[str] = set()
    frontier: list[str] = []
    for seed in seeds:
        key = normalize_name(seed)
        if key not in title_to_lt_id:
            logger.warning("Category seed không tồn tại: %s", seed)
            continue
        if key in expanded:
            continue
        expanded.add(key)
        frontier.append(key)

    for depth in range(1, max_depth + 1):
        next_frontier: list[str] = []
        for parent in frontier:
            for child in parent_to_children.get(parent, []):
                child_key = normalize_name(child)
                if child_key in expanded:
                    continue
                expanded.add(child_key)
                next_frontier.append(child)
        logger.info(
            "  mở rộng độ sâu %d: %d category mới (tổng %d)",
            depth,
            len(next_frontier),
            len(expanded),
        )
        frontier = next_frontier
        if not frontier:
            break

    return expanded


def main(argv: list[str] | None = None) -> int:
    """Điểm vào của CLI.

    Args:
        argv: Danh sách tham số dòng lệnh.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Dựng chỉ mục category")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--seed-config", default="configs/seed_articles.yaml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    seed_config = load_config(REPO_ROOT / args.seed_config)
    dump_version = str(config["dump"]["dump_version"])
    raw_dir = REPO_ROOT / str(config["paths"]["raw_dir"])
    interim_dir = REPO_ROOT / str(config["paths"]["interim_dir"])

    page_path = raw_dir / f"viwiki-{dump_version}-page.sql.gz"
    linktarget_path = raw_dir / f"viwiki-{dump_version}-linktarget.sql.gz"
    links_path = raw_dir / f"viwiki-{dump_version}-categorylinks.sql.gz"
    for path in (page_path, linktarget_path, links_path):
        if not path.exists():
            logger.error("Không tìm thấy %s", path)
            return 1

    article_page_ids = parse_article_page_ids(page_path)
    category_page_ids = parse_category_page_ids(page_path)
    linktarget = parse_linktarget(linktarget_path)
    members, subcats = parse_categorylinks(links_path)

    # lt_id → tên category (chỉ lt_namespace = 14).
    lt_to_category_title: dict[int, str] = {}
    for lt_id, (namespace, title) in linktarget.items():
        if namespace == 14:
            lt_to_category_title[lt_id] = title

    # Bảng `category` không còn cần: tên category lấy từ `linktarget`.
    # `cl_from` là page_id: bài viết (ns 0) hoặc trang category (ns 14).
    valid_members = {
        page_id: [lt for lt in lts if lt in lt_to_category_title]
        for page_id, lts in members.items()
        if page_id in article_page_ids
    }
    # `valid_subcats` khóa theo **page_id** của trang category (ns 14), còn
    # giá trị là **lt_id** của category con. Đổi sang khóa theo *tên* category
    # để `expand_categories` đi theo cây subcategory (bug: trước đây cha
    # được tra theo lt_id nên không tìm thấy con nào → cây rỗng).
    parent_to_children: dict[str, list[str]] = {}
    for parent_page_id, child_lts in subcats.items():
        parent_title = category_page_ids.get(parent_page_id)
        if not parent_title:
            continue
        children = [
            lt_to_category_title[lt]
            for lt in child_lts
            if lt in lt_to_category_title
        ]
        if children:
            parent_to_children.setdefault(
                normalize_name(parent_title), []
            ).extend(children)
    logger.info(
        "Sau khi lọc: %d bài viết có category, %d category cha có subcategory",
        len(valid_members),
        len(parent_to_children),
    )

    # Tên category → lt_id, dùng để tìm seed và để đảo chiều.
    title_to_lt_id: dict[str, int] = {}
    for lt_id, title in lt_to_category_title.items():
        title_to_lt_id.setdefault(normalize_name(title), lt_id)

    expanded = expand_categories(
        list(seed_config["category_seeds"]),
        title_to_lt_id,
        parent_to_children,
        max_depth=int(seed_config.get("category_max_depth", 3)),
    )
    logger.info("Tập category sau mở rộng: %d", len(expanded))

    expanded_lts = {
        lt_id
        for lt_id, title in lt_to_category_title.items()
        if normalize_name(title) in expanded
    }
    logger.info("Tập category sau mở rộng: %d mục category", len(expanded_lts))

    # Đảo chiều: lt_id → danh sách page_id thành viên.
    members_by_cat: dict[int, list[int]] = {}
    for page_id, lts in valid_members.items():
        for lt_id in lts:
            members_by_cat.setdefault(lt_id, []).append(page_id)

    category_members: dict[str, list[int]] = {}
    for lt_id in expanded_lts:
        title = lt_to_category_title.get(lt_id)
        if not title:
            continue
        pages = sorted(members_by_cat.get(lt_id, []))
        if pages:
            category_members[normalize_name(title)] = pages

    # Cây phân cấp (tên → tên con) cho các category trong tập mở rộng.
    hierarchy: dict[str, list[str]] = {}
    for parent_title, children in parent_to_children.items():
        if parent_title not in expanded:
            continue
        kept = sorted(
            normalize_name(child) for child in children if normalize_name(child) in expanded
        )
        if kept:
            hierarchy[parent_title] = kept

    interim_dir.mkdir(parents=True, exist_ok=True)
    members_path = interim_dir / "category_members.json"
    members_path.write_text(
        json.dumps(category_members, ensure_ascii=False), encoding="utf-8"
    )
    hierarchy_path = interim_dir / "category_hierarchy.json"
    hierarchy_path.write_text(
        json.dumps(hierarchy, ensure_ascii=False), encoding="utf-8"
    )
    total_members = sum(len(v) for v in category_members.values())
    logger.info(
        "Đã ghi %d category / %d liên kết thành viên vào %s",
        len(category_members),
        total_members,
        members_path.name,
    )
    logger.info("Đã ghi cây phân cấp %d nhánh vào %s", len(hierarchy), hierarchy_path.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Chỉ mục category cho bộ lọc Phase 1 (tín hiệu T1).

## Vì sao không quét wikitext

Bảng `categorylinks.sql.gz` của dump Wikimedia **đã có sẵn** quan hệ
"bài viết → category" và "category → subcategory" cho toàn bộ wiki. Dùng nó
nhanh hơn nhiều so với quét 1.1 GB `pages-articles.xml.bz2` và cho phép mở
rộng đệ quy subcategory mà không phải đọc lại dump.

## Quan hệ giữa các bảng

```
page(page_id, page_namespace, page_title, ...)
    │  page_namespace = 14 → trang category
    │  page_namespace = 0  → bài viết
    ▼
categorylinks(cl_from, cl_sortkey, cl_timestamp, cl_sortkey_prefix,
              cl_type, cl_namespace, cl_title)
```

- `cl_from` = **page_id** của trang nguồn (bài viết hoặc category cha).
- `cl_title` = **page_id** của trang category đích (KHÔNG phải `cat_id`).
- `cl_type` ∈ {`page`, `subcat`, `file`}.

`cl_title` là `page_id` của *trang* category, còn bảng `category` dùng `cat_id`
— hai định danh **khác nhau**. Vì vậy ta ánh xạ `page_id` → tên category
qua bảng `page` (namespace 14), không dùng bảng `category`.

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

#: Regex tuple của bảng `categorylinks`. `cl_sortkey` là chuỗi binary và
#: `cl_sortkey_prefix` có thể khác rỗng → chỉ khớp **phần đuôi** của tuple
#: (cột `cl_type`, `cl_namespace`, `cl_title`) cùng `cl_from` ở đầu.
_CATEGORYLINK_ROW_RE = re.compile(
    r"^\(\s*(\d+)\s*,.*,\s*'(page|subcat|file)'\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*,?\s*$"
)


def _unescape_sql(value: str) -> str:
    """Giải mã chuỗi SQL escape.

    Args:
        value: Chuỗi thô.

    Returns:
        Chuỗi đã giải mã.
    """
    return value.replace("''", "'").replace("\\'", "'").replace("\\\\", "\\")


def parse_page_titles(sql_path: Path) -> dict[int, str]:
    """Parse bảng `page` → `{page_id: title}` cho **mọi** namespace.

    Args:
        sql_path: Đường dẫn `page.sql.gz`.

    Returns:
        Dict ánh xạ page_id → tên trang (gạch dưới đã đổi thành khoảng trắng).
    """
    mapping: dict[int, str] = {}
    logger.info("Đọc %s ...", sql_path.name)
    with gzip.open(sql_path, "rt", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.startswith("("):
                continue
            match = _PAGE_ROW_RE.match(line)
            if match is None:
                continue
            page_id, _namespace, title = match.groups()
            mapping[int(page_id)] = _unescape_sql(title).replace("_", " ")
    logger.info("page: %d trang", len(mapping))
    return mapping


def parse_categorylinks(
    sql_path: Path,
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Parse bảng `categorylinks`.

    Args:
        sql_path: Đường dẫn `categorylinks.sql.gz`.

    Returns:
        Tuple ``(members, subcats)``:
        - `members`: `{page_id: [cat_page_id, ...]}` — bài viết thuộc category nào.
        - `subcats`: `{cat_page_id: [cat_page_id, ...]}` — category cha chứa subcat nào.
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
            cl_from, cl_type, _namespace, cl_title = match.groups()
            source = int(cl_from)
            target = int(cl_title)
            if cl_type == "subcat":
                subcats.setdefault(source, []).append(target)
            elif cl_type == "page":
                members.setdefault(source, []).append(target)
    logger.info(
        "categorylinks: %d trang có category, %d category cha có subcategory",
        len(members),
        len(subcats),
    )
    return members, subcats


def expand_categories(
    seeds: list[str],
    cat_page_to_title: dict[int, str],
    parent_to_children: dict[int, list[int]],
    max_depth: int = 3,
) -> set[str]:
    """Mở rộng đệ quy tập category seed theo cây subcategory.

    Args:
        seeds: Danh sách tên category seed.
        cat_page_to_title: Ánh xạ page_id của trang category → tên category.
        parent_to_children: Ánh xạ page_id category cha → danh sách page_id con.
        max_depth: Độ sâu mở rộng tối đa.

    Returns:
        Tập tên category (đã chuẩn hóa) sau khi mở rộng.
    """
    title_to_id: dict[str, int] = {}
    for page_id, title in cat_page_to_title.items():
        title_to_id.setdefault(normalize_name(title), page_id)

    expanded: set[str] = set()
    frontier: list[int] = []
    for seed in seeds:
        cat_id = title_to_id.get(normalize_name(seed))
        if cat_id is None:
            logger.warning("Category seed không tồn tại: %s", seed)
            continue
        expanded.add(normalize_name(seed))
        frontier.append(cat_id)

    for depth in range(1, max_depth + 1):
        next_frontier: list[int] = []
        for cat_id in frontier:
            for child in parent_to_children.get(cat_id, []):
                child_title = cat_page_to_title.get(child)
                if not child_title:
                    continue
                key = normalize_name(child_title)
                if key in expanded:
                    continue
                expanded.add(key)
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
    links_path = raw_dir / f"viwiki-{dump_version}-categorylinks.sql.gz"
    for path in (page_path, links_path):
        if not path.exists():
            logger.error("Không tìm thấy %s", path)
            return 1

    page_titles = parse_page_titles(page_path)
    members, subcats = parse_categorylinks(links_path)

    # Trang category = page_id có namespace 14.
    cat_page_to_title: dict[int, str] = {}
    for page_id, title in page_titles.items():
        cat_page_to_title[page_id] = title
    logger.info("Tổng số trang đã đọc: %d", len(page_titles))

    expanded = expand_categories(
        list(seed_config["category_seeds"]),
        cat_page_to_title,
        subcats,
        max_depth=int(seed_config.get("category_max_depth", 3)),
    )
    logger.info("Tập category sau mở rộng: %d", len(expanded))

    # Đảo chiều: cat_page_id → danh sách page_id thành viên.
    members_by_cat: dict[int, list[int]] = {}
    for page_id, cat_ids in members.items():
        for cat_id in cat_ids:
            members_by_cat.setdefault(cat_id, []).append(page_id)

    expanded_ids = {
        page_id
        for page_id, title in cat_page_to_title.items()
        if normalize_name(title) in expanded
    }
    logger.info("Tập category sau mở rộng: %d trang category", len(expanded_ids))

    category_members: dict[str, list[int]] = {}
    for cat_id in expanded_ids:
        title = cat_page_to_title.get(cat_id)
        if not title:
            continue
        pages = sorted(members_by_cat.get(cat_id, []))
        if pages:
            category_members[normalize_name(title)] = pages

    # Cây phân cấp (tên → tên con) cho các category trong tập mở rộng.
    hierarchy: dict[str, list[str]] = {}
    for parent_id, child_ids in subcats.items():
        if parent_id not in expanded_ids:
            continue
        parent_title = cat_page_to_title.get(parent_id)
        if not parent_title:
            continue
        children = sorted(
            cat_page_to_title[child]
            for child in child_ids
            if child in expanded_ids and child in cat_page_to_title
        )
        if children:
            hierarchy[normalize_name(parent_title)] = children

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

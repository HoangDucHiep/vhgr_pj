"""Lọc bài Wikipedia lịch sử Việt Nam từ dump (Module A1 — Phase 1).

## Bộ tín hiệu

| Mã | Tín hiệu | Nguồn | `keep_reason` |
|---|---|---|---|
| T0 | Wikidata: người / trận đánh / triều đại / sự kiện / địa danh trong phạm vi lịch sử VN | SPARQL QLever (cache đĩa) → `wikidata_seed_articles.json` | `wikidata` |
| T1 | Category khớp seed + mở rộng đệ quy subcategory (độ sâu ≤ 3) | `categorylinks.sql.gz` → `category_members.json` | `category` |
| T2 | Infobox thuộc whitelist **và** đủ trường lịch sử **và** có mốc năm trong cửa sổ lịch sử **và** liên quan Việt Nam | wikitext (parse đúng khối template) | `infobox` |
| T3 | BFS hyperlink nội bộ từ ứng viên đã có, nới ngưỡng trường lịch sử | wikitext | `seed_expansion` |
| T4 | Loại trừ (category + tiền tố tiêu đề) | wikitext | — |

## Kiến trúc 3 lượt quét dump (kiểm soát RAM < 4 GB)

Lượt 1 — **quét toàn bộ dump**, giữ metadata nhẹ của mọi ứng viên
(`page_id`, `title`, `revision_id`, `categories`, `links`).
Không giữ `wikitext` (3.000 bài × 20 KB ≈ 60 MB → vẫn an toàn, nhưng ta
vẫn ghi trực tiếp ra đĩa ở lượt 3 để tiết kiệm RAM).

Lượt 2 — **T3 BFS**: quét lại dump, xét các bài là đích hyperlink của
ứng viên; giữ bài nào thỏa điều kiện "nới ngưỡng T2".

Lượt 3 — **ghi output**: quét lại dump, ghi thẳng `wikitext` ra
`documents.jsonl` (streaming) — không tích lại vào RAM.

## Cách chạy

```bash
python -m src.preprocess.filter_articles --config configs/default.yaml
python -m src.preprocess.filter_articles --stats-only
```
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.common.config import REPO_ROOT, load_config
from src.common.ids import make_doc_id
from src.common.logger import get_logger
from src.common.normalize import normalize_name
from src.common.seed import set_seed
from src.common.text_utils import read_jsonl, write_jsonl
from src.preprocess.dump_reader import DumpPage, iter_dump_pages
from src.preprocess.infobox_parser import (
    history_fields,
    normalize_infobox_type,
    parse_infobox,
)

logger = get_logger(__name__)

#: Ngưỡng độ dài wikitext tối thiểu để coi là bài có nội dung thực.
MIN_WIKITEXT_LEN = 200

#: Số trang xử lý giữa mỗi lần ghi log tiến trình.
LOG_EVERY = 200_000

#: Thứ tự ưu tiên khi một bài khớp nhiều tín hiệu.
SIGNAL_PRIORITY = ["wikidata", "category", "infobox", "seed_expansion"]

#: Regex nhận diện category "liên quan tới Việt Nam" (dùng cho T2/T3/T5).
VIET_CATEGORY_RE = re.compile(r"viet|dai viet")

#: Tín hiệu Wikidata T0 đã chứng minh gắn với Việt Nam (P27/P19/P39/P17 → Q881).
#: Các tín hiệu này **không** cần thêm kiểm tra category.
VN_ANCHORED_SIGNALS = frozenset({"person", "place", "house"})

#: Tín hiệu Wikidata T0 quá rộng (battle/dynasty/event trên toàn Wikidata).
#: Bắt buộc phải có category trong phạm vi Việt Nam mới được giữ.
BROAD_SIGNALS = frozenset({"battle", "dynasty", "event"})

#: Category "nhà vua" — dùng để nhận diện phạm vi Việt Nam khi bài không
#: có category chứa chữ "Việt" (vd bài "Lý Thái Tông" chỉ có
#: "Người Bắc Ninh", "Vương tước nhà Lý").
#:
#: Khớp theo regex vì tên category biến thiên: "Nhà Lý", "Vương tước nhà Lý",
#: "Hoàng tộc nhà Lý", "Nhà Lê sơ", "Nhà Lê Trung Hưng"…
VN_HOUSE_RE = re.compile(
    r"\b(nha|vuong tuoc|hoang gia|hoang toc)\b.*"
    r"\b(ngo|dinh|tien le|ly|tran|ho|mac|le so|le trung hung|le trung huong|"
    r"le|nguyen|tay son|hoang de)\b"
)


def _wiki_url(title: str) -> str:
    """Dựng URL bài Wikipedia từ tiêu đề.

    Args:
        title: Tiêu đề bài.

    Returns:
        URL đầy đủ.
    """
    return f"https://vi.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}"


def _load_seed_signals(interim_dir: Path) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Nạp tín hiệu T0 từ `wikidata_seed_articles.json`.

    Args:
        interim_dir: Thư mục `data/interim`.

    Returns:
        Tuple ``(entries, seed_qids)``:
        - `entries`: `{title: {qid, signal, year, signals}}`.
        - `seed_qids`: tập QID của toàn bộ bài seed.
    """
    path = interim_dir / "wikidata_seed_articles.json"
    if not path.exists():
        logger.warning(
            "Không có %s — chạy `python -m src.preprocess.fetch_wikidata_seeds` trước",
            path.name,
        )
        return {}, set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, dict[str, Any]] = payload.get("entries", {})
    qids = {entry["qid"] for entry in entries.values() if entry.get("qid")}
    logger.info("T0 — %d bài seed (%d QID)", len(entries), len(qids))
    return entries, qids


def _load_category_members(interim_dir: Path) -> set[int]:
    """Nạp tập page_id thuộc category seed (T1).

    Args:
        interim_dir: Thư mục `data/interim`.

    Returns:
        Tập `page_id` (dạng số nguyên).
    """
    path = interim_dir / "category_members.json"
    if not path.exists():
        logger.warning(
            "Không có %s — chạy `python -m src.preprocess.category_index` trước",
            path.name,
        )
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    page_ids: set[int] = set()
    for pages in payload.values():
        page_ids.update(int(page) for page in pages)
    logger.info("T1 — %d bài thuộc category seed", len(page_ids))
    return page_ids


def _load_qid_map(interim_dir: Path) -> dict[str, str]:
    """Nạp ánh xạ `page_id → QID`.

    Args:
        interim_dir: Thư mục `data/interim`.

    Returns:
        Dict ``{"<page_id>": "<QID>"}``.
    """
    path = interim_dir / "pageid_to_qid.json"
    if not path.exists():
        logger.warning(
            "Không có %s — chạy `python -m src.preprocess.wikidata_map` trước",
            path.name,
        )
        return {}
    mapping = json.loads(path.read_text(encoding="utf-8"))
    logger.info("Bản đồ page_id → QID: %d mục", len(mapping))
    return mapping


def _is_excluded(
    title: str,
    categories: list[str],
    exclude_categories: set[str],
    exclude_prefixes: list[str],
) -> bool:
    """Kiểm tra bài có thuộc nhóm loại trừ (T4) không.

    Args:
        title: Tiêu đề bài.
        categories: Danh sách category của bài.
        exclude_categories: Tập category loại trừ (so khớp chính xác).
        exclude_prefixes: Danh sách tiền tố tiêu đề loại trừ.

    Returns:
        ``True`` nếu bài bị loại.
    """
    if any(title.startswith(prefix) for prefix in exclude_prefixes):
        return True
    normalized = {normalize_name(category) for category in categories}
    return any(normalize_name(excluded) in normalized for excluded in exclude_categories)


def _has_year_in_range(
    params: dict[str, str], year_min: int, year_max: int
) -> bool:
    """Kiểm tra infobox có mốc năm nào nằm trong cửa sổ lịch sử không.

    Args:
        params: Tham số infobox (khoá đã bỏ dấu).
        year_min: Năm nhỏ nhất.
        year_max: Năm lớn nhất.

    Returns:
        ``True`` nếu có ít nhất một năm hợp lệ.
    """
    for value in params.values():
        for match in re.finditer(r"\b(\d{3,4})\b", value):
            year = int(match.group(1))
            if year_min <= year <= year_max:
                return True
    return False


def _has_scope_category(categories: list[str]) -> bool:
    """Kiểm tra bài có category **thuộc phạm vi Việt Nam** hay không.

    Ngoài category chứa chữ "Việt",
    còn chấp nhận các category "nhà vua" (Nhà Lý, Nhà Trần, Nhà Nguyễn…)
    — vì nhiều bài nhân vật chỉ có category địa phương ("Người Bắc Ninh")
    hoặc category triều đại, không có chữ "Việt".

    Args:
        categories: Danh sách category của bài.

    Returns:
        ``True`` nếu có ít nhất một category thuộc phạm vi Việt Nam.
    """
    for category in categories:
        normalized = normalize_name(category)
        if VIET_CATEGORY_RE.search(normalized):
            return True
        if VN_HOUSE_RE.search(normalized):
            return True
    return False


def _in_history_scope(
    *,
    keep_reason: str,
    wikidata_signal: str | None,
    categories: list[str],
    in_seed_tree: bool,
) -> bool:
    """Kiểm tra bài có thực sự thuộc **phạm vi lịch sử Việt Nam** không.

    Đo trên corpus 3.113 bài của lượt chạy đầu: ~35% bài rơi ra ngoài phạm vi
    (Trận Stalingrad, Chiến tranh Afghanistan, Nhà Ptolemaios, Vương triều
    Palaiologos…) vì tín hiệu Wikidata `battle`/`dynasty` lấy được **mọi** trận
    đánh và triều đại có bài tiếng Việt, không giới hạn cho Việt Nam.

    Quy tắc (T5 — chốt sau khi đo):

    - Tín hiệu Wikidata **đã gắn Việt Nam** (`person`/`place`/`house` — tức
      `P27`/`P19`/`P39`/`P17` → `Q881`) → giữ, không cần kiểm tra thêm.
    - Tín hiệu Wikidata **quá rộng** (`battle`/`dynasty`/`event`) → chỉ giữ
      khi bài có category liên quan Việt Nam.
    - Tín hiệu `category` → bài phải vừa nằm trong cây category seed vừa có
      category liên quan Việt Nam (cây seed có cả nhánh "Chiến tranh liên
      quan tới Ba Lan" v.v. nên cần chặn thêm).
    - Tín hiệu `infobox`/`seed_expansion` → đã có kiểm tra Việt Nam ở T2/T3,
      giữ nguyên.

    Args:
        keep_reason: Tín hiệu đã khớp (`wikidata`/`category`/`infobox`/`seed_expansion`).
        wikidata_signal: Tín hiệu Wikidata gốc (chỉ có với `keep_reason="wikidata"`).
        categories: Danh sách category của bài.
        in_seed_tree: Bài có nằm trong cây category seed hay không.

    Returns:
        ``True`` nếu bài thuộc phạm vi lịch sử Việt Nam.
    """
    in_scope = _has_scope_category(categories)

    if keep_reason == "wikidata":
        if wikidata_signal in VN_ANCHORED_SIGNALS:
            return True
        return in_scope

    if keep_reason == "category":
        return in_seed_tree and in_scope

    return in_scope


def _infobox_profile(page: DumpPage) -> tuple[str | None, set[str], dict[str, str]]:
    """Trích thông tin infobox của một bài.

    Args:
        page: Trang dump.

    Returns:
        Tuple ``(node_type, history_field_names, params)``.
    """
    infobox = parse_infobox(page.wikitext)
    if infobox is None:
        return None, set(), {}
    return (
        normalize_infobox_type(infobox.loai),
        history_fields(infobox),
        infobox.params,
    )


def _classify(
    page: DumpPage,
    *,
    seed_titles: set[str],
    seed_qids: set[str],
    seed_entries: dict[str, dict[str, Any]],
    qid_map: dict[str, str],
    category_page_ids: set[int],
    infobox_whitelist: set[str],
    infobox_min_fields: dict[str, int],
    history_year_min: int,
    history_year_max: int,
    person_year_max: int,
) -> str | None:
    """Xác định `keep_reason` của một bài, hoặc ``None`` nếu không giữ.

    T0 khớp theo **QID** (đáng tin cậy hơn tên bài vì tên có thể trùng), sau đó
    mới thử tới tên bài. T2 yêu cầu infobox có loại nằm trong whitelist **và**
    đủ số trường lịch sử **và** có ít nhất một mốc năm nằm trong cửa sổ lịch
    sử **và** có category liên quan Việt Nam.

    Args:
        page: Trang dump.
        seed_titles: Tập tiêu đề seed T0.
        seed_qids: Tập QID seed T0.
        seed_entries: Thông tin seed T0 theo tiêu đề.
        qid_map: Ánh xạ `page_id → QID`.
        category_page_ids: Tập page_id thuộc category seed (T1).
        infobox_whitelist: Tập loại node được phép (T2).
        infobox_min_fields: Số trường lịch sử tối thiểu theo loại node (T2).
        history_year_min: Năm nhỏ nhất trong cửa sổ lịch sử.
        history_year_max: Năm lớn nhất trong cửa sổ lịch sử.
        person_year_max: Năm sinh tối đa của nhân vật (T0).

    Returns:
        `keep_reason` hoặc ``None``.
    """
    page_key = str(page.page_id)
    qid = qid_map.get(page_key, "")
    if (qid and qid in seed_qids) or page.title in seed_titles:
        entry = seed_entries.get(page.title)
        if entry is None:
            return "wikidata"
        year = entry.get("year")
        if year is None:
            return "wikidata"
        limit = (
            person_year_max
            if entry.get("signal") == "person"
            else history_year_max
        )
        return "wikidata" if year <= limit else None

    if page.page_id in category_page_ids:
        return "category"

    node_type, fields, params = _infobox_profile(page)
    if node_type is None or node_type not in infobox_whitelist:
        return None
    if len(fields) < int(infobox_min_fields.get(node_type, 2)):
        return None
    if not _has_year_in_range(params, history_year_min, history_year_max):
        return None
    if not _has_scope_category(page.categories):
        return None
    return "infobox"


def _scan_candidates(
    dump_path: Path,
    *,
    seed_titles: set[str],
    seed_qids: set[str],
    seed_entries: dict[str, dict[str, Any]],
    qid_map: dict[str, str],
    category_page_ids: set[int],
    infobox_whitelist: set[str],
    infobox_min_fields: dict[str, int],
    exclude_categories: set[str],
    exclude_prefixes: list[str],
    history_year_min: int,
    history_year_max: int,
    person_year_max: int,
) -> tuple[dict[int, dict[str, Any]], int]:
    """Lượt 1 — quét dump, chốt tập ứng viên (chỉ giữ metadata nhẹ).

    Args:
        dump_path: Đường dẫn `pages-articles.xml.bz2`.
        seed_titles: Tập tiêu đề seed T0.
        seed_qids: Tập QID seed T0.
        seed_entries: Thông tin seed T0 theo tiêu đề.
        qid_map: Ánh xạ `page_id → QID`.
        category_page_ids: Tập page_id thuộc category seed.
        infobox_whitelist: Tập loại node được phép.
        infobox_min_fields: Số trường lịch sử tối thiểu theo loại node.
        exclude_categories: Tập category loại trừ.
        exclude_prefixes: Tiền tố tiêu đề loại trừ.
        history_year_min: Năm nhỏ nhất trong cửa sổ lịch sử.
        history_year_max: Năm lớn nhất trong cửa sổ lịch sử.
        person_year_max: Năm sinh tối đa của nhân vật.

    Returns:
        Tuple ``(candidates, total_pages)``.
    """
    candidates: dict[int, dict[str, Any]] = {}
    total_pages = 0
    started = time.monotonic()

    for page in iter_dump_pages(dump_path):
        total_pages += 1
        if total_pages % LOG_EVERY == 0:
            logger.info(
                "  đã đọc %d trang (%.0fs), giữ %d ứng viên",
                total_pages,
                time.monotonic() - started,
                len(candidates),
            )
        if page.ns != 0 or page.is_redirect:
            continue
        if len(page.wikitext) < MIN_WIKITEXT_LEN:
            continue

        keep_reason = _classify(
            page,
            seed_titles=seed_titles,
            seed_qids=seed_qids,
            seed_entries=seed_entries,
            qid_map=qid_map,
            category_page_ids=category_page_ids,
            infobox_whitelist=infobox_whitelist,
            infobox_min_fields=infobox_min_fields,
            history_year_min=history_year_min,
            history_year_max=history_year_max,
            person_year_max=person_year_max,
        )
        if keep_reason is None:
            continue

        if _is_excluded(
            page.title, page.categories, exclude_categories, exclude_prefixes
        ):
            continue

        # T5 — chốt phạm vi lịch sử Việt Nam (xem `_in_history_scope`).
        signal = (
            seed_entries.get(page.title, {}).get("signal")
            if keep_reason == "wikidata"
            else None
        )
        if not _in_history_scope(
            keep_reason=keep_reason,
            wikidata_signal=signal,
            categories=page.categories,
            in_seed_tree=page.page_id in category_page_ids,
        ):
            continue

        candidates[page.page_id] = {
            "page_id": page.page_id,
            "title": page.title,
            "revision_id": page.revision_id,
            "categories": page.categories,
            "links": page.links,
            "keep_reason": keep_reason,
        }

    logger.info(
        "Lượt 1 xong: %d trang trong %.0fs, %d ứng viên",
        total_pages,
        time.monotonic() - started,
        len(candidates),
    )
    return candidates, total_pages


def _expand_bfs(
    dump_path: Path,
    candidates: dict[int, dict[str, Any]],
    *,
    seed_titles: set[str],
    max_depth: int,
    infobox_whitelist: set[str],
    history_year_min: int,
    history_year_max: int,
    exclude_categories: set[str],
    exclude_prefixes: list[str],
) -> int:
    """T3 — mở rộng BFS theo hyperlink nội bộ.

    Mỗi chiều sâu là **một lượt quét lại dump**: lấy `links` của các bài ở
    biên hiện tại, rồi đánh giá bài đích. Bài đích được giữ nếu có infobox
    loại được phép, có ≥ 1 trường lịch sử, có mốc năm trong cửa sổ lịch sử và
    có category liên quan Việt Nam — tức là T2 với ngưỡng trường **nới lỏng**
    (đây là lý do gọi là "mở rộng": bắt được nhân vật/địa danh có infobox
    thiếu trường nhưng chắc chắn thuộc lịch sử Việt Nam).

    Args:
        dump_path: Đường dẫn `pages-articles.xml.bz2`.
        candidates: Dict ứng viên (được cập nhật tại chỗ).
        seed_titles: Tập tiêu đề seed gốc.
        max_depth: Chiều sâu tối đa.
        infobox_whitelist: Tập loại node được phép.
        history_year_min: Năm nhỏ nhất trong cửa sổ lịch sử.
        history_year_max: Năm lớn nhất trong cửa sổ lịch sử.
        exclude_categories: Tập category loại trừ.
        exclude_prefixes: Tiền tố tiêu đề loại trừ.

    Returns:
        Số bài đã thêm mới.
    """
    title_to_page_id = {
        record["title"].lower(): record["page_id"] for record in candidates.values()
    }
    seen_titles = set(title_to_page_id) | {t.lower() for t in seed_titles}
    frontier = {title for title in seen_titles}
    added = 0

    for depth in range(1, max_depth + 1):
        if not frontier:
            break
        logger.info("T3 — BFS độ sâu %d (biên %d bài)", depth, len(frontier))

        wanted = {title.lower() for title in frontier}
        links_map: dict[str, list[str]] = {}
        total = 0
        for page in iter_dump_pages(dump_path):
            total += 1
            if total % LOG_EVERY == 0:
                logger.info("  quét %d trang (tìm %d tiêu đề)", total, len(wanted))
            if page.ns != 0 or page.is_redirect:
                continue
            key = page.title.lower()
            if key in wanted:
                links_map[key] = page.links

        next_frontier: set[str] = set()
        for links in links_map.values():
            for link in links:
                key = link.lower()
                if key in seen_titles:
                    continue
                seen_titles.add(key)
                next_frontier.add(link)

        logger.info(
            "T3 — độ sâu %d: +%d tiêu đề đích (tổng %d đã thấy)",
            depth,
            len(next_frontier),
            len(seen_titles),
        )
        frontier = next_frontier

    if not frontier:
        return added

    logger.info("T3 — đánh giá %d bài đích", len(frontier))
    wanted = {title.lower() for title in frontier}
    total = 0
    for page in iter_dump_pages(dump_path):
        total += 1
        if total % LOG_EVERY == 0:
            logger.info("  quét %d trang (cần %d tiêu đề)", total, len(wanted))
        if page.ns != 0 or page.is_redirect:
            continue
        if page.title.lower() not in wanted:
            continue
        if page.page_id in candidates:
            continue
        if len(page.wikitext) < MIN_WIKITEXT_LEN:
            continue
        if _is_excluded(
            page.title, page.categories, exclude_categories, exclude_prefixes
        ):
            continue
        node_type, fields, params = _infobox_profile(page)
        if node_type is None or node_type not in infobox_whitelist:
            continue
        if not fields:
            continue
        if not _has_year_in_range(params, history_year_min, history_year_max):
            continue
        if not _has_scope_category(page.categories):
            continue
        # T5 — bài mở rộng cũng phải nằm trong phạm vi lịch sử Việt Nam.
        if not _in_history_scope(
            keep_reason="seed_expansion",
            wikidata_signal=None,
            categories=page.categories,
            in_seed_tree=False,
        ):
            continue
        candidates[page.page_id] = {
            "page_id": page.page_id,
            "title": page.title,
            "revision_id": page.revision_id,
            "categories": page.categories,
            "links": page.links,
            "keep_reason": "seed_expansion",
        }
        added += 1

    logger.info("T3 — thêm %d bài", added)
    return added


def _write_documents(
    dump_path: Path,
    candidates: dict[int, dict[str, Any]],
    output_path: Path,
    *,
    dump_version: str,
    qid_map: dict[str, str],
    seed_entries: dict[str, dict[str, Any]],
) -> int:
    """Lượt cuối — ghi `documents.jsonl` (streaming wikitext ra đĩa).

    Args:
        dump_path: Đường dẫn `pages-articles.xml.bz2`.
        candidates: Dict ứng viên.
        output_path: Đường dẫn output.
        dump_version: Phiên bản dump.
        qid_map: Ánh xạ `page_id → QID`.
        seed_entries: Thông tin seed T0 theo tiêu đề.

    Returns:
        Số bài đã ghi.
    """
    written = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for page in iter_dump_pages(dump_path):
            if page.ns != 0 or page.is_redirect:
                continue
            record = candidates.get(page.page_id)
            if record is None:
                continue

            seed_entry = seed_entries.get(page.title)
            qid = qid_map.get(str(page.page_id)) or (
                seed_entry.get("qid") if seed_entry else ""
            )
            infobox = parse_infobox(page.wikitext)
            infobox_type = (
                normalize_infobox_type(infobox.loai) if infobox is not None else None
            )

            payload = {
                "doc_id": make_doc_id(page.page_id),
                "page_id": page.page_id,
                "title": page.title,
                "url": _wiki_url(page.title),
                "revision_id": page.revision_id,
                "categories": record["categories"],
                "wikibase_item": qid or None,
                "infobox_type": infobox_type,
                "keep_reason": record["keep_reason"],
                "wikidata_signal": seed_entry.get("signal") if seed_entry else None,
                "wikidata_year": seed_entry.get("year") if seed_entry else None,
                "dump_version": dump_version,
                "wikitext": page.wikitext,
            }
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")
            written += 1

    logger.info(
        "Đã ghi %d bài vào %s (%.0fs)",
        written,
        output_path.name,
        time.monotonic() - started,
    )
    return written


def _build_stats(
    output_path: Path,
    *,
    namespace_pages: int,
    candidates: int,
    seed_config: dict[str, Any],
) -> dict[str, Any]:
    """Tổng hợp thống kê bộ lọc từ file output.

    Args:
        output_path: Đường dẫn `documents.jsonl`.
        namespace_pages: Tổng số trang đã đọc.
        candidates: Số ứng viên sau tất cả tầng lọc.
        seed_config: Cấu hình seed.

    Returns:
        Dict thống kê.
    """
    by_reason: Counter[str] = Counter()
    by_infobox: Counter[str] = Counter()
    by_signal: Counter[str] = Counter()
    category_groups: Counter[str] = Counter()
    with_qid = 0
    total = 0
    empty_wikitext = 0

    for row in read_jsonl(output_path):
        total += 1
        by_reason[row.get("keep_reason") or "unknown"] += 1
        by_infobox[row.get("infobox_type") or "none"] += 1
        by_signal[row.get("wikidata_signal") or "none"] += 1
        if row.get("wikibase_item"):
            with_qid += 1
        if not row.get("wikitext"):
            empty_wikitext += 1
        for category in row.get("categories") or []:
            category_groups[normalize_name(category)] += 1

    target_min = int(seed_config["target_min_articles"])
    target_max = int(seed_config["target_max_articles"])

    return {
        "total_articles": total,
        "candidates_after_filter": candidates,
        "total_pages_scanned": namespace_pages,
        "by_keep_reason": dict(by_reason),
        "by_infobox_type": dict(by_infobox),
        "by_wikidata_signal": dict(by_signal),
        "top_categories": dict(category_groups.most_common(50)),
        "articles_with_qid": with_qid,
        "articles_with_qid_ratio": round(with_qid / total, 4) if total else 0.0,
        "articles_with_empty_wikitext": empty_wikitext,
        "target_min": target_min,
        "target_max": target_max,
        "in_target_range": bool(target_min <= total <= target_max),
    }


def _print_stats(stats_path: Path) -> None:
    """In thống kê bộ lọc ra stdout.

    Args:
        stats_path: Đường dẫn file thống kê.
    """
    if not stats_path.exists():
        logger.warning("Không có file thống kê: %s", stats_path)
        return
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    logger.info("=== THỐNG KÊ BỘ LỌC ===")
    logger.info("Tổng số bài giữ: %s", stats.get("total_articles"))
    logger.info("Theo keep_reason: %s", stats.get("by_keep_reason"))
    logger.info("Theo infobox_type: %s", stats.get("by_infobox_type"))
    logger.info("Theo tín hiệu Wikidata: %s", stats.get("by_wikidata_signal"))
    logger.info(
        "Bài có QID: %s (%.1f%%)",
        stats.get("articles_with_qid"),
        100.0 * float(stats.get("articles_with_qid_ratio") or 0.0),
    )
    logger.info(
        "Trong khoảng mục tiêu %s–%s: %s",
        stats.get("target_min"),
        stats.get("target_max"),
        stats.get("in_target_range"),
    )


def main(argv: list[str] | None = None) -> int:
    """Điểm vào của CLI.

    Args:
        argv: Danh sách tham số dòng lệnh (mặc định lấy từ `sys.argv`).

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Lọc bài lịch sử Việt Nam từ dump")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--seed-config", default="configs/seed_articles.yaml")
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Chỉ in thống kê từ file đã lọc, không chạy lại pipeline",
    )
    args = parser.parse_args(argv)

    config = load_config(args.config)
    seed_config = load_config(REPO_ROOT / args.seed_config)

    interim_dir = REPO_ROOT / str(config["paths"]["interim_dir"])
    output_path = interim_dir / "documents.jsonl"
    stats_path = interim_dir / "filter_stats.json"

    if args.stats_only:
        _print_stats(stats_path)
        return 0

    set_seed(int(config.get("seed", 42)))

    dump_version = str(config["dump"]["dump_version"])
    raw_dir = REPO_ROOT / str(config["paths"]["raw_dir"])
    dump_path = raw_dir / f"viwiki-{dump_version}-pages-articles.xml.bz2"

    if not dump_path.exists():
        logger.error("Không tìm thấy dump: %s", dump_path)
        logger.error("Chạy: python scripts/download_dump.py --dump-version %s", dump_version)
        return 1

    seed_entries, seed_qids = _load_seed_signals(interim_dir)
    seed_titles = set(seed_entries)
    category_page_ids = _load_category_members(interim_dir)
    qid_map = _load_qid_map(interim_dir)

    infobox_whitelist = set(seed_config["infobox_whitelist"])
    infobox_min_fields = {
        str(key): int(value)
        for key, value in dict(
            seed_config.get("infobox_min_history_fields", {})
        ).items()
    }
    exclude_categories = set(seed_config["exclude_categories"])
    exclude_prefixes = list(seed_config["exclude_title_prefixes"])
    history_year_min = int(seed_config.get("history_year_min", 850))
    history_year_max = int(seed_config.get("history_year_max", 1945))
    person_year_max = int(seed_config.get("person_year_max", 1900))

    candidates, total_pages = _scan_candidates(
        dump_path,
        seed_titles=seed_titles,
        seed_qids=seed_qids,
        seed_entries=seed_entries,
        qid_map=qid_map,
        category_page_ids=category_page_ids,
        infobox_whitelist=infobox_whitelist,
        infobox_min_fields=infobox_min_fields,
        exclude_categories=exclude_categories,
        exclude_prefixes=exclude_prefixes,
        history_year_min=history_year_min,
        history_year_max=history_year_max,
        person_year_max=person_year_max,
    )

    added = _expand_bfs(
        dump_path,
        candidates,
        seed_titles=seed_titles,
        max_depth=int(seed_config.get("bfs_max_depth", 2)),
        infobox_whitelist=infobox_whitelist,
        history_year_min=history_year_min,
        history_year_max=history_year_max,
        exclude_categories=exclude_categories,
        exclude_prefixes=exclude_prefixes,
    )
    logger.info("Tổng sau T3: %d bài (+%d từ BFS)", len(candidates), added)

    written = _write_documents(
        dump_path,
        candidates,
        output_path,
        dump_version=dump_version,
        qid_map=qid_map,
        seed_entries=seed_entries,
    )

    stats = _build_stats(
        output_path,
        namespace_pages=total_pages,
        candidates=len(candidates),
        seed_config=seed_config,
    )
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Đã ghi %d bài (%d dòng)", written, written)
    _print_stats(stats_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

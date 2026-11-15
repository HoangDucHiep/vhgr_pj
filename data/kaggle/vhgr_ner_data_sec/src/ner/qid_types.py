"""Tra cứu loại (nhãn NER) của QID từ Wikidata (Phase 4 — B2.1).

Vì sao cần module riêng: tra cứu Wikidata tốn **thời gian mạng** và bị
**rate-limit** (QLever trả HTTP 429 nếu gọi liên tiếp quá nhanh). Nên:

1. **Tách bước tra lớp `P31`** khỏi bước **map lớp → nhãn**:
   - Bước 1 (mạng): lấy `P31` của hàng loạt QID, ghi cache đĩa
     ``data/interim/qid_types.json``.
   - Bước 2 (mạng, ít hơn nhiều): mở rộng **phân cấp lớp** `P279*` cho
     tập lớp `P31` đã thu được — vì phần lớn QID có `P31` là lớp **con**
     (vd "Lê Lợi" → "nhân vật lịch sử" → `P279*` → "con người").
   - Bước 3 (không mạng): map lớp → nhãn NER theo
     ``configs/wikidata_type_map.yaml``.

Nhờ cache đĩa + cache SPARQL có sẵn trong ``src/preprocess/wikidata_query.py``,
chạy lại Phase 4 **không** tốn thêm request mạng nào.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.common.config import resolve_path
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Số QID trong 1 request SPARQL (dùng `VALUES`).
DEFAULT_BATCH_SIZE = 500

#: Số giây nghỉ thêm giữa 2 batch (trừ throttle sẵn có của `wikidata_query`).
EXTRA_SLEEP_S = 0.6

#: Số lần thử lại cho 1 batch khi endpoint bị rate-limit.
MAX_BATCH_RETRIES = 4


def _qid_from_uri(value: str) -> str:
    """Trích QID từ URI Wikidata.

    QLever trả URI dạng ``<http://www.wikidata.org/entity/Q5>`` (có dấu
    ``<``/``>`` bao ngoài), còn WDQS trả URI trần. Hàm này xử lý cả hai.

    Args:
        value: URI (có hoặc không có dấu ngoặc nhọn).

    Returns:
        QID (vd ``Q5``).
    """
    return value.strip().strip("<>").rsplit("/", 1)[-1]


def _fetch_p31(
    qids: list[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    use_cache: bool = True,
) -> dict[str, list[str]]:
    """Lấy lớp `P31` cho danh sách QID (gọi mạng, có cache SPARQL).

    Args:
        qids: Danh sách QID cần tra.
        batch_size: Số QID mỗi request.
        use_cache: Dùng cache SPARQL trên đĩa hay không.

    Returns:
        Map ``{qid: [lớp P31, ...]}`` — chỉ chứa QID **có** ít nhất 1 lớp.
    """
    from src.preprocess.wikidata_query import PREFIXES, QLEVER_ENDPOINT, run_query

    result: dict[str, list[str]] = {}
    total = len(qids)
    for start in range(0, total, batch_size):
        chunk = qids[start : start + batch_size]
        values = " ".join(f"wd:{qid}" for qid in chunk)
        query = (
            PREFIXES
            + f"""
SELECT DISTINCT ?item ?cls WHERE {{
  VALUES ?item {{ {values} }}
  ?item wdt:P31 ?cls .
}}
"""
        )
        rows: list[dict[str, Any]] = []
        for attempt in range(1, MAX_BATCH_RETRIES + 1):
            try:
                rows = run_query(query, endpoints=(QLEVER_ENDPOINT,), use_cache=use_cache)
                break
            except Exception as exc:  # noqa: BLE001 — endpoint lỗi → thử lại
                wait = 5.0 * attempt
                logger.warning(
                    "Batch %d/%d lỗi (lần %d/%d): %s — chờ %.0fs",
                    start // batch_size + 1,
                    (total + batch_size - 1) // batch_size,
                    attempt,
                    MAX_BATCH_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
        for row in rows:
            item = row.get("?item", {}).get("value", "")
            cls = row.get("?cls", {}).get("value", "")
            if not item or not cls:
                continue
            result.setdefault(_qid_from_uri(item), []).append(_qid_from_uri(cls))
        time.sleep(EXTRA_SLEEP_S)
    return result


def _fetch_ancestors(
    classes: list[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    use_cache: bool = True,
) -> dict[str, set[str]]:
    """Mở rộng phân cấp lớp `P279*` cho tập lớp `P31`.

    Args:
        classes: Danh sách lớp cần mở rộng.
        batch_size: Số lớp mỗi request.
        use_cache: Dùng cache SPARQL trên đĩa hay không.

    Returns:
        Map ``{lớp: {các lớp cha}}``.
    """
    from src.preprocess.wikidata_query import PREFIXES, QLEVER_ENDPOINT, run_query

    ancestors: dict[str, set[str]] = {cls: set() for cls in classes}
    total = len(classes)
    for start in range(0, total, batch_size):
        chunk = classes[start : start + batch_size]
        values = " ".join(f"wd:{cid}" for cid in chunk)
        query = (
            PREFIXES
            + f"""
SELECT DISTINCT ?cls ?anc WHERE {{
  VALUES ?cls {{ {values} }}
  ?cls wdt:P279* ?anc .
}}
"""
        )
        rows: list[dict[str, Any]] = []
        for attempt in range(1, MAX_BATCH_RETRIES + 1):
            try:
                rows = run_query(query, endpoints=(QLEVER_ENDPOINT,), use_cache=use_cache)
                break
            except Exception as exc:  # noqa: BLE001
                wait = 5.0 * attempt
                logger.warning(
                    "Mở rộng P279 batch %d lỗi (lần %d/%d): %s — chờ %.0fs",
                    start // batch_size + 1,
                    attempt,
                    MAX_BATCH_RETRIES,
                    exc,
                    wait,
                )
                time.sleep(wait)
        for row in rows:
            cls = row.get("?cls", {}).get("value", "")
            anc = row.get("?anc", {}).get("value", "")
            if not cls or not anc:
                continue
            ancestors.setdefault(_qid_from_uri(cls), set()).add(_qid_from_uri(anc))
        time.sleep(EXTRA_SLEEP_S)
    return ancestors


def load_cached_p31(path: str | Path) -> dict[str, list[str]]:
    """Nạp cache `P31` từ đĩa.

    Args:
        path: Đường dẫn file cache.

    Returns:
        Map ``{qid: [lớp]}`` (rỗng nếu file không tồn tại).
    """
    resolved = resolve_path(path)
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    entries = payload.get("p31") or {}
    return {qid: list(classes) for qid, classes in entries.items()}


def save_cached_p31(
    path: str | Path,
    p31: dict[str, list[str]],
    ancestors: dict[str, set[str]],
) -> None:
    """Ghi cache `P31` + phân cấp lớp ra đĩa.

    Args:
        path: Đường dẫn file cache.
        p31: Map ``{qid: [lớp]}``.
        ancestors: Map ``{lớp: {lớp cha}}``.
    """
    resolved = resolve_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {
            "nguon": "Wikidata SPARQL (QLever) — P31 + P279*",
            "so_qid": len(p31),
            "so_lop": len(ancestors),
        },
        "p31": {qid: sorted(classes) for qid, classes in sorted(p31.items())},
        "ancestors": {
            cls: sorted(values) for cls, values in sorted(ancestors.items()) if values
        },
    }
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def resolve_qid_types(
    qids: list[str],
    *,
    cache_path: str | Path,
    batch_size: int = DEFAULT_BATCH_SIZE,
    refresh: bool = False,
) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    """Tra `P31` + phân cấp `P279*` cho danh sách QID (có cache đĩa).

    Args:
        qids: Danh sách QID cần tra.
        cache_path: Đường dẫn file cache.
        batch_size: Số QID mỗi request.
        refresh: Bỏ qua cache, tra lại từ đầu.

    Returns:
        Cặp ``(p31, ancestors)``.
    """
    unique = sorted({qid for qid in qids if qid})
    cached_p31 = {} if refresh else load_cached_p31(cache_path)
    cached_anc: dict[str, set[str]] = {}
    if cached_p31:
        payload = json.loads(resolve_path(cache_path).read_text(encoding="utf-8"))
        cached_anc = {
            cls: set(values) for cls, values in (payload.get("ancestors") or {}).items()
        }

    missing = [qid for qid in unique if qid not in cached_p31]
    if missing:
        logger.info("Tra P31 cho %d QID mới (đã cache %d)", len(missing), len(cached_p31))
        fetched = _fetch_p31(missing, batch_size=batch_size)
        cached_p31.update(fetched)
        logger.info("→ %d/%d QID có P31", len(fetched), len(missing))
    else:
        logger.info("Dùng cache P31: %d QID", len(cached_p31))

    # Mở rộng phân cấp cho **mọi** lớp P31 đã biết (kể cả lớp cũ trong cache)
    # — cần để ánh xạ `ancestor` hoạt động cho QID lấy từ cache.
    all_classes = sorted({cls for classes in cached_p31.values() for cls in classes})
    need_anc = [cls for cls in all_classes if cls not in cached_anc]
    if need_anc:
        logger.info("Mở rộng P279* cho %d lớp", len(need_anc))
        fetched_anc = _fetch_ancestors(need_anc, batch_size=batch_size)
        for cls, values in fetched_anc.items():
            cached_anc.setdefault(cls, set()).update(values)
    else:
        logger.info("Dùng cache phân cấp: %d lớp", len(cached_anc))

    save_cached_p31(cache_path, cached_p31, cached_anc)
    return cached_p31, cached_anc


def classify_qid(
    qid: str,
    *,
    p31: dict[str, list[str]],
    ancestors: dict[str, set[str]],
    direct: dict[str, str],
    ancestor_map: dict[str, str],
) -> tuple[str | None, str]:
    """Xác định nhãn NER của một QID.

    Thứ tự ưu tiên (giảm dần độ chắc chắn):

    1. ``qid_direct`` — lớp `P31` có trong bảng `direct` (tên lớp tự nó
       khớp từ khoá).
    2. ``qid_ancestor`` — lớp `P31` có trong bảng `ancestor` (lớp cha `P279`
       của nó khớp từ khoá).

    Args:
        qid: QID cần tra.
        p31: Map ``{qid: [lớp P31]}``.
        ancestors: Map ``{lớp: {lớp cha}}`` (giữ để tương thích cache).
        direct: Bảng map lớp → nhãn (khớp trực tiếp).
        ancestor_map: Bảng map lớp → nhãn (khớp lớp cha).

    Returns:
        Cặp ``(nhãn, nguồn)``; nhãn là ``None`` nếu không xác định được.
    """
    classes = p31.get(qid) or []
    if not classes:
        return None, "unknown"

    # (1) Khớp trực tiếp — ưu tiên lớp phổ biến nhất (thứ tự trong config).
    direct_rank = {cls: index for index, cls in enumerate(direct)}
    best: tuple[int, str] | None = None
    for cls in classes:
        label = direct.get(cls)
        if label is None:
            continue
        rank = direct_rank[cls]
        if best is None or rank < best[0]:
            best = (rank, label)
    if best is not None:
        return best[1], "qid_direct"

    # (2) Khớp lớp cha — bảng `ancestor` đã **precomputed** từ đồ thị P279,
    #     nên chỉ cần tra chính lớp P31.
    ancestor_rank = {cls: index for index, cls in enumerate(ancestor_map)}
    best = None
    for cls in classes:
        label = ancestor_map.get(cls)
        if label is None:
            continue
        rank = ancestor_rank[cls]
        if best is None or rank < best[0]:
            best = (rank, label)
    if best is not None:
        return best[1], "qid_ancestor"
    return None, "unknown"


def group_classes(qids: list[str], p31: dict[str, list[str]]) -> dict[str, int]:
    """Thống kê phân bố lớp `P31` (để báo cáo & chọn ngưỡng).

    Args:
        qids: Danh sách QID.
        p31: Map ``{qid: [lớp]}``.

    Returns:
        Map ``{lớp: số QID}`` giảm dần theo số lượng.
    """
    counter: dict[str, int] = defaultdict(int)
    for qid in qids:
        for cls in p31.get(qid) or []:
            counter[cls] += 1
    return dict(sorted(counter.items(), key=lambda item: -item[1]))

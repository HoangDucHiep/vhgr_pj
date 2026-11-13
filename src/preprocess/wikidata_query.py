"""Truy vấn Wikidata SPARQL với cache đĩa và giãn nhịp.

## Endpoint

| Endpoint | Vai trò | Ghi chú |
|---|---|---|
| `https://qlever.cs.uni-freiburg.de/api/wikidata` | **chính** | Nhanh, ổn định, không bị rate-limit |
| `https://query.wikidata.org/sparql` | dự phòng | Chậm hơn nhiều, hay trả HTTP 429 khi có outage |

QLever **không** khai báo prefix sẵn nên mọi query ở đây viết **tường minh**
(`wdt:`, `wd:`, `schema:`). WDQS chấp nhận cùng cú pháp đó.

## Vì sao cần cache

WDQS hay bị rate-limit (đã gặp HTTP 429 "1 req / min" do outage 13/11/2026).
Mọi query được ghi vào `data/interim/wikidata_cache/<sha1>.json` nên chạy lại
không gọi mạng lần nữa → pipeline idempotent.

## Vì sao không dùng `P463`/`P361` để suy ra `thuoc_trieu_dai`

Đã kiểm chứng 11/2026: hai quan hệ này trả **0** kết quả cho người thuộc triều
đại. Chiến lược thay thế (đã kiểm chứng, đủ cả 9 triều đại):

```
?person wdt:P31 wd:Q5 ; wdt:P27 wd:Q881 ; wdt:P569 ?birth .
FILTER(YEAR(?birth) < 1950)
```

Xem `docs/CONTEXT.md` §2.6 và `docs/05-du-lieu-va-nguon.md` §3.1.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Endpoint chính — QLever (nhanh, ổn định).
QLEVER_ENDPOINT = "https://qlever.dev/api/wikidata"

#: Endpoint dự phòng — WDQS (chậm, dễ 429).
WDQS_ENDPOINT = "https://query.wikidata.org/sparql"

#: Thứ tự thử các endpoint.
ENDPOINTS: tuple[str, ...] = (QLEVER_ENDPOINT, WDQS_ENDPOINT)

# User-Agent ASCII (header HTTP chỉ mã hoá được latin-1)
USER_AGENT = (
    "vhgr-npl-project/1.0 (Knowledge Graph lich su Viet Nam; "
    "contact: hoangduchiep) Python-urllib"
)

CACHE_DIR = REPO_ROOT / "data" / "interim" / "wikidata_cache"

#: Giây chờ tối thiểu giữa hai request liên tiếp.
MIN_INTERVAL_S = 1.2

#: Số lần thử lại cho mỗi endpoint.
MAX_RETRIES = 3

#: Prefix tường minh — QLever không khai báo sẵn.
PREFIXES = """PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

_last_request_ts: float = 0.0


def _throttle() -> None:
    """Chờ để đảm bảo giữa hai request có khoảng cách tối thiểu."""
    global _last_request_ts
    now = time.monotonic()
    wait = MIN_INTERVAL_S - (now - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def _cache_path(query: str) -> Path:
    """Đường dẫn file cache cho một query.

    Args:
        query: Nội dung SPARQL.

    Returns:
        `Path` file cache JSON.
    """
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Chuẩn hóa response về cùng một dạng cho cả QLever và WDQS.

    WDQS trả ``{"results": {"bindings": [...]}}``; QLever trả
    ``{"selected": [...], "res": [[...]]}`` — cần chuyển đổi về cùng dạng dict.

    Args:
        payload: JSON response.

    Returns:
        Danh sách dict binding.
    """
    if "results" in payload:
        return list(payload["results"].get("bindings", []))

    # Dạng QLever: `selected` là danh sách tên biến, `res` là ma trận giá trị.
    if "res" in payload and "selected" in payload:
        columns: list[str] = list(payload["selected"])
        rows: list[dict[str, Any]] = []
        for raw_row in payload["res"]:
            row: dict[str, Any] = {}
            for index, column in enumerate(columns):
                if index >= len(raw_row):
                    break
                value = raw_row[index]
                if value is None:
                    continue
                row[column] = {"type": "literal", "value": str(value)}
            rows.append(row)
        return rows

    return []


def run_query(
    query: str,
    *,
    use_cache: bool = True,
    endpoints: tuple[str, ...] = ENDPOINTS,
) -> list[dict[str, Any]]:
    """Chạy một query SPARQL và trả về danh sách binding.

    Thử lần lượt từng endpoint trong `endpoints`; mỗi endpoint thử tối đa
    `MAX_RETRIES` lần với exponential backoff.

    Args:
        query: Nội dung SPARQL (đã kèm prefix nếu cần).
        use_cache: Dùng/ghi cache đĩa hay không.
        endpoints: Danh sách endpoint thử lần lượt.

    Returns:
        Danh sách dict binding (mỗi dict là một hàng kết quả).

    Raises:
        RuntimeError: Nếu mọi endpoint đều thất bại.
    """
    cache_file = _cache_path(query)
    if use_cache and cache_file.exists():
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            rows = _extract_rows(payload)
            logger.info("Dùng cache SPARQL: %s (%d dòng)", cache_file.name, len(rows))
            return rows
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cache hỏng (%s), tải lại: %s", exc, cache_file.name)

    full_query = query if "PREFIX" in query.upper() else f"{PREFIXES}\n{query}"
    last_error: Exception | None = None

    for endpoint in endpoints:
        params = urllib.parse.urlencode({"query": full_query})
        if "qlever" in endpoint:
            url = endpoint
            accept = "application/qlever-results+json"
            data: bytes | None = params.encode("utf-8")
        else:
            url = f"{endpoint}?{params}"
            accept = "application/sparql-results+json"
            data = None
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        for attempt in range(1, MAX_RETRIES + 1):
            _throttle()
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if "exception" in payload:
                    raise RuntimeError(f"SPARQL lỗi: {payload['exception']}")
                rows = _extract_rows(payload)
                if use_cache:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(
                        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                    )
                logger.info("SPARQL (%s) trả về %d dòng", endpoint, len(rows))
                return rows
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (429, 500, 502, 503, 504):
                    backoff = min(45.0, 5.0 * (2 ** (attempt - 1)))
                    logger.warning(
                        "SPARQL %s HTTP %s — thử lại sau %.0fs (lần %d/%d)",
                        endpoint,
                        exc.code,
                        backoff,
                        attempt,
                        MAX_RETRIES,
                    )
                    time.sleep(backoff)
                    continue
                logger.warning("SPARQL %s HTTP %s — chuyển endpoint", endpoint, exc.code)
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
                last_error = exc
                backoff = min(45.0, 5.0 * (2 ** (attempt - 1)))
                logger.warning(
                    "SPARQL %s lỗi (%s) — thử lại sau %.0fs (lần %d/%d)",
                    endpoint,
                    exc,
                    backoff,
                    attempt,
                    MAX_RETRIES,
                )
                time.sleep(backoff)

    raise RuntimeError(f"Không gọi được SPARQL: {last_error}")


def build_person_sitelink_query(
    *,
    relation_filter: str = "P22",
    min_birth_year: int = 1950,
    limit: int = 20000,
) -> str:
    """Sinh query lấy người Việt Nam có bài viết tiếng Việt.

    Args:
        relation_filter: Nhóm quan hệ lọc thêm, dùng để có tín hiệu "người lịch sử":
            - ``"P22"`` → có cha (tín hiệu mạnh nhất, 203 người);
            - ``"P22|P25|P26"`` → có cha/mẹ/vợ (293 người);
            - ``"P22|P25|P26|P39"`` → thêm chức vụ (783 người);
            - ``""`` → không lọc thêm (1996 người).
        min_birth_year: Chỉ lấy người sinh trước năm này.
        limit: Giới hạn số dòng.

    Returns:
        Chuỗi SPARQL (đã kèm prefix tường minh).
    """
    relation_clause = ""
    if relation_filter:
        parts = [f"wdt:{code}" for code in relation_filter.split("|")]
        relation_clause = (
            "  { " + " } UNION { ".join(f"?person {part} ?rel" for part in parts) + " }\n"
        )

    return f"""{PREFIXES}
SELECT DISTINCT ?person ?article ?birthYear WHERE {{
  ?person wdt:P31 wd:Q5 ;
           wdt:P27 wd:Q881 ;
           wdt:P569 ?birth .
  FILTER(YEAR(?birth) < {min_birth_year})
{relation_clause}  ?article schema:about ?person ;
           schema:isPartOf <https://vi.wikipedia.org/> .
  BIND(YEAR(?birth) AS ?birthYear)
}}
LIMIT {limit}
"""


def build_item_labels_query(qids: list[str]) -> str:
    """Sinh query lấy nhãn tiếng Việt cho danh sách QID.

    Args:
        qids: Danh sách QID.

    Returns:
        Chuỗi SPARQL (đã kèm prefix tường minh).
    """
    values = " ".join(f"wd:{qid}" for qid in qids)
    return f"""{PREFIXES}
SELECT ?item ?itemLabel WHERE {{
  VALUES ?item {{ {values} }}
  ?item rdfs:label ?itemLabel .
  FILTER(LANG(?itemLabel) IN ("vi", "en"))
}}
"""


def build_dynasty_membership_query(dynasty_qids: list[str]) -> str:
    """Sinh query lấy quan hệ `thuoc_trieu_dai` từ Wikidata.

    Chiến lược: lấy toàn bộ thành viên của 9 triều đại qua `P463` (thành viên)
    và `P361` (thuộc về) — hai quan hệ này *dùng để xác định thành viên* thì
    hoạt động; chỉ có việc suy ra thành viên từ *người* mới không có kết quả.

    Args:
        dynasty_qids: Danh sách QID của 9 triều đại.

    Returns:
        Chuỗi SPARQL (đã kèm prefix tường minh).
    """
    values = " ".join(f"wd:{qid}" for qid in dynasty_qids)
    return f"""{PREFIXES}
SELECT DISTINCT ?person ?dynasty WHERE {{
  VALUES ?dynasty {{ {values} }}
  {{ ?person wdt:P463 ?dynasty }}
  UNION
  {{ ?person wdt:P361 ?dynasty }}
  UNION
  {{ ?dynasty wdt:P527 ?person }}
  ?person wdt:P31 wd:Q5 .
}}
"""

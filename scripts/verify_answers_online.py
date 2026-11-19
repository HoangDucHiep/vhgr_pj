#!/usr/bin/env python
"""Kiểm chứng **trực tuyến** câu hỏi + câu trả lời (Phase 19 — 19.e/19.g/19.h).

Vì sao cần script này?
----------------------
Theo chỉ đạo: **không được tin LLM-judge nói "đúng"**. Mọi câu trả lời phải
được đối chiếu với **nguồn ngoài** (Wikipedia/Wikidata **live**).

Cơ chế kiểm chứng (theo loại câu hỏi):

| Loại | Cách kiểm chứng | Nguồn live |
|---|---|---|
| `narrative`, `multi_turn` | Mọi **số năm** trong câu trả lời phải xuất hiện trong bài Wikipedia live của `evidence_doc_id` ⇒ năm không tìm thấy ⇒ **bịa** | `action=query&prop=extracts&explaintext=1` |
| `relational`, `multi_hop` | Đối chiếu `expected_entities` / `expected_answer` với **Wikidata live** (`P22`/`P25`/`P26`/`P40`...) ⇒ chấm đúng/sai **không cần LLM** | `Special:EntityData/<QID>.json` |
| `no_data` | Hệ thống **phải** trả "Không có trong dữ liệu" ⇒ nếu trả lời có nội dung ⇒ **bịa** | (không cần mạng) |

Ngoài ra (19.h — kiểm chứng **câu hỏi**): mỗi câu hỏi `narrative`/`multi_turn`
phải được xác nhận là **hợp lệ** — tức là **mọi năm** trong `expected_answer`
phải xuất hiện trong bài Wikipedia live. Câu hỏi vô lý ⇒ **loại khỏi thống kê**
và **ghi vào báo cáo** (không xoá âm thầm).

Cách dùng
---------
```bash
# Kiểm chứng checkpoint đã có (D-124) — chỉ tốn HTTP, không tốn quota LLM
python scripts/verify_answers_online.py \
    --checkpoint data/eval/eval_d124_checkpoint.jsonl \
    --qa-set data/eval/qa_rag_250_v2.jsonl \
    --out reports/phase19_verify_d124.json

# Chỉ kiểm chứng câu hỏi (không cần checkpoint)
python scripts/verify_answers_online.py \
    --qa-set data/eval/qa_rag_250_v2.jsonl \
    --questions-only --out reports/phase19_verify_questions.json
```

Cache đĩa: `data/interim/verify_cache/` ⇒ chạy lại **không** gọi mạng lần nữa.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

#: User-Agent ASCII (header HTTP chỉ mã hoá được latin-1).
USER_AGENT = (
    "vhgr-npl-project/1.0 (Knowledge Graph lich su Viet Nam; "
    "contact: hoangduchiep) Python-urllib"
)

#: Thư mục cache đĩa.
CACHE_DIR = REPO_ROOT / "data" / "interim" / "verify_cache"

#: Giây chờ tối thiểu giữa hai request liên tiếp (giãn nhịp ⇒ không bị chặn).
MIN_INTERVAL_S = 1.2

#: Số lần thử lại cho mỗi request.
MAX_RETRIES = 3

#: Số lần thử lại **riêng** cho lỗi 429 (bị giới hạn tần suất).
MAX_RETRIES_429 = 6

#: Giây chờ khi gặp 429 (tăng dần theo số lần thử).
THROTTLE_429_BASE_S = 20.0

#: Regex bắt số năm (1000–2099).
YEAR_RE = re.compile(r"(?<![\d,])((?:1[0-9]|20[0-9])\d{2})(?![\d,])")

#: Mẫu nhận diện câu trả lời "không có trong dữ liệu".
NOT_IN_DATA_RE = re.compile(
    r"không có (?:trong |bất kỳ )?dữ liệu|không tìm thấy (?:thông tin )?dữ liệu",
    re.IGNORECASE,
)

#: Quan hệ QA → (property Wikidata, hướng).
#:
#: - ``"out"`` ⇒ subject ``[prop]`` object.
#: - ``"in"`` ⇒ object ``[prop]`` subject (quan hệ ngược).
RELATION_PROPERTY: dict[str, tuple[str, str]] = {
    "cha_cua": ("P22", "out"),
    "me_cua": ("P25", "out"),
    "vo_cua": ("P26", "out"),
    "inverse_cha_cua": ("P40", "out"),
    "inverse_me_cua": ("P40", "out"),
    "sinh_nam": ("P569", "out"),
    "mat_nam": ("P570", "out"),
    "sinh_tai": ("P19", "out"),
    "mat_tai": ("P20", "out"),
}

#: Quan hệ `multi_hop` → chuỗi 2 bước (mỗi bước là `(prop, hướng)`).
MULTI_HOP_CHAIN: dict[str, list[tuple[str, str]]] = {
    "multi_hop_cha_cua_cha_cua": [("P22", "out"), ("P22", "out")],
    "multi_hop_me_cua_me_cua": [("P25", "out"), ("P25", "out")],
    "multi_hop_vo_cua_cha": [("P22", "out"), ("P26", "out")],
}

_last_request_ts: float = 0.0


# ----------------------------------------------------------------------
# Tiện ích chuẩn hoá
# ----------------------------------------------------------------------


def _norm(text: str) -> str:
    """Chuẩn hoá chuỗi: bỏ dấu, hạ chữ thường, gộp khoảng trắng.

    Args:
        text: Chuỗi gốc.

    Returns:
        Chuỗi đã chuẩn hoá.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    # ⚠️ Phase 19 — "đ"/"Đ" (U+0111/U+0110) **không** tách được bằng NFD
    # (không phải ký tự có dấu phụ) ⇒ phải thay **cả hai** chữ hoa/thường.
    #
    # Vì sao cần? "Bồ Đào Nha" (hoa "Đ") vs "bo đao nha" (thường "đ") ⇒
    # so khớp **rơi** ⇒ báo sai (false negative) cho câu hỏi hợp lệ.
    stripped = stripped.replace("đ", "d").replace("Đ", "D")
    return " ".join(stripped.lower().split())


def cache_key(prefix: str, value: str) -> str:
    """Khoá cache **không va chạm** cho tên bài Wikipedia.

    Vì sao cần?
    ----------
    `_norm()` bỏ dấu ⇒ "Lê Hiển Tông" và "Lê Hiến Tông" cho cùng một khoá
    ⇒ cache trả **nhầm bài** (bài Lê Hiến Tông, 1461–1504, thay cho bài
    Lê Hiển Tông, mất 1786) ⇒ câu trả lời **đúng** bị báo "năm không có
    trong Wikipedia" ⇒ **false negative** cho Gate G19-6.

    ⇒ Khoá cache phải dùng **tên gốc** (bỏ khoảng trắng thừa), **không** bỏ
    dấu. Vẫn giữ `_norm()` cho việc **so khớp tên** (khác mục đích).

    Args:
        prefix: Tiền tố (vd. "wiki_extract::").
        value: Tên bài gốc.

    Returns:
        Khoá cache.
    """
    return f"{prefix}{' '.join((value or '').split())}"


def _years_in(text: str) -> list[int]:
    """Trích mọi **số năm** có trong văn bản.

    Args:
        text: Văn bản.

    Returns:
        Danh sách năm (theo thứ tự xuất hiện, có thể trùng).
    """
    return [int(value) for value in YEAR_RE.findall(text or "")]


def _is_not_in_data(answer: str) -> bool:
    """Câu trả lời là "không có trong dữ liệu" hay không.

    Args:
        answer: Câu trả lời.

    Returns:
        ``True`` nếu là câu không có dữ liệu.
    """
    return bool(NOT_IN_DATA_RE.search(answer or ""))


# ----------------------------------------------------------------------
# HTTP + cache
# ----------------------------------------------------------------------


def _throttle() -> None:
    """Chờ để giữ khoảng cách tối thiểu giữa hai request."""
    global _last_request_ts
    now = time.monotonic()
    wait = MIN_INTERVAL_S - (now - _last_request_ts)
    if wait > 0:
        time.sleep(wait)
    _last_request_ts = time.monotonic()


def _cache_path(key: str) -> Path:
    """Đường dẫn file cache.

    Args:
        key: Khoá cache.

    Returns:
        `Path` tới file cache.
    """
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def http_get_json(url: str, *, cache_key: str | None = None) -> Any | None:
    """GET một URL JSON (có cache đĩa + giãn nhịp + retry).

    Args:
        url: URL cần gọi.
        cache_key: Khoá cache (None ⇒ dùng URL).

    Returns:
        JSON đã parse, hoặc ``None`` nếu thất bại.
    """
    key = cache_key or url
    cache_file = _cache_path(key)
    if cache_file.exists():
        try:
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            return payload.get("data") if isinstance(payload, dict) else payload
        except (json.JSONDecodeError, OSError):
            pass

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    attempt = 0
    while True:
        attempt += 1
        _throttle()
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps({"url": url, "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
            return data
        except urllib.error.HTTPError as error:
            # 429 = bị giới hạn tần suất ⇒ chờ lâu hơn rồi thử lại.
            if error.code == 429 and attempt <= MAX_RETRIES_429:
                wait = min(120.0, THROTTLE_429_BASE_S * attempt)
                print(f"  [HTTP] 429 — chờ {wait:.0f}s rồi thử lại ({attempt}/{MAX_RETRIES_429})")
                time.sleep(wait)
                continue
            if attempt >= MAX_RETRIES:
                print(f"  [HTTP] thất bại {url}: {error}")
                return None
            time.sleep(min(20.0, 3.0 * (2 ** (attempt - 1))))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt >= MAX_RETRIES:
                print(f"  [HTTP] thất bại {url}: {error}")
                return None
            time.sleep(min(20.0, 3.0 * (2 ** (attempt - 1))))
    return None


def wikipedia_extract(title: str) -> str:
    """Lấy **toàn văn bài** Wikipedia tiếng Việt (live).

    Args:
        title: Tên bài.

    Returns:
        Văn bản bài (rỗng nếu không lấy được / bài không tồn tại).
    """
    if not title:
        return ""
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "extracts",
            "explaintext": "1",
            "titles": title,
            "format": "json",
            "redirects": "1",
        }
    )
    url = f"https://vi.wikipedia.org/w/api.php?{params}"
    payload = http_get_json(url, cache_key=cache_key("wiki_extract::", title))
    if not isinstance(payload, dict):
        return ""
    pages = ((payload.get("query") or {}).get("pages") or {})
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        if page.get("missing") is not None:
            continue
        extract = str(page.get("extract") or "")
        if extract:
            return extract
    return ""


def wikipedia_search_ids(title: str) -> str:
    """Tra cứu `wikibase_item` của bài Wikipedia (live).

    Args:
        title: Tên bài.

    Returns:
        QID (rỗng nếu không tra được).
    """
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "pageprops",
            "titles": title,
            "format": "json",
            "redirects": "1",
        }
    )
    url = f"https://vi.wikipedia.org/w/api.php?{params}"
    payload = http_get_json(url, cache_key=cache_key("wiki_pageprops::", title))
    if not isinstance(payload, dict):
        return ""
    for page in ((payload.get("query") or {}).get("pages") or {}).values():
        if not isinstance(page, dict):
            continue
        qid = str((page.get("pageprops") or {}).get("wikibase_item") or "")
        if qid:
            return qid
    return ""


def wikidata_entity(qid: str) -> dict[str, Any]:
    """Lấy entity Wikidata (live) theo QID.

    Args:
        qid: QID (vd. ``Q20025876``).

    Returns:
        Dict entity (rỗng nếu không lấy được).
    """
    if not qid:
        return {}
    url = f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    payload = http_get_json(url, cache_key=f"wd_entity::{qid}")
    if not isinstance(payload, dict):
        return {}
    entities = payload.get("entities") or {}
    entity = entities.get(qid) or {}
    return entity if isinstance(entity, dict) else {}


def wikidata_labels(qids: Iterable[str]) -> dict[str, str]:
    """Lấy nhãn tiếng Việt (fallback tiếng Anh) cho nhiều QID.

    Args:
        qids: Danh sách QID.

    Returns:
        Dict QID → nhãn.
    """
    out: dict[str, str] = {}
    for qid in qids:
        entity = wikidata_entity(qid)
        labels = entity.get("labels") or {}
        label = (
            (labels.get("vi") or {}).get("value")
            or (labels.get("en") or {}).get("value")
            or ""
        )
        out[qid] = str(label)
    return out


def wikidata_property_targets(qid: str, prop: str) -> list[str]:
    """Lấy danh sách QID đích của 1 property Wikidata.

    Args:
        qid: QID chủ thể.
        prop: Property (vd. ``P22``).

    Returns:
        Danh sách QID đích.
    """
    entity = wikidata_entity(qid)
    claims = entity.get("claims") or {}
    targets: list[str] = []
    for claim in claims.get(prop) or []:
        if not isinstance(claim, dict):
            continue
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            targets.append(str(value["id"]))
    return targets


def wikidata_property_years(qid: str, prop: str) -> list[int]:
    """Lấy các **năm** trong property dạng thời gian (vd. `P569` sinh năm).

    Args:
        qid: QID chủ thể.
        prop: Property.

    Returns:
        Danh sách năm.
    """
    entity = wikidata_entity(qid)
    claims = entity.get("claims") or {}
    years: list[int] = []
    for claim in claims.get(prop) or []:
        if not isinstance(claim, dict):
            continue
        value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("time"):
            match = re.match(r"^[+-](\d{4})-", str(value["time"]))
            if match:
                years.append(int(match.group(1)))
    return years


# ----------------------------------------------------------------------
# Nạp dữ liệu
# ----------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Nạp file JSONL.

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách dict.
    """
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_doc_titles(path: Path) -> dict[str, str]:
    """Nạp map `doc_id` → tên bài Wikipedia.

    Args:
        path: `data/interim/documents_clean.jsonl`.

    Returns:
        Dict `doc_id` → title.
    """
    out: dict[str, str] = {}
    for record in load_jsonl(path):
        doc_id = str(record.get("doc_id") or "")
        title = str(record.get("title") or "")
        if doc_id and title:
            out[doc_id] = title
    return out


def load_entity_qids(path: Path) -> dict[str, dict[str, Any]]:
    """Nạp entity theo `entity_id` (kèm QID).

    Args:
        path: `data/knowledge_base/entities.jsonl`.

    Returns:
        Dict `entity_id` → entity.
    """
    out: dict[str, dict[str, Any]] = {}
    for record in load_jsonl(path):
        entity_id = str(record.get("entity_id") or "")
        if entity_id:
            out[entity_id] = record
    return out


def entity_index_by_name(entities: dict[str, dict[str, Any]]) -> dict[str, list[dict]]:
    """Index entity theo tên chuẩn hoá.

    Args:
        entities: Dict `entity_id` → entity.

    Returns:
        Dict tên chuẩn hoá → danh sách entity.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for entity in entities.values():
        name = _norm(str(entity.get("name") or ""))
        if name:
            index.setdefault(name, []).append(entity)
    return index


# ----------------------------------------------------------------------
# Kiểm chứng
# ----------------------------------------------------------------------


def verify_question(
    row: dict[str, Any],
    doc_titles: dict[str, str],
) -> dict[str, Any]:
    """Kiểm chứng **tính hợp lệ của câu hỏi** (19.h).

    Với câu `narrative`/`multi_turn`: mọi **năm** trong `expected_answer` phải
    xuất hiện trong bài Wikipedia live của `evidence_doc_id` ⇒ câu hỏi hợp lệ.
    Câu hỏi vô lý ⇒ `valid = False` + lý do (ghi ra báo cáo, **không** xoá âm thầm).

    Args:
        row: Bản ghi câu hỏi.
        doc_titles: Map `doc_id` → tên bài.

    Returns:
        Dict kết quả kiểm chứng.
    """
    qtype = str(row.get("type") or "")
    result: dict[str, Any] = {
        "qid": row.get("qid"),
        "type": qtype,
        "question": row.get("question"),
        "valid": True,
        "reason": "",
        "missing_years": [],
    }
    if qtype not in {"narrative", "multi_turn"}:
        result["reason"] = "không cần kiểm chứng online (nhóm khác)"
        return result

    doc_ids = [str(d) for d in (row.get("evidence_doc_id") or [])]
    titles = [doc_titles.get(doc_id, "") for doc_id in doc_ids]
    titles = [title for title in titles if title]
    if not titles:
        result["valid"] = False
        result["reason"] = "không có evidence_doc_id để đối chiếu"
        return result

    haystack = ""
    for title in titles:
        extract = wikipedia_extract(title)
        if extract:
            haystack += "\n" + extract
    if not haystack:
        result["valid"] = False
        result["reason"] = "không tải được bài Wikipedia live"
        return result

    years = _years_in(str(row.get("expected_answer") or ""))
    missing = [year for year in years if str(year) not in haystack]
    result["missing_years"] = missing
    if missing:
        result["valid"] = False
        result["reason"] = f"năm không có trong Wikipedia live: {missing}"
    return result


def _name_keys(name: str) -> set[str]:
    """Sinh các khóa so khớp tên từ 1 chuỗi.

    Wikidata thường lưu nhãn **rút gọn** ("Lê Tuân") trong khi bộ câu hỏi dùng
    nhãn **đầy đủ** ("Lê Tuân (An vương)") ⇒ so khớp phải bỏ phần trong ngoặc.

    Args:
        name: Tên.

    Returns:
        Tập khóa đã chuẩn hoá.
    """
    base = re.sub(r"\s*\([^)]*\)\s*", " ", name or "")
    keys = {_norm(base), _norm(name)}
    return {key for key in keys if key}


def _split_expected_names(expected: str, target_keys: set[str] | None = None) -> list[str]:
    """Tách đáp án nhiều người thành danh sách tên.

    ⚠️ **Không được** `split(",")` một cách mù quáng: nhãn Wikidata tiếng Việt
    thường **tự chứa dấu phẩy** (vd. "Vương tước Philip, Công tước xứ
    Edinburgh") ⇒ tách mù ⇒ sinh 2 mảnh vô nghĩa ("Vương tước Philip" và
    "Công tước xứ Edinburgh") ⇒ **báo sai** (false negative) cho câu hỏi hoàn
    toàn hợp lệ.
    ⇒ Cách sửa: thử mọi cách **gộp lại** các mảnh bằng ", " và giữ cách gộp
    mà **mọi** mảnh đều khớp với tập đích (`target_keys`). Nếu không có cách
    gộp nào khớp ⇒ coi **toàn bộ** chuỗi là **một** tên (không tách).

    Args:
        expected: Đáp án tham chiếu (có thể chứa nhiều tên, phân tách bởi ", ").
        target_keys: Tập khóa tên của đích (nếu có). Không có ⇒ **không tách**.

    Returns:
        Danh sách tên.
    """
    parts = [part.strip() for part in expected.split(",") if part.strip()]
    if len(parts) <= 1:
        return parts
    if not target_keys:
        # Không có tập đích để đối chiếu ⇒ **không được** đoán ⇒ giữ nguyên
        # (một tên).
        return [expected.strip()]

    def _hits(name: str) -> bool:
        """Tên (hoặc một phần của nó) có khớp tập đích không.

        Args:
            name: Tên cần so.

        Returns:
            ``True`` nếu khớp.
        """
        return bool(_name_keys(name) & target_keys)

    # Thử **mọi** cách gộp (2^(n-1) cách) ⇒ giữ cách gộp mà mọi mảnh đều
    # khớp. Vì số mảnh nhỏ (<=5) ⇒ chi phí không đáng kể.
    n = len(parts)
    for mask in range(1, 1 << (n - 1)):
        merged: list[str] = []
        buffer = parts[0]
        for i in range(1, n):
            if mask & (1 << (i - 1)):
                merged.append(buffer)
                buffer = parts[i]
            else:
                buffer = f"{buffer}, {parts[i]}"
        merged.append(buffer)
        if all(_hits(item) for item in merged):
            return merged
    # Không cách gộp nào khớp ⇒ coi toàn bộ là **một** tên.
    return [expected.strip()]


def wikidata_name_keys(qid: str) -> set[str]:
    """Lấy tập khóa tên (nhãn + bí danh) của 1 QID từ Wikidata live.

    Args:
        qid: QID.

    Returns:
        Tập khóa đã chuẩn hoá.
    """
    entity = wikidata_entity(qid)
    keys: set[str] = set()
    labels = entity.get("labels") or {}
    for lang in ("vi", "en"):
        value = (labels.get(lang) or {}).get("value")
        if value:
            keys |= _name_keys(str(value))
    # ⚠️ Wikidata lưu `aliases` theo **ngôn ngữ** (`{"vi": [...], "en": [...]}`)
    # ⇒ đọc như dict ⇒ lấy **mọi** bí danh (cả vi lẫn en).
    #
    # Vì sao cần? Vì nhãn chính và bí danh **khác nhau** rất nhiều: Q1156054
    # có nhãn "Trần Thị Dung" nhưng bí danh "Linh Từ quốc mẫu" ⇒ bộ câu hỏi
    # dùng "Linh Từ quốc mẫu" (tên trong bài Wikipedia) ⇒ nếu chỉ đọc nhãn
    # ⇒ **báo sai** (false negative) cho câu hỏi hoàn toàn hợp lệ.
    aliases = entity.get("aliases") or {}
    if isinstance(aliases, dict):
        alias_lists: list[Any] = []
        for lang in ("vi", "en"):
            alias_lists.extend(aliases.get(lang) or [])
    else:
        alias_lists = list(aliases)
    for alias in alias_lists:
        if isinstance(alias, dict):
            value = alias.get("value")
            if value:
                keys |= _name_keys(str(value))
    return keys


def verify_relational_online(
    row: dict[str, Any],
    entities: dict[str, dict[str, Any]],
    by_name: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Kiểm chứng quan hệ bằng **Wikidata live** (không cần LLM).

    Args:
        row: Bản ghi câu hỏi.
        entities: Dict `entity_id` → entity.
        by_name: Index entity theo tên chuẩn hoá.

    Returns:
        Dict kết quả (`verified`, `method`, `detail`).
    """
    relation = str(row.get("relation") or "")
    expected = str(row.get("expected_answer") or "")
    subject_name = str(row.get("subject_name") or "")

    if relation in MULTI_HOP_CHAIN:
        chain = MULTI_HOP_CHAIN[relation]
    elif relation in RELATION_PROPERTY:
        chain = [RELATION_PROPERTY[relation]]
    else:
        return {
            "verified": None,
            "method": "skipped",
            "detail": f"quan hệ không có bảng tra Wikidata: {relation}",
        }

    subject_candidates = by_name.get(_norm(subject_name)) or []
    subject_qid = ""
    for entity in subject_candidates:
        qid = str(entity.get("wikidata_qid") or "")
        if qid:
            subject_qid = qid
            break
    if not subject_qid:
        return {
            "verified": None,
            "method": "skipped",
            "detail": f"không tra được QID của chủ thể: {subject_name}",
        }

    current = [subject_qid]
    for prop, direction in chain:
        # Property **thời gian** (P569/P570) không trỏ tới QID mà mang giá trị
        # năm ⇒ xử lý riêng bên dưới.
        if prop in {"P569", "P570"}:
            break
        nxt: list[str] = []
        for qid in current:
            targets = wikidata_property_targets(qid, prop)
            if direction == "out":
                nxt.extend(targets)
            else:
                # Quan hệ ngược: tìm node nào có `prop` trỏ tới `qid`.
                nxt.extend(_incoming(qid, prop))
        current = nxt
        if not current:
            break

    # --- Năm (sinh/mất) ⇒ so năm, không so tên ---------------------------
    if len(chain) == 1 and chain[0][0] in {"P569", "P570"}:
        expected_years = _years_in(expected)
        live_years: set[int] = set()
        for qid in current:
            live_years |= set(wikidata_property_years(qid, chain[0][0]))
        if not live_years:
            return {
                "verified": None,
                "method": "wikidata_live",
                "detail": "Wikidata live không có năm cho property này",
            }
        hit = bool(set(expected_years) & live_years)
        return {
            "verified": hit,
            "method": "wikidata_live",
            "detail": f"năm live={sorted(live_years)} | kỳ vọng={expected_years}",
        }

    if not current:
        return {
            "verified": False,
            "method": "wikidata_live",
            "detail": "Wikidata live không có chuỗi quan hệ này",
        }

    labels = wikidata_labels(current)
    target_keys: set[str] = set()
    for qid in current:
        target_keys |= wikidata_name_keys(qid)

    # Đáp án có thể **nhiều tên** (vd. "Ai là con của X?" ⇒ "A, B, C")
    # ⇒ **mọi** tên trong danh sách đều phải có trong tập đích.
    #
    # Vì sao cần so **QID** chứ không chỉ so tên? Vì Wikipedia có thể ghi
    # "Lập Giáo Hoàng hậu" còn Wikidata chỉ ghi "Lê Long Đĩnh" ⇒ so tên thô
    # ⇒ **báo sai** (false negative). ⇒ Tra QID của từng tên trong KG nội bộ
    # rồi so với tập QID đích **lấy từ Wikidata live**.
    target_qids = set(current)
    expected_names = _split_expected_names(expected, target_keys)

    def _matches(name: str) -> bool:
        """Tên có khớp tập đích không (theo tên hoặc theo QID)?

        Args:
            name: Tên cần so.

        Returns:
            ``True`` nếu khớp.
        """
        if _name_keys(name) & target_keys:
            return True
        for entity in by_name.get(_norm(name)) or []:
            qid = str(entity.get("wikidata_qid") or "")
            if qid and qid in target_qids:
                return True
        return False

    if len(expected_names) > 1:
        missing = [name for name in expected_names if not _matches(name)]
        return {
            "verified": not missing,
            "method": "wikidata_live",
            "detail": f"đích={labels} | thiếu={missing}",
        }

    hit = _matches(expected)
    return {
        "verified": hit,
        "method": "wikidata_live",
        "detail": f"đích={labels} | kỳ vọng={expected}",
    }


def _incoming(qid: str, prop: str) -> list[str]:
    """Tìm các QID có `prop` trỏ **tới** `qid` (quan hệ ngược).

    Vì sao cần? Quan hệ "con của X" (`inverse_cha_cua`) ⇒ cần biết **ai là
    con của X** ⇒ phải tra ngược property `P40` (con) từ phía X.

    Args:
        qid: QID đích.
        prop: Property (vd. ``P40``).

    Returns:
        Danh sách QID nguồn.
    """
    # Dùng SPARQL (QLever) vì Wikidata API không có "truy về ngược" trực tiếp.
    query = (
        "SELECT ?item WHERE { ?item wdt:"
        + prop
        + " wd:"
        + qid
        + " . } LIMIT 50"
    )
    url = (
        "https://query.wikidata.org/sparql?format=json&query="
        + urllib.parse.quote(query)
    )
    payload = http_get_json(url, cache_key=f"wd_incoming::{qid}::{prop}")
    if not isinstance(payload, dict):
        return []
    out: list[str] = []
    for binding in ((payload.get("results") or {}).get("bindings") or []):
        value = (binding.get("item") or {}).get("value")
        if value:
            out.append(str(value).rsplit("/", 1)[-1])
    return out


def verify_answer_against_wikipedia(
    answer: str,
    doc_ids: list[str],
    doc_titles: dict[str, str],
    extra_titles: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Kiểm chứng **số năm** trong câu trả lời bằng Wikipedia live.

    Mọi năm trong câu trả lời phải xuất hiện trong bài Wikipedia live của
    `evidence_doc_id` ⇒ năm không tìm thấy ⇒ câu trả lời **bịa** ⇒ đánh dấu đỏ.

    ⚠️ Phase 19 — sửa **false negative**: chỉ so với `evidence_doc_id` là
    **thiếu**. Ví dụ q0031 (arm B) trả "Nguyễn Huy Tự **sinh năm 1743** …
    [9][19]" ⇒ năm 1743 nằm ở bài **Nguyễn Huy Tự** (trích dẫn KG), không
    phải bài `evidence_doc_id` (Nguyễn Huy Hổ) ⇒ bị báo "bịa" **sai**.
    ⇒ Nay so với **mọi nguồn được trích dẫn** (KG + text) **và** mọi bài
    `evidence_doc_id`.

    Args:
        answer: Câu trả lời của hệ thống.
        doc_ids: Danh sách `doc_id` bằng chứng.
        doc_titles: Map `doc_id` → tên bài.
        extra_titles: Tên bài bổ sung (từ trích dẫn KG/text).

    Returns:
        Dict kết quả.
    """
    years = _years_in(answer)
    if not years:
        return {"n_years": 0, "unsupported_years": [], "ok": True}
    titles: list[str] = []
    for doc_id in doc_ids:
        title = doc_titles.get(doc_id, "")
        if title and title not in titles:
            titles.append(title)
    for title in extra_titles or []:
        if title and title not in titles:
            titles.append(title)
    haystack = ""
    for title in titles:
        extract = wikipedia_extract(title)
        if extract:
            haystack += "\n" + extract
    if not haystack:
        return {
            "n_years": len(years),
            "unsupported_years": [],
            "ok": None,
            "detail": "không tải được Wikipedia live",
        }
    unsupported = [year for year in years if str(year) not in haystack]
    return {
        "n_years": len(years),
        "unsupported_years": unsupported,
        "ok": not unsupported,
    }


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main() -> int:
    """Điểm vào CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", default="", help="File checkpoint eval (JSONL).")
    parser.add_argument(
        "--qa-set", default="data/eval/qa_rag_250_v2.jsonl", help="Bộ câu hỏi eval."
    )
    parser.add_argument(
        "--documents",
        default="data/interim/documents_clean.jsonl",
        help="File bài đã làm sạch (map doc_id → tên bài).",
    )
    parser.add_argument(
        "--entities",
        default="data/knowledge_base/entities.jsonl",
        help="File entity (map entity → QID).",
    )
    parser.add_argument("--arms", default="A,B,B-", help="Các arm cần kiểm chứng.")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số câu (0 = tất cả).")
    parser.add_argument(
        "--questions-only",
        action="store_true",
        help="Chỉ kiểm chứng câu hỏi (không cần checkpoint).",
    )
    parser.add_argument("--out", default="", help="Ghi kết quả ra file JSON.")
    args = parser.parse_args()

    qa_path = REPO_ROOT / args.qa_set
    qa_rows = load_jsonl(qa_path)
    if args.limit:
        qa_rows = qa_rows[: args.limit]
    doc_titles = load_doc_titles(REPO_ROOT / args.documents)
    entities = load_entity_qids(REPO_ROOT / args.entities)
    by_name = entity_index_by_name(entities)

    checkpoint: dict[str, dict[str, Any]] = {}
    if args.checkpoint and not args.questions_only:
        for record in load_jsonl(REPO_ROOT / args.checkpoint):
            qid = str(record.get("qid") or "")
            if qid:
                checkpoint[qid] = record

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    report: dict[str, Any] = {
        "qa_set": str(qa_path),
        "checkpoint": args.checkpoint,
        "questions": {},
        "answers": {},
        "summary": {},
    }

    n_invalid = 0
    n_checked_q = 0
    for row in qa_rows:
        qid = str(row.get("qid") or "")
        if not qid:
            continue
        check = verify_question(row, doc_titles)
        if check.get("reason", "").startswith("không cần"):
            pass
        else:
            n_checked_q += 1
            if not check.get("valid"):
                n_invalid += 1
        if check.get("type") in {"relational", "multi_hop"}:
            check["wikidata"] = verify_relational_online(row, entities, by_name)
        report["questions"][qid] = check
        print(
            f"[Q] {qid} ({check['type']}): "
            f"{'HỢP LỆ' if check.get('valid') else 'KHÔNG HỢP LỆ — ' + str(check.get('reason'))}"
        )

    n_answers = 0
    n_unsupported = 0
    n_no_data_violations = 0
    n_contradictions = 0
    for qid, record in checkpoint.items():
        row = next((r for r in qa_rows if str(r.get("qid")) == qid), None)
        if row is None:
            continue
        doc_ids = [str(d) for d in (row.get("evidence_doc_id") or [])]
        for arm in arms:
            arm_data = record.get(arm)
            if not isinstance(arm_data, dict):
                continue
            answer = str((arm_data.get("arm") or {}).get("answer") or "")
            if not answer.strip():
                continue
            entry: dict[str, Any] = {"type": row.get("type")}
            if row.get("type") == "no_data":
                # Ngoài phạm vi ⇒ **phải** trả "không có trong dữ liệu".
                violation = not _is_not_in_data(answer)
                entry["no_data_violation"] = violation
                n_answers += 1
                if violation:
                    n_no_data_violations += 1
            elif _is_not_in_data(answer):
                entry["abstain"] = True
                n_answers += 1
            else:
                # ⚠️ Phase 19 — so năm với **mọi nguồn được trích dẫn**
                # (KG + text), không chỉ `evidence_doc_id` (xem
                # `verify_answer_against_wikipedia`).
                extra_titles = [
                    str(citation.get("title") or "")
                    for citation in (arm_data.get("arm") or {}).get("citations") or []
                    if str(citation.get("title") or "")
                ]
                verdict = verify_answer_against_wikipedia(
                    answer, doc_ids, doc_titles, extra_titles
                )
                entry.update(verdict)
                n_answers += 1
                if verdict.get("ok") is False:
                    n_unsupported += 1
            report["answers"].setdefault(qid, {})[arm] = entry

    # Số câu có mâu thuẫn với đáp án tham chiếu (D-142) — tính nếu có judge.
    for qid, record in checkpoint.items():
        for arm in arms:
            arm_data = record.get(arm)
            if not isinstance(arm_data, dict):
                continue
            judge = arm_data.get("judge") or {}
            if judge.get("contradicts_reference"):
                n_contradictions += 1

    report["summary"] = {
        "n_questions_checked": n_checked_q,
        "n_questions_invalid": n_invalid,
        "n_answers_checked": n_answers,
        "n_answers_with_unsupported_years": n_unsupported,
        "n_no_data_violations": n_no_data_violations,
        "n_contradicts_reference": n_contradictions,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print("\n=== Tổng kết ===")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if args.out:
        out_path = REPO_ROOT / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"Ghi: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

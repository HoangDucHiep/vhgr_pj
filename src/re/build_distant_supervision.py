"""Sinh cặp quan hệ Wikidata bằng distant supervision (Phase 7 — D1 phần 1).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 7.

Vì sao không viết `src/re/wikidata_client.py` mới (như `docs/09` gợi ý)
----------------------------------------------------------------------
Module `src/preprocess/wikidata_query.py` (Phase 1) **đã có đầy đủ**:
fallback 2 endpoint (QLever → WDQS), throttle, retry với exponential backoff
và **cache đĩa** theo hash truy vấn. Viết thêm một client sẽ phải sao chép
logic đó → hai nơi sửa khi WDQS lại 429. Quyết định này ghi ở
`docs/DECISIONS.md` D-058.

Vì sao QLever phải gọi theo **từng property một**
-----------------------------------------------
QLever **không** hỗ trợ `?p` là biến predicate trong `UNION` mà vẫn trả về
tên property; WDQS cũng vậy (biến predicate bị rơi khỏi kết quả). Đo được
15/11/2026: query `UNION` 13 property trả về 2.429 dòng **không có** cột
predicate → không biết dòng nào thuộc property nào.

→ Vì vậy mỗi property được hỏi riêng, mỗi lần một lô QID (`VALUES`).
Đo được: 13 property × 1.262 QID = 12.602 cặp trong 301 s (WDQS, throttle
1,4 s/lô) hoặc 171 s (QLever, throttle 0,4 s/lô).

Vì sao chunk theo 9 triều đại
---------------------------
`docs/09` yêu cầu "Chunk theo 9 triều đại (mỗi truy vấn 1 triều đại) để tránh
timeout". Corpus 2.441 bài được gắn nhãn triều đại qua
`data/interim/category_members.json` (category ``nha <triều>`` /
``nhan vat thoi <triều>``). Chia theo triều đại giúp một triều đại timeout
không chặn cả phase.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger
from src.common.normalize import normalize_name
from src.preprocess.wikidata_query import run_query
from src.re.wikidata_relations import RelationMap, load_relation_map

logger = get_logger(__name__)

#: Prefix SPARQL tường minh — QLever không khai báo sẵn.
PREFIXES = """PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
"""

#: Ngưỡng throttle giữa hai request (giây).
DEFAULT_MIN_INTERVAL_S = 0.4

#: Số QID trong một lô truy vấn.
DEFAULT_BATCH_SIZE = 200


def build_label_query(qids: list[str]) -> str:
    """Sinh query lấy nhãn tiếng Việt (fallback tiếng Anh) cho một lô QID.

    Args:
        qids: Danh sách QID.

    Returns:
        Chuỗi SPARQL (đã kèm prefix tường minh).
    """
    values = " ".join(f"wd:{qid}" for qid in qids)
    return f"""{PREFIXES}
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?item ?label WHERE {{
  VALUES ?item {{ {values} }}
  ?item rdfs:label ?label .
  FILTER(LANG(?label) IN ("vi", "en"))
}}
"""


def fetch_labels(
    qids: set[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    use_cache: bool = True,
) -> dict[str, list[str]]:
    """Lấy nhãn (tên) của một tập QID.

    Nhãn là **bắt buộc** cho grounding theo tên: object của một cặp Wikidata
    thường chưa có `entity_id` trong corpus (đo 15/11/2026: chỉ 3.731/12.602
    cặp có object là entity trong corpus) — nếu không có nhãn thì mất
    gần 2/3 mẫu.

    Args:
        qids: Tập QID cần nhãn.
        batch_size: Số QID trong một lô.
        min_interval_s: Nghỉ tối thiểu giữa hai request (giây).
        use_cache: Dùng cache đĩa.

    Returns:
        Map ``QID`` → danh sách nhãn (có thể >1 nhãn nếu có cả vi và en).
    """
    labels: dict[str, list[str]] = defaultdict(list)
    all_qids = sorted(qids)
    last_ts = 0.0

    for start in range(0, len(all_qids), batch_size):
        batch = all_qids[start : start + batch_size]
        wait = min_interval_s - (time.monotonic() - last_ts)
        if wait > 0:
            time.sleep(wait)
        query = build_label_query(batch)
        try:
            rows = run_query(query, use_cache=use_cache)
        except RuntimeError as exc:
            logger.error("SPARQL lấy nhãn thất bại: %s — bỏ qua lô này", exc)
            continue
        last_ts = time.monotonic()
        for row in rows:
            item = _clean_qid(_binding_value(row, "item"))
            label = _clean_label(_binding_value(row, "label"))
            if not item or not label:
                continue
            if label not in labels[item]:
                labels[item].append(label)
    logger.info("Lấy nhãn cho %d/%d QID", len(labels), len(all_qids))
    return dict(labels)


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc JSONL theo luồng.

    Args:
        path: Đường dẫn file JSONL.

    Yields:
        Từng record dict.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def build_property_query(qids: list[str], prop: str) -> str:
    """Sinh query lấy tất cả object của một property cho một lô QID.

    Args:
        qids: Danh sách QID chủ thể.
        prop: Tên property, ví dụ ``"P22"``.

    Returns:
        Chuỗi SPARQL (đã kèm prefix tường minh).
    """
    values = " ".join(f"wd:{qid}" for qid in qids)
    return f"""{PREFIXES}
SELECT ?s ?o WHERE {{
  VALUES ?s {{ {values} }}
  ?s wdt:{prop} ?o .
}}
"""


def _clean_qid(raw: str) -> str:
    """Chuẩn hoá giá trị trả về thành QID.

    WDQS trả URI thuần (``http://www.wikidata.org/entity/Q42``); QLever trả
    URI bọc trong ``<...>``; giá trị literal có thể kèm kiểu dữ liệu
    (``"1753-01-01T00:00:00Z"^^<http://...>``).

    Args:
        raw: Giá trị thô từ SPARQL.

    Returns:
        QID hoặc chuỗi rỗng.
    """
    value = (raw or "").strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    if '"' in value:
        value = value.split('"')[1] if value.count('"') >= 2 else value
    if value.startswith("http://www.wikidata.org/entity/"):
        return value.rsplit("/", 1)[-1]
    return value


def _is_qid(value: str) -> bool:
    """Kiểm tra chuỗi có phải QID không.

    Args:
        value: Chuỗi cần kiểm tra.

    Returns:
        ``True`` nếu khớp mẫu ``Q<digits>``.
    """
    return value.startswith("Q") and value[1:].isdigit()


def _clean_label(raw: str) -> str:
    """Chuẩn hoá nhãn literal của SPARQL về tên thuần.

    QLever trả literal dạng ``"Động Hoa Lư"@vi``; WDQS trả
    ``{"value": "Động Hoa Lư", "xml:lang": "vi"}`` (đã rút qua
    `_binding_value` nên chỉ còn chuỗi).

    Args:
        raw: Giá trị thô.

    Returns:
        Tên đã bỏ chú thích literal.
    """
    value = (raw or "").strip()
    if value.startswith('"') and '"' in value[1:]:
        value = value[1 : value.index('"', 1)]
    if "@" in value:
        value = value.rsplit("@", 1)[0]
    return value.strip()


def _extract_pairs(
    rows: list[dict[str, Any]],
) -> list[tuple[str, str]]:
    """Chuẩn hoá các dòng SPARQL thành cặp ``(subject_qid, object)``.

    `run_query` trả binding dạng ``{"s": {"type": ..., "value": ...}}`` (đã
    chuẩn hoá cả QLever và WDQS về một dạng). Hàm này rút ra ``value`` và
    bỏ các dòng thiếu trường.

    Args:
        rows: Danh sách binding từ `run_query`.

    Returns:
        Danh sách cặp; object giữ nguyên dạng (QID hoặc literal).
    """
    pairs: list[tuple[str, str]] = []
    for row in rows:
        subject = _clean_qid(_binding_value(row, "s"))
        obj = _clean_qid(_binding_value(row, "o"))
        if not subject or not obj:
            continue
        pairs.append((subject, obj))
    return pairs


def _binding_value(row: dict[str, Any], key: str) -> str:
    """Rút giá trị của một binding.

    Binding có thể ở dạng dict ``{"value": ...}`` (WDQS/QLever sau khi
    `run_query` chuẩn hoá) hoặc chuỗi thô.

    Args:
        row: Binding.
        key: Tên biến, ví dụ ``"s"``.

    Returns:
        Chuỗi giá trị (rỗng nếu không có).
    """
    value = row.get(key)
    if value is None:
        value = row.get(f"?{key}")
    if value is None:
        return ""
    if isinstance(value, dict):
        return str(value.get("value") or "")
    return str(value)


def collect_corpus_qids(
    infobox_entities_path: str | Path,
    documents_path: str | Path,
) -> dict[str, list[str]]:
    """Thu thập QID của các entity có mặt trong corpus.

    Nguồn A — `infobox_entities.jsonl` (Phase 3): `wikidata_qid` của entity.
    Nguồn B — `documents.jsonl` (Phase 2): `wikibase_item` của bài.

    QID trùng nhau chỉ giữ một lần. QID của bài mà entity infobox đã có vẫn
    được giữ (dùng chung QID) — không mất thông tin gì.

    Args:
        infobox_entities_path: Đường dẫn `infobox_entities.jsonl`.
        documents_path: Đường dẫn `documents.jsonl`.

    Returns:
        Set QID (dùng `set` — hàm trả về set để dễ kiểm tra).
    """
    qids: set[str] = set()
    for entity in iter_jsonl(infobox_entities_path):
        qid = entity.get("wikidata_qid")
        if qid:
            qids.add(str(qid))
    for doc in iter_jsonl(documents_path):
        qid = doc.get("wikibase_item")
        if qid:
            qids.add(str(qid))
    logger.info("Corpus: %d QID duy nhất", len(qids))
    return qids


def load_dynasty_buckets(
    category_members_path: str | Path,
    dynasty_names: list[str],
) -> dict[str, set[int]]:
    """Gom `page_id` của corpus theo 9 triều đại.

    Dùng `data/interim/category_members.json` — map ``category → [page_id]``.
    Category dùng để nhận diện triều đại: ``nha <tên>`` và ``nhan vat thoi
    <tên>`` (viết không dấu, lowercase).

    Args:
        category_members_path: Đường dẫn `category_members.json`.
        dynasty_names: Danh sách tên triều đại (không dấu, lowercase), lấy từ
            khóa `dynasties` trong `configs/default.yaml`.

    Returns:
        Map ``tên triều đại → set page_id``. Triều đại không có bài nào sẽ
        không có trong dict.
    """
    path = Path(category_members_path)
    if not path.exists():
        logger.warning("Không có %s — bỏ qua chia theo triều đại", path)
        return {}

    with path.open("r", encoding="utf-8") as handle:
        members = json.load(handle)

    buckets: dict[str, set[int]] = {name: set() for name in dynasty_names}
    for category, pages in members.items():
        cat_norm = normalize_name(category)
        for name in dynasty_names:
            if cat_norm == name or cat_norm == f"nhan vat thoi {name}":
                buckets[name].update(int(p) for p in pages)
    total = sum(len(v) for v in buckets.values())
    logger.info(
        "Chia triều đại: %d triều đại, %d lượt bài (page_id)",
        len([v for v in buckets.values() if v]),
        total,
    )
    return buckets


def build_wikidata_pairs(
    qids: set[str],
    relation_map: RelationMap,
    *,
    extended: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    chunks: list[tuple[str, set[str]]] | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Truy vấn Wikidata và sinh danh sách cặp quan hệ.

    Args:
        qids: Tập QID chủ thể trong corpus.
        relation_map: Bảng mapping property → quan hệ.
        extended: Có truy vấn bộ property mở rộng không.
        batch_size: Số QID trong một lô.
        min_interval_s: Nghỉ tối thiểu giữa hai request (giây).
        chunks: Danh sách ``(nhãn, tập QID)`` để chia theo triều đại. Nếu
            ``None`` thì truy vấn toàn bộ QID trong một lần.
        use_cache: Dùng cache đĩa (Gate: chạy lại không gọi mạng).

    Returns:
        Danh sách record: ``{subject_qid, property, relation, direction,
        object_qid, object_label}``.
    """
    props = relation_map.active_properties(extended=extended)
    all_qids = sorted(qids)
    if chunks:
        # Giữ QID không thuộc triều đại nào vào một lô riêng cuối cùng.
        covered: set[str] = set()
        for _label, chunk_qids in chunks:
            covered |= chunk_qids
        leftovers = [q for q in all_qids if q not in covered]
        work_chunks: list[tuple[str, list[str]]] = [
            (label, sorted(chunk_qids)) for label, chunk_qids in chunks
        ]
        if leftovers:
            work_chunks.append(("__khong_trieu_dai__", leftovers))
    else:
        work_chunks = [("__all__", all_qids)]

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    last_ts = 0.0
    object_qids: set[str] = set()

    for label, chunk_qids in work_chunks:
        if not chunk_qids:
            continue
        logger.info("Chunk '%s': %d QID", label, len(chunk_qids))
        for prop in props:
            spec = relation_map.get(prop, extended=extended)
            if spec is None:
                continue
            for start in range(0, len(chunk_qids), batch_size):
                batch = chunk_qids[start : start + batch_size]
                wait = min_interval_s - (time.monotonic() - last_ts)
                if wait > 0:
                    time.sleep(wait)
                query = build_property_query(batch, prop)
                try:
                    rows = run_query(query, use_cache=use_cache)
                except RuntimeError as exc:
                    logger.error(
                        "SPARQL thất bại (chunk=%s, %s): %s — bỏ qua lô này",
                        label,
                        prop,
                        exc,
                    )
                    continue
                last_ts = time.monotonic()
                for subject, obj in _extract_pairs(rows):
                    key = (subject, prop, obj)
                    if key in seen:
                        continue
                    seen.add(key)
                    if _is_qid(obj):
                        object_qids.add(obj)
                    records.append(
                        {
                            "subject_qid": subject,
                            "property": prop,
                            "relation": spec.relation,
                            "direction": spec.direction,
                            "object_qid": obj,
                            "object_is_entity": _is_qid(obj),
                        }
                    )
        logger.info(
            "Chunk '%s' xong — tổng %d cặp", label, len(records)
        )
    return records, object_qids


def main() -> None:
    """Điểm vào CLI.

    Raises:
        SystemExit: Nếu tham số không hợp lệ.
    """
    parser = argparse.ArgumentParser(
        description="Sinh cặp quan hệ Wikidata cho tập huấn luyện RE (Phase 7)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default=None, help="Đường dẫn output JSONL.")
    parser.add_argument(
        "--extended",
        action="store_true",
        help="Truy vấn thêm bộ property mở rộng (chỉ +59 mẫu grounded).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Không dùng cache đĩa (mặc định CÓ — Gate yêu cầu chạy lại không gọi mạng).",
    )
    args = parser.parse_args()

    config = load_default_config()
    interim = resolve_path(config["paths"]["interim_dir"])
    re_cfg = config.get("re") or {}

    out_path = Path(args.out) if args.out else resolve_path(
        re_cfg.get("pairs_path", "data/interim/wikidata_pairs.jsonl")
    )

    relation_map = load_relation_map(re_cfg.get("relations_config"))
    qids = collect_corpus_qids(
        interim / "infobox_entities.jsonl", interim / "documents.jsonl"
    )

    buckets: dict[str, set[int]] = {}
    chunks: list[tuple[str, set[str]]] = []
    if re_cfg.get("chunk_by_dynasty", True):
        buckets = load_dynasty_buckets(
            interim / "category_members.json",
            list((config.get("dynasties") or {}).keys()),
        )
        page_to_qid = {
            int(doc.get("page_id") or 0): str(doc.get("wikibase_item") or "")
            for doc in iter_jsonl(interim / "documents.jsonl")
            if doc.get("wikibase_item")
        }
        for name, pages in buckets.items():
            chunk_qids = {page_to_qid[p] for p in pages if p in page_to_qid}
            chunk_qids &= qids
            if chunk_qids:
                chunks.append((name, chunk_qids))

    records, object_qids = build_wikidata_pairs(
        qids,
        relation_map,
        extended=args.extended,
        batch_size=int(re_cfg.get("sparql_batch_size", DEFAULT_BATCH_SIZE)),
        min_interval_s=float(
            re_cfg.get("sparql_min_interval_s", DEFAULT_MIN_INTERVAL_S)
        ),
        chunks=chunks,
        use_cache=not args.no_cache,
    )

    # Nhãn (tên) của object — bắt buộc cho grounding theo tên.
    labels = fetch_labels(
        object_qids,
        batch_size=int(re_cfg.get("sparql_batch_size", DEFAULT_BATCH_SIZE)),
        min_interval_s=float(
            re_cfg.get("sparql_min_interval_s", DEFAULT_MIN_INTERVAL_S)
        ),
        use_cache=not args.no_cache,
    )
    for record in records:
        record["object_labels"] = labels.get(record["object_qid"], [])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    by_prop: dict[str, int] = defaultdict(int)
    for record in records:
        by_prop[record["property"]] += 1
    logger.info(
        "Ghi %d cặp quan hệ → %s (%d property)", len(records), out_path, len(by_prop)
    )
    for prop, count in sorted(by_prop.items()):
        logger.info("  %s: %d", prop, count)


if __name__ == "__main__":
    main()

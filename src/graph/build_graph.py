"""Phase 10 — Bước 1: dựng đồ thị KG từ entity + triple.

Đầu ra: `data/knowledge_base/graph.jsonl` gồm 2 phần:
- `{"type": "nodes", "items": [...]}` — node theo 7 label của schema.
- `{"type": "edges", "items": [...]}` — cạnh theo 18 quan hệ, **luôn có**
  `confidence`, `method`, `evidence_sentence`, `source_url`, `doc_id`,
  `doc_title`, `sentence_id`, `alt_evidence`, `start_year`, `end_year`.

Quy tắc:
- Node `Year` (`entity_id = year_<n>`) cho quan hệ `sinh_nam` / `mat_nam`.
- Chuẩn hóa orientation quan hệ đối xứng (`anh_em_cua`, `tham_gia_tran`).
- Bỏ edge có subject/object không có trong node set → ghi
  `reports/orphan_edges.log`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger
from src.common.normalize import normalize_name
from src.common.schemas import RELATION_TYPES, normalize_orientation

logger = get_logger("src.graph.build_graph")

#: Map `type` của entity → label Neo4j.
TYPE_TO_LABEL = {
    "person": "Person",
    "place": "Place",
    "event": "Event",
    "dynasty": "Dynasty",
    "organization": "Organization",
    "title": "Title",
    "article": "Article",
    "unknown": "Entity",
}

#: Thuộc tính node lấy từ `props` của entity (nếu có).
PROP_FIELDS = (
    "birth_year",
    "death_year",
    "reign_start",
    "reign_end",
    "temple_name",
    "posthumous_name",
    "reign_title",
    "gender",
    "birth_place",
    "death_place",
    "dynasty",
    "latitude",
    "longitude",
)

#: Khoảng năm hợp lệ của dữ liệu lịch sử Việt Nam (dương lịch).
MIN_PLAUSIBLE_YEAR = 500
MAX_PLAUSIBLE_YEAR = 2000


def _alias_names(aliases: Any) -> list[str]:
    """Trích danh sách tên alias dạng `list[str]` từ `aliases` (list-of-dict).

    `aliases` gốc là list-of-dict ⇒ Neo4j lưu thành **JSON string** ⇒ không
    truy vấn được bằng `any(a IN n.aliases ...)`. Thêm `alias_names` (list of
    string — kiểu Neo4j chấp nhận) để tìm kiếm theo alias chạy được.

    Args:
        aliases: Giá trị `aliases` gốc.

    Returns:
        Danh sách tên alias (đã loại trùng, giữ thứ tự).
    """
    names: list[str] = []
    seen: set[str] = set()
    for item in aliases or []:
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = str(item.get("alias") or "")
        else:
            continue
        text = text.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        names.append(text)
    return names


def _valid_year_pair(
    birth: Any,
    death: Any,
) -> tuple[Any, Any]:
    """Lọc cặp năm sinh/mất để tránh mâu thuẫn `birth_year > death_year`.

    Năm âm lịch (vd Kinh Dương Vương: sinh 2919 âm / mất 2792 âm) không thể
    quy đổi sang dương lịch ở đây (D-007) ⇒ quy tắc là **loại bỏ** cả hai
    năm thay vì "convert sai" (xem `docs/10-nhat-ky/phase-10.md` §6).

    Args:
        birth: Năm sinh thô.
        death: Năm mất thô.

    Returns:
        Tuple `(birth_year, death_year)` đã lọc.
    """
    birth_value = birth if isinstance(birth, int) and birth > 0 else None
    death_value = death if isinstance(death, int) and death > 0 else None
    if birth_value and death_value and birth_value > death_value:
        return None, None
    return birth_value, death_value


def _name_from_entity_id(entity_id: str) -> str:
    """Suy ra tên hiển thị từ `entity_id` (`ent_<slug>_<hash8>`).

    Args:
        entity_id: Id của entity.

    Returns:
        Tên hiển thị (slug đổi `_` → khoảng trắng).
    """
    parts = entity_id.split("_")
    if len(parts) >= 3 and parts[0] == "ent":
        # Bỏ hash8 ở cuối (8 ký tự hex) và tiền tố `ent`.
        slug = "_".join(parts[1:-1])
        return slug.replace("_", " ").strip()
    return entity_id


def _wiki_url(name: str) -> str:
    """Dựng URL bài Wikipedia tiếng Việt từ tên.

    Args:
        name: Tên hiển thị.

    Returns:
        URL bài Wikipedia.
    """
    slug = quote(name.replace(" ", "_"), safe="/:(),!'.\u2013\u2014-")
    return f"https://vi.wikipedia.org/wiki/{slug}"


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Đọc JSONL.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng dict.
    """
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_nodes(entities: list[dict[str, Any]]) -> tuple[list[dict], set[str]]:
    """Dựng danh sách node.

    Args:
        entities: Danh sách entity từ Phase 9.

    Returns:
        Tuple `(nodes, node_ids)`.
    """
    nodes: list[dict[str, Any]] = []
    node_ids: set[str] = set()
    for entity in entities:
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id:
            continue
        entity_type = str(entity.get("type") or "unknown")
        label = TYPE_TO_LABEL.get(entity_type, "Entity")
        # Thuộc tính chi tiết nằm trong `entity["props"]` (Phase 3), KHÔNG nằm
        # ở top-level — đọc sai chỗ khiến `reign_start`/`gender`/`description`
        # luôn NULL trong Neo4j ⇒ câu hỏi "ai là vua năm 1855?" không bao giờ
        # có kết quả.
        entity_props = entity.get("props") or {}
        if not isinstance(entity_props, dict):
            entity_props = {}
        props: dict[str, Any] = {
            "entity_id": entity_id,
            "name": entity.get("name"),
            "name_normalized": entity.get("name_normalized"),
            "type": entity_type,
            "aliases": entity.get("aliases") or [],
            "alias_names": _alias_names(entity.get("aliases")),
            "aliases_normalized": entity.get("aliases_normalized") or [],
            "description": entity.get("description") or entity_props.get("description"),
            "wiki_url": entity.get("wiki_url") or _wiki_url(
                str(entity.get("name") or entity_id)
            ),
            "wikidata_qid": entity.get("wikidata_qid"),
            "verified": bool(entity.get("verified")),
            "mention_count": int(entity.get("mention_count") or 0),
            "source_method": entity.get("source_method"),
        }
        for field in PROP_FIELDS:
            # Ưu tiên giá trị top-level (đã chuẩn hóa năm), fallback `props`.
            value = entity.get(field)
            if value is None:
                value = entity_props.get(field)
            if value is None:
                props.pop(field, None)
            else:
                props[field] = value
        # Năm sinh/mất phải nhất quán: `props` (nguồn thô từ Phase 3) có thể
        # chứa **năm âm lịch** ⇒ `birth_year > death_year` ⇒ Gate Phase 10 FAIL.
        # Lọc ở đây (giống `src/link/build_aliases.py::_valid_years`).
        if "birth_year" in props or "death_year" in props:
            birth, death = _valid_year_pair(
                props.get("birth_year"), props.get("death_year")
            )
            if birth is None:
                props.pop("birth_year", None)
            else:
                props["birth_year"] = birth
            if death is None:
                props.pop("death_year", None)
            else:
                props["death_year"] = death
        nodes.append({
            "entity_id": entity_id,
            "label": label,
            "props": props,
        })
        node_ids.add(entity_id)
    return _dedupe_nodes(nodes), node_ids


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gộp các node trùng `entity_id`.

    `entities.jsonl` (Phase 9) có thể sinh 2 entity **cùng `entity_id`** khi
    2 tên khác nhau chuẩn hóa ra cùng `name_normalized` (vd "Nguyễn Du" và
    "Nguyễn Dữ" → `nguyen du`). Nếu không gộp, `graph.jsonl` có node trùng
    ⇒ `MERGE` ở Neo4j chỉ giữ 1 ⇒ số node trong DB lệch artifact.

    Args:
        nodes: Danh sách node thô.

    Returns:
        Danh sách node đã gộp (giữ node đầu tiên, bù các property NULL).
    """
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for node in nodes:
        entity_id = str(node.get("entity_id") or "")
        if entity_id not in merged:
            merged[entity_id] = node
            order.append(entity_id)
            continue
        current = merged[entity_id]
        for key, value in (node.get("props") or {}).items():
            if value in (None, "", [], {}):
                continue
            if current["props"].get(key) in (None, "", [], {}):
                current["props"][key] = value
        # Ưu tiên `name` dài hơn (tên đầy đủ hơn).
        if len(str(node["props"].get("name") or "")) > len(
            str(current["props"].get("name") or "")
        ):
            current["props"]["name"] = node["props"].get("name")
    return [merged[entity_id] for entity_id in order]


def add_year_nodes(
    nodes: list[dict[str, Any]],
    node_ids: set[str],
    triples: list[dict[str, Any]],
) -> None:
    """Thêm node `Year` cho `sinh_nam` / `mat_nam`.

    Args:
        nodes: Danh sách node (được cập nhật tại chỗ).
        node_ids: Set `entity_id` (được cập nhật tại chỗ).
        triples: Danh sách triple.
    """
    created = 0
    for triple in triples:
        relation = str(triple.get("relation") or "")
        if relation not in {"sinh_nam", "mat_nam"}:
            continue
        for role in ("subject", "object"):
            value = str(triple.get(role) or "")
            if not value.startswith("year_"):
                continue
            if value in node_ids:
                continue
            year = value.split("_", 1)[1]
            nodes.append({
                "entity_id": value,
                "label": "Year",
                "props": {
                    "entity_id": value,
                    "name": year,
                    "name_normalized": year,
                    # Gate Phase 10: mọi node đều phải có `wiki_url`.
                    "wiki_url": f"https://vi.wikipedia.org/wiki/{year}",
                    "type": "year",
                    "value": int(year) if year.isdigit() else year,
                    "aliases": [],
                    "aliases_normalized": [],
                    "wikidata_qid": None,
                    "verified": True,
                    "mention_count": 0,
                    "source_method": "derived",
                },
            })
            node_ids.add(value)
            created += 1
    if created:
        logger.info("Thêm %d node Year", created)


def build_edges(
    triples: list[dict[str, Any]],
    node_ids: set[str],
) -> tuple[list[dict], list[dict]]:
    """Dựng danh sách cạnh, loại edge có node không tồn tại.

    Args:
        triples: Danh sách triple đã chuẩn hóa.
        node_ids: Set `entity_id` hợp lệ.

    Returns:
        Tuple `(edges, orphans)`.
    """
    edges: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    created_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    for triple in triples:
        relation = str(triple.get("relation") or "")
        subject = str(triple.get("subject") or "")
        object_ = str(triple.get("object") or "")
        if relation not in RELATION_TYPES:
            orphans.append({"reason": "relation_outside_catalog", **triple})
            continue
        if subject not in node_ids or object_ not in node_ids:
            orphans.append({"reason": "missing_node", **triple})
            continue
        subject, object_, relation = normalize_orientation(subject, object_, relation)
        edges.append({
            "source": subject,
            "target": object_,
            "type": relation,
            "props": {
                "confidence": float(triple.get("confidence") or 0.0),
                "method": triple.get("method"),
                "evidence_sentence": triple.get("evidence_sentence"),
                "source_url": triple.get("source_url"),
                "doc_id": triple.get("doc_id"),
                "doc_title": triple.get("doc_title"),
                "sentence_id": triple.get("sentence_id"),
                "alt_evidence": triple.get("alt_evidence") or [],
                "start_year": triple.get("start_year"),
                "end_year": triple.get("end_year"),
                "created_at": created_at,
            },
        })
    return edges, orphans


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Dựng đồ thị KG (Phase 10 — bước 1)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--entities", default="data/knowledge_base/entities.jsonl",
    )
    parser.add_argument(
        "--triples", default="data/interim/triples_merged.jsonl",
    )
    parser.add_argument(
        "--out", default="data/knowledge_base/graph.jsonl",
    )
    parser.add_argument(
        "--orphan-log", default="reports/orphan_edges.log",
    )
    parser.add_argument(
        "--add-missing-entities", action="store_true",
        help="Tự tạo node cho entity chỉ xuất hiện trong triple (nhãn Entity).",
    )
    parser.add_argument(
        "--recovered-entities",
        default="data/knowledge_base/entities_recovered.jsonl",
        help="Entity khôi phục tên/kiểu cho entity chỉ có trong triple (D-085). "
             "File không tồn tại ⇒ bỏ qua.",
    )
    args = parser.parse_args()

    config = load_default_config()
    entities = list(iter_jsonl(resolve_path(args.entities)))
    triples = list(iter_jsonl(resolve_path(args.triples)))
    logger.info("Nạp %d entity · %d triple", len(entities), len(triples))

    # D-085: entity chỉ xuất hiện trong triple đã được khôi phục tên + kiểu
    # (nếu `src/graph/recover_entities.py` đã chạy) ⇒ nối vào registry để
    # node có **tên có dấu** và **label đúng** thay vì `Entity` chung chung.
    recovered_path = Path(args.recovered_entities)
    if not recovered_path.is_absolute():
        recovered_path = Path.cwd() / recovered_path
    n_recovered = 0
    if recovered_path.exists():
        known_ids = {str(e.get("entity_id") or "") for e in entities}
        for record in iter_jsonl(recovered_path):
            entity_id = str(record.get("entity_id") or "")
            if not entity_id or entity_id in known_ids:
                continue
            entities.append(record)
            known_ids.add(entity_id)
            n_recovered += 1
        logger.info(
            "Nối %d entity khôi phục từ %s", n_recovered, recovered_path.name
        )

    nodes, node_ids = build_nodes(entities)
    add_year_nodes(nodes, node_ids, triples)

    if args.add_missing_entities:
        n_added = 0
        for triple in triples:
            for role in ("subject", "object"):
                value = str(triple.get("object") or "") if role == "object" else str(
                    triple.get("subject") or ""
                )
                if not value or value in node_ids:
                    continue
                if value.startswith("year_"):
                    continue
                name = _name_from_entity_id(value)
                nodes.append({
                    "entity_id": value,
                    "label": "Entity",
                    "props": {
                        "entity_id": value,
                        "name": name,
                        "name_normalized": normalize_name(name),
                        "type": "unknown",
                        "aliases": [],
                        "aliases_normalized": [],
                        # Gate Phase 10: 0 node thiếu `wiki_url` ⇒ dựng URL
                        # Wikipedia từ slug trong `entity_id`.
                        "wiki_url": _wiki_url(name),
                        "wikidata_qid": None,
                        "verified": False,
                        "mention_count": 0,
                        "source_method": "triple",
                    },
                })
                node_ids.add(value)
                n_added += 1
        if n_added:
            logger.info("Thêm %d node cho entity chỉ có trong triple", n_added)

    edges, orphans = build_edges(triples, node_ids)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"type": "nodes", "items": nodes}, ensure_ascii=False) + "\n")
        handle.write(json.dumps({"type": "edges", "items": edges}, ensure_ascii=False) + "\n")
    logger.info("Ghi %d node · %d edge → %s", len(nodes), len(edges), out_path)

    orphan_path = Path(args.orphan_log)
    if not orphan_path.is_absolute():
        orphan_path = Path.cwd() / orphan_path
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    with orphan_path.open("w", encoding="utf-8") as handle:
        for orphan in orphans:
            handle.write(json.dumps(orphan, ensure_ascii=False) + "\n")
    logger.info("Ghi %d edge orphan → %s", len(orphans), orphan_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Phase 9 — Bước 1: thu thập alias cho mỗi entity.

Nguồn alias (theo `docs/09-ke-hoach-thuc-thien.md` §Phase 9):

1. **Infobox** — trường alias đã map trong `configs/infobox_mapping.yaml`
   (`mieu hieu`, `thuy hieu`, `nien hieu`, `tu`, `ten khac`, `bi danh`...) cộng
   các **thuộc tính node** dạng tên: `temple_name`, `posthumous_name`,
   `reign_title`, `courtesy_name`.
2. **Wikidata** — `skos:altLabel` (tiếng Việt), `P742` (tên húy), `P1449`
   (miếu hiệu), `P1709` (tôn hiệu), `P1813` (tên gọi khác) — truy vấn qua
   `src/preprocess/wikidata_query.py` (có cache đĩa, idempotent).
3. **Hyperlink trong corpus** — các bài Wikipedia khác trỏ tới entity hiện tại
   bằng phần chữ hiển thị khác tên chính.

Mỗi alias mang `type` để biết nó là loại tên nào (temple/posthumous/era/
courtesy/other) — dùng cho Gate "≥ 95% entity PERSON có ≥ 2 alias".

Đầu ra:
- `data/knowledge_base/entities.jsonl` — entity + alias + QID (output contract
  của Phase 9).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from urllib.parse import quote
from pathlib import Path
from typing import Any, Iterator

from src.common.config import load_default_config, resolve_path
from src.common.ids import make_entity_id
from src.common.logger import get_logger
from src.common.normalize import normalize_name

logger = get_logger("src.link.build_aliases")

#: Thuộc tính node của Phase 3 chứa **tên** (không phải số).
NAME_PROP_TO_ALIAS_TYPE = {
    "temple_name": "temple",
    "posthumous_name": "posthumous",
    "reign_title": "era",
    "courtesy_name": "courtesy",
}

#: Property Wikidata chứa alias (→ loại alias tương ứng).
WIKIDATA_ALIAS_PROPERTIES = {
    "P742": "birth",
    "P1449": "temple",
    "P1709": "era",
    "P1813": "other",
    "P1477": "birth",
}

#: Loại bỏ alias quá dài / rỗng.
MAX_ALIAS_LEN = 120


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Đọc file JSONL, bỏ qua dòng rỗng.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng dict của mỗi dòng.
    """
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _clean_alias(text: Any) -> str:
    """Chuẩn hóa một chuỗi alias thành dạng dùng được.

    Args:
        text: Giá trị thô.

    Returns:
        Chuỗi đã rút gọn khoảng trắng, hoặc ``""`` nếu không hợp lệ.
    """
    if not isinstance(text, str):
        return ""
    cleaned = " ".join(text.split())
    if not cleaned or len(cleaned) > MAX_ALIAS_LEN:
        return ""
    # Bỏ dấu ngoặc/ngoặc kép thừa — nhưng chỉ khi ngoặc đóng "cân" (vd
    # "Thái Tổ (太祖)" → "Thái Tổ (太祖)"; "Thái Tổ (太祖" → "Thái Tổ (太祖").
    cleaned = cleaned.strip("“”\"'{}|")
    if cleaned.count("(") == cleaned.count(")"):
        # Chỉ bỏ ngoặc bao **ngoài cùng** ("(Thái Tổ)" → "Thái Tổ"); ngoặc
        # trong nội dung giữ nguyên ("Thái Tổ (太祖)" → "Thái Tổ (太祖)").
        while cleaned.startswith("(") and cleaned.endswith(")") and len(cleaned) > 2:
            inner = cleaned[1:-1]
            if inner.count("(") != inner.count(")"):
                break
            cleaned = inner.strip()
    else:
        # Ngoặc mở không đóng → bỏ nốt nhóm ngoặc lơ lửng.
        cleaned = re.sub(r"\s*\([^)]*$", "", cleaned).strip()
    return cleaned.strip()


def _valid_years(birth: Any, death: Any) -> tuple[Any, Any]:
    """Lọc năm sinh/mất hợp lệ.

    Ngày âm lịch có thể ra năm âm (vd "Kinh Dương Vương": sinh 2919 âm,
    mất 2792 âm) → gây mâu thuẫn `birth_year > death_year`. Quy tắc:
    - năm âm ⇒ bỏ (không chuyển đổi lịch âm→dương ở đây);
    - `birth_year > death_year` ⇒ bỏ cả hai.

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


class AliasCollector:
    """ Gom alias theo `entity_id`.

    Attributes:
        by_entity: Dict `entity_id` → list alias (`{"alias", "type"}`).
    """

    def __init__(self) -> None:
        """Khởi tạo bộ gom rỗng."""
        self.by_entity: dict[str, list[dict[str, str]]] = defaultdict(list)
        self._seen: dict[str, set[tuple[str, str]]] = defaultdict(set)

    def add(self, entity_id: str, alias: str, alias_type: str) -> bool:
        """Thêm một alias cho entity.

        Args:
            entity_id: ID entity.
            alias: Chuỗi alias (đã làm sạch).
            alias_type: Loại alias.

        Returns:
            ``True`` nếu alias mới (chưa tồn tại cho entity này).
        """
        if not entity_id or not alias:
            return False
        key = (alias, alias_type)
        if key in self._seen[entity_id]:
            return False
        self._seen[entity_id].add(key)
        self.by_entity[entity_id].append({"alias": alias, "type": alias_type})
        return True

    def add_normalized_variants(self, entity_id: str, alias: str, alias_type: str) -> bool:
        """Thêm alias kèm biến thể bỏ dấu (nếu khác nhau).

        Args:
            entity_id: ID entity.
            alias: Chuỗi alias.
            alias_type: Loại alias.

        Returns:
            ``True`` nếu có ít nhất một alias mới được thêm.
        """
        added = self.add(entity_id, alias, alias_type)
        stripped = normalize_name(alias)
        # Biến thể bỏ dấu chỉ hữu ích khi khác chuỗi gốc (vd "Lê Lợi" →
        # "Le Loi") — giữ nguyên dấu ở tên hiển thị.
        if stripped and stripped != alias:
            added = self.add(entity_id, stripped, f"{alias_type}_nodiacritic") or added
        return added


def collect_from_infobox(
    entities_path: Path,
    collector: AliasCollector,
) -> int:
    """Thu alias từ `infobox_entities.jsonl`.

    Args:
        entities_path: Đường dẫn artifact Phase 3.
        collector: Bộ gom alias.

    Returns:
        Số entity đã đọc.
    """
    n = 0
    for entity in iter_jsonl(entities_path):
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id:
            continue
        n += 1
        for alias in entity.get("aliases") or []:
            name = alias.get("alias") if isinstance(alias, dict) else alias
            alias_type = (
                str(alias.get("type") or "other") if isinstance(alias, dict) else "other"
            )
            cleaned = _clean_alias(name)
            if cleaned:
                collector.add_normalized_variants(entity_id, cleaned, alias_type)
        props = entity.get("props") or {}
        if isinstance(props, dict):
            for prop, alias_type in NAME_PROP_TO_ALIAS_TYPE.items():
                cleaned = _clean_alias(props.get(prop))
                if cleaned:
                    collector.add_normalized_variants(entity_id, cleaned, alias_type)
    return n


def collect_from_documents(
    documents_path: Path,
    title_to_qid: dict[str, str],
    qid_to_entity: dict[str, str],
    collector: AliasCollector,
) -> int:
    """Thu alias từ hyperlink trong corpus.

    Mỗi liên kết nội bộ ``[[đích|text hiển thị]]`` trỏ tới một bài có
    `wikibase_item` → entity tương ứng. Nếu text hiển thị khác tên bài thì
    đó là một alias.

    Args:
        documents_path: Đường dẫn `documents.jsonl` (Phase 1).
        title_to_qid: Map tên bài → QID (Phase 1).
        qid_to_entity: Map QID → `entity_id`.
        collector: Bộ gom alias.

    Returns:
        Số alias đã thêm.
    """
    added = 0
    for doc in iter_jsonl(documents_path):
        qid = str(doc.get("wikibase_item") or "")
        entity_id = qid_to_entity.get(qid)
        title = str(doc.get("title") or "")
        if entity_id and title:
            if collector.add_normalized_variants(entity_id, title, "title"):
                added += 1
        for link in doc.get("links") or []:
            if not isinstance(link, dict):
                continue
            target_title = str(link.get("target") or "")
            anchor = _clean_alias(link.get("anchor") or "")
            if not target_title or not anchor:
                continue
            target_qid = title_to_qid.get(target_title, "")
            target_entity = qid_to_entity.get(target_qid)
            if not target_entity:
                continue
            if anchor == target_title:
                continue
            if collector.add_normalized_variants(target_entity, anchor, "link"):
                added += 1
    return added


def collect_from_wikidata(
    entities: list[dict[str, Any]],
    collector: AliasCollector,
    *,
    limit: int = 0,
) -> int:
    """Thu alias từ Wikidata (`skos:altLabel` + property tên).

    Dùng `src/preprocess/wikidata_query.py` (cache đĩa ⇒ chạy lại không gọi
    mạng).

    Args:
        entities: Danh sách entity cần lấy alias.
        collector: Bộ gom alias.
        limit: Giới hạn số entity (0 = không giới hạn).

    Returns:
        Số alias đã thêm.
    """
    from src.preprocess.wikidata_query import run_query

    added = 0
    targets = entities[:limit] if limit else entities
    for index, entity in enumerate(targets, start=1):
        qid = str(entity.get("wikidata_qid") or "")
        entity_id = str(entity.get("entity_id") or "")
        if not qid or not entity_id:
            continue
        # `skos:altLabel` + các property tên, gộp 1 request cho nhiều QID.
        values = " ".join(f"wd:{pid}" for pid in WIKIDATA_ALIAS_PROPERTIES)
        query = (
            "SELECT ?alias WHERE { "
            f"VALUES ?pid {{ {values} }} "
            "wd:" + qid + " ?pid ?alias . "
            'FILTER(LANG(?alias) IN ("vi", "vi-vn", "")) '
            "}"
        )
        try:
            rows = run_query(query)
        except Exception as exc:  # noqa: BLE001 - mạng lỗi không được chặn pipeline
            logger.warning("Wikidata lỗi cho %s: %s", qid, exc)
            continue
        for row in rows:
            alias = _clean_alias(row.get("alias"))
            if alias and collector.add_normalized_variants(entity_id, alias, "wikidata"):
                added += 1
        if index % 50 == 0:
            logger.info("Đã truy vấn Wikidata alias cho %d/%d entity", index, len(targets))
    return added


def collect_from_coref(
    coref_path: Path,
    collector: AliasCollector,
    name_of: dict[str, str],
) -> int:
    """Thu alias từ mention trong `coref_resolved.jsonl` (Phase 6).

    Mỗi mention có `canonical_id` + tên bề mặt → tên bề mặt đó là alias của
    entity. Đây là nguồn alias **lớn nhất** (đo được: 137.584 mention đã
    resolve, 15.559 entity khác nhau).

    Args:
        coref_path: Đường dẫn `coref_resolved.jsonl`.
        collector: Bộ gom alias.
        name_of: Map `entity_id` → tên hiển thị (được cập nhật tại chỗ).

    Returns:
        Số entity mới phát hiện.
    """
    n_new = 0
    for record in iter_jsonl(coref_path):
        for mention in record.get("mentions") or []:
            entity_id = str(mention.get("canonical_id") or "")
            if not entity_id:
                continue
            surface = _clean_alias(mention.get("text") or "")
            if not surface:
                continue
            if entity_id not in name_of:
                name_of[entity_id] = surface
                n_new += 1
            collector.add_normalized_variants(entity_id, surface, "mention")
    return n_new


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Thu thập alias cho entity (Phase 9 — bước 1)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--infobox-entities", default="data/interim/infobox_entities.jsonl",
        help="Artifact Phase 3.",
    )
    parser.add_argument(
        "--documents", default="data/interim/documents.jsonl",
        help="Artifact Phase 1 (dùng để thu alias từ hyperlink).",
    )
    parser.add_argument(
        "--wikidata-limit", type=int, default=0,
        help="Giới hạn số entity truy vấn Wikidata (0 = tất cả).",
    )
    parser.add_argument(
        "--skip-wikidata", action="store_true",
        help="Bỏ qua nguồn Wikidata (chạy offline hoàn toàn).",
    )
    parser.add_argument(
        "--out", default="data/knowledge_base/entities.jsonl",
        help="Đường dẫn output.",
    )
    parser.add_argument(
        "--coref", default="data/interim/coref_resolved.jsonl",
        help="Artifact Phase 6 (nguồn alias lớn nhất).",
    )
    parser.add_argument(
        "--include-coref-entities", action="store_true",
        help="Thêm entity chỉ xuất hiện trong coref (không có trong infobox).",
    )
    parser.add_argument(
        "--ner-vote-types", action="store_true",
        help="Gán `type` entity bằng **vote NER đa số** từ coref (D-063). "
             "Mặc định: chỉ dùng cho entity thiếu type từ infobox.",
    )
    args = parser.parse_args()

    config = load_default_config()
    link_cfg = config.get("link") or {}
    kb_dir = resolve_path(config.get("paths", {}).get("kb_dir", "data/knowledge_base"))

    infobox_path = resolve_path(args.infobox_entities)
    documents_path = resolve_path(args.documents)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Nạp entity gốc từ Phase 3 ---
    base_entities: list[dict[str, Any]] = []
    qid_to_entity: dict[str, str] = {}
    known_ids: set[str] = set()
    for entity in iter_jsonl(infobox_path):
        entity_id = str(entity.get("entity_id") or "")
        name = str(entity.get("name") or "")
        if not entity_id or not name:
            continue
        base_entities.append(entity)
        known_ids.add(entity_id)
        qid = str(entity.get("wikidata_qid") or "")
        if qid:
            qid_to_entity.setdefault(qid, entity_id)

    logger.info("Nạp %d entity từ %s", len(base_entities), infobox_path)

    # Mô tả từ đoạn dẫn Wikipedia (nếu đã sinh ở bước trước).
    descriptions: dict[str, str] = {}
    desc_path = kb_dir / "entity_descriptions.jsonl"
    if desc_path.exists():
        for record in iter_jsonl(desc_path):
            entity_id = str(record.get("entity_id") or "")
            text = str(record.get("description") or "")
            if entity_id and text:
                descriptions[entity_id] = text
        logger.info("Nạp %d description từ %s", len(descriptions), desc_path)
    else:
        logger.warning(
            "Không có %s — chạy `python -m src.link.add_descriptions` trước.",
            desc_path,
        )

    collector = AliasCollector()
    collect_from_infobox(infobox_path, collector)
    title_to_qid_path = resolve_path("data/interim/title_to_qid.json")
    title_to_qid: dict[str, str] = {}
    if title_to_qid_path.exists():
        title_to_qid = json.loads(title_to_qid_path.read_text(encoding="utf-8"))
    n_links = collect_from_documents(documents_path, title_to_qid, qid_to_entity, collector)
    logger.info("Thu %d alias từ hyperlink corpus", n_links)

    # --- Nguồn coref: alias + entity chỉ thấy ở Phase 6 ---
    coref_path = resolve_path(args.coref)
    coref_names: dict[str, str] = {}
    if coref_path.exists():
        n_new = collect_from_coref(coref_path, collector, coref_names)
        logger.info(
            "Thu alias từ coref: %d entity mới, %d entity có alias",
            n_new, len(collector.by_entity),
        )

    if not args.skip_wikidata:
        n_wd = collect_from_wikidata(
            base_entities, collector, limit=args.wikidata_limit
        )
        logger.info("Thu %d alias từ Wikidata", n_wd)

    # --- Ghi output contract ---
    n_alias = 0
    n_people = 0
    n_people_with_2 = 0

    # Bảng type theo **vote NER đa số** (D-063). Dùng để gán type cho
    # entity không có trong infobox (vốn để `unknown` ⇒ 89% node KG rơi
    # vào label `Entity` chung chung ⇒ đồ thị rối và câu trả lời vô nghĩa).
    ner_types: dict[str, str] = {}
    if args.ner_vote_types or args.include_coref_entities:
        from src.re.data_convert_re import build_entity_types

        ner_types = build_entity_types(args.coref, args.infobox_entities)
        logger.info(
            "Bảng type từ vote NER: %d entity có type", len(ner_types)
        )

    with out_path.open("w", encoding="utf-8") as handle:
        for entity in base_entities:
            entity_id = str(entity["entity_id"])
            aliases = collector.by_entity.get(entity_id, [])
            n_alias += len(aliases)
            entity_type = str(entity.get("type") or "")
            if not entity_type or entity_type == "unknown":
                entity_type = ner_types.get(entity_id, entity_type)
            if entity_type == "person":
                n_people += 1
                if len(aliases) >= 2:
                    n_people_with_2 += 1
            props = entity.get("props") or {}
            birth_year, death_year = _valid_years(
                props.get("birth_year"), props.get("death_year")
            )
            record = {
                "entity_id": entity_id,
                "name": entity.get("name"),
                "name_normalized": entity.get("name_normalized")
                or normalize_name(str(entity.get("name") or "")),
                "type": entity_type,
                "aliases": aliases,
                "aliases_normalized": [normalize_name(a["alias"]) for a in aliases],
                "wikidata_qid": entity.get("wikidata_qid"),
                "wiki_url": entity.get("wiki_url"),
                "birth_year": birth_year,
                "death_year": death_year,
                "verified": bool(entity.get("verified")),
                "mention_count": int(entity.get("mention_count") or 0),
                "source_method": entity.get("source_method", "infobox"),
                "dump_version": entity.get("dump_version"),
                "model_name": entity.get("model_name"),
                # Mô tả lấy từ đoạn dẫn Wikipedia (Phase 9 bổ sung) — cần cho
                # câu hỏi "X là ai?".
                "description": descriptions.get(entity_id),
                # Giữ thuộc tính chi tiết (năm trị vị, giới tính, miếu hiệu…)
                # để Phase 10 dựng node đầy đủ. Trước đây field này bị rơi
                # ⇒ `reign_start`/`gender`/`description` luôn NULL trong Neo4j.
                "props": props,
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        # --- Entity chỉ xuất hiện ở coref (chưa có trong infobox) ---
        if args.include_coref_entities:
            # Tra tên bài Wikipedia + URL từ `title_to_qid` để gắn
            # `wiki_url`/`wikidata_qid` cho entity mới.
            title_to_qid_norm: dict[str, str] = {}
            for title, qid in title_to_qid.items():
                title_to_qid_norm.setdefault(normalize_name(title), qid)

            for entity_id, name in sorted(coref_names.items()):
                if entity_id in known_ids:
                    continue
                aliases = collector.by_entity.get(entity_id, [])
                n_alias += len(aliases)
                key = normalize_name(name)
                qid = title_to_qid_norm.get(key)
                # Mọi entity đều có `wiki_url` (Gate Phase 10 yêu cầu 0 node
                # thiếu): dựng URL bài Wikipedia từ tên hiển thị.
                slug = quote(name.replace(" ", "_"), safe="/:(),!'.-")
                wiki_url = f"https://vi.wikipedia.org/wiki/{slug}"
                record = {
                    "entity_id": entity_id,
                    "name": name,
                    "name_normalized": key,
                    "type": ner_types.get(entity_id, "unknown"),
                    "aliases": aliases,
                    "aliases_normalized": [normalize_name(a["alias"]) for a in aliases],
                    "wikidata_qid": qid,
                    "wiki_url": wiki_url,
                    "birth_year": None,
                    "death_year": None,
                    "verified": False,
                    "mention_count": len(aliases),
                    "source_method": "coref",
                    "dump_version": None,
                    "model_name": None,
                    "description": descriptions.get(entity_id),
                    "props": {},
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    n_total = len(base_entities) + (
        len(coref_names) - len(known_ids & set(coref_names))
        if args.include_coref_entities else 0
    )
    ratio = (n_people_with_2 / n_people) if n_people else 0.0
    logger.info(
        "Ghi %d entity / %d alias → %s", n_total, n_alias, out_path
    )
    logger.info(
        "PERSON có ≥ 2 alias: %d/%d (%.1f%%)", n_people_with_2, n_people, ratio * 100
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

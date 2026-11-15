"""Phase 9/10 — Khôi phục tên + kiểu cho entity chỉ xuất hiện trong triple.

**Vấn đề (D-085).** `triples_merged.jsonl` có chứa các `entity_id` được *mint*
ở Phase 8 (grounding Wikidata) nhưng **không** có trong
`data/knowledge_base/entities.jsonl` (Phase 9). Vì `make_entity_id` băm
`sha1(f"{type}|{name_normalized}")`, id ấy **mã hoá** cả tên lẫn kiểu — nên
tên/kiểu có thể khôi phục lại bằng cách thử lại (tên, kiểu) và kiểm tra
id có khớp hay không.

Không làm vậy thì `src/graph/build_graph.py` buộc phải tự tạo node mồ côi
với label `Entity` chung chung và tên là slug (`"abdul ali mazari"`), làm
đồ thị rối và câu trả lời RAG vô nghĩa.

**Nguồn ứng viên (theo độ tin cậy giảm dần):**

1. `infobox_triples.jsonl` / `lead_triples.jsonl` — bằng chứng dạng
   `"<nhãn>: <tên>"` kèm `subject_type`/`object_type` ⇒ **có cả tên lẫn
   kiểu** ⇒ nguồn đáng tin nhất.
2. `wikidata_pairs.jsonl` (`object_labels`) — có tên nhưng **không có kiểu**
   ⇒ thử lần lượt các kiểu trong schema.
3. Văn bản bề mặt của mention (`coref_resolved.jsonl`, `linked_mentions.jsonl`)
   + `subject_name`/`object_name` của `re_positive.jsonl` + tiêu đề bài +
   anchor/target của hyperlink — tên bề mặt, không kèm kiểu.

Output: file JSONL các entity đã khôi phục (mỗi dòng 1 record, cùng format
với `entities.jsonl`) để nối vào registry của Phase 9.

Cách dùng::

    python -m src.graph.recover_entities \
        --out data/knowledge_base/entities_recovered.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator

from src.common.ids import make_entity_id
from src.common.logger import get_logger
from src.common.normalize import normalize_name

logger = get_logger("src.graph.recover_entities")

#: Các kiểu node trong schema (`docs/04`) — thử theo thứ tự ưu tiên.
SCHEMA_TYPES: tuple[str, ...] = (
    "person",
    "place",
    "event",
    "dynasty",
    "title",
    "organization",
    "unknown",
    "article",
)


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc JSONL, bỏ qua dòng rỗng.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng dict.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _add_candidate(
    recovered: dict[str, dict[str, str]],
    entity_id: str,
    name: str,
    entity_type: str,
    *,
    source: str,
) -> None:
    """Ghi nhận một ứng viên (tên, kiểu) cho `entity_id` nếu id khớp.

    `entity_id` chỉ được ghi khi `make_entity_id(type, name) == entity_id`
    ⇒ **tự kiểm chứng**: không có cách nào "đoán sai" tên/kiểu.

    Args:
        recovered: Dict kết quả (được cập nhật tại chỗ).
        entity_id: Id cần khôi phục.
        name: Tên hiển thị (có dấu).
        entity_type: Kiểu node.
        source: Nguồn ứng viên (để truy vết).
    """
    if not entity_id or not name or not entity_type:
        return
    if entity_id in recovered:
        return
    if make_entity_id(entity_type, name) != entity_id:
        return
    recovered[entity_id] = {
        "name": name,
        "type": entity_type,
        "source": source,
    }


def _names_from_infobox(
    paths: Iterable[str | Path],
    targets: set[str],
) -> dict[str, dict[str, str]]:
    """Khôi phục (tên, kiểu) từ artifact infobox/lead.

    Args:
        paths: Danh sách artifact.
        targets: Tập `entity_id` cần khôi phục.

    Returns:
        Dict `entity_id` → `{"name", "type", "source"}`.
    """
    recovered: dict[str, dict[str, str]] = {}
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        for record in iter_jsonl(path):
            subject = str(record.get("subject") or "")
            object_ = str(record.get("object") or "")
            subject_type = str(record.get("subject_type") or "")
            object_type = str(record.get("object_type") or "")
            title = str(record.get("doc_title") or "").strip()
            evidence = str(record.get("evidence_sentence") or "")
            # Bằng chứng infobox có dạng `"<nhãn>: <tên>"` → tên nằm sau dấu
            # `:` đầu tiên.
            label_value = evidence.split(":", 1)[1].strip() if ":" in evidence else ""
            for entity_id, own_type, candidates in (
                (subject, subject_type, (title, label_value)),
                (object_, object_type, (label_value, title)),
            ):
                if entity_id not in targets:
                    continue
                for candidate in candidates:
                    if not candidate:
                        continue
                    # Ưu tiên kiểu đã khai báo trong artifact; nếu không có
                    # (ví dụ do đảo chiều), thử toàn bộ kiểu trong schema.
                    types = (
                        (own_type,) if own_type else ()
                    ) + tuple(t for t in SCHEMA_TYPES if t != own_type)
                    for entity_type_try in types:
                        _add_candidate(
                            recovered,
                            entity_id,
                            candidate,
                            entity_type_try,
                            source=path.name,
                        )
                        if entity_id in recovered:
                            break
                    if entity_id in recovered:
                        break
    return recovered


def _name_universe(
    coref_path: str | Path,
    linked_path: str | Path,
    positive_path: str | Path,
    documents_path: str | Path,
    wikidata_path: str | Path,
) -> set[str]:
    """Thu tập mọi tên bề mặt có thể xuất hiện trong corpus.

    Args:
        coref_path: Artifact Phase 6.
        linked_path: Artifact Phase 9.
        positive_path: Artifact Phase 7.
        documents_path: Artifact Phase 1.
        wikidata_path: Artifact Phase 7.

    Returns:
        Tập tên (chuỗi, đã trim).
    """
    names: set[str] = set()

    def add(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            names.add(text)

    if Path(coref_path).exists():
        for record in iter_jsonl(coref_path):
            for mention in record.get("mentions") or []:
                add(mention.get("text"))
    if Path(linked_path).exists():
        for record in iter_jsonl(linked_path):
            add(record.get("text"))
    if Path(positive_path).exists():
        for record in iter_jsonl(positive_path):
            for key in (
                "subject_name",
                "object_name",
                "subject_mention",
                "object_mention",
            ):
                add(record.get(key))
    if Path(documents_path).exists():
        for record in iter_jsonl(documents_path):
            add(record.get("title"))
            for link in record.get("links") or []:
                add(link.get("target"))
                add(link.get("anchor"))
    if Path(wikidata_path).exists():
        for record in iter_jsonl(wikidata_path):
            for label in record.get("object_labels") or []:
                add(label)
    return names


def _recover_from_universe(
    names: set[str],
    targets: set[str],
) -> dict[str, dict[str, str]]:
    """Thử (tên, kiểu) cho mọi tên trong `names` để khớp `targets`.

    Args:
        names: Tập tên bề mặt.
        targets: Tập `entity_id` chưa khôi phục.

    Returns:
        Dict `entity_id` → `{"name", "type", "source"}`.
    """
    recovered: dict[str, dict[str, str]] = {}
    for name in names:
        for entity_type in SCHEMA_TYPES:
            entity_id = make_entity_id(entity_type, name)
            if entity_id in targets and entity_id not in recovered:
                recovered[entity_id] = {
                    "name": name,
                    "type": entity_type,
                    "source": "name_universe",
                }
    return recovered


def _slug_fallback(entity_id: str) -> str:
    """Suy tên hiển thị từ `entity_id` khi không khôi phục được.

    Args:
        entity_id: Id entity.

    Returns:
        Tên dạng `"Abdul Ali Mazari"` (viết hoa chữ cái đầu).
    """
    parts = entity_id.split("_")
    slug = "_".join(parts[1:-1]) if len(parts) >= 3 else entity_id
    text = slug.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else entity_id


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Khôi phục tên + kiểu cho entity chỉ có trong triple (D-085)."
    )
    parser.add_argument(
        "--entities", default="data/knowledge_base/entities.jsonl",
        help="Registry entity hiện có (Phase 9).",
    )
    parser.add_argument(
        "--triples", default="data/interim/triples_merged.jsonl",
        help="Triple đã gộp (Phase 8).",
    )
    parser.add_argument(
        "--infobox-triples", default="data/interim/infobox_triples.jsonl",
    )
    parser.add_argument(
        "--lead-triples", default="data/interim/lead_triples.jsonl",
    )
    parser.add_argument("--coref", default="data/interim/coref_resolved.jsonl")
    parser.add_argument("--linked-mentions", default="data/interim/linked_mentions.jsonl")
    parser.add_argument("--re-positive", default="data/interim/re_positive.jsonl")
    parser.add_argument("--documents", default="data/interim/documents.jsonl")
    parser.add_argument("--wikidata-pairs", default="data/interim/wikidata_pairs.jsonl")
    parser.add_argument(
        "--out", default="data/knowledge_base/entities_recovered.jsonl",
        help="Đường dẫn output (JSONL, 1 record/dòng).",
    )
    args = parser.parse_args()

    known: set[str] = set()
    for record in iter_jsonl(args.entities):
        entity_id = str(record.get("entity_id") or "")
        if entity_id:
            known.add(entity_id)
    logger.info("Registry hiện có: %d entity", len(known))

    used: set[str] = set()
    for record in iter_jsonl(args.triples):
        for role in ("subject", "object"):
            entity_id = str(record.get(role) or "")
            if not entity_id or entity_id in known:
                continue
            # Node thời gian (`year_<n>`) được `build_graph.py` tự sinh ở
            # bước sau — không phải entity cần khôi phục tên/kiểu.
            if entity_id.startswith("year_"):
                continue
            used.add(entity_id)
    logger.info("Entity chỉ có trong triple: %d", len(used))
    if not used:
        logger.info("Không có entity nào cần khôi phục.")
        return 0

    recovered: dict[str, dict[str, str]] = {}
    recovered.update(
        _names_from_infobox(
            (args.infobox_triples, args.lead_triples), used
        )
    )
    logger.info("Khôi phục từ infobox/lead: %d", len(recovered))

    remaining = used - set(recovered)
    if remaining:
        universe = _name_universe(
            args.coref,
            args.linked_mentions,
            args.re_positive,
            args.documents,
            args.wikidata_pairs,
        )
        logger.info("Tập tên bề mặt: %d", len(universe))
        recovered.update(_recover_from_universe(universe, remaining))
    logger.info("Tổng đã khôi phục: %d/%d", len(recovered), len(used))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_fallback = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for entity_id in sorted(used):
            info = recovered.get(entity_id)
            if info is None:
                info = {
                    "name": _slug_fallback(entity_id),
                    "type": "unknown",
                    "source": "slug_fallback",
                }
                n_fallback += 1
            name = info["name"]
            record = {
                "entity_id": entity_id,
                "name": name,
                "name_normalized": normalize_name(name),
                "type": info["type"],
                "aliases": [],
                "aliases_normalized": [],
                "wikidata_qid": None,
                "wiki_url": (
                    "https://vi.wikipedia.org/wiki/"
                    + name.replace(" ", "_").replace("(", "%28").replace(")", "%29")
                ),
                "birth_year": None,
                "death_year": None,
                "verified": False,
                "mention_count": 0,
                "source_method": "recovered",
                "recovered_from": info["source"],
                "dump_version": None,
                "model_name": None,
                "description": None,
                "props": {},
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info(
        "Ghi %d entity (%d fallback slug) → %s",
        len(used), n_fallback, out_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

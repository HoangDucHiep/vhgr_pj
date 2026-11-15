"""Gazetteer tra cứu thực thể cho Phase 6 (coreference C1/C2).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 6.

Gazetteer hợp nhất hai nguồn
---------------------------
1. **Nguồn A — `data/interim/infobox_entities.jsonl`** (Phase 3): tên entity +
   các alias (miếu hiệu, thụy hiệu, niên hiệu, tự) + `props.gender`.
   Đây là nguồn **đáng tin nhất** — `entity_id` đã được `make_entity_id` sinh
   và tái lập được 1.764/1.764 (đo 15/11/2026).
2. **Nguồn B — `data/interim/documents.jsonl`** (Phase 2): tiêu đề bài có type
   suy ra từ `infobox_type` / `wikidata_signal`. Nguồn này có **nhiều entity
   hơn** nhưng type kém chắc hơn, nên chỉ dùng khi nguồn A không có.

Đo trên corpus (15/11/2026):

===========================================  ======  ======
Chỉ số                                       Giá trị  Nguồn
===========================================  ======  ======
Key trong gazetteer nguồn A                   2.004   đo
Key trong gazetteer nguồn B                   1.672   đo
Mention NER có tên (non-TIME)                88.153  đo
Mention hit gazetteer (A ∪ B)                 27.101  đo
Tỉ lệ hit                                    30,7%   đo
===========================================  ======  ======

→ Vì vậy phần lớn named mention cần **mint** `entity_id` mới (xem
`docs/10-nhat-ky/phase-06.md` §3, D-044).

Xung đột type
-------------
Đo được ~3.400 mention có type NER khác type gazetteer (chủ yếu `EVENT`↔`place`
và `DYNASTY`↔`event`). Quy tắc chốt:

- Nguồn A (infobox) > Nguồn B (tiêu đề bài) > type NER.
- Nguồn B chỉ được dùng khi **không** có nguồn A cho cùng tên.
- Khi type gazetteer và type NER khác nhau → giữ type gazetteer, nhưng nếu
  type NER là `DYNASTY`/`TITLE` còn gazetteer là `event`/`place` thì vẫn ưu
  tiên gazetteer (nguồn suy ra từ Wikidata/infobox đáng tin hơn nhãn mô hình).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from src.common.ids import make_entity_id
from src.common.logger import get_logger
from src.common.normalize import normalize_name

logger = get_logger(__name__)

#: Ánh xạ nhãn NER → loại node KG (theo `src.common.schemas.NODE_TYPES`).
LABEL_TO_TYPE: dict[str, str] = {
    "PERSON": "person",
    "DYNASTY": "dynasty",
    "EVENT": "event",
    "LOCATION": "place",
    "TITLE": "title",
}

#: Nhãn NER không tạo node trong KG (mốc thời gian → node `Year` riêng).
NON_ENTITY_LABELS: frozenset[str] = frozenset({"TIME"})

#: `infobox_type` / `wikidata_signal` → loại node KG.
SIGNAL_TO_TYPE: dict[str, str] = {
    "person": "person",
    "place": "place",
    "dynasty": "dynasty",
    "event": "event",
    "battle": "event",
    "house": "dynasty",
}


@dataclass(slots=True)
class GazetteerEntry:
    """Một mục trong gazetteer.

    Attributes:
        entity_id: `entity_id` chuẩn (`ent_<slug>_<hash8>`).
        name: Tên hiển thị (có dấu).
        type: Loại node KG (`person`/`place`/`event`/`dynasty`/`title`).
        source: Nguồn — `"infobox"` (A) hoặc `"doc_title"` (B).
        gender: Giới tính nếu biết (`male`/`female`), ngược lại `None`.
        qid: Wikidata QID nếu có.
    """

    entity_id: str
    name: str
    type: str
    source: str
    gender: str | None = None
    qid: str | None = None


@dataclass(slots=True)
class Gazetteer:
    """Bộ tra cứu tên → thực thể.

    Attributes:
        entries: Map `name_normalized` → `GazetteerEntry`.
        by_qid: Map QID → `entity_id` (dùng để ưu tiên id đã có sẵn).
    """

    entries: dict[str, GazetteerEntry] = field(default_factory=dict)
    by_qid: dict[str, str] = field(default_factory=dict)

    def __len__(self) -> int:
        """Số lượng key trong gazetteer.

        Returns:
            Số key chuẩn hóa.
        """
        return len(self.entries)

    def lookup(self, name: str) -> GazetteerEntry | None:
        """Tra cứu một tên (tự chuẩn hóa).

        Args:
            name: Tên cần tra (có dấu hoặc không).

        Returns:
            `GazetteerEntry` nếu tìm thấy, ngược lại `None`.
        """
        return self.entries.get(normalize_name(name))

    def lookup_normalized(self, name_normalized: str) -> GazetteerEntry | None:
        """Tra cứu bằng tên **đã chuẩn hóa**.

        Args:
            name_normalized: Tên đã bỏ dấu, lowercase.

        Returns:
            `GazetteerEntry` nếu tìm thấy, ngược lại `None`.
        """
        return self.entries.get(name_normalized)

    def add(self, entry: GazetteerEntry) -> None:
        """Thêm một mục, không ghi đè mục đã có (nguồn A được giữ trước).

        Args:
            entry: Mục cần thêm.
        """
        key = normalize_name(entry.name)
        if not key:
            return
        # Đăng ký QID **luôn** (kể cả khi tên mới) — nếu bỏ qua nhánh "tên mới"
        # thì phần lớn entity nguồn A không có trong `by_qid` (đo 15/11/2026:
        # 175/1.736 QID của infobox bị thiếu) → `article_subject` mint lại id
        # trùng tên nhưng **khác hash** so với id đã kiểm chứng ở Phase 3.
        if entry.qid and entry.qid not in self.by_qid:
            self.by_qid[entry.qid] = entry.entity_id

        existing = self.entries.get(key)
        if existing is None:
            self.entries[key] = entry
            return
        # Ưu tiên nguồn A (infobox) — có gender + QID + id đã kiểm chứng.
        if existing.source == "infobox":
            return
        if entry.source == "infobox":
            self.entries[key] = entry


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc JSONL theo luồng (không nạp toàn bộ file).

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


def build_gazetteer(
    infobox_entities_path: str | Path,
    documents_path: str | Path,
) -> Gazetteer:
    """Dựng gazetteer hợp nhất từ infobox entities + tiêu đề bài.

    Args:
        infobox_entities_path: Đường dẫn `infobox_entities.jsonl` (nguồn A).
        documents_path: Đường dẫn `documents.jsonl` (nguồn B).

    Returns:
        `Gazetteer` đã đầy đủ.
    """
    gazetteer = Gazetteer()

    # --- Nguồn A: infobox entities (đáng tin nhất) ---
    n_infobox = 0
    for entity in iter_jsonl(infobox_entities_path):
        entity_id = str(entity.get("entity_id") or "")
        name = str(entity.get("name") or "")
        entity_type = str(entity.get("type") or "")
        if not entity_id or not name or not entity_type:
            continue
        props = entity.get("props") or {}
        gender = props.get("gender") if isinstance(props, dict) else None
        qid = entity.get("wikidata_qid")
        gazetteer.add(
            GazetteerEntry(
                entity_id=entity_id,
                name=name,
                type=entity_type,
                source="infobox",
                gender=gender if isinstance(gender, str) else None,
                qid=str(qid) if qid else None,
            )
        )
        # Alias (miếu hiệu / thụy hiệu / niên hiệu / tự) cũng trỏ về cùng entity.
        for alias in entity.get("aliases") or []:
            alias_name = alias.get("alias") if isinstance(alias, dict) else alias
            if not isinstance(alias_name, str) or not alias_name.strip():
                continue
            alias_key = normalize_name(alias_name)
            if alias_key and alias_key not in gazetteer.entries:
                gazetteer.entries[alias_key] = GazetteerEntry(
                    entity_id=entity_id,
                    name=alias_name,
                    type=entity_type,
                    source="infobox",
                    gender=gender if isinstance(gender, str) else None,
                    qid=str(qid) if qid else None,
                )
        n_infobox += 1

    # --- Nguồn B: tiêu đề bài (nhiều entity hơn, type kém chắc hơn) ---
    n_docs = 0
    for doc in iter_jsonl(documents_path):
        title = str(doc.get("title") or "")
        if not title:
            continue
        doc_type = doc.get("infobox_type")
        if not doc_type:
            doc_type = doc.get("wikidata_signal")
        entity_type = SIGNAL_TO_TYPE.get(str(doc_type or ""))
        if entity_type is None:
            continue
        qid = doc.get("wikibase_item")
        qid_str = str(qid) if qid else None
        # Nếu QID đã biết → dùng lại `entity_id` của nguồn A (tránh mint trùng).
        entity_id = gazetteer.by_qid.get(qid_str or "")
        if entity_id is None:
            entity_id = make_entity_id(entity_type, title)
        gazetteer.add(
            GazetteerEntry(
                entity_id=entity_id,
                name=title,
                type=entity_type,
                source="doc_title",
                qid=qid_str,
            )
        )
        if qid_str and qid_str not in gazetteer.by_qid:
            gazetteer.by_qid[qid_str] = entity_id
        n_docs += 1

    logger.info(
        "Gazetteer: %d key (nguồn A: %d entity · nguồn B: %d bài)",
        len(gazetteer),
        n_infobox,
        n_docs,
    )
    return gazetteer


def resolve_explicit(
    gazetteer: Gazetteer,
    name: str,
    label: str,
    *,
    mint: bool = True,
) -> tuple[str | None, str, float]:
    """Tra cứu (hoặc mint) `entity_id` cho một named mention.

    Args:
        gazetteer: Gazetteer đã dựng.
        name: Tên hiển thị của mention (có dấu).
        label: Nhãn NER (`PERSON`/`DYNASTY`/`EVENT`/`LOCATION`/`TITLE`).
        mint: Cho phép sinh `entity_id` mới khi tên chưa có trong gazetteer.

    Returns:
        Bộ ba ``(entity_id, resolved_by, score)``.
        - Nếu tìm thấy trong gazetteer → ``(entity_id, "explicit", 0.95)``.
        - Nếu mint được → ``(entity_id, "explicit", 0.75)``.
        - Nếu không → ``(None, "unlinked", 0.0)``.
    """
    entry = gazetteer.lookup(name)
    if entry is not None:
        return entry.entity_id, "explicit", 0.95

    if label in NON_ENTITY_LABELS:
        return None, "unlinked", 0.0

    if not mint:
        return None, "unlinked", 0.0

    entity_type = LABEL_TO_TYPE.get(label)
    if entity_type is None:
        return None, "unlinked", 0.0
    return make_entity_id(entity_type, name), "explicit", 0.75

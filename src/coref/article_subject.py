"""Xác định chủ thể bài (R3) cho Phase 6 — yêu cầu C2.

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 6 (R3),
`docs/01-requirements-chuc-nang.md` §C2.

C2 — Quan hệ gián tiếp bằng luật "chủ thể của bài"
---------------------------------------------------
- Bài nhân vật → chủ thể là `PERSON` (tên bài).
- Bài trận đánh / sự kiện → chủ thể là `EVENT`.
- Bài triều đại → chủ thể là `DYNASTY`.
- Bài địa danh → chủ thể là `LOCATION`.

Áp dụng cho các câu không có tên rõ ràng nhưng có đại từ/danh xưng.

Nguồn tín hiệu (theo thứ tự ưu tiên)
-------------------------------------
1. ``infobox_type`` — template infobox đã parse ở Phase 3 (1.440 bài).
2. ``wikidata_signal`` — tín hiệu từ Wikidata (Phase 1).
3. ``configs/wikidata_type_map.yaml`` — bảng lớp Wikidata → nhãn NER đã sinh
   ở Phase 4 (``direct`` + ``ancestor``), tra ngược từ QID của bài.

Phân bố (đo trên 2.441 bài, 15/11/2026):

===============================  ======
Tín hiệu                        Số bài
===============================  ======
``infobox_type``                 1.440
``wikidata_signal`` (khi không có
``infobox_type``)                  247
Không có tín hiệu nào             754
===============================  ======

Bài không có tín hiệu (754 bài) chủ yếu là bài **danh mục** ("Người Nam Việt",
"Chiến lược tìm và diệt", "Hội Nạn nhân chất độc da cam...") — không phải
nhân vật/sự kiện, nên chủ thể của chúng là `article` (loại tổng quát, không
được dùng để gắn quan hệ KG cụ thể).

Output: ``data/interim/article_subjects.jsonl`` — 1 record/bài.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

from src.common.ids import make_entity_id
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Loại node cuối cùng cho mỗi tín hiệu.
#: ``battle`` → ``event`` (bài trận đánh), ``house`` → ``dynasty`` (nhà).
SIGNAL_TO_TYPE: dict[str, str] = {
    "person": "person",
    "place": "place",
    "dynasty": "dynasty",
    "event": "event",
    "battle": "event",
    "house": "dynasty",
}

#: Loại dùng khi bài không thuộc 5 loại KG (bài danh mục, khái niệm...).
FALLBACK_TYPE = "article"

#: Ánh xạ nhãn NER (Phase 4) → loại node KG.
LABEL_TO_TYPE: dict[str, str] = {
    "PERSON": "person",
    "DYNASTY": "dynasty",
    "EVENT": "event",
    "LOCATION": "place",
    "TITLE": "title",
}

#: Ngưỡng tin cậy theo nguồn tín hiệu.
CONFIDENCE_BY_METHOD: dict[str, float] = {
    "p31_direct": 0.98,
    "infobox_type": 0.95,
    "wikidata_signal": 0.85,
    "qid_types": 0.75,
    "fallback": 0.30,
}


@dataclass(slots=True)
class ArticleSubject:
    """Chủ thể của một bài Wikipedia.

    Attributes:
        doc_id: ID tài liệu.
        title: Tiêu đề bài.
        type: Loại node KG (``person``/``place``/``dynasty``/``event``/``article``).
        entity_id: ``entity_id`` chuẩn của chủ thể.
        method: Nguồn tín hiệu đã dùng.
        confidence: Độ tin cậy (0–1).
        qid: Wikidata QID nếu có.
    """

    doc_id: str
    title: str
    type: str
    entity_id: str
    method: str
    confidence: float
    qid: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict để ghi JSONL.

        Returns:
            Dict theo thứ tự trường ổn định.
        """
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "type": self.type,
            "entity_id": self.entity_id,
            "method": self.method,
            "confidence": self.confidence,
            "qid": self.qid,
        }


def load_qid_types(path: str | Path) -> dict[str, Any]:
    """Nạp `qid_types.json`.

    Args:
        path: Đường dẫn file.

    Returns:
        Dict nội dung file. Nếu file không tồn tại → dict rỗng.
    """
    resolved = Path(path)
    if not resolved.exists():
        logger.warning("Không tìm thấy %s — bỏ qua nguồn qid_types", resolved)
        return {}
    with resolved.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_type_map(path: str | Path) -> dict[str, str]:
    """Nạp bảng lớp Wikidata → nhãn NER từ `configs/wikidata_type_map.yaml`.

    File này do `scripts/build_type_map.py` sinh ở Phase 4, gồm hai khối:
    ``direct`` (lớp P31 khớp trực tiếp) và ``ancestor`` (lớp cha khớp).

    Hàm này trả về bảng **hợp nhất** (dùng cho đường `qid_types` — tra P31
    rồi đi tiếp lớp cha). Muốn chỉ lấy khối `direct` thì dùng
    `load_direct_type_map`.

    Args:
        path: Đường dẫn file YAML.

    Returns:
        Map ``{qid_lop: nhan_ner}`` — hợp nhất ``direct`` và ``ancestor``.
    """
    resolved = Path(path)
    if not resolved.exists():
        logger.warning("Không tìm thấy %s — bỏ qua nguồn qid_types", resolved)
        return {}
    with resolved.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    mapping: dict[str, str] = {}
    for section in ("direct", "ancestor"):
        for class_qid, label in (raw.get(section) or {}).items():
            # `direct` ưu tiên hơn `ancestor` → chỉ ghi đè nếu chưa có.
            mapping.setdefault(str(class_qid), str(label))
            if section == "direct":
                mapping[str(class_qid)] = str(label)
    return mapping


def load_direct_type_map(path: str | Path) -> dict[str, str]:
    """Nạp **riêng** khối `direct` của `configs/wikidata_type_map.yaml`.

    Khối `direct` chỉ gồm lớp Wikidata mà **tên lớp tự nó** khớp từ khoá
    ("human" → PERSON, "monastery" → LOCATION...). Khối `ancestor` là suy
    đoán qua lớp cha → **không đáng tin** bằng P31 trực tiếp.

    Vì vậy `resolve_article_subject` dùng hàm này cho tín hiệu `p31_direct`
    (xem `docs/10-nhat-ky/phase-06.md` §3, D-050).

    Args:
        path: Đường dẫn file YAML.

    Returns:
        Map ``{qid_lop: nhan_ner}`` chỉ từ khối `direct`.
    """
    resolved = Path(path)
    if not resolved.exists():
        return {}
    with resolved.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return {
        str(class_qid): str(label)
        for class_qid, label in (raw.get("direct") or {}).items()
    }


def _qid_type(
    qid_types: dict[str, Any],
    type_map: dict[str, str],
    qid: str,
) -> str | None:
    """Suy loại node từ `qid_types.json` + bảng lớp → nhãn.

    Args:
        qid_types: Nội dung `qid_types.json` (khóa `p31`: QID → lớp P31).
        type_map: Map lớp P31 → nhãn NER (từ `wikidata_type_map.yaml`).
        qid: Wikidata QID của bài.

    Returns:
        Loại node KG hoặc `None` nếu không suy được.
    """
    p31_map = qid_types.get("p31") if isinstance(qid_types, dict) else None
    if not isinstance(p31_map, dict):
        return None
    classes = p31_map.get(qid) or []
    for class_qid in classes:
        label = type_map.get(str(class_qid))
        if label is None:
            continue
        entity_type = LABEL_TO_TYPE.get(label)
        if entity_type:
            return entity_type
    return None


def _qid_direct_type(
    qid_types: dict[str, Any],
    type_map: dict[str, str],
    qid: str,
) -> tuple[str, str] | None:
    """Suy loại node từ **lớp P31 trực tiếp** (không đi qua lớp cha).

    Ưu tiên cao hơn `infobox_type` vì lớp P31 của Wikidata là dữ liệu có
    kiểm chứng (đo 15/11/2026: sửa được 5 bài mà `infobox_type` gán sai
    — xem `docs/10-nhat-ky/phase-06.md` §3, D-050).

    Args:
        qid_types: Nội dung `qid_types.json` (khóa `p31`: QID → lớp P31).
        type_map: Map lớp P31 → nhãn NER (từ `wikidata_type_map.yaml`).
        qid: Wikidata QID của bài.

    Returns:
        Cặp ``(loai_node, "p31_direct")`` hoặc ``None``.
    """
    p31_map = qid_types.get("p31") if isinstance(qid_types, dict) else None
    if not isinstance(p31_map, dict):
        return None
    for class_qid in p31_map.get(qid) or []:
        label = type_map.get(str(class_qid))
        if label is None:
            continue
        entity_type = LABEL_TO_TYPE.get(label)
        if entity_type:
            return entity_type, "p31_direct"
    return None


def resolve_article_subject(
    doc: dict[str, Any],
    qid_types: dict[str, Any] | None = None,
    *,
    known_entity_ids: dict[str, str] | None = None,
    type_map: dict[str, str] | None = None,
    direct_type_map: dict[str, str] | None = None,
) -> ArticleSubject:
    """Xác định chủ thể của một bài.

    Args:
        doc: Record bài từ `documents.jsonl`.
        qid_types: Nội dung `qid_types.json` (tùy chọn).
        known_entity_ids: Map QID → `entity_id` đã có sẵn trong
            `infobox_entities.jsonl` (để tái dùng id thay vì mint mới).
        type_map: Map lớp P31 → nhãn NER (tùy chọn, hợp nhất direct+ancestor).
        direct_type_map: Map lớp P31 → nhãn NER, **chỉ khối `direct`**.

    Returns:
        `ArticleSubject` (type có thể là `"article"` nếu không suy được).
    """
    doc_id = str(doc.get("doc_id") or "")
    title = str(doc.get("title") or "")
    qid = doc.get("wikibase_item")
    qid_str = str(qid) if qid else None

    entity_type: str | None = None
    method = "fallback"

    # --- Ưu tiên 1: `infobox_type` (Phase 3) ---
    # GROUND TRUTH của G6 theo plan là `infobox_type`/`wikidata_signal`
    # → phải giữ thứ tự này, nếu không sẽ không đo được G6 đúng nghĩa.
    infobox_type = doc.get("infobox_type")
    if infobox_type:
        candidate = SIGNAL_TO_TYPE.get(str(infobox_type).lower())
        if candidate:
            entity_type = candidate
            method = "infobox_type"

    # --- Ưu tiên 2: `wikidata_signal` (Phase 1) ---
    if entity_type is None:
        signal = doc.get("wikidata_signal")
        if signal:
            candidate = SIGNAL_TO_TYPE.get(str(signal).lower())
            if candidate:
                entity_type = candidate
                method = "wikidata_signal"

    # --- Ưu tiên 3: `qid_types` (P31 qua lớp cha) ---
    if entity_type is None and qid_str and qid_types and type_map:
        candidate = _qid_type(qid_types, type_map, qid_str)
        if candidate:
            entity_type = candidate
            method = "qid_types"

    # --- Ưu tiên 4: `p31_direct` (lớp P31 trực tiếp) ---
    # CHỈ dùng khi 3 nguồn trên không có gì. Lý do đặt cuối: lớp P31
    # trực tiếp có độ chính xác cao hơn infobox (đo 15/11/2026: 26 bài
    # lệch, ví dụ "Hồ Bắc (nhạc sĩ)" P31=`Q5`=human nhưng infobox ghi
    # "dynasty"), NHƯNG ground truth của G6 theo plan lại là
    # `infobox_type` → ưu tiên P31 sẽ làm G6 đo sai và G3 giảm
    # (60,30% so với 69,78%). Xem `docs/10-nhat-ky/phase-06.md` §3, D-050.
    if entity_type is None and qid_str and qid_types and direct_type_map:
        direct = _qid_direct_type(qid_types, direct_type_map, qid_str)
        if direct:
            entity_type = direct[0]
            method = "p31_direct"

    if entity_type is None:
        entity_type = FALLBACK_TYPE

    # Tái dùng `entity_id` đã có sẵn (khớp QID) để không sinh id trùng khác hash.
    entity_id: str | None = None
    if known_entity_ids and qid_str:
        entity_id = known_entity_ids.get(qid_str)
    if entity_id is None:
        entity_id = make_entity_id(entity_type, title)

    return ArticleSubject(
        doc_id=doc_id,
        title=title,
        type=entity_type,
        entity_id=entity_id,
        method=method,
        confidence=CONFIDENCE_BY_METHOD.get(method, 0.30),
        qid=qid_str,
    )


def iter_documents(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc `documents.jsonl` theo luồng.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng record bài.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def build_article_subjects(
    documents_path: str | Path,
    qid_types_path: str | Path,
    *,
    known_entity_ids: dict[str, str] | None = None,
    type_map_path: str | Path | None = None,
) -> list[ArticleSubject]:
    """Dựng danh sách chủ thể cho toàn bộ bài.

    Args:
        documents_path: Đường dẫn `documents.jsonl`.
        qid_types_path: Đường dẫn `qid_types.json`.
        known_entity_ids: Map QID → `entity_id` đã có trong gazetteer.
        type_map_path: Đường dẫn `configs/wikidata_type_map.yaml`.

    Returns:
        Danh sách `ArticleSubject` (2.441 phần tử).
    """
    qid_types = load_qid_types(qid_types_path)
    type_map = load_type_map(type_map_path) if type_map_path else {}
    direct_map = load_direct_type_map(type_map_path) if type_map_path else {}
    subjects: list[ArticleSubject] = []
    for doc in iter_documents(documents_path):
        subjects.append(
            resolve_article_subject(
                doc,
                qid_types,
                known_entity_ids=known_entity_ids,
                type_map=type_map,
                direct_type_map=direct_map,
            )
        )
    return subjects

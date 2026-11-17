"""Phase 16 — Bước 1: dựng bộ câu hỏi đánh giá (250 câu / 5 dạng).

Vì sao sinh từ **Wikidata** (độc lập KG)?
--------------------------------------
KG của dự án được xây từ Wikipedia + Wikidata + LLM. Nếu sinh câu hỏi từ
chính KG thì đáp án nằm sẵn trong KG ⇒ **tự tham chiếu** ⇒ chấm điểm không
có ý nghĩa. Vì vậy:
- **Đáp án** lấy từ `data/interim/wikidata_pairs.jsonl` (12.602 cặp, tải
  trực tiếp từ Wikidata API ở Phase 7) — nguồn **độc lập** với KG nội bộ.
- **Câu hỏi** sinh bằng template theo quan hệ ⇒ có thể kiểm chứng tự động.
- **`evidence_doc_id`** lấy từ cạnh KG có `evidence_sentence` khớp quan hệ
  (để đo `citation_precision`: trích dẫn có trỏ đúng bài không).

Phạm vi: **lịch sử Việt Nam** — mọi entity dùng trong câu hỏi/đáp án phải có
bài Wikipedia trong corpus (`documents_clean.jsonl`) ⇒ cả hai arm đều có khả
năng trả lời ⇒ so sánh công bằng.

Chiều quan hệ trong `wikidata_pairs.jsonl` (raw Wikidata)
----------------------------------------------------------
`subject` = người được mô tả, `object` = người/địa điểm/ngày được hỏi về.

| Quan hệ | subject | object | Câu hỏi sinh ra |
|---|---|---|---|
| `cha_cua` (P22) | con | cha | "Ai là cha của {subject}?" |
| `me_cua` (P25) | con | mẹ | "Ai là mẹ của {subject}?" |
| `anh_em_cua` (P3373) | người A | người B | "Ai là anh em của {subject}?" |
| `vo_cua` (P26) | người A | người B | "Ai là vợ/chồng của {subject}?" (theo giới của object) |
| `sinh_nam` (P569) | người | ngày | "{subject} sinh năm nào?" |
| `mat_nam` (P570) | người | ngày | "{subject} mất năm nào?" |
| `sinh_tai` (P19) | người | nơi | "{subject} sinh tại đâu?" |
| `mat_tai` (P20) | người | nơi | "{subject} mất tại đâu?" |

5 dạng câu hỏi (250 câu)
------------------------
| # | Dạng (`type`) | Số | Nguồn | Đặc điểm |
|---|---|---|---|---|
| 1 | `relational` | 60 | Wikidata (cha/mẹ/vợ, sinh/mất năm, nơi) | đáp án chính xác |
| 2 | `narrative` | 60 | bài có section "Diễn biến" | chỉ RAG mới trả lời được |
| 3 | `multi_hop` | 40 | Wikidata 2 bước (cha của cha…) | cần nối text ↔ graph |
| 4 | `no_data` | 30 | chủ đề ngoài lịch sử Việt Nam | đo `no_data_accuracy` |
| 5 | `multi_turn` | 60 | 30 bộ × 2 lượt (lượt 2 dùng đại từ) | đo kế thừa chủ thề |

Output contract (`data/eval/qa_rag_250.jsonl`)
--------------------------------------------
```json
{"qid":"q0001","question":"...","type":"relational",
 "expected_answer":"...","expected_entities":["ent_..."],
 "evidence_doc_id":["doc_..."],"session_id":null,
 "prev_turns":[],"turn_index":0,"_meta":{...}}
```
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.common.config import resolve_path
from src.common.logger import get_logger

logger = get_logger("src.evaluation.build_qa_set")

#: Seed tái lập (nguyên tắc #6 trong `AGENTS.md` §5).
SEED = 42

#: Từ khoá trong `description` ⇒ giống cái (dùng để chọn "vợ" hay "chồng").
FEMALE_HINTS: tuple[str, ...] = (
    "hoang hau", "cong chua", "thai hau", "nu hoang", "hoang phi",
    "que ty", "ba noi", "thieu nhi", "thieu nữ", "nữ", "em gai", "chi em",
)
MALE_HINTS: tuple[str, ...] = (
    "vua ", "vua.", "hoang de", "thai tu", "quoc cong tien", "ong ",
    "trang tuong", "dai tuong", "tai tuong", "hau tai", "chuong tuong",
)

#: Template câu hỏi nhiều lượt (lượt 2 dùng đại từ).
FOLLOW_UP_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("Ông ấy sinh năm nào?", "sinh_nam"),
    ("Ông ấy mất năm nào?", "mat_nam"),
    ("Vị ấy sinh tại đâu?", "sinh_tai"),
)

#: Chủ đề ngoài phạm vi (dùng cho dạng `no_data`).
NO_DATA_TOPICS: list[str] = [
    "Công nghệ blockchain và tiền mã hoá",
    "Hệ thống điện mặt trời hoạt động như thế nào",
    "Cách nấu món phở bò Hà Nội",
    "Lịch thi đấu bóng đá World Cup 2026",
    "Trí tuệ nhân tạo tạo ảnh như thế nào",
    "Xe điện Tesla Model Y dùng pin loại gì",
    "Cách lập bảng theo dõi chi phí gia đình",
    "Quy trình đăng ký hộ khẩu tại Hà Nội",
    "Cách chăm sóc cây thủy tinh trong nhà",
    "Nguyên lý hoạt động của động cơ điện",
    "Phương pháp học tập từ vựng tiếng Anh hiệu quả",
    "Cách tính thuế thu nhập cá nhân",
    "Công thức nấu cháo đậu đỏ",
    "Cách chọn giày chạy bộ phù hợp",
    "Nguyên tắc an toàn khi sửa điện",
    "Cách trồng hoa hướng dương",
    "Khẩu vị món gà nướng than",
    "Cách thanh lý xe máy cũ",
    "Cấu trúc của một bài thơ Đường luật",
    "Cách sử dụng máy lọc nước gia đình",
    "Nguyên lý hoạt động của tủ lạnh",
    "Cách trồng rau thủy canh tại nhà",
    "Bí quyết chọn dầu ăn tốt cho sức khỏe",
    "Cách làm bánh xèo giòn",
    "Công nghệ 5G khác 4G như thế nào",
    "Cách đăng ký bảo hiểm y tế",
    "Nguyên lý của tủ lạnh inverter",
    "Cách tập luyện cơ bắp tại nhà",
    "Hướng dẫn chọn máy lọc nước cho gia đình",
]

#: Từ khoá section cho dạng `narrative` (so khớp **không phân biệt dấu**).
NARRATIVE_SECTIONS: tuple[str, ...] = (
    "dien bien",
    "dien bien tran danh",
    "dien bien cuoc chien",
    "dien bien va ket qua",
    "dien tai",
    "dien tich",
    "hoan doi luc luong hai ben",
    "khoi nghia",
    "chu bien",
)

#: Số chunk tối thiểu của một section để làm câu hỏi narrative.
NARRATIVE_MIN_CHUNKS = 3


def _norm(text: str) -> str:
    """Chuẩn hoá tên để so khớp (bỏ dấu + hạ thường + gộp khoảng trắng).

    Args:
        text: Chuỗi gốc.

    Returns:
        Chuỗi chuẩn hoá.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.replace("đ", "d").lower().split())


def _year_from_date(value: str) -> str:
    """Trích năm từ chuỗi ngày kiểu Wikidata (``0940-01-01T00:00:00Z``).

    Args:
        value: Chuỗi ngày.

    Returns:
        Năm dạng chuỗi (rỗng nếu không parse được).
    """
    match = re.match(r"^([+-]?\d{1,6})-(\d{2})-(\d{2})", str(value or ""))
    if not match:
        return ""
    year = int(match.group(1))
    if year <= 0:
        return ""
    return str(year)


def _looks_female(entity: dict[str, Any]) -> bool:
    """Suy đoán giới từ `description` của entity.

    Args:
        entity: Entity.

    Returns:
        ``True`` nếu có dấu hiệu nữ.
    """
    text = _norm(str(entity.get("description") or ""))
    if any(hint in text for hint in FEMALE_HINTS):
        return True
    if any(hint in text for hint in MALE_HINTS):
        return False
    return False


def load_entities(path: Path) -> dict[str, dict[str, Any]]:
    """Nạp entity theo `entity_id`.

    Args:
        path: Đường dẫn `entities.jsonl`.

    Returns:
        Dict `entity_id` → entity.
    """
    entities: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                record = json.loads(line)
                entities[str(record.get("entity_id"))] = record
    return entities


def load_qid_index(entities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Chọn 1 entity đại diện cho mỗi QID (ưu tiên `person`).

    Args:
        entities: Dict entity theo `entity_id`.

    Returns:
        Dict `qid` → entity đại diện.
    """
    index: dict[str, dict[str, Any]] = {}
    for entity in entities.values():
        qid = str(entity.get("wikidata_qid") or "")
        if not qid:
            continue
        current = index.get(qid)
        if current is None:
            index[qid] = entity
        elif current.get("type") != "person" and entity.get("type") == "person":
            index[qid] = entity
    return index


def load_doc_scope(path: Path) -> dict[str, dict[str, Any]]:
    """Dựng phạm vi corpus: QID → `{doc_id, title}`.

    Chỉ entity có bài Wikipedia trong corpus mới được dùng ⇒ câu hỏi/đáp án
    đều nằm trong tầng truy xuất văn bản ⇒ **so sánh A vs B công bằng**.

    Args:
        path: Đường dẫn `documents_clean.jsonl`.

    Returns:
        Dict `qid` → `{doc_id, title}`.
    """
    scope: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            qid = str(doc.get("wikibase_item") or "")
            if not qid:
                continue
            scope.setdefault(
                qid, {"doc_id": str(doc.get("doc_id")), "title": str(doc.get("title"))}
            )
    return scope


def build_evidence_index(
    triples: list[dict[str, Any]],
) -> dict[tuple[str, str], list[str]]:
    """Dựng chỉ mục `(subject, relation)` → danh sách `doc_id`.

    Args:
        triples: Danh sách triple.

    Returns:
        Dict `(subject_entity_id, relation)` → `doc_id` (không trùng).
    """
    index: dict[tuple[str, str], list[str]] = {}
    for triple in triples:
        key = (str(triple.get("subject") or ""), str(triple.get("relation") or ""))
        doc_id = str(triple.get("doc_id") or "")
        if not doc_id:
            continue
        bucket = index.setdefault(key, [])
        if doc_id not in bucket:
            bucket.append(doc_id)
    return index


def _relations_of(
    pairs: list[dict[str, Any]],
    qid_index: dict[str, dict[str, Any]],
    scope: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Chuẩn hoá cặp Wikidata thành bản ghi có tên + phạm vi.

    Args:
        pairs: Cặp quan hệ thô.
        qid_index: Index entity theo QID.
        scope: Phạm vi corpus theo QID.

    Returns:
        Danh sách bản ghi đã chuẩn hoá.
    """
    out: list[dict[str, Any]] = []
    for pair in pairs:
        relation = str(pair.get("relation") or "")
        subject_qid = str(pair.get("subject_qid") or "")
        object_qid = str(pair.get("object_qid") or "")
        subject = qid_index.get(subject_qid)
        if subject is None:
            continue
        record: dict[str, Any] = {
            "relation": relation,
            "subject_qid": subject_qid,
            "subject": subject,
            "subject_name": str(subject.get("name") or ""),
            "object_qid": object_qid,
            "object": qid_index.get(object_qid),
            "object_name": "",
            "subject_in_scope": subject_qid in scope,
            "object_in_scope": object_qid in scope,
            "object_is_entity": bool(pair.get("object_is_entity")),
        }
        obj = record["object"]
        record["object_valid"] = obj is not None
        if obj is not None:
            record["object_name"] = str(obj.get("name") or "")
        # Chuẩn hoá chiều `cha_cua`:
        # - P22 (father)  : subject = con,  object = cha
        # - P40 (child)   : subject = cha,  object = con
        father_qid = ""
        child_qid = ""
        if relation == "cha_cua":
            if str(pair.get("property") or "") == "P40":
                father_qid, child_qid = subject_qid, object_qid
            else:
                father_qid, child_qid = object_qid, subject_qid
        record["father_qid"] = father_qid
        record["child_qid"] = child_qid
        out.append(record)
    return out


def build_relational_questions(
    relations: list[dict[str, Any]],
    qid_index: dict[str, dict[str, Any]],
    evidence_index: dict[tuple[str, str], list[str]],
    scope: dict[str, dict[str, Any]],
    rng: random.Random,
    limit: int,
) -> list[dict[str, Any]]:
    """Sinh câu hỏi dạng `relational`.

    Args:
        relations: Cặp đã chuẩn hoá.
        qid_index: Index entity theo QID.
        evidence_index: Chỉ mục bằng chứng.
        scope: Phạm vi corpus.
        rng: RNG có seed.
        limit: Số câu cần sinh.

    Returns:
        Danh sách câu hỏi.
    """
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        key = _norm(item["question"])
        if key in seen:
            return
        seen.add(key)
        candidates.append(item)

    # 1) Cha / mẹ.
    for record in relations:
        relation = record["relation"]
        if relation not in {"cha_cua", "me_cua"}:
            continue
        if relation == "cha_cua":
            child_qid, parent_qid = record["child_qid"], record["father_qid"]
        else:
            child_qid, parent_qid = record["subject_qid"], record["object_qid"]
        child = qid_index.get(child_qid)
        parent = qid_index.get(parent_qid)
        if child is None or parent is None:
            continue
        if child_qid not in scope or parent_qid not in scope:
            continue
        if child.get("type") != "person" or parent.get("type") != "person":
            continue
        child_name = str(child.get("name") or "")
        parent_name = str(parent.get("name") or "")
        if not child_name or not parent_name:
            continue
        word = "cha" if relation == "cha_cua" else "mẹ"
        add(
            {
                "question": f"Ai là {word} của {child_name}?",
                "type": "relational",
                "expected_answer": parent_name,
                "expected_entities": [
                    str(child.get("entity_id")),
                    str(parent.get("entity_id")),
                ],
                "evidence_doc_id": evidence_index.get(
                    (str(child.get("entity_id")), relation), []
                )[:3],
                "relation": relation,
                "subject_name": child_name,
                "object_name": parent_name,
            }
        )

    # 2) Con (chiều ngược).
    grouped: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for record in relations:
        relation = record["relation"]
        if relation not in {"cha_cua", "me_cua"}:
            continue
        if relation == "cha_cua":
            parent_qid, child_qid = record["father_qid"], record["child_qid"]
        else:
            parent_qid, child_qid = record["object_qid"], record["subject_qid"]
        parent = qid_index.get(parent_qid)
        child = qid_index.get(child_qid)
        if parent is None or child is None:
            continue
        if parent_qid not in scope or child_qid not in scope:
            continue
        if parent.get("type") != "person" or child.get("type") != "person":
            continue
        grouped[(parent_qid, relation)].append((child_qid, record))
    for (parent_qid, relation), entries in grouped.items():
        parent = qid_index.get(parent_qid)
        if parent is None:
            continue
        parent_name = str(parent.get("name") or "")
        child_names = list(
            dict.fromkeys(
                str((qid_index.get(child_qid) or {}).get("name") or "")
                for child_qid, _ in entries
            )
        )
        child_names = [name for name in child_names if name]
        if not parent_name or not child_names:
            continue
        add(
            {
                "question": f"Ai là con của {parent_name}?",
                "type": "relational",
                "expected_answer": ", ".join(sorted(child_names)),
                "expected_entities": sorted(
                    {
                        str((qid_index.get(child_qid) or {}).get("entity_id"))
                        for child_qid, _ in entries
                    }
                ),
                "evidence_doc_id": evidence_index.get(
                    (str(parent.get("entity_id")), relation), []
                )[:3],
                "relation": f"inverse_{relation}",
                "subject_name": parent_name,
                "object_name": ", ".join(sorted(child_names)),
            }
        )

    # 3) Năm sinh / năm mất.
    for record in relations:
        relation = record["relation"]
        if relation not in {"sinh_nam", "mat_nam"}:
            continue
        if not record["subject_in_scope"] or record["object_is_entity"]:
            continue
        if record["subject"].get("type") != "person":
            continue
        year = _year_from_date(record["object_qid"])
        if not year:
            continue
        word = "sinh" if relation == "sinh_nam" else "mất"
        add(
            {
                "question": f"{record['subject_name']} {word} năm nào?",
                "type": "relational",
                "expected_answer": f"năm {year}",
                "expected_entities": [str(record["subject"].get("entity_id"))],
                "evidence_doc_id": evidence_index.get(
                    (str(record["subject"].get("entity_id")), relation), []
                )[:3],
                "relation": relation,
                "subject_name": record["subject_name"],
                "object_name": year,
            }
        )

    # 4) Nơi sinh / nơi mất.
    for record in relations:
        relation = record["relation"]
        if relation not in {"sinh_tai", "mat_tai"}:
            continue
        if not record["subject_in_scope"] or not record["object_in_scope"]:
            continue
        if record["subject"].get("type") != "person":
            continue
        if not record["object_name"]:
            continue
        word = "sinh" if relation == "sinh_tai" else "mất"
        add(
            {
                "question": f"{record['subject_name']} {word} tại đâu?",
                "type": "relational",
                "expected_answer": record["object_name"],
                "expected_entities": [
                    str(record["subject"].get("entity_id")),
                    str(record["object"].get("entity_id")),
                ],
                "evidence_doc_id": evidence_index.get(
                    (str(record["subject"].get("entity_id")), relation), []
                )[:3],
                "relation": relation,
                "subject_name": record["subject_name"],
                "object_name": record["object_name"],
            }
        )

    # 5) Vợ / chồng (giới lấy theo `description` của object).
    for record in relations:
        if record["relation"] != "vo_cua":
            continue
        if not record["subject_in_scope"] or not record["object_in_scope"]:
            continue
        if record["subject"].get("type") != "person":
            continue
        obj = record["object"]
        if obj is None or obj.get("type") != "person" or not record["object_name"]:
            continue
        word = "vợ" if _looks_female(obj) else "chồng"
        add(
            {
                "question": f"Ai là {word} của {record['subject_name']}?",
                "type": "relational",
                "expected_answer": record["object_name"],
                "expected_entities": [
                    str(record["subject"].get("entity_id")),
                    str(obj.get("entity_id")),
                ],
                "evidence_doc_id": evidence_index.get(
                    (str(record["subject"].get("entity_id")), "vo_cua"), []
                )[:3],
                "relation": "vo_cua",
                "subject_name": record["subject_name"],
                "object_name": record["object_name"],
            }
        )

    # Cân bằng theo dạng quan hệ (tránh dồn toàn bộ vào "sinh năm").
    quotas = {
        "cha_cua": 8,
        "me_cua": 5,
        "inverse_cha_cua": 8,
        "inverse_me_cua": 4,
        "vo_cua": 6,
        "sinh_nam": 9,
        "mat_nam": 8,
        "sinh_tai": 5,
        "mat_tai": 5,
    }
    by_relation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        by_relation[str(item.get("relation") or "")].append(item)
    selected: list[dict[str, Any]] = []
    for relation, quota in quotas.items():
        bucket = by_relation.get(relation, [])
        rng.shuffle(bucket)
        selected.extend(bucket[:quota])
    rng.shuffle(selected)
    return selected[:limit]


def build_narrative_questions(
    chunks_path: Path,
    kg_doc_ids: set[str],
    rng: random.Random,
    limit: int,
) -> list[dict[str, Any]]:
    """Sinh câu hỏi dạng `narrative` từ section "Diễn biến" của bài có KG.

    Args:
        chunks_path: Đường dẫn `chunks.jsonl`.
        kg_doc_ids: Tập `doc_id` có mặt trong KG (đồ thị có dữ liệu liên quan).
        rng: RNG có seed.
        limit: Số câu cần sinh.

    Returns:
        Danh sách câu hỏi.
    """
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            section_path = str(record.get("section_path") or "")
            section_last = section_path.split(" > ")[-1]
            if not any(keyword in _norm(section_last) for keyword in NARRATIVE_SECTIONS):
                continue
            if len(str(record.get("text") or "")) < 200:
                continue
            by_doc[str(record.get("doc_id"))].append(record)

    candidates: list[dict[str, Any]] = []
    for doc_id, chunks in by_doc.items():
        if doc_id not in kg_doc_ids:
            continue
        if len(chunks) < NARRATIVE_MIN_CHUNKS:
            continue
        title = str(chunks[0].get("title") or "")
        section_path = str(chunks[0].get("section_path") or "")
        section = section_path.split(" > ")[-1]
        if not title or not section:
            continue
        normalized_section = _norm(section)
        if "dien bien" in normalized_section:
            question = f"Kể lại diễn biến {title}."
        elif normalized_section.startswith("khoi nghia"):
            question = f"Kể lại diễn biến khởi nghĩa {title}."
        else:
            question = f"Trong {title}, {section.lower()} diễn ra như thế nào?"
        # Đoạn tham chiếu: 600 ký tự đầu của phần narrative.
        reference = " ".join(str(c.get("text") or "") for c in chunks)[:600].strip()
        candidates.append(
            {
                "question": question,
                "type": "narrative",
                "expected_answer": reference,
                "expected_entities": [],
                "evidence_doc_id": [doc_id],
                "evidence_section": section,
                "relation": "narrative",
                "subject_name": title,
                "object_name": section,
            }
        )

    # Ưu tiên chủ đề "lịch sử cổ đại" (chiến tranh, trận đánh, triều đại) trước,
    # rồi mới tới sự kiện hiện đại ⇒ câu hỏi sát phạm vi đề tài.
    priority = ("chiến tranh", "trận", "khởi nghĩa", "nhà ", "triều", "vua ", "đế ")
    candidates.sort(key=lambda item: 0 if any(k in _norm(item["subject_name"]) for k in priority) else 1)
    rng.shuffle(candidates)
    return candidates[:limit]


def build_multi_hop_questions(
    relations: list[dict[str, Any]],
    qid_index: dict[str, dict[str, Any]],
    scope: dict[str, dict[str, Any]],
    evidence_index: dict[tuple[str, str], list[str]],
    rng: random.Random,
    limit: int,
) -> list[dict[str, Any]]:
    """Sinh câu hỏi 2 bước: cha của cha, mẹ của mẹ, vợ của cha, chồng của mẹ.

    Args:
        relations: Cặp đã chuẩn hoá.
        qid_index: Index entity theo QID.
        scope: Phạm vi corpus.
        evidence_index: Chỉ mục bằng chứng.
        rng: RNG có seed.
        limit: Số câu cần sinh.

    Returns:
        Danh sách câu hỏi.
    """
    # `parents[child_qid]` = danh sách (cha/mẹ) của người đó.
    parents: dict[str, list[dict[str, Any]]] = defaultdict(list)
    spouses: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in relations:
        if record["relation"] == "cha_cua":
            child_qid = record["child_qid"]
            parent_qid = record["father_qid"]
        elif record["relation"] == "me_cua":
            child_qid = record["subject_qid"]
            parent_qid = record["object_qid"]
        else:
            child_qid = parent_qid = ""
        if record["relation"] in {"cha_cua", "me_cua"}:
            parent = qid_index.get(parent_qid)
            if parent is None or parent_qid not in scope or child_qid not in scope:
                continue
            parents[child_qid].append(record)
        elif record["relation"] == "vo_cua":
            if (
                record["subject_in_scope"]
                and record["object_in_scope"]
                and record["object_valid"]
            ):
                spouses[record["subject_qid"]].append(record)

    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        key = _norm(item["question"])
        if key in seen:
            return
        seen.add(key)
        candidates.append(item)

    for child_qid, entries in parents.items():
        child = qid_index.get(child_qid)
        if child is None:
            continue
        child_name = str(child.get("name") or "")
        for entry in entries:
            if entry["relation"] != "cha_cua":
                continue
            father_qid = entry["father_qid"]
            father = qid_index.get(father_qid)
            if father is None:
                continue
            father_name = str(father.get("name") or "")
            if not child_name or not father_name:
                continue

            # (a) Cha của cha.
            for grandpa_entry in parents.get(father_qid, []):
                if grandpa_entry["relation"] != "cha_cua":
                    continue
                grandpa = qid_index.get(grandpa_entry["father_qid"])
                if grandpa is None:
                    continue
                add(
                    {
                        "question": f"Cha của cha {child_name} là ai?",
                        "type": "multi_hop",
                        "expected_answer": str(grandpa.get("name") or ""),
                        "expected_entities": [
                            str(child.get("entity_id")),
                            str(father.get("entity_id")),
                            str(grandpa.get("entity_id")),
                        ],
                        "evidence_doc_id": evidence_index.get(
                            (str(child.get("entity_id")), "cha_cua"), []
                        )[:3],
                        "relation": "multi_hop_cha_cua_cha_cua",
                        "subject_name": child_name,
                        "object_name": str(grandpa.get("name") or ""),
                    }
                )

            # (b) Mẹ của mẹ.
            for mother_entry in parents.get(father_qid, []):
                if mother_entry["relation"] != "me_cua":
                    continue
                mother = qid_index.get(mother_entry["object_qid"])
                if mother is None:
                    continue
                add(
                    {
                        "question": f"Mẹ của mẹ {child_name} là ai?",
                        "type": "multi_hop",
                        "expected_answer": str(mother.get("name") or ""),
                        "expected_entities": [
                            str(child.get("entity_id")),
                            str(father.get("entity_id")),
                            str(mother.get("entity_id")),
                        ],
                        "evidence_doc_id": evidence_index.get(
                            (str(child.get("entity_id")), "cha_cua"), []
                        )[:3],
                        "relation": "multi_hop_me_cua_me_cua",
                        "subject_name": child_name,
                        "object_name": str(mother.get("name") or ""),
                    }
                )

            # (c) Vợ của cha (bà nội).
            for spouse_entry in spouses.get(father_qid, []):
                wife = spouse_entry["object"]
                if wife is None or not _looks_female(wife):
                    continue
                add(
                    {
                        "question": f"Vợ của cha {child_name} là ai?",
                        "type": "multi_hop",
                        "expected_answer": spouse_entry["object_name"],
                        "expected_entities": [
                            str(child.get("entity_id")),
                            str(father.get("entity_id")),
                            str(wife.get("entity_id")),
                        ],
                        "evidence_doc_id": evidence_index.get(
                            (str(child.get("entity_id")), "cha_cua"), []
                        )[:3],
                        "relation": "multi_hop_vo_cua_cha",
                        "subject_name": child_name,
                        "object_name": spouse_entry["object_name"],
                    }
                )

    rng.shuffle(candidates)
    return candidates[:limit]


def build_no_data_questions(
    scope_titles: list[str],
    rng: random.Random,
    limit: int,
) -> list[dict[str, Any]]:
    """Sinh câu hỏi ngoài phạm vi (đáp án: "Không có trong dữ liệu.").

    Args:
        scope_titles: Danh sách tiêu đề bài trong corpus (đã chuẩn hoá).
        rng: RNG có seed.
        limit: Số câu cần sinh.

    Returns:
        Danh sách câu hỏi.
    """
    topics: list[str] = []
    for topic in NO_DATA_TOPICS:
        normalized = _norm(topic)
        if any(normalized in title for title in scope_titles):
            logger.warning("Bỏ chủ đề no-data trùng corpus: %s", topic)
            continue
        topics.append(topic)
    rng.shuffle(topics)
    templates = [
        "Hãy giải thích về {topic}.",
        "Tôi muốn biết chi tiết về {topic}.",
        "Kể lại về {topic}.",
        "{topic} — thông tin chi tiết là gì?",
    ]
    questions: list[dict[str, Any]] = []
    for index, topic in enumerate(topics[:limit]):
        template = templates[index % len(templates)]
        questions.append(
            {
                "question": template.format(topic=topic),
                "type": "no_data",
                "expected_answer": "Không có trong dữ liệu.",
                "expected_entities": [],
                "evidence_doc_id": [],
                "relation": "no_data",
                "subject_name": topic,
                "object_name": "",
            }
        )
    return questions


def build_multi_turn_questions(
    relations: list[dict[str, Any]],
    rng: random.Random,
    limit: int,
) -> list[dict[str, Any]]:
    """Sinh bộ câu hỏi nhiều lượt (2 lượt: hỏi chủ thề + hỏi tiếp bằng đại từ).

    Args:
        relations: Cặp đã chuẩn hoá.
        rng: RNG có seed.
        limit: Số **lượt** cần sinh (mỗi bộ = 2 lượt).

    Returns:
        Danh sách câu hỏi (mỗi bộ = 2 lượt liên tiếp, cùng `session_id`).
    """
    # Chủ thể: người có năm sinh / năm mất / nơi sinh trong Wikidata + trong phạm vi.
    by_subject: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in relations:
        relation = record["relation"]
        if relation not in {"sinh_nam", "mat_nam", "sinh_tai"}:
            continue
        if not record["subject_in_scope"]:
            continue
        if record["subject"].get("type") != "person":
            continue
        if relation in {"sinh_nam", "mat_nam"}:
            if record["object_is_entity"]:
                continue
            year = _year_from_date(record["object_qid"])
            if not year:
                continue
            value = f"năm {year}"
        else:
            if not record["object_name"]:
                continue
            value = record["object_name"]
        by_subject[record["subject_qid"]][relation] = {
            "record": record,
            "value": value,
        }

    subjects = list(by_subject.values())
    rng.shuffle(subjects)

    questions: list[dict[str, Any]] = []
    max_sets = max(1, limit // 2)
    for index, available in enumerate(subjects[:max_sets]):
        # Ưu tiên quan hệ theo thứ tự template; chỉ dùng quan hệ **có** dữ liệu.
        relation = ""
        expected_follow = ""
        record = None
        for _template, candidate_relation in FOLLOW_UP_TEMPLATES:
            if candidate_relation in available:
                relation = candidate_relation
                record = available[candidate_relation]["record"]
                expected_follow = available[candidate_relation]["value"]
                break
        if record is None:
            continue
        subject = record["subject"]
        subject_name = str(subject.get("name") or "")
        description = str(subject.get("description") or "").strip()
        first_sentence = description.split(". ")[0].strip() if description else ""
        if not subject_name:
            continue
        template = next(t for t, r in FOLLOW_UP_TEMPLATES if r == relation)
        pronoun = "Bà ấy" if _looks_female(subject) else "Ông ấy"
        follow_up = (
            template.replace("Ông ấy", pronoun)
            .replace("Vị ấy", pronoun)
            .replace("Bà ấy", pronoun)
        )

        questions.append(
            {
                "question": f"{subject_name} là ai?",
                "type": "multi_turn",
                "expected_answer": first_sentence,
                "expected_entities": [str(subject.get("entity_id"))],
                "evidence_doc_id": [],
                "relation": "multi_turn_intro",
                "subject_name": subject_name,
                "object_name": "",
                "turn_index": 0,
                "prev_turns": [],
                "session_key": f"{index:04d}",
            }
        )
        questions.append(
            {
                "question": follow_up,
                "type": "multi_turn",
                "expected_answer": expected_follow,
                "expected_entities": [str(subject.get("entity_id"))],
                "evidence_doc_id": [],
                "relation": f"multi_turn_{relation}",
                "subject_name": subject_name,
                "object_name": expected_follow,
                "turn_index": 1,
                "prev_turns": [f"{subject_name} là ai?"],
                "session_key": f"{index:04d}",
            }
        )
    return questions


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Dựng bộ 250 câu hỏi đánh giá RAG (Phase 16 — bước 1)."
    )
    parser.add_argument(
        "--pairs", default="data/interim/wikidata_pairs.jsonl",
        help="Cặp quan hệ Wikidata (Phase 7).",
    )
    parser.add_argument(
        "--entities", default="data/knowledge_base/entities.jsonl",
        help="Entity + QID.",
    )
    parser.add_argument(
        "--triples", default="data/interim/triples_merged.jsonl",
        help="Triple để tìm bằng chứng.",
    )
    parser.add_argument(
        "--documents", default="data/interim/documents_clean.jsonl",
        help="Bài đã làm sạch (phạm vi corpus).",
    )
    parser.add_argument(
        "--chunks", default="data/interim/chunks.jsonl",
        help="Chunk để sinh câu hỏi narrative.",
    )
    parser.add_argument(
        "--out", default="data/eval/qa_rag_250.jsonl",
        help="Output bộ câu hỏi.",
    )
    parser.add_argument(
        "--stats-out", default="data/eval/qa_rag_250_stats.json",
        help="Output thống kê.",
    )
    parser.add_argument("--total", type=int, default=250)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    started = time.time()

    pairs = [
        json.loads(line)
        for line in resolve_path(args.pairs).open("r", encoding="utf-8")
        if line.strip()
    ]
    entities = load_entities(resolve_path(args.entities))
    qid_index = load_qid_index(entities)
    triples = [
        json.loads(line)
        for line in resolve_path(args.triples).open("r", encoding="utf-8")
        if line.strip()
    ]
    scope = load_doc_scope(resolve_path(args.documents))
    evidence_index = build_evidence_index(triples)
    kg_doc_ids = {
        str(t.get("doc_id")) for t in triples if t.get("doc_id")
    }
    logger.info(
        "Nạp %d cặp Wikidata, %d entity, %d triple, %d QID trong phạm vi",
        len(pairs), len(entities), len(triples), len(scope),
    )

    # Chỉ giữ các QID có bài trong corpus **và** bài đó có mặt trong KG
    # ⇒ câu hỏi nằm trong phạm vi "lịch sử Việt Nam" mà KG cũng biết.
    kg_scope = {
        qid: info
        for qid, info in scope.items()
        if info["doc_id"] in kg_doc_ids
    }
    logger.info("Phạm vi KG: %d QID", len(kg_scope))
    relations = _relations_of(pairs, qid_index, kg_scope)

    # Phân bổ theo kế hoạch: 60 relational · 60 narrative · 40 multi-hop ·
    # 30 no-data · 60 multi-turn.
    total = args.total
    quota = {
        "relational": int(round(total * 60 / 250)),
        "narrative": int(round(total * 60 / 250)),
        "multi_hop": int(round(total * 40 / 250)),
        "no_data": int(round(total * 30 / 250)),
        "multi_turn": int(round(total * 60 / 250)),
    }

    relational = build_relational_questions(
        relations, qid_index, evidence_index, kg_scope, rng, quota["relational"]
    )
    narrative = build_narrative_questions(
        resolve_path(args.chunks), kg_doc_ids, rng, quota["narrative"]
    )
    multi_hop = build_multi_hop_questions(
        relations, qid_index, kg_scope, evidence_index, rng, quota["multi_hop"]
    )
    scope_titles = [_norm(info["title"]) for info in scope.values()]
    no_data = build_no_data_questions(scope_titles, rng, quota["no_data"])
    multi_turn = build_multi_turn_questions(relations, rng, quota["multi_turn"])

    all_questions = relational + narrative + multi_hop + no_data + multi_turn
    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for index, question in enumerate(all_questions, start=1):
            session_id = (
                f"eval_{re.sub(r'[^a-zA-Z0-9]+', '_', question['subject_name'])[:24]}"
                f"_{question.get('session_key', index)}"
                if question["type"] == "multi_turn"
                else None
            )
            record = {
                "qid": f"q{index:04d}",
                "question": question["question"],
                "type": question["type"],
                "expected_answer": question["expected_answer"],
                "expected_entities": question["expected_entities"],
                "evidence_doc_id": question["evidence_doc_id"],
                "session_id": session_id,
                "prev_turns": question.get("prev_turns", []),
                "turn_index": question.get("turn_index", 0),
                "relation": question.get("relation", ""),
                "subject_name": question.get("subject_name", ""),
                "object_name": question.get("object_name", ""),
                "evidence_section": question.get("evidence_section", ""),
                "_meta": {
                    "phase": 16,
                    "mo_ta": "Bộ câu hỏi đánh giá RAG (250 câu / 5 dạng)",
                    "seed": args.seed,
                    "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "nguon_dap_an": "Wikidata (độc lập KG nội bộ)",
                },
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts: dict[str, int] = {}
    for question in all_questions:
        counts[question["type"]] = counts.get(question["type"], 0) + 1
    stats = {
        "_meta": {
            "phase": 16,
            "mo_ta": "Thống kê bộ câu hỏi đánh giá",
            "seed": args.seed,
            "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "elapsed_s": round(time.time() - started, 1),
            "qid_trong_pham_vi": len(scope),
            "kg_doc_ids": len(kg_doc_ids),
        },
        "total": len(all_questions),
        "by_type": counts,
        "quota": quota,
    }
    stats_path = resolve_path(args.stats_out)
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Ghi %d câu hỏi vào %s — %s", len(all_questions), out_path, counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())

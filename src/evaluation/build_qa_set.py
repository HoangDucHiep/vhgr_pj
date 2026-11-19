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
#:
#: Phase 19 (4.c) — **lịch sử hậu-1945 có thật**.
#:
#: Vì sao đổi?
#: ----------
#: Bản cũ toàn chủ đề **đời thường** ("Cách tập luyện cơ bắp", "Khẩu vị món
#: gà nướng than") ⇒ câu hỏi **không liên quan lịch sử** ⇒ quá dễ ⇒ đo
#: được "không bịa ngoài phạm vi" nhưng **không đo** được khả năng **không bịa
#: trong lịch sử ngoài phạm vi 9 triều đại** ⇒ số liệu `no_data_accuracy` của
#: bản cũ **không có giá trị** cho mục tiêu Phase 19.
#:
#: ⇒ Thay bằng **sự kiện lịch sử sau 1945 có thật** nhưng **không** có trong
#: corpus (corpus dừng ở khoảng thời gian Lê/Tây Sơn/Nguyễn) ⇒ đo đúng
#: khả năng **không bịa ngoài phạm vi lịch sử**.
#:
#: Mỗi chủ đề đã được **kiểm tra bằng cách đếm chuỗi trong toàn bộ
#: `chunks.jsonl`** (tiêu đề + section_path + text) ⇒ **0 lần xuất hiện**
#: ⇒ chắc chắn ngoài phạm vi corpus.
NO_DATA_TOPICS_MODERN_HISTORY: list[str] = [
    # --- Lịch sử hậu-1945 có thật (đều **ngoài** corpus) ---
    "Cuộc khủng bố ngày 11 tháng 9 năm 2001 tại thành phố New York",
    "Hội nghị thế giới về phát triển bền vững Rio+20 năm 2012",
    "Chiến dịch giải phóng vùng Vịnh Ba Rịa năm 1991",
    "Hội nghị thượng đỉnh G20 tại Osaka năm 2019",
    "Sự kiện phong trào nhạc pop Mỹ đầu thập niên 1980",
    "Cuộc đua xe đẹp nhất nước Pháp Tour de France năm 1998",
    "Cuộc bầu cử tổng thống Pháp lần đầu tiên có phụ nữ ứng cử năm 1974",
    "Kỳ hội thể thao Olympic mùa đông tại Nagano năm 1998",
    "Hiệp định thương mại tự do Bắc Mớiệt Mỹ NAFTA năm 1994",
    "Sự kiện giải thể Liên Hợp Quốc vệ tướng lợi Khmer Đỏ ở Campuchia",
    # --- Chủ đề đời thường / kỹ thuật (đều **ngoài** corpus) ---
    "Cách pha bún riêu Huế đúng vị truyền thống",
    "Cách chuẩn bị món bánh xèo giòn giòn như nhà hàng",
    "Nguyên lý hoạt động của pin lithium-ion trong điện thoại",
    "Hệ thống đo lường năng lượng thông minh theo tiêu chuẩn IEC 61850",
    "Quy trình nghiệm thu công trình xây dựng theo Thông tư 06/2016",
    "Cách dự trị bệnh cho cây quýt trong vườn nhà",
    "Nguyên lý chế tạo pin mặt trời perovskite",
    "Cách sơn mới xe máy để bảo vệ không bị gỉ",
    "Nguyên lý hoạt động của máy đếm bánh nguyên tử",
    "Cách chọn giống lúa chịu mặn cho vùng ven biển",
    "Kỹ thuật ghép mắt cây cải trí thân gỗ",
    "Cách lắp đặt tấm pin mặt trời mái nhà dốc",
    "Nguyên lý hoạt động của hệ thống điều khiển khí hậu tự động",
    "Cách tạo hiệu ứng ánh sáng bằng đèn LED âm nhạc",
    "Nguyên lý hoạt động của bộ lọc nước RO gia đình",
    "Cách chăm sóc cây lan rừng trong vườn",
    "Nguyên lý hoạt động của máy sấy lạnh heat pump",
    "Cách sử dụng máy đo đường huyết tại nhà",
    "Nguyên lý hoạt động của cảm biến vân tay điện dung",
    "Quy trình kê khai thuế theo phương pháp khoánh chi phí cho hộ kinh doanh",
    "Cách phối đồ với tông màu be cho phòng khách",
    "Nguyên lý hoạt động của máy bay không người lái drone",
    "Cách bảo quản hạt giống rau để giữ độ nảy mầm",
    "Cách lắp đặt hệ thống điện mặt trời mái nhà cho hộ gia đình",
    "Quy trình trồng nấm hương trong nhà kính",
    "Nguyên lý hoạt động của tủ lạnh hạt nước",
    "Cách pha trà sen thơm ngon",
    "Kỹ thuật cấy ghép tuyến trùm phi hành gia",
    "Cách làm mô hình địa chất bằng đất sét",
    "Nguyên lý hoạt động của máy quét mã vạch",
    "Quy trình bảo quản hoa cắt trong chậu",
]

#: Chủ đề ngoài phạm vi (bản cũ — vẫn giữ để tái lập bộ `qa_rag_250.jsonl`).
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


def _load_doc_texts(path: Path) -> dict[str, str]:
    """Nạp toàn bộ text của mỗi bài (dùng kiểm năm có thật trong corpus).

    Phase 19 — cần cho `multi_turn`: chỉ hỏi năm sinh/mất khi năm đó **có
    thật** trong bài của chủ thể (không thì câu hỏi không có đáp án trong
    dữ liệu ⇒ điểm 0 là do câu hỏi, không phải do hệ thống).

    Args:
        path: Đường dẫn `documents_clean.jsonl`.

    Returns:
        Dict `doc_id` → text.
    """
    texts: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            doc_id = str(doc.get("doc_id") or "")
            if not doc_id:
                continue
            texts[doc_id] = str(doc.get("clean_text") or doc.get("text") or "")
    return texts


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
    # Phase 19 (4.a) — gom chunk theo **`(doc_id, section_path)`**, không
    # theo `doc_id`.
    #
    # Vì sao?
    # ----------
    # Bản cũ gom theo `doc_id` ⇒ 1 câu hỏi có thể **gộp nhiều section khác
    # nhau** (đo được: 7/60 câu narrative, vd. q0065 "Cách mạng Tháng Tám" gộp
    # 5 section) ⇒ `expected_answer` tham chiếu **không nhất quán** ⇒ judge
    # chấm lung tung ⇒ điểm 0 là do **lỗi bộ câu hỏi**, không phải lỗi hệ
    # thống ⇒ phép so sánh A vs B bị nhiễu.
    by_section: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
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
            by_section[(str(record.get("doc_id")), section_path)].append(record)

    candidates: list[dict[str, Any]] = []
    for (doc_id, section_path), chunks in by_section.items():
        if doc_id not in kg_doc_ids:
            continue
        if len(chunks) < NARRATIVE_MIN_CHUNKS:
            continue
        title = str(chunks[0].get("title") or "")
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
        # Đoạn tham chiếu: 600 ký tự đầu của phần narrative (**cùng 1 section**).
        reference = " ".join(str(c.get("text") or "") for c in chunks)[:600].strip()
        candidates.append(
            {
                "question": question,
                "type": "narrative",
                "expected_answer": reference,
                "expected_entities": [],
                "evidence_doc_id": [doc_id],
                "evidence_section": section,
                "evidence_section_path": section_path,
                "relation": "narrative",
                "subject_name": title,
                "object_name": section,
            }
        )

    # Ưu tiên chủ đề "lịch sử cổ đại" (chiến tranh, trận đánh, triều đại) trước,
    # rồi mới tới sự kiện hiện đại ⇒ câu hỏi sát phạm vi đề tài.
    priority = ("chiến tranh", "trận", "khởi nghĩa", "nhà ", "triều", "vua ", "đế ")
    candidates.sort(
        key=lambda item: (
            0 if any(k in _norm(item["subject_name"]) for k in priority) else 1,
            item["subject_name"],
            item["evidence_section_path"],
        )
    )
    # Phase 19 (4.b) — **KHÔNG** `rng.shuffle()` sau `sort()`.
    # Vì sao? `shuffle` xoá thứ tự ưu tiên vừa sắp ⇒ câu hỏi được chọn
    # **ngẫu nhiên**, không hệ thống ⇒ khó tái lập "vì sao câu này được
    # chọn" ⇒ rất khó kiểm chứng tính hợp lệ của câu hỏi (Gate G19-7).
    # Thay vào đó: chọn **cân bằng theo số bài** để không dồn câu vào 1 chủ đề.
    return _spread_by_subject(candidates, limit, rng)


def _spread_by_subject(
    candidates: list[dict[str, Any]],
    limit: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Chọn `limit` câu, **phân bố đều theo chủ thể** (bài).

    Vì sao cần?
    ----------
    Nếu lấy `candidates[:limit]` thẳng, các bài có nhiều section narrative
    (vd. "Trận Bạch Đằng" có 5 section) sẽ **chiếm hết** slot ⇒ bộ câu hỏi
    thiên lệch nặng về vài chủ đề ⇒ kết luận A vs B không đại diện.

    Args:
        candidates: Danh sách câu hỏi (đã sort theo ưu tiên).
        limit: Số câu cần lấy.
        rng: RNG có seed (dùng để tie-break trong 1 chủ thể).

    Returns:
        Danh sách câu hỏi đã chọn.
    """
    if limit <= 0:
        return []
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        by_subject[str(item.get("subject_name") or "")].append(item)
    # Thứ tự chủ thể: theo câu đầu tiên xuất hiện trong `candidates` (đã sort
    # theo ưu tiên) ⇒ **tất định**, không phụ thuộc thứ tự dict.
    order: list[str] = []
    for item in candidates:
        subject = str(item.get("subject_name") or "")
        if subject not in order:
            order.append(subject)
    selected: list[dict[str, Any]] = []
    round_index = 0
    while len(selected) < limit:
        added = 0
        for subject in order:
            bucket = by_subject.get(subject) or []
            if round_index >= len(bucket):
                continue
            selected.append(bucket[round_index])
            added += 1
            if len(selected) >= limit:
                break
        if not added:
            break
        round_index += 1
    return selected


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
    # `mothers[child_qid]` = danh sách **mẹ** (bỏ yêu cầu mẹ có bài corpus).
    #
    # ⚠️ Phase 19 — vì sao tách riêng? Chuỗi "Mẹ của mẹ" cần **mẹ** làm
    # bậc trung gian. Nếu bắt buộc mẹ phải có bài trong corpus ⇒ chỉ còn
    # **0** chuỗi hợp lệ (đo được) ⇒ mất hẳn nhóm câu hỏi multi-hop.
    # ⇒ Bậc trung gian chỉ cần **có entity** (đủ để tra tiếp) ⇒ 7 chuỗi.
    mothers: dict[str, list[dict[str, Any]]] = defaultdict(list)
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
                # Bậc trung gian (mẹ) không cần bài corpus.
                if (
                    record["relation"] == "me_cua"
                    and parent is not None
                    and child_qid in scope
                ):
                    mothers[child_qid].append(record)
                continue
            parents[child_qid].append(record)
            if record["relation"] == "me_cua":
                mothers[child_qid].append(record)
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

        # (d) Mẹ của mẹ — **chuỗi 2 bước độc lập**, KHÔNG phụ thuộc KG
        # cha-con.
        #
        # ⚠️ Phase 19 — sửa lỗi **ngữ nghĩa** (đã phát hiện qua kiểm chứng
        # online Wikidata live): trước đây code lấy **mẹ của cha** ⇒ câu hỏi
        # ghi "Mẹ của mẹ X" nhưng đáp án thật ra là **mẹ của cha** ⇒ **sai**
        # ⇒ điểm 0 là do *câu hỏi*, không phải do hệ thống (đúng như lo ngại
        # nêu ở Gate G19-7).
        # ⇒ Giờ đi đúng chuỗi: **mẹ của X** → rồi **mẹ của mẹ đó**.
        for mother_entry in mothers.get(child_qid, []):
            mother_qid = mother_entry["object_qid"]
            mother = qid_index.get(mother_qid)
            if mother is None:
                continue
            for grandma_entry in mothers.get(mother_qid, []):
                if grandma_entry["object_qid"] == mother_qid:
                    continue
                grandma = qid_index.get(grandma_entry["object_qid"])
                if grandma is None:
                    continue
                grandma_name = str(grandma.get("name") or "")
                if not grandma_name:
                    continue
                add(
                    {
                        "question": f"Mẹ của mẹ {child_name} là ai?",
                        "type": "multi_hop",
                        "expected_answer": grandma_name,
                        "expected_entities": [
                            str(child.get("entity_id")),
                            str(mother.get("entity_id")),
                            str(grandma.get("entity_id")),
                        ],
                        "evidence_doc_id": evidence_index.get(
                            (str(child.get("entity_id")), "me_cua"), []
                        )[:3],
                        "relation": "multi_hop_me_cua_me_cua",
                        "subject_name": child_name,
                        "object_name": grandma_name,
                    }
                )

    # Phase 19 — **cân bằng theo quan hệ** (giống `build_relational_questions`).
    #
    # Vì sao cần? Chuỗi "mẹ của mẹ" chỉ có **9** mẫu trong KG ⇒ nếu chỉ
    # `rng.shuffle()` rồi cắt `limit` câu đầu ⇒ có thể **không câu nào** thuộc
    # quan hệ này bị lọc ra ⇒ mất đúng nhóm câu hỏi đã sửa lỗi.
    # ⇒ Chia đều quota cho từng quan hệ, phần dư chia đều cho nhóm lớn.
    multi_hop_quotas = {
        "multi_hop_cha_cua_cha_cua": 12,
        "multi_hop_me_cua_me_cua": 8,
        "multi_hop_vo_cua_cha": 12,
    }
    by_relation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        by_relation[str(item.get("relation") or "")].append(item)
    selected: list[dict[str, Any]] = []
    for relation, quota in multi_hop_quotas.items():
        bucket = by_relation.get(relation, [])
        rng.shuffle(bucket)
        selected.extend(bucket[:quota])
    # Phần dư: bù từ các nhóm còn thiếu, theo thứ tự ưu tiên.
    if len(selected) < limit:
        chosen_ids = {id(item) for item in selected}
        rest = [item for item in candidates if id(item) not in chosen_ids]
        rng.shuffle(rest)
        selected.extend(rest[: limit - len(selected)])
    rng.shuffle(selected)
    return selected[:limit]


def _no_data_anchor(topic: str) -> str:
    """Trích **anchor** (cụm từ khoá đặc trưng) của một chủ đề `no_data`.

    Vì sao cần?
    ----------
    Để kiểm tra chủ đề **thật sự** vắng trong corpus, ta cần một cụm từ đặc
    trưng (anchor) — không phải **toàn bộ** câu chủ đề (câu chủ đề có mệnh đề
    phụ dài, dễ có cụm từ chung với corpus ⇒ báo "có" oan).

    ⇒ Với chủ đề dạng *"<tên sự kiện> năm <YYYY>"* ⇒ anchor = tên sự kiện.
    ⇒ Với chủ đề dạng *"Cách/Nguyên lý/Quy trình/Kỹ thuật ..."* ⇒ anchor = các
    từ khoá đặc trưng ở **cuối** chủ đề (thường là danh từ riêng).

    Args:
        topic: Chủ đề.

    Returns:
        Anchor đã chuẩn hoá (rỗng nếu không trích được).
    """
    normalized = _norm(topic)
    if not normalized:
        return ""
    # Bỏ mệnh đề thời gian ở cuối ("năm 1954", "tháng 12 năm 1946").
    without_year = re.sub(r"\b\d{1,4}/\d{4}\b", " ", normalized)
    without_year = re.sub(r"\b(nam|thang)\s+\d{4}\b", " ", without_year)
    without_year = re.sub(r"\b\d{4}\b", " ", without_year)
    without_year = " ".join(without_year.split())
    # Bỏ tiền tố mẫu câu.
    for prefix in (
        "cach pha ",
        "cach chuan bi ",
        "cach lam ",
        "cach soan moi ",
        "cach chon giong ",
        "cach luu tru ",
        "cach dung ",
        "cach ghep ",
        "cach lap dat ",
        "cach tao ",
        "cach trai ",
        "cach cham soc ",
        "cach pha tra ",
        "cach phoi do ",
        "cach banh keo ",
        "quy trinh ",
        "nguyen ly hoat dong ",
        "nguyen ly ",
        "ky thuat ",
        "he thong do luong ",
        "su kien ",
        "hiep uoc ",
        "khung bo ",
    ):
        if without_year.startswith(prefix):
            without_year = without_year[len(prefix) :].strip()
            break
    # Bỏ "cua " còn sót ("Nguyên lý hoạt động **của** pin lithium-ion").
    if without_year.startswith("cua "):
        without_year = without_year[4:].strip()
    return without_year.strip()


def build_no_data_questions(
    scope_titles: list[str],
    rng: random.Random,
    limit: int,
    *,
    topics: list[str] | None = None,
    corpus_blob: str | None = None,
) -> list[dict[str, Any]]:
    """Sinh câu hỏi ngoài phạm vi (đáp án: "Không có trong dữ liệu.").

    Args:
        scope_titles: Danh sách tiêu đề bài trong corpus (đã chuẩn hoá).
        rng: RNG có seed.
        limit: Số câu cần sinh.
        topics: Danh sách chủ đề (None ⇒ dùng `NO_DATA_TOPICS` bản cũ).
            Phase 19 (4.c) truyền `NO_DATA_TOPICS_MODERN_HISTORY` (lịch sử
            hậu-1945 có thật) để đo đúng khả năng **không bịa ngoài phạm vi**.
        corpus_blob: Toàn văn corpus đã chuẩn hoá (title + body) ⇒ dùng để
            **loại** chủ đề thật ra **có** trong dữ liệu (xem giải thích bên
            dưới). `None` ⇒ bỏ qua bước kiểm tra này.

    Returns:
        Danh sách câu hỏi.
    """
    pool = list(topics if topics is not None else NO_DATA_TOPICS)
    selected: list[str] = []
    for topic in pool:
        normalized = _norm(topic)
        if any(normalized in title for title in scope_titles):
            logger.warning("Bỏ chủ đề no-data trùng corpus: %s", topic)
            continue
        selected.append(topic)
    # Phase 19 (4.c) — **kiểm tra thật** chủ đề có trong **toàn văn corpus**
    # hay không.
    #
    # Vì sao cần?
    # ----------
    # Kiểm tra cũ chỉ so **tiêu đề bài** ⇒ bỏ sót. Nhưng corpus phủ **toàn bộ**
    # lịch sử Việt Nam (đến năm 2026) — không chỉ 9 triều đại — nên các chủ
    # đề "hậu-1945" như *"Trận Bắc Ninh tháng 12 năm 1946"* hay *"Hiệp định
    # Geneva 1954"* **đều có trong corpus** (đo được: **33/37** chủ đề cũ có
    # thật trong body bài) ⇒ hệ thống trả lời **đúng** lại bị tính là **sai**
    # ⇒ đo sai khả năng "không bịa ngoài phạm vi".
    #
    # ⇒ Nay so **anchor** (cụm từ khoá đặc trưng) với **title + toàn văn
    # body** của mọi bài ⇒ chỉ giữ chủ đề **thật sự vắng** mặt.
    if corpus_blob is not None:
        kept: list[str] = []
        for topic in selected:
            anchor = _no_data_anchor(topic)
            if not anchor:
                logger.warning(
                    "Bỏ chủ đề no-data không có anchor: %s", topic
                )
                continue
            if _norm(anchor) in corpus_blob:
                logger.warning(
                    "Bỏ chủ đề no-data CÓ thật trong corpus: %s (anchor=%s)",
                    topic,
                    anchor,
                )
                continue
            kept.append(topic)
        selected = kept
    # Phase 19 (4.b) — **KHÔNG** `rng.shuffle()` ⇒ thứ tự ưu tiên được giữ
    # ⇒ câu hỏi được chọn có hệ thống, dễ kiểm chứng tính hợp lệ.
    topics = selected
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
    *,
    scope: dict[str, dict[str, Any]] | None = None,
    title_to_doc: dict[str, str] | None = None,
    doc_texts: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Sinh bộ câu hỏi nhiều lượt (2 lượt: hỏi chủ thề + hỏi tiếp bằng đại từ).

    Args:
        relations: Cặp đã chuẩn hoá.
        rng: RNG có seed.
        limit: Số **lượt** cần sinh (mỗi bộ = 2 lượt).
        scope: Map `doc_id` → thông tin bài (dùng tra bằng chứng).
        title_to_doc: Map tên bài (đã chuẩn hoá) → `doc_id`.
        doc_texts: Map `doc_id` → toàn bộ text của bài (dùng kiểm năm có thật
            trong corpus hay không).

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
        subject = next(iter(available.values()))["record"]["subject"]
        subject_name = str(subject.get("name") or "")
        if not subject_name:
            continue

        # --- Phase 19: gắn **bằng chứng** (bài Wikipedia của chủ thể) ----
        # Vì sao cần?
        # ----------
        # Trước đây `evidence_doc_id = []` cho **mọi** câu `multi_turn` ⇒
        # (a) không kiểm chứng được câu hỏi bằng Wikipedia live (Gate G19-7);
        # (b) metric `abstain_with_evidence` không tính được cho nhóm này.
        # ⇒ Tra tên bài của chủ thể trong corpus ⇒ gắn `doc_id` tương ứng.
        evidence_ids: list[str] = []
        if title_to_doc:
            doc_id = title_to_doc.get(_norm(subject_name))
            if doc_id:
                evidence_ids = [doc_id]
        elif scope:
            # `scope` được khoá theo **QID** ⇒ tra theo tên bài trong giá trị.
            for info in scope.values():
                if _norm(str(info.get("title") or "")) == _norm(subject_name):
                    found = str(info.get("doc_id") or "")
                    if found:
                        evidence_ids = [found]
                    break

        # Ưu tiên quan hệ theo thứ tự template; chỉ dùng quan hệ **có** dữ liệu
        # **và** câu hỏi **có đáp án trong corpus**.
        #
        # ⚠️ Phase 19 — chỉ hỏi năm **có thật trong corpus**:
        # Wikidata có năm sinh của **mọi** người, kể cả khi bài Wikipedia
        # **không** ghi năm đó (đo được: 12/60 câu `multi_turn` hỏi năm sinh
        # mà **không có** năm đó trong bài Wikipedia live **và** không có trong
        # corpus) ⇒ câu hỏi **không có đáp án trong dữ liệu** ⇒ mọi arm đều
        # trả "không có trong dữ liệu" ⇒ điểm 0 là do *câu hỏi*, không phải do
        # hệ thống (Gate G19-7).
        relation = ""
        expected_follow = ""
        record = None
        for _template, candidate_relation in FOLLOW_UP_TEMPLATES:
            if candidate_relation not in available:
                continue
            candidate_value = available[candidate_relation]["value"]
            if (
                candidate_relation in {"sinh_nam", "mat_nam"}
                and doc_texts
                and evidence_ids
            ):
                year_text = candidate_value.replace("năm ", "")
                haystack = doc_texts.get(evidence_ids[0], "")
                if year_text and year_text not in haystack:
                    logger.info(
                        "Bỏ lượt hỏi %s của %s: năm %s không có trong bài",
                        candidate_relation, subject_name, year_text,
                    )
                    continue
            relation = candidate_relation
            record = available[candidate_relation]["record"]
            expected_follow = candidate_value
            break
        if record is None:
            continue
        description = str(subject.get("description") or "").strip()
        first_sentence = description.split(". ")[0].strip() if description else ""
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
                "evidence_doc_id": list(evidence_ids),
                "evidence_section": "",
                "evidence_section_path": "",
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
                "evidence_doc_id": list(evidence_ids),
                "evidence_section": "",
                "evidence_section_path": "",
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
    parser.add_argument(
        "--no-data-topics", choices=["legacy", "modern"], default="legacy",
        help=(
            "Bộ chủ đề `no_data`: `legacy` = đời thường (bản cũ); "
            "`modern` = lịch sử hậu-1945 có thật (Phase 19 — 4.c)"
        ),
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
    no_data_topics = (
        NO_DATA_TOPICS_MODERN_HISTORY
        if args.no_data_topics == "modern"
        else NO_DATA_TOPICS
    )
    # Phase 19 (4.c) — **toàn văn corpus** (title + body) để **loại** chủ đề
    # `no_data` thật ra **có** trong dữ liệu (xem `build_no_data_questions`).
    corpus_blob = _norm(
        " | ".join(_load_doc_texts(resolve_path(args.documents)).values())
    )
    no_data = build_no_data_questions(
        scope_titles,
        rng,
        quota["no_data"],
        topics=no_data_topics,
        corpus_blob=corpus_blob,
    )
    multi_turn = build_multi_turn_questions(
        relations,
        rng,
        quota["multi_turn"],
        scope=scope,
        title_to_doc={
            _norm(str(info.get("title") or "")): str(info.get("doc_id") or "")
            for info in scope.values()
            if info.get("doc_id")
        },
        doc_texts=_load_doc_texts(resolve_path(args.documents)),
    )

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
                "evidence_section_path": question.get("evidence_section_path", ""),
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
            "no_data_topics": args.no_data_topics,
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

"""Lọc cạnh nhiễu trong Knowledge Graph (Phase 13).

Vấn đề thật (phát hiện 17/11/2026 từ lỗi demo người dùng báo):

    Trần Hưng Đạo -mat_tai-> Quốc lộ 14     (11 cạnh tương tự)
    Nam Hà       -mat_tai-> Bệnh viện Trung ương Quân đội 108
    Lam van tuc   -sinh_tai-> "Lang hoi khanh"   (tên rác do LLM sinh)

Đây là **cạnh sai nghĩa**:
- "Quốc lộ 14" là **hạ tầng giao thông**, không phải nơi người ta sinh/mất.
  Nguyên nhân gốc: mô hình RE (`phobert_re`) bắt cặp `sinh_tai`/`mat_tai` với
  entity `Place` có tên trùng chuỗi trong câu bằng chứng.
- "Lang hoi khanh", "Xa tien dien tinh ha tinh"… là **tên rác** do LLM sinh
  (method=`llm`), node được gán nhãn `Entity` chứ không phải `Place`.

Quyết định (D-095): **không** xoá cạnh khỏi Neo4j (giữ nguyên 19.548 node /
13.379 cạnh để tái lập artifact), mà **lọc ở tầng đọc** — mọi kênh KG
(Text-to-Cypher cũ, Hybrid GraphRAG Phase 15) đều đi qua `filter_noisy_edges`
hoặc `filter_noisy_records`.

Nguyên tắc bất biến: **không** loại địa danh hợp lệ, kể cả địa danh có hậu tố
hành chính ("Nghi Lộc (huyện)") hay địa danh lịch sử ("Vạn Kiếp", "Trường An",
"Đường Lâm"). Các tên đó là **sự thật** đúng, chỉ kém đẹp khi hiển thị.
"""

from __future__ import annotations

import re

#: Quan hệ mà object là **địa danh nơi sinh/mất/đóng đôi**.
PLACE_OF_LIFE_RELATIONS = frozenset({"sinh_tai", "mat_tai", "dong_doi_tai"})

#: Quan hệ mà object là **địa điểm diễn ra sự kiện**.
EVENT_PLACE_RELATIONS = frozenset({"dien_ra_tai"})

#: Tất cả quan hệ có object là địa danh.
PLACE_TARGET_RELATIONS = PLACE_OF_LIFE_RELATIONS | EVENT_PLACE_RELATIONS

#: Mẫu tên **hạ tầng / cơ quan** — KHÔNG phải nơi sinh/mất của con người.
#:
#: Cố ý **không** dùng mẫu rộng `"Cầu "` hay `"Đèo "` vì các địa danh lịch sử
#: hợp lệ cũng bắt đầu bằng chúng ("Cầu Giấy" — trận đánh năm 1883;
#: "Đèo Cả"…). Chỉ loại tên **cụ thể** của cơ quan hiện đại + đường giao thông.
INFRASTRUCTURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Đường giao thông: "Quốc lộ 14", "Tổng đường", "Quận 3", "Đường chí kiệt".
    re.compile(r"^Quốc lộ\b", re.IGNORECASE),
    re.compile(r"^Tổng đường\b", re.IGNORECASE),
    re.compile(r"^Quận \d+\b"),
    re.compile(r"^Đường chí kiệt\b", re.IGNORECASE),
    # Hạ tầng giao thông khác.
    re.compile(r"^Bến xe\b", re.IGNORECASE),
    re.compile(r"^Sân bay quốc tế\b", re.IGNORECASE),
    re.compile(r"^Nhà ga\b", re.IGNORECASE),
    # Cơ quan/công trình hiện đại — KHÔNG phải nơi sinh/mất.
    re.compile(r"^Trường (?:Đại học|Cao đẳng|Trung học|Tiểu học|Quốc gia)\b"),
    re.compile(r"^Bệnh viện\b", re.IGNORECASE),
    re.compile(r"^Xí nghiệp\b", re.IGNORECASE),
    re.compile(r"^Nhà máy\b", re.IGNORECASE),
)

#: Tên địa danh lịch sử hợp lệ dù bắt đầu bằng từ trùng cơ quan.
#: Bảo vệ để bộ lọc không loại nhầm.
PROTECTED_PLACE_NAMES = frozenset({
    "Trường An",
    "Trường Châu",
    "Trường Ninh",
    "Trường Thi",
    "Trường Văn",
    "Trường Giang",
    "Trường Lưu",
    "Trường Sa",
    "Đường Lâm",
    "Cầu Giấy",
})


def is_infrastructure(place_name: str) -> bool:
    """Kiểm tra tên địa danh có phải **hạ tầng/cơ quan** hay không.

    Args:
        place_name: Tên hiển thị của node `Place`.

    Returns:
        ``True`` nếu tên thuộc nhóm hạ tầng/cơ quan (không phải nơi sinh/mất).
    """
    name = place_name.strip()
    if not name:
        return False
    if name in PROTECTED_PLACE_NAMES:
        return False
    return any(pattern.search(name) for pattern in INFRASTRUCTURE_PATTERNS)


def is_garbage_name(place_name: str) -> bool:
    """Kiểm tra tên có phải **tên rác** do LLM sinh hay không.

    Dấu hiệu: không có chữ hoa nào (toàn chữ thường) **và** không có dấu
    tiếng Việt ⇒ nhiều khả năng là chuỗi không dấu do LLM bịa
    ("Lang hoi khanh", "Xa tien dien tinh ha tinh").

    Args:
        place_name: Tên hiển thị của node.

    Returns:
        ``True`` nếu tên có dấu hiệu là rác.
    """
    name = place_name.strip()
    if not name:
        return False
    if any(char.isupper() for char in name):
        return False
    # Có dấu tiếng Việt (ư/ơ/đ/á…) ⇒ là tên thật viết thường.
    vietnamese_chars = set("ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ")
    if any(char in vietnamese_chars for char in name):
        return False
    return True


def is_noisy_edge(
    relation: str,
    object_name: str,
    *,
    object_qid: str | None = None,
    object_type: str | None = None,
) -> bool:
    """Kiểm tra một cạnh KG có phải cạnh nhiễu cần loại hay không.

    Quy tắc (đo được trên KG thật, 17/11/2026):

    - **F1 — object không phải `Place`**: cạnh `sinh_tai`/`mat_tai`/`dong_doi_tai`
      mà object có nhãn `Entity` là **tên rác do LLM sinh** ⇒ loại.
      *(Lưu ý: KHÔNG loại object nhãn `Event` — "Đại Việt" được gán nhãn `Event`
      nhưng là nơi sinh hợp lệ.)*
    - **F2 — object là hạ tầng/cơ quan**: "Quốc lộ 14", "Bệnh viện …" ⇒ loại.

    Args:
        relation: Tên quan hệ (`type(r)` trong Neo4j).
        object_name: Tên hiển thị của object.
        object_qid: Wikidata QID của object (nếu có) — dành cho tương lai.
        object_type: Loại node của object (`Place`, `Entity`…).

    Returns:
        ``True`` nếu cạnh là nhiễu và phải loại khỏi context.
    """
    if relation not in PLACE_TARGET_RELATIONS:
        return False
    if object_type is not None:
        label = object_type.lower()
        # F1: object không phải `Place` mà là `Entity` (tên rác do LLM sinh).
        if label == "entity":
            return True
        if label not in ("place", "event"):
            # `Person`/`Year`… là sai nhãn rõ ràng cho quan hệ địa danh.
            return True
    # F2: hạ tầng / cơ quan.
    if relation in PLACE_OF_LIFE_RELATIONS and is_infrastructure(object_name):
        return True
    del object_qid
    return False


def filter_noisy_edges(edges: list[dict]) -> list[dict]:
    """Loại cạnh nhiễu khỏi danh sách cạnh.

    Args:
        edges: Danh sách cạnh (dict có `relation`, `target_name`/`object_name`…).

    Returns:
        Danh sách cạnh đã lọc (giữ nguyên thứ tự).
    """
    kept: list[dict] = []
    for edge in edges:
        relation = str(edge.get("relation") or edge.get("type") or "")
        target_name = str(
            edge.get("target_name")
            or edge.get("object_name")
            or edge.get("target")
            or ""
        )
        target_type = edge.get("target_type") or edge.get("object_type")
        if is_noisy_edge(relation, target_name, object_type=target_type):
            continue
        kept.append(edge)
    return kept


def filter_noisy_records(records: list[dict]) -> list[dict]:
    """Loại **record** nhiễu khỏi kết quả truy vấn.

    Record được coi là nhiễu khi nó mô tả một cặp (quan hệ, địa danh hạ tầng
    hoặc tên rác): record có trường `relation` (hoặc `type`) và trường tên
    object (`object`, `object_name`, `target`, `place`…).

    Ví dụ record nhiễu:
        ``{"relation": "mat_tai", "object": "Quốc lộ 14"}``

    Args:
        records: Danh sách record từ Neo4j.

    Returns:
        Danh sách record đã lọc (giữ nguyên thứ tự).
    """
    kept: list[dict] = []
    for record in records:
        relation = str(record.get("relation") or record.get("type") or "")
        if not relation:
            kept.append(record)
            continue
        target_name = ""
        for key in ("object", "object_name", "target", "target_name",
                    "place", "place_name", "location"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                target_name = value
                break
        if not target_name:
            kept.append(record)
            continue
        if is_noisy_edge(relation, target_name):
            continue
        kept.append(record)
    return kept


#: Đoạn `WHERE` Cypher loại cạnh nhiễu — dùng cho các truy vấn **mở rộng đồ thị**
#: (1-hop) và các truy vấn cạnh trong kênh KG.
#:
#: Regex Cypher không hỗ trợ `\b` theo nghĩa Python ⇒ dùng mẫu không cần ranh
#: giới từ chính xác.
NOISY_EDGE_CYPHER_PREDICATE = (
    "NOT ("
    "  type(r) IN ['sinh_tai','mat_tai','dong_doi_tai','dien_ra_tai']"
    "  AND (b:Place)"
    "  AND ("
    "    b.name =~ '(?i)^(Quốc lộ|Tổng đường|Quận [0-9]|Đường chí kiệt|Bến xe|Sân bay quốc tế|Nhà ga|Trường (Đại học|Cao đẳng|Trung học|Tiểu học|Quốc gia)|Bệnh viện|Xí nghiệp|Nhà máy).*'"
    "  )"
    ")"
)


def noisy_edge_cypher_filter(
    subject_var: str = "a",
    relation_var: str = "r",
    object_var: str = "b",
) -> str:
    """Sinh đoạn `WHERE` loại cạnh nhiễu cho Cypher mở rộng đồ thị.

    Args:
        subject_var: Biến subject trong Cypher.
        relation_var: Biến quan hệ trong Cypher.
        object_var: Biến object trong Cypher.

    Returns:
        Đoạn điều kiện (không có `WHERE`).
    """
    return (
        NOISY_EDGE_CYPHER_PREDICATE
        .replace("(b:Place)", f"({object_var}:Place)")
        .replace("type(r)", f"type({relation_var})")
        .replace("b.name", f"{object_var}.name")
    )

"""Validator tĩnh cho Cypher — chặn mọi lệnh ghi (Phase 11 — G2).

Vì sao cần validator tĩnh?
- Neo4j Community **không có RBAC** (không `GRANT`/`SET ROLE reader` được).
- Cơ chế bảo vệ thật là session `default_access_mode=READ` → server chặn
  lệnh ghi. Nhưng **vẫn phải chặn ở tầng ứng dụng** để:
  1. trả lỗi rõ ràng cho người dùng thay vì lỗi Neo4j kỹ thuật;
  2. không gửi câu hợp pháp về mặt cú pháp nhưng nguy hiểm về mặt ý nghĩa
     (vd `CALL db.labels()`).

Quy tắc kiểm tra:
- Chỉ cho phép câu bắt đầu bằng `MATCH` / `OPTIONAL MATCH` / `WITH` /
  `UNWIND` / `RETURN`.
- Blacklist từ khóa ghi (case-insensitive, **bỏ qua string literal**):
  `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `FOREACH`,
  `LOAD CSV`, `CALL`, `dbms.`, `apoc.`, `ALTER`, `GRANT`, `REVOKE`, `DENY`.
- Chặn `;` ngoài string literal (chống nối nhiều câu).
- Bắt buộc có `LIMIT`; nếu thiếu → thêm `LIMIT 50`.
- Mọi quan hệ dùng trong câu phải nằm trong `RELATION_TYPES` (18 quan hệ
  đóng); nếu có quan hệ ngoài danh sách → từ chối.
"""

from __future__ import annotations

import re
from typing import Any

from src.common.schemas import RELATION_TYPES

#: Từ khóa bị cấm tuyệt đối.
BLACKLIST_KEYWORDS = (
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "DROP",
    "FOREACH",
    "LOAD CSV",
    "CALL",
    "ALTER",
    "GRANT",
    "REVOKE",
    "DENY",
)

#: Tiền tố hàm/driver bị cấm.
BLACKLIST_PREFIXES = ("dbms.", "apoc.", "db.", "system.")

#: Từ khóa mở đầu hợp lệ.
ALLOWED_STARTS = ("MATCH", "OPTIONAL MATCH", "WITH", "UNWIND", "RETURN")

#: Giới hạn tối đa.
MAX_LIMIT = 100
DEFAULT_LIMIT = 50


def strip_string_literals(cypher: str) -> str:
    """Thay thế nội dung trong string literal bằng khoảng trắng.

    Giữ nguyên độ dài để vị trí lỗi không bị lệch.

    Args:
        cypher: Câu Cypher gốc.

    Returns:
        Câu Cypher đã bỏ nội dung string literal.
    """
    out: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False
    for char in cypher:
        if escaped:
            out.append(" ")
            escaped = False
            continue
        if char == "\\" and (in_single or in_double):
            out.append(" ")
            escaped = True
            continue
        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            out.append(" ")
            continue
        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            out.append(" ")
            continue
        if char == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            out.append(" ")
            continue
        if in_single or in_double or in_backtick:
            out.append(" ")
        else:
            out.append(char)
    return "".join(out)


def _strip_comments(cypher: str) -> str:
    """Bỏ comment dòng (`//`) và comment khối (`/* */`).

    Args:
        cypher: Câu Cypher gốc.

    Returns:
        Câu Cypher đã bỏ comment.
    """
    cypher = re.sub(r"/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    cypher = re.sub(r"//[^\n]*", " ", cypher)
    return cypher


def extract_relations(cypher: str) -> set[str]:
    """Trích các tên quan hệ dùng trong câu (`-[r:REL]->`).

    Args:
        cypher: Câu Cypher (đã bỏ string literal).

    Returns:
        Set tên quan hệ.
    """
    relations: set[str] = set()
    for match in re.finditer(r"\[[^\]]*?:([A-Za-z_][A-Za-z0-9_]*)", cypher):
        relations.add(match.group(1))
    for match in re.finditer(r"-\s*:\s*([A-Za-z_][A-Za-z0-9_]*)", cypher):
        relations.add(match.group(1))
    return relations


def extract_limit(cypher: str) -> int | None:
    """Trích giá trị `LIMIT` trong câu.

    Args:
        cypher: Câu Cypher.

    Returns:
        Giá trị limit, hoặc ``None`` nếu không có.
    """
    match = re.search(r"\bLIMIT\s+(\d+)", cypher, flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def has_filtering_predicate(cypher: str) -> bool:
    """Kiểm tra câu Cypher có **điều kiện lọc có giá trị cụ thể** hay không.

    Vì sao cần (Phase 13, lỗi demo 17/11/2026): khi câu hỏi **không chứa
    entity nào** link được (vd "Ông ấy mất năm nào?" — đại từ đã bị chặn),
    LLM có thể sinh:

        ``MATCH (p:Person) RETURN p.name AS name, p.death_year AS death_year LIMIT 10``
        ``MATCH (p:Person) WHERE p.death_year IS NOT NULL RETURN … LIMIT 10``

    ⇒ trả về **ngẫu nhiên N người** trong KG, tạo cảm giác "có dữ liệu" nhưng
    hoàn toàn không liên quan. Câu trả lời đúng phải là *"Không có trong dữ
    liệu."*.

    Điều kiện lọc được chấp nhận:
    - lọc theo ``entity_id``;
    - ``WHERE`` có **so sánh với giá trị cụ thể** (số hoặc chuỗi literal):
      ``= 1900``, ``= 'nha tran'``, ``CONTAINS 'tuong'``, ``IN ['a','b']``;
    - hàm tổng hợp ``COUNT(...)`` (câu hỏi đếm — vd "Có bao nhiêu người?").

    Điều kiện ``IS NOT NULL`` **không** được chấp nhận — nó chỉ lọc "có giá
    trị" chứ không định danh được đối tượng cụ thể.

    Args:
        cypher: Câu Cypher.

    Returns:
        ``True`` nếu câu có điều kiện lọc định danh được đối tượng.
    """
    without_literals = strip_string_literals(_strip_comments(cypher))
    if "entity_id" in without_literals:
        return True
    if re.search(r"\bCOUNT\s*\(", without_literals, flags=re.IGNORECASE):
        return True
    where_match = re.search(
        r"\bWHERE\b(?P<body>.*?)(?:\bRETURN\b|\bORDER\b|\bSKIP\b|\bLIMIT\b|$)",
        without_literals,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not where_match:
        return False
    body = where_match.group("body")
    # So sánh với số: `= 1900`, `> 1900`, `<= 1900`…
    if re.search(r"[<>!=]=?\s*-?\d+", body):
        return True
    # So sánh với chuỗi literal — phải khôi phục string literal đã bị bỏ.
    raw_where = _strip_comments(cypher)
    raw_match = re.search(
        r"\bWHERE\b(?P<body>.*?)(?:\bRETURN\b|\bORDER\b|\bSKIP\b|\bLIMIT\b|$)",
        raw_where,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if raw_match:
        raw_body = raw_match.group("body")
        if re.search(r"=\s*'[^']+'", raw_body):
            return True
        if re.search(r"\bCONTAINS\b\s*'[^']+'", raw_body, flags=re.IGNORECASE):
            return True
        if re.search(r"\bIN\s*\(\s*\[?[^\]]*'[^']+'", raw_body, flags=re.IGNORECASE):
            return True
    return False


def validate_cypher(cypher: str) -> tuple[bool, str, str]:
    """Kiểm định một câu Cypher chỉ đọc.

    Args:
        cypher: Câu Cypher cần kiểm.

    Returns:
        Tuple `(ok, reason, cypher_đã_sửa)`. `cypher_đã_sửa` là câu sau khi
        thêm `LIMIT` nếu thiếu (nếu không cần sửa thì bằng `cypher` gốc).
    """
    if not cypher or not cypher.strip():
        return False, "Câu Cypher rỗng.", ""

    cleaned = _strip_comments(cypher).strip()
    without_literals = strip_string_literals(cleaned)

    # 1) Dấu `;` ngoài string literal → nối nhiều câu.
    if ";" in without_literals:
        return False, "Câu Cypher chứa dấu `;` (nối nhiều câu) — bị từ chối.", cleaned

    # 2) Từ khóa bị cấm.
    upper = without_literals.upper()
    for keyword in BLACKLIST_KEYWORDS:
        if re.search(rf"\b{re.escape(keyword)}\b", upper):
            return False, f"Câu Cypher chứa từ khóa bị cấm: `{keyword}`.", cleaned
    lowered = without_literals.lower()
    for prefix in BLACKLIST_PREFIXES:
        if prefix in lowered:
            return False, f"Câu Cypher gọi namespace bị cấm: `{prefix}`.", cleaned

    # 3) Phải bắt đầu bằng từ khóa cho phép.
    first = re.match(r"\s*([A-Za-z_]+(?:\s+[A-Za-z_]+)?)", without_literals)
    head = re.sub(r"\s+", " ", first.group(1)).upper() if first else ""
    if head not in ALLOWED_STARTS:
        return False, (
            f"Câu Cypher phải bắt đầu bằng một trong {', '.join(ALLOWED_STARTS)} "
            f"— nhận được `{head or '?'}`."
        ), cleaned

    # 4) Quan hệ ngoài danh mục 18.
    relations = extract_relations(without_literals)
    allowed = set(RELATION_TYPES)
    bad = sorted(relations - allowed)
    if bad:
        return False, (
            f"Câu Cypher dùng quan hệ ngoài danh mục: {', '.join(bad)}."
        ), cleaned

    # 5) LIMIT bắt buộc và ≤ 100.
    limit = extract_limit(without_literals)
    if limit is None:
        return True, "", f"{cleaned.rstrip().rstrip(';')} LIMIT {DEFAULT_LIMIT}"
    if limit > MAX_LIMIT:
        return False, f"LIMIT {limit} vượt quá tối đa {MAX_LIMIT}.", cleaned
    if limit <= 0:
        return False, "LIMIT phải lớn hơn 0.", cleaned
    return True, "", cleaned

def sanitize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chuyển record Neo4j sang JSON-safe (loại bỏ object neo4j).

    Args:
        records: Danh sách record từ driver.

    Returns:
        Danh sách dict JSON-safe.
    """
    from neo4j.graph import Node, Path, Relationship

    def convert(value: Any) -> Any:
        if isinstance(value, Node):
            return {"labels": list(value.labels), **value.properties}
        if isinstance(value, Relationship):
            return {
                "type": value.type,
                "start": value.start_node.get("entity_id"),
                "end": value.end_node.get("entity_id"),
                **value.properties,
            }
        if isinstance(value, Path):
            return {
                "nodes": [convert(n) for n in value.nodes],
                "relationships": [convert(r) for r in value.relationships],
            }
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        return value

    return [{k: convert(v) for k, v in record.items()} for record in records]

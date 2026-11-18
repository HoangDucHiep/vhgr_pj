"""Phase 16 — Chuẩn hoá **chiều quan hệ** ở tầng đọc KG (D-118).

Vì sao cần module này?
----------------------
KG lưu quan hệ **có hướng** (theo `docs/04-schema-knowledge-graph.md` §3.1):

    (Lê Lợi)-[:cha_cua]->(Lê Khánh Dư)      nghĩa: Lê Lợi là con của Lê Khánh Dư
    (Lê Lợi)-[:me_cua]->(Lê Thị Ngọc)        nghĩa: Lê Lợi là con của Lê Thị Ngọc
    (Lê Lợi)-[:vo_cua]->(Lê Thị Ngọc)        nghĩa: Lê Lợi là chồng của Lê Thị Ngọc

Nhưng các template Cypher của `src/qa/graph_context.py` lại khớp **không
hướng** (``MATCH (e)-[r]-(other)``) rồi gán cứng ``source = e``,
``target = other``. Hệ quả: **mọi cạnh bị đảo chiều khi hiển thị**.

    KG thật:      (Ưng Dự)-[:cha_cua]->(Hồng Thiết)
    Hiển thị sai: Hồng Thiết — cha của → Ưng Dự

Đo được trên KG thật (17/11/2026): **2.601/2.601** cạnh gia đình
(`cha_cua`/`me_cua`/`vo_cua`/`chong_cua`) bị hiển thị đảo chiều ⇒
LLM sinh câu trả lời sai, judge chấm `faithfulness` < 2 ⇒ Arm B không đạt
gate `faithfulness_rate ≥ 0,90`.

Cách sửa (giữ nguyên dữ liệu)
-------------------------------
Theo nguyên tắc đã dùng ở D-095 (lọc ở **tầng đọc**, không sửa Neo4j), ta
sửa **tầng đọc**:

1. Mọi template Cypher dùng match **có hướng** ``(e)-[r]->(other)`` và
   trả về cả chiều thật qua ``startNode``/``endNode``.
2. Module này cung cấp :func:`normalize_direction` để **hiển thị** quan hệ
   theo nghĩa đúng: quan hệ đi ngược được đổi nhãn sang quan hệ đảo
   (``cha_cua`` ⇄ ``con_cua``…) để câu "Ai là cha của X?" đọc đúng.

Quy ước hiển thị
-----------------
Cạnh ``A -[rel]-> B`` nghĩa "A có quan hệ ``rel`` với B", trong đó nhãn
``rel`` **luôn được đọc theo nghĩa chủ thể → đối tượng**:

    ``cha_cua``   : A là con của B
    ``me_cua``    : A là con của B
    ``vo_cua``    : A là chồng của B
    ``chong_cua``  : A là vợ của B
    ``anh_em_cua``: A là anh/em của B
    ``ke_vi``     : A là kế vị của B (B là tiền nhiệm)

⇒ Khi hiển thị theo **chiều ngược** (B là chủ thể), ta **đổi nhãn** sang
quan hệ đảo cho đúng nghĩa:

    ``A -[cha_cua]-> B``   hiển thị ngược: ``B -[con_cua]-> A``
                            nghĩa: B là con của A ✔

Quan hệ **đối xứng** (``anh_em_cua``) giữ nguyên nhãn khi đảo chiều.
"""

from __future__ import annotations

from typing import Any

from src.common.logger import get_logger

logger = get_logger("src.graph.direction")

#: Quan hệ **đối xứng** — đảo chiều vẫn giữ nguyên nghĩa.
SYMMETRIC_RELATIONS: frozenset[str] = frozenset({
    "anh_em_cua",
})

#: Bảng đảo nhãn: quan hệ đi ngược được hiển thị bằng nhãn nào.
#:
#: Khóa = nhãn gốc trong KG; giá trị = nhãn dùng khi hiển thị **ngược chiều**.
INVERSE_LABEL: dict[str, str] = {
    "cha_cua": "con_cua",
    "me_cua": "con_cua",
    "vo_cua": "chong_cua",
    "chong_cua": "vo_cua",
    "ke_vi": "ke_vi",
    "thuoc_trieu_dai": "thuoc_trieu_dai",
    "giu_chuc_vu": "giu_chuc_vu",
    "chi_huy_tran": "chi_huy_tran",
    "tham_gia_tran": "tham_gia_tran",
    "danh_bai": "danh_bai",
    "sinh_nam": "sinh_nam",
    "sinh_tai": "sinh_tai",
    "mat_nam": "mat_nam",
    "mat_tai": "mat_tai",
    "lap_ra": "lap_ra",
    "dien_ra_tai": "dien_ra_tai",
    "dong_doi_tai": "dong_doi_tai",
}

#: Nhãn hiển thị tiếng Việt cho **quan hệ đảo** (dùng khi đổi chiều).
INVERSE_LABEL_VI: dict[str, str] = {
    "con_cua": "con của",
    "chong_cua": "chồng của",
    "vo_cua": "vợ của",
    "cha_cua": "cha của",
    "me_cua": "mẹ của",
}


#: Nhóm quan hệ **gia đình** — các quan hệ này mô tả **cùng một vai trò**
#: (cha–mẹ–con, vợ–chồng) nên 2 cạnh ngược chiều là **cùng 1 sự thật**
#: hiển thị 2 lần ⇒ loại trùng ở tầng đọc (D-118).
#:
#: Đo được trên KG thật: 196 cặp `vo_cua` 2 chiều + 40 cặp có **cả**
#: `vo_cua` và `chong_cua` cùng chiều + 37 cặp có **cả** `cha_cua` và
#: `me_cua` cùng chiều ⇒ context thừa cạnh gây **mâu thuẫn** ⇒ LLM không
#: biết chọn cạnh nào ⇒ trả lời sai.
FAMILY_RELATION_GROUPS: dict[str, str] = {
    "cha_cua": "parent",
    "me_cua": "parent",
    "con_cua": "parent",
    "con_cua_va_me_cua": "parent",
    "vo_cua": "spouse",
    "chong_cua": "spouse",
    "anh_em_cua": "sibling",
}

#: Tiền tố bằng chứng khớp với nhãn quan hệ (vd evidence "Mẹ: X" ⇒ nhãn
#: `me_cua` đúng). Dùng để ưu tiên cạnh đúng khi có 2 cạnh cùng cặp.
_EVIDENCE_PREFIX_VI: dict[str, str] = {
    "cha_cua": "Cha",
    "me_cua": "Mẹ",
    "con_cua": "Con",
    "vo_cua": "Vợ",
    "chong_cua": "Chồng",
}


def _evidence_matches_relation(edge: dict[str, Any]) -> bool:
    """Kiểm tra bằng chứng của cạnh có **khớp** nhãn quan hệ không.

    Vì sao cần?
    -----------
    KG có 2 cạnh cùng cặp với nhãn khác nhau (vd `Mai Ngọc Đỉnh -vo_cua->
    Lê Hiến Tông` **và** `Mai Ngọc Đỉnh -chong_cua-> Lê Hiến Tông`). Bằng
    chứng `"Chồng: Lê Hiến Tông"` chỉ khớp nhãn `chong_cua` ⇒ cạnh đó đúng
    ⇒ giữ, loại cạnh kia.

    Args:
        edge: Cạnh KG.

    Returns:
        ``True`` nếu bằng chứng khớp nhãn (hoặc không có bằng chứng để so).
    """
    relation = str(edge.get("relation") or "")
    prefix = _EVIDENCE_PREFIX_VI.get(relation)
    if not prefix:
        return False
    evidence = str(edge.get("evidence_sentence") or "").strip()
    if not evidence:
        return False
    return evidence.startswith(prefix + ":")


def invert_relation(relation: str) -> str:
    """Đổi nhãn quan hệ sang nhãn đảo.

    Args:
        relation: Nhãn quan hệ gốc.

    Returns:
        Nhãn đảo (`con_cua` cho `cha_cua`…). Quan hệ đối xứng giữ nguyên.
    """
    if relation in SYMMETRIC_RELATIONS:
        return relation
    return INVERSE_LABEL.get(relation, relation)


def relation_label_vi(relation: str) -> str:
    """Lấy nhãn tiếng Việt của quan hệ (kể cả quan hệ đảo).

    Args:
        relation: Nhãn quan hệ (có thể đã là nhãn đảo).

    Returns:
        Nhãn tiếng Việt.
    """
    from src.qa.graph_context import RELATION_LABEL

    if relation in RELATION_LABEL:
        return RELATION_LABEL[relation]
    return INVERSE_LABEL_VI.get(relation, relation)


def normalize_direction(
    edge: dict[str, Any],
    *,
    anchor_id: str = "",
) -> dict[str, Any]:
    """Chuẩn hoá chiều của một cạnh KG để hiển thị đúng nghĩa.

    Cạnh được xử lý:

    - ``source_id``/``target_id``/``source_name``/``target_name`` được đảo nếu
      cạnh thật đi theo chiều ngược với ``anchor_id`` (hoặc với chiều mặc
      định mà template trả về).
    - ``relation`` được đổi sang nhãn đảo tương ứng.
    - ``reversed`` được đặt ``True`` nếu đã đảo.

    Args:
        edge: Cạnh KG (dict có `source_id`, `target_id`, `relation`…).
        anchor_id: Id entity làm mốc (entity người dùng hỏi về). Nếu cạnh
            nối với mốc thì mốc luôn được đặt làm **chủ thể** để câu hỏi
            đọc đúng chiều.

    Returns:
        Cạnh đã chuẩn hoá (copy — không sửa input).
    """
    out = dict(edge)
    relation = str(out.get("relation") or "")
    source_id = str(out.get("source_id") or "")
    target_id = str(out.get("target_id") or "")

    if not source_id and not target_id:
        return out

    # Cạnh tự tham chiếu (source == target) ⇒ vô nghĩa, loại.
    if source_id and source_id == target_id:
        out["_self_loop"] = True
        return out

    # Cạnh nối với mốc ⇒ mốc là chủ thể (đọc "cha của X" theo đúng chiều).
    should_reverse = False
    if anchor_id:
        if target_id == anchor_id and source_id != anchor_id:
            should_reverse = True
        elif source_id == anchor_id:
            should_reverse = False

    if should_reverse:
        # Lưu tạm trước khi ghi đè (tránh đảo 2 lần).
        old_source_id, old_source_name = source_id, out.get("source_name")
        old_target_id, old_target_name = target_id, out.get("target_name")
        old_source_labels = out.get("source_labels")
        old_target_labels = out.get("target_labels")
        out["source_id"] = old_target_id
        out["source_name"] = old_target_name
        out["target_id"] = old_source_id
        out["target_name"] = old_source_name
        # D-123: phải đảo **nhãn** theo tên, nếu không node `Title` sẽ còn
        # nhãn ở `source_labels` còn tên ở `target_name` ⇒ tầng đọc không
        # nhận ra đó là node `Title` (danh xưng) nên không sửa tên hiển thị.
        if old_source_labels is not None or old_target_labels is not None:
            out["source_labels"] = old_target_labels
            out["target_labels"] = old_source_labels
        out["relation"] = invert_relation(relation)
        out["reversed"] = True
    else:
        out.setdefault("reversed", False)
    return out


def normalize_edges(
    edges: list[dict[str, Any]],
    *,
    anchor_id: str = "",
) -> list[dict[str, Any]]:
    """Chuẩn hoá chiều cho nhiều cạnh (loại cạnh tự tham chiếu + trùng cặp).

    Vì sao loại **trùng cặp**?
    ----------------------
    KG lưu quan hệ gia đình theo **nhiều hướng** cho cùng một sự thật (vd
    `Mai Ngọc Đỉnh -vo_cua-> Lê Hiến Tông` **và** `... -chong_cua-> ...`).
    Hiển thị cả 2 ⇒ context **mâu thuẫn** ⇒ LLM không biết cạnh nào đúng ⇒
    trả lời sai ⇒ judge chấm `faithfulness < 2`.

    ⇒ Với mỗi **cặp node** (không phân biệt thứ tự) trong cùng nhóm quan hệ
    gia đình, chỉ giữ **một** cạnh: ưu tiên cạnh mà **bằng chứng khớp nhãn**
    (vd evidence `"Chồng: X"` ⇒ cạnh `chong_cua`).

    Args:
        edges: Danh sách cạnh.
        anchor_id: Id entity làm mốc.

    Returns:
        Danh sách cạnh đã chuẩn hoá.
    """
    normalized: list[dict[str, Any]] = []
    for edge in edges:
        item = normalize_direction(edge, anchor_id=anchor_id)
        if item.get("_self_loop"):
            continue
        item.pop("_self_loop", None)
        normalized.append(item)

    # --- Khử trùng cặp quan hệ gia đình -------------------------------
    kept: list[dict[str, Any]] = []
    #: (node_a, node_b, nhóm quan hệ) → index trong `kept`.
    seen_pairs: dict[tuple[str, str, str], int] = {}
    for item in normalized:
        group = FAMILY_RELATION_GROUPS.get(str(item.get("relation") or ""))
        if not group:
            kept.append(item)
            continue
        source_id = str(item.get("source_id") or "")
        target_id = str(item.get("target_id") or "")
        key = (
            *sorted((source_id, target_id)),
            group,
        )
        if key not in seen_pairs:
            seen_pairs[key] = len(kept)
            kept.append(item)
            continue
        # Đã có cạnh cho cặp này ⇒ giữ cạnh nào có bằng chứng **khớp nhãn**.
        existing = kept[seen_pairs[key]]
        if _evidence_matches_relation(item) and not _evidence_matches_relation(
            existing
        ):
            kept[seen_pairs[key]] = item
    return kept


__all__ = [
    "FAMILY_RELATION_GROUPS",
    "INVERSE_LABEL",
    "INVERSE_LABEL_VI",
    "SYMMETRIC_RELATIONS",
    "invert_relation",
    "normalize_direction",
    "normalize_edges",
    "relation_label_vi",
]

"""Dịch câu hỏi tiếng Việt → Cypher chỉ đọc (Phase 11 — bước 5).

Luồng:
    câu hỏi → **link entity** (thay tên bằng `entity_id`) → LLM sinh Cypher
    → **validate tĩnh** → thực thi trên Neo4j (session READ).

Retry (G5): tối đa 3 lần. Mỗi lần lỗi, đưa **thông báo lỗi + Cypher cũ**
vào prompt để LLM tự sửa. Nếu lần cuối vẫn lỗi hoặc kết quả rỗng →
`status="not_in_data"`.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT, load_config
from src.common.llm_client import LLMClient
from src.common.logger import get_logger
from src.graph.noise_filter import filter_noisy_edges, filter_noisy_records

from backend.app.services.cypher_validator import (
    has_filtering_predicate,
    sanitize_records,
    validate_cypher,
)
from backend.app.services.entity_linker import get_linker

logger = get_logger(__name__)

#: Prompt template.
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "text_to_cypher.txt"

#: Số lần retry tối đa.
MAX_RETRIES = 3


def load_prompt_template() -> str:
    """Đọc prompt template từ file.

    Returns:
        Nội dung prompt.
    """
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Không tìm thấy prompt: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _get_client() -> LLMClient:
    """Dựng `LLMClient` từ `configs/llm.yaml`.

    Returns:
        Đối tượng client.
    """
    config = load_config(REPO_ROOT / "configs" / "llm.yaml")
    return LLMClient.from_config(config)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Trích JSON từ phản hồi LLM (bỏ markdown fence).

    Args:
        text: Phản hồi thô.

    Returns:
        Dict nếu parse được, ngược lại ``None``.
    """
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def build_prompt(
    question: str,
    annotated: str,
    entities: list[dict[str, Any]],
    template: str,
    previous: str | None = None,
    error: str | None = None,
) -> str:
    """Dựng prompt cho LLM.

    Args:
        question: Câu hỏi gốc.
        annotated: Câu hỏi đã gắn `[entity_id]`.
        entities: Danh sách entity tìm được.
        template: Nội dung prompt template.
        previous: Cypher trước đó (khi retry).
        error: Thông báo lỗi (khi retry).

    Returns:
        Prompt hoàn chỉnh.
    """
    entity_lines = "\n".join(
        f"- {item['surface']} → entity_id = {item['entity_id']} "
        f"(tên chuẩn: {item['canonical_name']})"
        for item in entities
    ) or "- (không tìm thấy entity nào — hãy lọc theo thuộc tính)"

    parts = [
        template,
        "\n\n## CÂU HỎI CỦA NGƯỜI DÙNG\n",
        f"{question}\n",
        "\n## CÂU HỎI ĐÃ GẮN ENTITY_ID (dùng đúng các id này)\n",
        f"{annotated}\n",
        "\n## DANH SÁCH ENTITY ĐÃ NHẬN DIỆN\n",
        entity_lines,
    ]
    if previous and error:
        parts.extend([
            "\n## LẦN TRƯỚC CỦA BẠN ĐÃ SAI\n",
            f"Cypher cũ: {previous}\n",
            f"Lỗi: {error}\n",
            "\nHãy sửa lại. Nhớ: chỉ dùng MATCH/OPTIONAL MATCH/WITH/WHERE/RETURN "
            "và LUÔN kết thúc bằng LIMIT ≤ 100.\n",
        ])
    return "".join(parts)


def ask(
    question: str,
    *,
    max_retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    """Trả lời một câu hỏi tiếng Việt.

    Args:
        question: Câu hỏi.
        max_retries: Số lần thử tối đa.

    Returns:
        Dict theo output contract của Phase 11:
        `{"status", "answer", "cypher", "entities", "records", "graph",
        "retries", "elapsed_ms"}`.
    """
    started = time.time()

    # Nếu câu hỏi **là Cypher thô** (bắt đầu bằng MATCH/RETURN/...) thì
    # không gọi LLM — kiểm định tĩnh rồi thực thi. Nhờ vậy payload độc hại
    # (vd "MATCH (n) DETACH DELETE n") bị chặn ở tầng ứng dụng.
    direct = _as_raw_cypher(question)
    if direct is not None:
        return _run_direct(direct, started)

    template = load_prompt_template()
    linker = get_linker()
    annotated, entities = linker.annotate(question)
    client = _get_client()

    previous_cypher: str | None = None
    last_error: str | None = None
    retries = 0

    for attempt in range(1, max_retries + 1):
        retries = attempt - 1
        prompt = build_prompt(
            question, annotated, entities, template, previous_cypher, last_error,
        )
        try:
            raw = client.complete_json(prompt, temperature=0.0, max_tokens=1024)
        except Exception as exc:  # noqa: BLE001 - lỗi provider → retry
            last_error = f"Lỗi gọi LLM: {exc}"
            logger.warning("Lần %d: %s", attempt, last_error)
            continue

        payload = raw if isinstance(raw, dict) else _extract_json(
            raw if isinstance(raw, str) else json.dumps(raw)
        )
        if not payload or not payload.get("cypher"):
            last_error = "Phản hồi LLM không phải JSON hợp lệ có trường `cypher`."
            logger.warning("Lần %d: %s", attempt, last_error)
            continue

        cypher = str(payload["cypher"]).strip()
        ok, reason, fixed = validate_cypher(cypher)
        if not ok:
            last_error = reason
            previous_cypher = cypher
            logger.warning("Lần %d bị validator chặn: %s", attempt, reason)
            continue

        # Phase 13: nếu câu hỏi **không có entity nào** link được (vd đại từ
        # "Ông ấy" đã bị chặn) mà LLM sinh Cypher **không lọc theo giá trị cụ
        # thể** ⇒ câu đó sẽ quét toàn đồ thị và trả về các bản ghi ngẫu nhiên.
        # ⇒ chặn ngay, không retry (LLM lặp lại cùng dạng câu), trả "Không có
        # trong dữ liệu." đúng nguyên tắc #3.
        if not entities and not has_filtering_predicate(fixed):
            logger.warning(
                "Câu hỏi không có entity cụ thể và Cypher không lọc theo giá trị "
                "cụ thể — trả 'không có trong dữ liệu' (không retry).",
            )
            return {
                "status": "not_in_data",
                "answer": (
                    "Không có trong dữ liệu. Câu hỏi không nêu tên cụ thể nào "
                    "(ví dụ dùng đại từ như \"ông ấy\", \"vị vua đó\") nên hệ "
                    "thống không xác định được đối tượng cần tra cứu. Vui lòng "
                    "nêu rõ tên người, nhà, hoặc sự kiện."
                ),
                "cypher": fixed,
                "entities": [],
                "records": [],
                "graph": {"nodes": [], "edges": []},
                "retries": retries,
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        from backend.app.services import neo4j_client

        try:
            records = neo4j_client.run_read_query(fixed)
        except Exception as exc:  # noqa: BLE001 - lỗi cú pháp Cypher → retry
            last_error = f"Lỗi thực thi Cypher: {exc}"
            previous_cypher = fixed
            logger.warning("Lần %d: %s", attempt, last_error)
            continue

        safe_records = sanitize_records(records)
        # Phase 13: loại record nhiễu (vd `mat_tai → Quốc lộ 14`).
        safe_records = filter_noisy_records(safe_records)
        if not safe_records:
            # Thử lần cuối: lấy **node đầy đủ** cho các entity đã link. Nhiều
            # câu hỏi hỏi về thuộc tính null (`start_year` của sự kiện, `reign_end`
            # của vua…) → Cypher trả 1 dòng toàn null ⇒ bị coi là "không có
            # dữ liệu" dù entity **có** trong KG.
            safe_records = _fallback_entity_records(entities)
            if not safe_records:
                return {
                    "status": "not_in_data",
                    "answer": "Không có trong dữ liệu.",
                    "cypher": fixed,
                    "entities": entities,
                    "records": [],
                    "graph": {"nodes": [], "edges": []},
                    "retries": retries,
                    "elapsed_ms": int((time.time() - started) * 1000),
                }
            fixed = (
                "MATCH (n) WHERE n.entity_id IN ["
                + ", ".join(f"'{e['entity_id']}'" for e in entities)
                + "] RETURN n LIMIT 50"
            )

        from backend.app.services.answer_generator import generate_answer

        answer = generate_answer(question, safe_records)
        return {
            "status": "found",
            "answer": answer,
            "cypher": fixed,
            "entities": entities,
            "records": safe_records,
            "graph": _build_graph(safe_records, entities),
            "retries": retries,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    logger.warning("Hết %d lần thử: %s", max_retries, last_error)
    return {
        "status": "error",
        "answer": (
            "Không tạo được truy vấn phù hợp cho câu hỏi này. "
            f"Chi tiết: {last_error}"
        ),
        "cypher": previous_cypher or "",
        "entities": entities,
        "records": [],
        "graph": {"nodes": [], "edges": []},
        "retries": retries,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _as_raw_cypher(question: str) -> str | None:
    """Nhận diện câu hỏi có dạng Cypher thô.

    Args:
        question: Câu hỏi.

    Returns:
        Cypher thô nếu câu hỏi bắt đầu bằng từ khóa Cypher, ngược lại ``None``.
    """
    text = question.strip()
    head = text.split(None, 1)[0].upper() if text else ""
    if head in {"MATCH", "OPTIONAL", "RETURN", "WITH", "UNWIND", "CREATE",
                "MERGE", "DELETE", "DETACH", "CALL", "LOAD", "DROP"}:
        return text
    return None


def _run_direct(cypher: str, started: float) -> dict[str, Any]:
    """Kiểm định + thực thi Cypher thô (không qua LLM).

    Args:
        cypher: Cypher thô.
        started: Thời điểm bắt đầu (để tính `elapsed_ms`).

    Returns:
        Dict theo output contract của Phase 11.
    """
    from backend.app.services import neo4j_client

    ok, reason, fixed = validate_cypher(cypher)
    if not ok:
        logger.warning("Cypher thô bị từ chối: %s", reason)
        return {
            "status": "error",
            "answer": f"Câu truy vấn bị từ chối: {reason}",
            "cypher": cypher,
            "entities": [],
            "records": [],
            "graph": {"nodes": [], "edges": []},
            "retries": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    try:
        records = neo4j_client.run_read_query(fixed)
    except Exception as exc:  # noqa: BLE001 - lỗi cú pháp Cypher
        logger.warning("Cypher thô lỗi cú pháp: %s", exc)
        return {
            "status": "error",
            "answer": f"Câu truy vấn không hợp lệ: {exc}",
            "cypher": fixed,
            "entities": [],
            "records": [],
            "graph": {"nodes": [], "edges": []},
            "retries": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    safe_records = sanitize_records(records)
    safe_records = filter_noisy_records(safe_records)
    if not safe_records:
        return {
            "status": "not_in_data",
            "answer": "Không có trong dữ liệu.",
            "cypher": fixed,
            "entities": [],
            "records": [],
            "graph": {"nodes": [], "edges": []},
            "retries": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
    from backend.app.services.answer_generator import generate_answer

    return {
        "status": "found",
        "answer": generate_answer(cypher, safe_records),
        "cypher": fixed,
        "entities": [],
        "records": safe_records,
        "graph": _build_graph(safe_records),
        "retries": 0,
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def _build_answer(question: str, records: list[dict[str, Any]]) -> str:
    """Tạo câu trả lời từ `records` (không suy đoán ngoài dữ liệu).

    Args:
        question: Câu hỏi.
        records: Kết quả truy vấn.

    Returns:
        Câu trả lời tiếng Việt.
    """
    if not records:
        return "Không có trong dữ liệu."
    if len(records) == 1:
        record = records[0]
        parts: list[str] = []
        for key, value in record.items():
            if value is None or value == "":
                continue
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value[:10])
            parts.append(f"{key}: {value}")
        return "; ".join(parts) if parts else "Không có trong dữ liệu."
    lines = [f"Tìm thấy {len(records)} kết quả:"]
    for index, record in enumerate(records[:20], start=1):
        values = [
            str(value) for value in record.values()
            if value is not None and value != ""
        ]
        lines.append(f"{index}. " + " — ".join(values))
    if len(records) > 20:
        lines.append(f"... và {len(records) - 20} kết quả khác.")
    return "\n".join(lines)


def _build_graph(
    records: list[dict[str, Any]],
    entities: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Dựng đồ thị nhỏ (nodes/edges) từ `records` để vẽ.

    Vấn đề đã gặp: LLM thường trả `p.name AS name` (string) chứ không trả
    cả node ⇒ bản cũ không tạo được node nào ⇒ **UI không hiện gì**.
    Cách sửa: dùng `entity_id` từ **entity linker** (đã biết chắc) + truy vấn
    lại DB theo id để lấy node/edge thật.

    Args:
        records: Kết quả truy vấn.
        entities: Entity đã link trong câu hỏi (từ `entity_linker`).

    Returns:
        Dict `{"nodes": [...], "edges": [...]}`.
    """
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    # Thu thập `entity_id` từ entity linker (nguồn đáng tin cậy nhất).
    entity_ids: set[str] = set()
    for item in entities or []:
        entity_id = str(item.get("entity_id") or "")
        if entity_id:
            entity_ids.add(entity_id)

    # Bổ sung từ records (kể cả string bắt đầu bằng `ent_`).
    for record in records:
        for value in record.values():
            if isinstance(value, dict) and "entity_id" in value:
                entity_ids.add(str(value.get("entity_id") or ""))
            elif isinstance(value, str) and value.startswith("ent_"):
                entity_ids.add(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and "entity_id" in item:
                        entity_ids.add(str(item.get("entity_id") or ""))
                    elif isinstance(item, str) and item.startswith("ent_"):
                        entity_ids.add(item)

    if entity_ids:
        _enrich_graph_from_db(entity_ids, nodes, edges)
    else:
        # Cypher trả **tên** (`p.name AS king`) chứ không phải `entity_id` ⇒
        # không có id để truy vấn. Giải quyết bằng cách tra tên trong Neo4j.
        names = {
            str(value)
            for record in records
            for value in record.values()
            if isinstance(value, str) and value.strip() and not value.startswith("ent_")
        }
        if names:
            _enrich_graph_by_names(sorted(names)[:20], nodes, edges)

    return {"nodes": list(nodes.values()), "edges": edges}


def _enrich_graph_by_names(
    names: list[str],
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    """Tra cứu node/cạnh theo **tên** hiển thị.

    Dùng khi Cypher trả tên (`RETURN p.name AS king`) mà không trả `entity_id`.

    Args:
        names: Danh sách tên cần tra.
        nodes: Dict node đích (cập nhật tại chỗ).
        edges: Danh sách cạnh đích (cập nhật tại chỗ).
    """
    from backend.app.services import neo4j_client

    try:
        rows = neo4j_client.run_read_query(
            """
            MATCH (n)
            WHERE n.name IN $names OR n.name_normalized IN $names
            RETURN n.entity_id AS entity_id
            LIMIT 40
            """,
            {"names": names},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không tra được node theo tên: %s", exc)
        return
    entity_ids = [str(row.get("entity_id") or "") for row in rows]
    entity_ids = [e for e in entity_ids if e]
    if entity_ids:
        _enrich_graph_from_db(entity_ids, nodes, edges)


def _fallback_entity_records(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Lấy thuộc tính đầy đủ của entity đã link (fallback khi Cypher rỗng).

    Args:
        entities: Entity đã link trong câu hỏi.

    Returns:
        Danh sách record (mỗi record là 1 dict thuộc tính).
    """
    if not entities:
        return []
    from backend.app.services import neo4j_client

    ids = [str(e.get("entity_id") or "") for e in entities if e.get("entity_id")]
    if not ids:
        return []
    try:
        rows = neo4j_client.run_read_query(
            """
            MATCH (n)
            WHERE n.entity_id IN $ids
            RETURN n.entity_id AS entity_id,
                   n.name AS name,
                   n.description AS description,
                   n.birth_year AS birth_year,
                   n.death_year AS death_year,
                   n.reign_start AS reign_start,
                   n.reign_end AS reign_end,
                   n.reign_title AS reign_title,
                   n.temple_name AS temple_name,
                   n.posthumous_name AS posthumous_name,
                   n.gender AS gender,
                   n.birth_place AS birth_place,
                   n.death_place AS death_place,
                   n.start_year AS start_year,
                   n.end_year AS end_year,
                   n.wiki_url AS wiki_url
            LIMIT 20
            """,
            {"ids": ids[:20]},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không lấy được thuộc tính entity: %s", exc)
        return []
    records: list[dict[str, Any]] = []
    for row in rows:
        record = {k: v for k, v in row.items() if v is not None}
        # Bổ sung năm sự kiện suy từ tên ("Trận Bạch Đằng (1288)").
        if "start_year" not in record:
            year = _year_from_name(str(row.get("name") or ""))
            if year:
                record["start_year"] = year
        if record:
            records.append(record)
    return records


def _year_from_name(name: str) -> int | None:
    """Suy ra năm từ tên entity, vd "Trận Bạch Đằng (1288)" → 1288.

    Args:
        name: Tên hiển thị của entity.

    Returns:
        Năm nếu tìm được, ngược lại ``None``.
    """
    match = re.search(r"\((\d{3,4})\)", name)
    if match:
        return int(match.group(1))
    return None


def _enrich_graph_from_db(
    entity_ids: set[str],
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    """Bổ sung node/edge thật từ Neo4j cho các `entity_id` đã biết.

    Args:
        entity_ids: Set id node cần lấy.
        nodes: Dict node (được cập nhật tại chỗ).
        edges: List edge (được cập nhật tại chỗ).
    """
    from backend.app.services import neo4j_client

    ids = sorted(entity_ids)[:60]
    try:
        node_rows = neo4j_client.run_read_query(
            """
            MATCH (n)
            WHERE n.entity_id IN $ids
            RETURN n.entity_id AS entity_id,
                   n.name AS name,
                   head(labels(n)) AS label,
                   n.birth_year AS birth_year,
                   n.death_year AS death_year,
                   n.reign_start AS reign_start,
                   n.reign_end AS reign_end,
                   n.verified AS verified
            LIMIT 60
            """,
            {"ids": ids},
        )
        edge_rows = neo4j_client.run_read_query(
            """
            MATCH (a)-[r]->(b)
            WHERE a.entity_id IN $ids OR b.entity_id IN $ids
            RETURN a.entity_id AS source,
                   b.entity_id AS target,
                   type(r) AS relation,
                   b.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT 120
            """,
            {"ids": ids},
        )
    except Exception as exc:  # noqa: BLE001 - lỗi DB không được làm hỏng câu trả lời
        logger.warning("Không lấy được đồ thị từ DB: %s", exc)
        return

    for row in node_rows:
        entity_id = str(row.get("entity_id") or "")
        if not entity_id:
            continue
        name = str(row.get("name") or entity_id)
        nodes[entity_id] = {
            "id": entity_id,
            "label": str(row.get("label") or "Entity"),
            "name": name,
            "birth_year": row.get("birth_year"),
            "death_year": row.get("death_year"),
            "reign_start": row.get("reign_start"),
            "reign_end": row.get("reign_end"),
            # Sự kiện thường không có `start_year` mà có năm trong tên
            # ("Trận Bạch Đằng (1288)") — suy ra để trả lời được.
            "event_year": _year_from_name(name),
            "verified": row.get("verified") is not False,
        }

    # Năm sinh/mất có thể nằm ở QUAN HỆ `sinh_nam`/`mat_nam` tới node `Year`
    # thay vì ở thuộc tính `birth_year`/`death_year` (chỉ ~7% người có infobox).
    # Bổ sung để node trong đồ thị hiển thị đúng năm (D-088).
    try:
        year_rows = neo4j_client.run_read_query(
            """
            MATCH (p)-[r]->(y:Year)
            WHERE p.entity_id IN $ids
              AND (type(r) = 'sinh_nam' OR type(r) = 'mat_nam')
            RETURN p.entity_id AS entity_id,
                   type(r) AS relation,
                   y.value AS year
            LIMIT 120
            """,
            {"ids": ids},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không lấy được năm sinh/mất từ quan hệ: %s", exc)
        year_rows = []

    for row in year_rows:
        entity_id = str(row.get("entity_id") or "")
        year = row.get("year")
        if not entity_id or year is None:
            continue
        target_node = nodes.get(entity_id)
        if target_node is None:
            continue
        field = "birth_year" if row.get("relation") == "sinh_nam" else "death_year"
        if target_node.get(field) is None:
            try:
                target_node[field] = int(year)
            except (TypeError, ValueError):
                continue

    for row in edge_rows:
        source = str(row.get("source") or "")
        target = str(row.get("target") or "")
        if not source or not target:
            continue
        edges.append({
            "source": source,
            "target": target,
            "relation": str(row.get("relation") or ""),
            "target_name": str(row.get("target_name") or ""),
            "confidence": row.get("confidence"),
            "evidence_sentence": row.get("evidence_sentence"),
            "source_url": row.get("source_url"),
            "method": row.get("method"),
        })
        # Thêm node lân cận (đầu cạnh khác) để đồ thị không bị "mồ côi".
        for endpoint in (source, target):
            if endpoint not in nodes:
                nodes[endpoint] = {
                    "id": endpoint,
                    "label": "Entity",
                    "name": endpoint,
                    "verified": True,
                }

    # Phase 13: loại cạnh nhiễu ("sinh_tai → Quốc lộ 14"). KG **không** đổi
    # (13.379 cạnh vẫn trong DB); chỉ lọc ở tầng đọc.
    edges = filter_noisy_edges(edges)

    # Lấy tên thật cho node lân cận mới thêm.
    missing = [eid for eid in nodes if nodes[eid]["label"] == "Entity"
               and nodes[eid]["name"] == eid]
    if missing:
        try:
            name_rows = neo4j_client.run_read_query(
                """
                MATCH (n)
                WHERE n.entity_id IN $ids
                RETURN n.entity_id AS entity_id,
                       n.name AS name,
                       head(labels(n)) AS label,
                       n.verified AS verified
                LIMIT 120
                """,
                {"ids": missing[:120]},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Không lấy được tên node lân cận: %s", exc)
        else:
            for row in name_rows:
                entity_id = str(row.get("entity_id") or "")
                if entity_id and entity_id in nodes:
                    nodes[entity_id]["name"] = str(row.get("name") or entity_id)
                    nodes[entity_id]["label"] = str(row.get("label") or "Entity")
                    nodes[entity_id]["verified"] = row.get("verified") is not False


def _primary_label(node: dict[str, Any]) -> str:
    """Suy ra nhãn chính của node từ dict Neo4j.

    Args:
        node: Dict thuộc tính node.

    Returns:
        Tên nhãn.
    """
    labels = node.get("labels")
    if isinstance(labels, list) and labels:
        for label in ("Person", "Place", "Event", "Dynasty", "Organization",
                      "Title", "Year", "Article", "Entity"):
            if label in labels:
                return label
    node_type = str(node.get("type") or "").strip().lower()
    mapping = {
        "person": "Person", "place": "Place", "event": "Event",
        "dynasty": "Dynasty", "organization": "Organization",
        "title": "Title", "year": "Year", "article": "Article",
    }
    return mapping.get(node_type, "Entity")

#!/usr/bin/env python3
"""Nạp KG vào Neo4j (Phase 10 — bước 3).

Đặc tính:
- **Idempotent**: node dùng `MERGE` theo `entity_id`; edge dùng `MERGE` theo
  `(source, target, type)`. Chạy lại 3 lần → số node/edge không đổi.
- **Không cần APOC**: Neo4j 5 Community không hỗ trợ dynamic label / dynamic
  relationship type ⇒ script **gom theo nhóm** (9 label, 18 quan hệ) và dựng
  câu Cypher tĩnh cho từng nhóm.
- Đọc `src/graph/schema.cypher` → chạy từng statement (bỏ qua lỗi "already
  exists").

Dùng:
    python scripts/load_neo4j.py --batch 1000
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.common.logger import get_logger  # noqa: E402

logger = get_logger("scripts.load_neo4j")

#: Nhãn hợp lệ.
VALID_LABELS = {
    "Person", "Place", "Event", "Dynasty", "Organization",
    "Title", "Year", "Article", "Entity",
}


def load_dotenv() -> None:
    """Nạp biến môi trường từ `.env` (không ghi đè biến đã có).

    Returns:
        None.
    """
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def split_statements(text: str) -> list[str]:
    """Tách file Cypher thành từng statement.

    Args:
        text: Nội dung file `.cypher`.

    Returns:
        Danh sách statement.
    """
    statements: list[str] = []
    buffer: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []
    if buffer:
        statement = "\n".join(buffer).strip().rstrip(";").strip()
        if statement:
            statements.append(statement)
    return statements


def read_graph(path: Path) -> tuple[list[dict], list[dict]]:
    """Đọc `graph.jsonl` (2 dòng: nodes + edges).

    Args:
        path: Đường dẫn file.

    Returns:
        Tuple `(nodes, edges)`.
    """
    nodes: list[dict] = []
    edges: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if payload.get("type") == "nodes":
                nodes = payload.get("items") or []
            elif payload.get("type") == "edges":
                edges = payload.get("items") or []
    return nodes, edges


def batches(items: list[Any], size: int) -> Iterator[list[Any]]:
    """Chia list thành batch.

    Args:
        items: Danh sách gốc.
        size: Kích thước batch.

    Yields:
        Từng batch.
    """
    for start in range(0, len(items), size):
        yield items[start : start + size]


def count_graph(driver: Any) -> tuple[int, int]:
    """Đếm node/edge hiện tại trong DB.

    Args:
        driver: Neo4j driver.

    Returns:
        Tuple `(nodes, edges)`.
    """
    with driver.session() as session:
        nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    return int(nodes), int(edges)


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Nạp KG vào Neo4j (Phase 10).")
    parser.add_argument(
        "--graph", default="data/knowledge_base/graph.jsonl",
    )
    parser.add_argument(
        "--schema", default="src/graph/schema.cypher",
    )
    parser.add_argument("--batch", type=int, default=1000)
    parser.add_argument("--uri", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument(
        "--skip-schema", action="store_true", help="Bỏ qua phần tạo constraint.",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Xóa toàn bộ node/edge trước khi nạp (dùng khi artifact đã đổi "
             "và cần nạp lại từ đầu, tránh sót cạnh cũ).",
    )
    args = parser.parse_args()

    load_dotenv()
    from neo4j import GraphDatabase

    uri = args.uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = args.user or os.environ.get("NEO4J_USER", "neo4j")
    password = args.password or os.environ.get("NEO4J_PASSWORD", "neo4jpass")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    try:
        driver.verify_connectivity()
        logger.info("Kết nối Neo4j tại %s OK", uri)

        if not args.skip_schema:
            schema_path = REPO_ROOT / args.schema
            statements = split_statements(schema_path.read_text(encoding="utf-8"))
            with driver.session() as session:
                for statement in statements:
                    try:
                        session.run(statement).consume()
                    except Exception as exc:  # noqa: BLE001 - "already exists" là bình thường
                        if "already exists" not in str(exc).lower():
                            logger.warning(
                                "Schema lỗi: %s | %s", str(exc)[:120], statement[:60]
                            )
            logger.info("Đã áp dụng %d statement schema", len(statements))

        nodes, edges = read_graph(Path(args.graph))
        logger.info("Đọc %d node · %d edge", len(nodes), len(edges))

        before = count_graph(driver)
        logger.info("Trước khi nạp: %d node · %d edge", *before)

        if args.reset:
            # Xóa theo lô (LIMIT 5000) vì xóa 335k edge cùng lúc vượt quá
            # `dbms.memory.transaction.total.max` của Neo4j Community.
            deleted_edges = deleted_nodes = 0
            with driver.session() as session:
                while True:
                    batch = session.run(
                        "MATCH ()-[r]->() WITH r LIMIT 5000 DELETE r "
                        "RETURN count(r) AS c"
                    ).single()["c"]
                    deleted_edges += batch
                    if not batch:
                        break
                while True:
                    batch = session.run(
                        "MATCH (n) WITH n LIMIT 5000 DETACH DELETE n "
                        "RETURN count(n) AS c"
                    ).single()["c"]
                    deleted_nodes += batch
                    if not batch:
                        break
            logger.info(
                "Đã xóa graph cũ (--reset): %d edge · %d node",
                deleted_edges, deleted_nodes,
            )

        # --- Gom node theo label ---
        by_label: dict[str, list[dict]] = defaultdict(list)
        for node in nodes:
            label = str(node.get("label") or "")
            if label not in VALID_LABELS:
                logger.warning("Bỏ node có label lạ: %s", label)
                continue
            by_label[label].append(node)

        # Neo4j chỉ nhận property kiểu primitive/array ⇒ `aliases` (list of
        # dict) phải chuyển thành JSON string.
        def sanitize_props(props: dict[str, Any]) -> dict[str, Any]:
            """Chuyển property không hợp lệ (dict/list-of-dict) sang JSON string.

            Args:
                props: Dict property gốc.

            Returns:
                Dict property đã chuẩn hóa.
            """
            clean: dict[str, Any] = {}
            for key, value in props.items():
                if value is None:
                    continue
                if isinstance(value, (str, int, float, bool)):
                    clean[key] = value
                elif isinstance(value, list) and all(
                    isinstance(v, (str, int, float, bool)) for v in value
                ):
                    clean[key] = value
                else:
                    clean[key] = json.dumps(value, ensure_ascii=False)
            return clean

        started = time.time()
        n_nodes = 0
        with driver.session() as session:
            for label, group in by_label.items():
                rows = [
                    {
                        "entity_id": n["entity_id"],
                        "props": sanitize_props(n.get("props") or {}),
                    }
                    for n in group
                ]
                # `SET n += props` KHÔNG xóa property cũ không còn trong
                # artifact (vd `birth_year` đã bị loại) ⇒ xóa hết property
                # cũ trước, rồi set lại từ artifact ⇒ nạp là đúng trạng thái
                # artifact (idempotent + tái lập).
                query = (
                    "UNWIND $batch AS row "
                    f"MERGE (n:{label} {{entity_id: row.entity_id}}) "
                    "WITH n, row "
                    "SET n = {} "
                    "SET n += row.props "
                    "RETURN count(n)"
                )
                for batch in batches(rows, args.batch):
                    session.run(query, batch=batch).consume()
                    n_nodes += len(batch)
                logger.info("Nạp label %s: %d node", label, len(rows))
        logger.info("Nạp %d node trong %.1fs", n_nodes, time.time() - started)

        # --- Gom edge theo quan hệ ---
        # Neo4j 5 Community **không hỗ trợ** index toàn cục (`FOR (n) ON (...)`
        # bị SyntaxError) ⇒ `MATCH (s {entity_id: ...})` không kèm label sẽ
        # full-scan toàn bộ node cho mỗi dòng (nạp 335k edge bị nghẽn ~0
        # edge/30s). Vì vậy phải MATCH **kèm label** để dùng được unique
        # constraint theo label (index có sẵn ở `src/graph/schema.cypher`).
        label_of: dict[str, str] = {
            str(n.get("entity_id")): str(n.get("label"))
            for n in nodes
            if n.get("entity_id") and n.get("label") in VALID_LABELS
        }
        by_relation: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
        n_no_label = 0
        for edge in edges:
            edge_type = str(edge.get("type") or "")
            if not re.fullmatch(r"[a-z_]{3,40}", edge_type):
                logger.warning("Bỏ edge có type lạ: %s", edge_type)
                continue
            src_label = label_of.get(str(edge.get("source")))
            tgt_label = label_of.get(str(edge.get("target")))
            if not src_label or not tgt_label:
                n_no_label += 1
                continue
            by_relation[(src_label, tgt_label, edge_type)].append(edge)
        if n_no_label:
            logger.warning("Bỏ %d edge không tra được label node", n_no_label)

        started = time.time()
        n_edges = 0
        with driver.session() as session:
            for (src_label, tgt_label, edge_type), group in by_relation.items():
                rows = [
                    {
                        "source": e["source"],
                        "target": e["target"],
                        "props": sanitize_props(e.get("props") or {}),
                    }
                    for e in group
                ]
                # MERGE theo (source, target) ⇒ idempotent.
                # `confidence` chỉ được ghi đè khi giá trị mới CAO HƠN.
                query = (
                    "UNWIND $batch AS row "
                    f"MATCH (s:{src_label} {{entity_id: row.source}}) "
                    f"MATCH (t:{tgt_label} {{entity_id: row.target}}) "
                    f"MERGE (s)-[r:{edge_type}]->(t) "
                    "SET r += row.props "
                    "WITH r, row "
                    "SET r.confidence = CASE "
                    "WHEN r.confidence IS NULL OR row.props.confidence > r.confidence "
                    "THEN row.props.confidence ELSE r.confidence END "
                    "RETURN count(r)"
                )
                for batch in batches(rows, args.batch):
                    session.run(query, batch=batch).consume()
                    n_edges += len(batch)
                logger.info(
                    "Nạp quan hệ %s (%s→%s): %d edge",
                    edge_type, src_label, tgt_label, len(rows),
                )
        logger.info("Nạp %d edge trong %.1fs", n_edges, time.time() - started)

        after = count_graph(driver)
        logger.info("Sau khi nạp: %d node · %d edge", *after)
        logger.info(
            "Tăng: +%d node · +%d edge",
            after[0] - before[0], after[1] - before[1],
        )
        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())

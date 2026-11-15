#!/usr/bin/env python3
"""Kiểm tra chất lượng KG trong Neo4j (Phase 10 — bước 5).

10 kiểm tra theo `docs/04-schema-knowledge-graph.md` §10. In bảng PASS/FAIL;
exit code ≠ 0 nếu có lỗi nghiêm trọng (thiếu prop bắt buộc, quan hệ lạ,
edge trùng, node nhiều nhãn chính, mâu thuẫn năm).

Dùng:
    python scripts/validate_graph.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.common.logger import get_logger  # noqa: E402
from src.common.schemas import RELATION_TYPES  # noqa: E402

logger = get_logger("scripts.validate_graph")

#: Khoảng năm sinh hợp lệ cho `Person`.
BIRTH_YEAR_MIN = 500
BIRTH_YEAR_MAX = 2000

#: Nhãn chính theo schema (mỗi node chỉ được mang 1 nhãn chính).
PRIMARY_LABELS = {
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


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = không có lỗi nghiêm trọng).
    """
    parser = argparse.ArgumentParser(description="Kiểm tra chất lượng KG (Phase 10).")
    parser.add_argument("--uri", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    load_dotenv()
    from neo4j import GraphDatabase

    uri = args.uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = args.user or os.environ.get("NEO4J_USER", "neo4j")
    password = args.password or os.environ.get("NEO4J_PASSWORD", "neo4jpass")

    driver = GraphDatabase.driver(uri, auth=(user, password))
    checks: list[tuple[str, bool, str, bool]] = []
    try:
        with driver.session() as session:
            def one(query: str, **params: object) -> int:
                record = session.run(query, **params).single()
                return int(record["c"]) if record else 0

            n_nodes = one("MATCH (n) RETURN count(n) AS c")
            n_edges = one("MATCH ()-[r]->() RETURN count(r) AS c")

            # 1. Node thiếu `entity_id` → 0
            missing_id = one(
                "MATCH (n) WHERE n.entity_id IS NULL OR n.entity_id = '' "
                "RETURN count(n) AS c"
            )
            checks.append((
                "Node thiếu `entity_id`", missing_id == 0, f"{missing_id}/{n_nodes}", True,
            ))
            # 2. Node thiếu `wiki_url` → 0
            missing_url = one(
                "MATCH (n) WHERE n.wiki_url IS NULL OR n.wiki_url = '' "
                "RETURN count(n) AS c"
            )
            checks.append((
                "Node thiếu `wiki_url`", missing_url == 0, f"{missing_url}/{n_nodes}", True,
            ))
            # 3. Cạnh thiếu `evidence_sentence` → 0
            missing_ev = one(
                "MATCH ()-[r]->() WHERE r.evidence_sentence IS NULL "
                "OR r.evidence_sentence = '' RETURN count(r) AS c"
            )
            checks.append((
                "Cạnh thiếu `evidence_sentence`", missing_ev == 0,
                f"{missing_ev}/{n_edges}", True,
            ))
            # 4. Cạnh thiếu `source_url` → 0
            missing_src = one(
                "MATCH ()-[r]->() WHERE r.source_url IS NULL OR r.source_url = '' "
                "RETURN count(r) AS c"
            )
            checks.append((
                "Cạnh thiếu `source_url`", missing_src == 0, f"{missing_src}/{n_edges}", True,
            ))
            # 5. Cạnh thiếu `confidence` / `method` → 0
            missing_conf = one(
                "MATCH ()-[r]->() WHERE r.confidence IS NULL OR r.confidence < 0 "
                "OR r.confidence > 1 RETURN count(r) AS c"
            )
            checks.append((
                "Cạnh thiếu `confidence` hợp lệ", missing_conf == 0,
                f"{missing_conf}/{n_edges}", True,
            ))
            missing_meth = one(
                "MATCH ()-[r]->() WHERE r.method IS NULL OR r.method = '' "
                "RETURN count(r) AS c"
            )
            checks.append((
                "Cạnh thiếu `method`", missing_meth == 0, f"{missing_meth}/{n_edges}", True,
            ))
            # 6. Quan hệ ngoài danh mục → 0
            bad_rel = one(
                "MATCH ()-[r]->() WHERE NOT type(r) IN $rels RETURN count(r) AS c",
                rels=sorted(RELATION_TYPES),
            )
            checks.append((
                "Quan hệ ngoài danh mục 18", bad_rel == 0, f"{bad_rel}/{n_edges}", True,
            ))
            # 7. Cạnh trùng lặp do quan hệ đối xứng → 0
            dup_edge = one(
                "MATCH ()-[r]->() WITH r, count(r) AS c WHERE c > 1 RETURN count(r) AS c"
            )
            checks.append((
                "Cạnh trùng lặp", dup_edge == 0, f"{dup_edge}/{n_edges}", True,
            ))
            # 8. Node có nhiều hơn 1 nhãn chính → 0
            multi_label = one(
                "MATCH (n) WITH n, size(labels(n)) AS c "
                "WHERE c > 1 RETURN count(n) AS c"
            )
            checks.append((
                "Node có > 1 nhãn", multi_label == 0, f"{multi_label}/{n_nodes}", True,
            ))
            # 8b. Node có `entity_id` trùng (sẽ vi phạm constraint)
            dup_id = one(
                "MATCH (n) WITH n.entity_id AS e, count(n) AS c "
                "WHERE e IS NOT NULL AND c > 1 RETURN count(e) AS c"
            )
            checks.append((
                "Node trùng `entity_id`", dup_id == 0, f"{dup_id}", True,
            ))
            # 9. Person có `birth_year` ngoài [500, 2000] → đánh dấu review
            out_range = one(
                "MATCH (n:Person) WHERE n.birth_year IS NOT NULL "
                "AND (n.birth_year < $lo OR n.birth_year > $hi) RETURN count(n) AS c",
                lo=BIRTH_YEAR_MIN, hi=BIRTH_YEAR_MAX,
            )
            checks.append((
                "Person `birth_year` ngoài [500, 2000] (cần review)",
                out_range == 0, f"{out_range} node", False,
            ))
            # 10. Person có `birth_year > death_year` → mâu thuẫn
            conflict = one(
                "MATCH (n:Person) WHERE n.birth_year IS NOT NULL "
                "AND n.death_year IS NOT NULL AND n.birth_year > n.death_year "
                "RETURN count(n) AS c"
            )
            checks.append((
                "Person mâu thuẫn `birth_year > death_year`",
                conflict == 0, f"{conflict} node", True,
            ))
            # 11. Self-loop → 0
            self_loop = one(
                "MATCH (a)-[r]->(b) WHERE a.entity_id = b.entity_id RETURN count(r) AS c"
            )
            checks.append((
                "Self-loop", self_loop == 0, f"{self_loop}/{n_edges}", True,
            ))
    finally:
        driver.close()

    print("=" * 74)
    print("PHASE 10 — KIỂM ĐỊNH CHẤT LƯỢNG KG")
    print("=" * 74)
    n_fail = 0
    for name, passed, detail, severe in checks:
        status = "PASS" if passed else ("FAIL" if severe else "WARN")
        if not passed and severe:
            n_fail += 1
        print(f"  [{status:4s}] {name}: {detail}")
    print("-" * 74)
    print(f"KẾT QUẢ: {len(checks) - n_fail}/{len(checks)} PASS (có {n_fail} lỗi nghiêm trọng)")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())

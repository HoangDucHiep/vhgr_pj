"""Test cho validator Cypher tĩnh (Phase 11 — Gate G2).

- ≥ 20 payload độc hại phải bị chặn.
- ≥ 10 Cypher hợp lệ phải pass (và câu thiếu `LIMIT` được bổ sung).
"""

from __future__ import annotations

import pytest

from backend.app.services.cypher_validator import (
    extract_relations,
    strip_string_literals,
    validate_cypher,
)

#: 20+ payload độc hại.
MALICIOUS = [
    "MATCH (n) DETACH DELETE n",
    "MATCH (n) SET n.x = 1",
    "MATCH (n) REMOVE n.x",
    "CREATE (n:Foo {id: 1})",
    "MERGE (n:Person {entity_id: 'x'})",
    "MATCH (n) DELETE n",
    "DROP DATABASE neo4j",
    "DROP INDEX ON :Person(entity_id)",
    "CALL db.labels()",
    "CALL dbms.listQueries()",
    "CALL apoc.periodic.iterate()",
    "LOAD CSV FROM 'file:///etc/passwd' AS line RETURN line",
    "FOREACH (x IN [1] | CREATE (:Foo))",
    "MATCH (n) SET n.x = 1 // ghi",
    "MATCH (n) /* comment */ DETACH DELETE n",
    "MATCH (n) RETURN n LIMIT 10; MATCH (m) DELETE m",
    "MATCH (n) RETURN n LIMIT 10; DROP DATABASE neo4j",
    "MATCH (n) SET n.a = 1 RETURN n LIMIT 5",
    "ALTER CURRENT USER SET PASSWORD FROM 'x' TO 'y'",
    "GRANT MATCH ON GRAPH neo4j TO reader",
    "REVOKE MATCH ON GRAPH neo4j FROM reader",
    "MATCH (n) RETURN n LIMIT 100 CALL db.labels()",
    "MATCH (n)-[:ke_vi]->(m) RETURN n LIMIT 1000",
    "MATCH (n)-[:bogus_relation]->(m) RETURN n LIMIT 5",
    "DELETE FROM Person WHERE entity_id = 'x'",
    "MATCH (n) RETURN n LIMIT 5 UNION MATCH (m) CREATE (m:Foo)",
]

#: 12 Cypher hợp lệ.
VALID = [
    "MATCH (p:Person {entity_id: 'ent_le_loi_1a2b3c4d'}) RETURN p.birth_year LIMIT 1",
    "MATCH (p:Person) RETURN p.name LIMIT 50",
    "MATCH (p:Person)-[:thuoc_trieu_dai]->(d:Dynasty) RETURN d.name LIMIT 50",
    "MATCH (p:Person)-[:sinh_nam]->(y:Year) RETURN y.value LIMIT 50",
    "MATCH (p:Person) WHERE p.birth_year > 1800 RETURN p.name LIMIT 50",
    "MATCH (p:Person) RETURN COUNT(p) AS total LIMIT 1",
    "OPTIONAL MATCH (p:Person)-[:cha_cua]->(f:Person) RETURN p.name, f.name LIMIT 50",
    "MATCH (p:Person) RETURN p.name ORDER BY p.birth_year DESC LIMIT 10",
    "MATCH (e:Event)-[:dien_ra_tai]->(pl:Place) RETURN e.name LIMIT 50",
    "WITH 1 AS x RETURN x LIMIT 1",
    "MATCH (p:Person) WHERE p.name_normalized = 'le loi' RETURN p.birth_year LIMIT 1",
    "UNWIND [1,2,3] AS x RETURN x LIMIT 3",
]


@pytest.mark.parametrize("payload", MALICIOUS)
def test_malicious_blocked(payload: str) -> None:
    """Payload độc hại phải bị từ chối.

    Args:
        payload: Chuỗi Cypher độc hại.
    """
    ok, reason, _ = validate_cypher(payload)
    assert not ok, f"Phải chặn: {payload}"
    assert reason


@pytest.mark.parametrize("cypher", VALID)
def test_valid_accepted(cypher: str) -> None:
    """Cypher hợp lệ phải được pass.

    Args:
        cypher: Chuỗi Cypher hợp lệ.
    """
    ok, reason, fixed = validate_cypher(cypher)
    assert ok, f"Phải pass: {cypher} — {reason}"
    assert fixed


def test_missing_limit_gets_default() -> None:
    """Câu thiếu `LIMIT` phải được bổ sung `LIMIT 50`."""
    ok, reason, fixed = validate_cypher("MATCH (p:Person) RETURN p.name")
    assert ok, reason
    assert "LIMIT 50" in fixed.upper()


def test_limit_over_max_rejected() -> None:
    """`LIMIT > 100` phải bị từ chối."""
    ok, _, _ = validate_cypher("MATCH (n) RETURN n LIMIT 500")
    assert not ok


def test_limit_exactly_max_ok() -> None:
    """`LIMIT = 100` phải được chấp nhận."""
    ok, reason, _ = validate_cypher("MATCH (n) RETURN n LIMIT 100")
    assert ok, reason


def test_semicolon_blocked() -> None:
    """Dấu `;` nối nhiều câu phải bị chặn."""
    ok, _, _ = validate_cypher("MATCH (n) RETURN n LIMIT 5; MATCH (m) RETURN m LIMIT 5")
    assert not ok


def test_keyword_inside_string_literal_allowed() -> None:
    """Từ khóa nằm trong string literal không phải là lệnh ghi."""
    ok, reason, fixed = validate_cypher(
        "MATCH (p:Person) WHERE p.name CONTAINS 'DELETE' RETURN p.name LIMIT 5"
    )
    assert ok, reason
    assert "DELETE" in fixed


def test_escape_in_string_literal() -> None:
    """Escape trong string literal không được làm lộ từ khóa."""
    payload = "MATCH (p:Person) WHERE p.name = 'a\\' DELETE' RETURN p.name LIMIT 5"
    ok, reason, _ = validate_cypher(payload)
    assert ok, reason


def test_relation_outside_catalog_rejected() -> None:
    """Quan hệ ngoài danh mục 18 phải bị từ chối."""
    ok, reason, _ = validate_cypher(
        "MATCH (a)-[:khong_ton_tai]->(b) RETURN a LIMIT 5"
    )
    assert not ok
    assert "khong_ton_tai" in reason


def test_relation_extraction() -> None:
    """Trích quan hệ từ câu nhiều dạng.

    Args:
        None.
    """
    relations = extract_relations(
        "MATCH (a:Person)-[r:ke_vi]->(b:Person)-[:thuoc_trieu_dai]->(d:Dynasty) "
        "RETURN a LIMIT 5"
    )
    assert relations == {"ke_vi", "thuoc_trieu_dai"}


def test_strip_string_literals_keeps_length() -> None:
    """Bỏ string literal phải giữ nguyên độ dài chuỗi.

    Args:
        None.
    """
    text = "MATCH (n) WHERE n.name = 'abc' RETURN n"
    stripped = strip_string_literals(text)
    assert len(stripped) == len(text)
    assert "abc" not in stripped


def test_empty_cypher_rejected() -> None:
    """Câu rỗng phải bị từ chối."""
    ok, _, _ = validate_cypher("   ")
    assert not ok


def test_must_start_with_allowed_keyword() -> None:
    """Câu không bắt đầu bằng từ khóa cho phép phải bị từ chối."""
    ok, _, _ = validate_cypher("SHOW DATABASES")
    assert not ok

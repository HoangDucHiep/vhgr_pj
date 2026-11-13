"""Probe: tìm người thuộc 9 triều đại qua chuỗi quan hệ tổ tiên (P22/P25/P26)."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://qlever.dev/api/wikidata"
PREFIXES = """PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX schema: <http://schema.org/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""

DYNASTIES = [
    "Q703919",
    "Q1372154",
    "Q1317884",
    "Q878309",
    "Q3111454",
    "Q1209047",
    "Q878276",
    "Q1034173",
    "Q6500483",
]
VALUES = " ".join(f"wd:{q}" for q in DYNASTIES)

SITELINK = "  ?article schema:about ?p ; schema:isPartOf <https://vi.wikipedia.org/> .\n"


def query(sql: str) -> list[list[str]]:
    """Chạy query và trả về ma trận kết quả."""
    params = urllib.parse.urlencode({"query": PREFIXES + sql})
    for attempt in range(5):
        request = urllib.request.Request(
            ENDPOINT,
            data=params.encode("utf-8"),
            headers={
                "Accept": "application/qlever-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if "exception" in payload:
                return [[payload["exception"]]]
            return payload["res"]
        except Exception as exc:  # noqa: BLE001
            if attempt == 4:
                return [[f"ERROR {exc}"]]
            time.sleep(5 * (attempt + 1))
    return []


QUERIES = {
    "dynasty_members_P463_P361": f"""
SELECT DISTINCT ?p ?d WHERE {{
  VALUES ?d {{ {VALUES} }}
  {{ ?p wdt:P463 ?d }} UNION {{ ?p wdt:P361 ?d }}
}}""",
    "person_parent_is_dynasty": f"""
SELECT DISTINCT ?p ?d WHERE {{
  VALUES ?d {{ {VALUES} }}
  {{ ?p wdt:P22 ?d }} UNION {{ ?p wdt:P25 ?d }}
}}""",
    "person_grandparent_is_dynasty": f"""
SELECT DISTINCT ?p ?d WHERE {{
  VALUES ?d {{ {VALUES} }}
  {{ ?p wdt:P22/wdt:P22 ?d }} UNION {{ ?p wdt:P22/wdt:P25 ?d }}
  UNION {{ ?p wdt:P25/wdt:P22 ?d }} UNION {{ ?p wdt:P25/wdt:P25 ?d }}
}}""",
    "dynasty_contains_person_P527": f"""
SELECT DISTINCT ?p ?d WHERE {{
  VALUES ?d {{ {VALUES} }}
  ?d wdt:P527 ?p .
}}""",
    "battle_in_vietnam_country": """
SELECT DISTINCT ?p WHERE {
  ?p wdt:P31/wdt:P279* wd:Q178561 .
  { ?p wdt:P17 wd:Q881 } UNION { ?p wdt:P276/wdt:P17 wd:Q881 }
  ?article schema:about ?p ; schema:isPartOf <https://vi.wikipedia.org/> .
}""",
    "battle_part_of_dynasty": f"""
SELECT DISTINCT ?p ?d WHERE {{
  VALUES ?d {{ {VALUES} }}
  ?p wdt:P361 ?d .
  ?article schema:about ?p ; schema:isPartOf <https://vi.wikipedia.org/> .
}}""",
}

for name, sql in QUERIES.items():
    rows = query(sql)
    print(f"{name:32s} {len(rows)}", flush=True)
    if rows and len(rows) <= 30:
        for row in rows[:10]:
            print("   ", row)
    time.sleep(2)

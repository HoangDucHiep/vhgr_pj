"""Đếm nhanh các tín hiệu Wikidata để thiết kế bộ lọc Phase 1 (v3)."""

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


def count(query: str) -> int:
    """Chạy query COUNT và trả về số kết quả (có retry khi 429)."""
    params = urllib.parse.urlencode({"query": PREFIXES + query})
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
                return -1
            row = payload["res"][0]
            return int(str(row[0]).split("^^")[0].strip('"'))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (attempt + 1))
    return -1


SITELINK = "  ?article schema:about ?p ; schema:isPartOf <https://vi.wikipedia.org/> .\n"

QUERIES = {
    "H1_human_birth_lt1950_viwiki": f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b .
  FILTER(YEAR(?b) < 1950)
{SITELINK}}}""",
    "H2_human_birth_lt1900_viwiki": f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b .
  FILTER(YEAR(?b) < 1900)
{SITELINK}}}""",
    "H3_union_vn_person": f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b .
  FILTER(YEAR(?b) < 1950)
  {{ ?p wdt:P27 wd:Q881 }}
  UNION
  {{ ?p wdt:P19/wdt:P17 wd:Q881 }}
  UNION
  {{ ?p wdt:P39/wdt:P17 wd:Q881 }}
{SITELINK}}}""",
    "H4_union_vn_person_birth_lt1900": f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b .
  FILTER(YEAR(?b) < 1900)
  {{ ?p wdt:P27 wd:Q881 }}
  UNION
  {{ ?p wdt:P19/wdt:P17 wd:Q881 }}
  UNION
  {{ ?p wdt:P39/wdt:P17 wd:Q881 }}
{SITELINK}}}""",
    "H5_human_birth_lt1950_viwiki_no_citizenship": f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b .
  FILTER(YEAR(?b) < 1950)
  FILTER NOT EXISTS {{ ?p wdt:P27 wd:Q881 }}
{SITELINK}}}""",
    "H6_dynasty_event_battle": """
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {
  { ?p wdt:P31 wd:Q164950 }
  UNION
  { ?p wdt:P31 wd:Q1656682 }
  UNION
  { ?p wdt:P31/wdt:P279* wd:Q178561 }
  ?article schema:about ?p ; schema:isPartOf <https://vi.wikipedia.org/> .
}""",
    "H7_settlement_vn_inception_lt1900": """
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {
  ?p wdt:P31/wdt:P279* wd:Q486972 ; wdt:P571 ?i .
  FILTER(YEAR(?i) < 1900)
  ?article schema:about ?p ; schema:isPartOf <https://vi.wikipedia.org/> .
}""",
}

for name, query in QUERIES.items():
    print(f"{name:44s} {count(query)}", flush=True)
    time.sleep(2)

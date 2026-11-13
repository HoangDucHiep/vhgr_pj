"""Probe: chốt query T0 theo khoảng năm của 9 triều đại."""

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
SITE = "  ?article schema:about ?p ; schema:isPartOf <https://vi.wikipedia.org/> .\n"

VN_LINK = """  { ?p wdt:P27 wd:Q881 }
  UNION
  { ?p wdt:P19/wdt:P17 wd:Q881 }
  UNION
  { ?p wdt:P39/wdt:P17 wd:Q881 }
"""


def query(sql: str) -> list[list[str]]:
    """Chạy query và trả về ma trận kết quả."""
    params = urllib.parse.urlencode({"query": PREFIXES + sql})
    for attempt in range(6):
        request = urllib.request.Request(
            ENDPOINT,
            data=params.encode("utf-8"),
            headers={
                "Accept": "application/qlever-results+json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if "exception" in payload:
                return [[payload["exception"]]]
            return payload["res"]
        except Exception as exc:  # noqa: BLE001
            if attempt == 5:
                return [[f"ERROR {exc}"]]
            time.sleep(8 * (attempt + 1))
    return []


def count(name: str, sql: str) -> int:
    """Chạy query COUNT và in kết quả."""
    rows = query(sql)
    value = rows[0][0] if rows and rows[0] else "?"
    print(f"{name:46s} {value}", flush=True)
    time.sleep(2)
    return -1


def main() -> None:
    """Chạy toàn bộ probe."""
    for year in (1900, 1920, 1850, 1800, 1950):
        count(
            f"person vn-link birth<{year}",
            f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b .
  FILTER(YEAR(?b) < {year})
{VN_LINK}{SITE}}}""",
        )

    count(
        "person vn-link birth 850..1900",
        f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b .
  FILTER(YEAR(?b) > 850 && YEAR(?b) < 1900)
{VN_LINK}{SITE}}}""",
    )

    count(
        "person vn-link birth 850..1900 + parent",
        f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q5 ; wdt:P569 ?b ; wdt:P22 ?par .
  FILTER(YEAR(?b) > 850 && YEAR(?b) < 1900)
{VN_LINK}{SITE}}}""",
    )

    for year in (1900, 1945, 1800):
        count(
            f"battle vn any, start<{year}",
            f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31/wdt:P279* wd:Q178561 ; wdt:P580 ?s .
  FILTER(YEAR(?s) < {year})
{SITE}}}""",
        )

    count(
        "battle vn place, start<1945",
        f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31/wdt:P279* wd:Q178561 ; wdt:P580 ?s .
  FILTER(YEAR(?s) < 1945)
  {{ ?p wdt:P17 wd:Q881 }} UNION {{ ?p wdt:P276/wdt:P17 wd:Q881 }}
{SITE}}}""",
    )

    count(
        "dynasty class",
        f"""
SELECT (COUNT(DISTINCT ?p) AS ?c) WHERE {{
  ?p wdt:P31 wd:Q164950 .
{SITE}}}""",
    )


if __name__ == "__main__":
    main()

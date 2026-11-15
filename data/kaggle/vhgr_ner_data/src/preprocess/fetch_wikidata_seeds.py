"""Tải tập seed bài lịch sử Việt Nam từ Wikidata (tín hiệu T0 — Phase 1).

## Chiến lược

Sáu truy vấn SPARQL riêng, mỗi truy vấn gắn **nhãn tín hiệu** và **mốc thời
gian** để sau đó cắt theo cửa sổ lịch sử của 9 triều đại (938–1945):

| `?signal` | Điều kiện Wikidata | Mốc thời gian |
|---|---|---|
| `person` | `P31=Q5` + `P569` + (một trong: `P27=Q881`, `P19/P17=Q881`, `P39/P17=Q881`) | năm sinh |
| `battle` | `P31/P279* = Q178561` | `P580` (năm bắt đầu) |
| `dynasty` | `P31 = Q164950` | `P571` (năm thành lập) |
| `house` | một trong 9 QID triều đại đã verify | `P571` |
| `event` | `P31 = Q1656682` | `P580` |
| `place` | `P17 = Q881` + `P571` | năm thành lập |

Kết quả ghi ra `data/interim/wikidata_seed_articles.json`:

```json
{
  "dump_version": "20261101",
  "entries": {
    "Lê Lợi": {"qid": "Q...", "signal": "person", "year": 1385, "signals": ["person"]}
  }
}
```

Chạy:
    python -m src.preprocess.fetch_wikidata_seeds --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT, load_config
from src.common.logger import get_logger
from src.preprocess.wikidata_query import PREFIXES, run_query

logger = get_logger(__name__)

#: Namespace 0 của Wikipedia tiếng Việt.
VIWIKI = "https://vi.wikipedia.org/"

#: Ngưỡng năm sinh tối đa để coi là nhân vật lịch sử.
MAX_BIRTH_YEAR = 1950

#: Ngưỡng năm thành lập tối đa cho địa danh.
MAX_PLACE_INCEPTION_YEAR = 1900

#: Ngưỡng năm bắt đầu tối đa cho trận đánh / sự kiện.
MAX_EVENT_START_YEAR = 1945

#: 9 QID triều đại đã verify trong `docs/CONTEXT.md`.
DYNASTY_QIDS = [
    "Q703919",  # Nhà Ngô
    "Q1372154",  # Nhà Đinh
    "Q1317884",  # Nhà Tiền Lê
    "Q878309",  # nhà Lý
    "Q3111454",  # nhà Trần
    "Q1209047",  # Nhà Hồ
    "Q878276",  # nhà Lê sơ
    "Q1034173",  # nhà Tây Sơn
    "Q6500483",  # nhà Nguyễn
]

_SITE = f"  ?article schema:about ?item ; schema:isPartOf <{VIWIKI}> .\n"


def _person_query() -> str:
    """Query người có mặt trong lịch sử Việt Nam."""
    return f"""{PREFIXES}
SELECT DISTINCT ?item ?article ?year WHERE {{
  ?item wdt:P31 wd:Q5 ;
        wdt:P569 ?birth .
  FILTER(YEAR(?birth) < {MAX_BIRTH_YEAR})
  {{ ?item wdt:P27 wd:Q881 }}
  UNION
  {{ ?item wdt:P19/wdt:P17 wd:Q881 }}
  UNION
  {{ ?item wdt:P39/wdt:P17 wd:Q881 }}
{_SITE}  BIND(YEAR(?birth) AS ?year)
}}
"""


def _battle_query() -> str:
    """Query trận đánh có bài tiếng Việt."""
    return f"""{PREFIXES}
SELECT DISTINCT ?item ?article ?year WHERE {{
  ?item wdt:P31/wdt:P279* wd:Q178561 ;
        wdt:P580 ?start .
  FILTER(YEAR(?start) < {MAX_EVENT_START_YEAR})
{_SITE}  BIND(YEAR(?start) AS ?year)
}}
"""


def _event_query() -> str:
    """Query sự kiện lịch sử."""
    return f"""{PREFIXES}
SELECT DISTINCT ?item ?article ?year WHERE {{
  ?item wdt:P31 wd:Q1656682 ;
        wdt:P580 ?start .
  FILTER(YEAR(?start) < {MAX_EVENT_START_YEAR})
{_SITE}  BIND(YEAR(?start) AS ?year)
}}
"""


def _dynasty_query() -> str:
    """Query nhà vua / triều đại (lớp `Q164950`)."""
    return f"""{PREFIXES}
SELECT DISTINCT ?item ?article ?year WHERE {{
  ?item wdt:P31 wd:Q164950 .
{_SITE}  OPTIONAL {{ ?item wdt:P571 ?inception }}
  BIND(YEAR(?inception) AS ?year)
}}
"""


def _house_query() -> str:
    """Query 9 triều đại đã verify (theo QID cụ thể)."""
    values = " ".join(f"wd:{qid}" for qid in DYNASTY_QIDS)
    return f"""{PREFIXES}
SELECT DISTINCT ?item ?article ?year WHERE {{
  VALUES ?item {{ {values} }}
{_SITE}  OPTIONAL {{ ?item wdt:P571 ?inception }}
  BIND(YEAR(?inception) AS ?year)
}}
"""


def _place_query() -> str:
    """Query địa danh thuộc Việt Nam, có mốc thành lập."""
    return f"""{PREFIXES}
SELECT DISTINCT ?item ?article ?year WHERE {{
  ?item wdt:P17 wd:Q881 ;
        wdt:P571 ?inception .
  FILTER(YEAR(?inception) < {MAX_PLACE_INCEPTION_YEAR})
{_SITE}  BIND(YEAR(?inception) AS ?year)
}}
"""


#: Danh sách (nhãn tín hiệu, hàm sinh query) — thứ tự ưu tiên khi gộp.
QUERY_BUILDERS: list[tuple[str, Any]] = [
    ("person", _person_query),
    ("battle", _battle_query),
    ("event", _event_query),
    ("dynasty", _dynasty_query),
    ("house", _house_query),
    ("place", _place_query),
]


def _strip_literal(value: str) -> str:
    """Bỏ dấu nháy, kiểu dữ liệu và ngôn ngữ của literal SPARQL.

    Args:
        value: Giá trị literal thô.

    Returns:
        Chuỗi đã làm sạch.
    """
    text = value.strip()
    if text.startswith('"'):
        end = text.rfind('"')
        if end > 0:
            text = text[1:end]
    if "@" in text:
        text = text.split("@", 1)[0]
    if "^^" in text:
        text = text.split("^^", 1)[0]
    text = text.strip().strip('"')
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1]
    return text.strip()


def _title_from_article(url: str) -> str:
    """Chuyển URL bài Wikipedia thành tiêu đề (giải mã URL).

    Args:
        url: URL bài, vd ``https://vi.wikipedia.org/wiki/L%C3%AA_L%E1%BB%A3i``.

    Returns:
        Tiêu đề bài.
    """
    from urllib.parse import unquote

    text = url.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        if end > 0:
            text = text[1:end]
    text = text.strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1]
    path = text.split("/wiki/", 1)[-1] if "/wiki/" in text else text.rsplit("/", 1)[-1]
    return unquote(path).replace("_", " ").strip()


def _qid_from_item(item_url: str) -> str:
    """Lấy QID từ URL item của Wikidata.

    Args:
        item_url: URL item, vd ``http://www.wikidata.org/entity/Q123``.

    Returns:
        QID hoặc chuỗi rỗng.
    """
    text = _strip_literal(item_url)
    return text.rsplit("/", 1)[-1] if "/entity/" in text else ""


def fetch_seeds() -> dict[str, Any]:
    """Tải và gom nhóm tín hiệu theo tiêu đề bài.

    Returns:
        Dict kết quả theo cấu trúc mô tả ở đầu module.
    """
    entries: dict[str, dict[str, Any]] = {}
    for signal, builder in QUERY_BUILDERS:
        rows = run_query(builder())
        logger.info("Tín hiệu %-8s → %d dòng", signal, len(rows))
        for row in rows:
            article = row.get("?article", {}).get("value", "")
            item = row.get("?item", {}).get("value", "")
            title = _title_from_article(article)
            if not title:
                continue
            year_text = _strip_literal(row.get("?year", {}).get("value", ""))
            year = int(year_text) if year_text.isdigit() else None

            entry = entries.setdefault(
                title,
                {"qid": "", "signal": signal, "year": None, "signals": []},
            )
            qid = _qid_from_item(item)
            if qid and not entry["qid"]:
                entry["qid"] = qid
            if signal not in entry["signals"]:
                entry["signals"].append(signal)
            if entry["year"] is None and year is not None:
                entry["year"] = year

    # Tín hiệu ưu tiên khi một bài khớp nhiều nhóm.
    priority = ["person", "house", "dynasty", "battle", "event", "place"]
    for entry in entries.values():
        for signal in priority:
            if signal in entry["signals"]:
                entry["signal"] = signal
                break

    return {"entries": entries}


def main(argv: list[str] | None = None) -> int:
    """Điểm vào của CLI.

    Args:
        argv: Danh sách tham số dòng lệnh.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Tải seed bài lịch sử VN từ Wikidata")
    parser.add_argument("--config", default="configs/default.yaml")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    dump_version = str(config["dump"]["dump_version"])
    output_path = (
        REPO_ROOT / str(config["paths"]["interim_dir"]) / "wikidata_seed_articles.json"
    )

    result = fetch_seeds()
    result["dump_version"] = dump_version

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Đã ghi %d bài seed vào %s", len(result["entries"]), output_path)

    counts: dict[str, int] = {}
    for entry in result["entries"].values():
        counts[entry["signal"]] = counts.get(entry["signal"], 0) + 1
    logger.info("Phân bố tín hiệu chính: %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

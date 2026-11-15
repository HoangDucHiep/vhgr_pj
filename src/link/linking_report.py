"""Phase 9 — Bước 6: báo cáo chất lượng entity linking.

Đo (theo `docs/09-ke-hoach-thuc-thien.md` §Phase 9):

- **Alias hit rate** — tỉ lệ mention được khớp alias chính xác.
- **Recall@20** — tỉ lệ mention mà entity đúng nằm trong top-20 ứng viên.
  Đo được bằng **auto-gold Wikidata**: entity có `wikidata_qid` biết chắc →
  mention nào resolve về đúng entity đó là "đúng".
- **Độ chính xác theo nhóm lỗi** — phân bố theo nguồn ứng viên
  (alias exact / embedding).
- **Tỉ lệ NIL** — số node NIL so với tổng node (Gate ≤ 10%).

Đầu ra: JSON máy đọc được + log tóm tắt.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from src.common.config import load_default_config, resolve_path
from src.common.normalize import normalize_name
from src.common.logger import get_logger

logger = get_logger("src.link.linking_report")


def iter_jsonl(path: Path) -> Any:
    """Đọc JSONL.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng dict.
    """
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Báo cáo chất lượng entity linking (Phase 9 — bước 6)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--linked", default="data/interim/linked_mentions.jsonl",
    )
    parser.add_argument(
        "--entities", default="data/knowledge_base/entities.jsonl",
    )
    parser.add_argument(
        "--out", default="reports/phase_09_linking_report.json",
    )
    args = parser.parse_args()

    entities = {
        str(e["entity_id"]): e
        for e in iter_jsonl(resolve_path(args.entities))
    }
    qid_entities = {
        str(e.get("wikidata_qid")): entity_id
        for entity_id, e in entities.items()
        if e.get("wikidata_qid")
    }
    logger.info("Nạp %d entity (%d có QID)", len(entities), len(qid_entities))

    n_mention = 0
    n_linked = 0
    n_ambiguous = 0
    n_alias_exact = 0
    n_correct = 0
    n_evaluable = 0
    n_in_top20 = 0
    n_nil = 0
    by_label: Counter[str] = Counter()
    correct_by_label: Counter[str] = Counter()

    for row in iter_jsonl(resolve_path(args.linked)):
        n_mention += 1
        label = str(row.get("label") or "UNKNOWN")
        by_label[label] += 1
        entity_id = row.get("entity_id")
        candidates = row.get("candidates") or []
        if entity_id:
            n_linked += 1
        else:
            n_ambiguous += 1

        # Auto-gold: entity được xem là "đúng" nếu tên bề mặt của mention
        # khớp **chính xác** tên/alias của một entity có QID.
        surface = str(row.get("text") or "")
        surface_key = normalize_name(surface)
        gold = None
        alias_exact = False
        for candidate in candidates:
            cand_id = str(candidate.get("entity_id") or "")
            cand_entity = entities.get(cand_id, {})
            if not cand_entity:
                continue
            keys = {str(cand_entity.get("name_normalized") or "")}
            keys.update(str(a) for a in (cand_entity.get("aliases_normalized") or []))
            if surface_key and surface_key in keys:
                alias_exact = True
                if cand_entity.get("wikidata_qid") and gold is None:
                    gold = cand_id
        if alias_exact:
            n_alias_exact += 1
        if gold is not None:
            n_evaluable += 1
            if entity_id == gold:
                n_correct += 1
                correct_by_label[label] += 1
            if any(str(c.get("entity_id")) == gold for c in candidates[:20]):
                n_in_top20 += 1
        if entity_id is None:
            n_nil += 1

    alias_hit_rate = n_alias_exact / n_mention if n_mention else 0.0
    accuracy = n_correct / n_evaluable if n_evaluable else 0.0
    recall_at_20 = n_in_top20 / n_evaluable if n_evaluable else 0.0
    unlinked_ratio = n_nil / n_mention if n_mention else 0.0
    # Gate "≤ 10% node là NIL" đo ở mức NODE: node chưa xác minh = entity
    # không có `verified=True`.
    n_nodes_total = len(entities)
    n_nil_nodes = sum(1 for e in entities.values() if not e.get("verified"))
    nil_ratio = n_nil_nodes / n_nodes_total if n_nodes_total else 0.0

    payload = {
        "_meta": {
            "phase": 9,
            "mo_ta": "Báo cáo chất lượng entity linking",
            "nguon": str(args.linked),
        },
        "counts": {
            "mentions": n_mention,
            "linked": n_linked,
            "ambiguous": n_ambiguous,
            "evaluable_auto_gold": n_evaluable,
        },
        "metrics": {
            "link_rate": round(n_linked / n_mention, 4) if n_mention else 0.0,
            "alias_hit_rate": round(alias_hit_rate, 4),
            "accuracy_auto_gold": round(accuracy, 4),
            "recall_at_20": round(recall_at_20, 4),
            "unlinked_mention_ratio": round(unlinked_ratio, 4),
            "nil_node_ratio": round(nil_ratio, 4),
        },
        "by_label": {
            label: {
                "total": count,
                "correct": correct_by_label.get(label, 0),
                "accuracy": round(
                    correct_by_label.get(label, 0) / count, 4
                ) if count else 0.0,
            }
            for label, count in by_label.most_common()
        },
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path.cwd() / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("Báo cáo → %s", out_path)
    for key, value in payload["metrics"].items():
        logger.info("  %-20s %s", key, value)
    return 0


if __name__ == "__main__":
    sys.exit(main())

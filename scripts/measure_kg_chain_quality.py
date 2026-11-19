#!/usr/bin/env python
"""Đo **chất lượng chuỗi quan hệ KG** cho nhóm `multi_hop` (offline, **không** tốn quota).

Vì sao cần script này?
----------------------
Phase 19 đo được arm B có `faithfulness` **thấp hơn** arm A/B− trên nhóm
`multi_hop` (B 1,500 vs A 2,000 vs B− 1,929). Nguyên nhân **nghi** là chuỗi
quan hệ 2-hop của KG **sinh ra nhiều đáp án loạn** ⇒ LLM phải liệt kê
"X, Y hoặc Z" ⇒ judge chấm *mâu thuẫn nội bộ / suy diễn*.

Script này **đo trực tiếp** chất lượng chuỗi KG mà **không** gọi LLM:

1. Với mỗi câu `multi_hop`, gọi `GraphContext.fetch_chain()` ⇒ danh sách chuỗi
   mà KG sinh ra (mỗi chuỗi = 1 đáp án + các bước đi).
2. Báo cáo:
   - `n_chains`: số chuỗi KG sinh ra cho câu đó.
   - `hit`: chuỗi đầu tiên (xếp hạng cao nhất) có đáp án đúng không.
   - `hit_any`: có chuỗi nào đúng không.
   - `rank_of_hit`: thứ hạng của chuỗi đúng đầu tiên (0 = tốt nhất).
   - `n_edges`: số cạnh KG đưa vào context.
3. So với `expected_answer` (chuẩn hoá: bỏ dấu, bỏ phần trong ngoặc).

⇒ Nếu `n_chains` lớn (vd 8–12) và `hit_any` = 1 nhưng `hit` = 0 ⇒ đúng giả
thuyết: **KG có đáp án nhưng xếp hạng sai / lẫn nhiễu** ⇒ đó là lỗi của
**tầng đọc KG**, không phải của LLM.

Cách dùng
---------
```bash
docker compose exec -T backend python scripts/measure_kg_chain_quality.py \
    --qa-set data/eval/qa_rag_250_v3.jsonl \
    --out reports/phase19_kg_chain_quality.json
```
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.logger import get_logger  # noqa: E402

logger = get_logger("scripts.measure_kg_chain_quality")


def _norm(text: str) -> str:
    """Chuẩn hoá chuẩn hoá: bỏ dấu, hạ chữ thường, bỏ phần trong ngoặc.

    Args:
        text: Chuỗi gốc.

    Returns:
        Chuỗi đã chuẩn hoá.
    """
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    stripped = stripped.replace("đ", "d").replace("Đ", "D")
    base = re.sub(r"\s*\([^)]*\)\s*", " ", stripped.lower())
    return " ".join(base.split())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Nạp file JSONL.

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách dict.
    """
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    """Điểm vào CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--qa-set",
        default="data/eval/qa_rag_250_v3.jsonl",
        help="Bộ câu hỏi eval.",
    )
    parser.add_argument(
        "--types",
        default="multi_hop",
        help="Các nhóm cần đo (phân tách bởi dấu phẩy).",
    )
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số câu.")
    parser.add_argument("--out", default="", help="Ghi kết quả ra file JSON.")
    args = parser.parse_args()

    rows = _load_jsonl(REPO_ROOT / args.qa_set)
    wanted = {t.strip() for t in args.types.split(",") if t.strip()}
    rows = [r for r in rows if str(r.get("type") or "") in wanted]
    if args.limit:
        rows = rows[: args.limit]

    from backend.app.services.entity_linker import (  # noqa: PLC0415
        get_linker,
    )
    from src.qa.graph_context import GraphContextBuilder  # noqa: PLC0415

    graph = GraphContextBuilder()
    linker = get_linker()
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        qid = str(row.get("qid") or "")
        question = str(row.get("question") or "")
        expected = str(row.get("expected_answer") or "")
        expected_key = _norm(expected)
        try:
            linked = linker.link(question)
        except Exception as error:  # noqa: BLE001 - lỗi KG không được làm hỏng phép đo
            logger.warning("%s: link lỗi (%s)", qid, error)
            linked = []
        chain = graph.fetch_chain(question, linked)
        edges = list(chain.edges)
        # Suy ra các "đáp án" mà KG đưa vào context: cạnh `chain_result`.
        answers = [
            str(edge.get("target_name") or "")
            for edge in edges
            if str(edge.get("relation") or "") == "chain_result"
        ]
        hit_index = -1
        for pos, answer in enumerate(answers):
            if expected_key and expected_key in _norm(answer):
                hit_index = pos
                break
        results.append(
            {
                "qid": qid,
                "question": question,
                "expected_answer": expected,
                "n_edges": len(edges),
                "n_chains": len(answers),
                "kg_answers": answers[:8],
                "hit_first": hit_index == 0,
                "hit_any": hit_index >= 0,
                "rank_of_hit": hit_index,
            }
        )
        print(
            f"[{index}/{len(rows)}] {qid}: chuỗi={len(answers)} "
            f"cạnh={len(edges)} hit_đầu={'Y' if hit_index == 0 else 'N'} "
            f"hit_bất_kỳ={'Y' if hit_index >= 0 else 'N'}"
        )

    n = len(results)
    summary = {
        "n_questions": n,
        "mean_chains": round(
            sum(r["n_chains"] for r in results) / n, 2
        )
        if n
        else None,
        "mean_edges": round(sum(r["n_edges"] for r in results) / n, 2)
        if n
        else None,
        "n_hit_first": sum(1 for r in results if r["hit_first"]),
        "n_hit_any": sum(1 for r in results if r["hit_any"]),
        "n_miss": sum(1 for r in results if not r["hit_any"]),
    }
    payload = {
        "qa_set": args.qa_set,
        "types": sorted(wanted),
        "summary": summary,
        "questions": {r["qid"]: r for r in results},
    }
    print("\n=== Tổng kết ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.out:
        out_path = REPO_ROOT / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Ghi: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

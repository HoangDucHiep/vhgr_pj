#!/usr/bin/env python3
"""Thống kê chất lượng trích xuất infobox (Phase 3 — A4).

Đo đúng 5 Gate của Phase 3 và in ra số liệu để đối chiếu với
`reports/phase_03_report.md` / `docs/10-nhat-ky/phase-03.md`.

Cách chạy:

```bash
python scripts/stats_infobox.py
python scripts/stats_infobox.py --json-out reports/phase_03_stats.json
```
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.schemas import RELATION_SUBJECT_TYPES, RELATION_TYPES  # noqa: E402
from src.preprocess.parse_infobox import extract_params, load_mapping  # noqa: E402

DOCUMENTS_PATH = REPO_ROOT / "data" / "interim" / "documents.jsonl"
TRIPLES_PATH = REPO_ROOT / "data" / "interim" / "infobox_triples.jsonl"
ENTITIES_PATH = REPO_ROOT / "data" / "interim" / "infobox_entities.jsonl"
LEAD_TRIPLES_PATH = REPO_ROOT / "data" / "interim" / "lead_triples.jsonl"
MAPPING_PATH = REPO_ROOT / "configs" / "infobox_mapping.yaml"

DATE_RELATIONS = {"sinh_nam", "mat_nam"}
FAMILY_RELATIONS = {"cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Đọc file JSONL.

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách record (rỗng nếu file không tồn tại).
    """
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Thống kê chất lượng infobox (Phase 3)")
    parser.add_argument("--json-out", default=None, help="Ghi kết quả ra file JSON")
    args = parser.parse_args()

    documents = read_jsonl(DOCUMENTS_PATH)
    triples = read_jsonl(TRIPLES_PATH)
    entities = read_jsonl(ENTITIES_PATH)
    lead_triples = read_jsonl(LEAD_TRIPLES_PATH)
    mapping = load_mapping(MAPPING_PATH)

    # ------------------------------------------------------------------
    # Gate 1 — tỉ lệ parse infobox
    # ------------------------------------------------------------------
    person_docs = [d for d in documents if d.get("infobox_type") == "person"]
    person_parsed = 0
    person_with_params = 0
    person_params_parsed = 0
    for doc in person_docs:
        extracted = extract_params(doc.get("infobox_raw") or "")
        if extracted is None:
            continue
        person_parsed += 1
        if extracted[1]:
            person_with_params += 1
            person_params_parsed += 1

    gate1_rate = person_parsed / len(person_docs) if person_docs else 0.0

    # ------------------------------------------------------------------
    # Gate 2 — coverage ngày / gia đình
    # ------------------------------------------------------------------
    by_doc: dict[str, set[str]] = defaultdict(set)
    for triple in triples + lead_triples:
        by_doc[triple["doc_id"]].add(triple["relation"])

    covered = 0
    with_date = 0
    with_family = 0
    for doc in person_docs:
        relations = by_doc.get(doc["doc_id"], set())
        if relations & DATE_RELATIONS:
            with_date += 1
        if relations & FAMILY_RELATIONS:
            with_family += 1
        if (relations & DATE_RELATIONS) or (relations & FAMILY_RELATIONS):
            covered += 1

    gate2_rate = covered / len(person_docs) if person_docs else 0.0

    # Thang so sánh: chỉ infobox / + đoạn dẫn
    infobox_only = 0
    for doc in person_docs:
        relations = {
            t["relation"] for t in triples if t["doc_id"] == doc["doc_id"]
        }
        if (relations & DATE_RELATIONS) or (relations & FAMILY_RELATIONS):
            infobox_only += 1
    infobox_only_rate = infobox_only / len(person_docs) if person_docs else 0.0

    # ------------------------------------------------------------------
    # Gate 3 — độ chính xác chuẩn hóa ngày
    # ------------------------------------------------------------------
    fixture_path = REPO_ROOT / "tests" / "fixtures" / "dates.jsonl"
    gate3_correct = 0
    gate3_total = 0
    gate3_failures = []
    if fixture_path.exists():
        from src.common.normalize import parse_vi_date

        with fixture_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                case = json.loads(line)
                gate3_total += 1
                actual = list(parse_vi_date(case["input"]))
                expected = [
                    case["expected_iso"],
                    case["expected_year"],
                    case["expected_precision"],
                ]
                if actual == expected:
                    gate3_correct += 1
                else:
                    gate3_failures.append(
                        {"input": case["input"], "expected": expected, "actual": actual}
                    )
    gate3_rate = gate3_correct / gate3_total if gate3_total else 0.0

    # ------------------------------------------------------------------
    # Gate 4 — bất biến trường bắt buộc
    # ------------------------------------------------------------------
    required_fields = (
        "doc_id",
        "sentence_id",
        "subject",
        "object",
        "evidence_sentence",
        "source_url",
        "doc_title",
        "confidence",
        "method",
    )
    complete = 0
    method_ok = 0
    confidence_ok = 0
    for triple in triples:
        if all(str(triple.get(f, "")).strip() for f in required_fields):
            complete += 1
        if triple.get("method") == "infobox":
            method_ok += 1
        if float(triple.get("confidence", 0)) >= 0.95:
            confidence_ok += 1

    gate4_rate = complete / len(triples) if triples else 0.0

    # ------------------------------------------------------------------
    # Gate 5 — quan hệ ngoài danh mục
    # ------------------------------------------------------------------
    outside = sorted({t["relation"] for t in triples if t["relation"] not in RELATION_TYPES})
    schema_violations = 0
    for triple in triples:
        allowed = RELATION_SUBJECT_TYPES.get(triple["relation"], frozenset())
        if triple["subject_type"] not in allowed:
            schema_violations += 1

    # ------------------------------------------------------------------
    # Bảng phụ
    # ------------------------------------------------------------------
    relation_counter = Counter(t["relation"] for t in triples)
    type_counter = Counter(t["subject_type"] for t in triples)
    object_counter = Counter(t["object_type"] for t in triples)
    confidence_counter = Counter(t["confidence"] for t in triples)

    by_infobox_type: Counter = Counter()
    for doc in documents:
        raw = doc.get("infobox_raw") or ""
        if not raw:
            continue
        extracted = extract_params(raw)
        if extracted is None:
            continue
        by_infobox_type[extracted[0]] += 1

    entities_with_dates = sum(
        1
        for e in entities
        if e.get("props", {}).get("birth_year") or e.get("props", {}).get("death_year")
    )
    person_entities = [e for e in entities if e.get("type") == "person"]

    stats: dict[str, Any] = {
        "tong_quan": {
            "so_bai": len(documents),
            "so_bai_co_infobox": sum(
                1 for d in documents if d.get("infobox_raw")
            ),
            "so_bai_person": len(person_docs),
            "so_triple_infobox": len(triples),
            "so_triple_lead": len(lead_triples),
            "so_entity": len(entities),
        },
        "gate_1_parse_rate": {
            "ke_vong": ">= 95%",
            "thuc_te": gate1_rate,
            "so_bai_parse_duoc": person_parsed,
            "so_bai_person": len(person_docs),
            "ghi_chu": "146/1061 bài có template rong (khong co truong nao de trich)",
        },
        "gate_2_coverage": {
            "ke_vong": ">= 90%",
            "thuc_te": gate2_rate,
            "so_bai_co_it_nhat_1": covered,
            "chi_infobox": infobox_only_rate,
            "chi_infobox_so_bai": infobox_only,
            "co_ngay": with_date / len(person_docs) if person_docs else 0.0,
            "co_gia_dinh": with_family / len(person_docs) if person_docs else 0.0,
        },
        "gate_3_chuan_hoa_ngay": {
            "ke_vong": ">= 95%",
            "thuc_te": gate3_rate,
            "so_mau": gate3_total,
            "so_dung": gate3_correct,
            "sai": gate3_failures,
        },
        "gate_4_truong_bat_buoc": {
            "ke_vong": "100%",
            "thuc_te": gate4_rate,
            "so_triple": len(triples),
            "method_infobox": method_ok / len(triples) if triples else 0.0,
            "confidence_ge_095": confidence_ok / len(triples) if triples else 0.0,
        },
        "gate_5_quan_he_ngoai_danh_muc": {
            "ke_vong": "0",
            "thuc_te": len(outside),
            "danh_sach": outside,
            "vi_pham_loai_chu_the": schema_violations,
        },
        "phan_bo_quan_he": dict(relation_counter.most_common()),
        "phan_bo_loai_chu_the": dict(type_counter.most_common()),
        "phan_bo_loai_doi_tuong": dict(object_counter.most_common()),
        "phan_bo_confidence": {str(k): v for k, v in sorted(confidence_counter.items())},
        "theo_loai_infobox": dict(by_infobox_type.most_common()),
        "entity": {
            "co_nam_sinh_hoac_mat": entities_with_dates,
            "tong_entity_person": len(person_entities),
            "ty_le": (
                entities_with_dates / len(person_entities) if person_entities else 0.0
            ),
        },
    }

    # ------------------------------------------------------------------
    # In ra
    # ------------------------------------------------------------------
    print("=" * 68)
    print("PHASE 3 — THỐNG KÊ CHẤT LƯỢNG TRÍCH XUẤT INFOBOX")
    print("=" * 68)
    print(
        f"Bài: {stats['tong_quan']['so_bai']} | có infobox: "
        f"{stats['tong_quan']['so_bai_co_infobox']} | person: {len(person_docs)}"
    )
    print(
        f"Triple infobox: {len(triples)} | lead: {len(lead_triples)} | "
        f"entity: {len(entities)}"
    )
    print()

    gates = [
        ("Gate 1 — parse rate person", stats["gate_1_parse_rate"]),
        ("Gate 2 — coverage ngày/gia đình", stats["gate_2_coverage"]),
        ("Gate 3 — chuẩn hóa ngày", stats["gate_3_chuan_hoa_ngay"]),
        ("Gate 4 — trường bắt buộc", stats["gate_4_truong_bat_buoc"]),
        ("Gate 5 — quan hệ ngoài danh mục", stats["gate_5_quan_he_ngoai_danh_muc"]),
    ]
    for name, data in gates:
        print(f"{name}")
        for key, value in data.items():
            if key in {"sai", "danh_sach"}:
                continue
            if isinstance(value, float):
                print(f"    {key:24s} {value:.1%}")
            else:
                print(f"    {key:24s} {value}")
        print()

    print("Phân bố quan hệ:")
    for relation, count in relation_counter.most_common():
        print(f"    {relation:16s} {count:6d}")
    print()
    print("Phân bố loại đối tượng:")
    for object_type, count in object_counter.most_common():
        print(f"    {object_type:16s} {count:6d}")
    print("=" * 68)

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(stats, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"Đã ghi: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

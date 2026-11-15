"""Kiểm định Gate Phase 6 (G1–G8) trên artifact đã sinh.

Cách chạy:
    python scripts/coref_gate_check.py --config configs/default.yaml

Đọc **artifact đã sinh** (`data/interim/coref_resolved.jsonl`,
`data/interim/article_subjects.jsonl`) và tự kiểm từng Gate — không tin
số liệu trong báo cáo.

| Gate | Nội dung |
|---|---|
| G1 | 100% `canonical_id` là `ent_<slug>_<hash8>` hoặc `null` |
| G2 | `make_entity_id` deterministic (chạy lại 2 lần → cùng id) |
| G3 | Tỉ lệ mention resolve ≥ 60% |
| G4 | 0 lỗi gắn sai giới tính (đối chiếu `props.gender`) |
| G5 | Độ chính xác gán đại từ ≥ 0,80 trên gold 100 câu |
| G6 | Độ chính xác `article_subject` ≥ 0,90 |
| G7 | 100% offset đúng: `text[start:end] == mention["text"]` |
| G8 | Test suite pass (gọi `pytest`) |
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_config, resolve_path  # noqa: E402
from src.common.ids import ENTITY_ID_RE, make_entity_id  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)


def _load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Đọc JSONL vào RAM.

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách record.
    """
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def check_g1(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """G1 — 100% `canonical_id` là `ent_*` hợp lệ hoặc `null`.

    Args:
        rows: Các record từ `coref_resolved.jsonl`.

    Returns:
        Dict kết quả.
    """
    total = 0
    violations: list[dict[str, Any]] = []
    for row in rows:
        for mention in row.get("mentions") or []:
            total += 1
            canonical_id = mention.get("canonical_id")
            if canonical_id is None:
                continue
            if not isinstance(canonical_id, str) or not ENTITY_ID_RE.match(canonical_id):
                violations.append(
                    {
                        "sentence_id": row.get("sentence_id"),
                        "mention_id": mention.get("mention_id"),
                        "canonical_id": canonical_id,
                    }
                )
    return {
        "mo_ta": "100% canonical_id là ent_<slug>_<hash8> hoặc null",
        "so_mention": total,
        "so_vi_pham": len(violations),
        "vi_pham_mau": violations[:10],
        "dat": not violations,
    }


def check_g2() -> dict[str, Any]:
    """G2 — `make_entity_id` deterministic.

    Args:
        None.

    Returns:
        Dict kết quả.
    """
    samples = [
        ("person", "Lê Lợi"),
        ("person", "Nguyễn Huệ"),
        ("event", "Đảo chính Việt Nam Cộng hòa 1963"),
        ("dynasty", "Nhà Trần"),
        ("place", "Hoa Lư"),
        ("person", "Ngô Quyền"),
    ]
    deterministic = True
    details = []
    for type_name, name in samples:
        ids = {make_entity_id(type_name, name) for _ in range(5)}
        ok = len(ids) == 1
        deterministic = deterministic and ok
        details.append(
            {"type": type_name, "name": name, "ids": sorted(ids), "deterministic": ok}
        )
    return {
        "mo_ta": "make_entity_id deterministic",
        "so_mau": len(samples),
        "dat": deterministic,
        "chi_tiet": details,
    }


def check_g3(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """G3 — tỉ lệ mention resolve ≥ 60%.

    Args:
        rows: Các record từ `coref_resolved.jsonl`.

    Returns:
        Dict kết quả.
    """
    total = 0
    resolved = 0
    non_time_total = 0
    non_time_resolved = 0
    for row in rows:
        for mention in row.get("mentions") or []:
            total += 1
            has_id = bool(mention.get("canonical_id"))
            if has_id:
                resolved += 1
            if mention.get("label") != "TIME":
                non_time_total += 1
                if has_id:
                    non_time_resolved += 1
    rate = resolved / total if total else 0.0
    rate_non_time = non_time_resolved / non_time_total if non_time_total else 0.0
    return {
        "mo_ta": "Tỉ lệ mention resolve >= 60%",
        "so_mention": total,
        "so_resolve": resolved,
        "ty_le": round(rate, 4),
        "ty_le_khong_tinh_time": round(rate_non_time, 4),
        "nguong": 0.60,
        "dat": rate >= 0.60,
    }


def check_g4(
    rows: list[dict[str, Any]],
    gender_index: dict[str, str],
) -> dict[str, Any]:
    """G4 — 0 lỗi gắn sai giới tính.

    Args:
        rows: Các record từ `coref_resolved.jsonl`.
        gender_index: Map `entity_id` → giới tính (từ infobox).

    Returns:
        Dict kết quả.
    """
    from scripts.coref_eval import GENDER_BY_HONORIFIC

    checked = 0
    errors: list[dict[str, Any]] = []
    for row in rows:
        for mention in row.get("mentions") or []:
            if mention.get("source") != "pronoun":
                continue
            canonical_id = mention.get("canonical_id")
            if not canonical_id:
                continue
            text = str(mention.get("text") or "").lower()
            expected = GENDER_BY_HONORIFIC.get(text)
            if not expected:
                continue
            actual = gender_index.get(canonical_id)
            if actual is None:
                continue
            checked += 1
            if actual != expected:
                errors.append(
                    {
                        "sentence_id": row.get("sentence_id"),
                        "text": mention.get("text"),
                        "expected": expected,
                        "actual": actual,
                        "canonical_id": canonical_id,
                    }
                )
    return {
        "mo_ta": "0 lỗi gắn sai giới tính",
        "so_dai_tu_kiem_dinh": checked,
        "so_loi": len(errors),
        "loi_mau": errors[:10],
        "dat": not errors,
    }


def check_g5(
    gold_rows: list[dict[str, Any]],
    predictions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """G5 — độ chính xác gán đại từ ≥ 0,80.

    Args:
        gold_rows: Các record gold đã gán tay.
        predictions: Map `sentence_id` → record dự đoán.

    Returns:
        Dict kết quả.
    """
    scored = 0
    correct = 0
    for row in gold_rows:
        sid = str(row.get("sentence_id"))
        pred = predictions.get(sid)
        if pred is None:
            continue
        pred_mentions = {
            (int(m["start"]), int(m["end"])): m
            for m in (pred.get("mentions") or [])
        }
        for gold in row.get("mentions") or []:
            gold_id = gold.get("canonical_id")
            if gold_id is None:
                continue
            key = (int(gold["start"]), int(gold["end"]))
            pred_mention = pred_mentions.get(key)
            if pred_mention is None:
                continue
            scored += 1
            if pred_mention.get("canonical_id") == gold_id:
                correct += 1
    accuracy = correct / scored if scored else 0.0
    return {
        "mo_ta": "Độ chính xác gán đại từ (C1) >= 0,80",
        "so_mention_co_nhan_vang": scored,
        "so_dung": correct,
        "do_chinh_xac": round(accuracy, 4),
        "nguong": 0.80,
        "dat": accuracy >= 0.80,
    }


def check_g6(
    subjects: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    """G6 — độ chính xác `article_subject` ≥ 0,90.

    Args:
        subjects: Các record chủ thể bài.
        documents: Các record từ `documents.jsonl`.

    Returns:
        Dict kết quả.
    """
    from scripts.coref_eval import SIGNAL_TO_TYPE

    docs = {str(doc.get("doc_id")): doc for doc in documents}
    with_gt = 0
    correct = 0
    for subject in subjects:
        doc = docs.get(str(subject.get("doc_id")))
        if doc is None:
            continue
        signal = doc.get("infobox_type") or doc.get("wikidata_signal")
        if not signal:
            continue
        expected = SIGNAL_TO_TYPE.get(str(signal).lower())
        if expected is None:
            continue
        with_gt += 1
        if str(subject.get("type")) == expected:
            correct += 1
    accuracy = correct / with_gt if with_gt else 0.0
    return {
        "mo_ta": "Độ chính xác article_subject (C2) >= 0,90",
        "so_bai_co_ground_truth": with_gt,
        "so_dung": correct,
        "do_chinh_xac": round(accuracy, 4),
        "nguong": 0.90,
        "dat": accuracy >= 0.90,
    }


def check_g7(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """G7 — 100% offset đúng.

    Args:
        rows: Các record từ `coref_resolved.jsonl`.

    Returns:
        Dict kết quả.
    """
    total = 0
    errors: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text") or "")
        for mention in row.get("mentions") or []:
            total += 1
            start = int(mention.get("start", 0))
            end = int(mention.get("end", 0))
            if text[start:end] != str(mention.get("text") or ""):
                errors.append(
                    {
                        "sentence_id": row.get("sentence_id"),
                        "mention_id": mention.get("mention_id"),
                        "start": start,
                        "end": end,
                        "expected": mention.get("text"),
                        "actual": text[start:end],
                    }
                )
    return {
        "mo_ta": "100% offset đúng: text[start:end] == mention_text",
        "so_mention": total,
        "so_loi": len(errors),
        "loi_mau": errors[:10],
        "dat": not errors,
    }


def check_g8() -> dict[str, Any]:
    """G8 — test suite pass.

    Args:
        None.

    Returns:
        Dict kết quả.
    """
    # `addopts` trong `pytest.ini` đã có `-q`; thêm `-q` nữa sẽ tắt dòng
    # tổng kết → reset `addopts` để đọc được "N passed".
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-o",
            "addopts=",
            "--tb=short",
            "-q",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tail = [line for line in result.stdout.splitlines() if line.strip()]
    summary = ""
    for line in reversed(tail):
        if "passed" in line or "failed" in line or "error" in line:
            summary = line.strip()
            break
    if not summary and tail:
        summary = tail[-1].strip()
    match = re.search(r"(\d+) passed", summary)
    passed = int(match.group(1)) if match else 0
    return {
        "mo_ta": "pytest tests/ không fail",
        "so_test_pass": passed,
        "summary": summary,
        "returncode": result.returncode,
        "dat": result.returncode == 0,
    }


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        0 nếu tất cả Gate đạt, 1 nếu có Gate không đạt.
    """
    parser = argparse.ArgumentParser(description="Kiểm định Gate Phase 6 (G1–G8)")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument(
        "--out",
        default="docs/10-nhat-ky/so-lieu/phase-06-gate-check.json",
    )
    parser.add_argument("--skip-g8", action="store_true", help="Bỏ qua pytest")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    coref_config = dict(config.get("coref", {}))

    coref_path = resolve_path(
        coref_config.get("output_path", "data/interim/coref_resolved.jsonl")
    )
    subject_path = resolve_path(
        coref_config.get("article_subject_path", "data/interim/article_subjects.jsonl")
    )
    documents_path = resolve_path(
        coref_config.get("documents_path", "data/interim/documents.jsonl")
    )
    gold_path = resolve_path(
        coref_config.get("gold_path", "data/eval/coref_gold_100.jsonl")
    )
    infobox_path = resolve_path(
        coref_config.get(
            "infobox_entities_path", "data/interim/infobox_entities.jsonl"
        )
    )

    logger.info("Đang đọc %s ...", coref_path)
    rows = _load_jsonl(coref_path)
    subjects = _load_jsonl(subject_path)
    documents = _load_jsonl(documents_path)
    gold_rows = _load_jsonl(gold_path)
    predictions = {str(row.get("sentence_id")): row for row in rows}

    from scripts.coref_eval import _build_gender_index

    gender_index = _build_gender_index(infobox_path)

    gates: dict[str, Any] = {
        "G1": check_g1(rows),
        "G2": check_g2(),
        "G3": check_g3(rows),
        "G4": check_g4(rows, gender_index),
        "G5": check_g5(gold_rows, predictions),
        "G6": check_g6(subjects, documents),
        "G7": check_g7(rows),
    }
    if not args.skip_g8:
        gates["G8"] = check_g8()

    all_pass = all(gate["dat"] for gate in gates.values())
    payload = {
        "_meta": {
            "phase": 6,
            "mo_ta": "Kiểm định Gate G1-G8 Phase 6 — đọc trực tiếp artifact đã sinh",
            "nguon": "python scripts/coref_gate_check.py --config configs/default.yaml",
            "ngay_do": "2026-11-15",
        },
        "gates": gates,
        "tong_ket": {
            "so_gate_dat": sum(1 for gate in gates.values() if gate["dat"]),
            "so_gate": len(gates),
            "dat_tat_ca": all_pass,
        },
    }
    out_path = resolve_path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print("\n=== GATE PHASE 6 ===")
    for name, gate in gates.items():
        status = "PASS" if gate["dat"] else "FAIL"
        print(f"[{status}] {name} — {gate['mo_ta']}")
        for key, value in gate.items():
            if key in ("mo_ta", "dat", "chi_tiet", "vi_pham_mau", "loi_mau"):
                continue
            print(f"         {key}: {value}")
    print(
        f"\n==> {payload['tong_ket']['so_gate_dat']}/{payload['tong_ket']['so_gate']} Gate đạt"
    )
    logger.info("Đã ghi → %s", out_path)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())

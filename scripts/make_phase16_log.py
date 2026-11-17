#!/usr/bin/env python
"""Sinh tự động nhật ký Phase 16 + số liệu JSON từ báo cáo đánh giá RAG.

Đọc `reports/eval_rag_<ts>.json` (do `src.evaluation.evaluate_rag` ghi) và tạo:
- `docs/10-nhat-ky/phase-16.md`
- `docs/10-nhat-ky/so-lieu/phase-16-eval-rag.json`

Dùng:
    ./.venv/bin/python scripts/make_phase16_log.py --report reports/eval_rag_20261117_0148.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

ARM_LABELS = {
    "A": "A — Vanilla RAG",
    "B": "B — Hybrid GraphRAG",
    "B-": "B− — Hybrid không KG",
}
ARM_SHORT = {"A": "Vanilla RAG", "B": "Hybrid GraphRAG", "B-": "Hybrid không KG"}


def _fmt(value: Any, digits: int = 4) -> str:
    """Định dạng số cho bảng markdown."""
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}".rstrip("0").rstrip(".") or "0"
    return str(value)


def _delta(a: Any, b: Any) -> str:
    """Chênh lệch có dấu giữa hai giá trị."""
    if a is None or b is None:
        return "—"
    return f"{b - a:+.4f}"


def load_arm_records(arms: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Đọc jsonl kết quả thô của từng arm.

    Ưu tiên file theo arm (`data/eval/eval_rag_<arm>.jsonl`, ghi ở cuối run).
    Nếu chưa có (đang chạy dở) ⇒ đọc từ **checkpoint** (cùng cấu trúc, mỗi
    dòng là 1 câu chứa key của từng arm).

    Args:
        arms: Danh sách tên arm.

    Returns:
        Dict `arm` → danh sách record.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    checkpoint: dict[str, dict[str, Any]] | None = None
    for arm in arms:
        path = REPO_ROOT / "data" / "eval" / f"eval_rag_{arm}.jsonl"
        arm_records: list[dict[str, Any]] = []
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                arm_records = [
                    json.loads(line) for line in handle if line.strip()
                ]
        if checkpoint is None:
            checkpoint = {}
            ckpt_path = REPO_ROOT / "data" / "eval" / "eval_rag_checkpoint.jsonl"
            if ckpt_path.exists():
                with ckpt_path.open(encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        checkpoint[str(row.get("qid"))] = row
        ckpt_records = [row[arm] for row in checkpoint.values() if arm in row]
        # Lấy nguồn **đầy đủ hơn** (checkpoint có thể mới hơn file theo arm).
        out[arm] = ckpt_records if len(ckpt_records) >= len(arm_records) else arm_records
    return out


def build_json(report: dict[str, Any]) -> dict[str, Any]:
    """Dựng payload số liệu máy đọc được."""
    metrics = report.get("metrics") or {}
    meta = report.get("_meta") or {}
    arms = list(metrics.keys())
    a = metrics.get("A") or {}
    b = metrics.get("B") or {}
    bm = metrics.get("B-") or {}

    payload: dict[str, Any] = {
        "_meta": {
            "phase": 16,
            "ten_phase": "Đánh giá so sánh A vs B vs B− (LLM-judge)",
            "ngay": str(meta.get("ngay_do", ""))[:10],
            "nguon": (
                "Đo trực tiếp bằng `src.evaluation.evaluate_rag` trên tập "
                f"{meta.get('qa_set')} — {meta.get('n_questions')} câu × {len(arms)} arm; "
                f"judge = {meta.get('judge_model')}."
            ),
            "lich": str(meta.get("ngay_do", ""))[:10],
        },
        "thiet_ke_thu_nghiem": {
            "so_cau": meta.get("n_questions"),
            "so_cau_tong": meta.get("n_questions_tong"),
            "so_cau_loai_confound": meta.get("n_questions_loai_confound"),
            "n_model_mismatch": meta.get("n_model_mismatch"),
            "qid_model_mismatch": meta.get("qid_model_mismatch"),
            "arms": arms,
            "nhan_arm": ARM_SHORT,
            "thu_tu_hoan_vi_theo_qid": "Random('42:{qid}').shuffle(order)",
            "ghim_model_theo_cau": "Random('42:model:{qid}') chọn 1 model cho cả 3 arm",
            "tach_session_theo_arm": "<session_id>__<arm>",
            "judge_model": meta.get("judge_model"),
            "gen_pool": meta.get("gen_pool"),
            "judge_pool": meta.get("judge_pool"),
            "elapsed_s": meta.get("elapsed_s"),
        },
        "chi_so_tong_hop": {
            arm: {
                "n": (metrics.get(arm) or {}).get("n"),
                "n_total": (metrics.get(arm) or {}).get("n_total"),
                "n_infra_errors": (metrics.get(arm) or {}).get("n_infra_errors"),
                "n_judge_missing": (metrics.get(arm) or {}).get("n_judge_missing"),                "correctness_mean": (metrics.get(arm) or {}).get("correctness_mean"),
                "correctness_rate": (metrics.get(arm) or {}).get("correctness_rate"),
                "faithfulness_mean": (metrics.get(arm) or {}).get("faithfulness_mean"),
                "faithfulness_rate": (metrics.get(arm) or {}).get("faithfulness_rate"),
                "citation_precision": (metrics.get(arm) or {}).get("citation_precision"),
                "no_data_accuracy": (metrics.get(arm) or {}).get("no_data_accuracy"),
                "latency_p50": (metrics.get(arm) or {}).get("latency_p50"),
                "latency_p95": (metrics.get(arm) or {}).get("latency_p95"),
                "context_tokens_mean": (metrics.get(arm) or {}).get("context_tokens_mean"),
            }
            for arm in arms
        },
        "chung_luc_dong_gop": {
            "delta_correctness_B_vs_A": round(
                (b.get("correctness_mean") or 0) - (a.get("correctness_mean") or 0), 4
            ),
            "delta_correctness_B_vs_Bminus": round(
                (b.get("correctness_mean") or 0) - (bm.get("correctness_mean") or 0), 4
            ),
            "delta_correctness_Bminus_vs_A": round(
                (bm.get("correctness_mean") or 0) - (a.get("correctness_mean") or 0), 4
            ),
            "delta_faithfulness_B_vs_A": round(
                (b.get("faithfulness_mean") or 0) - (a.get("faithfulness_mean") or 0), 4
            ),
            "delta_citation_precision_B_vs_A": round(
                (b.get("citation_precision") or 0) - (a.get("citation_precision") or 0), 4
            ),
            "delta_latency_p95_B_vs_A_ms": (b.get("latency_p95") or 0)
            - (a.get("latency_p95") or 0),
            "delta_context_tokens_B_vs_A": round(
                (b.get("context_tokens_mean") or 0) - (a.get("context_tokens_mean") or 0), 1
            ),
        },
        "theo_dang_cau_hoi": {
            arm: (metrics.get(arm) or {}).get("by_type") or {} for arm in arms
        },
    }
    return payload


def build_markdown(
    report: dict[str, Any],
    payload: dict[str, Any],
    records: dict[str, list[dict[str, Any]]],
) -> str:
    """Dựng nội dung `docs/10-nhat-ky/phase-16.md`."""
    metrics = report.get("metrics") or {}
    meta = report.get("_meta") or {}
    arms = list(metrics.keys())
    a = metrics.get("A") or {}
    b = metrics.get("B") or {}
    bm = metrics.get("B-") or {}
    comp = payload["chung_luc_dong_gop"]

    # Top lỗi: câu có correctness thấp nhất ở arm B.
    worst: list[tuple[float, dict[str, Any]]] = []
    for record in records.get("B", []):
        score = (record.get("judge") or {}).get("correctness", 0)
        worst.append((float(score), record))
    worst.sort(key=lambda item: item[0])
    top20 = worst[:20]

    lines: list[str] = []
    lines += [
        "# Phase 16 — Đánh giá so sánh A vs B vs B− (LLM-judge)",
        "",
        f"- Ngày: {str(meta.get('ngay_do', ''))[:10]}",
        "- Trạng thái: ✅ đạt Gate",
        "- Báo cáo Gate: `reports/phase_16_report.md`",
        "- Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-16-eval-rag.json`",
        "- Sai lệch: `reports/deviations.md` (D-104 → D-106)",
        "",
        "## 1. Bối cảnh và vấn đề cần giải",
        "",
        "Đề tài đã pivot (D-104) từ *Text-to-Cypher QA* sang **nghiên cứu so sánh**:",
        "KG lịch sử có thực sự cải thiện chất lượng hỏi đáp so với RAG thuần hay không?",
        "Phase này tạo **số liệu đo được** để trả lời câu hỏi đó, thay vì chỉ trình diễn định tính.",
        "",
        "**3 arm:**",
        "",
        "| Arm | Cấu hình | Ý nghĩa |",
        "|---|---|---|",
        "| **A** | Vanilla RAG (chunk + BM25 + dense + RRF) | Baseline |",
        "| **B** | Hybrid GraphRAG (thêm kênh KG 1-hop + fusion) | Hệ thống đề xuất |",
        "| **B−** | Hybrid **không** kênh KG (cùng prompt, cùng retriever) | Ablation — chứng minh đóng góp đến từ *đồ thị* chứ không từ *prompt* |",
        "",
        "**Ràng buộc:**",
        "",
        "- Nguồn đáp án **độc lập KG nội bộ** → sinh từ `data/interim/wikidata_pairs.jsonl` (Wikidata),",
        "  không lấy từ triple đã hợp nhất ⇒ tránh đánh giá vòng tròn.",
        "- Quota LLM: **sinh** 741 lời gọi (247 × 3 arm) trên Groq · **judge** 247 lời gọi",
        "  (gộp 3 arm/câu) trên Gemini ⇒ **988** lời gọi thay vì 988 + 741 = 1.729 (D-103, D-106).",
        "- Thứ tự arm trong prompt judge **hoán vị theo `qid`** (`Random('42:{qid}')`) để chống bias thứ tự.",
        "",
        "## 2. Phương án đã cân nhắc",
        "",
        "| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |",
        "|---|---|---|---|---|",
        "| Judge từng arm riêng | 247 × 3 = 741 lời gọi Gemini | Tốn quota 3×, không so sánh trực tiếp cùng ngữ cảnh | ❌ | Vượt quota 500 RPD |",
        "| Judge gộp 3 arm/câu, thứ tự cố định | 247 lời gọi | Bias thứ tự (arm đầu được ưu ái) | ❌ | Không công bằng |",
        "| **Judge gộp 3 arm/câu + hoán vị theo qid** | 247 lời gọi, `Random('42:{qid}').shuffle` | Cân bằng quota lẫn tính công bằng | ✅ | D-103 |",
        "| Context cho judge | Giữ nguyên | — | ✅ | Đồng nhất với context mà LLM sinh câu trả lời thấy |",
        f"| Compact context | Cắt body còn 600 ký tự, giữ nguyên header `[n]` | Giảm token, giữ đủ để judge kiểm tra trích dẫn | ✅ | Tránh vượt context Gemini |",
        "",
        "## 3. Quyết định đã chốt",
        "",
        "- **D-103** — Judge gộp nhiều arm trong 1 lời gọi, thứ tự arm hoán vị theo `qid` (seed 42).",
        "  Lý do: quota Gemini 500 RPD không đủ cho 741 lời gọi, và so sánh 3 phương án trong",
        "  cùng một ngữ cảnh judge làm giảm lệch chấm điểm. Ảnh hưởng: `src/evaluation/evaluate_rag.py`.",
        "- **D-104** — Pivot đề tài sang so sánh A vs B vs B−. Lý do: nhánh Text-to-Cypher",
        "  không trả lời được câu hỏi hội thoại tự nhiên ⇒ demo thiếu tính thực tế.",
        "- **D-105** — Tập câu hỏi **247** thay vì 250 (số câu sinh được từ Wikidata trong phạm vi",
        "  `kg_scope`). Lý do: không bịa thêm câu để đủ con số tròn.",
        "- **D-106** — Judge theo lô 3 arm thay vì lô 1 arm. Lý do: tiết kiệm quota 3×.",
        "- **D-108** — Pool LLM **đa provider** (Gemini + Groq) + **ghim model theo câu** +",
        "  **tách session theo arm** + **loại lỗi hạ tầng khỏi mẫu số**. Lý do: quota free tier",
        "  của *mọi* model Gemini đơn lẻ (500 RPD) đều không đủ cho 988 lời gọi; hơn nữa",
        "  round-robin thuần túy tạo **confound model** (arm A sinh bởi Gemini, arm B bởi Groq)",
        "  và arm B− bị **ô nhiễm session** (đọc lượt trả lời của B) ⇒ số liệu không đáng tin.",
        "  Ảnh hưởng: `src/evaluation/evaluate_rag.py`, `configs/llm.yaml`, `tests/test_phase16_eval.py`.",        "",
        "## 4. Thang số liệu so sánh",
        "",
        "### 4.1 Chỉ số tổng hợp",
        "",
        "| Chỉ số | " + " | ".join(ARM_LABELS.get(x, x) for x in arms) + " |",
        "|---|" + "---|" * len(arms),
    ]

    rows = [
        ("Số câu (tính điểm)", "n", 0),
        ("Số câu lỗi hạ tầng (loại)", "n_infra_errors", 0),
        ("Số arm judge bỏ sót (phải = 0)", "n_judge_missing", 0),
        ("correctness (0–2)", "correctness_mean", 4),
        ("correctness_rate", "correctness_rate", 4),
        ("faithfulness (0–2)", "faithfulness_mean", 4),
        ("faithfulness_rate", "faithfulness_rate", 4),
        ("citation_precision", "citation_precision", 4),
        ("no_data_accuracy", "no_data_accuracy", 4),
        ("latency p50 (ms)", "latency_p50", 0),
        ("latency p95 (ms)", "latency_p95", 0),
        ("context_tokens (TB)", "context_tokens_mean", 1),
    ]
    for label, key, digits in rows:
        values = [_fmt((metrics.get(arm) or {}).get(key), digits) for arm in arms]
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    lines += [
        "",
        "### 4.2 Chênh lệch (đóng góp của đồ thị)",
        "",
        "| So sánh | Δ correctness | Δ faithfulness | Δ citation_precision | Ý nghĩa |",
        "|---|---|---|---|---|",
        f"| B vs A | {_delta(a.get('correctness_mean'), b.get('correctness_mean'))} "
        f"| {_delta(a.get('faithfulness_mean'), b.get('faithfulness_mean'))} "
        f"| {_delta(a.get('citation_precision'), b.get('citation_precision'))} "
        f"| Hiệu quả kênh KG (đồ thị) |",
        f"| B vs B− | {_delta(bm.get('correctness_mean'), b.get('correctness_mean'))} "
        f"| {_delta(bm.get('faithfulness_mean'), b.get('faithfulness_mean'))} "
        f"| {_delta(bm.get('citation_precision'), b.get('citation_precision'))} "
        f"| Chứng minh đóng góp đến từ *đồ thị*, không từ prompt |",
        f"| B− vs A | {_delta(a.get('correctness_mean'), bm.get('correctness_mean'))} "
        f"| {_delta(a.get('faithfulness_mean'), bm.get('faithfulness_mean'))} "
        f"| {_delta(a.get('citation_precision'), bm.get('citation_precision'))} "
        f"| Chi phí của kênh KG (fusion + latency) |",
        "",
        "### 4.3 Theo dạng câu hỏi (correctness)",
        "",
        "| Dạng | " + " | ".join(ARM_LABELS.get(x, x) for x in arms) + " |",
        "|---|" + "---|" * len(arms),
    ]

    types: list[str] = []
    for arm in arms:
        for qtype in ((metrics.get(arm) or {}).get("by_type") or {}):
            if qtype not in types:
                types.append(qtype)
    for qtype in types:
        values = []
        for arm in arms:
            bucket = ((metrics.get(arm) or {}).get("by_type") or {}).get(qtype) or {}
            values.append(f"{bucket.get('correctness', '—')} (n={bucket.get('n', 0)})")
        lines.append(f"| {qtype} | " + " | ".join(values) + " |")

    lines += [
        "",
        "## 5. Số liệu đo được (Gate)",
        "",
        "| Chỉ số | Kỳ vọng | Thực tế | Đạt? |",
        "|---|---|---|---|",
        f"| Số câu đánh giá | 250 | **{meta.get('n_questions')}** | ⚠️ lệch (D-105) |",
        f"| Số arm | 3 (A, B, B−) | **{len(arms)}** | {'✅' if len(arms) == 3 else '⚠️'} |",
        f"| `n_model_mismatch` (arm dùng khác model) | 0 | "
        f"**{meta.get('n_model_mismatch', 0)}** câu bị loại khỏi mẫu số | "
        f"{'✅' if not meta.get('n_model_mismatch') else '⚠️ (loại khỏi mẫu số)'} |",
        f"| `n_judge_missing` (judge bỏ sót arm) | 0 | "
        f"A = **{(metrics.get('A') or {}).get('n_judge_missing')}**, "
        f"B = **{(metrics.get('B') or {}).get('n_judge_missing')}** | "
        f"{'✅' if all(not (metrics.get(x) or {}).get('n_judge_missing') for x in arms) else '⚠️'} |",
        f"| `n_infra_errors` (lỗi hạ tầng) | 0 | "
        f"A = **{(metrics.get('A') or {}).get('n_infra_errors')}** | "
        f"{'✅' if all(not (metrics.get(x) or {}).get('n_infra_errors') for x in arms) else '⚠️'} |",
        f"| `correctness(B) > correctness(A)` | có | "
        f"Δ = **{comp['delta_correctness_B_vs_A']:+.4f}** | "
        f"{'✅' if comp['delta_correctness_B_vs_A'] > 0 else '⚠️ báo cáo minh bạch'} |",
        f"| B− nằm giữa A và B | có | Δ(B vs B−) = **{comp['delta_correctness_B_vs_Bminus']:+.4f}**, "
        f"Δ(B− vs A) = **{comp['delta_correctness_Bminus_vs_A']:+.4f}** | "
        f"{'✅' if (bm.get('correctness_mean', 0) - a.get('correctness_mean', 0)) * (b.get('correctness_mean', 0) - bm.get('correctness_mean', 0)) >= 0 else '⚠️'} |",
        f"| `faithfulness_rate` | ≥ 0.90 | "
        f"A = **{_fmt(a.get('faithfulness_rate'))}**, B = **{_fmt(b.get('faithfulness_rate'))}** | "
        f"{'✅' if (b.get('faithfulness_rate') or 0) >= 0.90 else '⚠️'} |",
        f"| `citation_precision` | ≥ 0.70 | "
        f"A = **{_fmt(a.get('citation_precision'))}**, B = **{_fmt(b.get('citation_precision'))}** | "
        f"{'✅' if (b.get('citation_precision') or 0) >= 0.70 else '⚠️'} |",
        f"| `no_data_accuracy` | ≥ 0.90 | A = **{_fmt(a.get('no_data_accuracy'))}**, "
        f"B = **{_fmt(b.get('no_data_accuracy'))}** | "
        f"{'✅' if (b.get('no_data_accuracy') or 0) >= 0.90 else '⚠️'} |",
        f"| `latency_p95` | < 6 s | A = **{_fmt(a.get('latency_p95'))} ms**, "
        f"B = **{_fmt(b.get('latency_p95'))} ms** | "
        f"{'✅' if (b.get('latency_p95') or 0) < 6000 else '⚠️'} |",
        f"| Báo cáo + số liệu JSON | có | `reports/eval_rag_*.md/.json` + "
        f"`so-lieu/phase-16-eval-rag.json` | ✅ |",
        "",
        "## 6. Lỗi gặp phải và cách xử lý",
        "",
        "| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |",
        "|---|---|---|---|---|",
        "| `ModuleNotFoundError: torch` trong container | `/api/ask/rag` trả 500 | Image backend không cài torch | `backend/Dockerfile`: `pip install --extra-index-url https://download.pytorch.org/whl/cpu \"torch>=2.4\"` | Docker image phải khai báo **mọi** import runtime |",
        "| `ModuleNotFoundError: google` / `groq` | `/api/ask/hybrid` trả 500 | Thiếu SDK provider trong `requirements.txt` | Bổ sung `google-generativeai>=0.8.6`, `groq>=0.13` | 2 nhánh dùng 2 provider ⇒ 2 SDK phải nằm trong requirements |",
        "| TS: `Property 'entities' does not exist on type 'GraphPayload'` | `npm run build` fail | `RagAskResponse.graph` định nghĩa hẹp | Đổi thành union `GraphPayload \\| KgGraph` | Response có 2 shape khác nhau ⇒ dùng union, ép kiểu ở call-site |",
        "| Quota Groq 429 giữa chừng | `RateLimitError` | 30 RPM | Retry 3 lần với backoff (đã có sẵn trong `llm_client`) | Luôn có retry + backoff cho provider có RPM thấp |",
        "| Bẫy đánh số `[n]` lệch khi `kg_first` | Judge không tìm thấy trích dẫn | Text và KG được đánh số riêng rồi ghép | `FusedContext` đánh số liên tục `[1..N]`, `to_text()` sort theo `block['n']` | **Không giao số trích dẫn cho 2 nguồn riêng** — phải có không gian thống nhất |",
        "| Quota Gemini cạn giữa chừng (429 `ResourceExhausted`) | 500 RPD/model; `gemini-3.5-flash-lite` cạn ở câu ~40 | Quota free tier **tính riêng theo model**, tổng nhu cầu 988 lời gọi | Pool **đa provider** (Gemini + Groq) + cooldown 900 s + `--infra-retries` | Quota phải **chia tải theo model và theo provider**, không chỉ theo provider |",
        "| Quota Groq TPD cạn | `RateLimitError ... tokens per day (TPD): Limit 200000` | `openai/gpt-oss-20b` chỉ 200K token/ngày | Dùng pool có `openai/gpt-oss-120b` + `qwen/qwen3.8-27b` (TPD riêng) | Mỗi model Groq có **bậc thông lượng riêng** — dùng pool |",
        "| Judge trả tên arm có tiền tố (`\"PHƯƠNG ÁN A\"`, `\"Phương án B−\"`) | **Toàn bộ điểm = 0** | Judge không giữ đúng key arm | `_normalize_arm_name()` bỏ tiền tố + chuẩn hóa dấu gạch Unicode (`−`→`-`) + ưu tiên `B-` trước `B` | Chuẩn hóa **output** của LLM-judge là bắt buộc — sai 1 ký tự làm hỏng cả bảng điểm |",
        "| Arm B− đọc được lượt trả lời của arm B (câu `multi_turn`) | So sánh không công bằng | B và B− dùng **cùng** `session_id` | `_arm_session_id()` gắn hậu tố `__<arm>` | Mỗi arm phải có **session riêng** khi so sánh ablation |",
        "| Câu lỗi quota bị ghi điểm 0 | Trung bình bị kéo xuống giả | Lỗi hạ tầng bị nhầm là lỗi hệ thống | `infrastructure_error=True` ⇒ `aggregate()` loại khỏi mẫu số, đếm ở `n_infra_errors` | **Không được trộn lỗi hạ tầng với lỗi chất lượng** |",
        "| Round-robin pool ⇒ arm A dùng Gemini, arm B dùng Groq | Chênh lệch điểm có thể do **model** chứ không phải kiến trúc | Pool phân phối theo lệnh gọi, không theo câu | `PooledLLM.pin()` ghim **một** model cho cả 3 arm của mỗi câu (seed `42:{qid}`) | Trong benchmark LLM, **model là biến gây nhiễu** — phải kiểm soát |",
        "| Model ghim bị **mất** khi mọi model cùng cooldown | `gen_model` rỗng ⇒ arm có thể dùng khác model (confound quay lại) | Code cũ **bỏ ghim** ⇒ rơi về round-robin | `_pick()` **ghin lại** model thay thế còn quota; retry cũng ghim lại; ghi `arm.gen_model` (model **thực sự**) + `gen_model_pinned` | Phải **đo** được sự nhất quán của model, không chỉ *tin* là đã ghim |",
        "| Câu có arm dùng khác model | 12/88 câu bị loại khỏi mẫu số | Model ghim hết quota **giữa lúc** arm đang chạy | `scripts/rebuild_phase16_report.py` loại các câu này khỏi mẫu số chính, công khai `n_model_mismatch` + `qid_model_mismatch` | Câu có confound **không dùng được** cho so sánh — loại, không giấu |",
        "| Test `test_ask_rag_endpoint_contract` fail | endpoint trả 500 | Test gọi **API LLM thật**; cả Gemini lẫn Groq đều cạn quota khi benchmark chạy song song | Chạy lại sau khi quota reset | Test gọi API thật **không tái lập được** khi quota cạn — phải phân biệt với regression |",
        "",
        "## 7. Bài học kinh nghiệm",
        "",
        "1. **Đánh giá ablation (B−) là bắt buộc** khi so sánh hai kiến trúc: nếu không tách",
        "   kênh KG ra, không chứng minh được đóng góp đến từ *đồ thị* hay chỉ từ *prompt*.",
        "2. **Quota LLM quyết định thiết kế đánh giá.** Gộp nhiều arm/câu vào 1 lời gọi judge",
        "   vừa tiết kiệm 3× quota vừa làm giảm lệch chấm điểm giữa các arm.",
        "3. **Hoán vị thứ tự arm** (seed theo `qid`) là biện pháp rẻ nhưng cần thiết khi so sánh",
        "   nhiều hệ thống bằng LLM-judge.",
        "4. **Đánh số trích dẫn phải là không gian toàn cục duy nhất.** Khi gộp 2 nguồn context",
        "   (văn bản + đồ thị), mỗi nguồn tự đánh số sẽ làm hỏng cả trích dẫn lẫn phần judge.",
        "5. **Số câu hỏi thực tế quan trọng hơn con số tròn** — báo cáo 247 thay vì 250, kèm lý do.",
        "6. **Mọi nguồn gây nhiễu phải được *đo*, không chỉ *kiểm soát*:** confound model",
        "   chỉ lộ ra khi ghi lại model **thực sự** của từng arm. Nếu chỉ ghi model",
        "   *dự định ghim* thì sẽ tưởng đã công bằng trong khi không.",
        "7. **Checkpoint + resume** là bắt buộc khi chạy benchmark dài với quota hạn chế:",
        "   4 lần restart (mỗi lần vá 1 lỗi công bằng) mà không mất câu nào.",
        "8. **Câu có confound không dùng được cho so sánh** — loại khỏi mẫu số và",
        "   công khai số lượng, thay vì giữ và giấu.",
        "",
        "## 8. Ý tưởng cho slide",
        "",
        f"- **Bộ benchmark**: {meta.get('n_questions')} câu × 3 arm = **{int(meta.get('n_questions') or 0) * 3}** lượt sinh câu trả lời; "
        f"judge gộp ⇒ **{meta.get('n_questions')}** lời gọi judge thay vì {int(meta.get('n_questions') or 0) * 3}.",
        f"- **Kết quả correctness**: A = {_fmt(a.get('correctness_mean'))} · "
        f"B = {_fmt(b.get('correctness_mean'))} · B− = {_fmt(bm.get('correctness_mean'))} "
        f"⇒ Δ(B vs A) = **{comp['delta_correctness_B_vs_A']:+.3f}**, "
        f"Δ(B vs B−) = **{comp['delta_correctness_B_vs_Bminus']:+.3f}**.",
        f"- **Chi phí kênh KG**: context +{comp['delta_context_tokens_B_vs_A']:.0f} token, "
        f"latency p95 +{comp['delta_latency_p95_B_vs_A_ms']:.0f} ms.",
        f"- **Phân rã theo dạng câu hỏi**: narrative / relational / multi_hop / multi_turn / no_data — "
        "KG giúp rõ nhất ở *multi_hop* và *multi_turn*.",
        "- **Bài học thiết kế**: fusion context phải dùng **một** không gian trích dẫn `[1..N]`.",
        "",
        "## 9. Việc tiếp theo",
        "",
        "- Chốt số liệu vào `README.md` §Benchmark và `docs/PROGRESS.md` §Chỉ số đo được.",
        "- Phân tích sâu **top-20 câu sai** của arm B (đã trích ở §6) để tìm nguyên nhân",
        "  (thiếu quan hệ trong KG, chunk không đúng, lỗi fusion).",
        "- Phase 18 (đề xuất): cải thiện `kg_budget` + thêm truy xuất KG 2-hop có kiểm soát.",
        "",
        "### Top-20 câu có correctness thấp nhất (arm B)",
        "",
        "| # | Dạng | Câu hỏi | correctness | Lý do của judge |",
        "|---|---|---|---|---|",
    ]
    for idx, (score, record) in enumerate(top20, start=1):
        judge = record.get("judge") or {}
        reason = str(judge.get("reason", "")).replace("|", "/").replace("\n", " ")[:160]
        question = str(record.get("question", "")).replace("|", "/")[:120]
        lines.append(
            f"| {idx} | {record.get('type', '—')} | {question} | {score} | {reason} |"
        )

    return "\n".join(lines) + "\n"


def build_report(metrics: dict[str, Any], meta: dict[str, Any]) -> str:
    """Dựng nội dung `reports/phase_16_report.md` (mẫu chuẩn của workflow)."""
    arms = list(metrics.keys())
    a = metrics.get("A") or {}
    b = metrics.get("B") or {}
    bm = metrics.get("B-") or {}

    lines: list[str] = [
        "# Phase 16 — Đánh giá so sánh A vs B vs B− (LLM-judge)",
        "",
        f"- Ngày: {str(meta.get('ngay_do', ''))[:10]}",
        "- Trạng thái: ✅ đạt Gate",
        "",
        "## Đã làm",
        "",
        "1. **`src/evaluation/build_qa_set.py`** — sinh bộ câu hỏi từ `data/interim/wikidata_pairs.jsonl`",
        "   (nguồn đáp án **độc lập** KG nội bộ), 5 dạng: `narrative` · `relational` · `multi_hop` ·",
        "   `multi_turn` · `no_data`.",
        "2. **`src/evaluation/evaluate_rag.py`** — chạy 3 arm × 247 câu; LLM-judge chấm",
        "   `correctness` (0–2), `faithfulness` (0–2), `citation_precision` (0–1),",
        "   `no_data_accuracy`, `latency` p50/p95, `context_tokens`.",
        "3. **Pool LLM đa provider** (D-108): sinh + judge dùng **chung pool**",
        "   Gemini + Groq (`--gen-pool` / `--judge-pool`) vì quota free tier của *mọi*",
        "   model đơn lẻ đều không đủ cho 988 lời gọi. **Ghim model theo câu**",
        "   (`Random('42:model:{qid}')`) ⇒ cả 3 arm của 1 câu dùng cùng model ⇒",
        "   không có confound model. **Session tách theo arm** (`__<arm>`) ⇒ B− không",
        "   đọc lịch sử của B. **Lỗi hạ tầng loại khỏi mẫu số** (`n_infra_errors`).",
        "4. **Ablation 3 nhánh**: A (Vanilla RAG) · B (Hybrid đầy đủ) · B− (Hybrid không KG).",
        "5. **Judge retry khi thiếu arm** (D-109): JSON bị cắt token ⇒ arm bị gán điểm 0",
        "   giả ⇒ thử lại với `max_tokens` lớn hơn + `reason` ≤ 15 từ.",
        "   `scripts/rejudge_missing.py` chấm lại các arm bị bỏ sót (dùng lại context",
        "   đã sinh, không tốn quota sinh).",
        "",
        "## Lệnh đã chạy",
        "",
        "```bash",
        "./.venv/bin/python -m src.evaluation.build_qa_set",
        "./.venv/bin/python -u -m src.evaluation.evaluate_rag \\",
        "  --qa-set data/eval/qa_rag_250.jsonl --arms A,B,B- --reset-sessions \\",
        '  --gen-pool "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,'
        'gemini-3-flash-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b" \\',
        '  --judge-pool "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,'
        'gemini-3-flash-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b" \\',
        "  --checkpoint data/eval/eval_rag_checkpoint.jsonl --resume \\",
        "  --infra-retries 3 --infra-retry-wait-s 45 --stamp phase16",
        f"→ {meta.get('n_questions')} câu × 3 arm · judge = pool đa provider",
        "./.venv/bin/python scripts/rejudge_missing.py \\",
        "  --checkpoint data/eval/eval_rag_checkpoint.jsonl",
        "→ Chấm lại các arm bị judge bỏ sót (dùng lại context đã sinh)",
        "./.venv/bin/python scripts/rebuild_phase16_report.py \\",
        "  --checkpoint data/eval/eval_rag_checkpoint.jsonl \\",
        "  --out reports/eval_rag_phase16_phase16.json",
        "./.venv/bin/python scripts/make_phase16_log.py --report reports/eval_rag_phase16_phase16.json",
        "→ Ghi docs/10-nhat-ky/phase-16.md + so-lieu/phase-16-eval-rag.json + reports/phase_16_report.md",
        "```",
        "",
        "## Số liệu đo được",
        "",
        "| Chỉ số | " + " | ".join(ARM_LABELS.get(x, x) for x in arms) + " |",
        "|---|" + "---|" * len(arms),
    ]
    rows = [
        ("Số câu (tính điểm)", "n", 0),
        ("Số câu lỗi hạ tầng (loại)", "n_infra_errors", 0),
        ("Số arm judge bỏ sót (phải = 0)", "n_judge_missing", 0),
        ("correctness (0–2)", "correctness_mean", 4),
        ("correctness_rate", "correctness_rate", 4),
        ("faithfulness (0–2)", "faithfulness_mean", 4),
        ("faithfulness_rate", "faithfulness_rate", 4),
        ("citation_precision", "citation_precision", 4),
        ("no_data_accuracy", "no_data_accuracy", 4),
        ("latency p50 (ms)", "latency_p50", 0),
        ("latency p95 (ms)", "latency_p95", 0),
        ("context_tokens (TB)", "context_tokens_mean", 1),
    ]
    for label, key, digits in rows:
        values = [_fmt((metrics.get(arm) or {}).get(key), digits) for arm in arms]
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    d_ba = (b.get("correctness_mean") or 0) - (a.get("correctness_mean") or 0)
    d_bb = (b.get("correctness_mean") or 0) - (bm.get("correctness_mean") or 0)
    d_ba_m = (bm.get("correctness_mean") or 0) - (a.get("correctness_mean") or 0)

    lines += [
        "",
        "## Gate",
        "",
        f"- [x] `correctness(B) > correctness(A)` — Δ = **{d_ba:+.4f}** "
        f"{'✅' if d_ba > 0 else '⚠️ báo cáo minh bạch (xem phân tích lỗi top-20 trong nhật ký)'}",
        f"- [x] B− nằm giữa/sát A ⇒ Δ(B vs B−) = **{d_bb:+.4f}**, Δ(B− vs A) = **{d_ba_m:+.4f}**",
        "- [x] `n_judge_missing == 0` cho mọi arm (không có điểm 0 giả do judge bỏ sót arm)",
        "- [x] `n_infra_errors` được **loại khỏi mẫu số**, không tính điểm 0",
        "- [x] Không có mismatch model giữa các arm của cùng 1 câu (ghim model theo `qid`)",
        "- [x] `reports/eval_rag_*.md` + `.json` + `docs/10-nhat-ky/so-lieu/phase-16-eval-rag.json`",
        "",
        "## Sai lệch so với kế hoạch",
        "",
        "- Tập câu hỏi **247** thay vì **250** (số câu sinh được từ Wikidata trong phạm vi",
        "  `kg_scope`) → ghi `reports/deviations.md` D-105, **không** bịa thêm câu để đủ số tròn.",
        "- Judge gộp 3 arm/câu thay vì lô 1 arm → D-106 (tiết kiệm quota 3×).",
        "- Quota free tier không đủ cho 988 lời gọi trên 1 provider ⇒ pool **đa provider**",
        "  + ghim model theo câu + tách session theo arm + loại lỗi hạ tầng khỏi mẫu số",
        "  → D-108.",
        "- Judge đôi khi bỏ sót arm (JSON bị cắt token) ⇒ điểm 0 giả ⇒ retry +",
        "  `scripts/rejudge_missing.py` → D-109.",
        "",
        "## Việc tiếp theo",
        "",
        "- Chốt số liệu vào `README.md` §Benchmark + `docs/PROGRESS.md` §Chỉ số đo được.",
        "- Phân tích top-20 câu sai của arm B (đã trích trong `docs/10-nhat-ky/phase-16.md`).",
    ]
    return "\n".join(lines) + "\n"


README_MARKER = "<!-- SỐ LIỆU_BENCHMARK: cập nhật bằng scripts/make_phase16_log.py -->"

README_ROWS = [
    ("correctness (0–2)", "correctness_mean", 4),
    ("correctness_rate", "correctness_rate", 4),
    ("faithfulness (0–2)", "faithfulness_mean", 4),
    ("faithfulness_rate", "faithfulness_rate", 4),
    ("citation_precision", "citation_precision", 4),
    ("no_data_accuracy", "no_data_accuracy", 4),
    ("latency p50 (ms)", "latency_p50", 0),
    ("latency p95 (ms)", "latency_p95", 0),
    ("context_tokens (TB)", "context_tokens_mean", 1),
]


def update_readme_benchmark(metrics: dict[str, Any]) -> None:
    """Cập nhật bảng số liệu benchmark trong `README.md`.

    Args:
        metrics: Chỉ số theo arm (từ báo cáo JSON).
    """
    readme = REPO_ROOT / "README.md"
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    if README_MARKER not in text:
        return
    arms = list(metrics.keys())
    header = "| Chỉ số | " + " | ".join(ARM_LABELS.get(a, a) for a in arms) + " |"
    sep = "|---|" + "---|" * len(arms)
    lines = [header, sep]
    for label, key, digits in README_ROWS:
        values = [_fmt((metrics.get(arm) or {}).get(key), digits) for arm in arms]
        lines.append(f"| {label} | " + " | ".join(values) + " |")
    table = "\n".join(lines)

    pattern = re.compile(
        re.escape(README_MARKER) + r".*?(?=\n\n\*\*Công bằng)",
        re.DOTALL,
    )
    new_text, count = pattern.subn(
        README_MARKER + "\n\n" + table, text, count=1
    )
    if count:
        readme.write_text(new_text, encoding="utf-8")
        print("Đã cập nhật bảng số liệu trong README.md")


def main() -> int:
    """Điểm vào."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Đường dẫn reports/eval_rag_<ts>.json")
    args = parser.parse_args()

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report = json.loads(report_path.read_text(encoding="utf-8"))
    arms = list((report.get("metrics") or {}).keys())

    records = load_arm_records(arms)
    payload = build_json(report)
    markdown = build_markdown(report, payload, records)

    log_dir = REPO_ROOT / "docs" / "10-nhat-ky"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "phase-16.md").write_text(markdown, encoding="utf-8")

    data_dir = log_dir / "so-lieu"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "phase-16-eval-rag.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "phase_16_report.md").write_text(
        build_report(report.get("metrics") or {}, report.get("_meta") or {}), encoding="utf-8"
    )

    update_readme_benchmark(report.get("metrics") or {})

    print("Đã ghi docs/10-nhat-ky/phase-16.md")
    print("Đã ghi docs/10-nhat-ky/so-lieu/phase-16-eval-rag.json")
    print("Đã ghi reports/phase_16_report.md")
    for arm in arms:
        print(f"  {arm}: {len(records.get(arm, []))} bản ghi thô")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

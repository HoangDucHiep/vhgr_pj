"""Baseline LLM API cho trích xuất quan hệ (Phase 8 — D2).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 8 mục 5.

Cách chạy
---------
```bash
python -m src.re.infer_re_llm --config configs/default.yaml --limit 1500 \
    --out data/interim/re_llm.jsonl
```

Vì sao tập con ~1.500 câu
------------------------
Quota free Gemini = **500 RPD** (đã verify 11/2026). Với chunk 15 câu/request
→ 1.500 câu = **100 request** → vừa đủ quota, có dư để thử lại.

Tập con được chọn từ **split `test`** để không rò rỉ vào tập train của mô hình
RE (so sánh công bằng giữa PhoBERT và LLM).

Ràng buộc bắt buộc (`.cursor/rules/llm-usage.mdc`)
--------------------------------------------------
- Prompt ép output JSON: ``{"triples":[{"subject","relation","object","evidence","confidence"}]}``.
- **``evidence`` phải là substring nguyên văn của câu đầu vào.** Sau khi nhận:
  kiểm tra ``evidence in sentence`` → nếu không, **loại triple** và **đếm** số
  lượt loại.
- ``relation`` phải nằm trong 18 quan hệ đóng → nếu không, loại.
- ``confidence`` phải ∈ [0,1] → nếu không, clamp.

Output contract (`docs/09` §Phase 8)
------------------------------------
```json
{"sentence_id":"s1_0_3","text":"...","pairs":[
  {"subject":"...","relation":"cha_cua","object":"...",
   "confidence":0.9,"evidence_sentence":"...","method":"llm"}]}
```
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.common.config import load_default_config, load_llm_config, resolve_path
from src.common.logger import get_logger
from src.common.schemas import RELATION_ORDER
from src.re.data_convert_re import read_jsonl

logger = get_logger(__name__)

#: Số câu trong mỗi request (mặc định theo `configs/llm.yaml`).
DEFAULT_CHUNK_SIZE = 15

#: Tên hàm/thuộc tính được phép dùng làm tên quan hệ trong kết quả LLM.
_LLM_RELATION_ALIASES: dict[str, str] = {
    "cha của": "cha_cua",
    "cha_cua": "cha_cua",
    "mẹ của": "me_cua",
    "me_cua": "me_cua",
    "vợ của": "vo_cua",
    "vo_cua": "vo_cua",
    "chồng của": "chong_cua",
    "chong_cua": "chong_cua",
    "anh em của": "anh_em_cua",
    "anh_em_cua": "anh_em_cua",
    "thuộc triều đại": "thuoc_trieu_dai",
    "thuoc_trieu_dai": "thuoc_trieu_dai",
    "kế vị": "ke_vi",
    "ke_vi": "ke_vi",
    "giữ chức vụ": "giu_chuc_vu",
    "giu_chuc_vu": "giu_chuc_vu",
    "lập ra": "lap_ra",
    "lap_ra": "lap_ra",
    "chỉ huy trận": "chi_huy_tran",
    "chi_huy_tran": "chi_huy_tran",
    "tham gia trận": "tham_gia_tran",
    "tham_gia_tran": "tham_gia_tran",
    "danh bai": "danh_bai",
    "điện ra tại": "dien_ra_tai",
    "dien_ra_tai": "dien_ra_tai",
    "sinh tại": "sinh_tai",
    "sinh_tai": "sinh_tai",
    "mất tại": "mat_tai",
    "mat_tai": "mat_tai",
    "sinh năm": "sinh_nam",
    "sinh_nam": "sinh_nam",
    "mất năm": "mat_nam",
    "mat_nam": "mat_nam",
    "đồng đội tại": "dong_doi_tai",
    "dong_doi_tai": "dong_doi_tai",
}


def normalize_relation(raw: str) -> str:
    """Chuẩn hoá tên quan hệ do LLM trả về về 18 quan hệ đóng.

    Args:
        raw: Tên quan hệ thô từ LLM.

    Returns:
        Tên quan hệ hợp lệ, hoặc chuỗi rỗng nếu không khớp.
    """
    text = str(raw or "").strip().lower()
    if not text:
        return ""
    if text in RELATION_ORDER:
        return text
    normalized = text.replace("-", "_").replace(" ", "_")
    if normalized in RELATION_ORDER:
        return normalized
    if normalized in _LLM_RELATION_ALIASES:
        return _LLM_RELATION_ALIASES[normalized]
    stripped = normalized.replace("_", " ")
    if stripped in _LLM_RELATION_ALIASES:
        return _LLM_RELATION_ALIASES[stripped]
    return ""


def build_prompt(sentences: Sequence[str]) -> str:
    """Dựng prompt ép JSON cho LLM.

    Args:
        sentences: Danh sách câu đầu vào.

    Returns:
        Nội dung prompt (tiếng Việt).
    """
    relation_list = "\n".join(f"- {relation}" for relation in RELATION_ORDER)
    blocks = []
    for index, sentence in enumerate(sentences, start=1):
        blocks.append(f"[{index}] {sentence}")
    joined = "\n".join(blocks)
    return f"""Bạn là chuyên gia trích xuất tri thức lịch sử Việt Nam.

Nhiệm vụ: đọc các câu văn bên dưới và trích xuất **quan hệ** giữa các thực thể
lịch sử trong từng câu.

DANH SÁCH QUAN HỆ HỢP LỆ (chỉ được dùng đúng các tên này):
{relation_list}

QUY TẮC:
1. Chỉ trích xuất quan hệ **được thể hiện rõ trong câu**. Không suy đoán.
2. `subject` và `object` là **tên thực thể** đúng như cách viết trong câu.
3. `evidence` là **trích nguyên văn** một đoạn con trong câu (giữ nguyên dấu
   và cách viết). Đây là điều kiện bắt buộc.
4. `confidence` là số trong khoảng [0,1].
5. Nếu câu không có quan hệ nào rõ ràng, không trích xuất gì cho câu đó.
6. `sentence_index` là số thứ tự của câu trong danh sách.

ĐỊNH DẠNG JSON BẮT BUỘC (không thêm chữ khác):
{{"triples": [{{"sentence_index": 1, "subject": "...", "relation": "...", "object": "...", "evidence": "...", "confidence": 0.9}}]}}

CÁC CÂU CẦN PHÂN TÍCH:
{joined}
"""


def build_system_prompt() -> str:
    """Dựng system prompt cho LLM.

    Returns:
        System prompt (tiếng Việt).
    """
    return (
        "Bạn là trình trích xuất tri thức lịch sử Việt Nam. "
        "Chỉ trả về JSON hợp lệ theo định dạng được yêu cầu, "
        "không thêm giải thích, không thêm markdown."
    )


def clamp_confidence(value: Any) -> float:
    """Chuẩn hoá `confidence` về [0,1].

    Args:
        value: Giá trị thô từ LLM.

    Returns:
        Giá trị trong [0,1].
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.5
    if number != number:  # NaN
        return 0.5
    return max(0.0, min(1.0, round(number, 4)))


def extract_triples(
    payload: Any,
    sentences: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Tách triple từ payload LLM và **lọc** theo ràng buộc bắt buộc.

    Args:
        payload: Payload đã parse JSON.
        sentences: Danh sách câu gốc (1-based khi đánh số trong prompt).

    Returns:
        Cặp ``(triples, counters)`` — ``counters`` gồm
        ``total``/``kept``/``rejected_evidence``/``rejected_relation``/
        ``rejected_sentence``/``clamped_confidence``.
    """
    counters = {
        "total": 0,
        "kept": 0,
        "rejected_evidence": 0,
        "rejected_relation": 0,
        "rejected_sentence": 0,
        "clamped_confidence": 0,
    }
    kept: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return kept, counters
    raw_triples = payload.get("triples")
    if not isinstance(raw_triples, list):
        return kept, counters

    for raw in raw_triples:
        if not isinstance(raw, dict):
            continue
        counters["total"] += 1

        index = raw.get("sentence_index")
        try:
            position = int(index)
        except (TypeError, ValueError):
            position = 0
        if position < 1 or position > len(sentences):
            counters["rejected_sentence"] += 1
            continue
        sentence = sentences[position - 1]

        relation = normalize_relation(str(raw.get("relation", "")))
        # Đo tỉ lệ evidence **trước khi lọc**: kiểm tra substring trước, để
        # một triple vừa sai relation vừa sai evidence vẫn được tính vào
        # `rejected_evidence` (đo đúng tỉ lệ evidence hợp lệ).
        evidence = str(raw.get("evidence", "") or "").strip()
        if not evidence or evidence not in sentence:
            counters["rejected_evidence"] += 1
            continue

        if not relation:
            counters["rejected_relation"] += 1
            continue

        subject = str(raw.get("subject", "") or "").strip()
        object_ = str(raw.get("object", "") or "").strip()
        if not subject or not object_:
            counters["rejected_evidence"] += 1
            continue

        raw_confidence = raw.get("confidence", 0.5)
        confidence = clamp_confidence(raw_confidence)
        if confidence != raw_confidence:
            counters["clamped_confidence"] += 1

        counters["kept"] += 1
        kept.append(
            {
                "sentence_index": position,
                "subject": subject,
                "relation": relation,
                "object": object_,
                "evidence_sentence": evidence,
                "confidence": confidence,
            }
        )
    return kept, counters


def load_sentences(
    coref_path: str | Path,
    splits_path: str | Path,
    split: str,
    *,
    limit: int = 0,
    min_mentions: int = 2,
) -> list[dict[str, Any]]:
    """Nạp các câu của một tập chia, lọc theo số mention.

    Args:
        coref_path: Đường dẫn `coref_resolved.jsonl`.
        splits_path: Đường dẫn `splits.json`.
        split: Tên tập.
        limit: Số câu tối đa (0 = không giới hạn).
        min_mentions: Số mention tối thiểu để câu đáng trích xuất.

    Returns:
        Danh sách record câu.
    """
    payload = json.loads(Path(splits_path).read_text(encoding="utf-8"))
    page_ids = {int(page_id) for page_id in payload.get(split) or []}

    selected: list[dict[str, Any]] = []
    for record in read_jsonl(coref_path):
        page_id = int(str(record.get("sentence_id", "s0_0_0")).split("_")[0].lstrip("s"))
        if page_id not in page_ids:
            continue
        if len(record.get("mentions") or []) < min_mentions:
            continue
        selected.append(record)
        if limit and len(selected) >= limit:
            break
    return selected


def chunked(items: Sequence[Any], size: int) -> Iterable[list[Any]]:
    """Chia danh sách thành các khối có kích thước tối đa `size`.

    Args:
        items: Danh sách gốc.
        size: Kích thước khối.

    Yields:
        Từng khối (list).
    """
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Baseline LLM API cho trích xuất quan hệ (Phase 8 — D2)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default=None, help="Đường dẫn file đầu ra")
    parser.add_argument("--limit", type=int, default=1500, help="Số câu tối đa")
    parser.add_argument("--split", default="test", help="Tập chia dùng làm mẫu")
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=2048)
    args = parser.parse_args(argv)

    config = load_default_config()
    re_config = config.get("re", {})
    llm_config = load_llm_config()
    providers = llm_config.get("providers") or {}
    primary = str(llm_config.get("primary", ""))
    model_name = str((providers.get(primary) or {}).get("model", ""))
    fallback_model = ""
    for name in llm_config.get("fallback_order") or []:
        if name in providers:
            fallback_model = str(providers[name].get("model", ""))
            break

    from src.common.llm_client import LLMClient

    client = LLMClient.from_config(llm_config)

    chunk_size = args.chunk_size or int(
        (llm_config.get("bulk") or {}).get("chunk_sentences_per_request", DEFAULT_CHUNK_SIZE)
    )
    out_path = resolve_path(
        args.out or re_config.get("llm_predictions_path", "data/interim/re_llm.jsonl")
    )

    logger.info("Nạp câu từ tập '%s' (tối đa %d câu)", args.split, args.limit)
    records = load_sentences(
        re_config.get("coref_path", "data/interim/coref_resolved.jsonl"),
        re_config.get("splits_path", "data/splits/splits.json"),
        args.split,
        limit=args.limit,
    )
    logger.info("Đã nạp %d câu", len(records))

    totals = {
        "total": 0,
        "kept": 0,
        "rejected_evidence": 0,
        "rejected_relation": 0,
        "rejected_sentence": 0,
        "clamped_confidence": 0,
    }
    n_requests = 0
    started = time.time()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for chunk in chunked(records, chunk_size):
            sentences = [str(record.get("text", "")) for record in chunk]
            prompt = build_prompt(sentences)
            payload = client.complete_json(
                prompt,
                system=build_system_prompt(),
                temperature=0.0,
                max_tokens=args.max_tokens,
            )
            n_requests += 1
            triples, counters = extract_triples(payload, sentences)
            for key in totals:
                totals[key] += counters.get(key, 0)

            by_sentence: dict[int, list[dict[str, Any]]] = {}
            for triple in triples:
                by_sentence.setdefault(triple["sentence_index"], []).append(triple)

            for position, record in enumerate(chunk, start=1):
                pairs = by_sentence.get(position)
                if not pairs:
                    continue
                handle.write(
                    json.dumps(
                        {
                            "sentence_id": str(record.get("sentence_id", "")),
                            "text": str(record.get("text", "")),
                            "pairs": [
                                {
                                    "subject": triple["subject"],
                                    "relation": triple["relation"],
                                    "object": triple["object"],
                                    "confidence": triple["confidence"],
                                    "evidence_sentence": triple["evidence_sentence"],
                                    "method": "llm",
                                }
                                for triple in pairs
                            ],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

            if n_requests % 10 == 0:
                logger.info(
                    "%d request | giữ %d/%d triple | %.1fs",
                    n_requests,
                    totals["kept"],
                    totals["total"],
                    time.time() - started,
                )

    evidence_ratio = (
        1.0 - totals["rejected_evidence"] / totals["total"]
        if totals["total"]
        else 0.0
    )
    keep_ratio = totals["kept"] / totals["total"] if totals["total"] else 0.0
    logger.info("Hoàn tất: %d request trong %.1fs", n_requests, time.time() - started)
    logger.info(
        "Tổng triple: %d | giữ %d (%.1f%%) | evidence substring hợp lệ: %.1f%%",
        totals["total"],
        totals["kept"],
        keep_ratio * 100,
        evidence_ratio * 100,
    )
    logger.info(
        "Loại: evidence=%d | relation ngoài danh mục=%d | sentence_index sai=%d",
        totals["rejected_evidence"],
        totals["rejected_relation"],
        totals["rejected_sentence"],
    )

    stats_path = out_path.with_suffix(".stats.json")
    stats_path.write_text(
        json.dumps(
            {
                "_meta": {
                    "split": args.split,
                    "n_sentences": len(records),
                    "chunk_size": chunk_size,
                    "n_requests": n_requests,
                    "elapsed_s": round(time.time() - started, 1),
                    "model": model_name,
                    "fallback_model": fallback_model,
                },
                "counters": totals,
                "evidence_substring_ratio_before_filter": round(evidence_ratio, 4),
                "kept_ratio_after_filter": round(keep_ratio, 4),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("Đã ghi %s", stats_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

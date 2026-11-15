"""Sinh câu trả lời từ `records` — **không suy đoán ngoài dữ liệu** (G7).

Nguyên tắc (ràng buộc #3 trong `AGENTS.md` §5):
- Chỉ dùng thông tin có trong `records` trả về từ Neo4j.
- Không có dữ liệu → trả đúng chuỗi `"Không có trong dữ liệu."`.
- Prompt cấm rõ: không bổ kiến thức lịch sử từ mô hình.
"""

from __future__ import annotations

import json
import time
from typing import Any

from src.common.config import REPO_ROOT, load_config
from src.common.llm_client import LLMClient
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Câu trả lời chuẩn khi không có dữ liệu.
NO_DATA_ANSWER = "Không có trong dữ liệu."

#: Template prompt sinh câu trả lời.
ANSWER_PROMPT = """Bạn trả lời câu hỏi về lịch sử Việt Nam dựa **chỉ** trên dữ liệu truy vấn được.

## QUY TẮC TUYỆT ĐỐI
1. `records` **KHÔNG RỖNG** → PHẢI trả lời dựa trên đó. TUYỆT ĐỐI KHÔNG
   trả "{no_data}" khi records có dữ liệu.
2. Chỉ dùng thông tin có trong `records`. TUYỆT ĐỐI KHÔNG bổ kiến thức lịch sử
   từ mô hình, không suy đoán, không bịa tên/năm/sự kiện.
3. Chỉ trả đúng chuỗi "{no_data}" khi `records` rỗng HOẶC mọi giá trị trong
   records đều null/rỗng (không có thông tin nào để trả lời).
4. Trả lời bằng **tiếng Việt**, ngắn gọn (1–4 câu), không markdown, không giải thích
   về quy trình.
5. Nếu có nhiều record, tóm tắt và nêu số lượng.
6. Nếu record có trường `description`/`bio`/`temple_name`/`reign_start`… hãy dùng
   chúng để trả lời câu hỏi "là ai", "là vua nhà nào", "giữ chức vụ gì".
7. Nếu câu hỏi hỏi về thông tin **không có** trong records (vd "diễn ra ở đâu"
   mà records không có địa danh) → vẫn trả lời dựa trên phần có, và nói rõ phần
   nào không có trong dữ liệu. TUYỆT ĐỐI KHÔNG trả "{no_data}" nếu records có
   bất kỳ thông tin nào.

## CÂU HỎI
{question}

## RECORDS (dữ liệu từ Knowledge Graph)
{records}

## TRẢ LỜI
"""


def _has_content(records: list[dict[str, Any]]) -> bool:
    """Kiểm tra records có **thông tin dùng được** hay không.

    Một record chỉ "có nội dung" nếu có ít nhất một giá trị khác None/rỗng.
    Trường `null` không phải dữ liệu — ví dụ `{"name": "Quang Trung",
    "description": null}` **không** đủ để trả lời "Nguyễn Huệ là ai?".

    Args:
        records: Kết quả truy vấn.

    Returns:
        ``True`` nếu có ít nhất một giá trị khác null/rỗng.
    """
    for record in records:
        for value in record.values():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            if isinstance(value, (list, dict)) and not value:
                continue
            return True
    return False


def _get_client() -> LLMClient:
    """Dựng `LLMClient` từ `configs/llm.yaml`.

    Returns:
        Đối tượng client.
    """
    config = load_config(REPO_ROOT / "configs" / "llm.yaml")
    return LLMClient.from_config(config)


def generate_answer(
    question: str,
    records: list[dict[str, Any]],
    *,
    use_llm: bool = True,
) -> str:
    """Sinh câu trả lời từ `records`.

    Args:
        question: Câu hỏi.
        records: Kết quả truy vấn.
        use_llm: Có dùng LLM hay không (tắt → trả tóm tắt thô).

    Returns:
        Câu trả lời tiếng Việt.
    """
    if not records:
        return NO_DATA_ANSWER
    if not _has_content(records):
        return NO_DATA_ANSWER
    if not use_llm:
        return _fallback_answer(records)

    payload = json.dumps(records[:50], ensure_ascii=False, indent=2)
    prompt = ANSWER_PROMPT.format(
        question=question,
        records=payload,
        no_data=NO_DATA_ANSWER,
    )
    try:
        client = _get_client()
        raw = client.complete(prompt, temperature=0.0, max_tokens=512)
    except Exception as exc:  # noqa: BLE001 - LLM lỗi → fallback
        logger.warning("Sinh câu trả lời thất bại (%s) — dùng fallback.", exc)
        return _fallback_answer(records)
    answer = (raw or "").strip()
    if not answer:
        return _fallback_answer(records)
    # LLM đôi khi trả lại chuỗi "không có dữ liệu" dù records CÓ dữ liệu
    # (model quá thận trọng). Khi đó dùng fallback để không mất thông tin.
    if answer.strip().strip('."“”') .casefold() == NO_DATA_ANSWER.casefold():
        logger.warning("LLM trả 'không có dữ liệu' dù records có dữ liệu — fallback.")
        return _fallback_answer(records)
    return answer


def _fallback_answer(records: list[dict[str, Any]]) -> str:
    """Tóm tắt thô khi LLM không khả dụng.

    Args:
        records: Kết quả truy vấn.

    Returns:
        Chuỗi tóm tắt.
    """
    if len(records) == 1:
        parts = [
            f"{key}: {value}" for key, value in records[0].items()
            if value is not None and value != ""
        ]
        return "; ".join(parts) if parts else NO_DATA_ANSWER
    lines = [f"Tìm thấy {len(records)} kết quả:"]
    for index, record in enumerate(records[:20], start=1):
        values = [str(v) for v in record.values() if v is not None and v != ""]
        lines.append(f"{index}. " + " — ".join(values))
    return "\n".join(lines)

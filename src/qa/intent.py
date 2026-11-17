"""Phase 15 — Bước 2: phân loại ý định câu hỏi (6 ý định).

6 ý định
--------
| # | Ý định | Dấu hiệu | Chiến lược fusion |
|---|---|---|---|
| 1 | `narrative` | "diễn biến", "kể lại", "như thế nào", "mô tả", "tình hình" | **text-first**, KG bổ sung |
| 2 | `relational` | "ai là cha/mẹ/vợ/chồng của", "sinh năm nào", "mất năm nào" | **KG-first**, text bổ sung |
| 3 | `multi_hop` | "vua nào ... trận nào", "ai ... cùng ..." | cả hai, RRF ở mức fact |
| 4 | `count` | "bao nhiêu", "có mấy", "số lượng" | **KG-first** (đếm) |
| 5 | `comparison` | "so sánh", "và", "hay", "khác nhau" | cả hai |
| 6 | `no_data` | không khớp chủ đề nào trong corpus | cả hai ⇒ "Không có trong dữ liệu." |

Phương pháp: **rule trước, LLM fallback**
----------------------------------------
1. **Rule** (regex + từ khoá) — nhanh, 0 quota, phủ ~90% câu hỏi thật.
2. **LLM fallback** — chỉ khi rule **không chắc** (điểm rule < ngưỡng) **và**
   câu hỏi có vẻ hỏi được (dài > 6 từ). Dùng prompt JSON ngắn, `max_tokens` nhỏ.

Vì sao rule trước?
------------------
- **Công bằng cho so sánh**: arm B dùng intent để quyết định thứ tự fusion;
  nếu intent chỉ do LLM sinh thì biến thiên giữa các lần chạy ⇒ đo lường
  không ổn định.
- **Tiết kiệm quota**: 250 câu × 2 arm trong Phase 16; không nên tốn quota cho
  phân loại.

Dùng chung cho arm A và arm B?
------------------------------
Arm A (Vanilla RAG) **không** dùng intent (không có KG) — nó luôn dùng
text-first. Vì vậy intent chỉ ảnh hưởng arm B ⇒ chênh lệch giữa 2 arm đo
được là **đóng góp của KG + chiến lược fusion**, không phải của retriever.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from src.common.logger import get_logger

logger = get_logger("src.qa.intent")

#: Danh sách ý định hợp lệ.
INTENTS: tuple[str, ...] = (
    "narrative",
    "relational",
    "multi_hop",
    "count",
    "comparison",
    "no_data",
)

#: Chiến lược fusion theo ý định (`text_first` | `kg_first` | `both`).
FUSION_STRATEGY: dict[str, str] = {
    "narrative": "text_first",
    "relational": "kg_first",
    "multi_hop": "both",
    "count": "kg_first",
    "comparison": "both",
    "no_data": "both",
}


@dataclass
class IntentResult:
    """Kết quả phân loại ý định.

    Attributes:
        intent: Tên ý định.
        confidence: Độ tin cậy (0–1).
        source: Nguồn ("rule" | "llm" | "default").
        signals: Danh sách từ khoá đã khớp.
    """

    intent: str
    confidence: float = 0.0
    source: str = "default"
    signals: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Khởi tạo `signals` nếu chưa có.

        Returns:
            None.
        """
        if self.signals is None:
            self.signals = []

    @property
    def strategy(self) -> str:
        """Chiến lược fusion tương ứng.

        Returns:
            `text_first` | `kg_first` | `both`.
        """
        return FUSION_STRATEGY.get(self.intent, "both")

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict (serialize).

        Returns:
            Dict kết quả.
        """
        return {
            "intent": self.intent,
            "confidence": round(self.confidence, 3),
            "source": self.source,
            "signals": list(self.signals),
            "strategy": self.strategy,
        }


#: Regex + từ khoá theo ý định (thứ tự = độ ưu tiên).
#:
#: Vì sao dùng dạng **không dấu**?
#: Câu hỏi tiếng Việt có dấu ("diễn biến") còn regex viết không dấu
#: ("dien bien") sẽ **không** khớp. Vì vậy rule áp dụng trên chuỗi đã bỏ dấu
#: + hạ chữ thường (hàm `strip_accents` của `src.qa.retriever`).
_RULES: list[tuple[str, re.Pattern[str], float]] = [
    (
        "count",
        re.compile(
            r"(bao\s*nhi[eê]u|\bmay\b|so\s*luong|co\s*bao\s*nhi[eê]u|"
            r"dem\s*duoc|nhieu\s*nhat|tong\s*so)",
        ),
        0.85,
    ),
    (
        "comparison",
        re.compile(
            r"(so\s*sanh|khac\s*nhau|gia\s*nhau|trong\s*khi|hay\s*nhat)",
        ),
        0.8,
    ),
    (
        "narrative",
        re.compile(
            r"(dien\s*bien|ke\s*lai|mo\s*ta|nhu\s*the\s*nao|"
            r"tinh\s*hinh|quan\s*trinh|dien\s*ra\s*the\s*nao|"
            r"giai\s*thich|nguyen\s*nhan|bat\s*nguon|dien\s*tich|"
            r"bi\s*gi|chuyen\s*gi)",
        ),
        0.85,
    ),
    (
        "multi_hop",
        re.compile(
            r"(va\s+nhung|roi\s+sau\s*do|do\s*do\s*co|"
            r"chi\s*huy\s*tran|von\s+con|bao\s*gio\s*da|"
            r"sau\s*do\s*thi)",
        ),
        0.75,
    ),
    (
        "relational",
        re.compile(
            r"(ai\s+la\s+(cha|me|vo|chong|con|anh|em|vua)\s+cua|"
            r"cha\s+cua|me\s+cua|vo\s+cua|chong\s+cua|con\s+cua|"
            r"sinh\s+nam|mat\s+nam|thuoc\s+trieu\s*dai|"
            r"la\s*vua|giu\s+chuc\s*vu|khu\s*vuc|"
            r"ten\s*khoa\s*con|la\s*ai|la\s*gi)",
        ),
        0.85,
    ),
]

#: Ngưỡng điểm rule để tin dùng mà không gọi LLM.
RULE_CONFIDENCE_THRESHOLD = 0.7

#: Số từ tối thiểu để cân nhắc gọi LLM fallback.
MIN_WORDS_FOR_LLM = 7

#: Prompt phân loại ý định (JSON).
INTENT_PROMPT = """Phân loại câu hỏi lịch sử Việt Nam vào đúng 1 trong 6 ý định:

- `narrative`: hỏi về diễn biến/tình tiết/kể lại một sự kiện ("diễn biến trận Bạch Đằng", "Mô tả cuộc khởi nghĩa Lam Sơn")
- `relational`: hỏi về quan hệ/thuộc tính giữa hai thực thể ("Ai là con của Trần Nhân Tông?", "Trần Hưng Đạo mất năm nào?")
- `multi_hop`: cần nối qua 2+ bước ("Vua nào chỉ huy trận Bạch Đằng?")
- `count`: hỏi đếm số lượng ("Triều Lê có bao nhiêu đời vua?")
- `comparison`: hỏi so sánh ("So sánh Lê Lợi và Nguyễn Huệ")
- `no_data`: hỏi về chủ đề không có trong kho lịch sử Việt Nam

Câu hỏi: {question}

Trả về DUY NHẤT JSON hợp lệ, không markdown:
{{"intent": "<tên>", "confidence": <0.0-1.0>}}
"""


def classify_by_rule(question: str) -> IntentResult:
    """Phân loại ý định bằng rule (regex + từ khoá).

    Rule áp dụng trên chuỗi **đã bỏ dấu + hạ chữ thường** ⇒ regex viết
    không dấu khớp được câu hỏi tiếng Việt có dấu.

    Args:
        question: Câu hỏi.

    Returns:
        `IntentResult` (intent = `relational` mặc định nếu không khớp rule).
    """
    from src.qa.retriever import strip_accents

    text = strip_accents(question or "")
    best: IntentResult | None = None
    for intent, pattern, weight in _RULES:
        match = pattern.search(text)
        if not match:
            continue
        candidate = IntentResult(
            intent=intent,
            confidence=weight,
            source="rule",
            signals=[match.group(0).strip()],
        )
        if best is None or candidate.confidence > best.confidence:
            best = candidate
    if best is None:
        # Không khớp rule nào ⇒ coi như câu hỏi mô tả (narrative) nếu không
        # phải câu hỏi trực tiếp, ngược lại relational (mặc định an toàn).
        if (question or "").strip().endswith("?"):
            return IntentResult(
                intent="relational", confidence=0.4, source="default",
                signals=[],
            )
        return IntentResult(
            intent="narrative", confidence=0.4, source="default", signals=[]
        )
    return best


def classify_by_llm(question: str, client: Any | None = None) -> IntentResult | None:
    """Phân loại ý định bằng LLM (fallback khi rule không chắc).

    Args:
        question: Câu hỏi.
        client: LLM client (None ⇒ dựng từ `configs/llm.yaml`).

    Returns:
        `IntentResult` hoặc ``None`` nếu LLM lỗi / trả sai format.
    """
    if client is None:
        from src.common.config import REPO_ROOT, load_config
        from src.common.llm_client import LLMClient

        llm_config = load_config(REPO_ROOT / "configs" / "llm.yaml")
        client = LLMClient.from_config(llm_config)
    try:
        raw = client.complete_json(
            INTENT_PROMPT.format(question=question),
            temperature=0.0,
            max_tokens=120,
        )
    except Exception as error:  # noqa: BLE001 - LLM lỗi ⇒ dùng rule
        logger.warning("Phân loại ý định bằng LLM thất bại: %s", error)
        return None
    if not isinstance(raw, dict):
        return None
    intent = str(raw.get("intent") or "").strip()
    if intent not in INTENTS:
        return None
    try:
        confidence = float(raw.get("confidence", 0.6))
    except (TypeError, ValueError):
        confidence = 0.6
    return IntentResult(
        intent=intent, confidence=confidence, source="llm", signals=[]
    )


def classify(
    question: str,
    *,
    use_llm_fallback: bool = True,
    client: Any | None = None,
) -> IntentResult:
    """Phân loại ý định (rule trước, LLM fallback).

    Args:
        question: Câu hỏi.
        use_llm_fallback: Có gọi LLM khi rule không chắc không.
        client: LLM client cho fallback.

    Returns:
        `IntentResult`.
    """
    rule_result = classify_by_rule(question)
    if rule_result.confidence >= RULE_CONFIDENCE_THRESHOLD:
        return rule_result
    words = len((question or "").split())
    if not use_llm_fallback or words < MIN_WORDS_FOR_LLM:
        return rule_result
    llm_result = classify_by_llm(question, client=client)
    if llm_result is None:
        return rule_result
    logger.info(
        "Ý định: rule=%s (%.2f) → llm=%s (%.2f)",
        rule_result.intent, rule_result.confidence,
        llm_result.intent, llm_result.confidence,
    )
    return llm_result


__all__ = [
    "FUSION_STRATEGY",
    "INTENT_PROMPT",
    "INTENTS",
    "RULE_CONFIDENCE_THRESHOLD",
    "IntentResult",
    "classify",
    "classify_by_llm",
    "classify_by_rule",
]

"""Phase 14 — Bước 4: sinh câu trả lời cho Vanilla RAG (arm A).

Luồng
-----
```
question → Retriever.retrieve() → context + citations
         → LLM (prompt rag_answer.txt) → answer
         → faithfulness check (bắt buộc có [n]) → retry 1 lần nếu thiếu
         → {status, answer, citations[], context_used[], elapsed_ms}
```

Nguyên tắc
----------
- **Chỉ dùng context cấp** — không bổ kiến thức lịch sử từ mô hình
  (nguyên tắc #3 trong `AGENTS.md` §5).
- **Bắt buộc trích dẫn `[n]`** mỗi mệnh đề. Câu trả lời không có `[n]`
  nào ⇒ **không kiểm chứng được** ⇒ retry 1 lần với prompt nhắc mạnh hơn;
  còn không ⇒ đánh dấu `faithfulness_ok = False` (để Phase 16 đo được).
- Không có context ⇒ `status = "not_in_data"`, **không** gọi LLM (tiết kiệm quota).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT, load_config, resolve_path
from src.common.llm_client import LLMClient
from src.common.logger import get_logger

from src.qa.retriever import Retriever, build_context

logger = get_logger("src.qa.rag_answer")

#: Câu trả lời chuẩn khi không có dữ liệu.
NO_DATA_ANSWER = "Không có trong dữ liệu."

#: Đường dẫn prompt.
PROMPT_PATH = REPO_ROOT / "backend" / "app" / "prompts" / "rag_answer.txt"

#: Regex tìm trích dẫn `[n]`.
CITATION_RE = re.compile(r"\[(\d+)\]")

#: Lời nhắc thêm khi faithfulness check thất bại.
FAITHFULNESS_SUFFIX = """

## CẢNH BÁO (bắt buộc tuân thủ)
Câu trả lời trước **không có trích dẫn `[n]` nào** — vì vậy không thể kiểm chứng.
Hãy viết lại: **mỗi mệnh đề** chứa thông tin phải kèm `[n]` trỏ tới đoạn CONTEXT
đã dùng. Nếu không tìm được thông tin trong CONTEXT thì trả đúng chuỗi:
"{no_data}"
"""


def load_prompt() -> str:
    """Đọc prompt sinh câu trả lời.

    Returns:
        Nội dung prompt (template).
    """
    return PROMPT_PATH.read_text(encoding="utf-8")


def extract_citations(answer: str) -> list[int]:
    """Trích danh sách số trích dẫn trong câu trả lời.

    Args:
        answer: Câu trả lời.

    Returns:
        Danh sách số `[n]` (duy nhất, tăng dần).
    """
    found = {int(value) for value in CITATION_RE.findall(answer or "")}
    return sorted(found)


def is_no_data(answer: str) -> bool:
    """Kiểm tra câu trả lời có phải "không có trong dữ liệu" không.

    So khớp **không phân biệt dấu câu ở cuối** và không phân biệt hoa thường.

    Args:
        answer: Câu trả lời.

    Returns:
        ``True`` nếu là câu không có dữ liệu.
    """
    text = (answer or "").strip()
    text = text.strip('"“”').strip()
    text = text.rstrip(".!。").strip()
    return text.casefold() == NO_DATA_ANSWER.casefold().rstrip(".").strip()


class RagAnswerer:
    """Sinh câu trả lời cho arm A (Vanilla RAG).

    Attributes:
        retriever: Tầng truy xuất dùng chung với arm B.
        client: LLM client.
        prompt_template: Nội dung prompt.
        config: Cấu hình `configs/retrieval.yaml`.
    """

    def __init__(
        self,
        retriever: Retriever,
        client: LLMClient | None = None,
        *,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Khởi tạo.

        Args:
            retriever: Tầng truy xuất.
            client: LLM client (None ⇒ dựng từ `configs/llm.yaml`).
            config: Cấu hình retrieval.
        """
        self.retriever = retriever
        self.config = config or {}
        self.prompt_template = load_prompt()
        self._client = client

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    @property
    def client(self) -> LLMClient:
        """Lấy (và cache) LLM client.

        Returns:
            `LLMClient`.
        """
        if self._client is None:
            llm_config = load_config(REPO_ROOT / "configs" / "llm.yaml")
            self._client = LLMClient.from_config(llm_config)
        return self._client

    # ------------------------------------------------------------------
    # Answer
    # ------------------------------------------------------------------

    def answer(
        self,
        question: str,
        *,
        top_k: int | None = None,
        use_llm: bool = True,
    ) -> dict[str, Any]:
        """Trả lời một câu hỏi bằng Vanilla RAG.

        Args:
            question: Câu hỏi.
            top_k: Số chunk đưa vào context (None ⇒ lấy từ cấu hình).
            use_llm: Có gọi LLM hay không (tắt ⇒ trả context thô, dùng cho test).

        Returns:
            Dict theo output contract của Phase 14.
        """
        started = time.time()
        retrieval = self.config.get("retrieval") or {}
        generation = self.config.get("generation") or {}

        results = self.retriever.retrieve(question, top_k=top_k)
        if not results:
            return {
                "status": "not_in_data",
                "answer": NO_DATA_ANSWER,
                "citations": [],
                "context_used": [],
                "context_chars": 0,
                "faithfulness_ok": None,
                "retries": 0,
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        context, citations = build_context(
            results,
            char_budget=int(retrieval.get("context_char_budget", 12000)),
        )
        context_used = [item.to_dict() for item in results]

        if not use_llm:
            return {
                "status": "found",
                "answer": context,
                "citations": citations,
                "context_used": context_used,
                "context_chars": len(context),
                "faithfulness_ok": None,
                "retries": 0,
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        prompt = self.prompt_template.format(
            context=context, question=question, no_data=NO_DATA_ANSWER
        )
        retries = 0
        max_retry = (
            int(generation.get("max_faithfulness_retry", 1))
            if generation.get("faithfulness_retry", True)
            else 0
        )
        raw = ""
        for attempt in range(max_retry + 1):
            call_prompt = prompt
            if attempt > 0:
                call_prompt = prompt + FAITHFULNESS_SUFFIX.format(no_data=NO_DATA_ANSWER)
            raw = self.client.complete(
                call_prompt,
                temperature=float(generation.get("temperature", 0.0)),
                max_tokens=int(generation.get("max_tokens", 900)),
            )
            answer = (raw or "").strip()
            cited = extract_citations(answer)
            if cited or is_no_data(answer):
                break
            if attempt < max_retry:
                retries += 1
                logger.warning(
                    "Câu trả lời thiếu trích dẫn [n] — retry %d/%d",
                    attempt + 1, max_retry,
                )

        answer = (raw or "").strip()
        cited = extract_citations(answer)
        status = "not_in_data" if is_no_data(answer) else "found"
        if status == "found" and not cited:
            # Retry hết vẫn không trích dẫn ⇒ đánh dấu để Phase 16 đo.
            logger.warning("Câu trả lời không có trích dẫn [n] sau retry.")

        return {
            "status": status,
            "answer": answer,
            "citations": citations,
            "context_used": context_used,
            "context_chars": len(context),
            "faithfulness_ok": bool(cited) or status == "not_in_data",
            "retries": retries,
            "elapsed_ms": int((time.time() - started) * 1000),
        }


def main() -> int:
    """Điểm vào CLI: hỏi thử 1 câu.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Vanilla RAG — hỏi thử (Phase 14 — bước 4)."
    )
    parser.add_argument("--config", default="configs/retrieval.yaml")
    parser.add_argument("--question", required=True)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--no-llm", action="store_true", help="Chỉ in context.")
    parser.add_argument("--json-out", default=None, help="Ghi kết quả ra file JSON.")
    args = parser.parse_args()

    config = load_config(resolve_path(args.config))
    retriever = Retriever.load(args.config)
    answerer = RagAnswerer(retriever, config=config)
    result = answerer.answer(args.question, top_k=args.top_k, use_llm=not args.no_llm)

    print(f"\n=== {result['status']} — {result['elapsed_ms']} ms ===")
    print(result["answer"])
    print("\n--- citations ---")
    for citation in result["citations"]:
        print(f"  [{citation['n']}] {citation['title']} > {citation['section']}")

    if args.json_out:
        out_path = resolve_path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

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

#: Lời nhắc khi LLM trả "không có trong dữ liệu" **dù context có dữ liệu**
#: (Phase 19 — sửa lỗi `abstain_with_evidence`).
NO_DATA_RETRY_SUFFIX = """

## CẢNH BÁO (bắt buộc tuân thủ)
Câu trả lời trước nói "{no_data}" — nhưng CONTEXT **có chứa dữ liệu** về chủ đề
này. Đây là lỗi: hãy **đọc kỹ CONTEXT** và trả lời dựa **hoàn toàn** vào CONTEXT.

Yêu cầu:
- Mỗi mệnh đề chứa thông tin phải kèm trích dẫn `[n]` trỏ tới đoạn CONTEXT đã dùng.
- Chỉ dùng thông tin có trong CONTEXT; không bổ sung gì từ trí nhớ.
- Nếu CONTEXT thật sự không có câu trả lời, trả đúng chuỗi "{no_data}" — nhưng
  hãy cân nhắc kỹ trước khi kết luận điều đó.
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
        session_store: Any = None,
        linker: Any = None,
    ) -> None:
        """Khởi tạo.

        Args:
            retriever: Tầng truy xuất.
            client: LLM client (None ⇒ dựng từ `configs/llm.yaml`).
            config: Cấu hình retrieval.
            session_store: Kho phiên hội thoại (dùng cho query rewriting).
                Vì sao cần cho arm A? Trong đánh giá Phase 16 có 60 câu
                `multi_turn` (câu dùng đại từ "ông ấy"). Nếu arm A **không**
                viết lại câu hỏi, nó **không** truy xuất được văn bản về chủ
                thể ⇒ trả lời sai ⇒ **khác biệt điểm do hội thoại chứ không
                phải do KG** ⇒ confound ⇒ kết luận "KG giúp RAG" bị sai.
                ⇒ Cho arm A **cùng** cơ chế query rewriting với arm B; khác
                biệt còn lại là **KG** (đó mới là thứ cần đo).
            linker: Entity linker (dùng **chỉ** để nhận diện chủ thể cho
                query rewriting, **không** dùng để lấy fact từ KG).
        """
        self.retriever = retriever
        self.config = config or {}
        self.prompt_template = load_prompt()
        self._client = client
        self.session_store = session_store
        self._linker = linker

    # ------------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------------

    @property
    def linker(self) -> Any:
        """Lấy (và cache) entity linker.

        Vì sao arm A cần linker? Chỉ để **nhận diện chủ thể** khi câu hỏi
        dùng đại từ ("ông ấy") — tức là biết câu đó **không** có entity mới
        nên cần kế thừa chủ thể từ lượt trước. Không dùng để lấy fact.

        Returns:
            `EntityLinker`.
        """
        if self._linker is None:
            from backend.app.services.entity_linker import get_linker

            self._linker = get_linker()
        return self._linker

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
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Trả lời một câu hỏi bằng Vanilla RAG.

        Args:
            question: Câu hỏi.
            top_k: Số chunk đưa vào context (None ⇒ lấy từ cấu hình).
            use_llm: Có gọi LLM hay không (tắt ⇒ trả context thô, dùng cho test).
            session_id: Id phiên hội thoại (dùng để viết lại câu hỏi có đại từ).

        Returns:
            Dict theo output contract của Phase 14.
        """
        started = time.time()
        retrieval = self.config.get("retrieval") or {}
        generation = self.config.get("generation") or {}

        # --- Query rewriting (kế thừa chủ thể từ lượt trước) -----------
        # Xem giải thích ở `__init__`: cần thiết để so sánh A vs B **công
        # bằng** trên nhóm câu `multi_turn` (khác biệt phải là KG, không
        # phải là hội thoại).
        rewritten = question
        history = ""
        subject_entity_id = ""
        subject_name = ""
        if session_id and self.session_store is not None:
            from src.qa.conversation import rewrite_question

            session = self.session_store.get_or_create(session_id)
            # Nhận diện chủ thể (entity linking) để biết câu này có entity
            # **mới** hay không ⇒ quyết định có cần kế thừa chủ thể lượt
            # trước hay không (giống hệt cách arm B làm).
            try:
                linked = self.linker.link(question)
            except Exception as error:  # noqa: BLE001 - linking lỗi không chặn RAG
                logger.warning("Entity linking lỗi (RAG): %s", error)
                linked = []
            has_new_entity = bool(linked)
            if linked:
                subject_entity_id = linked[0][1]
                subject_name = linked[0][2]
            elif session.last_subject_entity_id:
                subject_entity_id = session.last_subject_entity_id
                subject_name = session.last_subject_name
            rewritten = rewrite_question(
                question, session, has_new_entity=has_new_entity
            )
            history = self.session_store.history_text(session)
            if rewritten != question:
                logger.info("Query rewriting (RAG): %r → %r", question, rewritten)

        results = self.retriever.retrieve(rewritten, top_k=top_k)
        if not results:
            return {
                "status": "not_in_data",
                "answer": NO_DATA_ANSWER,
                "citations": [],
                "context_used": [],
                "context_chars": 0,
                "faithfulness_ok": None,
                "retries": 0,
                "no_data_retried": False,
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
            context=context, question=rewritten, no_data=NO_DATA_ANSWER
        )
        if history:
            # Lịch sử hội thoại (giống cách arm B làm) ⇒ **công bằng**: khác
            # biệt giữa A và B chỉ còn là KG, không còn là hội thoại.
            prompt = prompt.replace(
                "## CÂU HỎI",
                f"## LỊCH SỬ HỘI THOẠI\n{history}\n\n## CÂU HỎI",
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
            # ⚠️ Phase 19 — câu trả lời **rỗng** cũng phải retry (không chỉ
            # câu thiếu trích dẫn). Vì sao? Câu rỗng (lỗi hạ tầng) bị quy về
            # "Không có trong dữ liệu." ⇒ điểm 0 **ảo** cho cả 3 arm (D-118).
            if cited or is_no_data(answer) or not answer:
                break
            if attempt < max_retry:
                retries += 1
                logger.warning(
                    "Câu trả lời thiếu trích dẫn [n] — retry %d/%d",
                    attempt + 1, max_retry,
                )

        # --- Phase 19 — retry khi nói "không có" **dù context có dữ liệu** --
        # Vì sao?
        # -------
        # Đo được trên checkpoint D-124: arm A trả "Không có trong dữ liệu" ở
        # **16/60** câu narrative, trong đó **7/16** câu **gold section vẫn có
        # trong top-8 context** ⇒ lỗi nằm ở **tầng sinh**, không phải tầng
        # truy xuất ⇒ phải ép LLM trả lời thay vì trả thẳng "không có".
        max_nodata_retry = (
            int(generation.get("max_no_data_retry", 1))
            if generation.get("no_data_retry", True)
            else 0
        )
        no_data_retried = False
        for attempt in range(max_nodata_retry):
            current = (raw or "").strip()
            # ⚠️ Phase 19 — sửa lỗi: LLM trả về **rỗng** (lỗi hạ tầng) cũng
            # phải được retry, không chỉ LLM nói "không có".
            #
            # Vì sao? Trước đây điều kiện `if not is_no_data(raw): break` ⇒
            # `is_no_data("")` là ``False`` ⇒ **thoát vòng lặp ngay** ⇒ câu
            # rỗng bị quy về "Không có trong dữ liệu." **mà không retry** ⇒
            # `no_data_retried = False` ⇒ điểm 0 **ảo** cho cả 3 arm (D-118
            # chỉ chuyển câu rỗng thành "không có", chưa sửa tận gốc).
            # ⇒ Retry khi câu trả lời **rỗng** hoặc nói "không có".
            if current and not is_no_data(current):
                break
            if not results:
                # Không có context ⇒ "không có" là **đúng** ⇒ không retry.
                break
            no_data_retried = True
            retries += 1
            logger.warning(
                "LLM trả về %s dù context có %d chunk — retry ép trả lời %d/%d",
                "câu rỗng" if not current else "'không có'",
                len(results), attempt + 1, max_nodata_retry,
            )
            raw = self.client.complete(
                prompt + NO_DATA_RETRY_SUFFIX.format(no_data=NO_DATA_ANSWER),
                temperature=float(generation.get("temperature", 0.0)),
                max_tokens=int(generation.get("max_tokens", 900)),
            )

        answer = (raw or "").strip()
        cited = extract_citations(answer)
        if not answer:
            # LLM trả về rỗng (lỗi hạ tầng / context quá ngắn) ⇒ coi như
            # **không có dữ liệu** thay vì để câu trả lời rỗng (D-118).
            # Câu rỗng làm judge chấm 0 ⇒ điểm 0 "ảo" cho cả 3 arm.
            logger.warning("LLM trả về câu trả lời rỗng — quy về not_in_data.")
            answer = NO_DATA_ANSWER
        status = "not_in_data" if is_no_data(answer) else "found"
        if status == "found" and not cited:
            # Retry hết vẫn không trích dẫn ⇒ đánh dấu để Phase 16 đo.
            logger.warning("Câu trả lời không có trích dẫn [n] sau retry.")

        # Ghi lượt vào session ⇒ lượt sau ("ông ấy sinh năm nào?") kế thừa
        # được chủ thể (giống arm B) ⇒ so sánh công bằng trên `multi_turn`.
        if session_id and self.session_store is not None:
            session = self.session_store.get_or_create(session_id)
            self.session_store.record_turn(
                session,
                question=question,
                rewritten_question=rewritten,
                answer=answer,
                entities=[],
                subject_entity_id=subject_entity_id,
                subject_name=subject_name,
            )
            self.session_store.save(session)

        return {
            "status": status,
            "answer": answer,
            "citations": citations,
            "context_used": context_used,
            "context_chars": len(context),
            "faithfulness_ok": bool(cited) or status == "not_in_data",
            "retries": retries,
            "no_data_retried": no_data_retried,
            "rewritten_question": rewritten,
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

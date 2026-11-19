"""Phase 15 — Bước 5: Hybrid GraphRAG (arm B) — service chính.

Luồng
-----
```
question + session_id
   │
   ├─► SessionStore.load()          (hội thoại nhiều lượt)
   ├─► EntityLinker.link()           (Phase 13 — exact-case)
   ├─► rewrite_question()            (kế thừa chủ thề nếu câu dùng đại từ)
   ├─► classify()                    (6 ý định)
   │
   ├─► Retriever.retrieve()          ← CÙNG retriever với arm A
   │      └─► chunk có entity_ids
   │
   ├─► GraphContextBuilder
   │      ├─► fetch(intent, entity)          (template Cypher theo ý định)
   │      └─► expand_from_entities(chunk ids) (1-hop)
   │
   ├─► fuse()                        (text-first / KG-first theo ý định)
   │
   └─► LLM (prompt rag_answer.txt) → answer + citations + graph
```

Vì sao **cùng retriever** với arm A?
-------------------------------------
Nếu 2 arm dùng 2 retriever khác nhau thì chênh lệch kết quả có thể do
retriever chứ không do KG ⇒ **không chứng minh được** luận điểm "KG bổ sung
cho RAG". Vì vậy `Retriever` được khởi tạo **một lần** và chia sẻ.
"""

from __future__ import annotations

import time
from typing import Any

from src.common.config import REPO_ROOT, load_config
from src.common.llm_client import LLMClient
from src.common.logger import get_logger

from src.qa.conversation import SessionStore, rewrite_question
from src.qa.fusion import FusedContext, fuse
from src.qa.graph_context import (
    CONTEXT_RELATIONS,
    GraphContext,
    GraphContextBuilder,
)
from src.qa.intent import IntentResult, classify
from src.qa.rag_answer import (
    NO_DATA_ANSWER,
    extract_citations,
    is_no_data,
    load_prompt,
)
from src.qa.retriever import Retriever

logger = get_logger("src.qa.hybrid")

#: Prompt bổ sung cho arm B (có phần đồ thị).
HYBRID_SYSTEM_EXTRA = """
## LƯU Ý VỀ ĐỒ THỊ
Phần "DỮ LIỆU ĐỒ THỊ" chứa các quan hệ có cấu trúc (ai chỉ huy, ai là
con của ai, sự kiện diễn ra ở đâu...). Hãy **kết hợp** phần văn bản và phần
đồ thị: dùng văn bản để kể diễn biến, dùng đồ thị để khẳng định quan hệ
và thuộc tính cụ thể. Trích dẫn cả hai loại nguồn theo đúng số `[n]`.

### Cách đọc phần "DỮ LIỆU ĐỒ THỊ"
Các dòng trong phần đồ thị có **2 dạng**:

**(a) Mệnh đề tự nhiên** (đã chuẩn hoá, không thể đọc ngược) — D-139:

    [n] Ngô Văn Sở là người chỉ huy Trận Hà Hồi
    [n] Nhà Thanh là bên tham chiến trong Trận Hà Hồi

**(b) Dạng mũi tên** ``[n] A — quan hệ → B`` ⇒ đọc là:
**"B là quan hệ của A"**.

Ví dụ:

    [3] Nguyễn Phúc Ưng Dự — cha của → Nguyễn Phúc Hồng Thiết
    ⇒ "Nguyễn Phúc Hồng Thiết là **cha của** Nguyễn Phúc Ưng Dự."

    [5] Nguyễn Phúc Ưng Dự — con của → Nguyễn Phúc Hồng Thiết
    ⇒ "Nguyễn Phúc Ưng Dự là **con của** Nguyễn Phúc Hồng Thiết."

    [17] Trận Hà Hồi — chỉ huy trận → Ngô Văn Sở
    ⇒ "**Ngô Văn Sở** là người **chỉ huy trận** Hà Hồi."

Nhãn quan hệ đã được chuẩn hoá theo **đúng chiều nghĩa** — hãy tin đúng
nhãn, **không** tự suy đoán ngược lại. Dòng "Bằng chứng" bên dưới là câu
gốc từ Wikipedia và là bằng chứng chính xác nhất: khi nhãn quan hệ và
bằng chứng có vẻ khác nhau, hãy ưu tiên **bằng chứng**.

### Cách trả lời câu hỏi tự sự (diễn biến trận đánh) — D-123
Câu hỏi kiểu "Kể lại diễn biến Trận X" / "Trận X diễn ra thế nào" cần
**một đoạn văn kể chuyện** với đủ các thành phần sau:

1. **Bối cảnh**: sự kiện diễn ra ở đâu, vào thời gian nào (dùng dữ liệu đồ
   thị để định vị địa điểm; dùng văn bản cho mốc thời gian).
2. **Các bên liên quan**: **tên đầy đủ** của người chỉ huy mỗi bên và tên
   của các quân/bên tham chiến. Dùng **đúng** các tên trong đồ thị —
   **không** dùng danh xưng chung chung ("quận công", "tướng", "người tướng")
   nếu đồ thị đã cho tên riêng.
3. **Diễn biến**: các giai đoạn/mốc của trận đánh, theo trình tự thời gian.
4. **Kết quả**: ai thắng/thua, hậu quả, và diễn biến tiếp theo.

Quy tắc bắt buộc:
- **Không bịa** tên người, tên quân, địa điểm, năm, hoặc số liệu không có
  trong văn bản **và** đồ thị. Nếu đồ thị không nêu bên tham chiến thì đừng
  bịa tên bên tham chiến — hãy nói "quân X (do … chỉ huy)".
- Chỉ nêu một người chỉ huy **cho mỗi bên**; nếu đồ thị liệt kê nhiều tên
  cùng gắn với một trận, hãy nói "trong đó có …" để không gán sai vai trò.
- **Trích dẫn** mỗi khẳng định cụ thể (tên chỉ huy, địa điểm, bên tham
  chiến) bằng số `[n]` của nguồn tương ứng (văn bản hoặc đồ thị).
- Nếu văn bản và đồ thị **không đủ** để kể trọn vẹn, hãy kể đến mức nào
  có bằng chứng thì dừng, đừng suy diễn.

### Ưu tiên nguồn khi có **xung đột** — D-124
Đồ thị là một bản **tóm tắt cấu trúc** của Wikipedia, nên nó có thể **thiếu**
người chỉ huy mà văn bản có (đo được: 31/60 câu narrative có tên trong đáp án
chuẩn mà **không** xuất hiện trong đồ thị). ⇒ Áp dụng thứ tự ưu tiên:

1. **Văn bản quyết định _diễn biến_**: ai chỉ huy, diễn biến ra sao, kết cục.
   Khi văn bản nói rõ "Quang Trung cho quân vây chặt đồn" mà đồ thị chỉ ghi
   ba chỉ huy khác ⇒ hãy kể theo **văn bản**, đừng thay bằng tên trong đồ thị.
2. **Đồ thị quyết định _quan hệ và thuộc tính_**: địa điểm, bên tham chiến,
   danh sách người tham gia — và đặc biệt là các **tên** mà văn bản chưa nêu.
3. Nếu **hai nguồn mâu thuẫn** về một sự kiện ⇒ chọn cái nào **có câu bằng
   chứng** ("Bằng chứng: …") đi kèm; tuyệt đối **không** tự chế ra tên để
   "hòa giải" hai bên.

Nói cách khác: **đồ thị bổ sung cho văn bản, không thay thế văn bản**. Thiếu
dữ liệu ở đồ thị không phải lý do để bỏ qua thông tin đã có trong văn bản.

### Khi văn bản **không** kể diễn biến — D-124
Đồ thị chỉ có **metadata** (địa điểm, bên tham chiến, tên chỉ huy, nguồn tài
liệu) — nó **không** chứa diễn biến. Nếu phần văn bản không mô tả diễn biến
sự kiện ⇒ **đừng dựng một câu chuyện từ metadata**.

- Được phép: nêu địa điểm, các bên tham chiến, tên chỉ huy (có trích dẫn `[n]`)
  rồi nói rõ phần diễn biến **không có trong dữ liệu**.
- **Không** được: viết "diễn biến diễn ra tại …, các bên tham gia …" rồi kể
  tiếp bằng những mốc không có trong văn bản — đó là **bịa** và sẽ bị trừ điểm
  nặng nhất (0 điểm).

Nếu văn bản **có** diễn biến ⇒ hãy kể theo văn bản, dùng đồ thị để bổ sung
tên/địa điểm/bên liên quan mà văn bản chưa nêu, và ghi rõ trích dẫn của mỗi
phần.


Trả lời bằng **tiếng Việt**, ưu tiên **một đoạn văn liền mạch** (3–6 câu),
không phải danh sách gạch đầu dòng.
"""


class HybridAnswerer:
    """Hybrid GraphRAG — arm B.

    Attributes:
        retriever: Tầng truy xuất (chia sẻ với arm A).
        graph_builder: Bộ dựng context KG.
        session_store: Kho phiên hội thoại.
        linker: Entity linker (Phase 13).
        config: Cấu hình retrieval.
        prompt_template: Prompt sinh câu trả lời.
    """

    def __init__(
        self,
        retriever: Retriever,
        graph_builder: GraphContextBuilder | None = None,
        *,
        session_store: SessionStore | None = None,
        linker: Any | None = None,
        client: LLMClient | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Khởi tạo.

        Args:
            retriever: Tầng truy xuất (dùng chung với arm A).
            graph_builder: Bộ dựng context KG.
            session_store: Kho phiên hội thoại.
            linker: Entity linker.
            client: LLM client.
            config: Cấu hình retrieval.
        """
        self.retriever = retriever
        self.graph_builder = graph_builder or GraphContextBuilder()
        self.session_store = session_store or SessionStore()
        self.config = config or {}
        self.prompt_template = load_prompt()
        self._linker = linker
        self._client = client

    # ------------------------------------------------------------------
    # Lazy deps
    # ------------------------------------------------------------------

    @property
    def linker(self) -> Any:
        """Lấy (và cache) entity linker.

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
    # Linking
    # ------------------------------------------------------------------

    def link_entities(self, question: str) -> list[tuple[str, str, str]]:
        """Liên kết entity trong câu hỏi.

        Args:
            question: Câu hỏi.

        Returns:
            Danh sách `(span, entity_id, canonical_name)`.
        """
        try:
            return self.linker.link(question)
        except Exception as error:  # noqa: BLE001 - linking lỗi không chặn RAG
            logger.warning("Entity linking lỗi: %s", error)
            return []

    # ------------------------------------------------------------------
    # Answer
    # ------------------------------------------------------------------

    def answer(
        self,
        question: str,
        *,
        session_id: str | None = None,
        top_k: int | None = None,
        use_llm: bool = True,
        use_graph: bool = True,
    ) -> dict[str, Any]:
        """Trả lời câu hỏi bằng Hybrid GraphRAG.

        Args:
            question: Câu hỏi.
            session_id: Id phiên hội thoại.
            top_k: Số chunk đưa vào context.
            use_llm: Có gọi LLM hay không.
            use_graph: Có dùng kênh KG hay không (để đo ablation B−).

        Returns:
            Dict theo output contract của Phase 15.
        """
        started = time.time()
        retrieval = self.config.get("retrieval") or {}
        generation = self.config.get("generation") or {}

        # 1) Session + entity linking.
        session = self.session_store.get_or_create(session_id)
        linked = self.link_entities(question)
        entity_ids = [entity_id for _span, entity_id, _name in linked]
        has_new_entity = bool(entity_ids)

        # 2) Query rewriting (kế thừa chủ thề).
        rewritten = rewrite_question(
            question, session, has_new_entity=has_new_entity
        )
        if rewritten != question:
            logger.info("Query rewriting: %r → %r", question, rewritten)

        # 3) Phân loại ý định.
        intent: IntentResult = classify(rewritten, client=self.client)

        # 4) Truy xuất văn bản (CÙNG retriever với arm A).
        results = self.retriever.retrieve(rewritten, top_k=top_k)

        # 5) Context KG.
        graph = GraphContext()
        if use_graph:
            graph = self._build_graph(intent, linked, results, session, question)

        # 6) Fusion.
        fused = fuse(
            intent=intent,
            text_results=results,
            graph=graph,
            char_budget=int(retrieval.get("context_char_budget", 12000)),
        )

        if fused.is_empty():
            answer_text = NO_DATA_ANSWER
            status = "not_in_data"
            cited: list[int] = []
            faithfulness_ok: bool | None = None
            retries = 0
        elif not use_llm:
            answer_text = fused.to_text()
            status = "found"
            cited = []
            faithfulness_ok = None
            retries = 0
        else:
            answer_text, status, cited, faithfulness_ok, retries = self._generate(
                question=rewritten,
                fused=fused,
                generation=generation,
                history=self.session_store.history_text(session),
            )

        # 7) Ghi lượt vào session.
        subject_entity_id = ""
        subject_name = ""
        if linked:
            subject_entity_id = linked[0][1]
            subject_name = linked[0][2]
        elif session.last_subject_entity_id:
            subject_entity_id = session.last_subject_entity_id
            subject_name = session.last_subject_name
        self.session_store.record_turn(
            session,
            question=question,
            rewritten_question=rewritten,
            answer=answer_text,
            entities=entity_ids,
            subject_entity_id=subject_entity_id,
            subject_name=subject_name,
        )
        self.session_store.save(session)

        return {
            "status": status,
            "answer": answer_text,
            "citations": fused.citations,
            "context_used": [block["text"] for block in fused.text_blocks],
            "context_blocks": [
                {
                    "doc_id": block.get("doc_id"),
                    "title": block.get("title"),
                    "section": block.get("section"),
                    "section_path": block.get("section"),
                }
                for block in fused.text_blocks
            ],
            "kg_used": [block["text"] for block in fused.kg_blocks],
            "context_text": fused.to_text(),
            "intent": intent.to_dict(),
            "fusion_strategy": fused.strategy,
            "rewritten_question": rewritten,
            "session_id": session.session_id,
            "entities": [
                {"entity_id": eid, "name": name}
                for _span, eid, name in linked
            ],
            "graph": graph.to_dict(),
            "faithfulness_ok": faithfulness_ok,
            "retries": retries,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_graph(
        self,
        intent: IntentResult,
        linked: list[tuple[str, str, str]],
        results: list[Any],
        session: Any,
        question: str = "",
    ) -> GraphContext:
        """Dựng context KG: template theo ý định + mở rộng 1-hop.

        Args:
            intent: Kết quả phân loại ý định.
            linked: Entity đã link.
            results: Chunk đã truy xuất.
            session: Phiên hội thoại.
            question: Câu hỏi gốc (dùng cho truy vấn chuỗi quan hệ — D-120).

        Returns:
            `GraphContext` (có thể rỗng).
        """
        context = GraphContext()
        entity_id = ""
        if linked:
            entity_id = linked[0][1]
        elif session.last_subject_entity_id:
            entity_id = session.last_subject_entity_id

        # D-120: chuỗi quan hệ ("cha của cha X") — ưu tiên cao nhất vì 1-hop
        # **không** chứa mắt xích thứ hai ⇒ không có câu trả lời.
        if question:
            chain = self.graph_builder.fetch_chain(question, linked)
            if not chain.is_empty():
                context = chain
        if context.is_empty() and entity_id:
            template = self._template_for_intent(intent.intent)
            context = self.graph_builder.fetch(template, entity_id)

        # Mở rộng 1-hop từ entity của chunk (cơ chế "link sang quan hệ khác").
        chunk_entity_ids: list[str] = []
        for item in results:
            chunk_entity_ids.extend(item.chunk.entity_ids)
        if chunk_entity_ids:
            # D-123: câu hỏi `narrative` chỉ lấy quan hệ **bối cảnh** —
            # loại quan hệ sinh tử ("sinh tại"/"mất tại") vì chúng là nhiễu
            # cho câu hỏi tự sự (đo được: 27,4 cạnh nhiễu/câu khi dùng mọi
            # quan hệ ⇒ 0,0 khi chỉ dùng quan hệ bối cảnh).
            expansion_relations = (
                CONTEXT_RELATIONS
                if intent.intent == "narrative"
                else None
            )
            expansion = self.graph_builder.expand_from_entities(
                chunk_entity_ids,
                anchor_id=entity_id,
                relations=expansion_relations,
            )
            if not context.is_empty():
                known = {
                    (edge.get("source_id"), edge.get("relation"), edge.get("target_id"))
                    for edge in context.edges
                }
                for edge in expansion.edges:
                    key = (
                        edge.get("source_id"),
                        edge.get("relation"),
                        edge.get("target_id"),
                    )
                    if key in known:
                        continue
                    context.edges.append(edge)
                context.entities.extend(
                    node
                    for node in expansion.entities
                    if node["entity_id"]
                    not in {e["entity_id"] for e in context.entities}
                )
                context.source = f"{context.source}+chunk_expansion"
        return context

    @staticmethod
    def _template_for_intent(intent: str) -> str:
        """Chọn template Cypher theo ý định.

        Args:
            intent: Tên ý định.

        Returns:
            Tên template.
        """
        mapping = {
            # D-121: câu hỏi narrative cần **các bên liên quan** (người chỉ
            # huy, quân tham chiến, địa điểm) ⇒ truy vấn 2-hop quanh sự kiện.
            "narrative": "event_deep",
            "relational": "relational",
            "multi_hop": "one_hop",
            "count": "dynasty",
            "comparison": "one_hop",
            "no_data": "relational",
        }
        return mapping.get(intent, "relational")

    def _generate(
        self,
        *,
        question: str,
        fused: FusedContext,
        generation: dict[str, Any],
        history: str,
    ) -> tuple[str, str, list[int], bool | None, int]:
        """Sinh câu trả lời + kiểm tra faithfulness.

        Args:
            question: Câu hỏi (đã viết lại).
            fused: Context đã hợp nhất.
            generation: Cấu hình sinh.
            history: Lịch sử hội thoại.

        Returns:
            Tuple `(answer, status, citations, faithfulness_ok, retries)`.
        """
        prompt = self.prompt_template.format(
            context=fused.to_text(), question=question, no_data=NO_DATA_ANSWER
        )
        if fused.kg_blocks:
            prompt = prompt + HYBRID_SYSTEM_EXTRA
        if history:
            prompt = prompt.replace(
                "## CÂU HỎI",
                f"## LỊCH SỬ HỘI THOẠI\n{history}\n\n## CÂU HỎI",
            )

        max_retry = (
            int(generation.get("max_faithfulness_retry", 1))
            if generation.get("faithfulness_retry", True)
            else 0
        )
        retries = 0
        answer = ""
        cited: list[int] = []
        for attempt in range(max_retry + 1):
            call_prompt = prompt
            if attempt > 0:
                from src.qa.rag_answer import FAITHFULNESS_SUFFIX

                call_prompt = prompt + FAITHFULNESS_SUFFIX.format(no_data=NO_DATA_ANSWER)
            answer = (
                self.client.complete(
                    call_prompt,
                    temperature=float(generation.get("temperature", 0.0)),
                    max_tokens=int(generation.get("max_tokens", 900)),
                )
                or ""
            ).strip()
            cited = extract_citations(answer)
            # ⚠️ Phase 19 — câu trả lời **rỗng** cũng phải retry (xem giải
            # thích ở `src/qa/rag_answer.py`).
            if cited or is_no_data(answer) or not answer:
                break
            if attempt < max_retry:
                retries += 1
                logger.warning("Hybrid: thiếu trích dẫn [n] — retry %d", attempt + 1)

        # --- Phase 19 — retry khi nói "không có" **dù context có dữ liệu** --
        # Xem giải thích ở `src/qa/rag_answer.py` (cùng lý do, cùng cách sửa).
        max_nodata_retry = (
            int(generation.get("max_no_data_retry", 1))
            if generation.get("no_data_retry", True)
            else 0
        )
        for attempt in range(max_nodata_retry):
            # ⚠️ Phase 19 — sửa lỗi: LLM trả về **rỗng** cũng phải retry
            # (xem giải thích chi tiết ở `src/qa/rag_answer.py`).
            if answer and not is_no_data(answer):
                break
            if fused.is_empty():
                break
            retries += 1
            logger.warning(
                "Hybrid: nói 'không có' dù context có dữ liệu — retry ép trả lời %d/%d",
                attempt + 1, max_nodata_retry,
            )
            from src.qa.rag_answer import NO_DATA_RETRY_SUFFIX

            answer = (
                self.client.complete(
                    prompt + NO_DATA_RETRY_SUFFIX.format(no_data=NO_DATA_ANSWER),
                    temperature=float(generation.get("temperature", 0.0)),
                    max_tokens=int(generation.get("max_tokens", 900)),
                )
                or ""
            ).strip()
            cited = extract_citations(answer)

        status = "not_in_data" if is_no_data(answer) else "found"
        if not answer:
            # LLM trả về rỗng (lỗi hạ tầng / context quá ngắn) ⇒ coi như
            # **không có dữ liệu** thay vì để câu trả lời rỗng (D-118).
            logger.warning("Hybrid: LLM trả về câu trả lời rỗng — quy về not_in_data.")
            answer = NO_DATA_ANSWER
            status = "not_in_data"
        faithfulness_ok = bool(cited) or status == "not_in_data"
        return answer, status, cited, faithfulness_ok, retries


__all__ = ["HYBRID_SYSTEM_EXTRA", "HybridAnswerer"]

"""Endpoint `POST /api/ask/hybrid` — Hybrid GraphRAG (arm B, Phase 15).

Output contract:
```json
{"status":"found","answer":"...","citations":[...],
 "context_used":[...],"kg_used":[...],"intent":{"intent":"narrative",...},
 "fusion_strategy":"text_first","rewritten_question":"...",
 "session_id":"sess_...","entities":[...],"graph":{"nodes":[],"edges":[]},
 "faithfulness_ok":true,"retries":0,"elapsed_ms":2140}
```
`status` ∈ {`found`, `not_in_data`, `error`}.

Endpoint liên quan
-----------------
- `GET /api/session/{session_id}` — lấy lịch sử hội thoại.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.common.config import REPO_ROOT
from src.common.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["hybrid"])

#: File log câu hỏi hybrid.
LOG_PATH = REPO_ROOT / "logs" / "ask_hybrid.log"

#: Retriever + answerer dùng chung (lazy load 1 lần cho toàn process).
_ANSWERER: Any | None = None


def get_answerer() -> Any:
    """Lấy (và cache) `HybridAnswerer`.

    Returns:
        Đối tượng `HybridAnswerer`.
    """
    global _ANSWERER
    if _ANSWERER is None:
        from src.common.config import load_config
        from src.qa.hybrid import HybridAnswerer
        from src.qa.retriever import Retriever

        config = load_config(REPO_ROOT / "configs" / "retrieval.yaml")
        retriever = Retriever.load(REPO_ROOT / "configs" / "retrieval.yaml")
        _ANSWERER = HybridAnswerer(retriever, config=config)
    return _ANSWERER


class HybridAskRequest(BaseModel):
    """Body của `POST /api/ask/hybrid`.

    Attributes:
        question: Câu hỏi tiếng Việt.
        session_id: Id phiên hội thoại (None ⇒ tạo mới).
        top_k: Số chunk đưa vào context.
        use_graph: Tắt kênh KG để chạy ablation B−.
    """

    question: str = Field(..., min_length=1, max_length=500)
    session_id: str | None = Field(default=None, max_length=64)
    top_k: int | None = Field(default=None, ge=1, le=30)
    use_graph: bool = True


def _write_log(payload: dict[str, Any]) -> None:
    """Ghi log câu hỏi vào `logs/ask_hybrid.log`.

    Args:
        payload: Dict cần ghi.
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Không ghi được log: %s", exc)


@router.post("/ask/hybrid")
def post_ask_hybrid(request: HybridAskRequest) -> dict[str, Any]:
    """Trả lời câu hỏi bằng Hybrid GraphRAG (KG + RAG).

    Args:
        request: Body request.

    Returns:
        Dict theo output contract của Phase 15.
    """
    started = time.time()
    question = request.question.strip()
    try:
        answerer = get_answerer()
        result = answerer.answer(
            question,
            session_id=request.session_id,
            top_k=request.top_k,
            use_graph=request.use_graph,
        )
    except Exception as error:  # noqa: BLE001 - lỗi hạ tầng → trả error
        logger.exception("Lỗi khi trả lời Hybrid: %s", error)
        return {
            "status": "error",
            "answer": f"Lỗi hệ thống: {error}",
            "citations": [],
            "context_used": [],
            "kg_used": [],
            "intent": None,
            "fusion_strategy": "both",
            "rewritten_question": question,
            "session_id": request.session_id or "",
            "entities": [],
            "graph": {"nodes": [], "edges": []},
            "faithfulness_ok": None,
            "retries": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    _write_log(
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "question": question,
            "rewritten_question": result.get("rewritten_question"),
            "status": result.get("status"),
            "intent": (result.get("intent") or {}).get("intent"),
            "strategy": result.get("fusion_strategy"),
            "n_citations": len(result.get("citations") or []),
            "n_kg": len(result.get("kg_used") or []),
            "session_id": result.get("session_id"),
            "elapsed_ms": result.get("elapsed_ms"),
            "wall_ms": int((time.time() - started) * 1000),
        }
    )
    logger.info(
        "ask/hybrid | %s | intent=%s | %s | %d kg | %s ms",
        result.get("status"),
        (result.get("intent") or {}).get("intent"),
        question[:50],
        len(result.get("kg_used") or []),
        result.get("elapsed_ms"),
    )
    return result


@router.get("/session/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    """Lấy lịch sử hội thoại của một phiên.

    Args:
        session_id: Id phiên.

    Returns:
        Dict `{"session_id", "turns", "last_subject_*", "recent_entity_ids"}`.
    """
    from src.qa.conversation import SessionStore

    store = SessionStore()
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên.")
    return session.to_dict()

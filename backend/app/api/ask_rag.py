"""Endpoint `POST /api/ask/rag` — Vanilla RAG (arm A, Phase 14).

Output contract:
```json
{"status":"found","answer":"...","citations":[{"n":1,"chunk_id":"...",
 "title":"...","section":"...","source_url":"..."}],
 "context_used":[...],"context_chars":1234,"faithfulness_ok":true,
 "retries":0,"elapsed_ms":2140}
```
`status` ∈ {`found`, `not_in_data`, `error`}.

Vì sao có endpoint riêng (không dùng chung `/api/ask`)?
-----------------------------------------------------
`/api/ask` là kênh **Text-to-Cypher** (chỉ trả lời được câu quan hệ, giới hạn
18 quan hệ). `/api/ask/rag` là kênh **truy xuất văn bản** — trả lời được câu
tự sự ("diễn biến trận Bạch Đằng"). Hai arm so sánh trong Phase 16:
- **A** = `/api/ask/rag` (Vanilla RAG)
- **B** = `/api/ask/hybrid` (Phase 15 — KG + RAG)

Cả hai dùng **cùng** `Retriever` ⇒ so sánh công bằng.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.common.config import REPO_ROOT
from src.common.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["rag"])

#: File log câu hỏi RAG.
LOG_PATH = REPO_ROOT / "logs" / "ask_rag.log"

#: Retriever dùng chung (lazy load 1 lần cho toàn process).
_RETRIEVER: Any | None = None


def get_answerer() -> Any:
    """Lấy (và cache) `RagAnswerer`.

    Returns:
        Đối tượng `RagAnswerer`.
    """
    global _RETRIEVER
    from src.qa.rag_answer import RagAnswerer
    from src.qa.retriever import Retriever

    if _RETRIEVER is None:
        retriever = Retriever.load(REPO_ROOT / "configs" / "retrieval.yaml")
        _RETRIEVER = RagAnswerer(retriever)
    return _RETRIEVER


class RagAskRequest(BaseModel):
    """Body của `POST /api/ask/rag`.

    Attributes:
        question: Câu hỏi tiếng Việt.
        top_k: Số chunk đưa vào context (None ⇒ lấy từ cấu hình).
    """

    question: str = Field(..., min_length=1, max_length=500)
    top_k: int | None = Field(default=None, ge=1, le=30)


def _write_log(payload: dict[str, Any]) -> None:
    """Ghi log câu hỏi vào `logs/ask_rag.log`.

    Args:
        payload: Dict cần ghi.
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Không ghi được log: %s", exc)


@router.post("/ask/rag")
def post_ask_rag(request: RagAskRequest) -> dict[str, Any]:
    """Trả lời câu hỏi bằng Vanilla RAG (BM25 + dense + RRF).

    Args:
        request: Body request.

    Returns:
        Dict theo output contract của Phase 14.
    """
    started = time.time()
    question = request.question.strip()
    try:
        answerer = get_answerer()
        result = answerer.answer(question, top_k=request.top_k)
    except Exception as error:  # noqa: BLE001 - lỗi hạ tầng → trả error
        logger.exception("Lỗi khi trả lời RAG: %s", error)
        return {
            "status": "error",
            "answer": f"Lỗi hệ thống: {error}",
            "citations": [],
            "context_used": [],
            "context_chars": 0,
            "faithfulness_ok": None,
            "retries": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
        }

    _write_log(
        {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "question": question,
            "status": result.get("status"),
            "n_citations": len(result.get("citations") or []),
            "context_chars": result.get("context_chars"),
            "faithfulness_ok": result.get("faithfulness_ok"),
            "retries": result.get("retries"),
            "elapsed_ms": result.get("elapsed_ms"),
            "wall_ms": int((time.time() - started) * 1000),
        }
    )
    logger.info(
        "ask/rag | %s | %s | %d citations | %s ms",
        result.get("status"), question[:60],
        len(result.get("citations") or []), result.get("elapsed_ms"),
    )
    return result

"""Endpoint `POST /api/ask` — hỏi đáp Text-to-Cypher (Phase 11 — bước 7).

Output contract:
```json
{"status":"found","answer":"...","cypher":"...","entities":[...],
 "records":[...],"graph":{"nodes":[...],"edges":[...]},"retries":0,
 "elapsed_ms":2140}
```
`status` ∈ {`found`, `not_in_data`, `error`}.
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

from backend.app.services.text_to_cypher import ask as run_ask

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["ask"])

#: File log câu hỏi.
LOG_PATH = REPO_ROOT / "logs" / "ask.log"


class AskRequest(BaseModel):
    """Body của `POST /api/ask`.

    Attributes:
        question: Câu hỏi tiếng Việt.
    """

    question: str = Field(..., min_length=1, max_length=500)


def _write_log(payload: dict[str, Any]) -> None:
    """Ghi log câu hỏi vào `logs/ask.log`.

    Args:
        payload: Dict cần ghi.
    """
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("Không ghi được log: %s", exc)


@router.post("/ask")
def post_ask(request: AskRequest) -> dict[str, Any]:
    """Trả lời câu hỏi tiếng Việt bằng Text-to-Cypher.

    Args:
        request: Body request.

    Returns:
        Dict theo output contract của Phase 11.
    """
    started = time.time()
    question = request.question.strip()
    result = run_ask(question)
    payload = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question": question,
        "status": result.get("status"),
        "cypher": result.get("cypher"),
        "n_records": len(result.get("records") or []),
        "n_entities": len(result.get("entities") or []),
        "retries": result.get("retries"),
        "elapsed_ms": result.get("elapsed_ms"),
        "wall_ms": int((time.time() - started) * 1000),
    }
    _write_log(payload)
    logger.info(
        "ask | %s | %s | %d records | %s ms",
        payload["status"], question[:60], payload["n_records"],
        payload["elapsed_ms"],
    )
    return result

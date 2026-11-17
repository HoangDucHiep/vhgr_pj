"""Phase 15 — Bước 4: hội thoại nhiều lượt (session store + query rewriting).

Vấn đề giải quyết
------------------
Câu hỏi lượt 2 thường **không lặp lại** chủ thể lượt 1:
- *"Ông ấy mất năm nào?"* (sau lượt về Trần Hưng Đạo)
- *"Vị vua đó chỉ huy trận nào?"*
- *"Triều đó có bao nhiêu đời vua?"*

Cơ chế
-------
`SessionStore` giữ:
- `last_subject_entity_id` + `last_subject_name` — chủ thể lượt trước
- `recent_entity_ids[]` — các entity đã nhắc gần đây
- `turns[]` — lịch sử hội thoại (để đưa vào prompt)

**Query rewriting** (`rewrite_question`):
1. Câu mới **có** entity riêng → giữ nguyên, cập nhật chủ thề.
2. Câu mới **không** có entity nhưng có đại từ/từ chỉ từ → thay đại từ bằng
   `last_subject_name`.
3. Câu mới **không** có entity, không đại từ → nối `last_subject_name` vào
   đầu câu (kế thừa chủ thề).

Lưu ý (Phase 13)
-----------------
Alias `ông ấy` **đã bị chặn** trong entity linker (map nhầm sang George H. W.
Bush). Vì vậy bước 2 ở trên là cơ chế **thay thế** chứ không phải "entity
linking tìm được đại từ".

Lưu trữ
--------
`data/interim/sessions/<session_id>.json` — 1 file / session, ghi atomic.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.common.config import resolve_path
from src.common.logger import get_logger

logger = get_logger("src.qa.conversation")

#: Thư mục lưu session.
SESSION_DIR = Path("data/interim/sessions")

#: Số lượt giữ trong lịch sử (để đưa vào prompt).
MAX_TURNS_KEPT = 10

#: Số entity gần đây giữ lại.
MAX_RECENT_ENTITIES = 10

#: Các từ chỉ từ / đại từ cần thay thế (dạng không dấu).
PRONOUNS: frozenset[str] = frozenset({
    "ong ay", "ong ta", "ong no", "ong ky", "ong vua", "vi vua",
    "vua do", "vua ay", "nguoi do", "nguoi ay", "nguoi no", "nguoi vua",
    "vi do", "vi ay", "toan bo", "ca bo", "ca nhan", "phan lon",
    "trieu do", "trieu ay", "trieu dai do", "nha do", "nha ay",
    "tran do", "tran ay", "cuoc do", "cuoc ay", "su kien do",
    "nam do", "nam ay", "chuyen do", "chuyen ay", "viec do", "viec ay",
    "suc do", "suc ay", "diem do", "diem ay", "phien do", "phien ay",
    "thoi do", "thoi ay", "doi do", "doi ay", "noi do", "noi ay",
    "dia danh do", "dia danh ay", "nguoi do la", "cai do",
    "cuoc chien do", "cuoc chien ay", "tran chien do", "tran chien ay",
    "ba ay", "ba do", "co ay", "co do", "vi ay", "vi do",
})

#: Regex tìm đại từ trong câu — áp dụng trên chuỗi **đã bỏ dấu** (thường).
#:
#: Cách an toàn: bỏ dấu cả từ khoá lẫn câu hỏi rồi so khớp trên chuỗi
#: không dấu ⇒ tránh nhầm lẫn do dấu phụ (vốn là codepoint riêng).
_COMBINING_MARKS = r"[\u0300-\u036f]*"

#: Nguyên âm/ký tự tiếng Việt có thể mang dấu (dùng để nhận diện chữ cái).
_VN_BASE_LETTERS = set("abcdefghijklmnopqrstuvwxyz")

#: Chữ cái nào cần lớp ký tự riêng (`đ` không phải là `d` có dấu).
_VN_SPECIAL_CLASSES: dict[str, str] = {"d": "[dđ]"}


def _accent_insensitive_pattern(text: str) -> str:
    """Dựng regex không phân biệt dấu từ một chuỗi không dấu.

    Args:
        text: Chuỗi không dấu (chỉ chứa chữ cái + khoảng trắng).

    Returns:
        Chuỗi regex (áp dụng trên chuỗi đã bỏ dấu).
    """
    parts: list[str] = []
    for char in text:
        if char in _VN_SPECIAL_CLASSES:
            parts.append(_VN_SPECIAL_CLASSES[char])
        elif char in _VN_BASE_LETTERS:
            parts.append(re.escape(char))
        else:
            parts.append(re.escape(char))
    return r"\b" + "".join(parts) + r"\b"


#: Regex tìm đại từ (không phân biệt dấu **và** hoa thường).
PRONOUN_RE = re.compile(
    "|".join(
        _accent_insensitive_pattern(p)
        for p in sorted(PRONOUNS, key=len, reverse=True)
    ),
    re.IGNORECASE,
)


@dataclass
class Turn:
    """Một lượt hỏi trong hội thoại.

    Attributes:
        question: Câu hỏi gốc.
        rewritten_question: Câu hỏi sau khi viết lại.
        answer: Câu trả lời (rút gọn).
        entities: Entity đã link.
        subject_entity_id: Chủ thể của lượt.
        subject_name: Tên chủ thể.
        ts: Mốc thời gian.
    """

    question: str
    rewritten_question: str = ""
    answer: str = ""
    entities: list[str] = field(default_factory=list)
    subject_entity_id: str = ""
    subject_name: str = ""
    ts: float = 0.0


@dataclass
class Session:
    """Một phiên hội thoại.

    Attributes:
        session_id: Id phiên.
        turns: Lịch sử các lượt.
        last_subject_entity_id: Entity chủ thể gần nhất.
        last_subject_name: Tên chủ thể gần nhất.
        recent_entity_ids: Các entity đã nhắc gần đây.
        created_at: Thời điểm tạo.
        updated_at: Thời điểm cập nhật.
    """

    session_id: str
    turns: list[Turn] = field(default_factory=list)
    last_subject_entity_id: str = ""
    last_subject_name: str = ""
    recent_entity_ids: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict (serialize).

        Returns:
            Dict phiên.
        """
        return {
            "session_id": self.session_id,
            "turns": [asdict(turn) for turn in self.turns],
            "last_subject_entity_id": self.last_subject_entity_id,
            "last_subject_name": self.last_subject_name,
            "recent_entity_ids": list(self.recent_entity_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Dựng `Session` từ dict.

        Args:
            data: Dict phiên.

        Returns:
            `Session`.
        """
        return cls(
            session_id=str(data.get("session_id") or ""),
            turns=[Turn(**turn) for turn in (data.get("turns") or [])],
            last_subject_entity_id=str(data.get("last_subject_entity_id") or ""),
            last_subject_name=str(data.get("last_subject_name") or ""),
            recent_entity_ids=[str(e) for e in (data.get("recent_entity_ids") or [])],
            created_at=float(data.get("created_at") or 0.0),
            updated_at=float(data.get("updated_at") or 0.0),
        )


def _normalize(text: str) -> str:
    """Chuẩn hoá chuỗi để so khớp đại từ (bỏ dấu + hạ thường).

    Args:
        text: Chuỗi gốc.

    Returns:
        Chuỗi chuẩn hoá.
    """
    from src.qa.retriever import strip_accents

    return strip_accents(text or "")


def _nfd(text: str) -> str:
    """Chuẩn hoá NFD (tách dấu thành codepoint riêng).

    Args:
        text: Chuỗi gốc.

    Returns:
        Chuỗi NFD.
    """
    return unicodedata.normalize("NFD", text or "")


def _strip_with_map(text: str) -> tuple[str, list[int]]:
    """Bỏ dấu chuỗi + giữ bản đồ chỉ số về chuỗi gốc.

    Mỗi ký tự trong chuỗi kết quả ánh xạ về **chỉ số ký tự gốc** đầu tiên
    của nó. Nhờ vậy có thể tìm đại từ trên chuỗi không dấu rồi cắt trên chuỗi
    gốc (giữ nguyên dấu).

    Args:
        text: Chuỗi gốc.

    Returns:
        Tuple `(text_khong_dau, mapping)`.
    """
    out: list[str] = []
    mapping: list[int] = []
    for index, char in enumerate(text):
        decomposed = unicodedata.normalize("NFD", char)
        base = "".join(c for c in decomposed if not unicodedata.combining(c))
        base = base.replace("Đ", "D").replace("đ", "d")
        for piece in base:
            out.append(piece)
            mapping.append(index)
    return "".join(out), mapping


def has_pronoun(question: str) -> bool:
    """Kiểm tra câu hỏi có chứa đại từ / từ chỉ từ không.

    So khớp trên chuỗi **đã bỏ dấu** ⇒ "Ông ấy" khớp từ khoá "ong ay".

    Args:
        question: Câu hỏi.

    Returns:
        ``True`` nếu có đại từ.
    """
    stripped, _ = _strip_with_map(question or "")
    return bool(PRONOUN_RE.search(stripped))


def _replace_pronouns(text: str, replacement: str) -> str:
    """Thay đại từ trong câu bằng chuỗi thay thế (giữ nguyên dấu câu).

    Vì so khớp chạy trên chuỗi bỏ dấu nên việc thay thế phải cắt trên chuỗi
    gốc (dùng bản đồ chỉ số) ⇒ kết quả giữ nguyên dấu tiếng Việt.

    Args:
        text: Câu hỏi gốc.
        replacement: Chuỗi thay thế (tên chủ thể).

    Returns:
        Câu hỏi đã thay đại từ.
    """
    stripped, mapping = _strip_with_map(text or "")
    if not stripped:
        return text

    pieces: list[str] = []
    cursor = 0
    for match in PRONOUN_RE.finditer(stripped):
        if match.start() < cursor:
            continue
        # Vị trí trên chuỗi gốc.
        start = mapping[match.start()]
        end = mapping[min(match.end() - 1, len(mapping) - 1)] + 1
        pieces.append(text[cursor:start])
        pieces.append(replacement)
        cursor = end
    pieces.append(text[cursor:])
    return "".join(pieces)


def rewrite_question(
    question: str,
    session: Session | None,
    *,
    has_new_entity: bool = False,
) -> str:
    """Viết lại câu hỏi để kế thừa chủ thể từ lượt trước.

    Args:
        question: Câu hỏi gốc.
        session: Phiên hiện tại (None ⇒ không viết lại).
        has_new_entity: Câu hỏi đã có entity riêng.

    Returns:
        Câu hỏi sau khi viết lại.
    """
    text = (question or "").strip()
    if session is None or has_new_entity:
        return text
    subject = session.last_subject_name
    if not subject:
        return text

    if has_pronoun(text):
        # Thay đại từ bằng tên chủ thể.
        rewritten = _replace_pronouns(text, subject)
        # Viết lại chữ hoa đầu câu cho tự nhiên.
        if rewritten:
            rewritten = rewritten[0].upper() + rewritten[1:]
        return rewritten

    # Không có đại từ, không có entity ⇒ nối chủ thề vào đầu câu.
    normalized = _normalize(text)
    if _normalize(subject) in normalized:
        return text
    return f"{subject} {text}".strip()


class SessionStore:
    """Kho phiên hội thoại (lưu file JSON).

    Attributes:
        directory: Thư mục lưu session.
    """

    def __init__(self, directory: str | Path = SESSION_DIR) -> None:
        """Khởi tạo kho.

        Args:
            directory: Thư mục lưu session.
        """
        self.directory = resolve_path(directory)

    def path_for(self, session_id: str) -> Path:
        """Đường dẫn file của một session.

        Args:
            session_id: Id session.

        Returns:
            Đường dẫn file.
        """
        safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id) or "default"
        return self.directory / f"{safe}.json"

    def get(self, session_id: str) -> Session | None:
        """Nạp session từ đĩa.

        Args:
            session_id: Id session.

        Returns:
            `Session` hoặc ``None`` nếu chưa có.
        """
        path = self.path_for(session_id)
        if not path.exists():
            return None
        try:
            return Session.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError) as error:
            logger.warning("Không đọc được session %s: %s", session_id, error)
            return None

    def get_or_create(self, session_id: str | None = None) -> Session:
        """Nạp hoặc tạo session.

        Args:
            session_id: Id session (None ⇒ sinh mới).

        Returns:
            `Session`.
        """
        if session_id:
            existing = self.get(session_id)
            if existing is not None:
                return existing
            now = time.time()
            return Session(
                session_id=session_id,
                created_at=now,
                updated_at=now,
            )
        now = time.time()
        return Session(
            session_id=f"sess_{uuid.uuid4().hex[:12]}",
            created_at=now,
            updated_at=now,
        )

    def save(self, session: Session) -> Path:
        """Lưu session xuống đĩa (ghi atomic).

        Args:
            session: Session cần lưu.

        Returns:
            Đường dẫn file đã ghi.
        """
        path = self.path_for(session.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        session.updated_at = time.time()
        payload = json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent),
            prefix=path.name, suffix=".tmp", delete=False,
        ) as handle:
            handle.write(payload)
            temp_path = handle.name
        os.replace(temp_path, path)
        return path

    def record_turn(
        self,
        session: Session,
        *,
        question: str,
        rewritten_question: str,
        answer: str,
        entities: list[str],
        subject_entity_id: str = "",
        subject_name: str = "",
    ) -> Session:
        """Ghi một lượt vào session + cập nhật chủ thề.

        Args:
            session: Session hiện tại.
            question: Câu hỏi gốc.
            rewritten_question: Câu hỏi sau viết lại.
            answer: Câu trả lời (rút gọn).
            entities: Entity đã link.
            subject_entity_id: Entity chủ thề.
            subject_name: Tên chủ thề.

        Returns:
            Session đã cập nhật.
        """
        session.turns.append(
            Turn(
                question=question,
                rewritten_question=rewritten_question,
                answer=answer[:600],
                entities=list(entities),
                subject_entity_id=subject_entity_id,
                subject_name=subject_name,
                ts=time.time(),
            )
        )
        if len(session.turns) > MAX_TURNS_KEPT:
            session.turns = session.turns[-MAX_TURNS_KEPT:]
        if subject_entity_id:
            session.last_subject_entity_id = subject_entity_id
            session.last_subject_name = subject_name
        for entity_id in entities:
            if entity_id and entity_id not in session.recent_entity_ids:
                session.recent_entity_ids.append(entity_id)
        if len(session.recent_entity_ids) > MAX_RECENT_ENTITIES:
            session.recent_entity_ids = session.recent_entity_ids[-MAX_RECENT_ENTITIES:]
        return session

    def history_text(self, session: Session | None, *, max_turns: int = 3) -> str:
        """Dựng chuỗi lịch sử hội thoại cho prompt.

        Args:
            session: Session hiện tại.
            max_turns: Số lượt gần nhất.

        Returns:
            Chuỗi lịch sử (rỗng nếu không có).
        """
        if session is None or not session.turns:
            return ""
        lines: list[str] = []
        for turn in session.turns[-max_turns:]:
            lines.append(f"Người dùng: {turn.question}")
            lines.append(f"Trợ lý: {turn.answer[:300]}")
        return "\n".join(lines)


__all__ = [
    "MAX_RECENT_ENTITIES",
    "MAX_TURNS_KEPT",
    "PRONOUNS",
    "Session",
    "SessionStore",
    "Turn",
    "has_pronoun",
    "rewrite_question",
]

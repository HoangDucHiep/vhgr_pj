"""Liên kết entity trong câu hỏi tiếng Việt (Phase 11 — bước 3).

Nạp `data/knowledge_base/entities.jsonl` (Phase 9) → dict alias chuẩn hóa →
`entity_id`. Hỗ trợ **khớp dài nhất**: "Lê Thái Tổ" phải được ưu tiên hơn
"Lê" và "Lê Lợi" phải ưu tiên hơn "Lê".

Vì sao cần: LLM cần `entity_id` chuẩn hóa để sinh Cypher đúng; nếu đưu tên
tự do, LLM dễ bịa `entity_id` không tồn tại.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.common.config import REPO_ROOT
from src.common.logger import get_logger
from src.common.normalize import normalize_name, strip_accents

logger = get_logger(__name__)

#: Đường dẫn artifact entity (Phase 9).
ENTITIES_PATH = REPO_ROOT / "data" / "knowledge_base" / "entities.jsonl"

#: Từ chức năng tiếng Việt — KHÔNG được coi là entity (hay xuất hiện trong
#: câu hỏi và gây nhiễu: "sinh", "năm", "mất", "vua", "triều"…).
STOPWORD_ALIASES = {
    "sinh", "nam", "mat", "vua", "vua vi", "nguoi", "la", "la ai", "ai",
    "khi", "o", "thuoc", "trieu", "nha", "ten", "tuoi", "con", "bo",
    "me", "cha", "vo", "chong", "anh", "em", "co", "chau",
    "co", "gia", "ten", "hien", "nay", "kia", "luc", "roi", "da", "se",
    "va", "hoac", "nhung", "khong", "co", "gi", "the", "cua", "cho",
    "cau", "hien", "gia", "do", "nay", "mot", "hai", "ba", "bon",
    # Danh xưng / từ chức năng hay gặp trong câu hỏi lịch sử.
    "ong", "ba", "co", "chu", "dai", "thuong", "dai tuong", "dai vuong",
    "hoang de", "hoang doi", "biet", "anh", "truong", "vuong", "tong",
    "dien bien", "tran", "dien bien phu", "chi tiet", "chi tiet ve",
    "tranh", "anh hung", "su kien", "nguoi", "thoi", "giai doan",
    "ngoai", "trong", "ve", "cua", "mot", "hai", "the", "gioi",
}

#: Alias 1 từ trỏ tới nhiều entity ⇒ gần như chắc là danh xưng/đại từ
#: ("ông", "vua", "bà"…) chứ không phải tên riêng. Số ngưỡng: alias xuất
#: hiện ở ≥ 3 entity thì loại khỏi chỉ mục link câu hỏi.
AMBIGUOUS_ALIAS_MIN_ENTITIES = 3

#: Loại alias KHÔNG phải tên riêng — bề mặt danh xưng/đại từ gom từ văn bản.
#: Đo được: 23.190/50.820 alias thuộc nhóm này; chúng làm link sai câu hỏi
#: ("diễn biến" → "Điện Biên", "trận" → "Nhà Trần").
#: Loại alias **không phải tên riêng**. Đo được trên `entities.jsonl`:
#: `mention` 23.190 + `mention_nodiacritic` 19.248 là danh xưng/đại từ gom từ
#: văn bản ("ông", "vua", "trận", "đời"…) và gây nhiễu nặng cho câu hỏi.
#:
#: **KHÔNG** loại `other` (161 alias) — đó là tên riêng thật lấy từ redirect
#: Wikipedia ("Nguyễn Du", "Nguyễn Trãi", "Tây Đô"…).
NON_NAME_ALIAS_TYPES = {
    "mention",
    "mention_nodiacritic",
}

#: Từ viết thường được phép nằm trong span khớp (từ chức năng đi kèm tên
#: riêng): "ông Lê Lợi", "vua Lê Lợi"…
#:
#: **Cẩn thận:** không được thêm từ có thể trùng bề mặt với tên riêng sau khi
#: bỏ dấu — vd "chỉ" → "chi" trùng "Nguyễn Huệ Chi". Đây là nguyên nhân gốc
#: của lỗi link sai lúc demo (15/11/2026).
LOWERCASE_OK_WORDS = {
    "ong", "ba", "co", "anh", "em", "cha", "me", "vua", "chu", "hoang",
    "dai", "thuong", "vuong", "de", "dieu", "hau", "cong",
    "huyen", "quan", "gia", "trieu", "nha", "thanh",
}

#: **Bề mặt đại từ / danh xưng** — tuyệt đối KHÔNG được dùng để link câu hỏi.
#:
#: Vì sao (Phase 13, lỗi demo 16/11/2026): alias `"ông ấy"` trong KG trỏ tới
#: `ent_george_h_5df82ed5` (George H. W. Bush) vì coref gom bề mặt đại từ làm
#: tên entity. Người dùng hỏi *"Ông ấy mất năm nào?"* ⇒ hệ thống link nhầm
#: sang George H. W. Bush ⇒ trả lời sai hoàn toàn.
#:
#: Các bề mặt này **không** mang thông tin định danh ⇒ phải xử lý ở tầng hội
#: thoại (Phase 15 — `conversation.py` thay bằng `last_subject`), không phải
#: ở tầng entity linking.
PRONOUN_ALIASES = {
    "ong ay", "ong ta", "ong no", "ong ky", "ong vua", "vi vua",
    "vua do", "vua ay", "nguoi do", "nguoi ay", "nguoi no", "nguoi vua",
    "vi do", "vi ay", "toan bo", "ca bo", "ca nhan", "phan lon",
    "trieu do", "trieu ay", "trieu dai do", "nha do", "nha ay",
    "tran do", "tran ay", "cuoc do", "cuoc ay", "su kien do",
    "nam do", "nam ay", "chuyen do", "chuyen ay", "viec do", "viec ay",
    "suc do", "suc ay", "diem do", "diem ay", "phien do", "phien ay",
    "thoi do", "thoi ay", "doi do", "doi ay", "noi do", "noi ay",
    "dia danh do", "dia danh ay", "tieu biet", "sieu kien",
}


def _find_normalized(text: str, alias: str, from_index: int) -> tuple[int, int] | None:
    """Tìm vị trí của `alias` (đã bỏ dấu) trong `text` gốc.

    Args:
        text: Chuỗi gốc.
        alias: Chuỗi đã chuẩn hóa (bỏ dấu).
        from_index: Vị trí bắt đầu tìm.

    Returns:
        Tuple `(start, end)` trong `text`, hoặc ``None``.
    """
    target = strip_accents(text[from_index:]).casefold()
    needle = strip_accents(alias).casefold()
    index = target.find(needle)
    if index == -1:
        return None
    return from_index + index, from_index + index + len(needle)


class EntityLinker:
    """Tra cứu tên bề mặt → `entity_id` trong câu hỏi.

    Attributes:
        alias_to_ids: Map tên chuẩn hóa → list `entity_id`.
        name_of: Map `entity_id` → tên hiển thị.
    """

    def __init__(self, entities_path: Path | None = None) -> None:
        """Nạp entity và dựng chỉ mục alias.

        Args:
            entities_path: Đường dẫn `entities.jsonl` (mặc định artifact Phase 9).
        """
        self.alias_to_ids: dict[str, list[str]] = {}
        self.alias_display: dict[str, set[str]] = {}
        self.name_of: dict[str, str] = {}
        self.type_of: dict[str, str] = {}
        self.qid_of: dict[str, str] = {}
        path = entities_path or ENTITIES_PATH
        if not path.exists():
            logger.warning("Không tìm thấy %s — entity linker sẽ rỗng.", path)
            return
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entity = json.loads(line)
                entity_id = str(entity.get("entity_id") or "")
                name = str(entity.get("name") or "")
                if not entity_id or not name:
                    continue
                self.name_of[entity_id] = name
                self.type_of[entity_id] = str(entity.get("type") or "unknown")
                qid = str(entity.get("wikidata_qid") or "")
                if qid:
                    self.qid_of[entity_id] = qid

                # Chỉ dùng alias **tên riêng**. Bỏ qua alias loại `mention`
                # (bề mặt danh xưng/đại từ gom từ văn bản: "ông", "vua",
                # "trận", "đời"…). Đo được: 23.190/50.820 alias là `mention`,
                # và chúng gây nhiễu nặng cho câu hỏi.
                keys: set[str] = set()
                for alias in entity.get("aliases") or []:
                    alias_type = str(alias.get("type") or "")
                    if alias_type in NON_NAME_ALIAS_TYPES:
                        continue
                    alias_text = str(alias.get("alias") or "")
                    if alias_text:
                        keys.add(normalize_name(alias_text))
                        # Giữ alias **gốc** (có dấu) — cần cho lớp khớp chính
                        # xác (khớp giữ dấu), tránh false positive do bỏ dấu
                        # ("Nguyễn Huệ chỉ" ≈ "Nguyễn Huệ Chi").
                        self.alias_display.setdefault(normalize_name(alias_text), set()).add(
                            alias_text
                        )
                keys.add(str(entity.get("name_normalized") or normalize_name(name)))
                self.alias_display.setdefault(
                    str(entity.get("name_normalized") or normalize_name(name)), set()
                ).add(name)

                for key in keys:
                    if not key:
                        continue
                    # Bỏ alias quá ngắn (1–2 ký tự không dấu): "áo", "lê",
                    # "sinh"… khớp lung tung trong câu tiếng Việt.
                    if len(key.replace(" ", "")) < 3:
                        continue
                    if key in STOPWORD_ALIASES:
                        continue
                    # Entity loại `unknown` lấy tên từ **văn bản** (coref), nên
                    # tên có thể là bề mặt ngẫu nhiên ("Nguyễn Huệ Chi",
                    # "Trần Não") ⇒ loại khỏi chỉ mục link câu hỏi.
                    if (
                        self.type_of[entity_id] == "unknown"
                        and not self.qid_of.get(entity_id)
                    ):
                        continue
                    bucket = self.alias_to_ids.setdefault(key, [])
                    if entity_id not in bucket:
                        bucket.append(entity_id)

        # Loại alias mơ hồ (nhiều entity cùng tên) — đa số là danh xưng/đại
        # từ ("ông", "vua"…) được gom từ nhiều bài. Giữ lại nếu entity đó
        # **có QID** (tên riêng có thật) và alias dài ≥ 2 từ.
        qid_of = self._qid_by_entity(entities_path or path)
        ambiguous = 0
        for alias, ids in list(self.alias_to_ids.items()):
            if len(ids) < AMBIGUOUS_ALIAS_MIN_ENTITIES:
                continue
            if len(alias.split()) >= 2 and any(qid_of.get(i) for i in ids):
                continue
            del self.alias_to_ids[alias]
            ambiguous += 1

        # Alias **1 từ** không bao giờ dùng để link câu hỏi: trong tiếng Việt,
        # 1 từ gần như luôn là từ chức năng ("diễn", "trận", "đời", "bao"…)
        # chứ không phải tên riêng. Đo được: 14.748/23.190 alias `mention`
        # là 1 từ, và chúng gây nhiễu nặng cho câu hỏi.
        single_word = 0
        for alias in list(self.alias_to_ids):
            if len(alias.split()) < 2:
                del self.alias_to_ids[alias]
                single_word += 1

        # ---- Phase 13 — chặn alias viết **toàn chữ thường** & đại từ ----
        #
        # Nguyên nhân gốc lỗi demo (16/11/2026): lớp khớp giữ dấu **không** kiểm
        # tra chữ hoa ⇒ câu "Đổi mới đất nước" khớp entity "Đổi Mới"; câu
        # "Ông ấy mất năm nào" khớp entity "ông ấy" (George H. W. Bush).
        #
        # Cách sửa (3 bước):
        #   (a) Loại khỏi chỉ mục mọi alias mà **mọi** bề mặt gốc đều viết
        #       toàn chữ thường và ≥ 2 từ ("chiến thắng", "triều đại",
        #       "phong kiến"…) — đây là cụm từ thường, không phải tên riêng.
        #   (b) Loại alias là **đại từ/danh xưng** ("ông ấy", "vị vua đó"…).
        #   (c) Lớp khớp giữ dấu chỉ nhận span có **đúng** chữ hoa của bề mặt
        #       alias (xem `_case_pattern_ok`).
        lowercase_multi = 0
        pronoun = 0
        for alias in list(self.alias_to_ids):
            if alias in PRONOUN_ALIASES:
                del self.alias_to_ids[alias]
                self.alias_display.pop(alias, None)
                pronoun += 1
                continue
            displays = self.alias_display.get(alias) or set()
            if not displays:
                del self.alias_to_ids[alias]
                continue
            if all(display == display.lower() for display in displays):
                del self.alias_to_ids[alias]
                self.alias_display.pop(alias, None)
                lowercase_multi += 1

        logger.info(
            "Entity linker: %d alias → %d entity "
            "(loại %d alias mơ hồ, %d alias 1 từ, %d alias toàn-chữ-thường, "
            "%d alias đại từ)",
            len(self.alias_to_ids), len(self.name_of), ambiguous, single_word,
            lowercase_multi, pronoun,
        )

    @staticmethod
    def _qid_by_entity(path: Path) -> dict[str, str]:
        """Lấy map `entity_id` → `wikidata_qid`.

        Args:
            path: Đường dẫn `entities.jsonl`.

        Returns:
            Dict id → QID.
        """
        mapping: dict[str, str] = {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    entity = json.loads(line)
                    entity_id = str(entity.get("entity_id") or "")
                    qid = str(entity.get("wikidata_qid") or "")
                    if entity_id and qid:
                        mapping[entity_id] = qid
        except OSError:
            pass
        return mapping

    def link(self, text: str) -> list[tuple[str, str, str]]:
        """Tìm các entity trong `text`.

        **Hai lớp khớp** (lớp 1 ưu tiên tuyệt đối):

        1. **Khớp giữ dấu** — "Nguyễn Huệ" khớp "Nguyễn Huệ", "Trận Bạch Đằng"
           khớp "Trận Bạch Đằng". Chính xác, không sinh false positive.
        2. **Khớp bỏ dấu** (dự phòng) — "Le Loi" khớp "Lê Lợi". Vì bỏ dấu
           làm mất phân biệt ("Nguyễn Huệ **chỉ**" ≈ "Nguyễn Huệ **Chi**"),
           lớp 2 **bắt buộc** kiểm tra **chữ hoa**: mỗi từ trong span phải
           viết hoa đúng như tên riêng, hoặc là từ chức năng đã biết.

        Khớp **dài nhất trước**: duyệt alias theo độ dài giảm dần, mỗi span
        đã khớp thì không khớp lại (tránh "Lê Thái Tổ" bị khớp "Lê").

        Args:
            text: Câu hỏi tiếng Việt.

        Returns:
            Danh sách `(span, entity_id, canonical_name)`.
        """
        if not text.strip():
            return []
        results = self._match(text, keep_accents=True)
        if results:
            return results
        return self._match(text, keep_accents=False)

    def _match(
        self, text: str, keep_accents: bool,
    ) -> list[tuple[str, str, str]]:
        """Khớp entity trong text theo một lớp.

        Lớp giữ dấu (``keep_accents=True``) dùng **khớp đúng chữ hoa**
        (case-sensitive) trên chính `text` gốc — xem `_case_pattern_ok`.
        Lớp bỏ dấu (``keep_accents=False``) là lớp dự phòng, dùng
        `_capitalization_ok`.

        Args:
            text: Câu hỏi tiếng Việt.
            keep_accents: ``True`` = khớp giữ dấu; ``False`` = bỏ dấu.

        Returns:
            Danh sách `(span, entity_id, canonical_name)`.
        """
        if not text.strip():
            return []
        if keep_accents:
            # Lớp 1: khớp **case-sensitive** trên text gốc.
            haystack = text
        else:
            haystack = strip_accents(text).casefold()
        if not haystack.strip():
            return []
        aliases = sorted(self.alias_to_ids, key=len, reverse=True)
        taken: list[tuple[int, int]] = []
        results: list[tuple[int, str, str, str]] = []
        for alias in aliases:
            if keep_accents:
                needles = self.alias_display.get(alias) or set()
                if not needles:
                    continue
            else:
                needles = {alias}
            for raw_alias in needles:
                needle = (
                    raw_alias if keep_accents else alias.casefold()
                )
                start = haystack.find(needle)
                while start != -1:
                    end = start + len(needle)
                    # Yêu cầu ranh giới từ: ký tự trước/sau không phải chữ cái.
                    before_ok = start == 0 or not haystack[start - 1].isalnum()
                    after_ok = end >= len(haystack) or not haystack[end].isalnum()
                    if (
                        before_ok
                        and after_ok
                        and not any(start < e and s < end for s, e in taken)
                    ):
                        # Lớp giữ dấu: span phải viết **đúng** chữ hoa của bề
                        # mặt alias — nếu không, "Đổi mới đất nước" sẽ khớp
                        # "Đổi Mới" (lỗi demo 16/11/2026).
                        # Lớp bỏ dấu: kiểm tra chữ hoa tổng quát — nếu không,
                        # "Nguyễn Huệ chỉ" khớp "Nguyễn Huệ Chi".
                        ok = (
                            self._case_pattern_ok(text, start, end, raw_alias)
                            if keep_accents
                            else self._capitalization_ok(text, start, end)
                        )
                        if ok:
                            entity_id = self.alias_to_ids[alias][0]
                            taken.append((start, end))
                            results.append((
                                start,
                                text[start:end],
                                entity_id,
                                self.name_of.get(entity_id, alias),
                            ))
                    start = haystack.find(needle, start + 1)
        results.sort(key=lambda item: item[0])
        return [(span, entity_id, canonical) for _, span, entity_id, canonical in results]

    @staticmethod
    def _case_pattern_ok(
        text: str, start: int, end: int, raw_alias: str,
    ) -> bool:
        """Kiểm tra span có **đúng** chữ hoa của bề mặt alias hay không.

        Quy tắc (Phase 13): mỗi từ trong span phải viết hoa **đúng như** từ
        tương ứng trong `raw_alias` — hoặc là từ chức năng được phép viết
        thường (`LOWERCASE_OK_WORDS`: "ông", "vua"…).

        Vì sao cần (lỗi demo 16/11/2026):
        - "Đổi mới đất nước" khớp "Đổi Mới" ⇒ sai;
        - "Ông ấy mất năm nào" khớp "ông ấy" (George H. W. Bush) ⇒ sai;
        - nhưng "Trần Hưng Đạo", "triều Lê", "Trần Nhân Tông" phải **vẫn** khớp.

        Args:
            text: Câu hỏi gốc.
            start: Vị trí bắt đầu span.
            end: Vị trí kết thúc span.
            raw_alias: Bề mặt gốc của alias (có dấu, đúng chữ hoa).

        Returns:
            ``True`` nếu span nhất quán với bề mặt alias.
        """
        span_words = text[start:end].split()
        alias_words = raw_alias.split()
        if not span_words or len(span_words) != len(alias_words):
            return False
        for span_word, alias_word in zip(span_words, alias_words):
            if not span_word[:1].isalpha():
                continue
            if span_word[0].isupper() == alias_word[:1].isupper():
                continue
            # Khác nhau ở chữ hoa: chỉ chấp nhận nếu span word là từ chức năng
            # được phép viết thường ("ông Lê Lợi", "vua Lê Lợi").
            if not span_word[0].isupper() and normalize_name(span_word) in LOWERCASE_OK_WORDS:
                continue
            return False
        return True

    def _capitalization_ok(self, text: str, start: int, end: int) -> bool:
        """Kiểm tra span có viết **hoa** như tên riêng hay không.

        Quy tắc: từ đầu tiên của span phải viết hoa (tên riêng tiếng Việt luôn
        viết hoa chữ đầu); các từ sau được phép viết thường nếu là từ chức
        năng đã biết ("ông", "vua") — nếu không thì span là một cụm từ thường
        ("chỉ huy", "trận nào") chứ không phải tên riêng.

        Args:
            text: Câu hỏi gốc.
            start: Vị trí bắt đầu span.
            end: Vị trí kết thúc span.

        Returns:
            ``True`` nếu span nhất quán với tên riêng.
        """
        span = text[start:end]
        words = span.split()
        if not words:
            return False
        first = words[0]
        if first[:1].isalpha() and not first[0].isupper():
            return False
        for word in words[1:]:
            if not word[:1].isalpha():
                continue
            if word[0].isupper():
                continue
            if normalize_name(word) in LOWERCASE_OK_WORDS:
                continue
            return False
        return True

    def annotate(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        """Thay span trong câu hỏi bằng `entity_id`.

        Args:
            text: Câu hỏi gốc.

        Returns:
            Tuple `(câu_đã_annotate, danh_sách_entity_tìm_thấy)`.
        """
        linked = self.link(text)
        if not linked:
            return text, []
        pieces: list[str] = []
        cursor = 0
        entities: list[dict[str, Any]] = []
        for alias, entity_id, canonical in linked:
            position = _find_normalized(text, alias, cursor)
            if position is None:
                continue
            start, end = position
            pieces.append(text[cursor:start])
            pieces.append(f"[{entity_id}]")
            entities.append({
                "surface": text[start:end],
                "entity_id": entity_id,
                "canonical_name": canonical,
            })
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces), entities


@lru_cache(maxsize=1)
def get_linker() -> EntityLinker:
    """Trả về `EntityLinker` dùng chung (lazy).

    Returns:
        Đối tượng linker.
    """
    return EntityLinker()

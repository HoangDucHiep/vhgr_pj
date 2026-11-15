"""Giải quyết đồng tham chiếu (coreference) theo quy tắc — Phase 6 (C1, C2).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 6,
`docs/01-requirements-chuc-nang.md` §C1–C2.

Cách chạy
---------
```bash
python -m src.coref.resolve_coref --config configs/default.yaml
```

Output contract
---------------
`data/interim/coref_resolved.jsonl` — 1 dòng/câu, UTF-8, không BOM:

```json
{"sentence_id":"s80_0_3","doc_id":"doc_80","text":"...",
 "mentions":[{"start":0,"end":10,"text":"Lê Lợi","label":"PERSON",
              "mention_id":"ms80_0_3_0","canonical_id":"ent_le_loi_c820c0c9",
              "resolved_by":"explicit","score":0.95,"source":"ner"}]}
```

- Offset là **ch� số ký tự Python** `[start, end)` trong `text` của câu →
  bắt buộc `text[start:end] == mention["text"]`.
- `canonical_id` hoặc `ent_<slug>_<hash8>` hoặc `null`.
- `resolved_by` ∈ `RESOLUTION_METHODS` (`src/common/schemas.py`).

Thứ tự ưu tiên
--------------
=============  ======================================================  ==================
Bước          Quy tắc                                                  `resolved_by`
=============  ======================================================  ==================
R0             Named mention có tên → tra gazetteer                    `explicit`
R0'            Named mention chưa có trong gazetteer → mint entity_id  `explicit`
R2             Danh xưng đi kèm tên riêng → entity của tên đó          `coref_honorific`
R1             Đại từ → entity PERSON cuối cùng trước đó trong đoạn    `coref_pronoun`
R3             Đoạn không có PERSON → chủ thể bài                       `article_subject`
R4             Lọc theo giới tính của đại từ                           (lọc bên trong)
R5             Đoạn có >= N PERSON, không rõ ứng viên → bỏ qua          `ambiguous`
R6             Đoạn có đúng 1 PERSON → gắng entity đó (fallback)        `coref_pronoun`
=============  ======================================================  ==================

Ghi chú thiết kế
----------------
- **Streaming**: đọc `documents.jsonl` và `ner_predictions.jsonl` theo luồng,
  xử lý từng `doc_id` một lượt → RAM giữ ở mức vài MB (không nạp 214 MB
  `documents.jsonl` và 58 MB `ner_predictions.jsonl` vào RAM cùng lúc).
- **Chia đoạn**: `sentence_id` có dạng `s<page_id>_<para_idx>_<sent_idx>` →
  `para_idx` là chỉ số đoạn, dùng để áp dụng R1/R5/R6 trong **phạm vi đoạn**.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from src.common.config import load_config, resolve_path
from src.common.ids import make_mention_id
from src.common.logger import get_logger
from src.coref.article_subject import ArticleSubject, build_article_subjects
from src.coref.gazetteer import (
    Gazetteer,
    build_gazetteer,
    iter_jsonl,
    resolve_explicit,
)
from src.coref.honorifics import (
    Honorific,
    detect_pronouns,
    load_honorifics,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class Mention:
    """Một mention sau khi resolve.

    Attributes:
        start: Offset ký tự bắt đầu (bao gồm).
        end: Offset ký tự kết thúc (không bao gồm).
        text: Văn bản span.
        label: Nhãn NER.
        mention_id: ID mention (`m<sentence_id>_<idx>`).
        canonical_id: `entity_id` sau khi resolve, hoặc `None`.
        resolved_by: Cách resolve.
        score: Độ tin cậy (0–1).
        source: Nguồn span — ``ner``, ``pronoun`` hoặc ``pronoun_name``.
        gender: Giới tính của đại từ (``male``/``female``/``None``).
        name_span: Cặp offset ``(start, end)`` của tên riêng đi kèm danh xưng.
        name_text: Văn bản tên riêng đi kèm danh xưng.
        doc_id: ID tài liệu chứa mention (dùng cho R3 — chủ thể bài).
        sentence_id: ID câu chứa mention (dùng cho R1a — ưu tiên cùng câu).
    """

    start: int
    end: int
    text: str
    label: str
    mention_id: str
    canonical_id: str | None = None
    resolved_by: str = "unlinked"
    score: float = 0.0
    source: str = "ner"
    gender: str | None = None
    name_span: tuple[int, int] | None = None
    name_text: str | None = None
    is_plural: bool = False
    doc_id: str = ""
    sentence_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict để ghi JSONL.

        Returns:
            Dict theo thứ tự trường ổn định.
        """
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "label": self.label,
            "mention_id": self.mention_id,
            "canonical_id": self.canonical_id,
            "resolved_by": self.resolved_by,
            "score": self.score,
            "source": self.source,
        }


def _para_index(sentence_id: str) -> int:
    """Trích chỉ số đoạn từ `sentence_id`.

    Args:
        sentence_id: ID câu (`s<page_id>_<para_idx>_<sent_idx>`).

    Returns:
        Chỉ số đoạn; `-1` nếu không parse được.
    """
    parts = sentence_id.split("_")
    if len(parts) < 3:
        return -1
    try:
        return int(parts[1])
    except ValueError:
        return -1


class CorefResolver:
    """Bộ giải quyết coreference theo quy tắc R0–R6.

    Attributes:
        gazetteer: Gazetteer tra cứu entity.
        honorifics: Từ điển danh xưng.
        article_subjects: Map `doc_id` → `ArticleSubject`.
        config: Cấu hình mục `coref` trong `configs/default.yaml`.
    """

    def __init__(
        self,
        gazetteer: Gazetteer,
        honorifics: Sequence[Honorific],
        article_subjects: dict[str, ArticleSubject],
        config: dict[str, Any],
    ) -> None:
        """Khởi tạo bộ giải quyết.

        Args:
            gazetteer: Gazetteer tra cứu entity.
            honorifics: Từ điển danh xưng.
            article_subjects: Map `doc_id` → chủ thể bài.
            config: Cấu hình mục `coref`.
        """
        self.gazetteer = gazetteer
        self.honorifics = list(honorifics)
        self.article_subjects = article_subjects
        self.config = config

        self.detect_pronouns = bool(config.get("detect_pronouns", True))
        self.mint_entity_ids = bool(config.get("mint_entity_ids", True))
        self.score_gazetteer = float(config.get("score_gazetteer", 0.95))
        self.score_mint = float(config.get("score_mint", 0.75))
        self.score_coref_pronoun = float(config.get("score_coref_pronoun", 0.70))
        self.score_coref_honorific = float(config.get("score_coref_honorific", 0.70))
        self.score_article_subject = float(config.get("score_article_subject", 0.60))
        self.max_persons = int(config.get("max_persons_in_paragraph", 3))
        self.gender_strict = bool(config.get("gender_strict", True))

        # Thứ tự ưu tiên các quy tắc giải quyết đại từ (D-052).
        # Đây là **tham số cấu hình** (không hard-code) để ablation đo được
        # trên đúng đường dẫn code thật, thay vì monkeypatch (xem
        # `scripts/coref_ablation.py`).
        self.rule_order: list[str] = [
            str(name).lower()
            for name in config.get(
                "pronoun_rule_order",
                ["r1a", "r1b", "r3", "r5", "r6"],
            )
        ]
        # R1b chỉ được dùng khi đoạn có **đúng 1** người được nhắc tới.
        # Lý do (đo 15/11/2026): khi đoạn nhắc nhiều người, ứng viên "người
        # cuối cùng trước đại từ" gần như luôn **sai** — đó là người được
        # nhắc trong ngữ cảnh ("đời Thiệu Trị", "Sau khi Thành Thái lên
        # ngôi"), không phải chủ thể đang được nói đến. Với đoạn chỉ có 1
        # người thì ứng viên là duy nhất → không mơ hồ.
        self.r1b_unique_only = bool(config.get("r1b_unique_only", False))
        # R3 chỉ dùng khi đoạn **không** có `PERSON` nào — đúng điều kiện
        # trong `docs/09` §Phase 6 ("Dùng khi đoạn không có entity `PERSON`
        # nào"). Mặc định `False` để giữ hành vi đo được tốt hơn; bật `True`
        # để ablation đo biến thể bám sát đặc tả.
        self.r3_requires_no_person = bool(config.get("r3_requires_no_person", False))

        # Cache giới tính: `entity_id` → `male`/`female`.
        self._gender_cache: dict[str, str] = {}
        for entry in gazetteer.entries.values():
            if entry.gender:
                self._gender_cache.setdefault(entry.entity_id, entry.gender)

    # -- tiện ích ---------------------------------------------------------

    def _gender_matches(self, gender: str, entity_id: str | None) -> bool:
        """Kiểm tra giới tính của entity có khớp với đại từ không.

        Args:
            gender: Giới tính của đại từ (``male``/``female``).
            entity_id: ID entity ứng viên.

        Returns:
            ``True`` nếu khớp **hoặc** không có thông tin để phán đoán
            (thiếu dữ liệu ≠ sai giới tính).
        """
        actual = self._gender_cache.get(entity_id or "")
        if actual is None:
            return True
        return actual == gender

    # -- quy tắc -----------------------------------------------------------

    def _resolve_named(self, mention: Mention) -> tuple[str | None, str, float]:
        """R0 / R0' — named mention có tên.

        Args:
            mention: Mention cần resolve.

        Returns:
            Bộ ba ``(canonical_id, resolved_by, score)``.
        """
        entity_id, resolved_by, score = resolve_explicit(
            self.gazetteer,
            mention.text,
            mention.label,
            mint=self.mint_entity_ids,
        )
        if entity_id is None:
            return None, "unlinked", 0.0
        if score >= 0.9:
            return entity_id, resolved_by, self.score_gazetteer
        return entity_id, resolved_by, self.score_mint

    def _resolve_pronoun(
        self,
        mention: Mention,
        candidates_pool: Sequence[Mention],
    ) -> tuple[str | None, str, float]:
        """Giải quyết đại từ theo thứ tự quy tắc đã cấu hình (R1a/R1b/R3/R5/R6).

        Thứ tự ưu tiên **đo được** trên bộ gold 100 câu (xem
        `docs/10-nhat-ky/phase-06.md` §4.2 và `scripts/coref_ablation.py`):

        1. **R1a** — ứng viên `PERSON` trong **cùng câu**, đứng trước đại từ.
           Ưu tiên cao nhất: trong tiếng Việt, đại từ thường tham chiếu thực
           thể vừa được nhắc trong câu.
        2. **R1b** — ứng viên `PERSON` ở câu **trước** trong cùng đoạn.
        3. **R3** — chủ thể bài (khi đoạn không có `PERSON` nào phù hợp).
        4. **R5/R6** — bỏ qua hoặc nới theo "Lùi" của `docs/09` §Phase 6.

        Args:
            mention: Mention danh xưng/đại từ.
            candidates_pool: Các mention đã resolve (đoạn trước **+** cùng câu).

        Returns:
            Bộ ba ``(canonical_id, resolved_by, score)``.
        """
        gender = mention.gender
        total_persons = [m for m in candidates_pool if m.label == "PERSON"]
        # Ứng viên: PERSON đã resolve, đứng **trước** vị trí đại từ.
        candidates = [
            item
            for item in total_persons
            if item.canonical_id and item.end <= mention.start
        ]

        # --- R5-pre: đại từ số nhiều → không tham chiếu thực thể đơn lẻ ---
        # "các ông dành cho tôi...", "các vua Trần", "các triều vua Trần".
        # Gắn một entity đơn lẻ ở đây là **sai** → để `null` (D-048).
        # Đây là **chốt an toàn**, không phải quy tắc cạnh tranh → luôn chạy
        # trước mọi quy tắc khác, bất kể thứ tự cấu hình.
        if mention.is_plural:
            return None, "ambiguous", 0.0

        # --- R4: lọc theo giới tính ---
        if self.gender_strict and gender:
            filtered = [
                item
                for item in candidates
                if self._gender_matches(gender, item.canonical_id)
            ]
            # Nếu lọc hết → không có ứng viên hợp lệ (an toàn hơn gắn sai).
            candidates = filtered

        # Tách ứng viên theo phạm vi câu để R1a và R1b độc lập với nhau.
        same_sentence = [
            item for item in candidates if item.sentence_id == mention.sentence_id
        ]
        prev_sentence = [
            item for item in candidates if item.sentence_id != mention.sentence_id
        ]

        # Dispatch theo thứ tự cấu hình (`pronoun_rule_order`).
        for rule in self.rule_order:
            result = self._apply_pronoun_rule(
                rule,
                mention=mention,
                gender=gender,
                total_persons=total_persons,
                candidates=candidates,
                same_sentence=same_sentence,
                prev_sentence=prev_sentence,
            )
            if result is not None:
                return result

        return None, "ambiguous", 0.0

    def _apply_pronoun_rule(
        self,
        rule: str,
        *,
        mention: Mention,
        gender: str | None,
        total_persons: Sequence[Mention],
        candidates: Sequence[Mention],
        same_sentence: Sequence[Mention],
        prev_sentence: Sequence[Mention],
    ) -> tuple[str | None, str, float] | None:
        """Áp dụng 1 quy tắc giải quyết đại từ.

        Args:
            rule: Tên quy tắc (``r1a``, ``r1b``, ``r3``, ``r5``, ``r6``).
            mention: Mention danh xưng/đại từ.
            gender: Giới tính của đại từ.
            total_persons: Toàn bộ `PERSON` trong pool.
            candidates: Ứng viên đã lọc giới tính, đứng trước đại từ.
            same_sentence: Ứng viên trong cùng câu.
            prev_sentence: Ứng viên ở câu trước.

        Returns:
            Bộ ba ``(canonical_id, resolved_by, score)`` nếu quy tắc có kết
            quả; ``None`` nếu quy tắc không áp dụng (để thử quy tắc kế tiếp).
        """
        if rule == "r1a":
            # Ứng viên trong CÙNG câu, đứng gần đại từ nhất.
            if same_sentence:
                return (
                    same_sentence[-1].canonical_id,
                    "coref_pronoun",
                    self.score_coref_pronoun,
                )
            return None

        if rule == "r1b":
            # Ứng viên ở câu TRƯỚC trong cùng đoạn.
            if prev_sentence:
                # Ràng buộc (D-053): chỉ dùng R1b khi đoạn có **đúng 1**
                # người — khi đoạn nhắc nhiều người, "người cuối cùng trước
                # đại từ" gần như luôn là người *được nhắc*, không phải
                # chủ thể *đang được nói đến*.
                if self.r1b_unique_only and len(total_persons) != 1:
                    return None
                return (
                    prev_sentence[-1].canonical_id,
                    "coref_pronoun",
                    self.score_coref_pronoun,
                )
            return None

        if rule == "r3":
            # Chủ thể bài là một **tiên đề mạnh** (prior): trong bài viết về một
            # nhân vật, "ông"/"vua" thường chỉ chính nhân vật đó.
            #
            # Ràng buộc (đo 15/11/2026): chỉ dùng chủ thể bài cho đại từ nhãn
            # `PERSON` khi chủ thể là **người**. Nếu không, "ông" trong bài về
            # sự kiện/triều đại sẽ bị gắn nhầm sang entity sự kiện
            # (vd `ent_dao_chinh_viet_nam_cong_hoa_1963`).
            #
            # Ràng buộc (theo `docs/09` §Phase 6): R3 dùng khi đoạn **không**
            # có entity `PERSON` nào. Biến thể bám sát đặc tả bật cờ này.
            if self.r3_requires_no_person and total_persons:
                return None
            subject = self.article_subjects.get(mention.doc_id)
            if subject is not None and subject.type == "person":
                # Ràng buộc R4: chủ thể bài phải khớp giới tính đại từ.
                # (Đo 15/11/2026: bài viết về nữ nghệ sĩ mà đại từ là "ông"
                # → không được gắn chủ thể nữ.)
                if gender and self.gender_strict and not self._gender_matches(
                    gender, subject.entity_id
                ):
                    return None, "ambiguous", 0.0
                return subject.entity_id, "article_subject", self.score_article_subject
            if subject is not None and subject.type in ("event", "dynasty"):
                # Chủ thể không phải người → chỉ dùng cho danh xưng không phải
                # PERSON (vd "vụ", "nhà") — với nhãn PERSON thì bỏ qua.
                if mention.label != "PERSON":
                    return (
                        subject.entity_id,
                        "article_subject",
                        self.score_article_subject,
                    )
            return None

        if rule == "r5":
            # Quá nhiều PERSON trong đoạn → không rõ ứng viên.
            if len(total_persons) >= self.max_persons:
                return None, "ambiguous", 0.0
            return None

        if rule == "r6":
            # Đoạn có đúng 1 PERSON → gắng entity đó (fallback).
            # (Đây là "Lùi" của docs/09 §Phase 6: siết danh xưng + thêm R6.)
            #
            # Ràng buộc R4 (đo 15/11/2026): R6 cũng phải **tôn trọng giới tính**.
            # Trước khi sửa, R6 gắn entity nữ cho đại từ "ông" và ngược lại —
            # vi phạm Gate G4. Nay: nếu entity duy nhất trong đoạn **mâu thuẫn**
            # giới tính đại từ → không gắng (an toàn hơn gắn sai).
            if len(total_persons) == 1 and total_persons[0].canonical_id:
                only = total_persons[0]
                if not (gender and self.gender_strict):
                    return (
                        only.canonical_id,
                        "coref_pronoun",
                        self.score_coref_pronoun,
                    )
                if self._gender_matches(gender, only.canonical_id):
                    return (
                        only.canonical_id,
                        "coref_pronoun",
                        self.score_coref_pronoun,
                    )
                return None, "ambiguous", 0.0
            return None

        # Quy tắc lạ → bỏ qua (không đoán).
        return None

    # -- API chính ---------------------------------------------------------

    def resolve_sentence(
        self,
        record: dict[str, Any],
        paragraph: Sequence[Mention],
    ) -> list[Mention]:
        """Giải quyết toàn bộ mention của một câu.

        Args:
            record: Record từ `ner_predictions.jsonl`.
            paragraph: Mention của các câu trước trong cùng đoạn (đã resolve).

        Returns:
            Danh sách mention đã resolve, sắp theo `start` tăng dần.
        """
        text = str(record.get("text") or "")
        sentence_id = str(record.get("sentence_id") or "")
        doc_id = str(record.get("doc_id") or "")

        mentions: list[Mention] = []
        known_spans: list[tuple[int, int]] = []

        # --- 1. Span NER ---
        for entity in record.get("entities") or []:
            start = int(entity.get("start", 0))
            end = int(entity.get("end", 0))
            mentions.append(
                Mention(
                    start=start,
                    end=end,
                    text=str(entity.get("text") or ""),
                    label=str(entity.get("label") or ""),
                    mention_id="",
                    doc_id=doc_id,
                    sentence_id=sentence_id,
                    source="ner",
                )
            )
            known_spans.append((start, end))

        # --- 2. Span danh xưng/đại từ (Phase 6 dò thêm) ---
        pronoun_mentions: list[Mention] = []
        if self.detect_pronouns:
            for pronoun in detect_pronouns(text, known_spans, self.honorifics):
                pronoun_mentions.append(
                    Mention(
                        start=pronoun.start,
                        end=pronoun.end,
                        text=pronoun.text,
                        label=pronoun.label,
                        mention_id="",
                        doc_id=doc_id,
                        sentence_id=sentence_id,
                        source="pronoun",
                        gender=pronoun.gender,
                        name_span=(
                            (pronoun.name_start, pronoun.name_end)
                            if pronoun.name_start is not None
                            and pronoun.name_end is not None
                            else None
                        ),
                        name_text=pronoun.name_text,
                        is_plural=pronoun.is_plural,
                    )
                )

        # --- 3. Gộp & sắp theo offset, loại trùng lặp ---
        all_mentions: list[Mention] = sorted(
            mentions + pronoun_mentions,
            key=lambda item: (item.start, item.end),
        )
        # Loại span danh xưng trùng với span NER (đã xử lý ở `detect_pronouns`).
        deduped: list[Mention] = []
        for mention in all_mentions:
            if mention.source == "pronoun" and any(
                mention.start < end and start < mention.end
                for start, end in known_spans
            ):
                continue
            deduped.append(mention)
        all_mentions = deduped

        for index, mention in enumerate(all_mentions):
            mention.mention_id = make_mention_id(sentence_id, index)

        # --- 4. Resolve named trước (R0/R0') ---
        for mention in all_mentions:
            if mention.source != "ner":
                continue
            mention.canonical_id, mention.resolved_by, mention.score = (
                self._resolve_named(mention)
            )

        # --- 5. Resolve danh xưng/đại từ (R2 → R1 → R3 → R5 → R6) ---
        # Ứng viên = mention của đoạn (câu trước) **+** mention named đã
        # resolve trong chính câu này (để R1a hoạt động — xem D-048).
        pool = list(paragraph)
        for other in all_mentions:
            if other.source == "ner" and other.canonical_id:
                pool.append(other)

        for mention in all_mentions:
            if mention.source != "pronoun":
                continue

            # R2 — danh xưng đi kèm tên riêng → entity của tên đó.
            if mention.name_span and mention.name_text:
                name_start, name_end = mention.name_span
                target = next(
                    (
                        other
                        for other in all_mentions
                        if other.source == "ner"
                        and other.start == name_start
                        and other.end == name_end
                        and other.canonical_id
                    ),
                    None,
                )
                if target is None:
                    # Tên riêng chưa có trong span NER → mint theo nhãn PERSON.
                    target_id, _, _ = resolve_explicit(
                        self.gazetteer,
                        mention.name_text,
                        "PERSON",
                        mint=self.mint_entity_ids,
                    )
                else:
                    target_id = target.canonical_id
                if target_id:
                    mention.canonical_id = target_id
                    mention.resolved_by = "coref_honorific"
                    mention.score = self.score_coref_honorific
                    continue

            mention.canonical_id, mention.resolved_by, mention.score = (
                self._resolve_pronoun(mention, pool)
            )

        return all_mentions


def _group_by_paragraph(
    records: Iterable[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    """Nhóm các record câu theo chỉ số đoạn.

    Args:
        records: Các record câu của một bài.

    Returns:
        Map `para_idx` → danh sách record (theo thứ tự `sent_idx`).
    """
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_para_index(str(record.get("sentence_id") or ""))].append(record)
    for para_idx in grouped:
        grouped[para_idx].sort(
            key=lambda item: int(str(item.get("sentence_id") or "0").split("_")[-1] or 0)
        )
    return grouped


def resolve_document(
    resolver: CorefResolver,
    records: Sequence[dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Giải quyết coreference cho toàn bộ câu của một bài.

    Args:
        resolver: Bộ giải quyết.
        records: Các record câu của bài (theo thứ tự file).

    Yields:
        Record kết quả (1 record/câu) theo Output contract.
    """
    grouped = _group_by_paragraph(records)
    for para_idx in sorted(grouped):
        paragraph: list[Mention] = []
        for record in grouped[para_idx]:
            mentions = resolver.resolve_sentence(record, paragraph)
            paragraph.extend(mentions)
            yield {
                "sentence_id": str(record.get("sentence_id") or ""),
                "doc_id": str(record.get("doc_id") or ""),
                "text": str(record.get("text") or ""),
                "mentions": [mention.to_dict() for mention in mentions],
            }


def _iter_doc_blocks(
    path: str | Path,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    """Đọc `ner_predictions.jsonl` theo luồng, gom theo `doc_id`.

    File được sắp theo `doc_id` liên tục (đo: 186.960 dòng / 2.441 doc,
    0 doc lặp lại) nên chỉ cần giữ 1 doc tại a time.

    Args:
        path: Đường dẫn file.

    Yields:
        Cặp ``(doc_id, records)``.
    """
    current_doc: str | None = None
    block: list[dict[str, Any]] = []
    for record in iter_jsonl(path):
        doc_id = str(record.get("doc_id") or "")
        if current_doc is None:
            current_doc = doc_id
        if doc_id != current_doc:
            yield current_doc, block
            current_doc = doc_id
            block = []
        block.append(record)
    if current_doc is not None:
        yield current_doc, block


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Giải quyết coreference theo quy tắc (Phase 6)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--input", default=None, help="Đường dẫn NER predictions")
    parser.add_argument("--documents", default=None, help="Đường dẫn documents.jsonl")
    parser.add_argument("--out", default=None, help="Đường dẫn output JSONL")
    parser.add_argument(
        "--article-subject-out",
        default=None,
        help="Đường dẫn output article subjects",
    )
    parser.add_argument("--limit-docs", type=int, default=0, help="Giới hạn số bài")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    coref_config = dict(config.get("coref", {}))

    predictions_path = resolve_path(
        args.input
        or coref_config.get("predictions_path", "data/interim/ner_predictions.jsonl")
    )
    documents_path = resolve_path(
        args.documents
        or coref_config.get("documents_path", "data/interim/documents.jsonl")
    )
    infobox_path = resolve_path(
        coref_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl")
    )
    qid_types_path = resolve_path(
        coref_config.get("qid_types_path", "data/interim/qid_types.json")
    )
    output_path = resolve_path(
        args.out or coref_config.get("output_path", "data/interim/coref_resolved.jsonl")
    )
    subject_output_path = resolve_path(
        args.article_subject_out
        or coref_config.get("article_subject_path", "data/interim/article_subjects.jsonl")
    )
    honorifics_path = resolve_path(
        coref_config.get("honorifics_path", "configs/honorifics.yaml")
    )

    gazetteer = build_gazetteer(infobox_path, documents_path)
    honorifics = load_honorifics(honorifics_path)
    subjects = build_article_subjects(
        documents_path,
        qid_types_path,
        known_entity_ids=gazetteer.by_qid,
        type_map_path=resolve_path("configs/wikidata_type_map.yaml"),
    )
    subject_map = {subject.doc_id: subject for subject in subjects}

    # Ghi artifact chủ thể bài (P4 — file riêng, không phá output contract).
    subject_output_path.parent.mkdir(parents=True, exist_ok=True)
    with subject_output_path.open("w", encoding="utf-8") as handle:
        for subject in subjects:
            handle.write(json.dumps(subject.to_dict(), ensure_ascii=False) + "\n")
    logger.info("Đã ghi %d chủ thể bài → %s", len(subjects), subject_output_path)

    resolver = CorefResolver(gazetteer, honorifics, subject_map, coref_config)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    n_sentences = 0
    n_mentions = 0
    n_resolved = 0
    n_docs = 0

    with output_path.open("w", encoding="utf-8") as handle:
        for doc_id, records in _iter_doc_blocks(predictions_path):
            n_docs += 1
            for result in resolve_document(resolver, records):
                mentions = result["mentions"]
                n_sentences += 1
                n_mentions += len(mentions)
                n_resolved += sum(1 for m in mentions if m["canonical_id"])
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            if n_docs % 200 == 0:
                logger.info(
                    "Đã xử lý %d bài · %d câu · %d mention · %d resolve",
                    n_docs,
                    n_sentences,
                    n_mentions,
                    n_resolved,
                )
            if args.limit_docs and n_docs >= args.limit_docs:
                break

    rate = n_resolved / n_mentions if n_mentions else 0.0
    logger.info(
        "Hoàn tất: %d bài · %d câu · %d mention · %d resolve (%.2f%%) → %s",
        n_docs,
        n_sentences,
        n_mentions,
        n_resolved,
        rate * 100,
        output_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

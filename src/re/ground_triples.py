"""Grounding triple vào câu corpus để sinh mẫu POSITIVE (Phase 7).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 7.

Ba nguồn nhãn
--------------
1. **Wikidata** (`wikidata_pairs.jsonl`) — distant supervision thuần.
2. **Infobox** (`infobox_triples.jsonl`) — triple Phase 3, ``method="infobox"``.
3. **Lead** (`lead_triples.jsonl`) — triple fallback Phase 3, ``method="rule"``.

Vì sao cần cả ba (D-056)
------------------------
Đo thật trên corpus 15/11/2026:

===========================  ==========  ==============
Nguồn nhãn                   POSITIVE    Số quan hệ
===========================  ==========  ==============
Wikidata (13 property)          12.197            10
Infobox + lead                  3.383            16
**Hợp nhất (unique)**          **15.580**        **17**
===========================  ==========  ==============

Wikidata thuần **không** đạt Gate ≥ 10.000 nếu grounding chặt (chỉ 4.834
mẫu / 9 quan hệ khi khớp `entity_id`; 12.197 / 10 quan hệ khi cho phép khớp
theo tên). Infobox bổ sung các quan hệ mà Wikidata không có (`ke_vi`,
`thuoc_trieu_dai`, `chi_huy_tran`, `dong_doi_tai`, `lap_ra`, `dien_ra_tai`).

Cách grounding
--------------
Với mỗi triple ``(subject, relation, object)``:

- **Khớp theo `entity_id`**: câu phải chứa mention resolve về đúng
  `entity_id` của subject **và** object. Đây là đường chính xác nhất.
- **Khớp theo tên**: khi object không có `entity_id` trong corpus (ví dụ đối
  tượng Wikidata chưa từng xuất hiện), dùng nhãn tiếng Việt của object
  (từ `wikidata_pairs.object_label`) làm viết tắt bằng `normalize_name`.
- **Quan hệ năm** (`sinh_nam`/`mat_nam`): object là ``year_<năm>`` — câu
  phải chứa chủ thể **và** chuỗi năm tương ứng.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from src.common.config import load_default_config, resolve_path
from src.common.ids import make_entity_id, make_year_id
from src.common.logger import get_logger
from src.common.normalize import normalize_name
from src.re.wikidata_relations import RelationMap, load_relation_map

logger = get_logger(__name__)

#: Regex nhận diện năm trong câu (3–4 chữ số).
_YEAR_RE = re.compile(r"(?<!\d)(\d{3,4})(?!\d)")


def iter_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc JSONL theo luồng.

    Args:
        path: Đường dẫn file JSONL.

    Yields:
        Từng record dict.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(path: str | Path, records: list[dict[str, Any]]) -> None:
    """Ghi danh sách record ra JSONL (UTF-8, không BOM).

    Args:
        path: Đường dẫn output.
        records: Danh sách record.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class CorpusIndex:
    """Chỉ mục corpus cho grounding.

    Attributes:
        sentence_text: Map ``sentence_id`` → nội dung câu.
        sentence_mentions: Map ``sentence_id`` → map ``entity_id`` → tập tên
            mention đã chuẩn hoá.
        sentence_normalized: Map ``sentence_id`` → câu đã bỏ dấu.
        sentence_mention_names: Map ``sentence_id`` → tập tên mention đã
            chuẩn hoá (không gắn với entity cụ thể).
        entity_sentences: Map ``entity_id`` → tập ``sentence_id``.
        sentence_spans: Map ``sentence_id`` → map ``entity_id`` → tật tên
            span ``(start, end, text_có_dấu)`` của mention resolve về entity
            đó trong câu.
    """

    def __init__(self) -> None:
        """Khởi tạo chỉ mục rỗng."""
        self.sentence_text: dict[str, str] = {}
        self.sentence_mentions: dict[str, dict[str, set[str]]] = {}
        self.sentence_normalized: dict[str, str] = {}
        self.sentence_mention_names: dict[str, set[str]] = defaultdict(set)
        self.entity_sentences: dict[str, set[str]] = defaultdict(set)
        self.sentence_spans: dict[str, dict[str, set[tuple[int, int, str]]]] = {}

    def add_sentence(self, record: dict[str, Any]) -> None:
        """Thêm một câu vào chỉ mục.

        Args:
            record: Record từ `coref_resolved.jsonl`.
        """
        sentence_id = str(record.get("sentence_id") or "")
        if not sentence_id:
            return
        text = str(record.get("text") or "")
        self.sentence_text[sentence_id] = text
        self.sentence_normalized[sentence_id] = normalize_name(text)
        mentions: dict[str, set[str]] = {}
        spans: dict[str, set[tuple[int, int, str]]] = {}
        for mention in record.get("mentions") or []:
            canonical = mention.get("canonical_id")
            mention_text = mention.get("text")
            if not mention_text:
                continue
            normalized = normalize_name(str(mention_text))
            if not normalized:
                continue
            self.sentence_mention_names[sentence_id].add(normalized)
            if canonical:
                entity_id = str(canonical)
                mentions.setdefault(entity_id, set()).add(normalized)
                self.entity_sentences[entity_id].add(sentence_id)
                span = self._mention_span(mention, text)
                if span is not None:
                    spans.setdefault(entity_id, set()).add(span)
        self.sentence_mentions[sentence_id] = mentions
        self.sentence_spans[sentence_id] = spans

    @staticmethod
    def _mention_span(
        mention: dict[str, Any],
        text: str,
    ) -> tuple[int, int, str] | None:
        """Trích span ``(start, end, text)`` của một mention.

        Offset luôn là **chỉ số ký tự Python** trong `text` và phải thỏa
        ``text[start:end] == span_text`` (xem `.cursor/rules/data-contracts.mdc`).

        Args:
            mention: Record mention.
            text: Nội dung câu.

        Returns:
            Bộ ba ``(start, end, text)`` hoặc ``None`` nếu không xác định được.
        """
        start = mention.get("start")
        end = mention.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            return None
        if start < 0 or end > len(text) or end <= start:
            return None
        return (start, end, text[start:end])

    def spans_of(self, sentence_id: str, entity_id: str) -> set[tuple[int, int, str]]:
        """Các span của entity trong câu.

        Args:
            sentence_id: ID câu.
            entity_id: ID thực thể.

        Returns:
            Tập ``(start, end, text)``.
        """
        return self.sentence_spans.get(sentence_id, {}).get(entity_id, set())

    def find_name_span(
        self,
        sentence_id: str,
        normalized_name: str,
    ) -> tuple[int, int, str] | None:
        """Tìm span đầu tiên của một tên đã chuẩn hoá trong câu.

        Dùng cho đường grounding theo **tên**: object Wikidata chưa có
        `entity_id` trong corpus, nên phải định vị tên trong câu bằng cách
        quét text đã bỏ dấu — độ dài chuỗi đã bỏ dấu bằng chuỗi gốc nên
        offset ký tự vẫn khớp.

        Args:
            sentence_id: ID câu.
            normalized_name: Tên đã bỏ dấu, lowercase.

        Returns:
            Bộ ba ``(start, end, text_có_dấu)`` hoặc ``None``.
        """
        if not normalized_name:
            return None
        haystack = self.sentence_normalized.get(sentence_id, "")
        position = haystack.find(normalized_name)
        if position < 0:
            return None
        original = self.sentence_text.get(sentence_id, "")
        # Chuỗi đã bỏ dấu giữ nguyên độ dài chuỗi gốc (`strip_accents` chỉ
        # thay ký tự, không xoá) → offset chuyển trực tiếp.
        span_text = original[position : position + len(normalized_name)]
        return (position, position + len(normalized_name), span_text)

    def sentences_of(self, entity_id: str) -> set[str]:
        """Các câu có chứa entity.

        Args:
            entity_id: ID thực thể.

        Returns:
            Tập ``sentence_id``.
        """
        return self.entity_sentences.get(entity_id, set())

    def has_name(self, sentence_id: str, normalized_name: str) -> bool:
        """Câu có chứa tên đã chuẩn hoá không.

        Args:
            sentence_id: ID câu.
            normalized_name: Tên đã bỏ dấu, lowercase.

        Returns:
            ``True`` nếu tên xuất hiện trong câu (mention hoặc text thô).
        """
        if normalized_name in self.sentence_mention_names.get(sentence_id, set()):
            return True
        return normalized_name in self.sentence_normalized.get(sentence_id, "")

    def years_in(self, sentence_id: str) -> set[int]:
        """Các năm xuất hiện trong câu.

        Args:
            sentence_id: ID câu.

        Returns:
            Tật năm.
        """
        found: set[int] = set()
        for match in _YEAR_RE.finditer(self.sentence_text.get(sentence_id, "")):
            found.add(int(match.group(1)))
        return found

    def find_year_span(
        self,
        sentence_id: str,
        year: int,
    ) -> tuple[int, int, str] | None:
        """Tìm span của một năm trong câu.

        Dùng cho quan hệ năm (`sinh_nam`/`mat_nam`) — object là
        ``year_<năm>`` nên cần định vị chuỗi năm trong câu bằng chứng.

        Args:
            sentence_id: ID câu.
            year: Năm cần tìm.

        Returns:
            Bộ ba ``(start, end, text)`` hoặc ``None``.
        """
        for match in _YEAR_RE.finditer(self.sentence_text.get(sentence_id, "")):
            if int(match.group(1)) == year:
                return (match.start(), match.end(), match.group(0))
        return None


def build_corpus_index(coref_path: str | Path) -> CorpusIndex:
    """Dựng chỉ mục corpus từ `coref_resolved.jsonl`.

    Args:
        coref_path: Đường dẫn artifact Phase 6.

    Returns:
        `CorpusIndex` đã đầy đủ.
    """
    index = CorpusIndex()
    count = 0
    for record in iter_jsonl(coref_path):
        index.add_sentence(record)
        count += 1
    logger.info(
        "Corpus: %d câu, %d entity có mention",
        count,
        len(index.entity_sentences),
    )
    return index


def load_entity_names(
    infobox_entities_path: str | Path,
) -> tuple[dict[str, str], dict[str, str]]:
    """Nạp tên và loại của entity từ `infobox_entities.jsonl`.

    Args:
        infobox_entities_path: Đường dẫn artifact Phase 3.

    Returns:
        Tuple ``(entity_id → tên đã chuẩn hoá, entity_id → loại node)``.
    """
    names: dict[str, str] = {}
    types: dict[str, str] = {}
    for entity in iter_jsonl(infobox_entities_path):
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id:
            continue
        names[entity_id] = normalize_name(str(entity.get("name") or ""))
        types[entity_id] = str(entity.get("type") or "")
    return names, types


def load_wikidata_labels(
    pairs_path: str | Path,
) -> dict[str, set[str]]:
    """Nạp nhãn (tên) của object Wikidata từ `wikidata_pairs.jsonl`.

    Cặp Wikidata lưu ``object_qid``; để grounding theo tên cần tên tiếng Việt
    của object. Artifact ghi kèm ``object_label`` (danh sách tên đã bỏ dấu).

    Args:
        pairs_path: Đường dẫn artifact Phase 7.

    Returns:
        Map ``object_qid`` → tập tên đã chuẩn hoá.
    """
    labels: dict[str, set[str]] = defaultdict(set)
    for record in iter_jsonl(pairs_path):
        qid = str(record.get("object_qid") or "")
        if not qid:
            continue
        for label in record.get("object_labels") or []:
            normalized = normalize_name(str(label))
            if normalized:
                labels[qid].add(normalized)
    return labels


def load_wikidata_display_labels(
    pairs_path: str | Path,
) -> dict[str, dict[str, str]]:
    """Nạp tên **hiển thị** (có dấu) của object Wikidata.

    `data-contracts.mdc` quy định tên hiển thị phải giữ dấu; `object_labels`
    trong artifact lưu tên có dấu, còn `load_wikidata_labels` trả bản đã
    chuẩn hoá để tra cứu. Hàm này giữ **cả hai** để tra cứu và hiển thị
    cùng lúc.

    Args:
        pairs_path: Đường dẫn artifact Phase 7.

    Returns:
        Map ``QID`` → map ``tên đã chuẩn hoá`` → ``tên có dấu``.
    """
    display: dict[str, dict[str, str]] = defaultdict(dict)
    for record in iter_jsonl(pairs_path):
        qid = str(record.get("object_qid") or "")
        if not qid:
            continue
        for label in record.get("object_labels") or []:
            normalized = normalize_name(str(label))
            if normalized:
                display[qid][normalized] = str(label)
    return dict(display)


def load_entity_display_names(
    infobox_entities_path: str | Path,
) -> dict[str, str]:
    """Nạp **tên hiển thị** (có dấu) của entity.

    `data-contracts.mdc` quy định: `name_normalized` chỉ dùng để tra cứu,
    **không** dùng làm tên hiển thị. Vì vậy artifact RE phải giữ tên có
    dấu.

    Args:
        infobox_entities_path: Đường dẫn artifact Phase 3.

    Returns:
        Map ``entity_id`` → tên có dấu.
    """
    display: dict[str, str] = {}
    for entity in iter_jsonl(infobox_entities_path):
        entity_id = str(entity.get("entity_id") or "")
        if not entity_id:
            continue
        name = str(entity.get("name") or "")
        if name:
            display[entity_id] = name
    return display


def _span_for(
    index: CorpusIndex,
    sentence_id: str,
    entity_id: str,
    normalized_name: str,
) -> tuple[int | None, int | None, str]:
    """Định vị span hiển thị của một entity trong câu.

    Ưu tiên span của mention resolve về `entity_id`; nếu không có (đường
    grounding theo tên) thì quét text đã bỏ dấu để tìm tên.

    Args:
        index: Chỉ mục corpus.
        sentence_id: ID câu.
        entity_id: ID thực thể.
        normalized_name: Tên đã chuẩn hoá (fallback).

    Returns:
        Bộ ba ``(start, end, text_có_dấu)``; ``start``/`end`` là ``None``
        nếu không định vị được.
    """
    spans = index.spans_of(sentence_id, entity_id)
    if spans:
        start, end, text = min(spans)
        return start, end, text
    if normalized_name:
        found = index.find_name_span(sentence_id, normalized_name)
        if found is not None:
            start, end, text = found
            return start, end, text
    return None, None, ""


def _resolve_ends(
    index: CorpusIndex,
    subject_ids: list[str],
    subject_names: dict[str, str],
    object_ids: list[str],
    object_names: set[str],
) -> list[tuple[str, str, str]]:
    """Tìm các cặp (sentence_id, subject_id, object_id) có mặt cùng một câu.

    Đối tượng được khớp theo **hai đường**:
    1. ``entity_id`` — câu chứa mention resolve về đúng entity.
    2. **tên** — câu chứa tên đã chuẩn hoá của object (dùng khi object
       Wikidata chưa có mặt trong corpus). Khớp tên được đánh dấu bằng tiền tố
       ``name:`` để phân biệt với `entity_id`.

    Args:
        index: Chỉ mục corpus.
        subject_ids: Danh sách `entity_id` ứng viên của subject.
        subject_names: Map ``entity_id`` → tên đã chuẩn hoá của subject.
        object_ids: Danh sách `entity_id` ứng viên của object.
        object_names: Tập tên đã chuẩn hoá của object.

    Returns:
        Danh sách bộ ba ``(sentence_id, subject_entity_id, object_ref)``;
        ``object_ref`` là `entity_id` hoặc ``name:<tên đã chuẩn hoá>``.
    """
    scope: set[str] = set()
    for entity_id in subject_ids:
        scope |= index.sentences_of(entity_id)
    if not scope:
        return []

    triples: set[tuple[str, str, str]] = set()
    for sentence_id in scope:
        mention_map = index.sentence_mentions.get(sentence_id, {})

        present_subjects = [e for e in subject_ids if e in mention_map]
        if not present_subjects:
            # Fallback: subject có tên trong câu nhưng chưa resolve về entity.
            present_subjects = [
                e
                for e in subject_ids
                if subject_names.get(e) and index.has_name(sentence_id, subject_names[e])
            ]
        if not present_subjects:
            continue

        present_objects = [e for e in object_ids if e in mention_map]
        if not present_objects:
            for name in object_names:
                if index.has_name(sentence_id, name):
                    present_objects.append(f"name:{name}")
        if not present_objects:
            continue

        for subject in present_subjects:
            for obj in present_objects:
                triples.add((sentence_id, subject, obj))
    return sorted(triples)


def _mint_object(
    name: str,
    object_type: str,
    entity_types: dict[str, str],
    name_to_entity: dict[str, str] | None = None,
) -> str:
    """Sinh `entity_id` cho object khi chỉ biết tên.

    Args:
        name: Tên đã chuẩn hoá của object.
        object_type: Loại node dự kiến (từ mapping property).
        entity_types: Map ``entity_id`` → loại (dùng để suy ra loại khi có).
        name_to_entity: Map tên đã chuẩn hoá → `entity_id` đã biết trong
            corpus (nếu tên đã tồn tại thì dùng lại chính `entity_id` đó
            thay vì mint mới — tránh trùng entity).

    Returns:
        `entity_id` hợp lệ.
    """
    if name_to_entity and name in name_to_entity:
        return name_to_entity[name]
    resolved = ""
    if name_to_entity:
        resolved = entity_types.get(name_to_entity.get(name, ""), "")
    if not resolved:
        # Tên chưa có trong corpus → dùng loại dự kiến từ mapping property.
        resolved = object_type or "person"
    return make_entity_id(resolved, name)


def ground_wikidata_pairs(
    pairs: list[dict[str, Any]],
    index: CorpusIndex,
    relation_map: RelationMap,
    qid_to_entities: dict[str, list[str]],
    entity_names: dict[str, str],
    entity_types: dict[str, str],
    qid_labels: dict[str, set[str]],
    display_names: dict[str, str] | None = None,
    qid_display_labels: dict[str, dict[str, str]] | None = None,
    name_to_entity: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Grounding các cặp Wikidata vào câu corpus.

    Args:
        pairs: Danh sách cặp từ `wikidata_pairs.jsonl`.
        index: Chỉ mục corpus.
        relation_map: Bảng mapping property → quan hệ.
        qid_to_entities: Map ``QID`` → danh sách `entity_id` trong corpus.
        entity_names: Map ``entity_id`` → tên đã chuẩn hoá.
        entity_types: Map ``entity_id`` → loại node.
        qid_labels: Map ``QID`` → tập tên đã chuẩn hoá.
        display_names: Map ``entity_id`` → tên có dấu (hiển thị).
        qid_display_labels: Map ``QID`` → map tên chuẩn hoá → tên có dấu.
        name_to_entity: Map tên đã chuẩn hoá → `entity_id` đã biết.

    Returns:
        Danh sách mẫu POSITIVE.
    """
    display_names = display_names or {}
    qid_display_labels = qid_display_labels or {}
    name_to_entity = name_to_entity or {}
    samples: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for pair in pairs:
        subject_qid = str(pair.get("subject_qid") or "")
        object_qid = str(pair.get("object_qid") or "")
        prop = str(pair.get("property") or "")
        spec = relation_map.get(prop)
        if spec is None:
            continue

        subject_entities = qid_to_entities.get(subject_qid, [])
        if not subject_entities:
            continue
        subject_names = {
            entity_names[e] for e in subject_entities if entity_names.get(e)
        }
        subject_ids = list(subject_entities)

        if spec.is_year:
            year = _extract_year(object_qid)
            if year is None:
                continue
            year_id = make_year_id(year)
            for sentence_id in sorted(
                set().union(*(index.sentences_of(e) for e in subject_ids))
            ):
                if year not in index.years_in(sentence_id):
                    continue
                mention_map = index.sentence_mentions.get(sentence_id, {})
                present = [e for e in subject_ids if e in mention_map]
                if not present:
                    present = [
                        e
                        for e in subject_ids
                        if entity_names.get(e)
                        and index.has_name(sentence_id, entity_names[e])
                    ]
                year_span = index.find_year_span(sentence_id, year)
                for subject in present:
                    key = (sentence_id, subject, spec.relation, year_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    sub_start, sub_end, sub_text = _span_for(
                        index,
                        sentence_id,
                        subject,
                        entity_names.get(subject, ""),
                    )
                    samples.append(
                        _make_sample(
                            sentence_id=sentence_id,
                            subject=subject,
                            subject_mention=sub_text,
                            subject_name=display_names.get(
                                subject, entity_names.get(subject, "")
                            ),
                            subject_start=sub_start,
                            subject_end=sub_end,
                            relation=spec.relation,
                            obj=year_id,
                            obj_mention=str(year),
                            obj_name=str(year),
                            obj_start=year_span[0] if year_span else None,
                            obj_end=year_span[1] if year_span else None,
                            source="wikidata",
                            prop=prop,
                        )
                    )
            continue

        object_entities = qid_to_entities.get(object_qid, [])
        object_names = set(qid_labels.get(object_qid, set()))

        # Hướng: `inverse` đảo subject ↔ object.
        if spec.direction == "inverse":
            subject_entities = qid_to_entities.get(object_qid, [])
            subject_names = {
                entity_names[e] for e in subject_entities if entity_names.get(e)
            }
            object_entities = qid_to_entities.get(subject_qid, [])
            object_names = set(qid_labels.get(subject_qid, set()))
            if not subject_entities:
                continue

        ends = _resolve_ends(
            index,
            subject_entities,
            {e: entity_names.get(e, "") for e in subject_entities},
            object_entities,
            object_names,
        )
        for sentence_id, subject, obj in ends:
            if obj.startswith("name:"):
                obj_name = obj[5:]
                obj_entity = _mint_object(
                    obj_name, spec.object_type, entity_types, name_to_entity
                )
                obj_display = qid_display_labels.get(object_qid, {}).get(obj_name, "")
                obj_normalized = obj_name
            else:
                obj_entity = obj
                obj_normalized = entity_names.get(obj, "")
                obj_display = display_names.get(obj, obj_normalized)
            key = (sentence_id, subject, spec.relation, obj_entity)
            if key in seen:
                continue
            seen.add(key)
            sub_start, sub_end, sub_text = _span_for(
                index,
                sentence_id,
                subject,
                entity_names.get(subject, ""),
            )
            # Ưu tiên span của mention resolve về entity (có thể là từ thay
            # thế như "ông"); chỉ fallback sang quét tên khi entity không có
            # mention nào trong câu.
            if index.spans_of(sentence_id, obj_entity):
                obj_start, obj_end, obj_text = _span_for(
                    index, sentence_id, obj_entity, obj_normalized
                )
            else:
                found = index.find_name_span(sentence_id, obj_normalized)
                obj_start = found[0] if found else None
                obj_end = found[1] if found else None
                obj_text = found[2] if found else ""
            samples.append(
                _make_sample(
                    sentence_id=sentence_id,
                    subject=subject,
                    subject_mention=sub_text,
                    subject_name=display_names.get(
                        subject, entity_names.get(subject, "")
                    ),
                    subject_start=sub_start,
                    subject_end=sub_end,
                    relation=spec.relation,
                    obj=obj_entity,
                    obj_mention=obj_text,
                    obj_name=obj_display or obj_normalized,
                    obj_start=obj_start,
                    obj_end=obj_end,
                    source="wikidata",
                    prop=prop,
                )
            )
    return samples


def _extract_year(value: str) -> int | None:
    """Trích năm từ giá trị object Wikidata.

    Wikidata trả ngày ISO (``"1753-11-20T00:00:00Z"``) cho ``P569``/``P570``.

    Args:
        value: Giá trị object thô.

    Returns:
        Năm hoặc ``None``.
    """
    match = re.match(r"^[+-]?(\d{3,4})", value or "")
    if not match:
        return None
    year = int(match.group(1))
    if not 900 <= year <= 2026:
        return None
    return year


def _make_sample(
    *,
    sentence_id: str,
    subject: str,
    subject_mention: str,
    subject_name: str = "",
    subject_start: int | None = None,
    subject_end: int | None = None,
    relation: str,
    obj: str,
    obj_mention: str,
    obj_name: str = "",
    obj_start: int | None = None,
    obj_end: int | None = None,
    source: str,
    prop: str,
) -> dict[str, Any]:
    """Dựng một mẫu POSITIVE.

    `mention` là **dạng bề mặt trong câu** (phải thỏa ``text[start:end] ==
    mention``); `*_name` là tên chuẩn của entity trong KG (có thể khác, ví dụ
    coref gộp nhiều cách gọi về một entity).

    Args:
        sentence_id: ID câu bằng chứng.
        subject: `entity_id` chủ thể.
        subject_mention: Dạng bề mặt của chủ thể trong câu.
        subject_name: Tên chuẩn của chủ thể.
        subject_start: Offset ký tự đầu của span chủ thể.
        subject_end: Offset ký tự cuối (exclusive) của span chủ thể.
        relation: Tên quan hệ.
        obj: `entity_id` đối tượng.
        obj_mention: Dạng bề mặt của đối tượng trong câu.
        obj_name: Tên chuẩn của đối tượng.
        obj_start: Offset ký tự đầu của span đối tượng.
        obj_end: Offset ký tự cuối (exclusive) của span đối tượng.
        source: Nguồn nhãn (``wikidata``/``infobox``/``lead``).
        prop: Property Wikidata (rỗng với nguồn nội bộ).

    Returns:
        Record mẫu.
    """
    return {
        "sentence_id": sentence_id,
        "subject": subject,
        "subject_mention": subject_mention,
        "subject_name": subject_name,
        "subject_start": subject_start,
        "subject_end": subject_end,
        "relation": relation,
        "object": obj,
        "object_mention": obj_mention,
        "object_name": obj_name,
        "object_start": obj_start,
        "object_end": obj_end,
        "source": source,
        "property": prop,
    }


def ground_triples(
    triples_path: str | Path,
    index: CorpusIndex,
    entity_names: dict[str, str],
    *,
    source: str,
    display_names: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Grounding triple nội bộ (infobox/lead) vào câu corpus.

    Args:
        triples_path: Đường dẫn artifact triple.
        index: Chỉ mục corpus.
        entity_names: Map ``entity_id`` → tên đã chuẩn hoá.
        source: Nhãn nguồn (``infobox``/``lead``).
        display_names: Map ``entity_id`` → tên có dấu (hiển thị).

    Returns:
        Danh sách mẫu POSITIVE.
    """
    display_names = display_names or {}
    samples: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for triple in iter_jsonl(triples_path):
        subject = str(triple.get("subject") or "")
        obj = str(triple.get("object") or "")
        relation = str(triple.get("relation") or "")
        if not subject or not obj or not relation:
            continue
        subject_name = entity_names.get(subject, "")
        object_name = entity_names.get(obj, "")
        subject_display = display_names.get(subject, subject_name)
        object_display = display_names.get(obj, object_name)

        if relation in ("sinh_nam", "mat_nam"):
            year_text = obj.split("_")[-1]
            try:
                year = int(year_text)
            except ValueError:
                continue
            for sentence_id in sorted(index.sentences_of(subject)):
                if year not in index.years_in(sentence_id):
                    continue
                mention_map = index.sentence_mentions.get(sentence_id, {})
                if subject not in mention_map and not (
                    subject_name and index.has_name(sentence_id, subject_name)
                ):
                    continue
                key = (sentence_id, subject, relation, obj)
                if key in seen:
                    continue
                seen.add(key)
                sub_start, sub_end, sub_text = _span_for(
                    index, sentence_id, subject, subject_name
                )
                year_span = index.find_year_span(sentence_id, year)
                samples.append(
                    _make_sample(
                        sentence_id=sentence_id,
                        subject=subject,
                        subject_mention=sub_text,
                        subject_name=subject_display,
                        subject_start=sub_start,
                        subject_end=sub_end,
                        relation=relation,
                        obj=obj,
                        obj_mention=year_text,
                        obj_name=year_text,
                        obj_start=year_span[0] if year_span else None,
                        obj_end=year_span[1] if year_span else None,
                        source=source,
                        prop="",
                    )
                )
            continue

        object_scope = index.sentences_of(obj)
        if not object_scope:
            continue
        for sentence_id in sorted(index.sentences_of(subject)):
            if sentence_id not in object_scope:
                continue
            mention_map = index.sentence_mentions.get(sentence_id, {})
            subject_ok = subject in mention_map or (
                subject_name and index.has_name(sentence_id, subject_name)
            )
            object_ok = obj in mention_map or (
                object_name and index.has_name(sentence_id, object_name)
            )
            if not subject_ok or not object_ok:
                continue
            key = (sentence_id, subject, relation, obj)
            if key in seen:
                continue
            seen.add(key)
            sub_start, sub_end, sub_text = _span_for(
                index, sentence_id, subject, subject_name
            )
            obj_start, obj_end, obj_text = _span_for(
                index, sentence_id, obj, object_name
            )
            samples.append(
                _make_sample(
                    sentence_id=sentence_id,
                    subject=subject,
                    subject_mention=sub_text,
                    subject_name=subject_display,
                    subject_start=sub_start,
                    subject_end=sub_end,
                    relation=relation,
                    obj=obj,
                    obj_mention=obj_text,
                    obj_name=object_display,
                    obj_start=obj_start,
                    obj_end=obj_end,
                    source=source,
                    prop="",
                )
            )
    return samples


def build_qid_to_entities(
    infobox_entities_path: str | Path,
    documents_path: str | Path,
) -> dict[str, list[str]]:
    """Dựng map ``QID`` → danh sách `entity_id` có mặt trong corpus.

    Nguồn A — `infobox_entities.jsonl` (đáng tin nhất).
    Nguồn B — `documents.jsonl`: `wikibase_item` của bài + `entity_id` theo
    `make_entity_id(type, title)`.

    Args:
        infobox_entities_path: Đường dẫn artifact Phase 3.
        documents_path: Đường dẫn artifact Phase 2.

    Returns:
        Map ``QID`` → danh sách `entity_id`.
    """
    mapping: dict[str, list[str]] = defaultdict(list)
    for entity in iter_jsonl(infobox_entities_path):
        qid = entity.get("wikidata_qid")
        entity_id = entity.get("entity_id")
        if qid and entity_id:
            mapping[str(qid)].append(str(entity_id))

    signal_to_type = {
        "person": "person",
        "place": "place",
        "dynasty": "dynasty",
        "event": "event",
        "battle": "event",
        "house": "dynasty",
    }
    for doc in iter_jsonl(documents_path):
        qid = doc.get("wikibase_item")
        title = doc.get("title")
        if not qid or not title:
            continue
        doc_type = doc.get("infobox_type") or doc.get("wikidata_signal")
        entity_type = signal_to_type.get(str(doc_type or ""))
        if entity_type is None:
            continue
        entity_id = make_entity_id(entity_type, str(title))
        bucket = mapping[str(qid)]
        if entity_id not in bucket:
            bucket.append(entity_id)
    return dict(mapping)


def main() -> None:
    """Điểm vào CLI."""
    parser = argparse.ArgumentParser(
        description="Grounding triple vào câu corpus (Phase 7)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    config = load_default_config()
    re_cfg = config.get("re") or {}
    interim = resolve_path(config["paths"]["interim_dir"])

    out_path = Path(args.out) if args.out else resolve_path(
        re_cfg.get("positive_path", "data/interim/re_positive.jsonl")
    )
    pairs_path = resolve_path(
        re_cfg.get("pairs_path", "data/interim/wikidata_pairs.jsonl")
    )

    relation_map = load_relation_map(re_cfg.get("relations_config"))
    index = build_corpus_index(resolve_path(re_cfg.get("coref_path")))
    entity_names, entity_types = load_entity_names(
        resolve_path(re_cfg.get("infobox_entities_path"))
    )
    qid_to_entities = build_qid_to_entities(
        resolve_path(re_cfg.get("infobox_entities_path")),
        resolve_path(config["paths"]["interim_dir"]) / "documents.jsonl",
    )
    qid_labels = load_wikidata_labels(pairs_path)
    display_names = load_entity_display_names(
        resolve_path(re_cfg.get("infobox_entities_path"))
    )
    qid_display_labels = load_wikidata_display_labels(pairs_path)
    name_to_entity: dict[str, str] = {}
    for entity_id, normalized in entity_names.items():
        if normalized and normalized not in name_to_entity:
            name_to_entity[normalized] = entity_id

    pairs = list(iter_jsonl(pairs_path))
    samples = ground_wikidata_pairs(
        pairs,
        index,
        relation_map,
        qid_to_entities,
        entity_names,
        entity_types,
        qid_labels,
        display_names=display_names,
        qid_display_labels=qid_display_labels,
        name_to_entity=name_to_entity,
    )
    logger.info("Wikidata: %d mẫu grounded", len(samples))

    infobox_samples = ground_triples(
        resolve_path(re_cfg.get("infobox_triples_path")),
        index,
        entity_names,
        source="infobox",
        display_names=display_names,
    )
    logger.info("Infobox: %d mẫu grounded", len(infobox_samples))

    lead_samples = ground_triples(
        resolve_path(re_cfg.get("lead_triples_path")),
        index,
        entity_names,
        source="lead",
        display_names=display_names,
    )
    logger.info("Lead: %d mẫu grounded", len(lead_samples))

    # Dedupe: (sentence_id, subject, relation, object) — giữ nguồn ưu tiên
    # wikidata > infobox > lead.
    priority = {"wikidata": 0, "infobox": 1, "lead": 2}
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for sample in samples + infobox_samples + lead_samples:
        key = (
            sample["sentence_id"],
            sample["subject"],
            sample["relation"],
            sample["object"],
        )
        current = merged.get(key)
        if current is None or priority[sample["source"]] < priority[current["source"]]:
            merged[key] = sample

    records = sorted(
        merged.values(),
        key=lambda s: (s["sentence_id"], s["subject"], s["relation"], s["object"]),
    )
    write_jsonl(out_path, records)
    by_source: dict[str, int] = defaultdict(int)
    for record in records:
        by_source[record["source"]] += 1
    logger.info(
        "Ghi %d mẫu POSITIVE unique → %s (%s)",
        len(records),
        out_path,
        dict(by_source),
    )


if __name__ == "__main__":
    main()

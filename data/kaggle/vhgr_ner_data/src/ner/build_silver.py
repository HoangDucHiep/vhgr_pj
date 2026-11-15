"""Sinh nhãn bạc NER từ hyperlink (Phase 4 — B2 phần 1).

Vì sao cần: để huấn luyện mô hình NER (Phase 5) cần nhãn, nhưng corpus
chưa có nhãn thủ công. Wikipedia **đã có** nhãn sẵn ở dạng hyperlink: mỗi
link ``[[Lê Lợi]]`` là một lần xác nhận "đây là một thực thể" — chỉ thiếu
**loại** của thực thể đó.

Cách làm: suy loại từ **đích** của link theo thứ tự ưu tiên (giảm dần độ
chắc chắn):

1. ``qid_direct``    — đích có QID → ``P31`` khớp trực tiếp bảng ``direct``.
2. ``qid_ancestor``  — đích có QID → ``P31`` → ``P279*`` khớp bảng ``ancestor``.
3. ``kg_type``       — đích nằm trong ``infobox_entities.jsonl`` (Phase 3).
4. ``wikidata_signal`` — tín hiệu loại từ Phase 1.
5. ``pattern``       — mẫu tên ("nhà X" → DYNASTY, "Thế kỷ XV" → TIME…).
6. ``time_regex``    — regex năm / thế kỷ trên câu (không cần link).

Nếu không xác định được → **bỏ** (không gán nhãn sai — nguyên tắc
``AGENTS.md`` §5.3 "không bịa").

Nhãn ở **mức token** (word-level) vì PhoBERT dùng subword; khi train sẽ
map sang subword bằng offset của tokenizer (Phase 5, ``src/ner/data_convert.py``).

Artifact sinh ra:

- ``data/interim/ner_silver.jsonl`` — nhãn bạc theo câu.
- ``data/interim/qid_types.json`` — cache QID → lớp ``P31`` (để chạy lại nhanh).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.common.config import resolve_path
from src.common.logger import get_logger

logger = get_logger(__name__)

#: 6 lớp nhãn NER — khớp với `docs/CONTEXT.md` §2.4 (7 loại node KG, bỏ `article`).
NER_LABELS: tuple[str, ...] = ("PERSON", "DYNASTY", "EVENT", "LOCATION", "TIME", "TITLE")

#: Số nhãn khi chuyển sang BIO: mỗi lớp × 2 tiền tố (`B-`, `I-`) + `O`.
#:
#: Khớp với `docs/CONTEXT.md` §2.4 ("13 lớp = 6 nhãn × BIOES + O") và
#: `docs/09` Phase 5 (`num_labels = 2*6 + 1 = 13`). Lưu ý: đặc tả gọi là
#: "BIOES" nhưng **con số 13 chỉ khớp với scheme BIO** (`B-`/`I-`) —
#: scheme đầy đủ 4 tiền tố (`B-`/`I-`/`E-`/`S-`) sẽ là 25 lớp.
NUM_LABELS = 2 * len(NER_LABELS) + 1

#: Tiền tố nhãn (scheme BIO).
BIO_PREFIXES: tuple[str, ...] = ("B-", "I-")


# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TypeMapConfig:
    """Cấu hình ánh xạ loại → nhãn NER.

    Gồm 2 file:

    - ``configs/wikidata_type_map.yaml`` — bảng map lớp Wikidata → nhãn
      (sinh tự động, ~2.400 lớp).
    - ``configs/ner_silver_config.yaml`` — cấu hình thủ công: độ tin cậy,
      ngưỡng, mẫu tên, regex TIME.

    Attributes:
        direct: Map QID lớp → nhãn (tên lớp P31 tự nó khớp).
        ancestor: Map QID lớp → nhãn (lớp cha P279 khớp).
        kg_type: Map loại node KG (Phase 3) → nhãn.
        wikidata_signal: Map tín hiệu Wikidata (Phase 1) → nhãn.
        confidence: Độ tin cậy theo nguồn nhãn.
        min_confidence: Ngưỡng lọc nhãn.
        patterns: Danh sách mẫu tên → nhãn.
        time_patterns: Mẫu regex sinh nhãn TIME.
    """

    direct: dict[str, str] = field(default_factory=dict)
    ancestor: dict[str, str] = field(default_factory=dict)
    kg_type: dict[str, str] = field(default_factory=dict)
    wikidata_signal: dict[str, str] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)
    min_confidence: float = 0.0
    patterns: list[dict[str, str]] = field(default_factory=list)
    time_patterns: list[dict[str, Any]] = field(default_factory=list)
    time_context_before: set[str] = field(default_factory=set)
    time_context_after: set[str] = field(default_factory=set)

    def conf(self, source: str) -> float:
        """Lấy độ tin cậy của một nguồn nhãn.

        Args:
            source: Tên nguồn (vd ``qid_direct``).

        Returns:
            Độ tin cậy (0.0 nếu không có trong config).
        """
        return float(self.confidence.get(source, 0.0))


def load_type_map(
    type_map_path: str | Path = "configs/wikidata_type_map.yaml",
    config_path: str | Path = "configs/ner_silver_config.yaml",
) -> TypeMapConfig:
    """Nạp cấu hình ánh xạ loại → nhãn NER.

    Args:
        type_map_path: Đường dẫn bảng map lớp Wikidata → nhãn.
        config_path: Đường dẫn cấu hình thủ công.

    Returns:
        Đối tượng `TypeMapConfig`.
    """
    raw: dict[str, Any] = {}
    type_map_file = resolve_path(type_map_path)
    if type_map_file.exists():
        with type_map_file.open("r", encoding="utf-8") as handle:
            raw.update(yaml.safe_load(handle) or {})

    config_file = resolve_path(config_path)
    if config_file.exists():
        with config_file.open("r", encoding="utf-8") as handle:
            raw.update(yaml.safe_load(handle) or {})

    time_patterns: list[dict[str, Any]] = []
    time_cfg = raw.get("time") or {}
    for group, entries in time_cfg.items():
        for entry in entries or []:
            item = dict(entry)
            item["group_kind"] = group
            item.setdefault("label", "TIME")
            time_patterns.append(item)

    return TypeMapConfig(
        direct=dict(raw.get("direct") or {}),
        ancestor=dict(raw.get("ancestor") or {}),
        kg_type=dict(raw.get("kg_type") or {}),
        wikidata_signal=dict(raw.get("wikidata_signal") or {}),
        confidence=dict(raw.get("confidence") or {}),
        min_confidence=float(raw.get("min_confidence") or 0.0),
        patterns=list(raw.get("patterns") or []),
        time_patterns=time_patterns,
        time_context_before=set(raw.get("time_context_before") or []),
        time_context_after=set(raw.get("time_context_after") or []),
    )


# ---------------------------------------------------------------------------
# Tiện ích văn bản
# ---------------------------------------------------------------------------


def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt, chuyển chữ thường.

    Chỉ dùng cho **tra cứu** (khớp mẫu tên, khớp tên đích) — không dùng làm
    tên hiển thị (nguyên tắc `AGENTS.md` §5.10).

    Args:
        text: Chuỗi đầu vào.

    Returns:
        Chuỗi đã bỏ dấu, viết thường.
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped).lower().strip()


#: Mẫu token: giữ chữ/số, tách dấu câu.
_TOKEN_RE = re.compile(r"\w+(?:[-–—']\w+)*|\S", re.UNICODE)


def tokenize(text: str) -> tuple[list[str], list[int], list[int]]:
    """Tách câu thành token kèm vị trí ký tự (bắt đầu / kết thúc).

    Dùng regex ``\\w+`` thay vì ``split()`` vì tiếng Việt có dấu và tên riêng
    có thể chứa dấu gạch nối ("Bắc-Ninh", "Phạm-Đình").

    Args:
        text: Câu văn bản.

    Returns:
        Bộ ba ``(tokens, starts, ends)``.
    """
    tokens: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for match in _TOKEN_RE.finditer(text):
        tokens.append(match.group(0))
        starts.append(match.start())
        ends.append(match.end())
    return tokens, starts, ends


def _char_span_to_token_span(
    char_start: int,
    char_end: int,
    starts: list[int],
    ends: list[int],
) -> tuple[int, int] | None:
    """Đổi khoảng ký tự → khoảng chỉ số token.

    Args:
        char_start: Vị trí bắt đầu (ký tự).
        char_end: Vị trí kết thúc (ký tự, exclusive).
        starts: Danh sách vị trí bắt đầu của token.
        ends: Danh sách vị trí kết thúc của token.

    Returns:
        Cặp ``(i, j)`` token bao trọn khoảng ký tự (j exclusive), hoặc
        ``None`` nếu khoảng ký tự không khớp trọn vẹn bất kỳ token nào.
    """
    first = last = -1
    for index, (start, end) in enumerate(zip(starts, ends)):
        if start >= char_start and end <= char_end:
            if first < 0:
                first = index
            last = index
    if first < 0 or last < 0:
        return None
    return first, last + 1


# ---------------------------------------------------------------------------
# BIOES
# ---------------------------------------------------------------------------


def build_bioes(
    n_tokens: int,
    spans: list[tuple[int, int, str]],
) -> list[str]:
    """Chuyển danh sách span (token) → nhãn BIO.

    Scheme **BIO** (`B-`/`I-`/`O`) — khớp với `docs/CONTEXT.md` §2.4
    (13 lớp = 6 nhãn × 2 tiền tố + `O`).

    Args:
        n_tokens: Tổng số token của câu.
        spans: Danh sách ``(start_token, end_token, label)``, ``end_token`` exclusive.

    Returns:
        Danh sách nhãn BIO dài đúng ``n_tokens``.
    """
    labels = ["O"] * n_tokens
    # Sắp xếp theo vị trí, ưu tiên span dài hơn khi trùng vị trí.
    for start, end, label in sorted(spans, key=lambda s: (s[0], -s[1])):
        if start >= end or end > n_tokens:
            continue
        labels[start] = f"B-{label}"
        for index in range(start + 1, end):
            labels[index] = f"I-{label}"
    return labels


def bioes_to_mentions(
    tokens: list[str],
    labels: list[str],
) -> list[dict[str, Any]]:
    """Khôi phục danh sách mention từ nhãn BIO.

    Args:
        tokens: Danh sách token.
        labels: Danh sách nhãn BIO (cùng độ dài với ``tokens``).

    Returns:
        Danh sách mention ``{start_token, end_token, label, text}`` —
        ``end_token`` exclusive.
    """
    mentions: list[dict[str, Any]] = []
    index = 0
    total = len(labels)
    while index < total:
        label = labels[index]
        if label == "O" or "-" not in label:
            index += 1
            continue
        prefix, _, entity_type = label.partition("-")
        if prefix != "B":
            index += 1
            continue
        start = index
        end = index + 1
        # Nuôi tiếp chuỗi I- cùng loại.
        while end < total:
            nxt = labels[end]
            if nxt == "O" or "-" not in nxt:
                break
            nxt_prefix, _, nxt_type = nxt.partition("-")
            if nxt_type != entity_type or nxt_prefix != "I":
                break
            end += 1
        text = " ".join(tokens[start:end])
        mentions.append(
            {
                "start_token": start,
                "end_token": end,
                "label": entity_type,
                "text": text,
            }
        )
        index = end
    return mentions


# ---------------------------------------------------------------------------
# Bộ gán nhãn
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SilverLabeller:
    """Gán nhãn NER bạc cho mention dựa trên nhiều nguồn.

    Attributes:
        config: Cấu hình ánh xạ loại → nhãn.
        p31: Map ``{qid: [lớp P31]}``.
        ancestors: Map ``{lớp: {lớp cha}}``.
        kg_types: Map ``{tên entity (bỏ dấu): loại node KG}``.
        signals: Map ``{tên bài (bỏ dấu): tín hiệu Wikidata}``.
        title_to_qid: Map ``{tên bài: QID}``.
        compiled_patterns: Danh sách ``(regex, nhãn)`` từ cấu hình.
    """

    config: TypeMapConfig
    p31: dict[str, list[str]] = field(default_factory=dict)
    ancestors: dict[str, set[str]] = field(default_factory=dict)
    kg_types: dict[str, str] = field(default_factory=dict)
    signals: dict[str, str] = field(default_factory=dict)
    title_to_qid: dict[str, str] = field(default_factory=dict)
    categories: dict[str, dict[str, Any]] = field(default_factory=dict)
    compiled_patterns: list[tuple[re.Pattern[str], str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.compiled_patterns = [
            (re.compile(entry["pattern"], re.IGNORECASE), entry["label"])
            for entry in self.config.patterns
        ]

    # -- nguồn nhãn ---------------------------------------------------------

    def label_from_category(self, target: str) -> tuple[str | None, str]:
        """Suy nhãn từ **category Wikipedia** (mạnh nhất cho corpus này).

        Args:
            target: Tên đích link.

        Returns:
            Cặp ``(nhãn, nguồn)``.
        """
        entry = self.categories.get(target)
        if entry is None:
            return None, "unknown"
        label = entry.get("label")
        if label is None:
            return None, "unknown"
        return label, "category"

    def label_from_qid(self, qid: str) -> tuple[str | None, str]:
        """Suy nhãn từ QID (qua `P31` / `P279*`).

        Args:
            qid: QID cần tra.

        Returns:
            Cặp ``(nhãn, nguồn)``; nhãn là ``None`` nếu không xác định được.
        """
        from src.ner.qid_types import classify_qid

        return classify_qid(
            qid,
            p31=self.p31,
            ancestors=self.ancestors,
            direct=self.config.direct,
            ancestor_map=self.config.ancestor,
        )

    def label_from_kg(self, target: str) -> tuple[str | None, str]:
        """Suy nhãn từ loại node KG của Phase 3.

        Args:
            target: Tên đích link.

        Returns:
            Cặp ``(nhãn, nguồn)``.
        """
        kg_type = self.kg_types.get(strip_accents(target))
        if kg_type is None:
            return None, "unknown"
        label = self.config.kg_type.get(kg_type)
        if label is None:
            return None, "unknown"
        return label, "kg_type"

    def label_from_signal(self, target: str) -> tuple[str | None, str]:
        """Suy nhãn từ tín hiệu Wikidata của Phase 1.

        Args:
            target: Tên đích link.

        Returns:
            Cặp ``(nhãn, nguồn)``.
        """
        signal = self.signals.get(strip_accents(target))
        if signal is None:
            return None, "unknown"
        label = self.config.wikidata_signal.get(signal)
        if label is None:
            return None, "unknown"
        return label, "wikidata_signal"

    def label_from_pattern(self, target: str) -> tuple[str | None, str]:
        """Suy nhãn từ mẫu tên (vd "nhà X" → DYNASTY).

        Args:
            target: Tên đích link.

        Returns:
            Cặp ``(nhãn, nguồn)``.
        """
        normalized = strip_accents(target)
        for pattern, label in self.compiled_patterns:
            if pattern.search(normalized):
                return label, "pattern"
        return None, "unknown"

    def resolve(self, target: str) -> tuple[str | None, str, float]:
        """Suy nhãn của một đích link theo đầy đủ thứ tự ưu tiên.

        Thứ tự ưu tiên (giảm dần độ chắc chắn):

        1. ``category`` — category Wikipedia (biên tập viên gắn tay).
        2. ``qid_direct`` / ``qid_ancestor`` — Wikidata `P31` / `P279`.
        3. ``kg_type`` — loại node KG (Phase 3).
        4. ``wikidata_signal`` — tín hiệu Phase 1.
        5. ``pattern`` — mẫu tên.

        Args:
            target: Tên đích link.

        Returns:
            Bộ ba ``(nhãn, nguồn, độ tin cậy)``; nhãn là ``None`` nếu không
            xác định được.
        """
        label, source = self.label_from_category(target)
        if label:
            return label, source, self.config.conf(source)

        qid = self.title_to_qid.get(target)
        if qid:
            label, source = self.label_from_qid(qid)
            if label:
                return label, source, self.config.conf(source)

        label, source = self.label_from_kg(target)
        if label:
            return label, source, self.config.conf(source)

        label, source = self.label_from_signal(target)
        if label:
            return label, source, self.config.conf(source)

        label, source = self.label_from_pattern(target)
        if label:
            return label, source, self.config.conf(source)

        return None, "unknown", 0.0

    # -- nhãn TIME bằng regex ----------------------------------------------

    def find_time_spans(self, text: str) -> list[tuple[int, int, str]]:
        """Tìm các span thời gian trong câu bằng regex.

        Mẫu có ``require_context: true`` chỉ được chấp nhận khi token **trước**
        hoặc **sau** nằm trong danh sách ngữ cảnh cho phép (vd ``năm 1945``,
        ``(1831)``). Nhờ vậy các số đơn vị đo (650.000 m³, 500 ha) không bị
        gán nhầm là năm.

        Args:
            text: Câu văn bản.

        Returns:
            Danh sách ``(char_start, char_end, nhãn)``.
        """
        spans: list[tuple[int, int, str]] = []
        for entry in self.config.time_patterns:
            pattern = entry.get("pattern")
            if not pattern:
                continue
            group = int(entry.get("group", 1))
            label = entry.get("label", "TIME")
            require_context = bool(entry.get("require_context"))
            for match in re.finditer(pattern, text, re.IGNORECASE):
                try:
                    start = match.start(group)
                    end = match.end(group)
                except (IndexError, re.error):
                    continue
                if start < 0 or end <= start:
                    continue
                if require_context and not self._has_time_context(text, start, end):
                    continue
                spans.append((start, end, label))
        # Loại trùng lặp, giữ lần đầu.
        unique: list[tuple[int, int, str]] = []
        seen: set[tuple[int, int, str]] = set()
        for span in sorted(spans, key=lambda s: (s[0], s[1])):
            if span in seen:
                continue
            seen.add(span)
            unique.append(span)
        return unique

    def _has_time_context(self, text: str, start: int, end: int) -> bool:
        """Kiểm tra span năm có ngữ cảnh đủ mạnh hay không.

        Chỉ xét **token liền kề** (tối đa 2 token trước / 2 token sau), không
        xét toàn bộ phần trước của câu. Nếu xét toàn câu thì chỉ cần một
        chữ "năm" ở bất kỳ đâu cũng làm mọi con số sau đó thành "năm" →
        gán sai hàng nghìn số đo lượng (vd "203/2025/QH15").

        Args:
            text: Câu văn bản.
            start: Vị trí bắt đầu span (ký tự).
            end: Vị trí kết thúc span (ký tự, exclusive).

        Returns:
            `True` nếu có ngữ cảnh hợp lệ.
        """
        before_tokens = _TOKEN_RE.findall(text[:start])
        after_tokens = _TOKEN_RE.findall(text[end:])
        context_before = {
            strip_accents(token) for token in self.config.time_context_before
        }
        context_after = {
            strip_accents(token) for token in self.config.time_context_after
        }
        for token in before_tokens[-2:]:
            if strip_accents(token) in context_before:
                return True
        for token in after_tokens[:2]:
            if strip_accents(token) in context_after:
                return True
        return False


# ---------------------------------------------------------------------------
# Sinh nhãn
# ---------------------------------------------------------------------------


def _iter_jsonl(path: str | Path):
    """Duyệt file JSONL.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng dict đã parse.
    """
    resolved = resolve_path(path)
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _valid_link(anchor: str, target: str) -> bool:
    """Kiểm tra link có dùng để gán nhãn được không.

    Giữ link khi ``anchor == target`` (anchor chính là tên thực thể) hoặc
    ``target`` là chuỗi con của ``anchor`` (vd anchor "Cộng hòa xã hội chủ
    nghĩa Việt Nam" → target "Việt Nam"). Bỏ link khi anchor chỉ là từ chung
    (vd anchor "thủ đô" → target "thủ đô") vì đó không phải tên thực thể.

    Args:
        anchor: Text hiển thị của link.
        target: Tiêu đề bài đích.

    Returns:
        `True` nếu link dùng để gán nhãn được.
    """
    if not anchor or not target:
        return False
    anchor_norm = strip_accents(anchor)
    target_norm = strip_accents(target)
    if anchor_norm == target_norm:
        return True
    return target_norm in anchor_norm


def build_silver(
    *,
    documents_path: str | Path,
    title_to_qid_path: str | Path,
    infobox_entities_path: str | Path,
    dump_facts_path: str | Path,
    type_map_path: str | Path,
    silver_config_path: str | Path,
    output_path: str | Path,
    qid_cache_path: str | Path,
    limit_docs: int | None = None,
    refresh_qid: bool = False,
) -> dict[str, Any]:
    """Sinh file nhãn bạc NER.

    Args:
        documents_path: Đường dẫn `documents.jsonl`.
        title_to_qid_path: Đường dẫn `title_to_qid.json`.
        infobox_entities_path: Đường dẫn `infobox_entities.jsonl`.
        dump_facts_path: Đường dẫn `dump_facts.jsonl` (nguồn category).
        type_map_path: Đường dẫn bảng map lớp Wikidata → nhãn.
        silver_config_path: Đường dẫn cấu hình thủ công.
        output_path: Đường dẫn output `ner_silver.jsonl`.
        qid_cache_path: Đường dẫn cache QID → lớp.
        limit_docs: Giới hạn số bài (để smoke test).
        refresh_qid: Bỏ qua cache QID, tra lại từ đầu.

    Returns:
        Thống kê tổng hợp của quá trình sinh nhãn.
    """
    config = load_type_map(type_map_path, silver_config_path)

    title_to_qid: dict[str, str] = {}
    qid_resolved = resolve_path(title_to_qid_path)
    if qid_resolved.exists():
        title_to_qid = json.loads(qid_resolved.read_text(encoding="utf-8"))
    logger.info("title_to_qid: %d bài", len(title_to_qid))

    # Loại node KG (Phase 3) — dùng làm nguồn nhãn dự phòng.
    kg_types: dict[str, str] = {}
    for entity in _iter_jsonl(infobox_entities_path):
        name = entity.get("name") or entity.get("title") or ""
        kg_type = entity.get("type")
        if not name or not kg_type:
            continue
        kg_types[strip_accents(name)] = kg_type

    # Tín hiệu Wikidata (Phase 1) — dùng làm nguồn nhãn dự phòng.
    signals: dict[str, str] = {}
    for doc in _iter_jsonl(documents_path):
        title = doc.get("title") or ""
        signal = doc.get("wikidata_signal")
        if title and signal:
            signals[strip_accents(title)] = signal

    # Tập QID cần tra: mọi đích link trong corpus.
    targets: set[str] = set()
    for doc in _iter_jsonl(documents_path):
        for link in doc.get("links") or []:
            target = link.get("target")
            if target:
                targets.add(target)

    qids = sorted({title_to_qid[t] for t in targets if t in title_to_qid})
    logger.info("Cần tra %d QID cho %d đích link", len(qids), len(targets))

    from src.ner.qid_types import resolve_qid_types

    p31, ancestors = resolve_qid_types(
        qids,
        cache_path=qid_cache_path,
        refresh=refresh_qid,
    )

    # Chỉ mục category Wikipedia — nguồn nhãn **mạnh nhất** cho corpus này.
    from src.ner.category_types import build_category_index

    category_index = build_category_index(dump_facts_path, targets)

    labeller = SilverLabeller(
        config=config,
        p31=p31,
        ancestors=ancestors,
        kg_types=kg_types,
        signals=signals,
        title_to_qid=title_to_qid,
        categories=category_index,
    )

    out_resolved = resolve_path(output_path)
    out_resolved.parent.mkdir(parents=True, exist_ok=True)

    label_counter: Counter[str] = Counter()
    source_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    n_sentences = 0
    n_sentences_with_label = 0
    n_sentences_with_link = 0
    n_mentions = 0
    n_dropped_low_conf = 0
    n_docs = 0

    with out_resolved.open("w", encoding="utf-8") as handle:
        for doc in _iter_jsonl(documents_path):
            if limit_docs is not None and n_docs >= limit_docs:
                break
            n_docs += 1
            doc_id = doc.get("doc_id")
            page_id = doc.get("page_id")

            # Gom link theo câu (offset là **tương đối** trong câu).
            links_by_sentence: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for link in doc.get("links") or []:
                sid = link.get("sentence_id")
                if sid:
                    links_by_sentence[sid].append(link)

            for sentence in doc.get("sentences") or []:
                sid = sentence.get("sentence_id")
                text = sentence.get("text") or ""
                if not sid or not text:
                    continue
                n_sentences += 1
                tokens, starts, ends = tokenize(text)
                if not tokens:
                    continue

                sent_links = links_by_sentence.get(sid) or []
                if sent_links:
                    n_sentences_with_link += 1

                spans: list[tuple[int, int, str]] = []
                mention_meta: dict[tuple[int, int], dict[str, Any]] = {}

                # (1) Nhãn từ hyperlink
                # Lưu ý: offset của link là **tương đối với `clean_text` của
                # bài**, còn `sentences[].text` bắt đầu tại `char_start` →
                # phải trừ `char_start` của câu để được offset tương đối trong câu.
                sent_char_start = int(sentence.get("char_start") or 0)
                for link in sent_links:
                    anchor = link.get("anchor") or ""
                    target = link.get("target") or ""
                    if not _valid_link(anchor, target):
                        continue
                    char_start = int(link.get("start", 0)) - sent_char_start
                    char_end = int(link.get("end", 0)) - sent_char_start
                    if char_end <= char_start or char_start < 0:
                        continue
                    token_span = _char_span_to_token_span(char_start, char_end, starts, ends)
                    if token_span is None:
                        continue
                    label, source, confidence = labeller.resolve(target)
                    if label is None:
                        continue
                    if confidence < config.min_confidence:
                        n_dropped_low_conf += 1
                        continue
                    t_start, t_end = token_span
                    spans.append((t_start, t_end, label))
                    label_counter[label] += 1
                    source_counter[source] += 1
                    type_counter[label] += 1
                    mention_meta.setdefault(
                        (t_start, t_end),
                        {
                            "target": target,
                            "qid": title_to_qid.get(target),
                            "source": source,
                            "target_type_confidence": round(confidence, 3),
                        },
                    )

                # (2) Nhãn TIME bằng regex (chỉ chỗ **chưa** có nhãn)
                for char_start, char_end, label in labeller.find_time_spans(text):
                    token_span = _char_span_to_token_span(char_start, char_end, starts, ends)
                    if token_span is None:
                        continue
                    t_start, t_end = token_span
                    if any(
                        t_start < span_end and span_start < t_end
                        for span_start, span_end, _ in spans
                    ):
                        continue  # đã có nhãn khác → bỏ qua
                    spans.append((t_start, t_end, label))
                    label_counter[label] += 1
                    source_counter["time_regex"] += 1
                    mention_meta.setdefault(
                        (t_start, t_end),
                        {
                            "source": "time_regex",
                            "target_type_confidence": round(
                                config.conf("time_regex"), 3
                            ),
                        },
                    )

                labels = build_bioes(n_tokens=len(tokens), spans=spans)
                if any(label != "O" for label in labels):
                    n_sentences_with_label += 1
                n_mentions += len(spans)

                mentions = bioes_to_mentions(tokens, labels)
                for mention in mentions:
                    key = (mention["start_token"], mention["end_token"])
                    meta = mention_meta.get(key)
                    if meta is not None:
                        mention.update(meta)

                record = {
                    "sentence_id": sid,
                    "doc_id": doc_id,
                    "page_id": page_id,
                    "text": text,
                    "tokens": tokens,
                    "labels": labels,
                    "mentions": mentions,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    stats = {
        "n_docs": n_docs,
        "n_sentences": n_sentences,
        "n_sentences_with_link": n_sentences_with_link,
        "n_sentences_with_label": n_sentences_with_label,
        "n_mentions": n_mentions,
        "n_dropped_low_conf": n_dropped_low_conf,
        "coverage_linked": round(
            n_sentences_with_label / n_sentences_with_link, 4
        )
        if n_sentences_with_link
        else 0.0,
        "coverage_all": round(n_sentences_with_label / n_sentences, 4)
        if n_sentences
        else 0.0,
        "label_distribution": dict(label_counter.most_common()),
        "source_distribution": dict(source_counter.most_common()),
    }
    logger.info("Hoàn tất: %d câu, %d mention", n_sentences, n_mentions)
    logger.info("Nguồn nhãn: %s", dict(source_counter.most_common()))
    logger.info("Phân bố nhãn: %s", dict(label_counter.most_common()))
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Danh sách tham số dòng lệnh (mặc định `sys.argv[1:]`).

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(description="Sinh nhãn bạc NER (Phase 4)")
    parser.add_argument("--documents", default="data/interim/documents.jsonl")
    parser.add_argument("--title-to-qid", default="data/interim/title_to_qid.json")
    parser.add_argument(
        "--infobox-entities", default="data/interim/infobox_entities.jsonl"
    )
    parser.add_argument("--dump-facts", default="data/interim/dump_facts.jsonl")
    parser.add_argument("--type-map", default="configs/wikidata_type_map.yaml")
    parser.add_argument("--silver-config", default="configs/ner_silver_config.yaml")
    parser.add_argument("--out", default="data/interim/ner_silver.jsonl")
    parser.add_argument("--qid-cache", default="data/interim/qid_types.json")
    parser.add_argument("--limit-docs", type=int, default=None)
    parser.add_argument("--refresh-qid", action="store_true")
    parser.add_argument("--stats-out", default=None)
    args = parser.parse_args(argv)

    stats = build_silver(
        documents_path=args.documents,
        title_to_qid_path=args.title_to_qid,
        infobox_entities_path=args.infobox_entities,
        dump_facts_path=args.dump_facts,
        type_map_path=args.type_map,
        silver_config_path=args.silver_config,
        output_path=args.out,
        qid_cache_path=args.qid_cache,
        limit_docs=args.limit_docs,
        refresh_qid=args.refresh_qid,
    )

    if args.stats_out:
        out = resolve_path(args.stats_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

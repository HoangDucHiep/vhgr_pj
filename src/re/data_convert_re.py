"""Chuyển tập RE của Phase 7 → đầu vào mô hình PhoBERT đa nhãn (Phase 8 — D1.2).

Vì sao cần module này
----------------------
`data/interim/re_train.jsonl` (Phase 7) là artifact **theo câu**: mỗi câu có
một mảng ``pairs``, mỗi cặp là một *slot* ``(subject, object, relation, label)``.
Phase 8 cần biến mỗi cặp thành một mẫu mô hình với **19 nhãn đa nhãn**
(18 quan hệ theo `RELATION_ORDER` + 1 đầu ``NA``).

Định dạng đầu vào mô hình (đặc tả `docs/09` §Phase 8)
------------------------------------------------------
```
<s> subj_mention [SEP] câu có «PERSON:Lê Lợi» và «PERSON:Nguyễn Trung» [SEP] obj_mention
```

- **3 đoạn** nối tiếp bằng ``</s>``; nhãn dự đoán nằm ở vị trí ``<s>`` (đầu chuỗi)
  → dùng ``AutoModelForSequenceClassification`` (sequence classification).
- Marker **có type**: ``«`` + ``TYPE`` + ``:`` + ``mention`` + ``»``.
- PhoBERT có ``type_vocab_size = 1`` → **không** dùng được ``token_type_ids``,
  nên ba đoạn được nối thành **một** chuỗi (đúng như đặc tả viết).

Vì sao nhãn là **đa nhãn** chứ không phải 19 lớp đơn nhãn (D-061)
------------------------------------------------------------------
Đo được ở Phase 7: **14,7%** input có nhãn mục tiêu mâu thuẫn dưới dạng đơn
nhãn; riêng **1.777** input có ≥ 2 quan hệ POSITIVE, trong đó **53,7%** là cặp
``cha_cua`` + ``me_cua`` — quan hệ *song sinh* hợp lệ (anh em cùng cha mẹ), không
phải lỗi gán nhãn.

→ Mô hình có **19 đầu sigmoid**; mỗi quan hệ là một nhị phân độc lập.

Mất đối chiếu (mask) — vì sao cần
---------------------------------
Một input chỉ có slot cho một vài quan hệ (đo được: ``cha_cua`` 24,0% input,
``lap_ra`` 0,1%). Quan hệ **chưa có slot** là *chưa biết*, **không phải** "không
có quan hệ" → dùng ``-100`` để **không tính loss** cho các slot đó. Nếu không
mask, mô hình bị dạy sai rằng quan hệ chưa quan sát là "vắng mặt".

- Slot POSITIVE → nhãn ``1.0``
- Slot NEGATIVE → nhãn ``0.0``
- Quan hệ chưa có slot → nhãn ``-100`` (mask)
- Đầu ``NA``: ``1.0`` khi input **không có** quan hệ POSITIVE nào, ``0.0`` ngược lại.

Kiểu dữ liệu đầu ra
--------------------
Mỗi *input* (một cặp subject–object trong một câu) sinh **một** mẫu, mang
vector nhãn 19 chiều có mask. Không sinh một mẫu cho mỗi slot (sẽ mã hoá lại
cùng một chuỗi 29.957 lần với cùng một tín hiệu gradient).

Token hoá **theo word** (D-039)
-------------------------------
Cùng cách với Phase 5: tách câu bằng `src.ner.build_silver.tokenize` (regex
``\\w+`` + dấu nối) rồi BPE **từng word** bằng `tokenizer.bpe(word)``.
Tokenize raw text sẽ cho phân bố subword khác với lúc train → mô hình suy luận
kém hơn mức thật. Marker cũng được tách word tương ứng để hai tầng
(train / infer) thấy **cùng** chuỗi subword.

Slow tokenizer (D-040)
----------------------
Fast tokenizer đi kèm repo `vinai/phobert-base` có vocab 66.119 > embedding
64.001 → ``IndexError``. Module này dùng `src.ner.data_convert.load_tokenizer`
(slow tokenizer) làm nguồn sự thật vocab.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger
from src.common.schemas import RELATION_ORDER
from src.ner.build_silver import tokenize
from src.ner.data_convert import WordTokenizer, load_tokenizer

logger = get_logger(__name__)

#: Nhãn ``NA`` — dùng cho quan hệ "không có quan hệ nào".
NA_LABEL = "NA"

#: 19 lớp: 18 quan hệ (thứ tự `RELATION_ORDER`) + ``NA`` (đầu ra cuối).
LABEL_LIST: tuple[str, ...] = tuple(RELATION_ORDER) + (NA_LABEL,)

#: Số lớp = 18 + 1 = 19.
NUM_LABELS: int = len(LABEL_LIST)

#: Ánh xạ nhãn → id.
LABEL2ID: dict[str, int] = {label: index for index, label in enumerate(LABEL_LIST)}

#: Ánh xạ id → nhãn.
ID2LABEL: dict[int, str] = {index: label for label, index in LABEL2ID.items()}

#: Id của đầu ra ``NA`` (luôn là chiều cuối cùng).
NA_INDEX: int = LABEL2ID[NA_LABEL]

#: Giá trị nhãn cho slot **chưa biết** → bị loại khỏi loss.
IGNORE_VALUE: float = -100.0

#: Ánh xạ nhãn NER (Phase 5) → **type KG chuẩn hoá** (D-063).
NER_TO_KG_TYPE: dict[str, str] = {
    "PERSON": "person",
    "DYNASTY": "dynasty",
    "EVENT": "event",
    "LOCATION": "place",
    "TITLE": "title",
    "TIME": "year",
}

#: Tập type KG hợp lệ.
KG_TYPES: frozenset[str] = frozenset(
    {"person", "dynasty", "event", "place", "title", "year"}
)

#: Type khi không xác định được.
UNKNOWN_TYPE = "unknown"

#: Tập từ bị coi là **đại từ** khi dựng tên hiển thị (không dùng làm tên).
PRONOUN_TOKENS: frozenset[str] = frozenset(
    {
        "ông", "bà", "ông ấy", "chú", "bác", "tôi", "tao", "mình", "hắn",
        "y", "chàng", "cô", "nàng", "họ", "nó", "người", "đó", "đây", "kia",
        "ấy", "này", "quý", "công", "chúa", "vua", "ảnh", "anh", "em", "chị",
        "anh ấy", "cô ấy", "chú ấy", "bác ấy", "dạ", "tên", "người ấy",
    }
)


def is_pronoun(text: str) -> bool:
    """Kiểm tra một chuỗi có phải **đại từ/danh xưng** hay không.

    Args:
        text: Văn bản cần kiểm tra.

    Returns:
        ``True`` nếu là đại từ/danh xưng.
    """
    return text.strip().lower() in PRONOUN_TOKENS


# ---------------------------------------------------------------------------
# Bảng map type của entity
# ---------------------------------------------------------------------------


def build_entity_types(
    coref_path: str | Path,
    infobox_entities_path: str | Path,
) -> dict[str, str]:
    """Dựng bảng ``entity_id`` → **type KG chuẩn hoá** (D-063).

    Chuỗi ưu tiên (đo được trên tập Phase 7):

    1. **Vote NER đa số** theo ``canonical_id`` trong `coref_resolved.jsonl`
       → 93,5% số lượt mention.
    2. **Fallback infobox** — ``infobox_entities.jsonl`` → 0% (mọi entity đã
       có vote NER) nhưng vẫn giữ để phòng khi thiếu coref.
    3. **Tiền tố ``year_``** trong ``entity_id`` → 4,3%.
    4. ``unknown`` → 2,2%.

    Args:
        coref_path: Đường dẫn `coref_resolved.jsonl`.
        infobox_entities_path: Đường dẫn `infobox_entities.jsonl`.

    Returns:
        Dict ``entity_id`` → type KG (đã chuẩn hoá về `KG_TYPES`).
    """
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    with Path(coref_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            for mention in record.get("mentions") or []:
                entity_id = str(mention.get("canonical_id") or "")
                label = str(mention.get("label") or "")
                if not entity_id or not label:
                    continue
                kg_type = NER_TO_KG_TYPE.get(label)
                if kg_type is None:
                    continue
                votes[entity_id][kg_type] += 1

    types: dict[str, str] = {}
    for entity_id, counter in votes.items():
        if counter:
            types[entity_id] = counter.most_common(1)[0][0]

    infobox_path = Path(infobox_entities_path)
    if infobox_path.exists():
        with infobox_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                entity_id = str(record.get("entity_id") or "")
                kg_type = str(record.get("type") or "")
                if not entity_id or entity_id in types:
                    continue
                if kg_type in KG_TYPES:
                    types[entity_id] = kg_type

    return types


def build_display_names(
    coref_path: str | Path,
    infobox_entities_path: str | Path,
) -> dict[str, str]:
    """Dựng bảng ``entity_id`` → **tên hiển thị chuẩn**.

    Vì sao cần tên chuẩn thay vì dùng luôn mention bề mặt
    ------------------------------------------------------
    Đo được: **1.383/29.957** cặp (4,6%) có **mention bề mặt giống hệt nhau**
    ở hai đầu (vd cặp "chúa Nguyễn" ↔ "chúa Nguyễn"). Nếu marker chỉ chứa
    mention bề mặt thì mô hình **không phân biệt được** chủ thể và đối tượng
    → không thể học quan hệ có hướng.

    Với tên chuẩn, chỉ **83** cặp (0,28%) còn trùng (đều là self-loop thật,
    đã loại ở `build_examples`).

    Chuỗi ưu tiên:
    1. Tên trong `infobox_entities.jsonl` (tên chuẩn của KG).
    2. Mention **không phải đại từ** phổ biến nhất trong `coref_resolved.jsonl`.
    3. Rỗng → dùng mention bề mặt tại thời điểm mã hoá.

    Args:
        coref_path: Đường dẫn `coref_resolved.jsonl`.
        infobox_entities_path: Đường dẫn `infobox_entities.jsonl`.

    Returns:
        Dict ``entity_id`` → tên hiển thị (có thể rỗng).
    """
    names: dict[str, str] = {}

    infobox_path = Path(infobox_entities_path)
    if infobox_path.exists():
        with infobox_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                entity_id = str(record.get("entity_id") or "")
                name = str(record.get("name") or "").strip()
                if entity_id and name:
                    names[entity_id] = name

    votes: dict[str, Counter[str]] = defaultdict(Counter)
    with Path(coref_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            for mention in record.get("mentions") or []:
                entity_id = str(mention.get("canonical_id") or "")
                text = str(mention.get("text") or "").strip()
                if not entity_id or not text or is_pronoun(text):
                    continue
                votes[entity_id][text] += 1

    for entity_id, counter in votes.items():
        if entity_id in names:
            continue
        if counter:
            names[entity_id] = counter.most_common(1)[0][0]

    return names


def resolve_entity_type(
    entity_id: str,
    types: dict[str, str],
) -> str:
    """Xác định type KG của một entity theo chuỗi ưu tiên.

    Args:
        entity_id: Id entity.
        types: Bảng ``entity_id`` → type KG (từ `build_entity_types`).

    Returns:
        Type KG (một trong `KG_TYPES`) hoặc ``"unknown"``.
    """
    if not entity_id:
        return UNKNOWN_TYPE
    known = types.get(entity_id)
    if known:
        return known
    if entity_id.startswith("year_"):
        return "year"
    return UNKNOWN_TYPE


# ---------------------------------------------------------------------------
# Marker
# ---------------------------------------------------------------------------


def marker_words(type_name: str, name: str, role: str = "") -> list[str]:
    """Dựng danh sách *word* của một marker typed.

    Marker có dạng ``«TYPE:ROLE:NAME»`` (hoặc ``«TYPE:NAME»`` nếu không có
    role). Vì tách **theo word** (D-039), marker được tách thành:
    ``«TYPE:ROLE:`` + các word của tên + ``»``.

    Args:
        type_name: Type KG (ví dụ ``"person"``) hoặc ``"unknown"``.
        name: Tên hiển thị của entity.
        role: Vai trò (``"SUBJ"``/``"OBJ"``), rỗng → không ghi role.

    Returns:
        Danh sách word (mỗi phần tử sẽ được BPE riêng).
    """
    head = f"«{type_name.upper()}:{role.upper()}:" if role else f"«{type_name.upper()}:"
    body = tokenize(name)[0] if name else []
    return [head, *body, "»"]


def display_marker(type_name: str, name: str, role: str = "") -> str:
    """Dựng chuỗi marker đầy đủ (dùng để hiển thị / kiểm thử).

    Args:
        type_name: Type KG.
        name: Tên hiển thị của entity.
        role: Vai trò (``"SUBJ"``/``"OBJ"``), rỗng → không ghi role.

    Returns:
        Chuỗi ``«TYPE:ROLE:NAME»``.
    """
    if role:
        return f"«{type_name.upper()}:{role.upper()}:{name}»"
    return f"«{type_name.upper()}:{name}»"


# ---------------------------------------------------------------------------
# Mã hoá
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ReExample:
    """Một mẫu đã mã hoá cho mô hình RE đa nhãn.

    Attributes:
        input_ids: Id subword của chuỗi đầy đủ (3 đoạn).
        attention_mask: Mặt nạ attention.
        labels: Vector nhãn 19 chiều (``-100.0`` = slot chưa biết).
        key: Khoá input ``sentence_id|subject_id|object_id``.
        sentence_id: Id câu nguồn.
        doc_id: Id bài nguồn.
        page_id: Id trang wiki.
        split: Tập chia (``train``/``dev``/``test``).
        text: Văn bản câu gốc.
        subject_entity_id: Id entity chủ thể.
        object_entity_id: Id entity đối tượng.
        subject_mention: Mention bề mặt của chủ thể.
        object_mention: Mention bề mặt của đối tượng.
        subject_type: Type KG của chủ thể.
        object_type: Type KG của đối tượng.
        gold_relations: Tập quan hệ POSITIVE (gold).
        masked_relations: Tập quan hệ chưa có slot (bị mask).
        slot_labels: Map ``relation`` → ``"POSITIVE"``/``"NEGATIVE"``.
    """

    input_ids: list[int]
    attention_mask: list[int]
    labels: list[float]
    key: str
    sentence_id: str
    doc_id: str
    page_id: int
    split: str
    text: str
    subject_entity_id: str
    object_entity_id: str
    subject_mention: str
    object_mention: str
    subject_type: str
    object_type: str
    gold_relations: list[str] = field(default_factory=list)
    masked_relations: list[str] = field(default_factory=list)
    slot_labels: dict[str, str] = field(default_factory=dict)


def _word_range(
    starts: Sequence[int],
    ends: Sequence[int],
    span_start: int,
    span_end: int,
) -> tuple[int, int]:
    """Tìm khoảng word bao trọn một khoảng ký tự.

    Args:
        starts: Vị trí bắt đầu của từng word.
        ends: Vị trí kết thúc của từng word.
        span_start: Bắt đầu khoảng ký tự.
        span_end: Kết thúc khoảng ký tự (exclusive).

    Returns:
        Cặp ``(first, last)`` — chỉ số word, ``last`` exclusive.
    """
    n = len(starts)
    first = 0
    while first < n and ends[first] <= span_start:
        first += 1
    last = first
    while last < n and starts[last] < span_end:
        last += 1
    return first, last


def _build_segment_ids(
    tokenizer: WordTokenizer,
    words: Sequence[str],
) -> list[int]:
    """BPE một danh sách word thành id subword.

    Args:
        tokenizer: `WordTokenizer` bọc slow tokenizer.
        words: Danh sách word.

    Returns:
        Danh sách id subword.
    """
    ids: list[int] = []
    for word in words:
        ids.extend(tokenizer.tokenize_word(word))
    return ids


def _marked_sentence_words(
    tokens: Sequence[str],
    marks: Sequence[tuple[int, int, str, str, str]],
    low: int,
    high: int,
) -> list[str]:
    """Dựng danh sách word của câu đã chèn marker.

    Mỗi marker là **tự chứa** (``«TYPE:ROLE:NAME»``) và **thay thế** các word
    của span tương ứng trong câu.

    Xử lý span **chồng lấn**
    -----------------------
    Đo được ở Phase 7: **1.552/29.957** cặp (5,2%) có hai span chồng lấn (vd
    "Tự Đức" ⊃ "Tự Đứ"). Với mỗi marker tự chứa, span lồng nhau vẫn được phát
    ra **đầy đủ** (marker thứ hai phát ngay sau marker thứ nhất) → mô hình
    không mất vai trò của đối tượng.

    Args:
        tokens: Danh sách word gốc của câu.
        marks: Danh sách ``(word_start, word_end, type, name, role)``, đã sắp
            xếp theo ``word_start`` rồi ``word_end`` giảm dần (ngoài trước).
        low: Chỉ số word đầu của cửa sổ ngữ cảnh.
        high: Chỉ số word cuối (exclusive) của cửa sổ ngữ cảnh.

    Returns:
        Danh sách word đã chèn marker.
    """
    output: list[str] = []
    index = low
    for mark_start, mark_end, type_name, name, role in marks:
        if mark_start >= high:
            break
        if mark_start > index:
            output.extend(tokens[index:mark_start])
        output.extend(marker_words(type_name, name, role))
        index = max(index, min(mark_end, high))
    if index < high:
        output.extend(tokens[index:high])
    return output


def encode_pair(
    tokenizer: WordTokenizer,
    text: str,
    subject: dict[str, Any],
    object_: dict[str, Any],
    subject_type: str,
    object_type: str,
    *,
    subject_name: str = "",
    object_name: str = "",
    max_len: int = 256,
    context_words: int = 48,
    mention_max_subwords: int = 48,
) -> tuple[list[int], list[int]]:
    """Mã hoá một cặp (subject, object) trong một câu thành id subword.

    Chuỗi sinh ra có dạng::

        <s> subj_name </s> câu có «TYPE:SUBJ:name» và «TYPE:OBJ:name» </s> obj_name </s>

    Vì sao marker mang **role** (``SUBJ``/``OBJ``)
    ----------------------------------------------
    Đo được ở Phase 7: **1.383/29.957** cặp (4,6%) có mention bề mặt **giống
    hệt** ở hai đầu (vd "chúa Nguyễn" ↔ "chúa Nguyễn"). Nếu marker chỉ chứa
    tên hiển thị thì vẫn có **83** cặp (0,28%) trùng tên → mô hình không phân
    biệt được hướng của quan hệ.

    → Marker ghi rõ **vai trò** (``SUBJ``/``OBJ``) bên cạnh type, giúp mô hình
    biết đâu là chủ thể, đâu là đối tượng. Chuỗi ``«PERSON:SUBJ:Lê Lợi»``
    vẫn tuân thủ đặc tả `docs/09` (marker có type) — chỉ bổ sung thêm role.

    Vì sao dùng **tên hiển thị chuẩn** thay vì mention bề mặt
    --------------------------------------------------------
    Mention bề mặt là đại từ ở **30,0%** các đầu (vd "ông", "chúa") → marker
    ``«PERSON:ông»`` không mang thông tin định danh. Tên chuẩn giúp mô hình
    nối được mention với entity.

    Args:
        tokenizer: `WordTokenizer` bọc slow tokenizer.
        text: Văn bản câu gốc.
        subject: Dict chủ thể (cần ``mention``, ``start``, ``end``).
        object_: Dict đối tượng (cần ``mention``, ``start``, ``end``).
        subject_type: Type KG của chủ thể.
        object_type: Type KG của đối tượng.
        subject_name: Tên hiển thị chuẩn của chủ thể (rỗng → dùng mention).
        object_name: Tên hiển thị chuẩn của đối tượng (rỗng → dùng mention).
        max_len: Độ dài tối đa của chuỗi (kể cả ``<s>``/``</s>``).
        context_words: Số word ngữ cảnh giữ mỗi bên của hai mention.
        mention_max_subwords: Trần số subword cho mỗi đoạn mention đứng riêng.

    Returns:
        Cặp ``(input_ids, attention_mask)``.
    """
    tokens, starts, ends = tokenize(text)
    if not tokens:
        return [], []

    subj_start = int(subject.get("start", 0))
    subj_end = int(subject.get("end", 0))
    obj_start = int(object_.get("start", 0))
    obj_end = int(object_.get("end", 0))

    subj_range = _word_range(starts, ends, subj_start, subj_end)
    obj_range = _word_range(starts, ends, obj_start, obj_end)

    subj_display = subject_name or str(subject.get("mention", ""))
    obj_display = object_name or str(object_.get("mention", ""))

    marks = [
        (
            subj_range[0],
            subj_range[1],
            subject_type,
            subj_display,
            "SUBJ",
        ),
        (
            obj_range[0],
            obj_range[1],
            object_type,
            obj_display,
            "OBJ",
        ),
    ]
    # Sắp xếp: theo `word_start` tăng dần; khi trùng `word_start` thì span
    # **dài hơn** đứng trước (để marker ngoài bao trọn marker trong).
    marks.sort(key=lambda item: (item[0], -item[1]))

    # Ngân sách subword: trừ 1 token `<s>` + 3 token `</s>`.
    budget = max(8, max_len - 4)

    subj_ids = _build_segment_ids(tokenizer, tokenize(subj_display)[0])
    obj_ids = _build_segment_ids(tokenizer, tokenize(obj_display)[0])
    subj_ids = subj_ids[:mention_max_subwords]
    obj_ids = obj_ids[:mention_max_subwords]

    low = min(subj_range[0], obj_range[0])
    high = max(subj_range[1], obj_range[1])

    # Thu hẹp cửa sổ ngữ cảnh cho tới khi đoạn câu vừa ngân sách.
    sent_ids: list[int] = []
    for context in (context_words, 32, 16, 8, 0):
        window_low = max(0, low - context)
        window_high = min(len(tokens), high + context)
        words = _marked_sentence_words(tokens, marks, window_low, window_high)
        sent_ids = _build_segment_ids(tokenizer, words)
        remaining = budget - len(subj_ids) - len(obj_ids)
        if len(sent_ids) <= remaining or context == 0:
            break

    remaining = max(0, budget - len(subj_ids) - len(obj_ids))
    sent_ids = sent_ids[:remaining]

    input_ids = [
        tokenizer.cls_token_id,
        *subj_ids,
        tokenizer.sep_token_id,
        *sent_ids,
        tokenizer.sep_token_id,
        *obj_ids,
        tokenizer.sep_token_id,
    ]
    return input_ids, [1] * len(input_ids)


# ---------------------------------------------------------------------------
# Gom nhãn theo input
# ---------------------------------------------------------------------------


def group_slots(
    records: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Gom các slot của `re_train.jsonl` theo input ``(sentence, subj, obj)``.

    Mỗi input giữ:
    - ``slots``: map ``relation`` → ``"POSITIVE"``/``"NEGATIVE"``;
    - ``gold_relations``: tập quan hệ POSITIVE;
    - ``masked_relations``: tập quan hệ chưa có slot.

    Args:
        records: Record theo câu của `re_train.jsonl`.

    Returns:
        Dict ``key`` → thông tin input.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        sentence_id = str(record.get("sentence_id", ""))
        text = str(record.get("text", ""))
        for pair in record.get("pairs") or []:
            subject = pair.get("subject") or {}
            object_ = pair.get("object") or {}
            subject_id = str(subject.get("entity_id", ""))
            object_id = str(object_.get("entity_id", ""))
            relation = str(pair.get("relation", ""))
            label = str(pair.get("label", ""))
            if relation not in LABEL2ID:
                continue
            key = f"{sentence_id}|{subject_id}|{object_id}"
            entry = grouped.get(key)
            if entry is None:
                entry = {
                    "key": key,
                    "sentence_id": sentence_id,
                    "doc_id": str(record.get("doc_id", "")),
                    "page_id": int(record.get("page_id", 0) or 0),
                    "split": str(record.get("split", "")),
                    "text": text,
                    "subject": subject,
                    "object": object_,
                    "slots": {},
                }
                grouped[key] = entry
            entry["slots"][relation] = label

    for entry in grouped.values():
        slots: dict[str, str] = entry["slots"]
        gold = sorted(rel for rel, label in slots.items() if label == "POSITIVE")
        entry["gold_relations"] = gold
        entry["masked_relations"] = sorted(
            relation for relation in RELATION_ORDER if relation not in slots
        )
    return grouped


def build_labels(slots: dict[str, str]) -> list[float]:
    """Dựng vector nhãn 19 chiều có mask.

    Args:
        slots: Map ``relation`` → ``"POSITIVE"``/``"NEGATIVE"``.

    Returns:
        Vector 19 chiều: ``1.0`` (POSITIVE), ``0.0`` (NEGATIVE), ``-100.0``
        (quan hệ chưa có slot).
    """
    labels = [IGNORE_VALUE] * NUM_LABELS
    for relation, label in slots.items():
        index = LABEL2ID.get(relation)
        if index is None or index == NA_INDEX:
            continue
        labels[index] = 1.0 if label == "POSITIVE" else 0.0
    labels[NA_INDEX] = 0.0 if any(
        label == "POSITIVE" for label in slots.values()
    ) else 1.0
    return labels


def build_examples(
    grouped: dict[str, dict[str, Any]],
    tokenizer: WordTokenizer,
    *,
    max_len: int = 256,
    context_words: int = 48,
    drop_self_loops: bool = True,
) -> list[ReExample]:
    """Sinh danh sách mẫu đã mã hoá từ các input đã gom.

    Args:
        grouped: Kết quả của `group_slots`.
        tokenizer: `WordTokenizer`.
        max_len: Độ dài tối đa.
        context_words: Số word ngữ cảnh mỗi bên.
        drop_self_loops: Bỏ input có subject và object là **cùng** entity
            (self-loop — không phải quan hệ hợp lệ trong KG).

    Returns:
        Danh sách `ReExample`.
    """
    examples: list[ReExample] = []
    dropped_self_loops = 0
    for entry in grouped.values():
        subject = entry["subject"]
        object_ = entry["object"]
        if drop_self_loops and subject.get("entity_id") == object_.get("entity_id"):
            dropped_self_loops += 1
            continue
        input_ids, attention_mask = encode_pair(
            tokenizer,
            entry["text"],
            subject,
            object_,
            str(subject.get("type", UNKNOWN_TYPE)),
            str(object_.get("type", UNKNOWN_TYPE)),
            subject_name=str(subject.get("display_name", "")),
            object_name=str(object_.get("display_name", "")),
            max_len=max_len,
            context_words=context_words,
        )
        if not input_ids:
            continue
        examples.append(
            ReExample(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=build_labels(entry["slots"]),
                key=entry["key"],
                sentence_id=entry["sentence_id"],
                doc_id=entry["doc_id"],
                page_id=entry["page_id"],
                split=entry["split"],
                text=entry["text"],
                subject_entity_id=str(subject.get("entity_id", "")),
                object_entity_id=str(object_.get("entity_id", "")),
                subject_mention=str(subject.get("mention", "")),
                object_mention=str(object_.get("mention", "")),
                subject_type=str(subject.get("type", UNKNOWN_TYPE)),
                object_type=str(object_.get("type", UNKNOWN_TYPE)),
                gold_relations=list(entry["gold_relations"]),
                masked_relations=list(entry["masked_relations"]),
                slot_labels=dict(entry["slots"]),
            )
        )
    if dropped_self_loops:
        logger.info("Bỏ %d input self-loop (subject == object)", dropped_self_loops)
    return examples


def example_to_dict(example: ReExample) -> dict[str, Any]:
    """Chuyển `ReExample` sang dict để ghi JSONL.

    Args:
        example: Mẫu đã mã hoá.

    Returns:
        Dict record.
    """
    return {
        "input_ids": example.input_ids,
        "attention_mask": example.attention_mask,
        "labels": example.labels,
        "key": example.key,
        "sentence_id": example.sentence_id,
        "doc_id": example.doc_id,
        "page_id": example.page_id,
        "split": example.split,
        "text": example.text,
        "subject_entity_id": example.subject_entity_id,
        "object_entity_id": example.object_entity_id,
        "subject_mention": example.subject_mention,
        "object_mention": example.object_mention,
        "subject_type": example.subject_type,
        "object_type": example.object_type,
        "gold_relations": example.gold_relations,
        "masked_relations": example.masked_relations,
        "slot_labels": example.slot_labels,
    }


def example_from_dict(record: dict[str, Any]) -> ReExample:
    """Khôi phục `ReExample` từ dict (đọc lại artifact đã mã hoá).

    Args:
        record: Dict record.

    Returns:
        `ReExample`.
    """
    return ReExample(
        input_ids=list(record.get("input_ids") or []),
        attention_mask=list(record.get("attention_mask") or []),
        labels=[float(value) for value in record.get("labels") or []],
        key=str(record.get("key", "")),
        sentence_id=str(record.get("sentence_id", "")),
        doc_id=str(record.get("doc_id", "")),
        page_id=int(record.get("page_id", 0) or 0),
        split=str(record.get("split", "")),
        text=str(record.get("text", "")),
        subject_entity_id=str(record.get("subject_entity_id", "")),
        object_entity_id=str(record.get("object_entity_id", "")),
        subject_mention=str(record.get("subject_mention", "")),
        object_mention=str(record.get("object_mention", "")),
        subject_type=str(record.get("subject_type", UNKNOWN_TYPE)),
        object_type=str(record.get("object_type", UNKNOWN_TYPE)),
        gold_relations=list(record.get("gold_relations") or []),
        masked_relations=list(record.get("masked_relations") or []),
        slot_labels=dict(record.get("slot_labels") or {}),
    )


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc file JSONL, bỏ qua dòng rỗng.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng record (dict).
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """Ghi danh sách record ra JSONL (UTF-8, không BOM, 1 record/dòng).

    Args:
        path: Đường dẫn đích.
        records: Iterable record.

    Returns:
        Số record đã ghi.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count


def prepare_grouped(
    records: Iterable[dict[str, Any]],
    types: dict[str, str],
    names: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Gom slot và gắn type KG cho mỗi đầu của cặp.

    Args:
        records: Record theo câu của `re_train.jsonl`.
        types: Bảng ``entity_id`` → type KG.
        names: Bảng ``entity_id`` → tên hiển thị chuẩn.

    Returns:
        Dict ``key`` → thông tin input (đã có ``type``/``display_name`` cho
        subject/object).
    """
    grouped = group_slots(records)
    for entry in grouped.values():
        for side in ("subject", "object"):
            entity_id = str(entry[side].get("entity_id", ""))
            entry[side]["type"] = resolve_entity_type(entity_id, types)
            display = names.get(entity_id, "")
            if not display:
                display = str(entry[side].get("name", "") or "")
            if not display:
                display = str(entry[side].get("mention", "") or "")
            entry[side]["display_name"] = display
    return grouped


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Mã hoá tập RE của Phase 7 thành đầu vào mô hình (Phase 8)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--train", default=None, help="Đường dẫn re_train.jsonl")
    parser.add_argument("--out", default=None, help="Đường dẫn file mã hoá")
    parser.add_argument("--model", default=None, help="Tên model HuggingFace")
    parser.add_argument("--max-len", type=int, default=None)
    parser.add_argument("--context-words", type=int, default=None)
    args = parser.parse_args(argv)

    config = load_default_config()
    re_config = config.get("re", {})
    convert_config = dict(re_config.get("convert", {}))

    train_path = args.train or re_config.get("train_path", "data/interim/re_train.jsonl")
    out_path = args.out or re_config.get(
        "encoded_path", "data/interim/re_model_input.jsonl"
    )
    model_name = args.model or re_config.get("model_name", "vinai/phobert-base")
    max_len = args.max_len if args.max_len is not None else int(
        convert_config.get("max_len", re_config.get("max_len", 256))
    )
    context_words = (
        args.context_words
        if args.context_words is not None
        else int(convert_config.get("context_words", 48))
    )

    logger.info("Đọc tập RE: %s", train_path)
    records = list(read_jsonl(train_path))
    logger.info("Số câu: %d", len(records))

    types = build_entity_types(
        re_config.get("coref_path", "data/interim/coref_resolved.jsonl"),
        re_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl"),
    )
    logger.info("Bảng type: %d entity", len(types))

    names = build_display_names(
        re_config.get("coref_path", "data/interim/coref_resolved.jsonl"),
        re_config.get("infobox_entities_path", "data/interim/infobox_entities.jsonl"),
    )
    logger.info("Bảng tên hiển thị: %d entity", len(names))

    grouped = prepare_grouped(records, types, names)
    logger.info("Số input (sau khi gom slot): %d", len(grouped))

    tokenizer = load_tokenizer(model_name)
    examples = build_examples(
        grouped, tokenizer, max_len=max_len, context_words=context_words
    )
    logger.info("Số mẫu sau mã hoá: %d", len(examples))

    out_file = resolve_path(out_path)
    count = write_jsonl(out_file, (example_to_dict(example) for example in examples))
    logger.info("Đã ghi %d mẫu ra %s", count, out_file)

    splits = Counter(example.split for example in examples)
    lengths = [len(example.input_ids) for example in examples]
    logger.info(
        "Phân bố tập: %s | độ dài subword: max=%d trung bình=%.1f",
        dict(splits),
        max(lengths) if lengths else 0,
        (sum(lengths) / len(lengths)) if lengths else 0.0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

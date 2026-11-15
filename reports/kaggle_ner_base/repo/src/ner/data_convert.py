"""Chuyển nhãn bạc word-level BIO → subword để huấn luyện NER (Phase 5 — B1).

Vì sao cần module này
--------------------
Nhãn bạc ở `data/interim/ner_silver.jsonl` ở mức **word** (token do
`src.ner.build_silver.tokenize` tách), scheme **BIO** 13 lớp:

    O, B-PERSON, I-PERSON, B-DYNASTY, I-DYNASTY, ... (2 * 6 + 1 = 13)

Mô hình PhoBERT dùng BPE ở mức **subword** (một word có thể thành nhiều
subword, vd "hòa" → "hò@@" + "a"). Huấn luyện token classification đòi nhãn
ở đúng mức subword → module này làm cầu nối.

Quy tắc ánh xạ nhãn (theo `docs/09` §Phase 5)
---------------------------------------------
- Subword **đầu tiên** của một word mang **đúng** nhãn của word (`B-X` hoặc `O`).
- Các subword **còn lại** của word đó mang `I-X` nếu word có nhãn `X`,
  ngược lại `O`.
- Subword đặc biệt (`<s>`, `</s>`, `<pad>`) → nhãn `-100` (bị ignore khi loss).

Vì sao dùng **slow tokenizer** (`PhobertTokenizer`), không dùng fast (D-040)
---------------------------------------------------------------------------
Đo thực tế trên `vinai/phobert-base`:

| Tokenizer | Vocab | Embedding model | Vấn đề |
|---|---|---|---|
| `AutoTokenizer` (slow, `PhobertTokenizer`) | 64.001 | 64.001 | ✅ khớp |
| `PreTrainedTokenizerFast` (file `tokenizer.json` của repo) | **66.119** | 64.001 | ❌ **2.118 token có id ≥ 64.001 → `IndexError: index out of range in self`** |

File `tokenizer.json` đi kèm repo `vinai/phobert-base` được sinh từ BPE
**khác** (dùng `</w>` thay vì `@@` của PhoBERT) và chứa 2.118 token thừa vượt
quá kích thước embedding → mọi câu có từ đó sẽ crash khi suy luận.

→ Module này dùng **slow tokenizer** (`AutoTokenizer.from_pretrained`) làm nguồn
sự thật vocab, và tự **token hóa từng word** bằng `tokenizer.bpe(word)`
(có cache → nhanh: ~660.000 word/s, toàn corpus ~10 giây).

Vì sao token hóa theo **word**, không theo raw text
---------------------------------------------------
Đo thực tế (2.000 câu): token hóa `words` với `is_split_into_words=True` khác
token hóa `text` thô ở **1.883/2.000** câu (vd "số," thành "số" + "," khi
token hóa thô, nhưng gộp lại khi tách theo word). Nếu huấn luyện theo word
mà suy luận theo raw text → **lệch phân bố subword**, mô hình suy luận kém hơn
mức thật.

→ Cả huấn luyện lẫn suy luận đều token hóa theo **word**.
Offset ký tự cho suy luận được suy ra từ `src.ner.build_silver.tokenize`
(cùng hàm đã sinh ra `tokens` trong artifact nhãn bạc) → offset luôn khớp
với `text` và `text[start:end] == span_text`.

Cửa sổ trượt (sliding window)
-----------------------------
91/186.960 câu vượt 256 word (max 804). Module cung cấp `subword_windows()`
để chia **mức subword** (sau khi mã hóa) thành các cửa sổ có chồng lấn —
dùng chung cho cả huấn luyện lẫn suy luận → hai tầng nhìn thấy cùng
cách chia, đảm bảo số liệu đánh giá nhất quán.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from src.common.logger import get_logger
from src.common.schemas import NER_LABELS

logger = get_logger(__name__)

#: 13 lớp theo thứ tự cố định: ``O`` trước, rồi từng cặp ``B-``/``I-``.
#: Thứ tự này là **bất biến** — đã lưu trong `config.json` của model nên
#: nạp lại checkpoint luôn khớp.
LABEL_LIST: tuple[str, ...] = (
    "O",
    *(f"B-{label}" for label in NER_LABELS),
    *(f"I-{label}" for label in NER_LABELS),
)

#: Số lớp = 2 * 6 nhãn + 1 (``O``) = 13 (D-031 — **không** phải 25).
NUM_LABELS: int = len(LABEL_LIST)

#: Ánh xạ nhãn → id.
LABEL2ID: dict[str, int] = {label: index for index, label in enumerate(LABEL_LIST)}

#: Ánh xạ id → nhãn.
ID2LABEL: dict[int, str] = {index: label for label, index in LABEL2ID.items()}

#: Nhãn bị ignore khi tính loss (padding + subword đặc biệt).
IGNORE_INDEX: int = -100


class WordTokenizer:
    """Bọc tokenizer PhoBERT để token hóa **theo word**.

    Dùng slow tokenizer (`PhobertTokenizer`) vì fast tokenizer đi kèm repo
    `vinai/phobert-base` có vocab **66.119** token ≠ kích thước embedding
    **64.001** → sinh id vượt kích thước và gây `IndexError` khi suy luận
    (D-040).

    Attributes:
        tokenizer: Tokenizer gốc (slow).
        vocab_size: Kích thước vocab thực của tokenizer.
        cache: Cache word → subword để không token hóa lại.
    """

    def __init__(self, tokenizer: Any) -> None:
        """Khởi tạo wrapper.

        Args:
            tokenizer: Tokenizer slow của PhoBERT.
        """
        self.tokenizer = tokenizer
        self.vocab_size = len(tokenizer)
        self.cache: dict[str, list[int]] = {}

    @property
    def cls_token_id(self) -> int:
        """Id token ``<s>``.

        Returns:
            Id của ``<s>``.
        """
        return int(self.tokenizer.cls_token_id)

    @property
    def sep_token_id(self) -> int:
        """Id token ``</s>``.

        Returns:
            Id của ``</s>``.
        """
        return int(self.tokenizer.sep_token_id)

    @property
    def pad_token_id(self) -> int:
        """Id token ``<pad>``.

        Returns:
            Id của ``<pad>``.
        """
        return int(self.tokenizer.pad_token_id)

    def tokenize_word(self, word: str) -> list[int]:
        """Token hóa một word thành danh sách id subword.

        Args:
            word: Một word (đã tách theo `src.ner.build_silver.tokenize`).

        Returns:
            Danh sách id subword (có thể rỗng nếu word rỗng).
        """
        if not word:
            return []
        cached = self.cache.get(word)
        if cached is not None:
            return cached
        tokens = self.tokenizer.bpe(word).split(" ")
        ids = self.tokenizer.convert_tokens_to_ids(tokens)
        self.cache[word] = ids
        return ids

    def save_pretrained(self, save_directory: str | Path) -> None:
        """Lưu tokenizer xuống thư mục (vocab + bpe.codes).

        Args:
            save_directory: Thư mục đích.
        """
        target = Path(save_directory)
        target.mkdir(parents=True, exist_ok=True)
        self.tokenizer.save_pretrained(str(target))


def load_tokenizer(model_name: str) -> WordTokenizer:
    """Nạp tokenizer cho PhoBERT.

    Args:
        model_name: Tên model trên HuggingFace, vd ``"vinai/phobert-base"``.

    Returns:
        `WordTokenizer` bọc slow tokenizer.

    Raises:
        RuntimeError: Nếu kích thước vocab **vượt quá** kích thước
            embedding của model — dấu hiệu dùng nhầm tokenizer (D-040).
    """
    from transformers import AutoConfig, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    try:
        config = AutoConfig.from_pretrained(model_name)
        model_vocab = int(getattr(config, "vocab_size", len(tokenizer)))
    except Exception:  # pragma: no cover - config không đọc được thì bỏ qua
        model_vocab = len(tokenizer)

    if len(tokenizer) > model_vocab:
        raise RuntimeError(
            f"Tokenizer '{model_name}' có vocab {len(tokenizer)} > vocab_size "
            f"của model ({model_vocab}) → id vượt kích thước embedding. "
            "Dùng slow tokenizer (D-040)."
        )

    return WordTokenizer(tokenizer)


@dataclass(slots=True)
class EncodedExample:
    """Một mẫu đã mã hóa ở mức subword.

    Attributes:
        input_ids: Id subword (đã thêm ``<s>``/``</s>``).
        attention_mask: Mặt nạ attention.
        labels: Nhãn id ở mức subword (``-100`` cho vị trí bị ignore).
        word_ids: Chỉ số word gốc của từng subword (``-1`` cho subword đặc biệt).
        sentence_id: Id câu nguồn.
        doc_id: Id bài nguồn.
        text: Văn bản câu.
        word_start: Chỉ số word đầu tiên của cửa sổ trong câu.
        word_end: Chỉ số word cuối (exclusive) của cửa sổ trong câu.
    """

    input_ids: list[int]
    attention_mask: list[int]
    labels: list[int]
    word_ids: list[int]
    sentence_id: str
    doc_id: str
    text: str
    word_start: int
    word_end: int
    n_words: int = 0


def subword_windows(
    n_subwords: int,
    max_len: int,
    stride: int,
) -> list[tuple[int, int]]:
    """Chia chuỗi subword thành các cửa sổ có chồng lấn.

    Cửa sổ đã trừ sẵn 2 vị trí cho ``<s>``/``</s>``.

    Args:
        n_subwords: Tổng số subword (không kể ``<s>``/``</s>``).
        max_len: Độ dài tối đa **kể cả** ``<s>``/``</s>``.
        stride: Bước nhảy giữa hai cửa sổ.

    Returns:
        Danh sách cặp ``(start, end)`` (end exclusive) trong không gian subword.

    Raises:
        ValueError: Nếu ``max_len`` <= 2 hoặc ``stride`` không dương.
    """
    if max_len <= 2:
        raise ValueError(f"max_len phải > 2, nhận {max_len}")
    if stride <= 0:
        raise ValueError(f"stride phải dương, nhận {stride}")

    window_size = max_len - 2
    if n_subwords <= window_size:
        return [(0, n_subwords)]

    windows: list[tuple[int, int]] = []
    start = 0
    while start < n_subwords:
        end = min(start + window_size, n_subwords)
        windows.append((start, end))
        if end >= n_subwords:
            break
        start += stride
    return windows


def encode_words(
    tokenizer: WordTokenizer,
    tokens: Sequence[str],
    labels: Sequence[str],
) -> dict[str, list]:
    """Mã hóa word + nhãn BIO word-level → subword (không thêm special token).

    Args:
        tokenizer: `WordTokenizer` bọc slow tokenizer.
        tokens: Danh sách word của câu.
        labels: Nhãn BIO word-level, cùng độ dài với ``tokens``.

    Returns:
        Dict gồm ``input_ids``, ``attention_mask``, ``labels`` (id),
        ``word_ids`` (``-1`` cho subword đặc biệt).

    Raises:
        ValueError: Nếu độ dài ``tokens`` và ``labels`` không bằng nhau.
    """
    if len(tokens) != len(labels):
        raise ValueError(
            f"Độ dài tokens ({len(tokens)}) != labels ({len(labels)})"
        )
    if not tokens:
        return {"input_ids": [], "attention_mask": [], "labels": [], "word_ids": []}

    input_ids: list[int] = []
    word_ids: list[int] = []
    for word_index, word in enumerate(tokens):
        sub_ids = tokenizer.tokenize_word(word)
        if not sub_ids:
            continue
        input_ids.extend(sub_ids)
        word_ids.extend([word_index] * len(sub_ids))

    sub_labels: list[int] = []
    for position, word_id in enumerate(word_ids):
        word_label = labels[word_id]
        if word_label == "O":
            sub_labels.append(LABEL2ID["O"])
            continue
        prefix, _, entity_type = word_label.partition("-")
        if prefix == "B":
            # Subword đầu của word mang nhãn gốc (B-X).
            if position == 0 or word_ids[position - 1] != word_id:
                sub_labels.append(LABEL2ID[word_label])
            else:
                sub_labels.append(LABEL2ID[f"I-{entity_type}"])
        else:
            # Word đã mang I-X → các subword sau cũng là I-X.
            sub_labels.append(LABEL2ID[f"I-{entity_type}"])

    return {
        "input_ids": input_ids,
        "attention_mask": [1] * len(input_ids),
        "labels": sub_labels,
        "word_ids": word_ids,
    }


def build_examples(
    records: Iterable[dict[str, Any]],
    tokenizer: WordTokenizer,
    *,
    max_len: int = 256,
    stride: int = 64,
) -> list[EncodedExample]:
    """Sinh danh sách mẫu đã mã hóa từ các record nhãn bạc.

    Câu nào vượt ``max_len`` subword sẽ bị chia thành nhiều cửa sổ có
    chồng lấn (stride ``stride``).

    Args:
        records: Record nhãn bạc.
        tokenizer: `WordTokenizer`.
        max_len: Độ dài tối đa (kể cả ``<s>``/``</s>``).
        stride: Bước nhảy giữa hai cửa sổ.

    Returns:
        Danh sách `EncodedExample`.
    """
    cls_id = tokenizer.cls_token_id
    sep_id = tokenizer.sep_token_id

    examples: list[EncodedExample] = []
    for record in records:
        tokens: list[str] = list(record.get("tokens") or [])
        labels: list[str] = list(record.get("labels") or [])
        if not tokens:
            continue
        encoded = encode_words(tokenizer, tokens, labels)
        if not encoded["input_ids"]:
            continue

        sub_ids = encoded["input_ids"]
        sub_labels = encoded["labels"]
        sub_word_ids = encoded["word_ids"]

        for window_start, window_end in subword_windows(len(sub_ids), max_len, stride):
            window_word_ids = sub_word_ids[window_start:window_end]
            valid_words = [w for w in window_word_ids if w is not None and w >= 0]
            word_start = min(valid_words) if valid_words else 0
            word_end = (max(valid_words) + 1) if valid_words else 0

            examples.append(
                EncodedExample(
                    input_ids=[cls_id, *sub_ids[window_start:window_end], sep_id],
                    attention_mask=[1] * (window_end - window_start + 2),
                    labels=[
                        IGNORE_INDEX,
                        *sub_labels[window_start:window_end],
                        IGNORE_INDEX,
                    ],
                    word_ids=[-1, *window_word_ids, -1],
                    sentence_id=str(record.get("sentence_id", "")),
                    doc_id=str(record.get("doc_id", "")),
                    text=str(record.get("text", "")),
                    word_start=word_start,
                    word_end=word_end,
                    n_words=len(tokens),
                )
            )
    return examples


def decode_word_labels(
    logits: Sequence[Sequence[float]],
    word_ids: Sequence[int],
    *,
    num_words: int | None = None,
) -> list[int]:
    """Chuyển logits subword → nhãn id ở mức **word**.

    Với mỗi word, lấy nhãn của **subword đầu tiên** (quy ước chuẩn của
    HuggingFace cho `is_split_into_words=True`).

    Args:
        logits: Logits của mô hình, shape ``(n_subword, num_labels)``.
        word_ids: Chỉ số word của từng subword (``-1``/``None`` cho subword
            đặc biệt).
        num_words: Nếu có, trả về đúng `num_words` phần tử (word chưa có
            dự đoán → ``O``).

    Returns:
        Danh sách nhãn id ứng với từng word, theo thứ tự word xuất hiện.
    """
    best: dict[int, int] = {}
    limit = min(len(logits), len(word_ids))
    for position in range(limit):
        word_id = word_ids[position]
        if word_id is None or word_id < 0:
            continue
        if word_id in best:
            continue
        row = logits[position]
        best[word_id] = max(range(len(row)), key=lambda index: row[index])

    if num_words is None:
        return [best[word_id] for word_id in sorted(best)]

    result = [LABEL2ID["O"]] * num_words
    for word_id, label_id in best.items():
        if 0 <= word_id < num_words:
            result[word_id] = label_id
    return result


def gold_word_labels(labels: Sequence[str]) -> list[int]:
    """Chuyển nhãn BIO word-level → id.

    Args:
        labels: Nhãn BIO ở mức word.

    Returns:
        Danh sách id nhãn.

    Raises:
        KeyError: Nếu có nhãn không nằm trong 13 lớp.
    """
    result: list[int] = []
    for label in labels:
        if label not in LABEL2ID:
            raise KeyError(f"Nhãn không hợp lệ: {label!r}")
        result.append(LABEL2ID[label])
    return result


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


def load_split_page_ids(splits_path: str | Path, split: str) -> set[int]:
    """Nạp danh sách `page_id` của một tập.

    Args:
        splits_path: Đường dẫn `data/splits/splits.json`.
        split: Tên tập (``train``/``dev``/``test``).

    Returns:
        Tập `page_id` (int).

    Raises:
        KeyError: Nếu tập không tồn tại trong file splits.
    """
    payload = json.loads(Path(splits_path).read_text(encoding="utf-8"))
    if split not in payload:
        raise KeyError(f"Tập {split!r} không có trong {splits_path}")
    return {int(page_id) for page_id in payload[split]}


def iter_silver_by_split(
    silver_path: str | Path,
    splits_path: str | Path,
    split: str,
) -> Iterator[dict[str, Any]]:
    """Lọc các record nhãn bạc thuộc một tập.

    Args:
        silver_path: Đường dẫn `ner_silver.jsonl`.
        splits_path: Đường dẫn `splits.json`.
        split: Tên tập.

    Yields:
        Record nhãn bạc thuộc tập.
    """
    page_ids = load_split_page_ids(splits_path, split)
    for record in read_jsonl(silver_path):
        if int(record.get("page_id", -1)) in page_ids:
            yield record


def merge_window_predictions(
    predictions: Iterable[tuple[int, int, int]],
    n_words: int,
) -> list[int]:
    """Gộp nhãn dự đoán của nhiều cửa sổ thành nhãn ở mức câu.

    Với mỗi word, lấy nhãn của cửa sổ **đầu tiên** có dự đoán cho word đó
    (cửa sổ sau chỉ dùng để bổ sung word chưa được dự đoán).

    Args:
        predictions: Chuỗi ``(word_id, label_id, n_words)``.
        n_words: Tổng số word của câu.

    Returns:
        Danh sách nhãn id ứng với từng word của câu.
    """
    result = [LABEL2ID["O"]] * n_words
    seen: set[int] = set()
    for word_id, label_id, _total in predictions:
        if word_id in seen or not (0 <= word_id < n_words):
            continue
        seen.add(word_id)
        result[word_id] = label_id
    return result

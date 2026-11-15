"""Test cho `src/ner/data_convert.py` — chuyển nhãn bạc word-level → subword (Phase 5).

Bao phủ các bất biến quan trọng:
- Scheme BIO 13 lớp (D-031), không phải 25.
- Ánh xạ nhãn word → subword đúng quy tắc (subword đầu giữ nhãn gốc).
- Cửa sổ trượt phủ hết câu dài, không sót word.
- Tokenizer nạp được có vocab khớp embedding (D-040).
"""

from __future__ import annotations

import pytest

from src.common.schemas import NER_LABELS
from src.ner.data_convert import (
    IGNORE_INDEX,
    LABEL2ID,
    LABEL_LIST,
    NUM_LABELS,
    WordTokenizer,
    build_examples,
    decode_word_labels,
    encode_words,
    gold_word_labels,
    load_tokenizer,
    subword_windows,
)


class DummyTokenizer:
    """Tokenizer giả: mỗi word → 1 subword, trừ word kết thúc bằng 'x' → 2."""

    cls_token_id = 0
    sep_token_id = 2
    pad_token_id = 1

    def __init__(self) -> None:
        self.calls = 0

    def tokenize_word(self, word: str) -> list[int]:
        """Trả id subword giả.

        Args:
            word: Word cần token hóa.

        Returns:
            Danh sách id.
        """
        self.calls += 1
        if word.endswith("x"):
            return [100, 101]
        return [200]


def test_label_list_is_bio_13_classes() -> None:
    """Scheme phải là BIO 13 lớp: O + 6 nhãn × (B, I)."""
    assert NUM_LABELS == 13
    assert len(LABEL_LIST) == 13
    assert LABEL_LIST[0] == "O"
    assert set(NER_LABELS) == {"PERSON", "DYNASTY", "EVENT", "LOCATION", "TIME", "TITLE"}
    for label in NER_LABELS:
        assert f"B-{label}" in LABEL_LIST
        assert f"I-{label}" in LABEL_LIST
    # KHÔNG phải BIOES 25 lớp (D-031).
    assert not any(label.endswith(("-E", "-S")) for label in LABEL_LIST)


def test_label2id_is_bijective() -> None:
    """Ánh xạ nhãn ↔ id phải 1-1."""
    assert len(LABEL2ID) == NUM_LABELS
    assert set(LABEL2ID.values()) == set(range(NUM_LABELS))


def test_encode_words_maps_bio_labels() -> None:
    """Subword đầu giữ nhãn gốc; subword sau của word có nhãn thành I-X."""
    tokenizer = DummyTokenizer()
    tokens = ["Lê", "Lợi", "là"]
    labels = ["B-PERSON", "I-PERSON", "O"]
    encoded = encode_words(tokenizer, tokens, labels)

    assert encoded["input_ids"] == [200, 200, 200]
    assert encoded["labels"] == [
        LABEL2ID["B-PERSON"],
        LABEL2ID["I-PERSON"],
        LABEL2ID["O"],
    ]
    assert encoded["word_ids"] == [0, 1, 2]


def test_encode_words_multi_subword_word() -> None:
    """Word có nhiều subword: subword đầu = B-X, còn lại = I-X."""
    tokenizer = DummyTokenizer()
    tokens = ["Lê", "Lợix"]
    labels = ["B-PERSON", "B-PERSON"]
    encoded = encode_words(tokenizer, tokens, labels)

    assert encoded["input_ids"] == [200, 100, 101]
    # Word 0: 1 subword → B-PERSON.
    # Word 1: 2 subword → subword đầu B-PERSON, subword sau I-PERSON.
    assert encoded["labels"] == [
        LABEL2ID["B-PERSON"],
        LABEL2ID["B-PERSON"],
        LABEL2ID["I-PERSON"],
    ]
    assert encoded["word_ids"] == [0, 1, 1]


def test_encode_words_multi_subword_without_label() -> None:
    """Word không nhãn có nhiều subword → tất cả đều là O."""
    tokenizer = DummyTokenizer()
    encoded = encode_words(tokenizer, ["xox"], ["O"])
    assert encoded["labels"] == [LABEL2ID["O"], LABEL2ID["O"]]


def test_encode_words_length_mismatch_raises() -> None:
    """tokens và labels lệch độ dài → ValueError."""
    with pytest.raises(ValueError):
        encode_words(DummyTokenizer(), ["a", "b"], ["O"])


def test_encode_words_empty() -> None:
    """Câu rỗng → kết quả rỗng."""
    encoded = encode_words(DummyTokenizer(), [], [])
    assert encoded["input_ids"] == []


def test_subword_windows_single() -> None:
    """Câu ngắn → đúng 1 cửa sổ."""
    assert subword_windows(10, 256, 64) == [(0, 10)]


def test_subword_windows_covers_all() -> None:
    """Cửa sổ trượt phải phủ hết subword, không sót."""
    windows = subword_windows(1000, 100, 30)
    assert windows[0][0] == 0
    assert windows[-1][1] == 1000
    # Các cửa sổ liên tiếp, có overlap.
    for previous, current in zip(windows, windows[1:]):
        assert current[0] < previous[1]


def test_subword_windows_invalid_params() -> None:
    """Tham số không hợp lệ → ValueError."""
    with pytest.raises(ValueError):
        subword_windows(10, 2, 64)
    with pytest.raises(ValueError):
        subword_windows(10, 256, 0)


def test_decode_word_labels_uses_first_subword() -> None:
    """Decode lấy nhãn của subword đầu của mỗi word."""
    # word_ids: vị trí 0 là subword đặc biệt (bị bỏ qua).
    # word 0 nằm ở vị trí 1, word 1 nằm ở vị trí 2 và 3 (2 subword).
    word_ids = [-1, 0, 1, 1]
    logits = [
        [9, 0],          # subword đặc biệt (bị bỏ qua)
        [0, 9],          # word 0 → id 1
        [9, 0],          # word 1 subword đầu → id 0
        [0, 9],          # word 1 subword sau (bị bỏ qua)
    ]
    assert decode_word_labels(logits, word_ids) == [1, 0]


def test_decode_word_labels_with_num_words_pads() -> None:
    """`num_words` ép độ dài kết quả, word chưa dự đoán → O."""
    word_ids = [-1, 0, -1]
    logits = [[0, 0], [0, 9], [0, 0]]
    result = decode_word_labels(logits, word_ids, num_words=3)
    assert result == [1, LABEL2ID["O"], LABEL2ID["O"]]


def test_gold_word_labels_invalid() -> None:
    """Nhãn ngoài 13 lớp → KeyError."""
    with pytest.raises(KeyError):
        gold_word_labels(["S-PERSON"])


def test_build_examples_adds_special_tokens() -> None:
    """Mẫu phải có `<s>`/`</s>` và nhãn -100 ở 2 vị trí đó."""
    tokenizer = DummyTokenizer()
    record = {
        "sentence_id": "s1_0_0",
        "doc_id": "doc_1",
        "text": "Lê Lợi",
        "tokens": ["Lê", "Lợi"],
        "labels": ["B-PERSON", "I-PERSON"],
    }
    examples = build_examples([record], tokenizer, max_len=256)
    assert len(examples) == 1
    example = examples[0]
    assert example.input_ids[0] == tokenizer.cls_token_id
    assert example.input_ids[-1] == tokenizer.sep_token_id
    assert example.labels[0] == IGNORE_INDEX
    assert example.labels[-1] == IGNORE_INDEX
    assert example.n_words == 2
    assert example.word_start == 0 and example.word_end == 2
    assert example.sentence_id == "s1_0_0"


def test_build_examples_splits_long_sentence() -> None:
    """Câu dài phải được chia thành nhiều cửa sổ phủ hết word."""
    tokenizer = DummyTokenizer()
    n_words = 40
    record = {
        "sentence_id": "s2_0_0",
        "doc_id": "doc_2",
        "text": "x " * n_words,
        "tokens": ["x"] * n_words,
        "labels": ["O"] * n_words,
    }
    examples = build_examples([record], tokenizer, max_len=10, stride=4)
    assert len(examples) > 1
    covered = set()
    for example in examples:
        covered.update(range(example.word_start, example.word_end))
    assert covered == set(range(n_words))


@pytest.mark.slow
def test_load_tokenizer_vocab_matches_model() -> None:
    """Tokenizer nạp được phải có vocab ≤ vocab_size của model (D-040)."""
    from transformers import AutoConfig

    model_name = "vinai/phobert-base"
    tokenizer = load_tokenizer(model_name)
    config = AutoConfig.from_pretrained(model_name)
    assert tokenizer.vocab_size <= int(config.vocab_size)
    assert isinstance(tokenizer, WordTokenizer)


@pytest.mark.slow
def test_real_tokenizer_ids_in_range() -> None:
    """Mọi id sinh ra cho word tiếng Việt phải nằm trong kích thước vocab."""
    from transformers import AutoConfig

    model_name = "vinai/phobert-base"
    tokenizer = load_tokenizer(model_name)
    config = AutoConfig.from_pretrained(model_name)
    limit = int(config.vocab_size)
    for word in ["triển", "Trần", "thành", "phố", "Nguyễn", "Thái", "Tổ", "hòa"]:
        ids = tokenizer.tokenize_word(word)
        assert ids, f"word {word!r} không token hóa được"
        assert all(0 <= value < limit for value in ids), (word, ids)

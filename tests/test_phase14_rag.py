"""Test cho tầng truy xuất RAG (Phase 14).

Bao phủ 4 phần:
1. `chunking` — hợp đồng 11 trường, loại đoạn tiêu đề, ánh xạ section.
2. `retriever` — tokenize, BM25, RRF, ngưỡng no-data, `build_context`.
3. `rag_answer` — trích xuất trích dẫn, faithfulness check, no-data.
4. Endpoint `POST /api/ask/rag` — output contract.

Các test dùng **artifact thật** khi có; nếu thiếu thì `pytest.skip` để repo
vẫn test được trên máy không có dữ liệu.
"""

from __future__ import annotations

import json

import pytest

from src.common.config import REPO_ROOT
from src.qa.chunking import CHUNK_FIELDS, build_section_stack, clean_text
from src.qa.rag_answer import (
    NO_DATA_ANSWER,
    extract_citations,
    is_no_data,
)
from src.qa.retriever import (
    BM25Index,
    Chunk,
    build_context,
    strip_accents,
    tokenize,
)

CHUNKS_PATH = REPO_ROOT / "data" / "interim" / "chunks.jsonl"
INDEX_PATH = REPO_ROOT / "data" / "interim" / "bm25_index.npz"


# ----------------------------------------------------------------------
# 1. chunking
# ----------------------------------------------------------------------


def test_chunk_fields_contract() -> None:
    """Hợp đồng chunk có đúng 11 trường."""
    assert len(CHUNK_FIELDS) == 11
    assert CHUNK_FIELDS[0] == "chunk_id"
    assert CHUNK_FIELDS[-1] == "kind"
    assert "entity_ids" in CHUNK_FIELDS
    assert "section_path" in CHUNK_FIELDS


def test_clean_text_removes_html_entities() -> None:
    """Bỏ HTML entity + gọn khoảng trắng."""
    assert clean_text("3.359,82&nbsp;km²") == "3.359,82 km²"
    assert clean_text("  a   b  ") == "a b"
    assert clean_text("") == ""


def test_build_section_stack() -> None:
    """Dựng `section_path` lồng nhau theo level tiêu đề."""
    paragraphs = [
        {"text": "Mở đầu bài", "heading": False},
        {"text": "Địa lý", "heading": True},
        {"text": "Vị trí", "heading": True},
        {"text": "Nội dung vị trí", "heading": False},
    ]
    headings = [
        {"level": 2, "title": "Địa lý", "plain_title": "Địa lý"},
        {"level": 3, "title": "Vị trí", "plain_title": "Vị trí"},
    ]
    result = build_section_stack(paragraphs, headings)
    assert result[0] == ("", "")
    assert result[1] == ("Địa lý", "Địa lý")
    assert result[2] == ("Vị trí", "Địa lý > Vị trí")
    assert result[3] == ("Vị trí", "Địa lý > Vị trí")


@pytest.mark.skipif(not CHUNKS_PATH.exists(), reason="Thiếu chunks.jsonl")
def test_chunks_file_contract() -> None:
    """File chunks thật đúng hợp đồng + không chứa đoạn tiêu đề."""
    count = 0
    with CHUNKS_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            assert list(record.keys()) == list(CHUNK_FIELDS)
            assert record["kind"] != "heading"
            assert record["chunk_id"].startswith("chunk_")
            assert record["text"].strip()
            count += 1
            if count >= 500:
                break
    assert count == 500


# ----------------------------------------------------------------------
# 2. retriever
# ----------------------------------------------------------------------


def test_strip_accents() -> None:
    """Bỏ dấu tiếng Việt."""
    assert strip_accents("Trần Hưng Đạo") == "tran hung dao"
    assert strip_accents("Đại Việt") == "dai viet"
    assert strip_accents("Lê Lợi") == "le loi"


def test_tokenize_removes_stopwords() -> None:
    """Loại stopword + từ 1 ký tự."""
    tokens = tokenize("Ai là con của Trần Nhân Tông")
    assert "con" in tokens
    assert "tran" in tokens
    assert "nhan" in tokens
    assert "cua" not in tokens
    assert "la" not in tokens


def _make_chunk(index: int, title: str, text: str, section: str = "") -> Chunk:
    """Tạo chunk test.

    Args:
        index: Chỉ số.
        title: Tên bài.
        text: Nội dung.
        section: Mục.

    Returns:
        Chunk.
    """
    return Chunk(
        chunk_id=f"chunk_doc_{index}",
        doc_id=f"doc_{index}",
        page_id=index,
        title=title,
        section=section,
        section_path=section,
        text=text,
        source_url=f"https://vi.wikipedia.org/wiki/{index}",
    )


def test_bm25_prefers_title_match() -> None:
    """BM25 ưu tiên chunk có title khớp (kiểm tra trọng số trường)."""
    chunks = [
        _make_chunk(0, "Trận Bạch Đằng (1288)", "một đoạn về cuộc chiến"),
        _make_chunk(1, "Hà Nội", "đoạn về thủ đô và các địa danh khác"),
        _make_chunk(2, "Lý Thường Kiệt", "đoạn về một vị vua nhà Lý"),
    ]
    index = BM25Index.build(
        chunks, field_weights={"title": 3, "section": 2, "body": 1}
    )
    hits = index.search(tokenize("Trận Bạch Đằng"))
    assert hits, "Phải tìm được kết quả"
    assert hits[0][0] == 0


def test_bm25_no_match_returns_empty() -> None:
    """Không từ khoá nào khớp ⇒ không có kết quả."""
    chunks = [_make_chunk(0, "Trận Bạch Đằng (1288)", "nội dung")]
    index = BM25Index.build(chunks)
    assert index.search(tokenize("zzzqqqxyz")) == []


def test_bm25_index_roundtrip(tmp_path) -> None:
    """Lưu/nạp chỉ mục BM25 cho kết quả giống nhau."""
    chunks = [
        _make_chunk(0, "Trận Bạch Đằng (1288)", "diễn biến trận đánh năm 1288"),
        _make_chunk(1, "Hà Nội", "thủ đô của Việt Nam"),
    ]
    index = BM25Index.build(chunks)
    path = tmp_path / "idx.npz"
    index.save(path, tmp_path / "idx.json")
    loaded = BM25Index.load(path)
    before = index.search(tokenize("Trận Bạch Đằng"))
    after = loaded.search(tokenize("Trận Bạch Đằng"))
    assert [i for i, _ in before] == [i for i, _ in after]


def test_build_context_numbers_citations() -> None:
    """Context đánh số `[n]` khớp với danh sách citations."""
    from src.qa.retriever import RetrievedChunk

    chunks = [
        _make_chunk(0, "A", "nội dung A", "Mục 1"),
        _make_chunk(1, "B", "nội dung B", "Mục 2"),
    ]
    results = [
        RetrievedChunk(chunk=chunks[0], index=0, rrf_score=0.02),
        RetrievedChunk(chunk=chunks[1], index=1, rrf_score=0.01),
    ]
    context, citations = build_context(results)
    assert citations[0]["n"] == 1
    assert citations[1]["n"] == 2
    assert "[1]" in context and "[2]" in context
    assert citations[0]["source_url"].startswith("https://")


def test_build_context_respects_char_budget() -> None:
    """Không vượt ngân sách ký tự (trừ khối đầu tiên)."""
    from src.qa.retriever import RetrievedChunk

    chunks = [_make_chunk(i, f"T{i}", "x" * 500) for i in range(5)]
    results = [
        RetrievedChunk(chunk=chunk, index=index, rrf_score=0.02 - index * 0.001)
        for index, chunk in enumerate(chunks)
    ]
    context, citations = build_context(results, char_budget=700)
    assert len(context) <= 700
    assert len(citations) < 5


@pytest.mark.skipif(not INDEX_PATH.exists(), reason="Thiếu bm25_index.npz")
def test_real_index_top1_is_bach_dang() -> None:
    """Trên index thật: top-1 cho câu "diễn biến trận Bạch Đằng" là bài đúng."""
    from src.qa.retriever import load_chunks

    chunks = load_chunks(CHUNKS_PATH)
    index = BM25Index.load(INDEX_PATH)
    hits = index.search(tokenize("diễn biến trận Bạch Đằng năm 1288"), top_k=5)
    assert hits
    top = chunks[hits[0][0]]
    assert "Bạch Đằng" in top.title


# ----------------------------------------------------------------------
# 3. rag_answer
# ----------------------------------------------------------------------


def test_extract_citations() -> None:
    """Trích số `[n]` từ câu trả lời."""
    assert extract_citations("Trần Hưng Đạo chỉ huy [1] và [2]") == [1, 2]
    assert extract_citations("Không có trích dẫn") == []
    assert extract_citations("[3] rồi [1]") == [1, 3]


def test_is_no_data() -> None:
    """Nhận diện câu "không có trong dữ liệu"."""
    assert is_no_data(NO_DATA_ANSWER)
    assert is_no_data('"Không có trong dữ liệu."')
    assert not is_no_data("Trần Hưng Đạo mất năm 1300 [1]")


def test_prompt_template_has_citation_rule() -> None:
    """Prompt bắt buộc trích dẫn `[n]` + cấm bịa."""
    from src.qa.rag_answer import load_prompt

    prompt = load_prompt()
    assert "[n]" in prompt
    assert "{context}" in prompt
    assert "{question}" in prompt
    assert "{no_data}" in prompt


def test_rag_answerer_no_context_returns_no_data(monkeypatch) -> None:
    """Không có chunk nào ⇒ `not_in_data` và **không** gọi LLM."""
    from src.qa.rag_answer import RagAnswerer

    class _Retriever:
        """Retriever giả — luôn trả rỗng."""

        def retrieve(self, query: str, **_: object) -> list:
            """Trả về danh sách rỗng.

            Args:
                query: Câu hỏi.
                **_: Bỏ qua.

            Returns:
                Danh sách rỗng.
            """
            return []

    class _Client:
        """LLM giả — không được gọi."""

        def complete(self, *args: object, **kwargs: object) -> str:
            """Ném lỗi nếu bị gọi.

            Args:
                *args: Bỏ qua.
                **kwargs: Bỏ qua.

            Raises:
                AssertionError: Luôn.
            """
            raise AssertionError("Không được gọi LLM khi không có context")

    answerer = RagAnswerer(_Retriever(), _Client())
    result = answerer.answer("Câu hỏi không có dữ liệu")
    assert result["status"] == "not_in_data"
    assert result["answer"] == NO_DATA_ANSWER
    assert result["citations"] == []


def test_rag_answerer_retries_when_missing_citation() -> None:
    """Câu trả lời thiếu `[n]` ⇒ retry 1 lần rồi đánh dấu không faithful."""
    from src.qa.rag_answer import RagAnswerer

    class _Retriever:
        """Retriever giả — trả 1 chunk."""

        def retrieve(self, query: str, **_: object) -> list:
            """Trả 1 chunk giả.

            Args:
                query: Câu hỏi.
                **_: Bỏ qua.

            Returns:
                Danh sách 1 chunk.
            """
            return [
                _Retrieved(_make_chunk(0, "A", "nội dung A")),
            ]

    class _Retrieved:
        """Chunk giả có `to_dict`."""

        def __init__(self, chunk: Chunk) -> None:
            """Khởi tạo.

            Args:
                chunk: Chunk.
            """
            self.chunk = chunk
            self.index = 0
            self.rrf_score = 0.02

        def to_dict(self) -> dict:
            """Dict giả.

            Returns:
                Dict rỗng.
            """
            return {}

    calls: list[str] = []

    class _Client:
        """LLM giả — luôn trả về câu không trích dẫn."""

        def complete(self, prompt: str, **_: object) -> str:
            """Ghi lại prompt và trả câu không trích dẫn.

            Args:
                prompt: Nội dung prompt.
                **_: Bỏ qua.

            Returns:
                Câu trả lời không có `[n]`.
            """
            calls.append(prompt)
            return "Câu trả lời không có trích dẫn nào."

    answerer = RagAnswerer(_Retriever(), _Client())
    result = answerer.answer("Câu hỏi")
    assert len(calls) == 2, "Phải retry đúng 1 lần"
    assert result["retries"] == 1
    assert result["faithfulness_ok"] is False


# ----------------------------------------------------------------------
# 4. endpoint
# ----------------------------------------------------------------------


def test_ask_rag_endpoint_contract() -> None:
    """`POST /api/ask/rag` trả đúng output contract."""
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post("/api/ask/rag", json={"question": "diễn biến trận Bạch Đằng"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"found", "not_in_data"}
    assert isinstance(payload["answer"], str) and payload["answer"]
    assert isinstance(payload["citations"], list)
    assert isinstance(payload["context_used"], list)
    assert isinstance(payload["elapsed_ms"], int)


def test_ask_rag_endpoint_rejects_empty_question() -> None:
    """Câu hỏi rỗng ⇒ 422 (validation)."""
    from fastapi.testclient import TestClient

    from backend.app.main import create_app

    client = TestClient(create_app())
    response = client.post("/api/ask/rag", json={"question": ""})
    assert response.status_code == 422

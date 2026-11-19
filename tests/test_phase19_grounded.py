"""Test cho Phase 19 — retrieval đa dạng + retry "không có" + metric mới.

Bao phủ 5 phần:
1. `retriever` — cap chunk/section, cap chunk/doc, boost tiêu đề, boost
   section, phạt section nhiễu.
2. `rag_answer` — retry "không có" khi context **có** dữ liệu; **không**
   retry khi context rỗng.
3. `hybrid` — retry "không có" tương tự.
4. `evaluate_rag` — `context_has_gold` + metric `abstain_with_evidence`.
5. `build_qa_set` — gom theo `(doc_id, section_path)`, không shuffle phá sort,
   `no_data` là lịch sử hậu-1945.
"""

from __future__ import annotations

import json

import pytest

from src.common.config import REPO_ROOT
from src.qa.rag_answer import NO_DATA_ANSWER, is_no_data
from src.qa.retriever import Chunk, Retriever

QA_V1 = REPO_ROOT / "data" / "eval" / "qa_rag_250.jsonl"
QA_V2 = REPO_ROOT / "data" / "eval" / "qa_rag_250_v2.jsonl"


# ----------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------


def _make_chunk(
    index: int,
    title: str,
    text: str,
    section: str = "",
    doc_id: str | None = None,
) -> Chunk:
    """Tạo chunk test.

    Args:
        index: Chỉ số.
        title: Tên bài.
        text: Nội dung.
        section: Đường dẫn section.
        doc_id: Id bài (None ⇒ `doc_{index}`).

    Returns:
        Chunk.
    """
    return Chunk(
        chunk_id=f"chunk_{index}",
        doc_id=doc_id or f"doc_{index}",
        page_id=index,
        title=title,
        section=section.split(" > ")[-1] if section else "",
        section_path=section,
        text=text,
        source_url=f"https://vi.wikipedia.org/wiki/{index}",
    )


class _FakeBM25:
    """BM25 giả — trả về đúng thứ tự chunk đã cho."""

    def __init__(self, indices: list[int]) -> None:
        """Khởi tạo.

        Args:
            indices: Các chỉ số chunk, theo thứ tự hạng.
        """
        self._indices = indices

    def search(self, tokens: list[str], top_k: int = 50) -> list[tuple[int, float]]:
        """Trả về hit giả.

        Args:
            tokens: Token truy vấn (bỏ qua).
            top_k: Số kết quả tối đa.

        Returns:
            Danh sách `(index, score)`.
        """
        total = len(self._indices)
        return [
            (index, float(total - rank))
            for rank, index in enumerate(self._indices[:top_k])
        ]


def _make_retriever(chunks: list[Chunk], indices: list[int]) -> Retriever:
    """Dựng retriever giả (không dense, không parent expansion).

    Args:
        chunks: Danh sách chunk.
        indices: Thứ tự BM25 hit.

    Returns:
        `Retriever`.
    """
    config = {
        "retrieval": {
            "top_k": 8,
            "candidate_k": 50,
            "fusion": {"k": 60, "min_rrf_score": 0.0, "relative_score_floor": 0.0},
            "dense": {"enabled": False},
            "parent_expansion": {"enabled": False},
            "diversity": {
                "max_chunks_per_section": 2,
                "max_chunks_per_doc": 5,
                "title_boost": 0.0,
                "section_boost": 0.0,
                "noise_penalty": 0.0,
            },
        }
    }
    return Retriever(chunks, _FakeBM25(indices), embeddings=None, config=config)


# ----------------------------------------------------------------------
# 1. retriever — diversity
# ----------------------------------------------------------------------


def test_max_chunks_per_section_is_capped() -> None:
    """Không lấy quá `max_chunks_per_section` chunk của cùng 1 section."""
    chunks = [
        _make_chunk(0, "A", "a", "Diễn biến"),
        _make_chunk(1, "A", "b", "Diễn biến"),
        _make_chunk(2, "A", "c", "Diễn biến"),
        _make_chunk(3, "B", "d", "Khởi nghĩa"),
        _make_chunk(4, "C", "e", "Diễn biến"),
    ]
    retriever = _make_retriever(chunks, [0, 1, 2, 3, 4])
    retriever.config["retrieval"]["diversity"]["max_chunks_per_section"] = 2
    results = retriever.retrieve("diễn biến", top_k=5)
    counts: dict[tuple[str, str], int] = {}
    for item in results:
        key = (item.chunk.doc_id, item.chunk.section_path)
        counts[key] = counts.get(key, 0) + 1
    assert all(value <= 2 for value in counts.values()), counts


def test_max_chunks_per_doc_is_capped() -> None:
    """Không lấy quá `max_chunks_per_doc` chunk của cùng 1 bài."""
    chunks = [
        _make_chunk(i, "A", f"nội dung {i}", f"Mục {i}") for i in range(6)
    ]
    retriever = _make_retriever(chunks, list(range(6)))
    retriever.config["retrieval"]["diversity"]["max_chunks_per_doc"] = 3
    results = retriever.retrieve("nội dung", top_k=6)
    doc_ids = [item.chunk.doc_id for item in results]
    assert doc_ids.count("doc_0") <= 3, doc_ids


def test_title_boost_prefers_matching_title() -> None:
    """Chunk có tiêu đề khớp câu hỏi được ưu tiên."""
    chunks = [
        _make_chunk(0, "Trận Bạch Đằng", "nội dung về Trận Bạch Đằng"),
        _make_chunk(1, "Hà Nội", "nội dung về Hà Nội"),
    ]
    retriever = _make_retriever(chunks, [0, 1])
    diversity = retriever.config["retrieval"]["diversity"]
    diversity["title_boost"] = 1.0
    diversity["title_boost_mode"] = "subset"
    results = retriever.retrieve("Trận Bạch Đằng", top_k=2)
    assert results[0].chunk.title == "Trận Bạch Đằng"
    assert results[0].title_boost == pytest.approx(2.0)


def test_section_boost_prefers_matching_section() -> None:
    """Chunk ở section tên khớp câu hỏi được ưu tiên."""
    chunks = [
        _make_chunk(0, "Bài X", "nội dung", "Xem thêm"),
        _make_chunk(1, "Bài X", "nội dung", "Diễn biến"),
    ]
    retriever = _make_retriever(chunks, [0, 1])
    diversity = retriever.config["retrieval"]["diversity"]
    diversity["section_boost"] = 1.0
    results = retriever.retrieve("Kể lại diễn biến Bài X", top_k=2)
    assert results[0].chunk.section_path == "Diễn biến"


def test_noise_section_is_penalised() -> None:
    """Chunk ở section nhiễu ("Tham khảo") bị giảm điểm."""
    chunks = [
        _make_chunk(0, "Bài X", "nội dung", "Tham khảo"),
        _make_chunk(1, "Bài X", "nội dung", "Diễn biến"),
    ]
    retriever = _make_retriever(chunks, [0, 1])
    diversity = retriever.config["retrieval"]["diversity"]
    diversity["noise_penalty"] = 0.9
    results = retriever.retrieve("diễn biến", top_k=2)
    assert results[0].chunk.section_path == "Diễn biến"


def test_is_noise_section_detects_nested_noise() -> None:
    """Section "Liên kết > Tài liệu" cũng là nhiễu."""
    assert Retriever._is_noise_section(_make_chunk(0, "T", "x", "Xem thêm"))
    assert Retriever._is_noise_section(_make_chunk(0, "T", "x", "Liên kết > Tài liệu"))
    assert not Retriever._is_noise_section(_make_chunk(0, "T", "x", "Diễn biến"))


def test_retriever_config_has_diversity_keys() -> None:
    """Cấu hình thật phải có đủ khóa `diversity` (không hard-code)."""
    from src.common.config import load_config

    path = REPO_ROOT / "configs" / "retrieval.yaml"
    if not path.exists():
        pytest.skip("Thiếu configs/retrieval.yaml")
    config = load_config(path)
    diversity = (config.get("retrieval") or {}).get("diversity") or {}
    assert "max_chunks_per_section" in diversity
    assert "max_chunks_per_doc" in diversity
    assert "title_boost" in diversity


# ----------------------------------------------------------------------
# 2. rag_answer — no_data retry
# ----------------------------------------------------------------------


class _StubClient:
    """LLM giả — trả lần lượt các câu trả lời định sẵn."""

    def __init__(self, answers: list[str]) -> None:
        """Khởi tạo.

        Args:
            answers: Danh sách câu trả lời (dùng theo thứ tự).
        """
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete(self, prompt: str, **_: object) -> str:
        """Trả câu trả lời tiếp theo.

        Args:
            prompt: Nội dung prompt.
            **_: Bỏ qua.

        Returns:
            Câu trả lời.
        """
        self.prompts.append(prompt)
        if self.answers:
            return self.answers.pop(0)
        return NO_DATA_ANSWER


class _StubRetriever:
    """Retriever giả — trả về `n` chunk cố định."""

    def __init__(self, chunks: list[Chunk]) -> None:
        """Khởi tạo.

        Args:
            chunks: Chunk sẽ trả về.
        """
        from src.qa.retriever import RetrievedChunk

        self._items = [
            RetrievedChunk(chunk=chunk, index=index, rrf_score=0.02 - index * 0.001)
            for index, chunk in enumerate(chunks)
        ]

    def retrieve(self, query: str, **_: object) -> list:
        """Trả về chunk giả.

        Args:
            query: Câu hỏi.
            **_: Bỏ qua.

        Returns:
            Danh sách chunk.
        """
        return self._items


def _rag_answerer(chunks: list[Chunk], answers: list[str]):
    """Dựng `RagAnswerer` với client giả.

    Args:
        chunks: Chunk cho retriever giả.
        answers: Câu trả lời lần lượt.

    Returns:
        Tuple `(answerer, client)`.
    """
    from src.qa.rag_answer import RagAnswerer

    client = _StubClient(answers)
    answerer = RagAnswerer(_StubRetriever(chunks), client)
    return answerer, client


def test_no_data_retry_when_context_has_data() -> None:
    """LLM nói "không có" dù context có dữ liệu ⇒ phải retry ép trả lời."""
    chunks = [_make_chunk(0, "Đỗ Khuyển", "nội dung thật", "Diễn biến")]
    answerer, client = _rag_answerer(
        chunks,
        [NO_DATA_ANSWER, "Đỗ Khuyển tham gia khởi nghĩa [1]."],
    )
    result = answerer.answer("Đỗ Khuyển tham gia khởi nghĩa thế nào?")
    assert len(client.prompts) == 2, "Phải gọi LLM lần 2"
    assert result["status"] == "found"
    assert result["no_data_retried"] is True
    assert result["retries"] == 1


def test_no_data_retry_skipped_when_context_empty() -> None:
    """Context rỗng ⇒ "không có" là **đúng** ⇒ không retry."""
    answerer, client = _rag_answerer([], [NO_DATA_ANSWER])
    result = answerer.answer("Câu hỏi ngoài phạm vi")
    assert len(client.prompts) == 0, "Context rỗng ⇒ không gọi LLM, không retry"
    assert result["status"] == "not_in_data"
    assert result["no_data_retried"] is False


def test_no_data_retry_disabled_by_config() -> None:
    """Tắt `no_data_retry` trong config ⇒ không retry."""
    from src.qa.rag_answer import RagAnswerer

    chunks = [_make_chunk(0, "A", "nội dung", "Mục")]
    client = _StubClient([NO_DATA_ANSWER])
    answerer = RagAnswerer(
        _StubRetriever(chunks),
        client,
        config={"generation": {"no_data_retry": False, "max_no_data_retry": 1}},
    )
    result = answerer.answer("Câu hỏi")
    assert len(client.prompts) == 1
    assert result["status"] == "not_in_data"


def test_no_data_retry_keeps_answer_when_still_no_data() -> None:
    """Retry vẫn trả "không có" ⇒ giữ nguyên, không vòng lặp vô hạn."""
    chunks = [_make_chunk(0, "A", "nội dung", "Mục")]
    answerer, client = _rag_answerer(chunks, [NO_DATA_ANSWER, NO_DATA_ANSWER])
    result = answerer.answer("Câu hỏi")
    assert len(client.prompts) == 2
    assert result["status"] == "not_in_data"
    assert is_no_data(result["answer"])


def test_no_data_retry_when_llm_returns_empty() -> None:
    """⚠️ Phase 19 — LLM trả về **rỗng** cũng phải retry.

    Vì sao cần? Trước đây điều kiện `if not is_no_data(raw): break` ⇒
    `is_no_data("")` là ``False`` ⇒ **thoát vòng lặp ngay** ⇒ câu rỗng bị
    quy về "Không có trong dữ liệu." **mà không retry** ⇒ điểm 0 **ảo**
    cho cả 3 arm.
    """
    chunks = [_make_chunk(0, "A", "nội dung", "Mục")]
    answerer, client = _rag_answerer(
        chunks,
        ["", "Có dữ liệu trong context [1]."],
    )
    result = answerer.answer("Câu hỏi")
    assert len(client.prompts) == 2, "Câu rỗng phải được retry"
    assert result["no_data_retried"] is True
    assert result["status"] == "found"
    assert result["answer"] == "Có dữ liệu trong context [1]."


def test_hybrid_no_data_retry_when_llm_returns_empty() -> None:
    """⚠️ Phase 19 — arm B (hybrid) cũng retry khi LLM trả về rỗng.

    Vì sao? Câu rỗng (lỗi hạ tầng) bị quy về "Không có trong dữ liệu." ⇒
    điểm 0 **ảo** cho cả 3 arm ⇒ phải retry giống arm A.
    """
    from src.qa.hybrid import HybridAnswerer

    class _StubHybridClient:
        """Client giả — trả lần lượt các câu trả lời định sẵn."""

        def __init__(self, answers: list[str]) -> None:
            """Khởi tạo.

            Args:
                answers: Câu trả lời lần lượt.
            """
            self.answers = list(answers)
            self.prompts: list[str] = []

        def complete(self, prompt: str, **_: object) -> str:
            """Trả câu trả lời tiếp theo.

            Args:
                prompt: Nội dung prompt.
                **_: Bỏ qua.

            Returns:
                Câu trả lời.
            """
            self.prompts.append(prompt)
            if self.answers:
                return self.answers.pop(0)
            return ""

        def complete_json(self, prompt: str, **_: object) -> dict:
            """JSON giả.

            Args:
                prompt: Nội dung prompt.
                **_: Bỏ qua.

            Returns:
                Dict rỗng.
            """
            return {}

    client = _StubHybridClient(["", "Câu trả lời có [1]."])
    answerer = HybridAnswerer(
        _StubRetriever([_make_chunk(0, "A", "nội dung", "Mục")]),
        client=client,
        session_store=None,
    )
    answer, status, _citations, _faithful, _retries = answerer._generate(
        question="Câu hỏi",
        fused=_StubFused(),
        generation={
            "no_data_retry": True,
            "max_no_data_retry": 1,
            "faithfulness_retry": True,
            "max_faithfulness_retry": 1,
        },
        history="",
    )
    assert len(client.prompts) == 2, "Câu rỗng phải được retry"
    assert status == "found", "Retry phải cho lại câu trả lời có nội dung"
    assert "Câu trả lời có [1]." in answer


# ----------------------------------------------------------------------
# 3. hybrid — no_data retry
# ----------------------------------------------------------------------


def test_hybrid_no_data_retry_when_context_has_data() -> None:
    """Arm B/B− cũng phải retry "không có" khi context có dữ liệu."""
    from src.qa.hybrid import HybridAnswerer

    class _StubHybridClient(_StubClient):
        """Client giả cho hybrid."""

        def complete_json(self, prompt: str, **_: object) -> dict:
            """JSON giả.

            Args:
                prompt: Nội dung prompt.
                **_: Bỏ qua.

            Returns:
                Dict rỗng.
            """
            return {}

    class _StubHybridSession:
        """Session store giả."""

        def get_or_create(self, session_id: str) -> object:
            """Trả session giả.

            Args:
                session_id: Id phiên.

            Returns:
                Object giả.
            """
            return _StubSession()

    class _StubSession:
        """Session giả."""

        last_subject_entity_id = ""
        last_subject_name = ""

        def record_turn(self, *_: object, **__: object) -> None:
            """Không làm gì."""

        def save(self, *_: object, **__: object) -> None:
            """Không làm gì."""

    class _StubHybridRetriever(_StubRetriever):
        """Retriever giả cho hybrid."""

    chunks = [_make_chunk(0, "A", "nội dung", "Mục")]
    client = _StubHybridClient([NO_DATA_ANSWER, "Câu trả lời có [1]."])
    answerer = HybridAnswerer(
        _StubHybridRetriever(chunks),
        client=client,
        session_store=_StubHybridSession(),
    )
    answerer._generate(
        question="Câu hỏi",
        fused=_StubFused(),
        generation={"no_data_retry": True, "max_no_data_retry": 1},
        history="",
    )
    assert len(client.prompts) == 2, "Phải retry 1 lần"
    assert client.prompts[-1].find("CẢNH BÁO") >= 0


class _StubFused:
    """`FusedContext` giả — có 1 khối văn bản."""

    def __init__(self) -> None:
        """Khởi tạo."""
        self.text_blocks = [{"n": 1, "kind": "text", "text": "[1] A > Mục\nnội dung"}]
        self.kg_blocks: list[dict] = []
        self.citations: list[dict] = []
        self.strategy = "text_first"
        self.intent = "relational"
        self.elapsed_ms = 0

    def is_empty(self) -> bool:
        """Context không rỗng.

        Returns:
            ``False``.
        """
        return False

    def to_text(self) -> str:
        """Text của context.

        Returns:
            Chuỗi context.
        """
        return "[1] A > Mục\nnội dung"


# ----------------------------------------------------------------------
# 4. evaluate_rag — metric abstain_with_evidence
# ----------------------------------------------------------------------


def test_context_has_gold_matches_section() -> None:
    """Context có chunk đúng `doc_id` + `section` ⇒ có bằng chứng."""
    from src.evaluation.evaluate_rag import context_has_gold

    blocks = [
        {"doc_id": "doc_1", "section": "Diễn biến"},
        {"doc_id": "doc_2", "section": "Khác"},
    ]
    assert context_has_gold(blocks, ["doc_1"], "Diễn biến") is True
    assert context_has_gold(blocks, ["doc_1"], "Khác") is False
    assert context_has_gold(blocks, ["doc_3"], "Diễn biến") is False
    assert context_has_gold([], ["doc_1"], "Diễn biến") is False


def test_context_has_gold_matches_nested_section_path() -> None:
    """Section lồng nhau ("Quân đội Hoa Kỳ > Diễn biến") vẫn khớp."""
    from src.evaluation.evaluate_rag import context_has_gold

    blocks = [{"doc_id": "doc_1", "section": "Quân đội Hoa Kỳ > Diễn biến"}]
    assert context_has_gold(blocks, ["doc_1"], "Diễn biến") is True


def test_aggregate_reports_abstain_with_evidence() -> None:
    """`aggregate()` trả metric `abstain_with_evidence` đúng."""
    from src.evaluation.evaluate_rag import aggregate

    def _record(answer: str, blocks: list[dict]) -> dict:
        """Dựng bản ghi giả.

        Args:
            answer: Câu trả lời.
            blocks: Khối context.

        Returns:
            Bản ghi.
        """
        return {
            "qid": "q0001",
            "type": "narrative",
            "question": "câu hỏi",
            "expected_answer": "đáp án",
            "evidence_doc_id": ["doc_1"],
            "evidence_section": "Diễn biến",            "arm": {
                "answer": answer,
                "context": "[1] A > Diễn biến\nnội dung có đáp án",
                "context_blocks": blocks,
                "elapsed_ms": 10,
                "infrastructure_error": False,
            },
            "judge": {
                "correctness": 1,
                "faithfulness": 2,
                "citation_precision": 1.0,
                "reason": "ok",
            },
        }

    records = [
        _record(NO_DATA_ANSWER, [{"doc_id": "doc_1", "section": "Diễn biến"}]),
        _record(NO_DATA_ANSWER, [{"doc_id": "doc_9", "section": "Khác"}]),
        _record("Câu trả lời có [1].", [{"doc_id": "doc_1", "section": "Diễn biến"}]),
    ]
    metrics = aggregate(records)
    assert metrics["abstain_with_evidence"] == 1
    assert metrics["abstain_total"] == 2


# ----------------------------------------------------------------------
# 5. build_qa_set — bộ câu hỏi v2
# ----------------------------------------------------------------------


def test_build_qa_set_no_data_modern_topics_absent_from_corpus() -> None:
    """Mọi chủ đề `no_data` (lịch sử hậu-1945) phải **không** có trong corpus."""
    from src.evaluation.build_qa_set import NO_DATA_TOPICS_MODERN_HISTORY

    chunks_path = REPO_ROOT / "data" / "interim" / "chunks.jsonl"
    if not chunks_path.exists():
        pytest.skip("Thiếu chunks.jsonl")

    import unicodedata

    def _norm(text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text or "")
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        return " ".join(stripped.replace("đ", "d").lower().split())

    blob: list[str] = []
    with chunks_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            blob.append(
                _norm(
                    f"{record.get('title') or ''} "
                    f"{record.get('section_path') or ''} "
                    f"{record.get('text') or ''}"
                )
            )
    full = "\n".join(blob)
    for topic in NO_DATA_TOPICS_MODERN_HISTORY:
        assert _norm(topic) not in full, f"Chủ đề nằm trong corpus: {topic}"


@pytest.mark.skipif(not QA_V2.exists(), reason="Thiếu qa_rag_250_v2.jsonl")
def test_qa_v2_narrative_answers_use_single_section() -> None:
    """Câu narrative trong bộ v2 lấy đáp án từ **đúng 1 section**."""
    rows = [
        json.loads(line)
        for line in QA_V2.open("r", encoding="utf-8")
        if line.strip()
    ]
    narrative = [row for row in rows if row["type"] == "narrative"]
    assert narrative
    for row in narrative:
        assert row.get("evidence_section_path"), row["qid"]
        assert row["expected_answer"].strip()


@pytest.mark.skipif(not QA_V2.exists(), reason="Thiếu qa_rag_250_v2.jsonl")
def test_qa_v2_no_data_is_modern_history() -> None:
    """Nhóm `no_data` của bộ v2 là **lịch sử hậu-1945**, đáp án đều là
    "Không có trong dữ liệu."."""
    rows = [
        json.loads(line)
        for line in QA_V2.open("r", encoding="utf-8")
        if line.strip()
    ]
    no_data = [row for row in rows if row["type"] == "no_data"]
    assert no_data
    for row in no_data:
        assert row["expected_answer"] == "Không có trong dữ liệu."
        assert row["evidence_doc_id"] == []


@pytest.mark.skipif(not QA_V1.exists() or not QA_V2.exists(), reason="Thiếu bộ eval")
def test_qa_v2_keeps_v1_intact() -> None:
    """Bộ cũ `qa_rag_250.jsonl` phải **giữ nguyên** để so sánh."""
    old = [
        json.loads(line)
        for line in QA_V1.open("r", encoding="utf-8")
        if line.strip()
    ]
    assert old, "Bộ cũ bị mất"
    assert {row["type"] for row in old} >= {"narrative", "no_data"}


# ----------------------------------------------------------------------
# Phase 19 — các lỗi bộ câu hỏi phát hiện qua kiểm chứng online
# ----------------------------------------------------------------------


def _qa_v2_rows() -> list[dict]:
    """Nạp bộ câu hỏi v2.

    Returns:
        Danh sách bản ghi.
    """
    return [
        json.loads(line)
        for line in QA_V2.open("r", encoding="utf-8")
        if line.strip()
    ]


@pytest.mark.skipif(not QA_V2.exists(), reason="Thiếu qa_rag_250_v2.jsonl")
def test_qa_v2_multi_turn_has_evidence_doc() -> None:
    """⚠️ Mọi câu `multi_turn` phải có `evidence_doc_id` (bằng chứng).

    Vì sao? Trước đây `evidence_doc_id = []` cho **mọi** câu `multi_turn`
    ⇒ không kiểm chứng được câu hỏi bằng Wikipedia live (Gate G19-7) ⇒
    60/60 câu bị đánh dấu "không hợp lệ" (false negative).
    """
    rows = [row for row in _qa_v2_rows() if row["type"] == "multi_turn"]
    assert rows
    missing = [row["qid"] for row in rows if not row["evidence_doc_id"]]
    assert not missing, f"Câu multi_turn thiếu evidence_doc_id: {missing[:5]}"


@pytest.mark.skipif(not QA_V2.exists(), reason="Thiếu qa_rag_250_v2.jsonl")
def test_qa_v2_multi_hop_mother_chain_is_correct() -> None:
    """⚠️ "Mẹ của mẹ X" phải là **mẹ của mẹ**, không phải **mẹ của cha**.

    Vì sao? Trước đây builder lấy **mẹ của cha** ⇒ câu hỏi ghi "Mẹ của mẹ X"
    nhưng đáp án thật ra là mẹ của cha ⇒ **sai** ⇒ điểm 0 là do *câu hỏi*,
    không phải do hệ thống (đúng như lo ngại ở Gate G19-7).

    Kiểm chứng bằng **Wikidata live** (P25 = mẹ): mẹ của X ⇒ rồi mẹ của
    mẹ đó ⇒ phải khớp `expected_answer`.
    """
    rows = [
        row
        for row in _qa_v2_rows()
        if row["relation"] == "multi_hop_me_cua_me_cua"
    ]
    assert rows, "Không có câu 'Mẹ của mẹ' nào trong bộ v2"

    from scripts.verify_answers_online import (
        _norm,
        wikidata_name_keys,
        wikidata_property_targets,
    )

    entities = {
        str(entity.get("wikidata_qid") or ""): entity
        for entity in (
            json.loads(line)
            for line in (REPO_ROOT / "data" / "knowledge_base" / "entities.jsonl")
            .open("r", encoding="utf-8")
            if line.strip()
        )
        if entity.get("wikidata_qid")
    }
    by_name = {
        str(entity.get("name") or "").casefold(): str(entity.get("wikidata_qid") or "")
        for entity in entities.values()
    }

    for row in rows:
        subject_qid = by_name.get(str(row["subject_name"]).casefold())
        assert subject_qid, f"{row['qid']}: không tra được QID của chủ thể"
        mothers = wikidata_property_targets(subject_qid, "P25")
        assert mothers, f"{row['qid']}: không có mẹ trong Wikidata live"
        # Chuỗi đúng: mẹ của X → rồi mẹ của mẹ đó.
        grandmas: set[str] = set()
        for mother_qid in mothers:
            grandmas |= set(wikidata_property_targets(mother_qid, "P25"))
        # Nhãn **và bí danh** (vd. Q1156054: nhãn "Trần Thị Dung", bí danh
        # "Linh Từ quốc mẫu") ⇒ so khớp phải bao gồm cả bí danh.
        labels: set[str] = set()
        for qid in grandmas:
            labels |= wikidata_name_keys(qid)
        assert _norm(row["expected_answer"]) in labels, (
            f"{row['qid']}: 'Mẹ của mẹ {row['subject_name']}' theo Wikidata live = "
            f"{sorted(labels)}, không phải {row['expected_answer']!r}"
        )


@pytest.mark.skipif(not QA_V2.exists(), reason="Thiếu qa_rag_250_v2.jsonl")
def test_qa_v2_year_questions_exist_in_corpus() -> None:
    """⚠️ Câu hỏi năm sinh/mất phải có **năm đó trong corpus**.

    Vì sao? Wikidata có năm của **mọi** người, kể cả khi bài Wikipedia
    **không** ghi năm đó ⇒ câu hỏi không có đáp án trong dữ liệu ⇒ mọi arm
    đều trả "không có trong dữ liệu" ⇒ điểm 0 là do *câu hỏi*.
    """
    docs = {
        record["doc_id"]: record.get("clean_text") or ""
        for record in (
            json.loads(line)
            for line in (REPO_ROOT / "data" / "interim" / "documents_clean.jsonl")
            .open("r", encoding="utf-8")
            if line.strip()
        )
    }
    rows = [
        row
        for row in _qa_v2_rows()
        if row["type"] == "multi_turn"
        and row["relation"] in {"multi_turn_sinh_nam", "multi_turn_mat_nam"}
    ]
    assert rows
    missing = []
    for row in rows:
        year = row["expected_answer"].replace("năm ", "")
        haystack = " ".join(
            docs.get(doc_id, "") for doc_id in row["evidence_doc_id"]
        )
        if year and year not in haystack:
            missing.append((row["qid"], year, row["subject_name"]))
    assert not missing, f"Câu hỏi năm không có trong corpus: {missing[:5]}"


def test_split_expected_names_keeps_comma_in_label() -> None:
    """⚠️ Nhãn Wikidata có thể **tự chứa dấu phẩy**.

    Vì sao? "Vương tước Philip, Công tước xứ Edinburgh" là **một** người
    ⇒ tách mù bằng `split(",")` ⇒ sinh 2 mảnh vô nghĩa ⇒ báo sai (false
    negative) cho câu hỏi hoàn toàn hợp lệ.
    """
    from scripts.verify_answers_online import _split_expected_names

    # Không có tập đích ⇒ **không tách** (giữ nguyên 1 tên có dấu phẩy).
    assert _split_expected_names("Vương tước Philip, Công tước xứ Edinburgh") == [
        "Vương tước Philip, Công tước xứ Edinburgh"
    ]
    # Có tập đích khớp **cả hai** phần ⇒ tách thành 2 tên.
    assert _split_expected_names(
        "A, B",
        {"a", "b"},
    ) == ["A", "B"]
    # Có tập đích khớp **một** phần ⇒ gộp lại thành 1 tên.
    assert _split_expected_names(
        "Vương tước Philip, Công tước xứ Edinburgh",
        {"vương tước philip"},
    ) == ["Vương tước Philip, Công tước xứ Edinburgh"]
    assert _split_expected_names("Chỉ một tên") == ["Chỉ một tên"]


def test_evaluate_rag_filters_type_before_limit() -> None:
    """⚠️ `--only-types` phải lọc **trước** `--limit`.

    Vì sao? Trước đây `limit` cắt danh sách trước ⇒ `--only-types narrative
    --limit 2` cắt còn 2 câu đầu (nhóm `relational`) ⇒ lọc type ⇒ **0 câu**
    ⇒ chạy eval **không được gì** mà không báo lỗi.
    """
    import inspect

    from src.evaluation import evaluate_rag

    source = inspect.getsource(evaluate_rag.main)
    only_pos = source.index("if args.only_types:")
    limit_pos = source.index("if args.limit:")
    assert only_pos < limit_pos, "Phải lọc type TRƯỚC rồi mới cắt limit"



def test_http_get_json_retries_on_429(monkeypatch, tmp_path) -> None:
    """⚠️ HTTP 429 (bị giới hạn tần suất) phải **retry**, không được bỏ câu hỏi.

    Vì sao? Lần chạy đầu tiên của `verify_answers_online.py` gặp 429 ở bài
    "Đỗ Mường Trừng Nguyên" ⇒ câu hỏi bị đánh dấu **không hợp lệ** (false
    negative) ⇒ G19-7 bị báo sai.
    """
    import urllib.error

    from scripts import verify_answers_online as vao

    calls: list[int] = []

    class _FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def _fake_urlopen(request, timeout=None):  # noqa: ANN001, ANN202 — test stub
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", None, None)
        return _FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(vao.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(vao, "_throttle", lambda: None)
    monkeypatch.setattr(vao.time, "sleep", lambda _s: None)
    monkeypatch.setattr(vao, "MAX_RETRIES_429", 6)
    # Cache rỗng (thư mục tạm) ⇒ buộc phải gọi mạng.
    monkeypatch.setattr(vao, "_cache_path", lambda _key: tmp_path / "cache.json")

    result = vao.http_get_json("https://vi.wikipedia.org/w/api.php?action=test")
    assert result == {"ok": True}
    assert len(calls) == 3, f"Phải thử lại sau 429, thực tế {len(calls)} lần"


def test_measure_gold_hit_rate_script_exists() -> None:
    """Script đo hit-rate gold section phải tồn tại (G19-2 — đo offline)."""
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "measure_gold_hit_rate.py"
    assert script.exists(), "Thiếu scripts/measure_gold_hit_rate.py"
    source = script.read_text(encoding="utf-8")
    assert "evidence_doc_id" in source
    assert "evidence_section" in source


def test_context_has_gold_requires_answer_in_context() -> None:
    """⚠️ `abstain_with_evidence` phải kiểm tra **đáp án có trong context**, không chỉ `doc_id`.

    Vì sao? Câu hỏi "Gioan Baotixita Nguyễn Thần Đồng mất năm nào?" có
    `evidence_doc_id = doc_7598948`; context **có** đúng bài nhưng các chunk lấy
    về nằm ở section **khác** ⇒ **không** có câu trả lời ⇒ "Không có trong dữ
    liệu" là **đúng** ⇒ đếm là lỗi là **sai** (đo được 13/13 câu bị đếm oan
    trước khi sửa).
    """
    from src.evaluation.evaluate_rag import context_has_gold

    blocks = [
        {"doc_id": "doc_1", "section": "Bị bắt và đày ra Côn Đảo"},
        {"doc_id": "doc_1", "section": "Thân thế và con đường tu học"},
    ]

    # Đáp án **có** trong context ⇒ tính là lỗi (abstain oan).
    assert context_has_gold(
        blocks, ["doc_1"], "", "[1] ... sinh năm Bính Dần (1866) ...", "năm 1866"
    ) is True
    # Đáp án **không** có trong context ⇒ "không có" là **đúng** ⇒ không lỗi.
    assert context_has_gold(
        blocks, ["doc_1"], "", "[1] ... sinh năm Bính Dần (1866) ...", "năm 1944"
    ) is False
    # Đáp án là **tên** không có trong context ⇒ không lỗi.
    assert context_has_gold(
        blocks, ["doc_1"], "", "[1] Nguyễn Phúc Nguyên ...", "Gia Long"
    ) is False
    # Tên **có** trong context ⇒ lỗi.
    assert context_has_gold(
        blocks, ["doc_1"], "", "[1] Nguyễn Phúc Nguyên ...", "Nguyễn Phúc Nguyên"
    ) is True
    # Không có `evidence_doc_id` ⇒ coi như có dữ liệu (thiên về phát hiện lỗi).
    assert context_has_gold(blocks, [], "", "bất kỳ", "bất kỳ") is True

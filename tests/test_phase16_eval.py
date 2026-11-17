"""Test Phase 16 — đánh giá RAG (pool LLM, chuẩn hóa arm, loại lỗi hạ tầng).

Bao phủ các điểm dễ sai đã gặp thực tế:
- LLM-judge trả tên arm có tiền tố ("PHƯƠNG ÁN A", "Phương án B−") ⇒ phải
  chuẩn hóa về key gốc, nếu không **toàn bộ điểm = 0**.
- Quota LLM hết giữa chừng (429) ⇒ câu đó là **lỗi hạ tầng**, phải bị loại
  khỏi mẫu số chứ không được tính điểm 0.
- Arm B và B− phải dùng **session riêng** để không ô nhiễm lượt trả lời.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.evaluation.evaluate_rag import (  # noqa: E402
    _arm_session_id,
    _clamp_float,
    _clamp_int,
    _normalize_arm_name,
    _parse_pool_spec,
    aggregate,
    estimate_tokens,
    is_no_data,
)


CANDIDATES = [{"arm": "A"}, {"arm": "B"}, {"arm": "B-"}]


class TestNormalizeArmName:
    """Chuẩn hóa tên arm do LLM-judge trả về."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("A", "A"),
            ("B", "B"),
            ("B-", "B-"),
            ("PHƯƠNG ÁN A", "A"),
            ("Phương án B", "B"),
            ("Phương án B-", "B-"),
            ("phuong an B-", "B-"),
            ("đáp án A", "A"),
            ("**B−**", "B-"),
            ("B−", "B-"),
            ("Phương án B−", "B-"),
            ("  A  ", "A"),
        ],
    )
    def test_normalize(self, raw: str, expected: str) -> None:
        """Các biến thể tên arm đều về đúng key."""
        assert _normalize_arm_name(raw, CANDIDATES) == expected

    def test_unknown_arm_returns_empty(self) -> None:
        """Tên không khớp ⇒ chuỗi rỗng (không gán nhầm arm khác)."""
        assert _normalize_arm_name("Phương án Z", CANDIDATES) == ""

    def test_empty_returns_empty(self) -> None:
        """Chuỗi rỗng ⇒ chuỗi rỗng."""
        assert _normalize_arm_name("", CANDIDATES) == ""

    def test_prefers_hyphen_arm_over_plain(self) -> None:
        """`B-` phải được ưu tiên hơn `B` (độ dài giảm dần)."""
        assert _normalize_arm_name("Phương án B−", CANDIDATES) == "B-"


class TestClamp:
    """Giới hạn giá trị điểm về khoảng hợp lệ."""

    def test_clamp_int(self) -> None:
        """Clamp int về [low, high], giá trị lỗi ⇒ low."""
        assert _clamp_int(5, 0, 2) == 2
        assert _clamp_int(-1, 0, 2) == 0
        assert _clamp_int("abc", 0, 2) == 0
        assert _clamp_int(1, 0, 2) == 1

    def test_clamp_float(self) -> None:
        """Clamp float về [low, high], giá trị lỗi ⇒ low."""
        assert _clamp_float(1.5, 0.0, 1.0) == 1.0
        assert _clamp_float(-0.2, 0.0, 1.0) == 0.0
        assert _clamp_float("x", 0.0, 1.0) == 0.0
        assert _clamp_float(0.5, 0.0, 1.0) == 0.5


class TestNoData:
    """Nhận diện câu trả lời "không có dữ liệu"."""

    def test_detects(self) -> None:
        """Chuỗi chuẩn bị nhận diện."""
        assert is_no_data("Không có trong dữ liệu.")

    def test_detects_variant(self) -> None:
        """Biến thể viết hoa khác nhau cũng nhận diện."""
        assert is_no_data("KHÔNG CÓ TRONG DỮ LIỆU")
        assert is_no_data('"Không có trong dữ liệu."')


class TestArmSession:
    """Tách session theo arm (tránh ô nhiễm lượt trả lời)."""

    def test_separates_arms(self) -> None:
        """B và B− phải có session khác nhau."""
        assert _arm_session_id("eval_X_0001", "B") != _arm_session_id(
            "eval_X_0001", "B-"
        )

    def test_keeps_prefix(self) -> None:
        """Session id giữ nguyên tiền tố gốc (để dễ truy ngược)."""
        assert _arm_session_id("eval_X_0001", "B") == "eval_X_0001__B"

    def test_none_stays_none(self) -> None:
        """Không có session ⇒ không tạo."""
        assert _arm_session_id(None, "B") is None
        assert _arm_session_id("", "B") is None


class TestParsePoolSpec:
    """Phân tích đặc tả pool đa provider."""

    def test_single_provider(self) -> None:
        """Một provider, nhiều model."""
        assert _parse_pool_spec("gemini:a,b") == [("gemini", ["a", "b"])]

    def test_multi_provider(self) -> None:
        """Nhiều provider ngăn cách bằng dấu chấm phẩy."""
        assert _parse_pool_spec("gemini:a;groq:b") == [
            ("gemini", ["a"]),
            ("groq", ["b"]),
        ]

    def test_ignores_garbage(self) -> None:
        """Đoạn không hợp lệ bị bỏ qua."""
        assert _parse_pool_spec("") == []
        assert _parse_pool_spec("khongco dauhaicham") == []
        assert _parse_pool_spec("gemini:") == []


def _record(
    qid: str,
    correctness: int,
    *,
    infra: bool = False,
    qtype: str = "relational",
    answer: str = "câu trả lời",
) -> dict:
    """Dựng record giả cho test.

    Args:
        qid: Id câu.
        correctness: Điểm correctness.
        infra: Có phải lỗi hạ tầng không.
        qtype: Loại câu hỏi.
        answer: Câu trả lời.

    Returns:
        Record theo format của evaluate_rag.
    """
    return {
        "qid": qid,
        "question": "hỏi",
        "type": qtype,
        "expected_answer": "đáp án",
        "evidence_doc_id": [],
        "arm": {
            "answer": answer,
            "status": "error" if infra else "found",
            "citations": [],
            "context": "ngữ cảnh",
            "context_chars": 7,
            "elapsed_ms": 100,
            "faithfulness_ok": None,
            "infrastructure_error": infra,
        },
        "judge": {
            "correctness": correctness,
            "faithfulness": 2,
            "citation_precision": 1.0,
            "reason": "",
        },
    }


class TestAggregate:
    """Tính chỉ số tổng hợp."""

    def test_basic(self) -> None:
        """Chỉ số cơ bản đúng."""
        metrics = aggregate([_record("q1", 2), _record("q2", 0)])
        assert metrics["n"] == 2
        assert metrics["correctness_mean"] == 1.0
        assert metrics["correctness_rate"] == 0.5
        assert metrics["faithfulness_mean"] == 2.0
        assert metrics["citation_precision"] == 1.0

    def test_infra_errors_excluded(self) -> None:
        """Câu lỗi hạ tầng **không** được tính điểm 0 vào mẫu số."""
        metrics = aggregate(
            [_record("q1", 2), _record("q2", 0), _record("q3", 0, infra=True)]
        )
        assert metrics["n"] == 2
        assert metrics["n_infra_errors"] == 1
        assert metrics["n_total"] == 3
        assert metrics["correctness_mean"] == 1.0

    def test_all_infra_errors(self) -> None:
        """Toàn bộ lỗi hạ tầng ⇒ không có mẫu số hợp lệ."""
        metrics = aggregate([_record("q1", 0, infra=True)])
        assert metrics["n"] == 0
        assert metrics["n_infra_errors"] == 1

    def test_no_data_accuracy(self) -> None:
        """Độ chính xác câu `no_data` chỉ tính trên câu hợp lệ."""
        metrics = aggregate(
            [
                _record(
                    "q1", 2, qtype="no_data",
                    answer="Không có trong dữ liệu.",
                ),
                _record("q2", 0, qtype="no_data", answer="có dữ liệu"),
                _record("q3", 0, qtype="no_data", infra=True),
            ]
        )
        assert metrics["no_data_accuracy"] == 0.5

    def test_by_type(self) -> None:
        """Chỉ số theo dạng câu hỏi."""
        metrics = aggregate(
            [
                _record("q1", 2, qtype="relational"),
                _record("q2", 0, qtype="relational"),
                _record("q3", 2, qtype="narrative"),
            ]
        )
        assert metrics["by_type"]["relational"]["n"] == 2
        assert metrics["by_type"]["relational"]["correctness"] == 1.0
        assert metrics["by_type"]["narrative"]["correctness"] == 2.0


def test_estimate_tokens_positive() -> None:
    """Ước lượng token luôn dương (tối thiểu 1)."""
    assert estimate_tokens("xin chào Việt Nam") > 0
    assert estimate_tokens("") == 1


class TestJudgeRetry:
    """Judge phải trả đủ điểm cho **mọi** arm.

    Lỗi thực tế: JSON output của judge bị cắt token ⇒ thiếu entry cho 1 arm ⇒
    arm đó bị gán điểm 0 ⇒ **số liệu sai** (không phải số liệu kém).
    """

    class _FakeClient:
        """Client giả trả về lần lượt các payload đã chuẩn bị."""

        def __init__(self, payloads: list[dict | None]) -> None:
            """Khởi tạo.

            Args:
                payloads: Danh sách payload trả về theo thứ tự lời gọi.
            """
            self.payloads = payloads
            self.calls = 0

        def complete_json(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
            """Trả payload theo thứ tự.

            Args:
                *args: Bỏ qua.
                **kwargs: Bỏ qua.

            Returns:
                Payload kế tiếp (None nếu hết).
            """
            index = min(self.calls, len(self.payloads) - 1)
            self.calls += 1
            return self.payloads[index]

    def test_retries_until_all_arms_scored(self) -> None:
        """Thử lại khi judge thiếu điểm cho 1 arm."""
        from src.evaluation.evaluate_rag import Judge

        client = self._FakeClient(
            [
                {"scores": [{"arm": "A", "correctness": 2, "faithfulness": 2,
                             "citation_precision": 1.0, "reason": "ok"}]},
                {"scores": [
                    {"arm": "A", "correctness": 2, "faithfulness": 2,
                     "citation_precision": 1.0, "reason": "ok"},
                    {"arm": "B", "correctness": 1, "faithfulness": 2,
                     "citation_precision": 0.5, "reason": "thiếu chi tiết"},
                ]},
            ]
        )
        judge = Judge(client)  # type: ignore[arg-type]
        scores = judge.score(
            question="hỏi",
            expected_answer="đáp án",
            candidates=[
                {"arm": "A", "context": "ctx", "answer": "a"},
                {"arm": "B", "context": "ctx", "answer": "b"},
            ],
        )
        assert client.calls == 2
        assert scores["A"]["correctness"] == 2
        assert scores["B"]["correctness"] == 1

    def test_missing_arm_still_zero(self) -> None:
        """Judge hỏng hoàn toàn ⇒ vẫn trả điểm 0 (nhưng đếm được)."""
        from src.evaluation.evaluate_rag import Judge

        client = self._FakeClient([None, None, None])
        judge = Judge(client)  # type: ignore[arg-type]
        scores = judge.score(
            question="hỏi",
            expected_answer="đáp án",
            candidates=[{"arm": "A", "context": "ctx", "answer": "a"}],
        )
        assert scores["A"]["correctness"] == 0
        assert "không trả về điểm" in scores["A"]["reason"]


class TestAggregateJudgeMissing:
    """Đếm số arm bị judge bỏ sót (điểm 0 giả)."""

    def test_counts_missing(self) -> None:
        """Số arm thiếu điểm được đếm riêng."""
        record = _record("q1", 2)
        record["judge"]["reason"] = "Judge không trả về điểm cho phương án này."
        metrics = aggregate([record, _record("q2", 1)])
        assert metrics["n_judge_missing"] == 1
        assert metrics["n"] == 2


class TestInfraErrorResume:
    """Câu lỗi hạ tầng phải được **chạy lại**, không bị `--resume` bỏ qua."""

    def test_detects_infra_error(self) -> None:
        """Bản ghi có arm lỗi hạ tầng ⇒ `True`."""
        from src.evaluation.evaluate_rag import _has_infra_error

        record = {
            "qid": "q1",
            "A": {"arm": {"infrastructure_error": False}},
            "B": {"arm": {"infrastructure_error": True}},
        }
        assert _has_infra_error(record, ["A", "B"]) is True

    def test_healthy_record_passes(self) -> None:
        """Bản ghi bình thường ⇒ `False`."""
        from src.evaluation.evaluate_rag import _has_infra_error

        record = {
            "qid": "q1",
            "A": {"arm": {"infrastructure_error": False}},
            "B": {"arm": {"infrastructure_error": False}},
        }
        assert _has_infra_error(record, ["A", "B"]) is False


class _FakeLLMClient:
    """Client giả cho test `PooledLLM`."""

    def __init__(self, name: str, *, fail: bool = False) -> None:
        """Khởi tạo.

        Args:
            name: Tên model.
            fail: Luôn ném lỗi (mô phỏng hết quota).
        """
        self.providers = [type("P", (), {"name": name.split("/")[0], "model": name.split("/")[1]})()]
        self.fail = fail

    def complete(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        """Trả về hoặc ném lỗi.

        Args:
            *args: Bỏ qua.
            **kwargs: Bỏ qua.

        Returns:
            Chuỗi phản hồi.

        Raises:
            RuntimeError: Nếu `fail` bật.
        """
        if self.fail:
            raise RuntimeError("429 Rate limit reached")
        return "ok"


class TestPooledLLMPinning:
    """Ghim model phải giữ được tính nhất quán giữa các arm."""

    def test_pin_used_when_available(self) -> None:
        """Model ghim được ưu tiên."""
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [_FakeLLMClient("groq/m1"), _FakeLLMClient("gemini/m2")],
        )
        pool.pin("gemini/m2")
        assert pool.complete("p") == "ok"
        assert pool.last_model == "gemini/m2"

    def test_pin_switches_to_replacement_not_unpinned(self) -> None:
        """Model ghim hết quota ⇒ **ghin lại** model thay thế (không bỏ ghim).

        Nếu bỏ ghim ⇒ round-robin ⇒ các arm khác nhau dùng khác model ⇒
        confound model quay lại.
        """
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [_FakeLLMClient("groq/m1", fail=True), _FakeLLMClient("gemini/m2")],
            quota_cooldown_s=900.0,
        )
        pool.pin("groq/m1")
        assert pool.complete("p") == "ok"
        assert pool.last_model == "gemini/m2"
        # Model thay thế vẫn được ghim ⇒ lời gọi sau cũng dùng m2.
        assert pool.complete("p") == "ok"
        assert pool.last_model == "gemini/m2"

    def test_strict_pin_never_switches_model(self) -> None:
        """Ghim **cứng**: model ghim lỗi ⇒ KHÔNG đổi model.

        Vì sao: nếu đổi model giữa chừng ⇒ 3 arm dùng khác model ⇒
        confound ⇒ câu đó phải loại. Ghim cứng ⇒ `complete()` **chờ** quota
        hồi của **đúng model đó** rồi thử lại.
        """
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [_FakeLLMClient("groq/m1", fail=True), _FakeLLMClient("gemini/m2")],
            quota_cooldown_s=900.0,
            max_quota_wait_s=0.0,
        )
        pool.pin_strict("groq/m1")
        with pytest.raises(Exception):  # noqa: B017, PT011
            pool.complete("p")
        # Chỉ model ghim được thử ⇒ không có lời gọi nào tới `gemini/m2`.
        assert pool.last_model == ""
        assert pool.errors.get("gemini/m2", 0) == 0
        assert pool.errors.get("groq/m1", 0) == 1

    def test_probe_all_marks_dead_models(self) -> None:
        """Probe đánh dấu model đã chết ⇒ `healthy_keys` loại chúng."""
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [_FakeLLMClient("groq/m1", fail=True), _FakeLLMClient("gemini/m2")],
            quota_cooldown_s=900.0,
        )
        health = pool.probe_all()
        assert health == {"groq/m1": False, "gemini/m2": True}
        assert pool.healthy_keys() == ["gemini/m2"]

    def test_retry_after_parses_gemini_reset_time(self) -> None:
        """Gemini báo "retry in 5h14m16s" ⇒ chờ đúng 5h14m."""
        from src.evaluation.evaluate_rag import PooledLLM

        error = RuntimeError(
            "Quota exceeded for metric: generate_content_free_tier_requests, "
            "limit: 500, model: gemini-3.1-flash-lite. "
            "Please retry in 5h14m16.763661727s."
        )
        wait = PooledLLM._retry_after_s(error)
        assert wait is not None
        assert 5 * 3600 + 14 * 60 + 16 <= wait < 5 * 3600 + 14 * 60 + 18

    def test_retry_after_parses_groq_reset_time(self) -> None:
        """Groq báo "try again in 2m53.664s" ⇒ chờ đúng 2m53s."""
        from src.evaluation.evaluate_rag import PooledLLM

        error = RuntimeError(
            "Rate limit reached for model `openai/gpt-oss-120b` ... "
            "Please try again in 2m53.664s."
        )
        wait = PooledLLM._retry_after_s(error)
        assert wait is not None
        assert 173 <= wait < 175

    def test_retry_after_none_when_absent(self) -> None:
        """Không có thông tin reset ⇒ trả `None`."""
        from src.evaluation.evaluate_rag import PooledLLM

        assert PooledLLM._retry_after_s(RuntimeError("boom")) is None

    def test_healthy_keys_order_is_stable(self) -> None:
        """Thứ tự `healthy_keys` **ổn định** theo tên model.

        Vì sao: danh sách model dùng được phụ thuộc trạng thái quota ⇒ đổi
        giữa các vòng `--resume` ⇒ nếu chọn model theo thứ tự đó thì cùng
        1 câu có thể đổi model ⇒ **mất LLM cache hit** ⇒ tốn token Groq lần
        nữa. ⇒ Sắp xếp theo tên ⇒ ổn định.
        """
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [
                _FakeLLMClient("groq/m3"),
                _FakeLLMClient("groq/m1"),
                _FakeLLMClient("gemini/m2"),
            ],
        )
        first = pool.healthy_keys()
        assert first == sorted(first)
        # Thứ tự không đổi dù pool có biến động khác.
        assert pool.healthy_keys() == first

    def test_cooldown_capped_by_max_cooldown_s(self) -> None:
        """Cooldown bị **cắt** ở `max_cooldown_s` (provider báo 5h14m).

        Vì sao: Gemini báo "5h14m" ⇒ loại model khỏi pool 5 giờ ⇒ nếu quota
        thực tế hồi sớm hơn thì mất cả ngày. Cắt còn 15 phút ⇒ thử lại
        định kỳ, không bỏ lỡ.
        """
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [_FakeLLMClient("gemini/m1")],
            quota_cooldown_s=900.0,
            max_cooldown_s=900.0,
        )
        error = RuntimeError(
            "Quota exceeded ... Please retry in 5h14m16.763661727s."
        )
        pool._cooldown_until = {}
        pool._record_quota_cooldown("gemini/m1", error)
        remaining = pool._cooldown_until["gemini/m1"] - pool._cooldown_until["gemini/m1"] + 0
        assert remaining >= 0
        # Cooldown phải ≤ 900s (có trần), không phải ~5 giờ.
        import time as _time

        delta = pool._cooldown_until["gemini/m1"] - _time.time()
        assert 0 < delta <= 900.0 + 5


class TestProviderPriority:
    """Ưu tiên provider theo **thang đo quota** khác nhau.

    Vì sao: Groq giới hạn theo **token/ngày**, Gemini giới hạn theo
    **request/ngày**. Sinh câu trả lời nặng token ⇒ nên đi qua Groq; judge
    gọn (1 request/câu) ⇒ nên đi qua Gemini. Nếu sắp xếp theo tên thuần
    ⇒ ``gemini/...`` luôn đứng trước ``groq/...`` ⇒ đốt nhanh quota RPD.
    """

    def test_preferred_group_picks_highest_priority_provider(self) -> None:
        """Chỉ chọn model trong provider ưu tiên cao nhất."""
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [
                _FakeLLMClient("gemini/g1"),
                _FakeLLMClient("groq/q1"),
            ],
            quota_cooldown_s=900.0,
        )
        pool.provider_priority = ("groq", "gemini")
        group = pool.preferred_group(["gemini/g1", "groq/q1"])
        assert group == ["groq/q1"]

    def test_preferred_group_falls_back_when_priority_empty(self) -> None:
        """Provider ưu tiên hết quota ⇒ lùi xuống provider kế tiếp."""
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [
                _FakeLLMClient("gemini/g1"),
                _FakeLLMClient("groq/q1"),
            ],
            quota_cooldown_s=900.0,
        )
        pool.provider_priority = ("groq", "gemini")
        group = pool.preferred_group(["gemini/g1"])
        assert group == ["gemini/g1"]

    def test_healthy_keys_sorted_by_provider_priority(self) -> None:
        """`healthy_keys` sắp theo ưu tiên provider, rồi theo tên model."""
        from src.evaluation.evaluate_rag import PooledLLM

        pool = PooledLLM(
            [
                _FakeLLMClient("gemini/g1"),
                _FakeLLMClient("groq/q1"),
            ],
            quota_cooldown_s=900.0,
        )
        pool.provider_priority = ("groq", "gemini")
        assert pool.healthy_keys() == ["groq/q1", "gemini/g1"]

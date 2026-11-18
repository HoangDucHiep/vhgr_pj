"""Test cho các fix D-126 → D-130 (hạ tầng đo lường & quota).

Nội dung:
- **D-126**: model Gemini *thinking* cần ngân sách token riêng.
- **D-127**: cache LLM không lưu phản hồi rỗng.
- **D-128**: phân biệt hạn mức RPM (phút) với RPD (ngày).
- **D-129**: ngân sách context cho judge là tham số cấu hình.
- **D-130**: driver eval lặp có điều kiện thoát rõ ràng.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from src.common.llm_client import LLMCache, ProviderConfig
from src.evaluation.evaluate_rag import (
    JUDGE_PROMPT,
    THINKING_MODEL_PREFIXES,
    Judge,
    PooledLLM,
    _is_thinking_model,
    build_client_pool,
    compact_context,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------------
# D-126 — model thinking
# ----------------------------------------------------------------------


class TestThinkingModel:
    """D-126 — nhận diện model thinking + ngân sách token."""

    @pytest.mark.parametrize(
        "model",
        ["gemini-4-hydrogen", "gemini-4-argon", "gemini-4-carbon"],
    )
    def test_nhan_dien_model_thinking(self, model: str) -> None:
        """Model `gemini-4-*` là thinking ⇒ cần ngân sách token riêng."""
        assert _is_thinking_model(model) is True

    @pytest.mark.parametrize(
        "model",
        [
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
            "gemini-3-flash-preview",
        ],
    )
    def test_model_thuong_khong_phai_thinking(self, model: str) -> None:
        """Model flash thường **không** thinking ⇒ giữ hành vi cũ."""
        assert _is_thinking_model(model) is False

    def test_pool_bat_thinking_cho_model_thinking(self) -> None:
        """`build_client_pool()` bật cờ thinking cho model `gemini-4-*`."""
        clients = build_client_pool("gemini", ["gemini-4-hydrogen"])
        provider = clients[0].providers[0]
        assert provider.thinking is True
        assert provider.thinking_budget > 0

    def test_pool_khong_bat_thinking_cho_model_thuong(self) -> None:
        """Model thường ⇒ `thinking = False` ⇒ `max_output_tokens` giữ nguyên."""
        clients = build_client_pool("gemini", ["gemini-3.1-flash-lite"])
        provider = clients[0].providers[0]
        assert provider.thinking is False

    def test_provider_config_co_truong_thinking(self) -> None:
        """`ProviderConfig` có `thinking` + `thinking_budget`."""
        fields = ProviderConfig.__dataclass_fields__
        assert "thinking" in fields
        assert "thinking_budget" in fields

    def test_tien_to_thinking_khai_bao(self) -> None:
        """Hằng số tiền tố phải tồn tại và không rỗng."""
        assert THINKING_MODEL_PREFIXES
        assert all(p.startswith("gemini") for p in THINKING_MODEL_PREFIXES)


# ----------------------------------------------------------------------
# D-127 — cache không lưu phản hồi rỗng
# ----------------------------------------------------------------------


class TestCacheNoEmpty:
    """D-127 — phản hồi rỗng không được ghi vào cache."""

    def test_cache_khong_luu_phan_hoi_rong(self, tmp_path: Path) -> None:
        """Ghi chuỗi rỗng ⇒ cache **không** có bản ghi."""
        cache = LLMCache(tmp_path / "cache.sqlite", enabled=True)
        cache.set("k1", "model-x", "")
        cache.set("k2", "model-x", "   \n ")
        assert cache.get("k1") is None
        assert cache.get("k2") is None
        assert cache.count() == 0

    def test_cache_van_luu_phan_hoi_hop_le(self, tmp_path: Path) -> None:
        """Phản hồi có nội dung ⇒ vẫn được cache (để tái lập được)."""
        cache = LLMCache(tmp_path / "cache.sqlite", enabled=True)
        cache.set("k1", "model-x", "câu trả lời")
        assert cache.get("k1") == "câu trả lời"
        assert cache.count() == 1

    def test_script_don_cache_ton_tai(self) -> None:
        """Script dọn cache phải có trong repo (dùng được cho vận hành)."""
        script = REPO_ROOT / "scripts" / "clean_llm_cache.py"
        assert script.exists()
        assert "TRIM(response) = ''" in script.read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# D-128 — RPM vs RPD
# ----------------------------------------------------------------------


class TestRpmVersusRpd:
    """D-128 — mốc reset ngắn ⇒ RPM ⇒ cooldown ngắn."""

    def _pool(self) -> PooledLLM:
        """Dựng pool rỗng chỉ để kiểm tra tham số cooldown."""
        return PooledLLM(
            [],
            quota_cooldown_s=900.0,
            rpd_threshold_s=1800.0,
            max_cooldown_s=14400.0,
        )

    def test_moc_reset_ngan_cooldown_ngan(self) -> None:
        """Mốc reset 30 s (< ngưỡng) ⇒ coi là RPM ⇒ cooldown ngắn."""
        pool = self._pool()
        error = RuntimeError("429 quota exceeded. Please retry in 30s.")
        pool._record_quota_cooldown("m1", error)
        cooldown = pool._cooldown_until["m1"] - __import__("time").time()
        assert cooldown <= 120.0

    def test_gemini_bo_qua_moc_reset_dai(self) -> None:
        """Gemini báo mốc reset **không đáng tin** ⇒ cooldown ngắn (D-130)."""
        pool = self._pool()
        error = RuntimeError("429 quota exceeded. Please retry in 2h15m4s.")
        pool._record_quota_cooldown("gemini/m1", error)
        cooldown = pool._cooldown_until["gemini/m1"] - __import__("time").time()
        assert cooldown <= 120.0

    def test_groq_tin_moc_reset_dai(self) -> None:
        """Groq báo mốc reset TPD **chính xác** ⇒ tin mốc đó."""
        pool = self._pool()
        error = RuntimeError("429 rate limit reached on tokens per day. Try again in 2h15m4s.")
        pool._record_quota_cooldown("groq/m1", error)
        cooldown = pool._cooldown_until["groq/m1"] - __import__("time").time()
        assert cooldown > 3000.0

    def test_khong_co_moc_reset_dung_quota_cooldown(self) -> None:
        """Không có mốc reset ⇒ dùng `quota_cooldown_s` mặc định."""
        pool = self._pool()
        pool._record_quota_cooldown("m1", RuntimeError("429 quota"))
        cooldown = pool._cooldown_until["m1"] - __import__("time").time()
        assert 800.0 < cooldown <= 900.0

    def test_cli_co_tham_so_rpm_rpd(self) -> None:
        """Harness có 2 CLI arg cho RPM/RPD."""
        source = (REPO_ROOT / "src" / "evaluation" / "evaluate_rag.py").read_text(
            encoding="utf-8"
        )
        assert "--rpd-threshold-s" in source
        assert "--rpm-min-cooldown-s" in source


# ----------------------------------------------------------------------
# D-129 — ngân sách context cho judge
# ----------------------------------------------------------------------


class TestJudgeContextBudget:
    """D-129 — ngân sách context của judge là tham số."""

    def test_score_nhan_tham_so_context_chars(self) -> None:
        """`Judge.score()` nhận `context_chars`."""
        params = inspect.signature(Judge.score).parameters
        assert "context_chars" in params

    def test_context_chars_mac_dinh(self) -> None:
        """Mặc định 9.000 ký tự (đủ cho Gemini, vừa cho Groq 3 arm)."""
        params = inspect.signature(Judge.score).parameters
        assert params["context_chars"].default == 9000

    def test_compact_context_giu_ton_tran(self) -> None:
        """`compact_context` cắt context theo trần `total`."""
        context = "\n\n".join(f"[{i}] " + ("x" * 500) for i in range(1, 30))
        assert len(compact_context(context, per_block=600, total=2200)) <= 2200

    def test_cli_co_tham_so_judge_context(self) -> None:
        """Harness có CLI arg `--judge-context-chars`."""
        source = (REPO_ROOT / "src" / "evaluation" / "evaluate_rag.py").read_text(
            encoding="utf-8"
        )
        assert "--judge-context-chars" in source

    def test_prompt_judge_co_phan_phuong_an(self) -> None:
        """Prompt judge yêu cầu chấm **đúng 1 entry cho mỗi phương án**."""
        assert "PHƯƠNG ÁN" in JUDGE_PROMPT
        assert "scores" in JUDGE_PROMPT


# ----------------------------------------------------------------------
# D-130 — driver eval lặp
# ----------------------------------------------------------------------


class TestEvalLoopDriver:
    """D-130 — driver có điều kiện thoát rõ ràng (không treo)."""

    def test_driver_ton_tai(self) -> None:
        """Script driver phải có trong repo."""
        script = REPO_ROOT / "scripts" / "run_narrative_eval_loop.sh"
        assert script.exists()

    def test_driver_dung_resume(self) -> None:
        """Driver dùng `--resume` ⇒ không làm lại câu đã xong."""
        text = (
            REPO_ROOT / "scripts" / "run_narrative_eval_loop.sh"
        ).read_text(encoding="utf-8")
        assert "--resume" in text

    def test_driver_co_dieu_kien_thoat(self) -> None:
        """Driver dừng khi đủ 60 câu ⇒ không lặp vô hạn."""
        text = (
            REPO_ROOT / "scripts" / "run_narrative_eval_loop.sh"
        ).read_text(encoding="utf-8")
        assert "-ge 60" in text
        assert "break" in text

    def test_driver_dung_mot_model_cho_ca_gen_va_judge(self) -> None:
        """1 model cho gen + judge ⇒ 3 arm cùng model ⇒ không confound."""
        text = (
            REPO_ROOT / "scripts" / "run_narrative_eval_loop.sh"
        ).read_text(encoding="utf-8")
        assert text.count("--gen-pool") == 1
        assert text.count("--judge-pool") == 1


# ----------------------------------------------------------------------
# D-135 — nhận diện chính xác RPM vs RPD của Gemini qua `quota_id`
# ----------------------------------------------------------------------


class TestGeminiQuotaKind:
    """D-135 — phân loại hạn mức Gemini theo `quota_id` trong lỗi 429."""

    RPD_ERROR = (
        "429 ResourceExhausted: Quota exceeded for metric: "
        "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
        "limit: 500, model: gemini-3.5-flash-lite, description: Generate content "
        "requests per day limit exceeded on Free Tier. Please retry in 1h25m3s.\n"
        "violations {\n"
        "  description: \"Quota exceeded.\"\n"
        "  quota_metric: \"generativelanguage.googleapis.com/"
        "generate_content_free_tier_requests\"\n"
        "  quota_id: \"GenerateRequestsPerDayPerProjectPerModel-FreeTier\"\n"
        "}"
    )
    RPM_ERROR = (
        "429 ResourceExhausted: Quota exceeded for metric: "
        "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
        "limit: 15, model: gemini-3.5-flash-lite. Please retry in 30s.\n"
        "violations {\n"
        "  quota_id: \"GenerateRequestsPerMinutePerProjectPerModel-FreeTier\"\n"
        "}"
    )

    def _pool(self) -> PooledLLM:
        """Dựng pool rỗng chỉ để kiểm tra tham số cooldown."""
        return PooledLLM(
            [],
            quota_cooldown_s=900.0,
            rpd_threshold_s=1800.0,
            rpm_min_cooldown_s=60.0,
            max_cooldown_s=14400.0,
        )

    def test_nhan_dien_rpd(self) -> None:
        """`quota_id` chứa `PerDay` ⇒ hạn mức ngày."""
        assert (
            PooledLLM._gemini_quota_kind(RuntimeError(self.RPD_ERROR)) == "rpd"
        )

    def test_nhan_dien_rpm(self) -> None:
        """`quota_id` chứa `PerMinute` ⇒ hạn mức phút."""
        assert (
            PooledLLM._gemini_quota_kind(RuntimeError(self.RPM_ERROR)) == "rpm"
        )

    def test_khong_nhan_dien_duoc(self) -> None:
        """Lỗi không có `quota_id` ⇒ không đoán ⇒ ``None``."""
        assert PooledLLM._gemini_quota_kind(RuntimeError("429 quota")) is None

    def test_rpd_cooldown_dai(self) -> None:
        """RPD ⇒ cooldown **dài** (tin mốc provider, có trần)."""
        pool = self._pool()
        pool._record_quota_cooldown("gemini/m1", RuntimeError(self.RPD_ERROR))
        cooldown = pool._cooldown_until["gemini/m1"] - __import__("time").time()
        assert cooldown > 3000.0

    def test_rpm_cooldown_ngan(self) -> None:
        """RPM ⇒ cooldown **ngắn** (60 s) ⇒ thử lại sớm."""
        pool = self._pool()
        pool._record_quota_cooldown("gemini/m1", RuntimeError(self.RPM_ERROR))
        cooldown = pool._cooldown_until["gemini/m1"] - __import__("time").time()
        assert cooldown <= 120.0

    def test_rpd_thang_ke_vao_gemini(self) -> None:
        """Lỗi RPD của Gemini **không** rơi vào nhánh cooldown ngắn (D-130)."""
        pool = self._pool()
        pool._record_quota_cooldown("gemini/m1", RuntimeError(self.RPD_ERROR))
        cooldown = pool._cooldown_until["gemini/m1"] - __import__("time").time()
        assert cooldown > 120.0

"""Test cho module `src.coref.honorifics` — dò danh xưng/đại từ (Phase 6).

Nguyên tắc kiểm thử
-------------------
- Dùng fixture nhỏ, **không** phụ thuộc dữ liệu thật.
- Mỗi test kiểm tra một quy tắc ngôn ngữ cụ thể đã ghi nhận trong
  `docs/10-nhat-ky/phase-06.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.coref.honorifics import (  # noqa: E402
    detect_pronouns,
    infer_gender_from_name,
    is_person_honorific,
    load_honorifics,
)

HONORIFICS_PATH = REPO_ROOT / "configs" / "honorifics.yaml"


@pytest.fixture(scope="module")
def honorifics():
    """Nạp từ điển danh xưng thật từ `configs/honorifics.yaml`."""
    return load_honorifics(HONORIFICS_PATH)


def _spans(text: str, honorifics) -> list:
    """Dò span danh xưng/đại từ trong `text` (không có span NER nào)."""
    return detect_pronouns(text, [], honorifics)


class TestDetectPronouns:
    """Kiểm tra việc dò span danh xưng/đại từ."""

    def test_detects_ong(self, honorifics):
        """Dò được đại từ "ông"."""
        spans = _spans("Ông rất tài giỏi.", honorifics)
        assert len(spans) == 1
        assert spans[0].text.lower() == "ông"
        assert spans[0].label == "PERSON"
        assert spans[0].gender == "male"

    def test_detects_ba(self, honorifics):
        """Dò được đại từ "bà" và suy giới tính nữ."""
        spans = _spans("Bà là người sớm suy luận.", honorifics)
        assert len(spans) == 1
        assert spans[0].text.lower() == "bà"
        assert spans[0].gender == "female"

    def test_longest_match_ong_ay(self, honorifics):
        """"ông ấy" phải ưu tiên hơn "ông" (longest-match)."""
        spans = _spans("ông ấy đã ra trận.", honorifics)
        assert len(spans) == 1
        assert spans[0].text.lower() == "ông ấy"

    def test_detects_vua(self, honorifics):
        """Dò được danh xưng "vua" (nhãn PERSON, giới tính nam)."""
        spans = _spans("Vua Lê mất năm 1416.", honorifics)
        titles = [s for s in spans if s.text.lower() == "vua"]
        assert titles
        assert titles[0].label == "PERSON"
        assert titles[0].gender == "male"

    def test_ignores_y_te(self, honorifics):
        """Không dò "y tế" (false-positive 205/401 đo được ở Phase 6)."""
        spans = _spans("Bệnh viện Y tế đã cứu bệnh nhân.", honorifics)
        assert not [s for s in spans if s.text.lower() == "y"]

    def test_ignores_ba_vi(self, honorifics):
        """Không dò "Ba Vì" (tên địa danh, không phải danh xưng)."""
        spans = _spans("Ba Vì là một phường của Hà Nội.", honorifics)
        assert not [s for s in spans if s.text.lower() == "ba"]

    def test_skips_overlapping_ner_span(self, honorifics):
        """Không dò span trùng với span NER đã biết."""
        text = "Vua Lê mất năm 1416."
        # NER đã bắt "Vua Lê" (0, 7).
        spans = detect_pronouns(text, [(0, 7)], honorifics)
        assert not spans

    def test_offsets_are_exact(self, honorifics):
        """Offset trả về phải khớp chính xác văn bản."""
        text = "Nguyễn Huệ, sau này là Quang Trung, từng là vua."
        for span in _spans(text, honorifics):
            assert text[span.start : span.end] == span.text


class TestNameAfterHonorific:
    """Kiểm tra việc bắt tên riêng đi kèm danh xưng."""

    def test_simple_name(self, honorifics):
        """"vua Lê" → bắt được tên "Lê"."""
        spans = _spans("Vua Lê mất năm 1416.", honorifics)
        vua = next(s for s in spans if s.text.lower() == "vua")
        assert vua.name_text == "Lê"

    def test_forward_connector(self, honorifics):
        """"vua, tức là Lê Ý Tông" → bắt tên sau nối."""
        text = "lập em Duy Phường làm vua, tức là Lê Ý Tông."
        spans = _spans(text, honorifics)
        vua = next(s for s in spans if s.text.lower() == "vua")
        assert vua.name_text == "Lê Ý Tông"

    def test_forward_kinship(self, honorifics):
        """"vua em Lê Long Đĩnh" → bắt tên sau từ quan hệ họ tập."""
        text = "thờ cùng với Lê Đại Hành và vua em Lê Long Đĩnh."
        spans = _spans(text, honorifics)
        vua = next(s for s in spans if s.text.lower() == "vua")
        assert vua.name_text == "Lê Long Đĩnh"

    def test_parenthesized_name(self, honorifics):
        """"Hoàng đế (Chu Đệ)" → bắt tên trong ngoặc."""
        text = "Đại Tông Văn Hoàng đế (Chu Đệ) đã tha tội."
        spans = _spans(text, honorifics)
        hoang = next(s for s in spans if "Hoàng đế" in s.text)
        assert hoang.name_text == "Chu Đệ"


class TestPlural:
    """Kiểm tra phát hiện đại từ số nhiều."""

    def test_plural_cac_ong(self, honorifics):
        """"các ông" → đánh dấu số nhiều."""
        spans = _spans("tôi yêu cầu các ông dành cho tôi các nghi thức.", honorifics)
        ong = next(s for s in spans if s.text.lower() == "ông")
        assert ong.is_plural is True

    def test_plural_cac_vua(self, honorifics):
        """"các triều vua Trần" → "vua" đứng sau dấu hiệu số nhiều."""
        spans = _spans("cuộc đời ông dưới các triều vua Trần thì có thể đoán.", honorifics)
        vua = next(s for s in spans if s.text.lower() == "vua")
        assert vua.is_plural is True

    def test_singular_not_plural(self, honorifics):
        """"ông" đứng một mình không phải số nhiều."""
        spans = _spans("Sau đó ông tục huyền với bà Nguyễn Thị Mão.", honorifics)
        ong = next(s for s in spans if s.text.lower() == "ông")
        assert ong.is_plural is False


class TestHelpers:
    """Kiểm tra các hàm trợ giúp."""

    def test_is_person_honorific(self):
        """Chỉ nhãn PERSON mới là danh xưng người."""
        assert is_person_honorific("PERSON") is True
        assert is_person_honorific("TITLE") is False

    def test_infer_gender_from_name(self):
        """Suy giới tính từ tiền tố tên."""
        assert infer_gender_from_name("Bà Huyện Thanh Quan") == "female"
        assert infer_gender_from_name("Bà Trịnh Thị Ngọc Lung") == "female"
        assert infer_gender_from_name("Nguyễn Văn Nhơn") is None

    def test_honorifics_sorted_by_length_desc(self, honorifics):
        """Từ điển phải sắp giảm dần độ dài (longest-match)."""
        lengths = [len(h.surface) for h in honorifics]
        assert lengths == sorted(lengths, reverse=True)

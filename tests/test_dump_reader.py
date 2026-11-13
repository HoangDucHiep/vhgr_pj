"""Test cho module đọc dump và bộ lọc Phase 1."""

from __future__ import annotations

import bz2
from pathlib import Path

import pytest

from src.preprocess.dump_reader import (
    extract_categories,
    extract_infobox_type,
    extract_links,
    iter_dump_pages,
)

SAMPLE_XML = """<?xml version="1.0" encoding="utf-8"?>
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <page>
    <title>Lê Lợi</title>
    <ns>0</ns>
    <id>12345</id>
    <revision>
      <id>99000000</id>
      <timestamp>2026-01-01T00:00:00Z</timestamp>
      <text xml:space="preserve">{{Infobox person
| tên = Lê Lợi
| sinh = 10 tháng 9 năm 1385
| mất = 5 tháng 9 năm 1433
}}
'''Lê Lợi''' ({{lang|en|Le Loi}}, 1385 — 1433) là một nhà chính trị và người khởi nghĩa.
Ông lớn lên tại [[Thành phố Thanh Hóa]].
[[Trận Bạch Đằng (1406)]] là trận quyết định.
[[Thể loại:Nhân vật thời Lê]]
[[Thể loại:Nhà Lê]]
</text>
    </revision>
  </page>
  <page>
    <title>Một bài redirect</title>
    <ns>0</ns>
    <id>999</id>
    <redirect title="Lê Lợi" />
    <revision>
      <id>1</id>
      <text xml:space="preserve">#đổi [[Lê Lợi]]</text>
    </revision>
  </page>
  <page>
    <title>Thảo luận:Lê Lợi</title>
    <ns>1</ns>
    <id>1000</id>
    <revision>
      <id>2</id>
      <text xml:space="preserve">nội dung thảo luận</text>
    </revision>
  </page>
  <page>
    <title>Bài có QID</title>
    <ns>0</ns>
    <id>2000</id>
    <page_props>
      <wikibase_item>Q123456</wikibase_item>
    </page_props>
    <revision>
      <id>3</id>
      <text xml:space="preserve">nội dung bài viết</text>
    </revision>
  </page>
</mediawiki>
"""


@pytest.fixture(scope="module")
def dump_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Tạo file dump XML nhỏ để test.

    Returns:
        Đường dẫn file `.xml.bz2`.
    """
    path = tmp_path_factory.mktemp("dump") / "sample.xml.bz2"
    with bz2.open(path, "wb") as handle:
        handle.write(SAMPLE_XML.encode("utf-8"))
    return path


def test_iter_dump_pages_doc_du_cac_trang(dump_file: Path) -> None:
    """Đọc được toàn bộ 4 trang trong file mẫu."""
    pages = list(iter_dump_pages(dump_file))
    assert len(pages) == 4


def test_page_co_bang_dung_truong(dump_file: Path) -> None:
    """Trang đầu có đủ page_id, title, ns, revision_id, wikitext."""
    pages = {p.title: p for p in iter_dump_pages(dump_file)}
    le_loi = pages["Lê Lợi"]
    assert le_loi.page_id == 12345
    assert le_loi.ns == 0
    assert le_loi.revision_id == 99000000
    assert le_loi.is_redirect is False
    assert "Lê Lợi" in le_loi.wikitext


def test_redirect_duoc_nhan_dien(dump_file: Path) -> None:
    """Trang có thẻ <redirect> bị đánh dấu redirect."""
    pages = {p.title: p for p in iter_dump_pages(dump_file)}
    redirect = pages["Một bài redirect"]
    assert redirect.is_redirect is True
    assert redirect.redirect_target == "Lê Lợi"


def test_namespace_duoc_giu(dump_file: Path) -> None:
    """Trang namespace 1 (thảo luận) có ns = 1."""
    pages = {p.title: p for p in iter_dump_pages(dump_file)}
    assert pages["Thảo luận:Lê Lợi"].ns == 1


def test_qid_tu_page_props(dump_file: Path) -> None:
    """QID được trích từ <page_props><wikibase_item>."""
    pages = {p.title: p for p in iter_dump_pages(dump_file)}
    assert pages["Bài có QID"].qid == "Q123456"
    assert pages["Lê Lợi"].qid is None


def test_extract_categories() -> None:
    """Trích category và bỏ tiền tố namespace."""
    wikitext = "[[Thể loại:Nhân vật thời Lê]]\n[[Thể loại:Nhà Lê]]"
    assert extract_categories(wikitext) == ["Nhân vật thời Lê", "Nhà Lê"]


def test_extract_categories_khong_trung_lap() -> None:
    """Category lặp lại chỉ giữ 1 lần."""
    wikitext = "[[Thể loại:A]][[Thể loại:A]]"
    assert extract_categories(wikitext) == ["A"]


def test_extract_links_bo_the_loai() -> None:
    """Link tới Thể loại/Wikipedia không được coi là bài viết."""
    wikitext = "[[Lê Lợi]] [[Thể loại:Nhà Lê]] [[Wikipedia:Vua]] [[Tập tin:X.jpg]]"
    links = extract_links(wikitext)
    assert "Lê Lợi" in links
    assert "Thể loại:Nhà Lê" not in links
    assert "Wikipedia:Vua" not in links
    assert "Tập tin:X.jpg" not in links


def test_extract_links_bo_anchor() -> None:
    """Phần sau dấu # bị loại khỏi tiêu đề link."""
    links = extract_links("[[Lê Lợi#Đời sống]]")
    assert links == ["Lê Lợi"]


def test_extract_links_bo_link_ngon_ngu_khac() -> None:
    """Link ``en:Foo`` không phải bài viết tiếng Việt."""
    links = extract_links("[[en:Lê Lợi]] [[Lê Lợi]]")
    assert links == ["Lê Lợi"]


def test_extract_infobox_type_person() -> None:
    """Infobox person → loại person."""
    assert extract_infobox_type("{{Infobox person\n|sinh=1385\n}}") == "person"


def test_extract_infobox_type_battle() -> None:
    """Infobox battle → loại battle."""
    assert extract_infobox_type("{{Infobox battle\n|date=1406\n}}") == "battle"


def test_extract_infobox_type_viet_nam() -> None:
    """Infobox tiếng Việt ``Thông tin`` cũng được nhận diện."""
    assert extract_infobox_type("{{Thông tin nhân vật\n|tên=Lê Lợi\n}}") == "person"


def test_extract_infobox_type_khong_co() -> None:
    """Không có infobox → None."""
    assert extract_infobox_type("Bài viết bình thường không có infobox") is None


def test_dump_reader_la_generator_khong_nap_toan_bo(dump_file: Path) -> None:
    """Hàm trả về generator (tiêu chí streaming của python-standards)."""
    import types

    assert isinstance(iter_dump_pages(dump_file), types.GeneratorType)

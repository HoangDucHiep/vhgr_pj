"""Sinh định dạng ID bất biến của dự án.

| Đối tượng | Format | Ví dụ |
|---|---|---|
| `doc_id` | `doc_<page_id>` | `doc_12345` |
| `sentence_id` | `s<page_id>_<para_idx>_<sent_idx>` | `s12345_0_3` |
| `mention_id` | `m<sentence_id>_<idx>` | `ms12345_0_3_0` |
| `entity_id` | `ent_<slug>_<hash8>` | `ent_le_loi_1a2b3c4d` |
| `year_id` | `year_<năm>` | `year_1385` |
| `nil_id` | `nil_<hash8>` | `nil_9f2c1a7b` |

`hash8 = sha1(f"{type}|{name_normalized}")[:8]`

Luôn dùng các hàm trong module này — không tự viết chuỗi ID ở nơi khác.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime

from src.common.normalize import normalize_name, slugify

# Regex kiểm tra entity_id hợp lệ
ENTITY_ID_RE = re.compile(r"^ent_[a-z0-9_]{1,40}_[0-9a-f]{8}$")
YEAR_ID_RE = re.compile(r"^year_\d{1,4}$")
NIL_ID_RE = re.compile(r"^nil_[0-9a-f]{8}$")
DOC_ID_RE = re.compile(r"^doc_\d+$")
SENTENCE_ID_RE = re.compile(r"^s\d+_\d+_\d+$")
MENTION_ID_RE = re.compile(r"^ms\d+_\d+_\d+_\d+$")


def _hash8(entity_type: str, name_normalized: str) -> str:
    """Tính hash 8 ký tự từ ``f"{type}|{name_normalized}"``.

    Args:
        entity_type: Loại thực thể (vd ``"person"``).
        name_normalized: Tên đã chuẩn hóa (bỏ dấu, lowercase).

    Returns:
        Chuỗi hex 8 ký tự.
    """
    payload = f"{entity_type}|{name_normalized}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:8]


def make_entity_id(entity_type: str, name: str) -> str:
    """Sinh ``entity_id`` theo format ``ent_<slug>_<hash8>``.

    Args:
        entity_type: Loại thực thể: ``person``/``dynasty``/``event``/``place``/
            ``title``/``year``/``article``.
        name: Tên hiển thị (có dấu) của thực thể.

    Returns:
        Chuỗi ``entity_id``, ví dụ ``"ent_le_loi_1a2b3c4d"``.
    """
    name_normalized = normalize_name(name)
    slug = slugify(name)
    return f"ent_{slug}_{_hash8(entity_type, name_normalized)}"


def make_year_id(year: int) -> str:
    """Sinh ``year_id`` theo format ``year_<năm>``.

    Args:
        year: Năm (dương lịch).

    Returns:
        Chuỗi ``year_id``, ví dụ ``"year_1385"``.
    """
    return f"year_{int(year)}"


def make_nil_id(name: str) -> str:
    """Sinh ``nil_id`` cho thực thể chưa liên kết được.

    Args:
        name: Chuỗi mô tả thực thể nil (ví dụ chuỗi trong câu).

    Returns:
        Chuỗi ``nil_id``, ví dụ ``"nil_9f2c1a7b"``.
    """
    payload = name.strip().lower().encode("utf-8")
    return f"nil_{hashlib.sha1(payload).hexdigest()[:8]}"


def make_doc_id(page_id: int) -> str:
    """Sinh ``doc_id`` theo format ``doc_<page_id>``.

    Args:
        page_id: ID trang Wikipedia.

    Returns:
        Chuỗi ``doc_id``, ví dụ ``"doc_12345"``.
    """
    return f"doc_{int(page_id)}"


def make_sentence_id(page_id: int, para_idx: int, sent_idx: int) -> str:
    """Sinh ``sentence_id`` theo format ``s<page_id>_<para_idx>_<sent_idx>``.

    Args:
        page_id: ID trang Wikipedia.
        para_idx: Chỉ số đoạn (0-based).
        sent_idx: Chỉ số câu trong đoạn (0-based).

    Returns:
        Chuỗi ``sentence_id``, ví dụ ``"s12345_0_3"``.
    """
    return f"s{int(page_id)}_{int(para_idx)}_{int(sent_idx)}"


def make_mention_id(sentence_id: str, idx: int) -> str:
    """Sinh ``mention_id`` theo format ``m<sentence_id>_<idx>``.

    Args:
        sentence_id: ID câu chứa mention.
        idx: Chỉ số mention trong câu (0-based).

    Returns:
        Chuỗi ``mention_id``, ví dụ ``"ms12345_0_3_0"``.
    """
    return f"m{sentence_id}_{int(idx)}"


def make_run_id(now: datetime | None = None) -> str:
    """Sinh ``run_id`` theo format ``r<YYYYMMDD-HHMMSS>``.

    Args:
        now: Thời điểm (mặc định lấy hiện tại).

    Returns:
        Chuỗi ``run_id``, ví dụ ``"r20261113-210700"``.
    """
    moment = now or datetime.now()
    return moment.strftime("r%Y%m%d-%H%M%S")


def is_valid_entity_id(entity_id: str) -> bool:
    """Kiểm tra ``entity_id`` có đúng format không.

    Args:
        entity_id: Chuỗi cần kiểm tra.

    Returns:
        ``True`` nếu hợp lệ.
    """
    return bool(ENTITY_ID_RE.match(entity_id or ""))


def is_valid_year_id(year_id: str) -> bool:
    """Kiểm tra ``year_id`` có đúng format không.

    Args:
        year_id: Chuỗi cần kiểm tra.

    Returns:
        ``True`` nếu hợp lệ.
    """
    return bool(YEAR_ID_RE.match(year_id or ""))

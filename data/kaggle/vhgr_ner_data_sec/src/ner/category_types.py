"""Tra loại entity từ **category Wikipedia** (Phase 4 — B2.1).

Vì sao cần: Wikidata `P31` cho kết quả **không ổn định** với corpus tiếng
Việt — nhiều bài Việt Nam không có `P31` chuẩn (vd "Lê Lợi" không có QID
trong dump), và khi `P31` là lớp generic ("human") thì mọi người đều thành
`PERSON` — kể cả khi tên đích thực ra là quốc gia hay địa danh.

Trong khi đó, **category Wikipedia** do biên tập viên gắn là tín hiệu **rõ
ràng và đúng** cho từng bài:
- "Người Hà Nội", "Người họ Nguyễn tại Việt Nam" → `PERSON`
- "Thành phố thuộc tỉnh (Việt Nam)", "Tỉnh của Việt Nam" → `LOCATION`
- "Trận đánh liên quan tới Việt Nam", "Chiến tranh Việt Nam" → `EVENT`
- "Nhà Nguyễn", "Vương triều Nguyễn" → `DYNASTY`
- "Miếu hiệu", "Tước vị trong lịch sử Việt Nam" → `TITLE`

Vì vậy thứ tự ưu tiên nguồn nhãn trong `build_silver.py` là:

1. ``category`` — category Wikipedia (mạnh nhất cho corpus này).
2. ``qid_direct`` / ``qid_ancestor`` — Wikidata `P31` / `P279`.
3. ``kg_type`` — loại node KG (Phase 3).
4. ``wikidata_signal`` — tín hiệu Phase 1.
5. ``pattern`` — mẫu tên.
6. ``time_regex`` — regex năm/thế kỷ.

Module này cung cấp:

- :func:`load_target_categories` — nạp category của mọi đích link.
- :func:`classify_category` — suy nhãn từ danh sách category.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.common.config import resolve_path
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Nhãn NER hợp lệ.
NER_LABELS: tuple[str, ...] = ("PERSON", "DYNASTY", "EVENT", "LOCATION", "TIME", "TITLE")

def strip_accents(text: str) -> str:
    """Bỏ dấu + viết thường (dùng cho **khớp mẫu**, không phải hiển thị).

    Vì sao cần: tên category trong Wikipedia dùng **nhiều chính tả** cho
    cùng một khái niệm ("Miếu hiệu" vs "Miêu hiệu", "Tước vị" vs "Tước vĩ").
    Nếu viết pattern theo dấu, sẽ bỏ sót một nửa. Vì vậy **cả pattern và
    category đều được bỏ dấu trước khi khớp.

    Args:
        text: Chuỗi đầu vào.

    Returns:
        Chuỗi đã chuẩn hóa.
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped).lower().strip()


#: Mẫu category → nhãn. Thứ tự **quan trọng**: mẫu trên cùng thắng.
#:
#: LƯU Ý về `\\b`: mọi nhánh thay thế phải kết thúc bằng ranh giới từ.
#: Nếu không, "nha hoat dong" sẽ khớp nhánh `ho` của "nha ho" → gán nhầm
#: `DYNASTY` cho bài về nhà hoạt động.
CATEGORY_PATTERNS: tuple[tuple[str, str], ...] = (
    # --- TIME ---
    # CHỈ giữ category thực sự chỉ **đơn vị thời gian**. Các category kiểu
    # "Năm sinh không rõ" / "Năm mất thiếu" là **siêu dữ liệu** gắn cho bài
    # người → không được dùng để gán nhãn TIME cho cả bài.
    (r"^the ky\b", "TIME"),
    (r"^thap nien\b", "TIME"),
    (r"^moc thoi gian\b", "TIME"),
    (r"^ngay trong nam\b", "TIME"),
    (r"^can chi\b", "TIME"),
    # --- TITLE ---
    # LƯU Ý: "Miếu hiệu" (tước hiệu) khác "Miếu X" (công trình kiến trúc).
    # Vì vậy pattern TITLE phải khớp **trọn cụm** "miêu hieu", không phải "miêu ".
    # Dùng ký tự lớp `[ee]` vì "miếu" và "miêu" là 2 chính tả.
    (r"^mi[ee]u hieu\b", "TITLE"),
    (r"^thuy hieu\b", "TITLE"),
    (r"^trieu hieu\b", "TITLE"),
    (r"^tuoc v[ii]\b", "TITLE"),
    (r"^nam tuoc\b", "TITLE"),
    (r"^nu tuoc\b", "TITLE"),
    (r"^ngai v[ii]\b", "TITLE"),
    (r"^chuc vi\b", "TITLE"),
    (r"^danh hieu\b", "TITLE"),
    (r"^huy chuong\b", "TITLE"),
    (r"^huan chuong\b", "TITLE"),
    # "Quan lại nhà X" là **người** (vd "Quan lại nhà Nguyễn"), KHÔNG phải
    # tước hiệu → phải nằm sau mẫu PERSON. Chỉ "Quan lại" đứng một mình
    # (tước hiệu) mới là TITLE.
    (r"^quan ch[uc]c\b", "TITLE"),
    (r"^cong tuoc\b", "TITLE"),
    (r"^cong binh\b", "TITLE"),
    (r"^tuong (đai|quan|ngu)\b", "TITLE"),
    (r"^đai tuong\b", "TITLE"),
    (r"^tiet đo su\b", "TITLE"),
    (r"^tong thong\b", "TITLE"),
    (r"^thu tuong\b", "TITLE"),
    (r"^quan l[aai]i$", "TITLE"),
    # --- DYNASTY ---
    # Tên triều đại: "Nhà Nguyễn", "Nhà Lê", "Nhà Trần", "Nhà Hậu Lê"…
    (r"^nha (nguyen|le|tran|ly|tien|trieu|ho|ngo|dinh|mac)\b", "DYNASTY"),
    (r"^nha (hau|huu|trung hung|trung thuoc|đai|tieu hung)\b", "DYNASTY"),
    (r"^nha (tay son|tay|son)\b", "DYNASTY"),
    (r"^nha (dinh|đinh)\b", "DYNASTY"),
    (r"^nha (vua|hanh chinh)\b", "DYNASTY"),
    (r"^nha nuoc\b", "DYNASTY"),
    (r"^vuong trieu\b", "DYNASTY"),
    (r"^vua viet nam\b", "DYNASTY"),
    (r"^hoang toc\b", "DYNASTY"),
    (r"^ngai vang\b", "DYNASTY"),
    (r"^cuong quoc\b", "DYNASTY"),
    # --- EVENT ---
    (r"^tran\b", "EVENT"),
    (r"^chien tranh\b", "EVENT"),
    (r"^hiep đinh\b", "EVENT"),
    (r"^h[oo]i uoc\b", "EVENT"),
    (r"^khoi nghia\b", "EVENT"),
    (r"^su kien\b", "EVENT"),
    (r"^lich su (chien tranh|viet nam)\b", "EVENT"),
    (r"^nghe thuat co đao\b", "EVENT"),
    (r"^hoc thuyet\b", "EVENT"),
    (r"^phong trao\b", "EVENT"),
    (r"^thoi ky\b", "EVENT"),
    (r"^giai đoan\b", "EVENT"),
    (r"^cuoc chien\b", "EVENT"),
    (r"^tran đanh\b", "EVENT"),
    # --- PERSON ---
    # "Người <việc/tộc>" → người. Riêng "Người họ X" là dòng tộc, nhưng
    # category này cũng dùng cho bài cá nhân nên giữ `PERSON` (an toàn).
    (r"^nguoi\b", "PERSON"),
    # "Quan lại nhà X" / "Quan lại nhà Nguyễn" → **người** (chức quan),
    # không phải tước hiệu.
    (r"^quan l[aai]i\b", "PERSON"),
    # "Hoàng đế" là chức vị của **một người** → PERSON.
    (r"^hoang đe?t\b", "PERSON"),
    # "Nhà <nghề nghiệp>" là **người**, không phải triều đại.
    (r"^nha (hoat dong|hoa hoc|ngoai giao|ky thuat|trien|khai moi)\b", "PERSON"),
    (r"^nha (van|tho|hoa si|thi si|nhac si|đao dien|nha bao)\b", "PERSON"),
    (r"^nha (cach mang|giao duc|si|than)\b", "PERSON"),
    (r"^nha (đau tu|lap đia)\b", "PERSON"),
    (r"^nha (cai tri|tri thu)\b", "PERSON"),
    (r"^ngoi sao\b", "PERSON"),
    (r"^dien vien\b", "PERSON"),
    (r"^ca si\b", "PERSON"),
    (r"^nhac si\b", "PERSON"),
    (r"^van đong vien\b", "PERSON"),
    (r"^chinh khach\b", "PERSON"),
    (r"^đai bieu\b", "PERSON"),
    (r"^nhan vat lich su\b", "PERSON"),
    (r"^nhan vat trong\b", "PERSON"),
    (r"^nguoi that\b", "PERSON"),
    (r"^anh hung\b", "PERSON"),
    (r"^vuong (tu|nu)\b", "PERSON"),
    (r"^tuong (linh|quan)\b", "PERSON"),
    (r"^tuong\b", "PERSON"),
    (r"^vo si\b", "PERSON"),
    (r"^đau bep\b", "PERSON"),
    (r"^doanh nhan\b", "PERSON"),
    (r"^giai thuong\b", "PERSON"),
    # --- LOCATION ---
    (r"^thanh pho\b", "LOCATION"),
    (r"^thi xa\b", "LOCATION"),
    (r"^thi tran\b", "LOCATION"),
    (r"^tinh\b", "LOCATION"),
    (r"^huyen\b", "LOCATION"),
    (r"^xa\b", "LOCATION"),
    (r"^phuong\b", "LOCATION"),
    (r"^quan\b", "LOCATION"),
    (r"^lang\b", "LOCATION"),
    (r"^song\b", "LOCATION"),
    (r"^nui\b", "LOCATION"),
    (r"^ho\b", "LOCATION"),
    (r"^bien\b", "LOCATION"),
    (r"^đao\b", "LOCATION"),
    (r"^thanh\b", "LOCATION"),
    (r"^đia danh\b", "LOCATION"),
    (r"^đia ly\b", "LOCATION"),
    (r"^khu vuc\b", "LOCATION"),
    (r"^vung\b", "LOCATION"),
    (r"^chau\b", "LOCATION"),
    (r"^luc đia\b", "LOCATION"),
    (r"^quoc gia\b", "LOCATION"),
    (r"^đo thi\b", "LOCATION"),
    (r"^thu phu\b", "LOCATION"),
    (r"^cang\b", "LOCATION"),
    (r"^san bay\b", "LOCATION"),
    (r"^cong trinh\b", "LOCATION"),
    (r"^di tich\b", "LOCATION"),
    (r"^mi[ee]u\b", "LOCATION"),
    (r"^đen\b", "LOCATION"),
    (r"^chua\b", "LOCATION"),
    (r"^nha tho\b", "LOCATION"),
    (r"^bao tang\b", "LOCATION"),
    (r"^thu vien\b", "LOCATION"),
    (r"^truong\b", "LOCATION"),
    (r"^đai hoc\b", "LOCATION"),
    (r"^cau lac bo\b", "LOCATION"),
    (r"^san van đong\b", "LOCATION"),
)

#: Regex đã biên dịch. Cả pattern lẫn category đều **không dấu** trước khi
#: khớp (xem :func:`strip_accents`) → không phụ thuộc chính tả.
_COMPILED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(pattern), label) for pattern, label in CATEGORY_PATTERNS
]


def classify_category(category: str) -> str | None:
    """Suy nhãn NER từ tên category Wikipedia.

    Args:
        category: Tên category (có dấu).

    Returns:
        Nhãn NER, hoặc ``None`` nếu không khớp mẫu nào.
    """
    normalized = strip_accents(category)
    for pattern, label in _COMPILED:
        if pattern.search(normalized):
            return label
    return None


def load_target_categories(
    dump_facts_path: str | Path,
    targets: Iterable[str],
) -> dict[str, list[str]]:
    """Nạp danh sách category của các đích link.

    Args:
        dump_facts_path: Đường dẫn `dump_facts.jsonl` (có trường ``cats``).
        targets: Tập tên bài cần tra.

    Returns:
        Map ``{tên bài: [category, ...]}`` — chỉ chứa bài **có** category.
    """
    wanted = set(targets)
    result: dict[str, list[str]] = {}
    resolved = resolve_path(dump_facts_path)
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            title = record.get("title")
            if title not in wanted:
                continue
            cats = record.get("cats") or []
            if cats:
                result[title] = list(cats)
    return result


def classify_target(
    categories: list[str],
) -> tuple[str | None, str]:
    """Suy nhãn cho một đích link từ danh sách category của nó.

    Vì sao dùng **đếm phiếu** thay vì "category khớp đầu tiên": một bài có
    nhiều category (vd "Lê Lợi" có cả "Người họ Lê", "Nhà Lê", "Nhân vật
    lịch sử Việt Nam") — nếu lấy category đầu tiên thì kết quả phụ thuộc
    thứ tự categorylinks. Đếm phiếu theo nhãn rồi lấy nhãn có **điểm cao
    nhất** là ổn định hơn.

    Args:
        categories: Danh sách category của bài.

    Returns:
        Cặp ``(nhãn, category đã dùng)``; nhãn là ``None`` nếu không suy được.
    """
    votes: Counter[str] = Counter()
    evidence: dict[str, str] = {}
    for category in categories:
        label = classify_category(category)
        if label is None:
            continue
        votes[label] += 1
        if label not in evidence:
            evidence[label] = category
    if not votes:
        return None, ""
    # Ưu tiên nhãn có nhiều phiếu nhất; tie-break theo thứ tự NER_LABELS.
    best = max(
        votes.items(),
        key=lambda item: (item[1], -NER_LABELS.index(item[0])),
    )[0]
    return best, evidence.get(best, "")


def build_category_index(
    dump_facts_path: str | Path,
    targets: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Dựng chỉ mục ``{tên bài: {label, evidence, categories}}``.

    Args:
        dump_facts_path: Đường dẫn `dump_facts.jsonl`.
        targets: Tập tên bài cần tra.

    Returns:
        Map chỉ mục category.
    """
    categories_by_title = load_target_categories(dump_facts_path, targets)
    index: dict[str, dict[str, Any]] = {}
    for title, categories in categories_by_title.items():
        label, evidence = classify_target(categories)
        if label is None:
            continue
        index[title] = {
            "label": label,
            "evidence": evidence,
            "n_categories": len(categories),
        }
    logger.info("Chỉ mục category: %d/%d đích link có nhãn", len(index), len(categories_by_title))
    return index

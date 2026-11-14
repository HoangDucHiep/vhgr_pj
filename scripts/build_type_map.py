#!/usr/bin/env python3
"""Sinh `configs/wikidata_type_map.yaml` từ phân cấp lớp Wikidata (Phase 4).

Vì sao cần script này: bảng map QID → nhãn NER phải **phủ** hàng nghìn lớp
Wikidata thực tế (2.872 lớp `P31` trong corpus), trong khi viết tay chỉ phủ
vài chục. Vì vậy map được **sinh tự động** từ:

1. Đồ thị phân cấp lớp `P279` (``data/interim/class_hierarchy.json``).
2. Nhãn tiếng Anh/Việt của từng lớp (``data/interim/class_labels.json``).
3. Bảng **từ khoá** → nhãn NER (định nghĩa trong chính script này).

Hai nguyên tắc quan trọng:

- **Khớp theo ranh giới từ** — dùng ``\\b`` trong regex, không dùng
  ``in``. Nếu dùng ``in`` thì "vietnam" chứa "era" (→ TIME) và "ward"
  chứa "war" (→ EVENT) — hai lỗi nghiêm trọng.
- **Cụm dài thắng cụm ngắn** — "human settlement" (LOCATION) phải thắng
  "human" (PERSON); "calendar year" (TIME) thắng "year" (TIME).

Kết quả tách làm 2 bảng:

- ``direct``: tên lớp **tự nó** khớp từ khoá → nhãn (độ tin cậy cao).
- ``ancestor``: tên lớp không khớp, nhưng **lớp cha** khớp → nhãn.

Lớp nào không khớp từ khoá nào → **không** đưa vào map (nguyên tắc
"không bịa": thà bỏ còn hơn gán sai).

Cách chạy::

    python scripts/build_type_map.py
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Lớp KHÔNG phải thực thể → không gán nhãn nào.
EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "disambiguation page",
    "wikimedia list article",
    "wikimedia category",
    "wikimedia template",
    "wikipedia portal",
    "redirect page",
    "set of articles",
    "draft article",
    "wikimedia disambiguation page",
)

#: Từ khoá → nhãn NER. Thứ tự trong list **không** quyết định (dùng độ dài
#: cụm dài nhất), nhưng giữ nhóm cho dễ đọc.
KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    # --- TITLE ---
    (
        "TITLE",
        (
            "posthumous name",
            "temple name",
            "era name",
            "noble title",
            "military rank",
            "public office",
            "office",
            "position",
            "title",
            "mieu hieu",
            "thuy hieu",
            "trieu hieu",
            "danh hieu",
            "tước hiệu",
            "chuc vu",
            "huu chuc",
            "religious title",
        ),
    ),
    # --- DYNASTY ---
    (
        "DYNASTY",
        (
            "dynasty",
            "trieu dai",
            "royal house",
            "house of",
            "the dynasty",
            "vương triều",
            "vua",
            "nguoi",
            "nhà",
        ),
    ),
    # --- EVENT ---
    (
        "EVENT",
        (
            "battle",
            "war",
            "conflict",
            "campaign",
            "military operation",
            "rebellion",
            "uprising",
            "treaty",
            "siege",
            "skirmish",
            "expedition",
            "revolution",
            "revolt",
            "coup",
            "massacre",
            "insurrection",
            "hiệp ước",
            "chiến tranh",
            "trận",
            "khởi nghĩa",
            "sự kiện",
        ),
    ),
    # --- PERSON ---
    #
    # LƯU Ý: không dùng "sovereign" / "state" ở đây — "sovereign state"
    # (quốc gia) là LOCATION, còn "sovereign" (người tối cao) là PERSON.
    # Xử lý bằng cụm dài ở nhóm LOCATION ("sovereign state") + danh sách
    # loại trừ bên dưới.
    (
        "PERSON",
        (
            "human",
            "person",
            "người",
            "nguoi",
            "monarch",
            "empress",
            "emperor",
            "king",
            "queen",
            "prince",
            "princess",
            "general",
            "military officer",
            "politician",
            "historian",
            "writer",
            "poet",
            "composer",
            "painter",
            "scientist",
            "philosopher",
            "religious leader",
            "nhà vua",
            "hoàng đế",
            "tướng",
            "vua",
        ),
    ),
    # --- TIME ---
    (
        "TIME",
        (
            "calendar year",
            "year",
            "century",
            "decade",
            "era",
            "period",
            "calendar date",
            "date",
            "ngày",
            "thế kỷ",
            "thoi ky",
        ),
    ),
    # --- LOCATION ---
    (
        "LOCATION",
        (
            "human settlement",
            "sovereign state",
            "administrative territorial entity",
            "settlement",
            "city",
            "town",
            "village",
            "province",
            "district",
            "region",
            "country",
            "state",
            "nation",
            "empire",
            "kingdom",
            "commune",
            "ward",
            "capital",
            "island",
            "river",
            "mountain",
            "sea",
            "lake",
            "place",
            "location",
            "territory",
            "neighborhood",
            "geographic",
            "prefecture",
            "municipality",
            "county",
            "vùng",
            "khu vực",
            "tỉnh",
            "thành phố",
            "huyện",
            "làng",
            "xã",
            "thành",
            "áp",
        ),
    ),
]

#: Từ khoá **loại trừ** — nếu lớp chứa từ này thì KHÔNG map theo từ khoá
#: khác (dùng cụm dài hơn đã khớp). Ví dụ "sovereign state" chứa "sovereign"
#: (PERSON) → phải ưu tiên LOCATION.
EXCLUDE_IF_MATCHED: tuple[str, ...] = (
    "sovereign state",
    "island country",
    "constitutional monarchy",
    "unitary state",
    "historical country",
    "former country",
    "city in the",
    "commune of",
    "district of",
    "county of",
    "state of",
    "province of",
    "capital of",
    "country in",
)

#: Cache biên dịch regex theo từ khoá.
_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def strip_accents(text: str) -> str:
    """Bỏ dấu + viết thường.

    Args:
        text: Chuỗi đầu vào.

    Returns:
        Chuỗi đã chuẩn hóa.
    """
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped).lower().strip()


def normalize_label(label: str) -> str:
    """Chuẩn hóa nhãn lớp (bỏ hậu tố ngôn ngữ).

    Args:
        label: Nhãn thô (vd ``"human"@en``).

    Returns:
        Nhãn đã chuẩn hóa.
    """
    return strip_accents(label.split("@")[0].strip().strip('"'))


def _keyword_regex(keyword: str) -> re.Pattern[str]:
    """Biên dịch từ khoá thành regex khớp **theo ranh giới từ**.

    Args:
        keyword: Từ khoá đã bỏ dấu.

    Returns:
        Regex đã biên dịch (có cache).
    """
    pattern = _REGEX_CACHE.get(keyword)
    if pattern is None:
        # `\b` chỉ hoạt động với ký tự word; với tiếng Việt có dấu đã bỏ
        # nên dùng ranh giới "không phải chữ/số" tường minh.
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])")
        _REGEX_CACHE[keyword] = pattern
    return pattern


def classify_class_name(class_name: str) -> str | None:
    """Suy nhãn NER từ tên lớp.

    Nguyên tắc: **cụm dài nhất thắng**; nếu không khớp từ khoá nào → ``None``.

    Args:
        class_name: Tên lớp đã chuẩn hóa (bỏ dấu, viết thường).

    Returns:
        Nhãn NER, hoặc ``None`` nếu không xác định được.
    """
    if any(_keyword_regex(keyword).search(class_name) for keyword in EXCLUDE_KEYWORDS):
        return None

    # Cụm loại trừ (vd "sovereign state") được ưu tiên tuyệt đối.
    for phrase in EXCLUDE_IF_MATCHED:
        if _keyword_regex(phrase).search(class_name):
            # Chuỗi "sovereign state" → LOCATION, "commune of X" → LOCATION…
            for label, keywords in KEYWORD_RULES:
                if any(
                    _keyword_regex(keyword).search(phrase) for keyword in keywords
                ):
                    return label

    best_label: str | None = None
    best_length = 0
    for label, keywords in KEYWORD_RULES:
        for keyword in keywords:
            if len(keyword) <= best_length:
                continue
            if _keyword_regex(keyword).search(class_name):
                best_label = label
                best_length = len(keyword)
    return best_label


def main() -> int:
    """Điểm vào chính.

    Returns:
        Mã thoát.
    """
    hierarchy_path = REPO_ROOT / "data" / "interim" / "class_hierarchy.json"
    labels_path = REPO_ROOT / "data" / "interim" / "class_labels.json"
    qid_cache_path = REPO_ROOT / "data" / "interim" / "qid_types.json"
    out_path = REPO_ROOT / "configs" / "wikidata_type_map.yaml"

    hierarchy = json.loads(hierarchy_path.read_text(encoding="utf-8"))
    raw_labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels = {qid: normalize_label(text) for qid, text in raw_labels.items()}

    qid_cache = json.loads(qid_cache_path.read_text(encoding="utf-8"))
    p31 = qid_cache.get("p31") or {}
    class_freq: Counter[str] = Counter()
    for classes in p31.values():
        class_freq.update(classes)

    def ancestors_of(class_id: str) -> list[str]:
        """Liệt kê lớp cha theo thứ tự gần → xa.

        Args:
            class_id: Lớp cần tra.

        Returns:
            Danh sách lớp cha (không bao gồm lớp gốc).
        """
        result: list[str] = []
        seen = {class_id}
        frontier = [class_id]
        while frontier:
            nxt: list[str] = []
            for node in frontier:
                for parent in hierarchy.get(node) or []:
                    if parent not in seen:
                        seen.add(parent)
                        result.append(parent)
                        nxt.append(parent)
            frontier = nxt
        return result

    direct: dict[str, str] = {}
    ancestor: dict[str, str] = {}
    label_counter: Counter[str] = Counter()

    for class_id in sorted(class_freq):
        own = labels.get(class_id)
        label = classify_class_name(own) if own else None
        if label is not None:
            direct[class_id] = label
            label_counter[label] += 1
            continue
        # Không khớp tự thân → tìm ở lớp cha (gần → xa).
        for node in ancestors_of(class_id):
            parent_name = labels.get(node)
            if not parent_name:
                continue
            parent_label = classify_class_name(parent_name)
            if parent_label is not None:
                ancestor[class_id] = parent_label
                label_counter[parent_label] += 1
                break

    def coverage(mapping: dict[str, str]) -> tuple[int, int]:
        """Tính độ phủ (số lớp, số QID) của một bảng map.

        Args:
            mapping: Bảng map lớp → nhãn.

        Returns:
            Cặp ``(số lớp, số QID)``.
        """
        n_classes = len(mapping)
        n_qids = sum(class_freq[c] for c in mapping)
        return n_classes, n_qids

    total_qids = sum(class_freq.values())
    d_classes, d_qids = coverage(direct)
    a_classes, a_qids = coverage(ancestor)
    print(f"direct:   {d_classes} lớp, phủ {d_qids}/{total_qids} QID ({d_qids / total_qids:.1%})")
    print(f"ancestor: {a_classes} lớp, phủ {a_qids}/{total_qids} QID ({a_qids / total_qids:.1%})")
    total_covered = d_qids + a_qids
    print(f"Tổng phủ: {total_covered}/{total_qids} QID ({total_covered / total_qids:.1%})")
    print("Phân bố nhãn:", dict(label_counter.most_common()))

    # Xuất YAML.
    lines: list[str] = [
        "# Bảng map lớp Wikidata → nhãn NER (Phase 4 — B2.1)",
        "#",
        "# File này được SINH TỰ ĐỘNG bởi `scripts/build_type_map.py` từ:",
        "#   - `data/interim/class_hierarchy.json`  (đồ thị phân cấp lớp P279)",
        "#   - `data/interim/class_labels.json`     (nhãn lớp từ Wikidata)",
        "#",
        "# Cấu trúc:",
        "#   direct:   tên lớp P31 tự nó khớp từ khoá → nhãn (độ tin cậy cao)",
        "#   ancestor: tên lớp P31 không khớp, nhưng lớp cha khớp → nhãn",
        "",
        "direct:",
    ]
    for class_id in sorted(direct, key=lambda c: (-class_freq[c], c)):
        lines.append(
            f"  {class_id}: {direct[class_id]}  # {class_freq[class_id]:>5} QID · {labels.get(class_id, '?')}"
        )
    lines.extend(["", "ancestor:"])
    for class_id in sorted(ancestor, key=lambda c: (-class_freq[c], c)):
        lines.append(
            f"  {class_id}: {ancestor[class_id]}  # {class_freq[class_id]:>5} QID · {labels.get(class_id, '?')}"
        )
    lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"→ ghi {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

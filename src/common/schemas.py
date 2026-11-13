"""Hợp đồng dữ liệu dùng chung cho mọi phase.

Đây là **nguồn sự thật duy nhất** cho:
- 18 quan hệ đóng (`RELATION_TYPES`),
- 6 nhãn NER (`NER_LABELS`),
- 5 phương pháp trích xuất (`EXTRACTION_METHODS`),
- 7 loại node (`NODE_TYPES`),
- cấu trúc record `Document` / `Sentence` / `Mention` / `Triple` / `Entity`.

Đổi bất kỳ hằng số nào ở đây → phải cập nhật đồng thời
`docs/CONTEXT.md`, `docs/04-schema-knowledge-graph.md`, `docs/09-ke-hoach-thuc-thien.md`,
`configs/default.yaml` và prompt/validator/test liên quan.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Schema đóng
# ---------------------------------------------------------------------------

#: 18 quan hệ KG (nguồn: docs/CONTEXT.md §2.5, docs/04)
RELATION_TYPES: frozenset[str] = frozenset(
    {
        "cha_cua",
        "me_cua",
        "vo_cua",
        "chong_cua",
        "anh_em_cua",
        "thuoc_trieu_dai",
        "ke_vi",
        "giu_chuc_vu",
        "lap_ra",
        "chi_huy_tran",
        "tham_gia_tran",
        "danh_bai",
        "dien_ra_tai",
        "sinh_tai",
        "mat_tai",
        "sinh_nam",
        "mat_nam",
        "dong_doi_tai",
    }
)

#: Thứ tự ổn định của 18 quan hệ (dùng cho nhãn RE và prompt).
RELATION_ORDER: tuple[str, ...] = (
    "cha_cua",
    "me_cua",
    "vo_cua",
    "chong_cua",
    "anh_em_cua",
    "thuoc_trieu_dai",
    "ke_vi",
    "giu_chuc_vu",
    "lap_ra",
    "chi_huy_tran",
    "tham_gia_tran",
    "danh_bai",
    "dien_ra_tai",
    "sinh_tai",
    "mat_tai",
    "sinh_nam",
    "mat_nam",
    "dong_doi_tai",
)

#: Quan hệ đối xứng — chuẩn hóa orientation (subject_id < object_id) trước khi nạp.
SYMMETRIC_RELATIONS: frozenset[str] = frozenset({"anh_em_cua", "tham_gia_tran"})

#: 6 nhãn NER.
NER_LABELS: tuple[str, ...] = (
    "PERSON",
    "DYNASTY",
    "EVENT",
    "LOCATION",
    "TIME",
    "TITLE",
)

#: 5 phương pháp trích xuất triple.
EXTRACTION_METHODS: frozenset[str] = frozenset(
    {
        "infobox",
        "distant_supervision",
        "phobert_re",
        "llm",
        "rule",
    }
)

#: 7 loại node KG.
NODE_TYPES: frozenset[str] = frozenset(
    {"person", "dynasty", "event", "place", "title", "year", "article"}
)

#: Label Neo4j tương ứng với node type.
NODE_LABELS: dict[str, str] = {
    "person": "Person",
    "dynasty": "Dynasty",
    "event": "Event",
    "place": "Place",
    "title": "Title",
    "year": "Year",
    "article": "Article",
}

#: Cách resolve một mention.
RESOLUTION_METHODS: frozenset[str] = frozenset(
    {
        "explicit",
        "coref_pronoun",
        "coref_honorific",
        "article_subject",
        "ambiguous",
        "unlinked",
    }
)

#: Nguồn sinh entity.
ENTITY_SOURCE_METHODS: frozenset[str] = frozenset(
    {"infobox", "wikidata", "link", "llm", "nil"}
)

#: Quan hệ hợp lệ theo từng loại node (dùng cho validator và prompt).
#: ``None`` nghĩa là không giới hạn theo loại.
RELATION_SUBJECT_TYPES: dict[str, frozenset[str]] = {
    "cha_cua": frozenset({"person"}),
    "me_cua": frozenset({"person"}),
    "vo_cua": frozenset({"person"}),
    "chong_cua": frozenset({"person"}),
    "anh_em_cua": frozenset({"person"}),
    "thuoc_trieu_dai": frozenset({"person", "dynasty"}),
    "ke_vi": frozenset({"person"}),
    "giu_chuc_vu": frozenset({"person"}),
    "lap_ra": frozenset({"person", "event"}),
    "chi_huy_tran": frozenset({"person"}),
    "tham_gia_tran": frozenset({"person"}),
    "danh_bai": frozenset({"person"}),
    "dien_ra_tai": frozenset({"person", "event"}),
    "sinh_tai": frozenset({"person", "place"}),
    "mat_tai": frozenset({"person", "place"}),
    "sinh_nam": frozenset({"person"}),
    "mat_nam": frozenset({"person"}),
    "dong_doi_tai": frozenset({"place"}),
}

#: Quan hệ dùng để tạo node `Year` (năm được biểu diễn cả 2 chiều).
YEAR_RELATIONS: frozenset[str] = frozenset({"sinh_nam", "mat_nam"})


# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Sentence:
    """Một câu trong văn bản đã làm sạch.

    Attributes:
        sentence_id: ID câu, format ``s<page_id>_<para_idx>_<sent_idx>``.
        doc_id: ID tài liệu chứa câu.
        para_idx: Chỉ số đoạn (0-based).
        sent_idx: Chỉ số câu trong đoạn (0-based).
        text: Nội dung câu.
        start: Offset ký tự bắt đầu trong ``clean_text`` của tài liệu.
        end: Offset ký tự kết thúc (không bao gồm) trong ``clean_text``.
    """

    sentence_id: str
    doc_id: str
    para_idx: int
    sent_idx: int
    text: str
    start: int
    end: int


@dataclass(slots=True)
class Mention:
    """Một mention được NER gán nhãn.

    Attributes:
        mention_id: ID mention, format ``m<sentence_id>_<idx>``.
        start: Offset bắt đầu (ký tự Python, 0-based, bao gồm).
        end: Offset kết thúc (không bao gồm).
        text: Văn bản của span.
        label: Nhãn NER ∈ `NER_LABELS`.
        canonical_id: ``entity_id`` sau khi resolve, hoặc ``None``.
        resolved_by: Cách resolve ∈ `RESOLUTION_METHODS`.
    """

    mention_id: str
    start: int
    end: int
    text: str
    label: str
    canonical_id: str | None = None
    resolved_by: str = "unlinked"

    def is_valid(self) -> bool:
        """Kiểm tra tính hợp lệ của mention.

        Returns:
            ``True`` nếu span không rỗng, offset đúng thứ tự và nhãn hợp lệ.
        """
        if not self.text.strip():
            return False
        if self.start < 0 or self.end <= self.start:
            return False
        if self.label not in NER_LABELS:
            return False
        return True


@dataclass(slots=True)
class Triple:
    """Một quan hệ có bằng chứng.

    Mọi triple **bắt buộc** có `evidence_sentence` + `source_url` + `confidence`
    + `method`. Thiếu bằng chứng → loại khỏi KG (không có ngoại lệ).
    """

    doc_id: str
    sentence_id: str
    subject: str
    relation: str
    object: str
    evidence_sentence: str
    source_url: str
    doc_title: str
    confidence: float
    method: str
    start_year: int | None = None
    end_year: int | None = None
    alt_evidence: list[dict[str, Any]] = field(default_factory=list)

    def is_valid(self) -> bool:
        """Kiểm tra triple có hợp lệ để đưa vào KG không.

        Điều kiện:
        - quan hệ ∈ `RELATION_TYPES`;
        - subject/object khác nhau và khác rỗng;
        - có bằng chứng: `evidence_sentence` và `source_url` không rỗng;
        - `confidence` ∈ [0, 1];
        - `method` ∈ `EXTRACTION_METHODS`.

        Returns:
            ``True`` nếu hợp lệ.
        """
        if self.relation not in RELATION_TYPES:
            return False
        if not self.subject or not self.object:
            return False
        if self.subject == self.object:
            return False
        if not self.evidence_sentence or not self.evidence_sentence.strip():
            return False
        if not self.source_url or not self.source_url.strip():
            return False
        if not isinstance(self.confidence, (int, float)):
            return False
        if not 0.0 <= float(self.confidence) <= 1.0:
            return False
        if self.method not in EXTRACTION_METHODS:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Chuyển triple thành dict để ghi JSONL.

        Returns:
            Dict theo đúng thứ tự trường của data-contracts.
        """
        data = asdict(self)
        data["confidence"] = float(self.confidence)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Triple":
        """Dựng triple từ dict.

        Args:
            data: Dict record.

        Returns:
            Đối tượng `Triple`.
        """
        return cls(
            doc_id=data["doc_id"],
            sentence_id=data["sentence_id"],
            subject=data["subject"],
            relation=data["relation"],
            object=data["object"],
            evidence_sentence=data["evidence_sentence"],
            source_url=data["source_url"],
            doc_title=data["doc_title"],
            confidence=float(data["confidence"]),
            method=data["method"],
            start_year=data.get("start_year"),
            end_year=data.get("end_year"),
            alt_evidence=list(data.get("alt_evidence") or []),
        )


@dataclass(slots=True)
class Entity:
    """Một thực thể trong KG.

    Attributes:
        entity_id: ID thực thể, format ``ent_<slug>_<hash8>``.
        name: Tên hiển thị (giữ dấu).
        name_normalized: Tên bỏ dấu, dùng tra cứu.
        type: Loại node ∈ `NODE_TYPES`.
        aliases: Danh sách alias kèm nguồn.
        aliases_normalized: Bản bỏ dấu của alias.
        wikidata_qid: QID Wikidata nếu có.
        wiki_url: URL Wikipedia nếu có.
        verified: Đã được đối chiếu với Wikidata hay chưa.
        mention_count: Số lần được nhắc đến.
        source_method: Nguồn sinh entity ∈ `ENTITY_SOURCE_METHODS`.
    """

    entity_id: str
    name: str
    name_normalized: str
    type: str
    aliases: list[dict[str, Any]] = field(default_factory=list)
    aliases_normalized: list[str] = field(default_factory=list)
    wikidata_qid: str | None = None
    wiki_url: str | None = None
    verified: bool = False
    mention_count: int = 0
    source_method: str = "link"

    def is_valid(self) -> bool:
        """Kiểm tra entity có hợp lệ không.

        Returns:
            ``True`` nếu có tên, loại hợp lệ và nguồn hợp lệ.
        """
        if not self.entity_id or not self.name.strip():
            return False
        if self.type not in NODE_TYPES:
            return False
        if self.source_method not in ENTITY_SOURCE_METHODS:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        """Chuyển entity thành dict để ghi JSONL.

        Returns:
            Dict theo đúng thứ tự trường của data-contracts.
        """
        return asdict(self)


@dataclass(slots=True)
class Document:
    """Một bài Wikipedia đã lọc và làm sạch.

    Attributes:
        doc_id: ID tài liệu, format ``doc_<page_id>``.
        page_id: ID trang Wikipedia.
        title: Tiêu đề bài.
        url: URL bài.
        revision_id: ID phiên bản.
        categories: Danh sách category của bài.
        wikibase_item: QID Wikidata (nếu có).
        infobox_type: Loại infobox suy ra (``person``/``battle``/``dynasty``/``place``...).
        keep_reason: Lý do giữ bài (``wikidata``/``category``/``infobox``/``seed_expansion``).
        dump_version: Phiên bản dump nguồn.
        wikitext: Wikitext gốc (chỉ có ở Phase 1).
        clean_text: Văn bản đã làm sạch (Phase 2+).
        sentences: Danh sách câu (Phase 2+).
        links: Danh sách hyperlink đã trích (Phase 2+).
    """

    doc_id: str
    page_id: int
    title: str
    url: str
    revision_id: int
    categories: list[str]
    wikibase_item: str | None
    infobox_type: str | None
    keep_reason: str
    dump_version: str
    wikitext: str = ""
    clean_text: str = ""
    sentences: list[Sentence] = field(default_factory=list)
    links: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Chuyển document thành dict để ghi JSONL.

        Returns:
            Dict record.
        """
        data = asdict(self)
        data["sentences"] = [asdict(s) if not isinstance(s, dict) else s for s in self.sentences]
        return data


def normalize_orientation(
    subject_id: str, object_id: str, relation: str
) -> tuple[str, str, str]:
    """Chuẩn hóa orientation cho quan hệ đối xứng.

    Với quan hệ đối xứng (`anh_em_cua`, `tham_gia_tran`), sắp xếp hai đầu theo
    thứ tự lexicographic để `A -[anh_em_cua]-> B` và `B -[anh_em_cua]-> A` là
    cùng một cạnh. Quan hệ không đối xứng giữ nguyên.

    Args:
        subject_id: ID chủ thể.
        object_id: ID đối tượng.
        relation: Tên quan hệ.

    Returns:
        Tuple ``(subject_id, object_id, relation)`` đã chuẩn hóa.
    """
    if relation in SYMMETRIC_RELATIONS and subject_id > object_id:
        return object_id, subject_id, relation
    return subject_id, object_id, relation


def validate_relation(relation: str) -> bool:
    """Kiểm tra quan hệ có nằm trong 18 quan hệ đóng không.

    Args:
        relation: Tên quan hệ.

    Returns:
        ``True`` nếu hợp lệ.
    """
    return relation in RELATION_TYPES


def validate_method(method: str) -> bool:
    """Kiểm tra phương pháp trích xuất có hợp lệ không.

    Args:
        method: Tên phương pháp.

    Returns:
        ``True`` nếu hợp lệ.
    """
    return method in EXTRACTION_METHODS


def ner_label_to_bioes(label: str) -> list[str]:
    """Sinh nhãn BIOES cho một nhãn NER.

    Args:
        label: Nhãn thực thể, ví dụ ``"PERSON"``.

    Returns:
        Danh sách 4 nhãn: ``[B-..., I-..., E-..., S-...]``.
    """
    return [f"B-{label}", f"I-{label}", f"E-{label}", f"S-{label}"]

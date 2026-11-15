"""Hợp nhất triple từ nhiều nguồn (Phase 8 — D3).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 8 mục 7.

Cách chạy
---------
```bash
python -m src.re.merge_triples --out data/interim/triples_merged.jsonl
```

Nguồn gộp (5 nguồn)
--------------------
| Nguồn | Artifact | `method` |
|---|---|---|
| Infobox | `data/interim/infobox_triples.jsonl` | `infobox` |
| Đoạn dẫn (rule) | `data/interim/lead_triples.jsonl` | `rule` |
| Distant supervision | `data/interim/re_positive.jsonl` | `distant_supervision` |
| Mô hình RE | `data/interim/re_phobert.jsonl` | `phobert_re` |
| LLM | `data/interim/re_llm.jsonl` (+ `re_llm_kaggle.jsonl`) | `llm` |

Quy tắc xử lý
-------------
1. **Chuẩn hoá subject/object** về `entity_id` (dùng `make_entity_id` nếu chưa
   có). Id dạng ``year_`` giữ nguyên.
2. **Loại self-loop** — ``subject == object`` (đo được 4 self-loop khi mô phỏng).
3. **Loại quan hệ ngoài danh mục** 18 quan hệ đóng.
4. **Loại** triple có subject/object rỗng hoặc ``evidence_sentence`` rỗng.
5. **Chuẩn hoá orientation** cho quan hệ đối xứng (`anh_em_cua`,
   `tham_gia_tran`) về ``subject_id < object_id`` → tránh trùng.
6. **Loại trùng** ``(subject, relation, object)``: giữ bản ``confidence`` **cao
   nhất**; các bằng chứng còn lại vào ``alt_evidence``.

Output contract (`docs/09` §Phase 8)
------------------------------------
```json
{"doc_id":"doc_1","sentence_id":"s1_0_3","subject":"ent_le_loi_1a2b3c4d",
 "relation":"cha_cua","object":"ent_le_khanh_du_...","evidence_sentence":"...",
 "source_url":"...","doc_title":"Lê Lợi","confidence":0.97,"method":"phobert_re",
 "start_year":null,"end_year":null,"alt_evidence":[]}
```
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from src.common.config import load_default_config, resolve_path
from src.common.ids import make_entity_id
from src.common.logger import get_logger
from src.common.schemas import RELATION_TYPES, normalize_orientation

logger = get_logger(__name__)

#: 13 trường bắt buộc trong output contract (`docs/09` §Phase 8).
#:
#: ``alt_evidence`` là trường **bắt buộc** — nó lưu các bằng chứng còn lại
#: sau khi dedupe theo ``(subject, relation, object)``. Nếu bỏ trường này thì
#: thông tin bằng chứng thay thế bị **mất vĩnh viễn** và edge trong Neo4j
#: luôn có ``alt_evidence = []`` (vi phạm contract Phase 10 §edge).
REQUIRED_FIELDS: tuple[str, ...] = (
    "doc_id",
    "sentence_id",
    "subject",
    "relation",
    "object",
    "evidence_sentence",
    "source_url",
    "doc_title",
    "confidence",
    "method",
    "start_year",
    "end_year",
    "alt_evidence",
)

#: Ngưỡng confidence tối thiểu để giữ triple (0 = giữ tất cả).
DEFAULT_MIN_CONFIDENCE = 0.0


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc file JSONL, bỏ qua dòng rỗng.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng record (dict).
    """
    source = Path(path)
    if not source.exists():
        return
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_documents(path: str | Path) -> dict[str, dict[str, Any]]:
    """Nạp metadata bài viết để tra `source_url` / `doc_title`.

    Args:
        path: Đường dẫn `documents_clean.jsonl`.

    Returns:
        Dict ``doc_id`` → metadata.
    """
    documents: dict[str, dict[str, Any]] = {}
    for record in read_jsonl(path):
        doc_id = str(record.get("doc_id", ""))
        if not doc_id:
            continue
        documents[doc_id] = {
            "url": str(record.get("url", "")),
            "title": str(record.get("title", "")),
            "page_id": int(record.get("page_id", 0) or 0),
        }
    return documents


def ensure_entity_id(raw: str, entity_type: str = "") -> str:
    """Chuẩn hoá một định danh thành ``entity_id`` hợp lệ.

    - Id đã có dạng ``ent_*`` → giữ nguyên.
    - Id dạng ``year_*`` → giữ nguyên (node thời gian).
    - Còn lại → sinh ``ent_<slug>_<hash8>`` bằng `make_entity_id`.

    Args:
        raw: Định danh thô.
        entity_type: Type KG (dùng khi sinh id mới).

    Returns:
        ``entity_id`` hợp lệ, hoặc chuỗi rỗng nếu đầu vào rỗng.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    if text.startswith("ent_") or text.startswith("year_"):
        return text
    return make_entity_id(entity_type or "unknown", text)


def normalize_triple(
    record: dict[str, Any],
    *,
    method: str,
    documents: dict[str, dict[str, Any]],
    default_confidence: float,
) -> dict[str, Any] | None:
    """Chuẩn hoá một triple về 12 trường của output contract.

    Args:
        record: Record thô từ artifact nguồn.
        method: ``method`` gán cho triple.
        documents: Metadata bài viết.
        default_confidence: Confidence mặc định khi nguồn không cung cấp.

    Returns:
        Dict 12 trường, hoặc ``None`` nếu triple không hợp lệ.
    """
    subject_raw = str(record.get("subject", "") or "")
    object_raw = str(record.get("object", "") or "")
    subject_type = str(record.get("subject_type", "") or "")
    object_type = str(record.get("object_type", "") or "")

    subject = ensure_entity_id(subject_raw, subject_type)
    object_ = ensure_entity_id(object_raw, object_type)
    if not subject or not object_:
        return None
    if subject == object_:
        return None

    relation = str(record.get("relation", "") or "").strip()
    if relation not in RELATION_TYPES:
        return None

    subject, object_, relation = normalize_orientation(subject, object_, relation)

    evidence = str(record.get("evidence_sentence", "") or "").strip()
    if not evidence:
        return None

    doc_id = str(record.get("doc_id", "") or "")
    sentence_id = str(record.get("sentence_id", "") or "")
    doc_meta = documents.get(doc_id, {})
    source_url = str(record.get("source_url", "") or "") or str(
        doc_meta.get("url", "")
    )
    doc_title = str(record.get("doc_title", "") or "") or str(
        doc_meta.get("title", "")
    )

    try:
        confidence = float(record.get("confidence", default_confidence))
    except (TypeError, ValueError):
        confidence = default_confidence
    confidence = max(0.0, min(1.0, round(confidence, 4)))

    start_year = record.get("start_year")
    end_year = record.get("end_year")

    return {
        "doc_id": doc_id,
        "sentence_id": sentence_id,
        "subject": subject,
        "relation": relation,
        "object": object_,
        "evidence_sentence": evidence,
        "source_url": source_url,
        "doc_title": doc_title,
        "confidence": confidence,
        "method": method,
        "start_year": start_year,
        "end_year": end_year,
        "alt_evidence": [],
    }


def iter_source_triples(
    path: str | Path,
    *,
    method: str,
    documents: dict[str, dict[str, Any]],
    default_confidence: float,
) -> Iterator[dict[str, Any]]:
    """Đọc và chuẩn hoá triple từ một artifact nguồn.

    Args:
        path: Đường dẫn artifact.
        method: ``method`` gán cho triple.
        documents: Metadata bài viết.
        default_confidence: Confidence mặc định.

    Yields:
        Triple đã chuẩn hoá.
    """
    for record in read_jsonl(path):
        normalized = normalize_triple(
            record,
            method=method,
            documents=documents,
            default_confidence=default_confidence,
        )
        if normalized is not None:
            yield normalized


def iter_ds_triples(
    path: str | Path,
    *,
    documents: dict[str, dict[str, Any]],
) -> Iterator[dict[str, Any]]:
    """Đọc `re_positive.jsonl` (distant supervision) → triple đã chuẩn hoá.

    Artifact này có định dạng khác (`subject`/`object` là entity_id, không có
    `evidence_sentence`/`doc_id`) → cần tra `sentence_id` để lấy câu gốc.

    Args:
        path: Đường dẫn `re_positive.jsonl`.
        documents: Metadata bài viết.

    Yields:
        Triple đã chuẩn hoá.
    """
    from src.re.ground_triples import CorpusIndex, build_corpus_index

    index: CorpusIndex = build_corpus_index(
        "data/interim/coref_resolved.jsonl"
    )
    for record in read_jsonl(path):
        sentence_id = str(record.get("sentence_id", ""))
        evidence = index.sentence_text.get(sentence_id, "").strip()
        if not evidence:
            continue
        page_id = int(sentence_id.split("_")[0].lstrip("s") or 0)
        doc_id = f"doc_{page_id}"
        candidate = {
            "doc_id": doc_id,
            "sentence_id": sentence_id,
            "subject": record.get("subject", ""),
            "object": record.get("object", ""),
            "relation": record.get("relation", ""),
            "evidence_sentence": evidence,
            "confidence": 0.75,
        }
        normalized = normalize_triple(
            candidate,
            method="distant_supervision",
            documents=documents,
            default_confidence=0.75,
        )
        if normalized is not None:
            yield normalized


def iter_model_triples(
    path: str | Path,
    *,
    method: str,
    documents: dict[str, dict[str, Any]],
    default_confidence: float,
    resolve_names: bool = False,
) -> Iterator[dict[str, Any]]:
    """Đọc artifact dự đoán (PhoBERT / LLM) → triple đã chuẩn hoá.

    Args:
        path: Đường dẫn artifact.
        method: ``method`` gán cho triple (``phobert_re``/``llm``).
        documents: Metadata bài viết.
        default_confidence: Confidence mặc định.
        resolve_names: Nếu ``True``, tra tên bề mặt (LLM) về ``entity_id``
            qua chỉ mục corpus. PhoBERT đã sinh sẵn ``entity_id`` nên không
            cần.

    Yields:
        Triple đã chuẩn hoá.
    """
    index = None
    if resolve_names:
        from src.re.ground_triples import build_corpus_index

        index = build_corpus_index("data/interim/coref_resolved.jsonl")

    for record in read_jsonl(path):
        sentence_id = str(record.get("sentence_id", ""))
        text = str(record.get("text", "") or "")
        page_id = int(sentence_id.split("_")[0].lstrip("s") or 0)
        doc_id = f"doc_{page_id}"
        for pair in record.get("pairs") or []:
            evidence = str(pair.get("evidence_sentence", "") or text).strip()
            subject = str(pair.get("subject", "") or "")
            object_ = str(pair.get("object", "") or "")
            if index is not None:
                subject = _resolve_name(index, sentence_id, subject)
                object_ = _resolve_name(index, sentence_id, object_)
            candidate = {
                "doc_id": doc_id,
                "sentence_id": sentence_id,
                "subject": subject,
                "object": object_,
                "relation": pair.get("relation", ""),
                "evidence_sentence": evidence,
                "confidence": pair.get("confidence", default_confidence),
            }
            normalized = normalize_triple(
                candidate,
                method=method,
                documents=documents,
                default_confidence=default_confidence,
            )
            if normalized is not None:
                yield normalized


#: Kiểu đích hợp lệ của từng quan hệ (theo `docs/04` §3.1).
#: Quan hệ có đích là **node `Year`** được xử lý riêng (xem `YEAR_RELATIONS`).
RELATION_TARGET_TYPES: dict[str, frozenset[str]] = {
    "cha_cua": frozenset({"Person"}),
    "me_cua": frozenset({"Person"}),
    "vo_cua": frozenset({"Person"}),
    "chong_cua": frozenset({"Person"}),
    "anh_em_cua": frozenset({"Person"}),
    "thuoc_trieu_dai": frozenset({"Dynasty"}),
    "ke_vi": frozenset({"Person"}),
    "giu_chuc_vu": frozenset({"Title"}),
    "lap_ra": frozenset({"Dynasty", "Event"}),
    "chi_huy_tran": frozenset({"Event"}),
    "tham_gia_tran": frozenset({"Event"}),
    "danh_bai": frozenset({"Dynasty"}),
    "dien_ra_tai": frozenset({"Place"}),
    "sinh_tai": frozenset({"Place"}),
    "mat_tai": frozenset({"Place"}),
    "sinh_nam": frozenset({"Year"}),
    "mat_nam": frozenset({"Year"}),
    "dong_doi_tai": frozenset({"Place"}),
}

#: Số quan hệ tối đa giữ cho **một cặp (sentence, subject, object)**.
#:
#: Vì sao cần (D-080): mô hình RE dùng **masked BCE** (88,7% slot chưa biết
#: ⇒ không tính loss) ⇒ ở dữ liệu ngoài tập train, một cặp ứng viên bị fire
#: **13,5 quan hệ** trung bình (đo trên 300 cặp: 63% cặp ≥ 2 quan hệ, 18%
#: ≥ 10 quan hệ). Thêm vào đó, mô hình **không** được ràng buộc theo kiểu
#: đích ⇒ sinh cả `sinh_nam` tới địa danh ("A Lưới → Huế").
#:
#: Quy tắc chọn: mỗi cặp trong 1 câu chỉ giữ **quan hệ mạnh nhất**; quan hệ
#: phải khớp **kiểu đích** theo schema (`docs/04` §3.1) — trừ khi đích là
#: entity loại `unknown` (chưa xác minh) thì giữ để không mất dữ liệu.
MAX_RELATIONS_PER_PAIR: int = 1

#: **Từ kích hoạt** cho từng quan hệ — chia 2 mức (D-083).
#:
#: Vì sao cần: mô hình RE đã học được "cặp người nào nhắc cùng trong câu
#: ⇒ gán quan hệ gia đình", kể cả khi câu **không có** từ nào chỉ quan hệ
#: đó. Đo được: cặp ``Lê Thái Tổ --vo_cua--> Lý Thái Tổ`` có bằng chứng là
#: câu so sánh niên hiệu của hai vua — hoàn toàn không có từ "vợ".
#:
#: - **Mạnh** (`RELATION_TRIGGER_STRONG`): cụm từ chuyên biệt (vd "hoàng
#:   hậu", "tước vị") ⇒ chỉ cần **có mặt** trong câu bằng chứng.
#: - **Yếu** (`RELATION_TRIGGER_WEAK`): cụm từ phổ biến (vd "cha", "em",
#:   "nhà", "đánh") ⇒ phải nằm **gần** (≤60 ký tự) tên entity của cặp,
#:   nếu không thì chỉ là từ của entity khác trong câu.
RELATION_TRIGGER_STRONG: dict[str, frozenset[str]] = {
    "cha_cua": frozenset({
        "cha của", "cha ruột", "bố của", "con của ông", "con trai của",
        "con gái của", "cha đẻ",
    }),
    "me_cua": frozenset({
        "mẹ của", "mẹ ruột", "bà mẹ", "sinh ra", "sinh ra được", "đẻ ra",
        "mẹ đẻ",
    }),
    "vo_cua": frozenset({
        "vợ của", "vợ ông", "hoàng hậu", "thái hậu", "hoàng phi", "thuộc hậu",
        "kết hôn", "là vợ", "phu nhân", "hoàng thái phi",
    }),
    "chong_cua": frozenset({
        "chồng của", "chồng ông", "phu quân", "là chồng",
    }),
    "anh_em_cua": frozenset({
        "anh trai", "em gái", "anh em", "em trai", "chị em", "anh ruột",
        "em ruột", "anh em trai", "em chị", "anh cả", "em út",
    }),
    "thuoc_trieu_dai": frozenset({
        "nhà hậu", "nhà tiền", "nhà sơ", "nhà nguyên", "nhà trần", "nhà lý",
        "nhà hồ", "nhà lê", "nhà ngô", "đời nhà", "thuộc nhà", "nhà vua",
        "nhà mạc", "nhà tây son", "nhà nguyễn", "nhà đinh",
    }),
    "ke_vi": frozenset({
        "kế vị", "kế nghiệp", "ngai vàng", "lên ngôi", "đăng quang", "kế tục",
        "tiếp nối", "successor", "kế vị của",
    }),
    "giu_chuc_vu": frozenset({
        "chức vụ", "chức vu", "làm quan", "giữ chức", "đảm nhiệm", "thủ tướng",
        "tổng thống", "chủ tịch", "bộ trưởng", "đô đốc", "hiệp trưởng",
        "tư lệnh", "đại tướng", "thiếu tướng", "tả tướng", "hầu tướng",
        "quốc công", "tước vị", "phong chức", "ban hàm", "chỉ huy trưởng",
        "đốc đông", "tư lệnh",
    }),
    "lap_ra": frozenset({
        "lập ra", "thành lập", "sáng lập", "lập nên", "thành lập nên",
        "khởi lập", "dựng nên", "người sáng lập", "sáng lập ra",
    }),
    "chi_huy_tran": frozenset({
        "chỉ huy", "chi huy", "điện đàn", "khởi nghĩa", "nổi dậy", "dẫn quân",
        "ra trận", "phó tướng", "tướng quân", "chỉ huy quân",
    }),
    "tham_gia_tran": frozenset({
        "tham gia", "chiến đấu", "hợp quân", "cùng đánh", "hiệp lực",
        "tham chiến", "cùng tham", "chiến tranh", "trận đánh",
    }),
    "danh_bai": frozenset({
        "danh bai", "tôn vinh", "trưng bày", "tượng", "đài tưởng niệm",
        "bia ghi", "lập bia", "đền thờ", "miếu thờ",
    }),
    "dien_ra_tai": frozenset({
        "diễn ra", "dien ra", "xảy ra", "xay ra", "diễn biến", "diễn ra tại",
        "diễn ra ở", "nổ ra", "bùng nổ",
    }),
    "sinh_tai": frozenset({
        "sinh ở", "sinh tại", "sinh ra ở", "sinh ra tại", "ra đời tại",
        "địa điểm sinh", "nơi sinh", "sinh ra vào",
    }),
    "mat_tai": frozenset({
        "mất tại", "mất ở", "từ trần", "qua đời tại", "qua đời ở",
        "tử trận tại", "hy sinh tại", "tử vong tại",
    }),
    "sinh_nam": frozenset({
        "sinh năm", "sinh ngày", "năm sinh", "ra đời năm", "sinh ra năm",
    }),
    "mat_nam": frozenset({
        "mất năm", "qua đời năm", "từ trần năm", "mất ngày", "tử vong năm",
    }),
    "dong_doi_tai": frozenset({
        "đóng đô", "đổi đô", "kinh đô", "vua triều đình", "đặt triều đình",
        "dời đô",
    }),
}

#: Từ kích hoạt **yếu** — phải nằm gần tên entity mới chấp nhận.
RELATION_TRIGGER_WEAK: dict[str, frozenset[str]] = {
    "cha_cua": frozenset({"cha", "bố", "sinh ra"}),
    "me_cua": frozenset({"mẹ"}),
    "vo_cua": frozenset({"vợ"}),
    "chong_cua": frozenset({"chồng"}),
    "anh_em_cua": frozenset({"anh", "em", "anh là", "em là"}),
    "thuoc_trieu_dai": frozenset({"nhà", "triều đại", "trieu dai", "triều"}),
    "ke_vi": frozenset({"kế vị", "lên ngôi"}),
    "giu_chuc_vu": frozenset({"tướng", "chỉ huy", "quân", "quan"}),
    "lap_ra": frozenset({"lập", "thành lập", "sáng lập"}),
    "chi_huy_tran": frozenset({"đánh", "trận", "chiến", "điện đàn"}),
    "tham_gia_tran": frozenset({"đánh", "trận", "chiến", "tham gia"}),
    "danh_bai": frozenset({"bia", "tượng"}),
    "dien_ra_tai": frozenset({"diễn ra", "xảy ra"}),
    "sinh_tai": frozenset({"sinh", "ra đời", "quê"}),
    "mat_tai": frozenset({"mất", "qua đời", "từ trần"}),
    "sinh_nam": frozenset({"sinh"}),
    "mat_nam": frozenset({"mất"}),
}

#: **Kiểu chủ thể** hợp lệ cho từng quan hệ (theo `docs/04` §3.1). Quan hệ
#: bị loại nếu node chủ thể có label **đã xác minh** khác loại này
#: (D-084). Ví dụ `lap_ra` (lập ra) phải xuất phát từ `Person` hoặc
#: `Dynasty` — không thể từ `Place`.
RELATION_SOURCE_TYPES: dict[str, frozenset[str]] = {
    "cha_cua": frozenset({"Person"}),
    "me_cua": frozenset({"Person"}),
    "vo_cua": frozenset({"Person"}),
    "chong_cua": frozenset({"Person"}),
    "anh_em_cua": frozenset({"Person"}),
    "thuoc_trieu_dai": frozenset({"Person", "Dynasty"}),
    "ke_vi": frozenset({"Person", "Dynasty"}),
    "giu_chuc_vu": frozenset({"Person"}),
    "lap_ra": frozenset({"Person", "Dynasty", "Event"}),
    "chi_huy_tran": frozenset({"Person"}),
    "tham_gia_tran": frozenset({"Person", "Dynasty"}),
    "danh_bai": frozenset({"Person", "Event", "Place"}),
    "dien_ra_tai": frozenset({"Event"}),
    "sinh_tai": frozenset({"Person"}),
    "mat_tai": frozenset({"Person"}),
    "sinh_nam": frozenset({"Person"}),
    "mat_nam": frozenset({"Person"}),
    "dong_doi_tai": frozenset({"Dynasty"}),
}

#: Danh sách **tên chung** (danh từ chức vụ/danh hiệu) không phải thực thể lịch
#: sử cụ thể ⇒ không được làm chủ thể/đối tượng của một quan hệ (D-081).
#:
#: Vì sao cần: NER Phase 5 gán nhãn `TITLE` cho các danh từ chung như "vua",
#: "ông", "bà", "nhà", "hoàng đế"... Chúng được link thành **entity riêng**
#: (`ent_vua_...`) và sinh ra hàng nghìn cạnh vô nghĩa kiểu
#: ``Lê Thái Tổ --vo_cua--> vua``. Đo được: 12.273/50.677 cạnh (24,2%) có
#: ít nhất một đầu là tên chung.
GENERIC_TITLE_NAMES: frozenset[str] = frozenset({
    # Danh từ chức vụ / thân phận
    "vua", "ông", "bà", "người", "con", "chồng", "vợ", "cha", "mẹ",
    "anh", "em", "chị", "em gái", "anh trai", "thái tử", "hoàng tử",
    "hoàng đế", "hoang de", "thái hoàng", "thái tổ", "tổ", "ông nội",
    "mẹ đẻ", "vợ", "hậu", "phi", "quận chúa", "công chúa", "chúa",
    "hoàng tổ", "thân tướng", "đại tướng", "tướng", "quân", "thiếu tướng",
    "thượng tướng", "đại công thần", "công thần", "quốc công", "công hầu",
    # Danh từ tổ chức / gia tộc
    "nhà", "nha ho", "nha ho va", "triều đại", "trieu dai", "nhà Lê",
    "nhà Trần", "nhà Ngô", "nhà Đinh", "nhà Lý", "nhà Hồ", "nhà Tây Sơn",
    "nhà Nguyễn", "nhà Minh", "nhà Hậu Trần", "nhà Nguyễn Ánh",
    "vương", "kingdom", "gia đình", "dòng họ", "tộc",
    # Danh từ chung khác
    "Lê", "Ngô", "Đinh", "Lý", "Trần", "Hồ", "Tây Sơn", "Nguyễn",
    "quốc", "nước", "đất nước", "thành", "đô", "kinh đô",
    "ngôi", "ngai", "ngai vàng", "triều đình",
})

#: Tên triều đại **hợp lệ** — được phép làm đối tượng của `thuoc_trieu_dai`
#: dù cũng nằm trong `GENERIC_TITLE_NAMES` (D-086).
#:
#: Vì sao cần: `GENERIC_TITLE_NAMES` chặn "nhà Trần"/"nhà Nguyễn" vì NER
#: thường gán nhãn `TITLE` cho chúng. Nhưng với quan hệ `thuoc_trieu_dai`
#: ("thuộc triều đại") thì "Nhà Trần" là **triều đại hợp lệ** — đo được:
#: 29 cạnh `thuoc_trieu_dai` → "Nhà Nguyễn", 18 → "Nhà Trần", 17 → "Nhà Lê
#: sơ", 11 → "Nhà Tây Sơn"… (từ trường infobox "Triều đại").
#:
#: ⇒ Danh sách này **loại trừ** các tên triều đại khỏi `GENERIC_TITLE_NAMES`
#: **chỉ khi quan hệ là `thuoc_trieu_dai`**.
GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY: frozenset[str] = frozenset({
    "nhà Lê", "nha le", "nhà Trần", "nha tran", "nhà Ngô", "nha ngo",
    "nhà Đinh", "nha dinh", "nhà Lý", "nha ly", "nhà Hồ", "nha ho",
    "nhà Tây Sơn", "nha tai son", "nhà Nguyễn", "nha nguyen",
    "nhà Minh", "nha minh", "nhà Hậu Trần", "nha hau tran",
    "nhà Nguyễn Ánh", "nha nguyen anh",
    "nhà Tiền Lê", "nha tien le", "nhà Mạc", "nha mac",
    "nhà Hậu Lê", "nha hau le", "nhà Lê sơ", "nha le so",
    "nhà Lê Trung hưng", "nha le trung hung", "Lê sơ", "le so",
    "Lê trung hưng", "le trung hung", "Hậu Lê", "hau le",
    "Trần", "Lê", "Ngô", "Đinh", "Lý", "Hồ", "Tây Sơn", "Nguyễn",
    "Tiền Lê", "tien le", "Triều Trần", "trieu tran",
    "Triều Lê", "trieu le", "Triều Nguyễn", "trieu nguyen",
})

#: Tên chung ở dạng **chưa bỏ dấu** (để so khớp không phụ thuộc dấu).
def _strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường.

    Dùng `src.common.normalize.strip_accents` (xử lý được `Đ`/`đ` **precomposed**)
    thay vì tự viết lại — bản cũ ở đây dùng NFD trực tiếp nên **không** phân
    rã được "Đ"/"đ" ⇒ `"Đại Nam"` ra `"đai nam"` ≠ `"dai nam"` ⇒ so khớp với
    danh sách tên chung **luôn trượt** (đo được: 85 cạnh `thuoc_trieu_dai` →
    node "Triều đại", 75 cạnh `giu_chuc_vu` → node "nhà Nguyễn" sống sót).

    Args:
        text: Chuỗi đầu vào.

    Returns:
        Chuỗi đã chuẩn hoá.
    """
    from src.common.normalize import strip_accents

    return strip_accents(text).strip().lower()


#: Phiên bản không dấu của `GENERIC_TITLE_NAMES`.
GENERIC_TITLE_NAMES_NODIACRITIC: frozenset[str] = frozenset(
    _strip_diacritics(name) for name in GENERIC_TITLE_NAMES
)

#: **Tên chung riêng theo quan hệ** — đối tượng hợp lệ về mặt ngữ nghĩa nhưng
#: vô nghĩa với quan hệ cụ thể (D-086).
#:
#: Vì sao cần: `GENERIC_TITLE_NAMES` là danh sách **chung** cho mọi quan hệ,
#: nên không thể thêm "Đại Việt" (một *địa danh* hợp lệ cho `sinh_tai`) vào đó.
#: Nhưng với `thuoc_trieu_dai` ("thuộc triều đại") thì "Đại Việt" /
#: "Việt Nam" là **tên quốc gia**, không phải triều đại ⇒ cạnh
#: ``Bà Triệu --thuoc_trieu_dai--> Đại Việt`` là sai.
#:
#: Đo được trên `triples_merged.jsonl` (13.462 cạnh):
#: - `thuoc_trieu_dai` → "Triều đại" (85, khái niệm chung, từ trường
#:   "Kiểu Hoàng Tộc" trỏ tới bài khái niệm), "Đại Việt" (46), "Việt Nam"
#:   (23), "Đại Nam" (15) ⇒ 169 cạnh (28,6% của quan hệ này) vô nghĩa.
#: - `giu_chuc_vu` → "nhà Nguyễn" (75, từ trường "Nghề nghiệp" trỏ tới bài
#:   "Nhà Nguyễn") ⇒ 75 cạnh vô nghĩa (đã bị `GENERIC_TITLE_NAMES` bắt,
#:   nhưng **không** bị bắt do lỗi slug — xem `drop_generic_title_triples`).
GENERIC_TARGET_NAMES_BY_RELATION: dict[str, frozenset[str]] = {
    "thuoc_trieu_dai": frozenset({
        # Khái niệm chung (bài khái niệm Wikipedia, không phải triều đại)
        "trieu dai", "gia toc", "hoang toc", "quoc gia", "nha vua",
        "vua", "nguoi", "the", "hoang phi",
        # Tên quốc gia (không phải triều đại)
        "dai viet", "viet nam", "dai nam", "dai ngu", "nuoc dai viet",
        "cong hoa xa hoi chu nghia viet nam", "viet nam cong hoa",
    }),
}


def _resolve_name(index: Any, sentence_id: str, raw: str) -> str:
    """Tra một tên bề mặt về ``entity_id`` trong câu.

    Ưu tiên entity có mention **khớp chính xác** tên trong câu; nếu không có,
    giữ nguyên giá trị gốc (sẽ được `ensure_entity_id` xử lý).

    Args:
        index: `CorpusIndex`.
        sentence_id: Id câu.
        raw: Tên bề mặt.

    Returns:
        ``entity_id`` nếu tra được, ngược lại chuỗi gốc.
    """
    from src.common.normalize import normalize_name

    text = str(raw or "").strip()
    if not text or text.startswith("ent_") or text.startswith("year_"):
        return text
    normalized = normalize_name(text)
    if not normalized:
        return text
    mention_map = index.sentence_mentions.get(sentence_id, {})
    matches = [
        entity_id
        for entity_id, names in mention_map.items()
        if normalized in names
    ]
    if len(matches) == 1:
        return matches[0]
    return text


def merge_triples(
    triples: Iterable[dict[str, Any]],
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Gộp triple trùng theo ``(subject, relation, object)``.

    Giữ bản có ``confidence`` **cao nhất**; các bằng chứng còn lại (khác
    ``evidence_sentence``) vào ``alt_evidence``.

    Args:
        triples: Iterable triple đã chuẩn hoá.
        min_confidence: Ngưỡng confidence tối thiểu để giữ.

    Returns:
        Cặp ``(merged, stats)`` — ``stats`` gồm ``n_input``/``n_merged``/
        ``n_duplicates``/``n_below_threshold``.
    """
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    stats = {
        "n_input": 0,
        "n_merged": 0,
        "n_duplicates": 0,
        "n_below_threshold": 0,
    }
    for triple in triples:
        stats["n_input"] += 1
        if float(triple["confidence"]) < min_confidence:
            stats["n_below_threshold"] += 1
            continue
        # Chuẩn hoá orientation lần nữa (phòng thủ): đảm bảo cặp đối xứng
        # luôn gộp về cùng một khoá.
        subject, object_, relation = normalize_orientation(
            triple["subject"], triple["object"], triple["relation"]
        )
        key = (subject, relation, object_)
        grouped[key].append({**triple, "subject": subject, "object": object_})

    merged: list[dict[str, Any]] = []
    for key in sorted(grouped):
        group = grouped[key]
        best = max(group, key=lambda item: (float(item["confidence"]), item["method"]))
        alt_evidence: list[str] = []
        seen = {best["evidence_sentence"]}
        for item in group:
            evidence = item["evidence_sentence"]
            if evidence in seen:
                continue
            seen.add(evidence)
            alt_evidence.append(evidence)
        if len(group) > 1:
            stats["n_duplicates"] += len(group) - 1
        result = dict(best)
        result["alt_evidence"] = alt_evidence
        merged.append(result)

    stats["n_merged"] = len(merged)
    return merged, stats


def validate_merged(merged: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Kiểm tra các Gate về chất lượng của artifact đã hợp nhất.

    Args:
        merged: Danh sách triple đã hợp nhất.

    Returns:
        Dict kết quả kiểm tra.
    """
    missing_required = 0
    invalid_confidence = 0
    invalid_relation = 0
    self_loops = 0
    empty_evidence = 0
    duplicate_keys = 0
    seen: set[tuple[str, str, str]] = set()
    for triple in merged:
        for field in (
            "doc_id",
            "sentence_id",
            "subject",
            "relation",
            "object",
            "evidence_sentence",
            "source_url",
            "doc_title",
            "confidence",
            "method",
            "start_year",
            "end_year",
        ):
            if field not in triple:
                missing_required += 1
                break
        try:
            confidence = float(triple["confidence"])
        except (TypeError, ValueError):
            invalid_confidence += 1
            continue
        if not (0.0 <= confidence <= 1.0):
            invalid_confidence += 1
        if triple["relation"] not in RELATION_TYPES:
            invalid_relation += 1
        if triple["subject"] == triple["object"]:
            self_loops += 1
        if not str(triple["evidence_sentence"]).strip():
            empty_evidence += 1
        key = (triple["subject"], triple["relation"], triple["object"])
        if key in seen:
            duplicate_keys += 1
        seen.add(key)
    return {
        "n_triples": len(merged),
        "missing_required_fields": missing_required,
        "invalid_confidence": invalid_confidence,
        "invalid_relation": invalid_relation,
        "self_loops": self_loops,
        "empty_evidence": empty_evidence,
        "duplicate_keys": duplicate_keys,
    }


def write_merged(path: str | Path, merged: Sequence[dict[str, Any]]) -> int:
    """Ghi triple đã hợp nhất ra JSONL.

    Args:
        path: Đường dẫn đích.
        merged: Danh sách triple.

    Returns:
        Số triple đã ghi.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as handle:
        for triple in merged:
            payload = {
                field: triple.get(field) for field in REQUIRED_FIELDS
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Hợp nhất triple từ nhiều nguồn (Phase 8 — D3)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default=None, help="Đường dẫn file đầu ra")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=None,
        help="Ngưỡng confidence tối thiểu (0 = giữ tất cả)",
    )
    parser.add_argument(
        "--no-filter-model",
        action="store_true",
        help="Không lọc nguồn mô hình (top-1/cặp + kiểu đích) — D-080",
    )
    parser.add_argument(
        "--keep-generic-titles",
        action="store_true",
        help="Giữ lại các cạnh có đầu là tên chung (vua, ông, nhà...) — D-081",
    )
    parser.add_argument(
        "--no-require-evidence",
        action="store_true",
        help="Không yêu cầu tên chủ thể/đối tượng xuất hiện trong "
             "evidence_sentence cho nguồn mô hình — D-082",
    )
    parser.add_argument(
        "--no-require-trigger",
        action="store_true",
        help="Không yêu cầu từ kích hoạt của quan hệ xuất hiện trong "
             "evidence_sentence — D-083",
    )
    args = parser.parse_args(argv)

    config = load_default_config()
    re_config = config.get("re", {})
    merge_config = dict(re_config.get("merge", {}))
    filter_model = not args.no_filter_model

    documents = load_documents(
        merge_config.get("documents_path", "data/interim/documents_clean.jsonl")
    )
    logger.info("Nạp %d bài viết", len(documents))

    out_path = resolve_path(
        args.out or re_config.get("merged_path", "data/interim/triples_merged.jsonl")
    )
    min_confidence = (
        args.min_confidence
        if args.min_confidence is not None
        else float(merge_config.get("min_confidence", DEFAULT_MIN_CONFIDENCE))
    )

    all_triples: list[dict[str, Any]] = []
    model_filter_stats: dict[str, dict[str, int]] = {}

    infobox_path = merge_config.get(
        "infobox_path", "data/interim/infobox_triples.jsonl"
    )
    lead_path = merge_config.get("lead_path", "data/interim/lead_triples.jsonl")
    ds_path = merge_config.get("ds_path", "data/interim/re_positive.jsonl")
    phobert_path = merge_config.get(
        "phobert_path", "data/interim/re_phobert.jsonl"
    )
    llm_path = merge_config.get("llm_path", "data/interim/re_llm.jsonl")
    llm_kaggle_path = merge_config.get(
        "llm_kaggle_path", "data/interim/re_llm_kaggle.jsonl"
    )

    sources = [
        (infobox_path, "infobox", 0.97),
        (lead_path, "rule", 0.85),
    ]
    for path, method, confidence in sources:
        count = 0
        for triple in iter_source_triples(
            path,
            method=method,
            documents=documents,
            default_confidence=confidence,
        ):
            all_triples.append(triple)
            count += 1
        logger.info("Nguồn %-20s %6d triple", method, count)

    count = 0
    for triple in iter_ds_triples(ds_path, documents=documents):
        all_triples.append(triple)
        count += 1
    logger.info("Nguồn %-20s %6d triple", "distant_supervision", count)

    for path, method, resolve_names in (
        (phobert_path, "phobert_re", False),
        (llm_path, "llm", True),
        (llm_kaggle_path, "llm", True),
    ):
        count = 0
        model_triples: list[dict[str, Any]] = []
        for triple in iter_model_triples(
            path,
            method=method,
            documents=documents,
            default_confidence=0.8,
            resolve_names=resolve_names,
        ):
            model_triples.append(triple)
            count += 1
        logger.info("Nguồn %-20s %6d triple", method, count)
        if model_triples and filter_model:
            entity_labels = load_entity_labels(
                merge_config.get(
                    "entities_path", "data/knowledge_base/entities.jsonl"
                ),
                merge_config.get(
                    "infobox_entities_path",
                    "data/interim/infobox_entities.jsonl",
                ),
            )
            entity_names = load_entity_names(
                merge_config.get(
                    "entities_path", "data/knowledge_base/entities.jsonl"
                )
            )
            kept, filter_stats = filter_model_predictions(
                model_triples,
                entity_labels=entity_labels,
                entity_names=entity_names,
                require_evidence=not args.no_require_evidence,
                require_trigger=not args.no_require_trigger,
            )
            logger.info(
                "Lọc %-16s %6d → %6d (sai kiểu đích %d, dư trong cặp %d, "
                "không có bằng chứng %d, không có từ kích hoạt %d, sai kiểu chủ thể %d)",
                method,
                filter_stats["n_input"],
                filter_stats["n_kept"],
                filter_stats["n_dropped_type"],
                filter_stats["n_dropped_extra"],
                filter_stats["n_dropped_ungrounded"]
                + filter_stats["n_dropped_no_evidence"],
                filter_stats["n_dropped_no_trigger"],
                filter_stats["n_dropped_source_type"],
            )
            model_filter_stats[method] = filter_stats
            model_triples = kept
        all_triples.extend(model_triples)

    merged, stats = merge_triples(
        all_triples, min_confidence=min_confidence
    )
    logger.info(
        "Gộp: %d input → %d unique (loại %d trùng, %d dưới ngưỡng)",
        stats["n_input"],
        stats["n_merged"],
        stats["n_duplicates"],
        stats["n_below_threshold"],
    )

    validation = validate_merged(merged)
    logger.info("Kiểm tra Gate: %s", validation)

    if not args.keep_generic_titles:
        entity_names = load_entity_names(
            merge_config.get(
                "entities_path", "data/knowledge_base/entities.jsonl"
            )
        )
        merged, generic_stats = drop_generic_title_triples(merged, entity_names)
        logger.info(
            "Loại tên chung (D-081): %d → %d (bỏ %d cạnh)",
            generic_stats["n_input"],
            generic_stats["n_kept"],
            generic_stats["n_dropped_generic"],
        )
    else:
        generic_stats = {
            "n_input": len(merged),
            "n_kept": len(merged),
            "n_dropped_generic": 0,
        }

    n_written = write_merged(out_path, merged)
    logger.info("Đã ghi %d triple ra %s", n_written, out_path)

    stats_path = out_path.with_suffix(".stats.json")
    stats_path.write_text(
        json.dumps(
            {
                "_meta": {
                    "min_confidence": min_confidence,
                    "n_documents": len(documents),
                },
                "merge_stats": stats,
                "model_filter_stats": model_filter_stats,
                "generic_title_filter_stats": generic_stats,
                "validation": validation,
                "by_method": _count_by_method(merged),
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    logger.info("Đã ghi %s", stats_path)
    return 0


def load_entity_names(
    entities_path: str | Path,
) -> dict[str, str]:
    """Nạp map `entity_id` → tên hiển thị (từ `entities.jsonl` Phase 9).

    Args:
        entities_path: `data/knowledge_base/entities.jsonl`.

    Returns:
        Dict `entity_id` → tên.
    """
    names: dict[str, str] = {}
    path = Path(entities_path)
    if not path.exists():
        return names
    for record in read_jsonl(path):
        entity_id = str(record.get("entity_id", ""))
        name = str(record.get("name", ""))
        if entity_id and name:
            names[entity_id] = name
    return names


def drop_generic_title_triples(
    triples: Sequence[dict[str, Any]],
    entity_names: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Loại các cạnh có đầu là **tên chung** (D-081).

    NER Phase 5 gán nhãn ``TITLE`` cho danh từ chung ("vua", "ông", "nhà"...)
    ⇒ chúng trở thành entity riêng và sinh ra cạnh vô nghĩa như
    ``Lê Thái Tổ --vo_cua--> vua``. Hàm này loại mọi cạnh mà chủ thể
    **hoặc** đối tượng có tên nằm trong `GENERIC_TITLE_NAMES`.

    So khớp **không dấu** + không phân biệt hoa/thường để bắt được cả
    "Hoàng đế" lẫn "hoang de".

    Args:
        triples: Danh sách triple đã hợp nhất.
        entity_names: Map `entity_id` → tên hiển thị. Nếu rỗng ⇒ dùng slug
            trong `entity_id` (`ent_<slug>_<hash8>`) làm tên dự phòng.

    Returns:
        Cặp ``(kept, stats)``.
    """
    stats = {"n_input": len(triples), "n_kept": 0, "n_dropped_generic": 0}

    def resolve(entity_id: str) -> str:
        """Tra tên hiển thị của một entity (fallback sang slug trong id).

        Args:
            entity_id: Id entity.

        Returns:
            Tên hiển thị (chuẩn hoá không dấu, chữ thường).
        """
        name = (entity_names or {}).get(entity_id, "")
        if not name:
            # `ent_<slug>_<hash8>` → lấy slug làm dự phòng.
            parts = entity_id.split("_")
            name = "_".join(parts[1:-1]) if len(parts) > 2 else entity_id
            # Slug dùng dấu `_` làm dấu cách ⇒ **phải** đổi thành khoảng
            # trắng. Nếu không, `ent_trieu_dai_6f5af0b6` → "trieu_dai" khác
            # "trieu dai" trong `GENERIC_TITLE_NAMES` ⇒ tên chung **không bị
            # loại** (đo được: 85 cạnh `thuoc_trieu_dai` → node "Triều đại",
            # 75 cạnh `giu_chuc_vu` → node "nhà Nguyễn").
            name = name.replace("_", " ")
        return _strip_diacritics(name)

    kept: list[dict[str, Any]] = []
    for triple in triples:
        subject = resolve(str(triple.get("subject", "")))
        obj = resolve(str(triple.get("object", "")))
        relation = str(triple.get("relation", ""))
        # Tên triều đại hợp lệ được **miễn trừ** khỏi danh sách tên chung khi
        # quan hệ là `thuoc_trieu_dai` (D-086).
        allow_dynasty = relation == "thuoc_trieu_dai"
        subject_generic = (
            subject in GENERIC_TITLE_NAMES_NODIACRITIC
            and not (allow_dynasty and subject in GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY)
        )
        obj_generic = (
            obj in GENERIC_TITLE_NAMES_NODIACRITIC
            and not (allow_dynasty and obj in GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY)
        )
        if (
            subject_generic
            or obj_generic
            or obj in GENERIC_TARGET_NAMES_BY_RELATION.get(relation, frozenset())
        ):
            stats["n_dropped_generic"] += 1
            continue
        kept.append(triple)
    stats["n_kept"] = len(kept)
    return kept, stats


def filter_model_predictions(
    triples: Sequence[dict[str, Any]],
    *,
    entity_labels: dict[str, str] | None = None,
    entity_names: dict[str, str] | None = None,
    max_per_pair: int = MAX_RELATIONS_PER_PAIR,
    require_evidence: bool = True,
    require_trigger: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Lọc quan hệ do **mô hình** dự đoán (PhoBERT/LLM).

    Hai quy tắc (D-080):

    1. **Top-1 mỗi cặp** — mỗi cặp ``(sentence_id, subject, object)`` chỉ
       giữ quan hệ có ``confidence`` cao nhất. Lý do: mô hình RE dùng masked
       BCE ⇒ ở dữ liệu ngoài tập train một cặp bị fire **13,5 quan hệ**
       trung bình (63% cặp ≥ 2 quan hệ).
    2. **Kiểu đích theo schema** — quan hệ chỉ được giữ nếu node đích có
       label hợp lệ theo `docs/04` §3.1 (vd `sinh_nam` → node `Year`).
       Node đích có label `Entity` (chưa xác minh) **vẫn được giữ** để
       không mất dữ liệu hợp lệ chưa có kiểu.
    3. **Bằng chứng có thật** (D-082) — cả tên chủ thể **và** tên đối tượng
       phải xuất hiện trong `evidence_sentence` (so khớp không dấu). Mô hình
       thường gán quan hệ cho cặp **không cùng xuất hiện trong câu** (vd
       "Lê Thái Tổ --sinh_tai--> Hoa Kỳ" với câu về Trường Chinh) ⇒ cạnh
       không có bằng chứng ⇒ vi phạm nguyên tắc #1 của `AGENTS.md`.
    4. **Từ kích hoạt trong câu** (D-083) — câu bằng chứng phải chứa ít nhất
       một **từ kích hoạt** của quan hệ (vd `vo_cua` ⇒ "vợ", "hoàng hậu"...).
       Nếu không, quan hệ bị loại: mô hình chỉ gán quan hệ cho cặp người
       **cùng nhắc trong câu**, kể cả khi câu không nói gì về quan hệ đó
       (vd "Lê Thái Tổ --vo_cua--> Lý Thái Tổ" với câu so sánh niên hiệu).

    Hàm này chỉ áp dụng cho **nguồn mô hình**; nguồn curated (infobox,
    rule, distant supervision) đã được kiểm duyệt nên giữ nguyên.

    Args:
        triples: Danh sách triple do mô hình sinh.
        entity_labels: Map `entity_id` → label Neo4j (rỗng ⇒ bỏ qua quy tắc 2).
        entity_names: Map `entity_id` → tên hiển thị (dùng cho quy tắc 3).
        max_per_pair: Số quan hệ tối đa mỗi cặp.
        require_evidence: Bật/tắt quy tắc 3.
        require_trigger: Bật/tắt quy tắc 4 (từ kích hoạt trong câu bằng chứng).

    Returns:
        Cặp ``(kept, stats)``.
    """
    stats = {
        "n_input": len(triples),
        "n_dropped_type": 0,
        "n_dropped_extra": 0,
        "n_dropped_ungrounded": 0,
        "n_dropped_no_evidence": 0,
        "n_dropped_no_trigger": 0,
        "n_dropped_source_type": 0,
    }
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    extras: list[dict[str, Any]] = []
    for triple in triples:
        key = (
            str(triple.get("sentence_id", "")),
            str(triple.get("subject", "")),
            str(triple.get("object", "")),
        )
        current = best.get(key)
        if current is None:
            best[key] = triple
        elif float(triple.get("confidence", 0)) > float(current.get("confidence", 0)):
            best[key] = triple
            extras.append(current)
        else:
            extras.append(triple)

    kept: list[dict[str, Any]] = []
    for key, triple in best.items():
        relation = str(triple.get("relation", ""))
        allowed = RELATION_TARGET_TYPES.get(relation)
        if allowed and entity_labels:
            target_label = entity_labels.get(str(triple.get("object", "")), "")
            if target_label and target_label not in allowed:
                # Đích là entity chưa xác minh → vẫn giữ.
                if target_label != "Entity":
                    stats["n_dropped_type"] += 1
                    continue
        # Kiểu **chủ thể** theo schema (D-084).
        allowed_source = RELATION_SOURCE_TYPES.get(relation)
        if allowed_source and entity_labels:
            source_label = entity_labels.get(str(triple.get("subject", "")), "")
            if source_label and source_label not in allowed_source:
                if source_label != "Entity":
                    stats["n_dropped_source_type"] += 1
                    continue
        kept.append(triple)
    stats["n_dropped_extra"] = len(extras)

    if entity_names and require_evidence:
        grounded: list[dict[str, Any]] = []
        for triple in kept:
            subject = str((entity_names or {}).get(str(triple.get("subject", "")), ""))
            obj = str((entity_names or {}).get(str(triple.get("object", "")), ""))
            evidence = str(triple.get("evidence_sentence") or "")
            if not evidence:
                stats["n_dropped_no_evidence"] += 1
                continue
            evidence_key = _strip_diacritics(evidence)
            subject_ok = not subject or _strip_diacritics(subject) in evidence_key
            object_ok = not obj or _strip_diacritics(obj) in evidence_key
            if subject_ok and object_ok:
                grounded.append(triple)
            else:
                stats["n_dropped_ungrounded"] += 1
        kept = grounded

    if require_trigger:
        triggered: list[dict[str, Any]] = []
        for triple in kept:
            relation = str(triple.get("relation", ""))
            strong = RELATION_TRIGGER_STRONG.get(relation)
            weak = RELATION_TRIGGER_WEAK.get(relation)
            if not strong and not weak:
                # Quan hệ không có từ kích hoạt riêng → không áp dụng.
                triggered.append(triple)
                continue
            evidence = str(triple.get("evidence_sentence") or "")
            evidence_key = _strip_diacritics(evidence)
            subject = str((entity_names or {}).get(str(triple.get("subject", "")), ""))
            obj = str((entity_names or {}).get(str(triple.get("object", "")), ""))
            names = (
                [_strip_diacritics(subject), _strip_diacritics(obj)]
                if entity_names
                else []
            )
            # Mức mạnh: chỉ cần có mặt trong câu.
            if strong and any(
                _strip_diacritics(trigger) in evidence_key for trigger in strong
            ):
                triggered.append(triple)
                continue
            # Mức yếu: phải nằm gần tên entity của cặp.
            if weak and _has_trigger_near(
                evidence_key,
                frozenset(_strip_diacritics(trigger) for trigger in weak),
                names,
            ):
                triggered.append(triple)
                continue
            stats["n_dropped_no_trigger"] += 1
        kept = triggered

    stats["n_kept"] = len(kept)
    return kept, stats


def _has_trigger_near(
    evidence_key: str,
    triggers: frozenset[str],
    names: list[str],
    window: int = 30,
) -> bool:
    """Kiểm tra từ kích hoạt có nằm **gần** tên entity trong câu không.

    Vì sao cần (D-083): chỉ kiểm tra "câu có chứa từ kích hoạt" là chưa đủ —
    trong câu dài, từ "vợ" của entity khác vẫn làm cho quan hệ pass. Vì vậy
    từ kích hoạt phải nằm trong cửa sổ ±``window`` ký tự quanh ít nhất một
    tên entity của cặp. Cửa sổ 30 ký tự ≈ 5–6 từ tiếng Việt — đủ hẹp để
    loại các cặp chỉ "cùng xuất hiện trong câu" mà không có quan hệ thật.

    Args:
        evidence_key: Câu bằng chứng đã bỏ dấu + hạ chữ thường.
        triggers: Tập từ kích hoạt của quan hệ.
        names: Danh sách tên entity của cặp (đã bỏ dấu + hạ chữ thường).
        window: Bán kính (ký tự) quanh tên được coi là "gần".

    Returns:
        ``True`` nếu có từ kích hoạt nằm gần ít nhất một tên.
    """
    positions: list[int] = []
    for name in names:
        if not name:
            continue
        start = 0
        while True:
            index = evidence_key.find(name, start)
            if index < 0:
                break
            positions.append(index)
            start = index + 1
    if not positions:
        # Không xác định được vị trí tên → chỉ kiểm tra toàn câu.
        return any(trigger in evidence_key for trigger in triggers)
    for trigger in triggers:
        start = 0
        while True:
            index = evidence_key.find(trigger, start)
            if index < 0:
                break
            if any(abs(index - position) <= window for position in positions):
                return True
            start = index + 1
    return False


def load_entity_labels(
    entities_path: str | Path,
    infobox_entities_path: str | Path,
) -> dict[str, str]:
    """Nạp map `entity_id` → label Neo4j (để kiểm tra kiểu đích).

    Args:
        entities_path: `data/knowledge_base/entities.jsonl` (Phase 9).
        infobox_entities_path: `data/interim/infobox_entities.jsonl` (Phase 3).

    Returns:
        Dict `entity_id` → label.
    """
    from src.graph.build_graph import TYPE_TO_LABEL

    labels: dict[str, str] = {}
    for path in (entities_path, infobox_entities_path):
        if not Path(path).exists():
            continue
        for record in read_jsonl(path):
            entity_id = str(record.get("entity_id", ""))
            if not entity_id or entity_id in labels:
                continue
            entity_type = str(record.get("type", "") or "unknown")
            labels[entity_id] = TYPE_TO_LABEL.get(entity_type, "Entity")
    return labels


def _count_by_method(merged: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Đếm số triple theo từng `method`.

    Args:
        merged: Danh sách triple đã hợp nhất.

    Returns:
        Dict ``method`` → số lượng.
    """
    counter: dict[str, int] = defaultdict(int)
    for triple in merged:
        counter[str(triple.get("method", ""))] += 1
    return dict(sorted(counter.items(), key=lambda item: -item[1]))


if __name__ == "__main__":
    sys.exit(main())

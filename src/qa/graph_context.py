"""Phase 15 — Bước 1: lấy context từ Knowledge Graph cho Hybrid GraphRAG.

Vì sao **Cypher template cố định** thay vì LLM sinh Cypher?
-----------------------------------------------------------
| Tiêu chí | LLM sinh Cypher | Template cố định |
|---|---|---|
| Đảo chiều quan hệ | sai ~30% (chỉ có few-shot chiều thuận) | **đúng 100%** (bảng 19 dòng) |
| Biến thiên giữa 2 arm | có (prompt khác ⇒ Cypher khác) | **không** ⇒ so sánh công bằng |
| Tốc độ | 1–3 s (gọi API) | **0,11 s** (truy vấn Neo4j) |
| Quota LLM | tốn | **0** |

⇒ Template cố định là lựa chọn đúng cho **kênh KG trong Hybrid**: nó cung cấp
thông tin có cấu trúc, chính xác, rẻ — và biến "đóng góp của đồ thị" thành
điều **đo được** (ablation B vs B− trong Phase 16).

Mô hình truy xuất KG
--------------------
```
chunk đã lấy (từ Retriever) → entity_ids
       │
       ├──► 1-hop từ entity của chunk  (mở rộng ngữ cảnh)
       └──► template theo ý định      (truy vấn thẳng theo câu hỏi)
```

Lọc nhiễu
---------
Mọi cạnh trả về đều đi qua `src/graph/noise_filter.py` (D-095) ở **tầng
đọc** ⇒ Neo4j không bị thay đổi (giữ nguyên 19.548 node / 13.379 cạnh ⇒
tính tái lập của artifact Phase 10).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.common.logger import get_logger

from src.graph.direction import normalize_edges
from src.graph.noise_filter import filter_noisy_edges

logger = get_logger("src.qa.graph_context")

#: Bảng chiều đảo quan hệ: quan hệ lưu chiều → quan hệ "đảo" dùng khi hỏi
#: ngược. 19 dòng, đối xứng 2 chiều.
INVERSE_RELATION: dict[str, str] = {
    "cha_cua": "con_cua",
    "me_cua": "con_cua",
    "con_cua": "cha_cua_va_me_cua",
    "anh_em_cua": "anh_em_cua",
    "vo_cua": "chong_cua",
    "chong_cua": "vo_cua",
    "ke_vi": "ke_vi",
    "thuoc_trieu_dai": "co_vua_trong_trieu_dai",
    "giu_chuc_vu": "co_nguoi_giu_chuc_vu",
    "chi_huy_tran": "chi_huy_tran",
    "tham_gia_tran": "tham_gia_tran",
    "danh_bai": "danh_bai",
    "sinh_nam": "sinh_nam",
    "sinh_tai": "sinh_tai",
    "mat_nam": "mat_nam",
    "mat_tai": "mat_tai",
    "lap_ra": "duoc_lap_ra_boi",
    "dien_ra_tai": "dien_ra_tai",
    "dong_doi_tai": "dong_doi_tai",
}

#: Nhãn quan hệ hiển thị cho người dùng (tiếng Việt).
#:
#: Quy ước: ``[n] {source} — {label} → {target}``. Với quan hệ **gia đình**,
#: KG lưu theo chiều **con → cha/mẹ** (doc §3.1) ⇒ nhãn mô tả vai trò của
#: **target** ⇒ dạng mũi tên dễ bị LLM đọc ngược ⇒ dùng template riêng
#: (xem `RELATION_TEMPLATE`) để câu hiển thị là **mệnh đề tự nhiên**.
RELATION_LABEL: dict[str, str] = {
    "cha_cua": "cha của",
    "me_cua": "mẹ của",
    "vo_cua": "vợ của",
    "chong_cua": "chồng của",
    "anh_em_cua": "anh/em của",
    "ke_vi": "kế vị của",
    "thuoc_trieu_dai": "thuộc triều đại",
    "giu_chuc_vu": "giữ chức vụ",
    "lap_ra": "lập ra",
    "chi_huy_tran": "chỉ huy trận",
    "tham_gia_tran": "tham gia trận",
    "danh_bai": "đánh bại",
    "sinh_nam": "sinh năm",
    "sinh_tai": "sinh tại",
    "mat_nam": "mất năm",
    "mat_tai": "mất tại",
    "dien_ra_tai": "diễn ra tại",
    "dong_doi_tai": "đóng đôi tại",
    # Nhãn **đảo** — sinh ra khi hiển thị cạnh theo chiều ngược (D-118).
    "con_cua": "con của",
    "con_cua_va_me_cua": "con của",
    # Nhãn cho **chuỗi quan hệ** (D-120): mỗi bước là 1 cạnh.
    "cha_cua_hop": "cha của",
    "me_cua_hop": "mẹ của",
    "vo_cua_hop": "vợ của",
    "chong_cua_hop": "chồng của",
    "con_cua_hop": "con của",
    "chain_result": "kết quả chuỗi quan hệ",
}

#: Template hiển thị **mệnh đề tự nhiên** cho quan hệ gia đình.
#:
#: Vì sao cần?
#: ----------
#: Dạng mũi tên ``A — mẹ của → B`` bị LLM đọc **ngược** (đo được ở q0001:
#: dòng ``Mai Ngọc Đỉnh — mẹ của → Nguyễn Thị Tuyến`` bị hiểu thành
#: "Mai Ngọc Đỉnh là **mẹ** của Nguyễn Thị Tuyến" ⇒ trả lời sai ⇒ judge chấm
#: `faithfulness = 0`). ⇒ Hiển thị thành câu có **chủ thể → vị thể rõ ràng**
#: ⇒ không thể đọc ngược.
#:
#: Lưu ý chiều: KG lưu ``A -[cha_cua]-> B`` nghĩa **A là con của B**
#: (doc §3.1; evidence ``"Mẹ: X"`` xác nhận subject là con) ⇒ với quan hệ
#: gia đình, **vai trò nằm ở target**.
RELATION_TEMPLATE: dict[str, str] = {
    "cha_cua": "{target} là cha của {source}",
    "me_cua": "{target} là mẹ của {source}",
    "con_cua": "{target} là con của {source}",
    "con_cua_va_me_cua": "{target} là con của {source}",
    "vo_cua": "{target} là vợ của {source}",
    "chong_cua": "{target} là chồng của {source}",
    "anh_em_cua": "{source} và {target} là anh em",
    # Chuỗi quan hệ (D-120) — cùng dạng mệnh đề tự nhiên.
    "cha_cua_hop": "{target} là cha của {source}",
    "me_cua_hop": "{target} là mẹ của {source}",
    "vo_cua_hop": "{target} là vợ của {source}",
    "chong_cua_hop": "{target} là chồng của {source}",
    "con_cua_hop": "{target} là con của {source}",
    "chain_result": "{target} là kết quả của chuỗi quan hệ từ {source}",
}

#: Template hiển thị **mệnh đề tự nhiên** cho quan hệ **sự kiện** (D-139).
#:
#: Vì sao cần?
#: ----------
#: Dạng mũi tên ``Trận Hà Hồi — chỉ huy trận → Ngô Văn Sở`` bị đọc **ngược**
#: ⇒ LLM (và judge) hiểu thành "Trận Hà Hồi chỉ huy trận" ⇒ trả lời sai /
#: judge chấm *"thông tin về chỉ huy không có trong ngữ cảnh"*.
#: Đo được (D-124, 60 câu narrative): **7/60** câu arm B bị trừ điểm **vì lý
#: do này** (q0062, q0077, q0082, q0102, q0107…).
#:
#: ⇒ Dựng mệnh đề theo **nhãn node thật** (`Event` / `Person` / `Place`) ⇒
#: không phụ thuộc chiều `source`/`target` ⇒ **không thể đọc ngược**.
#:
#: Tham số: `{event}` = tên sự kiện, `{other}` = node còn lại.
EVENT_RELATION_TEMPLATES: dict[str, str] = {
    "chi_huy_tran": "{other} là người chỉ huy {event}",
    "tham_gia_tran": "{other} là bên tham chiến trong {event}",
    "dien_ra_tai": "{event} diễn ra tại {other}",
}

#: Trần số cạnh trả về mỗi truy vấn (không vượt quy tắc `LIMIT ≤ 100`).
MAX_EDGES = 60


@dataclass
class GraphContext:
    """Kết quả truy xuất KG.

    Attributes:
        entities: Danh sách node liên quan.
        edges: Danh sách cạnh (đã lọc nhiễu).
        source: Nguồn ("intent" | "chunk_expansion").
        elapsed_ms: Thời gian truy vấn (ms).
        queries: Danh sách Cypher đã chạy (để truy vết).
    """

    entities: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    source: str = "intent"
    elapsed_ms: int = 0
    queries: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """Kiểm tra context có rỗng không.

        Returns:
            ``True`` nếu không có entity hay cạnh nào.
        """
        return not self.entities and not self.edges

    def to_dict(self) -> dict[str, Any]:
        """Chuyển sang dict (serialize).

        Returns:
            Dict context.
        """
        return {
            "entities": self.entities,
            "edges": self.edges,
            "source": self.source,
            "elapsed_ms": self.elapsed_ms,
            "n_entities": len(self.entities),
            "n_edges": len(self.edges),
        }

    def to_text(self) -> str:
        """Chuyển sang văn bản cho context LLM.

        Returns:
            Chuỗi mô tả các quan hệ tìm được.
        """
        if not self.edges and not self.entities:
            return ""
        lines: list[str] = []
        if self.entities:
            names = ", ".join(
                str(e.get("name") or e.get("entity_id") or "") for e in self.entities[:12]
            )
            lines.append(f"- Các thực thể liên quan: {names}")
        for edge in self.edges:
            source = edge.get("source_name") or edge.get("source")
            target = edge.get("target_name") or edge.get("target")
            relation = str(edge.get("relation") or "")
            label = RELATION_LABEL.get(relation, relation)
            evidence = str(edge.get("evidence_sentence") or "").strip()
            line = f"- {source} — {label} → {target}"
            if evidence:
                line += f" (bằng chứng: {evidence[:200]})"
            lines.append(line)
        return "\n".join(lines)


#: Các template Cypher theo ý định. Tham số: `$entity_id` (entity đã link).
#:
#: Mỗi template trả về cùng một shape ⇒ `run_read_query` cho dict thống nhất.
_INTENT_TEMPLATES: dict[str, dict[str, Any]] = {
    "relational": {
        "description": "Quan hệ trực tiếp của entity (2 chiều)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r]-(other)
            WITH startNode(r) AS s, endNode(r) AS t, r
            RETURN s.entity_id AS source_id,
                   s.name AS source_name,
                   type(r) AS relation,
                   t.entity_id AS target_id,
                   t.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "biographical": {
        "description": "Thuộc tính sinh tử (sinh/mất năm, nơi sinh, nơi mất)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})
            OPTIONAL MATCH (e)-[r1]->(y1:Year)
            OPTIONAL MATCH (e)-[r2]->(p1:Place)
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   'thuoc_tinh' AS relation,
                   coalesce(y1.name, p1.name, '') AS target_name,
                   coalesce(y1.entity_id, p1.entity_id, '') AS target_id,
                   r1.confidence AS confidence,
                   r1.evidence_sentence AS evidence_sentence,
                   r1.source_url AS source_url,
                   r1.method AS method
            LIMIT $limit
        """,
    },
    "event": {
        "description": "Sự kiện liên quan (chỉ huy, tham gia, diễn ra tại)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r]-(other)
            WHERE type(r) IN $event_relations
            WITH startNode(r) AS s, endNode(r) AS t, r
            RETURN s.entity_id AS source_id,
                   s.name AS source_name,
                   type(r) AS relation,
                   t.entity_id AS target_id,
                   t.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "event_deep": {
        "description": (
            "Sự kiện + quan hệ **bối cảnh** quanh sự kiện (chỉ huy, bên tham "
            "chiến, địa điểm, triều đại, chức vụ)"
        ),
        # D-123: template cũ **nhân bản** 2 hop ⇒ tích `r1 × r2` (cartesian
        # product) ⇒ `LIMIT 60` cắt cụt **cả cạnh 1-hop** còn lại 4/12 ⇒ mất
        # 8/10 chỉ huy (đo được với "Cuộc bao vây thành Quy Nhơn").
        # ⇒ Tách **2 truy vấn độc lập** (union, không nhân bản):
        #   - `event_deep` : hop-1 (cạnh trực tiếp của sự kiện).
        #   - `event_hop2` : hop-2 (cạnh của node trung gian).
        # ⇒ Mỗi truy vấn có `LIMIT` riêng ⇒ không cạnh nào bị cắt oan.
        #
        # D-123: chỉ dùng **quan hệ bối cảnh** (`CONTEXT_RELATIONS`) — không
        # dùng quan hệ sinh tử (sinh/mất) vì chúng là **nhiễu** cho câu hỏi
        # tự sự (đo được: 27,4 cạnh nhiễu/câu với "mọi quan hệ" ⇒ 0,0 với
        # `CONTEXT_RELATIONS`).
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r1]-(n1)
            WHERE type(r1) IN $context_relations
            WITH startNode(r1) AS s1, endNode(r1) AS t1, r1
            RETURN s1.entity_id AS source_id,
                   s1.name AS source_name,
                   labels(s1) AS source_labels,
                   type(r1) AS relation,
                   t1.entity_id AS target_id,
                   t1.name AS target_name,
                   labels(t1) AS target_labels,
                   r1.confidence AS confidence,
                   r1.evidence_sentence AS evidence_sentence,
                   r1.source_url AS source_url,
                   r1.method AS method
            LIMIT $limit
        """,
    },
    "event_hop2": {
        "description": (
            "Quan hệ **hop-2** quanh sự kiện: cạnh của node trung gian "
            "(người chỉ huy → trận khác, địa điểm → sự kiện khác…)"
        ),
        # D-123: hop-2 chỉ giữ quan hệ **sự kiện** (`EVENT_RELATIONS`) — đây
        # là chỗ chứa "các bên liên quan" (người chỉ huy → trận khác, địa điểm
        # → sự kiện khác). Thêm quan hệ sinh tử chỉ gây nhiễu.
        #
        # D-124: chỉ giữ hop-2 **chạm lại chính sự kiện đang hỏi** (`n2 = e`)
        # ⇒ cạnh hop-2 chỉ còn "các bên liên quan của sự kiện này" (địa
        # điểm ↔ sự kiện, bên tham chiến ↔ sự kiện) mà **không** kéo theo
        # sự kiện khác. Vì sao?
        # ---------------------------------
        # Đo được (D-124, 59 sự kiện của 60 câu narrative):
        #   - hop-2 **tự do** = 1.229/1.731 cạnh (71%) ⇒ chỉ còn **29%** là
        #     cạnh trực tiếp của sự kiện.
        #   - Trong đó `dien_ra_tai` chiếm **694 cạnh** (56% hop-2) — đây là
        #     cạnh "địa điểm → sự kiện khác cùng địa điểm" ⇒ **nhiễu thuần**.
        #   - Chi phí: hop-2 chiếm **70,2%** ngân sách KG (282K/402K ký tự) ⇒
        #     chen ngang các cạnh hop-1 **có giá trị** (chỉ huy, bên tham
        #     chiến) ⇒ LLM đọc nhiều quan hệ lạ, bỏ qua quan hệ đúng ⇒
        #     judge chấm "sai", "bịa" (đo được: 40,1% cạnh KG trong context
        #     không chứa từ khoá chủ thể của câu hỏi).
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r1]-(n1)
            WHERE type(r1) IN $context_relations
            MATCH (n1)-[r2]-(n2)
            WHERE type(r2) IN $event_relations
              AND n2 = e
            WITH startNode(r2) AS s2, endNode(r2) AS t2, r2
            RETURN s2.entity_id AS source_id,
                   s2.name AS source_name,
                   labels(s2) AS source_labels,
                   type(r2) AS relation,
                   t2.entity_id AS target_id,
                   t2.name AS target_name,
                   labels(t2) AS target_labels,
                   r2.confidence AS confidence,
                   r2.evidence_sentence AS evidence_sentence,
                   r2.source_url AS source_url,
                   r2.method AS method
            LIMIT $limit
        """,
    },
    "event_parties": {
        "description": (
            "**Các bên liên quan** của sự kiện: người chỉ huy, bên tham "
            "chiến, địa điểm — lấy theo **cả hai chiều** của cạnh"
        ),
        # D-124: đây là cơ chế **quan trọng nhất** cho câu hỏi tự sự.
        #
        # Vì sao cần?
        # ---------
        # Đo được (D-124): trên 60 câu narrative, chỉ **39/60** sự kiện có
        # cạnh hop-1 thuộc `chi_huy_tran`/`tham_gia_tran`. ⇒ 21/60 câu **không
        # có** "các bên liên quan" nào trong context KG ⇒ Hybrid không có gì
        # để thêm so với RAG thuần.
        #
        # ⇒ Bổ sung: lấy **mọi** cạnh sự kiện theo **chiều ngược** — tức là
        # cạnh mà node trung gian (`n1`) là **người chỉ huy/bên tham chiến**
        # của sự kiện, nhưng bản thân cạnh đó lại trỏ tới **sự kiện khác**
        # (vd "Ngô Văn Sở — chỉ huy trận → Trận Ngọc Hồi – Đống Đa").
        # ⇒ Nhờ vậy ta biết **Ngô Văn Sở là chỉ huy** mà không cần cạnh
        # trực tiếp với sự kiện đang hỏi.
        #
        # Bộ lọc: chỉ giữ cạnh mà **một đầu** là node sự kiện (`n2`) và cạnh
        # đó **không** chạm sự kiện gốc (tránh trùng với hop-1/hop-2 đã lấy).
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r1]-(n1)
            WHERE type(r1) IN $party_relations
            MATCH (n1)-[r2]-(n2)
            WHERE type(r2) IN $event_relations
              AND n2 <> e
            WITH DISTINCT startNode(r2) AS s2, endNode(r2) AS t2, r2
            RETURN s2.entity_id AS source_id,
                   s2.name AS source_name,
                   labels(s2) AS source_labels,
                   type(r2) AS relation,
                   t2.entity_id AS target_id,
                   t2.name AS target_name,
                   labels(t2) AS target_labels,
                   r2.confidence AS confidence,
                   r2.evidence_sentence AS evidence_sentence,
                   r2.source_url AS source_url,
                   r2.method AS method
            LIMIT $limit
        """,
    },
    "dynasty": {
        "description": "Vua của một triều đại + quan hệ triều đại",
        "cypher": """
            MATCH (e {entity_id: $entity_id})
            OPTIONAL MATCH (p:Person)-[r]->(e)
            WHERE type(r) = 'thuoc_trieu_dai'
            RETURN e.entity_id AS source_id,
                   e.name AS source_name,
                   'co_vua_trong_trieu_dai' AS relation,
                   p.entity_id AS target_id,
                   p.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "inverse_family": {
        "description": "Truy vấn chiều ngược gia đình (con của, vợ của)",
        "cypher": """
            MATCH (e {entity_id: $entity_id})<-[r]-(other)
            WHERE type(r) IN $family_relations
            RETURN other.entity_id AS source_id,
                   other.name AS source_name,
                   type(r) AS relation,
                   e.entity_id AS target_id,
                   e.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
    "one_hop": {
        "description": "Mở rộng 1-hop từ entity của chunk",
        "cypher": """
            MATCH (e {entity_id: $entity_id})-[r]-(other)
            WITH startNode(r) AS s, endNode(r) AS t, r
            RETURN s.entity_id AS source_id,
                   s.name AS source_name,
                   type(r) AS relation,
                   t.entity_id AS target_id,
                   t.name AS target_name,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
        """,
    },
}

#: Nhóm quan hệ sự kiện.
EVENT_RELATIONS: list[str] = [
    "chi_huy_tran", "tham_gia_tran", "danh_bai", "dien_ra_tai", "lap_ra",
]

#: Quan hệ **bối cảnh** — hữu ích cho câu hỏi tự sự ("nhà nào", "ai giữ chức
#: vụ", "kế vị ai") nhưng **không gây nhiễu** như quan hệ sinh tử.
CONTEXT_RELATIONS: list[str] = EVENT_RELATIONS + [
    "thuoc_trieu_dai", "giu_chuc_vu", "ke_vi",
]

#: Quan hệ **sinh tử** — nhiễu nặng cho câu hỏi tự sự.
#:
#: Vì sao phải loại?
#: ---------------
#: Đo được (60 câu narrative): truy vấn "mọi quan hệ" trả **27,4 cạnh
#: sinh/mất** mỗi câu — gần **50%** context KG là rác ("Trần Hưng Đạo — mất
#: tại → Quốc lộ 14"; "Nguyễn Huy Tự — sinh tại → Đà Nẵng" cho câu hỏi về
#: *Chiến dịch Market Time*) ⇒ LLM bị nhiễu và gán nhầm thông tin.
LIFE_RELATIONS: list[str] = [
    "sinh_tai", "mat_tai", "sinh_nam", "mat_nam", "dong_doi_tai",
]

#: Quan hệ **"bên liên quan"** — dùng để **mở rộng** danh sách người chỉ huy
#: / bên tham chiến khi sự kiện không có cạnh trực tiếp (D-124).
#:
#: Vì sao cần?
#: -----------
#: Đo được (D-124, 60 câu narrative): chỉ **39/60** sự kiện có cạnh hop-1
#: thuộc `chi_huy_tran`/`tham_gia_tran` ⇒ 21/60 câu **không có** "các bên
#: liên quan" trong context KG ⇒ Hybrid **không có gì** để thêm so với RAG
#: thuần (đây là lý do B thua A ở nhóm câu hỏi này).
#:
#: Ví dụ đo được — "Trận Hà Hồi" chỉ có 3 chỉ huy trong KG (Ngô Văn Sở,
#: Phan Văn Lân, Trương Triều Long) nhưng bài Wikipedia kể "Quang Trung cho
#: quân vây chặt đồn" ⇒ đáp án chuẩn có Quang Trung mà KG **không** có.
PARTY_RELATIONS: list[str] = ["chi_huy_tran", "tham_gia_tran"]

#: Tiền tố bằng chứng theo quan hệ sự kiện (D-123).
#:
#: Vì sao cần?
#: ----------
#: Bằng chứng của KG có dạng `"<Vai trò>: <Tên>"` — ví dụ `"Chỉ huy: Võ Tánh"`.
#: Bằng chứng là **nguồn chính xác nhất** cho tên hiển thị (được trích tự
#: động từ infobox Wikipedia), trong khi `node.name` có thể là **danh xưng**
#: thay vì tên riêng (xem `TITLE_NODE_LABELS` bên dưới).
EVENT_EVIDENCE_PREFIXES: dict[str, str] = {
    "chi_huy_tran": "Chỉ huy",
    "tham_gia_tran": "Bên tham chiến",
    "dien_ra_tai": "Địa điểm",
    "danh_bai": "Đánh bại",
    "lap_ra": "Lập ra",
}

#: Tiền tố bằng chứng **có biến thể** (D-124).
#:
#: Vì sao cần?
#: ----------
#: Không phải cạnh nào cũng dùng đúng tiền tố chuẩn: đo được trong KG có
#: **129** cạnh `chi_huy_tran` với tiền tố `"Chi Huy 1"` (63 cạnh) hoặc
#: `"Chi Huy 2"` (66 cạnh) — đây là các bản infobox ghi **nhiều chỉ huy** theo
#: thứ tự. ⇒ Cơ chế `_resolve_title_names` / hiển thị bằng chứng phải nhận
#: diện được các biến thể này, nếu không node `Title` sẽ **không** được
#: sửa tên ⇒ tái diễn lỗi "quận công".
#:
#: Lưu ý: biến thể được **gắn theo quan hệ** (`chi_huy_tran` chỉ nhận tiền tố
#: "Chỉ huy"/"Chi Huy*") ⇒ tránh tình huống cạnh `chi_huy_tran` mang bằng
#: chứng `"Địa điểm: Bình Định"` bị hiểu nhầm thành tên chỉ huy.
EVIDENCE_PREFIX_VARIANTS: dict[str, tuple[str, ...]] = {
    "chi_huy_tran": ("Chỉ huy", "Chi Huy 1", "Chi Huy 2", "Chi Huy"),
    "tham_gia_tran": ("Bên tham chiến",),
    "dien_ra_tai": ("Địa điểm",),
    "danh_bai": ("Đánh bại",),
    "lap_ra": ("Lập ra",),
}

#: Node nhãn `Title` có `node.name` là **danh xưng**, không phải tên riêng.
#:
#: Vì sao cần?
#: ----------
#: Node `ent_nguyen_van_thanh_539b705c` có `name = "quận công"` (danh xưng) nhưng
#: bằng chứng cạnh là `"Chỉ huy: Nguyễn Văn Thành"` ⇒ hiển thị "quận công —
#: chỉ huy trận → Cuộc bao vây thành Quy Nhơn" khiến LLM **gán nhầm** danh xưng
#: này cho **cả 10 chỉ huy** thật của trận đánh (đo được: câu trả lời cho
#: "Cuộc bao vây thành Quy Nhơn" nói "các tướng Võ Tánh, Nguyễn Văn Thành,
#: Gia Long" — nhưng "Gia Long" **không có mặt** trong văn bản, chỉ có trong KG).
#:
#: ⇒ Khi node là `Title`, dùng **tên trong bằng chứng** làm tên hiển thị.
TITLE_NODE_LABELS: frozenset[str] = frozenset({"Title"})

#: Nhóm quan hệ gia đình (dùng cho truy vấn chiều ngược).
FAMILY_RELATIONS: list[str] = [
    "cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua",
]

#: **Toàn bộ** quan hệ trong KG (dùng cho truy vấn 2-hop).
#:
#: Vì sao cần (D-121)?
#: --------------------
#: Câu hỏi loại `narrative` ("Kể lại diễn biến Trận Hà Hồi") cần **các bên
#: liên quan**: người chỉ huy, quân tham chiến, địa điểm. Trong KG, các
#: quan hệ đó nằm **2 bước** từ node sự kiện:
#:
#: ```text
#: Trận Hà Hồi --dien_ra_tai--> Hà Tây
#: Trận Hà Hồi <--chi_huy_tran-- Ngô Văn Sở
#: ```
#:
#: ⇒ truy vấn 1-hop không thấy "người chỉ huy" ⇒ Hybrid không có gì để
#: thêm so với RAG thuần. Truy vấn 2-hop với **mọi** quan hệ khắp phục.
ALL_RELATIONS: list[str] = [
    "sinh_tai", "chi_huy_tran", "cha_cua", "mat_tai", "sinh_nam", "mat_nam",
    "vo_cua", "giu_chuc_vu", "anh_em_cua", "thuoc_trieu_dai", "dien_ra_tai",
    "ke_vi", "tham_gia_tran", "me_cua", "chong_cua", "lap_ra",
    "dong_doi_tai", "danh_bai",
]


def _run(cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Chạy truy vấn Cypher chỉ đọc.

    Args:
        cypher: Câu Cypher.
        params: Tham số.

    Returns:
        Danh sách record (rỗng nếu lỗi).
    """
    from backend.app.services.neo4j_client import run_read_query

    try:
        return run_read_query(cypher, params)
    except Exception as error:  # noqa: BLE001 - KG lỗi không được làm hỏng RAG
        logger.warning("Truy vấn KG lỗi (%s) — bỏ qua", error)
        return []


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Loại trùng cạnh theo `(source, relation, target)`.

    Args:
        edges: Danh sách cạnh.

    Returns:
        Danh sách cạnh đã loại trùng.
    """
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for edge in edges:
        key = (
            str(edge.get("source_id") or ""),
            str(edge.get("relation") or ""),
            str(edge.get("target_id") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(edge)
    return out


def _name_from_evidence(relation: str, evidence: str) -> str:
    """Trích **tên riêng** từ bằng chứng KG (D-123).

    Vì sao cần?
    -----------
    Bằng chứng của KG có dạng `"<Vai trò>: <Tên riêng>"` — ví dụ
    `"Chỉ huy: Nguyễn Văn Thành"`, `"Bên tham chiến: Nhà Thanh"`,
    `"Địa điểm: Định Tường"`. Tên trong bằng chứng được trích **tự động từ
    infobox Wikipedia** ⇒ chính xác hơn `node.name` (vốn có thể là **danh
    xưng**: node `ent_nguyen_van_thanh_539b705c` có `name = "quận công"`).

    Args:
        relation: Tên quan hệ.
        evidence: Câu bằng chứng.

    Returns:
        Tên riêng, hoặc `""` nếu bằng chứng không theo định dạng.
    """
    prefix = EVENT_EVIDENCE_PREFIXES.get(relation)
    text = (evidence or "").strip()
    if not text:
        return ""
    # D-124: thử tiền tố **chuẩn** trước, rồi tới các **biến thể**
    # (vd "Chi Huy 1: …", "Chi Huy 2: …") — bằng chứng dạng đa chỉ huy.
    candidates = list(EVIDENCE_PREFIX_VARIANTS.get(relation, ()))
    if prefix and prefix not in candidates:
        candidates.insert(0, prefix)
    for candidate in candidates:
        if not text.startswith(candidate + ":"):
            continue
        value = text[len(candidate) + 1:].strip()
        # Bằng chứng dài ⇒ không phải mẫu "Vai trò: Tên" đơn giản ⇒ bỏ qua.
        if not value or len(value) > 80:
            continue
        return value
    return ""


def _resolve_title_names(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sửa **tên hiển thị** của node `Title` bằng tên trong bằng chứng (D-123).

    Vì sao cần?
    -----------
    Node nhãn `Title` có `name` là **danh xưng** (vd "quận công"), không phải
    tên riêng. Khi hiển thị cạnh `chi_huy_tran`, LLM đọc:

        "quận công — chỉ huy trận → Cuộc bao vây thành Quy Nhơn"

    ⇒ hiểu là **"quận công"** là người chỉ huy trận ⇒ gán danh xưng này cho
    **cả 10 chỉ huy** thật (đo được: câu trả lời cho "Cuộc bao vây thành
    Quy Nhơn" nói "các tướng Võ Tánh, Nguyễn Văn Thành, Gia Long" — trong đó
    "Gia Long" **không** xuất hiện trong văn bản, chỉ có ở KG ⇒ judge chấm
    `faithfulness = 1` vì "thông tin ngoài ngữ cảnh").

    ⇒ Khi node là `Title`, **thay tên hiển thị** bằng tên trong bằng chứng
    (`"Chỉ huy: Nguyễn Văn Thành"` ⇒ `"Nguyễn Văn Thành"`) ⇒ LLM đọc đúng.

    Args:
        edges: Danh sách cạnh.

    Returns:
        Danh sách cạnh đã sửa tên hiển thị (copy — không sửa input).
    """
    out: list[dict[str, Any]] = []
    for edge in edges:
        item = dict(edge)
        relation = str(item.get("relation") or "")
        evidence = str(item.get("evidence_sentence") or "")
        resolved = _name_from_evidence(relation, evidence)
        if not resolved:
            out.append(item)
            continue
        for id_key, name_key, labels_key in (
            ("source_id", "source_name", "source_labels"),
            ("target_id", "target_name", "target_labels"),
        ):
            labels = item.get(labels_key) or []
            if not (isinstance(labels, list) and "Title" in labels):
                continue
            item[name_key] = resolved
            item[f"{id_key}_display_fixed"] = True
        out.append(item)
    return out



class GraphContextBuilder:
    """Dựng context KG cho Hybrid GraphRAG.

    Attributes:
        max_edges: Trần số cạnh mỗi truy vấn.
    """

    def __init__(self, *, max_edges: int = MAX_EDGES) -> None:
        """Khởi tạo.

        Args:
            max_edges: Trần số cạnh.
        """
        self.max_edges = max_edges

    # ------------------------------------------------------------------
    # Intent templates
    # ------------------------------------------------------------------

    def fetch(
        self,
        intent: str,
        entity_id: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> GraphContext:
        """Truy vấn KG theo ý định + entity.

        Vì sao chạy **2 template** cho ý định `narrative`? (D-123)
        ------------------------------------------------------
        Template cũ `event_deep` gộp hop-1 và hop-2 trong **một** truy vấn
        ⇒ Cypher sinh **tích bắc cầu** (`r1 × r2`) ⇒ 1 sự kiện có 12 cạnh
        hop-1 và 59 cạnh hop-2 sinh ra **708 dòng** ⇒ `LIMIT 60` cắt cụt
        còn **4 cạnh hop-1** ⇒ mất **8/10 người chỉ huy** (đo được với
        "Cuộc bao vây thành Quy Nhơn": 10 chỉ huy trong KG, context chỉ còn
        Gia Long + "quận công").

        ⇒ Tách thành 2 truy vấn **độc lập** (`event_deep` = hop-1,
        `event_hop2` = hop-2), mỗi truy vấn có `LIMIT` riêng ⇒ **không cạnh
        nào bị cắt oan**.

        Args:
            intent: Tên ý định (key trong `_INTENT_TEMPLATES`).
            entity_id: Id entity đã link.
            extra: Tham số bổ sung (ví dụ quan hệ cụ thể).

        Returns:
            `GraphContext`.
        """
        started = time.time()
        template = _INTENT_TEMPLATES.get(intent) or _INTENT_TEMPLATES["relational"]
        params: dict[str, Any] = {
            "entity_id": entity_id,
            "limit": self.max_edges,
            "event_relations": EVENT_RELATIONS,
            "context_relations": CONTEXT_RELATIONS,
            "family_relations": FAMILY_RELATIONS,
            "party_relations": PARTY_RELATIONS,
            "any_relations": ALL_RELATIONS,
        }
        if extra:
            params.update(extra)
        records = _run(template["cypher"], params)
        edges = filter_noisy_edges(records)
        edges = _dedupe_edges(edges)[: self.max_edges]
        queries = [template["cypher"].strip()]

        # D-123: ý định `narrative` ⇒ chạy **thêm** truy vấn hop-2 riêng.
        #
        # LƯU Ý (D-123): `fetch()` được gọi với **tên template** (không phải
        # tên ý định) — `hybrid._template_for_intent()` map `"narrative"` →
        # `"event_deep"`. ⇒ Điều kiện phải theo **tên template** (`event_deep`),
        # nếu không nhánh hop-2 **không bao giờ chạy** (lỗi đã gặp).
        if intent in ("event_deep", "narrative"):
            hop2_template = _INTENT_TEMPLATES["event_hop2"]
            hop2_records = _run(hop2_template["cypher"], params)
            if hop2_records:
                hop2_edges = filter_noisy_edges(hop2_records)
                edges = _dedupe_edges(edges + hop2_edges)[: self.max_edges]
                queries.append(hop2_template["cypher"].strip())

            # D-124: bổ sung **các bên liên quan** khi sự kiện thiếu cạnh
            # trực tiếp. Vì sao cần?
            # ---------------------
            # Đo được: 21/60 câu narrative có sự kiện **không** có cạnh
            # hop-1 `chi_huy_tran`/`tham_gia_tran` ⇒ không có "các bên liên
            # quan" nào trong context ⇒ Hybrid không có gì để thêm.
            #
            # ⇒ Truy vấn `event_parties`: mở rộng qua node trung gian là
            # người chỉ huy/bên tham chiến, lấy cạnh sự kiện của họ ở sự
            # kiện **khác** ⇒ biết họ là chỉ huy của ai (bổ sung ngữ cảnh
            # "các bên liên quan") mà **không** thêm cạnh nhiễu "địa điểm →
            # sự kiện khác".
            party_template = _INTENT_TEMPLATES["event_parties"]
            party_records = _run(party_template["cypher"], params)
            if party_records:
                party_edges = filter_noisy_edges(party_records)
                edges = _dedupe_edges(edges + party_edges)[: self.max_edges]
                queries.append(party_template["cypher"].strip())

        # D-118: chuẩn hoá chiều để mốc (entity người hỏi về) luôn là chủ thể.
        edges = normalize_edges(edges, anchor_id=entity_id)

        # D-123: node `Title` có tên là **danh xưng** ⇒ thay bằng tên riêng
        # lấy từ bằng chứng, tránh LLM gán nhầm danh xưng cho mọi chỉ huy.
        # ⇒ Phải chạy **SAU** `normalize_edges`: hàm đó có thể **lật chiều**
        # cạnh (Title là nguồn ⇒ thành đích), nếu sửa tên trước thì tên đã
        # sửa rơi vào `source_name` còn `target_name` vẫn là danh xưng.
        edges = _resolve_title_names(edges)
        entities = self._entities_from_edges(edges)
        return GraphContext(
            entities=entities,
            edges=edges,
            source="intent",
            elapsed_ms=int((time.time() - started) * 1000),
            queries=queries,
        )

    # ------------------------------------------------------------------
    # Chuỗi quan hệ (D-120) — 2-hop theo đúng vai trò
    # ------------------------------------------------------------------

    def fetch_chain(
        self,
        question: str,
        linked: list[tuple[str, str, str]],
        *,
        max_chains: int = 12,
    ) -> GraphContext:
        """Truy vấn **chuỗi quan hệ** (2–3 hop) theo đúng vai trò.

        Vì sao cần?
        -----------
        Câu hỏi loại `multi_hop` là *chuỗi* ("cha của cha X", "vợ của cha Y").
        Truy vấn 1-hop chỉ thấy mắt xích đầu ⇒ LLM trả "không có dữ liệu".
        Đo được: đáp án nằm trong KG **1-hop** 0/40 câu, **2-hop** 40/40.

        Args:
            question: Câu hỏi gốc.
            linked: Entity đã link (`(span, entity_id, name)`).
            max_chains: Số chuỗi tối đa giữ lại.

        Returns:
            `GraphContext` chứa các cạnh của chuỗi đã giải (rỗng nếu câu hỏi
            không phải chuỗi quan hệ).
        """
        from src.qa.relation_chain import (
            ROLE_SPEC,
            build_chain_cypher,
            parse_chain,
            resolve_anchor,
            resolve_chains,
        )

        started = time.time()
        spec = parse_chain(question)
        if spec is None:
            return GraphContext(source="chain", elapsed_ms=0)

        anchor_id, anchor_name = resolve_anchor(spec, linked)
        if not anchor_id:
            return GraphContext(source="chain", elapsed_ms=0)

        hop_roles = spec.hop_roles
        params: dict[str, Any] = {
            "entity_id": anchor_id,
            "limit": self.max_edges * 4,
        }
        for index, role in enumerate(hop_roles, start=1):
            params[f"t{index}"] = list(ROLE_SPEC.get(role, ((),))[0])
        records = _run(build_chain_cypher(len(hop_roles)), params)
        chains = resolve_chains(
            spec, records, anchor_id=anchor_id, anchor_name=anchor_name
        )[:max_chains]
        if not chains:
            return GraphContext(source="chain", elapsed_ms=int(
                (time.time() - started) * 1000
            ))

        # Biến mỗi chuỗi thành **cạnh KG** để tái dùng pipeline fusion +
        # trích dẫn (mỗi bước = 1 cạnh, nhãn = vai trò theo bước đi).
        edges: list[dict[str, Any]] = []
        entities: dict[str, dict[str, Any]] = {}
        for chain in chains:
            # Cạnh tổng hợp: mốc → đáp án cuối. Đặt **trước** các bước để
            # LLM thấy **kết luận** trước khi đọc chi tiết (giảm rủi ro chọn
            # nhầm giữa nhiều chuỗi).
            edges.append(
                {
                    "source_id": anchor_id,
                    "source_name": anchor_name,
                    "relation": "chain_result",
                    "target_id": chain["answer_id"],
                    "target_name": chain["answer"],
                    "confidence": 1.0,
                    "evidence_sentence": chain["statement"],
                    "source_url": chain["source_url"],
                    "method": "chain_2hop",
                    "chain_statement": chain["statement"],
                }
            )
            for step in chain["steps"]:
                relation = f"{step['role']}_hop"
                edges.append(
                    {
                        "source_id": step["subject_id"],
                        "source_name": step["subject_name"],
                        "relation": relation,
                        "target_id": step["answer_id"],
                        "target_name": step["answer_name"],
                        "confidence": 1.0,
                        "evidence_sentence": step["evidence"],
                        "source_url": step["source_url"],
                        "method": "chain_2hop",
                        "chain_statement": chain["statement"],
                    }
                )
                for node_id, node_name in (
                    (step["subject_id"], step["subject_name"]),
                    (step["answer_id"], step["answer_name"]),
                ):
                    if node_id and node_id not in entities:
                        entities[node_id] = {
                            "entity_id": node_id,
                            "name": node_name,
                        }
            if chain["answer_id"] and chain["answer_id"] not in entities:
                entities[chain["answer_id"]] = {
                    "entity_id": chain["answer_id"],
                    "name": chain["answer"],
                }

        edges = _dedupe_edges(edges)[: self.max_edges]
        return GraphContext(
            entities=list(entities.values()),
            edges=edges,
            source="chain",
            elapsed_ms=int((time.time() - started) * 1000),
            queries=[f"chain({len(hop_roles)} hop) anchor={anchor_id}"],
        )

    # ------------------------------------------------------------------
    # Chunk expansion
    # ------------------------------------------------------------------

    def expand_from_entities(
        self,
        entity_ids: list[str],
        *,
        max_entities: int = 12,
        anchor_id: str = "",
        relations: list[str] | None = None,
    ) -> GraphContext:
        """Mở rộng 1-hop từ các entity xuất hiện trong chunk đã truy xuất.

        Đây là cơ chế "link sang các quan hệ khác": câu hỏi tự sự lấy được
        narrative từ văn bản, còn các quan hệ (ai chỉ huy, ở đâu, quân nào
        tham chiến) lấy từ đồ thị.

        Args:
            entity_ids: Danh sách entity_id từ chunk.
            max_entities: Số entity tối đa dùng làm gốc.
            anchor_id: Entity **chính** của câu hỏi (nếu có) ⇒ cạnh nào
                **chạm** anchor được ưu tiên lên đầu (D-121). Lý do: chunk
                truy xuất được có thể chứa nhiều entity không liên quan
                (vd "sinh tại Thanh Hóa" của hàng loạt người) ⇒ nếu không
                ưu tiên, LLM thấy toàn cạnh nhiễu và bỏ qua quan hệ thật.
            relations: Danh sách quan hệ được phép (None ⇒ mọi quan hệ).
                D-123: câu hỏi `narrative` chỉ lấy quan hệ **bối cảnh** —
                loại bỏ quan hệ sinh tử ("sinh tại", "mất tại") vì chúng là
                **nhiễu** cho câu hỏi tự sự (đo được: 27,4 cạnh nhiễu/câu).

        Returns:
            `GraphContext`.
        """
        started = time.time()
        unique: list[str] = []
        for entity_id in entity_ids:
            if entity_id and entity_id not in unique:
                unique.append(entity_id)
            if len(unique) >= max_entities:
                break
        if not unique:
            return GraphContext(source="chunk_expansion", elapsed_ms=0)

        params: dict[str, Any] = {"entity_ids": unique, "limit": self.max_edges}
        relation_filter = ""
        if relations:
            params["relations"] = relations
            relation_filter = "AND type(r) IN $relations"
        records = _run(
            f"""
            MATCH (e)-[r]-(other)
            WHERE e.entity_id IN $entity_ids
              {relation_filter}
            WITH startNode(r) AS s, endNode(r) AS t, r
            RETURN s.entity_id AS source_id,
                   s.name AS source_name,
                   labels(s) AS source_labels,
                   type(r) AS relation,
                   t.entity_id AS target_id,
                   t.name AS target_name,
                   labels(t) AS target_labels,
                   r.confidence AS confidence,
                   r.evidence_sentence AS evidence_sentence,
                   r.source_url AS source_url,
                   r.method AS method
            LIMIT $limit
            """,
            params,
        )
        edges = _dedupe_edges(filter_noisy_edges(records))[: self.max_edges]
        # D-123: sửa tên hiển thị node `Title` (danh xưng ⇒ tên riêng).
        edges = _resolve_title_names(edges)
        # D-121: ưu tiên cạnh **chạm anchor** (entity chính của câu hỏi) lên
        # đầu ⇒ LLM thấy quan hệ thật trước, phần nhiễu sau.
        if anchor_id:
            def _anchor_rank(edge: dict[str, Any]) -> int:
                touches = (
                    edge.get("source_id") == anchor_id
                    or edge.get("target_id") == anchor_id
                )
                return 0 if touches else 1

            edges.sort(key=_anchor_rank)
        entities = self._entities_from_edges(edges)
        return GraphContext(
            entities=entities,
            edges=edges,
            source="chunk_expansion",
            elapsed_ms=int((time.time() - started) * 1000),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entities_from_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Suy ra danh sách node từ cạnh.

        Args:
            edges: Danh sách cạnh.

        Returns:
            Danh sách node (`entity_id`, `name`).
        """
        seen: set[str] = set()
        nodes: list[dict[str, Any]] = []
        for edge in edges:
            for id_key, name_key in (("source_id", "source_name"), ("target_id", "target_name")):
                entity_id = str(edge.get(id_key) or "")
                if not entity_id or entity_id in seen:
                    continue
                seen.add(entity_id)
                nodes.append(
                    {
                        "entity_id": entity_id,
                        "name": str(edge.get(name_key) or entity_id),
                    }
                )
        return nodes


__all__ = [
    "CONTEXT_RELATIONS",
    "EVENT_RELATIONS",
    "FAMILY_RELATIONS",
    "INVERSE_RELATION",
    "EVENT_RELATION_TEMPLATES",
    "RELATION_LABEL",
    "GraphContext",
    "GraphContextBuilder",
]

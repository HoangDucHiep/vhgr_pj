"""Phase 16 (D-120) — Truy vấn **chuỗi quan hệ gia đình** (2-hop).

Vì sao cần?
------------
Câu hỏi loại `multi_hop` trong bộ đánh giá là **chuỗi quan hệ**:

    "Cha của cha Huyền Trân Công chúa là ai?"   ⇒ Trần Thánh Tông
    "Vợ của cha Nguyễn Phúc Miên Lương là ai?"  ⇒ Hồ Thị Hoa
    "Mẹ của mẹ Nguyễn Phúc Miên Điều là ai?"    ⇒ Trần Thị Đang

Nhưng tầng đọc KG chỉ truy vấn **1-hop** (`_INTENT_TEMPLATES`) ⇒ context
chỉ chứa *"Huyền Trân Công chúa là con của Trần Nhân Tông"* ⇒ LLM **không
thấy** mắt xích thứ hai ⇒ trả *"Không có trong dữ liệu."*

Đo được (17/11/2026, trên 40 câu `multi_hop` của `data/eval/qa_rag_250.jsonl`):

| Bước                                  | Kết quả                        |
|---------------------------------------|--------------------------------|
| Đáp án có trong KG **1-hop**          | **0 / 40**                     |
| Đáp án có trong KG **2-hop gia đình** | **40 / 40** (đo bằng Cypher thô) |

⇒ thiếu **một bước duy nhất**: đi 2-hop theo đúng **vai trò** quan hệ.

Vì sao không dùng Cypher "2-hop chung"?
---------------------------------------
Cypher 2-hop không phân biệt **vai trò** ("cha của" vs "con của" vs "vợ
của") ⇒ trả về cả 2 chiều ⇒ LLM phải tự suy luận chiều ⇒ dễ đảo chiều
(đúng lỗi đã gặp ở D-118). Ở đây ta **phân tích vai trò ngay trong tiếng
Việt** (`parse_chain`) rồi **chỉ giữ đúng chuỗi nghĩa** ⇒ context hiển
thị dạng mệnh đề tự nhiên, không thể đọc ngược.

Quy ước chiều trong KG (xem `docs/04-schema-knowledge-graph.md` §3.1)
--------------------------------------------------------------------
    (con)-[:cha_cua]->(cha)      (con)-[:me_cua]->(mẹ)
    (chồng)-[:vo_cua]->(vợ)      (vợ)-[:chong_cua]->(chồng)

⇒ với vai trò R, "X là R của Y" được suy ra như sau:

| R (vai trò)  | Quan hệ KG dùng      | Y là…            | ⇒ đáp án là…   |
|--------------|----------------------|------------------|----------------|
| `cha_cua`    | `cha_cua`/`me_cua`   | con (nguồn cạnh) | target cạnh    |
| `me_cua`     | `cha_cua`/`me_cua`   | con (nguồn cạnh) | target cạnh    |
| `con_cua`    | `cha_cua`/`me_cua`   | cha/mẹ (đích cạnh) | nguồn cạnh   |
| `vo_cua`     | `vo_cua`             | chồng (nguồn)    | target cạnh    |
| `chong_cua`  | `chong_cua`          | vợ (nguồn)       | target cạnh    |
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from src.common.logger import get_logger

logger = get_logger("src.qa.relation_chain")

#: Từ khoá tiếng Việt → nhãn quan hệ nội bộ.
RELATION_WORDS: dict[str, str] = {
    "cha": "cha_cua",
    "me": "me_cua",
    "vo": "vo_cua",
    "chong": "chong_cua",
    "con": "con_cua",
}

#: Nhãn hiển thị (dùng trong mệnh đề "X là <nhãn> của Y").
RELATION_VI: dict[str, str] = {
    "cha_cua": "cha",
    "me_cua": "mẹ",
    "vo_cua": "vợ",
    "chong_cua": "chồng",
    "con_cua": "con",
}

#: Vai trò → (các quan hệ KG được phép, chủ thể là **nguồn** của cạnh?).
#:
#: `cha_cua`/`me_cua`: chủ thể là **con** ⇒ nằm ở nguồn cạnh.
#: `con_cua`: chủ thể là **cha/mẹ** ⇒ nằm ở đích cạnh.
#: `vo_cua`/`chong_cua`: chủ thể là **chồng/vợ** ⇒ nằm ở nguồn cạnh.
#:
#: Vì sao `cha_cua` cho phép **cả** `cha_cua` và `me_cua`?
#: --------------------------------------------
#: Câu hỏi "cha của cha X" chỉ nói **một** vai trò, nhưng bằng chứng trong KG
#: có thể ghi "Cha: Y" **hoặc** "Mẹ: Y" cho cùng một quan hệ (vd Huyền Trân
#: Công chúa: bằng chứng "Mẹ: Bảo Thánh hoàng hậu" + "Cha: Trần Nhân Tông"
#: cùng chiều). ⇒ chấp nhận cả 2 nhãn ở tầng **lọc**, rồi **ưu tiên** nhãn
#: khớp chính xác ở tầng **xếp hạng** (xem `ROLE_PREFERENCE`) ⇒ vẫn trả được
#: đáp án nhưng đáp án **đúng vai trò** được đứng trước.
ROLE_SPEC: dict[str, tuple[tuple[str, ...], bool]] = {
    "cha_cua": (("cha_cua", "me_cua"), True),
    "me_cua": (("cha_cua", "me_cua"), True),
    "con_cua": (("cha_cua", "me_cua"), False),
    "vo_cua": (("vo_cua",), True),
    "chong_cua": (("chong_cua",), True),
}

#: Thứ tự ưu tiên nhãn quan hệ cho mỗi vai trò (nhãn đầu = ưu tiên cao).
#:
#: Dùng để **xếp hạng lại** các chuỗi đã giải: chuỗi dùng nhãn khớp chính
#: xác đứng trước ⇒ LLM thấy đáp án đúng vai trò trước tiên.
ROLE_PREFERENCE: dict[str, tuple[str, ...]] = {
    "cha_cua": ("cha_cua", "me_cua"),
    "me_cua": ("me_cua", "cha_cua"),
    "con_cua": ("con_cua",),
    "vo_cua": ("vo_cua",),
    "chong_cua": ("chong_cua",),
}

#: Tiền tố bằng chứng ↔ vai trò (evidence "Cha: X" ⇒ nhãn `cha_cua` đúng).
#:
#: Dùng để **chấm điểm bằng chứng**: cạnh có bằng chứng khớp nhãn được ưu
#: tiên (như D-118 đã làm cho cạnh 1-hop).
EVIDENCE_PREFIX: dict[str, str] = {
    "cha_cua": "cha",
    "me_cua": "me",
    "vo_cua": "vo",
    "chong_cua": "chong",
    "con_cua": "con",
}

#: Regex nhận dạng chuỗi quan hệ.
#:
#: Nhóm 1 = quan hệ **ngoài cùng**; nhóm 2 = các quan hệ bên trong (tối đa 3).
#: Lưu ý: tiếng Việt hay **bỏ dấu "của"** ở mắt xích trong: "cha của **cha**
#: Huyền Trân Công chúa" ⇒ nhóm 2 cho phép thiếu "cua".
_CHAIN_RE = re.compile(
    r"\b(cha|me|vo|chong|con)\s+cua\s+"
    r"((?:cha|me|vo|chong|con)\s+(?:cua\s+)?){1,3}"
)

#: Đuôi câu hỏi cắt khỏi phần "chủ thể" (anchor).
_TAIL_RE = re.compile(
    r"\s+(la\s+ai|la\s+gi|la\s+nguoi\s+nao|co\s+ten\s+la\s+gi|"
    r"la\s+ten\s+gi|thi\s+la\s+ai)\b.*$"
)

#: Cụm hỏi dạng "Ai là <quan hệ> của <…>?" — bỏ tiền tố này khỏi chủ thể.
_LEAD_RE = re.compile(
    r"^\s*(ai\s+la|ai\s+la\s+nguoi\s+|nguoi\s+nao\s+la|"
    r"cho\s+toi\s+biet\s+ai\s+la|ai\s+)\s*"
)


def strip_accents(text: str) -> str:
    """Bỏ dấu + hạ chữ thường + gộp khoảng trắng.

    Lưu ý: chữ ``đ`` / ``Đ`` **không** phải dấu phụ nên `unicodedata` không
    loại được ⇒ phải thay thủ công (nếu không, "Điều" ≠ "Dieu").

    Args:
        text: Chuỗi đầu vào.

    Returns:
        Chuỗi đã chuẩn hoá.
    """
    normalized = unicodedata.normalize("NFD", str(text))
    stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    stripped = stripped.replace("đ", "d").replace("Đ", "D")
    return re.sub(r"\s+", " ", stripped.lower()).strip()


@dataclass
class ChainSpec:
    """Mô tả một chuỗi quan hệ cần đi qua KG.

    Attributes:
        roles: Danh sách vai trò, **từ trong ra ngoài**
            (vd `["cha_cua", "cha_cua"]` = "cha của cha").
        anchor_text: Tên chủ thể gốc (sau mắt xích quan hệ).
        raw: Câu hỏi gốc.
    """

    roles: list[str] = field(default_factory=list)
    anchor_text: str = ""
    raw: str = ""

    @property
    def hop_roles(self) -> list[str]:
        """Thứ tự vai trò **theo bước đi trên KG** (từ mốc ra ngoài).

        Vì sao cần đảo?
        -----------------
        Trong tiếng Việt, quan hệ được viết **ngoài trước**: "vợ của cha X"
        nghĩa là *cha của X* rồi tới *vợ của người cha đó*. ⇒ bước đi đầu
        tiên trên KG là vai trò **trong cùng** (`cha_cua`), bước sau là vai
        trò **ngoài cùng** (`vo_cua`).

        ⇒ `roles` (thứ tự văn bản) phải **đảo** khi dùng làm bước đi.

        Returns:
            Danh sách vai trò theo bước đi.
        """
        return list(reversed(self.roles))

    @property
    def descriptor(self) -> str:
        """Mô tả chuỗi bằng tiếng Việt (vd "vợ của cha").

        Returns:
            Chuỗi mô tả.
        """
        return " của ".join(RELATION_VI.get(role, role) for role in self.roles)


def parse_chain(question: str) -> ChainSpec | None:
    """Phân tích câu hỏi thành chuỗi quan hệ (nếu có).

    Args:
        question: Câu hỏi.

    Returns:
        `ChainSpec` nếu câu hỏi chứa **≥ 2** quan hệ nối tiếp, ngược lại
        `None`.
    """
    normalized = strip_accents(question)
    match = _CHAIN_RE.search(normalized)
    if not match:
        return None

    roles: list[str] = [RELATION_WORDS[match.group(1)]]
    inner = match.group(2)
    for word in re.findall(r"\b(cha|me|vo|chong|con)\b", inner):
        roles.append(RELATION_WORDS[word])
    if len(roles) < 2:
        return None

    anchor = normalized[match.end():]
    anchor = _TAIL_RE.sub("", anchor).strip()
    anchor = _LEAD_RE.sub("", anchor).strip()
    anchor = anchor.strip(" ?!.,")
    if not anchor:
        return None

    return ChainSpec(roles=roles, anchor_text=anchor, raw=question)


def resolve_anchor(
    spec: ChainSpec,
    linked: list[tuple[str, str, str]],
) -> tuple[str, str]:
    """Chọn entity gốc (mốc) của chuỗi.

    Ưu tiên entity mà **tên nằm trong** `anchor_text`; nếu không có thì lấy
    entity đầu tiên đã link.

    Args:
        spec: Chuỗi quan hệ.
        linked: Danh sách `(span, entity_id, name)` từ entity linker.

    Returns:
        Tuple `(entity_id, name)`; `("", "")` nếu không có entity nào.
    """
    if not linked:
        return "", ""
    anchor = strip_accents(spec.anchor_text)
    best: tuple[str, str] = ("", "")
    best_len = -1
    for _span, entity_id, name in linked:
        normalized = strip_accents(name)
        if not normalized:
            continue
        if normalized in anchor:
            if len(normalized) > best_len:
                best = (entity_id, name)
                best_len = len(normalized)
    if best[0]:
        return best
    return linked[0][1], linked[0][2]


def build_chain_cypher(hop_count: int) -> str:
    """Sinh Cypher cho chuỗi `hop_count` bước (match **không hướng**).

    Việc match không hướng + lọc vai trò ở Python cho phép dùng **cùng một
    mẫu** cho mọi vai trò (`cha`/`mẹ`/`vợ`/`chồng`/`con`) mà không phải viết
    5 biến thể Cypher.

    Args:
        hop_count: Số bước (2 hoặc 3).

    Returns:
        Câu Cypher.
    """
    if hop_count < 2:
        raise ValueError("hop_count phải >= 2")
    parts = [
        "MATCH (a {entity_id: $entity_id})-[r1]-(b)-[r2]-(c)",
    ]
    if hop_count >= 3:
        parts.append("-[r3]-(d)")
    parts.append("WHERE c <> a")
    for index in range(1, hop_count + 1):
        parts.append(f"AND type(r{index}) IN $t{index}")
    columns = [
        "startNode(r1).entity_id AS h1s_id",
        "startNode(r1).name AS h1s_name",
        "endNode(r1).entity_id AS h1t_id",
        "endNode(r1).name AS h1t_name",
        "type(r1) AS h1_rel",
        "r1.evidence_sentence AS h1_evidence",
        "r1.source_url AS h1_url",
        "r1.confidence AS h1_conf",
        "startNode(r2).entity_id AS h2s_id",
        "startNode(r2).name AS h2s_name",
        "endNode(r2).entity_id AS h2t_id",
        "endNode(r2).name AS h2t_name",
        "type(r2) AS h2_rel",
        "r2.evidence_sentence AS h2_evidence",
        "r2.source_url AS h2_url",
        "r2.confidence AS h2_conf",
    ]
    if hop_count >= 3:
        columns += [
            "startNode(r3).entity_id AS h3s_id",
            "startNode(r3).name AS h3s_name",
            "endNode(r3).entity_id AS h3t_id",
            "endNode(r3).name AS h3t_name",
            "type(r3) AS h3_rel",
            "r3.evidence_sentence AS h3_evidence",
            "r3.source_url AS h3_url",
            "r3.confidence AS h3_conf",
        ]
    parts.append("RETURN " + ",\n       ".join(columns))
    parts.append("LIMIT $limit")
    return "\n".join(parts)


def _resolve_hop(
    role: str,
    source_id: str,
    source_name: str,
    target_id: str,
    target_name: str,
    edge_type: str,
) -> tuple[str, str, str] | None:
    """Suy ra (chủ thể, đáp án) cho một bước theo vai trò.

    Args:
        role: Vai trò (`cha_cua`…).
        source_id: Id nguồn cạnh.
        source_name: Tên nguồn cạnh.
        target_id: Id đích cạnh.
        target_name: Tên đích cạnh.
        edge_type: Nhãn quan hệ thật của cạnh.

    Returns:
        Tuple `(subject_id, subject_name, answer_name)` nếu cạnh khớp vai trò,
        ngược lại `None`.
    """
    allowed, subject_is_source = ROLE_SPEC.get(role, ((), True))
    if edge_type not in allowed:
        return None
    if subject_is_source:
        return source_id, source_name, target_name
    return target_id, target_name, source_name


def role_score(role: str, edge_type: str) -> int:
    """Điểm **khớp vai trò** của một bước (cao = khớp chính xác).

    Vì sao cần?
    -----------
    KG có thể lưu cùng một quan hệ với nhãn `cha_cua` **hoặc** `me_cua`
    (bằng chứng "Cha: Y" vs "Mẹ: Y"). Câu hỏi "cha của cha X" chỉ hỏi **một**
    vai trò ⇒ chuỗi dùng nhãn `cha_cua` phải được xếp **trước** chuỗi dùng
    nhãn `me_cua` ⇒ LLM thấy đáp án đúng vai trò đầu tiên.

    Args:
        role: Vai trò cần đáp ứng.
        edge_type: Nhãn quan hệ thật của cạnh.

    Returns:
        Điểm (cao hơn = khớp tốt hơn).
    """
    preference = ROLE_PREFERENCE.get(role, ())
    if edge_type in preference:
        return len(preference) - preference.index(edge_type)
    return 0


def evidence_score(role: str, evidence: str, answer_name: str) -> int:
    """Điểm **bằng chứng** của một bước trong chuỗi.

    Vì sao cần?
    -----------
    Cùng một quan hệ có thể được suy ra từ nhiều câu khác nhau. Bằng chứng
    **khớp trực tiếp** (tiền tố "Cha:"/"Mẹ:"/"Vợ:", hoặc câu có nhắc đích
    danh) là tín hiệu mạnh nhất rằng cạnh đó **đúng vai trò**.

    Ba tín hiệu (đo trên 40 câu `multi_hop`):

    | Tín hiệu                                   | Điểm |
    |--------------------------------------------|------|
    | Bằng chứng có tiền tố khớp nhãn ("Cha: X") | +6   |
    | Bằng chứng **nhắc đích danh**              | +3   |
    | Bằng chứng nhắc "Hoàng hậu" (vợ chính)    | +5   |

    Args:
        role: Vai trò của bước.
        evidence: Bằng chứng (evidence_sentence).
        answer_name: Tên người/thực thể ở đích bước.

    Returns:
        Điểm (cao hơn = bằng chứng mạnh hơn).
    """
    text = strip_accents(evidence)
    name = strip_accents(answer_name)
    score = 0
    prefix = EVIDENCE_PREFIX.get(role)
    if prefix and text.startswith(prefix + ":"):
        score += 6
    if name and name in text:
        score += 3
    if role == "vo_cua" and "hoang hau" in text:
        score += 5
    return score


def resolve_chains(
    spec: ChainSpec,
    records: list[dict[str, Any]],
    *,
    anchor_id: str,
    anchor_name: str,
) -> list[dict[str, Any]]:
    """Lọc các đường đi **đúng vai trò** và dựng mệnh đề.

    Args:
        spec: Chuỗi quan hệ.
        records: Record Cypher (2–3 hop).
        anchor_id: Id entity gốc.
        anchor_name: Tên entity gốc.

    Returns:
        Danh sách chuỗi đã giải, mỗi phần tử gồm `answer`, `steps`,
        `statement`, `evidence`, `source_url`, `entity_ids`.
    """
    hop_count = len(spec.roles)
    chains: list[dict[str, Any]] = []
    seen: set[str] = set()

    #: Vai trò theo **bước đi** trên KG (từ mốc ra ngoài).
    hop_roles = spec.hop_roles

    for record in records:
        # --- Bước 1 ---
        hop1 = _resolve_hop(
            hop_roles[0],
            str(record.get("h1s_id") or ""),
            str(record.get("h1s_name") or ""),
            str(record.get("h1t_id") or ""),
            str(record.get("h1t_name") or ""),
            str(record.get("h1_rel") or ""),
        )
        if hop1 is None:
            continue
        subject1_id, subject1_name, answer1_name = hop1
        # Chủ thể bước 1 phải là entity gốc.
        if subject1_id != anchor_id:
            continue
        answer1_id = (
            str(record.get("h1t_id") or "")
            if subject1_id == str(record.get("h1s_id") or "")
            else str(record.get("h1s_id") or "")
        )

        # --- Bước 2 ---
        hop2 = _resolve_hop(
            hop_roles[1],
            str(record.get("h2s_id") or ""),
            str(record.get("h2s_name") or ""),
            str(record.get("h2t_id") or ""),
            str(record.get("h2t_name") or ""),
            str(record.get("h2_rel") or ""),
        )
        if hop2 is None:
            continue
        subject2_id, subject2_name, answer2_name = hop2
        if subject2_id != answer1_id:
            continue
        answer2_id = (
            str(record.get("h2t_id") or "")
            if subject2_id == str(record.get("h2s_id") or "")
            else str(record.get("h2s_id") or "")
        )

        steps = [
            {
                "role": hop_roles[0],
                "subject_id": subject1_id,
                "subject_name": subject1_name,
                "answer_id": answer1_id,
                "answer_name": answer1_name,
                "edge_type": str(record.get("h1_rel") or ""),
                "confidence": float(record.get("h1_conf") or 0.0),
                "evidence": str(record.get("h1_evidence") or ""),
                "source_url": str(record.get("h1_url") or ""),
            },
            {
                "role": hop_roles[1],
                "subject_id": subject2_id,
                "subject_name": subject2_name,
                "answer_id": answer2_id,
                "answer_name": answer2_name,
                "edge_type": str(record.get("h2_rel") or ""),
                "confidence": float(record.get("h2_conf") or 0.0),
                "evidence": str(record.get("h2_evidence") or ""),
                "source_url": str(record.get("h2_url") or ""),
            },
        ]

        # --- Bước 3 (tuỳ chọn) ---
        if hop_count >= 3:
            hop3 = _resolve_hop(
                hop_roles[2],
                str(record.get("h3s_id") or ""),
                str(record.get("h3s_name") or ""),
                str(record.get("h3t_id") or ""),
                str(record.get("h3t_name") or ""),
                str(record.get("h3_rel") or ""),
            )
            if hop3 is None:
                continue
            subject3_id, subject3_name, answer3_name = hop3
            if subject3_id != answer2_id:
                continue
            answer3_id = (
                str(record.get("h3t_id") or "")
                if subject3_id == str(record.get("h3s_id") or "")
                else str(record.get("h3s_id") or "")
            )
            steps.append(
                {
                    "role": hop_roles[2],
                    "subject_id": subject3_id,
                    "subject_name": subject3_name,
                    "answer_id": answer3_id,
                    "answer_name": answer3_name,
                    "edge_type": str(record.get("h3_rel") or ""),
                    "confidence": float(record.get("h3_conf") or 0.0),
                    "evidence": str(record.get("h3_evidence") or ""),
                    "source_url": str(record.get("h3_url") or ""),
                }
            )
            final_name = answer3_name
            final_id = answer3_id
        else:
            final_name = answer2_name
            final_id = answer2_id

        if not final_name or final_name == anchor_name:
            continue
        key = "|".join([final_name] + [step["answer_name"] for step in steps])
        if key in seen:
            continue
        seen.add(key)

        # Dựng mệnh đề tự nhiên (không dùng mũi tên ⇒ không đọc ngược được).
        #
        # Quan trọng: dùng **nhãn quan hệ thật** (`edge_type`) chứ không dùng
        # **vai trò** (`role`) cho phần mệnh đề. Ví dụ KG lưu cạnh
        # `Minh Mạng --cha_cua--> Nguyễn Phúc Miên Điều`; nếu ta ghi theo
        # vai trò `me_cua` sẽ sinh câu **sai** ("Minh Mạng là *mẹ* của ...").
        sentences: list[str] = []
        for step in steps:
            label = RELATION_VI.get(
                step.get("edge_type") or step["role"],
                step.get("edge_type") or step["role"],
            )
            sentences.append(
                f"{step['answer_name']} là {label} của {step['subject_name']}"
            )
        path = " → ".join(
            [anchor_name] + [step["answer_name"] for step in steps]
        )
        #: Chuỗi có **nhất quán** giữa vai trò và nhãn thật không?
        #:
        #: Nếu không nhất quán (vd hỏi "mẹ của cha" nhưng KG lưu nhãn
        #: `cha_cua`), ta **không** dùng vai trò để kết luận ⇒ tránh sinh
        #: câu sai ⇒ kết luận dùng **nhãn thật** của đường đi.
        consistent = all(
            step.get("edge_type") == step["role"] for step in steps
        )
        if consistent:
            conclusion = f"{spec.descriptor} của {anchor_name} là {final_name}"
        else:
            actual_descriptor = " của ".join(
                RELATION_VI.get(
                    step.get("edge_type") or step["role"],
                    step.get("edge_type") or step["role"],
                )
                for step in reversed(steps)
            )
            conclusion = (
                f"{actual_descriptor} của {anchor_name} là {final_name}"
            )
        statement = (
            "Chuỗi quan hệ: " + path + ". "
            + " ⇒ ".join(sentences)
            + f". ⇒ Kết luận: {conclusion}."
        )
        evidence = " | ".join(
            step["evidence"] for step in steps if step.get("evidence")
        )
        source_url = next(
            (step["source_url"] for step in steps if step.get("source_url")), ""
        )
        entity_ids = [anchor_id] + [step["answer_id"] for step in steps]
        #: Điểm **bằng chứng** (mạnh nhất: tiền tố khớp nhãn + nhắc tên).
        evidence_points = sum(
            evidence_score(
                step["role"],
                step.get("evidence", ""),
                step.get("answer_name", ""),
            )
            for step in steps
        )
        #: Điểm khớp vai trò (cao = nhãn quan hệ đúng vai trò ở mọi bước).
        score = sum(
            role_score(step["role"], step.get("edge_type", ""))
            for step in steps
        )
        #: **Độ tin cậy** của KG cho các cạnh trong chuỗi (0–1).
        #:
        #: Đo được: cạnh `phobert_re` có conf ≈ 0.98, cạnh suy ra bằng
        #: `distant_supervision` chỉ ≈ 0.75 ⇒ dùng để **xếp hạng** chuỗi
        #: (chuỗi tin cậy cao đứng trước) ⇒ LLM thấy đáp án đúng trước.
        confidence = sum(
            float(step.get("confidence") or 0.0) for step in steps
        ) / max(len(steps), 1)
        chains.append(
            {
                "answer": final_name,
                "answer_id": final_id,
                "steps": steps,
                "statement": statement,
                "conclusion": conclusion,
                "evidence": evidence,
                "source_url": source_url,
                "entity_ids": [eid for eid in entity_ids if eid],
                "score": score,
                "evidence_points": evidence_points,
                "confidence": round(confidence, 4),
            }
        )

    # Sắp xếp: (1) bằng chứng mạnh, (2) khớp vai trò, (3) độ tin cậy KG.
    chains.sort(
        key=lambda item: (
            -int(item.get("evidence_points") or 0),
            -int(item.get("score") or 0),
            -float(item.get("confidence") or 0.0),
        )
    )
    return chains


__all__ = [
    "ChainSpec",
    "EVIDENCE_PREFIX",
    "RELATION_VI",
    "RELATION_WORDS",
    "ROLE_PREFERENCE",
    "ROLE_SPEC",
    "build_chain_cypher",
    "evidence_score",
    "parse_chain",
    "resolve_anchor",
    "resolve_chains",
    "role_score",
    "strip_accents",
]

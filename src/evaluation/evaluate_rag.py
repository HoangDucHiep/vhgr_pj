"""Phase 16 — Bước 2: đánh giá so sánh A (Vanilla RAG) vs B (Hybrid GraphRAG).

3 arm (ablation)
----------------
| Arm | Mô tả | Endpoint |
|---|---|---|
| **A** | Vanilla RAG (chỉ văn bản) | `/api/ask/rag` |
| **B** | Hybrid GraphRAG đầy đủ (văn bản + KG) | `/api/ask/hybrid` (`use_graph=True`) |
| **B−** | Hybrid **không** KG (cùng pipeline, tắt kênh đồ thị) | `/api/ask/hybrid` (`use_graph=False`) |

Vì sao cần arm **B−**?
----------------------
Nếu chỉ so sánh A vs B thì chênh lệch có thể do:
- prompt khác nhau ⇒ không biết đóng góp đến từ *đồ thị* hay từ *prompt*.
- pipeline khác nhau ⇒ không biết đóng góp đến từ *fusion* hay từ *retriever*.

B− dùng **cùng** `HybridAnswerer`, **cùng** prompt, **cùng** retriever — chỉ
tắt kênh KG ⇒ **đóng góp đến từ đồ thị** là phần chênh lệch B vs B−.

Chỉ số đo
---------
| Chỉ số | Cách tính | Khoảng |
|---|---|---|
| `correctness` | LLM-judge chấm 0–2 (2 = đúng hoàn toàn) | 0–2 |
| `correctness_rate` | % câu có điểm = 2 | 0–1 |
| `faithfulness` | LLM-judge 0–2 (2 = mọi mệnh đề có căn cứ trong context) | 0–2 |
| `faithfulness_rate` | % câu có điểm 2 | 0–1 |
| `citation_precision` | % trích dẫn `[n]` **thực sự hỗ trợ** câu trả lời (judge) | 0–1 |
| `no_data_accuracy` | % câu `no_data` trả đúng "Không có trong dữ liệu." | 0–1 |
| `latency_p50/p95` | ms | ms |
| `context_tokens` | ước lượng token của context | token |

LLM-judge
---------
Prompt chấm điểm **JSON** (mỗi judge đánh giá 1 câu, 2 lần cho arm A/B để
giảm bias thứ tự). Nếu 2 judge khác nhau (Gemini + Groq) thì lấy trung bình
theo tài liệu kế hoạch.

Output
------
- `reports/eval_rag_<arm>.json` — kết quả chi tiết từng câu
- `reports/eval_rag_<ts>.md` — báo cáo so sánh (markdown)
- `data/eval/eval_rag_<arm>.jsonl` — kết quả thô
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from src.common.config import REPO_ROOT, load_config, resolve_path
from src.common.llm_client import LLMClient
from src.common.logger import get_logger

logger = get_logger("src.evaluation.evaluate_rag")

#: Seed tái lập (thứ tự arm trong prompt judge).
SEED = 42

#: Câu trả lời chuẩn khi không có dữ liệu.
NO_DATA_ANSWER = "Không có trong dữ liệu."

#: Prompt LLM-judge (JSON) — chấm **nhiều arm trong 1 lời gọi**.
#:
#: Vì sao gộp?
#: -----------
#: Quota Gemini free = 500 RPD, Groq = 1.000 RPD. Chấm riêng từng arm thì
#: cần 250 câu × 3 arm = **750 lời gọi judge** ⇒ vượt quota Gemini. Chấm gộp
#: cả 3 arm trong **1 lời gọi/câu** ⇒ 250 lời gọi ⇒ an toàn quota.
#:
#: Cân bằng thứ tự: thứ tự arm được **hoán vị ngẫu nhiên theo qid** để triệt
#: tiêu position bias của judge (mỗi câu có 1 thứ tự cố định ⇒ vẫn tái lập
#: được nhờ seed 42).
JUDGE_PROMPT = """Bạn là giám khảo đánh giá câu trả lời hỏi đáp lịch sử Việt Nam.

## LOẠI CÂU HỎI
{question_type}

## CÂU HỎI
{question}

## ĐÁP ÁN THAM KHẢO (từ Wikidata — nguồn độc lập)
{expected_answer}

> **LƯU Ý QUAN TRỌNG (D-142).** Đáp án tham chiếu ở trên **chỉ là gợi ý**, KHÔNG
> phải chuẩn để đối chiếu tuyệt đối. Nếu **CONTEXT** của phương án **mâu thuẫn**
> với đáp án tham chiếu ⇒ hãy **theo CONTEXT** (đây là lỗi của bộ câu hỏi,
> không phải lỗi của hệ thống) ⇒ đặt `contradicts_reference = true` và **không**
> trừ điểm vì lý do đó. Nếu CONTEXT **không** nói gì về điểm đang hỏi mà đáp án
> tham chiếu lại khẳng định điều đó ⇒ cũng đặt `contradicts_reference = true`.

## CHỦ THỂ CỦA CÂU HỎI (nếu có)
{subject_hint}

## CÁC PHƯƠNG ÁN CẦN CHẤM
{candidates}

## VIỆC CẦN CHẤM (chấm **độc lập** từng phương án)

Với **mỗi** phương án, chấm:

1. **correctness** (0–2): câu trả lời có đúng không?
   - 2 = đúng hoàn toàn (đáp án chính xác, đầy đủ)
   - 1 = đúng một phần (thiếu chi tiết, có chỗ mơ hồ, nhưng không sai)
   - 0 = sai hoặc không trả lời được câu hỏi
   Nếu `expected_answer` là "Không có trong dữ liệu." thì chấm 2 khi câu trả lời
   nói không có dữ liệu, 0 nếu câu trả lời bịa.
   Nếu loại câu hỏi là `narrative` (expected_answer là một đoạn văn tham chiếu
   trích từ Wikipedia) ⇒ chấm theo **mức độ bao phủ các mốc sự kiện chính**
   có trong đoạn tham chiếu, không đòi hỏi trùng văn bản.
   Nếu loại câu hỏi là `multi_turn` ⇒ câu hỏi là lượt tiếp theo trong hội thoại,
   dùng đại từ; hãy hiểu đại từ theo lượt trước trong CONTEXT (nếu có).
   Nếu mục "CHỦ THỂ CỦA CÂU HỎI" có nêu tên ⇒ đó **chính là** đối tượng mà
   đại từ ("ông ấy", "vị ấy"…) chỉ tới ⇒ hãy dùng tên đó để đánh giá, và
   **không** coi câu trả lời là "tự suy diễn" khi nó nêu đúng tên đó.

2. **faithfulness** (0–2): mọi mệnh đề trong câu trả lời có được CONTEXT hỗ trợ?
   - 2 = tất cả mệnh đề đều có căn cứ trong CONTEXT
   - 1 = phần lớn có căn cứ, có 1–2 mệnh đề không có
   - 0 = phần lớn là bịa hoặc suy diễn ngoài CONTEXT

3. **citation_precision** (0–1): trong các trích dẫn `[n]` có trong câu trả lời,
   bao nhiêu phần trỏ tới đoạn CONTEXT **thực sự hỗ trợ** nội dung câu trả lời?
   (0 = không có trích dẫn nào hỗ trợ; 1 = tất cả đều hỗ trợ)

4. **contradicts_reference** (true/false): phương án có **mâu thuẫn** với đáp án
   tham chiếu không? (true = có mâu thuẫn rõ ràng; false = không mâu thuẫn hoặc
   không đủ căn cứ để kết luận). Trường này **chỉ để đánh dấu**, KHÔNG dùng
   để trừ điểm.

Trả về DUY NHẤT JSON hợp lệ, không markdown, đúng cấu trúc sau (một entry cho
mỗi phương án, giữ nguyên đúng tên phương án):
{{"scores": [{{"arm": "<tên phương án>", "correctness": <0|1|2>, "faithfulness": <0|1|2>, "citation_precision": <0.0-1.0>, "contradicts_reference": <true|false>, "reason": "<tóm tắt ngắn, tiếng Việt>"}}]}}

QUY TẮC BẮT BUỘC:
- Phải có **đúng 1 entry cho MỖI phương án** được nêu trong phần "CÁC PHƯƠNG ÁN CẦN CHẤM".
- `reason` **tối đa 15 từ**, không lặp lại nội dung đáp án.
- Không thêm entry nào ngoài danh sách phương án.

## CÁCH ĐỌC PHẦN "DỮ LIỆU ĐỒ THỊ" TRONG CONTEXT (D-138/D-139)

Nếu CONTEXT của phương án có phần `### DỮ LIỆU ĐỒ THỊ (Knowledge Graph)`,
các dòng cạnh có **2 dạng**:

**(a) Mệnh đề tự nhiên** (không thể đọc ngược):

    [n] Ngô Văn Sở là người chỉ huy Trận Hà Hồi
    ⇒ Ngô Văn Sở **là người chỉ huy** Trận Hà Hồi.

    [n] Nhà Thanh là bên tham chiến trong Trận Hà Hồi
    ⇒ Nhà Thanh **là bên tham chiến** trong Trận Hà Hồi.

**(b) Dạng mũi tên** ``[n] A — quan hệ → B`` (quan hệ ghi theo
**chủ thể → đối tượng**) ⇒ đọc là: **"B là quan hệ của A"**:

    [n] Trận Hà Hồi — chỉ huy trận → Ngô Văn Sở
    ⇒ "**Ngô Văn Sở** là người **chỉ huy trận** Hà Hồi."

    [n] Trận Hà Hồi — diễn ra tại → Hà Tây (tỉnh)
    ⇒ "Trận Hà Hồi **diễn ra tại** Hà Tây (tỉnh)."

Dòng "Bằng chứng" là câu gốc từ Wikipedia và là nguồn **chính xác nhất**:
khi nhãn quan hệ và bằng chứng có vẻ khác nhau ⇒ hãy tin **bằng chứng**.

⇒ TUYỆT ĐỐI **KHÔNG** kết luận "thông tin về chỉ huy không có trong ngữ cảnh"
chỉ vì bạn đọc hướng ngược. Hãy kiểm tra lại theo quy ước trên, và coi phần
đồ thị là **nguồn hợp lệ** cho thông tin quan hệ (người chỉ huy, bên tham
chiến, địa điểm) — đó là điểm khác biệt của phương án dùng đồ thị.
"""

#: Mô tả loại câu hỏi cho judge.
QUESTION_TYPE_LABELS: dict[str, str] = {
    "relational": "quan hệ (cha/mẹ/vợ, năm sinh/mất, nơi sinh/mất) — đáp án là tên hoặc năm",
    "narrative": "tự sự (diễn biến sự kiện) — đáp án tham chiếu là đoạn văn từ Wikipedia",
    "multi_hop": "2 bước (cha của cha, vợ của cha...) — cần nối 2 quan hệ",
    "no_data": "ngoài phạm vi dữ liệu — đáp án đúng là 'Không có trong dữ liệu.'",
    "multi_turn": "hội thoại nhiều lượt — câu hỏi dùng đại từ tham chiếu lượt trước",
}


# ----------------------------------------------------------------------
# Helper
# ----------------------------------------------------------------------


def is_no_data(answer: str) -> bool:
    """Kiểm tra câu trả lời có phải "không có trong dữ liệu" không.

    Args:
        answer: Câu trả lời.

    Returns:
        ``True`` nếu là câu không có dữ liệu.
    """
    text = (answer or "").strip().strip('"“”').strip().rstrip(".!").strip()
    return text.casefold() == NO_DATA_ANSWER.casefold().rstrip(".").strip()


def context_has_gold(
    blocks: Iterable[dict[str, Any]] | None,
    evidence_doc_ids: Iterable[str] | None,
    evidence_section: str | None,
    context_text: str | None = None,
    expected_answer: str | None = None,
) -> bool:
    """Kiểm tra context của arm có chứa **bằng chứng** (gold) không.

    Vì sao cần?
    ----------
    Lỗi "không có trong dữ liệu" chỉ là **lỗi** khi context **có** dữ liệu
    liên quan. Nếu context rỗng ⇒ "không có" là **đúng** ⇒ không tính lỗi.
    ⇒ Metric `abstain_with_evidence` = số câu arm nói "không có" **dù context
    có bằng chứng** ⇒ đây chính là lỗi cần đưa về **0** (Gate G19-1).

    ⚠️ Phase 19 — **không** được chỉ kiểm tra `doc_id` khớp.
    Lý do? Với câu hỏi `relational` (vd. "Gioan Baotixita Nguyễn Thần Đồng mất
    năm nào?"), context có **đúng bài** nhưng các chunk lấy về lại nằm ở
    section **khác** ("Bị bắt và đày ra Côn Đảo") ⇒ **không** có câu trả lời
    ⇒ "không có trong dữ liệu" là **đúng** ⇒ đếm là lỗi là **sai**.
    ⇒ Với câu hỏi **quan hệ/năm** (đáp án là **tên** hoặc **năm**), phải kiểm
    tra thêm: **đáp án có thật sự xuất hiện trong context** không.

    Args:
        blocks: Danh sách khối context (mỗi khối có `doc_id`, `section`).
        evidence_doc_ids: Danh sách `doc_id` là bằng chứng.
        evidence_section: Tên section là bằng chứng (có thể rỗng).
        context_text: Toàn văn context (dùng để kiểm tra đáp án có trong đó).
        expected_answer: Đáp án tham chiếu (tên hoặc năm).

    Returns:
        ``True`` nếu context có bằng chứng **thực sự** chứa đáp án.
    """
    items = list(blocks or [])
    if not items:
        return False
    doc_ids = {str(d) for d in (evidence_doc_ids or []) if str(d)}
    if not doc_ids:
        # Không rõ bằng chứng ⇒ coi như context có dữ liệu (thiên về phát
        # hiện lỗi hơn là bỏ sót lỗi).
        return True
    section = (evidence_section or "").strip()
    matched_doc = False
    for block in items:
        if str(block.get("doc_id") or "") not in doc_ids:
            continue
        matched_doc = True
        if not section:
            break
        path = str(block.get("section") or "")
        parts = [p.strip() for p in path.split(">") if p.strip()]
        if section in parts or path == section:
            break
    else:
        matched_doc = False
    if not matched_doc:
        return False

    # --- Kiểm tra thêm: đáp án (tên/năm) có **trong context** không? --------
    answer = str(expected_answer or "").strip()
    haystack = str(context_text or "")
    if answer and haystack:
        years = _extract_years(answer)
        if years:
            # Câu hỏi về **năm** ⇒ năm phải xuất hiện trong context.
            return all(year in haystack for year in years)
        # Câu hỏi về **tên** ⇒ kiểm tra tên có trong context không
        # (bỏ qua ngoặc/vế sau như "Lê Tuân (An vương)").
        for token in _answer_tokens(answer):
            if token and token.casefold() in haystack.casefold():
                return True
        return False
    return True


def _extract_years(text: str) -> list[str]:
    """Trích các **năm** (4 chữ số 1000–2099) trong chuỗi.

    Args:
        text: Chuỗi cần quét.

    Returns:
        Danh sách năm (chuỗi), theo thứ tự xuất hiện, bỏ trùng.
    """
    return list(dict.fromkeys(re.findall(r"(?<![\d,])((?:1[0-9]|20[0-9])\d{2})(?![\d,])", text or "")))


def _answer_tokens(answer: str) -> list[str]:
    """Tách đáp án tham chiếu thành các **tên** để đối chiếu với context.

    Args:
        answer: Đáp án tham chiếu (vd. "Lê Tuân (An vương)").

    Returns:
        Danh sách token (phần trước dấu ngoặc, và các tên trong ngoặc).
    """
    base = answer.split("(")[0].strip()
    tokens = [base] if base else []
    inner = re.findall(r"\(([^)]*)\)", answer)
    tokens.extend(part.strip() for part in inner)
    return [token for token in tokens if len(token) >= 2]


def estimate_tokens(text: str) -> int:
    """Ước lượng số token (tiếng Việt ≈ 3 ký tự / token).

    Args:
        text: Chuỗi.

    Returns:
        Số token ước lượng.
    """
    return max(1, len(text or "") // 3)


def compact_context(
    context: str,
    *,
    per_block: int = 600,
    total: int = 9000,
    keep_indices: Iterable[int] | None = None,
) -> str:
    """Nén context trước khi đưa cho judge.

    Mỗi khối `[n] ...` bị cắt còn `per_block` ký tự ⇒ judge thấy đủ "nội dung
    khối đó nói gì" mà không bị tràn context. Quan trọng: phải giữ **mọi** số
    `[n]` trong khối vì đó là không gian trích dẫn dùng chung cho text + KG.

    Vì sao `total` = 9.000 (D-124)?
    ---------------------------
    Judge nhận **3 arm** trong **một** lời gọi ⇒ prompt = 3 × context + phần
    đáp án tham khảo. Với `total = 16.000` ⇒ prompt vượt **7.000 token/phút**
    (ITPM) của Groq ⇒ Groq trả lỗi **413** ⇒ judge **hỏng** ⇒ câu bị hoãn.
    Đo được: prompt 3 arm ≈ 10.456 ký tự ≈ 3.485 token vượt trần ITPM của
    Groq cho model `qwen/qwen3.8-27b` (7.000 token/phút).

    ⇒ Hạ trần mỗi arm còn 9.000 ký tự ⇒ tổng ≈ 27.000 ký tự ≈ 9.000 token —
    vẫn **vừa** cho Gemini (context rất lớn) và **vừa** cho Groq.

    D-132: **giữ phần KG** (không cắt mất).
    -------------------------------------
    Vì sao cần?
    ----------
    Context của arm B gồm 2 phần: `### VĂN BẢN TỪ WIKIPEDIA` rồi tới
    `### DỮ LIỆU ĐỒ THỊ (Knowledge Graph)`. Cắt theo thứ tự ⇒ khi trần
    `total` bị đạt ở giữa phần văn bản ⇒ **toàn bộ phần KG bị mất** ⇒
    judge **không nhìn thấy** thông tin KG của arm B ⇒ phép so sánh **lệch
    có lợi cho arm A** (đo được: ở `total = 2.200`, **35/37** câu có KG bị
    mất phần KG; ở `total = 9.000` còn **8/37**).

    ⇒ Cắt **phần văn bản** trước (nó có dự phòng), **luôn giữ** phần KG.

    D-138: **giữ luôn các khối mà câu trả lời đã trích dẫn**.
    ---------------------------------------------
    Vì sao cần?
    ----------
    Câu trả lời trích dẫn `[n]`. Nếu `compact_context()` cắt bỏ khối `[n]` đó
    ⇒ judge thấy trích dẫn **không tồn tại** ⇒ trừ `citation_precision` về 0
    ⇒ **điểm giảm ở arm B** (arm B có context dài nhất ⇒ hay bị cắt nhất).
    Đo được (D-124): **7/60** câu arm B trích dẫn khối đã bị cắt
    (q0081 [27], q0087 [28], q0089 [13,15], q0095 [15], q0099 [15],
    q0108 [13], q0113 [13]).

    ⇒ `keep_indices` cho phép giữ **bắt buộc** những khối đã được trích dẫn.

    Args:
        context: Context đầy đủ.
        per_block: Số ký tự tối đa cho mỗi khối.
        total: Tổng ký tự tối đa.
        keep_indices: Số thứ tự khối `[n]` **phải** giữ (dù đã trích dẫn).

    Returns:
        Context đã nén.
    """
    if not context:
        return ""
    # D-132: tách phần **KG** (giữ **nguyên vẹn**) khỏi phần **văn bản**
    # (được cắt trước) ⇒ judge luôn nhìn thấy cạnh KG của arm B.
    kg_marker = "### DỮ LIỆU ĐỒ THỊ"
    head, sep, kg_part = context.partition(kg_marker)
    if not sep:
        head, kg_part = context, ""

    keep = {int(i) for i in (keep_indices or ())}

    def _block_index(block: str) -> int | None:
        """Trích số thứ tự khối `[n]` từ đầu khối (None nếu không phải khối)."""
        match = re.match(r"\[(\d+)\]", block.strip())
        return int(match.group(1)) if match else None

    def _pieces(source: str) -> list[tuple[str, bool]]:
        """Tách `source` thành các khối `[n]`, kèm cờ "đã được trích dẫn"."""
        blocks = re.split(r"(?m)^(?=\[\d+\]\s)", source)
        out: list[tuple[str, bool]] = []
        for block in blocks:
            if not block.strip():
                continue
            block_head = block.split("\n", 1)[0]
            body = block[len(block_head):].strip()
            if len(body) > per_block:
                body = body[:per_block].rsplit(" ", 1)[0] + " …"
            piece = f"{block_head}\n{body}" if body else block_head
            index = _block_index(block)
            out.append((piece, index is not None and index in keep))
        return out

    def _assemble(
        text_pieces: list[tuple[str, bool]],
        kg_pieces: list[tuple[str, bool]],
    ) -> str:
        """Ghép 2 phần với ngân sách, **ưu tiên giữ khối đã trích dẫn**.

        Thứ tự ưu tiên (D-138):
        1. Khối **đã được trích dẫn** (bắt buộc) — kể cả khi vượt ngân sách.
        2. Phần **KG** (có giá trị bổ sung, không có dự phòng).
        3. Phần **văn bản** (có dự phòng trong Wikipedia ⇒ cắt được).
        """
        marker_len = len(kg_marker) + 2 if kg_pieces else 0
        forced = [p for p, is_keep in text_pieces + kg_pieces if is_keep]
        forced_len = sum(len(p) + 2 for p in forced)
        remaining = max(0, total - marker_len - forced_len)

        # Phần KG trước (giá trị cao hơn văn bản).
        kg_kept: list[str] = []
        used = 0
        for piece, is_keep in kg_pieces:
            if is_keep:
                kg_kept.append(piece)
                continue
            if used + len(piece) + 2 > remaining:
                continue
            kg_kept.append(piece)
            used += len(piece) + 2

        # Phần văn bản với phần ngân sách còn lại.
        text_kept: list[str] = []
        used_text = 0
        for piece, is_keep in text_pieces:
            if is_keep:
                text_kept.append(piece)
                continue
            if used_text + len(piece) + 2 > remaining - used:
                continue
            text_kept.append(piece)
            used_text += len(piece) + 2

        parts: list[str] = []
        if text_kept:
            parts.append("\n\n".join(text_kept))
        if kg_kept:
            parts.append(kg_marker + "\n\n".join(kg_kept))
        return "\n\n".join(parts)

    text_pieces = _pieces(head)
    kg_pieces = _pieces(kg_part) if kg_part else []
    result = _assemble(text_pieces, kg_pieces)
    # Trường hợp hiếm: phần KG một mình đã vượt trần ⇒ cắt đuôi.
    if len(result) > total:
        result = result[:total].rsplit("\n\n", 1)[0]
    return result


def build_client(provider: str, *, model: str | None = None) -> LLMClient:
    """Dựng `LLMClient` với provider ưu tiên chỉ định.

    Mục đích: tách quota — **sinh câu trả lời** dùng Groq (1.000 RPD) vì
    có 750 lời gọi; **LLM-judge** dùng Gemini (500 RPD) vì chỉ 250 lời gọi.

    Args:
        provider: Tên provider (`gemini` | `groq`).
        model: Ghi đè model của provider (dùng khi chia tải quota nhiều model).

    Returns:
        `LLMClient` đã cấu hình.
    """
    llm_config = load_config(REPO_ROOT / "configs" / "llm.yaml")
    config = dict(llm_config)
    config["primary"] = provider
    fallback = [p for p in (llm_config.get("fallback_order") or []) if p != provider]
    config["fallback_order"] = fallback
    if model:
        providers = dict(config.get("providers") or {})
        spec = dict(providers.get(provider) or {})
        spec["model"] = model
        providers[provider] = spec
        config["providers"] = providers
    return LLMClient.from_config(config)


#: Tiền tố model Gemini **thinking** (có phần suy nghĩ ẩn) — D-126.
#:
#: Vì sao cần?
#: ----------
#: Model thinking **tiêu ngân sách output token** cho suy nghĩ ⇒ với
#: `max_output_tokens=900` (mặc định của `rag_answer`/`hybrid`) phần còn lại
#: cho câu trả lời **không đủ** ⇒ model trả về **chuỗi rỗng** ⇒
#: `rag_answer` quy về `not_in_data` ⇒ **sai số liệu** (đo được 18/11/2026:
#: `gemini-4-hydrogen` trả rỗng với `max_output_tokens=900`).
#:
#: ⇒ Tách ngân sách: `thinking_budget` (suy nghĩ) + `max_tokens` (trả lời).
THINKING_MODEL_PREFIXES: tuple[str, ...] = ("gemini-4-",)


def _is_thinking_model(model: str) -> bool:
    """Kiểm tra model Gemini có **suy nghĩ** (thinking) hay không.

    Args:
        model: Tên model.

    Returns:
        ``True`` nếu model cần ngân sách token riêng cho suy nghĩ.
    """
    name = (model or "").strip().lower()
    return any(name.startswith(prefix) for prefix in THINKING_MODEL_PREFIXES)


def build_client_pool(
    provider: str,
    models: list[str],
    *,
    requests_per_day: int | None = None,
) -> list[LLMClient]:
    """Dựng pool client, mỗi client một model (chia tải quota).

    Quota free tier của Gemini là **theo từng model** (15 RPM/model, RPD
    riêng), nên chạy nhiều model song song tăng thông lượng gấp N lần.

    Mỗi client trong pool có `max_retries=0` và **không** có provider dự phòng
    ⇒ khi một model hết quota, lỗi trả về ngay để `PooledLLM` thử model kế
    tiếp (thay vì retry 3 lần trên model đã hết quota rồi mới chuyển).

    Args:
        provider: Tên provider (`gemini` | `groq`).
        models: Danh sách model.
        requests_per_day: Ghi đè RPD của provider (mặc định lấy từ config).

    Returns:
        Danh sách `LLMClient` (rỗng nếu `models` rỗng).
    """
    llm_config = load_config(REPO_ROOT / "configs" / "llm.yaml")
    base = dict(llm_config)
    base["primary"] = provider
    base["fallback_order"] = []
    clients: list[LLMClient] = []
    for model in models:
        config = dict(base)
        providers = dict(config.get("providers") or {})
        spec = dict(providers.get(provider) or {})
        spec["model"] = model
        spec["max_retries"] = 0
        if requests_per_day is not None:
            spec["requests_per_day"] = requests_per_day
        # D-126: model Gemini **thinking** (vd `gemini-4-hydrogen`) cần ngân
        # sách token riêng cho suy nghĩ ⇒ nếu không, `max_output_tokens=900`
        # bị hết ⇒ model trả về câu trả lời **rỗng** ⇒ quy về `not_in_data`.
        # ⇒ Tự nhận diện theo tên model ⇒ không cần khai báo thủ công.
        if provider == "gemini" and _is_thinking_model(model):
            spec["thinking"] = True
            # D-126: đo được — `900` ⇒ rỗng (`MAX_TOKENS`); `4096` ⇒ 702 ký tự
            # ⇒ cần **cộng thêm** ngân sách suy nghĩ vào `max_tokens`.
            spec["thinking_budget"] = int(spec.get("thinking_budget") or 3200)
        providers[provider] = spec
        config["providers"] = providers
        clients.append(LLMClient.from_config(config))
    return clients


def build_cross_provider_pool(
    provider_models: list[tuple[str, list[str]]],
    *,
    requests_per_day: int | None = None,
) -> list[LLMClient]:
    """Dựng pool **đa provider** (Gemini + Groq) từ danh sách (provider, models).

    Vì sao cần?
    -----------
    Quota free tier **cả hai** provider đều hữu hạn theo ngày:
    - Gemini: 500 RPD **riêng theo model** ⇒ pool nhiều model vẫn đủ, nhưng
      mỗi model chỉ 500 RPD.
    - Groq: **TPD 200.000 token** cho `openai/gpt-oss-20b` (và tương tự cho
      model khác) ⇒ sinh câu trả lời dài sẽ vỡ quota giữa chừng.

    ⇒ Gộp **cả hai** provider vào một pool ⇒ khi Gemini cạn, lời gọi tự
    chuyển sang Groq (và ngược lại). Đây là cơ chế duy nhất chịu được
    741 lời gọi sinh + 247 lời gọi judge trong 1 ngày free tier.

    Args:
        provider_models: Danh sách cặp `(provider, [model, ...])`.
        requests_per_day: Ghi đè RPD cho mọi provider (mặc định lấy config).

    Returns:
        Danh sách `LLMClient`.
    """
    clients: list[LLMClient] = []
    for provider, models in provider_models:
        if not models:
            continue
        clients.extend(
            build_client_pool(provider, models, requests_per_day=requests_per_day)
        )
    return clients


class PooledLLM:
    """Router gọi LLM qua **pool nhiều model**, chia tải round-robin.

    Nếu một model lỗi (429/quota), router thử model tiếp theo ⇒ không mất câu
    nào chỉ vì hết quota của một model.

    Attributes:
        clients: Danh sách client (mỗi client một model).
        index: Con trỏ round-robin.
        errors: Đếm lỗi theo model.
    """

    def __init__(
        self,
        clients: list[LLMClient],
        *,
        quota_cooldown_s: float = 900.0,
        max_quota_wait_s: float = 0.0,
        max_cooldown_s: float = 900.0,
        rpd_threshold_s: float = 1800.0,
        rpm_min_cooldown_s: float = 60.0,
    ) -> None:
        """Khởi tạo.

        Args:
            clients: Danh sách client.
            quota_cooldown_s: Thời gian **loại tạm** một model sau khi gặp
                lỗi quota (429). Mục đích: không spam lời gọi vào model đã
                hết quota ⇒ mỗi lời gọi lãng phí thêm 1 request (Google
                tính cả request bị từ chối vào quota).
            max_quota_wait_s: Tổng thời gian tối đa được **chờ** để quota
                hồi lại trong một lần gọi (giây). ``0`` ⇒ không chờ, ném
                lỗi ngay.
            max_cooldown_s: Trần **tối đa** cho thời gian loại tạm một
                model sau lỗi quota (giây). Provider có thể báo mốc reset
                rất xa (vd Gemini "5h14m") ⇒ không nên loại model khỏi pool
                lâu như vậy (nó có thể hồi sớm hơn, và mỗi phút thử lại vẫn
                rẻ hơn là bỏ câu).
            rpd_threshold_s: D-130 — ngưỡng phân biệt **RPD** (hạn mức
                ngày) với **RPM** (hạn mức phút). Mốc reset do provider báo
                **≥** ngưỡng này ⇒ coi là RPD ⇒ tin mốc reset dài hạn.
                Ngắn hơn ⇒ RPM ⇒ chỉ loại tạm thời gian ngắn.
            rpm_min_cooldown_s: D-130 — thời gian loại tạm **tối thiểu** khi
                lỗi là RPM (giây). Đo được 18/11/2026: quota Gemini hồi sau
                ~40–60 giây ⇒ 60 giây là mốc hợp lý để thử lại.
        """
        self.clients = clients
        self.index = 0
        self.errors: dict[str, int] = {}
        self.quota_cooldown_s = quota_cooldown_s
        #: Tổng thời gian tối đa được **chờ** để quota hồi lại trong 1 lần
        #: gọi (giây). ``0`` ⇒ không chờ, ném lỗi ngay.
        self.max_quota_wait_s = max(0.0, float(max_quota_wait_s))
        #: Trần thời gian loại tạm một model sau lỗi quota (giây).
        self.max_cooldown_s = max(1.0, float(max_cooldown_s))
        #: D-130: ngưỡng phân biệt RPD (ngày) với RPM (phút).
        self.rpd_threshold_s = max(1.0, float(rpd_threshold_s))
        #: D-130: cooldown tối thiểu cho lỗi RPM.
        self.rpm_min_cooldown_s = max(1.0, float(rpm_min_cooldown_s))
        #: Thứ tự **ưu tiên provider** khi chọn model (ví dụ: ``("groq",
        #: "gemini")`` ⇒ ưu tiên Groq trước Gemini). Vì sao: quota free tier
        #: mỗi provider hữu hạn theo **thang đo khác nhau** — Groq giới hạn
        #: theo **token/ngày** (TPD), Gemini giới hạn theo **request/ngày**
        #: (RPD). ⇒ Đặt provider **token-heavy** (sinh câu trả lời dài) ở
        #: vị trí ưu tiên cao, provider **request-heavy** (judge gọn) ở vị trí
        #: thấp. Nếu không, phép sắp xếp theo tên sẽ luôn xếp
        #: ``gemini/...`` trước ``groq/...`` ⇒ sinh câu trả lời cũng đi qua
        #: Gemini ⇒ đốt nhanh hạn mức 500 RPD/model mà judge cũng cần dùng.
        self.provider_priority: tuple[str, ...] = ()
        #: Tổng số giây đã chờ vì hết quota (ghi vào báo cáo).
        self.quota_wait_total_s = 0.0
        #: Model → mốc thời gian hết cooldown.
        self._cooldown_until: dict[str, float] = {}
        #: Model đang được **ghim** (ép dùng) — dùng để đảm bảo cả 3 arm của
        #: cùng một câu được sinh bởi **cùng một model** (tránh confound).
        self._pinned_key: str | None = None
        #: Ghim **cứng**: model ghim lỗi quota ⇒ ném lỗi thay vì đổi model.
        self._strict_pin = False
        #: Thống kê số lời gọi theo model (để ghi vào báo cáo).
        self.calls_by_model: dict[str, int] = {}
        #: Model **thực sự** đã phục vụ lời gọi gần nhất (dùng để ghi
        #: `gen_model` chính xác cho từng arm ⇒ kiểm chứng "ghim model").
        self.last_model: str = ""

    def keys(self) -> list[str]:
        """Danh sách khóa model trong pool.

        Returns:
            Danh sách `provider/model`.
        """
        return [self._model_key(client) for client in self.clients]

    def pin(self, key: str | None) -> None:
        """Ghim (ép) một model cho các lời gọi tiếp theo.

        Args:
            key: Khóa `provider/model`, hoặc ``None`` để bỏ ghim.
        """
        self._pinned_key = key

    def pin_strict(self, key: str | None) -> None:
        """Ghim **cứng**: nếu model ghim lỗi quota ⇒ **không** chuyển sang
        model khác mà ném lỗi ngay.

        Vì sao: nếu model ghim hết quota **giữa lúc** arm đang chạy ⇒ arm đó
        sẽ được sinh bởi model khác ⇒ 3 arm dùng **khác model** ⇒ confound
        ⇒ câu đó phải bị loại. Fail-fast + retry **toàn bộ câu** rẻ hơn nhiều
        so với loại bỏ câu.

        Args:
            key: Khóa `provider/model`, hoặc ``None` để bỏ ghim.
        """
        self._pinned_key = key
        self._strict_pin = True

    def unpin(self) -> None:
        """Bỏ ghim (quay lại round-robin) và tắt chế độ ghim cứng."""
        self._pinned_key = None
        self._strict_pin = False

    def cooldown_keys(self) -> list[str]:
        """Danh sách model đang trong thời gian cooldown (hết quota).

        Returns:
            Danh sách khóa model.
        """
        now = time.time()
        return [
            key for key, until in self._cooldown_until.items() if until > now
        ]

    def healthy_keys(self) -> list[str]:
        """Danh sách model **còn dùng được** (ưu tiên ghim).

        Vì sao: khi quota free tier cạn, lời gọi tới model đó thất bại
        (429) nhưng **vẫn còn trong pool** ⇒ nếu ghim phải chọn model đó thì
        câu đó sẽ lỗi hoặc lệch model. ⇒ Ưu tiên model **chưa hết cooldown**.

        Lưu ý: quota **có hồi lại** (Gemini reset 8h sáng, Groq TPD theo
        chu kỳ) ⇒ một model đã lỗi trước đó vẫn dùng được lại ⇒ **không**
        loại vĩnh viễn, chỉ xếp hạng thấp hơn.

        Returns:
            Danh sách khóa model ưu tiên (có thể rỗng).
        """
        cooldown = set(self.cooldown_keys())
        # **Sắp xếp theo tên** ⇒ thứ tự ổn định giữa các vòng `--resume`.
        # Vì sao: danh sách "còn dùng được" phụ thuộc trạng thái quota ⇒ đổi
        # giữa các vòng ⇒ nếu chọn model theo thứ tự này thì cùng 1 câu có
        # thể đổi model ⇒ **mất LLM cache hit** ⇒ tốn token Groq lần nữa.
        fresh = [
            key
            for key in self.keys()
            if key not in cooldown and self.errors.get(key, 0) == 0
        ]
        recovered = [
            key
            for key in self.keys()
            if key not in cooldown and self.errors.get(key, 0) > 0
        ]
        return sorted(fresh, key=self._sort_key) + sorted(recovered, key=self._sort_key)

    def _sort_key(self, key: str) -> tuple[int, str]:
        """Khóa sắp xếp ổn định: ưu tiên provider trước, rồi theo tên model.

        Args:
            key: Khóa ``provider/model``.

        Returns:
            Tuple ``(ưu tiên provider, tên model)``.
        """
        provider = key.split("/", 1)[0]
        try:
            rank = self.provider_priority.index(provider)
        except ValueError:
            rank = len(self.provider_priority)
        return (rank, key)

    def preferred_group(self, available: list[str]) -> list[str]:
        """Lọc ra các model thuộc provider **ưu tiên cao nhất** còn dùng được.

        Vì sao cần?
        -----------
        Nếu chỉ sắp xếp theo ưu tiên provider rồi chọn **ngẫu nhiên trên
        toàn bộ** danh sách ⇒ xác suất chọn provider thứ 2 vẫn rất cao ⇒
        vẫn đốt quota của provider không ưu tiên. ⇒ Phải chọn **chỉ trong
        nhóm provider ưu tiên cao nhất** còn quota; chỉ khi nhóm đó hết
        mới lùi xuống nhóm kế tiếp.

        Args:
            available: Danh sách khóa model còn dùng được.

        Returns:
            Danh sách khóa thuộc provider ưu tiên cao nhất (có thể rỗng).
        """
        if not available:
            return []
        if not self.provider_priority:
            return list(available)
        groups: dict[str, list[str]] = {}
        for key in available:
            provider = key.split("/", 1)[0]
            groups.setdefault(provider, []).append(key)
        for provider in self.provider_priority:
            members = groups.get(provider)
            if members:
                return sorted(members, key=self._sort_key)
        return sorted(available, key=self._sort_key)

    @staticmethod
    def _model_key(client: LLMClient) -> str:
        """Lấy khóa định danh model của client.

        Args:
            client: Client.

        Returns:
            Chuỗi khóa (provider/model).
        """
        if not client.providers:
            return "?"
        provider = client.providers[0]
        return f"{provider.name}/{provider.model}"

    def _is_quota_error(self, error: BaseException) -> bool:
        """Kiểm tra lỗi có phải hết quota (429) hay không.

        Args:
            error: Exception.

        Returns:
            ``True`` nếu là lỗi quota.
        """
        text = str(error).lower()
        return (
            "429" in text
            or "resourceexhausted" in text
            or "quota" in text
            or "rate limit reached" in text
            or "rate_limit" in text
        )

    def wait_for_any_quota(
        self,
        max_wait_s: float,
        *,
        deadline: float | None = None,
    ) -> bool:
        """Chờ cho tới khi **ít nhất một** model hết cooldown.

        Vì sao chờ ở đây thay vì defer + restart?
        ---------------------------------------
        Mỗi vòng `--resume` phải nạp lại 65.608 chunk + embedding (~60s).
        Groq hồi quota theo **rolling window** (~10–20 phút) ⇒ chờ tại chỗ
        rẻ hơn nhiều so với thoát ra rồi vào lại.

        Args:
            max_wait_s: Thời gian chờ tối đa cho lần chờ này (giây).
            deadline: Mốc thời gian ** tuyệt đối** (epoch) mà vượt quá thì
                dừng chờ. Dùng để giới hạn **tổng** thời gian chờ của cả
                lượt chạy: nếu không, 163 câu × 900s = **40 giờ** chờ vô ích.

        Returns:
            ``True`` nếu có model dùng được, ``False`` nếu hết thời gian chờ.
        """
        wait_deadline = time.time() + max(0.0, float(max_wait_s))
        while True:
            if self.healthy_keys():
                return True
            wait_s = self._sleep_until_next_cooldown()
            if wait_s is None or wait_s <= 0:
                return bool(self.healthy_keys())
            remaining = wait_deadline - time.time()
            if remaining <= 0:
                return bool(self.healthy_keys())
            if deadline is not None:
                remaining = min(remaining, deadline - time.time())
                if remaining <= 0:
                    return bool(self.healthy_keys())
            sleep_s = min(wait_s, remaining)
            logger.info(
                "Chờ quota hồi %.0fs (tối đa %.0fs nữa)",
                sleep_s,
                remaining,
            )
            time.sleep(sleep_s)

    @staticmethod
    def _gemini_quota_kind(error: BaseException) -> str | None:
        """Phân loại hạn mức Gemini theo ``quota_id`` trong lỗi 429.

        Vì sao cần?
        ----------
        Gemini báo **một** thông điệp 429 cho cả RPM và RPD, chỉ khác ở
        ``quota_id``:

        - `GenerateRequestsPerMinutePerProjectPerModel-FreeTier` ⇒ **RPM**
          ⇒ hồi sau vài chục giây.
        - `GenerateRequestsPerDayPerProjectPerModel-FreeTier` ⇒ **RPD**
          ⇒ cả ngày mới hồi (thực tế ~24 h, không phải "1h" như báo).

        Trước D-135, harness chỉ đoán qua **độ dài** mốc reset
        (`rpd_threshold_s`) ⇒ dễ **nhầm** ⇒ cooldown sai ⇒ mất cả ngày.

        Args:
            error: Lỗi từ provider.

        Returns:
            ``"rpd"``, ``"rpm"`` hoặc ``None`` nếu không nhận diện được.
        """
        text = str(error)
        if "PerDay" in text or "per_day" in text.lower():
            return "rpd"
        if "PerMinute" in text or "per_minute" in text.lower():
            return "rpm"
        return None

    def _record_quota_cooldown(self, key: str, error: BaseException) -> None:
        """Ghi nhận mốc hồi quota cho 1 model (có trần).

        Vì sao có trần?
        --------------
        Provider báo mốc reset **rất xa** (Gemini: "retry in 5h14m16s" khi
        quota ngày cạn) ⇒ nếu loại model khỏi pool đúng 5 giờ thì khi quota
        thực tế hồi sớm hơn (ví dụ Gemini reset lúc 8h sáng) ta vẫn bỏ
        lỡ ⇒ mất cả ngày. ⇒ Cắt cooldown ở `max_cooldown_s` để thử lại
        định kỳ.

        D-130: phân biệt hạn mức **theo provider**.
        -----------------------------------------
        Đo được 18/11/2026 (2 phép thực nghiệm):

        | Provider | Mốc reset **báo** | Hành vi **thật** |
        |---|---|---|
        | Gemini | "retry in 1h58m" | hồi sau **~40–60 giây** |
        | Groq | "try again in 5m1s" | TPD 200K ⇒ **đúng** mốc reset |

        ⇒ Gemini báo mốc reset **không đáng tin** (nó là mốc reset *ngày*,
        nhưng lỗi thực tế là do hạn mức *phút*) ⇒ **không** tin mốc đó ⇒
        dùng cooldown **ngắn** (`rpm_min_cooldown_s`) rồi thử lại. Groq báo
        mốc reset TPD **chính xác** ⇒ tin mốc đó (có trần `max_cooldown_s`).

        D-135: nhận diện **chính xác** RPM vs RPD của Gemini.
        ---------------------------------------------------
        Gemini ghi `quota_id` trong lỗi 429:

        - `...PerMinute...-FreeTier` ⇒ **RPM** ⇒ hồi sau ~40–60 s.
        - `...PerDay...-FreeTier` ⇒ **RPD** ⇒ cả ngày mới hồi.

        ⇒ Nếu là **RPD** ⇒ cooldown dài (tin mốc provider, có trần
        `max_cooldown_s`) ⇒ **không** probe lại model đó mỗi vòng (mỗi
        lần probe = 1 request **bị tính** vào RPD ⇒ tự làm cạn thêm).
        ⇒ Nếu là **RPM** ⇒ cooldown ngắn (`rpm_min_cooldown_s`).

        Args:
            key: Khoá model.
            error: Lỗi (chứa thông tin mốc reset nếu provider báo).
        """
        retry_after = self._retry_after_s(error)
        kind = self._gemini_quota_kind(error) if key.startswith("gemini/") else None
        if kind == "rpd":
            # Gemini hạn mức **ngày** ⇒ hồi rất xa ⇒ loại tạm lâu, có trần.
            cooldown = (
                min(retry_after, self.max_cooldown_s)
                if retry_after is not None
                else self.max_cooldown_s
            )
        elif kind == "rpm":
            # Gemini hạn mức **phút** ⇒ hồi sau vài chục giây.
            cooldown = self.rpm_min_cooldown_s
        elif retry_after is None:
            cooldown = self.quota_cooldown_s
        elif key.startswith("gemini/"):
            # Gemini: mốc reset **không đáng tin** (D-130) ⇒ cooldown ngắn.
            cooldown = self.rpm_min_cooldown_s
        elif retry_after >= self.rpd_threshold_s:
            # Groq báo mốc reset dài (TPD) ⇒ tin mốc đó (có trần).
            cooldown = min(retry_after, self.max_cooldown_s)
        else:
            # Mốc reset **ngắn** ⇒ RPM ⇒ chỉ cần chờ một chút.
            cooldown = max(retry_after, self.rpm_min_cooldown_s)
        self._cooldown_until[key] = max(
            self._cooldown_until.get(key, 0.0),
            time.time() + cooldown,
        )

    @staticmethod
    def _retry_after_s(error: BaseException) -> float | None:
        """Trích **thời gian chờ** mà provider tự báo trong lỗi quota.

        Vì sao: Gemini báo "Please retry in 5h14m16s" (reset RPD lúc 8h sáng
        theo giờ VN), Groq báo "try again in 2m53s" ⇒ biết đúng mốc reset
        ⇒ **chờ đúng số đó** thay vì lãng phí request vào model đã chết.

        Args:
            error: Exception.

        Returns:
            Số giây cần chờ, hoặc ``None`` nếu không tìm thấy.
        """
        text = str(error)
        # Gemini: "Please retry in 5h14m16.763661727s"
        match = re.search(
            r"retry in (\d+)h(\d+)m([\d.]+)s", text, flags=re.IGNORECASE
        )
        if match:
            hours, minutes, seconds = match.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        # Groq: "Please try again in 2m53.664s." — có thể kèm giờ cho TPD dài.
        match = re.search(
            r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s",
            text,
            flags=re.IGNORECASE,
        )
        if match:
            hours, minutes, seconds = match.groups()
            return (
                int(hours or 0) * 3600
                + int(minutes or 0) * 60
                + float(seconds)
            )
        # Gemini dạng khác: "retry_delay { seconds: 35820 }"
        match = re.search(r"retry_delay[^0-9]{0,20}(\d+)", text)
        if match:
            return float(match.group(1))
        match = re.search(r"in ([\d.]+)s", text)
        if match:
            return float(match.group(1))
        return None

    def _pick(self) -> LLMClient:
        """Chọn client kế tiếp (round-robin, bỏ qua model đang cooldown).

        Nếu có model đang được **ghin** (`pin`) và chưa hết quota ⇒ ưu tiên
        model đó ⇒ cả 3 arm của cùng một câu dùng **cùng model**.

        Nếu model ghim đã hết quota ⇒ **ghin lại** sang model thay thế đang
        còn quota (thay vì bỏ ghim rồi round-robin). Lý do: nếu bỏ ghim, arm A
        có thể rơi vào model X còn arm B vào model Y ⇒ **confound model** quay
        lại ⇒ phép so sánh giữa các arm không còn công bằng.
        Ở chế độ **ghim cứng** (`pin_strict`) ⇒ trả về **đúng** model ghim
        (kể cả khi đang cooldown) ⇒ `complete()` sẽ **chờ** quota hồi thay vì
        đổi model.

        Returns:
            Client được chosen.
        """
        count = len(self.clients)
        if not count:
            raise RuntimeError("Pool LLM rỗng")
        now = time.time()
        if self._pinned_key:
            for client in self.clients:
                if self._model_key(client) != self._pinned_key:
                    continue
                if self._cooldown_until.get(self._pinned_key, 0.0) <= now:
                    return client
            # Model ghim đã hết quota ⇒ chuyển ghim sang model thay thế còn
            # quota (giữ tính nhất quán cho cả 3 arm của câu đang chạy).
            if self._strict_pin:
                # Ghim **cứng** ⇒ KHÔNG đổi model (đổi model ⇒ confound!).
                # Fail **ngay** để vòng retry của câu ghim lại model khác
                # đang còn quota ⇒ không mất câu, không lệch model.
                from src.common.llm_client import LLMError

                raise LLMError(
                    f"Model ghim {self._pinned_key} đang hết quota "
                    "(ghim cứng ⇒ không đổi model, retry câu với model khác)."
                )
            logger.warning(
                "Model ghim %s đã hết quota — chuyển sang model khác",
                self._pinned_key,
            )
            replacement = self._pick_unpinned()
            if replacement is not None:
                self._pinned_key = self._model_key(replacement)
                return replacement
            self._pinned_key = None
        return self._pick_unpinned()

    def _pick_unpinned(self) -> LLMClient | None:
        """Chọn client không theo ghim (bỏ qua model đang cooldown).

        Returns:
            Client được chọn, hoặc ``None`` nếu pool rỗng.
        """
        count = len(self.clients)
        now = time.time()
        for offset in range(count):
            client = self.clients[(self.index + offset) % count]
            key = self._model_key(client)
            until = self._cooldown_until.get(key, 0.0)
            if until > now:
                continue
            self.index = (self.index + offset + 1) % count
            return client
        # Tất cả đang cooldown ⇒ chọn cái có cooldown sớm nhất.
        client = self.clients[self.index % count]
        self.index = (self.index + 1) % count
        return client

    def save_state(self, path: str | Path) -> None:
        """Lưu trạng thái cooldown ra file (để vòng sau khỏi probe lại).

        Vì sao?
        --------
        Gemini có hạn mức **500 request/ngày/model**. Mỗi vòng `--resume`
        gọi `probe_all()` (1 lời gọi/model) ⇒ 40 vòng × 7 model = 280 lời
        gọi lãng phí (>50% hạn mức) ⇒ chạy được ít câu hơn. ⇒ Lưu mốc
        cooldown giữa các vòng ⇒ vòng sau bỏ qua model đã biết chết.

        Args:
            path: Đường dẫn file JSON.
        """
        try:
            Path(path).write_text(
                json.dumps(
                    {
                        "cooldown_until": dict(self._cooldown_until),
                        "errors": dict(self.errors),
                        "saved_at": time.time(),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def load_state(self, path: str | Path) -> None:
        """Khôi phục trạng thái cooldown từ file (xem `save_state`).

        Args:
            path: Đường dẫn file JSON.
        """
        file_path = Path(path)
        if not file_path.exists():
            return
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for key, until in (data.get("cooldown_until") or {}).items():
            self._cooldown_until[str(key)] = float(until)
        for key, count in (data.get("errors") or {}).items():
            self.errors[str(key)] = int(count)

    def probe_all(self, *, skip_cooling: bool = False) -> dict[str, bool]:
        """Thử **một** lời gọi rất nhỏ với từng model để biết model nào còn
        quota.

        Vì sao: free tier có thể **đã cạn** từ trước khi chạy (ví dụ hôm
        trước dùng hết quota, hoặc model khác trong cùng tài khoản đã cạn).
        Nếu không probe thì pool có thể ghim nhầm model đã chết ⇒ câu đó
        lỗi hoặc lệch model ⇒ mất dữ liệu.

        Args:
            skip_cooling: Bỏ qua các model **đang cooldown** (đã biết là
                chết) ⇒ không tốn lời gọi probe cho chúng. Vì sao cần?
                Gemini có hạn mức **500 request/ngày/model**; mỗi vòng
                `--resume` probe lại toàn bộ pool ⇒ 40 vòng × 7 model = 280
                lời gọi lãng phí (hơn nửa hạn mức!) ⇒ phải bỏ qua model
                đã biết chết.

        Returns:
            Mapping ``model key`` → ``True`` nếu model còn dùng được.
        """
        healthy: dict[str, bool] = {}
        now = time.time()
        for client in self.clients:
            key = self._model_key(client)
            if skip_cooling and self._cooldown_until.get(key, 0.0) > now:
                # Đã biết chết (đang cooldown) ⇒ không tốn lời gọi probe.
                healthy[key] = False
                continue
            try:
                client.complete(
                    "Trả về đúng một chữ: OK",
                    temperature=0.0,
                    max_tokens=8,
                )
                healthy[key] = True
                self.calls_by_model[key] = self.calls_by_model.get(key, 0) + 1
            except Exception as error:  # noqa: BLE001 - chỉ để đánh dấu
                healthy[key] = False
                self.errors[key] = self.errors.get(key, 0) + 1
                if self._is_quota_error(error):
                    self._record_quota_cooldown(key, error)
                logger.warning("Model %s không dùng được: %s", key, str(error)[:120])
        alive = [k for k, ok in healthy.items() if ok]
        logger.info(
            "Sức khoẻ pool: %d/%d model còn quota — %s",
            len(alive), len(healthy), alive or "KHÔNG CÒN",
        )
        return healthy

    def complete(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        """Gọi LLM, thử lần lượt qua từng model trong pool.

        Args:
            prompt: Nội dung prompt.
            system: System prompt.
            temperature: Nhiệt độ.
            max_tokens: Trần token.
            json_mode: Ép JSON.

        Returns:
            Nội dung phản hồi.

        Raises:
            LLMError: Nếu mọi model trong pool đều thất bại.
        """
        from src.common.llm_client import LLMError

        if not self.clients:
            raise LLMError("Pool LLM rỗng")
        errors: list[str] = []
        waited = 0.0
        while True:
            quota_hit = False
            # Ghim cứng ⇒ chỉ thử **đúng** model ghim (đổi model ⇒ confound).
            attempts = 1 if self._strict_pin else len(self.clients)
            for _ in range(attempts):
                client = self._pick()
                key = self._model_key(client)
                try:
                    response = client.complete(
                        prompt,
                        system=system,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        json_mode=json_mode,
                    )
                    self.calls_by_model[key] = self.calls_by_model.get(key, 0) + 1
                    self.last_model = key
                    return response
                except Exception as error:  # noqa: BLE001 - thử model tiếp theo
                    self.errors[key] = self.errors.get(key, 0) + 1
                    if self._is_quota_error(error):
                        quota_hit = True
                        self._record_quota_cooldown(key, error)
                    errors.append(f"{key}: {error}")
                    if self._strict_pin and self._pinned_key == key:
                        # Ghim cứng ⇒ KHÔNG đổi model (tránh confound).
                        # Thoát vòng lặp ⇒ xử lý "chờ quota hồi" bên dưới.
                        break
            if not quota_hit:
                break
            # Ghim cứng ⇒ **không** chờ ở đây: ném lỗi ngay để vòng retry
            # của câu ghim lại model khác đang còn quota (nhanh hơn chờ).
            if self._strict_pin:
                break
            # --- Mọi model đều hết quota ⇒ CHỜ để quota hồi --------------
            # Free tier reset theo ngày (Gemini 8h sáng, Groq TPD theo
            # chu kỳ) ⇒ bỏ câu sẽ mất dữ liệu. Chờ tới mốc cooldown
            # sớm nhất rồi thử lại (giới hạn bởi `max_quota_wait_s`).
            sleep_s = self._sleep_until_next_cooldown()
            if sleep_s is None or sleep_s <= 0:
                break
            if waited + sleep_s > self.max_quota_wait_s:
                break
            logger.warning(
                "Mọi model hết quota — chờ %.0fs để quota hồi (đã chờ %.0fs)",
                sleep_s, waited,
            )
            time.sleep(sleep_s)
            waited += sleep_s
            self.quota_wait_total_s += sleep_s
            errors.clear()
        raise LLMError("Mọi model trong pool đều thất bại — " + " | ".join(errors))

    def _sleep_until_next_cooldown(
        self,
        *,
        only_pinned: bool = False,
    ) -> float | None:
        """Tính số giây cần chờ tới khi ít nhất một model hết cooldown.

        Args:
            only_pinned: Nếu ``True`` ⇒ chỉ xét **model đang ghim** (dùng
                trong `complete()` khi ghim cứng: không được đổi model nên
                chỉ chờ đúng model đó). Nếu ``False`` ⇒ xét **mọi** model
                và lấy mốc **sớm nhất** (dùng khi sẽ ghim lại model khác).

        Returns:
            Số giây chờ, hoặc ``None`` nếu không có model nào đang cooldown.
        """
        now = time.time()
        if only_pinned and self._pinned_key:
            until = self._cooldown_until.get(self._pinned_key, 0.0)
            if until > now:
                return max(1.0, until - now)
        pending = [until for until in self._cooldown_until.values() if until > now]
        if not pending:
            return None
        return max(1.0, min(pending) - now)

    def complete_json(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> Any | None:
        """Gọi LLM ở chế độ JSON (tương thích `LLMClient.complete_json`).

        Args:
            prompt: Nội dung prompt.
            system: System prompt.
            temperature: Nhiệt độ.
            max_tokens: Trần token.

        Returns:
            Object đã parse hoặc ``None``.
        """
        from src.common.llm_client import parse_json_payload

        raw = self.complete(
            prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        parsed = parse_json_payload(raw)
        if parsed is not None:
            return parsed
        logger.warning("JSON không hợp lệ — retry 1 lần yêu cầu JSON thuần")
        retry_prompt = (
            f"{prompt}\n\n"
            "YÊU CẦU: Trả về **duy nhất** JSON hợp lệ, không markdown, "
            "không giải thích."
        )
        raw = self.complete(
            retry_prompt,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        return parse_json_payload(raw)


# ----------------------------------------------------------------------
# Arm runners
# ----------------------------------------------------------------------


def _parse_pool_spec(spec: str) -> list[tuple[str, list[str]]]:
    """Phân tích chuỗi pool đa provider.

    Định dạng: ``provider:model1,model2;provider2:model3``.

    Args:
        spec: Chuỗi đặc tả pool.

    Returns:
        Danh sách cặp `(provider, [model, ...])`.
    """
    groups: list[tuple[str, list[str]]] = []
    for chunk in (spec or "").split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        provider, _, models = chunk.partition(":")
        provider = provider.strip()
        model_list = [m.strip() for m in models.split(",") if m.strip()]
        if provider and model_list:
            groups.append((provider, model_list))
    return groups


def _parse_provider_priority(spec: str) -> tuple[str, ...]:
    """Phân tích chuỗi thứ tự ưu tiên provider.

    Args:
        spec: Chuỗi provider cách nhau bởi dấu phẩy (vd ``"gemini,groq"``).

    Returns:
        Tuple thứ tự ưu tiên (rỗng ⇒ không ưu tiên ⇒ sắp theo tên model).
    """
    return tuple(
        part.strip().lower()
        for part in (spec or "").split(",")
        if part.strip()
    )


def _build_pool_or_single(
    *,
    pool_spec: str,
    provider: str,
    models: list[str],
    requests_per_day: int | None,
    quota_cooldown_s: float,
    label: str,
    max_quota_wait_s: float = 0.0,
    max_cooldown_s: float = 900.0,
    provider_priority: tuple[str, ...] = (),
    rpd_threshold_s: float = 1800.0,
    rpm_min_cooldown_s: float = 60.0,
) -> Any:
    """Dựng client sinh/judge: ưu tiên pool đa provider, fallback pool 1 provider.

    Args:
        pool_spec: Đặc tả pool đa provider (`--gen-pool` / `--judge-pool`).
        provider: Provider dùng nếu không có `pool_spec`.
        models: Danh sách model dùng nếu không có `pool_spec`.
        requests_per_day: Ghi đè RPD (None ⇒ lấy từ config).
        quota_cooldown_s: Thời gian cooldown sau lỗi quota.
        label: Nhãn để log.
        max_quota_wait_s: Tổng thời gian tối đa được chờ để quota hồi lại.
        max_cooldown_s: Trần thời gian loại tạm 1 model sau lỗi quota.
        provider_priority: Thứ tự ưu tiên provider khi chọn model (vd
            ``("groq", "gemini")`` ⇒ ưu tiên Groq trước Gemini).
        rpd_threshold_s: D-130 — ngưỡng phân biệt RPD với RPM.
        rpm_min_cooldown_s: D-130 — cooldown tối thiểu cho lỗi RPM.

    Returns:
        `PooledLLM` hoặc `LLMClient`.
    """
    groups = _parse_pool_spec(pool_spec)
    if groups:
        clients = build_cross_provider_pool(
            groups, requests_per_day=requests_per_day
        )
        logger.info(
            "Pool %s (đa provider): %s",
            label,
            [f"{p}:{','.join(ms)}" for p, ms in groups],
        )
        pool = PooledLLM(
            clients,
            quota_cooldown_s=quota_cooldown_s,
            max_quota_wait_s=max_quota_wait_s,
            max_cooldown_s=max_cooldown_s,
            rpd_threshold_s=rpd_threshold_s,
            rpm_min_cooldown_s=rpm_min_cooldown_s,
        )
        pool.provider_priority = provider_priority
        return pool
    if models:
        clients = build_client_pool(
            provider, models, requests_per_day=requests_per_day
        )
        logger.info("Pool %s (%s): %s", label, provider, models)
        return PooledLLM(
            clients,
            quota_cooldown_s=quota_cooldown_s,
            max_quota_wait_s=max_quota_wait_s,
            max_cooldown_s=max_cooldown_s,
            rpd_threshold_s=rpd_threshold_s,
            rpm_min_cooldown_s=rpm_min_cooldown_s,
        )
    logger.info("Dùng provider đơn cho %s: %s", label, provider)
    return build_client(provider)


def _run_question_arms(
    *,
    text: str,
    arms: list[str],
    retriever: Any,
    rag_answerer: Any,
    hybrid_answerer: Any,
    session_id: str | None,
    only_arms: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Chạy 3 arm cho **một** câu hỏi, bắt lỗi theo từng arm.

    Lỗi của 1 arm **không** làm hỏng các arm còn lại. Lỗi được đánh dấu
    `infrastructure_error=True` để `aggregate` loại khỏi mẫu số (xem
    `aggregate`).

    Args:
        text: Câu hỏi.
        arms: Danh sách arm.
        retriever: Retriever dùng chung.
        rag_answerer: `RagAnswerer` (arm A).
        hybrid_answerer: `HybridAnswerer` (arm B và B−).
        session_id: Session id gốc (đã tách theo arm bên trong).
        only_arms: Chỉ chạy các arm này (mặc định: tất cả).

    Returns:
        Dict `arm` → kết quả thô.
    """
    outcomes: dict[str, dict[str, Any]] = {}
    # `only_arms` cho phép chạy lại **riêng** arm bị lỗi hạ tầng mà không
    # tốn thêm token cho các arm đã thành công (Groq chỉ có 200K token/ngày
    # ⇒ tiết kiệm 2/3 lượng token là mấu chốt để hoàn tất 247 câu).
    target_arms = list(only_arms) if only_arms is not None else list(arms)
    for arm in target_arms:
        answerer_client = rag_answerer if arm == "A" else hybrid_answerer
        try:
            if arm == "A":
                outcomes[arm] = run_arm_a(text, retriever, rag_answerer, session_id)
            elif arm == "B":
                outcomes[arm] = run_arm_b(
                    text, retriever, hybrid_answerer,
                    _arm_session_id(session_id, arm), use_graph=True,
                )
            elif arm == "B-":
                outcomes[arm] = run_arm_b(
                    text, retriever, hybrid_answerer,
                    _arm_session_id(session_id, arm), use_graph=False,
                )
            else:
                raise ValueError(f"Arm không hợp lệ: {arm}")
            # Ghi lại model **thực sự** đã sinh câu trả lời của arm này.
            client = getattr(answerer_client, "client", None)
            used = getattr(client, "last_model", "")
            if used:
                outcomes[arm]["gen_model"] = used
        except Exception as error:  # noqa: BLE001 - lỗi 1 câu không dừng cả run
            logger.warning("Câu arm %s lỗi: %s", arm, error)
            outcomes[arm] = {
                "answer": "",
                "status": "error",
                "citations": [],
                "context": "",
                "context_chars": 0,
                "elapsed_ms": 0,
                "faithfulness_ok": None,
                "error": f"{type(error).__name__}: {error}"[:400],
                "infrastructure_error": True,
            }
    return outcomes


def _arm_session_id(session_id: str | None, arm: str) -> str | None:
    """Tách session id theo arm để **không ô nhiễm lượt trả lời**.

    Vì sao cần?
    -----------
    Arm B (có KG) và arm B− (không KG) dùng **cùng** `session_id` ⇒ với câu
    `multi_turn`, arm B− sẽ đọc được lượt trả lời của arm B trong lịch sử
    hội thoại ⇒ lệch so sánh (B− "biết" câu trả lời của B).

    ⇒ Mỗi arm có **session riêng** (`<session_id>__<arm>`) ⇒ mỗi arm tự
    xây lại lịch sử của chính nó ⇒ so sánh công bằng.

    Args:
        session_id: Session id gốc từ bộ câu hỏi (None ⇒ không có hội thoại).
        arm: Tên arm (`A` | `B` | `B-`).

    Returns:
        Session id đã tách theo arm, hoặc ``None``.
    """
    if not session_id:
        return None
    return f"{session_id}__{arm}"


def run_arm_a(
    question: str,
    retriever: Any,
    answerer: Any,
    session_id: str | None,
) -> dict[str, Any]:
    """Chạy arm A — Vanilla RAG.

    Args:
        question: Câu hỏi.
        retriever: Retriever (dùng chung với arm B).
        answerer: `RagAnswerer`.
        session_id: Id phiên (tách theo arm ⇒ không ô nhiễm lượt trả lời).

    Returns:
        Dict kết quả thô của arm.
    """
    # Truyền `session_id` ⇒ arm A cũng có **query rewriting** (kế thừa chủ
    # thể) như arm B. Vì sao? Nhóm câu `multi_turn` (60/247 câu) dùng đại từ
    # ("ông ấy sinh năm nào?") ⇒ nếu arm A không viết lại câu hỏi, nó **không
    # truy xuất được** văn bản về chủ thể ⇒ trả lời sai ⇒ chênh lệch điểm
    # A vs B là do **hội thoại**, không phải do KG ⇒ **confound** ⇒ kết luận
    # nghiên cứu bị sai. ⇒ Cho A cùng cơ chế; thứ khác biệt còn lại là KG.
    result = answerer.answer(question, session_id=session_id)
    context_blocks = list(result.get("context_used") or [])
    context_text = "\n\n".join(
        f"[{i}] {item.get('title', '')} > {item.get('section', '')}\n{item.get('text', '')}"
        for i, item in enumerate(context_blocks, start=1)
    )
    return {
        "answer": result.get("answer", ""),
        "status": result.get("status"),
        "citations": result.get("citations") or [],
        "context": context_text,
        "context_blocks": [
            {
                "doc_id": item.get("doc_id"),
                "title": item.get("title"),
                "section": item.get("section"),
                "section_path": item.get("section_path"),
            }
            for item in context_blocks
        ],
        "context_chars": result.get("context_chars", 0),
        "elapsed_ms": result.get("elapsed_ms", 0),
        "faithfulness_ok": result.get("faithfulness_ok"),
        "no_data_retried": bool(result.get("no_data_retried")),
    }


def run_arm_b(
    question: str,
    retriever: Any,
    answerer: Any,
    session_id: str | None,
    *,
    use_graph: bool = True,
) -> dict[str, Any]:
    """Chạy arm B (Hybrid) hoặc B− (tắt KG).

    Args:
        question: Câu hỏi.
        retriever: Retriever (dùng chung).
        answerer: `HybridAnswerer`.
        session_id: Id phiên hội thoại.
        use_graph: Bật kênh KG hay không.

    Returns:
        Dict kết quả thô của arm.
    """
    result = answerer.answer(
        question, session_id=session_id, use_graph=use_graph
    )
    context_text = result.get("context_text") or ""
    if not context_text:
        context_text = "\n\n".join(result.get("context_used") or [])
        kg_text = "\n\n".join(result.get("kg_used") or [])
        context_text += ("\n\n" + kg_text if kg_text else "")
    return {
        "answer": result.get("answer", ""),
        "status": result.get("status"),
        "citations": result.get("citations") or [],
        "context": context_text,
        "context_blocks": list(result.get("context_blocks") or []),
        "context_chars": len(context_text),
        "elapsed_ms": result.get("elapsed_ms", 0),
        "faithfulness_ok": result.get("faithfulness_ok"),
        "intent": (result.get("intent") or {}).get("intent"),
        "strategy": result.get("fusion_strategy"),
        "rewritten_question": result.get("rewritten_question"),
        "n_kg": len(result.get("kg_used") or []),
    }


# ----------------------------------------------------------------------
# Judge
# ----------------------------------------------------------------------


class Judge:
    """LLM-judge chấm điểm câu trả lời (gộp nhiều arm trong 1 lời gọi).

    Attributes:
        client: LLM client.
    """

    def __init__(self, client: LLMClient) -> None:
        """Khởi tạo.

        Args:
            client: LLM client.
        """
        self.client = client

    def score(
        self,
        *,
        question: str,
        expected_answer: str,
        candidates: list[dict[str, Any]],
        question_type: str = "",
        subject_name: str = "",
        context_chars: int = 9000,
    ) -> dict[str, dict[str, Any]]:
        """Chấm điểm nhiều phương án của **cùng một câu hỏi**.

        Args:
            question: Câu hỏi.
            expected_answer: Đáp án tham khảo.
            candidates: Danh sách `{"arm", "context", "answer"}`.
            question_type: Loại câu hỏi (`relational`, `narrative`, ...).
            subject_name: Tên chủ thể mà đại từ trong câu hỏi chỉ tới (dùng cho
                câu `multi_turn` — không có nó, judge coi đại từ là "không xác
                định đối tượng" ⇒ chấm 0 cho cả 3 arm dù câu trả lời đúng).

        Returns:
            Dict `arm` → `{"correctness", "faithfulness", "citation_precision",
            "reason"}`. Arm không có phương án ⇒ điểm 0.
        """
        result: dict[str, dict[str, Any]] = {}
        usable = [c for c in candidates if str(c.get("answer") or "").strip()]
        if not usable:
            for candidate in candidates:
                result[str(candidate.get("arm"))] = {
                    "correctness": 0,
                    "faithfulness": 0,
                    "citation_precision": 0.0,
                    "contradicts_reference": False,
                    "reason": "Không có câu trả lời.",
                }
            return result

        subject_hint = (
            f"Câu hỏi dùng đại từ chỉ tới: **{subject_name}**."
            if subject_name
            else "(không có — câu hỏi tự nêu rõ chủ thể)"
        )

        blocks: list[str] = []
        for candidate in usable:
            arm = str(candidate.get("arm"))
            answer_text = str(candidate.get("answer") or "")
            # D-138: giữ **bắt buộc** các khối `[n]` mà câu trả lời đã trích
            # dẫn ⇒ judge không thấy trích dẫn "không tồn tại".
            cited = {
                int(value)
                for value in re.findall(r"\[(\d+)\]", answer_text)
            }
            context = compact_context(
                str(candidate.get("context") or ""),
                total=context_chars,
                keep_indices=cited,
            )
            answer = answer_text[:3000]
            blocks.append(
                f"### PHƯƠNG ÁN {arm}\n"
                f"CONTEXT:\n{context or '(không có context)'}\n\n"
                f"CÂU TRẢ LỜI:\n{answer}"
            )
        prompt = JUDGE_PROMPT.format(
            question_type=QUESTION_TYPE_LABELS.get(
                question_type, question_type or "(không rõ)"
            ),
            question=question,
            expected_answer=expected_answer or "(không có đáp án tham khảo)",
            subject_hint=subject_hint,
            candidates="\n\n".join(blocks),
        )
        # Judge phải chấm **đủ** mọi phương án. Nếu output JSON bị cắt (thiếu
        # arm) ⇒ điểm 0 cho arm đó ⇒ **số liệu sai** (không phải số liệu kém).
        # ⇒ Thử lại với `max_tokens` lớn hơn + yêu cầu ngắn gọn hơn.
        scores: dict[str, dict[str, Any]] = {}
        attempts = (
            {"max_tokens": 1200, "terse": False},
            {"max_tokens": 2400, "terse": False},
            {"max_tokens": 2400, "terse": True},
        )
        for attempt_no, attempt in enumerate(attempts, start=1):
            attempt_prompt = prompt
            if attempt["terse"]:
                attempt_prompt = (
                    prompt
                    + "\n\nLƯU Ý: `reason` phải **rất ngắn** (tối đa 15 từ) để "
                    "toàn bộ JSON vừa trong giới hạn token."
                )
            try:
                parsed = self.client.complete_json(
                    attempt_prompt,
                    temperature=0.0,
                    max_tokens=int(attempt["max_tokens"]),
                )
            except Exception as error:  # noqa: BLE001 - judge lỗi ⇒ thử lại
                logger.warning("Judge lỗi (lần %d): %s", attempt_no, error)
                parsed = None

            scores = {}
            if isinstance(parsed, dict):
                for item in parsed.get("scores") or []:
                    if not isinstance(item, dict):
                        continue
                    raw_arm = str(item.get("arm") or "")
                    if not raw_arm:
                        continue
                    arm = _normalize_arm_name(raw_arm, candidates)
                    if not arm:
                        continue
                    scores[arm] = {
                        "correctness": _clamp_int(item.get("correctness"), 0, 2),
                        "faithfulness": _clamp_int(item.get("faithfulness"), 0, 2),
                        "citation_precision": _clamp_float(
                            item.get("citation_precision"), 0.0, 1.0
                        ),
                        "contradicts_reference": bool(
                            item.get("contradicts_reference")
                        ),
                        "reason": str(item.get("reason") or "")[:300],
                    }

            missing = [
                str(c.get("arm"))
                for c in candidates
                if str(c.get("arm")) not in scores
                and str(c.get("answer") or "").strip()
            ]
            if not missing:
                break
            logger.warning(
                "Judge thiếu điểm cho %s (lần %d/%d)",
                ",".join(missing), attempt_no, len(attempts),
            )

        # --- Vòng cuối: chấm **riêng từng arm** còn thiếu ----------------
        # Vì sao?
        # ------
        # Gộp cả 3 arm vào 1 prompt ⇒ JSON output dài ⇒ dễ bị **cắt token**
        # ⇒ judge trả về arm đầu rồi hết output ⇒ các arm sau bị bỏ sót
        # (đo được ~19/247 arm ≈ 7,7%). Thử tăng `max_tokens` chỉ giúp
        # một phần (prompt + output vẫn có thể vượt trần).
        # ⇒ Gọi lại với **chỉ 1 arm** còn thiếu mỗi lần ⇒ output cực ngắn
        # ⇒ hầu như không bao giờ bị cắt ⇒ giảm "điểm 0 giả" gần về 0.
        # Chi phí: 1 request cho mỗi arm còn thiếu (nhỏ hơn nhiều so với
        # mất 1 câu trong mẫu số của cả 1 arm).
        still_missing = [
            str(c.get("arm"))
            for c in candidates
            if str(c.get("arm")) not in scores
            and str(c.get("answer") or "").strip()
        ]
        for missing_arm in still_missing:
            solo = [c for c in candidates if str(c.get("arm")) == missing_arm]
            try:
                parsed = self.client.complete_json(
                    JUDGE_PROMPT.format(
                        question_type=QUESTION_TYPE_LABELS.get(
                            question_type, question_type or "(không rõ)"
                        ),
                        question=question,
                        expected_answer=expected_answer or "(không có đáp án tham khảo)",
                        subject_hint=subject_hint,
                    candidates="\n\n".join(
                        f"### PHƯƠNG ÁN {c.get('arm')}\n"
                        f"CONTEXT:\n{compact_context(str(c.get('context') or ''), keep_indices={int(v) for v in re.findall(r'\\[(\\d+)\\]', str(c.get('answer') or ''))}) or '(không có context)'}\n\n"
                        f"CÂU TRẢ LỜI:\n{str(c.get('answer') or '')[:3000]}"
                        for c in solo
                    ),
                    ),
                    temperature=0.0,
                    max_tokens=600,
                )
            except Exception as error:  # noqa: BLE001
                logger.warning("Judge lỗi khi chấm riêng %s: %s", missing_arm, error)
                continue
            if not isinstance(parsed, dict):
                continue
            for item in parsed.get("scores") or []:
                if not isinstance(item, dict):
                    continue
                arm = _normalize_arm_name(str(item.get("arm") or ""), solo)
                if arm != missing_arm:
                    continue
                scores[arm] = {
                    "correctness": _clamp_int(item.get("correctness"), 0, 2),
                    "faithfulness": _clamp_int(item.get("faithfulness"), 0, 2),
                    "citation_precision": _clamp_float(
                        item.get("citation_precision"), 0.0, 1.0
                    ),
                    "contradicts_reference": bool(
                        item.get("contradicts_reference")
                    ),
                    "reason": str(item.get("reason") or "")[:300],
                }
                break

        for candidate in candidates:
            arm = str(candidate.get("arm"))
            if arm not in scores:
                scores[arm] = {
                    "correctness": 0,
                    "faithfulness": 0,
                    "citation_precision": 0.0,
                    "contradicts_reference": False,
                    "reason": "Judge không trả về điểm cho phương án này.",
                }
        return scores


def _normalize_arm_name(
    raw_arm: str, candidates: list[dict[str, Any]]
) -> str:
    """Chuẩn hóa tên arm do judge trả về về key gốc.

    LLM-judge đôi khi trả `"PHƯƠNG ÁN A"` thay vì `"A"` (vì prompt yêu cầu giữ
    nguyên tên phương án nhưng model vẫn hay thêm tiền tố). Không chuẩn hóa
    ⇒ mọi arm rơi vào nhánh "judge không trả về điểm" ⇒ **toàn bộ điểm = 0**.

    Args:
        raw_arm: Tên arm do judge trả về.
        candidates: Danh sách phương án gốc.

    Returns:
        Key arm hợp lệ, hoặc chuỗi rỗng nếu không khớp.
    """
    text = (raw_arm or "").strip()
    if not text:
        return ""
    known = {str(c.get("arm")): str(c.get("arm")) for c in candidates}
    if text in known:
        return known[text]
    # Bỏ tiền tố "PHƯƠNG ÁN", "PHUONG AN", "PHƯƠNG ÁN:", ...
    normalized = re.sub(
        r"^(phương\s*án|phuong\s*an|đáp án|dap an)\s*[:\-–]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # KHÔNG strip dấu "-" vì arm "B−" kết thúc bằng dấu gạch.
    normalized = normalized.strip().strip(".:*#—– ").strip()
    if normalized in known:
        return known[normalized]
    # Chuẩn hóa dấu gạch Unicode (−, –, —) về "-" để "B−" ≡ "B-".
    dash_normalized = normalized.replace("−", "-").replace("–", "-").replace("—", "-")
    if dash_normalized in known:
        return known[dash_normalized]
    # Thử khớp bỏ qua dấu câu/hoa thường.
    lowered = {arm.casefold(): arm for arm in known}
    if normalized.casefold() in lowered:
        return lowered[normalized.casefold()]
    if dash_normalized.casefold() in lowered:
        return lowered[dash_normalized.casefold()]
    # Thử chứa arm như một từ riêng (ví dụ "Phương án A" → "A").
    # Sắp xếp theo độ dài giảm dần để "B-" được ưu tiên hơn "B".
    for arm in sorted(known, key=len, reverse=True):
        if re.search(rf"(^|\W){re.escape(arm)}($|\W)", text):
            return known[arm]
    return ""


def _clamp_int(value: Any, low: int, high: int) -> int:
    """Chuyển giá trị thành int trong khoảng `[low, high]`.

    Args:
        value: Giá trị gốc.
        low: Cận dưới.
        high: Cận trên.

    Returns:
        Int đã giới hạn.
    """
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return low


def _clamp_float(value: Any, low: float, high: float) -> float:
    """Chuyển giá trị thành float trong khoảng `[low, high]`.

    Args:
        value: Giá trị gốc.
        low: Cận dưới.
        high: Cận trên.

    Returns:
        Float đã giới hạn.
    """
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return low


# ----------------------------------------------------------------------
# Metrics
# ----------------------------------------------------------------------


def _load_reuse_map(path: str | Path) -> dict[str, dict[str, Any]]:
    """Đọc checkpoint cũ để **tái dùng** kết quả của arm không đổi.

    Vì sao cần?
    -----------
    Sau một bản sửa chỉ ảnh hưởng **một** arm (vd D-118 chỉ đổi arm B vì
    arm A/B− giữ nguyên prompt + context), chạy lại **cả 3 arm** sẽ đốt
    gấp 3 lần quota LLM — mà quota free tier (Groq 200K token/ngày) **không
    đủ**. Tái dùng kết quả cũ của arm **không đổi** ⇒ chỉ tốn quota cho arm
    thực sự thay đổi.

    Vì sao vẫn **công bằng**?
    -------------------
    1. Arm được tái dùng **giữ nguyên** `context` + `answer` cũ ⇒ context
       đó **đúng** với mã hiện tại (vì arm đó không đổi) ⇒ tái dùng là
       *tái lập được*, không phải "chép điểm".
    2. Điểm **luôn được chấm lại** bởi judge hiện tại (judge đã đổi: thêm
       `subject_hint`) ⇒ điểm là điểm **mới**, không phải điểm cũ.
    3. `gen_model` được **giữ nguyên** ⇒ cùng model với lần chạy cũ ⇒
       không phát sinh confound model ⇒ so sánh 3 arm vẫn cùng model.

    Args:
        path: Đường dẫn checkpoint cũ.

    Returns:
        Mapping ``qid`` → bản ghi checkpoint cũ.
    """
    file_path = Path(path)
    if not file_path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            qid = str(record.get("qid") or "")
            if qid:
                rows[qid] = record
    return rows


def _has_infra_error(
    record: dict[str, Any],
    arms: list[str],
) -> bool:
    """Kiểm tra bản ghi checkpoint có arm lỗi hạ tầng hay không.

    Vì sao: câu bị lỗi hạ tầng (quota LLM cạn) **không** phản ánh chất
    lượng hệ thống. Nếu coi như đã xong thì `--resume` sẽ **bỏ qua** ⇒ mất
    câu vĩnh viễn ⇒ mẫu số co lại ⇒ số liệu yếu hơn cần thiết.

    Args:
        record: Bản ghi checkpoint của 1 câu.
        arms: Danh sách arm.

    Returns:
        ``True`` nếu có arm lỗi hạ tầng.
    """
    for arm in arms:
        entry = record.get(arm) or {}
        if (entry.get("arm") or {}).get("infrastructure_error"):
            return True
    return False


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Tính chỉ số tổng hợp cho 1 arm.

    **Câu lỗi hạ tầng bị loại khỏi thống kê** (`infrastructure_error=True`):
    khi quota LLM hết, câu đó **không** phản ánh chất lượng hệ thống ⇒
    tính điểm 0 cho nó sẽ làm sai lệch kết luận. Thay vào đó, số câu đó
    được đếm riêng ở `n_infra_errors` và được **loại khỏi mẫu số** của
    mọi chỉ số.

    Args:
        records: Danh sách kết quả từng câu.

    Returns:
        Dict chỉ số.
    """
    if not records:
        return {"n": 0}

    infra = [r for r in records if (r.get("arm") or {}).get("infrastructure_error")]
    valid = [r for r in records if not (r.get("arm") or {}).get("infrastructure_error")]
    if not valid:
        return {
            "n": 0,
            "n_infra_errors": len(infra),
            "n_total": len(records),
        }

    # Arm mà judge **không** trả về điểm (JSON bị cắt) ⇒ điểm 0 **giả**.
    # Vì sao phải loại khỏi mẫu số?
    #   - Điểm 0 ấy **không** phản ánh chất lượng hệ thống (judge bị cắt
    #     output, không phải hệ thống trả lời sai).
    #   - Tính vào trung bình ⇒ **hạ** điểm của arm đó một cách không
    #     công bằng ⇒ so sánh A/B/B- bị lệch (arm nào bị cắt nhiều hơn thì
    #     điểm càng thấp).
    # ⇒ Loại khỏi mẫu số của chỉ số điểm; đếm riêng ở `n_judge_missing`
    #   (sau `scripts/rejudge_missing.py` phải = 0).
    def _judge_missing(record: dict[str, Any]) -> bool:
        """Kiểm tra arm có bị judge bỏ sót điểm hay không.

        Args:
            record: Bản ghi kết quả 1 arm.

        Returns:
            ``True`` nếu judge không trả về điểm.
        """
        return "không trả về điểm" in str(record["judge"].get("reason", ""))

    n_judge_missing = sum(1 for r in valid if _judge_missing(r))
    scored = [r for r in valid if not _judge_missing(r)]
    if not scored:
        return {
            "n": 0,
            "n_infra_errors": len(infra),
            "n_judge_missing": len(valid),
            "n_total": len(records),
        }

    correctness = [r["judge"]["correctness"] for r in scored]
    faithfulness = [r["judge"]["faithfulness"] for r in scored]
    citations = [r["judge"]["citation_precision"] for r in scored]
    latencies = [r["arm"]["elapsed_ms"] for r in scored]
    tokens = [estimate_tokens(r["arm"]["context"]) for r in scored]

    no_data_records = [r for r in valid if r["type"] == "no_data"]
    no_data_ok = sum(
        1
        for r in no_data_records
        if is_no_data(r["arm"]["answer"])
        or "không có" in r["arm"]["answer"].lower()
    )

    # --- Phase 19 — `abstain_with_evidence` ------------------------------
    # Số câu arm **nói "không có trong dữ liệu"** dù **context có bằng chứng**.
    # Đây chính là lỗi cần đưa về 0 (Gate G19-1): đo được ở checkpoint D-124
    # là arm A 16/60 câu narrative, trong đó 7/16 câu gold section **vẫn có
    # trong top-8 context** ⇒ lỗi ở tầng sinh, không phải tầng truy xuất.
    abstain_records = [r for r in valid if r["type"] != "no_data"]
    abstain_with_evidence = 0
    abstain_total = 0
    for record in abstain_records:
        answer = str((record.get("arm") or {}).get("answer") or "")
        if not (is_no_data(answer) or "không có" in answer.lower()):
            continue
        abstain_total += 1
        if context_has_gold(
            (record.get("arm") or {}).get("context_blocks"),
            record.get("evidence_doc_id"),
            record.get("evidence_section"),
            (record.get("arm") or {}).get("context"),
            record.get("expected_answer"),
        ):
            abstain_with_evidence += 1

    by_type: dict[str, dict[str, float]] = {}
    for record in scored:
        bucket = by_type.setdefault(
            record["type"],
            {"n": 0, "correctness_sum": 0, "faithfulness_sum": 0},
        )
        bucket["n"] += 1
        bucket["correctness_sum"] += record["judge"]["correctness"]
        bucket["faithfulness_sum"] += record["judge"]["faithfulness"]
    # Phase 19 — `abstain_with_evidence` **theo từng nhóm** câu hỏi.
    by_type_abstain: dict[str, dict[str, int]] = {}
    for record in abstain_records:
        answer = str((record.get("arm") or {}).get("answer") or "")
        if not (is_no_data(answer) or "không có" in answer.lower()):
            continue
        bucket = by_type_abstain.setdefault(
            str(record.get("type") or ""),
            {"abstain": 0, "abstain_with_evidence": 0},
        )
        bucket["abstain"] += 1
        if context_has_gold(
            (record.get("arm") or {}).get("context_blocks"),
            record.get("evidence_doc_id"),
            record.get("evidence_section"),
            (record.get("arm") or {}).get("context"),
            record.get("expected_answer"),
        ):
            bucket["abstain_with_evidence"] += 1
    for bucket in by_type.values():
        bucket["correctness"] = round(
            bucket["correctness_sum"] / bucket["n"], 4
        )
        bucket["faithfulness"] = round(
            bucket["faithfulness_sum"] / bucket["n"], 4
        )
        bucket.pop("correctness_sum")
        bucket.pop("faithfulness_sum")
    for qtype, bucket in by_type_abstain.items():
        target = by_type.setdefault(qtype, {"n": 0})
        target["abstain"] = bucket["abstain"]
        target["abstain_with_evidence"] = bucket["abstain_with_evidence"]

    return {
        # `n` = số câu **có điểm thật** (đã loại arm lỗi hạ tầng và arm
        # judge bỏ sót) ⇒ mẫu số của mọi chỉ số là mẫu số **công bằng**.
        "n": len(scored),
        "n_total": len(records),
        "n_infra_errors": len(infra),
        "n_judge_missing": n_judge_missing,
        "correctness_mean": round(statistics.mean(correctness), 4),
        "correctness_rate": round(
            sum(1 for c in correctness if c == 2) / len(correctness), 4
        ),
        "faithfulness_mean": round(statistics.mean(faithfulness), 4),
        "faithfulness_rate": round(
            sum(1 for f in faithfulness if f == 2) / len(faithfulness), 4
        ),
        "citation_precision": round(statistics.mean(citations), 4),
        "no_data_accuracy": (
            round(no_data_ok / len(no_data_records), 4) if no_data_records else None
        ),
        # --- Phase 19 --------------------------------------------------
        "abstain_with_evidence": abstain_with_evidence,
        "abstain_total": abstain_total,
        "abstain_rate": (
            round(abstain_total / len(abstain_records), 4) if abstain_records else 0.0
        ),
        "abstain_with_evidence_rate": (
            round(abstain_with_evidence / len(abstain_records), 4)
            if abstain_records
            else 0.0
        ),
        "no_data_retried": sum(
            1 for r in valid if (r.get("arm") or {}).get("no_data_retried")
        ),
        "latency_p50": int(statistics.median(latencies)) if latencies else 0,
        "latency_p95": (
            int(sorted(latencies)[int(len(latencies) * 0.95) - 1])
            if len(latencies) >= 20
            else max(latencies)
        ),
        "context_tokens_mean": int(statistics.mean(tokens)) if tokens else 0,
        "by_type": by_type,
    }


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------


def main() -> int:
    """Điểm vào CLI.

    Returns:
        Mã thoát (0 = thành công).
    """
    parser = argparse.ArgumentParser(
        description="Đánh giá A vs B vs B− bằng LLM-judge (Phase 16 — bước 2)."
    )
    parser.add_argument(
        "--qa-set", default="data/eval/qa_rag_250.jsonl",
        help="Bộ câu hỏi đánh giá.",
    )
    parser.add_argument("--arms", default="A,B,B-", help="Danh sách arm (A, B, B-).")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số câu (0 = tất cả).")
    parser.add_argument(
        "--only-types",
        default="",
        help=(
            "Chỉ chạy các loại câu hỏi cụ thể, phân tách bằng dấu phẩy "
            "(ví dụ: 'multi_hop,relational'). Rỗng = chạy tất cả."
        ),
    )
    parser.add_argument("--no-judge", action="store_true", help="Bỏ qua LLM-judge.")
    parser.add_argument(
        "--out-prefix", default="eval_rag",
        help="Tiền tố file output trong `reports/`.",
    )
    parser.add_argument(
        "--stamp", default=None, help="Nhãn thời gian cho file output.",
    )
    parser.add_argument(
        "--reset-sessions",
        action="store_true",
        help="Xoá session đánh giá cũ (`data/interim/sessions/eval_*.json`) trước khi chạy.",
    )
    parser.add_argument(
        "--reuse-arms-from",
        default="",
        help=(
            "File checkpoint cũ để **tái dùng** kết quả của các arm **không "
            "thay đổi** (D-118: chỉ arm B thay đổi ⇒ arm A/B− giữ nguyên "
            "prompt + context ⇒ cache hit 100%% ⇒ **miễn phí**). Arm được "
            "tái dùng vẫn được **chấm lại** bởi judge hiện tại (judge đổi: "
            "thêm `subject_hint`) ⇒ điểm luôn là điểm mới."
        ),    )
    parser.add_argument(
        "--gen-provider-priority",
        default="groq,groq",
        help=(
            "Thứ tự ưu tiên provider cho pool sinh câu trả lời. "
            "Mặc định `groq,gemini` (Groq giới hạn theo **token/ngày** ⇒ "
            "giữ chỗ cho câu có model cũ còn quota; Gemini giới hạn theo "
            "**request/ngày** ⇒ dự phòng khi Groq cạn token)."
        ),
    )
    parser.add_argument(
        "--judge-provider-priority",
        default="gemini,groq",
        help="Thứ tự ưu tiên provider cho pool LLM-judge.",
    )
    parser.add_argument(
        "--judge-provider",
        default="gemini",
        choices=["gemini", "groq"],
        help="Provider dùng cho LLM-judge (quota: Gemini 500 RPD, Groq 1.000 RPD).",
    )
    parser.add_argument(
        "--gen-provider",
        default="groq",
        choices=["gemini", "groq"],
        help="Provider dùng cho sinh câu trả lời (750 lời gọi ⇒ Groq).",
    )
    parser.add_argument(
        "--gen-models",
        default="",
        help=(
            "Danh sách model sinh câu trả lời, phân tách bằng dấu phẩy "
            "(ví dụ: 'gemini-3.5-flash-lite,gemini-3.1-flash-lite'). "
            "Quota free tier tính **theo từng model** ⇒ nhiều model = nhiều bậc thông lượng."
        ),
    )
    parser.add_argument(
        "--judge-models",
        default="",
        help=(
            "Danh sách model LLM-judge, phân tách bằng dấu phẩy. "
            "Mặc định: model trong `configs/llm.yaml`."
        ),
    )
    parser.add_argument(
        "--gen-pool",
        default="",
        help=(
            "Pool **đa provider** cho sinh câu trả lời, định dạng "
            "`provider:model1,model2;provider2:model3`. "
            "Ví dụ: `gemini:gemini-3.1-flash-lite;groq:openai/gpt-oss-120b`. "
            "Dùng khi quota một provider đã cạn (quota free tier tính riêng "
            "theo provider **và** theo model)."
        ),
    )
    parser.add_argument(
        "--judge-pool",
        default="",
        help=(
            "Pool **đa provider** cho LLM-judge, cùng định dạng với `--gen-pool`."
        ),
    )
    parser.add_argument(
        "--gen-rpd",
        type=int,
        default=0,
        help=(
            "Ghi đè giới hạn requests-per-day cho pool sinh câu trả lời "
            "(0 = lấy từ `configs/llm.yaml`)."
        ),
    )
    parser.add_argument(
        "--judge-rpd",
        type=int,
        default=0,
        help=(
            "Ghi đè giới hạn requests-per-day cho pool judge (0 = lấy từ config)."
        ),
    )
    parser.add_argument(
        "--quota-cooldown-s",
        type=float,
        default=900.0,
        help=(
            "Thời gian loại tạm một model sau khi gặp lỗi quota 429 "
            "(giây). Mặc định 900."
        ),
    )
    parser.add_argument(
        "--max-quota-wait-s",
        type=float,
        default=300.0,
        help=(
            "Tổng thời gian tối đa được CHỜ trong 1 lần gọi LLM khi mọi "
            "model đều hết quota (giây). Free tier reset theo ngày ⇒ chờ "
            "một chút thay vì bỏ câu; hết thời gian chờ ⇒ câu được retry "
            "với model khác. Mặc định 300 (5 phút)."
        ),
    )
    parser.add_argument(
        "--quota-wait-s",
        type=float,
        default=900.0,
        help=(
            "Thời gian **chờ tại chỗ** cho tới khi có model hồi quota (giây). "
            "Rẻ hơn nhiều so với thoát ra rồi `--resume` (mỗi vòng phải nạp "
            "lại toàn bộ index 65K chunk). Mặc định 900 (15 phút)."
        ),
    )
    parser.add_argument(
        "--total-quota-wait-s",
        type=float,
        default=3600.0,
        help=(
            "Tổng thời gian **tối đa** được chờ quota hồi trong 1 lượt chạy "
            "(giây). Nếu không giới hạn: 163 câu × 900s = 40 giờ chờ vô ích. "
            "Hết hạn ⇒ câu còn lại bị hoãn ⇒ vòng `--resume` sau xử lý. "
            "Mặc định 3600 (1 giờ)."
        ),
    )
    parser.add_argument(
        "--judge-context-chars",
        type=int,
        default=9000,
        help=(
            "D-131 — ngân sách **ký tự context** cho mỗi arm trong prompt "
            "judge (mặc định 9.000). Vì sao cần? Groq có trần **8.000 "
            "token/phút** (TPM) cho `openai/gpt-oss-*` ⇒ prompt judge gộp 3 "
            "arm với context 9.000 ký tự/arm ≈ 10.800 token ⇒ **413 Request "
            "too large**. ⇒ Khi judge dùng Groq, đặt ngân sách nhỏ hơn "
            "(vd 2.500) để vừa trần TPM. Lưu ý: **ngân sách là như nhau cho "
            "cả 3 arm** ⇒ phép so sánh A vs B vs B− vẫn công bằng."
        ),
    )
    parser.add_argument(
        "--max-cooldown-s",
        type=float,
        default=900.0,
        help=(
            "Trần tối đa cho thời gian loại tạm 1 model sau lỗi quota "
            "(giây). Provider có thể báo mốc reset rất xa (vd Gemini "
            "'5h14m') ⇒ cắt còn 15 phút để không bỏ lỡ khi quota hồi sớm."
        ),
    )
    parser.add_argument(
        "--rpd-threshold-s",
        type=float,
        default=1800.0,
        help=(
            "D-130 — ngưỡng phân biệt hạn mức **ngày** (RPD) với hạn mức "
            "**phút** (RPM). Mốc reset provider báo **≥** ngưỡng này ⇒ coi là "
            "RPD ⇒ tin mốc reset dài hạn; ngắn hơn ⇒ RPM ⇒ chỉ loại tạm "
            "ngắn. Đo được 18/11/2026: Gemini báo 429 kèm 'retry in 2h15m' "
            "nhưng quota thực tế hồi sau ~40–60 giây ⇒ là RPM. Mặc định 1800."
        ),
    )
    parser.add_argument(
        "--rpm-min-cooldown-s",
        type=float,
        default=60.0,
        help=(
            "D-130 — thời gian loại tạm **tối thiểu** khi lỗi là RPM "
            "(giây). Mặc định 60 (đo được: quota Gemini hồi sau ~40–60s)."
        ),
    )
    parser.add_argument(
        "--judge-max-cooldown-s",
        type=float,
        default=14400.0,
        help=(
            "Trần cooldown **riêng cho pool judge** (giây, mặc định 4 giờ). "
            "Vì sao khác pool sinh? Judge dùng Gemini (hạn mức **request/ngày**, "
            "reset ~15:00 UTC+7) ⇒ hết quota thì **cả ngày** không hồi ⇒ "
            "probe lại mỗi 15 phút chỉ để nhận 429 ⇒ **ăn vô ích** quota RPD. "
            "⇒ Trần dài hơn ⇒ ít probe lãng phí hơn."
        ),
    )
    parser.add_argument(
        "--infra-retries",
        type=int,
        default=2,
        help=(
            "Số lần thử lại khi một câu lỗi **hạ tầng** (hết quota LLM). "
            "Mặc định 2."
        ),
    )
    parser.add_argument(
        "--infra-retry-wait-s",
        type=float,
        default=60.0,
        help="Thời gian chờ giữa các lần thử lại câu lỗi hạ tầng (giây).",
    )
    parser.add_argument(
        "--model-retries",
        type=int,
        default=2,
        help=(
            "Số lần chạy lại toàn bộ câu khi các arm dùng KHÁC model "
            "(model ghim hết quota giữa lúc arm đang chạy ⇒ confound model)."
        ),
    )
    parser.add_argument(
        "--checkpoint",
        default="data/eval/eval_rag_checkpoint.jsonl",
        help="File checkpoint (JSONL) để resume khi bị gián đoạn.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Đọc checkpoint và bỏ qua các câu đã xử lý.",
    )
    args = parser.parse_args()

    from src.qa.conversation import SessionStore
    from src.qa.hybrid import HybridAnswerer
    from src.qa.rag_answer import RagAnswerer
    from src.qa.retriever import Retriever

    started = time.time()
    stamp = args.stamp or time.strftime("%Y%m%d_%H%M%S")

    qa_path = resolve_path(args.qa_set)
    questions: list[dict[str, Any]] = []
    with qa_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    # ⚠️ Phase 19 — thứ tự lọc: **type trước, limit sau**.
    #
    # Vì sao? Trước đây `limit` cắt danh sách **trước** khi lọc theo type
    # ⇒ `--only-types narrative --limit 2` cắt còn 2 câu đầu (thuộc nhóm
    # `relational`) ⇒ lọc type ⇒ **0 câu** ⇒ chạy eval **không được gì**
    # mà không báo lỗi.
    if args.only_types:
        wanted = {item.strip() for item in args.only_types.split(",") if item.strip()}
        questions = [
            item for item in questions if str(item.get("type") or "") in wanted
        ]
        logger.info("Lọc theo type=%s ⇒ còn %d câu", sorted(wanted), len(questions))
    if args.limit:
        questions = questions[: args.limit]
    logger.info("Nạp %d câu hỏi từ %s", len(questions), qa_path)

    config = load_config(REPO_ROOT / "configs" / "retrieval.yaml")
    retriever = Retriever.load(REPO_ROOT / "configs" / "retrieval.yaml")
    llm_config = load_config(REPO_ROOT / "configs" / "llm.yaml")
    pools_cfg = (llm_config.get("pools") or {}) if isinstance(llm_config, dict) else {}

    # ⚠️ Phase 19 — **mặc định dùng pool đa provider** từ `configs/llm.yaml`.
    #
    # Vì sao cần?
    # ----------
    # Trước đây `--gen-pool` / `--judge-pool` mặc định là **chuỗi rỗng** ⇒
    # fallback sang pool **1 provider** (`groq` cho sinh, `gemini` cho judge)
    # ⇒ khi 1 provider hết quota ⇒ **dừng cả eval** dù còn provider khác
    # còn quota ⇒ phải chờ 1 ngày mới chạy tiếp được.
    # ⇒ Nếu CLI không chỉ định ⇒ lấy `pools.generation.spec` /
    # `pools.judge.spec` trong `configs/llm.yaml` ⇒ **giống hệt** pool
    # D-123/D-124 (D-136: giữ nguyên model pool để số liệu so sánh được).
    gen_pool_spec = args.gen_pool or str(
        (pools_cfg.get("generation") or {}).get("spec") or ""
    )
    judge_pool_spec = args.judge_pool or str(
        (pools_cfg.get("judge") or {}).get("spec") or ""
    )

    # Sinh câu trả lời: 741 lời gọi ⇒ cần pool **đa provider** để chịu quota
    # free tier (Gemini: 500 RPD/model; Groq: 200.000 token/ngày).
    gen_client: Any = _build_pool_or_single(
        pool_spec=gen_pool_spec,
        provider=args.gen_provider,
        models=[m.strip() for m in args.gen_models.split(",") if m.strip()],
        requests_per_day=args.gen_rpd or None,
        quota_cooldown_s=args.quota_cooldown_s,
        label="sinh câu trả lời",
        max_quota_wait_s=args.max_quota_wait_s,
        max_cooldown_s=args.max_cooldown_s,
        # Sinh câu trả lời **nặng token** ⇒ ưu tiên provider giới hạn theo
        # token/ngày (Groq) để **giữ** quota request/ngày (Gemini) cho judge.
        provider_priority=_parse_provider_priority(args.gen_provider_priority),
        rpd_threshold_s=args.rpd_threshold_s,
        rpm_min_cooldown_s=args.rpm_min_cooldown_s,
    )
    # **Session store dùng chung** cho cả 2 answerer ⇒ nhưng mỗi arm có
    # session **tách riêng** (`<session_id>__<arm>`) ⇒ không ô nhiễm lượt
    # trả lời của nhau (xem `_arm_session_id`).
    session_store = SessionStore()
    rag_answerer = RagAnswerer(
        retriever, config=config, client=gen_client, session_store=session_store
    )
    hybrid_answerer = HybridAnswerer(
        retriever, config=config, client=gen_client, session_store=session_store
    )

    if args.reset_sessions:
        sessions_dir = REPO_ROOT / "data" / "interim" / "sessions"
        removed = 0
        if sessions_dir.exists():
            for path in sessions_dir.glob("eval_*.json"):
                path.unlink()
                removed += 1
        logger.info("Đã xoá %d session đánh giá cũ", removed)

    judge_client: Any = _build_pool_or_single(
        pool_spec=judge_pool_spec,
        provider=args.judge_provider,
        models=[m.strip() for m in args.judge_models.split(",") if m.strip()],
        requests_per_day=args.judge_rpd or None,
        quota_cooldown_s=args.quota_cooldown_s,
        label="LLM-judge",
        max_quota_wait_s=args.max_quota_wait_s,
        max_cooldown_s=args.judge_max_cooldown_s,
        # Judge **gọn** (1 request/câu, prompt ~2.8k token) ⇒ ưu tiên
        # provider giới hạn theo request/ngày (Gemini) vì token/ngày của
        # Groq cần dành cho sinh câu trả lời.
        provider_priority=_parse_provider_priority(args.judge_provider_priority),
        rpd_threshold_s=args.rpd_threshold_s,
        rpm_min_cooldown_s=args.rpm_min_cooldown_s,
    )
    judge = Judge(judge_client)

    # --- Probe sức khoẻ pool trước khi chạy ---------------------------
    # Free tier có thể đã cạn từ trước ⇒ ghim nhầm model chết ⇒ câu lỗi
    # hoặc lệch model. Probe 1 lời gọi nhỏ cho từng model để biết model
    # nào còn quota (model chết bị loại khỏi `healthy_keys`).
    #
    # Trạng thái cooldown được **lưu lại** giữa các vòng `--resume` ⇒ vòng
    # sau không probe lại model đã biết chết (Gemini chỉ 500 RPD/model ⇒
    # probe lặp lại 40 vòng sẽ ăn hơn nửa hạn mức!).
    checkpoint_path = resolve_path(args.checkpoint)
    # **File trạng thái riêng** cho gen pool và judge pool (2 pool dùng
    # chung 1 file ⇒ pool này đè mất trạng thái pool kia ⇒ mất thông tin
    # "model nào đã chết" ⇒ probe lại ⇒ lãng phí lời gọi).
    gen_state_path = checkpoint_path.with_name(
        checkpoint_path.stem + ".gen_state.json"
    )
    judge_state_path = checkpoint_path.with_name(
        checkpoint_path.stem + ".judge_state.json"
    )
    if isinstance(gen_client, PooledLLM):
        gen_client.load_state(gen_state_path)
        gen_client.probe_all(skip_cooling=True)
    if isinstance(judge_client, PooledLLM):
        judge_client.load_state(judge_state_path)
        judge_client.probe_all(skip_cooling=True)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    all_results: dict[str, list[dict[str, Any]]] = {arm: [] for arm in arms}
    all_metrics: dict[str, dict[str, Any]] = {}

    # Thứ tự arm trong prompt judge được **hoán vị theo qid** để triệt tiêu
    # position bias (seed cố định ⇒ vẫn tái lập được).
    judge_order: dict[str, list[str]] = {}
    for question in questions:
        qid = str(question.get("qid"))
        order = list(arms)
        random.Random(f"{SEED}:{qid}").shuffle(order)
        judge_order[qid] = order

    # --- Checkpoint / resume -------------------------------------------
    # Quota LLM free có thể hết giữa chừng (429 TPD/RPD) ⇒ lưu từng câu đã
    # xong để chạy lại không phải làm lại (cache LLM cũng giúp).
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    done: dict[str, dict[str, Any]] = {}
    if args.resume and checkpoint_path.exists():
        with checkpoint_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                qid_ = str(record.get("qid"))
                # Câu lỗi hạ tầng (quota cạn) ⇒ **không** coi là đã xong ⇒
                # phải chạy lại, nếu không sẽ mất câu vĩnh viễn khi `--resume`.
                if _has_infra_error(record, arms):
                    logger.info(
                        "Resume: bỏ qua qid %s (có arm lỗi hạ tầng) — sẽ chạy lại",
                        qid_,
                    )
                    continue
                done[qid_] = record
        logger.info("Resume: %d câu đã có trong checkpoint", len(done))

    checkpoint_handle = checkpoint_path.open("a", encoding="utf-8")
    #: Bản đồ ``qid`` → bản ghi cũ để **tái dùng** arm không đổi (D-118).
    reuse_map: dict[str, dict[str, Any]] = {}
    #: Tập arm được **tái dùng** (không gọi LLM sinh lại).
    reuse_arms: set[str] = set()
    if args.reuse_arms_from:
        reuse_map = _load_reuse_map(resolve_path(args.reuse_arms_from))
        # Chỉ arm **không thay đổi** mới được tái dùng. Mặc định: arm A và B−
        # (D-118 chỉ đổi arm B: chiều KG + ngân sách context + prompt đồ thị).
        reuse_arms = {"A", "B-"} & set(arms)
        logger.info(
            "Tái dùng %d câu cũ cho arm %s (từ %s)",
            len(reuse_map), sorted(reuse_arms), args.reuse_arms_from,
        )
    #: Danh sách qid bị **hoãn** (mọi model hết quota) ⇒ không ghi checkpoint
    #: ⇒ vòng `--resume` sau chạy lại.
    deferred_qids: list[str] = []
    #: **Deadline tổng** cho thời gian chờ quota trong lượt chạy này.
    #: Vì sao: nếu mỗi câu chờ tối đa `--quota-wait-s` (900s) và có 163 câu
    #: đều hết quota ⇒ 163 × 900s = **40 giờ** chờ vô ích. ⇒ Giới hạn
    #: **tổng** thời gian chờ; hết hạn ⇒ các câu còn lại bị hoãn ⇒ vòng
    #: `--resume` sau xử lý (quota Groq hồi theo rolling window ~10–20 phút).
    quota_wait_deadline = (
        time.time() + max(0.0, float(args.total_quota_wait_s))
        if args.total_quota_wait_s > 0
        else None
    )

    for index, question in enumerate(questions, start=1):
        qid = str(question.get("qid"))
        text = str(question.get("question"))
        session_id = question.get("session_id")

        if qid in done:
            # Câu đã xử lý ⇒ khôi phục kết quả, không gọi LLM lại.
            for arm in arms:
                all_results[arm].append(done[qid][arm])
            if index % 10 == 0:
                logger.info("đã chạy %d/%d câu (resume)", index, len(questions))
            continue

        outcomes: dict[str, dict[str, Any]] = {}
        #: Danh sách arm cần **chạy lại** (chỉ arm lỗi hạ tầng) ⇒ tiết kiệm
        #: token Groq.
        retry_arms: list[str] | None = None
        #: Câu bị **hoãn** (mọi model hết quota) ⇒ không ghi checkpoint,
        #: để vòng sau chạy lại (nhờ `_has_infra_error` bỏ qua bản ghi lỗi).
        deferred = False

        # --- Tái dùng arm KHÔNG thay đổi (D-118) -----------------------
        # Vì sao?
        # --------
        # D-118 chỉ đổi **arm B** (chiều KG + ngân sách context + hướng dẫn
        # đọc đồ thị). Arm A và B− giữ nguyên prompt + context ⇒ **tái lập
        # được** với mã hiện tại ⇒ tái dùng `context` + `answer` cũ là hợp lệ
        # (không phải "chép điểm": điểm vẫn do judge hiện tại chấm lại).
        #
        # Vì sao cần?
        # ---------
        # Quota free tier: Groq **200K token/ngày/model**. 247 câu × 3 arm
        # ≈ 2M token ⇒ **vượt quota 10×** ⇒ chạy cả 3 arm là không khả thi.
        # Chỉ sinh lại arm B ⇒ 247 lời gọi ≈ 670K token ⇒ chia 3 model Groq
        # ⇒ khả thi trong 1 ngày.
        reused_from_old: dict[str, dict[str, Any]] = {}
        old_record = reuse_map.get(qid) if reuse_map else None
        #: Model của lần chạy cũ (nếu có) — dùng để ghim ⇒ giữ tính nhất quán.
        reuse_model = ""
        if old_record:
            for arm in reuse_arms:
                old_entry = old_record.get(arm)
                if not old_entry:
                    continue
                old_arm = old_entry.get("arm") or {}
                # Bỏ qua bản ghi lỗi hạ tầng (không có câu trả lời thật).
                if old_arm.get("infrastructure_error") or not str(
                    old_arm.get("answer") or ""
                ).strip():
                    continue
                reused_from_old[arm] = old_entry
                candidate = str(old_entry.get("gen_model") or "")
                if candidate and not reuse_model:
                    reuse_model = candidate

        # Model của lần chạy cũ **không còn dùng được** (đã hết quota) ⇒
        # **không tái dùng** arm nào của câu này. Vì sao?
        # -------------------------------------------------
        # Arm tái dùng giữ `gen_model` cũ; arm chạy lại sinh bằng model mới ⇒
        # 3 arm dùng **khác model** ⇒ **confound model** ⇒ câu đó bị loại
        # khỏi mẫu số ⇒ mất dữ liệu. ⇒ Tốt hơn: **sinh lại toàn bộ** câu
        # bằng 1 model (tốn 3 lời gọi thay vì 1) nhưng giữ được câu trong
        # mẫu số.
        if reused_from_old and reuse_model and isinstance(gen_client, PooledLLM):
            if reuse_model not in set(gen_client.keys()):
                logger.info(
                    "Câu %s — model cũ (%s) không có trong pool ⇒ sinh lại toàn bộ",
                    qid, reuse_model,
                )
                reused_from_old = {}
            elif reuse_model not in set(gen_client.healthy_keys()):
                logger.info(
                    "Câu %s — model cũ (%s) đã hết quota ⇒ sinh lại toàn bộ",
                    qid, reuse_model,
                )
                reused_from_old = {}

        #: Arm thực sự cần gọi LLM (tất cả trừ arm tái dùng).
        arms_to_run = [arm for arm in arms if arm not in reused_from_old]
        if reused_from_old:
            logger.info(
                "Câu %s — tái dùng arm %s (không đổi) ⇒ chỉ gọi LLM cho %s",
                qid, ",".join(sorted(reused_from_old)), ",".join(arms_to_run),
            )

        # --- Pre-check: judge có sẵn sàng không? -------------------------
        # Vì sao kiểm tra TRƯỚC khi sinh câu trả lời?
        # ---------------------------------------------
        # Quota của 2 provider khác nhau:
        # - **Gemini**: hạn mức theo **số request/ngày** (500 RPD/model) ⇒
        #   token gần như không giới hạn ⇒ **judge** nên chạy ở đây.
        # - **Groq**: hạn mức theo **token/ngày** (200K token/model) ⇒
        #   **sinh câu trả lời** nên chạy ở đây.
        # Nếu judge (Gemini) hết quota mà vẫn sinh câu trả lời (Groq) ⇒ tốn
        # token Groq rồi câu vẫn bị hoãn vì judge lỗi ⇒ **lãng phí 100%**.
        # ⇒ Kiểm tra judge **trước**, hoãn câu ngay nếu judge chưa sẵn sàng.
        if isinstance(judge_client, PooledLLM) and not judge_client.healthy_keys():
            logger.info(
                "Câu %s — judge chưa sẵn sàng (hết quota) ⇒ HOÃN câu "
                "(không tốn token sinh câu trả lời)",
                qid,
            )
            deferred = True
            deferred_qids.append(qid)
            continue

        # --- Ghim model cho cả 3 arm của câu này -----------------------
        # Vì sao: nếu arm A dùng Gemini còn arm B dùng Groq thì chênh lệch
        # điểm có thể do **model** chứ không phải do kiến trúc ⇒ confound.
        # ⇒ Chọn 1 model theo `qid` (seed 42 ⇒ tái lập được), rồi ép cả 3
        # arm dùng model đó. Nếu model đó hết quota giữa chừng ⇒ pool **ghin
        # lại** sang model thay thế (vẫn cùng model cho cả 3 arm).
        pinned_model = ""
        if isinstance(gen_client, PooledLLM):
            # **Ưu tiên 1 — ghim theo model của lần chạy cũ** khi có arm
            # được tái dùng. Vì sao?
            # -------------------
            # Arm tái dùng giữ `gen_model` cũ ⇒ nếu arm B (chạy lại) sinh bằng
            # model **khác** ⇒ 3 arm dùng **khác model** ⇒ **confound model**
            # ⇒ câu đó phải bị loại khỏi mẫu số ⇒ mất dữ liệu.
            # ⇒ Ghim **đúng** model của lần chạy cũ ⇒ 3 arm cùng model ⇒
            #   không confound, **và** cache hit cho context cũ.
            pool_keys = set(gen_client.keys())
            if reuse_model and reuse_model in pool_keys:
                # D-124: **chỉ** ghim model cũ nếu nó **còn quota**.
                # Vì sao?
                # --------
                # Khi model cũ hết quota, `reused_from_old` đã bị **xoá** ở
                # trên ⇒ 3 arm đều **sinh lại** ⇒ ghim model cũ (đã chết) là
                # vô nghĩa: mọi lời gọi đều 429 ⇒ câu bị **hoãn** vô ích.
                # Đo được (18/11/2026): 17 câu kẹt ở vòng lặp
                # "lỗi hạ tầng → retry → lệch model" vì ghim model chết.
                #
                # ⇒ Chỉ ghim cứng khi model cũ **còn dùng được**; nếu không
                # thì để pool chọn model khác ⇒ 3 arm cùng model mới ⇒ vẫn
                # **không confound** (tất cả 3 arm đều sinh lại).
                if reuse_model in set(gen_client.healthy_keys()):
                    pinned_model = reuse_model
                    gen_client.pin_strict(pinned_model)
                    logger.info(
                        "Câu %s — ghim model của lần chạy cũ (%s) để giữ "
                        "tính nhất quán 3 arm",
                        qid, pinned_model,
                    )
                else:
                    logger.info(
                        "Câu %s — model cũ (%s) hết quota ⇒ sinh lại toàn bộ "
                        "bằng model khác (3 arm cùng model ⇒ không confound)",
                        qid, reuse_model,
                    )
        if isinstance(gen_client, PooledLLM) and not pinned_model:
            # Ưu tiên model **chưa từng lỗi** (quota còn) ⇒ tránh ghim phải
            # model đã cạn quota (đã có trong `errors`) vì model đó vẫn còn
            # trong pool nhưng mọi lời gọi đều 429.
            available = gen_client.healthy_keys()
            if not available:
                available = [
                    key
                    for key in gen_client.keys()
                    if key not in set(gen_client.cooldown_keys())
                ]
            if available:
                # **Thứ tự ưu tiên ổn định** (để tận dụng LLM cache):
                # danh sách `available` phụ thuộc trạng thái quota ⇒ thay đổi
                # giữa các vòng `--resume` ⇒ cùng 1 câu có thể đổi model
                # ⇒ mất cache hit ⇒ tốn token Groq lần nữa. ⇒ Sắp xếp theo
                # thứ tự **cố định** (theo tên model) rồi chọn theo seed
                # ⇒ cùng `qid` ⇒ cùng model (nếu model đó còn quota) ⇒
                # cache hit ⇒ **miễn phí**.
                ordered = gen_client.preferred_group(available)
                pinned_model = ordered[
                    random.Random(f"{SEED}:model:{qid}").randrange(len(ordered))
                ]
                gen_client.pin_strict(pinned_model)
            elif set(gen_client.keys()) <= set(gen_client.cooldown_keys()):
                # **Mọi** model đang cooldown ⇒ **không** gọi LLM (mỗi lời
                # gọi 429 vẫn tiêu 1 request trong hạn mức RPD 500/ngày/model
                # của Gemini ⇒ lãng phí 162 câu × 3 arm lời gọi vô ích).
                # Thay vào đó: **chờ tại chỗ** cho tới khi có model hồi quota
                # (rẻ hơn nhiều so với thoát ra rồi nạp lại toàn bộ index).
                logger.info(
                    "Câu %s — mọi model đang cooldown ⇒ chờ quota hồi",
                    qid,
                )
                if not gen_client.wait_for_any_quota(
                    max(0.0, float(args.quota_wait_s)),
                    deadline=quota_wait_deadline,
                ):
                    logger.info(
                        "Câu %s — hết thời gian chờ ⇒ HOÃN câu", qid,
                    )
                    deferred = True
                    deferred_qids.append(qid)
                    continue
                available = gen_client.healthy_keys()
                pinned_model = available[
                    random.Random(f"{SEED}:model:{qid}").randrange(len(available))
                ]
                gen_client.pin_strict(pinned_model)
            else:
                # Mọi model đang cooldown ⇒ ghim tạm theo quy tắc seed để
                # vẫn giữ được tính nhất quán giữa 3 arm khi pool hồi quota.
                pinned_model = gen_client.keys()[
                    random.Random(f"{SEED}:model:{qid}").randrange(len(gen_client.keys()))
                ]
                gen_client.pin_strict(pinned_model)

        # --- Retry câu lỗi hạ tầng ------------------------------------
        # Quota free tier có thể cạn giữa chừng (429). Thay vì bỏ mất câu
        # đó, chờ một lúc rồi thử lại (model đã vào cooldown nên pool sẽ
        # chọn model khác). Số lần retry có giới hạn để không treo.
        max_infra_retries = max(0, int(args.infra_retries))
        for attempt in range(max_infra_retries + 1):
            # Chỉ chạy lại **arm đã lỗi** (nếu có) — các arm thành công
            # giữ nguyên ⇒ tiết kiệm 2/3 token Groq (giới hạn 200K
            # token/ngày ⇒ đây là mấu chốt để hoàn tất 247 câu).
            attempt_outcomes = _run_question_arms(
                text=text,
                arms=arms_to_run,
                retriever=retriever,
                rag_answerer=rag_answerer,
                hybrid_answerer=hybrid_answerer,
                session_id=session_id,
                only_arms=retry_arms,
            )
            # **Gộp**: arm không chạy lại giữ kết quả lần trước (tiết kiệm
            # token ⇒ không được mất kết quả arm đã thành công).
            outcomes.update(attempt_outcomes)
            failed = [
                arm for arm in arms_to_run
                if (outcomes.get(arm) or {}).get("infrastructure_error")
            ]
            if not failed or attempt >= max_infra_retries:
                break
            logger.warning(
                "Câu %s lỗi hạ tầng ở arm %s — retry %d/%d sau %.0fs",
                qid, ",".join(failed), attempt + 1, max_infra_retries,
                args.infra_retry_wait_s,
            )
            # **Ghim lại** một model đang còn quota (không bỏ ghim) ⇒ trong
            # lần retry, cả 3 arm vẫn dùng **cùng** model ⇒ không phát sinh
            # confound model.
            #
            # Hai nhánh (quyết định **tiết kiệm token**):
            # a) Model ghim **vẫn còn quota** (lỗi tạm thời: timeout, 5xx)
            #    ⇒ giữ nguyên model ⇒ chỉ chạy lại **arm đã lỗi** ⇒ tiết
            #    kiệm 2/3 token (Groq chỉ có 200K token/ngày).
            # b) Model ghim **đã hết quota** ⇒ phải đổi model ⇒ để giữ
            #    tính nhất quán "3 arm cùng 1 model" ⇒ chạy lại **toàn bộ**.
            if isinstance(gen_client, PooledLLM):
                still_healthy = pinned_model in set(gen_client.healthy_keys())
                if still_healthy:
                    # (a) Giữ model ⇒ chỉ chạy lại arm lỗi.
                    retry_arms = failed
                    time.sleep(max(0.0, float(args.infra_retry_wait_s)))
                    continue
                retry_available = [
                    key for key in gen_client.healthy_keys() if key != pinned_model
                ]
                if not retry_available:
                    retry_available = [
                        key
                        for key in gen_client.keys()
                        if key not in set(gen_client.cooldown_keys())
                    ]
                if retry_available:
                    ordered = gen_client.preferred_group(retry_available)
                    pinned_model = ordered[
                        random.Random(f"{SEED}:model:{qid}").randrange(len(ordered))
                    ]
                    gen_client.pin_strict(pinned_model)
                    # (b) Đổi model ⇒ chạy lại **toàn bộ** câu.
                    retry_arms = None
                    # Có model khác còn quota ⇒ **không** cần chờ.
                    time.sleep(0.0)
                    continue
                # Mọi model đang cooldown ⇒ **hoãn** câu này thay vì chặn
                # cả tiến trình. Lý do: chờ 1 câu rồi cũng không giúp gì
                # (pool dùng chung ⇒ các câu sau cũng hết quota) ⇒ tốn thời
                # gian chờ vô ích. Thay vào đó: bỏ qua câu (không ghi
                # checkpoint) ⇒ vòng `--resume` sau sẽ chạy lại câu này khi
                # quota đã hồi.
                wait_s = gen_client._sleep_until_next_cooldown()
                logger.info(
                    "Câu %s — mọi model đang cooldown (hồi sau %.0fs) — HOÃN câu",
                    qid, wait_s or 0.0,
                )
                deferred = True
                break

        if deferred:
            deferred_qids.append(qid)
            continue

        # --- Retry câu bị LỆCH MODEL ----------------------------------
        # Vì sao: nếu model ghim hết quota **giữa lúc** arm đang chạy ⇒ arm
        # sau sinh bằng model khác ⇒ **confound model** ⇒ câu đó không dùng
        # được cho phép so sánh. ⇒ Chạy lại **toàn bộ** câu với model đang
        # còn quota để cả 3 arm cùng model.
        used_models = {
            (outcomes.get(arm) or {}).get("gen_model", "") for arm in arms_to_run
        }
        used_models.discard("")
        #: Model của các arm **tái dùng** (phải khớp ⇒ nếu lệch thì câu đó
        #: không dùng được cho so sánh).
        for old_entry in reused_from_old.values():
            old_model = str(old_entry.get("gen_model") or "")
            if old_model:
                used_models.add(old_model)
        max_model_retries = max(0, int(args.model_retries))
        for attempt in range(max_model_retries + 1):
            if len(used_models) <= 1:
                break
            if attempt >= max_model_retries:
                break
            logger.warning(
                "Câu %s bị lệch model (%s) — chạy lại toàn bộ câu %d/%d",
                qid, ",".join(sorted(used_models)), attempt + 1, max_model_retries,
            )
            time.sleep(max(0.0, float(args.infra_retry_wait_s)))
            if isinstance(gen_client, PooledLLM):
                retry_available = gen_client.healthy_keys()
                if not retry_available:
                    retry_available = [
                        key
                        for key in gen_client.keys()
                        if key not in set(gen_client.cooldown_keys())
                    ]
                # **Ưu tiên model của arm tái dùng** (nếu còn quota) ⇒ arm
                # chạy lại sinh bằng **cùng model** ⇒ không confound.
                if reuse_model and reuse_model in set(retry_available):
                    pinned_model = reuse_model
                elif retry_available:
                    pinned_model = retry_available[
                        random.Random(f"{SEED}:model:{qid}").randrange(len(retry_available))
                    ]
                if pinned_model:
                    gen_client.pin_strict(pinned_model)
            outcomes = _run_question_arms(
                text=text,
                arms=arms_to_run,
                retriever=retriever,
                rag_answerer=rag_answerer,
                hybrid_answerer=hybrid_answerer,
                session_id=session_id,
            )
            used_models = {
                (outcomes.get(arm) or {}).get("gen_model", "") for arm in arms_to_run
            }
            used_models.discard("")
            for old_entry in reused_from_old.values():
                old_model = str(old_entry.get("gen_model") or "")
                if old_model:
                    used_models.add(old_model)

        if args.no_judge:
            scores = {
                arm: {
                    "correctness": 0,
                    "faithfulness": 0,
                    "citation_precision": 0.0,
                    "reason": "skipped",
                }
                for arm in arms
            }
        else:
            ordered = judge_order.get(qid, arms)
            candidates = [
                {
                    "arm": arm,
                    "context": (
                        outcomes[arm]["context"]
                        if arm in outcomes
                        else str((reused_from_old.get(arm) or {}).get("arm", {}).get("context", ""))
                    ),
                    "answer": (
                        outcomes[arm]["answer"]
                        if arm in outcomes
                        else str((reused_from_old.get(arm) or {}).get("arm", {}).get("answer", ""))
                    ),
                }
                for arm in ordered
            ]
            scores = judge.score(
                question=text,
                expected_answer=str(question.get("expected_answer") or ""),
                candidates=candidates,
                question_type=str(question.get("type") or ""),
                subject_name=str(question.get("subject_name") or ""),
                context_chars=args.judge_context_chars,
            )

        # Câu còn arm lỗi hạ tầng ⇒ **không** ghi checkpoint.
        # Vì sao: checkpoint là append-only ⇒ bản ghi lỗi hạ tầng bị ghi lại
        # ở mỗi vòng `--resume` ⇒ (1) file phình to, (2) đếm `wc -l` sai,
        # (3) câu đó bị coi là "đã xong" ⇒ mất dữ liệu. ⇒ Chỉ ghi khi câu
        # **hoàn chỉnh**; câu lỗi hạ tầng được giữ trong `deferred_qids` và
        # chạy lại ở vòng sau.
        if any(
            (outcomes.get(arm) or {}).get("infrastructure_error")
            for arm in arms_to_run
        ):
            logger.info(
                "Câu %s — còn arm lỗi hạ tầng ⇒ không ghi checkpoint (chạy lại "
                "ở vòng sau)",
                qid,
            )
            deferred_qids.append(qid)
            continue

        checkpoint_record: dict[str, Any] = {"qid": qid}
        for arm in arms:
            if arm in reused_from_old:
                # Arm **tái dùng**: giữ nguyên `context` + `answer` + `gen_model`
                # của lần chạy cũ (tái lập được vì arm này không đổi) ⇒ nhưng
                # điểm là **điểm mới** (judge hiện tại đã chấm lại).
                old_entry = reused_from_old[arm]
                old_arm = dict(old_entry.get("arm") or {})
                old_arm["reused_from_previous_run"] = True
                record = {
                    "qid": qid,
                    "question": text,
                    "type": question.get("type"),
                    "expected_answer": question.get("expected_answer"),
                    "evidence_doc_id": question.get("evidence_doc_id"),
                    "evidence_section": question.get("evidence_section"),
                    "gen_model": old_entry.get("gen_model") or pinned_model,
                    "gen_model_pinned": pinned_model,
                    "arm": old_arm,
                    "judge": scores.get(
                        arm,
                        {
                            "correctness": 0,
                            "faithfulness": 0,
                            "citation_precision": 0.0,
                            "reason": "missing",
                        },
                    ),
                }
                all_results[arm].append(record)
                checkpoint_record[arm] = record
                continue
            # Model **thực sự** đã sinh câu trả lời của arm này (không phải
            # model dự định ghim) ⇒ để kiểm chứng "3 arm cùng 1 model".
            used_model = (outcomes[arm] or {}).get("gen_model") or pinned_model
            record = {
                "qid": qid,
                "question": text,
                "type": question.get("type"),
                "expected_answer": question.get("expected_answer"),
                "evidence_doc_id": question.get("evidence_doc_id"),
                "evidence_section": question.get("evidence_section"),
                "gen_model": used_model,
                "gen_model_pinned": pinned_model,
                "arm": outcomes[arm],
                "judge": scores.get(
                    arm,
                    {
                        "correctness": 0,
                        "faithfulness": 0,
                        "citation_precision": 0.0,
                        "reason": "missing",
                    },
                ),
            }
            all_results[arm].append(record)
            checkpoint_record[arm] = record
        checkpoint_handle.write(json.dumps(checkpoint_record, ensure_ascii=False) + "\n")
        checkpoint_handle.flush()
        if index % 10 == 0:
            logger.info("đã chạy %d/%d câu", index, len(questions))

    checkpoint_handle.close()
    # Lưu trạng thái cooldown để vòng sau bỏ qua model đã biết chết.
    if isinstance(gen_client, PooledLLM):
        gen_client.save_state(gen_state_path)
    if isinstance(judge_client, PooledLLM):
        judge_client.save_state(judge_state_path)
    if deferred_qids:
        # Ghi mốc quota hồi ⇒ supervisor ngủ đúng tới lúc đó thay vì poll
        # mỗi 60s (mỗi vòng nạp lại 65K chunk + embedding ~60s).
        #
        # Vì sao lấy **max** chứ không phải min?
        # Một câu chỉ chạy được khi có **cả**:
        #   (1) model **sinh** câu trả lời còn quota, VÀ
        #   (2) model **judge** còn quota (nếu không, câu bị hoãn ngay ở
        #       bước pre-check judge ⇒ tốn 0 token sinh).
        # ⇒ Thời điểm sớm nhất có thể chạy tiếp = **max** (hồi gen, hồi
        # judge). Nếu lấy min ⇒ supervisor thức dậy sớm khi Groq hồi nhưng
        # Gemini (judge) vẫn cạn ⇒ mọi câu lại bị hoãn ⇒ vòng `--resume`
        # tiếp theo chỉ để nạp lại index rồi hoãn tiếp ⇒ lãng phí hàng chục
        # vòng × 60s.
        now = time.time()

        def _earliest_recovery(pool: Any) -> float:
            """Mốc hồi sớm nhất của 1 pool (0 nếu không có model nào cooldown).

            Args:
                pool: Pool LLM.

            Returns:
                Epoch giây của mốc hồi sớm nhất.
            """
            if not isinstance(pool, PooledLLM):
                return 0.0
            return min(
                (
                    until
                    for until in pool._cooldown_until.values()
                    if until > now
                ),
                default=0.0,
            )

        gen_recovery = _earliest_recovery(gen_client)
        judge_recovery = _earliest_recovery(judge_client)
        next_available = max(gen_recovery, judge_recovery)
        state_path = checkpoint_path.with_name(
            checkpoint_path.stem + ".deferred.json"
        )
        try:
            state_path.write_text(
                json.dumps(
                    {
                        "deferred_qids": deferred_qids,
                        "next_available_epoch": next_available,
                        "n_deferred": len(deferred_qids),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
        logger.info(
            "ĐÃ HOÃN %d câu (mọi model hết quota) — quota hồi sau %.0fs "
            "(sinh: +%.0fs, judge: +%.0fs) — chạy lại với --resume",
            len(deferred_qids),
            max(0.0, next_available - now),
            max(0.0, gen_recovery - now),
            max(0.0, judge_recovery - now),
        )
    for arm in arms:
        records = all_results[arm]
        all_metrics[arm] = aggregate(records)
        out_dir = REPO_ROOT / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = REPO_ROOT / "data" / "eval" / f"{args.out_prefix}_{arm}.jsonl"
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Báo cáo.
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{args.out_prefix}_{stamp}.json"
    gen_pool_info: dict[str, Any] = {}
    if isinstance(gen_client, PooledLLM):
        gen_pool_info = {
            "models": gen_client.keys(),
            "calls_by_model": dict(gen_client.calls_by_model),
            "errors_by_model": dict(gen_client.errors),
        }
    judge_pool_info: dict[str, Any] = {}
    if isinstance(judge_client, PooledLLM):
        judge_pool_info = {
            "models": judge_client.keys(),
            "calls_by_model": dict(judge_client.calls_by_model),
            "errors_by_model": dict(judge_client.errors),
        }
    json_path.write_text(
        json.dumps(
            {
                "_meta": {
                    "phase": 16,
                    "mo_ta": "Kết quả đánh giá RAG: A vs B vs B−",
                    "qa_set": str(qa_path),
                    "n_questions": len(questions),
                    "arms": arms,
                    "judge_model": llm_config.get("providers", {})
                    .get("gemini", {})
                    .get("model"),
                    "gen_pool": gen_pool_info,
                    "judge_pool": judge_pool_info,
                    "ngay_do": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "elapsed_s": round(time.time() - started, 1),
                },
                "metrics": all_metrics,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path = write_markdown(reports_dir / f"{args.out_prefix}_{stamp}.md", all_metrics, arms)
    logger.info("Ghi %s + %s", json_path, md_path)
    return 0


def write_markdown(path: Path, metrics: dict[str, Any], arms: list[str]) -> Path:
    """Viết báo cáo markdown so sánh các arm.

    Args:
        path: Đường dẫn file `.md`.
        metrics: Chỉ số theo arm.
        arms: Danh sách arm.

    Returns:
        Đường dẫn đã ghi.
    """
    labels = {"A": "A — Vanilla RAG", "B": "B — Hybrid GraphRAG", "B-": "B− — Hybrid không KG"}
    lines: list[str] = [
        "# Đánh giá RAG — Vanilla RAG vs Hybrid GraphRAG",
        "",
        f"- Ngày: {time.strftime('%Y-%m-%d')}",
        f"- Arms: {', '.join(arms)}",
        "",
        "## Chỉ số tổng hợp",
        "",
        "| Chỉ số | " + " | ".join(labels.get(a, a) for a in arms) + " |",
        "|---|" + "---|" * len(arms),
    ]
    rows = [
        ("Số câu (tính điểm)", "n"),
        ("Số câu lỗi hạ tầng (loại)", "n_infra_errors"),
        ("correctness (0–2)", "correctness_mean"),
        ("correctness_rate", "correctness_rate"),
        ("faithfulness (0–2)", "faithfulness_mean"),
        ("faithfulness_rate", "faithfulness_rate"),
        ("citation_precision", "citation_precision"),
        ("no_data_accuracy", "no_data_accuracy"),
        ("abstain_with_evidence (lỗi)", "abstain_with_evidence"),
        ("abstain_total", "abstain_total"),
        ("no_data_retried", "no_data_retried"),
        ("latency p50 (ms)", "latency_p50"),
        ("latency p95 (ms)", "latency_p95"),
        ("context_tokens (TB)", "context_tokens_mean"),
    ]
    for label, key in rows:
        values = []
        for arm in arms:
            value = (metrics.get(arm) or {}).get(key)
            values.append("—" if value is None else str(value))
        lines.append(f"| {label} | " + " | ".join(values) + " |")

    lines += ["", "## Theo dạng câu hỏi (correctness)", ""]
    types: list[str] = []
    for arm in arms:
        for qtype in ((metrics.get(arm) or {}).get("by_type") or {}):
            if qtype not in types:
                types.append(qtype)
    lines.append("| Dạng | " + " | ".join(labels.get(a, a) for a in arms) + " |")
    lines.append("|---|" + "---|" * len(arms))
    for qtype in types:
        values = []
        for arm in arms:
            bucket = ((metrics.get(arm) or {}).get("by_type") or {}).get(qtype) or {}
            values.append(
                f"{bucket.get('correctness', '—')} (n={bucket.get('n', 0)})"
            )
        lines.append(f"| {qtype} | " + " | ".join(values) + " |")

    lines += [
        "",
        "## `abstain_with_evidence` theo nhóm (Phase 19 — lỗi 'không có' khi context có bằng chứng)",
        "",
        "| Dạng | " + " | ".join(labels.get(a, a) for a in arms) + " |",
        "|---|" + "---|" * len(arms),
    ]
    for qtype in types:
        values = []
        for arm in arms:
            bucket = ((metrics.get(arm) or {}).get("by_type") or {}).get(qtype) or {}
            values.append(
                f"{bucket.get('abstain_with_evidence', 0)}/{bucket.get('abstain', 0)}"
            )
        lines.append(f"| {qtype} | " + " | ".join(values) + " |")

    lines += [
        "",
        "## Kết luận",
        "",
    ]
    if "A" in metrics and "B" in metrics:
        a_corr = (metrics["A"] or {}).get("correctness_mean", 0)
        b_corr = (metrics["B"] or {}).get("correctness_mean", 0)
        delta = b_corr - a_corr
        lines.append(
            f"- `correctness`: B {b_corr} vs A {a_corr} ⇒ chênh lệch **{delta:+.4f}**."
        )
        if "B-" in metrics:
            bm_corr = (metrics["B-"] or {}).get("correctness_mean", 0)
            lines.append(
                f"- Đóng góp của **đồ thị** (B vs B−): {b_corr - bm_corr:+.4f} "
                f"(B− = {bm_corr})."
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    sys.exit(main())

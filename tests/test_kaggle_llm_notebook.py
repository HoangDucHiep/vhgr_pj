"""Unit test cho phần parse JSON của notebook Kaggle LLM (D-091).

Notebook `notebooks/kaggle/06_llm_extract_kaggle/notebook.ipynb` được sinh
từ `scripts/build_kaggle_llm_notebook.py`. Test này **trích** đúng các hàm
parse từ builder để bảo đảm logic đó được kiểm thử (không chạy notebook).

Bối cảnh: đo được 16/11/2026 — kernel trả `payload` **không phải None**
(top-level JSON array) ⇒ fail-fast cũ **không** kích hoạt, nhưng
`payload.get("triples")` không tồn tại ⇒ **0/0 triple**.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BUILDER = REPO_ROOT / "scripts" / "build_kaggle_llm_notebook.py"


def _load_notebook_functions() -> dict:
    """Trích các hàm parse từ mã nguồn notebook trong builder.

    Returns:
        Dict tên hàm → object hàm.
    """
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    code = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(t, "id", "") == "EXTRACT_CODE" for t in node.targets
        ):
            code = node.value.value
            break
    assert code is not None, "Không tìm thấy EXTRACT_CODE trong builder"

    # Chỉ lấy các hàm cần test.
    wanted = {"parse_json", "_scan_balanced", "normalize_payload"}
    module = ast.parse(code)
    selected = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {n.name for n in selected} == wanted, "Thiếu hàm parse trong notebook"

    namespace: dict = {"json": json, "re": re}
    exec(  # noqa: S102 - chạy code do chính repo sinh ra
        compile(ast.Module(body=selected, type_ignores=[]), "<notebook>", "exec"),
        namespace,
    )
    return namespace


@pytest.fixture(scope="module")
def funcs() -> dict:
    """Fixture các hàm parse.

    Returns:
        Dict tên hàm → object hàm.
    """
    return _load_notebook_functions()


def test_parse_json_object_wrapper(funcs) -> None:
    """Payload đúng dạng prompt ⇒ trả về dict với key `triples`."""
    raw = '{"triples": [{"sentence_index": 1, "subject": "A", "relation": "cha_cua", "object": "B"}]}'
    result = funcs["parse_json"](raw)
    assert result is not None
    assert len(result["triples"]) == 1
    assert result["triples"][0]["subject"] == "A"


def test_parse_json_top_level_array(funcs) -> None:
    """Top-level JSON array ⇒ **phải** ra triple (lỗi 0/0 của 16/11)."""
    raw = '[{"sentence_index": 1, "subject": "A", "relation": "cha_cua", "object": "B"}]'
    result = funcs["parse_json"](raw)
    assert result is not None, "Payload array phải parse được"
    assert len(result["triples"]) == 1
    assert result["triples"][0]["relation"] == "cha_cua"


def test_parse_json_fenced_array(funcs) -> None:
    """Array bọc trong markdown fence ⇒ vẫn ra triple."""
    raw = '```json\n[{"sentence_index": 2, "subject": "A", "relation": "me_cua", "object": "C"}]\n```'
    result = funcs["parse_json"](raw)
    assert result is not None
    assert len(result["triples"]) == 1


def test_parse_json_think_tags_stripped(funcs) -> None:
    """`<think>` của Qwen3 phải được loại bỏ trước khi parse."""
    raw = (
        "<think>Để tôi suy nghĩ</think>\n"
        '{"triples": [{"sentence_index": 1, "subject": "A", "relation": "vo_cua", "object": "D"}]}'
    )
    result = funcs["parse_json"](raw)
    assert result is not None
    assert len(result["triples"]) == 1


def test_parse_json_alternative_keys(funcs) -> None:
    """Các key thay thế (`relations`, `results`, `data`) ⇒ ra triple."""
    for key in ("relations", "results", "data", "items"):
        raw = json.dumps(
            {key: [{"sentence_index": 1, "subject": "A", "relation": "ke_vi", "object": "B"}]}
        )
        result = funcs["parse_json"](raw)
        assert result is not None, key
        assert len(result["triples"]) == 1, key


def test_parse_json_single_triple_object(funcs) -> None:
    """Một triple đơn ở top-level ⇒ vẫn ra 1 triple."""
    raw = '{"sentence_index": 1, "subject": "A", "relation": "lap_ra", "object": "E"}'
    result = funcs["parse_json"](raw)
    assert result is not None
    assert len(result["triples"]) == 1


def test_parse_json_returns_none_on_garbage(funcs) -> None:
    """Text không phải JSON ⇒ `None` (để fail-fast kích hoạt)."""
    assert funcs["parse_json"]("Không phải JSON, chỉ là văn bản.") is None


def test_normalize_payload_never_raises(funcs) -> None:
    """`normalize_payload` phải trả dict với key `triples` cho mọi input."""
    normalize = funcs["normalize_payload"]
    for payload in ([], {}, {"a": 1}, "text", 42, None, {"triples": None}):
        result = normalize(payload)
        assert isinstance(result, dict)
        assert isinstance(result["triples"], list)

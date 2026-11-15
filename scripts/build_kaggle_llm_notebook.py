#!/usr/bin/env python
"""Sinh notebook Kaggle trích xuất quan hệ bằng LLM mở (Phase 8 — D2).

Model: `Qwen/Qwen3-8B` nạp 4-bit bằng `bitsandbytes` (fallback `gpt-oss-20b`).
Ràng buộc bắt buộc: `evidence` phải là **substring** của câu đầu vào.

Cách dùng:
    python scripts/build_kaggle_llm_notebook.py
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = REPO_ROOT / "notebooks" / "kaggle"

EXTRACT_CODE = r'''
# %% [markdown]
# ## VHGR Phase 8 — Trích xuất quan hệ bằng LLM mở (Qwen3-8B 4-bit)
#
# **Quy trắc nghiệm** (`docs/09` §Phase 8 mục 4):
# - Chunk **15 câu/request**, prompt ép JSON.
# - **Bắt buộc**: `evidence` phải là *substring* của câu đầu vào → nếu không,
#   **loại triple** và **đếm** số lượt loại.
# - Ghi `re_llm_kaggle.jsonl` ra `/kaggle/working` để tải về.

# %%
import json
import os
import re
import time
from pathlib import Path

import torch

MODEL_ID = os.environ.get("LLM_MODEL", "Qwen/Qwen3-8B")

# Kernel Kaggle **không có DNS** (D-038) → không tải được từ huggingface.co.
# Thứ tự ưu tiên nguồn model:
#   1. `LLM_MODEL_PATH` — thư mục model đã bundle trong dataset (khuyến nghị).
#   2. `/kaggle/input/vhgr-re-data/models_hf/<tên model>` — bundle sẵn trong dataset.
#   3. Kaggle Models (`manojkumarcs28/qwen3-8b`) — mount qua `model_sources`.
#   4. `MODEL_ID` trên HuggingFace — chỉ khi kernel CÓ internet.
#:
# LƯU Ý (đo được 16/11/2026): Kaggle mount **Kaggle Models** vào thư mục có
# tên **ngẫu nhiên** (vd `/kaggle/input/qwen3-8b-1`), **không phải** tên cố
# định ⇒ đường dẫn cứng `/kaggle/input/qwen3-8b` **không tồn tại** ⇒
# notebook rơi về HuggingFace và phải tải **16,4 GB** (mất ~5 phút GPU mỗi
# lần chạy). Vì vậy `resolve_model_source()` **quét** `/kaggle/input` thay vì
# đoán đường dẫn.
MODEL_CANDIDATES = [
    os.environ.get("LLM_MODEL_PATH", ""),
    "/kaggle/input/vhgr-re-data/models_hf/" + MODEL_ID.split("/")[-1],
    "/kaggle/input/qwen3-8b",
]

CORPUS_PATH = os.environ.get(
    "LLM_CORPUS", "/kaggle/input/vhgr-re-data/re_model_input.jsonl.gz"
)
OUT_PATH = Path("/kaggle/working/re_llm_kaggle.jsonl")
CHUNK_SIZE = int(os.environ.get("LLM_CHUNK_SIZE", "15"))
#: Số câu tối đa. Đo được 15/11/2026: **95 s/request** (chunk 15 câu) trên
#: Qwen3-8B 4-bit ⇒ 5.000 câu = 333 request ≈ **8,8 giờ**. Giới hạn 600 câu
#: (40 request) ≈ **1,1 giờ** — đủ làm baseline LLM bulk mà không chiếm GPU
#: quá lâu (kernel này dùng **2 GPU T4** ⇒ chặn kernel suy luận RE).
LIMIT = int(os.environ.get("LLM_LIMIT", "600"))
MAX_NEW_TOKENS = int(os.environ.get("LLM_MAX_NEW_TOKENS", "1024"))
#: **Ngân sách thời gian** (giây) cho vòng suy luận. Quota GPU Kaggle của mỗi
#: tài khoản là 30 h/tuần; khi hết, kernel bị **cưỡng chế dừng** → mất sạch
#: output nếu chưa ghi file. Đo được 15/11/2026: `timeUsed` của
#: `hoanghiep421` đã vượt `totalTimeAllowed` (44.694 s / 21.600 s) ⇒ không
#: push được kernel mới. Vì vậy notebook **tự dừng** trước khi hết quota và
#: **checkpoint** output ra file sau mỗi request ⇒ còn quota thì vẫn còn kết quả.
TIME_BUDGET_S = int(os.environ.get("LLM_TIME_BUDGET_S", "0"))  # 0 = không giới hạn

RELATIONS = [
    "cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua",
    "thuoc_trieu_dai", "ke_vi", "giu_chuc_vu", "lap_ra",
    "chi_huy_tran", "tham_gia_tran", "danh_bai",
    "dien_ra_tai", "sinh_tai", "mat_tai",
    "sinh_nam", "mat_nam", "dong_doi_tai",
]

print("Torch:", torch.__version__, "| CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))
    print("VRAM:", round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1), "GB")

# %%
# Cài `bitsandbytes` để nạp 4-bit (kernel **có** internet — đo được 15/11/2026).
# Không có nó → 4-bit fail → fallback bf16 16-bit (16,4 GB trên T4 15,6 GB → rất
# chậm và rủi ro OOM). Đo được: 5 request / 796s / 0 req/s ở bf16.
try:
    import bitsandbytes  # noqa: F401

    print("bitsandbytes đã có sẵn:", bitsandbytes.__version__)
except ImportError:
    import subprocess
    import sys

    print("Đang cài bitsandbytes...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "-U", "bitsandbytes>=0.46.1"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    print("pip:", result.returncode, (result.stdout or result.stderr)[-300:])

# %%
from transformers import AutoModelForCausalLM, AutoTokenizer


def resolve_model_source():
    """Chọn nguồn model khả dụng (ưu tiên bundle offline).

    Ngoài các đường dẫn cứng, **quét** `/kaggle/input` tìm thư mục chứa
    `config.json` + `*.safetensors` (Kaggle mount Models vào thư mục tên
    ngẫu nhiên, đo được 16/11/2026).

    Returns:
        Đường dẫn nguồn model.
    """
    for candidate in MODEL_CANDIDATES:
        if candidate and Path(candidate).is_dir():
            print("Dùng model bundle:", candidate)
            return candidate

    # Quét `/kaggle/input` — Kaggle Models mount vào tên thư mục ngẫu nhiên.
    input_root = Path("/kaggle/input")
    if input_root.is_dir():
        for path in sorted(input_root.iterdir()):
            if not path.is_dir():
                continue
            has_config = (path / "config.json").is_file()
            has_weights = any(path.glob("*.safetensors")) or any(path.glob("*.bin"))
            if has_config and has_weights:
                print("Dùng model Kaggle mount:", path)
                return str(path)

    print("Không có bundle cục bộ → dùng:", MODEL_ID, "(cần internet)")
    return MODEL_ID


MODEL_SRC = resolve_model_source()

print("Đang nạp tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_SRC, trust_remote_code=True)

print("Đang nạp model 4-bit...")
try:
    from transformers import BitsAndBytesConfig

    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_SRC,
        quantization_config=quant_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    print("Nạp 4-bit thành công (bitsandbytes)")
except Exception as exc:  # noqa: BLE001
    print("4-bit thất bại:", exc)
    print("Fallback sang bf16 16-bit...")
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_SRC,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

model.eval()
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
print("Model:", MODEL_SRC)

# %%
def load_corpus(path, limit):
    """Nạp câu (kèm `sentence_id`) từ artifact đã mã hoá."""
    import gzip

    opener = gzip.open if str(path).endswith(".gz") else open
    rows = []
    seen = set()
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            sid = record.get("sentence_id", "")
            if sid in seen:
                continue
            seen.add(sid)
            rows.append(record)
            if limit and len(rows) >= limit:
                break
    return rows


corpus_candidates = sorted(
    Path("/kaggle/input").rglob("re_model_input.jsonl*")
)
if not corpus_candidates:
    raise FileNotFoundError("Không tìm thấy re_model_input.jsonl* trong /kaggle/input")
CORPUS_PATH = corpus_candidates[0]
print("File corpus:", CORPUS_PATH)

rows = load_corpus(CORPUS_PATH, LIMIT)
print("Đã nạp", len(rows), "câu")
# %%
SYSTEM = (
    "Bạn là chuyên gia trích xuất tri thức lịch sử Việt Nam. "
    "Chỉ trả về JSON hợp lệ, không thêm giải thích, không thêm markdown."
)


def build_prompt(sentences):
    """Dựng prompt ép JSON cho một chunk câu."""
    relation_list = "\n".join(f"- {r}" for r in RELATIONS)
    blocks = [f"[{i}] {s}" for i, s in enumerate(sentences, start=1)]
    joined = "\n".join(blocks)
    return f"""Trích xuất quan hệ lịch sử từ các câu dưới đây.

DANH SÁCH QUAN HỆ HỢP LỆ (chỉ dùng đúng các tên này):
{relation_list}

QUY TẮC:
1. Chỉ trích xuất quan hệ rõ ràng trong câu. Không suy đoán.
2. `evidence` phải là TRÍCH NGUYÊN VĂN một đoạn con trong câu.
3. `confidence` là số trong [0,1].
4. `sentence_index` là số thứ tự câu trong danh sách.

ĐỊNH DẠNG JSON BẮT BUỘC:
{{"triples":[{{"sentence_index":1,"subject":"...","relation":"...","object":"...","evidence":"...","confidence":0.9}}]}}

CÁC CÂU:
{joined}
"""


def parse_json(raw):
    """Parse JSON bọc trong markdown fence hoặc lẫn trong văn bản.

    Trả về **object đã chuẩn hoá**: luôn là dict có key ``triples`` là list.
    """
    text = raw.strip()
    # Bỏ `<think>...</think>` nếu model vẫn bật thinking (phòng thủ).
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    payload = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = _scan_balanced(text)
    if payload is None:
        return None
    return normalize_payload(payload)


def _scan_balanced(text):
    """Tìm object/array JSON cân bằng đầu tiên trong text.

    Args:
        text: Text thô.

    Returns:
        Payload đã parse, hoặc ``None``.
    """
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            in_string = False
            escaped = False
            for index in range(start, len(text)):
                char = text[index]
                if escaped:
                    escaped = False
                    continue
                if char == "\\":
                    escaped = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == opener:
                    depth += 1
                elif char == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : index + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    return None


def normalize_payload(payload):
    """Chuẩn hoá payload về dạng ``{"triples": [...]}``.

    Model LLM mở có thể trả nhiều hình dạng:
    - ``{"triples": [...]}`` (đúng như prompt);
    - ``[{...}, {...}]`` — **JSON array ở top-level** (đo được 16/11/2026:
      payload không phải ``None`` ⇒ không kích hoạt fail-fast, nhưng
      ``payload.get("triples")`` không tồn tại ⇒ **0/0 triple**);
    - ``{"relations": [...]}`` / ``{"results": [...]}`` / ``{"data": [...]}``;
    - ``{...}`` — **một** triple đơn.

    Args:
        payload: Payload thô.

    Returns:
        Dict ``{"triples": list}``.
    """
    if isinstance(payload, list):
        return {"triples": [item for item in payload if isinstance(item, dict)]}
    if not isinstance(payload, dict):
        return {"triples": []}
    for key in ("triples", "relations", "results", "data", "items", "output"):
        value = payload.get(key)
        if isinstance(value, list):
            return {"triples": [item for item in value if isinstance(item, dict)]}
    # Một triple đơn: có cả subject + relation + object.
    if {"subject", "relation", "object"} <= set(payload.keys()):
        return {"triples": [payload]}
    # Dict lồng nhau: tìm list đầu tiên trong các value.
    for value in payload.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return {"triples": [item for item in value if isinstance(item, dict)]}
    return {"triples": []}


print("Prompt mẫu:\n", build_prompt(["Lý Thường Kiệt là một nhà quân sự thời Lý."])[:400])

# %%
@torch.no_grad()
def generate(prompt):
    """Sinh phản hồi từ mô hình.

    Qwen3 là model **hybrid reasoning**: mặc định nó sinh `<think>...</think>`
    trước khi trả lời → output không phải JSON → parse fail (đo được 0/0 triple).
    Vì vậy **tắt thinking mode** (`enable_thinking=False`).
    """
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": prompt},
    ]
    template_kwargs = {}
    if "qwen3" in MODEL_ID.lower():
        template_kwargs["enable_thinking"] = False
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, **template_kwargs
    )
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    output = model.generate(
        **inputs,
        max_new_tokens=MAX_NEW_TOKENS,
        do_sample=False,
        temperature=None,
        top_p=None,
        top_k=None,
        pad_token_id=tokenizer.pad_token_id,
    )
    generated = output[0][inputs["input_ids"].shape[1] :]
    return tokenizer.decode(generated, skip_special_tokens=True)


# %% [markdown]
# ## Chạy trích xuất

# %%
counters = {"total": 0, "kept": 0, "rejected_evidence": 0,
             "rejected_relation": 0, "rejected_sentence": 0}
n_requests = 0
started = time.time()

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Fail-fast: 3 request đầu mà không parse được JSON → in raw output để chẩn đoán
# rồi dừng (tránh mất 12 h phiên GPU mà ra 0 triple).
n_parse_fail = 0
stop_reason = "het-limit"
#: Lưu raw output của vài request đầu ⇒ **chẩn đoán được** khi 0 triple.
RAW_PATH = OUT_PATH.with_name("re_llm_kaggle_raw.jsonl")
raw_handle = RAW_PATH.open("w", encoding="utf-8")
with OUT_PATH.open("w", encoding="utf-8") as handle:
    for start_index in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[start_index : start_index + CHUNK_SIZE]
        sentences = [str(r.get("text", "")) for r in chunk]
        if not any(s.strip() for s in sentences):
            continue

        # **Ngân sách thời gian**: dừng TRƯỚC khi hết quota GPU Kaggle để
        # không bị cưỡng chế dừng giữa chừng (mất sạch output).
        if TIME_BUDGET_S and (time.time() - started) >= TIME_BUDGET_S:
            stop_reason = "het-ngan-sach-thoi-gian"
            print(f"Dừng do ngân sách thời gian ({TIME_BUDGET_S}s) sau {n_requests} request.")
            break

        raw = generate(build_prompt(sentences))
        n_requests += 1
        payload = parse_json(raw)

        if n_requests <= 5:
            raw_handle.write(json.dumps({
                "request": n_requests,
                "raw": raw[:8000],
                "n_triples": 0 if payload is None else len(payload.get("triples", [])),
            }, ensure_ascii=False) + "\n")
            raw_handle.flush()
            os.fsync(raw_handle.fileno())

        if payload is None:
            n_parse_fail += 1
            if n_parse_fail <= 3:
                print(f"--- RAW OUTPUT (request {n_requests}, {len(raw)} ký tự) ---")
                print(raw[:2000])
                print("--- END RAW ---")
            if n_parse_fail >= 3:
                raise RuntimeError(
                    "3 request liên tiếp không parse được JSON — dừng để chẩn đoán. "
                    "Nguyên nhân thường gặp: model sinh '<think>' (Qwen3 hybrid "
                    "reasoning) → cần enable_thinking=False."
                )

        triples = []
        if isinstance(payload, dict) and isinstance(payload.get("triples"), list):
            for triple in payload["triples"]:
                if not isinstance(triple, dict):
                    continue
                counters["total"] += 1
                try:
                    position = int(triple.get("sentence_index", 0))
                except (TypeError, ValueError):
                    position = 0

                evidence = str(triple.get("evidence", "") or "").strip()
                # **Suy vị trí câu từ evidence** khi model không trả
                # `sentence_index` (hoặc trả sai): evidence là substring của
                # đúng một câu ⇒ vị trí đó là vị trí thật.
                if position < 1 or position > len(sentences):
                    hits = [i for i, s in enumerate(sentences, start=1)
                            if evidence and evidence in s]
                    if len(hits) == 1:
                        position = hits[0]
                    else:
                        counters["rejected_sentence"] += 1
                        continue
                sentence = sentences[position - 1]

                # **BẮT BUỘC**: evidence phải là substring của câu đầu vào
                if not evidence or evidence not in sentence:
                    counters["rejected_evidence"] += 1
                    continue

                relation = str(triple.get("relation", "") or "").strip().lower()
                relation = relation.replace("-", "_").replace(" ", "_")
                if relation not in RELATIONS:
                    counters["rejected_relation"] += 1
                    continue

                subject = str(triple.get("subject", "") or "").strip()
                object_ = str(triple.get("object", "") or "").strip()
                if not subject or not object_:
                    counters["rejected_evidence"] += 1
                    continue

                try:
                    confidence = float(triple.get("confidence", 0.5))
                except (TypeError, ValueError):
                    confidence = 0.5
                confidence = max(0.0, min(1.0, round(confidence, 4)))

                counters["kept"] += 1
                triples.append({
                    "sentence_index": position,
                    "subject": subject,
                    "relation": relation,
                    "object": object_,
                    "evidence_sentence": evidence,
                    "confidence": confidence,
                })

        by_sentence = {}
        for triple in triples:
            by_sentence.setdefault(triple["sentence_index"], []).append(triple)

        for position, record in enumerate(chunk, start=1):
            pairs = by_sentence.get(position)
            if not pairs:
                continue
            handle.write(json.dumps({
                "sentence_id": str(record.get("sentence_id", "")),
                "text": str(record.get("text", "")),
                "pairs": [{
                    "subject": t["subject"],
                    "relation": t["relation"],
                    "object": t["object"],
                    "confidence": t["confidence"],
                    "evidence_sentence": t["evidence_sentence"],
                    "method": "llm",
                } for t in pairs],
            }, ensure_ascii=False) + "\n")

        if n_requests % 5 == 0:
            elapsed = time.time() - started
            print(f"{n_requests} request | giữ {counters['kept']}/{counters['total']} "
                  f"| {elapsed:.0f}s | {n_requests/elapsed:.2f} req/s")

        # **Fail-fast khi parse OK nhưng 0 triple**: dấu hiệu payload có hình
        # dạng lạ mà `normalize_payload` chưa xử lý được (đo được 16/11/2026:
        # `payload` không None ⇒ không kích hoạt fail-fast cũ, nhưng
        # `payload.get("triples")` vắng mặt ⇒ 0/0 triple). Dừng sớm thay vì
        # đốt hết quota GPU.
        if n_requests >= 3 and counters["total"] == 0:
            raise RuntimeError(
                f"3 request đầu parse được JSON nhưng không có triple nào "
                f"(counters={counters}). Xem file raw mẫu {RAW_PATH.name} để "
                f"chẩn đoán hình dạng payload."
            )
        # **Checkpoint**: `flush` + `fsync` sau mỗi request ⇒ nếu kernel bị
        # cưỡng chế dừng (hết quota) thì phần đã ghi vẫn còn trên đĩa.
        handle.flush()
        os.fsync(handle.fileno())

raw_handle.flush()
os.fsync(raw_handle.fileno())
raw_handle.close()

print(f"Hoàn tất: {n_requests} request trong {time.time()-started:.0f}s")
print("Lý do dừng:", stop_reason)
print("Bộ đếm:", counters)
print("Đã ghi:", OUT_PATH)
print("Raw mẫu:", RAW_PATH)

# %%
stats_path = OUT_PATH.with_suffix(".stats.json")
stats_path.write_text(json.dumps({
    "_meta": {
        "model": MODEL_SRC,
        "model_id": MODEL_ID,
        "chunk_size": CHUNK_SIZE,
        "n_requests": n_requests,
        "n_parse_fail": n_parse_fail,
        "n_sentences": len(rows),
        "elapsed_s": round(time.time() - started, 1),
        "stop_reason": stop_reason,
        "time_budget_s": TIME_BUDGET_S,
        "throughput_sentences_per_s": round(
            len(rows) / max(time.time() - started, 1), 3),
    },
    "counters": counters,
}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print("Đã ghi:", stats_path)

import shutil
shutil.make_archive("/kaggle/working/re_llm_kaggle", "zip", str(OUT_PATH.parent))
print("Đã đóng gói kết quả.")
'''

INTRO = """# VHGR Phase 8 — Trích xuất quan hệ bằng LLM mở (Qwen3-8B 4-bit)

- Model: `Qwen/Qwen3-8B`, nạp **4-bit** bằng `bitsandbytes` (fallback bf16).
- Chunk **15 câu/request**, prompt ép JSON.
- **Bắt buộc**: `evidence` phải là *substring* của câu đầu vào → nếu không,
  **loại triple** và **đếm** số lượt loại.
- Ghi `re_llm_kaggle.jsonl` + `re_llm_kaggle.stats.json` ra `/kaggle/working`.
"""


def build_notebook(limit: int = 600, time_budget_s: int = 0) -> dict:
    """Dựng notebook Kaggle trích xuất LLM.

    Args:
        limit: Số câu tối đa xử lý (đóng cứng vào notebook).
        time_budget_s: Ngân sách thời gian suy luận (giây, 0 = không giới hạn).

    Returns:
        Dict notebook theo định dạng nbformat 4.
    """
    code = EXTRACT_CODE
    if limit:
        code = code.replace(
            'LIMIT = int(os.environ.get("LLM_LIMIT", "600"))',
            f'LIMIT = int(os.environ.get("LLM_LIMIT", "{limit}"))',
        )
    if time_budget_s:
        code = code.replace(
            'TIME_BUDGET_S = int(os.environ.get("LLM_TIME_BUDGET_S", "0"))',
            f'TIME_BUDGET_S = int(os.environ.get("LLM_TIME_BUDGET_S", "{time_budget_s}"))',
        )
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": INTRO.splitlines(keepends=True),
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": code.splitlines(keepends=True),
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    """Sinh notebook + metadata.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Sinh notebook Kaggle trích xuất LLM (Qwen3-8B 4-bit).",
    )
    parser.add_argument(
        "--account",
        default=os.environ.get("KAGGLE_USERNAME", "hoanghiep421"),
        help="Tài khoản Kaggle sở hữu kernel (owner/slug).",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Dataset nguồn (owner/slug). Mặc định: <account>/vhgr-re-data.",
    )
    parser.add_argument(
        "--kernel-slug",
        default="vhgr-phase-8-llm-extract-qwen3-8b-4bit",
        help="Slug kernel (phần sau owner/).",
    )
    parser.add_argument(
        "--time-budget-s",
        type=int,
        default=int(os.environ.get("LLM_TIME_BUDGET_S", "0")),
        help="Ngân sách thời gian suy luận (giây); 0 = không giới hạn.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=int(os.environ.get("LLM_LIMIT", "600")),
        help="Số câu tối đa xử lý.",
    )
    args = parser.parse_args()

    folder = NOTEBOOK_DIR / "06_llm_extract_kaggle"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "notebook.ipynb").write_text(
        json.dumps(
            build_notebook(limit=args.limit, time_budget_s=args.time_budget_s),
            ensure_ascii=False,
            indent=1,
        ) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "id": f"{args.account}/{args.kernel_slug}",
        "title": "VHGR Phase 8 - LLM extract Qwen3-8B 4bit",
        "code_file": "notebook.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": [
            args.dataset or f"{args.account}/vhgr-re-data"
        ],
        "keywords": ["vietnamese", "llm", "relation-extraction"],
        "competition_sources": [],
        "model_sources": ["manojkumarcs28/qwen3-8b/PyTorch/qwen3-8b/1"],
    }
    (folder / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"Đã sinh {folder}")
    print(f"  kernel : {metadata['id']}")
    print(f"  dataset: {metadata['dataset_sources'][0]}")
    print(f"  limit  : {args.limit} câu | ngân sách: {args.time_budget_s}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

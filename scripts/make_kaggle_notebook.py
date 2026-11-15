"""Sinh notebook Kaggle cho Phase 5 — huấn luyện NER PhoBERT trên GPU.

Notebook được sinh tự động (thay vì viết tay .ipynb) để:
- giữ cấu trúc JSON hợp lệ;
- có thể thay đổi `model_name` (arm A `phobert-base` / arm B `phobert-large`)
  bằng tham số CLI mà không phải sửa file JSON.

Cách dùng
---------
```bash
# Sinh notebook cho arm base
python scripts/make_kaggle_notebook.py \
    --out notebooks/kaggle/ner_train_phobert_base \
    --model vinai/phobert-base --arm base

# Sinh notebook cho arm large
python scripts/make_kaggle_notebook.py \
    --out notebooks/kaggle/ner_train_phobert_large \
    --model vinai/phobert-large --arm large
```

Kaggle kernel cần `kernel-metadata.json` trong thư mục kernel.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

#: Slug dataset Kaggle chứa nhãn bạc + mã nguồn + weight model.
DATASET_SLUG = "hoanghiep421/vhgr-ner-data"

#: Slug kernel Kaggle (Kaggle tự sinh từ `title` trong kernel-metadata.json).
KERNEL_SLUG = "hoanghiep421/vhgr-phase-5-ner-train-phobert-base"

#: Accelerator Kaggle yêu cầu.
ACCELERATOR = "gpu"

#: Thư mục chứa weight model đã bundle trong dataset (kernel không có DNS).
MODELS_HF_DIRNAME = "models_hf"


def build_cells(model_name: str, arm: str, dataset_slug: str) -> list[dict]:
    """Dựng danh sách cell của notebook.

    Args:
        model_name: Tên model HuggingFace.
        arm: Tên arm (``base``/``large``).
        dataset_slug: Slug dataset Kaggle được mount.

    Returns:
        Danh sách cell (dict) theo định dạng nbformat 4.
    """
    # `phobert-large` OOM với batch lớn trên T4 14.5 GB (đo 14/11/2026)
    # → giảm batch + micro-batch nhỏ hơn.
    is_large = "large" in model_name.lower()
    infer_batch = 16 if is_large else 64
    infer_micro_batch = 8 if is_large else 32
    train_batch = 8 if is_large else 32
    train_eval_batch = 16 if is_large else 64
    train_grad_accum = 4 if is_large else 1
    # `phobert-large` cần ~3 h/epoch + ~15 h suy luận toàn corpus (đo 15/11/2026)
    # → vượt giới hạn session 12 h của Kaggle. Rút gọn scope để chắc chắn xong:
    # giảm số epoch + giới hạn số câu train, và **bỏ** suy luận toàn corpus
    # (arm `large` chỉ dùng để so sánh dev F1 với arm `base`).
    train_epochs = 2 if is_large else None
    train_max_train = 60000 if is_large else None
    skip_inference = is_large
    md_intro = f"""# Phase 5 — Huấn luyện NER PhoBERT (arm `{arm}`)

- **Model**: `{model_name}`
- **Dataset**: `{dataset_slug}` (private)
- **Task**: token classification, scheme **BIO 13 lớp** (6 nhãn × {{B, I}} + `O`)
- **Seed**: 42 (theo `AGENTS.md` §5.6)

Máy local không có GPU → toàn bộ huấn luyện chạy ở đây (Kaggle T4 ×2).

## Quy trình

1. Mount dataset → giải nén nhãn bạc + mã nguồn + weight model
2. Kiểm tra thư viện (kernel không có DNS → không `pip install` được)
3. Kiểm tra GPU + môi trường
4. Huấn luyện (`src.ner.train_ner`)
5. Suy luận toàn corpus (`src.ner.infer_ner`) → `ner_predictions.jsonl`
6. Kiểm tra offset (0 span sai) + đóng gói output
"""

    code_mount = f"""# --- 1. Mount dataset ---------------------------------------------------------
import gzip
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

MODEL_NAME = "{model_name}"
ARM_NAME = "{arm}"

WORK = Path("/kaggle/working")
INPUT_ROOT = Path("/kaggle/input")
REPO = WORK / "repo"

# Tìm thư mục dataset đã mount: Kaggle đặt tên theo slug, có thể kèm hậu tố.
def find_dataset_dir() -> Path:
    candidates = sorted(
        path
        for path in INPUT_ROOT.iterdir()
        if path.is_dir() and "vhgr-ner-data" in path.name
    )
    if not candidates:
        # Fallback: dataset được giải nén ra thư mục con.
        candidates = sorted(
            path
            for path in INPUT_ROOT.rglob("ner_silver.jsonl*")
            if path.parent.is_dir()
        )
        if not candidates:
            raise FileNotFoundError(
                f"Không tìm thấy dataset trong {{INPUT_ROOT}}: {{list(INPUT_ROOT.iterdir())}}"
            )
        return candidates[0].parent
    return candidates[0]


DATASET_DIR = find_dataset_dir()
print("Dataset mount tại:", DATASET_DIR)
print("Nội dung:", sorted(p.name for p in DATASET_DIR.iterdir()))

if REPO.exists():
    shutil.rmtree(REPO)
REPO.mkdir(parents=True, exist_ok=True)

for item in DATASET_DIR.iterdir():
    if item.name.endswith(".zip") and item.is_file():
        with zipfile.ZipFile(item) as archive:
            archive.extractall(REPO)
    elif item.is_dir():
        shutil.copytree(item, REPO / item.name, dirs_exist_ok=True)
    else:
        shutil.copy2(item, REPO / item.name)

# Giải nén nhãn bạc
silver_gz = REPO / "ner_silver.jsonl.gz"
silver_plain = REPO / "ner_silver.jsonl"
if silver_gz.exists() and not silver_plain.exists():
    with gzip.open(silver_gz, "rb") as src, silver_plain.open("wb") as dst:
        shutil.copyfileobj(src, dst)

# Đặt đúng cấu trúc mà `src.common.config` kỳ vọng
(REPO / "data" / "interim").mkdir(parents=True, exist_ok=True)
(REPO / "data" / "splits").mkdir(parents=True, exist_ok=True)
if silver_plain.exists():
    shutil.move(str(silver_plain), str(REPO / "data" / "interim" / "ner_silver.jsonl"))
if (REPO / "splits.json").exists():
    shutil.move(str(REPO / "splits.json"), str(REPO / "data" / "splits" / "splits.json"))

print("Nội dung repo:", sorted(p.name for p in REPO.iterdir()))
print(
    "Số câu nhãn bạc:",
    sum(1 for _ in (REPO / "data" / "interim" / "ner_silver.jsonl").open(encoding="utf-8")),
)

# --- Model: dùng weight ĐÃ BUNDLE trong dataset -------------------------------
# Kernel Kaggle không có DNS → không tải được từ huggingface.co.
MODEL_DIR = REPO / "models_hf" / MODEL_NAME.split("/")[-1]
assert MODEL_DIR.exists(), f"Không thấy weight model tại {{MODEL_DIR}}"
MODEL_PATH = str(MODEL_DIR)
print("Model path:", MODEL_PATH)
print("Model files:", sorted(p.name for p in MODEL_DIR.iterdir()))
"""

    code_install = """# --- 2. Cài thư viện ------------------------------------------------------------
# Kernel không có DNS → `pip install` sẽ thất bại. Thư viện cần đã có sẵn
# trong ảnh Kaggle; chỉ kiểm tra, không cài.
import importlib

import torch
import transformers

print("torch:", torch.__version__, "| cuda:", torch.cuda.is_available())
print("transformers:", transformers.__version__)
for module in ["accelerate", "numpy", "sklearn", "sentencepiece", "tokenizers"]:
    try:
        imported = importlib.import_module(module)
        print(f"{module}: {getattr(imported, '__version__', '?')}")
    except Exception as exc:
        print(f"{module}: THIẾU ({exc})")
"""
    code_check = """# --- 3. Kiểm tra môi trường ----------------------------------------------------
import sys

sys.path.insert(0, "/kaggle/working/repo")

assert torch.cuda.is_available(), "Không có GPU — kernel phải chạy với accelerator GPU"
print("GPU:", torch.cuda.get_device_name(0))
print("Số GPU:", torch.cuda.device_count())

from src.ner.data_convert import (
    LABEL_LIST,
    NUM_LABELS,
    load_tokenizer,
)

print("Số lớp NER:", NUM_LABELS)
print("Danh sách lớp:", LABEL_LIST)

# Tokenizer: vocab phải khớp kích thước embedding của model (D-040)
tokenizer = load_tokenizer(MODEL_PATH)
print("Vocab tokenizer:", tokenizer.vocab_size)

import json
from transformers import AutoConfig

config = AutoConfig.from_pretrained(MODEL_PATH)
print("vocab_size model:", config.vocab_size)
assert tokenizer.vocab_size <= int(config.vocab_size), "Vocab tokenizer > embedding model"
"""

    train_args = [
        '"--config", "/kaggle/working/repo/configs/default.yaml"',
        '"--model", MODEL_PATH',
        '"--silver", "/kaggle/working/repo/data/interim/ner_silver.jsonl"',
        '"--splits", "/kaggle/working/repo/data/splits/splits.json"',
        '"--out", "/kaggle/working/models/ner"',
        f'"--batch-size", "{train_batch}"',
        f'"--eval-batch-size", "{train_eval_batch}"',
        f'"--grad-accum", "{train_grad_accum}"',
    ]
    if train_epochs is not None:
        train_args.append(f'"--epochs", "{train_epochs}"')
    if train_max_train is not None:
        train_args.append(f'"--max-train", "{train_max_train}"')
    train_args_block = ",\n        ".join(train_args)

    code_train = f"""# --- 4. Huấn luyện --------------------------------------------------------------
from src.ner.train_ner import main as train_main

train_main(
    [
        {train_args_block},
    ]
)
"""

    code_infer = f"""# --- 5. Suy luận toàn corpus ----------------------------------------------------
from src.ner.infer_ner import main as infer_main

infer_main(
    [
        "--config", "/kaggle/working/repo/configs/default.yaml",
        "--model", "/kaggle/working/models/ner",
        "--input", "/kaggle/working/repo/data/interim/ner_silver.jsonl",
        "--out", "/kaggle/working/ner_predictions.jsonl",
        "--batch-size", "{infer_batch}",
        "--micro-batch-size", "{infer_micro_batch}",
        "--fp16",
    ]
)
"""

    code_verify = '''# --- 6. Kiểm tra offset + đóng gói ------------------------------------------------
import json
import shutil
from pathlib import Path

PRED = Path("/kaggle/working/ner_predictions.jsonl")
VALID_LABELS = {"PERSON", "DYNASTY", "EVENT", "LOCATION", "TIME", "TITLE"}

n_sentences = 0
n_entities = 0
n_bad_offset = 0
n_bad_label = 0

if PRED.exists():
    with PRED.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            n_sentences += 1
            text = record["text"]
            for entity in record["entities"]:
                n_entities += 1
                if text[entity["start"] : entity["end"]] != entity["text"]:
                    n_bad_offset += 1
                if entity["label"] not in VALID_LABELS:
                    n_bad_label += 1

    print(f"Câu: {n_sentences}")
    print(f"Entity: {n_entities}")
    print(f"Span sai offset: {n_bad_offset}")
    print(f"Nhãn không hợp lệ: {n_bad_label}")

    assert n_bad_offset == 0, "Có span sai offset — Gate Phase 5 không đạt"
    assert n_bad_label == 0, "Có nhãn không hợp lệ"

# Đóng gói model + metrics + predictions thành 1 zip để tải về
shutil.make_archive("/kaggle/working/vhgr_ner_output", "zip", "/kaggle/working", "models")
if PRED.exists():
    shutil.make_archive(
        "/kaggle/working/vhgr_ner_predictions", "zip", "/kaggle/working", "ner_predictions.jsonl"
    )
print("Đã đóng gói output.")
'''

    code_summary = """# --- 7. Tóm tắt -----------------------------------------------------------------
import json
from pathlib import Path

metrics = json.loads(Path("/kaggle/working/models/ner/metrics.json").read_text(encoding="utf-8"))
print(json.dumps(metrics, ensure_ascii=False, indent=1))
"""

    raw_cells = [
        ("markdown", md_intro),
        ("code", code_mount),
        ("code", code_install),
        ("code", code_check),
        ("code", code_train),
    ]
    if not skip_inference:
        raw_cells.append(("code", code_infer))
    raw_cells.extend(
        [
            ("code", code_verify),
            ("code", code_summary),
        ]
    )

    cells: list[dict] = []
    for index, (cell_type, source) in enumerate(raw_cells):
        lines = source.splitlines(keepends=True)
        cell: dict = {
            "cell_type": cell_type,
            "id": f"cell-{index:02d}",
            "metadata": {},
            "source": lines,
        }
        # nbformat 4.5: chỉ cell code mới có `execution_count` và `outputs`.
        if cell_type == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.append(cell)
    return cells


def build_notebook(model_name: str, arm: str, dataset_slug: str) -> dict:
    """Dựng notebook JSON hoàn chỉnh.

    Args:
        model_name: Tên model HuggingFace.
        arm: Tên arm.

    Returns:
        Dict notebook theo nbformat 4.
    """
    return {
        "cells": build_cells(model_name, arm, dataset_slug),
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12.0",
            },
            "kaggle": {"accelerator": ACCELERATOR},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def build_kernel_metadata(
    kernel_slug: str, model_name: str, arm: str, dataset_slug: str
) -> dict:
    """Dựng `kernel-metadata.json` cho Kaggle kernel.

    Args:
        kernel_slug: Slug kernel.
        model_name: Tên model HuggingFace.
        arm: Tên arm.

    Returns:
        Dict metadata.
    """
    # Kaggle tự sinh slug từ `title` → phải khớp `kernel_slug` để script
    # `run_kaggle_ner.sh` poll đúng kernel.
    title = f"VHGR Phase 5 - NER train PhoBERT ({arm})"
    return {
        "id": kernel_slug,
        "title": title,
        "code_file": "notebook.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": [dataset_slug],
        "keywords": ["vietnamese", "wikipedia"],
        "competition_sources": [],
        "model_sources": [],
    }


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Sinh notebook Kaggle cho Phase 5")
    parser.add_argument("--out", required=True, help="Thư mục kernel")
    parser.add_argument("--model", default="vinai/phobert-base")
    parser.add_argument("--arm", default="base")
    parser.add_argument("--kernel-slug", default=KERNEL_SLUG)
    parser.add_argument(
        "--dataset-slug",
        default=DATASET_SLUG,
        help="Slug dataset Kaggle được mount (khác nhau giữa 2 tài khoản)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    notebook = build_notebook(args.model, args.arm, args.dataset_slug)
    notebook_path = out_dir / "notebook.ipynb"
    notebook_path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    metadata = build_kernel_metadata(
        args.kernel_slug, args.model, args.arm, args.dataset_slug
    )
    metadata_path = out_dir / "kernel-metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    logger.info("Đã sinh %s", notebook_path)
    logger.info("Đã sinh %s", metadata_path)
    logger.info(
        "Tiếp theo: kaggle kernels push -p %s", out_dir.relative_to(REPO_ROOT)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

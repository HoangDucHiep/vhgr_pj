#!/usr/bin/env python
"""Sinh notebook Kaggle **suy luận** RE trên GPU (Phase 8).

Notebook dùng **chính mã nguồn repo** (`src/re/infer_re.py`) nên kết quả trên
Kaggle **giống hệt** chạy local — chỉ khác thiết bị (GPU thay CPU).

Mã nguồn + model + cache cặp ứng viên được bundle trong dataset
`hoanghiep421/vhgr-re-infer`.

Cách dùng:
    python scripts/build_kaggle_re_infer_notebook.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = REPO_ROOT / "notebooks" / "kaggle"

CODE = r'''# %% [markdown]
# ## VHGR Phase 8 — Suy luận RE trên GPU (Kaggle)
#
# Chạy **đúng mã nguồn repo** (`src/re/infer_re.py`) trên GPU Kaggle.
#
# - Input: dataset `hoanghiep421/vhgr-re-infer` (mã nguồn + model + cache cặp ứng viên).
# - Output: `/kaggle/working/re_phobert.jsonl` — cùng format với lệnh local.
# - Ngưỡng lấy tự động từ `models/re/metrics.json` (0,55 / NA 0,50).

# %%
import glob
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

INPUT_ROOT = Path("/kaggle/input")
WORK = Path("/kaggle/working")
REPO = WORK / "repo"
#: Kaggle tự giải nén bundle `.tar` khi upload ⇒ dataset đã có sẵn cấu trúc
#: thư mục gốc (`src/`, `configs/`, `models/`, `data/`). Chỉ cần sao chép về
#: `/kaggle/working` để có thể ghi vào.
REPO.mkdir(parents=True, exist_ok=True)

#: Tìm thư mục gốc: dataset có thể nằm trực tiếp dưới `/kaggle/input/<slug>/`
#: hoặc lồng thêm một cấp (khi Kaggle giải nén `.tar`).
def find_root() -> Path:
    """Tìm thư mục chứa `src/` + `models/` trong dataset đầu vào.

    Returns:
        Đường dẫn gốc của bundle.

    Raises:
        FileNotFoundError: nếu không tìm thấy bundle hợp lệ.
    """
    #: Kaggle mount dataset **chậm** ⇒ `/kaggle/input/<slug>` có thể **chưa
    #: tồn tại** ở lần gọi đầu tiên. `iterdir()` trên thư mục không tồn tại
    #: ⇒ `FileNotFoundError` ⇒ phải bọc trong `try`.
    for attempt in range(30):
        candidates: list[Path] = []
        if INPUT_ROOT.exists():
            candidates.append(INPUT_ROOT)
            candidates.extend(
                sorted(p for p in INPUT_ROOT.iterdir() if p.is_dir())
            )
        for root in candidates:
            if (root / "src").exists() and (root / "models").exists():
                return root
            #: Dataset có thể nằm trong thư mục con (Kaggle giải nén `.tar`).
            for sub in sorted(root.glob("*/*")):
                if sub.is_dir() and (sub / "src").exists() and (sub / "models").exists():
                    return sub
        print(f"Chờ dataset mount (lần {attempt + 1}/30)...", flush=True)
        time.sleep(10)

    for tar_path in sorted(INPUT_ROOT.glob("**/*.tar")):
        target = WORK / tar_path.stem
        target.mkdir(parents=True, exist_ok=True)
        print("Giải nén:", tar_path.name, "->", target, flush=True)
        subprocess.run(["tar", "-xf", str(tar_path), "-C", str(target)], check=True)
        if (target / "src").exists() and (target / "models").exists():
            return target
    listing = sorted(str(p) for p in INPUT_ROOT.glob("**/*"))[:40]
    raise FileNotFoundError(
        f"Không tìm thấy bundle trong {INPUT_ROOT}. Nội dung: {listing}"
    )

SOURCE_ROOT = find_root()
print("Nguồn:", SOURCE_ROOT)

for name in ("src", "configs", "models", "data"):
    source = SOURCE_ROOT / name
    if not source.exists():
        raise FileNotFoundError(f"Thiếu {source} trong dataset")
    shutil.copytree(source, REPO / name)
    print("Sao chép", name)

# %%
os.chdir(REPO)
sys.path.insert(0, str(REPO))

#: Cache cặp ứng viên — dùng luôn bản đã cache để tiết kiệm ~3 phút quét.
CANDIDATES = REPO / "data" / "interim" / "_shards" / "candidates.jsonl"
OUT = WORK / "re_phobert.jsonl"

import torch

print("CUDA:", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")

#: Batch lớn trên GPU — không cần chia shard.
cmd = [
    sys.executable, "-m", "src.re.infer_re",
    "--config", "configs/default.yaml",
    "--model", "models/re",
    "--out", str(OUT),
    "--batch-size", "512",
    "--candidates-cache", str(CANDIDATES),
]
print("$", " ".join(cmd))
result = subprocess.run(cmd, cwd=str(REPO))
print("returncode:", result.returncode)

# %%
OUT.parent.mkdir(parents=True, exist_ok=True)
shutil.make_archive(str(WORK / "re_phobert"), "zip", str(WORK), "re_phobert.jsonl")

n_lines = sum(1 for _ in OUT.open("r", encoding="utf-8")) if OUT.exists() else 0
print("Số câu có dự đoán:", n_lines)
'''


def build(owner: str = "hoanghiep421") -> Path:
    """Sinh notebook và metadata.

    Args:
        owner: Chủ sở hữu kernel (tài khoản Kaggle). Dataset `vhgr-re-infer`
            phải thuộc **cùng** tài khoản này (dataset private không chia sẻ
            chéo tài khoản).

    Returns:
        Đường dẫn thư mục notebook.
    """
    target = NOTEBOOK_DIR / "re_infer_phobert_gpu"
    target.mkdir(parents=True, exist_ok=True)
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": (
                    "# VHGR Phase 8 — Suy luận RE trên GPU (Kaggle)\n\n"
                    "Chạy `src/re/infer_re.py` (mã nguồn repo) trên GPU.\n"
                ),
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": CODE.strip().splitlines(keepends=True),
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (target / "notebook.ipynb").write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    metadata = {
        "id": f"{owner}/vhgr-phase-8-re-infer-phobert-gpu",
        "title": "VHGR Phase 8 - RE infer PhoBERT (GPU)",
        "code_file": "notebook.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "dataset_sources": [f"{owner}/vhgr-re-infer"],
        "keywords": ["vietnamese", "nlp"],
        "competition_sources": [],
        "model_sources": [],
    }
    (target / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return target


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sinh notebook suy luận RE GPU")
    parser.add_argument(
        "--owner",
        default="hoanghiep421",
        help="Tài khoản Kaggle sở hữu kernel + dataset",
    )
    args = parser.parse_args()
    path = build(owner=args.owner)
    print(f"Đã tạo notebook: {path}")

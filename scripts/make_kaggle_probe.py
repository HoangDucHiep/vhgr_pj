"""Sinh notebook Kaggle **chẩn đoán môi trường** (Phase 5).

Kiểm tra: GPU có thật không, torch có CUDA không, internet/pip có dùng được
không, HuggingFace có tải được model không, dataset đã mount đúng chưa.

Cách dùng
---------
```bash
python scripts/make_kaggle_probe.py --out notebooks/kaggle/ner_probe \
    --kernel-slug hoangduchiep/vhgr-phase-5-ner-probe
kaggle kernels push -p notebooks/kaggle/ner_probe --accelerator NvidiaTeslaT4
```
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

DATASET_SLUG = "hoangduchiep/vhgr-ner-data"

CODE = """# Chẩn đoán môi trường Kaggle (Phase 5)
import subprocess
import sys
from pathlib import Path


def run(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.stdout + result.stderr
    except Exception as exc:
        return f"KHÔNG CHẠY ĐƯỢC: {exc}"


print("=" * 70)
print("1. Python")
print("=" * 70)
print(sys.version)

print("=" * 70)
print("2. GPU")
print("=" * 70)
try:
    import torch

    print("torch:", torch.__version__)
    print("torch.version.cuda:", torch.version.cuda)
    print("cuda.is_available():", torch.cuda.is_available())
    print("device_count():", torch.cuda.device_count())
    if torch.cuda.is_available():
        print("Tên GPU:", torch.cuda.get_device_name(0))
        print(
            "Dung lượng (GB):",
            round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2),
        )
except Exception as exc:
    print("LỖI torch:", exc)

print("=" * 70)
print("3. nvidia-smi")
print("=" * 70)
print(run(["nvidia-smi"])[:1200])

print("=" * 70)
print("4. Thiết bị / biến môi trường")
print("=" * 70)
print(run(["ls", "-la", "/dev/nvidia*"])[:600])
for key in ("KAGGLE_KERNEL_RUN_TYPE", "KAGGLE_GPU", "CUDA_VISIBLE_DEVICES"):
    print(f"{key} = {__import__('os').environ.get(key)}")

print("=" * 70)
print("5. Internet / pip")
print("=" * 70)
for url in ["https://pypi.org/simple/", "https://huggingface.co"]:
    print(f"{url} ->", run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "20", url]).strip()[:200])

print("=" * 70)
print("6. Thư viện quan trọng")
print("=" * 70)
for module in ["transformers", "accelerate", "numpy", "sklearn", "pandas", "tokenizers", "sentencepiece"]:
    try:
        imported = __import__(module)
        print(f"{module}: {getattr(imported, '__version__', '?')}")
    except Exception as exc:
        print(f"{module}: THIẾU ({exc})")

print("=" * 70)
print("7. Dataset mount")
print("=" * 70)
input_root = Path("/kaggle/input")
try:
    for path in sorted(input_root.rglob("*")):
        if path.is_file() and path.stat().st_size > 0:
            print("  ", path, f"{path.stat().st_size / 1024 / 1024:.1f} MB")
except Exception as exc:
    print("LỖI:", exc)

print("=" * 70)
print("8. Tải model từ HuggingFace")
print("=" * 70)
try:
    from huggingface_hub import snapshot_download

    path = snapshot_download("vinai/phobert-base", allow_patterns=["*.json", "*.txt"])
    print("Đã tải:", path)
    print("Nội dung:", sorted(p.name for p in Path(path).iterdir()))
except Exception as exc:
    print("LỖI tải model:", exc)

print("=" * 70)
print("9. pip install torch CUDA (nếu cần)")
print("=" * 70)
print(run(["pip", "download", "--no-deps", "-d", "/tmp/pipcheck", "sentencepiece"])[:600])

print("DIAGNOSIS_DONE")
"""


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Sinh notebook chẩn đoán Kaggle")
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--kernel-slug",
        default="hoangduchiep/vhgr-phase-5-ner-environment-probe",
    )
    parser.add_argument(
        "--docker-image",
        default=None,
        help="Ảnh docker của kernel (mặc định: để Kaggle chọn)",
    )
    parser.add_argument(
        "--pinning",
        default=None,
        choices=["original", "latest"],
        help="Kiểu ghim ảnh docker",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Tiêu đề kernel (phải khớp slug)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "id": "cell-00",
                "metadata": {},
                "execution_count": None,
                "outputs": [],
                "source": CODE.splitlines(keepends=True),
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12.0"},
            "kaggle": {"accelerator": "gpu"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (out_dir / "notebook.ipynb").write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    metadata = {
        "id": args.kernel_slug,
        "title": args.title or args.kernel_slug.split("/", 1)[-1].replace("-", " ").title(),
        "code_file": "notebook.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": [DATASET_SLUG],
        "keywords": ["vietnamese"],
        "competition_sources": [],
        "model_sources": [],
    }
    if args.docker_image:
        metadata["docker_image"] = args.docker_image
    if args.pinning:
        metadata["docker_image_pinning_type"] = args.pinning
    (out_dir / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    logger.info("Đã sinh probe tại %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

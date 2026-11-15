"""Đóng gói model PhoBERT **pretrained** thành dataset Kaggle (Phase 5).

Vì sao cần
----------
Đo thực tế trên Kaggle (probe kernel, 14/11/2026):

| Hạng mục | Kết quả |
|---|---|
| `enable_gpu: true` + `--accelerator NvidiaTeslaT4` | kernel chạy **CPU** (`torch 2.11.0+cpu`, `cuda.is_available()=False`, không có `nvidia-smi`) |
| Internet | **không có** (`pypi.org` → timeout DNS, `huggingface.co` → timeout DNS) |
| Dataset mount | ✅ OK (`/kaggle/input/datasets/<slug>/`) |

→ Kernel **không tải được** `vinai/phobert-*` từ HuggingFace. Giải pháp: đóng
gói sẵn model vào **dataset Kaggle** (kèm `tokenizer.json`, `vocab.txt`,
`bpe.codes`, `config.json`, `pytorch_model.bin`) rồi mount vào kernel.

Cách dùng
---------
```bash
python scripts/pack_kaggle_models.py --out data/kaggle/vhgr_ner_models
kaggle datasets create -p data/kaggle/vhgr_ner_models -r zip
```
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

#: Slug dataset Kaggle chứa model pretrained.
DATASET_SLUG = "hoangduchiep/vhgr-ner-models"

#: Model cần đóng gói → tên thư mục con.
MODELS: tuple[tuple[str, str], ...] = (
    ("vinai/phobert-base", "phobert-base"),
    ("vinai/phobert-large", "phobert-large"),
)

#: File cần tải từ HuggingFace.
PATTERNS: tuple[str, ...] = (
    "config.json",
    "pytorch_model.bin",
    "tokenizer.json",
    "vocab.txt",
    "bpe.codes",
)


def download_model(model_name: str, destination: Path) -> int:
    """Tải model pretrained về thư mục đích.

    Args:
        model_name: Tên model trên HuggingFace.
        destination: Thư mục đích.

    Returns:
        Số file đã tải.
    """
    from huggingface_hub import hf_hub_download

    destination.mkdir(parents=True, exist_ok=True)
    count = 0
    for pattern in PATTERNS:
        try:
            source = hf_hub_download(model_name, pattern)
        except Exception as exc:  # pragma: no cover - phụ thuộc mạng
            logger.warning("Không tải được %s (%s): %s", model_name, pattern, exc)
            continue
        target = destination / Path(source).name
        shutil.copy2(source, target)
        count += 1
        logger.info(
            "  %s → %s (%.1f MB)",
            pattern,
            target.name,
            target.stat().st_size / (1024 * 1024),
        )
    return count


def write_metadata(out_dir: Path) -> None:
    """Ghi `dataset-metadata.json` cho Kaggle CLI.

    Args:
        out_dir: Thư mục đích.
    """
    metadata = {
        "title": "VHGR Phase 5 — PhoBERT pretrained (offline)",
        "id": DATASET_SLUG,
        "licenses": [{"name": "MIT"}],
        "keywords": ["vietnamese", "phobert"],
        "subtitle": "vinai/phobert-base + vinai/phobert-large (vocab, bpe, weights)",
        "description": (
            "Model PhoBERT pretrained đóng gói sẵn để kernel Kaggle dùng **offline**.\n\n"
            "Lý do: kernel Kaggle trong phiên 14/11/2026 không có internet "
            "(`pypi.org`/`huggingface.co` timeout DNS) nên không tải được model "
            "từ HuggingFace.\n\n"
            "- `phobert-base/`: config.json, pytorch_model.bin, tokenizer.json, vocab.txt, bpe.codes\n"
            "- `phobert-large/`: tương tự\n\n"
            "Nguồn: `vinai/phobert-base`, `vinai/phobert-large` trên HuggingFace (MIT)."
        ),
        "resources": [
            {"path": "phobert-base.zip"},
            {"path": "phobert-large.zip"},
        ],
    }
    (out_dir / "dataset-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Đóng gói model PhoBERT pretrained cho Kaggle (offline)"
    )
    parser.add_argument("--out", default="data/kaggle/vhgr_ner_models")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)

    out_dir = resolve_path(args.out)
    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for model_name, folder in MODELS:
        logger.info("Tải %s → %s", model_name, folder)
        count = download_model(model_name, out_dir / folder)
        if count == 0:
            logger.error("Không tải được file nào của %s", model_name)
            return 1

    write_metadata(out_dir)

    total = sum(1 for path in out_dir.rglob("*") if path.is_file())
    size_mb = sum(
        path.stat().st_size for path in out_dir.rglob("*") if path.is_file()
    ) / (1024 * 1024)
    logger.info(
        "Đóng gói xong: %d file, %.1f MB → %s", total, size_mb, out_dir
    )
    logger.info("Tiếp theo: kaggle datasets create -p %s -r zip", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

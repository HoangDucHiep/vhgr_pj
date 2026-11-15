#!/usr/bin/env python
"""Đóng gói bundle **suy luận RE trên GPU** thành dataset Kaggle (Phase 8).

Vì sao cần script riêng:
- Kernel Kaggle **không có DNS** → không tải được model từ huggingface.co,
  phải bundle sẵn weight + tokenizer.
- `src/re/infer_re.py` cần `coref_resolved.jsonl` + `infobox_entities.jsonl`
  để dựng nhãn entity và tên hiển thị, cùng cache cặp ứng viên đã sinh sẵn
  (`data/interim/_shards/candidates.jsonl`) để tiết kiệm ~3 phút quét corpus.
- Kernel chạy **chính mã nguồn repo** ⇒ kết quả GPU khớp với chạy local.

Cách dùng
---------
```bash
python scripts/pack_re_infer_dataset.py --out data/kaggle/vhgr_re_infer
kaggle datasets create -p data/kaggle/vhgr_re_infer -r zip --private
# cập nhật version:
kaggle datasets version -p data/kaggle/vhgr_re_infer -r zip -m "phase8 re infer"
```

Lưu ý: `kaggle` CLI >= 2.2 cần `KAGGLE_API_TOKEN` (token từ Settings UI),
không đọc `KAGGLE_USERNAME`/`KAGGLE_KEY` kiểu cũ.
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

#: Các thư mục mã nguồn cần đóng gói.
SOURCE_DIRS: tuple[str, ...] = ("src", "configs")

#: Artifact đường dẫn tương đối repo → đường dẫn tương đối trong dataset.
DATA_FILES: tuple[tuple[str, str], ...] = (
    ("data/interim/coref_resolved.jsonl", "data/interim/coref_resolved.jsonl"),
    (
        "data/interim/infobox_entities.jsonl",
        "data/interim/infobox_entities.jsonl",
    ),
    (
        "data/interim/_shards/candidates.jsonl",
        "data/interim/_shards/candidates.jsonl",
    ),
)

#: Thư mục model trong dataset (không nén để load nhanh).
MODEL_DIRNAME: str = "models/re"


def copy_source(out_dir: Path) -> int:
    """Chép mã nguồn + cấu hình vào thư mục đóng gói.

    Args:
        out_dir: Thư mục đích.

    Returns:
        Số file đã chép.
    """
    count = 0
    for directory in SOURCE_DIRS:
        source = REPO_ROOT / directory
        if not source.exists():
            logger.warning("Bỏ qua (không tồn tại): %s", source)
            continue
        destination = out_dir / directory
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        count += sum(1 for path in destination.rglob("*") if path.is_file())
        logger.info("Đã chép %s → %s", directory, destination)

    requirements = REPO_ROOT / "requirements.txt"
    if requirements.exists():
        shutil.copy2(requirements, out_dir / "requirements.txt")
        count += 1
    return count


def copy_data(out_dir: Path) -> int:
    """Chép artifact dữ liệu vào thư mục đóng gói.

    Args:
        out_dir: Thư mục đích.

    Returns:
        Số file đã chép.
    """
    count = 0
    for relative, name in DATA_FILES:
        source = resolve_path(relative)
        if not source.exists():
            logger.warning("Bỏ qua (không tồn tại): %s", source)
            continue
        destination = out_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        size_mb = destination.stat().st_size / (1024 * 1024)
        logger.info("Đã chép %s (%.1f MB) → %s", relative, size_mb, destination)
        count += 1
    return count


def copy_model(out_dir: Path) -> int:
    """Chép weight model RE đã huấn luyện vào thư mục đóng gói.

    Args:
        out_dir: Thư mục đích.

    Returns:
        Số file đã chép.
    """
    source = REPO_ROOT / "models" / "re"
    if not source.exists():
        logger.warning("Bỏ qua (không tồn tại): %s", source)
        return 0
    destination = out_dir / MODEL_DIRNAME
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "training_args.bin"),
    )
    count = sum(1 for path in destination.rglob("*") if path.is_file())
    size_mb = sum(
        path.stat().st_size for path in destination.rglob("*") if path.is_file()
    ) / (1024 * 1024)
    logger.info("Đã chép model RE (%.1f MB) → %s", size_mb, destination)
    return count


def write_manifest(out_dir: Path) -> None:
    """Ghi manifest + metadata cho Kaggle CLI.

    Args:
        out_dir: Thư mục đóng gói.
    """
    manifest = {
        "_meta": {
            "phase": 8,
            "muc_tieu": "Suy luận RE PhoBERT trên GPU Kaggle (cùng mã nguồn repo)",
            "model": "vinai/phobert-base",
            "threshold": 0.55,
            "na_threshold": 0.5,
            "dump_version": "20261101",
            "seed": 42,
        },
        "files": sorted(
            str(path.relative_to(out_dir))
            for path in out_dir.rglob("*")
            if path.is_file()
        ),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    metadata = {
        "title": "VHGR Phase 8 — RE infer bundle (PhoBERT base + source)",
        "id": "hoanghiep421/vhgr-re-infer",
        "licenses": [{"name": "CC BY-SA 4.0"}],
        "keywords": ["vietnamese", "relation-extraction", "phobert"],
        "subtitle": "PhoBERT RE model + repo source + candidate pair cache for GPU inference",
        "description": (
            "Bundle cho kernel suy luận RE trên GPU Kaggle (Phase 8).\n\n"
            "- `src/`, `configs/`: mã nguồn pipeline (kernel chạy `src.re.infer_re`)\n"
            "- `models/re/`: weight PhoBERT-base RE (micro-F1 0.9375) + `metrics.json`\n"
            "- `data/interim/coref_resolved.jsonl`: mention + canonical id\n"
            "- `data/interim/infobox_entities.jsonl`: map canonical id → loại/tên\n"
            "- `data/interim/_shards/candidates.jsonl`: cache cặp ứng viên (99.348)\n"
            "- `manifest.json`: mô tả artifact\n\n"
            "Nguồn: Wikipedia tiếng Việt dump 20261101 (CC BY-SA 4.0).\n"
            "Model: vinai/phobert-base (MIT)."
        ),
        "resources": [
            {"path": "data/interim/_shards/candidates.jsonl"},
            {"path": "models/re/model.safetensors"},
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
        description="Đóng gói dataset Kaggle cho Phase 8 (suy luận RE trên GPU)"
    )
    parser.add_argument(
        "--out",
        default="data/kaggle/vhgr_re_infer",
        help="Thư mục đích",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Xoá thư mục đích trước khi đóng gói",
    )
    args = parser.parse_args(argv)

    out_dir = resolve_path(args.out)
    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_source = copy_source(out_dir)
    n_data = copy_data(out_dir)
    n_model = copy_model(out_dir)
    write_manifest(out_dir)

    total = sum(1 for path in out_dir.rglob("*") if path.is_file())
    size_mb = sum(
        path.stat().st_size for path in out_dir.rglob("*") if path.is_file()
    ) / (1024 * 1024)
    logger.info(
        "Đóng gói xong: %d file (%d mã nguồn + %d dữ liệu + %d model), tổng %.1f MB → %s",
        total,
        n_source,
        n_data,
        n_model,
        size_mb,
        out_dir,
    )
    logger.info(
        "Tiếp theo: kaggle datasets create -p %s -r zip --private", args.out
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

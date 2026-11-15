"""Đóng gói dữ liệu + mã nguồn cần thiết thành dataset Kaggle (Phase 5).

Máy local **không có GPU** (đã kiểm chứng 11/2026) → huấn luyện PhoBERT
phải chạy trên Kaggle GPU. Script này đóng gói:

- `data/interim/ner_silver.jsonl` (nhãn bạc, gzip để nhẹ)
- `data/splits/splits.json`
- `src/` (mã nguồn pipeline)
- `configs/` (cấu hình)
- `requirements.txt`

thành một dataset Kaggle **private** để kernel mount vào.

Cách dùng
---------
```bash
python scripts/pack_kaggle_dataset.py --out data/kaggle/vhgr_ner_data
# sau đó (nếu chưa có dataset):
kaggle datasets create -p data/kaggle/vhgr_ner_data -r zip --private
# cập nhật version:
kaggle datasets version -p data/kaggle/vhgr_ner_data -r zip -m "phase5 ner data"
```

Lưu ý: `kaggle` CLI >= 2.2 cần `KAGGLE_API_TOKEN` (token từ Settings UI),
không đọc `KAGGLE_USERNAME`/`KAGGLE_KEY` kiểu cũ.
"""

from __future__ import annotations

import argparse
import gzip
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

#: Các file đơn lẻ cần đóng gói.
SOURCE_FILES: tuple[str, ...] = ("requirements.txt",)

#: Artifact dữ liệu (đường dẫn tương đối repo) → tên file trong dataset.
DATA_FILES: tuple[tuple[str, str], ...] = (
    ("data/interim/ner_silver.jsonl", "ner_silver.jsonl.gz"),
    ("data/splits/splits.json", "splits.json"),
)

#: Slug dataset Kaggle (dùng trong `dataset-metadata.json` và notebook).
DATASET_SLUG: str = "hoanghiep421/vhgr-ner-data"

#: Model HuggingFace cần bundle (Kaggle kernel **không có DNS** → không tải
#: được từ huggingface.co trong kernel; phải đóng gói sẵn vào dataset).
MODEL_IDS: tuple[str, ...] = ("vinai/phobert-base", "vinai/phobert-large")

#: Thư mục đích chứa weight model trong dataset.
MODEL_DIRNAME: str = "models_hf"


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

    for name in SOURCE_FILES:
        source = REPO_ROOT / name
        if not source.exists():
            logger.warning("Bỏ qua (không tồn tại): %s", source)
            continue
        shutil.copy2(source, out_dir / name)
        count += 1

    return count


def copy_data(out_dir: Path) -> int:
    """Chép artifact dữ liệu (gzip file lớn) vào thư mục đóng gói.

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
        if name.endswith(".gz"):
            with source.open("rb") as src, gzip.open(destination, "wb", compresslevel=6) as dst:
                shutil.copyfileobj(src, dst)
        else:
            shutil.copy2(source, destination)
        size_mb = destination.stat().st_size / (1024 * 1024)
        logger.info("Đã chép %s → %s (%.1f MB)", relative, destination, size_mb)
        count += 1
    return count


def copy_models(out_dir: Path) -> int:
    """Tải + chép weight model HuggingFace vào dataset.

    Kaggle kernel **không có DNS** (đã kiểm chứng 11/2026) → không thể
    `from_pretrained("vinai/phobert-base")` trong kernel. Phải bundle sẵn
    weight + tokenizer vào dataset rồi nạp từ đường dẫn local.

    Args:
        out_dir: Thư mục đích.

    Returns:
        Số file đã chép.
    """
    from huggingface_hub import snapshot_download

    count = 0
    root = out_dir / MODEL_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    for model_id in MODEL_IDS:
        name = model_id.split("/")[-1]
        destination = root / name
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)

        snapshot = Path(
            snapshot_download(
                model_id,
                allow_patterns=[
                    "*.json",
                    "*.txt",
                    "*.model",
                    "*.safetensors",
                    "*.bin",
                    "bpe.codes",
                ],
                ignore_patterns=["*.h5", "*.msgpack", "*.onnx", "*.ot"],
            )
        )
        for path in sorted(snapshot.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(snapshot)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            count += 1
        size_mb = sum(
            item.stat().st_size for item in destination.rglob("*") if item.is_file()
        ) / (1024 * 1024)
        logger.info("Đã chép model %s (%.1f MB) → %s", model_id, size_mb, destination)
    return count


def write_manifest(out_dir: Path) -> None:
    """Ghi manifest mô tả nội dung dataset + metadata cho Kaggle CLI.

    Kaggle CLI yêu cầu file `datasets-metadata.json` trong thư mục đóng gói
    (thiếu → lỗi `kaggle datasets create`).

    Args:
        out_dir: Thư mục đích.
    """
    import json

    manifest = {
        "_meta": {
            "phase": 5,
            "muc_tieu": "Huấn luyện mô hình NER PhoBERT (BIO 13 lớp)",
            "dump_version": "20261101",
            "nguon_du_lieu": "data/interim/ner_silver.jsonl",
            "cau_hinh_lop": "NER: PERSON, DYNASTY, EVENT, LOCATION, TIME, TITLE",
            "schema_nhan": "BIO",
            "so_lop": 13,
            "seed": 42,
        },
        "files": sorted(
            path.name for path in out_dir.iterdir() if path.is_file()
        ),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    # Metadata bắt buộc của Kaggle CLI.
    metadata = {
        "title": "VHGR Phase 5 — NER silver labels (viwiki 20261101)",
        "id": DATASET_SLUG,
        "licenses": [{"name": "CC BY-SA 4.0"}],
        "keywords": ["vietnamese", "wikipedia", "ner", "named-entity-recognition"],
        "subtitle": "186.960 câu nhãn bạc BIO 13 lớp + mã nguồn pipeline",
        "description": (
            "Dữ liệu huấn luyện NER cho dự án Knowledge Graph lịch sử Việt Nam.\n\n"
            "- `ner_silver.jsonl.gz`: 186.960 câu, 138.860 mention, scheme BIO 13 lớp\n"
            "- `splits.json`: chia theo bài (80/10/10), seed 42\n"
            "- `src/`, `configs/`: mã nguồn pipeline Phase 5\n"
            "- `models_hf/`: weight PhoBERT base/large (kernel không có DNS nên\n"
            "  không tải được từ huggingface.co)\n"
            "- `manifest.json`: mô tả artifact\n\n"
            "Nguồn: Wikipedia tiếng Việt dump 20261101 (CC BY-SA 4.0).\n"
            "Model: vinai/phobert-base, vinai/phobert-large (MIT)."
        ),
        "resources": [{"path": "ner_silver.jsonl.gz"}],
    }
    # Kaggle CLI 2.x yêu cầu tên file `dataset-metadata.json` (không phải
    # `datasets-metadata.json`).
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
        description="Đóng gói dataset Kaggle cho Phase 5 (NER)"
    )
    parser.add_argument(
        "--out",
        default="data/kaggle/vhgr_ner_data",
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
    n_model = copy_models(out_dir)
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

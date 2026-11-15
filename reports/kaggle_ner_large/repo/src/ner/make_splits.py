"""Chia tập train/dev/test theo **bài** (Phase 4 — B2.3).

Vì sao chia theo **bài** chứ không theo câu: các câu trong cùng một bài
Wikipedia có văn phong, nhân vật và sự kiện giống nhau. Nếu chia ngẫu nhiên
theo câu, cùng một nhân vật có thể xuất hiện ở cả train và test → **rò rỉ
dữ liệu**, F1 bị thổi phồng. Nguyên tắc `AGENTS.md` §5.6: "chia tập theo
bài (không theo câu)".

Tái lập: seed cố định ``42`` (`AGENTS.md` §5.6) + lưu kết quả ra
``data/splits/splits.json`` để chạy lại cho kết quả giống hệt.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

from src.common.config import resolve_path
from src.common.logger import get_logger

logger = get_logger(__name__)

#: Seed cố định (nguyên tắc `AGENTS.md` §5.6).
DEFAULT_SEED = 42

#: Tỉ lệ chia: 80% train / 10% dev / 10% test.
DEFAULT_RATIOS: dict[str, float] = {"train": 0.8, "dev": 0.1, "test": 0.1}


def collect_page_ids(documents_path: str | Path) -> list[int]:
    """Thu thập `page_id` của mọi bài trong corpus.

    Args:
        documents_path: Đường dẫn `documents.jsonl`.

    Returns:
        Danh sách `page_id` tăng dần, không trùng.
    """
    resolved = resolve_path(documents_path)
    page_ids: set[int] = set()
    with resolved.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            page_id = record.get("page_id")
            if page_id is not None:
                page_ids.add(int(page_id))
    return sorted(page_ids)


def split_page_ids(
    page_ids: list[int],
    *,
    seed: int = DEFAULT_SEED,
    ratios: dict[str, float] | None = None,
) -> dict[str, list[int]]:
    """Chia `page_id` thành 3 tập theo seed cố định.

    Args:
        page_ids: Danh sách `page_id` (sẽ được shuffle theo seed).
        seed: Seed RNG.
        ratios: Tỉ lệ chia (mặc định 80/10/10).

    Returns:
        Dict ``{train: [...], dev: [...], test: [...]}``.
    """
    ratios = ratios or DEFAULT_RATIOS
    shuffled = list(page_ids)
    random.Random(seed).shuffle(shuffled)
    total = len(shuffled)

    n_train = int(total * ratios["train"])
    n_dev = int(total * ratios["dev"])
    # Phần còn lại sang test (đảm bảo tổng = total).
    splits = {
        "train": sorted(shuffled[:n_train]),
        "dev": sorted(shuffled[n_train : n_train + n_dev]),
        "test": sorted(shuffled[n_train + n_dev :]),
    }
    return splits


def write_splits(
    splits: dict[str, list[int]],
    output_path: str | Path,
    *,
    seed: int = DEFAULT_SEED,
    source: str = "data/interim/documents.jsonl",
) -> None:
    """Ghi ``splits.json``.

    Args:
        splits: Dict các tập.
        output_path: Đường dẫn output.
        seed: Seed đã dùng.
        source: Nguồn dữ liệu (để truy vết).
    """
    resolved = resolve_path(output_path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_meta": {
            "seed": seed,
            "source": source,
            "don_vi": "page_id",
            "ty_le": DEFAULT_RATIOS,
            "tong_so_bai": sum(len(v) for v in splits.values()),
        },
        **splits,
    }
    resolved.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )


def load_splits(path: str | Path) -> dict[str, list[int]]:
    """Nạp ``splits.json``.

    Args:
        path: Đường dẫn file.

    Returns:
        Dict ``{train, dev, test}`` — mỗi giá trị là danh sách `page_id`.

    Raises:
        FileNotFoundError: Nếu file không tồn tại.
    """
    resolved = resolve_path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"Không tìm thấy splits: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return {
        "train": list(payload.get("train") or []),
        "dev": list(payload.get("dev") or []),
        "test": list(payload.get("test") or []),
    }


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(description="Chia tập train/dev/test (Phase 4)")
    parser.add_argument("--documents", default="data/interim/documents.jsonl")
    parser.add_argument("--out", default="data/splits/splits.json")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    page_ids = collect_page_ids(args.documents)
    splits = split_page_ids(page_ids, seed=args.seed)
    write_splits(splits, args.out, seed=args.seed, source=args.documents)

    for name, values in splits.items():
        logger.info("%s: %d bài", name, len(values))

    # Kiểm tra không trùng lặp giữa các tập.
    all_ids = [pid for values in splits.values() for pid in values]
    if len(all_ids) != len(set(all_ids)):
        logger.error("CÓ page_id trùng giữa các tập!")
        return 1
    logger.info("Tổng %d bài, không trùng lặp", len(all_ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())

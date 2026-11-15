"""Đặt seed ngẫu nhiên để kết quả tái lập được.

Nguyên tắc 6 của `AGENTS.md`: seed cố định `42`, mọi artifact ghi kèm `dump_version`
và `model_name`. Hàm này được gọi ở đầu mọi script có dùng ngẫu nhiên.
"""

from __future__ import annotations

import os
import random
from typing import Any

DEFAULT_SEED = 42


def set_seed(seed: int = DEFAULT_SEED, *, deterministic_torch: bool = True) -> None:
    """Đặt seed cho `random`, `numpy` và `torch` (nếu đã cài).

    Args:
        seed: Giá trị seed (mặc định 42).
        deterministic_torch: Bật chế độ deterministic của torch để tái lập kết quả
            trên cùng một phiên bản CUDA. Mặc định ``True``.
    """
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy là phụ thuộc bắt buộc
        pass
    else:
        np.random.seed(seed)

    try:
        import torch
    except ImportError:
        # torch chỉ cần cho tầng offline (Kaggle) — máy local có thể chưa cài.
        return

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if deterministic_torch:
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False


def get_seed(config: dict[str, Any] | None = None) -> int:
    """Lấy seed từ cấu hình, mặc định 42.

    Args:
        config: Dict cấu hình (có thể là ``None``).

    Returns:
        Giá trị seed.
    """
    if not config:
        return DEFAULT_SEED
    value = config.get("seed", DEFAULT_SEED)
    return int(value)

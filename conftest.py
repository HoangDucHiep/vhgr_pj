"""Cấu hình pytest cho toàn repo.

Vì sao cần file này
-------------------
Khi chạy `pytest tests/` (nhịp phím của `pytest` trong `.venv/bin`), pytest
chỉ thêm thư mục chứa test (`tests/`) vào `sys.path` — **không** thêm thư mục
gốc repo. Vì vậy `import src...` thất bại với
`ModuleNotFoundError: No module named 'src'`, trong khi `python -m pytest`
lại chạy được (do Python tự thêm CWD vào `sys.path`).

Điều này tạo ra sự khác biệt dễ gây nhầm lẫn: cùng một bộ test, hai lệnh,
hai kết quả khác nhau — và lệnh trong `AGENTS.md` §8 là `pytest -q tests/`.

File này thêm thư mục gốc repo vào `sys.path` một cách tường minh để **mọi**
cách gọi pytest cho kết quả giống nhau.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Thư mục gốc repo (thư mục chứa `src/`, `tests/`, `configs/`).
REPO_ROOT = Path(__file__).resolve().parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

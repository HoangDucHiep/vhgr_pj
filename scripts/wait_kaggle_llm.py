#!/usr/bin/env python
"""Theo dõi kernel Kaggle LLM (Phase 8 — D-082) và tải kết quả về.

Cách dùng:
    python scripts/wait_kaggle_llm.py --ref dathungdao2004/vhgr-phase-8-llm-extract-qwen3-8b-4bit

Script chỉ **theo dõi**: poll trạng thái kernel, in log khi có thay đổi, và khi
kernel `COMPLETE`/`ERROR` thì tải output về `--out-dir` (mặc định
`data/interim/kaggle_llm_out`). Không push, không xoá kernel.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Các trạng thái kết thúc.
TERMINAL = ("COMPLETE", "ERROR", "CANCELLED")


def _kaggle_env() -> dict[str, str]:
    """Dựng env cho `kaggle` CLI theo tài khoản được yêu cầu.

    Returns:
        Dict env đã ghi đè token/username.
    """
    env = dict(os.environ)
    user = env.get("KAGGLE_USERNAME", "")
    token = env.get("KAGGLE_API_TOKEN", "") or env.get("KAGGLE_KEY", "")
    if user and token:
        env["KAGGLE_USERNAME"] = user
        env["KAGGLE_API_TOKEN"] = token
        env.pop("KAGGLE_KEY", None)
    return env


def kernel_status(ref: str, env: dict[str, str]) -> str:
    """Trả về trạng thái kernel (ví dụ `RUNNING`).

    Args:
        ref: `owner/slug`.
        env: Env cho CLI.

    Returns:
        Trạng thái dạng chữ in hoa, hoặc `UNKNOWN`.
    """
    proc = subprocess.run(
        ["kaggle", "kernels", "status", ref],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for token in TERMINAL + ("RUNNING", "QUEUED", "STARTING"):
        if token in out:
            return token
    return "UNKNOWN"


def download_output(ref: str, out_dir: Path, env: dict[str, str]) -> int:
    """Tải output của kernel về `out_dir`.

    Args:
        ref: `owner/slug`.
        out_dir: Thư mục đích.
        env: Env cho CLI.

    Returns:
        Mã thoát của lệnh `kaggle kernels output`.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["kaggle", "kernels", "output", ref, "-p", str(out_dir), "-o"],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
        check=False,
    )
    sys.stdout.write(proc.stdout or "")
    sys.stderr.write(proc.stderr or "")
    return proc.returncode


def main() -> int:
    """Điểm vào.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Theo dõi kernel Kaggle LLM và tải output.",
    )
    parser.add_argument("--ref", required=True, help="owner/slug của kernel.")
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "data" / "interim" / "kaggle_llm_out"),
        help="Thư mục tải output về.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=90,
        help="Giây giữa hai lần poll.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=7200,
        help="Tổng thời gian chờ tối đa (giây).",
    )
    args = parser.parse_args()

    env = _kaggle_env()
    out_dir = Path(args.out_dir)
    deadline = time.time() + args.timeout
    last = ""
    while time.time() < deadline:
        status = kernel_status(args.ref, env)
        if status != last:
            stamp = time.strftime("%H:%M:%S")
            print(f"[{stamp}] {args.ref} → {status}", flush=True)
            last = status
        if status in TERMINAL:
            print(f"Kernel kết thúc: {status}. Đang tải output...", flush=True)
            return download_output(args.ref, out_dir, env)
        time.sleep(args.interval)
    print("Hết thời gian chờ — kernel vẫn đang chạy.", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

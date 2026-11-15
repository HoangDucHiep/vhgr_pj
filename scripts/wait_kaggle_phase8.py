#!/usr/bin/env python3
"""Chờ 2 Kaggle kernel (2 tài khoản) chạy xong rồi tải artifact về.

- `hoanghiep421/vhgr-phase-8-re-train-phobert-base` → tải `models/re`
- `dathungdao2004/vhgr-phase-8-llm-extract-qwen3-8b-4bit-sec` → tải `re_llm.jsonl`

Dùng `KAGGLE_API_TOKEN` (token của account tương ứng) để chuyển account.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV_FILE = REPO / ".env"

TARGETS = [
    {
        "ref": "hoanghiep421/vhgr-phase-8-re-train-phobert-base",
        "env_key": "KAGGLE_KEY",
        "out_dir": REPO / "models" / "re",
        "label": "RE train GPU (account1)",
    },
    {
        "ref": "hoanghiep421/vhgr-phase-8-re-train-phobert-base-cpu",
        "env_key": "KAGGLE_KEY",
        "out_dir": REPO / "models" / "re_cpu_kaggle",
        "label": "RE train CPU (account1)",
    },
    {
        "ref": "dathungdao2004/vhgr-phase-8-llm-extract-qwen3-8b-4bit-sec",
        "env_key": "SEC_KAGGLE_KEY",
        "out_dir": REPO / "data" / "interim",
        "label": "LLM extract (account phụ)",
    },
]

DONE_STATES = ("COMPLETE", "ERROR", "CANCELLED", "DEADLINE_EXCEEDED")


def read_env() -> dict[str, str]:
    from dotenv import dotenv_values

    return {k: (v or "").strip() for k, v in dotenv_values(ENV_FILE).items()}


def kaggle(args: list[str], token: str, timeout: int = 300) -> tuple[int, str]:
    env = dict(os.environ)
    env["KAGGLE_API_TOKEN"] = token
    proc = subprocess.run(
        ["kaggle", *args], capture_output=True, text=True, env=env, timeout=timeout
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def status_of(ref: str, token: str) -> str:
    code, out = kaggle(["kernels", "status", ref], token, timeout=90)
    if code != 0:
        return "UNKNOWN"
    for state in DONE_STATES + ("RUNNING", "QUEUED"):
        if state in out:
            return state
    return "UNKNOWN"


def download(ref: str, token: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    code, out = kaggle(["kernels", "output", ref, "-p", str(out_dir)], token, timeout=1800)
    print(f"[download] {ref} -> {out_dir} rc={code}")
    if code != 0:
        print(out[-1500:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poll", type=int, default=120, help="giây giữa 2 lần kiểm tra")
    parser.add_argument("--max-minutes", type=int, default=600)
    args = parser.parse_args()

    envs = read_env()
    deadline = time.time() + args.max_minutes * 60
    states: dict[str, str] = {}

    while time.time() < deadline:
        for target in TARGETS:
            token = envs.get(target["env_key"], "")
            if not token:
                print(f"[warn] thiếu {target['env_key']} trong .env")
                continue
            state = status_of(target["ref"], token)
            if state != states.get(target["ref"]):
                print(f"[{time.strftime('%H:%M:%S')}] {target['label']}: {state}", flush=True)
                states[target["ref"]] = state
            if state == "COMPLETE":
                download(target["ref"], token, target["out_dir"])
                states[target["ref"]] = "DOWNLOADED"
            elif state in ("ERROR", "CANCELLED", "DEADLINE_EXCEEDED"):
                print(f"[FAIL] {target['ref']} -> {state}", flush=True)
                code, out = kaggle(["kernels", "output", target["ref"], "-p", "/tmp/kfail"], token)
                print(out[-1500:])
        if all(s == "DOWNLOADED" for s in states.values()) and len(states) == len(TARGETS):
            print("[OK] tất cả kernel đã xong và tải về.")
            return 0
        time.sleep(args.poll)

    print("[TIMEOUT] hết thời gian chờ.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

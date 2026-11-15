#!/usr/bin/env python3
"""Chờ kernel Kaggle GPU suy luận RE xong → tải `re_phobert.jsonl` về.

Bước:
1. Chờ kernel `hoanghiep421/vhgr-phase-8-re-infer-phobert-gpu` → `COMPLETE`.
2. Tải output (`re_phobert.zip`) về `data/interim/re_phobert.jsonl`.
3. Chạy `src.re.merge_triples` → `data/interim/triples_merged.jsonl`.
4. Chấm Gate Phase 8 theo `docs/09` §Phase 8.

Dùng:
    python scripts/finish_phase8_gpu.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
#: Kernel suy luận RE. Tài khoản chính đã **hết quota GPU** (44.677s/21.600s,
#: reset 21/11) nên kernel chạy trên tài khoản phụ (`dathungdao2004`, còn
#: ~4.400s) — dataset `vhgr-re-infer` cũng phải nằm trong tài khoản đó vì
#: dataset private không chia sẻ chéo tài khoản.
KERNEL = os.environ.get(
    "RE_INFER_KERNEL",
    "dathungdao2004/vhgr-phase-8-re-infer-phobert-gpu",
)
OUT_JSONL = REPO / "data" / "interim" / "re_phobert.jsonl"
MERGED = REPO / "data" / "interim" / "triples_merged.jsonl"
DL_DIR = Path("/tmp/kg_infer_out")


def kaggle_env() -> dict[str, str]:
    """Biến môi trường cho lệnh `kaggle` (hỗ trợ tài khoản phụ).

    Returns:
        Dict biến môi trường cần thêm vào lệnh con.
    """
    env = dict(os.environ)
    sec_user = env.get("SEC_KAGGLE_USERNAME", "").strip()
    sec_key = env.get("SEC_KAGGLE_KEY", "").strip()
    if sec_user and sec_key and KERNEL.startswith(sec_user):
        env["KAGGLE_USERNAME"] = sec_user
        env["KAGGLE_API_TOKEN"] = sec_key
    return env

RELATIONS = {
    "cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua", "thuoc_trieu_dai",
    "ke_vi", "giu_chuc_vu", "lap_ra", "chi_huy_tran", "tham_gia_tran", "danh_bai",
    "dien_ra_tai", "sinh_tai", "mat_tai", "sinh_nam", "mat_nam", "dong_doi_tai",
}


def run(cmd: list[str], timeout: int = 3600) -> tuple[int, str]:
    """Chạy lệnh và trả về `(returncode, output)`.

    Args:
        cmd: Lệnh cần chạy.
        timeout: Timeout tối đa (giây).

    Returns:
        Tuple `(returncode, output gộp stdout+stderr)`.
    """
    print(f"$ {' '.join(cmd)}", flush=True)
    proc = subprocess.run(
        cmd,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=kaggle_env(),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-4000:], flush=True)
    return proc.returncode, out


def kernel_state() -> str:
    """Lấy trạng thái kernel.

    Returns:
        Chuỗi trạng thái (rỗng nếu lỗi).
    """
    proc = subprocess.run(
        ["kaggle", "kernels", "status", KERNEL],
        capture_output=True,
        text=True,
        timeout=120,
        env=kaggle_env(),
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for token in ("COMPLETE", "ERROR", "RUNNING", "QUEUED", "CANCELLED", "STARTING"):
        if token in out:
            return token
    return ""


def wait_kernel(timeout_s: int = 7200) -> str:
    """Chờ kernel chạy xong.

    Args:
        timeout_s: Timeout tối đa (giây).

    Returns:
        Trạng thái cuối cùng.
    """
    started = time.time()
    last = ""
    while time.time() - started < timeout_s:
        state = kernel_state()
        if state != last:
            print(f"[{time.time() - started:.0f}s] trạng thái: {state}", flush=True)
            last = state
        if state in ("COMPLETE", "ERROR", "CANCELLED"):
            return state
        time.sleep(45)
    return "TIMEOUT"


def download() -> bool:
    """Tải output kernel và giải nén `re_phobert.jsonl`.

    Returns:
        ``True`` nếu thành công.
    """
    DL_DIR.mkdir(parents=True, exist_ok=True)
    code, out = run(["kaggle", "kernels", "output", KERNEL, "-p", str(DL_DIR), "-o"], timeout=3600)
    if code != 0:
        print("Tải output thất bại.", flush=True)
        return False
    archives = list(DL_DIR.glob("*.zip"))
    for archive in archives:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(DL_DIR)
    candidate = DL_DIR / "re_phobert.jsonl"
    if not candidate.exists():
        candidates = [p for p in DL_DIR.rglob("re_phobert.jsonl")]
        if not candidates:
            print(f"Không tìm thấy re_phobert.jsonl trong {DL_DIR}", flush=True)
            return False
        candidate = candidates[0]
    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    candidate.replace(OUT_JSONL)
    print(f"Đã đặt {OUT_JSONL} ({OUT_JSONL.stat().st_size} bytes)", flush=True)
    return True


def check_gate() -> dict:
    """Chấm Gate Phase 8.

    Returns:
        Dict kết quả từng mục Gate.
    """
    result: dict = {}

    metrics_path = REPO / "models" / "re" / "metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        per = metrics.get("per_relation") or {}
        result["G1_re_f1_micro"] = {
            "expected": ">= 0.70",
            "actual": metrics.get("micro_f1"),
            "pass": float(metrics.get("micro_f1") or 0) >= 0.70,
            "relations_f1_ge_070": sum(
                1 for v in per.values() if float(v.get("f1") or 0) >= 0.70
            ),
            "relations_total": len(per),
        }

    rows = [json.loads(line) for line in MERGED.open(encoding="utf-8")] if MERGED.exists() else []
    required = ("evidence_sentence", "source_url", "doc_id", "sentence_id")
    missing = sum(1 for r in rows if not all(r.get(k) for k in required))
    result["G2_required_fields"] = {
        "expected": "100%",
        "actual": f"{len(rows) - missing}/{len(rows)}",
        "pass": missing == 0,
    }
    keys = {(r.get("subject"), r.get("relation"), r.get("object")) for r in rows}
    result["G3_no_duplicate"] = {
        "expected": "0 trùng",
        "actual": len(rows) - len(keys),
        "pass": len(rows) == len(keys),
    }
    outside = sum(1 for r in rows if r.get("relation") not in RELATIONS)
    result["G4_no_out_of_catalog"] = {
        "expected": "0",
        "actual": outside,
        "pass": outside == 0,
    }

    out_path = REPO / "reports" / "phase_08_gate_check.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return result


def main() -> int:
    """Chạy chuỗi chờ → tải → merge → chấm Gate.

    Returns:
        Exit code.
    """
    state = wait_kernel()
    print(f"Trạng thái cuối: {state}", flush=True)
    if state != "COMPLETE":
        print("Kernel không COMPLETE — dừng.", flush=True)
        return 1
    if not download():
        return 1
    code, _ = run([sys.executable, "-m", "src.re.merge_triples", "--out", str(MERGED)])
    if code != 0:
        return code
    check_gate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Chuỗi hoàn tất Phase 8 tự động sau khi kernel Kaggle CPU xong.

Bước:
1. Chờ kernel `hoanghiep421/vhgr-phase-8-re-train-phobert-base-cpu` → COMPLETE
2. Tải `models/re` về
3. Chạy `src.re.infer_re` → `data/interim/re_phobert.jsonl`
4. Chạy `src.re.merge_triples` → `data/interim/triples_merged.jsonl`
5. Chấm Gate G1 theo `docs/09` §Phase 8

Dùng:
    python scripts/finish_phase8.py --out data/interim/re_phobert.jsonl
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
KERNEL = "hoanghiep421/vhgr-phase-8-re-train-phobert-base-cpu"
MODEL_DIR = REPO / "models" / "re"
RELATIONS = {
    "cha_cua", "me_cua", "vo_cua", "chong_cua", "anh_em_cua", "thuoc_trieu_dai",
    "ke_vi", "giu_chuc_vu", "lap_ra", "chi_huy_tran", "tham_gia_tran", "danh_bai",
    "dien_ra_tai", "sinh_tai", "mat_tai", "sinh_nam", "mat_nam", "dong_doi_tai",
}


def env_token() -> str:
    from dotenv import dotenv_values

    return (dotenv_values(REPO / ".env").get("KAGGLE_KEY") or "").strip()


def run(cmd: list[str], timeout: int = 7200, env_extra: dict[str, str] | None = None) -> tuple[int, str]:
    print(f"$ {' '.join(cmd)}", flush=True)
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        cmd, cwd=str(REPO), capture_output=True, text=True, timeout=timeout, env=env
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out[-3000:], flush=True)
    return proc.returncode, out


def kernel_state() -> str:
    env = dict(os.environ)
    env["KAGGLE_API_TOKEN"] = env_token()
    proc = subprocess.run(
        ["kaggle", "kernels", "status", KERNEL],
        capture_output=True, text=True, env=env, timeout=90,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for state in ("COMPLETE", "ERROR", "CANCELLED", "DEADLINE_EXCEEDED", "RUNNING", "QUEUED"):
        if state in out:
            return state
    return "UNKNOWN"


def download_kernel() -> bool:
    env = dict(os.environ)
    env["KAGGLE_API_TOKEN"] = env_token()
    target = REPO / "models" / "re_kaggle_raw"
    target.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["kaggle", "kernels", "output", KERNEL, "-p", str(target)],
        capture_output=True, text=True, env=env, timeout=3600,
    )
    print((proc.stdout or "") + (proc.stderr or "")[-2000:], flush=True)
    return proc.returncode == 0


def install_model(raw_dir: Path) -> bool:
    """Chép artifact từ zip output của Kaggle vào `models/re`."""
    import zipfile

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for archive in sorted(raw_dir.glob("*.zip")):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(raw_dir / "_unzipped")
    src = raw_dir / "_unzipped"
    # Kaggle đóng gói `/kaggle/working/models/re` → tìm thư mục chứa metrics.json
    candidates = [p for p in src.rglob("metrics.json")]
    if not candidates:
        print("Không tìm thấy metrics.json trong output Kaggle")
        return False
    root = candidates[0].parent
    print(f"Nguồn model: {root}")
    for item in root.iterdir():
        dest = MODEL_DIR / item.name
        if item.is_dir():
            if dest.exists():
                continue
            import shutil

            shutil.copytree(item, dest)
        else:
            import shutil

            shutil.copy2(item, dest)
    print("Đã cài model vào", MODEL_DIR)
    return True


def gate_check(merged: Path) -> dict:
    rows = [json.loads(line) for line in merged.open(encoding="utf-8")]
    required = ("evidence_sentence", "source_url", "doc_id", "sentence_id")
    missing = sum(1 for r in rows if not all(r.get(k) for k in required))
    bad_conf = sum(1 for r in rows if not 0 <= float(r.get("confidence", -1)) <= 1)
    bad_rel = sum(1 for r in rows if r.get("relation") not in RELATIONS)
    keys = {(r.get("subject"), r.get("relation"), r.get("object")) for r in rows}
    methods: dict[str, int] = {}
    for r in rows:
        methods[r.get("method", "?")] = methods.get(r.get("method", "?"), 0) + 1
    metrics_path = MODEL_DIR / "metrics.json"
    f1 = None
    if metrics_path.exists():
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        f1 = (payload.get("micro") or {}).get("f1")
    llm_stats = REPO / "data" / "interim" / "re_llm.stats.json"
    llm = json.loads(llm_stats.read_text(encoding="utf-8")) if llm_stats.exists() else {}
    return {
        "n_triples": len(rows),
        "missing_required_fields": missing,
        "invalid_confidence": bad_conf,
        "invalid_relation": bad_rel,
        "duplicate_keys": len(rows) - len(keys),
        "by_method": methods,
        "re_micro_f1_dev": f1,
        "llm_evidence_substring_ratio": llm.get("evidence_substring_ratio_before_filter"),
        "llm_kept_ratio": llm.get("kept_ratio_after_filter"),
        "gate": {
            "G1_re_f1_dev_ge_0.70": (f1 is not None and f1 >= 0.70),
            "G2_all_triples_have_required_fields": missing == 0,
            "G3_no_duplicate_triples": len(rows) == len(keys),
            "G4_no_relation_outside_catalog": bad_rel == 0,
            "G5_llm_evidence_ge_0.90": (llm.get("evidence_substring_ratio_before_filter") or 0) >= 0.90,
            "G6_llm_kept_ge_0.60": (llm.get("kept_ratio_after_filter") or 0) >= 0.60,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/interim/re_phobert.jsonl")
    parser.add_argument("--poll", type=int, default=180)
    parser.add_argument("--max-minutes", type=int, default=240)
    args = parser.parse_args()

    deadline = time.time() + args.max_minutes * 60
    state = ""
    while time.time() < deadline:
        current = kernel_state()
        if current != state:
            print(f"[{time.strftime('%H:%M:%S')}] kernel: {current}", flush=True)
            state = current
        if state == "COMPLETE":
            break
        if state in ("ERROR", "CANCELLED", "DEADLINE_EXCEEDED"):
            print("Kernel thất bại:", state)
            return 2
        time.sleep(args.poll)

    if state != "COMPLETE":
        print("Hết thời gian chờ kernel")
        return 1

    raw = REPO / "models" / "re_kaggle_raw"
    if not download_kernel():
        return 2
    if not install_model(raw):
        return 2

    # Chạy song song 4 shard (CPU): mỗi shard xử lý 1/N cặp ứng viên.
    # Đo được: 0,0745 s/cặp với 1 tiến trình / 8 thread → 99.348 cặp ≈ 2 giờ;
    # chia 4 shard × 2 thread → ≈ 35-50 phút.
    rc, _ = run([sys.executable, "scripts/run_infer_re_parallel.py",
                 "--model", str(MODEL_DIR), "--out", args.out,
                 "--shards", "4", "--threads", "2", "--batch-size", "256"],
                timeout=14400)
    if rc != 0:
        print("infer_re thất bại")
        return rc

    rc, _ = run([sys.executable, "-m", "src.re.merge_triples",
                 "--out", "data/interim/triples_merged.jsonl"], timeout=3600)
    if rc != 0:
        return rc

    report = gate_check(REPO / "data" / "interim" / "triples_merged.jsonl")
    out_path = REPO / "reports" / "phase_08_gate_check.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

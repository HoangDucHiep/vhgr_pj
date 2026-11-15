"""Benchmark tốc độ train RE trên Kaggle (CPU vs GPU) — chạy ~2 phút.

Đo: số step/s cho PhoBERT-base, seq_len 96, batch 8/16/32 trên thiết bị hiện có.
Mục đích: quyết định có khả thi train trên CPU (thời gian thực tế) hay phải chờ GPU.

Dùng:
    python scripts/build_kaggle_bench_notebook.py --out /tmp/bench --gpu
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CELLS = [
    {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "# %%\n",
            "import json\n",
            "import os\n",
            "import time\n",
            "from pathlib import Path\n",
            "\n",
            "import torch\n",
            "from transformers import AutoModelForSequenceClassification, AutoTokenizer\n",
            "\n",
            "MODEL_ID = os.environ.get('BENCH_MODEL', 'vinai/phobert-base')\n",
            "MODEL_DIR = Path('/kaggle/input/datasets/hoanghiep421/vhgr-re-data/models_hf/phobert-base')\n",
            "MODEL_PATH = str(MODEL_DIR) if MODEL_DIR.exists() else MODEL_ID\n",
            "SEQ = int(os.environ.get('BENCH_SEQ', '96'))\n",
            "NUM_LABELS = 19\n",
            "\n",
            "print('torch', torch.__version__, '| cuda', torch.cuda.is_available())\n",
            "if torch.cuda.is_available():\n",
            "    print('GPU:', torch.cuda.get_device_name(0))\n",
            "\n",
            "tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, use_fast=False)\n",
            "if tokenizer.pad_token is None:\n",
            "    tokenizer.pad_token = tokenizer.eos_token\n",
            "model = AutoModelForSequenceClassification.from_pretrained(\n",
            "    MODEL_PATH, num_labels=NUM_LABELS, problem_type='multi_label_classification'\n",
            ")\n",
            "device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')\n",
            "model.to(device)\n",
            "model.train()\n",
            "\n",
            "import torch.nn.functional as F\n",
            "\n",
            "results = {}\n",
            "for batch_size in (8, 16, 32):\n",
            "    ids = torch.randint(100, 1000, (batch_size, SEQ))\n",
            "    mask = torch.ones_like(ids)\n",
            "    labels = torch.rand(batch_size, NUM_LABELS).round()\n",
            "    opt = torch.optim.AdamW(model.parameters(), lr=1e-5)\n",
            "    # warmup\n",
            "    for _ in range(2):\n",
            "        out = model(input_ids=ids.to(device), attention_mask=mask.to(device), labels=labels.to(device))\n",
            "        out.loss.backward()\n",
            "        opt.step()\n",
            "        opt.zero_grad()\n",
            "    n_iter = 8\n",
            "    start = time.time()\n",
            "    for _ in range(n_iter):\n",
            "        out = model(input_ids=ids.to(device), attention_mask=mask.to(device), labels=labels.to(device))\n",
            "        out.loss.backward()\n",
            "        opt.step()\n",
            "        opt.zero_grad()\n",
            "    elapsed = time.time() - start\n",
            "    per_step = elapsed / n_iter\n",
            "    results[str(batch_size)] = {\n",
            "        'sec_per_step': round(per_step, 3),\n",
            "        'sec_per_example': round(per_step / batch_size, 4),\n",
            "        'steps_per_sec': round(1 / per_step, 3),\n",
            "    }\n",
            "    print(f'batch={batch_size}: {per_step:.3f}s/step | {per_step/batch_size:.4f}s/example')\n",
            "\n",
            "print('RESULTS', json.dumps(results))\n",
            "Path('/kaggle/working/bench.json').write_text(json.dumps(results, indent=1), encoding='utf-8')\n",
            "import shutil\n",
            "shutil.make_archive('/kaggle/working/bench', 'zip', '/kaggle/working/bench.json')\n",
            "print('DONE')\n",
        ],
    }
]


def build(gpu: bool) -> dict:
    return {
        "cells": CELLS,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.12.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/bench")
    parser.add_argument("--gpu", action="store_true")
    parser.add_argument("--id", default="hoanghiep421/vhgr-bench-re-cpu")
    parser.add_argument("--title", default="VHGR bench RE CPU")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "notebook.ipynb").write_text(
        json.dumps(build(args.gpu), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    metadata = {
        "id": args.id,
        "title": args.title,
        "code_file": "notebook.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": args.gpu,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": ["hoanghiep421/vhgr-re-data"],
        "keywords": ["vietnamese"],
        "competition_sources": [],
        "model_sources": [],
    }
    (out / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Đã sinh {out} (gpu={args.gpu}, id={args.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

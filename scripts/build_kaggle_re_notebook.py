#!/usr/bin/env python
"""Sinh notebook Kaggle train RE PhoBERT (Phase 8).

Notebook tự chứa toàn bộ mã cần thiết (không phụ thuộc `src/` của repo) để
có thể chạy độc lập trên Kaggle.

Cách dùng:
    python scripts/build_kaggle_re_notebook.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = REPO_ROOT / "notebooks" / "kaggle"

#: Cell mã nguồn — train RE đa nhãn.
TRAIN_CODE = r'''
# %% [markdown]
# ## VHGR Phase 8 — Huấn luyện mô hình RE (Relation Extraction) PhoBERT
#
# Mô hình đa nhãn: 18 đầu sigmoid quan hệ + 1 đầu `NA`.
# Loss: BCE có mask (`-100.0` cho slot chưa biết).
#
# **Quy trắc nghiệm** (`docs/09` §Phase 8):
# - Seed 42, tách theo bài, artifact `models/re/metrics.json` + `trainer_state.json`.
# - Ngưỡng hiệu chỉnh trên tập dev → `metrics.json._meta.threshold`.

# %%
import gzip
import json
import math
import os
import random
import shutil
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
torch.cuda.manual_seed_all(SEED)

NUM_LABELS = 19
IGNORE_VALUE = -100.0
NA_INDEX = 18

#: Thư tự 18 quan hệ — phải khớp `src/common/schemas.py::RELATION_ORDER`.
RELATION_ORDER = (
    "cha_cua",
    "me_cua",
    "vo_cua",
    "chong_cua",
    "anh_em_cua",
    "thuoc_trieu_dai",
    "ke_vi",
    "giu_chuc_vu",
    "lap_ra",
    "chi_huy_tran",
    "tham_gia_tran",
    "danh_bai",
    "dien_ra_tai",
    "sinh_tai",
    "mat_tai",
    "sinh_nam",
    "mat_nam",
    "dong_doi_tai",
)

# --- Tìm thư mục dataset đã mount ------------------------------------------------
# Kaggle đặt tên thư mục mount theo slug, **có thể kèm hậu tố** (ví dụ
# `vhgr-re-data-2`) → không hard-code đường dẫn, dùng glob (như notebook NER).
INPUT_ROOT = Path("/kaggle/input")


def find_dataset_dir():
    """Tìm thư mục dataset chứa `re_model_input.jsonl*`.

    Returns:
        Path tới thư mục dataset.
    """
    candidates = sorted(
        path
        for path in INPUT_ROOT.rglob("re_model_input.jsonl*")
        if path.parent.is_dir()
    )
    if candidates:
        return candidates[0].parent
    fallback = Path("/kaggle/input/vhgr-re-data")
    print("CẢNH BÁO: không tìm thấy re_model_input.jsonl*, dùng", fallback)
    return fallback


DATA_DIR = find_dataset_dir()
OUT_DIR = Path("/kaggle/working/models/re")

# Kernel Kaggle **không có DNS** (D-038) → không tải được từ huggingface.co.
# Weight `vinai/phobert-base` được bundle sẵn trong dataset → dùng đường dẫn local.
MODEL_NAME = os.environ.get("RE_MODEL", "vinai/phobert-base")
MODEL_DIR = DATA_DIR / "models_hf" / MODEL_NAME.split("/")[-1]
if MODEL_DIR.exists():
    MODEL_PATH = str(MODEL_DIR)
    print("Dùng weight bundle trong dataset:", MODEL_PATH)
    print("Files:", sorted(p.name for p in MODEL_DIR.iterdir()))
else:
    MODEL_PATH = MODEL_NAME
    print("CẢNH BÁO: không thấy weight bundle, thử tải từ HuggingFace:", MODEL_PATH)

print("Torch:", torch.__version__, "| CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

# %%
def load_encoded(path):
    """Đọc artifact đã mã hoá (tự nhận diện `.gz`).

    Args:
        path: Đường dẫn file.

    Returns:
        Danh sách record.
    """
    records = []
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# Kaggle có thể giải nén `.gz` khi mount → tìm file theo glob thay vì hard-code.
corpus_files = sorted(DATA_DIR.glob("re_model_input.jsonl*"))
if not corpus_files:
    raise FileNotFoundError(f"Không tìm thấy re_model_input.jsonl* trong {DATA_DIR}")
CORPUS_PATH = corpus_files[0]
print("File corpus:", CORPUS_PATH)

records = load_encoded(CORPUS_PATH)
print("Số ví dụ:", len(records))
splits = json.loads((DATA_DIR / "splits.json").read_text(encoding="utf-8"))
print("Splits:", {k: len(v) for k, v in splits.items() if isinstance(v, list)})

by_split = {}
for record in records:
    by_split.setdefault(record.get("split", "train"), []).append(record)
for key, value in by_split.items():
    print(f"  {key}: {len(value)}")

# %%
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)

tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, use_fast=False)

# PhoBERT cần từ chối: mô hình đã có `pad_token`; thêm `problem_type`.
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token


class ReDataset(Dataset):
    """Dataset cho bài toán RE đa nhãn."""

    def __init__(self, rows):
        """Khởi tạo.

        Args:
            rows: Danh sách record đã mã hoá.
        """
        self.rows = rows

    def __len__(self):
        """Số ví dụ.

        Returns:
            Số lượng.
        """
        return len(self.rows)

    def __getitem__(self, index):
        """Lấy một ví dụ.

        Args:
            index: Chỉ số.

        Returns:
            Dict chứa `input_ids`, `attention_mask`, `labels`.
        """
        row = self.rows[index]
        return {
            "input_ids": row["input_ids"],
            "attention_mask": row["attention_mask"],
            "labels": row["labels"],
        }


def collate(batch, pad_token_id):
    """Pad batch: chuỗi theo max len, nhãn giữ đúng 19 chiều."""
    max_len = max(len(item["input_ids"]) for item in batch)
    input_ids = [
        item["input_ids"] + [pad_token_id] * (max_len - len(item["input_ids"]))
        for item in batch
    ]
    attention_mask = [
        item["attention_mask"] + [0] * (max_len - len(item["attention_mask"]))
        for item in batch
    ]
    labels = [item["labels"] for item in batch]
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.float),
    }


# %%
def masked_bce_loss(logits, labels):
    """BCE có mask: slot `-100.0` bị bỏ qua hoàn toàn."""
    mask = (labels != IGNORE_VALUE).to(logits.dtype)
    safe = torch.where(mask > 0, labels, torch.zeros_like(labels))
    per_slot = F.binary_cross_entropy_with_logits(logits, safe, reduction="none")
    total = (per_slot * mask).sum()
    count = mask.sum()
    return total if count == 0 else total / count


def sigmoid_np(logits):
    """Sigmoid ổn định cho mảng numpy."""
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -30, 30)))


def evaluate(model, loader, device):
    """Đánh giá trên tập dev → micro/macro F1 + đầu NA."""
    model.eval()
    all_logits, all_labels = [], []
    with torch.no_grad():
        for batch in loader:
            outputs = model(
                input_ids=batch["input_ids"].to(device),
                attention_mask=batch["attention_mask"].to(device),
            )
            all_logits.append(outputs.logits.detach().cpu().numpy())
            all_labels.append(batch["labels"].numpy())
    logits = np.concatenate(all_logits, axis=0)
    labels = np.concatenate(all_labels, axis=0)
    probs = sigmoid_np(logits)

    mask = labels != IGNORE_VALUE
    safe = np.where(mask, labels, 0.0)
    preds = (probs >= 0.5).astype(float) * mask

    tp = float((preds * safe).sum())
    fp = float((preds * (1 - safe) * mask).sum())
    fn = float(((1 - preds) * safe * mask).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    # Đầu NA riêng
    na_true = labels[:, NA_INDEX] == 1.0
    na_pred = probs[:, NA_INDEX] >= 0.5
    na_tp = float((na_true & na_pred).sum())
    na_fp = float((~na_true & na_pred).sum())
    na_fn = float((na_true & ~na_pred).sum())
    na_p = na_tp / (na_tp + na_fp) if (na_tp + na_fp) else 0.0
    na_r = na_tp / (na_tp + na_fn) if (na_tp + na_fn) else 0.0
    na_f1 = 2 * na_p * na_r / (na_p + na_r) if (na_p + na_r) else 0.0

    return {
        "eval_loss": float(masked_bce_loss(torch.tensor(logits), torch.tensor(labels))),
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1,
        "na_f1": na_f1,
        "logits": logits,
        "labels": labels,
    }


def per_relation_f1(logits, labels, threshold):
    """Tính P/R/F1 cho từng quan hệ (18 quan hệ) trên tập dev.

    Quan hệ bị **mask** (``-100.0``) không được giám sát cho input đó →
    không tính vào FN (không phải "quan hệ không tồn tại").
    """
    probs = sigmoid_np(logits)
    mask = labels != IGNORE_VALUE
    safe = np.where(mask, labels, 0.0)
    preds = (probs >= threshold).astype(float) * mask

    out = {}
    for index, name in enumerate(RELATION_ORDER):
        sup = mask[:, index]
        if not sup.any():
            out[name] = {"support": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
            continue
        tp = float((preds[:, index] * safe[:, index] * sup).sum())
        fp = float((preds[:, index] * (1 - safe[:, index]) * sup).sum())
        fn = float(((1 - preds[:, index]) * safe[:, index] * sup).sum())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[name] = {
            "support": int(sup.sum()),
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
        }

    scored = [v["f1"] for v in out.values() if v["support"] > 0]
    macro = round(sum(scored) / len(scored), 6) if scored else 0.0
    return out, macro


class MultiLabelTrainer(Trainer):
    """Trainer với loss BCE có mask cho đa nhãn."""

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        """Tính loss có mask.

        Args:
            model: Mô hình.
            inputs: Batch.
            return_outputs: Trả về logits kèm loss.
            num_items_in_batch: Số phần tử (transformers 5.x).

        Returns:
            Loss (và logits nếu `return_outputs`).
        """
        labels = inputs.get("labels")
        outputs = model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs.get("attention_mask"),
        )
        loss = None
        if labels is not None:
            loss = masked_bce_loss(outputs.logits, labels.to(outputs.logits.dtype))
        return (loss, outputs) if return_outputs else loss


# %%
train_rows = by_split.get("train", [])
dev_rows = by_split.get("dev", [])

# Subsample tập train (giữ nguyên dev để số đo Gate G1 nhất quán).
# Lý do: CPU Kaggle chậm (đo được 11,1 s/step @ batch 32 — xem
# docs/10-nhat-ky/so-lieu/phase-08-kaggle-cpu-benchmark.json). Subsample giữ
# đường chạy CPU khả thi trong thời gian báo cáo mà vẫn đạt Gate G1
# (smoke 400 ví dụ đã đạt micro-F1 0,695).
TRAIN_SUBSAMPLE = int(os.environ.get("RE_TRAIN_SUBSAMPLE", "0"))
if TRAIN_SUBSAMPLE and TRAIN_SUBSAMPLE < len(train_rows):
    import random as _random

    _rng = _random.Random(SEED)
    train_rows = _rng.sample(train_rows, TRAIN_SUBSAMPLE)
    print(f"Subsample train: {len(train_rows)} ví dụ (seed {SEED})")

train_ds = ReDataset(train_rows)
dev_ds = ReDataset(dev_rows)

train_loader = DataLoader(
    train_ds,
    batch_size=32,
    shuffle=True,
    collate_fn=lambda b: collate(b, tokenizer.pad_token_id),
)
dev_loader = DataLoader(
    dev_ds,
    batch_size=64,
    shuffle=False,
    collate_fn=lambda b: collate(b, tokenizer.pad_token_id),
)

print(f"Train: {len(train_ds)} | Dev: {len(dev_ds)}")

# %%
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_PATH, num_labels=NUM_LABELS, problem_type="multi_label_classification"
)
model.config.id2label = {i: f"REL_{i}" for i in range(NUM_LABELS)}
model.config.label2id = {f"REL_{i}": i for i in range(NUM_LABELS)}

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

EPOCHS = int(os.environ.get("RE_EPOCHS", "3"))
BATCH = int(os.environ.get("RE_BATCH", "16"))
EVAL_BATCH = int(os.environ.get("RE_EVAL_BATCH", "32"))
LR = float(os.environ.get("RE_LR", "2e-5"))

args = TrainingArguments(
    output_dir=str(OUT_DIR),
    num_train_epochs=EPOCHS,
    per_device_train_batch_size=BATCH,
    per_device_eval_batch_size=EVAL_BATCH,
    learning_rate=LR,
    seed=SEED,
    data_seed=SEED,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    logging_steps=int(os.environ.get("RE_LOGGING_STEPS", "100")),
    fp16=torch.cuda.is_available(),
    report_to=[],
    remove_unused_columns=False,
    label_names=["labels"],
    load_best_model_at_end=False,
)

trainer = MultiLabelTrainer(
    model=model,
    args=args,
    train_dataset=train_ds,
    eval_dataset=dev_ds,
    data_collator=lambda b: collate(b, tokenizer.pad_token_id),
)

trainer.train()

# %%
result = evaluate(trainer.model, dev_loader, device)
logits, labels = result.pop("logits"), result.pop("labels")
print("Dev:", {k: round(v, 4) if isinstance(v, float) else v for k, v in result.items()})

# Hiệu chỉnh ngưỡng trên dev (Gate: `metrics.json._meta.threshold`)
mask = labels != IGNORE_VALUE
safe = np.where(mask, labels, 0.0)
best_threshold, best_f1 = 0.5, -1.0
for threshold in np.arange(0.05, 0.96, 0.05):
    preds = ((sigmoid_np(logits) >= threshold).astype(float)) * mask
    tp = float((preds * safe).sum())
    fp = float((preds * (1 - safe) * mask).sum())
    fn = float(((1 - preds) * safe * mask).sum())
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    if f1 > best_f1:
        best_f1, best_threshold = f1, float(threshold)

print(f"Ngưỡng hiệu chỉnh: {best_threshold:.2f} | micro-F1 = {best_f1:.4f}")

# F1 per-relation tại ngưỡng đã hiệu chỉnh (Gate G1 yêu cầu trong `metrics.json`)
per_relation, macro_f1 = per_relation_f1(logits, labels, best_threshold)
print(f"Macro-F1 = {macro_f1:.4f}")
for name, values in per_relation.items():
    print(f"  {name:<18} support={values['support']:<5} F1={values['f1']:.4f}")

# %%
OUT_DIR.mkdir(parents=True, exist_ok=True)
trainer.save_model(str(OUT_DIR))
tokenizer.save_pretrained(str(OUT_DIR))

trainer_state = trainer.state.log_history
(OUT_DIR / "trainer_state.json").write_text(
    json.dumps(trainer_state, ensure_ascii=False, indent=1), encoding="utf-8"
)

metrics = {
    "_meta": {
        "phase": 8,
        "model": MODEL_NAME,
        "seed": SEED,
        "epochs": EPOCHS,
        "num_labels": NUM_LABELS,
        "threshold": round(best_threshold, 4),
        "na_threshold": 0.5,
        "n_train": len(train_ds),
        "n_dev": len(dev_ds),
        "dump_version": "20261101",
        "eval": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in result.items()},
    },
    "micro_f1": round(best_f1, 6),
    "micro_precision": round(result["micro_precision"], 6),
    "micro_recall": round(result["micro_recall"], 6),
    "macro_f1": macro_f1,
    "na_f1": round(result["na_f1"], 6),
    "threshold": round(best_threshold, 4),
    "per_relation": per_relation,
}
(OUT_DIR / "metrics.json").write_text(
    json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8"
)

print("Đã lưu model tại", OUT_DIR)
for item in sorted(OUT_DIR.iterdir()):
    print("  ", item.name, f"({item.stat().st_size/1e6:.1f} MB)")

# %%
# Đóng gói model để tải về
shutil.make_archive(str(OUT_DIR.parent / "models_re"), "zip", str(OUT_DIR))
print("Đã đóng gói:", OUT_DIR.parent / "models_re.zip")
'''

#: Cell markdown giới thiệu.
INTRO = """# VHGR Phase 8 — Huấn luyện mô hình RE (Relation Extraction) PhoBERT

Mô hình **đa nhãn sigmoid**: 18 đầu quan hệ + 1 đầu `NA` (không có quan hệ).

- Loss: BCE **có mask** — slot chưa biết được gán `-100.0` và bị bỏ qua.
- Marker có kiểu: `<<TYPE:SUBJ:name>>` / `<<TYPE:OBJ:name>>` giữ hướng quan hệ.
- Seed 42, tách theo bài, artifact `models/re/metrics.json` + `trainer_state.json`.
"""


def build_notebook(model_name: str = "vinai/phobert-base") -> dict:
    """Dựng notebook Kaggle train RE.

    Args:
        model_name: Tên model HuggingFace.

    Returns:
        Dict notebook theo định dạng nbformat 4.
    """
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": INTRO.splitlines(keepends=True),
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": TRAIN_CODE.splitlines(keepends=True),
            },
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11.0"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def main() -> int:
    """Sinh notebook cho base và large.

    Returns:
        Mã thoát.
    """
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    for slug, model in (
        ("re_train_phobert_base", "vinai/phobert-base"),
        ("re_train_phobert_large", "vinai/phobert-large"),
    ):
        folder = NOTEBOOK_DIR / slug
        folder.mkdir(parents=True, exist_ok=True)
        notebook = build_notebook(model)
        (folder / "notebook.ipynb").write_text(
            json.dumps(notebook, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        metadata = {
            "id": f"hoanghiep421/vhgr-phase-8-re-train-{model.split('-')[-1]}",
            "title": f"VHGR Phase 8 - RE train PhoBERT ({model.split('-')[-1]})",
            "code_file": "notebook.ipynb",
            "language": "python",
            "kernel_type": "notebook",
            "is_private": True,
            "enable_gpu": True,
            "enable_tpu": False,
            "enable_internet": True,
            "dataset_sources": ["hoanghiep421/vhgr-re-data"],
            "keywords": ["vietnamese", "wikipedia", "relation-extraction"],
            "competition_sources": [],
            "model_sources": [],
        }
        (folder / "kernel-metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"Đã sinh {folder}")
    return 0


def build_cpu_variant() -> int:
    """Sinh biến thể **CPU-only** của notebook RE (chạy trên Kaggle CPU notebook).

    Lý do: hàng đợi GPU của Kaggle là *dùng chung* và cả 2 kernel Phase 8 đều
    `QUEUED` (đo được 15/11/2026). Kaggle CPU notebook **không** tranh GPU ⇒
    đường chạy song song thứ 3, vẫn thuộc Kaggle (không huấn luyện local).

    Với 12.877 câu × 3 epoch, PhoBERT-base trên 2 vCPU ước tính ~2–3 giờ —
    dưới trần 9 giờ của Kaggle CPU notebook.
    """
    folder = NOTEBOOK_DIR / "re_train_phobert_base_cpu"
    folder.mkdir(parents=True, exist_ok=True)
    notebook = build_notebook("vinai/phobert-base")
    # CPU chậm hơn GPU ~8–10×. Điều chỉnh dựa trên **benchmark đo thật** trên
    # Kaggle CPU (kernel `hoanghiep421/vhgr-bench-re-cpu`, 15/11/2026):
    #   batch  8 → 3,226 s/step | 0,4033 s/example
    #   batch 16 → 5,936 s/step | 0,3710 s/example
    #   batch 32 → 11,103 s/step| 0,3470 s/example  ← tốt nhất (ít overhead)
    # ⇒ chọn batch 32, epoch 3→2, logging_steps 100→10 (đo ETA).
    # 20.382 ví dụ / 32 × 2 epoch ≈ 1.274 step × 11,1 s ≈ 3,9 giờ < trần 9 giờ.
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        cell["source"] = [
            part.replace('RE_EPOCHS", "3"', 'RE_EPOCHS", "2"')
            .replace('RE_BATCH", "16"', 'RE_BATCH", "32"')
            .replace('RE_EVAL_BATCH", "32"', 'RE_EVAL_BATCH", "32"')
            .replace('RE_LR", "2e-5"', 'RE_LR", "3e-5"')
            .replace(
                'RE_LOGGING_STEPS", "100"', 'RE_LOGGING_STEPS", "10"'
            )
            .replace(
                'RE_TRAIN_SUBSAMPLE", "0"', 'RE_TRAIN_SUBSAMPLE", "6000"'
            )
            for part in cell["source"]
        ]
    (folder / "notebook.ipynb").write_text(
        json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    metadata = {
        "id": "hoanghiep421/vhgr-phase-8-re-train-phobert-base-cpu",
        "title": "VHGR Phase 8 - RE train PhoBERT base CPU",
        "code_file": "notebook.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": False,
        "enable_tpu": False,
        "enable_internet": True,
        "dataset_sources": ["hoanghiep421/vhgr-re-data"],
        "keywords": ["vietnamese", "wikipedia", "relation-extraction"],
        "competition_sources": [],
        "model_sources": [],
    }
    (folder / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"Đã sinh {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main() if "--cpu-variant" not in sys.argv else build_cpu_variant())

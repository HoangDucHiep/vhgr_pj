"""Huấn luyện mô hình RE PhoBERT đa nhãn (Phase 8 — D1.2).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 8.

Cách chạy
---------
```bash
# Local CPU (smoke test)
python -m src.re.train_re --config configs/default.yaml \
    --max-train 5000 --epochs 1 --max-len 64 --out models/re_smoke

# Kaggle GPU (train thật)
python -m src.re.train_re --config configs/default.yaml --out models/re
```

Vì sao là **đa nhãn** chứ không phải 19 lớp đơn nhãn (D-061)
-------------------------------------------------------------
Đo được ở Phase 7: 14,7% input có nhãn mục tiêu mâu thuẫn dưới dạng đơn
nhãn; **1.777** input có ≥ 2 quan hệ POSITIVE (53,7% là cặp ``cha_cua`` +
``me_cua`` — quan hệ *song sinh* hợp lệ, không phải lỗi gán nhãn).

→ Mô hình có **19 đầu sigmoid** (18 quan hệ + 1 đầu ``NA``).

Mất đối chiếu (mask) — điểm cốt lõi của module này
--------------------------------------------------
Vector nhãn 19 chiều có ba loại giá trị:

| Giá trị | Nghĩa | Tính loss? |
|---|---|---|
| ``1.0`` | quan hệ POSITIVE | ✅ |
| ``0.0`` | quan hệ NEGATIVE (đã biết là **không** có) | ✅ |
| ``-100.0`` | quan hệ **chưa quan sát** (chưa biết) | ❌ bị mask |

Đo được trên tập Phase 7: **88,7%** slot là "chưa quan sát" (vd `lap_ra` chỉ
có slot cho 0,1% input). Nếu coi chúng là 0, mô hình bị dạy sai rằng quan hệ
đó vắng mặt ở hầu hết các câu → dự đoán sai khi suy luận.

→ Loss = ``BCEWithLogitsLoss`` có mask, chuẩn hoá theo **số slot quan sát**
(không phải số phần tử vector) → mỗi slot quan sát đóng góp như nhau.

Đầu ``NA``
-----------
Nhãn ``1.0`` khi input **không có** quan hệ POSITIVE nào, ``0.0`` ngược lại.
Đầu này **luôn** có supervision (đo được: 12.227/26.030 input = 47,0% có NA=1)
→ mô hình học được ngưỡng quyết định "cặp này có quan hệ nào không".

Nguyên tắc bắt buộc
-------------------
- ``seed=42`` (AGENTS.md §5.6).
- F1 đo bằng `src/evaluation/metrics.py::relation_f1_multilabel` (micro/macro/
  per-relation).
- ``dump_version`` + ``model_name`` ghi vào ``metrics.json`` (nguyên tắc 6).
- ``fp16`` chỉ bật khi có CUDA.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from src.common.config import load_default_config, resolve_path
from src.common.logger import get_logger
from src.common.seed import set_seed
from src.evaluation.metrics import relation_f1_multilabel
from src.re.data_convert_re import (
    IGNORE_VALUE,
    LABEL_LIST,
    NA_INDEX,
    NUM_LABELS,
    RELATION_ORDER,
    example_from_dict,
    read_jsonl,
)

logger = get_logger(__name__)

#: Tên file kết quả đánh giá trong thư mục model.
METRICS_FILENAME = "metrics.json"

#: Ngưỡng mặc định khi dự đoán quan hệ (sẽ hiệu chỉnh trên dev).
DEFAULT_THRESHOLD = 0.5


@dataclass(slots=True)
class PairMeta:
    """Metadata của một mẫu (dùng để tính metric ngoài Trainer).

    Attributes:
        key: Khoá input ``sentence_id|subject_id|object_id``.
        gold_relations: Tập quan hệ POSITIVE.
        masked_relations: Tập quan hệ chưa quan sát.
    """

    key: str
    gold_relations: list[str]
    masked_relations: list[str]


class ReDataset:
    """Dataset torch cho bài toán RE đa nhãn.

    Chỉ trả về các trường mà model nhận (``input_ids``, ``attention_mask``,
    ``labels``); metadata tính metric giữ riêng trong `PairMeta`.
    """

    def __init__(
        self,
        examples: Sequence[Any],
        metas: Sequence[PairMeta] | None = None,
    ) -> None:
        """Khởi tạo dataset.

        Args:
            examples: Danh sách `ReExample` đã mã hoá.
            metas: Danh sách metadata song song (tuỳ chọn).
        """
        self.examples = list(examples)
        self.metas = list(metas) if metas is not None else None

    def __len__(self) -> int:
        """Số mẫu.

        Returns:
            Độ dài dataset.
        """
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, Any]:
        """Lấy một mẫu.

        Args:
            index: Chỉ số mẫu.

        Returns:
            Dict gồm `input_ids`, `attention_mask`, `labels`.
        """
        example = self.examples[index]
        return {
            "input_ids": example.input_ids,
            "attention_mask": example.attention_mask,
            "labels": example.labels,
        }


class DynamicPadCollator:
    """Collator pad động theo batch dài nhất.

    Nhãn là vector 19 chiều → pad bằng ``IGNORE_VALUE`` (bị mask, không tính
    loss).
    """

    def __init__(self, pad_token_id: int) -> None:
        """Khởi tạo collator.

        Args:
            pad_token_id: Id token padding.
        """
        self.pad_token_id = pad_token_id

    def __call__(self, features: list[dict[str, Any]]) -> dict[str, Any]:
        """Pad một batch.

        Args:
            features: Danh sách feature của các mẫu.

        Returns:
            Batch torch đã pad.
        """
        import torch

        max_len = max(len(feature["input_ids"]) for feature in features)
        input_ids: list[list[int]] = []
        attention_mask: list[list[int]] = []
        labels: list[list[float]] = []
        for feature in features:
            pad_len = max_len - len(feature["input_ids"])
            input_ids.append(feature["input_ids"] + [self.pad_token_id] * pad_len)
            attention_mask.append(feature["attention_mask"] + [0] * pad_len)
            # Nhãn là vector **19 chiều** (mỗi mẫu một vector) → không pad
            # theo độ dài chuỗi. Mẫu thiếu chiều được đệm bằng `IGNORE_VALUE`.
            row = list(feature["labels"])
            if len(row) < NUM_LABELS:
                row = row + [IGNORE_VALUE] * (NUM_LABELS - len(row))
            labels.append(row[:NUM_LABELS])
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.float),
        }


def masked_bce_loss(logits: Any, labels: Any) -> Any:
    """Tính BCE-with-logits **có mask**.

    Args:
        logits: Logit thô (shape ``(batch, 19)``).
        labels: Nhãn (shape ``(batch, 19)``), ``-100`` = bị mask.

    Returns:
        Loss vô hướng (scalar tensor).
    """
    import torch
    import torch.nn.functional as F

    mask = (labels != IGNORE_VALUE).to(logits.dtype)
    safe_labels = torch.where(
        mask > 0, labels, torch.zeros_like(labels)
    )
    per_slot = F.binary_cross_entropy_with_logits(
        logits, safe_labels, reduction="none"
    )
    total = (per_slot * mask).sum()
    count = mask.sum()
    if count == 0:
        return total
    return total / count


def build_multi_label_trainer_class() -> Any:
    """Dựng lớp `Trainer` với loss đa nhãn có mask.

    HuggingFace mặc định dùng `CrossEntropyLoss` (đơn nhãn) hoặc
    `BCEWithLogitsLoss` **không mask** → phải ghi đè `compute_loss`.

    Returns:
        Lớp `Trainer` đã ghi đè.
    """
    from transformers import Trainer

    class MultiLabelTrainer(Trainer):
        """Trainer với loss BCE mask cho nhãn đa nhãn."""

        def compute_loss(  # type: ignore[override]
            self,
            model: Any,
            inputs: dict[str, Any],
            return_outputs: bool = False,
            num_items_in_batch: Any = None,
        ) -> Any:
            """Tính loss đa nhãn có mask.

            Args:
                model: Mô hình.
                inputs: Batch đầu vào (chứa ``labels``).
                return_outputs: Trả về thêm output của model.
                num_items_in_batch: Không dùng (chuẩn HF).

            Returns:
                Loss (và output nếu ``return_outputs``).
            """
            labels = inputs.get("labels")
            outputs = model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs.get("attention_mask"),
            )
            logits = outputs.logits
            if labels is None:
                loss = None
            else:
                loss = masked_bce_loss(logits, labels.to(logits.dtype))
            if not return_outputs:
                return loss
            return (loss, outputs)

    return MultiLabelTrainer


def sigmoid(values: Any) -> Any:
    """Hàm logistic (viết lại để không phụ thuộc numpy cụ thể).

    Args:
        values: Mảng giá trị thực.

    Returns:
        Mảng xác suất.
    """
    import numpy as np

    array = np.asarray(values, dtype="float64")
    return 1.0 / (1.0 + np.exp(-np.clip(array, -60.0, 60.0)))


def predict_relations(
    logits: Any,
    metas: Sequence[PairMeta],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    na_threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Chuyển logits 19 chiều thành quan hệ dự đoán.

    Args:
        logits: Logit (shape ``(n, 19)``).
        metas: Metadata từng mẫu.
        threshold: Ngưỡng kích hoạt quan hệ.
        na_threshold: Ngưỡng coi là "không có quan hệ nào".

    Returns:
        Cặp ``(pred_records, gold_records)`` cho `relation_f1_multilabel`.
    """
    probabilities = sigmoid(logits)
    pred_records: list[dict[str, Any]] = []
    gold_records: list[dict[str, Any]] = []
    for index, meta in enumerate(metas):
        row = probabilities[index]
        na_score = float(row[NA_INDEX])
        predicted: set[str] = set()
        if na_score < na_threshold:
            for relation_index, relation in enumerate(RELATION_ORDER):
                if float(row[relation_index]) > threshold:
                    predicted.add(relation)
        pred_records.append(
            {"key": meta.key, "predicted": sorted(predicted)}
        )
        gold_records.append(
            {
                "key": meta.key,
                "relations": sorted(meta.gold_relations),
                "masked": sorted(meta.masked_relations),
            }
        )
    return pred_records, gold_records


def calibrate_threshold(
    logits: Any,
    metas: Sequence[PairMeta],
    *,
    na_threshold: float = DEFAULT_THRESHOLD,
    candidates: Sequence[float] | None = None,
) -> tuple[float, float]:
    """Hiệu chỉnh ngưỡng quan hệ trên tập dev.

    Args:
        logits: Logit dev (shape ``(n, 19)``).
        metas: Metadata dev.
        na_threshold: Ngưỡng đầu ``NA``.
        candidates: Danh sách ngưỡng cần thử.

    Returns:
        Cặp ``(threshold, micro_f1)`` tối ưu.
    """
    if candidates is None:
        candidates = (
            0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
            0.55, 0.60, 0.65, 0.70, 0.75, 0.80,
        )
    best_threshold = DEFAULT_THRESHOLD
    best_f1 = -1.0
    for threshold in candidates:
        pred_records, gold_records = predict_relations(
            logits, metas, threshold=threshold, na_threshold=na_threshold
        )
        result = relation_f1_multilabel(pred_records, gold_records)
        micro_f1 = float(result["micro"]["f1"])
        if micro_f1 > best_f1:
            best_f1 = micro_f1
            best_threshold = threshold
    return best_threshold, best_f1


def build_compute_metrics(
    metas: Sequence[PairMeta],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> Any:
    """Tạo hàm `compute_metrics` cho `transformers.Trainer`.

    Args:
        metas: Metadata từng mẫu dev.
        threshold: Ngưỡng kích hoạt quan hệ.

    Returns:
        Callable ``(EvalPrediction) -> dict[str, float]``.
    """

    def compute_metrics(eval_prediction: Any) -> dict[str, float]:
        """Tính micro/macro F1 trên tập dev.

        Args:
            eval_prediction: `EvalPrediction` của Trainer.

        Returns:
            Dict giá trị vô hướng.
        """
        import numpy as np

        logits = np.asarray(eval_prediction.predictions)
        if logits.ndim == 1:
            logits = logits.reshape(-1, NUM_LABELS)
        pred_records, gold_records = predict_relations(
            logits, metas, threshold=threshold
        )
        result = relation_f1_multilabel(pred_records, gold_records)
        micro = result["micro"]
        macro = result["macro"]
        return {
            "f1": float(micro["f1"]),
            "precision": float(micro["precision"]),
            "recall": float(micro["recall"]),
            "micro_f1": float(micro["f1"]),
            "micro_precision": float(micro["precision"]),
            "micro_recall": float(micro["recall"]),
            "macro_f1": float(macro["f1"]),
            "macro_precision": float(macro["precision"]),
            "macro_recall": float(macro["recall"]),
            "na_f1": float(result["na"]["f1"]),
        }

    return compute_metrics


def save_metrics(
    out_dir: Path,
    metrics: dict[str, Any],
    *,
    model_name: str,
    dump_version: str,
    seed: int,
    split: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Ghi `metrics.json` vào thư mục model.

    Args:
        out_dir: Thư mục model.
        metrics: Kết quả đánh giá (kết quả của `relation_f1_multilabel`).
        model_name: Tên model đã dùng.
        dump_version: Phiên bản dump.
        seed: Seed đã dùng.
        split: Tập đánh giá.
        extra: Thông tin bổ sung (vd thời gian train, ngưỡng).

    Returns:
        Đường dẫn file vừa ghi.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "_meta": {
            "model_name": model_name,
            "dump_version": dump_version,
            "seed": seed,
            "split": split,
            "num_labels": NUM_LABELS,
            "label_list": list(LABEL_LIST),
            "scheme": "multi_label_sigmoid",
            "na_index": NA_INDEX,
        },
        "micro": metrics.get("micro", {}),
        "macro": metrics.get("macro", {}),
        "per_relation": metrics.get("per_relation", {}),
        "na": metrics.get("na", {}),
        "n_inputs": metrics.get("n_inputs", 0),
        "n_gold_pairs": metrics.get("n_gold_pairs", 0),
    }
    if extra:
        payload["_meta"].update(extra)
    path = out_dir / METRICS_FILENAME
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return path


def load_examples(path: str | Path) -> list[Any]:
    """Nạp artifact đã mã hoá.

    Args:
        path: Đường dẫn `re_model_input.jsonl`.

    Returns:
        Danh sách `ReExample`.
    """
    return [example_from_dict(record) for record in read_jsonl(path)]


def build_metas(examples: Sequence[Any]) -> list[PairMeta]:
    """Dựng metadata tính metric từ danh sách mẫu.

    Args:
        examples: Danh sách `ReExample`.

    Returns:
        Danh sách `PairMeta` song song.
    """
    return [
        PairMeta(
            key=example.key,
            gold_relations=list(example.gold_relations),
            masked_relations=list(example.masked_relations),
        )
        for example in examples
    ]


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Huấn luyện mô hình RE PhoBERT đa nhãn (Phase 8)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--encoded", default=None, help="Đường dẫn artifact mã hoá")
    parser.add_argument("--model", default=None, help="Tên model HuggingFace")
    parser.add_argument("--out", default=None, help="Thư mục lưu model")
    parser.add_argument("--max-train", type=int, default=0, help="Giới hạn số mẫu train")
    parser.add_argument("--max-dev", type=int, default=0, help="Giới hạn số mẫu dev")
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--max-len", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--eval-batch-size", type=int, default=None)
    parser.add_argument(
        "--grad-accum",
        type=int,
        default=None,
        help="Số bước tích lũy gradient (bù effective batch khi giảm batch size)",
    )
    parser.add_argument("--lr", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--fp16", action="store_true", help="Ép fp16 (chỉ khi có CUDA)")
    parser.add_argument("--no-fp16", action="store_true", help="Tắt fp16")
    args = parser.parse_args(argv)

    config = load_default_config()
    re_config = config.get("re", {})
    train_config = dict(re_config.get("train", {}))

    model_name = args.model or train_config.get("model_name") or re_config.get(
        "model_name", "vinai/phobert-base"
    )
    encoded_path = args.encoded or re_config.get(
        "encoded_path", "data/interim/re_model_input.jsonl"
    )
    out_dir = resolve_path(args.out or train_config.get("model_dir", "models/re"))

    epochs = args.epochs if args.epochs is not None else int(train_config.get("epochs", 5))
    max_len = args.max_len if args.max_len is not None else int(train_config.get("max_len", 256))
    seed = args.seed if args.seed is not None else int(train_config.get("seed", 42))
    learning_rate = (
        args.lr
        if args.lr is not None
        else float(train_config.get("learning_rate", 3e-5))
    )

    is_large = "large" in model_name.lower()
    default_batch = 8 if is_large else int(train_config.get("batch_size", 32))
    batch_size = (
        args.batch_size if args.batch_size is not None else default_batch
    )
    default_eval_batch = 16 if is_large else int(train_config.get("eval_batch_size", 64))
    eval_batch_size = args.eval_batch_size or default_eval_batch
    grad_accum = (
        args.grad_accum
        if args.grad_accum is not None
        else int(train_config.get("gradient_accumulation_steps", 1 if not is_large else 4))
    )
    dump_version = str(config.get("dump", {}).get("dump_version", ""))

    set_seed(seed)

    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        EarlyStoppingCallback,
        TrainingArguments,
    )

    use_fp16 = False
    if not args.no_fp16:
        use_fp16 = bool(args.fp16) or torch.cuda.is_available()

    logger.info(
        "Model: %s | epochs=%d | max_len=%d | bs=%d | eval_bs=%d | grad_accum=%d "
        "| lr=%s | seed=%d",
        model_name, epochs, max_len, batch_size, eval_batch_size, grad_accum,
        learning_rate, seed,
    )
    logger.info("fp16=%s | cuda=%s", use_fp16, torch.cuda.is_available())

    logger.info("Đọc artifact mã hoá: %s", encoded_path)
    all_examples = load_examples(encoded_path)
    train_examples = [example for example in all_examples if example.split == "train"]
    dev_examples = [example for example in all_examples if example.split == "dev"]
    if args.max_train:
        train_examples = train_examples[: args.max_train]
    if args.max_dev:
        dev_examples = dev_examples[: args.max_dev]
    logger.info(
        "train=%d mẫu | dev=%d mẫu", len(train_examples), len(dev_examples)
    )

    dev_metas = build_metas(dev_examples)

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=NUM_LABELS,
        id2label={index: label for index, label in enumerate(LABEL_LIST)},
        label2id={label: index for index, label in enumerate(LABEL_LIST)},
        problem_type="multi_label_classification",
    )

    checkpoint_dir = resolve_path(
        train_config.get("checkpoint_dir", "models/_checkpoints")
    ) / out_dir.name

    steps_per_epoch = max(1, (len(train_examples) + batch_size - 1) // batch_size)
    total_steps = steps_per_epoch * epochs
    warmup_steps = int(total_steps * float(train_config.get("warmup_ratio", 0.1)))

    training_args = TrainingArguments(
        output_dir=str(checkpoint_dir),
        seed=seed,
        save_total_limit=int(train_config.get("save_total_limit", 2)),
        save_strategy="epoch",
        eval_strategy="epoch",
        metric_for_best_model="f1",
        greater_is_better=True,
        load_best_model_at_end=True,
        fp16=use_fp16,
        report_to="none",
        logging_steps=int(train_config.get("logging_steps", 100)),
        learning_rate=learning_rate,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=eval_batch_size,
        gradient_accumulation_steps=grad_accum,
        weight_decay=float(train_config.get("weight_decay", 0.01)),
        warmup_steps=warmup_steps,
        max_grad_norm=float(train_config.get("max_grad_norm", 1.0)),
        dataloader_num_workers=int(train_config.get("dataloader_num_workers", 2)),
        label_names=["labels"],
        remove_unused_columns=False,
    )

    trainer_cls = build_multi_label_trainer_class()
    trainer = trainer_cls(
        model=model,
        args=training_args,
        train_dataset=ReDataset(train_examples),
        eval_dataset=ReDataset(dev_examples),
        data_collator=DynamicPadCollator(model.config.pad_token_id),
        compute_metrics=build_compute_metrics(dev_metas),
        callbacks=[
            EarlyStoppingCallback(
                early_stopping_patience=int(
                    train_config.get("early_stopping_patience", 2)
                )
            )
        ],
    )

    started = time.time()
    trainer.train()
    train_seconds = time.time() - started

    eval_output = trainer.evaluate()
    logger.info("Eval: %s", eval_output)

    trainer.save_model(str(out_dir))

    from src.ner.data_convert import load_tokenizer

    tokenizer = load_tokenizer(model_name)
    tokenizer.save_pretrained(str(out_dir))

    trainer_state = trainer.state
    state_payload = {
        "best_metric": trainer_state.best_metric,
        "best_model_checkpoint": trainer_state.best_model_checkpoint,
        "global_step": trainer_state.global_step,
        "epoch": trainer_state.epoch,
        "max_steps": trainer_state.max_steps,
        "log_history": trainer_state.log_history,
    }
    (out_dir / "trainer_state.json").write_text(
        json.dumps(state_payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    tokenizer_dir = out_dir / "tokenizer"
    tokenizer_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(str(tokenizer_dir))

    # Tính lại metric chi tiết trên dev + hiệu chỉnh ngưỡng.
    import numpy as np

    predictions = trainer.predict(ReDataset(dev_examples))
    logits = np.asarray(predictions.predictions)
    if logits.ndim == 1:
        logits = logits.reshape(-1, NUM_LABELS)

    threshold, best_micro_f1 = calibrate_threshold(logits, dev_metas)
    logger.info("Ngưỡng hiệu chỉnh: %.2f | micro-F1 = %.4f", threshold, best_micro_f1)

    pred_records, gold_records = predict_relations(
        logits, dev_metas, threshold=threshold
    )
    detailed = relation_f1_multilabel(pred_records, gold_records)

    metrics_path = save_metrics(
        out_dir,
        detailed,
        model_name=model_name,
        dump_version=dump_version,
        seed=seed,
        split="dev",
        extra={
            "train_seconds": round(train_seconds, 1),
            "n_train_examples": len(train_examples),
            "n_dev_examples": len(dev_examples),
            "epochs": epochs,
            "max_len": max_len,
            "batch_size": batch_size,
            "eval_batch_size": eval_batch_size,
            "gradient_accumulation_steps": grad_accum,
            "learning_rate": learning_rate,
            "fp16": use_fp16,
            "threshold": threshold,
            "na_threshold": DEFAULT_THRESHOLD,
            "encoded_path": str(encoded_path),
        },
    )
    logger.info("Đã ghi %s", metrics_path)
    logger.info(
        "Micro F1 = %.4f | Macro F1 = %.4f | NA F1 = %.4f",
        detailed["micro"]["f1"],
        detailed["macro"]["f1"],
        detailed["na"]["f1"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

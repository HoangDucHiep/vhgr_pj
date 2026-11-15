"""Huấn luyện mô hình NER PhoBERT trên nhãn bạc (Phase 5 — B1).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 5.

Cách chạy
---------
```bash
# Local CPU (smoke test)
python -m src.ner.train_ner --config configs/default.yaml \
    --max-train 5000 --epochs 1 --max-len 64 --out models/ner_smoke

# Kaggle GPU (train thật)
python -m src.ner.train_ner --config configs/default.yaml --out models/ner
```

Nguyên tắc bắt buộc
-------------------
- Scheme **BIO 13 lớp** (`2 * 6 + 1`), không phải 25 (D-031).
- `seed=42` (AGENTS.md §5.6).
- F1 đo bằng `src/evaluation/metrics.py::ner_f1` (entity-level, span).
- `dump_version` + `model_name` ghi vào `metrics.json` (nguyên tắc 6).
- `fp16` chỉ bật khi có CUDA.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from src.common.config import load_config, resolve_path
from src.common.logger import get_logger
from src.common.seed import set_seed
from src.evaluation.metrics import ner_f1
from src.ner.data_convert import (
    ID2LABEL,
    IGNORE_INDEX,
    LABEL2ID,
    LABEL_LIST,
    NUM_LABELS,
    EncodedExample,
    build_examples,
    gold_word_labels,
    iter_silver_by_split,
    load_tokenizer,
)

logger = get_logger(__name__)

#: Tên file kết quả đánh giá trong thư mục model.
METRICS_FILENAME = "metrics.json"


@dataclass(slots=True)
class ExampleMeta:
    """Thông tin bổ sung của một mẫu đánh giá (dùng để dựng span).

    Attributes:
        word_ids: Chỉ số word của từng subword.
        n_words: Tổng số word của câu.
        gold_word_labels: Nhãn gold ở mức word (id).
        sentence_id: Id câu.
    """

    word_ids: list[int]
    n_words: int
    gold_word_labels: list[int]
    sentence_id: str


class NerDataset:
    """Dataset torch đơn giản cho token classification.

    Chỉ trả về các trường mà model nhận (`input_ids`, `attention_mask`,
    `labels`); metadata đánh giá giữ riêng trong `ExampleMeta` để tránh
    lỗi "unexpected keyword argument" khi forward.
    """

    def __init__(self, examples: Sequence[EncodedExample]) -> None:
        """Khởi tạo dataset.

        Args:
            examples: Danh sách mẫu đã mã hóa.
        """
        self.examples = list(examples)

    def __len__(self) -> int:
        """Số mẫu.

        Returns:
            Độ dài dataset.
        """
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, list[int]]:
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
    """Collator pad động theo batch dài nhất (nhanh hơn pad cố định)."""

    def __init__(self, pad_token_id: int) -> None:
        """Khởi tạo collator.

        Args:
            pad_token_id: Id token padding.
        """
        self.pad_token_id = pad_token_id

    def __call__(self, features: list[dict[str, list[int]]]) -> dict[str, Any]:
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
        labels: list[list[int]] = []
        for feature in features:
            pad_len = max_len - len(feature["input_ids"])
            input_ids.append(feature["input_ids"] + [self.pad_token_id] * pad_len)
            attention_mask.append(feature["attention_mask"] + [0] * pad_len)
            labels.append(feature["labels"] + [IGNORE_INDEX] * pad_len)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def build_meta(
    examples: Sequence[EncodedExample],
    gold_by_sentence: dict[str, list[int]],
) -> list[ExampleMeta]:
    """Dựng metadata đánh giá cho từng mẫu.

    Args:
        examples: Danh sách mẫu đã mã hóa.
        gold_by_sentence: Map ``sentence_id`` → nhãn gold ở mức word (id).

    Returns:
        Danh sách `ExampleMeta` song song với `examples`.
    """
    meta: list[ExampleMeta] = []
    for example in examples:
        meta.append(
            ExampleMeta(
                word_ids=list(example.word_ids),
                n_words=example.n_words,
                gold_word_labels=list(gold_by_sentence.get(example.sentence_id, [])),
                sentence_id=example.sentence_id,
            )
        )
    return meta


def merge_windows_to_sentence(
    predictions: list[list[int]],
    metas: Sequence[ExampleMeta],
    example_sentence_ids: Sequence[str],
) -> dict[str, list[int]]:
    """Gộp nhãn dự đoán của các cửa sổ thành nhãn ở mức câu.

    Với mỗi word, lấy nhãn từ cửa sổ **đầu tiên** có dự đoán cho word đó
    (cửa sổ đầu có nhiều ngữ cảnh hơn).

    Args:
        predictions: Danh sách nhãn id ở mức word, theo từng mẫu.
        metas: Metadata của từng mẫu.
        example_sentence_ids: Id câu của từng mẫu.

    Returns:
        Map ``sentence_id`` → nhãn id ở mức word cho toàn câu.
    """
    merged: dict[str, list[int]] = {}
    filled: dict[str, set[int]] = {}
    for example_index, (word_labels, meta) in enumerate(zip(predictions, metas)):
        sentence_id = example_sentence_ids[example_index]
        if sentence_id not in merged:
            merged[sentence_id] = [LABEL2ID["O"]] * meta.n_words
            filled[sentence_id] = set()
        sentence_labels = merged[sentence_id]
        covered = filled[sentence_id]
        for word_id, label_id in enumerate(word_labels):
            if word_id >= len(sentence_labels) or word_id in covered:
                continue
            sentence_labels[word_id] = label_id
            covered.add(word_id)
    return merged


def bio_labels_to_strings(label_ids: Sequence[int]) -> list[str]:
    """Chuyển nhãn id → chuỗi BIO.

    Args:
        label_ids: Danh sách id nhãn ở mức word.

    Returns:
        Danh sách nhãn BIO ở mức word.
    """
    return [ID2LABEL[label_id] for label_id in label_ids]


def evaluate_predictions(
    merged_predictions: dict[str, list[int]],
    gold_by_sentence: dict[str, list[int]],
    tokens_by_sentence: dict[str, list[str]],
) -> dict[str, Any]:
    """Tính F1 entity-level bằng `src/evaluation/metrics.py`.

    Args:
        merged_predictions: Map ``sentence_id`` → nhãn id ở mức word.
        gold_by_sentence: Map ``sentence_id`` → nhãn gold id ở mức word.
        tokens_by_sentence: Map ``sentence_id`` → word của câu.

    Returns:
        Dict kết quả từ `ner_f1`.
    """
    pred_records: list[dict[str, Any]] = []
    gold_records: list[dict[str, Any]] = []
    for sentence_id, gold_ids in gold_by_sentence.items():
        tokens = tokens_by_sentence.get(sentence_id, [])
        pred_ids = merged_predictions.get(sentence_id, [LABEL2ID["O"]] * len(gold_ids))
        pred_records.append(
            {
                "sentence_id": sentence_id,
                "tokens": tokens,
                "labels": bio_labels_to_strings(pred_ids),
            }
        )
        gold_records.append(
            {
                "sentence_id": sentence_id,
                "tokens": tokens,
                "labels": bio_labels_to_strings(gold_ids),
            }
        )
    return ner_f1(pred_records, gold_records)


def build_compute_metrics(
    metas: Sequence[ExampleMeta],
    example_sentence_ids: Sequence[str],
    gold_by_sentence: dict[str, list[int]],
    tokens_by_sentence: dict[str, list[str]],
) -> Any:
    """Tạo hàm `compute_metrics` cho `transformers.Trainer`.

    Hàm trả về **chỉ giá trị vô hướng** (Trainer cần chúng để so sánh
    `metric_for_best_model`); phần chi tiết per-label được tính lại sau
    khi train bằng `evaluate_predictions`.

    Args:
        metas: Metadata từng mẫu dev.
        example_sentence_ids: Id câu từng mẫu dev.
        gold_by_sentence: Map ``sentence_id`` → nhãn gold id ở mức word.
        tokens_by_sentence: Map ``sentence_id`` → word của câu.

    Returns:
        Callable ``(EvalPrediction) -> dict[str, float]``.
    """
    from src.ner.data_convert import decode_word_labels

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
            # Trainer đã argmax sẵn (khi model có `labels` trong forward).
            logits = logits.reshape(-1, 1)
        if logits.ndim == 2 and logits.shape[-1] != NUM_LABELS:
            # Dạng đã argmax: (n_subword,) -> mở rộng để decode được.
            expanded = np.zeros((logits.shape[0], NUM_LABELS), dtype=logits.dtype)
            expanded[np.arange(logits.shape[0]), logits] = 1
            logits = expanded

        word_predictions: list[list[int]] = []
        for row_index, meta in enumerate(metas):
            word_predictions.append(
                decode_word_labels(
                    logits[row_index],
                    meta.word_ids,
                    num_words=meta.n_words,
                )
            )

        merged = merge_windows_to_sentence(
            word_predictions, metas, example_sentence_ids
        )
        result = evaluate_predictions(merged, gold_by_sentence, tokens_by_sentence)
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
        }

    return compute_metrics


def collect_gold(
    records: Sequence[dict[str, Any]],
) -> tuple[dict[str, list[int]], dict[str, list[str]]]:
    """Thu thập nhãn gold và word của câu.

    Args:
        records: Record nhãn bạc.

    Returns:
        Cặp ``(gold_by_sentence, tokens_by_sentence)``.
    """
    gold: dict[str, list[int]] = {}
    tokens: dict[str, list[str]] = {}
    for record in records:
        sentence_id = str(record.get("sentence_id", ""))
        gold[sentence_id] = gold_word_labels(list(record.get("labels") or []))
        tokens[sentence_id] = list(record.get("tokens") or [])
    return gold, tokens


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
        metrics: Kết quả đánh giá (kết quả của `ner_f1`).
        model_name: Tên model đã dùng.
        dump_version: Phiên bản dump.
        seed: Seed đã dùng.
        split: Tập đánh giá.
        extra: Thông tin bổ sung (vd thời gian train).

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
            "scheme": "BIO",
        },
        "micro": metrics.get("micro", {}),
        "macro": metrics.get("macro", {}),
        "per_label": metrics.get("per_label", {}),
        "n_sentences": metrics.get("n_sentences", 0),
        "n_gold_entities": metrics.get("n_gold_entities", 0),
        "n_pred_entities": metrics.get("n_pred_entities", 0),
    }
    if extra:
        payload["_meta"].update(extra)
    path = out_dir / METRICS_FILENAME
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return path


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Huấn luyện mô hình NER PhoBERT (Phase 5)"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--silver", default=None, help="Đường dẫn ner_silver.jsonl")
    parser.add_argument("--splits", default=None, help="Đường dẫn splits.json")
    parser.add_argument("--model", default=None, help="Tên model HuggingFace")
    parser.add_argument("--out", default=None, help="Thư mục lưu model")
    parser.add_argument("--max-train", type=int, default=0, help="Giới hạn số câu train")
    parser.add_argument("--max-dev", type=int, default=0, help="Giới hạn số câu dev")
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

    config = load_config(args.config)
    ner_config = config.get("ner", {})
    train_config = dict(ner_config.get("train", {}))

    model_name = args.model or train_config.get("model_name") or ner_config.get(
        "model_name", "vinai/phobert-base"
    )
    silver_path = args.silver or ner_config.get(
        "silver_path", "data/interim/ner_silver.jsonl"
    )
    splits_path = args.splits or ner_config.get(
        "splits_path", "data/splits/splits.json"
    )
    out_dir = resolve_path(args.out or ner_config.get("infer", {}).get("model_dir", "models/ner"))

    epochs = args.epochs if args.epochs is not None else int(train_config.get("epochs", 5))
    max_len = args.max_len if args.max_len is not None else int(train_config.get("max_len", 256))

    # `phobert-large` OOM với batch 32 × max_len 256 trên T4 14.5 GB
    # (đo được 14/11/2026 trên Kaggle). Giảm batch + bù bằng gradient
    # accumulation để giữ effective batch như cấu hình gốc.
    is_large = "large" in model_name.lower()
    default_batch = 8 if is_large else int(train_config.get("batch_size", 32))
    batch_size = (
        args.batch_size
        if args.batch_size is not None
        else default_batch
    )
    default_eval_batch = 16 if is_large else int(train_config.get("eval_batch_size", 64))
    eval_batch_size = args.eval_batch_size or default_eval_batch
    grad_accum = (
        args.grad_accum
        if args.grad_accum is not None
        else int(train_config.get("gradient_accumulation_steps", 1 if not is_large else 4))
    )
    learning_rate = (
        args.lr
        if args.lr is not None
        else float(train_config.get("learning_rate", 3e-5))
    )
    seed = args.seed if args.seed is not None else int(train_config.get("seed", 42))
    stride = int(train_config.get("stride", 64))
    dump_version = str(config.get("dump", {}).get("dump_version", ""))

    set_seed(seed)

    import torch
    from transformers import (
        AutoModelForTokenClassification,
        EarlyStoppingCallback,
        Trainer,
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

    tokenizer = load_tokenizer(model_name)

    logger.info("Đọc nhãn bạc: %s", silver_path)
    train_records = list(iter_silver_by_split(silver_path, splits_path, "train"))
    dev_records = list(iter_silver_by_split(silver_path, splits_path, "dev"))
    if args.max_train:
        train_records = train_records[: args.max_train]
    if args.max_dev:
        dev_records = dev_records[: args.max_dev]
    logger.info("train=%d câu | dev=%d câu", len(train_records), len(dev_records))

    train_examples = build_examples(
        train_records, tokenizer, max_len=max_len, stride=stride
    )
    dev_examples = build_examples(dev_records, tokenizer, max_len=max_len, stride=stride)
    logger.info(
        "Mẫu sau mã hóa: train=%d | dev=%d (cửa sổ trượt cho câu dài)",
        len(train_examples),
        len(dev_examples),
    )

    gold_by_sentence, tokens_by_sentence = collect_gold(dev_records)
    dev_metas = build_meta(dev_examples, gold_by_sentence)
    dev_sentence_ids = [example.sentence_id for example in dev_examples]

    model = AutoModelForTokenClassification.from_pretrained(
        model_name,
        num_labels=NUM_LABELS,
        id2label={index: label for index, label in ID2LABEL.items()},
        label2id=dict(LABEL2ID),
    )

    # Thư mục checkpoint tách khỏi thư mục model để `models/ner/` đúng
    # Output contract của `docs/09` §Phase 5.
    checkpoint_dir = resolve_path(
        ner_config.get("train", {}).get("checkpoint_dir", "models/_checkpoints")
    ) / out_dir.name

    # transformers 5.x đã bỏ `warmup_ratio` → tính thủ công `warmup_steps`.
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

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=NerDataset(train_examples),
        eval_dataset=NerDataset(dev_examples),
        data_collator=DynamicPadCollator(tokenizer.pad_token_id),
        compute_metrics=build_compute_metrics(
            dev_metas, dev_sentence_ids, gold_by_sentence, tokens_by_sentence
        ),
        callbacks=[
            EarlyStoppingCallback(
                early_stopping_patience=int(train_config.get("early_stopping_patience", 2))
            )
        ],
    )

    started = time.time()
    trainer.train()
    train_seconds = time.time() - started

    eval_output = trainer.evaluate()
    logger.info("Eval: %s", eval_output)

    trainer.save_model(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    # `trainer_state.json` là bắt buộc theo Output contract của `docs/09`.
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

    # `tokenizer/` subfolder theo Output contract (bản gốc ở gốc thư mục để
    # `AutoTokenizer.from_pretrained("models/ner")` nạp được).
    tokenizer_dir = out_dir / "tokenizer"
    tokenizer_dir.mkdir(parents=True, exist_ok=True)
    tokenizer.save_pretrained(str(tokenizer_dir))

    # Tính lại chi tiết per-label bằng chính `ner_f1` để ghi metrics.json.
    import numpy as np

    predictions = trainer.predict(NerDataset(dev_examples))
    logits = np.asarray(predictions.predictions)
    if logits.ndim == 2 and logits.shape[-1] != NUM_LABELS:
        expanded = np.zeros((logits.shape[0], NUM_LABELS), dtype=logits.dtype)
        expanded[np.arange(logits.shape[0]), logits] = 1
        logits = expanded
    from src.ner.data_convert import decode_word_labels

    word_predictions = [
        decode_word_labels(logits[index], meta.word_ids, num_words=meta.n_words)
        for index, meta in enumerate(dev_metas)
    ]
    merged = merge_windows_to_sentence(word_predictions, dev_metas, dev_sentence_ids)
    detailed = evaluate_predictions(merged, gold_by_sentence, tokens_by_sentence)

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
        },
    )
    logger.info("Đã ghi %s", metrics_path)
    logger.info(
        "Micro F1 = %.4f | Macro F1 = %.4f",
        detailed["micro"]["f1"],
        detailed["macro"]["f1"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

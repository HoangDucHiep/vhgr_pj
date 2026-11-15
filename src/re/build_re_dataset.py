"""Sinh tập huấn luyện RE từ mẫu POSITIVE + NEGATIVE an toàn (Phase 7).

Đặc tả: `docs/09-ke-hoach-thuc-thien.md` §Phase 7.

Output contract
---------------
`data/interim/re_train.jsonl` — **1 record/câu** (không phải 1 record/cặp),
theo `docs/09` §Phase 7 và `.cursor/rules/data-contracts.mdc`:

```json
{"run_id":"r20261115-143500","sentence_id":"s116_40_1","doc_id":"doc_116",
 "page_id":116,"split":"train","text":"Vua Xiêm sai hai tướng là Chiêu Tăng đem...",
 "pairs":[
   {"subject":{"mention":"Chiêu Tăng","entity_id":"ent_chiieu_tang_...","start":37,"end":46},
    "object":{"mention":"Chiêu Sương","entity_id":"ent_chieu_suong_...","start":58,"end":68},
    "relation":"anh_em_cua","label":"POSITIVE","source":"wikidata","property":"P3373"},
   {"subject":{"mention":"Chiêu Tăng","entity_id":"ent_chieu_tang_..."},
    "object":{"mention":"Chiêu Sương","entity_id":"ent_chieu_suong_..."},
    "relation":"cha_cua","label":"NEGATIVE","source":"distant_supervision"}]}
```

Ba điểm khác biệt so với dạng phẳng (bản đầu của phase):

1. **Gom theo câu** — một câu có nhiều cặp thì nằm chung trong `pairs`.
   Nhờ vậy Phase 8 chỉ cần tokenize `text` **một lần** cho mọi cặp.
2. **Nhãn là chuỗi** ``"POSITIVE"``/``"NEGATIVE"`` (không phải ``1``/``0``) —
   đúng như lệnh kiểm thử trong `docs/09` và plan.
3. **Có `run_id`** — bắt buộc theo `data-contracts.mdc` §Định dạng chung.

Vì sao NEGATIVE phải "an toàn" (D-057)
-------------------------------------
Negative của distant supervision là **cặp không có quan hệ trong Wikidata**.
Nhưng "không có trong Wikidata" ≠ "không có trong thực tế": nếu cặp đó thực sự
có quan hệ mà Wikidata chưa ghi, ta dạy mô hình đi sai.

→ Quy tắc: **chỉ lấy negative khi cả hai đầu đều có QID** (đã được Wikidata
xác nhận tồn tại) **và** không cặp QID nào của chúng mang quan hệ nào trong
tập cặp đã thu. Những cặp có một đầu không có QID bị **loại** (không dùng
làm negative) — đo được: 12.562 cặp an toàn vs 72.557 cặp "không rõ QID".

Tỉ lệ NEG/POS
--------------
Gate yêu cầu ``NEG/POS ≤ 1.0``. Với 15.580 POSITIVE, tối đa 15.580 NEGATIVE.
Pool an toàn có 256.847 cặp (theo quan hệ) → **dư** thừa, nên giới hạn
bằng cách lấy tối đa ``max_negatives_per_positive`` negative cho mỗi POSITIVE
và theo quan hệ (mỗi quan hệ giữ cân bằng, tránh thiên về quan hệ dồi).

Tính tái lập
-------------
Random seed 42 (`src/common/seed.py`), lựa chọn negative theo thứ tự quan hệ
và câu → cùng input cho cùng output.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from src.common.config import load_default_config, resolve_path
from src.common.ids import make_run_id
from src.common.logger import get_logger
from src.common.schemas import RELATION_TYPES
from src.re.ground_triples import CorpusIndex, iter_jsonl
from src.re.wikidata_relations import load_gates, load_relation_map

logger = get_logger(__name__)

#: Nhãn nguồn cho POSITIVE (chuỗi — theo contract `docs/09` §Phase 7).
POSITIVE_LABEL = "POSITIVE"

#: Nhãn nguồn cho NEGATIVE.
NEGATIVE_LABEL = "NEGATIVE"


def load_splits(path: str | Path) -> dict[int, str]:
    """Nạp map ``page_id`` → split.

    Args:
        path: Đường dẫn `splits.json`.

    Returns:
        Dict ``page_id`` → ``"train"``/``"dev"``/``"test"``.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    mapping: dict[int, str] = {}
    for split in ("train", "dev", "test"):
        for page_id in raw.get(split) or []:
            mapping[int(page_id)] = split
    return mapping


def page_id_of(sentence_id: str) -> int | None:
    """Trích ``page_id`` từ ``sentence_id``.

    ``sentence_id`` có dạng ``s<page_id>_<para>_<sent>``.

    Args:
        sentence_id: ID câu.

    Returns:
        ``page_id`` hoặc ``None`` nếu không parse được.
    """
    parts = sentence_id.split("_")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0].lstrip("s"))
    except ValueError:
        return None


def load_qid_relations(
    pairs_path: str | Path,
    relation_map,
) -> dict[tuple[str, str], set[str]]:
    """Dựng map cặp QID → tập quan hệ đang được giữ.

    Đây là "sổ trắng" dùng để loại negative: nếu cặp QID có **bất kỳ**
    quan hệ nào trong Wikidata (theo 13 property lõi) thì cặp entity đó
    **không** được dùng làm negative.

    Args:
        pairs_path: Đường dẫn `wikidata_pairs.jsonl`.
        relation_map: Bảng mapping property → quan hệ.

    Returns:
        Map ``(subject_qid, object_qid)`` → tập quan hệ.
    """
    mapping: dict[tuple[str, str], set[str]] = defaultdict(set)
    for pair in iter_jsonl(pairs_path):
        prop = str(pair.get("property") or "")
        spec = relation_map.get(prop)
        if spec is None:
            continue
        subject = str(pair.get("subject_qid") or "")
        obj = str(pair.get("object_qid") or "")
        if not subject or not obj:
            continue
        if spec.direction == "inverse":
            subject, obj = obj, subject
        mapping[(subject, obj)].add(spec.relation)
    return dict(mapping)


def build_entity_qid_index(
    infobox_entities_path: str | Path,
    documents_path: str | Path,
) -> dict[str, set[str]]:
    """Dựng map ``entity_id`` → tập QID.

    Args:
        infobox_entities_path: Đường dẫn artifact Phase 3.
        documents_path: Đường dẫn artifact Phase 2.

    Returns:
        Map ``entity_id`` → tập QID.
    """
    from src.re.ground_triples import build_qid_to_entities

    qid_to_entities = build_qid_to_entities(
        infobox_entities_path, documents_path
    )
    index: dict[str, set[str]] = defaultdict(set)
    for qid, entities in qid_to_entities.items():
        for entity_id in entities:
            index[entity_id].add(qid)
    return dict(index)


def collect_negative_candidates(
    index: CorpusIndex,
    entity_qids: dict[str, set[str]],
    qid_relations: dict[tuple[str, str], set[str]],
) -> dict[str, list[tuple[str, str, str]]]:
    """Thu thập ứng viên negative an toàn theo từng quan hệ.

    Một cặp ``(a, b)`` là ứng viên cho quan hệ ``r`` khi:
    - cả ``a`` và ``b`` đều có QID;
    - không cặp QID nào của chúng mang quan hệ ``r`` trong Wikidata;
    - ``(a, r, b)`` không phải POSITIVE đã grounding.

    Với quan hệ đối xứng, cặp được coi là **đã có** quan hệ nếu ``r`` xuất
    hiện theo **chiều nào** — tránh sinh negative là đối xứng của một
    positive.

    Args:
        index: Chỉ mục corpus.
        entity_qids: Map ``entity_id`` → tập QID.
        qid_relations: Map cặp QID → tập quan hệ.

    Returns:
        Map ``relation → danh sách (sentence_id, subject, object)``.
    """
    positive_keys = _load_positive_keys()
    candidates: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    for sentence_id, mentions in index.sentence_mentions.items():
        entity_ids = sorted(mentions)
        if len(entity_ids) < 2:
            continue
        for i in range(len(entity_ids)):
            for j in range(i + 1, len(entity_ids)):
                subject = entity_ids[i]
                obj = entity_ids[j]
                qids_a = entity_qids.get(subject) or set()
                qids_b = entity_qids.get(obj) or set()
                if not qids_a or not qids_b:
                    # Không rõ QID → loại (không an toàn).
                    continue
                held: set[str] = set()
                for qa in qids_a:
                    for qb in qids_b:
                        held |= qid_relations.get((qa, qb), set())
                        held |= qid_relations.get((qb, qa), set())
                for relation in RELATION_TYPES:
                    if relation in held:
                        continue
                    if (sentence_id, subject, relation, obj) in positive_keys:
                        continue
                    if (sentence_id, obj, relation, subject) in positive_keys:
                        continue
                    candidates[relation].append((sentence_id, subject, obj))
    return candidates


_POSITIVE_KEYS: set[tuple[str, str, str, str]] = set()


def _load_positive_keys() -> set[tuple[str, str, str, str]]:
    """Nạp cache khoá POSITIVE (nạp một lần cho toàn module).

    Returns:
        Tập khoá ``(sentence_id, subject, relation, object)``.
    """
    return _POSITIVE_KEYS


def set_positive_keys(keys: set[tuple[str, str, str, str]]) -> None:
    """Đặt tập khoá POSITIVE cho module (dùng bởi `collect_negative_candidates`).

    Args:
        keys: Tập khoá POSITIVE.
    """
    global _POSITIVE_KEYS
    _POSITIVE_KEYS = keys


def sample_negatives(
    candidates: dict[str, list[tuple[str, str, str]]],
    positive_counts: dict[str, int],
    *,
    max_per_positive: int,
    seed: int,
) -> list[dict[str, Any]]:
    """Chọn negative theo tỉ lệ cân bằng giữa các quan hệ.

    Args:
        candidates: Map ``relation → danh sách ứng viên``.
        positive_counts: Map ``relation → số POSITIVE`` (để cân bằng).
        max_per_positive: Tối đa negative cho mỗi POSITIVE.
        seed: Seed random (42 theo nguyên tắc tái lập).

    Returns:
        Danh sách negative đã chọn.
    """
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    used: set[tuple[str, str, str]] = set()

    for relation in sorted(candidates):
        pool = candidates[relation]
        if not pool:
            continue
        positives = positive_counts.get(relation, 0)
        quota = positives * max_per_positive
        if quota <= 0:
            # Quan hệ không có POSITIVE nào → không sinh negative để tránh
            # dạy mô hình "không quan hệ nào" cho quan hệ không tồn tại.
            continue
        # Lấy mẫu ngẫu nhiên nhưng giữ thứ tự ổn định theo seed.
        indices = list(range(len(pool)))
        rng.shuffle(indices)
        taken = 0
        for idx in indices:
            sentence_id, subject, obj = pool[idx]
            key = (sentence_id, subject, obj)
            if key in used:
                continue
            used.add(key)
            selected.append(
                {
                    "sentence_id": sentence_id,
                    "subject": subject,
                    "relation": relation,
                    "object": obj,
                    "label": NEGATIVE_LABEL,
                }
            )
            taken += 1
            if taken >= quota:
                break
    return selected


def _mention_at(
    index: CorpusIndex,
    sentence_id: str,
    entity_id: str,
    start: int | None,
    end: int | None,
) -> str:
    """Trích dạng bề mặt của entity tại span đã biết.

    Args:
        index: Chỉ mục corpus.
        sentence_id: ID câu.
        entity_id: ID thực thể.
        start: Offset đầu span.
        end: Offset cuối (exclusive) span.

    Returns:
        Chuỗi con của câu tương ứng span; rỗng nếu không có span.
    """
    if start is None or end is None:
        return ""
    text = index.sentence_text.get(sentence_id, "")
    if start < 0 or end > len(text) or end <= start:
        return ""
    return text[start:end]


def _span_for_entity(
    index: CorpusIndex,
    sentence_id: str,
    entity_id: str,
) -> tuple[int | None, int | None]:
    """Định vị span của entity trong câu (chỉ dùng mention resolve).

    Args:
        index: Chỉ mục corpus.
        sentence_id: ID câu.
        entity_id: ID thực thể.

    Returns:
        Tuple ``(start, end)``; ``(None, None)`` nếu không có span.
    """
    spans = index.spans_of(sentence_id, entity_id)
    if not spans:
        return None, None
    start, end, _text = min(spans)
    return start, end


def _pair_entry(
    *,
    subject: str,
    subject_mention: str,
    subject_name: str,
    subject_start: int | None,
    subject_end: int | None,
    relation: str,
    obj: str,
    obj_mention: str,
    obj_name: str,
    obj_start: int | None,
    obj_end: int | None,
    label: str,
    source: str,
    prop: str,
) -> dict[str, Any]:
    """Dựng một phần tử của mảng ``pairs``.

    ``mention`` là **dạng bề mặt trong câu** — phải thỏa
    ``text[start:end] == mention`` (xem `.cursor/rules/data-contracts.mdc`
    §Offset). ``name`` là tên chuẩn của entity trong KG.

    Offset là **chỉ số ký tự Python** trong ``text`` của câu; trường offset
    bị **bỏ qua** khi không định vị được span (ví dụ cặp negative sinh từ
    hai entity không có mention trong câu).

    Args:
        subject: `entity_id` chủ thể.
        subject_mention: Dạng bề mặt của chủ thể trong câu.
        subject_name: Tên chuẩn của chủ thể.
        subject_start: Offset đầu span chủ thể.
        subject_end: Offset cuối (exclusive) span chủ thể.
        relation: Tên quan hệ.
        obj: `entity_id` đối tượng.
        obj_mention: Dạng bề mặt của đối tượng trong câu.
        obj_name: Tên chuẩn của đối tượng.
        obj_start: Offset đầu span đối tượng.
        obj_end: Offset cuối (exclusive) span đối tượng.
        label: ``"POSITIVE"`` hoặc ``"NEGATIVE"``.
        source: Nguồn nhãn.
        prop: Property Wikidata (rỗng nếu không có).

    Returns:
        Dict phần tử của ``pairs``.
    """
    entry: dict[str, Any] = {
        "subject": {
            "mention": subject_mention,
            "entity_id": subject,
            "name": subject_name,
        },
        "object": {
            "mention": obj_mention,
            "entity_id": obj,
            "name": obj_name,
        },
        "relation": relation,
        "label": label,
        "source": source,
    }
    if subject_start is not None and subject_end is not None:
        entry["subject"]["start"] = subject_start
        entry["subject"]["end"] = subject_end
    if obj_start is not None and obj_end is not None:
        entry["object"]["start"] = obj_start
        entry["object"]["end"] = obj_end
    if prop:
        entry["property"] = prop
    return entry


def build_dataset(
    positives: list[dict[str, Any]],
    splits: dict[int, str],
    index: CorpusIndex,
    *,
    max_per_positive: int,
    seed: int,
    entity_qids: dict[str, set[str]],
    qid_relations: dict[tuple[str, str], set[str]],
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Ghép POSITIVE + NEGATIVE thành tập huấn luyện.

    Trả về **record theo câu**: mỗi câu có một mảng ``pairs`` chứa các cặp
    dương và âm nằm trong câu đó (contract `docs/09` §Phase 7).

    Args:
        positives: Danh sách mẫu POSITIVE đã grounding.
        splits: Map ``page_id`` → split.
        index: Chỉ mục corpus.
        max_per_positive: Tối đa negative cho mỗi POSITIVE.
        seed: Seed random.
        entity_qids: Map ``entity_id`` → tập QID.
        qid_relations: Map cặp QID → tập quan hệ.
        run_id: Mã lần chạy (mặc định sinh theo thời điểm hiện tại).

    Returns:
        Danh sách record theo contract Phase 7.
    """
    run_id = run_id or make_run_id()
    positive_counts: dict[str, int] = defaultdict(int)
    positive_keys: set[tuple[str, str, str, str]] = set()
    # pairs theo câu: sentence_id → danh sách phần tử `pairs`
    pairs_by_sentence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sentence_meta: dict[str, dict[str, Any]] = {}

    for sample in positives:
        sentence_id = sample["sentence_id"]
        page_id = page_id_of(sentence_id)
        if page_id is None:
            continue
        split = splits.get(page_id)
        if split is None:
            continue
        relation = sample["relation"]
        if relation not in RELATION_TYPES:
            logger.warning("Bỏ qua quan hệ ngoài danh mục: %s", relation)
            continue
        key = (sentence_id, sample["subject"], relation, sample["object"])
        positive_keys.add(key)
        positive_counts[relation] += 1
        if sentence_id not in sentence_meta:
            sentence_meta[sentence_id] = {
                "page_id": page_id,
                "split": split,
                "text": index.sentence_text.get(sentence_id, ""),
            }
        pairs_by_sentence[sentence_id].append(
            _pair_entry(
                subject=sample["subject"],
                subject_mention=sample.get("subject_mention", ""),
                subject_name=sample.get("subject_name", ""),
                subject_start=sample.get("subject_start"),
                subject_end=sample.get("subject_end"),
                relation=relation,
                obj=sample["object"],
                obj_mention=sample.get("object_mention", ""),
                obj_name=sample.get("object_name", ""),
                obj_start=sample.get("object_start"),
                obj_end=sample.get("object_end"),
                label=POSITIVE_LABEL,
                source=sample.get("source", ""),
                prop=sample.get("property", ""),
            )
        )

    set_positive_keys(positive_keys)
    candidates = collect_negative_candidates(index, entity_qids, qid_relations)
    logger.info(
        "Ứng viên negative an toàn: %d (theo %d quan hệ)",
        sum(len(v) for v in candidates.values()),
        len(candidates),
    )

    negatives = sample_negatives(
        candidates,
        positive_counts,
        max_per_positive=max_per_positive,
        seed=seed,
    )

    for sample in negatives:
        sentence_id = sample["sentence_id"]
        page_id = page_id_of(sentence_id)
        if page_id is None:
            continue
        split = splits.get(page_id)
        if split is None:
            continue
        if sentence_id not in sentence_meta:
            sentence_meta[sentence_id] = {
                "page_id": page_id,
                "split": split,
                "text": index.sentence_text.get(sentence_id, ""),
            }
        subject = sample["subject"]
        obj = sample["object"]
        sub_start, sub_end = _span_for_entity(index, sentence_id, subject)
        obj_start, obj_end = _span_for_entity(index, sentence_id, obj)
        pairs_by_sentence[sentence_id].append(
            _pair_entry(
                subject=subject,
                subject_mention=_mention_at(index, sentence_id, subject, sub_start, sub_end),
                subject_name="",
                subject_start=sub_start,
                subject_end=sub_end,
                relation=sample["relation"],
                obj=obj,
                obj_mention=_mention_at(index, sentence_id, obj, obj_start, obj_end),
                obj_name="",
                obj_start=obj_start,
                obj_end=obj_end,
                label=NEGATIVE_LABEL,
                source="distant_supervision",
                prop="",
            )
        )

    records: list[dict[str, Any]] = []
    for sentence_id in sorted(pairs_by_sentence):
        meta = sentence_meta[sentence_id]
        page_id = meta["page_id"]
        records.append(
            {
                "run_id": run_id,
                "sentence_id": sentence_id,
                "doc_id": f"doc_{page_id}",
                "page_id": page_id,
                "split": meta["split"],
                "text": meta["text"],
                "pairs": pairs_by_sentence[sentence_id],
            }
        )
    return records


def iter_records(path: str | Path) -> Iterator[dict[str, Any]]:
    """Đọc JSONL theo luồng.

    Args:
        path: Đường dẫn file.

    Yields:
        Từng record.
    """
    yield from iter_jsonl(path)


def main() -> None:
    """Điểm vào CLI."""
    parser = argparse.ArgumentParser(
        description="Sinh tập huấn luyện RE (Phase 7)."
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Mã lần chạy (mặc định sinh theo thời điểm hiện tại).",
    )
    args = parser.parse_args()

    config = load_default_config()
    re_cfg = config.get("re") or {}
    interim = resolve_path(config["paths"]["interim_dir"])

    out_path = Path(args.out) if args.out else resolve_path(
        re_cfg.get("train_path", "data/interim/re_train.jsonl")
    )

    from src.re.ground_triples import build_corpus_index

    index = build_corpus_index(resolve_path(re_cfg.get("coref_path")))
    splits = load_splits(resolve_path(re_cfg.get("splits_path")))
    positives = list(
        iter_jsonl(resolve_path(re_cfg.get("positive_path")))
    )
    logger.info("Nạp %d mẫu POSITIVE", len(positives))

    gates = load_gates(re_cfg.get("relations_config"))
    max_per_positive = int(
        re_cfg.get("max_negatives_per_positive", gates.get("max_negatives_per_positive", 1))
    )
    seed = int(config.get("seed", 42))

    records = build_dataset(
        positives,
        splits,
        index,
        max_per_positive=max_per_positive,
        seed=seed,
        entity_qids=build_entity_qid_index(
            resolve_path(re_cfg.get("infobox_entities_path")),
            interim / "documents.jsonl",
        ),
        qid_relations=load_qid_relations(
            resolve_path(re_cfg.get("pairs_path")), load_relation_map()
        ),
        run_id=args.run_id,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    positive_count = sum(
        1 for r in records for p in r["pairs"] if p["label"] == POSITIVE_LABEL
    )
    negative_count = sum(
        1 for r in records for p in r["pairs"] if p["label"] == NEGATIVE_LABEL
    )
    logger.info(
        "Ghi %d câu (%d cặp) → %s (POS %d / NEG %d, tỉ lệ %.3f)",
        len(records),
        positive_count + negative_count,
        out_path,
        positive_count,
        negative_count,
        negative_count / positive_count if positive_count else 0.0,
    )


if __name__ == "__main__":
    main()

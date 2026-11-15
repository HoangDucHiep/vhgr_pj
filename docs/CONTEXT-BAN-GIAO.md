# CONTEXT BÀN GIAO — Dự án Knowledge Graph lịch sử Việt Nam

> Copy nguyên khối dưới đây sang chat mới. Không cần đọc lại transcript cũ.

---

## 1. Dự án là gì

Xây **Knowledge Graph lịch sử Việt Nam** từ Wikipedia tiếng Việt + hệ thống hỏi đáp Text-to-Cypher.

| Hạng mục | Giá trị |
|---|---|
| Backend | FastAPI (Python 3.12) + Neo4j 5 Community (Docker) |
| Frontend | React 18 + TypeScript + Vite + Cytoscape.js |
| Model | PhoBERT (NER/RE), BGE-M3 (entity linking) |
| LLM | Bulk: model mở lượng tử hóa trên Kaggle GPU · API: Gemini `gemini-3.5-flash-lite` + Groq `openai/gpt-oss-20b` |
| Dữ liệu | Wikipedia tiếng Việt dump `20261101` (CC BY-SA 4.0) + Wikidata (CC0) |
| Phạm vi | 9 triều đại: Ngô, Đinh, Tiền Lê, Lý, Trần, Hồ, Lê sơ, Tây Sơn, Nguyễn · 2.441 bài |
| Repo | `/media/hoanghiep/All/Codes/NPL/vhgr_pj` (git, working tree sạch) |
| Python | `source .venv/bin/activate` trước khi chạy lệnh |

---

## 2. TRẠNG THÁI HIỆN TẠI — Phase 0–4 ✅ XONG

| Phase | Tên | Trạng thái | Kết quả chính |
|---|---|---|---|
| 0 | Bootstrap repo, hạ tầng | ✅ 13/11 | Neo4j 5.26.32, READ_ACCESS chặn ghi, 56 test |
| 1 | Tải dump, lọc bài (A1) | ✅ 14/11 | **2.441 bài**, QID 97,3%, `person` 1.061 / `battle` 202 / `place` 150 / `dynasty` 16 |
| 2 | Làm sạch, tách câu, hyperlink (A2/A3/A5) | ✅ 14/11 | **101.628 đoạn · 186.960 câu** · 0 lỗi offset · 0 ký tự wiki sót · link giữ 99,8% |
| 3 | Parse infobox, chuẩn hóa ngày (A4) | ✅ 14/11 | **10.078 triple infobox** (conf ≥0,95) + **736 triple lead** (conf 0,85) + **1.764 entity** · parse rate person 100% · coverage ngày/gia đình 92,4% · **16/18 quan hệ**, 6/7 loại node · 0 trùng / 0 self-loop |
| 4 | Nhãn bạc NER từ hyperlink (B2.1) | ✅ 14/11 | **186.960 câu · 138.860 mention** · độ phủ câu có hyperlink **100%** · 6 lớp nhãn · `PERSON` phổ biến nhất · baseline gazetteer dev F1 **0,7990** |
| 5 | Huấn luyện + suy luận NER (B1/B2) | ⬜ **chưa bắt đầu** | — |
| 6–14 | Coreference → RE → linking → KG/Neo4j → Text-to-Cypher → UI → đánh giá | ⬜ | — |

**Test hiện tại:** `pytest -q tests/` → **306 passed** (26 test mới ở `tests/test_silver_labels.py`).

**Commit gần nhất (theo thứ tự):**
```
544afa2 feat(phase-4): sinh nhãn bạc NER từ hyperlink
3bf9402 fix(phase-3): audit đóng phase — khử trùng triple, loại self-loop, template mơ hồ
f0d7cd1 fix(phase-3): bu sung 2/11 thuoc tinh node + truy vet dump_version/model_name
51fea5c feat(phase-3): parse infobox + chuan hoa ngay, dat 5/5 Gate
add2bb7 feat(phase-2): sua 3 loi lon, dat 5/5 Gate lam sach + tach cau + trich hyperlink
```

---

## 3. Artifact đã có trên đĩa (đều gitignored)

| Đường dẫn | Nội dung |
|---|---|
| `data/interim/documents.jsonl` | 2.441 bài + `clean_text` + `sentences` + `links` (214 MB) |
| `data/interim/infobox_triples.jsonl` | 10.078 triple, `method="infobox"`, `confidence ≥ 0,95` |
| `data/interim/lead_triples.jsonl` | 736 triple, `method="rule"`, `confidence=0,85` |
| `data/interim/infobox_entities.jsonl` | 1.764 entity + 11 node props |
| `data/interim/ner_silver.jsonl` | 186.960 câu, 138.860 mention, scheme **BIO** (13 lớp) |
| `data/splits/splits.json` | train 1.952 / dev 244 / test 245, seed 42, trùng 0 |
| `data/interim/qid_types.json` | cache P31 (15.684 QID) + P279* |
| `data/interim/class_hierarchy.json` | 11.519 cạnh P279 / 6.579 lớp |
| `data/interim/class_labels.json` | 5.272 nhãn lớp |

---

## 4. Đọc gì trước khi làm (BẮT BUỘC theo `AGENTS.md` §2)

| Khi nào | Đọc file |
|---|---|
| Bắt đầu phiên | `docs/CONTEXT.md` (quyết định đã chốt, QID) + `docs/PROGRESS.md` (phase hiện tại) |
| Làm 1 phase | `docs/09-ke-hoach-thuc-thien.md` → phần phase tương ứng |
| Ghi chép sâu | `docs/10-nhat-ky/phase-XX.md` (mẫu 9 mục ở `docs/10-nhat-ky/README.md`) |
| Schema KG | `docs/04-schema-knowledge-graph.md` |
| Quy tắc code | `.cursor/rules/python-standards.mdc`, `.cursor/rules/data-contracts.mdc` |
| Prompt/API LLM | `.cursor/rules/llm-usage.mdc` |
| Cypher | `.cursor/rules/cypher-safety.mdc` |

**Quy tắc vàng:** số liệu, QID, tên quan hệ, ID format **đã chốt** nằm trong `docs/CONTEXT.md`. Không tự ý đổi. Muốn đổi → cập nhật `docs/CONTEXT.md` **và** file liên quan trong cùng một lần.

**Skills dự án (`.cursor/skills/`):** `run-phase` (đọc TRƯỚC khi code 1 phase) · `check-context` (hỏi nhanh schema/QID/trạng thái) · `validate-graph` (kiểm tra KG trong Neo4j).

---

## 5. Workflow bắt buộc (`.cursor/rules/workflow-phases.mdc`)

1. Đọc `AGENTS.md` → `docs/CONTEXT.md` → `docs/PROGRESS.md` → phần phase trong `docs/09-ke-hoach-thuc-thien.md` → (nếu có) `docs/10-nhat-ky/phase-<số trước>.md`.
2. **Chỉ làm 1 phase mỗi lần.** Không nhảy phase.
3. Tuân thủ Input/Output contract. Không đổi tên/trường bắt buộc.
4. **Chạy lệnh kiểm thử ghi trong phase** — không bỏ qua.
5. Đạt **Gate** (checklist của phase) mới chuyển phase sau.
6. Ghi `reports/phase_XX_report.md` ngay khi xong phase.
7. Ghi `docs/10-nhat-ky/phase-XX.md` ngay khi xong phase — **bắt buộc**, đủ 9 mục (bối cảnh · phương án · quyết định · thang số liệu so sánh · số liệu Gate · lỗi & bài học · bài học · ý tưởng slide · việc tiếp theo).
8. Cập nhật `docs/PROGRESS.md` (trạng thái, ngày, số liệu, việc tiếp theo).
9. Lệch kế hoạch → `reports/deviations.md` (đánh số D-0XX liên tiếp) **và** `docs/CONTEXT.md` nếu cần.

**Nếu không đạt Gate:** đọc mục "Lùi" của phase → thử tối đa 2 lần → vẫn không đạt thì ghi `reports/deviations.md`, **hạ tiêu chí có kiểm soát** (nêu số thực tế, **không** sửa số liệu để "cho xanh"), báo cáo minh bạch.

**Hỏi người dùng khi:** đổi schema KG · đổi phạm vi dữ liệu · đổi tập quan hệ · đổi ngưỡng chất lượng · chi phí LLM · xoá/thay artifact đã sinh.
**Không cần hỏi khi:** thêm test · sửa lỗi nội bộ · thêm log · refactor không đổi interface · viết tài liệu.

**Về subagent:** ưu tiên làm trực tiếp, tuần tự theo phase. **Không** tự khởi động subagent khi chưa được yêu cầu.

---

## 6. Nguyên tắc kỹ thuật không được vi phạm (`AGENTS.md` §5)

1. **Bằng chứng bắt buộc** — mọi triple/cạnh có `evidence_sentence` + `source_url` + `confidence` + `method`. Không bằng chứng → không có cạnh.
2. **Cypher chỉ đọc** — validator tĩnh chặn `CREATE/MERGE/DELETE/SET/REMOVE/DROP/CALL`; session Neo4j `default_access_mode=READ_ACCESS`; luôn `LIMIT ≤ 100`; timeout 10s.
3. **Không bịa** — KG không có dữ liệu thì trả "Không có trong dữ liệu".
4. **Idempotent** — nạp KG bằng `MERGE` theo `entity_id`.
5. **Schema đóng** — 18 quan hệ cố định (`docs/04`); không sinh quan hệ ngoài danh sách.
6. **Tái lập** — seed `42`; chia tập theo bài; ghi `dump_version` + `model_name` vào mọi artifact.
7. **Tách offline/online** — việc nặng (fine-tune, LLM bulk, embedding) offline trên Kaggle, ghi artifact; tầng online chỉ đọc artifact + Neo4j + LLM API.
8. **Không commit secret** — key trong `.env` (gitignored), chỉ commit `.env.example`.
9. **Ngôn ngữ** — UI, prompt, tài liệu, comment: **tiếng Việt hoặc tiếng Anh**. **Tuyệt đối không dùng tiếng Trung.**
10. **Tiếng Việt có dấu** trong dữ liệu; chuẩn hóa bỏ dấu chỉ dùng cho *tra cứu* (`name_normalized`), không dùng làm tên hiển thị.

**ID format (bất biến):** `doc_<page_id>` · `s<page_id>_<para_idx>_<sent_idx>` · `m<sentence_id>_<idx>` · `ent_<slug>_<hash8>` · `year_<năm>` · `nil_<hash8>` — với `hash8 = sha1(f"{type}|{name_normalized}")[:8]`.

---

## 7. Bối cảnh kỹ thuật quan trọng đã chốt (đừng phát minh lại)

### 7.1. Wikidata `P31` không đủ cho corpus tiếng Việt
Đo thực tế ở Phase 4: **0 / 1.788** QID mới có `P31`; và khi `P31` là lớp generic ("human") thì **mọi** người thành `PERSON`, kể cả khi tên đích là quốc gia/địa danh.
→ Nguồn nhãn mạnh nhất là **Wikipedia category** (biên tập viên gắn tay), chiếm **50,2%** nguồn nhãn.

### 7.2. Chuỗi suy nhãn NER (Phase 4) — `src/ner/build_silver.py::SilverLabeller.resolve()`
```
category (0.97) → qid_direct (0.95) → qid_ancestor (0.88)
→ kg_type (0.92) → wikidata_signal (0.85) → pattern (0.78) → bỏ
```
`min_confidence = 0.78`.

### 7.3. Scheme nhãn NER = **BIO** (`B-`/`I-`/`O`) = **13 lớp**
`docs/09` §Phase 5 đã được sửa từ "BIOES" → **13 lớp**. Đừng dùng 25.

### 7.4. Nhãn TIME chỉ gán khi có **ngữ cảnh liền kề**
Mẫu có cờ `require_context`; `_has_time_context()` chỉ xét **2 token liền kề**. Xét cả câu → mọi số sau một chữ "năm" đều thành năm (sai ~4.500 số). Danh sách ngữ cảnh ở `configs/ner_silver_config.yaml` (`time_context_before` / `time_context_after`).

### 7.5. Mọi mẫu category Wikipedia phải có **ranh giới từ** (`\b`)
Không có → khớp tiền tố: "Nhà **ho**ạt động" → DYNASTY (sai), "Nhà **ngo**ại giao" → DYNASTY (sai).
Ngoài ra: "Quan lại nhà X" / "Hoàng đế" là **người** (PERSON), không phải TITLE; "Năm sinh không rõ" là **siêu dữ liệu**, không phải TIME.

### 7.6. Offset của link là **cấp bài** (so với `clean_text`), không phải cấp câu
Phải trừ `sentence["char_start"]` trước khi map sang token. Đã gây lỗi lệch ở 502 bài ở Phase 2.

### 7.7. QLever SPARQL bọc URI trong `<...>`
Phải `.strip().strip("<>").rsplit("/", 1)[-1]`. QLever hay trả HTTP 429 → có retry/backoff trong `src/preprocess/wikidata_query.py`.

### 7.8. Chốt 2 file triple (D-011)
- `infobox_triples.jsonl` — `method="infobox"`, `confidence ≥ 0,95` (giữ Gate "100% method=infobox" đúng nghĩa)
- `lead_triples.jsonl` — `method="rule"`, `confidence=0,85` (trích từ đoạn dẫn, **chỉ** khi infobox không có trường ngày)

### 7.9. `anh_em_cua` = 0 và `danh_bai` = 0 là **có chủ đích**
- `anh_em_cua` = 0 — **không bài nào** trong corpus có trường anh em/sibling (hạn chế dữ liệu, đã quét wikitext thô).
- `danh_bai` = 0 — D-028: trích từ infobox trận đánh vi phạm schema (4/4 cặp sai) → sinh ở Phase 8.

---

## 8. Sai lệch đã ghi (đọc `reports/deviations.md` D-001 → D-035)

| Mã | Nội dung |
|---|---|
| D-001→D-014 | Phase 0–1: hạ tầng, lọc corpus T0–T5, `wikitextparser` thay `mwparser`, QID đúng |
| D-015 | Mẫu số hyperlink Phase 2: đếm trên wikitext **đã gỡ markup** (99,89%), không phải wikitext gốc (80,66%) |
| D-016 | Cách đếm "câu" Phase 2: tách prose / list-item / heading; Gate tính trên prose |
| D-017 | `schemas.py` align `RELATION_SUBJECT_TYPES` theo `docs/04` (tập 18 quan hệ **không đổi**) |
| D-018 | Dùng cache `pysbd` (tách câu ~86 giây) |
| D-019→D-026 | Phase 3: template mơ hồ, loại chủ thể → `article`, bổ sung node props, `dump_version` + `model_name` |
| D-027 | Phase 3 audit: 347 triple trùng, 4 self-loop, 81 trùng lead ∩ infobox (artifact stale) |
| D-028 | Không trích `danh_bai` từ infobox trận đánh |
| D-029 | Gộp khoá tham số `_` ↔ khoảng trắng (`_collapse_key`) |
| D-030 | Template mơ hồ `infobox former country` → ưu tiên tín hiệu Wikidata |
| **D-031** | **Scheme BIO (13 lớp) thay vì BIOES (25)** — đặc tả mâu thuẫn, chọn theo `docs/CONTEXT.md` §2.4 |
| **D-032** | **Thêm nguồn nhãn `category` đứng đầu** — chiếm 50,2% nguồn nhãn |
| **D-033** | **TIME chỉ gán khi có ngữ cảnh** — loại 16.099 số đo lượng bị gán nhầm là năm |
| **D-034** | **Sửa ranh giới từ trong mẫu category** — 4 nhóm lỗi thật |
| **D-035** | **Bảng map lớp Wikidata sinh tự động** (`scripts/build_type_map.py`) |

---

## 9. Phase 5 — việc tiếp theo (đọc `docs/09` §Phase 5)

**Mục tiêu:** `models/ner/` đạt F1 ≥ 0,85; `data/interim/ner_predictions.jsonl` cho toàn corpus.

**Đã có sẵn đầu vào:** `data/interim/ner_silver.jsonl` (186.960 câu, BIO 13 lớp) + `data/splits/splits.json` (80/10/10 theo `page_id`, seed 42) + `src/evaluation/metrics.py::ner_f1` (entity-level span: micro / macro / per-label).

**Cần làm:**
1. `src/ner/data_convert.py` — word-level BIO → subword: `tokenizer(text, is_split_into_words=True, return_offsets_mapping=True)`; label cho subword đầu = label của word, còn lại `I-<type>` nếu word đó cũng mang label, `O` nếu không; ghi `word_id` để map ngược.
2. `src/ner/train_ner.py` — chạy được cả local CPU lẫn Kaggle GPU:
   - `AutoModelForTokenClassification` từ `vinai/phobert-base`, **`num_labels = 2*6 + 1 = 13`**
   - `TrainingArguments`: `seed=42`, `output_dir`, `save_total_limit=2`, `save_steps`, `eval_strategy="epoch"`, `metric_for_best_model="f1"`, `load_best_model_at_end=True`, `fp16` chỉ khi có CUDA, `report_to="none"`
   - `EarlyStoppingCallback(early_stopping_patience=2)`
   - Tính F1 bằng `src/evaluation/metrics.py` trên tập dev
3. Suy luận toàn corpus → `data/interim/ner_predictions.jsonl`: `{"sentence_id","doc_id","text","entities":[{"start","end","text","label","score"}]}` — offset theo **ký tự** trong `text`.

**Lưu ý:** `transformers` / `torch` / `datasets` có thể chưa cài trong `.venv`; theo nguyên tắc tách offline/online, huấn luyện nặng nên chạy trên Kaggle GPU và ghi artifact, tầng online chỉ đọc artifact.

---

## 10. Lệnh thường dùng

```bash
source .venv/bin/activate
pytest -q tests/                                     # 306 test
python -m src.preprocess.clean_text --config configs/default.yaml
python -m src.preprocess.split_sentences --config configs/default.yaml
python -m src.preprocess.parse_infobox --config configs/default.yaml
python -m src.ner.build_silver --out data/interim/ner_silver.jsonl
python -m src.ner.silver_quality --out reports/silver_quality.md
python scripts/stats_text.py
python scripts/stats_infobox.py
docker compose up -d neo4j                          # DB
python scripts/load_neo4j.py --batch 1000            # nạp KG (Phase 10)
python scripts/validate_graph.py                     # kiểm tra KG
```

**Ghi chú vận hành đã kiểm chứng (xem `docs/CONTEXT.md` §2.7):**
- Đọc dump bằng `lxml.etree.iterparse` (không dùng `mwparser` — PyPI chỉ có bản `0.1`).
- Tách câu bằng `pysbd` (`language="en"`; `Language.MULTI` không có trong 0.3.4).
- SPARQL: **không** dùng `P463`/`P361` (trả 0) — dùng `P31=Q5` + `P27=Q881` + `P569` + `P22`.
- Neo4j Community không có RBAC → bảo vệ bằng session `READ_ACCESS`.
- Parse infobox: `wikitextparser` (chính) + regex cân bằng ngoặc (dự phòng).
- Ngày: ISO-8601 `YYYY-MM-DD` với **năm 4 chữ số** (`0939-02-01`).

---

## 11. Tóm tắt "bài học" để không lặp lại lỗi

1. **Gate xanh ≠ dữ liệu đúng.** Cả Phase 3 và Phase 4 đều đạt Gate ngay từ bản đầu nhưng audit sau đó phát hiện lỗi thật. Luôn audit **nội dung** nhãn/triple, không chỉ đọc số liệu Gate.
2. **Regex theo từ khoá rất dễ khớp tiền tố.** Mọi nhánh thay thế phải có ranh giới từ; cụm dài thắng cụm ngắn; cụm gây nhập nhằng phải loại trừ tường minh.
3. **"Có ngữ cảnh" phải nghĩa là liền kề**, không phải "cùng tồn tại trong câu".
4. **Tài liệu mâu thuẫn nhau → chọn theo "số đã chốt"** (`docs/CONTEXT.md`) và **sửa** tài liệu còn lại.
5. **Log "0 kết quả" phải kiểm chứng lại** trước khi kết luận là bug (0/1.788 QID có `P31` hoá ra là đúng thực tế dữ liệu).
6. **Đo bằng ablation** (tắt từng fix riêng lẻ) thay vì so sánh tổng trước/sau — xem `docs/10-nhat-ky/so-lieu/phase-0*-*.json` § `thang_so_sanh_ablation`.
7. **Offset luôn phải khai báo rõ mức nào** (doc-level vs sentence-level).
8. **Chuẩn hóa ở tầng đầu vào**, không ở từng chỗ dùng.

---

## 12. Cấu trúc thư mục (rút gọn)

```
docs/         # 00–10: đặc tả, CONTEXT, PROGRESS, DECISIONS, GLOSSARY, 09=plan, 10=nhật ký
configs/      # *.yaml — nguồn sự thật cho cấu hình (default, name_exceptions, infobox_mapping, wikidata_type_map, ner_silver_config)
src/          # preprocess/ (clean_text, split_sentences, parse_infobox, extract_lead_dates, infobox_entity_types, wikidata_query)
              # ner/ (build_silver, category_types, qid_types, make_splits, silver_quality)
              # common/ (normalize, schemas, config, text_utils, logger) · evaluation/ (metrics)
backend/      # FastAPI (app/api, app/services, app/prompts)
frontend/     # React + Vite + TS
scripts/      # CLI: stats_text, stats_infobox, build_type_map, fetch_class_labels, load_neo4j, validate_graph, evaluate, export_graph
notebooks/    # Kaggle notebooks
tests/        # pytest (306 test) + fixtures/
data/         # raw/ interim/ processed/ knowledge_base/ — GITIGNORED
models/       # checkpoints — GITIGNORED
reports/      # phase_XX_report.md, deviations.md, silver_quality.md
```

---

## 13. Yêu cầu với agent mới

- **Trả lời bằng tiếng Việt hoặc tiếng Anh. Tuyệt đối không dùng tiếng Trung** (kể cả comment trong code và tài liệu).
- **Chỉ làm 1 phase mỗi lần** theo `docs/09-ke-hoach-thuc-thien.md`.
- **Không tự ý** tạo `src/`, `backend/`, `frontend/`, tải dữ liệu hay khởi động hạ tầng nếu chưa được yêu cầu.
- Mọi con số trong báo cáo phải **truy được về lệnh đã chạy**; ghi sai lệch vào `reports/deviations.md` với số D-0XX kế tiếp (kỳ hạn **D-036** trở đi).
- Không sửa số liệu để "cho xanh"; hạ tiêu chí có kiểm soát và công khai nếu không đạt Gate.

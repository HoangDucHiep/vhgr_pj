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
| Repo | `/media/hoanghiep/All2/Codes/NPL/vhgr_pj` (git) — ⚠️ **đường dẫn đã đổi**, xem §14 |
| Python | `source .venv/bin/activate` trước khi chạy lệnh |

---

## 2. TRẠNG THÁI HIỆN TẠI — Phase 0–17 ✅ · Phase 18 🟡 (18/11/2026)

| Phase | Tên | Trạng thái | Kết quả chính |
|---|---|---|---|
| 0–4 | Bootstrap → lọc bài → làm sạch → infobox → NER bạc | ✅ 13–14/11 | 2.441 bài · 101.628 đoạn · 186.960 câu · 10.078 triple infobox · NER bạc 138.860 mention |
| 5–9 | NER (PhoBERT) → coref → RE (distant supervision) → entity linking | ✅ 15/11 | RE micro-F1 0,9375 (đo nghiêm 0,1569 — D-080) · coref G6 1,0000 · 15.931 entity / 50.820 alias |
| 10–12 | KG + Neo4j · Text-to-Cypher · giao diện web | ✅ 15–16/11 | KG **19.548 node / 13.379 edge** · validate 13/13 PASS · API end-to-end 2,5–8,0 s |
| 13 | Sửa chất lượng (linking · chiều đảo · lọc nhiễu KG) | ✅ 17/11 | 12/12 ca lỗi demo → 0 · 644 test pass |
| 14 | **Vanilla RAG** (nhánh A) | ✅ 17/11 | 65.608 chunk · BM25 + dense (MiniLM-L12) + RRF k=60 · `POST /api/ask/rag` · 700 test pass |
| 15 | **Hybrid GraphRAG** (nhánh B) | ✅ 17/11 | template Cypher tất định + mở rộng 1-hop · 6 ý định · fusion `text_first`/`kg_first` · hội thoại nhiều lượt · `POST /api/ask/hybrid` |
| 16 | **Đánh giá A vs B vs B− (LLM-judge)** | ✅ 17/11 | 247 câu / 5 dạng (60 narrative · 60 multi_turn · 58 relational · 40 multi_hop · 29 no_data) · **correctness** A 1,1619 · B **1,5506** · B− 1,1700 · citeP(B) 0,8275 · 0 arm bị judge bỏ sót |
| 17 | **Giao diện so sánh + đóng gói** | ✅ 17/11 | Toggle A/B/B− · `CitationPanel` click-to-source (phân biệt KG / Văn bản) · đồ thị 1-hop · 3 service healthy · 2 ảnh demo |
| 18 | **Sửa chất lượng Hybrid trên nhóm `narrative`** | ✅ 18/11 | D-123 (tách hop-1/hop-2, lọc nhiễu sinh tử, sửa tên node `Title`, prompt tự sự) · D-124 (scope hop-2 `n2 = e`, template `event_parties`, ưu tiên văn bản khi xung đột, lọc tên rác Wikipedia) · D-125 (harness quota) · **D-134** (nén context giữ phần KG) · **D-137..D-141** (harness: giữ khối đã trích dẫn, cạnh KG viết thành mệnh đề tự nhiên, rubric đối xứng, `scripts/rejudge_all.py`) → **eval 60/60 câu**: A **1,617** · B **1,783** · B− **1,650** ⇒ **B thắng A 6 câu / thua 0**, **B thắng B− 5 câu / thua 0** ⇒ **gate đạt** ✅ · 11 test `tests/test_phase18_d138_judge_harness.py` **11/11 pass** |

**Test hiện tại:** `pytest -q tests/` → **~731 passed** + 1 fail **có sẵn** (`test_phase16_eval.py::TestAggregateJudgeMissing::test_counts_missing`, xem `reports/deviations.md` D-129).

**Checkpoint eval hiện có (`data/eval/`):**

| File | Nội dung |
|---|---|
| `eval_d122_checkpoint.jsonl` | Baseline 60 câu narrative (trước D-123) |
| `eval_d123_checkpoint.jsonl` | 60/60 câu narrative sau D-123 |
| `eval_d124_checkpoint.jsonl` | **60/60** câu narrative — **kết quả cuối Phase 18** (đã chấm lại thống nhất theo D-141) |
| `eval_d124_narrative_{A,B,B-}.jsonl` | bản tách theo arm của D-124 (dùng để đối chiếu) |

**Commit gần nhất (theo thứ tự):**
```
9d1fcea fix(phase16): KG rỗng => văn bản dùng toàn bộ ngân sách (công bằng B− vs A)
28e3b30 fix(phase16): chuẩn hoá chiều quan hệ KG ở tầng đọc + sửa ngân sách context (D-118)
d568590 feat(phase16): template make_phase16_log.py tái lập được bảng theo dạng + deviation mới
9c2b37d docs(phase16): cập nhật PROGRESS + bảng lỗi trong phase-16.md với số liệu 247/247
28bda5b docs(phase16): chốt số liệu 247/247 + D-117 (arm A công bằng hội thoại)
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

## 8. Sai lệch đã ghi (đọc `reports/deviations.md` D-001 → D-129)

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

## 9. Phase 18 ✅ — KẾT QUẢ (đọc `docs/DECISIONS.md` D-123 → D-141)

**Mục tiêu:** trên nhóm câu hỏi `narrative` (60 câu), **Hybrid GraphRAG (B) phải
vượt Vanilla RAG (A)** — đây là nhóm duy nhất mà KG thể hiện được giá trị thật
(các bên liên quan: chỉ huy, quân tham chiến, địa điểm).

**Đã làm (D-123 → D-136) — xem `docs/DECISIONS.md`:**
- D-123: tách hop-1/hop-2 thành 2 truy vấn độc lập (hết cartesian product) ·
  sửa điều kiện chạy hop-2 · lọc nhiễu sinh tử (`CONTEXT_RELATIONS`) ·
  `_resolve_title_names` sửa tên node `Title` ("quận công") · prompt trả lời câu tự sự.
- D-124: scope hop-2 vào chính sự kiện (`n2 = e`, loại 71% nhiễu) · template
  `event_parties` (phủ 21/60 câu thiếu bên liên quan) · quy tắc ưu tiên **văn bản**
  khi xung đột với KG · lọc tên rác do liên kết Wikipedia ("Chuẩn đề đốc Page") ·
  biến thể tiền tố bằng chứng ("Chi Huy 1/2").
- D-125: harness không ghim cứng model đã hết quota + ngân sách context
  16.000 → 9.000 ký tự.
- D-126 → D-133: harness chịu rate-limit (ngân sách token cho model thinking ·
  cache không lưu phản hồi rỗng · phân biệt RPM/RPD · ngân sách context judge
  là tham số · driver lặp `scripts/run_narrative_eval_loop.sh`).
- **D-134**: `compact_context()` **phải giữ khối KG** (xem hồ sơ bên dưới).
- D-135: nhận diện **chính xác** RPM vs RPD của Gemini qua `quota_id` trong lỗi
  429 ⇒ RPD ⇒ cooldown dài ⇒ **không** probe lại model đã chết trong ngày.
- D-136: **không đổi model judge** giữa các lần chấm (giữ tính so sánh được).

### 9.1 Phát hiện quan trọng: kết luận D-123 là **artefact của harness**

`compact_context()` cũ cắt chuỗi context từ **đầu**. Context arm B có cấu
trúc `### VĂN BẢN TỪ WIKIPEDIA` … rồi `### DỮ LIỆU ĐỒ THỊ` (**cuối**) ⇒ khi
trần ngân sách nhỏ (Groq TPM 8.000 ⇒ ~2.200 ký tự/arm) ⇒ **toàn bộ phần KG bị
cắt mất** ⇒ judge **không nhìn thấy** KG ở arm B ⇒ **lệch có lợi cho arm A**.

- Đo được (`scripts/probe_kg_context.py`): **35/37** câu có KG bị mất KG.
- Sau D-134: **37/37** câu giữ KG ⇒ chạy lại eval (D-124 lần 2) để đo lại.

⇒ **Bài học chung:** khi một kết luận nghiên cứu đi ngược lại kiến trúc,
phải kiểm tra đó có phải **artefact của harness** không.

### 9.2 Kết quả cuối Phase 18 ✅ — **B đã vượt A**

**Đã xong (18/11/2026).** Toàn bộ 60 câu narrative đã chạy và **chấm lại thống
nhất** theo D-141 (cùng judge pool, cùng ngân sách context 9.000 ký tự):

| Arm | correctness | faithfulness | citation_precision | "không có dữ liệu" |
|---|---|---|---|---|
| A (Vanilla RAG) | 1,617 | 1,800 | 0,833 | 16/60 |
| **B (Hybrid GraphRAG)** | **1,783** | **1,817** | **0,883** | **7/60** |
| B− (Hybrid không KG) | 1,650 | 1,767 | 0,817 | 14/60 |

- **B thắng A: 6 câu · B thua A: 0 câu · hòa 54** ⇒ Δ(B−A) = **+0,166**.
- **B thắng B−: 5 câu · B thua B−: 0 câu · hòa 55** ⇒ Δ(B−B−) = **+0,133**.
- B bổ sung tên **"bên liên quan"** mà A không có ở **43/60** câu.
- A trả "không có dữ liệu" còn B trả đủ ở **10/60** câu.
- **Đối chiếu chéo**: chấm lại checkpoint **D-123** bằng **cùng rubric mới**
  ⇒ A 1,733 · B 1,717 · B− 1,783 ⇒ **vẫn B ≤ A**. ⇒ phần lớn cải thiến của
  D-124 đến từ **cải thiến kiến trúc/context**, **không** phải từ nới rubric.
- ⚠️ `q0059` có **model sinh khác** giữa các arm (`gpt-oss-20b` vs `gpt-oss-120b`)
  ⇒ đã đánh dấu `model_mismatch_qids` và tách riêng khi phân tích.

**Bốn artefact của harness đã tìm ra & sửa (đều ở tầng đánh giá, không phải
kiến trúc):**

| # | Artefact | Quyết định |
|---|---|---|
| 1 | `compact_context()` cắt từ **đầu** ⇒ mất hết phần KG ở cuối | **D-134** |
| 2 | Ngân sách context judge **khác nhau** giữa các lần chấm (9.000 vs 2.200) | **D-141** (`scripts/rejudge_all.py`) |
| 3 | Cạnh KG dạng mũi tên ⇒ bị đọc **ngược** chiều | **D-139** (mệnh đề tự nhiên theo nhãn node thật) |
| 4 | `compact_context()` cắt mất khối `[n]` **đã được trích dẫn** ⇒ `citation_precision = 0` | **D-138** (`keep_indices`) |
| 5 | Judge trừ điểm cho thông tin **bổ sung** của B; và cho 2 điểm oan cho "không có dữ liệu" | **D-140** |

**Việc còn lại (Phase 19 — đề xuất):**
1. **Chạy lại trên nhóm khác** (multi_turn / relational / multi_hop) với harness
   đã sửa ⇒ xem KG có giúp ở nhóm nào nữa (KG hữu ích nhất ở **narrative**).
2. **Chi phí độ trễ**: đo latency A vs B vs B− (KG lookup có làm chậm không).
3. **Kiểm tra lại `q0059`** với model sinh thống nhất để loại artefact model.
4. **Thống nhất `scripts/summarize_narrative_eval.py`** để xuất đủ bộ chỉ số
   (bổ sung tên "bên liên quan" + so khớp A "không có dữ liệu").
5. Đóng gói lại bản demo cho đồng chủ nhiệm.

---

## 9b. Vận hành: ổ cứng ngoài & đường dẫn mount (quan trọng — 18/11/2026)

Ổ cứng ngoài `/dev/sda1` (label "All") bị **unmount khỏi hệ thống** **hai lần**
⇒ thư mục cũ chỉ còn rỗng ⇒ **mất workspace ~8 giờ** (xem `reports/deviations.md` D-126).

- Đường dẫn repo **hiện tại**: `/media/hoanghiep/All3/Codes/NPL/vhgr_pj`
  (đường dẫn cũ `/media/hoanghiep/All/...`, `/All1/...`, `/All2/...` **đã chết** —
  `/All2` hiện chỉ chứa thư mục rỗng do mount đổi tên).
- **Kiểm tra trước khi chạy lệnh quan trọng:**
  ```bash
  mountpoint -q /media/hoanghiep/All3 || echo "!! Ổ CHƯA MOUNT"
  ```
- **Khôi phục khi mất mount:**
  ```bash
  udisksctl mount -b /dev/sda1
  ls /media/hoanghiep/          # xác định tên mount thực tế (All/All1/All2/All3)
  cd /media/hoanghiep/All3/Codes/NPL/vhgr_pj
  docker compose up -d --force-recreate backend
  ```
- `docker-compose.yml` mount bằng đường dẫn **tương đối** (`./data`, `./configs`)
  ⇒ **không** cần sửa compose khi đường dẫn mount đổi.
- ⚠️ **Sau khi đổi đường dẫn mount phải `docker compose build backend`** — image
  copy code (`COPY src/`) ⇒ image cũ vẫn chạy code cũ (đo được 18/11: image cũ
  ⇒ `D-135` **không** có trong container ⇒ `--force-recreate` không đủ).
- ⚠️ **Workspace root của trình soạn thảo** trỏ `/media/hoanghiep/All/Codes/NPL/vhgr_pj`
  (nay rỗng) ⇒ cần đổi sang `/media/hoanghiep/All3/Codes/NPL/vhgr_pj`.

---


## 10. Lệnh thường dùng

```bash
source .venv/bin/activate
pytest -q tests/                                     # ~720 test (1 fail có sẵn — D-129)
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
9. **Tách truy vấn nhiều hop thành nhiều Cypher riêng**, đừng gộp hop-1 và hop-2 vào một truy vấn ⇒ sinh **tích bắc cầu** (`r1 × r2`) ⇒ `LIMIT` cắt cụt cạnh quan trọng (D-123).
10. **Điều kiện rẽ nhánh phải khớp với tham số thực truyền vào** — `fetch()` nhận **tên template** chứ không phải **tên ý định** ⇒ nhánh hop-2 không bao giờ chạy (D-123).
11. **Node trong KG có thể mang *danh xưng* thay vì tên riêng** (`Title` → "quận công") ⇒ dùng tên trong **bằng chứng** để hiển thị (D-123).
12. **Kiểm tra sức khoẻ model trước khi ghim cứng** — quota free tier hữu hạn theo ngày, ghim model chết ⇒ vòng lặp retry vô hạn (D-125).
13. **Kiểm tra `mountpoint -q` trước mỗi lần chạy lệnh quan trọng** — ổ ngoài có thể bị unmount khỏi hệ thống (D-126).

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
tests/        # pytest (~720 test) + fixtures/
data/         # raw/ interim/ processed/ knowledge_base/ — GITIGNORED
models/       # checkpoints — GITIGNORED
reports/      # phase_XX_report.md, deviations.md, silver_quality.md
```

---

## 13. Yêu cầu với agent mới

- **Trả lời bằng tiếng Việt hoặc tiếng Anh. Tuyệt đối không dùng tiếng Trung** (kể cả comment trong code và tài liệu).
- **Chỉ làm 1 phase mỗi lần** theo `docs/09-ke-hoach-thuc-thien.md`.
- **Không tự ý** tạo `src/`, `backend/`, `frontend/`, tải dữ liệu hay khởi động hạ tầng nếu chưa được yêu cầu.
- Mọi con số trong báo cáo phải **truy được về lệnh đã chạy**; ghi sai lệch vào `reports/deviations.md` với số D-0XX kế tiếp (kỳ hạn **D-130** trở đi — `reports/deviations.md` đã dùng tới **D-129**).
- Không sửa số liệu để "cho xanh"; hạ tiêu chí có kiểm soát và công khai nếu không đạt Gate.
- ⚠️ **Đường dẫn repo đã đổi** → `/media/hoanghiep/All2/Codes/NPL/vhgr_pj` (xem §9b).

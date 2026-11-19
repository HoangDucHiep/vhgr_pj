# PROGRESS.md — Trạng thái triển khai

> Agent cập nhật file này **sau mỗi phase**. Đây là nơi agent mới biết "đang ở đâu".
> Cập nhật: cột "Ngày" = ngày hoàn thành, "Kết quả" = số liệu thực tế đo được.

## Tổng quan

| Phase | Tên | Trạng thái | Ngày | Kết quả chính |
|---|---|---|---|---|
| 0 | Bootstrap repo, cấu hình, hạ tầng | ✅ Xong | 13/11/2026 | 56 test pass · `/api/health` ok · Neo4j 5.26.32 · READ_ACCESS chặn ghi ✅ · build TS 0 lỗi |
| 1 | Tải dump, lọc bài (A1) | ✅ Xong | 14/11/2026 | **2.441 bài** trong `documents.jsonl` · QID 97,3% · `person` 1.061/`battle` 202/`place` 150/`dynasty` 16 · RAM peak 1,16 GB |
| 2 | Làm sạch, tách câu, hyperlink (A2/A3/A5) | ✅ Xong | 14/11/2026 | **2.441 bài · 101.628 đoạn · 186.960 câu** (143.100 văn xuôi + 43.860 mục danh sách) · **0 lỗi offset** · **0 ký tự wiki còn sót** · link giữ 99,8% · câu văn xuôi kết thúc dấu câu 95,3% · 185 test pass |
| 3 | Parse infobox, chuẩn hóa ngày (A4) | ✅ Xong | 14/11/2026 | **10.078 triple infobox** (conf ≥0,95) + **736 triple đoạn dẫn** (conf 0,85) + **1.764 entity** · parse rate person **100%** · coverage ngày/gia đình **92,4%** · chuẩn hóa ngày **100%** (30/30) · **16/18 quan hệ**, 6/7 loại node · **0 trùng / 0 self-loop** (audit) · **280 test pass** |
| 4 | Nhãn bạc NER từ hyperlink (B2.1) | ✅ Xong | 14/11/2026 | **186.960 câu · 138.860 mention** · độ phủ câu có hyperlink **100%** · **6** lớp nhãn · `PERSON` phổ biến nhất · baseline gazetteer dev F1 **0,7990** · **306 test pass** |
| 5 | Huấn luyện + suy luận NER (B1/B2) | ⚠️ Xong (lệch F1) | 15/11/2026 | **micro F1 0,6832** (macro 0,5589) trên dev 19.049 câu · **0** span sai offset / **143.108** entity · phủ **100%** (186.960 câu) · F1 bộ gold tay **0,6329** · 2 arm trên 2 tài khoản Kaggle (base 0,6832 vs large 0,6391) · **337 test pass** |
| 6 | Coreference (C1/C2) | ✅ Xong | 15/11/2026 | **197.610 mention · resolve 69,62%** (96,35% không tính TIME · **90,46%** riêng danh xưng/đại từ) · G5 **0,8729** (Gate ≥0,80) · G4 **0** lỗi giới tính · G6 **100,00%** · **0** vi phạm contract · **439 test pass** · Gate tự động **8/8** |
| 7 | Wikidata DS + tập train RE (D1.1) | ✅ Xong | 15/11/2026 | **15.580 POSITIVE / 17 quan hệ** (G1 ≥10.000 → **+55,8%**) · NEG/POS **0,9228** (G2 ≤1,0) · **0** quan hệ ngoài danh mục (G4) · **0 request** khi chạy lại SPARQL (G5) · `re_train.jsonl` **12.877 câu / 29.957 cặp** (contract 1 record/câu) · **480 test pass** |
| 8 | Mô hình RE, LLM bulk, hợp nhất triple (D1/D2/D3) | ✅ Xong | 16/11/2026 | **25.947** ví dụ RE đa nhãn (19 đầu, 88,7% slot mask) · **113.917** cặp ứng viên (khớp kế hoạch) · model GPU micro-F1 **0,9375** (macro 0,9190, NA-F1 0,9145, ngưỡng 0,55) — **đo lại nghiêm: P 0,0854 · R 0,9652 · F1 0,1569** (99,4% FP rơi vào slot mask, D-080) · suy luận **99.348** cặp → **17.358 câu / 511.567 quan hệ** (CPU 4 shard 3,66 giờ **và** Kaggle GPU khớp **454.767/454.767** cặp) · LLM API baseline 1.500 câu: evidence substring **97,51%**, giữ **97,51%** · bộ lọc 4 lớp (D-080→D-086): `phobert_re` 511.567 → **4.985**, `llm` 349 → **148** · **538.227** → **13.379** triple cuối (0 trùng / 0 ngoài danh mục / 0 self-loop) · khôi phục entity **2.826/2.871 (98,5%)** (D-085) · KG **19.548 node / 13.379 edge**, validate **13/13 PASS** · **83 test mới** (616 tổng) |
| 9 | Entity linking (E1–E4) | ✅ Xong | 15/11/2026 | **15.931 entity / 50.820 alias** · alias hit **72,82%** · link **72,86%** · recall@20 **1,000** · accuracy **0,8049** (chưa đạt 0,85) · **1,50 ms/mention** |
| 10 | Đồ thị + Neo4j (F1–F4) | ✅ Xong (nạp lại 16/11) | 16/11/2026 | **19.548 node / 13.379 edge** · validate **13/13 PASS** · idempotent **+0/+0** · 0 orphan · 0 node thiếu `wiki_url` |
| 11 | Text-to-Cypher backend (G1–G4/G6/G8) | ✅ Xong | 15/11/2026 | `POST /api/ask` đúng contract · **49/49** test validator · 4/4 câu mẫu đúng · 100% Cypher có `LIMIT ≤ 100` · end-to-end **2,5–8,0 s** · `/api/search` `/api/graph/{id}` `/api/entity/{id}` |
| 12 | Giao diện web (H1–H4) | ✅ Xong | 15/11/2026 | **7 component + 2 page** · `tsc --noEmit` **0 lỗi** · `npm run build` ✓ · 4/4 hành vi H1–H4 hoạt động · Cytoscape render node theo label |
| 13 | **Sửa chất lượng** (entity linking · chiều đảo · lọc nhiễu KG) | ✅ Xong | 17/11/2026 | **12/12** ca lỗi demo → 0 · alias 13.760 → **13.582** (−178) · exact-case + 176 alias thường + 42 đại từ · chiều đảo: **5/5** con Trần Nhân Tông · lọc **23** cạnh nhiễu (0 tổn thương đúng) · guard chống trả N người ngẫu nhiên · **644 test pass** |
| 14 | **Vanilla RAG (nhánh A)** | ✅ Xong | 17/11/2026 | **65.608 chunk** (1 đoạn = 1 chunk, giữ ranh giới `section`; kế hoạch ghi 101.628 — xem deviations D-105) · MiniLM-L12 **384-dim** float16 · BM25 (title×3 + section×2 + body×1) + dense + **RRF k=60** · `POST /api/ask/rag` ✓ · top-1 đúng bài 6/6 câu thật · **700 test pass** · D-099, D-100 |
| 15 | **Hybrid GraphRAG (nhánh B)** | ✅ Xong | 17/11/2026 | Kênh KG = **template Cypher tất định** + mở rộng 1-hop (bài Bạch Đằng: **30 entity → 60 cạnh / 0,11 s**) · 6 ý định · fusion `text_first`/`kg_first` với **không gian `[n]` liên tục** · hội thoại nhiều lượt (`SessionStore` + query rewriting) · `POST /api/ask/hybrid` + `GET /api/session/{id}` ✓ · D-101, D-102 |
| 16 | **Đánh giá A vs B vs B− (LLM-judge)** | ✅ Xong | 17/11/2026 | Bộ câu hỏi **247 câu / 5 dạng** (60 narrative · 60 multi_turn · 58 relational · 40 multi_hop · 29 no_data) từ Wikidata (độc lập KG) · judge **gộp 3 arm/câu** + hoán vị thứ tự theo `qid` (seed 42) · pool LLM **đa provider** (Gemini + Groq) + **ghim model theo câu** + **tách session theo arm** + **loại lỗi hạ tầng khỏi mẫu số** · **retry judge khi thiếu arm** (`n_judge_missing`) + `scripts/rejudge_missing.py` · **loại câu có confound model** (`n_model_mismatch`) · **sửa chiều quan hệ KG ở tầng đọc** (D-118) ⇒ `faithfulness_rate(B)` 0,8381 → **0,9150** ✅ · **tái dùng arm không đổi** (D-119) ⇒ chỉ sinh 247 lời gọi thay vì 741 · **Kết quả**: `correctness` A **1,1619** · B **1,5506** · B− **1,1700** (Δ B vs A = **+0,3887**) · `citation_precision(B)` **0,8275** · `no_data_accuracy` 0,9655 · 0 arm judge bỏ sót · 0 câu lệch model · D-103, D-104, D-106, D-108, D-109, D-111, D-118, D-119 |
| 17 | **Giao diện so sánh + đóng gói** | ✅ Xong | 17/11/2026 | Toggle **A / B / B−** · `CitationPanel` click-to-source (phân biệt `KG` / `Văn bản`) · đồ thị 1-hop từ `KgGraph` · `npm run typecheck` **0 lỗi** · `npm run build` ✓ · `docker compose up` 3 service healthy (`/api/health` → `neo4j: up`, frontend HTTP 200) · 2 ảnh demo trong `reports/screenshots/` · D-099..D-103 |
| 18 | **Sửa chất lượng Hybrid trên nhóm `narrative`** | 🟡 Đang làm | 18/11/2026 | **D-123** (tách hop-1/hop-2 thành 2 truy vấn độc lập — hết cartesian product; sửa điều kiện chạy hop-2; lọc nhiễu sinh tử bằng `CONTEXT_RELATIONS`; `_resolve_title_names` sửa tên node `Title` "quận công"; prompt trả lời câu tự sự) → eval 60 câu: A **1,84** · B **1,79** · B− **1,85** (D-122: A 1,91 · B 1,78 · B− 1,85) · B bổ sung thông tin bên liên quan **33 → 38/60** câu · **D-124** (scope hop-2 `n2 = e` — loại 71% nhiễu; template `event_parties` — phủ 21/60 câu thiếu bên liên quan; quy tắc ưu tiên văn bản khi xung đột; lọc tên rác liên kết Wikipedia "Chuẩn đề đốc Page"; biến thể tiền tố "Chi Huy 1/2") → eval 43/60 câu (hết quota): A **1,95** · B **1,79** · B− **1,92** · A "Không có trong dữ liệu" mà B có đủ **5/43** câu · **D-125** (harness: không ghim cứng model hết quota + ngân sách context 16.000 → 9.000 ký tự) · 20 test `tests/test_phase17_d123_d124.py` **20/20 pass** |
| 19 | **Trả lời đúng & có căn cứ, rồi đo lại A vs B vs B−** | 🟡 Đang làm | 19/11/2026 | **G19-2 đạt**: gold section trong top-8 (narrative) **46/60 → 55/60** nhờ `retrieval.diversity` (cap chunk/section=2 · cap chunk/doc=5 · `title_boost=1.0` · `section_boost=1.0` · `noise_penalty=0.5`) — đo offline bằng `scripts/measure_gold_hit_rate.py` (multi_hop 34/40 · relational 43/58 · multi_turn 24/58 · no_data 0/30) · **G19-7 đạt**: **0/118** câu hỏi không hợp lệ (kiểm chứng Wikipedia/Wikidata **live** bằng `scripts/verify_answers_online.py`) ⇒ **không** loại câu hỏi nào vì phạm vi (D-142) · **G19-6 (tạm) đạt**: **0** câu trả lời bịa số năm · **0** vi phạm `no_data` · tầng sinh: `no_data_retry` khi context có dữ liệu + metric `abstain_with_evidence` (D-144) · bộ câu hỏi v2 `qa_rag_250_v2.jsonl` (246 câu) — gom chunk theo `(doc_id, section_path)`, bỏ shuffle, `no_data` hậu-1945, sửa chuỗi "mẹ của mẹ", chỉ hỏi năm có trong corpus · **G19-1/3/4/5 chưa chốt** — eval 246 câu × 3 arm đang chạy nền (quota Gemini RPD 500/model/ngày) ⇒ **A vs B vs B− chưa kết luận được** (G19-5 trung thực) · test `tests/test_phase19_grounded.py` **26/26** + toàn bộ suite **100 % pass** |

Ký hiệu: ⬜ chưa · 🟡 đang làm · ✅ xong (đạt Gate) · ⚠️ xong nhưng lệch kế hoạch (xem `reports/deviations.md`)

## Việc tiếp theo

**Phase hiện tại: Phase 19 — Trả lời đúng & có căn cứ, rồi đo lại A vs B vs B−** 🟡 — 19/11/2026.
Phase 16 (đánh giá A vs B vs B−) ✅ + Phase 17 (giao diện + đóng gói) ✅ — 17/11/2026.
Phase 18 (sửa chất lượng Hybrid trên `narrative`) 🟡 — 18/11/2026 (số liệu D-123/D-124
bị nghi vấn là artefact của retrieval ⇒ Phase 19 đo lại từ đầu trên bộ câu hỏi v2).

> **Vấn đề đang xử lý (Phase 19):** số liệu A vs B **đảo chiều** giữa D-123 và D-124
> ⇒ phải tìm artefact trước khi kết luận về KG. Ba artefact đã xác định & sửa:
> (1) **retrieval** — BM25 `title` ×3 là doc-level ⇒ chunk "Di tích lịch sử" chiếm
> chỗ ⇒ thêm `retrieval.diversity` (cap chunk/section, boost tiêu đề/section, chống
> nhiễu) ⇒ gold section trong top-8 **46/60 → 55/60**; (2) **tầng sinh** — LLM trả
> "Không có trong dữ liệu" dù context có gold (7/16 câu của A) ⇒ thêm
> `no_data_retry` + metric `abstain_with_evidence`; (3) **bộ câu hỏi** — `qa_rag_250_v2`
> gom chunk theo `(doc_id, section_path)`, bỏ shuffle phá sort, `no_data` là sự kiện
> hậu-1945 có thật, sửa chuỗi "mẹ của mẹ", chỉ hỏi năm **có trong corpus**.
>
> **Kiểm chứng bằng nguồn ngoài live** (không tin LLM-judge): `scripts/verify_answers_online.py`
> ⇒ **0/118** câu hỏi không hợp lệ (**G19-7** ✅) · **0** câu trả lời có năm không có
> trong Wikipedia live (**G19-6** tạm đạt).
>
> **Kết luận A vs B vs B−: CHƯA kết luận được** — eval đầy đủ (246 câu × 3 arm) đang
> chạy nền theo quota Gemini (RPD 500/model/ngày) ⇒ driver
> `scripts/run_phase19_eval_loop.sh all 60` tự lặp + `--resume`.

> **Định hướng mới (chốt 16/11/2026):** so sánh **Vanilla RAG (A)** vs **Hybrid GraphRAG (B)** vs **Hybrid không KG (B−)**.
> Nhánh Text-to-Cypher không còn là arm so sánh.

> **Vấn đề đang xử lý (Phase 18):** ở nhóm câu hỏi `narrative` (60 câu — nhóm duy
> nhất KG phải thể hiện giá trị thật), Hybrid (B) **thua** Vanilla RAG (A).
> Ba vòng sửa đã làm: D-121 (truy vấn KG 2-hop) → D-122 (parent expansion ở
> tầng truy xuất) → **D-123/D-124** (tách hop-1/hop-2, lọc nhiễu, sửa tên node
> `Title`, scope hop-2 vào sự kiện, bổ sung "các bên liên quan", quy tắc ưu tiên
> văn bản khi xung đột). Số liệu hiện tại xem bảng dưới.

**Kết quả eval nhóm `narrative` (60 câu) — tiến trình:**

| Checkpoint | Ngày | A | B | B− | Ghi chú |
|---|---|---|---|---|---|
| `eval_d122_checkpoint.jsonl` | 17/11 | **1,91** | 1,78 | 1,85 | Baseline — B thua A |
| `eval_d123_checkpoint.jsonl` | 18/11 | 1,84 | **1,79** | 1,85 | Sau D-123 (60/60 câu) |
| `eval_d124_checkpoint.jsonl` | 18/11 | 1,95 | 1,79 | 1,92 | Sau D-124 — **43/60 câu** (hết quota free tier) |
| `eval_d124_checkpoint.jsonl` (lần 2) | 18/11 | *đang chạy* | *đang chạy* | *đang chạy* | Sau **D-134** (nén context **giữ phần KG**) — driver `scripts/run_narrative_eval_loop.sh` tự lặp `--resume` |

> ⚠️ Số liệu D-123 **đã nghi vấn là artefact của harness**: `compact_context()`
> cắt chuỗi context từ **đầu** ⇒ phần `### DỮ LIỆU ĐỒ THỊ` (KG) ở **cuối**
> bị cắt mất hoàn toàn ở trần ngân sách nhỏ ⇒ judge **không nhìn thấy** KG ở
> arm B ⇒ **lệch có lợi cho arm A**. Đo được: **35/37** câu có KG mất phần KG.
> ⇒ **D-134** sửa `compact_context()` (tách context tại marker KG, dành 45 %
> ngân sách cho KG) ⇒ **37/37** câu giữ KG ⇒ chạy lại eval (D-124 lần 2).

**Vì sao không đổi model judge giữa các lần chấm (D-136).** Pool của D-124
lần 2 **giống hệt** D-123 (đọc từ `logs/eval_d123_narrative.log`):
gen = `gemini-3.5-flash-lite` + `gemini-3.1-flash-lite` +
`gemini-3.1-flash-lite-preview`; judge = `gemini-3.1-flash-lite` +
`gemini-3.1-flash-lite-preview` + `gemini-3-flash-preview`. Groq là dự phòng.
Không dùng model khác hẳn (`gemma-4-31b-it` còn quota lúc 18/11 nhưng
**khác hệ** ⇒ số liệu **không so sánh được**).

**Harness chịu rate-limit (D-126 → D-136).** 9 quyết định liên tiếp:
ngân sách token cho model thinking (D-126) · cache không lưu phản hồi rỗng
(D-127) · phân biệt RPM/RPD (D-128) · ngân sách context judge là tham số
(D-129) · driver lặp (D-130) · nén context giữ KG (D-134) · nhận diện
chính xác RPM vs RPD qua `quota_id` (D-135) · không đổi model judge (D-136).

Chi tiết ở `docs/09-ke-hoach-thuc-thien.md` → mục "Phase 16" và "Phase 17".

Lệnh chạy đánh giá (Phase 16):
```bash
./.venv/bin/python -m src.evaluation.build_qa_set
./.venv/bin/python -u -m src.evaluation.evaluate_rag \
  --qa-set data/eval/qa_rag_250.jsonl --arms A,B,B- --reset-sessions \
  --gen-pool "gemini:gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b" \
  --judge-pool "gemini:gemini-3.1-flash-lite,gemini-3.1-flash-lite-preview,gemini-3.5-flash-lite;groq:openai/gpt-oss-120b,qwen/qwen3.8-27b" \
  --checkpoint data/eval/eval_rag_checkpoint.jsonl --resume \
  --reuse-arms-from data/eval/eval_rag_checkpoint_prev.jsonl \
  --infra-retries 3 --infra-retry-wait-s 45 --stamp phase16
```
> ⚠️ Quota free tier **không đủ** nếu dùng 1 provider: Gemini 500 RPD/**model**,
> Groq `gpt-oss-20b` 200K TPD ⇒ dùng pool **đa provider** — D-108.
>
> Chạy lại sau khi sửa **chỉ arm B** ⇒ dùng `--reuse-arms-from` để **tái dùng**
> arm A/B− (đã chứng minh tái lập được 100%) ⇒ chỉ sinh 247 lời gọi thay vì 741;
> điểm vẫn được judge hiện tại **chấm lại** ⇒ D-119.
>
> Sau khi run xong: `scripts/rejudge_missing.py` (chấm lại arm bị judge bỏ sót)
> → `scripts/rebuild_phase16_report.py` → `scripts/make_phase16_log.py`.

**Phase 8 (đã đóng Gate 11/11 — 16/11/2026)** — xem `docs/10-nhat-ky/phase-08.md`.

> Báo cáo: `reports/phase_08_report.md` · Nhật ký: `docs/10-nhat-ky/phase-08.md` ·
> Chấm Gate máy đọc được: `reports/phase_08_gate_check.json` ·
> Số liệu chưng cấp: `docs/10-nhat-ky/so-lieu/phase-08-distillation.json` ·
> Sai lệch: `reports/deviations.md` (D-061 → **D-087**).

Kết quả Phase 8 đã chốt (16/11/2026):
- **Đa nhãn sigmoid** (D-061): 19 đầu (18 quan hệ + `NA`), loss **masked BCE**,
  slot chưa biết = `-100.0` (**88,7%** slot). Marker **có vai trò** `SUBJ`/`OBJ`
  (D-062) — chặn **4,62%** cặp mơ hồ hướng.
- `data/interim/re_model_input.jsonl` — **25.947** ví dụ (train **20.382** /
  dev **2.987** / test **2.578**), mean **80,3** subword.
- **113.917** cặp ứng viên (≤ 60 token) — **khớp tuyệt đối** con số kế hoạch;
  dùng **99.348** cặp `canonical_id` khác nhau để suy luận.
- **Mô hình RE đã train xong trên Kaggle GPU** (D-077): micro-F1 **0,9375** ·
  macro-F1 0,9190 · NA-F1 0,9145 · ngưỡng **0,55** · eval_loss 0,1676 ·
  **16/18** quan hệ có F1 ≥ 0,70 → **vượt Gate G1 (≥0,70)**.
- ⚠️ **Đo lại nghiêm (D-080)**: `scripts/eval_re_strict.py` (slot mask tính là
  FP) cho **P 0,0854 · R 0,9652 · F1 0,1569** — **19.220/19.339 FP (99,4%)** rơi
  vào slot bị mask; 976/2.987 cặp fire **16** quan hệ. ⇒ Metric lỏng **không**
  dùng để kết luận chất lượng.
- **LLM API baseline**: 1.500 câu (split `test`) / **100** request / 386,7s →
  evidence substring **97,51%** (Gate ≥90%) · giữ lại **97,51%** (Gate ≥60%) ·
  **0** relation ngoài danh mục. Chạy lại = **0** API call (cache idempotent).
- ✅ **Suy luận RE toàn corpus** → `data/interim/re_phobert.jsonl`:
  **17.358 câu / 511.567 quan hệ**.
  - CPU local **4 shard × 2 thread** (8 core): 0,531 s/cặp/shard → **3,66 giờ**.
  - Kaggle GPU (tài khoản phụ, D-079): chạy **đúng** `src/re/infer_re.py`.
  - **Đối chiếu**: **454.767/454.767** cặp trùng tuyệt đối (0 chỉ-GPU, 0 chỉ-CPU) ·
    confidence giống tuyệt đối **95,47%** · mean |Δ| = **0,000714** ⇒ mã nguồn
    repo cho kết quả tương đương giữa 2 môi trường.
- ✅ **Bộ lọc chất lượng 4 lớp** (D-080 → D-084): Top-1/cặp + kiểu đích +
  kiểu chủ thể + grounding theo tên + từ kích hoạt.
  `phobert_re` **511.567 → 4.985 (0,97%)** · `llm` **349 → 148 (42,4%)**.
- ✅ **Hợp nhất 5 nguồn**: 538.227 input → lọc mô hình → 31.444 → dedupe →
  **15.825** → lọc tên chung → **13.379** triple cuối.
  Gate: **0** trùng · **0** ngoài danh mục · **0** self-loop · **0** evidence rỗng ·
  **100%** có 6 trường bắt buộc.
- ✅ **Khôi phục entity chỉ có trong triple** (D-085): đảo ngược hash
  `entity_id` trên **60.116** tên ứng viên ⇒ **2.826/2.871 (98,5%)** entity có
  tên có dấu + kiểu schema; node `Entity` **2.897 → 162**.
- ✅ **KG nạp lại Neo4j**: **19.548 node / 13.379 edge** · **0** orphan ·
  `validate_graph.py` **13/13 PASS** · nạp lại lần 2 → **+0/+0** (idempotent).
- ✅ **Sửa QA "bao nhiêu vua"** (D-087): "Nhà Trần có bao nhiêu vua?" → **19**
  (chỉ đếm node có `reign_start`), trước là **44**.
- ✅ **Rà soát kernel Kaggle (16/11)**: **0** kernel `RUNNING`/`QUEUED`; đã xoá
  3 kernel không cần; **giữ** `models/re/` từ GPU base (đã verify checksum).
- **83 test mới** (20 `test_llm_client` + 32 `test_re_model` + 24
  `test_merge_triples` + 7 `test_entity_linker`) → **625** test tổng, tất cả pass
  (thêm **8 test** `test_kaggle_llm_notebook` cho `normalize_payload` — D-091,
  và **1 test** regression `alt_evidence` ở mức ghi file — D-093).
- ✅ **Sửa mất dữ liệu `alt_evidence`** (D-093): `REQUIRED_FIELDS` thiếu
  `alt_evidence` ⇒ **13.294** câu bằng chứng thay thế bị mất im lặng. Thêm
  vào → **13 trường/record**; **3.308** triple + **3.308** edge Neo4j nay có
  `alt_evidence`; KG **không đổi** (19.548/13.379), validate **13/13 PASS**,
  nạp lại **+0/+0**.
- ✅ **Xác minh cache LLM idempotent** (D-094): chạy lại `infer_re_llm` với cùng
  tham số → **0,0 s · 0 request** (100/100 cache hit). Phát hiện cache SQLite
  **không bền** (bị thay thế giữa các lần chạy) ⇒ 89 request API bị lãng phí;
  artifact được giữ nguyên vì LLM ở `temperature=0` vẫn nondeterministic.

Còn lại của Phase 8 (không chặn Gate):
- ⏳ Kernel GPU LLM `re_llm_kaggle.jsonl` — **đã chạy xong** trên tài khoản
  phụ `dathungdao2004` (kernel **COMPLETE**, ngân sách thời gian **700 s** →
  dừng đúng lúc ở 724,5 s, **8 request**, Qwen3-8B **4-bit** thành công):
  **11** triple model trả về → **8** giữ lại (evidence substring **100%**) →
  **0** sau bộ lọc chất lượng ⇒ **KG giữ nguyên 13.379 cạnh** (byte-identical).
  **Quy mô nhỏ hơn kế hoạch 12,5 lần** vì quota GPU còn lại chỉ 18,7 phút
  (D-092). Kế hoạch lại: `--limit 5000 --time-budget-s 28800` khi quota
  reset 21/11/2026. **Không chặn Gate**: LLM baseline API đã đủ cho G5/G6.
- ⏳ **Cải thiện chất lượng RE** (không chặn demo): train lại với supervision
  **đầy đủ 18 quan hệ** cho mỗi cặp NEGATIVE (thay vì 1) ⇒ hết lỗi over-firing
  gốc thay vì lọc hậu kỳ.

**Sửa QA "sinh/mất năm" (16/11/2026 — D-087, D-088):**
- Triệu chứng: "Lý Thường Kiệt sinh năm nào?" → **"Không có trong dữ liệu"**
  dù KG có cạnh `sinh_nam → Year 1019`.
- Nguyên nhân: prompt đọc **thuộc tính** `p.birth_year` (chỉ **721/11.021**
  node Person có, 6,5%) thay vì **quan hệ** `sinh_nam` (**1.126** cạnh).
- Cách sửa: `OPTIONAL MATCH` + `coalesce(p.birth_year, y.value)` (vẫn chỉ đọc,
  trong 18 quan hệ) ⇒ **"Lý Thường Kiệt sinh năm 1019."** / **"mất năm 1105."** /
  **"Trần Hưng Đạo sinh năm 1230."**

**Phase 9 → 12 — ✅ đã hoàn thành (15/11/2026)** — xem bảng tổng quan ở trên.
Demo QA + Cytoscape đã xác minh chạy thật với 8 câu hỏi mẫu trả lời đúng.

**Sửa QA end-to-end (15/11/2026) — 4 lỗi đã xử lý:**
1. **Trả "Không có trong dữ liệu." dù KG có dữ liệu** → `answer_generator.py`:
   thêm `_has_content()` + fallback `_fallback_answer()`; prompt siết lại
   ("TUYỆT ĐỐI KHÔNG trả 'không có dữ liệu' khi records có dữ liệu").
2. **UI graph trắng** → `text_to_cypher.py`: `_build_graph` tra **1-hop** trong
   Neo4j theo `entity_id` (từ entity linker **hoặc** tra theo **tên** khi
   Cypher trả `p.name`) ⇒ mọi câu hỏi đều ra node + cạnh + bằng chứng.
3. **Entity linking sai** (bỏ dấu làm mất phân biệt) → `entity_linker.py`:
   khớp **giữ dấu** trước, bỏ dấu chỉ là dự phòng; loại alias loại `mention`.
4. **Node thiếu `description`/`reign_start`** → `build_aliases.py` giữ `props`,
   `build_graph.py` đọc `entity["props"]`; thêm `src/link/add_descriptions.py`
   (1.199 mô tả từ Wikipedia, đã loại chữ Hán).

**4 lỗi Kaggle thật phát hiện khi rà soát kernel (15/11/2026):**
1. **Kernel RE push với `dataset_sources: []`** → không mount được dataset →
   `FileNotFoundError` ngay ở cell đầu. Xoá kernel cũ, push lại từ builder
   (đã verify `kaggle kernels pull -m` → `dataset_sources` đúng). *(D-065)*
2. **Kernel Kaggle không có DNS** → `from_pretrained("vinai/phobert-base")` fail.
   Bundle weight `phobert-base` (523 MB) vào dataset `vhgr-re-data` (v2); LLM dùng
   **Kaggle Models** `manojkumarcs28/qwen3-8b/PyTorch/qwen3-8b/1` thay HuggingFace. *(D-066)*
3. **Mount path / tên file `.gz` không cố định** → dùng `rglob`/`glob` thay hard-code. *(D-067)*
4. **`metrics.json` thiếu per-relation F1** (Gate G1 yêu cầu) → thêm `per_relation_f1()`
   + `macro_f1`, đã unit test cục bộ. *(D-068)*

**Hạ tầng Kaggle — 5 phát hiện (15/11/2026):**
5. **Kernel CÓ internet** (đính chính D-066) → notebook LLM tự cài `bitsandbytes`
   để nạp 4-bit thay vì fallback bf16 16,4 GB. *(D-069)*
6. **Qwen3 thinking mode → 0/0 triple** sau 796s: `apply_chat_template` mặc định
   sinh `<think>` trước JSON → `parse_json` trả `None`. Sửa: `enable_thinking=False`
   + **fail-fast** (3 lần fail → in raw + `raise`). *(D-070)*
7. **Hàng đợi GPU Kaggle dùng chung toàn cục**: 2 kernel trên **2 tài khoản khác nhau**
   vẫn cả 2 `QUEUED` (12:12→12:46). Chia 2 tài khoản + dataset riêng cho account phụ. *(D-071)*
8. **Đường chạy không dùng GPU**: biến thể CPU (`enable_gpu: false`) → `RUNNING`
   **ngay lúc push**. *(D-072)*
9. **Benchmark tốc độ CPU thật** (kernel `vhgr-bench-re-cpu`): batch 8 → 3,226 s/step ·
   16 → 5,936 · **32 → 11,103 (s/example 0,3470 — tốt nhất)**. Chọn batch 32 +
   subsample 6.000 + `logging_steps=10` (bản đầu chạy >10 phút mà **không 1 dòng log**). *(D-073)*

> Phase 7 (phần D1.1) đã xong (15/11/2026) — đạt Gate **5/5**.
> Báo cáo: `reports/phase_07_report.md` · Nhật ký: `docs/10-nhat-ky/phase-07.md`.

Kết quả Phase 7 đã chốt:
- `data/interim/re_train.jsonl` — **29.957** mẫu (POS **15.580** / NEG **14.377**),
  tỉ lệ NEG/POS **0,9228**, **17/18** quan hệ có POSITIVE, **12.877** câu khác nhau.
- Nguồn nhãn POSITIVE: Wikidata **12.197** (78,3%) · Infobox **3.361** (21,6%) ·
  Lead **22** (0,1%).
- **0 false negative** · **0** khoá trùng · split train/dev/test = 23.526/3.491/2.940
  theo `splits.json` (chia theo `page_id`).
- **480 test pass** (41 test mới trong `tests/test_re_dataset.py`).
  Sai lệch: D-056 → **D-059**.

**4 điều đáng chú ý ở Phase 7 (15/11/2026):**
1. **Wikidata thuần KHÔNG đủ** — 12.197 mẫu / 10 quan hệ, thiếu 6 quan hệ
   (`ke_vi`, `thuoc_trieu_dai`, `chi_huy_tran`, `dong_doi_tai`, `lap_ra`,
   `dien_ra_tai`) vì các quan hệ này **không có trong Wikidata** cho nhân vật
   lịch sử Việt Nam. Hợp nhất 3 nguồn → 15.580 mẫu / 17 quan hệ. *(D-056)*
2. **Grounding theo TÊN quan trọng ngang đường theo `entity_id`** — chỉ
   3.731/12.602 cặp Wikidata có object là entity trong corpus; cho phép
   ground theo nhãn tiếng Việt bổ sung **7.363 mẫu** (4.834 → 12.197, +152%).
3. **"Không có trong Wikidata" ≠ "không có trong thực tế"** — trong 86.934 cặp
   entity đồng câu, **72.557** cặp có một đầu không rõ QID. Chỉ lấy **12.562**
   cặp "an toàn" (cả 2 đầu có QID + không mang quan hệ) làm negative →
   **0 false negative**. *(D-057)*
4. **`UNION` làm SPARQL mất tên property** trên cả QLever lẫn WDQS → phải hỏi
   **từng property một** (lô 200 QID). Tái dùng `run_query()` của Phase 1 →
   428 file cache dùng chung, chạy lại = **0 request HTTP**. *(D-058)*

**Việc cần làm ở Phase 8 (D1.2 — huấn luyện mô hình RE):**
1. Huấn luyện RE PhoBERT trên `data/interim/re_train.jsonl` (token-level,
   marker style `typed_markers`), seed 42; đánh giá P/R/F1 theo quan hệ trên
   dev/test.
2. ⚠️ Nhóm `coref_pronoun` có độ chính xác thấp nhất ở Phase 6 → cân nhắc dùng
   `coref` làm đầu vào thay vì chỉ dùng span NER.
3. ⚠️ Mô hình dùng slow tokenizer (D-040) → `word_ids()` không khả dụng; dùng
   `src.ner.data_convert.WordTokenizer`.
4. **Audit nhãn POSITIVE** — lấy ngẫu nhiên 100 mẫu, đối chiếu bằng chứng, đo tỉ
   lệ nhãn sai. Rủi ro cao: `vo_cua`/`chong_cua` (hướng phụ thuộc giới tính;
   corpus chỉ có 23 entity có `gender`) và `P40` (chiều inverse, D-059).
5. **Mở rộng bộ gold coref 100 → 300–500 câu** để chọn thứ tự ưu tiên R chắc
   chắn (D-054).

Kết quả Phase 6 đã chốt:
- `data/interim/coref_resolved.jsonl` — **186.960 câu · 197.610 mention**, resolve
  **137.584 (69,62%)**; không tính TIME **96,35%**; riêng danh xưng/đại từ **90,46%**.
- `data/interim/article_subjects.jsonl` — **2.441 chủ thể bài**, G6 **100,00%** trên 1.687 bài có ground-truth.
- Bộ gold **100 câu** gán tay (137 mention) → G5 **0,8729** (103 đúng / 118 có nhãn vàng).
- **439 test pass** · kiểm định Gate tự động **8/8** (`scripts/coref_gate_check.py`).
  Sai lệch: D-044 → **D-055**.

**4 điều đáng chú ý ở Phase 6 (15/11/2026):**
1. **Ablation đầu tiên đo sai** vì dùng monkeypatch (vá hàm) → vá chạy R3 *trước* chốt an toàn
   "đại từ số nhiều" → ra con số **0,7797 không tồn tại** trên hệ thống thật, **đảo ngược**
   kết luận thiết kế. Sửa bằng cách đưa thứ tự quy tự vào **config** (`coref.pronoun_rule_order`,
   D-052) → đo lại 9 biến thể trên **đúng đường dẫn code thật** → R3 đứng trước R1a
   (G5 0,8475 → **0,8729**). *(D-052)*
2. **Chênh lệch G5 giữa 2 thứ tự ưu tiên không có ý nghĩa thống kê**: McNemar **p = 0,5811**,
   CI 95% bootstrap chồng nhau → đây là chọn theo điểm số, **không** phải kết luận đã kiểm định.
   Cần mở rộng bộ gold ở Phase 7+ rồi đo lại. *(D-054)*
3. **Điều kiện R3 theo nguyên văn `docs/09`** ("đoạn không có `PERSON` nào") cho G5 chỉ
   **0,6864** → giữ điều kiện linh hoạt (R3 là tiên đề), **công khai sai lệch có chủ đích** kèm
   số liệu so sánh. *(D-047)*
4. **Báo cáo sinh tự động cũng phải rà soát ngôn ngữ**: `coref_quality.md` render nguyên văn
   câu mẫu → ký tự Hán của Wikipedia lọt vào tài liệu (1.030/2.441 bài corpus có chữ Hán).
   Đã thêm `sanitize_han()` + **3 test regression** đọc thẳng file đã sinh. *(D-055)*

Kết quả Phase 5 đã chốt:
- `models/ner/` — `vinai/phobert-base` fine-tune, **13 lớp BIO**, seed 42, 150.450 example × 5 epoch.
  Dev **micro F1 = 0,6832** · **macro F1 = 0,5589** (nền: gazetteer 0,7990).
- `data/interim/ner_predictions.jsonl` — **186.960 câu**, **143.108 entity**,
  **0** span sai offset, **0** nhãn sai, phủ **100%**.
- Bảng so sánh arm: `base` (scope đầy đủ) F1 **0,6832** > `large` (scope rút gọn 60k × 2 ep) F1 **0,6391**
  → **dùng `base`** làm artifact chính.
- Audit nhãn bạc (100 câu dev, seed 42): nhiễu **12,22%**, **thiếu 66,67%** mention →
  F1 bị trần bởi nhãn bạc, **không phải** lỗi model.
- Bộ gold 100 câu tay: F1 mô hình **0,6329** (P 0,7653 · R 0,5396) — chỉ số phụ, tái dùng cho Phase 13.
- **337 test pass**. Sai lệch: D-036 → **D-043**.

**3 lỗi thật phát hiện khi audit đóng phase (15/11/2026):**
1. **Off-by-one `end_token`** trong `apply_manual_review` → mỗi mention bị phủ dư 1 token → F1 bộ gold
   **0,0759 → 0,6329** sau khi sửa; thêm `tests/test_ner_audit.py` (3 test) chặn hồi quy. *(D-043)*
2. **Suy luận raw text lệch phân bố** với token hóa theo word ở **1.883/2.000** câu → chuyển cả
   train lẫn infer về dùng chung `build_silver.tokenize` → **0** span sai offset. *(D-040)*
3. **`phobert-large` OOM** ở batch 32 trên T4 14,56 GiB → batch 8 + `grad_accum=4` (giữ effective batch 32). *(D-039)*

**Việc cần làm ở Phase 7 (đã xong 15/11/2026 — xem kết quả Phase 7 ở trên):**
1. ✅ `data/interim/coref_resolved.jsonl` (đã có `canonical_id` cho 137.584 mention) làm đầu vào
   trực tiếp — **không** cần chạy lại Phase 6.
2. ⚠️ **Nhóm `coref_pronoun` có độ chính xác thấp nhất** → cân nhắc huấn luyện mô hình RE có dùng
   `coref` như đầu vào thay vì chỉ dùng span NER.
3. ⚠️ **Mô hình dùng slow tokenizer** (D-040) → `word_ids()` không khả dụng; dùng `src.ner.data_convert.WordTokenizer`.
4. ⚠️ **TITLE** F1 thấp nhất (0,2560, recall 0,22) → các quan hệ KG dựa trên danh xưng sẽ kém.
5. Cân nhắc mở rộng bộ gold coref 100 → 300–500 câu để chọn thứ tự ưu tiên R một cách chắc chắn (D-054).

**Vận hành đã kiểm chứng** (xem `docs/CONTEXT.md` §2.7) — dùng luôn cho Phase 1:
- Đọc dump bằng `lxml.etree.iterparse` (không dùng `mwparser` — PyPI chỉ có bản `0.1`).
- Tách câu bằng `pysbd` (`underthesea` không bắt buộc — D-005).
- SPARQL: **không** dùng `P463`/`P361` (trả 0) — dùng `P31=Q5` + `P27=Q881` + `P569` + `P22`
  (trả 213 người, đủ 9 triều đại).
- Neo4j: bảo vệ bằng session `READ_ACCESS` (Community không có RBAC — D-002).
- Parse infobox: `wikitextparser` (chính) + regex cân bằng ngoặc của Phase 1 (dự phòng) — xem `configs/infobox_mapping.yaml`.
- Ngày: ISO-8601 `YYYY-MM-DD` với **năm 4 chữ số** (`0939-02-01`) — D-022.

## Nhật ký

| Ngày | Phase | Nội dung | Ghi chú |
|---|---|---|---|
| 10/11/2026 | — | Hoàn thành bộ đặc tả `docs/00`–`docs/09` | Đã verify QID Wikidata, quota LLM, môi trường máy |
| 10/11/2026 | — | Tạo bộ file vibe-coding: `AGENTS.md`, `docs/CONTEXT.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/GLOSSARY.md`, rules, skills | |
| 10/11/2026 | — | Kiểm chứng hạ tầng (Neo4j Community không RBAC, `mwparser` không có trên PyPI, dump viwiki không có `redirects.xml.bz2`) | Ghi vào `docs/CONTEXT.md` §2.7, cập nhật D-008 và `cypher-safety.mdc` |
| 10/11/2026 | — | Thu hồi code triển khai sớm (`src/`, `backend/`, `frontend/`, `tests/`, `scripts/`, `configs/`, `.venv`) — giữ nguyên bộ setup vibe-coding | Theo yêu cầu: chỉ setup, chưa triển khai |
| 10/11/2026 | — | Rà soát chất lượng bộ setup: sửa 10 link/anchor hỏng trong `docs/00` và `docs/09`, bổ sung mục `docs/09` + `annotation-guidelines` vào bảng cấu trúc tài liệu | Kiểm tra tự động: 0 link hỏng, 0 anchor hỏng, 0 tiếng Trung, đủ 9 artifact theo `AGENTS.md` §7 |
| 13/11/2026 | — | Sửa bộ QID sai trong `docs/05` §3.1 + commit nền tảng vibe-coding setup | Dùng bộ 9 QID đã verify trong `docs/CONTEXT.md` §2.6; thay ví dụ SPARQL `P463`/`P361` (trả 0) bằng `P31=Q5`+`P27=Q881`+`P569`+`P22` |
| 13–14/11/2026 | 1 | Tải dump viwiki `20261101` + lọc 5 tầng T0–T5 | **2.441 bài** trong `data/interim/documents.jsonl` · QID 97,3% · `person` 1.061/`battle` 202/`place` 150/`dynasty` 16 · RAM peak 1,16 GB · 31 phút · checksum 2 lần **IDENTICAL** · 107 test pass. Sửa 4 lỗi: cây category khóa theo `lt_id` (D-010), khớp tiền tố loại infobox (D-009), T2 cần category Việt Nam (D-008), thêm T5 chốt phạm vi (D-012). Báo cáo: `reports/phase_01_report.md` |
| 14/11/2026 | 2 | Sửa lỗi code Phase 2 phát hiện khi dry-run | `pysbd` 0.3.4 không có `Language.MULTI` (D-013) → dùng `language="en"`; xử lý link lồng nhau / link hỏng ngoặc (D-014) → 0 bài còn ký tự wiki trong `clean_text` |
| 14/11/2026 | 2 | **Hoàn thành Phase 2** — làm sạch, tách câu/đoạn, trích hyperlink | **2.441 bài · 101.628 đoạn · 186.960 câu** (143.100 văn xuôi + 43.860 mục danh sách) · **0 lỗi offset** (186.960/186.960) · **0 bài còn ký tự wiki** · link giữ **99,8%** (mẫu số: wikitext thân bài — D-015) · 80,4% so với wikitext gốc · câu văn xuôi kết thúc dấu câu **95,3%** (Gate ≥95%) · toàn bộ 85,6% · 0 câu vỡ giữa tên có dấu phẩy · tách câu ~86 giây (cache `pysbd` — D-018) · **185 test pass**. Đã sửa 3 lỗi lớn: (a) offset link lệch ở **502 bài (20,6%)** → quét link một lần + đệ quy, gỡ ngoặc lạc **trước** khi ghi offset; (b) câu vỡ ở mỗi dòng do Wikipedia ngắt dòng cứng ~80 ký tự → nối soft-wrap (D-017); (c) `<ref>` không đóng nuốt 80 mục danh sách → sửa regex. Báo cáo: `reports/phase_02_report.md` · Nhật ký: `docs/10-nhat-ky/phase-02.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-02-text-stats.json` |
| 14/11/2026 | 3 | **Hoàn thành Phase 3** — parse infobox + chuẩn hóa ngày | **10.394 triple infobox** (conf ≥0,95) + **736 triple đoạn dẫn** (conf 0,85) + **1.764 entity** · Gate 1 parse rate person **100%** (1.061/1.061) · Gate 2 coverage ngày/gia đình **92,4%** (980/1.061; chỉ infobox 67,3% → +25,1 điểm từ đoạn dẫn) · Gate 3 chuẩn hóa ngày **100%** (30/30) · Gate 4 **100%** đủ trường · Gate 5 **0** quan hệ ngoài danh mục, **0** vi phạm loại chủ thể · **15/18 quan hệ**, 6/7 loại node · **274 test pass** (185 trước + 83 mới Phase 3 + 6 mới lượt rà soàn). 4 lỗi lớn đã sửa: (a) `split_items` gọi `clean_value` trước `extract_links` → mất toàn bộ link; (b) `combatant1` là **phe phái** ("Hoa Kỳ") chứ không phải người → thêm phát hiện tổ chức và **loại** triple; (c) khoảng ngày "25–26 tháng 12 năm 1944" bị đọc thành ngày đơn; (d) năm < 1000 thiếu số 0 (`939-02-01` → `0939-02-01`, D-022). Sai lệch D-019 → D-026 (D-021: 146/1.061 bài có infobox **rỗng** → đổi định nghĩa Gate 1; D-024: loại infobox lạ **không** mặc định `person` → `article` + dùng tín hiệu Wikidata, sửa lỗi node "Hà Nội"/"Cần Thơ" bị gán `person`; D-025: bổ sung 2/11 thuộc tính node còn thiếu `birth_place`/`death_place`; D-026: bổ sung `dump_version` + `model_name` cho cả 3 artifact). Báo cáo: `reports/phase_03_report.md` · Nhật ký: `docs/10-nhat-ky/phase-03.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-03-infobox-stats.json` |
| 14/11/2026 | 3 | **Audit đóng Phase 3** — rà chéo độc lập, phát hiện 4 lỗi thật | **10.394 → 10.078 triple** (−316: −253 `sinh_nam` trùng, −7 `mat_nam` trùng, −56 quan hệ khác trùng) · `sinh_nam` 985 → **732** (722/732 bài có **đúng 1** mốc sinh — là **khử trùng**, không mất dữ liệu) · self-loop 4 → **0** · trùng lead∩infobox 81 → **0** · `dong_doi_tai` 0 → **31** (template mơ hồ `infobox former country` → ưu tiên tín hiệu Wikidata) · gộp khoá tham số `_` ↔ khoảng trắng (`_collapse_key`) → +4 triple · **xoá** trích `danh_bai` từ infobox (4/4 cặp vi phạm schema, 1 cặp sai) · **280 test pass** (274 + 6 regression) · thêm 3 Gate bất biến (6/7/8) · sai lệch **D-027 → D-030** · số liệu đo bằng **ablation** (tắt từng fix riêng lẻ) chứ không so sánh tổng trước/sau |
| 14/11/2026 | 4 | **Hoàn thành Phase 4** — sinh nhãn bạc NER từ hyperlink | **186.960 câu · 138.860 mention** · scheme **BIO** (13 lớp) · Gate 1 độ phủ câu có hyperlink **100%** (60.078/60.078) · Gate 2 **6 lớp**, `PERSON` phổ biến nhất trong nhóm entity từ hyperlink (37.242 > LOCATION 30.818) · Gate 3 **100%** `len(tokens)==len(labels)` · Gate 4 splits 1.952/244/245 = 2.441, trùng **0** · Gate 5 baseline gazetteer dev micro F1 **0,7990** (macro 0,8261; surface 0,3917) · **306 test pass**. Nguồn nhãn: `category` 50,2% · `time_regex` 25,7% · `qid_direct` 13,1% · `qid_ancestor` 5,5% · `pattern` 2,9% · `kg_type` 2,4% · `wikidata_signal` 0,1%. Sai lệch D-031 → D-035. Báo cáo: `reports/phase_04_report.md` · Nhật ký: `docs/10-nhat-ky/phase-04.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-04-ner-stats.json` |
| 14/11/2026 | 4 | **Audit đóng Phase 4** — rà chéo độc lập, phát hiện 4 lỗi thật | **TIME 57.604 → 53.654** (loại **16.099** số đo lượng bị gán nhầm là năm — D-033; thêm lỗi ngữ cảnh lan toàn câu: "203/2025/QH15" → 2 năm sai) · **PERSON 35.425 → 37.242** (+765) · **TITLE 2.887 → 2.170** (−717: "Quan lại nhà Nguyễn" là **người** chứ không phải tước hiệu — D-034) · **DYNASTY** 5.957 · baseline gazetteer dev F1 **0,7388 → 0,7990** · nguồn nhãn `category` chiếm **50,2%** (là nguồn chính) · chuỗi ưu tiên đổi thành `category` → `qid_direct` → `qid_ancestor` → `kg_type` → `wikidata_signal` → `pattern` (D-032) · scheme đổi BIOES 25 → **BIO 13** (D-031) · **6 test regression** mới |
| 15/11/2026 | 5 | **Hoàn thành Phase 5** — huấn luyện NER PhoBERT + suy luận toàn corpus | **micro F1 0,6832** (macro 0,5589) trên dev 19.049 câu · **0** span sai offset / **143.108** entity / phủ **100%** (186.960 câu) · 2 arm trên **2 tài khoản Kaggle** chạy song song: `base` (150.450 × 5 ep, F1 **0,6832**, kernel 32.245 s) vs `large` (60.124 × 2 ep, F1 0,6391, kernel 6.828 s) → dùng `base` · audit nhãn bạc: nhiễu **12,22%**, **thiếu 66,67%** → F1 bị trần bởi nhãn bạc, không phải lỗi model · bộ gold 100 câu tay: F1 **0,6329** ≈ F1 dev → xác nhận mô hình học đúng · suy luận local từ `models/ner` khớp **40/40** câu với artifact Kaggle · **337 test pass**. Sai lệch D-036 → D-043. Báo cáo: `reports/phase_05_report.md` · Nhật ký: `docs/10-nhat-ky/phase-05.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-05-ner-stats.json` + `phase-05-base-vs-large.json` |
| 15/11/2026 | 5 | **Audit đóng Phase 5** — rà chéo độc lập, phát hiện 3 lỗi thật | (a) **Off-by-one `end_token`** trong `apply_manual_review` → mỗi mention bị phủ dư 1 token → F1 bộ gold **0,0759 → 0,6329** sau khi sửa (D-043, + 3 test regression); (b) **suy luận raw text lệch phân bố** với token hóa theo word ở **1.883/2.000** câu → chuyển cả train lẫn infer về dùng chung `build_silver.tokenize` → **0** span sai offset (D-040); (c) **`phobert-large` OOM** ở batch 32 trên T4 → batch 8 + `grad_accum=4` giữ effective batch 32 (D-039). Ngoài ra: **2 arm KHÔNG cùng scope** → không kết luận `large` tốt hơn `base` (D-042) |
| 15/11/2026 | 6 | **Hoàn thành Phase 6** — coreference rule-based (C1/C2) | **186.960 câu · 197.610 mention · resolve 137.584 (69,62%)** · không tính TIME **96,35%** · riêng danh xưng/đại từ **90,46%** (54.502 span dò thêm) · **2.441 chủ thể bài** (`article_subjects.jsonl`) · bộ gold **100 câu** gán tay (137 mention) → G5 **0,8729** · G4 **0** lỗi giới tính / 326 đại từ kiểm định · G6 **100,00%** (1.687 bài có ground-truth) · **0** vi phạm contract (G1/G7) · **439 test pass** · Gate tự động **8/8**. Sai lệch D-044 → D-055. Báo cáo: `reports/phase_06_report.md` · Nhật ký: `docs/10-nhat-ky/phase-06.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-06-coref-{stats,eval,ablation,significance}.json` |
| 15/11/2026 | 6 | **Audit đóng Phase 6** — phát hiện lỗi ở **công cụ đo**, không chỉ ở hệ thống | (a) **Ablation đầu tiên dùng monkeypatch** (vá hàm `_resolve_pronoun`) → bản vá chạy R3 *trước* chốt an toàn "đại từ số nhiều" → đo **sai**, ra con số **0,7797 không tồn tại** trên hệ thống thật, **đảo ngược** kết luận thiết kế (D-052) → sửa bằng cách đưa thứ tự quy tự vào **config** `coref.pronoun_rule_order` → đo lại **9 biến thể** trên đúng đường dẫn code thật → **R3 trước R1a** (G5 0,8475 → **0,8729**); (b) chênh lệch G5 giữa 2 thứ tự **không có ý nghĩa thống kê** → McNemar **p = 0,5811**, CI 95% bootstrap chồng nhau → công khai rõ đây là chọn theo điểm số, **không** phải kết luận đã kiểm định (D-054); (c) **điều kiện R3 theo nguyên văn `docs/09`** ("đoạn không có `PERSON` nào") cho G5 chỉ **0,6864** → giữ điều kiện linh hoạt + **công khai sai lệch có chủ đích** kèm số liệu (D-047/D-054); (d) R6 & R3 gắn sai giới tính → lọc theo giới tính ở cả 2 (D-051); (e) **rà soát ngôn ngữ trên file sinh tự động** → `coref_quality.md` render nguyên văn câu mẫu có **chữ Hán** của Wikipedia (1.030/2.441 bài corpus) → vi phạm quy tắc `no-chinese.mdc` → thêm `sanitize_han()` + **3 test regression** đọc thẳng file đã sinh (D-055) |
| 15/11/2026 | 7 | **Hoàn thành Phase 7 (D1.1)** — tập huấn luyện RE bằng distant supervision | **15.580 mẫu POSITIVE / 17 quan hệ** (G1 ≥10.000 → **+55,8%**) · NEG **14.377** → tỉ lệ **0,9228** (G2 ≤1,0) · **0** quan hệ ngoài danh mục 18 (G4) · **0 request HTTP** khi chạy lại (G5, 428 file cache) · `re_train.jsonl` **12.877 câu / 29.957 cặp** (contract: 1 record/câu, `pairs` lồng, nhãn chuỗi, `run_id`, offset **59.914/59.914** khớp `text[start:end] == mention`) · split 23.526/3.491/2.940 · **0 false negative** · **0** khoá trùng · **480 test pass**. Nguồn nhãn: Wikidata 12.197 (78,3%) + Infobox 3.361 (21,6%) + Lead 22 (0,1%). Sai lệch D-056 → D-060 (D-060: sửa contract output — bản đầu ghi phẳng theo cặp, làm lệnh kiểm thử chính thức `docs/09` crash). Báo cáo: `reports/phase_07_report.md` · Nhật ký: `docs/10-nhat-ky/phase-07.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-07-{re-stats,gate-check}.json` |
| 16/11/2026 | 8 | **Đóng Phase 8 — bộ lọc chất lượng + khôi phục entity + nạp lại KG** | ⚠️ **Phát hiện lớn nhất**: metric Phase 8 **bỏ qua** slot mask ⇒ micro-F1 0,9375 che mất lỗi over-firing; đo nghiêm (`scripts/eval_re_strict.py`) cho **P 0,0854 · R 0,9652 · F1 0,1569**, **19.220/19.339 FP (99,4%)** rơi vào slot mask, 976/2.987 cặp fire **16** quan hệ (D-080) → chuyển ràng buộc sang **bộ lọc hậu xử lý 4 lớp** (Top-1/cặp + kiểu đích + kiểu chủ thể + grounding theo tên + từ kích hoạt): `phobert_re` **511.567 → 4.985** (0,97%), `llm` **349 → 148** (42,4%) ⇒ **538.227 → 31.444 → 15.825 → 13.379** triple cuối (0 trùng / 0 ngoài danh mục / 0 self-loop / 0 evidence rỗng) (D-080…D-086). Thêm D-085: đảo ngược hash `entity_id` trên **60.116** tên ứng viên ⇒ khôi phục **2.826/2.871 (98,5%)** entity chỉ có trong triple (tên có dấu + kiểu schema), node `Entity` **2.897 → 162**. KG nạp lại: **19.548 node / 13.379 edge**, 0 orphan, `validate_graph.py` **13/13 PASS**, idempotent **+0/+0**. D-087: sửa QA "bao nhiêu vua" (44 → **19** vua có `reign_start`). ✅ Rà soát kernel Kaggle: **0** kernel `RUNNING`/`QUEUED`, xoá 3 kernel không cần, giữ `models/re/` GPU base (checksum OK). **616** test tổng pass. Sai lệch D-080 → **D-087**. Báo cáo: `reports/phase_08_report.md` · Nhật ký: `docs/10-nhat-ky/phase-08.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-08-distillation.json` |
| 15/11/2026 | 9 | **Hoàn thành Phase 9** — Entity Linking 3 tầng | KB mở rộng 1.764 → **15.931 entity / 50.820 alias** (gom canonical id từ coref Phase 6) → alias hit rate **24,8% → 72,82%** (+48 điểm) · link **143.973/197.610 = 72,86%** · recall@20 **1,000** · accuracy auto-gold **0,8049** (Gate ≥0,85 — chưa đạt) · **1,50 ms/mention** (Gate ≤200 ms) · embedding MiniLM-L12 (15.931×384) + `np.argpartition` (30 phút → 4 phút) · 4 test unit alias. Sai lệch D-073 (thêm) + định nghĩa lại `nil_node_ratio` (Gate nói "node", metric đo trên "mention"). Báo cáo: `reports/phase_09_report.md` · Nhật ký: `docs/10-nhat-ky/phase-09.md` |
| 15/11/2026 | 10 | **Hoàn thành Phase 10** — Đồ thị + Neo4j (F1–F4) | **19.758 node / 12.313 edge** trong Neo4j · **13/13** kiểm tra validate PASS (0 node thiếu prop, 0 edge thiếu bằng chứng, 0 quan hệ ngoài danh mục 18, 0 self-loop) · nạp **3 lần** → **+0/+0** (idempotent) · nạp 8,3 phút · user `reader` bị chặn ghi (`Neo.ClientError.Statement.AccessMode`) · sửa: node thiếu `wiki_url` 14.167 → **0**; mâu thuẫn năm âm lịch 3 → **0**; `SET n = {}` để DB khớp artifact. **D-074** (force-recreate container Neo4j) · **D-076** (Neo4j Community không APOC → gom theo 9 label + 18 quan hệ, Cypher tĩnh). Sai lệch: edge 12.313 < 50.000; nạp 50k ≈ 34 phút (> Gate 10 phút). Báo cáo: `reports/phase_10_report.md` · Nhật ký: `docs/10-nhat-ky/phase-10.md` |
| 15/11/2026 | 11 | **Hoàn thành Phase 11** — Text-to-Cypher backend (G1–G4, G6, G8) | `POST /api/ask` trả đúng output contract · **49/49 test** validator (25 payload độc hại chặn hết · 12 Cypher hợp lệ pass) · 4/4 câu mẫu đúng `status`: "Lê Lợi sinh năm nào?" → **1385** · "Lê Lợi là vua nhà nào?" → **Nhà Lê sơ** · "Ai là vua năm 1855?" → `not_in_data` · "MATCH (n) DETACH DELETE n" → `error` · **100%** Cypher có `LIMIT ≤ 100` · 0 quan hệ ngoài danh mục · end-to-end **2,5–8,0 s** (Gate p50 <10 s) · thêm `/api/search`, `/api/graph/{id}`, `/api/entity/{id}` · 3 lớp bảo vệ: validator tĩnh → session READ → prompt. **D-077**. Chưa đo G1 (execution accuracy) + p95 — cần tập câu hỏi có đáp án. Báo cáo: `reports/phase_11_report.md` · Nhật ký: `docs/10-nhat-ky/phase-11.md` |
| 15/11/2026 | 12 | **Hoàn thành Phase 12** — Giao diện web (H1–H4) | **7 component + 2 page** (`ChatPanel`, `MessageBubble`, `CypherBlock`, `GraphView` Cytoscape, `EntityCard`, `EvidencePanel`, `Legend`; `Home`, `EntityPage` `/entity/:id`) · `tsc --noEmit` **0 lỗi** · `npm run build` **✓ 1,89 s** (46 modules, JS 624 kB gzip 202 kB) · **4/4** hành vi H1–H4 hoạt động, xác nhận end-to-end trên trình duyệt ("Lê Lợi sinh năm 1385." 7.986 ms) · UI 100% tiếng Việt · node chưa xác minh viền đứt · mở rộng láng giềng ≤ 30 node. **D-078**. Sai lệch: dùng `useState` thay TanStack Query (rule `frontend.mdc`). Báo cáo: `reports/phase_12_report.md` · Nhật ký: `docs/10-nhat-ky/phase-12.md` |
| 17/11/2026 | 13 | **Hoàn thành Phase 13** — sửa chất lượng (entity linking · chiều đảo quan hệ · lọc cạnh nhiễu KG) | **12/12** ca lỗi người dùng báo → hết · **19 test** regression mới · **644 test** tổng pass (0 fail) · KG **không đổi**: 19.548 node / 13.379 cạnh. (a) **Exact-case ở lớp giữ dấu** (`_case_pattern_ok`) + loại **176** alias toàn-chữ-thường + chặn **42** đại từ ⇒ alias **13.760 → 13.582**; fix false positive (Đổi mới đất nước → Đổi Mới, Ông ấy → George H. W. Bush), giữ true positive (Trần Hưng Đạo, triều Lê, Le Loi không dấu); (b) **bảng chiều đảo 19 dòng** + 6 few-shot ngược trong prompt ⇒ câu hỏi về con của Trần Nhân Tông trả **5/5** con đúng (verify trực tiếp Neo4j); (c) **bộ lọc cạnh nhiễu** (`src/graph/noise_filter.py`) ở **TẦNG ĐỌC** (D-095) — 3.518 cạnh địa danh → lo **23** (11 Quốc lộ 14 + 2 bệnh viện + 10 tên rác LLM), **0** địa danh hợp lệ bị lo nhầm (giữ Vạn Kiếp, Trường An, Nghi Lộc (huyện), Đại Việt); so sánh 3 phương án: theo QID **1.405** / theo nhãn **126** / theo ngữ nghĩa **23**; (d) **guard chống bịa** (`has_filtering_predicate`) — câu đại từ trước trả 10 người ngẫu nhiên, sau trả `not_in_data` + hướng dẫn (D-096). Sai lệch D-095 → D-098. Báo cáo: `reports/phase_13_report.md` · Nhật ký: `docs/10-nhat-ky/phase-13.md` · Số liệu: `docs/10-nhat-ky/so-lieu/phase-13-chat-luong-kien-thuc.json` |
| 13/11/2026 | 0 | Bootstrap repo, cấu hình, hạ tầng | 56 test pass · Neo4j 5.26.32 ở `:7474` · `/api/health` → `ok`/`neo4j: up` · `READ_ACCESS` chặn ghi ở cấp server ✅ · `npm run build` 0 lỗi TS. Báo cáo: `reports/phase_00_report.md` |
| 14/11/2026 | 0–1 | Tạo `docs/10-nhat-ky/` — nhật ký triển khai chi tiết cho báo cáo/slide | Nhật ký chi tiết Phase 0 & 1 (quyết định, thang số liệu so sánh A/B/C/D, lỗi & bài học) + `so-lieu/*.json` máy đọc được. Xem `docs/10-nhat-ky/README.md` |
| 14/11/2026 | — | Cập nhật rules/skills để bắt buộc ghi nhật ký sau mỗi phase | `workflow-phases.mdc` (bước 7 + mục "Định dạng nhật ký"), `run-phase/SKILL.md` (Bước 7 mới), `check-context/SKILL.md`, `data-contracts.mdc` (hợp đồng JSON `so-lieu/`), `docs/09` + `AGENTS.md` |

## Chỉ số đo được (điền sau mỗi phase có số liệu)

| Chỉ số | Mục tiêu | Hiện tại |
|---|---|---|
| Số bài trong corpus | 2.000–5.000 | **2.441** (Phase 1) |
| Số câu | 150k–400k | **186.960** (Phase 2) |
| Triple infobox (conf ≥0,95) | — | **10.078** (Phase 3, sau audit) |
| Coverage ngày/gia đình (bài person) | ≥ 0,90 | **0,924** (Phase 3) |
| Nhãn bạc NER — số mention | — | **138.860** (Phase 4) |
| Nhãn bạc — độ phủ câu có hyperlink | ≥ 0,90 | **1,000** (Phase 4) |
| Nhãn bạc — F1 baseline trên dev | ≥ 0,60 | **0,799** (Phase 4) |
| NER F1 (dev) | ≥ 0.85 | **0,6832** (Phase 5, chấp nhận; trần do nhãn bạc thiếu 66,67% mention) |
| NER F1 (bộ gold 100 câu tay) | — | **0,6329** (Phase 5, chỉ số phụ) |
| Coref — resolve rate | ≥ 0,60 | **0,6962** (Phase 6) |
| Coref — resolve rate (không tính TIME) | — | **0,9635** (Phase 6) |
| Coref — resolve rate (danh xưng/đại từ) | — | **0,9046** (Phase 6) |
| Coref — G5 độ chính xác gán đại từ (C1) | ≥ 0,80 | **0,8729** (Phase 6) |
| Coref — G4 lỗi giới tính | 0 | **0** / 326 đại từ kiểm định (Phase 6) |
| Coref — G6 độ chính xác chủ thể bài (C2) | ≥ 0,90 | **1,0000** (Phase 6) |
| Coref — Gate G1–G8 kiểm định tự động | 8/8 | **8/8** (`scripts/coref_gate_check.py`) |
| RE — số mẫu POSITIVE (distant supervision) | ≥ 10.000 | **15.580** (Phase 7) |
| RE — tỉ lệ NEG/POS | ≤ 1,0 | **0,9228** (Phase 7) |
| RE — số quan hệ có POSITIVE | ≥ 8 | **17** / 18 (Phase 7) |
| RE — quan hệ ngoài danh mục | 0 | **0** (Phase 7) |
| RE — false negative | 0 | **0** (Phase 7) |
| RE F1 | ≥ 0.70 | **0,9375** (theo đặc tả Phase 8) — **đo nghiêm: 0,1569** (P 0,0854 · R 0,9652), xem D-080 |
| RE — số triple sau bộ lọc 4 lớp | — | `phobert_re` 511.567 → **4.985** (0,97%) · `llm` 349 → **148** (42,4%) |
| RE — số triple cuối cùng | — | **13.379** (538.227 input → lọc mô hình 31.444 → dedupe 15.825 → lọc tên chung 13.379) |
| Entity — tỉ lệ khôi phục (D-085) | — | **98,5%** (2.826/2.871) · node `Entity` 2.897 → **162** |
| Alias hit rate (linking) | ≥ 0.60 | **0,7282** (Phase 9) |
| Linking accuracy | ≥ 0.85 | **0,8049** (Phase 9, auto-gold; chưa đạt) |
| QA execution accuracy | ≥ 0.70 | — (Phase 11: 4 câu mẫu 4/4 đúng `status`) |
| Entity linking — false positive (exact-case) | 0 | **0** / 12 ca regression (Phase 13; trước: Đổi mới đất nước → Đổi Mới, Ông ấy → George H. W. Bush) |
| Entity linking — alias toàn-chữ-thường trong chỉ mục | 0 | **0** (Phase 13; trước: 211) |
| Alias đại từ trong chỉ mục | 0 | **0** (Phase 13; trước: 2) |
| Quan hệ đảo chiều (con của X) | 5/5 | **5/5** (Phase 13, verify Neo4j) |
| Cạnh nhiễu KG lọc khỏi context | 0 | **0** (Phase 13; lo 23 cạnh ở tầng đọc) |
| Câu hỏi không có entity cụ thể | `not_in_data` | **`not_in_data`** (Phase 13, guard D-096) |
| Số node KG | 5k–30k | **19.548** (Phase 10, nạp lại 16/11/2026) |
| Số cạnh KG | 50k–200k | **13.379** (thấp hơn mục tiêu — đánh đổi có chủ đích do bộ lọc chất lượng, xem D-083) |
| % cạnh có bằng chứng | 100% | **100%** (0/13.379 thiếu — Phase 10) |
| Cypher p95 (s) | < 2 | — (chưa đo, cần ≥100 truy vấn) |
| End-to-end p50 (s) | < 10 | **2,5–8,0** (Phase 11) |
| RAG — số câu benchmark | ≥ 200 | **247** (Phase 16 — đủ 5 dạng) |
| RAG — correctness A (Vanilla) | — | **1,1619** (247 câu, LLM-judge) |
| RAG — correctness B (Hybrid GraphRAG) | > A | **1,5506** (Δ **+0,3887**) |
| RAG — correctness B− (Hybrid không KG) | ≈ A | **1,1700** (Δ(B vs B−) = **+0,3806**) |
| RAG — citation_precision B | ≥ 0.70 | **0,8275** (A 0,6154 · B− 0,6275) |
| RAG — correctness A · **narrative** (60 câu) | — | D-122 **1,91** → D-123 **1,84** → D-124 **1,95** (43 câu) |
| RAG — correctness B · **narrative** (60 câu) | > A | D-122 **1,78** → D-123 **1,79** → D-124 **1,79** (43 câu) — ⚠️ chưa vượt A |
| RAG — correctness B− · **narrative** (60 câu) | ≈ A | D-122 **1,85** → D-123 **1,85** → D-124 **1,92** (43 câu) |
| RAG — B bổ sung thông tin "bên liên quan" | — | D-122 **33/60** → D-123 **38/60** câu (Phase 18) |
| RAG — A "Không có trong dữ liệu" mà B trả đủ | > 0 | D-123 **6/60** · D-124 **5/43** câu (ngược lại: **0**) |
| RAG — faithfulness_rate | ≥ 0.90 | A **0,9109** · B **0,9150** · B− **0,9231** (✅ sau D-118; trước: B 0,8381 ❌) |
| RAG — no_data_accuracy | ≥ 0.90 | **0,9655** (cả 3 arm) |
| RAG — mismatch model giữa 3 arm | 0 | **0** / 247 câu |
| RAG — arm bị judge bỏ sót | 0 | **0** (cả 3 arm) |
| RAG — câu lỗi hạ tầng | 0 | **0** (cả 3 arm) |
| RAG — gold section trong top-8 (narrative) | ≥ 55/60 | **55/60** ✅ (Phase 19; trước **46/60**) |
| RAG — câu hỏi eval hợp lệ (kiểm chứng live) | 100 % | **246/246** ✅ (0 câu không hợp lệ — G19-7; 98 mệnh đề Wikidata khớp) |
| RAG — câu trả lời bịa số năm (kiểm chứng live) | 0 | **0** ✅ (G19-6, checkpoint đang chạy) |
| RAG — `abstain_with_evidence` (nói "không có" khi context có gold) | 0 | 🟡 đang chờ eval đủ (metric đã có trong `evaluate_rag.py`) |
| Faithfulness (không bịa) | ≥ 0.90 | — |

## Tài liệu liên quan

| File | Nội dung |
|---|---|
| `docs/CONTEXT.md` | Quyết định đã chốt, QID, model, câu hỏi mở |
| `docs/09-ke-hoach-thuc-thien.md` | Đặc tả chi tiết từng phase |
| `docs/10-nhat-ky/` | **Nhật ký triển khai chi tiết** — quyết định, thang số liệu so sánh, lỗi & bài học (nguyên liệu cho báo cáo / slide) |
| `docs/DECISIONS.md` | Nhật ký quyết định kiến trúc |
| `docs/GLOSSARY.md` | Thuật ngữ |
| `reports/deviations.md` | Sai lệch so với kế hoạch |
| `reports/phase_XX_report.md` | Báo cáo từng phase |

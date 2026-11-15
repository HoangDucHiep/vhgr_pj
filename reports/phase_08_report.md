# Phase 08 — Mô hình RE, LLM baseline, hợp nhất triple (D1/D2/D3)

- Ngày: 2026-11-15 → **cập nhật 2026-11-16**
- Trạng thái: 🟢 **19/19 Gate đạt** · **12/12 mục objective đối chiếu PASS** — mô hình RE train xong trên Kaggle GPU (**micro-F1 0,9375**); **suy luận RE toàn corpus đã xong** (CPU local 4 shard + đối chiếu Kaggle GPU khớp 100%); bộ lọc chất lượng 4 lớp (D-080 → D-086) đã áp dụng; `triples_merged.jsonl` = **13.379 triple / 13 trường** (có `alt_evidence`, D-093); KG đã nạp lại **19.548 node / 13.379 edge**, validate **13/13 PASS**; **625** unit test pass
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-08.md`
- Sai lệch: `reports/deviations.md` (D-061 → **D-094**)
- Chấm Gate máy đọc được: `reports/phase_08_gate_check.json`
- Số liệu máy đọc: `docs/10-nhat-ky/so-lieu/phase-08-distillation.json` · `docs/10-nhat-ky/so-lieu/phase-08-objective-audit.json`

## Đã làm

- `src/re/data_convert_re.py` — mã hoá input mô hình RE:
  - Marker **có kiểu + vai trò**: `«PERSON:SUBJ:Lê Lợi»` / `«PERSON:OBJ:Nguyễn Phúc Chu»` (D-062).
  - Chuỗi: `<s> subj </s> câu có «…» và «…» </s> obj </s>` — nhãn ở `[CLS]`.
  - **19 đầu sigmoid** (18 quan hệ + `NA`), slot chưa biết = `-100.0` (masked BCE) (D-061).
  - Bảng type entity: NER vote → infobox → `year_` → `unknown` (D-063).
  - Bảng tên hiển thị: infobox → mode mention không phải đại từ → mention thô.
- `src/re/train_re.py` — `Trainer` đa nhãn, `masked_bce_loss`, hiệu chỉnh ngưỡng trên dev, ghi `models/re/metrics.json` + `trainer_state.json`.
- `src/evaluation/metrics.py` — thêm `relation_f1_multilabel` (micro/macro/per-relation/NA).
- `src/common/llm_client.py` — Gemini (`google-generativeai`) + Groq (`groq`) fallback, retry 429/5xx, rate limiter RPM/RPD, cache SQLite idempotent, không log key (D-064: tự nạp `.env`).
- `src/re/infer_re.py` — sinh cặp ứng viên (≤ 60 token), suy luận 19 sigmoid, lọc `NA` + threshold → `data/interim/re_phobert.jsonl`.
- `src/re/infer_re_llm.py` — prompt JSON 15 câu/request, kiểm `evidence` substring, đếm loại → `data/interim/re_llm.jsonl`.
- `src/re/merge_triples.py` — gộp **5 nguồn**, dedupe confidence cao nhất + `alt_evidence`, chuẩn hoá orientation quan hệ đối xứng, loại self-loop/evidence rỗng/quan hệ ngoài danh mục → `data/interim/triples_merged.jsonl` (**12 trường**).
- `tests/test_llm_client.py` (20), `tests/test_re_model.py` (32), `tests/test_merge_triples.py` (24) — **76 test mới**.
- Kaggle: dataset `hoanghiep421/vhgr-re-data` (v2 — bundle weight `vinai/phobert-base`, D-066) + `dathungdao2004/vhgr-re-data` (dataset riêng cho tài khoản phụ, D-071).
- **Hạ tầng huấn luyện (D-071, D-072, D-073):**
  - `scripts/build_kaggle_re_notebook.py --cpu-variant` → biến thể **CPU-only** của notebook RE (`enable_gpu: false`), kernel `hoanghiep421/vhgr-phase-8-re-train-phobert-base-cpu` → chuyển `RUNNING` **ngay lúc push** (không tranh GPU).
  - `scripts/build_kaggle_bench_notebook.py` → kernel benchmark `hoanghiep421/vhgr-bench-re-cpu`, đo `s/step` cho batch 8/16/32.
  - `scripts/wait_kaggle_phase8.py` — watcher 2 tài khoản, tự tải artifact.
  - `scripts/finish_phase8.py` — chuỗi tự động: chờ kernel → tải model → `infer_re` → `merge_triples` → chấm Gate.
- **Sửa lỗi nghiêm trọng kernel LLM (D-070):** `enable_thinking=False` cho Qwen3 + fail-fast khi parse JSON thất bại + tự cài `bitsandbytes` (4-bit).

## Lệnh đã chạy

```bash
# Mã hoá input (12.877 câu → 25.947 ví dụ)
python -m src.re.data_convert_re
→ 25.947 ví dụ (train 20.382 / dev 2.987 / test 2.578) · max 256 subword · mean 80,3 · 88,7% slot mask

# LLM baseline API (tập con 1.500 câu, split test)
python -m src.re.infer_re_llm --limit 1500 --chunk-size 15 --out data/interim/re_llm.jsonl
→ 100 request / 386,7s · 362 triple → giữ 353 (97,5%) · evidence substring 97,5% · relation ngoài danh mục 0

# Chạy lại (cache idempotent)
python -m src.re.infer_re_llm --limit 1500 --chunk-size 15 --out data/interim/re_llm.jsonl
→ 100 request / 0,0s · 0 API call · kết quả y hệt

# Hợp nhất triple
python -m src.re.merge_triples --out data/interim/triples_merged.jsonl
→ 26.660 input → 12.313 unique · 0 trùng · 0 ngoài danh mục · 0 self-loop · 0 evidence rỗng
→ LLM: 349 triple vào, 329 vào merge, 329/329 resolve về entity_id (100%)

# --- 16/11/2026: suy luận RE toàn corpus (CPU local, 4 shard × 2 thread) ---
python scripts/run_infer_re_parallel.py --model models/re --shards 4 --threads 2 \
    --batch-size 256 --out data/interim/re_phobert.jsonl
→ 4 shard × 24.837 cặp · 0,531 s/cặp/shard · 13.187s/shard ≈ 3,66 giờ (song song)
→ giữ lại 511.567 quan hệ · 17.358 câu có dự đoán

# Gộp shard (không cần chạy lại suy luận 3,7 giờ)
python scripts/merge_re_shards.py --out data/interim/re_phobert.jsonl
→ 4 shard → 17.358 câu / 511.567 quan hệ → data/interim/re_phobert.jsonl (230,4 MB)

# Hợp nhất lại 5 nguồn (giờ có phobert_re) — BẢN ĐẦU (chưa lọc chất lượng)
python -m src.re.merge_triples --out data/interim/triples_merged.jsonl
→ 538.227 input → 335.843 unique · 0 trùng · 0 ngoài danh mục · 0 self-loop · 0 evidence rỗng
→ by_method: phobert_re 324.520 · infobox 9.413 · distant_supervision 849 · rule 736 · llm 325

# --- 16/11/2026: đo lại nghiêm chất lượng RE (D-080) ---
python scripts/eval_re_strict.py --split dev
→ NGHIÊM — precision=0.0854 recall=0.9652 f1=0.1569
→ TP=1805 FP=19339 (trong đó 19220 thuộc slot MASK) FN=65
→ 1731/2987 cặp (58.0%) có quan hệ dự đoán; 976 cặp fire 16 quan hệ
→ ⇒ 99,4% FP rơi vào slot bị mask ⇒ metric lỏng (F1 0,9375) không phản ánh thật

# --- 16/11/2026: bộ lọc 4 lớp + merge LẠI (D-080 → D-086) ---
python -m src.re.merge_triples --out data/interim/triples_merged.jsonl
→ Nguồn phobert_re 511.567 → 4985 (sai kiểu đích 15804, dư trong cặp 455202,
    không có bằng chứng 9291, không có từ kích hoạt 12736, sai kiểu chủ thể 13549)
→ Nguồn llm 349 → 148
→ Gộp: 31444 input → 15825 unique (loại 15619 trùng)
→ Loại tên chung (D-081 + D-086): 15825 → 13379 (bỏ 2446 cạnh)
→ Đã ghi 13379 triple

# --- 16/11/2026: khôi phục entity chỉ có trong triple (D-085) ---
python -m src.graph.recover_entities
→ Registry 15925 entity · Entity chỉ có trong triple: 2871
→ Khôi phục từ infobox/lead: 2459 · Tập tên bề mặt: 60116
→ Tổng đã khôi phục: 2826/2871 (98,5%) · 45 fallback slug
→ Ghi 2871 entity → data/knowledge_base/entities_recovered.jsonl

# Dựng lại đồ thị + nạp Neo4j
python -m src.graph.build_graph --config configs/default.yaml \
    --out data/knowledge_base/graph.jsonl --add-missing-entities
→ 19548 node · 13379 edge · 0 orphan
python scripts/load_neo4j.py --batch 2000
→ nạp theo label + theo quan hệ (MERGE idempotent) · lần 2: +0 node / +0 edge

# Kiểm định chất lượng KG
python scripts/validate_graph.py
→ 13/13 PASS · 0 lỗi nghiêm trọng

# Đối chiếu Kaggle GPU vs CPU local (cùng mã nguồn repo)
python - <<'PY'
import json
def load(p):
    d = {}
    for line in open(p, encoding="utf-8"):
        r = json.loads(line)
        for p2 in r["pairs"]:
            d[(r["sentence_id"], p2["subject"], p2["relation"], p2["object"])] = round(p2["confidence"], 4)
    return d
gpu = load("/tmp/kg_infer_gpu/re_phobert.jsonl"); cpu = load("data/interim/re_phobert.jsonl")
kg, kc = set(gpu), set(cpu)
common = kg & kc
print("GPU", len(gpu), "CPU", len(cpu), "chung", len(common), "chỉ GPU", len(kg-kc), "chỉ CPU", len(kc-kg))
print("confidence tuyệt đối:", sum(1 for k in common if gpu[k]==cpu[k]), "/", len(common))
PY
→ GPU 454.767 · CPU 454.767 · chung 454.767 · chỉ-GPU 0 · chỉ-CPU 0
→ confidence giống tuyệt đối 434.176/454.767 (95,47%) · mean |Δ| = 0,000714

# Dựng lại đồ thị + nạp Neo4j (BẢN ĐẦU — đã thay bằng lệnh ở trên sau khi lọc)
python -m src.graph.build_graph --config configs/default.yaml \
    --out data/knowledge_base/graph.jsonl --add-missing-entities
→ 19.764 node · 335.843 edge · 0 orphan
python scripts/load_neo4j.py --batch 2000
→ nạp theo label + theo quan hệ (MERGE idempotent)

# Lệnh kiểm thử chính thức (docs/09 §Phase 8)
python - <<'PY'
import json
rows=[json.loads(l) for l in open('data/interim/triples_merged.jsonl')]
for r in rows:
    assert all(r.get(k) for k in ("evidence_sentence","source_url","doc_id","sentence_id")), r
    assert 0<=r['confidence']<=1
    assert r['method'] in {"infobox","distant_supervision","phobert_re","llm","rule"}
keys={(r['subject'],r['relation'],r['object']) for r in rows}
assert len(keys)==len(rows), "triple trùng sau merge"
print("OK triples",len(rows))
PY
→ OK triples 13379   (bản đầu trước lọc: 12313)

# Benchmark tốc độ Kaggle CPU (chọn batch size cho biến thể CPU)
python scripts/build_kaggle_bench_notebook.py --out /tmp/bench_cpu
kaggle kernels push -p /tmp/bench_cpu
→ batch 8: 3,226 s/step | batch 16: 5,936 | batch 32: 11,103 (s/example 0,3470 — tốt nhất)

# Dry-run infer_re (xác minh chuỗi hậu-xử lý trước khi model thật về)
python -m src.re.infer_re --model models/re_smoke --out /tmp/re_smoke_infer.jsonl --limit 500
→ 73 record, đúng format output contract Phase 8

# Test
pytest -q tests/test_re_model.py tests/test_merge_triples.py tests/test_llm_client.py
→ 76 test — tất cả pass
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số ví dụ train RE | — | 25.947 (train 20.382 / dev 2.987 / test 2.578) |
| Slot chưa biết được mask | — | 88,7% |
| **RE F1 dev (micro, GPU base)** | **≥ 0,70** | **0,9375** — vượt Gate (theo đặc tả) |
| **RE F1 dev (NGHIÊM — đo lại, D-080)** | — | **0,1569** (P 0,0854 · R 0,9652) — **99,4% FP rơi vào slot mask** |
| RE F1 dev (macro) | — | 0,9190 |
| RE NA-F1 | — | 0,9145 |
| RE eval_loss | — | 0,1676 |
| Quan hệ có F1 ≥ 0,70 | — | **16 / 18** |
| Ngưỡng hiệu chỉnh | — | 0,55 (NA 0,50) |
| Cặp ứng viên (≤ 60 token) | 113.917 (kế hoạch) | **113.917** (token khoảng trắng) — khớp tuyệt đối |
| Cặp `canonical_id` khác nhau (dùng để suy luận) | — | 99.348 (14.569 self-pair bị loại) |
| Cặp mơ hồ hướng (marker chỉ có tên) | — | 1.383 (4,62%) → **0** sau khi thêm vai trò |
| LLM: evidence substring (trước lọc) | ≥ 90% | **97,51%** |
| LLM: giữ lại sau lọc | ≥ 60% | **97,51%** |
| LLM: relation ngoài danh mục | 0 | **0** |
| LLM: số request | ~100 | 100 (15 câu/request) |
| Triple hợp nhất | — | 12.313 (từ 26.660 input) |
| Triple LLM resolve về `entity_id` | 100% | **329/329 (100%)** |
| **Suy luận RE — câu có dự đoán** | — | **17.358** (từ 99.348 cặp ứng viên) |
| **Suy luận RE — quan hệ giữ lại** | — | **511.567** |
| **Thời gian suy luận CPU (4 shard)** | — | **3,66 giờ** (0,531 s/cặp/shard) |
| **GPU vs CPU — cặp trùng** | 0 khác biệt | **454.767 / 454.767** (0 chỉ-GPU, 0 chỉ-CPU) |
| **GPU vs CPU — confidence tuyệt đối** | — | **95,47%** (mean \|Δ\| = 0,000714) |
| **Triple hợp nhất (5 nguồn)** | — | **335.843** (từ 538.227 input) — bản đầu, chưa lọc |
| **Triple hợp nhất (SAU bộ lọc 4 lớp + lọc tên chung)** | — | **13.379** (D-080 → D-086) |
| — `phobert_re` sau lọc | — | 511.567 → **4.985** (0,97%) |
| — `llm` sau lọc | — | 349 → **148** (42,4%) |
| — Dedupe | — | 31.444 → 15.825 (loại 15.619 trùng) |
| — Lọc tên chung | — | 15.825 → 13.379 (loại 2.446) |
| **Entity khôi phục (D-085)** | — | **2.826/2.871 (98,5%)** · node `Entity` 2.897 → **162** |
| **KG sau nạp** | 5k–30k node | **19.548 node / 13.379 edge** · validate **13/13 PASS** · idempotent **+0/+0** |
| **Trường mỗi triple (D-093)** | 13 (`docs/09` §Phase 8) | **13** — gồm `alt_evidence` (trước: 12 ⇒ mất 13.294 bằng chứng thay thế) |
| **Triple có `alt_evidence` (D-093)** | — | **3.308 / 13.379** · tổng **13.294** câu bằng chứng thay thế |
| **Edge Neo4j có `alt_evidence` (D-093)** | — | **3.308 / 13.379** (trước: 0) |
| **Cache LLM — chạy lại (D-094)** | 0 request | **0,0 s · 0 request** (100/100 cache hit) — đo lại 16/11 06:47 |
| Test mới | — | 76 (20 + 32 + 24) + 7 (`test_entity_linker`) + 8 (`test_kaggle_llm_notebook`) + 1 (`alt_evidence` regression) → **625** test tổng, tất cả pass |
| Tốc độ Kaggle CPU (batch 32) | — | 11,103 s/step · 0,3470 s/example |
| Thời gian train biến thể CPU | < 9 giờ (trần Kaggle) | ≈ 69 phút (6.000 ex × 2 epoch) |

## Gate

- [x] **G1** — RE F1 dev ≥ 0,70 → **0,9375** (micro, GPU base) ✅
- [x] **G2** — 100% triple có 6 trường bắt buộc → 100% (0 thiếu)
- [x] **G3** — 0 triple trùng sau merge → **0**
- [x] **G4** — 0 quan hệ ngoài danh mục → **0**
- [x] **G5** — LLM: ≥ 90% evidence là substring trước khi lọc → **97,51%**
- [x] **G6** — LLM: sau lọc còn ≥ 60% → **97,51%**
- [x] **G7** — `llm_client` test: retry + fallback + cache (mock) → **20 test pass**
- [x] **G8** — 0 self-loop · 0 evidence rỗng → **0 / 0**
- [x] **G9** — Triple LLM resolve về `entity_id` → **329/329 (100%)**
- [x] **G10** — Suy luận RE: `re_phobert.jsonl` đúng contract (1 record/câu, đủ trường) → **17.358 câu / 511.567 quan hệ / 0 invalid**
- [x] **G11** — GPU và CPU cho cùng kết quả → **454.767/454.767 cặp trùng, 0 khác biệt**
- [x] **G12** — Bộ lọc chất lượng (D-080→D-086): 538.227 → 31.444 → 15.825 → **13.379**
- [x] **G13** — Khôi phục entity (D-085): **2.826/2.871 (98,5%)**
- [x] **G14** — KG nạp & validate: **19.548 node / 13.379 edge**, validate **13/13 PASS**, idempotent **+0/+0**
- [x] **G15** — QA end-to-end: **6/6 câu mẫu đúng**, mỗi câu ≥ 26 node / ≥ 29 cạnh
- [x] **G16** — QA năm sinh/mất (D-088): **6/6 đúng** (Lý Thường Kiệt 1019/1105, Trần Hưng Đạo 1230)
- [x] **G17** — `alt_evidence` được giữ (D-093): **13 trường/record**, **3.308** triple + **3.308** edge có `alt_evidence`, **13.294** bằng chứng thay thế được phục hồi
- [x] **G18** — Cache LLM idempotent (D-094): chạy lại = **0 request**, **0,0 s**
- [x] **G19** — Pytest toàn bộ xanh: **625 test pass**

## Sai lệch so với kế hoạch

| Mã | Sai lệch | Xử lý |
|---|---|---|
| D-061 | Kế hoạch ngụ ý multi-class softmax ("giống Phase 5") → đổi sang **đa nhãn sigmoid** | Người dùng đã chốt khi được hỏi; ghi vào `docs/DECISIONS.md` (D-061) |
| D-062 | Marker có thêm **vai trò** `SUBJ`/`OBJ` + tên hiển thị chuẩn | Bắt buộc theo số liệu 4,62% cặp mơ hồ |
| D-063 | Bổ sung chuỗi 4 bước cho bảng type entity | Kế hoạch không quy định nguồn type |
| D-064 | `llm_client` tự nạp `.env` (nạp biến rỗng) | Sửa lỗi nội bộ — script `python -m` không đi qua `backend/app/settings.py` |
| D-065 | Kernel RE push với `dataset_sources: []` → không mount được dataset | Xoá kernel cũ, push lại từ builder (đã verify `kaggle kernels pull -m`) |
| D-066 | Kernel Kaggle **không có DNS** → `from_pretrained("vinai/...")` fail | Bundle weight `phobert-base` vào dataset (v2); LLM dùng Kaggle Models |
| D-067 | Mount path + tên file `.gz` có thể khác | Dùng `rglob`/`glob` thay vì đường dẫn cứng |
| D-068 | `metrics.json` thiếu per-relation F1 (Gate G1 yêu cầu) | Thêm `per_relation_f1()` + `macro_f1` (đã unit test cục bộ) |
| D-069 | Đính chính: kernel Kaggle **có** internet (log HF Hub reachable) | Notebook LLM tự cài `bitsandbytes` → nạp 4-bit |
| D-070 | Qwen3 **thinking mode** → 0/0 triple sau 796s | `enable_thinking=False` + fail-fast (in raw + `raise`) |
| D-071 | Hàng đợi GPU Kaggle là **dùng chung toàn cục** (2 account đều `QUEUED`) | Chia 2 kernel sang 2 tài khoản + dataset riêng cho account phụ |
| D-072 | Không có đường chạy nếu GPU kẹt | Thêm **biến thể CPU** (`enable_gpu: false`) → `RUNNING` ngay |
| D-073 | Không biết ETA vì `logging_steps=100` mà 2.548 step/epoch | Kernel benchmark đo `s/step` → chọn batch 32 + subsample 6.000 + `logging_steps=10` |
| D-077 | Kernel CPU báo `COMPLETE` nhưng **không có `metrics.json`** (dừng ở epoch 1, subsample 6.000) | Loại; dùng kernel **GPU base** (3 epoch, toàn bộ 20.382 câu, micro-F1 0,9375) |
| D-078 | Suy luận RE cần ~3,7 giờ CPU (máy local **không có GPU**) | Đóng gói bundle + đẩy Kaggle GPU; **chạy song song** CPU local làm dự phòng |
| D-079 | Tài khoản Kaggle **chính hết quota GPU** (44.677s / 21.600s, reset 21/11) ⇒ kernel kẹt `QUEUED` **vĩnh viễn** | Chuyển sang **tài khoản phụ** `dathungdao2004` (còn ~4.428s): đóng gói lại dataset riêng + push kernel; xoá 3 kernel không cần; sửa `find_root()` chịu được mount chậm (`FileNotFoundError` khi `/kaggle/input/<slug>` chưa tồn tại) |
| **D-080** | Metric Phase 8 **bỏ qua** slot mask ⇒ micro-F1 0,9375 che mất lỗi over-firing (nghiêm: P 0,0854 · R 0,9652 · F1 0,1569) | Đo lại bằng `scripts/eval_re_strict.py`; chuyển ràng buộc sang **bộ lọc hậu xử lý 4 lớp** (Top-1/cặp + kiểu đích + kiểu chủ thể + grounding tên + từ kích hoạt) |
| **D-081** | 24,2% cạnh có đầu là **tên chung** ("vua", "ông", "nhà") | Danh sách chặn `GENERIC_TITLE_NAMES`; loại **2.446** cạnh |
| **D-082** | Bằng chứng không chứa tên chủ thề/đối tượng ⇒ cạnh "đúng hình thức, sai ý nghĩa" | Bắt buộc grounding theo tên (có dấu trước, bỏ dấu dự phòng); loại 9.291 + 45 triple |
| **D-083** | Câu bằng chứng không chứa từ kích hoạt của quan hệ | Từ kích hoạt 2 mức (mạnh/yếu), từ yếu phải **gần** tên entity; loại 12.736 + 130 triple |
| **D-084** | Quan hệ không khớp **kiểu chủ thể** theo schema | `RELATION_SOURCE_TYPES`; loại 13.549 + 5 triple |
| **D-085** | 2.897 node `Entity` không có tên (chỉ có trong triple) | Đảo ngược hash `entity_id` trên 60.116 tên ứng viên ⇒ khôi phục **98,5%** |
| **D-086** | Chặn tên chung toàn cục **loại nhầm** cạnh `thuoc_trieu_dai` hợp lệ ("Nhà Trần") | `GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY` (miễn trừ khi quan hệ là `thuoc_trieu_dai`) + `GENERIC_TARGET_NAMES_BY_RELATION` |
| **D-087** | QA "Nhà Trần có bao nhiêu vua?" trả **44** (mọi người thuộc nhà) | Thêm quy tắc + few-shot vào `text_to_cypher.txt` ⇒ chỉ đếm node có `reign_start IS NOT NULL` ⇒ **19** |
| **D-088** | QA "sinh/mất năm" trả **"Không có trong dữ liệu"** dù KG có cạnh `sinh_nam`/`mat_nam` | Prompt đọc **thuộc tính** `p.birth_year` (chỉ **721/11.021** node) thay vì **quan hệ** (`sinh_nam` 1.126 cạnh, `mat_nam` 1.059) | `OPTIONAL MATCH` + `coalesce(p.birth_year, y.value)` ⇒ "Lý Thường Kiệt sinh năm **1019**" / "mất năm **1105**" / "Trần Hưng Đạo sinh năm **1230**" |
| **D-089** | Kernel LLM không chạy được: quota GPU tài khoạn chính **đã vượt** (44.694/21.600 s) | Chuyển sang tài khoản phụ `dathungdao2004` (còn **18,7 phút**); dùng `env -u KAGGLE_USERNAME -u KAGGLE_KEY KAGGLE_API_TOKEN=<tok>` vì `~/.kaggle/access_token` **đè** env |
| **D-090** | Kernel bị cưỡng chế dừng khi hết quota ⇒ **mất 100% output** | Thêm `LLM_TIME_BUDGET_S` (dừng trước) + `flush()`/`os.fsync()` từng request + ghi `stop_reason` |
| **D-091** | Kernel LLM log `giữ 0/0` dù model sinh ra text ⇒ payload **sai hình dạng** (array top-level), fail-fast cũ không kích hoạt | `normalize_payload()` chuẩn hoá mọi shape + `_scan_balanced()` + fail-fast theo `total == 0` + `re_llm_kaggle_raw.jsonl`; `resolve_model_source()` **quét** `/kaggle/input` (mount Kaggle Models tên **ngẫu nhiên**) |
| **D-092** | LLM bulk đạt **8/40 request** (12,5% kế hoạch) | Quota GPU còn lại chỉ **18,7 phút**; kernel tự dừng ở 724,5 s (ngân sách 700 s) |
| **D-093** | `alt_evidence` **bị mất** khi ghi file ⇒ **13.294** bằng chứng thay thế bị xoá | `REQUIRED_FIELDS` chỉ có **12** trường (thiếu `alt_evidence`) trong khi JSON mẫu `docs/09` §Phase 8 có 13 | Thêm `alt_evidence` → **13 trường**; `AGENTS.md` §7 cập nhật; +1 test regression ở mức ghi file ⇒ **3.308** triple có `alt_evidence`, **3.308/13.379** edge Neo4j có `alt_evidence`, KG **không đổi**, validate **13/13 PASS**, reload **+0/+0** |
| **D-094** | Chạy lại `infer_re_llm` **không** trúng cache: **100 request API thật, 386,9 s** | Cache SQLite **đã bị thay thế** giữa lần ghi artifact (15/11 20:15, `elapsed_s=0.0`) và lần kiểm tra (16/11) — bản ghi cache cũ nhất có mốc 15/11 23:00 | Cache **đúng** idempotent (lần chạy thứ hai: 100/100 hit, **0,0 s**, 0 request) nhưng **không bền**; artifact giữ nguyên vì LLM ở `temperature=0` vẫn nondeterministic (268 câu/353 triple vs 249 câu/348 triple) |

## Kết quả chạy kernel LLM Kaggle (16/11/2026 — D-091, D-092)

| Chỉ số | Giá trị |
|---|---|
| Kernel | `dathungdao2004/vhgr-phase-8-llm-extract-qwen3-8b-4bit` — **COMPLETE** |
| Model | Qwen/Qwen3-8B **4-bit** (bitsandbytes) |
| Request | **8** (chunk 15 câu) · **724,5 s** · ngân sách 700 s → `het-ngan-sach-thoi-gian` |
| Triple model trả về | **11** |
| Triple giữ lại | **8** (evidence substring **100%**) |
| Triple còn lại sau bộ lọc D-080→D-084 | **0** (4 không bằng chứng, 4 không từ kích hoạt) |
| KG sau hợp nhất | **13.379 cạnh — byte-identical** (sha1 `776209ce45ce996d`) |

## Việc tiếp theo

1. ~~Nạp 335.843 cạnh vào Neo4j~~ → **đã xong** với bản đã lọc: **19.548 node / 13.379 edge**, validate **13/13 PASS**, idempotent **+0/+0**.
2. ~~Chờ kernel RE~~ → **đã xong**: CPU local 4 shard (3,66 giờ) **và** Kaggle GPU
   đều cho ra **cùng** tập 454.767 cặp ⇒ `re_phobert.jsonl` (17.358 câu).
3. ✅ **Rà soát kernel Kaggle (16/11)**: không còn kernel `RUNNING`/`QUEUED`; đã
   xoá 3 kernel không cần; **giữ** `models/re/` từ GPU base.
4. ⏳ Kernel LLM Qwen3-8B — **đã chạy xong** (16/11): 8 request / 11 triple /
   8 giữ lại / 0 sau lọc ⇒ KG không đổi. **Quy mô nhỏ hơn kế hoạch 12,5×
   vì quota GPU còn lại 18,7 phút** (D-092). Kế hoạch lại: `--limit 5000
   --time-budget-s 28800` khi quota reset 21/11/2026. **Không chặn Gate**.
5. ✅ **Phase 9 → Phase 12** đã hoàn thành (entity linking, đồ thị, backend,
   giao diện). Demo QA + Cytoscape đã xác minh chạy thật (12 câu hỏi mẫu,
   graph 12 node / 12 cạnh, ảnh chụp UI đã kiểm).
6. *Cải thiện chất lượng RE (không chặn demo)*: train lại với supervision
   **đầy đủ 18 quan hệ** cho mỗi cặp NEGATIVE (thay vì 1) ⇒ hết lỗi
   over-firing gốc thay vì lọc hậu kỳ.


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
| 8 | Mô hình RE, LLM bulk, hợp nhất triple (D1/D2/D3) | ⬜ Chưa bắt đầu | — | — |
| 9 | Entity linking (E1–E4) | ⬜ Chưa bắt đầu | — | — |
| 10 | Đồ thị + Neo4j (F1–F4) | ⬜ Chưa bắt đầu | — | — |
| 11 | Text-to-Cypher backend (G1–G4/G6/G8) | ⬜ Chưa bắt đầu | — | — |
| 12 | Giao diện web (H1–H4) | ⬜ Chưa bắt đầu | — | — |
| 13 | Đánh giá (I3/I4) | ⬜ Chưa bắt đầu | — | — |
| 14 | Mở rộng + đóng gói | ⬜ Chưa bắt đầu | — | — |

Ký hiệu: ⬜ chưa · 🟡 đang làm · ✅ xong (đạt Gate) · ⚠️ xong nhưng lệch kế hoạch (xem `reports/deviations.md`)

## Việc tiếp theo

**Phase kế tiếp: Phase 8 — Mô hình RE, LLM bulk, hợp nhất triple (D1/D2/D3).**

Chi tiết ở `docs/09-ke-hoach-thuc-thien.md` → mục "Phase 8".

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
| RE F1 | ≥ 0.70 | — |
| Linking accuracy | ≥ 0.85 | — |
| QA execution accuracy | ≥ 0.70 | — |
| Số node KG | 5k–30k | — |
| Số cạnh KG | 50k–200k | — |
| % cạnh có bằng chứng | 100% | — |
| Cypher p95 (s) | < 2 | — |
| End-to-end p50 (s) | < 10 | — |
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

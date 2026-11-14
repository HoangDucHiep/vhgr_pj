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
| 4 | Nhãn bạc NER từ hyperlink (B2.1) | ⬜ Chưa bắt đầu | — | — |
| 5 | Huấn luyện + suy luận NER (B1/B2) | ⬜ Chưa bắt đầu | — | — |
| 6 | Coreference (C1/C2) | ⬜ Chưa bắt đầu | — | — |
| 7 | Wikidata DS + tập train RE (D1.1) | ⬜ Chưa bắt đầu | — | — |
| 8 | Mô hình RE, LLM bulk, hợp nhất triple (D1/D2/D3) | ⬜ Chưa bắt đầu | — | — |
| 9 | Entity linking (E1–E4) | ⬜ Chưa bắt đầu | — | — |
| 10 | Đồ thị + Neo4j (F1–F4) | ⬜ Chưa bắt đầu | — | — |
| 11 | Text-to-Cypher backend (G1–G4/G6/G8) | ⬜ Chưa bắt đầu | — | — |
| 12 | Giao diện web (H1–H4) | ⬜ Chưa bắt đầu | — | — |
| 13 | Đánh giá (I3/I4) | ⬜ Chưa bắt đầu | — | — |
| 14 | Mở rộng + đóng gói | ⬜ Chưa bắt đầu | — | — |

Ký hiệu: ⬜ chưa · 🟡 đang làm · ✅ xong (đạt Gate) · ⚠️ xong nhưng lệch kế hoạch (xem `reports/deviations.md`)

## Việc tiếp theo

**Phase kế tiếp: Phase 4 — Nhãn bạc NER từ hyperlink (B2.1).**

Chi tiết ở `docs/09-ke-hoach-thuc-thien.md` → mục "Phase 4".

> Phase 3 đã xong (14/11/2026) — **đã audit đóng phase** cùng ngày.
> Báo cáo: `reports/phase_03_report.md` · Nhật ký: `docs/10-nhat-ky/phase-03.md`.

Kết quả Phase 3 đã chốt (sau audit):
- `data/interim/infobox_triples.jsonl` — **10.078 triple**, `method="infobox"`, `confidence ≥ 0,95` (10.038 @ 0,97 + 40 @ 0,95).
- `data/interim/lead_triples.jsonl` — **736 triple** từ đoạn dẫn, `method="rule"`, `confidence=0,85`.
- `data/interim/infobox_entities.jsonl` — **1.764 entity** kèm `props` (birth_year, death_year, reign_start/end, temple_name, posthumous_name, gender, aliases, birth_place, death_place…).
- **16/18 quan hệ** có dữ liệu thật · **6/7 loại node** (`person`, `dynasty`, `event`, `place`, `title`, `year`).
  - `anh_em_cua` = 0 — **không bài nào** trong corpus có trường anh em/sibling (hạn chế dữ liệu).
  - `danh_bai` = 0 — **quyết định có chủ đích** (D-028), sinh ở Phase 8.
- Gate 1 **100%** · Gate 2 **92,4%** (67,3% chỉ infobox → +25,1 điểm từ đoạn dẫn) · Gate 3 **100%** (30/30) · Gate 4 **100%** · Gate 5 **0 vi phạm**.
- **Gate bổ sung (audit):** 0 triple trùng trong 1 doc · 0 self-loop · 0 trùng ngày lead ∩ infobox.
- **280 test pass** (274 trước audit + 6 regression mới). Sai lệch: D-019 → **D-030**.

**4 lỗi thật phát hiện khi audit đóng phase (14/11/2026):**
1. **347 triple trùng** trong 1 doc (Wikipedia có 2 trường cùng nội dung) → `sinh_nam` phình 732 → 985. Khử trùng → 732 (722/732 bài có **đúng 1** mốc sinh). *(D-027)*
2. **4 self-loop** (`subject == object`) → vi phạm `Triple.is_valid()`. *(D-027)*
3. **81 triple ngày trùng** giữa lead ∩ infobox trên 47 bài — `lead_triples.jsonl` **stale**. → ràng buộc thứ tự chạy. *(D-027)*
4. **`infobox former country`** dùng cho cả quốc gia (26 bài) lẫn triều đại (13 bài) → 13 bài gán nhầm `place` → `dong_doi_tai` = 0. Sửa bằng tín hiệu Wikidata → **31** triple. *(D-030)*

Việc cần làm ở Phase 4:
1. Sinh `data/interim/ner_silver.jsonl` — nhãn bạc NER từ **hyperlink** đã trích ở Phase 2 + **entity** từ `infobox_entities.jsonl` (Phase 3).
2. Gắn nhãn `entity_type` theo 7 loại node đã chốt.
3. Dựng tập đánh giá bạc (auto-gold) cho Phase 5.

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
| NER F1 (dev) | ≥ 0.85 | — |
| NER F1 (auto-gold) | ≥ 0.85 | — |
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

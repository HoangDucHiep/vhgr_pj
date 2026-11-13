# PROGRESS.md — Trạng thái triển khai

> Agent cập nhật file này **sau mỗi phase**. Đây là nơi agent mới biết "đang ở đâu".
> Cập nhật: cột "Ngày" = ngày hoàn thành, "Kết quả" = số liệu thực tế đo được.

## Tổng quan

| Phase | Tên | Trạng thái | Ngày | Kết quả chính |
|---|---|---|---|---|
| 0 | Bootstrap repo, cấu hình, hạ tầng | ✅ Xong | 13/11/2026 | 56 test pass · `/api/health` ok · Neo4j 5.26.32 · READ_ACCESS chặn ghi ✅ · build TS 0 lỗi |
| 1 | Tải dump, lọc bài (A1) | ✅ Xong | 14/11/2026 | **2.441 bài** trong `documents.jsonl` · QID 97,3% · `person` 1.061/`battle` 202/`place` 150/`dynasty` 16 · RAM peak 1,16 GB |
| 2 | Làm sạch, tách câu, hyperlink (A2/A3/A5) | 🟡 Code xong, chưa chạy | — | `clean_text.py` + `split_sentences.py` + 18 test pass — chờ Phase 1 xong mới chạy pipeline |
| 3 | Parse infobox, chuẩn hóa ngày (A4) | ⬜ Chưa bắt đầu | — | — |
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

**Phase kế tiếp: Phase 2 — Làm sạch wikitext, tách câu/đoạn, trích hyperlink.**

Chi tiết ở `docs/09-ke-hoach-thuc-thien.md` → mục "Phase 2".

> Phase 1 đã xong (13/11/2026) — báo cáo: `reports/phase_01_report.md`.

Kết quả Phase 1 đã chốt:
- `data/interim/documents.jsonl` — **2.441 bài** (khoảng mục tiêu 2.000–5.000).
- Phân bố `keep_reason`: `wikidata` 930 · `category` 933 · `infobox` 302 · `seed_expansion` 276.
- Phân bố `infobox_type`: `person` 1.061 · `battle` 202 · `place` 150 · `dynasty` 16 · `event` 11 · `none` 1.001.
- QID coverage **97,3%**; RAM peak **≈ 1,16 GB**; chạy 31 phút.
- Có tầng **T5** chốt phạm vi lịch sử Việt Nam (xem `reports/deviations.md` D-012) — lượt chạy đầu giữ 3.113 bài
  nhưng ~35% rơi ra ngoài phạm vi (Trận Stalingrad, Nhà Ptolemaios…).

Việc cần làm ở Phase 2:
1. `python -m src.preprocess.clean_text --config configs/default.yaml` — tách infobox ra `infobox_raw`,
   xoá template/ref/File/Thể loại/bảng/HTML, thay wikilink bằng anchor **kèm offset chính xác**.
2. `python -m src.preprocess.split_sentences --config configs/default.yaml` — tách đoạn (theo `\n\n`) và
   câu (`pysbd` `Language.MULTI`), sinh `sentence_id` = `s<page_id>_<para_idx>_<sent_idx>`.
3. Chạy `pytest -q tests/test_clean_text.py tests/test_sentence_split.py` (18 test — đã xanh).
4. Chạy `python scripts/stats_text.py` → đối chiếu Gate:
   0 ký tự wiki còn sót · ≥95% câu kết thúc bằng dấu câu · 100% offset hợp lệ · ≥95% link được giữ.
5. Ghi `reports/phase_02_report.md` + cập nhật file này.

**Vận hành đã kiểm chứng** (xem `docs/CONTEXT.md` §2.7) — dùng luôn cho Phase 1:
- Đọc dump bằng `lxml.etree.iterparse` (không dùng `mwparser` — PyPI chỉ có bản `0.1`).
- Tách câu bằng `pysbd` (`underthesea` không bắt buộc — D-005).
- SPARQL: **không** dùng `P463`/`P361` (trả 0) — dùng `P31=Q5` + `P27=Q881` + `P569` + `P22`
  (trả 213 người, đủ 9 triều đại).
- Neo4j: bảo vệ bằng session `READ_ACCESS` (Community không có RBAC — D-002).

## Nhật ký

| Ngày | Phase | Nội dung | Ghi chú |
|---|---|---|---|
| 10/11/2026 | — | Hoàn thành bộ đặc tả `docs/00`–`docs/09` | Đã verify QID Wikidata, quota LLM, môi trường máy |
| 10/11/2026 | — | Tạo bộ file vibe-coding: `AGENTS.md`, `docs/CONTEXT.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/GLOSSARY.md`, rules, skills | |
| 10/11/2026 | — | Kiểm chứng hạ tầng (Neo4j Community không RBAC, `mwparser` không có trên PyPI, dump viwiki không có `redirects.xml.bz2`) | Ghi vào `docs/CONTEXT.md` §2.7, cập nhật D-008 và `cypher-safety.mdc` |
| 10/11/2026 | — | Thu hồi code triển khai sớm (`src/`, `backend/`, `frontend/`, `tests/`, `scripts/`, `configs/`, `.venv`) — giữ nguyên bộ setup vibe-coding | Theo yêu cầu: chỉ setup, chưa triển khai |
| 10/11/2026 | — | Rà soát chất lượng bộ setup: sửa 10 link/anchor hỏng trong `docs/00` và `docs/09`, bổ sung mục `docs/09` + `annotation-guidelines` vào bảng cấu trúc tài liệu | Kiểm tra tự động: 0 link hỏng, 0 anchor hỏng, 0 tiếng Trung, đủ 9 artifact theo `AGENTS.md` §7 |
| 13/11/2026 | — | Sửa bộ QID sai trong `docs/05` §3.1 + commit nền tảng vibe-coding setup | Dùng bộ 9 QID đã verify trong `docs/CONTEXT.md` §2.6; thay ví dụ SPARQL `P463`/`P361` (trả 0) bằng `P31=Q5`+`P27=Q881`+`P569`+`P22` |
| 13–14/11/2026 | 1 | Tải dump viwiki `20261101` + lọc 5 tầng T0–T5 | **2.441 bài** trong `data/interim/documents.jsonl` · QID 97,3% · `person` 1.061/`battle` 202/`place` 150/`dynasty` 16 · RAM peak 1,16 GB · 31 phút · 107 test pass. Sửa 4 lỗi: cây category khóa theo `lt_id` (D-010), khớp tiền tố loại infobox (D-009), T2 cần category Việt Nam (D-008), thêm T5 chốt phạm vi (D-012). Báo cáo: `reports/phase_01_report.md` |
| 13/11/2026 | 0 | Bootstrap repo, cấu hình, hạ tầng | 56 test pass · Neo4j 5.26.32 ở `:7474` · `/api/health` → `ok`/`neo4j: up` · `READ_ACCESS` chặn ghi ở cấp server ✅ · `npm run build` 0 lỗi TS. Báo cáo: `reports/phase_00_report.md` |

## Chỉ số đo được (điền sau mỗi phase có số liệu)

| Chỉ số | Mục tiêu | Hiện tại |
|---|---|---|
| Số bài trong corpus | 2.000–5.000 | **2.441** (Phase 1) |
| Số câu | 150k–400k | — |
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
| `docs/DECISIONS.md` | Nhật ký quyết định kiến trúc |
| `docs/GLOSSARY.md` | Thuật ngữ |
| `reports/deviations.md` | Sai lệch so với kế hoạch |
| `reports/phase_XX_report.md` | Báo cáo từng phase |

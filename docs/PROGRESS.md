# PROGRESS.md — Trạng thái triển khai

> Agent cập nhật file này **sau mỗi phase**. Đây là nơi agent mới biết "đang ở đâu".
> Cập nhật: cột "Ngày" = ngày hoàn thành, "Kết quả" = số liệu thực tế đo được.

## Tổng quan

| Phase | Tên | Trạng thái | Ngày | Kết quả chính |
|---|---|---|---|---|
| 0 | Bootstrap repo, cấu hình, hạ tầng | ✅ Xong | 13/11/2026 | 56 test pass · `/api/health` ok · Neo4j 5.26.32 · READ_ACCESS chặn ghi ✅ · build TS 0 lỗi |
| 1 | Tải dump, lọc bài (A1) | ⬜ Chưa bắt đầu | — | — |
| 2 | Làm sạch, tách câu, hyperlink (A2/A3/A5) | ⬜ Chưa bắt đầu | — | — |
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

**Phase kế tiếp: Phase 1 — Tải dump viwiki `20261101` + lọc 2.000–5.000 bài lịch sử.**

Chi tiết ở `docs/09-ke-hoach-thuc-thien.md` → mục "Phase 1".

> Phase 0 đã xong (13/11/2026). Cây thư mục `src/`, `backend/`, `frontend/`, `scripts/`,
> `tests/`, `configs/` **đã được tạo** và kiểm thử xanh.

Việc cần làm ở Phase 1:
1. `scripts/download_dump.py` — tải `pages-articles.xml.bz2` (1111 MB) + `pages-meta-current.xml.bz2` (1442 MB),
   ghi `data/raw/manifest.json` (tên file, kích thước, sha1, ngày tải). Hỗ trợ `--resume`.
   **Lưu ý:** viwiki **không có** `redirects.xml.bz2` riêng — redirect nằm trong `pages-articles` (thẻ `<redirect>`).
2. `src/preprocess/filter_articles.py` — parse `pages-articles.xml.bz2` bằng `lxml.etree.iterparse`
   (streaming, không nạp toàn bộ vào RAM), bỏ namespace ≠ 0, bỏ redirect.
3. `src/preprocess/wikidata_map.py` — đọc `pages-meta-current.xml.bz2`, lấy `page_props/wikibase_item`
   → `data/interim/pageid_to_qid.json`.
4. Bộ lọc 5 tín hiệu: **T0 Wikidata** (SPARQL → QID → sitelink viwiki → seed) ·
   **T1 category** (tên đã kiểm chứng: `Vua Việt Nam` 57, `Địa danh Việt Nam` 90, `Người Việt Nam` 68;
   mở rộng đệ quy `<text>` trong `pages-meta-current`, độ sâu ≤ 3) ·
   **T2 infobox** (whitelist loại + ≥ 2 trường lịch sử) · **T3 BFS hyperlink** (từ seed T0, sâu ≤ 2) ·
   **T4 loại trừ** (`Danh sách`, `Bảng`, `Wikipedia:`, `Dự án Wikimedia`...).
5. Ghi `data/interim/documents.jsonl` + `data/interim/filter_stats.json`.
6. Chạy lệnh kiểm thử trong Phase 1 → đạt Gate → ghi `reports/phase_01_report.md`.

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
| 13/11/2026 | 0 | Bootstrap repo, cấu hình, hạ tầng | 56 test pass · Neo4j 5.26.32 ở `:7474` · `/api/health` → `ok`/`neo4j: up` · `READ_ACCESS` chặn ghi ở cấp server ✅ · `npm run build` 0 lỗi TS. Báo cáo: `reports/phase_00_report.md` |

## Chỉ số đo được (điền sau mỗi phase có số liệu)

| Chỉ số | Mục tiêu | Hiện tại |
|---|---|---|
| Số bài trong corpus | 2.000–5.000 | — |
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

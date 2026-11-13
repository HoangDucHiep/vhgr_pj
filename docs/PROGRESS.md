# PROGRESS.md — Trạng thái triển khai

> Agent cập nhật file này **sau mỗi phase**. Đây là nơi agent mới biết "đang ở đâu".
> Cập nhật: cột "Ngày" = ngày hoàn thành, "Kết quả" = số liệu thực tế đo được.

## Tổng quan

| Phase | Tên | Trạng thái | Ngày | Kết quả chính |
|---|---|---|---|---|
| 0 | Bootstrap repo, cấu hình, hạ tầng | ⬜ Chưa bắt đầu | — | — |
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

**Phase kế tiếp: Phase 0 — Bootstrap repo, cấu hình, hạ tầng.**

Chi tiết ở `docs/09-ke-hoach-thuc-thien.md` → mục "Phase 0".

> Trạng thái hiện tại: **chỉ mới hoàn thành phần setup vibe-coding** (spec + rules + skills + context docs).
> Cây thư mục `src/`, `backend/`, `frontend/`, `scripts/`, `tests/`, `configs/` **chưa được tạo** — đó là nội dung Phase 0.

Việc cần làm ở Phase 0 (theo Output contract):
1. Tạo cây thư mục theo `AGENTS.md` §3.
2. `src/common/`: `__init__.py`, `config.py`, `logger.py`, `seed.py`, `normalize.py`, `schemas.py`, `ids.py`, `text_utils.py`.
3. `configs/`: `default.yaml`, `pipeline.yaml`, `llm.yaml`, `neo4j.yaml`.
4. `requirements.txt` (đúng danh sách trong Phase 0), `docker-compose.yml` (service `neo4j` 5-community, `backend`, `frontend`).
5. `backend/app/main.py` với `/api/health` → `{"status":"ok","version":"0.1.0","neo4j":"up|down"}` và `/api/stats` giả lập; kết nối Neo4j **lazy**.
6. `frontend/`: Vite + React + TS, trang chủ có nút gọi `/api/health`.
7. `tests/test_health.py`.
8. Chạy lệnh kiểm thử trong Phase 0 → đạt Gate → ghi `reports/phase_00_report.md`.
9. Nếu `underthesea` lỗi trên Python 3.12 → dùng `pysbd` + regex tách đoạn, ghi `reports/deviations.md`.

**Vận hành đã kiểm chứng** (xem `docs/CONTEXT.md` §2.7) — dùng luôn cho Phase 0:
- Neo4j Community **không có RBAC** → bảo vệ cấp DB bằng session `READ_ACCESS`, không dựa vào role.
- Đọc dump bằng `lxml.etree.iterparse` (không dùng `mwparser` — PyPI chỉ có bản `0.1`).
- Tách câu bằng `pysbd` (`underthesea` không bắt buộc).

Lưu ý: `.env.example` và `.gitignore` **đã tạo** trong lần setup vibe-coding — chỉ cần đối chiếu với Phase 0.

## Nhật ký

| Ngày | Phase | Nội dung | Ghi chú |
|---|---|---|---|
| 10/11/2026 | — | Hoàn thành bộ đặc tả `docs/00`–`docs/09` | Đã verify QID Wikidata, quota LLM, môi trường máy |
| 10/11/2026 | — | Tạo bộ file vibe-coding: `AGENTS.md`, `docs/CONTEXT.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, `docs/GLOSSARY.md`, rules, skills | |
| 10/11/2026 | — | Kiểm chứng hạ tầng (Neo4j Community không RBAC, `mwparser` không có trên PyPI, dump viwiki không có `redirects.xml.bz2`) | Ghi vào `docs/CONTEXT.md` §2.7, cập nhật D-008 và `cypher-safety.mdc` |
| 10/11/2026 | — | Thu hồi code triển khai sớm (`src/`, `backend/`, `frontend/`, `tests/`, `scripts/`, `configs/`, `.venv`) — giữ nguyên bộ setup vibe-coding | Theo yêu cầu: chỉ setup, chưa triển khai |
| 10/11/2026 | — | Rà soát chất lượng bộ setup: sửa 10 link/anchor hỏng trong `docs/00` và `docs/09`, bổ sung mục `docs/09` + `annotation-guidelines` vào bảng cấu trúc tài liệu | Kiểm tra tự động: 0 link hỏng, 0 anchor hỏng, 0 tiếng Trung, đủ 9 artifact theo `AGENTS.md` §7 |

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

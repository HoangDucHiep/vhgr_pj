# Deviations — Nhật ký sai lệch so với kế hoạch

> Ghi **mọi** sai lệch so với `docs/09-ke-hoach-thuc-thien.md`: đổi công nghệ, đổi contract, đổi phạm vi, không đạt Gate, dùng fallback.
> Mục tiêu: báo cáo cuối cùng trung thực, không bịa số liệu.

## Format

```markdown
## D-001 — <mô tả ngắn>
- Ngày: YYYY-MM-DD
- Phase: <N>
- Loại: công nghệ | contract | phạm vi | tiêu chí | kỹ thuật
- Kế hoạch: <một câu>
- Thực tế: <một câu>
- Lý do: <một câu>
- Ảnh hưởng: <một câu>
- Xử lý: <một câu>
- Cập nhật file: <danh sách>
```

## Nhật ký

## D-001 — Agent triển khai sớm vượt phạm vi "setup vibe-coding"
- Ngày: 2026-11-10
- Phase: — (ngoài phase nào)
- Loại: phạm vi
- Kế hoạch: Chỉ tạo bộ file setup vibecode (`AGENTS.md`, rules, skills, docs context).
- Thực tế: Sau câu lệnh `/goal dont stop before you done the plan`, agent đọc nó là "làm hết 15 phase" và bắt đầu viết code Phase 0/1, tạo venv, chạy Neo4j Docker, tải dump Wikipedia (2GB+).
- Lý do: Diễn giải `/goal` thành "hoàn thành toàn bộ kế hoạch triển khai" thay vì "hoàn thành phần setup được giao".
- Ảnh hưởng: Tốn tài nguyên máy (download 2GB+, container Neo4j) và tạo ra artifact không được yêu cầu. Đã xóa toàn bộ.
- Xử lý: Thu hồi toàn bộ code triển khai sớm (`src/`, `backend/`, `frontend/`, `tests/`, `scripts/`, `configs/`, `requirements.txt`, `docker-compose.yml`, `.venv`, `data/`). Dừng container Neo4j. Bổ sung ghi chú phạm vi vào `AGENTS.md` §4.
- Cập nhật file: `AGENTS.md`, `docs/PROGRESS.md`

## D-002 — Neo4j Community không hỗ trợ RBAC (read-only user theo role)
- Ngày: 2026-11-10
- Phase: 10 (ghi nhận sớm từ kiểm chứng hạ tầng)
- Loại: kỹ thuật
- Kế hoạch: Tạo user `reader` với role built-in `reader` của Neo4j 5 → DB tự chặn ghi.
- Thực tế: `CREATE USER … SET ROLE reader` và `GRANT MATCH ON GRAPH … TO reader` đều lỗi cú pháp trên Neo4j 5 Community. User `reader` tạo được nhưng **vẫn ghi được** vào DB.
- Lý do: RBAC / fine-grained access control chỉ có trong Neo4j Enterprise.
- Ảnh hưởng: Cơ chế bảo vệ cấp DB theo kế hoạch không tồn tại.
- Xử lý: Chuyển sang cơ chế **session READ access mode** (`default_access_mode=READ_ACCESS`) — server từ chối mọi lệnh ghi (`Neo.ClientError.Statement.AccessMode`), đã kiểm chứng kể cả với superuser. Validator tĩnh ở tầng app giữ nguyên vai trò lớp phòng thủ đầu tiên.
- Cập nhật file: `.cursor/rules/cypher-safety.mdc`, `docs/DECISIONS.md` (D-008), `docs/CONTEXT.md` §2.7, `docs/09-ke-hoach-thuc-thien.md` (Phase 10), `AGENTS.md` §5.2

## D-003 — Thư viện `mwparser` không có bản dùng được trên PyPI
- Ngày: 2026-11-10
- Phase: 1 (ghi nhận sớm từ kiểm chứng hạ tầng)
- Loại: công nghệ
- Kế hoạch: Dùng `mwparser>=0.6.2` để parse wikitext.
- Thực tế: PyPI chỉ có bản `0.1`; bản `0.6.2` không được publish.
- Lý do: Package không còn được duy trì trên PyPI.
- Ảnh hưởng: Không cài được dependency theo kế hoạch.
- Xử lý: Dùng `lxml.etree.iterparse` để parse dump XML (streaming, nhanh hơn cho file 2GB+) + regex/wikitext-cleanup cho phần text.
- Cập nhật file: `docs/CONTEXT.md` §2.7, `docs/PROGRESS.md`

## D-004 — Bỏ `mwparser` khỏi `requirements.txt` (Phase 0)
- Ngày: 2026-11-13
- Phase: 0
- Loại: công nghệ
- Kế hoạch: Output contract Phase 0 liệt kê `mwparser` trong `requirements.txt`.
- Thực tế: Dùng `lxml` + `wikitextparser` + `pysbd`; không cài `mwparser`.
- Lý do: PyPI chỉ có bản `mwparser` 0.1 (bản 0.6.2 chưa publish) — đã ghi nhận ở D-003 và `docs/CONTEXT.md` §2.7.
- Ảnh hưởng: Không ảnh hưởng contract; `requirements.txt` của Phase 1+ cũng dùng bộ thư viện này.
- Xử lý: Cập nhật `requirements.txt` và ghi rõ lý do trong file.
- Cập nhật file: `requirements.txt`, `reports/phase_00_report.md`

## D-005 — Bỏ `underthesea`, dùng `pysbd` + regex tách đoạn (Phase 0)
- Ngày: 2026-11-13
- Phase: 0
- Loại: công nghệ
- Kế hoạch: Output contract Phase 0 liệt kê `underthesea` trong `requirements.txt`.
- Thực tế: Không cài `underthesea`; dùng `pysbd` để tách câu và regex `\n\s*\n` để tách đoạn.
- Lý do: Đúng mục "Lùi" của Phase 0 trong `docs/09-ke-hoach-thuc-thien.md` — `underthesea` không ổn định trên Python 3.12.
- Ảnh hưởng: Chất lượng tách câu có thể thấp hơn `underthesea`; cần đo ở Gate Phase 2 (≥95% câu kết thúc bằng dấu câu).
- Xử lý: Thêm `split_paragraphs` (regex) vào `src/common/text_utils.py`; ghi fallback vào `docs/CONTEXT.md` §2.7.
- Cập nhật file: `requirements.txt`, `src/common/text_utils.py`, `reports/phase_00_report.md`

## D-006 — `frontend/tsconfig.json` không dùng project reference (Phase 0)
- Ngày: 2026-11-13
- Phase: 0
- Loại: kỹ thuật
- Kế hoạch: Vite React TS template mặc định dùng `tsconfig.json` + `tsconfig.node.json` với `references`.
- Thực tế: Gộp `vite.config.ts` vào cùng `include` của `tsconfig.json`, bỏ `tsconfig.node.json`.
- Lý do: `composite: true` + `noEmit: true` xung đột → TypeScript báo lỗi TS6310 ("Referenced project may not disable emit").
- Ảnh hưởng: Không ảnh hưởng chức năng; `npm run build` vẫn chạy `tsc --noEmit` trên toàn bộ mã nguồn.
- Xử lý: Cài `@types/node` và dùng `loadEnv` từ Vite thay cho `process.env` trực tiếp trong `vite.config.ts`.
- Cập nhật file: `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/package.json`

## D-007 — Không quy đổi ngày âm lịch sang dương lịch (Phase 0)
- Ngày: 2026-11-13
- Phase: 0 (quyết định thiết kế trước khi làm Phase 3)
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 0 yêu cầu `src/common/normalize.py` có hàm chuẩn hóa ngày.
- Thực tế: `src/common/normalize.py` chỉ *nhận diện* ngày âm lịch (`is_lunar_date`) và trả `precision` cho ngày dương; **không** quy đổi âm → dương.
- Lý do: Bảng quy đổi âm lịch thủ công dễ sai và phụ thuộc múi giờ; quy đổi sai sẽ vi phạm nguyên tắc "không bịa" của dự án (quy tắc 3 trong `AGENTS.md` §5).
- Ảnh hưởng: Phase 3 chỉ gắn cờ `is_lunar` trong bằng chứng thay vì quy ra ngày dương tuyệt đối. Nếu cần ngày dương tuyệt đối cho ngày âm thì phải dùng thư viện chuyên dụng ở Phase 3 (có thể ghi thêm deviation).
- Xử lý: Ghi chú rõ trong docstring của `src/common/normalize.py`.
- Cập nhật file: `src/common/normalize.py`, `reports/phase_00_report.md`

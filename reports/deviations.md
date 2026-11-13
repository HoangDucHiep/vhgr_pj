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

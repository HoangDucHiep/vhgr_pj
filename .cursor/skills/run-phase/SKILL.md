---
name: run-phase
description: Thực hiện một phase của pipeline dự án Knowledge Graph lịch sử Việt Nam từ docs/09-ke-hoach-thuc-thien.md, gồm đọc contract, code, chạy lệnh kiểm thử, kiểm tra Gate, ghi báo cáo phase và ghi nhật ký triển khai chi tiết. Dùng khi người dùng yêu cầu "làm phase N", "tiếp tục phase", "chạy phase tiếp theo", hoặc muốn agent triển khai một bước của pipeline.
disable-model-invocation: true
---

# Run Phase

Thực hiện **đúng một phase** của pipeline theo đặc tả `docs/09-ke hoach-thuc-thien.md`.

## Bước 1 — Thu thập ngữ cảnh

Đọc theo thứ tự (không bỏ qua):

1. `AGENTS.md` — quy tắc dự án.
2. `docs/CONTEXT.md` — quyết định đã chốt, QID, model.
3. `docs/PROGRESS.md` — phase hiện tại + việc tiếp theo.
4. `docs/09-ke-hoach-thuc-thien.md` → mục phase cần làm (tìm theo `## Phase N`).
5. `docs/10-nhat-ky/phase-<số phase trước>.md` — nhật ký phase trước: quyết định đã chốt, thang số liệu, lỗi đã gặp. **Bỏ qua nếu chưa có.**
6. `.cursor/rules/` — các rule liên quan (luôn `data-contracts`, `workflow-phases`; thêm `python-standards` / `cypher-safety` / `llm-usage` / `frontend` tuỳ phase).

## Bước 2 — Xác nhận Input contract

Chạy lệnh kiểm tra input mà phase nêu (ví dụ: file artifact tồn tại, đủ số lượng record). **Nếu input chưa đủ → dừng và báo cáo**, không tự ý sửa phase trước.

## Bước 3 — Viết code

- Bám đúng Output contract: tên trường, format, đường dẫn.
- Dùng hằng số chung từ `src/common/schemas.py` (`RELATION_TYPES`, `SYMMETRIC_RELATIONS`, `ENTITY_TYPES`, `NER_LABELS`, `EXTRACTION_METHODS`).
- Dùng `make_entity_id()` / `make_year_id()` từ `src/common/ids.py` — không tự viết chuỗi ID.
- Cấu hình đọc từ `configs/*.yaml` — không hard-code đường dẫn, ngưỡng, model name.
- Logging qua `get_logger(__name__)`, không `print()` trong `src/`.
- Viết kèm test trong `tests/` cho phần logic mới.

## Bước 4 — Tự kiểm thử

Chạy **đúng các lệnh** trong mục "Lệnh kiểm thử" của phase, theo thứ tự. Dừng lại nếu một lệnh assert fail.

Bổ sung:
```bash
pytest -q tests/
```

Nếu có lỗi → sửa code (không sửa lệnh kiểm thử để "cho qua"). Chỉ được nới tiêu chí khi nằm trong mục "Lùi" của phase.

## Bước 5 — Kiểm tra Gate

Đối chiếu từng mục checklist Gate của phase → đánh dấu ✅/❌.

Nếu có mục ❌ → đọc mục "Lùi", thử fallback, tối đa 2 lần. Vẫn ❌ → ghi `reports/deviations.md`, hạ tiêu chí có kiểm soát, **không sửa số liệu**.

## Bước 6 — Báo cáo

Tạo `reports/phase_XX_report.md` theo format:

```markdown
# Phase XX — <tên>

- Ngày: YYYY-MM-DD
- Trạng thái: ✅ đạt Gate / ⚠️ lệch / ❌ không đạt

## Đã làm
## Lệnh đã chạy
## Số liệu đo được (bảng Kỳ vọng vs Thực tế)
## Gate (checklist)
## Sai lệch so với kế hoạch
## Việc tiếp theo
```

## Bước 7 — Ghi nhật ký triển khai (bắt buộc)

Tạo `docs/10-nhat-ky/phase_XX.md` theo mẫu ở `docs/10-nhat-ky/README.md`.
Đây là **nguyên liệu cho báo cáo, số liệu và slide** — không phải bản sao của `reports/phase_XX_report.md`.

9 mục bắt buộc: bối cảnh → phương án đã cân nhắc → quyết định đã chốt → **thang số liệu so sánh**
→ số liệu đo được (Gate) → lỗi gặp phải & cách xử lý → bài học → ý tưởng cho slide → việc tiếp theo.

Nếu có nhiều phương án đã đo được số liệu → tạo thêm
`docs/10-nhat-ky/so-lieu/phase-XX-<tên>.json` (UTF-8, JSON hợp lệ, có `_meta` mô tả nguồn).

Nguyên tắc:
- Mọi con số phải truy được về nguồn (lệnh đã chạy → output, hoặc trỏ tới `so-lieu/*.json`).
- Số liệu so sánh > số liệu đơn lẻ — luôn có bảng nhiều phương án khi có lựa chọn.
- Sai lệch: nêu số thực tế, **không** sửa số liệu để "cho xanh".
- Ngôn ngữ: tiếng Việt hoặc tiếng Anh, tuyệt đối không dùng tiếng Trung.

## Bước 8 — Cập nhật PROGRESS

Sửa `docs/PROGRESS.md`:
- Dòng phase tương ứng: trạng thái, ngày, kết quả chính.
- Bảng "Chỉ số đo được": điền số thực tế.
- Mục "Việc tiếp theo": phase kế tiếp + các bước cụ thể.
- Bảng "Nhật ký": thêm 1 dòng.
- Bảng "Tài liệu liên quan": dẫn tới `docs/10-nhat-ky/` (đã có sẵn — không cần sửa).

## Quy tắc quan trọng

- **1 phase = 1 lượt.** Xong thì dừng, báo cáo, chờ yêu cầu tiếp.
- **Không được bỏ qua Bước 7 (nhật ký triển khai).** `reports/phase_XX_report.md` trả lời
  *"làm gì, đạt Gate chưa"*; `docs/10-nhat-ky/phase_XX.md` trả lời *"vì sao chọn cách đó,
  số liệu so sánh ra sao, sai ở đâu, bài học gì"*. Thiếu một trong hai là phase chưa xong.
- Không sửa Output contract của phase trước đã đóng.
- Không tự ý đổi phạm vi dữ liệu, tập quan hệ, schema → hỏi người dùng.
- Phase có đánh dấu `[KAGGLE-GPU]` → không chạy local; hướng dẫn cách chạy trên Kaggle (notebook tương ứng trong `notebooks/kaggle/`) và dừng lại, chờ artifact được tải về.

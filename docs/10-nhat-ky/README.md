# 10 — Nhật ký triển khai (chi tiết theo phase)

> Thư mục này là **bản ghi chép sâu** cho mục đích làm **báo cáo, số liệu và slide**.
> `reports/phase_XX_report.md` trả lời *"làm gì, đạt Gate chưa"*.
> `docs/10-nhat-ky/phase-XX.md` trả lời *"vì sao chọn cách đó, số liệu so sánh ra sao, sai ở đâu,
> bài học gì, kết luận lấy vào slide là gì"*.

## Nguyên tắc

1. **Mọi con số phải truy được về nguồn.** Mỗi số liệu trong nhật ký ghi rõ:
   lệnh đã chạy → output thực tế, hoặc trỏ tới `so-lieu/*.json`.
2. **Số liệu so sánh > số liệu đơn lẻ.** Khi có nhiều phương án, luôn ghi bảng so sánh
   (phương án → kết quả → lý do chọn). Đây là nguyên liệu chính cho slide.
3. **Sai lệch phải công khai.** Không sửa số liệu để "cho xanh"; nếu lệch thì ghi cả
   số thực tế và lý do (xem `reports/deviations.md`).
4. **Không dùng tiếng Trung** trong toàn bộ nội dung của thư mục này.

## Cấu trúc

```
docs/10-nhat-ky/
├── README.md              # file này — chỉ mục + hướng dẫn dùng
├── phase-00.md            # nhật ký chi tiết Phase 0
├── phase-01.md            # nhật ký chi tiết Phase 1
└── so-lieu/               # số liệu máy đọc được (JSON) để dựng biểu đồ/slide
    ├── phase-00-mo-truong.json
    └── phase-01-bang-do-sanh.json
```

## Danh mục

| File | Phase | Ngày | Nội dung chính |
|---|---|---|---|
| [`phase-00.md`](phase-00.md) | 0 — Bootstrap hạ tầng | 13/11/2026 | Quyết định lớp bảo vệ Neo4j chỉ-đọc · thay thế thư viện · lựa chọn cấu hình TS |
| [`phase-01.md`](phase-01.md) | 1 — Lọc corpus 5 tầng T0–T5 | 13–14/11/2026 | Thang số liệu lọc nhiễu · vì sao thêm T5 · lỗi 5 lỗi & cách sửa |
| [`so-lieu/phase-00-mo-truong.json`](so-lieu/phase-00-mo-truong.json) | 0 | — | Phiên bản thư viện, cấu hình hạ tầng, so sánh phương án bảo vệ DB |
| [`so-lieu/phase-01-bang-do-sanh.json`](so-lieu/phase-01-bang-do-sanh.json) | 1 | — | Thống kê corpus trước/sau T5 theo mọi chiều |

## Cách dùng cho báo cáo / slide

| Nhu cầu | Nguồn |
|---|---|
| Slide "hạ tầng & quyết định kiến trúc" | `phase-00.md` § *Quyết định* + `so-lieu/phase-00-mo-truong.json` |
| Slide "vì sao lọc như vậy" | `phase-01.md` § *Thang số liệu* |
| Slide "chất lượng corpus" | `phase-01.md` § *Số liệu đo được* + `so-lieu/phase-01-bang-do-sanh.json` |
| Slide "bài học kinh nghiệm" | `phase-01.md` § *Bài học* |
| Slide "sai lệch so với kế hoạch" | `reports/deviations.md` (D-004 → D-014) |
| Số liệu tổng quan toàn dự án | `docs/PROGRESS.md` § *Chỉ số đo được* |

## Mẫu chuẩn cho phase sau

Khi hoàn thành một phase, tạo `docs/10-nhat-ky/phase-XX.md` theo đúng bộ mục sau.
Nếu có số liệu so sánh nhiều phương án → tạo thêm `so-lieu/phase-XX-<tên>.json`.

```markdown
# Phase XX — <tên phase>

- Ngày: YYYY-MM-DD
- Trạng thái: ✅ đạt Gate / ⚠️ đạt nhưng lệch / ❌ không đạt
- Báo cáo Gate: `reports/phase_XX_report.md`
- Sai lệch: `reports/deviations.md` (D-0XX)

## 1. Bối cảnh và vấn đề cần giải
<!-- Vì sao phase này tồn tại, đầu vào là gì, rủi ro/ràng buộc gì -->

## 2. Phương án đã cân nhắc
| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|

## 3. Quyết định đã chốt
<!-- D-0XX: quyết định + lý do + ảnh hưởng + file đã cập nhật -->

## 4. Thang số liệu so sánh
<!-- Bảng so sánh các phương án, hoặc so sánh trước/sau -->

## 5. Số liệu đo được (Gate)
| Chỉ số | Kỳ vọng | Thực tế | Đạt? |

## 6. Lỗi gặp phải và cách xử lý
| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |

## 7. Bài học kinh nghiệm
<!-- 3–5 điểm rút ra, viết để dùng được cho slide -->

## 8. Ý tưởng cho slide
<!-- 3–5 gạch đầu dòng + số liệu kèm theo để chèn thẳng vào slide -->

## 9. Việc tiếp theo
```

## Quy tắc cập nhật

| Khi | Cập nhật |
|---|---|
| Hoàn thành 1 phase | Tạo `phase-XX.md` + (nếu có so sánh) `so-lieu/phase-XX-*.json` |
| Có sai lệch so với kế hoạch | Ghi `reports/deviations.md` **và** dẫn chiếu trong `phase-XX.md` §3 |
| Có quyết định kỹ thuật mới | Ghi `docs/DECISIONS.md` **và** dẫn chiếu trong `phase-XX.md` §3 |
| Đổi định dạng ID / trường bắt buộc | Cập nhật cả `AGENTS.md` §6–7, `.cursor/rules/data-contracts.mdc`, `docs/CONTEXT.md` |
| Số liệu tổng quan đổi | Cập nhật `docs/PROGRESS.md` § *Chỉ số đo được* |

# Reports — Kết quả và báo cáo

## Cấu trúc

| Kiểu | Vị trí | Khi nào tạo |
|---|---|---|
| Báo cáo phase | `reports/phase_XX_report.md` | sau **mỗi** phase |
| Sai lệch | `reports/deviations.md` | khi lệch kế hoạch |
| Kết quả đánh giá | `reports/eval_<task>.md` + `.json` | Phase 13 |
| Thống kê KG | `reports/graph_stats.json` | Phase 10, 14 |
| Phân tích lỗi | `reports/error_analysis.md` | Phase 13 |

## Quy tắc

1. **Số liệu phải là số đo thật** — không ước lượng, không làm tròn đẹp để "đạt mục tiêu".
2. Mỗi số liệu kèm **lệnh đã dùng để đo** để người đánh giá tái lập được.
3. Nếu không đạt Gate → ghi rõ giá trị thực tế và lý do, đồng thời thêm mục vào `deviations.md`.
4. Ảnh chụp màn hình (UI) lưu vào `reports/screenshots/`.
5. File `.json` sinh ra từ script được gitignore — nhưng phần tóm tắt `.md` phải commit.

## Mẫu báo cáo phase

Xem mẫu đầy đủ trong `.cursor/rules/workflow-phases.mdc` §"Định dạng báo cáo phase".

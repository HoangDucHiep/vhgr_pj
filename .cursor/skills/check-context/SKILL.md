---
name: check-context
description: Trả lời câu hỏi về dữ liệu, schema, quyết định kỹ thuật, QID Wikidata, quan hệ KG, model LLM, hay trạng thái tiến độ của dự án Knowledge Graph lịch sử Việt Nam mà không cần đọc toàn bộ code. Dùng khi người dùng hỏi "quan hệ nào có sẵn", "QID của nhà Trần là gì", "đã làm đến phase nào", "schema node có gì", "dùng model LLM nào".
disable-model-invocation: false
---

# Tra cứu Context dự án

Câu hỏi cần trả lời nhanh, **không cần viết code**. Đọc file phù hợp rồi trả lời — không đoán, không tự kiểm chứng lại từ internet nếu đã có trong docs.

## Bảng tra nhanh

| Câu hỏi | Nguồn |
|---|---|
| Đang làm đến đâu? Việc tiếp theo? | `docs/PROGRESS.md` |
| Quyết định kỹ thuật đã chốt? | `docs/CONTEXT.md` |
| Có những quan hệ nào? Hướng nào? Đối xứng? | `docs/04-schema-knowledge-graph.md` §3 |
| Node có label/thuộc tính gì? | `docs/04-schema-knowledge-graph.md` §2 |
| Cypher DDL, index, constraint? | `docs/04-schema-knowledge-graph.md` §5 |
| QID 9 triều đại? | `docs/CONTEXT.md` §2.6 |
| QID lớp thực thể? | `docs/CONTEXT.md` §2.6 |
| Dùng model LLM nào? Quota? | `docs/CONTEXT.md` §2.2 |
| Format ID, trường bắt buộc? | `AGENTS.md` §6-7 |
| Phase này làm gì? Gate? | `docs/09-ke-hoach-thuc-thien.md` |
| Thuật ngữ nghĩa là gì? | `docs/GLOSSARY.md` |
| Vì sao chọn X? | `docs/DECISIONS.md` |
| Yêu cầu chức năng cụ thể (A1, D3, G4…) | `docs/01-requirements-chuc-nang.md` |
| Tiêu chí phi chức năng | `docs/02-requirements-phi-chuc-nang.md` |
| Nguồn dữ liệu, giấy phép? | `docs/05-du-lieu-va-nguon.md` |
| Công cụ, môi trường, lệnh? | `docs/08-cong-cu-va-moi-truong.md` |
| Vì sao chọn cách đó? Số liệu so sánh? Lỗi đã gặp? | `docs/10-nhat-ky/phase-XX.md` (chi tiết theo phase) |
| Cần số liệu máy đọc được để dựng biểu đồ | `docs/10-nhat-ky/so-lieu/*.json` |

## Quy tắc

- **Trả lời ngắn gọn, có trích dẫn** đường dẫn file và mục cụ thể.
- Nếu câu hỏi **không** có trong docs → nói rõ chưa có, và cho biết cần kiểm tra ở đâu (ví dụ: "cần tra Wikidata trực tiếp").
- **Không** tự tạo số liệu, QID, tên quan hệ mới. Nếu docs chưa có → đề xuất nơi cần bổ sung và hỏi người dùng có muốn xác minh qua API không.
- Nếu cần xác minh dữ liệu sống (QID, quota model), dùng tool đọc web/API rồi **cập nhật luôn** `docs/CONTEXT.md` và báo cáo thay đổi đó.

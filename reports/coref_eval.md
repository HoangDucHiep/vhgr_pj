# Đánh giá coreference — Phase 6

## 1. G5 — độ chính xác gán đại từ (AC C1)

| Chỉ số | Giá trị |
|---|---|
| Số câu đối chiếu | 100 |
| Số mention trong gold | 137 |
| Số mention có nhãn vàng (`canonical_id`) | 118 |
| Số dự đoán đúng | 103 |
| **Độ chính xác** | **0.8729** |
| Hệ thống bỏ sót (gold có, hệ thống null) | 6 |
| Hệ thống gắn thừa (gold null, hệ thống có) | 10 |

### Theo `resolved_by`

| `resolved_by` | Số mention | Đúng | Độ chính xác |
|---|---|---|---|
| `ambiguous` | 15 | 0 | 0.0 |
| `article_subject` | 74 | 62 | 0.8378 |
| `coref_honorific` | 43 | 39 | 0.907 |
| `coref_pronoun` | 5 | 2 | 0.4 |

## 2. G4 — kiểm tra giới tính

| Chỉ số | Giá trị |
|---|---|
| Số đại từ có giới tính được kiểm tra | 109 |
| **Số lỗi gắn sai giới tính** | **0** |

## 3. G6 — chủ thể bài (AC C2)

| Chỉ số | Giá trị |
|---|---|
| Số bài | 2441 |
| Số bài có ground-truth | 1687 |
| Số đúng | 1687 |
| **Độ chính xác (tất cả)** | **1.0** |
| **Độ chính xác (bài nhân vật)** | **1.0** |

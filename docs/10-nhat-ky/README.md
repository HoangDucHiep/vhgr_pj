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
| [`phase-02.md`](phase-02.md) | 2 — Làm sạch wikitext, tách câu/đoạn, trích hyperlink | 14/11/2026 | 3 lỗi lớn (offset lệch 502 bài · vỡ câu do soft-wrap · `<ref>` nuốt text) · chốt mẫu số link & cách đo "câu hợp lệ" |
| [`phase-03.md`](phase-03.md) | 3 — Parse infobox + chuẩn hóa ngày (A4) | 14/11/2026 | 10.078 triple confidence ≥ 0,95 · **audit đóng phase**: 4 lỗi thật (347 triple trùng · 4 self-loop · 81 trùng giữa artifact · template mơ hồ) · ablation đo từng fix |
| [`phase-04.md`](phase-04.md) | 4 — Nhãn bạc NER từ hyperlink (B2.1) | 14/11/2026 | 186.960 câu · 138.860 mention · độ phủ **100%** · **audit đóng phase**: 4 lỗi thật (thiếu ranh giới từ · "Quan lại nhà X" · siêu dữ liệu sinh tử · số đo lượng) · ablation 5 bước |
| [`phase-07.md`](phase-07.md) | 7 — Wikidata DS + tập train RE (D1.1) | 15/11/2026 | Vì sao Wikidata thuần không đủ · đường grounding có giá trị nhất (+152%) · ablation đo từng nguồn nhãn |
| [`phase-08.md`](phase-08.md) | 8 — Mô hình RE đa nhãn + LLM + hợp nhất triple (D1/D2/D3) | 15/11/2026 | Vì sao **đa nhãn sigmoid** không phải softmax · vì sao marker cần **vai trò** (4,62% cặp mơ hồ) · số liệu LLM baseline (evidence substring 97,51%) · 7 lỗi & cách sửa |
| [`phase-13.md`](phase-13.md) | 13 — Sửa chất lượng: entity linking exact-case, chiều đảo quan hệ, lọc cạnh nhiễu KG | 17/11/2026 | 12 ca lỗi demo → 0 · 3 lớp sửa entity linking (alias 13.760→13.582) · **thang so sánh 3 phương án lọc nhiễu** (1.405 / 126 / **23**) · guard chống trả N người ngẫu nhiên |
| [`phase-14.md`](phase-14.md) | 14 — Vanilla RAG: chunking đoạn + MiniLM-L12 + BM25/dense/RRF + trích dẫn `[n]` | 17/11/2026 | 65.608 chunk · embedding (65608, 384) float16 · top-1 đúng bài 6/6 · 700 test pass |
| [`phase-15.md`](phase-15.md) | 15 — Hybrid GraphRAG: template Cypher + ý định + fusion + hội thoại | 17/11/2026 | 6 template · 6 ý định · **không gian trích dẫn `[1..N]` liên tục** · bài Bạch Đằng 30 entity → 60 cạnh / 0,11 s |
| [`phase-16.md`](phase-16.md) | 16 — Đánh giá A vs B vs B− (LLM-judge) | 17/11/2026 | 247 câu × 3 arm · judge gộp 3 arm/câu + hoán vị thứ tự · **thang so sánh A / B / B−** · top-20 câu sai |
| [`phase-17.md`](phase-17.md) | 17 — Giao diện so sánh, demo, đóng gói | 17/11/2026 | Toggle A/B/B− · citation click-to-source · đồ thị 1-hop Cytoscape · docker compose 3 service |
| [`phase-19.md`](phase-19.md) | 19 — Trả lời đúng & có căn cứ, rồi đo lại A vs B vs B− | 19/11/2026 | 3 artefact làm sai lệch phép so sánh (retrieval · tầng sinh · bộ câu hỏi) · gold section trong top-8 **46/60 → 55/60** · **kiểm chứng live**: 0/118 câu hỏi vô lý, 0 câu trả lời bịa năm · **chưa kết luận được** A vs B vs B− |
| [`so-lieu/phase-19-grounded-eval.json`](so-lieu/phase-19-grounded-eval.json) | 19 | — | Số liệu Phase 19: 7 Gate · hit-rate gold section theo 5 nhóm · **thang so sánh 5 cấu hình retrieval** · số liệu kiểm chứng online |
| [`so-lieu/phase-13-chat-luong-kien-thuc.json`](so-lieu/phase-13-chat-luong-kien-thuc.json) | 13 | — | Số liệu Phase 13: chỉ số entity linking trước/sau · **thang so sánh 3 phương án lọc cạnh nhiễu** · số liệu guard chống bịa |
| [`so-lieu/phase-16-eval-rag.json`](so-lieu/phase-16-eval-rag.json) | 16 | — | Số liệu Phase 16: chỉ số 3 arm · **chênh lệch A/B/B−** · phân rã theo 5 dạng câu hỏi |
| [`so-lieu/phase-00-mo-truong.json`](so-lieu/phase-00-mo-truong.json) | 0 | — | Phiên bản thư viện, cấu hình hạ tầng, so sánh phương án bảo vệ DB |
| [`so-lieu/phase-01-bang-do-sanh.json`](so-lieu/phase-01-bang-do-sanh.json) | 1 | — | Thống kê corpus trước/sau T5 theo mọi chiều |
| [`so-lieu/phase-02-text-stats.json`](so-lieu/phase-02-text-stats.json) | 2 | — | Số liệu văn bản Phase 2: trước/sau theo từng lỗi · so sánh 3 phương án xử lý wikilink |
| [`so-lieu/phase-03-infobox-stats.json`](so-lieu/phase-03-infobox-stats.json) | 3 | — | Số liệu infobox Phase 3: 8 Gate (5 gốc + 3 bất biến) · **thang ablation** đo từng fix riêng lẻ |
| [`so-lieu/phase-04-ner-stats.json`](so-lieu/phase-04-ner-stats.json) | 4 | — | Số liệu nhãn bạc NER Phase 4: 5 Gate · phân bố nguồn nhãn (7 nguồn) · **thang ablation 5 bước** · F1 theo loại của 2 baseline |
| [`so-lieu/phase-07-re-stats.json`](so-lieu/phase-07-re-stats.json) | 7 | — | Số liệu tập train RE Phase 7: 5 Gate · phân bố nguồn nhãn POSITIVE (3 nguồn) · **thang ablation** đường grounding |
| [`so-lieu/phase-08-re-llm-merge.json`](so-lieu/phase-08-re-llm-merge.json) | 8 | — | Số liệu Phase 8: **thang so sánh marker** (1.383 cặp mơ hồ → 0) · **thang so sánh đơn vị đo khoảng cách** (khớp 113.917) · số liệu LLM baseline · số liệu hợp nhất 5 nguồn |

## Cách dùng cho báo cáo / slide

| Nhu cầu | Nguồn |
|---|---|
| Slide "hạ tầng & quyết định kiến trúc" | `phase-00.md` § *Quyết định* + `so-lieu/phase-00-mo-truong.json` |
| Slide "vì sao lọc như vậy" | `phase-01.md` § *Thang số liệu* |
| Slide "chất lượng corpus" | `phase-01.md` § *Số liệu đo được* + `so-lieu/phase-01-bang-do-sanh.json` |
| Slide "chất lượng văn bản" | `phase-02.md` § *Số liệu đo được* + `so-lieu/phase-02-text-stats.json` |
| Slide "bài học kinh nghiệm" | `phase-01.md` § *Bài học* |
| Slide "sai lệch so với kế hoạch" | `reports/deviations.md` (D-004 → D-030) |
| Slide "audit: 5 Gate xanh mà dữ liệu vẫn sai" | `phase-03.md` § *Ý tưởng cho slide* + `so-lieu/phase-03-infobox-stats.json` § `thang_so_sanh_ablation` |
| Slide "vì sao chọn đa nhãn cho RE" | `phase-08.md` § *Thang số liệu so sánh* (3.2) + `so-lieu/phase-08-re-llm-merge.json` § `quyet_dinh` |
| Slide "vì sao marker có vai trò" | `phase-08.md` § *Thang số liệu so sánh* (4.1) + `so-lieu/phase-08-re-llm-merge.json` § `thang_so_sanh_marker` |
| Slide "chất lượng LLM baseline" | `phase-08.md` § *Thang số liệu so sánh* (4.4) + `data/interim/re_llm.stats.json` |
| Slide "hợp nhất 5 nguồn triple" | `phase-08.md` § *Số liệu đo được* + `data/interim/triples_merged.stats.json` |
| Slide "sinh nhãn bạc NER" | `phase-04.md` § *Ý tưởng cho slide* + `so-lieu/phase-04-ner-stats.json` § `thang_so_sanh_ablation` |
| Slide "chất lượng nhãn NER" | `phase-04.md` § *Số liệu đo được* + `reports/silver_quality.md` |
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

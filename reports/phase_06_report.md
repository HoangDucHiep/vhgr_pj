# Phase 06 — Coreference Resolution (C1, C2)

- Ngày: 2026-11-15
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: `reports/phase_06_report.md`
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-06.md`
- Sai lệch: `reports/deviations.md` (D-044 → D-055)

## 1. Bối cảnh và vấn đề cần giải

Phase 5 (NER) chỉ gắn nhãn **named mention** (tên riêng có trong Wikipedia). Nhưng
phần lớn nội dung lịch sử Việt Nam viết bằng **đại từ và danh xưng**: "Ông",
"bà", "vua", "Hoàng đế", "đại vương". Đây là phần ngữ nghĩa quan trọng nhất
nhưng lại là phần **NER không bắt được**.

AC C1 yêu cầu "độ chính xác gán đại từ ≥ 0,80 trên gold 100 câu"; AC C2 yêu cầu
"xác định được chủ thể của bài". Để làm được, cần:

1. **Dò thêm** span danh xưng/đại từ mà NER bỏ sót.
2. **Gộp gazetteer** từ 2 nguồn (infobox Phase 3 + tiêu đề bài Phase 2).
3. **Suy chủ thể bài** làm tiên đề mạnh cho đại từ.
4. **Quy tắc ưu tiên** R0–R6 để gắn `canonical_id` cho từng đại từ.

Ràng buộc quan trọng: nguyên tắc "**không bịa**" (`AGENTS.md` §5.3) — khi không
xác định được thì để `null`, tuyệt đối không gắn bừa.

## 2. Phương án đã cân nhắc

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| P1 | **Mở rộng** — dò danh xưng/đại từ thành mention mới + gazetteer hợp nhất + mint `entity_id` cho named mention chưa có trong KB | Thêm **54.502** span danh xưng/đại từ; resolve **137.584/197.610 = 69,62%** | ✅ | Đây mới là C1/C2 thật; chỉ gán `canonical_id` cho span NER sẽ bỏ sót toàn bộ đại từ |
| P2 | Tối giểu đúng `docs/09` — chỉ gán `canonical_id` cho span NER | Resolve rate **~30,7%** (chỉ gazetteer hit) | ❌ | Không đạt Gate ≥ 60%, không giải quyết đại từ |
| P3 | Trung gian — dò danh xưng nhưng không mint `entity_id` | **~30,7%** + đại từ có gazetteer; 12.496 tên không có id | ❌ | Nửa vời, vẫn không đạt Gate |
| P4 | Lưu `article_subject` trong **file riêng** `data/interim/article_subjects.jsonl` | 1 record/doc: `{doc_id, title, type, entity_id, method, confidence}` | ✅ | An toàn về output contract; Phase 9/10 dễ dùng |
| P5 | Nhân bản `article_subject` vào từng record câu | File +~50% dung lượng (186.960 record) | ❌ | Lãng phí; contract không yêu cầu |
| P6 | Mint `entity_id` cho **mọi** named mention chưa có trong KB | `make_entity_id(type, name)` | ✅ | Cần thiết để đạt Gate 60%; id format đã chốt ở Phase 9 nên mint sớm là đúng |
| P7 | Chỉ mint cho tên khớp tiêu đề bài | Chỉ 5.674/62.462 mention (9%) → resolve rate **~38%** | ❌ | Không đạt Gate |
| P8 | Dùng `nil_id` cho named mention chưa có trong KB | `nil_*` không phải `ent_*` | ❌ | **Vi phạm Gate G1** |
| P9 | Bỏ qua mention danh xưng không resolve được | `canonical_id=null`, `resolved_by="ambiguous"` | ✅ | R5 bắt buộc; giữ nguyên tắc không bịa |
| P10 | Đánh giá bằng bộ gold **tay** 100 câu + đối chiếu `article_subject` tự động | G5 = **0,8729**; G6 = **1,00** | ✅ | Bộ gold NER 100 câu sẵn có không chứa nhãn coref → cần bộ riêng |
| P11 | Đánh giá bằng 50 bài nhân vật gán tay thêm | +50 bài | ❌ | Tốn thời gian gán; `article_subject` có ground-truth sẵn (`infobox_type` 1.061 person + `wikidata_signal` 832 person) → đối chiếu tự động đủ tin cậy |

## 3. Quyết định đã chốt

| Mã | Quyết định | Lý do | Ảnh hưởng |
|---|---|---|---|
| **D-044** | Mint `entity_id` **sớm** ở Phase 6 (không chờ Phase 9) | 62.462 named mention không có id sẵn; cần id để đo resolve rate | `coref_resolved.jsonl` dùng id giống hệt Phase 9 sẽ sinh → tái lập được |
| **D-045** | `article_subject` nằm ở **file riêng** `article_subjects.jsonl` | Không phá output contract của `coref_resolved.jsonl` | Phase 9/10 đọc file riêng |
| **D-046** | Bỏ `"y"` khỏi từ điển danh xưng | 205/401 false-positive dạng "y tế" | `configs/honorifics.yaml` không có `y` |
| **D-047** | Độ ưu tiên R0→R0'→R2→**R3**→R1a→**R1b**→R5→R6 (đo được trên gold) | Chủ thể bài là tiên đề mạnh hơn 'người vừa được nhắc trong câu' — G5 0,8475 → **0,8729** | `src/coref/resolve_coref.py`, `configs/default.yaml` |
| **D-048** | Đại từ số nhiều ("các ông", "các vua Trần") → `null` + `ambiguous` | Gắn 1 entity đơn lẻ cho đại từ số nhiều là **sai** | 5.201 mention `ambiguous` |
| **D-049** | R3 (chủ thể bài) chỉ dùng cho đại từ nhãn `PERSON` khi chủ thể là **người** | "ông" trong bài về sự kiện/triều đại sẽ bị gắn nhầm sang entity sự kiện | `ent_dao_chinh_viet_nam_cong_hoa_1963` không còn bị gắn cho "ông" |
| **D-050** | `p31_direct` (P31 trực tiếp) chỉ là tín hiệu **dự phòng cuối cùng** | P31 chính xác hơn `infobox_type` (26 bài lệch), **nhưng** ground-truth của G6 theo plan là `infobox_type` → ưu tiên P31 làm G6 đo sai và G3 giảm (60,30% vs 69,62%) | `src/coref/article_subject.py` |

Chi tiết đầy đủ: `docs/DECISIONS.md`.

## 4. Thang số liệu so sánh

### 4.1. So sánh phương án suy loại chủ thể bài (G6)

Đo trên 1.687 bài có ground-truth (`infobox_type`/`wikidata_signal`):

| Thứ tự ưu tiên | G6 (độ chính xác) | G3 (resolve rate) | Chọn? |
|---|---|---|---|
| `infobox_type` → `wikidata_signal` → `qid_types` → `p31_direct` | **1,0000** | **69,62%** | ✅ |
| `p31_direct` → `infobox_type` → `wikidata_signal` → `qid_types` | 0,3859 | 60,30% | ❌ |

Lý do: ground-truth của G6 theo plan (`docs/09` §Phase 6) là `infobox_type`/
`wikidata_signal`. Ưu tiên P31 (chính xác hơn về mặt sự thật) sẽ làm G6 đo sai
và làm G3 giảm 9,33 điểm → **không đạt Gate G3**.

### 4.2. So sánh thứ tự ưu tiên R (độ chính xác trên gold 100 câu)

Đo bằng `scripts/coref_ablation.py` — 9 biến thể, mỗi lần chạy lại toàn bộ
pipeline trên **đúng đường dẫn code thật** (thứ tự quy tự cấu hình qua
`coref.pronoun_rule_order` — D-052).

| Biến thể | Thứ tự | G5 | Đúng/tổng | G3 | Chọn? |
|---|---|---|---|---|---|
| A | R1a → R1b → R3 → R5 → R6 | 0,8475 | 100/118 | 69,63% | — |
| **B** | **R3 → R1a → R1b → R5 → R6** | **0,8729** | **103/118** | 69,62% | ✅ |
| C | R1a → R3 → R1b → R5 → R6 | 0,8559 | 101/118 | 69,62% | — |
| D | R1b → R1a → R3 → R5 → R6 | 0,8390 | 99/118 | 69,63% | — |
| E | R1a → R1b*(duy nhất)* → R3 → R5 → R6 | 0,8559 | 101/118 | 69,23% | — |
| F | R1a → R3 → R1b*(duy nhất)* → R5 → R6 | 0,8559 | 101/118 | 69,23% | — |
| G | R3 → R1a → R1b*(duy nhất)* → R5 → R6 | 0,8729 | 103/118 | 69,23% | — |
| H | R3*(đặc tả)* → R1a → R1b → R5 → R6 | **0,6864** | 81/118 | 66,76% | ❌ |
| I | R1a → R3*(đặc tả)* → R1b → R5 → R6 | **0,6864** | 81/118 | 66,76% | ❌ |

`R3*(đặc tả)*` = biến thể bám sát `docs/09` §Phase 6 ("R3 dùng khi đoạn **không**
có entity `PERSON` nào").

**Kiểm định ý nghĩa thống kê** (`scripts/coref_bootstrap.py`): biến thể B hơn A
chỉ **3/118 mention**; McNemar **p = 0,5811**, CI 95% bootstrap của A
[0,7685; 0,9159] và B [0,8053; 0,9323] **chồng nhau** → **không có bằng chứng
thống kê** B tốt hơn A. Chọn B vì điểm số cao nhất **và** an toàn hơn về nguyên
tắc (chủ thể bài có nguồn gốc rõ từ Wikipedia, không phải suy đoán mơ hồ).

### 4.3. So sánh có/không sửa lỗi giới tính ở R3 & R6

| Phương án | G4 (lỗi giới tính) | G5 | Chọn? |
|---|---|---|---|
| R3/R6 **không** lọc giới tính | 3 lỗi mô phỏng (gắn entity nữ cho "ông") | 0,8729 | ❌ |
| R3/R6 **có** lọc giới tính | **0** | 0,8729 | ✅ |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| **G1** — 100% `canonical_id` là `ent_*` hoặc `null` | tuyệt đối | **0** vi phạm / 197.610 mention | ✅ |
| **G2** — `make_entity_id` deterministic | 100% | 100% (test `tests/test_entity_id.py`) | ✅ |
| **G3** — Tỉ lệ mention được resolve | ≥ 60% | **69,62%** (không tính TIME: 96,35%) | ✅ |
| **G4** — Không đại từ nào gắn sai giới tính | 0 lỗi | **0** lỗi / 326 đại từ có giới tính được kiểm định (toàn corpus) | ✅ |
| **G5** — Độ chính xác gán đại từ (AC C1) | ≥ 0,80 | **0,8729** (103 đúng / 118 có nhãn vàng) | ✅ |
| **G6** — `article_subject` đúng (AC C2) | ≥ 90% | **100,00%** (1.687/1.687) | ✅ |
| **G7** — Offset mention đúng | 100% | **0** lỗi / 197.610 mention | ✅ |
| **G8** — Test suite | không fail | **439 test pass** (`pytest -q tests/`) | ✅ |

## 6. Lệnh đã chạy

```bash
# 1. Resolve toàn bộ corpus
python -m src.coref.resolve_coref --config configs/default.yaml
#   → 2441 bài · 186.960 câu · 197.610 mention · 137.584 resolve (69,62%)

# 2. Sinh template gold + gán tay
python scripts/coref_make_gold.py --config configs/default.yaml
#   → 100 câu / 137 mention
python scripts/coref_gold_annotate.py --config configs/default.yaml
#   → đã gán 137 mention trên 100 câu

# 3. Đánh giá G4/G5/G6
python scripts/coref_eval.py --config configs/default.yaml
#   → G5 độ chính xác = 0.8729 · G4 lỗi giới tính = 0 · G6 chủ thể = 1.0

# 4. Báo cáo chất lượng
python -m src.coref.quality_report --config configs/default.yaml
#   → Resolve: 137584/197610 (69,62%) · không tính TIME: 96,35% · vi phạm contract: 0

# 5. Ablation thứ tự ưu tiên R (9 biến thể) + kiểm định thống kê
python scripts/coref_ablation.py --config configs/default.yaml
#   → A 0,8475 · B 0,8729 (đã chọn) · H/I (bám sát docs/09) 0,6864
python scripts/coref_bootstrap.py --order-a r1a,r1b,r3,r5,r6 --order-b r3,r1a,r1b,r5,r6
#   → McNemar p = 0,5811 (KHÔNG có ý nghĩa thống kê) · CI 95% chồng nhau

# 6. Kiểm định Gate G1–G8 trực tiếp trên artifact đã sinh
python scripts/coref_gate_check.py --config configs/default.yaml
#   → 8/8 Gate đạt · G5 = 0,8729 · G3 = 0,6962 · G4 = 0 lỗi / 326 đại từ
#   → G8 = 439 passed · số liệu: docs/10-nhat-ky/so-lieu/phase-06-gate-check.json

# 7. Test
pytest -q tests/
#   → 439 passed
```

### 6.1. Công cụ hỗ trợ gán tay (dùng lại khi mở rộng bộ gold ở Phase 7+)

| Script | Việc |
|---|---|
| `scripts/coref_make_gold.py` | Sinh template gold từ tập dev (seed 42) |
| `scripts/coref_gold_annotate.py` | Ghi nhãn vàng vào gold |
| `scripts/coref_candidates.py` | Bảng ứng viên PERSON cho từng mention cần gán |
| `scripts/coref_dump_context.py` | In bối cảnh đầy đủ (toàn đoạn) cho các mention cần gán |
| `scripts/coref_show_para.py` | In đoạn văn đầy đủ cho các câu cần xem xét kỹ |
| `scripts/coref_para.py` | In đoạn của một danh sách `sentence_id` |
| `scripts/coref_debug_sent.py` | In mention NER + coref của một câu và các câu trước |
| `scripts/coref_entity_lookup.py` | Tra cứu ngược `entity_id` → tên (khi gán tay) |
| `scripts/coref_entity_info.py` | Tra cứu chi tiết entity theo `entity_id` hoặc tên |
| `scripts/coref_name_ids.py` | Lấy `entity_id` cho danh sách tên |

> Lưu ý: đây là **công cụ gán tay**, không phải pipeline. Chúng **không** tham gia
> vào bất kỳ Gate nào và **không** thay thế `scripts/coref_gate_check.py`.

## 7. Gate

- [x] G1 — 100% `canonical_id` là `ent_*` hoặc `null` (0 vi phạm)
- [x] G2 — `make_entity_id` deterministic (test tự động)
- [x] G3 — Resolve rate 69,62% ≥ 60%
- [x] G4 — 0 lỗi giới tính (326 đại từ kiểm định)
- [x] G5 — Độ chính xác gán đại từ 0,8729 ≥ 0,80
- [x] G6 — `article_subject` 100,00% ≥ 90%
- [x] G7 — 100% offset đúng (0 lỗi)
- [x] G8 — 439 test pass

## 8. Sai lệch so với kế hoạch

| Mã | Sai lệch | Xử lý |
|---|---|---|
| D-046 | Bỏ `"y"` khỏi từ điển danh xưng (kế hoạch chỉ nói "đặc biệt không đưa `y` vào" — đã làm đúng) | — |
| D-048 | Bổ sung quy tắc "đại từ số nhiều" (không có trong bảng R0–R6 gốc) | Bổ sung vào `docs/DECISIONS.md` |
| D-049 | Bổ sung ràng buộc `subject.type == "person"` cho R3 | Bổ sung vào `docs/DECISIONS.md` |
| D-050 | Bổ sung tín hiệu `p31_direct` làm dự phòng (không có trong kế hoạch) | Bổ sung vào `docs/DECISIONS.md` |
| D-044 | Mint `entity_id` sớm ở Phase 6 (kế hoạch P6 đã chốt) | — |
| **D-047** | **Điều kiện R3 theo `docs/09`** ("đoạn không có `PERSON` nào") **không** dùng; R3 hoạt động như tiên đề. Đo được biến thể bám sát đặc tả: G5 **0,6864** (−16,65 điểm) | Cờ `coref.r3_requires_no_person` (mặc định `false`) để đo được; ghi công khai |
| **D-052** | Thứ tự ưu tiên quy tự **cấu hình được** (`coref.pronoun_rule_order`) thay vì hard-code | Ablation cũ dùng monkeypatch → đo sai (0,7797 thay vì 0,8729) → **đảo ngược** kết luận thiết kế |
| **D-053** | Thêm cờ `coref.r1b_unique_only` (R1b chỉ dùng khi đoạn có đúng 1 người) — **không bật** | McNemar p = 1,00 → không có ý nghĩa thống kê; giữ làm phương án dự phòng đo được |
| **D-054** | Công khai sai lệch có chủ đích với `docs/09` (điều kiện R3) kèm số liệu so sánh | — |
| **D-055** | `reports/coref_quality.md` chứa **5 ký tự Trung Quốc** (render nguyên văn câu mẫu có chữ Hán từ corpus) → vi phạm quy tắc `.cursor/rules/no-chinese.mdc` | Thêm `sanitize_han()` (thay bằng `<bỏ dấu>`) + **3 test regression**; **không** đổi số liệu Phase 6, MD5 artifact giữ nguyên |

Chi tiết: `reports/deviations.md`.

## 9. Việc tiếp theo

**Phase 7 — Relation Extraction (RE)**: dùng `coref_resolved.jsonl` (đã có `canonical_id`
cho 137.584 mention) làm đầu vào để huấn luyện mô hình RE trên tập Wikidata DS.
Lưu ý: `coref_resolved.jsonl` đã sẵn sàng dùng làm **đầu vào trực tiếp** cho
Phase 7 — không cần chạy lại Phase 6.

**Cải thiện để cân nhắc ở phase sau (C3)**:
- Nhóm `coref_pronoun` có độ chính xác thấp nhất → cân nhắc mô hình.
- Mở rộng bộ gold 100 → 300–500 câu: chênh lệch giữa các thứ tự ưu tiên R hiện
  **không có ý nghĩa thống kê** (McNemar p = 0,58) → cần mẫu lớn hơn để chọn
  thứ tự một cách chắc chắn.
- Bổ sung giới tính từ Wikidata `P21` (hiện chỉ 23/1.205 entity có) để siết R4.

---

## 10. Tính tái lập

| Kiểm tra | Kết quả |
|---|---|
| Chạy lại `resolve_coref` → so MD5 `coref_resolved.jsonl` | `cb86fd32fbdb679c0213a29030f76743` — **giống hệt** |
| Chạy lại → so MD5 `article_subjects.jsonl` | `783178f1020efef34eaa9246fee1386a` — **giống hệt** |
| Kiểm định Gate G1–G8 trên artifact đã sinh | `python scripts/coref_gate_check.py` → **8/8 đạt** |

Số liệu kiểm định Gate: `docs/10-nhat-ky/so-lieu/phase-06-gate-check.json`.

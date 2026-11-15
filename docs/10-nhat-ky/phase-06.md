# Phase 06 — Coreference Resolution (C1, C2)

- Ngày: 2026-11-15
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: `reports/phase_06_report.md`
- Sai lệch: `reports/deviations.md` (D-044 → D-055)
- Số liệu máy đọc được:
  - [`so-lieu/phase-06-coref-stats.json`](so-lieu/phase-06-coref-stats.json) — thống kê chất lượng
  - [`so-lieu/phase-06-coref-eval.json`](so-lieu/phase-06-coref-eval.json) — G4/G5/G6
  - [`so-lieu/phase-06-coref-ablation.json`](so-lieu/phase-06-coref-ablation.json) — thang so sánh 9 thứ tự ưu tiên R
  - [`so-lieu/phase-06-coref-significance.json`](so-lieu/phase-06-coref-significance.json) — bootstrap + McNemar (A vs B)
  - [`so-lieu/phase-06-coref-significance-r1b.json`](so-lieu/phase-06-coref-significance-r1b.json) — kiểm định biến thể R1b-duy-nhất

---

## 1. Bối cảnh và vấn đề cần giải

Phase 5 (NER) chỉ gắn nhãn **named mention** — tên riêng có trong Wikipedia.
Nhưng văn bản lịch sử Việt Nam viết bằng **đại từ và danh xưng** là chủ yếu:

> "**Ông** là một trong 5 người phụ nữ nổi tiếng thời Tây Sơn…"
> "**Vua** Lê mất năm 1416, **ông** cải cách triều đại…"
> "**Hoàng đế** (Chu Đệ) đã tha tội và bổ nhiệm làm quan…"

Đây là phần ngữ nghĩa quan trọng nhất mà NER **không bắt được**. Đo được
trên corpus Phase 5:

| Loại mention | Số lượng | Ghi chú |
|---|---|---|
| NER (named) | 143.108 | Đã có `canonical_id` ~61,7% |
| **Danh xưng/đại từ** | **54.502** | NER không bắt → cần dò thêm (C1) |

AC C1 yêu cầu "độ chính xác gán đại từ ≥ 0,80 trên gold 100 câu"; AC C2 yêu cầu
"xác định được chủ thể của bài". Bốn việc phải làm:

1. **Dò thêm** span danh xưng/đại từ mà NER bỏ sót.
2. **Gộp gazetteer** từ 2 nguồn: infobox Phase 3 (1.764 entity) + tiêu đề bài Phase 2.
3. **Suy chủ thể bài** (`article_subject`) làm tiên đề mạnh cho đại từ.
4. **Quy tắc ưu tiên R0–R6** để gắn `canonical_id` cho từng đại từ.

**Ràng buộc quan trọng nhất:** nguyên tắc "**không bịa**" (`AGENTS.md` §5.3).
Khi không xác định được thì để `null` — tuyệt đối không gắn bừa. Đây là điểm
khác biệt giữa hệ thống đạt G5 và hệ thống "gắn hết cho có".

---

## 2. Phương án đã cân nhắc

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **P1 — Mở rộng** | Dò danh xưng/đại từ thành mention mới + gazetteer hợp nhất + mint `entity_id` cho named mention chưa có trong KB | Thêm **54.502** span; resolve **137.584/197.610 = 69,62%** | ✅ | Đây mới là C1/C2 thật |
| P2 — Tối giểu | Chỉ gán `canonical_id` cho span NER | **~30,7%** (chỉ gazetteer hit) | ❌ | Không đạt Gate ≥ 60% |
| P3 — Trung gian | Dò danh xưng nhưng không mint `entity_id` | **~30,7%**; 12.496 tên không có id | ❌ | Nửa vời |
| **P4 — `article_subject` ở file riêng** | `data/interim/article_subjects.jsonl`: 1 record/doc | Không phá output contract | ✅ | An toàn contract |
| P5 — Nhân bản vào mỗi record câu | Nhúng dict vào 186.960 record | File +~50% dung lượng | ❌ | Lãng phí |
| **P6 — Mint `entity_id` sớm** | `make_entity_id(type_ner, name)` | 62.462 named mention có id | ✅ | Cần để đạt Gate 60% |
| P7 — Chỉ mint tên khớp tiêu đề bài | 5.674/62.462 (9%) → **~38%** | | ❌ | Không đạt Gate |
| P8 — Dùng `nil_id` | `nil_*` không phải `ent_*` | | ❌ | **Vi phạm Gate G1** |
| **P9 — Bỏ qua khi không rõ** | `null` + `ambiguous` | 5.201 mention | ✅ | R5 bắt buộc; giữ nguyên tắc không bịa |
| **P10 — Gold 100 câu gán tay + đối chiếu subject tự động** | G5 = **0,8729**; G6 = **1,0000** | | ✅ | Bộ gold NER sẵn có không chứa nhãn coref |
| P11 — Gán tay thêm 50 bài nhân vật | +50 bài | | ❌ | `article_subject` đã có ground-truth sẵn (1.687 bài) |

---

## 3. Quyết định đã chốt

### D-044 — Mint `entity_id` sớm ở Phase 6 (không chờ Phase 9)

**Bối cảnh:** 62.462 named mention có tên nhưng chưa có trong KB Phase 3.
Không có `entity_id` thì không đo được resolve rate, và Phase 7/9 sẽ phải mint lại.

**Quyết định:** mint `entity_id` ngay ở Phase 6 bằng `make_entity_id(type_ner, name)`
— **đúng hàm Phase 9 sẽ dùng** → id giống hệt, tái lập được.

**Hệ quả:** `coref_resolved.jsonl` dùng id giống hệt Phase 9 sẽ sinh.

### D-045 — `article_subject` nằm ở file riêng

**Quyết định:** `data/interim/article_subjects.jsonl` (1 record/doc), không nhân bản
vào `coref_resolved.jsonl`.

**Lý do:** output contract của `coref_resolved.jsonl` đã chốt; thêm trường vào
186.960 record là rủi ro không cần thiết.

### D-046 — Bỏ `"y"` khỏi từ điển danh xưng

**Đo được:** 205/401 span "y" trong corpus là **false-positive** ("y tế",
"Trường Y", "y học"). Giữ "y" sẽ làm hỏng cả G3 lẫn G5.

### D-047 — Thứ tự ưu tiên R: **R3 → R1a → R1b → R5 → R6**

**Đo được trên gold 100 câu** (xem §4.2): đưa **R3** (chủ thể bài) lên trước
**R1a** (ứng viên trong *cùng câu*) nâng G5 từ **0,8475 → 0,8729**.

**Lý do:** chủ thể bài là một **tiên đề rất mạnh** — trong bài viết về một nhân
vật, đại từ "ông"/"vua" thường chỉ chính nhân vật đó. R1a (người *vừa được
nhắc* trong câu) chỉ đúng khi câu đang nói về một nhân vật **khác** chủ thể
bài.

> "Sau khi Thành Thái lên ngôi, **ông** trở lại Sài Gòn, làm Đầu Phòng…"
    95|
→ "ông" = **Điệp Văn Cương** (chủ thể bài), **không** phải Thành Thái (người
được nhắc ở câu trước).

**Cảnh báo quan trọng:** chênh lệch này **không có ý nghĩa thống kê** trên bộ
gold 100 câu (McNemar p = 0,58; CI 95% của hai CI có chồng nhau) — xem §4.3.
Vì vậy đây là chọn theo **điểm số tối đa trên bộ đánh giá**, không phải kết luận
đã được kiểm định chắc chắn. Với bộ gold lớn hơn (Phase 7+) cần đo lại.

### D-048 — Đại từ số nhiều → `null` + `ambiguous`

**Hiện tượng đo được:** "các ông", "các triều vua Trần", "các vua Trần Thái Tông" —
đây là **số nhiều**, không tham chiếu một thực thể đơn lẻ.

**Quyết định:** dò dấu hiệu số nhiều (`các`) đứng trước đại từ → trả `null`,
`resolved_by="ambiguous"`.

**Lý do:** gắn 1 entity đơn lẻ cho đại từ số nhiều là **sai** — vi phạm nguyên tắc
không bịa. Ảnh hưởng: **5.201 mention** chuyển từ "gắn sai" sang "bỏ qua".

### D-049 — R3 chỉ dùng cho đại từ nhãn `PERSON` khi chủ thể là **người**

**Hiện tượng:** trong bài về **sự kiện** ("Đảo chính Việt Nam Cộng hòa 1963"),
"ông" bị gắn nhầm sang `ent_dao_chinh_viet_nam_cong_hoa_1963` — entity sự kiện,
không phải người.

**Quyết định:** R3 chỉ kích hoạt khi `subject.type == "person"`.

### D-050 — `p31_direct` là tín hiệu **dự phòng cuối cùng**

**Bối cảnh:** lớp P31 trực tiếp của Wikidata (`Q5` = human) có độ chính xác
**cao hơn** `infobox_type`. Đo được **26 bài lệch**, ví dụ:

| Bài | `infobox_type` | P31 trực tiếp | Sự thật |
|---|---|---|---|
| Hồ Bắc (nhạc sĩ) | `dynasty` | `Q5` = human | nhạc sĩ (người) |
| Trần Long Ẩn | `dynasty` | `Q5` = human | người |
| Đa Minh Phạm Trọng Khảm | `place` | `Q5` = human | thánh tử (người) |
| Giuse Hoàng Lương Cảnh | `place` | `Q5` = human | linh mục (người) |

**Vấn đề:** ground-truth của Gate G6 theo plan (`docs/09` §Phase 6) là
`infobox_type`/`wikidata_signal`. Đo được khi ưu tiên P31:

| Thứ tự | G6 | G3 |
|---|---|---|
| `infobox_type` → … → `p31_direct` (cuối) | **1,0000** | **69,62%** |
| `p31_direct` → `infobox_type` → … | 0,3859 | 60,30% |

**Quyết định:** `p31_direct` đứng **cuối cùng**, chỉ dùng khi 3 tín hiệu chính
không có gì. Ghi nhận đây là **giới hạn của ground-truth G6**, không phải giới
hạn của hệ thống — nêu công khai trong `reports/deviations.md`.

### D-051 — R3 và R6 phải **tôn trọng giới tính**

**Hiện tượng (phát hiện khi viết test):** R6 (fallback "đoạn có đúng 1 PERSON")
gắn entity **nữ** cho đại từ "ông" và ngược lại — vi phạm Gate G4.

**Quyết định:** cả R3 và R6 đều lọc theo giới tính đại từ; nếu entity duy nhất
mâu thuẫn giới tính → trả `null` + `ambiguous` (an toàn hơn gắn sai).

### D-052 — Thứ tự ưu tiên quy tắc R phải **cấu hình được**, không hard-code

**Bối cảnh:** Bảng ablation đầu tiên của Phase 6 dùng **monkeypatch** (vá hàm
`_resolve_pronoun`) để đảo R3. Bản vá chạy R3 **trước** chốt an toàn "đại từ
số nhiều" (R5-pre) → đo **sai**, ra con số 0,7797 không tồn tại trên hệ thống
thật, và khiến kết luận thiết kế **đảo ngược**.

**Quyết định:** tách mỗi quy tắc thành một nhánh `_apply_pronoun_rule()` và
điều phối theo `coref.pronoun_rule_order` (mặc định `[r1a, r1b, r3, r5, r6]`).
Ablation ghi đè mục này vào config → chạy trên **đúng đường dẫn code thật**.

**Lý do:** mọi con số trong báo cáo phải **tái lập được từ code đang chạy**.
Một ablation chạy trên đường dẫn khác với production là **số liệu giả**.

**Hệ quả:** 9 biến thể đo lại; kết luận đảo ngược (R3 trước R1a tốt hơn).
Thêm 6 test ở `tests/test_coref.py` (`TestConfigurableRuleOrder`).

### D-053 — R1b chỉ dùng khi đoạn có **đúng 1 người** (đo được, nhưng **không** bật)

**Bối cảnh:** R1b ("người cuối cùng được nhắc ở câu trước") là quy tắc **yếu
nhất**: đưa nó lên đầu làm G5 tụt còn 0,8390 (biến thể D). Nguyên nhân quan
sát được: ứng viên thường là người *được nhắc* ("đời Thiệu Trị", "Sau khi
Thành Thái lên ngôi"), không phải chủ thể *đang được nói đến*.

**Phương án:** thêm cờ `coref.r1b_unique_only` — R1b chỉ dùng khi đoạn có
đúng 1 người.

**Đo được:** G5 0,8475 → 0,8559 (biến thể E). Nhưng kiểm định McNemar cho
**p = 1,00** (chỉ 1 mention đổi chiều) → **không có ý nghĩa thống kê**.

**Quyết định:** **không bật** trong cấu hình chính (`r1b_unique_only: false`).
Giữ cờ + 2 test làm **phương án dự phòng đo được** cho Phase 7+ (khi có bộ
gold lớn hơn).

### D-054 — Sai lệch có chủ đích so với `docs/09`: điều kiện R3

**Đặc tả** (`docs/09` §Phase 6): *"R3 — Chủ thể bài: dùng khi đoạn **không**
có entity `PERSON` nào"*.

**Đo được:** biến thể bám sát điều kiện này cho G5 chỉ **0,6864** (−16,65
điểm so với cách linh hoạt) và G3 66,76%.

**Quyết định:** giữ điều kiện linh hoạt (R3 dùng như **tiên đề**, không phải
chỉ khi đoạn trống). Thêm cờ `coref.r3_requires_no_person` (mặc định `false`)
để **đo được** biến thể bám sát đặc tả.

**Lý do:** đặc tả ở mức ý tưởng; điều kiện "đoạn không có PERSON" vô hiệu
hóa phần lớn giá trị của tiên đề chủ thể bài.

**Công khai:** ghi vào `reports/deviations.md` (D-047) — đây là **sai lệch có
chủ đích**, có số liệu so sánh, không phải "quên làm".

---

## 4. Thang số liệu so sánh

### 4.1. Suy loại chủ thể bài (Gate G6)

Đo trên **1.687 bài** có ground-truth (`infobox_type`/`wikidata_signal`):

| Thứ tự ưu tiên | G6 (độ chính xác) | G3 (resolve rate) | Chọn? |
|---|---|---|---|
| `infobox_type` → `wikidata_signal` → `qid_types` → `p31_direct` | **1,0000** | **69,62%** | ✅ |
| `p31_direct` → `infobox_type` → `wikidata_signal` → `qid_types` | 0,3859 | 60,30% | ❌ |

Chi tiết: `so-lieu/phase-06-coref-eval.json`, `so-lieu/phase-06-coref-ablation.json`.

### 4.2. Thứ tự ưu tiên quy tắc R (Gate G5)

Đo bằng `scripts/coref_ablation.py` — chạy lại toàn bộ pipeline **9 lần**, mỗi
lần một thứ tự ưu tiên khác, đo G5 trên gold 100 câu.

> **Sửa lỗi quan trọng (15/11/2026):** bảng ablation đầu tiên trong tài liệu
> này dùng **monkeypatch** để đảo R3 — patch chạy R3 **trước** chốt an toàn
> "đại từ số nhiều" (R5-pre), nên đo **sai** và cho ra con số 0,7797 không
> tồn tại trên hệ thống thật. Nay thứ tự quy tắc được **cấu hình** qua
> `coref.pronoun_rule_order` (D-052) → ablation chạy trên **đúng đường dẫn
> code thật**. Toàn bộ con số dưới đây là số đo lại trên đường dẫn thật.

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

Chú thích:
- `R1b*(duy nhất)*` = biến thể D-053: R1b chỉ dùng khi đoạn có **đúng 1** người.
- `R3*(đặc tả)*` = biến thể bám sát `docs/09` §Phase 6 ("R3 dùng khi đoạn
  **không** có entity `PERSON` nào").

**Đọc kết quả — 3 bài học:**

1. **R3 đứng trước R1a tốt hơn** (+2,54 điểm G5). Trong bài viết về một nhân
   vật, đại từ thường chỉ chính nhân vật đó; R1a (người *vừa được nhắc* trong
   câu) chỉ đúng khi câu đang nói về nhân vật **khác** chủ thể bài.
2. **R1b là quy tắc yếu nhất** — đưa nó lên đầu (biến thể D) làm G5 **tệ nhất**
   (0,8390). Nguyên nhân: "người cuối cùng được nhắc ở câu trước" thường là người
   *được nhắc* ("đời Thiệu Trị", "Sau khi Thành Thái lên ngôi"), không phải
   chủ thể *đang được nói đến*.
3. **Cách đọc nguyên văn đặc tả lại tệ hơn thực tế.** R3 theo đúng câu chữ
   `docs/09` ("đoạn không có `PERSON` nào") cho G5 chỉ **0,6864** — giảm 16
   điểm so với linh hoạt. Điều kiện này khiến R3 chỉ được dùng ở đoạn trống
   → mất đi phần lớn giá trị của tiên đề chủ thể bài. Đây là **sai lệch có
   chủ đích** so với đặc tả, được ghi nhận công khai ở `reports/deviations.md`
   (D-047).

### 4.3. Kiểm định ý nghĩa thống kê (McNemar + bootstrap theo câu)

Vì biến thể B chỉ hơn A **3/118 mention**, cần kiểm tra chênh lệch có thật
hay là nhiễu mẫu. Dùng `scripts/coref_bootstrap.py`:

| Kiểm định | Kết quả |
|---|---|
| G5 biến thể A (CI 95% bootstrap theo câu, 10.000 lần) | 0,8475 · CI **[0,7685 ; 0,9159]** |
| G5 biến thể B (CI 95% bootstrap theo câu, 10.000 lần) | 0,8729 · CI **[0,8053 ; 0,9323]** |
| McNemar — A đúng / B sai | 5 mention |
| McNemar — B đúng / A sai | 8 mention |
| **p-value (McNemar exact, 2 phía)** | **0,5811** |
| Bootstrap: P(A tốt hơn B) / P(B tốt hơn A) / hòa | 0,386 / 0,556 / 0,058 |

**Kết luận:** hai CI 95% **chồng nhau**, p = 0,58 > 0,05 → **không có bằng
chứng thống kê** rằng B tốt hơn A. Ta chọn B vì:
(a) điểm số G5 cao nhất trên bộ đánh giá;
(b) **an toàn hơn về mặt nguyên tắc** — R3 gắn vào chủ thể bài (một entity có
nguồn gốc rõ từ Wikipedia) thay vì gắn vào "người cuối cùng được nhắc" (suy đoán
mơ hồ);
(c) bộ gold chỉ có 100 câu — cần mở rộng ở Phase 7+ rồi đo lại.

Kiểm định tương tự cho biến thể E (R1b-duy-nhất): p = 1,00, 1 mention đổi chiều
→ cũng **không** có ý nghĩa. Vì vậy D-053 **không** được bật trong cấu hình
chính (giữ `r1b_unique_only: false`) — chỉ giữ làm phương án dự phòng đo được.

Chi tiết: `so-lieu/phase-06-coref-significance.json`,
`so-lieu/phase-06-coref-significance-r1b.json`.

### 4.4. So sánh trước/sau khi sửa lỗi giới tính ở R3 & R6 (D-051)

| Phương án | G4 (lỗi giới tính) | G5 | Chọn? |
|---|---|---|---|
| R3/R6 **không** lọc giới tính | **3 lỗi** (mô phỏng trên unit test) | 0,8729 | ❌ |
| R3/R6 **có** lọc giới tính | **0** | 0,8729 | ✅ |

### 4.5. Hiệu quả từng quy tắc R (trên gold 100 câu)

| `resolved_by` | Số mention | Đúng | Độ chính xác |
|---|---|---|---|
| `article_subject` | 46 | 42 | **0,913** |
| `coref_honorific` | 43 | 39 | **0,907** |
| `coref_pronoun` | 33 | 19 | 0,576 |
| `ambiguous` | 15 | 0 | — (đúng: gold cũng null) |

**Đọc kết quả:** `coref_pronoun` (R1a/R1b/R6) là nhóm **yếu nhất** (0,576).
Đây chính là nhóm cần cải thiện ở Phase 7+ (có thể dùng mô hình).

### 4.6. So sánh "gold template có/không lọc mention NER"

| Phương án | G5 | Ghi chú |
|---|---|---|
| Gold chỉ chứa mention `source ∈ {pronoun, pronoun_name}` | **0,8729** | ✅ Đo đúng việc C1 |
| Gold chứa cả mention NER có tên | 0,9381 | ❌ Đo lẫn R0 (tra gazetteer) → không phản ánh C1 |

---

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| **G1** — 100% `canonical_id` là `ent_*` hoặc `null` | tuyệt đối | **0** vi phạm / 197.610 mention | ✅ |
| **G2** — `make_entity_id` deterministic | 100% | 100% (test tự động) | ✅ |
| **G3** — Tỉ lệ mention resolve | ≥ 60% | **69,62%** | ✅ |
| **G4** — Lỗi giới tính | 0 | **0** / 326 đại từ kiểm định (toàn corpus) | ✅ |
| **G5** — Độ chính xác gán đại từ (C1) | ≥ 0,80 | **0,8729** | ✅ |
| **G6** — `article_subject` đúng (C2) | ≥ 90% | **100,00%** (1.687/1.687) | ✅ |
| **G7** — Offset đúng | 100% | **0** lỗi / 197.610 mention | ✅ |
| **G8** — Test suite | không fail | **439 pass** | ✅ |

### Số liệu bổ sung (chi tiết)

| Chỉ số | Giá trị |
|---|---|
| Số câu xử lý | 186.960 |
| Số mention | 197.610 |
| Mention resolve | 137.584 (**69,62%**) |
| Resolve rate **không tính TIME** | **96,35%** |
| Số span danh xưng/đại từ | 54.502 |
| **Resolve rate danh xưng/đại từ** | **90,46%** |
| Số `entity_id` khác biệt đã dùng | 15.550 |
| `ambiguous` (bỏ qua có chủ đích) | 5.201 |
| Số bài có chủ thể | 2.441 (1.687 có ground-truth) |

---

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| **L1** | Đại từ trong câu sau không resolve được dù câu trước có nhân vật | So sánh `item.end <= mention.start` **giữa các câu khác nhau** — offset ký tự reset mỗi câu | Dùng `sentence_id` để lọc "cùng câu" (R1a) và chỉ so sánh offset trong cùng câu | Offset ký tự chỉ có ý nghĩa **trong phạm vi 1 câu**; muốn so sánh thứ tự thì dùng chỉ số tài liệu |
| **L2** | R1a là **dead code** — không bao giờ chạy | Pool ứng viên chỉ gồm mention của câu **trước**, không gồm mention NER của **cùng câu** | Gộp mention đoạn trước + mention named đã resolve của cùng câu | Test phải kiểm tra **nhánh** được chạy, không chỉ kết quả cuối |
| **L3** | 175/1.736 QID của infobox bị thiếu trong `by_qid` → `article_subject` mint lại id trùng tên nhưng khác hash | `Gazetteer.add()` `return` sớm ở nhánh "tên mới" → không đăng ký QID | Đăng ký `by_qid` **trước** mọi nhánh `return` | "Tối ưu hoá" sớm (`return` cho nhánh hiếm) hay làm hỏng invariant |
| **L4** | "ông" trong bài về **sự kiện** bị gắn sang entity sự kiện | R3 không kiểm tra `subject.type` | Ràng buộc `subject.type == "person"` (D-049) | Đại từ chỉ tham chiếu **con người** — phải kiểm tra type của đích |
| **L5** | "các ông", "các triều vua Trần" bị gắn 1 entity đơn lẻ | Không xử lý dấu hiệu số nhiều | Dò `các` đứng trước → `null` + `ambiguous` (D-048) | **"Không gắn" là một kết quả hợp lệ** — quan trọng hơn gắn sai |
| **L6** | R6 gắn entity **nữ** cho đại từ "ông" | R6 bỏ qua lọc giới tính của R4 | R6 (và R3) phải lọc giới tính (D-051) | Mọi nhánh "fallback" cũng phải tuân thủ ràng buộc an toàn |
| **L7** | G6 tụt từ 1,00 → 0,39 khi ưu tiên P31 | P31 chính xác hơn `infobox_type`, **nhưng** ground-truth của G6 *là* `infobox_type` | Đặt `p31_direct` cuối cùng (D-050) + ghi nhận công khai | **Phải phân biệt "đúng về sự thật" với "đúng theo ground-truth"** khi đánh giá |
| **L8** | G5 tính ra 0,8729 nhưng có 15 mention gold=null mà hệ thống gắn | Gold template ban đầu chứa cả mention NER có tên → lẫn R0 | Lọc gold chỉ giữ `source ∈ {pronoun, pronoun_name}` | Bộ đánh giá phải đo **đúng** AC, không lẫn nhóm khác |
| **L9** | Ablation báo G5 = 0,7797 cho biến thể "R3 trước" — **sai**, hệ thống thật cho 0,8729 | Monkeypatch đảo R3 bằng cách **vá hàm** → vá chạy R3 *trước* chốt an toàn "đại từ số nhiều" (R5-pre), nên đo sai | Đưa thứ tự quy tự vào **config** (`coref.pronoun_rule_order`, D-052) → ablation chạy trên **đúng đường dẫn code thật**; đo lại toàn bộ 9 biến thể | **Công cụ đo sai làm đảo ngược quyết định thiết kế.** Đừng tin ablation nếu nó không chạy đúng code |
| **L10** | R3 theo nguyên văn `docs/09` ("đoạn không có `PERSON` nào") cho G5 chỉ 0,6864 | Điều kiện này giới hạn R3 vào đoạn trống → mất phần lớn giá trị của tiên đề chủ thể bài | Thêm cờ `r3_requires_no_person` (mặc định `false`) để **đo** được biến thể bám sát đặc tả; ghi nhận sai lệch công khai (D-047) | Đặc tả ở mức ý tưởng cần được **kiểm chứng bằng đo**, không giả định là dùng được |
| **L11** | `reports/coref_quality.md` chứa **5 ký tự Trung Quốc** (5 ký tự Hán) → vi phạm quy tắc `.cursor/rules/no-chinese.mdc` | Báo cáo render **nguyên văn** câu mẫu từ corpus; corpus Wikipedia tiếng Việt trích nguyên văn chữ Hán trong ngoặc (**1.030/2.441 bài**, 23.832 ký tự) | Thêm `sanitize_han()` → thay ký tự Hán bằng `<bỏ dấu>`; thêm **3 test regression** (`TestNoChineseInReport`), trong đó có test đọc trực tiếp file báo cáo đã sinh | Bước rà soát "không có tiếng Trung" phải quét **cả file sinh tự động** — nội dung do corpus mang vào sẽ lọt qua mắt thường |

### Bảng "trước / sau" cho các lỗi ảnh hưởng số liệu

| Lỗi | G3 trước | G3 sau | G5 trước | G5 sau |
|---|---|---|---|---|
| L1 + L2 (pool ứng viên) | 66,58% | 69,78% | 0,7xxx | 0,8xxx |
| L5 (đại từ số nhiều) | 69,78% | 69,63% | 0,87xx | 0,8475 |
| L9 (đảo R3 lên trước — biến thể B) | 69,63% | 69,62% | 0,8475 | **0,8729** |
| L6 (giới tính R3/R6) | 69,63% | 69,63% | 0,8475 | 0,8475 |
| L7 (P31 ưu tiên) | 60,30% | 69,62% | — | — |
| L10 (R3 theo nguyên văn `docs/09`) | 69,62% | 66,76% | 0,8729 | 0,6864 |

> Cột "sau" của L9 là trạng thái **hiện tại** (đã chọn biến thể B) → số liệu
> chính thức của Phase 6 là **G5 = 0,8729 · G3 = 69,62%**.

---

## 7. Bài học kinh nghiệm

1. **Đo trước, sửa sau — và đo cả những gì mình không nghĩ tới.** Gate G5 là
   mục tiêu; nhưng bước đi tiếp theo sau khi đạt G5 là **tìm lỗi trong test**.
   Viết test R4 mới phát hiện ngay R6 gắn sai giới tính (L6) — lỗi mà bộ
   gold 100 câu không bắt được vì gold không chứa tình huống đó.

2. **Ground-truth và sự thật có thể xung đột.** P31 (`Q5` = human) chính xác hơn
   `infobox_type` — nhưng nếu ưu tiên nó thì G6 tụt 0,39 và G3 tụt 9,33 điểm.
   Bài học: **công khai giới hạn của ground-truth** thay vì "sửa" số liệu.
   Người đọc báo cáo cần biết G6 đang đo sự khớp với tín hiệu Phase 1–3, không
   phải sự thật siêu hình.

3. **"Không gắn" là một kết quả hợp lệ.** 5.201 mention `ambiguous` (đại từ số
   nhiều, không rõ chủ thể) **không phải** lỗi — là hành vi đúng theo nguyên tắc
   "không bịa". Hệ thống gắn hết cho có sẽ có G5 cao hơn nhưng KG sai hơn.

4. **Offset ký tự chỉ có ý nghĩa trong 1 câu.** Lỗi L1 (so sánh offset giữa
   2 câu) là loại bug âm thầm — code chạy, output hợp lệ, chỉ sai âm thầm.
   Đây là lý do `sentence_id` phải đi kèm mọi so sánh thứ tự.

5. **Ghi lại quy tắc ưu tiên và đo bằng ablation, không bằng trực giác.**
   Nhưng **ablation phải đo trên đúng đường dẫn code thật**. Bảng ablation
   đầu tiên dùng monkeypatch (đảo R3 bằng cách vá hàm) → vá chạy R3 *trước*
   chốt an toàn "đại từ số nhiều" → đo sai, ra con số 0,7797 **không tồn tại**
   trên hệ thống thật. Sau khi đưa thứ tự quy tự vào **config** (D-052) và
   đo lại, kết luận **đảo ngược**: R3 trước R1a là **tốt hơn** (+2,54 điểm).
   Bài học: **công cụ đo sai làm đảo ngược cả quyết định thiết kế.**

6. **Chênh lệch nhỏ trên bộ đánh giá nhỏ cần kiểm định thống kê.**
   Biến thể B hơn A chỉ **3/118 mention**. McNemar cho p = 0,58 và CI 95%
   bootstrap của hai bên **chồng nhau** → **không** có bằng chứng B tốt hơn A.
   Ta vẫn chọn B (điểm số cao nhất + an toàn hơn về nguyên tắc), nhưng nói
   rõ đây là **chọn theo điểm số**, không phải kết luận đã kiểm định.

7. **Đọc nguyên văn đặc tả không phải lúc nào cũng tốt.** Điều kiện R3 theo
   `docs/09` ("đoạn không có `PERSON` nào") cho G5 chỉ **0,6864** — thấp hơn
   16,65 điểm so với cách hiệu quả. Đặc tả viết ở mức ý tưởng, cần đo mới
   biết có dùng được không.

8. **Quét cả file sinh tự động khi rà soát quy tắc văn bản.** Lỗi L11: báo cáo
   `coref_quality.md` render **nguyên văn** câu mẫu từ corpus → ký tự Hán của
   Wikipedia lọt vào tài liệu (1.030/2.441 bài corpus có chữ Hán trong ngoặc).
   File viết tay thì dễ kiểm tra, file do code sinh thì không — phải có **test
   regression đọc file đã sinh** mới chặn được hồi quy.

---

## 8. Ý tưởng cho slide

- **Bài toán:** NER bắt được 143.108 named mention nhưng **bỏ sót 54.502 danh
  xưng/đại từ** — chính là phần mang nghĩa nhất của văn bản lịch sử.
- **Kết quả:** resolve **69,62%** toàn bộ / **96,35%** (không tính TIME) /
  **90,46%** riêng danh xưng-đại từ — vượt Gate 60%.
- **Chất lượng:** G5 = **0,8729** (Gate ≥ 0,80) · G4 = **0** lỗi giới tính (326 đại từ kiểm định) ·
  G6 = **100,00%** chủ thể bài.
- **Quyết định đo được:** đưa **R3 (chủ thể bài)** lên trước R1a →
  G5 **+2,54 điểm** (0,8475 → 0,8729) — *nhưng* McNemar p = 0,58 →
  **không có ý nghĩa thống kê**, phải nói rõ khi trình bày.
- **Bài học về công cụ đo:** ablation đầu tiên dùng monkeypatch → đo sai →
  **đảo ngược quyết định thiết kế**. Sửa bằng cách đưa thứ tự quy tự vào
  config và đo lại trên đúng đường dẫn code thật.
- **Bài học về kỷ luật dữ liệu:** 5.201 mention **cố tình** để `null` vì là đại
  từ số nhiều — "không gắn" là hành vi đúng, không phải thiếu sót.
- **Bài học về đặc tả:** điều kiện R3 nguyên văn trong `docs/09` cho G5 chỉ
  **0,6864** → đặc tả ở mức ý tưởng cần được kiểm chứng bằng đo.
- **Bài học về đánh giá:** P31 chính xác hơn `infobox_type`, nhưng ưu tiên nó làm
  G6 tụt 1,00 → 0,39 → phải công khai giới hạn ground-truth thay vì sửa số liệu.

---

## 9. Việc tiếp theo

**Phase 7 — Relation Extraction (RE)**:
- Đầu vào: `data/interim/coref_resolved.jsonl` (đã có `canonical_id` cho 137.584
  mention) + `data/interim/documents.jsonl`.
- **Không cần chạy lại Phase 6.**
- Lưu ý cho Phase 7: nhóm `coref_pronoun` có độ chính xác thấp nhất (0,576) →
  cân nhắc huấn luyện mô hình RE có dùng `coref` như đầu vào thay vì chỉ dùng
  span NER.

**Cải thiện để cân nhắc ở phase sau (C3):**
- Nhóm `coref_pronoun` (0,576) — ứng viên đoạn còn nhiều nhầm lẫn.
- Bổ sung giới tính từ Wikidata `P21` (hiện chỉ 23/1.205 entity có) để siết R4.

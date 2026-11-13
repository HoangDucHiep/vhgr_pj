# Phase 01 — Tải dump viwiki `20261101` và lọc corpus lịch sử Việt Nam

- Ngày: 2026-11-13 (lượt chạy cuối: 14/11/2026 00:38)
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: [`reports/phase_01_report.md`](../../reports/phase_01_report.md)
- Sai lệch: D-008 → D-012 (xem [`reports/deviations.md`](../../reports/deviations.md))
- Số liệu máy đọc được: [`so-lieu/phase-01-bang-do-sanh.json`](so-lieu/phase-01-bang-do-sanh.json)
- Artifact sinh ra: `data/interim/documents.jsonl`, `data/interim/filter_stats.json`,
  `data/interim/category_members.json`, `data/interim/category_hierarchy.json`,
  `data/interim/wikidata_seed_articles.json`, `data/interim/pageid_to_qid.json`,
  `data/interim/title_to_qid.json`

---

## 1. Bối cảnh và vấn đề cần giải

Dump viwiki `20261101` có **2.255.249 trang**. Mục tiêu của Phase 1: lấy ra một corpus
**2.000–5.000 bài** làm lịch sử Việt Nam, làm nền cho NER/RE/entity linking ở Phase 4–9.

Bốn ràng buộc đồng thời:

| # | Ràng buộc | Nguồn |
|---|---|---|
| R1 | Corpus nằm trong khoảng 2.000–5.000 bài | Gate Phase 1 |
| R2 | RAM peak < 4 GB (dump XML 2,5 GB) | Gate Phase 1 |
| R3 | Chạy lại 2 lần → checksum `documents.jsonl` **giống hệt** | Nguyên tắc tái lập (AGENTS.md §5.6) |
| R4 | Bài phải **thực sự là lịch sử Việt Nam**, không phải "có bài tiếng Việt" | Rủi ro lớn nhất, phát hiện khi đo |

R4 là rủi ro trọng tâm của phase này: tín hiệu "là một thực thể lịch sử" từ Wikidata
**không tự động kéo theo** "là lịch sử Việt Nam".

---

## 2. Phương án đã cân nhắc

### 2.1 Kiến trúc bộ lọc

| Phương án | Cách làm | Kết quả | Chọn? |
|---|---|---|---|
| A. 1 lượt đọc dump, giữ toàn bộ `links` trong RAM | Nạp 2,25 triệu trang + toàn bộ link | ❌ Vượt 4 GB — giữ `links` của toàn bộ dump không khả thi | Không |
| B. 3 lượt streaming | (1) phân loại T0/T1/T2 · (2) BFS T3 quét lại để lấy `links` của biên · (3) ghi `wikitext` ra đĩa | ✅ RAM peak **1,16 GB** · tổng 31 phút (đọc lại file 1,1 GB nhiều lần) | **Có** (D-011) |
| C. Lưu `links` ra file đĩa ở lượt 1 rồi BFS từ file | 1 lượt đọc dump + BFS trên file | ⚠️ Nhanh hơn nhưng thêm 1 artifact trung gian ~500 MB và phức tạp hoá code | Chưa làm — ghi nhận là hướng tối ưu nếu cần rút ngắn thời gian |

### 2.2 Chọn tín hiệu "người lịch sử" từ Wikidata (T0)

Đếm trên QLever (13/11/2026):

| Bộ quan hệ lọc | Số người trả về | Đánh giá |
|---|---|---|
| `P22` (có cha) | **203** | ✅ Tín hiệu mạnh nhất, đúng 9 triều đại |
| `P22 \| P25 \| P26` | 293 | Rộng hơn, vẫn hợp lý |
| `P22 \| P25 \| P26 \| P39` | 783 | Bắt đầu lẫn sang người hiện đại |
| Không lọc quan hệ | 1.996 | ❌ Quá rộng, chủ yếu người thế kỷ 19–20 |

→ Chọn `P22` làm tín hiệu chính (`wikidata_relation_filter: "P22"` trong
`configs/seed_articles.yaml`), cộng thêm cửa sổ năm sinh `person_year_max = 1900`
(nhà Nguyễn kết thúc 1945 nhưng đa số nhân vật thời Nguyễn sinh trước 1900).

### 2.3 Vì sao cần tầng T5 "chốt phạm vi"

Tín hiệu Wikidata `battle` (`P31/P279* = Q178561`) và `dynasty` (`P31 = Q164950`) là
**toàn cầu**: lấy *mọi* trận đánh và *mọi* triều đại có bài tiếng Việt.

Đã thử lọc thêm bằng `P17`/`P276`/`P131` → **trả về 0 dòng**, vì Wikidata không gắn
quốc gia cho trận đánh. Vậy nên không có cách nào "sửa" truy vấn; phải lọc ở tầng category.

Quan sát thực tế trên 3.113 bài ở lượt chạy đầu (~35% nằm ngoài phạm vi):

| Bài giữ nhầm | Vì sao lọt vào |
|---|---|
| Trận Stalingrad, Trận Le Mans, Chiến tranh Afghanistan (2001–2021) | `battle` — có bài tiếng Việt, nằm trong cửa sổ năm |
| Nhà Ptolemaios, Vương triều Palaiologos | `dynasty` — `P31 = Q164950` khớp toàn cầu |
| Chiến tranh Mali, Xung đột chính trị Jamaica | `event` / `place` không gắn Việt Nam |

### 2.4 Cách xác định "category trong phạm Việt Nam"

| Phương án | Cách làm | Kết quả | Chọn? |
|---|---|---|---|
| A. Chỉ category chứa chữ "Việt" | `normalize_name(category)` chứa `"viet"` | ⚠️ Bỏ sót nhiều nhân vật chỉ có category địa phương ("Người Bắc Ninh", "Vương tước nhà Lý") | Một phần |
| B. A + regex nhóm "nhà vua" (`VN_HOUSE_RE`) | Nhà Ngô/Đinh/Tiền Lê/Lý/Trần/Hồ/Mạc/Lê sơ/Hậu Lê/Lê Trung Hưng/Nguyễn/Tây Sơn | ✅ Bắt được các nhân vật chỉ có category địa phương | **Có** |
| C. Bắt buộc category chứa "Việt" (loại trừ mọi thứ khác) | Chỉ nhóm "Việt" | ❌ Mất các nhân vật/địa danh quan trọng | Không |

→ Chọn **B**: `_has_scope_category()` = có chữ "Việt" **hoặc** khớp `VN_HOUSE_RE`.

---

## 3. Quyết định đã chốt

| Mã | Quyết định | Lý do | Ảnh hưởng | File |
|---|---|---|---|---|
| D-008 | T2 (và T3 nới lỏng) bắt buộc có category trong phạm Việt Nam + siết số trường lịch sử tối thiểu theo loại infobox (`person: 3`, `place: 2`, `dynasty: 2`, `battle: 1`, `event: 1`) | Infobox `battle` + mốc năm là điều kiện **rất yếu** — trận Verdun/Poltava/Boer đều khớp | T2 giảm từ ~1.300 → 277 bài; corpus 3.113 bài (vẫn trong khoảng Gate) | `src/preprocess/filter_articles.py`, `configs/seed_articles.yaml` |
| D-009 | `normalize_infobox_type` khớp **từ khoá đầy đủ**, chỉ cho phép khớp tiền tố khi khoá ≥ 4 ký tự và không trùng khoá khác | `tranh` (tranh vẽ) khớp tiền tố `tran` → nhận nhầm `battle`; `nha nhac` → nhận nhầm `dynasty` | Phân bố `infobox_type` chính xác | `src/preprocess/infobox_parser.py` |
| D-010 | Cây category khóa theo **title**, không theo `page_id` | MediaWiki tách `categorylinks` và `linktarget` thành 2 bảng: `cl_from` = `page_id` của trang category, `cl_target_id` = `lt_id` | Mở rộng cây: **11 → 81 category** (1.682 categorylink, 1.285 trang) → T1 giữ 1.190 bài thay vì ~0 | `src/preprocess/category_index.py` |
| D-011 | Bộ lọc chạy **3 lượt streaming** | Giữ `links` của 2,25 triệu trang trong RAM sẽ vượt 4 GB | RAM peak 1,16 GB (đạt Gate) · thời gian 31 phút | `src/preprocess/filter_articles.py` |
| D-012 | Thêm tầng **T5 "chốt phạm vi lịch sử Việt Nam"** | Tín hiệu Wikidata `battle`/`dynasty` là toàn cầu; `P17`/`P276`/`P131` không gắn quốc gia cho trận đánh (trả 0 dòng) | Corpus **3.113 → 2.441**; tỉ lệ bài có category chứa "Việt" **64,6% → 82,3%**; bài trong phạm vi nghiêm **73,3% → 96,7%** | `src/preprocess/filter_articles.py`, `tests/test_filter_scope.py`, `docs/CONTEXT.md` §2.7 |
| — | 16 category seed chỉ khớp **chính xác tên**, không khớp tiền tố | Category như "Thời đại Lê", "Nhà Lê", "Vua" trả 0 hoặc toàn bài nước ngoài | T1 đáng tin | `configs/seed_articles.yaml` |
| — | `history_year_min = 850` (thời Đại Cồ Việt), `history_year_max = 1945` (kết thúc nhà Nguyễn) | Bao trùm 9 triều đại từ Ngô Quyền (938) | Chặn bài hiện đại có infobox đầy đủ | `configs/seed_articles.yaml` |
| — | BFS T3 giới hạn chiều sâu ≤ 2 | Chiều sâu 3 sẽ nở rộng sang bài phi lịch sử | T3 thêm 276 bài | `configs/seed_articles.yaml` |

---

## 4. Thang số liệu so sánh

### 4.1 Thang lọc nhiễu — bốn phương án đo được (điểm mấu chốt của phase)

| Phương án | Mô tả | Số bài | % so với gốc | Tỉ lệ có category "Việt" | Chọn? |
|---|---|---|---|---|---|
| **A** | T0–T4, không có T5 (kế hoạch ban đầu) | **3.113** | 100% | 64,6% | — (bị loại vì ~35% nằm ngoài phạm vi) |
| **B** | Giữ T0 `person`/`place`/`house`; `battle`/`dynasty`/`event` phải có category "Việt" | **2.606** | 83,7% | — | — |
| **C** | B + T1 phải nằm trong cây seed **và** có category "Việt" | **2.250** | 72,3% | — | — (mất bài hợp lệ) |
| **D** | C + mở rộng category phạm vi bằng `VN_HOUSE_RE` (nhóm "nhà vua") | **2.331** | 74,9% | — | — |
| **Hiện thực** | D tích hợp + `place`/`event` giữ theo điều kiện riêng | **2.441** | 78,4% | **82,3%** | ✅ **Đã chọn** |

Đọc bảng: phương án **C siết quá tay** (mất 356 bài so với D, nhiều bài là nhân vật chỉ có
category địa phương). Phương án **D** thêm lại nhóm "nhà vua" mà vẫn giữ được độ phủ.

### 4.2 Trước / sau T5 — theo mọi chiều

| Chỉ số | Trước T5 (3.113 bài) | Sau T5 (2.441 bài) | Thay đổi |
|---|---|---|---|
| Tổng số bài | 3.113 | **2.441** | −672 (−21,6%) |
| Bài có QID | 3.046 (97,85%) | 2.375 (**97,3%**) | −0,55 pp |
| Bài có category chứa "Việt" | 2.010 (64,57%) | 2.009 (**82,3%**) | **+17,7 pp** |
| Bài trong phạm vi nghiêm (T5) | 2.281 (73,27%) | 2.361 (**96,72%**) | **+23,4 pp** |

Phân bố theo `keep_reason`:

| `keep_reason` | Trước T5 | Sau T5 |
|---|---|---|
| `wikidata` (T0) | 1.425 | **930** |
| `category` (T1) | 1.190 | **933** |
| `infobox` (T2) | 277 | **302** |
| `seed_expansion` (T3) | 221 | **276** |

Phân bố theo `infobox_type`:

| `infobox_type` | Trước T5 | Sau T5 | Nhận xét |
|---|---|---|---|
| `person` | 997 | **1.061** | Tăng — T5 loại bài nhiễu nên T2 có thêm biên |
| `battle` | 651 | **202** | **Giảm 69%** — đây chính là nguồn nhiễu lớn nhất |
| `place` | 151 | **150** | Ổn định — tín hiệu `place` đã gắn `P17=Q881` |
| `dynasty` | 16 | **16** | Ổn định — 9 triều đại đã verify vẫn còn đủ |
| `event` | 12 | **11** | Gần như giữ nguyên |
| `none` | 1.286 | **1.001** | — |

Phân bố theo tín hiệu Wikidata (chỉ nhóm `keep_reason="wikidata"`):

| Tín hiệu | Trước T5 | Sau T5 | Ghi chú |
|---|---|---|---|
| `person` | 832 | **832** | Không đổi — tín hiệu đã gắn Việt Nam qua `P27`/`P19`/`P39` |
| `battle` | 385 | **3** | **Giảm 99%** — trận đánh toàn cầu bị loại |
| `dynasty` | 119 | **7** | **Giảm 94%** — triều đại ngoài Việt Nam bị loại |
| `place` | 77 | **77** | Không đổi |
| `house` | 9 | **9** | Không đổi — 9 triều đại đã verify |
| `event` | 1 | **0** | — |

> **Điểm quan trọng:** `person` (832) và `place` (77) **không đổi** → T5 chỉ loại đúng nhóm
> tín hiệu bị lẫn, không đụng vào nhóm tín hiệu đã gắn Việt Nam. Đây là bằng chứng rằng
> T5 là bộ lọc **có chọn lọc**, không phải cắt từng cơ bản.

### 4.3 Tín hiệu Wikidata thô (trước khi lọc theo bài)

Tổng 3.786 entry trong `wikidata_seed_articles.json`:

| Tín hiệu | Số entry | Khoảng năm |
|---|---|---|
| `person` | 3.193 | 10 – 1949 |
| `battle` | 385 | 194 – 1944 |
| `dynasty` | 121 | 35 – 1976 |
| `place` | 77 | 192 – 1899 |
| `house` | 9 | 939 – 1802 (đúng 9 triều đại) |
| `event` | 1 | 1941 |

Chênh lệch giữa 3.786 entry và 930 bài giữ cuối cùng là do: nhiều entry không có bài
trong dump (redirect/trùng), nhiều bài không có category phạm vi, và các bài trùng với
T1/T2/T3 chỉ được tính 1 lần theo `keep_reason` ưu tiên.

---

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Số bài trong `documents.jsonl` | 2.000–5.000 | **2.441** | ✅ |
| Tổng trang đã quét | — | 2.255.249 | — |
| Bài có `doc_id`/`title`/`url`/`keep_reason`/`dump_version`/`wikitext` | 100% | **100%** | ✅ |
| `doc_id` khớp `page_id` | 100% | **100%** | ✅ |
| Bài có `wikibase_item` (QID) | ≥ 80% | **97,3%** (2.375/2.441) | ✅ |
| `infobox_type` có đủ `person`/`battle`/`dynasty`/`place` | đủ 4 | `person` 1.061 · `battle` 202 · `place` 150 · `dynasty` 16 · `event` 11 · `none` 1.001 | ✅ |
| Bài có `wikitext` rỗng | 0 | **0** | ✅ |
| RAM peak | < 4 GB | **≈ 1,16 GB** (1.211.772 kB) | ✅ |
| Checksum 2 lần chạy | giống hệt | **IDENTICAL** (`b04dd858…12de19`) | ✅ |
| Thời gian chạy | — | 31:08 | — |
| Số test | pass | **107 passed** (gồm 7 test T5 trong `tests/test_filter_scope.py`) | ✅ |

### Kiểm tra chất lượng bằng mẫu ngẫu nhiên (seed 99)

25 bài ngẫu nhiên trong corpus cuối: `Trận Bạch Đằng (938)`, `Đền Trần Thương`,
`Cung Diên Thổ`, `Hiếu Trang Duệ Hoàng hậu`, `Nguyễn Hữu Tiến`, `Trương Đình Dụ`,
`Phan Văn Trường`, `Dương Văn An`, `Lịch sử chiến tranh Trung Quốc – Việt Nam`,
`Anh hùng dân tộc Việt Nam`… — **25/25 đúng phạm vi**.

---

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| Cây category mở rộng trả về **0** subcategory | Chỉ 11 category, 1.285 trang, T1 giữ ~0 bài | Trộn `page_id` với `lt_id`: `categorylinks.cl_from` là `page_id` của trang category, còn `cl_target_id` là `lt_id` trong bảng `linktarget` | Dựng ánh xạ cha–con theo `normalize_name(parent_title)` | **Schema MediaWiki tách bảng.** Đọc tên cột là chưa đủ — phải biết cột đó tham chiếu bảng nào |
| Regex SQL không nhận dòng kết thúc bằng `;` | Cây category thiếu nhánh | Chỉ khớp dòng kết thúc bằng `,` | Chấp nhận cả `,` và `;` | Dữ liệu SQL dump có nhiều biến thể kết thúc dòng |
| `normalize_infobox_type` khớp tiền tố | `tranh` → nhận nhầm `battle`; `nha nhac` → nhận nhầm `dynasty` | Bảng `INFOBOX_TYPE_MAP` có khoá là tiền tố của nhau | Ưu tiên khớp chính xác; chỉ khớp tiền tố khi khoá ≥ 4 ký tự và không trùng khoá khác | Từ khoá tiếng Việt không có dấu phân cách (`tranh`/`trận`, `nha`/`nhà`) → phải cẩn thận khi khớp chuỗi |
| 3.113 bài, ~35% nằm ngoài phạm Việt Nam | Trận Stalingrad, Chiến tranh Afghanistan, Nhà Ptolemaios… | Tín hiệu Wikidata `battle`/`dynasty` là toàn cầu; `P17`/`P276`/`P131` trả **0 dòng** cho trận đánh | Thêm tầng T5 dựa trên category phạm vi | **"Có bản tiếng Việt" ≠ "lịch sử Việt Nam".** Cần một tầng chốt phạm vi riêng, không dựa vào tín hiệu có sẵn |
| `pysbd.Segmenter(language=pysbd.Language.MULTI)` lỗi | `AttributeError` | `pysbd` 0.3.4 không có `Language.MULTI` (chỉ 23 ngôn ngữ, không có tiếng Việt) | Dùng `pysbd.Segmenter(language="en", clean=False, char_span=True)` — dấu kết thúc câu `.`/`!`/`?`/`…` giống nhau và tiếng Việt không có dấu phẩy cuối câu | Bộ quy tắc tách câu theo **dấu câu** đa số ngôn ngữ không có dấu hạt giống nhau → dùng chung bộ quy tắc được |
| Wikitext thật có link lồng nhau và link hỏng ngoặc | Còn ký tự `]]` rác trong `clean_text` | Regex phẳng không theo dõi độ sâu ngoặc: `[[Tập tin:X.jpg|nhỏ|[[A]] và [[B]]]]`, `[[23 tháng 9 năm 1945 … [[C]]` | Bộ quét cân bằng ngoặc `_find_link_end` + thay thế nhiều vòng theo link trong cùng `_innermost_links`; thêm `_strip_stray_markers` dọn `|nhãn]]` | Wikitext thật **không** tuân theo grammar đều — cần parser đo theo cân bằng ngoặc, không phải regex |

---

## 7. Bài học kinh nghiệm

1. **Phải có tầng "chốt phạm vi" riêng.** Tín hiệu lịch sử (Wikidata, infobox, category)
   đều trả lời câu hỏi *"đây có phải là một thực thể lịch sử?"*, **không** trả lời
   *"lịch sử của quốc gia nào?"*. T5 là câu trả lời cho câu hỏi thứ hai, và nó nâng
   tỉ lệ bài hợp lệ từ 73,3% → **96,7%**.
2. **Khi không sửa được truy vấn thì lọc ở tầng khác.** `P17` trả 0 dòng cho trận đánh
   → đừng cố thêm `P17`/`P276`/`P131`; chuyển sang dùng category.
3. **Số liệu trước/sau là bằng chứng mạnh hơn "đã sửa".** Bảng §4.2 cho thấy `person`
   và `place` **không đổi** trong khi `battle` giảm 99% → chứng minh bộ lọc có chọn lọc.
4. **Bảng tra trong dump SQL có thể sai mà không báo lỗi.** Sai khoá dẫn tới kết quả
   "0" — mà 0 trông rất giống "không có dữ liệu". Phải đối chiếu kỳ vọng (81 category,
   1.285 trang) mới phát hiện.
5. **Tất định là tính năng, không phải may mắn.** Checksum 2 lần chạy giống hệt là bằng
   chứng cho nguyên tắc tái lập — và là điều kiện tiên quyết để mọi số liệu đo ở phase sau
   có giá trị so sánh.
6. **Tách offline/online ngay từ Phase 1.** Toàn bộ việc nặng (quét 2,25 triệu trang,
   ghi 325 MB `dump_facts.jsonl`) nằm ở tầng offline, sinh artifact JSONL; tầng online
   sau này chỉ đọc artifact.

---

## 8. Ý tưởng cho slide

- **Từ 2.255.249 trang dump → 2.441 bài lịch sử Việt Nam**, QID coverage **97,3%**,
  RAM peak **1,16 GB**, chạy **31 phút**, checksum 2 lần **IDENTICAL**.
- **Bộ lọc 5 tầng T0–T5:** T0 Wikidata (930) · T1 category (933) · T2 infobox (302) ·
  T3 mở rộng BFS (276) · T5 chốt phạm vi Việt Nam.
- **Tầng T5 là bài học lớn nhất:** không có nó, **~35% corpus nằm ngoài phạm vi**
  (Trận Stalingrad, Nhà Ptolemaios…). Có nó: bài hợp lệ **73,3% → 96,7%**.
- **Số liệu "không đổi" cũng là số liệu:** tín hiệu `person` (832) và `place` (77)
  **giữ nguyên 100%** → bộ lọc loại đúng nhóm nhiễu, không hy sinh bài hợp lệ.
- **4 lỗi thật đã sửa, mỗi lỗi là một bài học:** khoá cây category theo `lt_id`
  (→0 subcategory), khớp tiền tố loại infobox, `pysbd` không có `Language.MULTI`,
  wikitext có link lồng nhau/link hỏng ngoặc.
- **Thang lọc nhiễu 4 phương án:** A 3.113 → B 2.606 → C 2.250 → D 2.331 → **thực hiện 2.441**;
  C siết quá tay, D mở lại nhóm "nhà vua".

---

## 9. Việc tiếp theo

**Phase 2 — Làm sạch wikitext, tách câu/đoạn, trích hyperlink có offset ký tự chính xác.**
Code đã sẵn sàng (`src/preprocess/clean_text.py`, `src/preprocess/split_sentences.py`),
đã sửa D-013 và D-014. Chi tiết ở `docs/09-ke-hoach-thuc-thien.md` → "Phase 2".

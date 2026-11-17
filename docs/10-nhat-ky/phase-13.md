# Phase 13 — Sửa chất lượng: entity linking exact-case, chiều đảo quan hệ, lọc cạnh nhiễu KG

- Ngày: 17/11/2026
- Trạng thái: ✅ đạt Gate (12/12 ca lỗi người dùng báo → hết · 0 regression · KG không đổi 19.548/13.379)
- Báo cáo Gate: `reports/phase_13_report.md`
- Số liệu máy đọc: `docs/10-nhat-ky/so-lieu/phase-13-chat-luong-kien-thuc.json`

## 1. Bối cảnh và vấn đề cần giải

Demo ngày 16/11/2026, người dùng báo 3 triệu chứng:

| # | Triệu chứng | Nguyên nhân gốc đã xác minh |
|---|---|---|
| 1 | "Ai là **con** của Trần Nhân Tông" không được, chỉ "ai là **cha**" mới được | Quan hệ lưu **một chiều** (`cha_cua`: subject=cha) — prompt chỉ có few-shot chiều thuận |
| 2 | "17 đời vua triều Lê" → map `tiết`→Tiết, `đời`→Đổi; "bao nhiêu đời vua" → `bao`→Bảo | Lớp khớp **giữ dấu** không kiểm chữ hoa; alias 1 từ chưa bị loại hết |
| 3 | Nhiều lần trả "không có dữ liệu" | Không có tầng truy xuất văn bản (sẽ xử lý ở Phase 14) |

Ngoài ra, đối chiếu trực tiếp với artifact thật phát hiện 2 lỗi chất lượng nghiêm trọng hơn:

- **"Đổi mới đất nước" → entity "Đổi Mới"** (`ent_doi_moi_1b2ad4f7`)
- **"Ông ấy" → `ent_george_h_5df82ed5`** (coref gom bề mặt đại từ làm tên entity ⇒ "ông ấy" trỏ về George H. W. Bush)

Và 1 lỗi **ngữ nghĩa KG**:

- `Trần Hưng Đạo -mat_tai-> Quốc lộ 14` (11 cạnh tương tự) — "Quốc lộ 14" là hạ tầng giao thông, không phải nơi người ta mất.

Ràng buộc: Phase 13 là **tiền điều kiện** cho Phase 14/15 (RAG + Hybrid). Sửa entity linking sai thì RAG cũng hỏng. Nhưng Gate của phase này là *"KG không đổi"* (19.548 node / 13.379 cạnh) — tức **không được nạp lại DB**, chỉ sửa ở tầng ứng dụng.

## 2. Phương án đã cân nhắc

### 2.1 Sửa false-positive entity linking

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A. Exact-case ở lớp giữ dấu** | Khớp case-sensitive trên `text` gốc, mỗi từ trong span phải viết hoa đúng như bề mặt alias (trừ từ chức năng `LOWERCASE_OK_WORDS`) | "Đổi mới đất nước" → 0 match; "Ông ấy" → 0 match; "Trần Hưng Đạo"/"triều Lê"/"Trần Nhân Tông" → vẫn khớp | ✅ | Sửa đúng nguyên nhân gốc, giữ nguyên lớp dự phòng bỏ dấu |
| B. Chỉ kiểm tra chữ hoa từ đầu | `_capitalization_ok` cho lớp giữ dấu | "Đổi mới đất nước" → vẫn khớp "Đổi Mới" (chữ "mới" thường nhưng alias "Đổi Mới" cũng có 1 từ thường → lọt) | ❌ | Không đủ |
| C. Chỉ loại alias toàn-chữ-thường | Bỏ alias mà mọi bề mặt đều viết thường | Fix được "ông ấy" nhưng **không** fix "Đổi mới đất nước" (alias "Đổi Mới" viết hoa) | ⚠️ | Chỉ là nửa vấn đề |
| **D. A + C + chặn đại từ** | Exact-case + loại 176 alias toàn-chữ-thường + 42 bề mặt đại từ | 0 false positive trong 12 ca regression | ✅ | 3 lớp độc lập, mỗi lớp bắt một nhóm lỗi |

### 2.2 Lọc cạnh nhiễu KG

Đo trên Neo4j thật: 3.518 cạnh có object là địa danh.

| Phương án | Số cạnh bị lo | Chọn? | Lý do |
|---|---|---|---|
| A. Loại object không có QID | **1.405** (40%) | ❌ | Quá rộng — loại cả "Nghi Lộc (huyện)", "Thái Bình", "Phú Xuân" là địa danh **hợp lệ** |
| B. Loại object có nhãn ≠ `Place` | **126** | ❌ | Loại nhầm "Đại Việt" (nhãn `Event`) — là nơi sinh hợp lệ của nhiều vua |
| **C. Loại theo tên hạ tầng/cơ quan** + tên rác (nhãn `Entity`) | **23** (0,65%) | ✅ | Chính xác theo ngữ nghĩa: 11 "Quốc lộ 14" + 2 "Bệnh viện …" + 10 tên rác do LLM sinh |

### 2.3 Xử lý câu hỏi không có entity (đại từ)

| Phương án | Chọn? | Lý do |
|---|---|---|
| A. Để LLM tự sinh Cypher rộng | ❌ | Trả về 10–50 người **ngẫu nhiên** ⇒ có cảm giác "có dữ liệu" nhưng hoàn toàn không liên quan (vi phạm nguyên tắc #3) |
| B. Chặn ở tầng ứng dụng: Cypher phải lọc theo **giá trị cụ thể** | ✅ | `IS NOT NULL` không đủ (LLM hay dùng) — phải là `entity_id` / so sánh số / so sánh chuỗi / `CONTAINS` / `IN` / `COUNT` |
| C. Sửa ở prompt | ⚠️ | LLM vẫn sinh câu rộng khi không có entity — không đáng tin |

## 3. Quyết định đã chốt

**D-095 — Lọc cạnh nhiễu ở TẦNG ĐỌC, không xoá khỏi Neo4j**

- **Lý do:** Gate Phase 13 yêu cầu KG không đổi (19.548/13.379). Xoá cạnh sẽ phá vỡ khả năng tái lập artifact và mất dấu vết để audit.
- **Ảnh hưởng:** mọi kênh KG (Text-to-Cypher cũ + Hybrid Phase 15) phải đi qua `filter_noisy_edges` / `filter_noisy_records` hoặc điều kiện Cypher `noisy_edge_cypher_filter()`.
- **File đã cập nhật:** `src/graph/noise_filter.py` (mới), `backend/app/services/text_to_cypher.py`.

**D-096 — Exact-case ở lớp khớp giữ dấu + chặn alias toàn-chữ-thường + chặn đại từ**

- **Lý do:** 3 nhóm lỗi độc lập, cùng triệu chứng "link sai entity".
- **Ảnh hưởng:** alias index giảm 13.760 → 13.582 (−178). Chỉ mục entity **không** bị sửa ⇒ Phase 9/10 không cần nạp lại.
- **File đã cập nhật:** `backend/app/services/entity_linker.py`.

**D-097 — Bảng chiều đảo quan hệ trong prompt + 6 few-shot ngược**

- **Lý do:** đảo chiều bằng Cypher đã verify 5/5 con đúng; thêm vào prompt rẻ hơn nhiều so với LLM tự suy luận.
- **File đã cập nhật:** `backend/app/prompts/text_to_cypher.txt`.

**D-098 — Guard "Cypher không lọc theo giá trị cụ thể" ⇒ `not_in_data`**

- **Lý do:** chặn hiện tượng "trả 10 người ngẫu nhiên" khi câu hỏi dùng đại từ.
- **Ảnh hưởng:** câu hỏi đại từ (chưa có session) trả "Không có trong dữ liệu" kèm hướng dẫn, **không** retry (tiết kiệm quota LLM).
- **File đã cập nhật:** `backend/app/services/cypher_validator.py`, `backend/app/services/text_to_cypher.py`.

## 4. Thang số liệu so sánh

### 4.1 Entity linking: trước vs sau

| Chỉ số | Trước | Sau | Nguồn |
|---|---|---|---|
| Alias trong chỉ mục | 13.760 | 13.582 | log `Entity linker:` |
| Alias ≥ 2 từ toàn-chữ-thường | 211 | **0** | `test_no_all_lowercase_multiword_alias_in_index` |
| Alias đại từ | 2 ("ông ấy", "ông ta") | **0** | `test_pronoun_aliases_removed_from_index` |
| False positive "Đổi mới đất nước" | 1 (→ "Đổi Mới") | **0** | `test_case03` |
| False positive "Ông ấy" | 1 (→ George H. W. Bush) | **0** | `test_case04` |
| True positive "Trần Hưng Đạo" | ✓ | ✓ | `test_true_positives_preserved` |
| True positive "triều Lê" | ✓ | ✓ | `test_case01/02` |
| True positive "Le Loi" (không dấu) | ✓ | ✓ | `test_case10` |

### 4.2 Lọc cạnh nhiễu: 3 phương án

| Phương án | Cạnh bị lo | % trong 3.518 | Địa danh hợp lệ bị lo nhầm |
|---|---|---|---|
| A. Không có QID | 1.405 | 39,96% | "Nghi Lộc (huyện)", "Thái Bình", "Phú Xuân"… |
| B. Nhãn ≠ `Place` | 126 | 3,58% | "Đại Việt" (nơi sinh của nhiều vua) |
| **C. Tên hạ tầng + tên rác** | **23** | **0,65%** | **0** |

### 4.3 Guard Cypher: trước vs sau

| Câu hỏi | Trước | Sau |
|---|---|---|
| "Ông ấy mất năm nào?" | `found` — trả 10 người ngẫu nhiên (Quang Trung 1792, Lý Thái Tổ 1028…) | `not_in_data` + hướng dẫn nêu tên cụ thể |
| "Vị vua đó mất năm nào?" | `found` — trả 50 người | `not_in_data` |
| "Ai là con của Trần Nhân Tông?" | không đúng chiều | `found` — **5 con đúng** |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| 12 ca lỗi người dùng báo → hết | 12/12 | **19/19 test pass** (12 ca lỗi + 7 test bổ trợ) | ✅ |
| Regression | 0 | **0** (`pytest -q tests/` → 644 pass, 0 fail) | ✅ |
| KG không đổi | 19.548 node / 13.379 cạnh | **19.548 / 13.379** | ✅ |
| Cạnh nhiễu vào context KG | 0 | **0** (23 cạnh bị lo ở tầng đọc) | ✅ |
| Câu hỏi đảo chiều | 5/5 đúng | **5/5** (verify trực tiếp trên Neo4j) | ✅ |
| Câu hỏi đại từ không bịa | trả `not_in_data` | **`not_in_data`** | ✅ |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| Test case 7c fail lần 1 | `assert 3 == 2` — bộ lọc **không** loại "Vạn Kiếp" | Tôi tưởng "Vạn Kiếp" là nhiễu, nhưng đó là nơi Trần Hưng Đạo mất — **địa danh hợp lệ** | Sửa lại kỳ vọng test + ghi rõ trong docstring | **Đừng đoán "cái này là nhiễu" — phải kiểm tra ngữ nghĩa từng cạnh.** "Quốc lộ 14" mới là nhiễu |
| Guard v1 quá lỏng | LLM thêm `WHERE p.death_year IS NOT NULL` ⇒ vẫn lọt, vẫn trả 10 người | `IS NOT NULL` chỉ lọc "có giá trị", không định danh đối tượng | Siết `has_filtering_predicate()`: chỉ nhận lọc theo **giá trị cụ thể** | Điều kiện lọc phải **định danh được đối tượng**, không chỉ lọc theo "có/không null" |
| Guard v2 trả `status=error` | Người dùng thấy "Không tạo được truy vấn" thay vì "không có dữ liệu" | Sau 3 lần retry thất bại, `ask()` rơi vào nhánh `error` | Guard trả thẳng `not_in_data` + **không retry** (LLM lặp lại cùng dạng câu) | Khi đã biết câu hỏi không xác định được đối tượng, retry là **lãng phí quota** |
| Bộ lọc theo nhãn loại nhầm "Đại Việt" | 126 cạnh bị lo, gồm nơi sinh hợp lệ | `Đại Việt` bị gán nhãn `Event` trong KG | Chỉ loại nhãn `Entity` (tên rác LLM), giữ `Event` | **Nhãn node trong KG có nhiễu** — đừng tin nhãn một cách mù quáng |
| Log "176 alias toàn-chữ-thường" khác 211 đếm được | Lệch 35 | Bộ đếm ban đầu đếm *mọi* alias ≥ 2 từ có ≥ 1 bề mặt thường (3.863); bộ lọc thực tế chỉ loại alias mà **mọi** bề mặt đều thường | Ghi rõ tiêu chí đếm trong docstring | Số liệu phải ghi rõ **định nghĩa**, nếu không sẽ so sánh sai |

## 7. Bài học kinh nghiệm

1. **Case-sensitivity là ranh giới quan trọng hơn fuzzy matching.** Bỏ dấu làm "chỉ" → "chi" trùng "Nguyễn Huệ Chi"; bỏ case làm "mới" → "Mới" trùng "Đổi Mới". Cả hai đều là **false positive âm thầm** — hệ thống trả lời *sai một cách thuyết phục*.
2. **Lỗi "link sai" nguy hiểm hơn "không link".** "Ông ấy" → George H. W. Bush còn tệ hơn là trả "không có trong dữ liệu": người dùng **không biết** mình đang bị bịa.
3. **Đại từ không phải entity.** Nó là *vị trí* cần điền vào từ ngữ cảnh hội thoại (Phase 15 — `conversation.py`), không phải thứ để tra cứu trong KG.
4. **Chất lượng KG và chất lượng *đọc* KG là hai đường.** Sửa ở tầng đọc giữ được tính tái lập của artifact; xoá trong DB thì mất dấu vết audit.
5. **Lọc theo "thiếu tín hiệu nhận dạng" (không QID) quá rộng.** Tín hiệu tốt phải gắn với **ngữ nghĩa sai** ("đây không phải nơi sinh/mất"), không phải với **dữ liệu thiếu**.
6. **Guard "không lọc theo giá trị cụ thể" là lớp phòng thủ rẻ và hiệu quả.** Chặn 1 dạng Cypher quét toàn đồ thị loại bỏ được cả lớp lỗi "trả N bản ghi ngẫu nhiên".

## 8. Ý tưởng cho slide

- **"Lỗi người dùng báo ≠ lỗi hệ thống có"** — 3 triệu chứng demo ⇒ 5 nguyên nhân gốc, tất cả đều kiểm chứng được trên artifact thật.
- **Sửa entity linking bằng 3 lớp, đo được từng lớp**: exact-case → 0 FP; loại 176 alias toàn-chữ-thường → 0 FP; chặn 42 đại từ → 0 FP. Chỉ số alias 13.760 → 13.582 (−1,3%).
- **Quan hệ lưu MỘT CHIỀU là nguyên nhân của câu hỏi "con của"**: bảng tra 19 dòng + 6 few-shot ngược ⇒ "Ai là con của Trần Nhân Tông" trả đúng **5/5**.
- **Lọc nhiễu: 3 phương án, chọn phương án ít tổn thương nhất**: 1.405 cạnh (theo QID) vs 126 (theo nhãn) vs **23** (theo ngữ nghĩa) — 0 địa danh hợp lệ bị lo nhầm.
- **Guard chống bịa**: trước "Ông ấy mất năm nào?" trả 10 người ngẫu nhiên ⇒ sau trả `not_in_data` + hướng dẫn.
- **Con số tổng**: 12/12 ca lỗi hết · 644 test pass 0 fail · KG giữ nguyên 19.548/13.379.

## 9. Việc tiếp theo

**Phase 14 — Vanilla RAG (nhánh A)**. Phase 13 đã dọn xong nền: entity linking đúng, Cypher đảo chiều đúng, cạnh nhiễu đã lọc. Bước tiếp theo là tạo **tầng truy xuất văn bản** để trả lời được câu hỏi tự sự ("diễn biến trận Bạch Đằng") — thứ mà KG thuần không làm được.

Trạng thái: ✅ Phase 13 đạt Gate, sẵn sàng Phase 14.

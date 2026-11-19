# Phase 19 — Trả lời đúng & có căn cứ, rồi đo lại A vs B vs B−

- Ngày: 19/11/2026
- Trạng thái: 🟡 **đạt 4/7 Gate**, eval đầy đủ đang chạy nền theo quota
- Báo cáo Gate: `reports/phase_19_report.md`
- Quyết định: `docs/DECISIONS.md` → D-142..D-145
- Sai lệch: `reports/deviations.md` (D-140, D-141)

## 1. Bối cảnh và vấn đề cần giải

Phase 18 (D-123/D-124) kết luận "Hybrid GraphRAG thắng Vanilla RAG trên nhóm
narrative" — nhưng **số liệu đảo chiều** giữa 2 lần chấm:

| Lần chấm | A | B | B− |
|---|---|---|---|
| D-123 | **1,733** | 1,717 | — |
| D-124 | 1,617 | **1,783** | 1,650 |

⇒ Chênh lệch Δ(B − A) đổi dấu ⇒ **không** kết luận được từ dữ liệu đó.

Phân tích Phase 19 tìm ra **3 artefact** làm sai lệch phép so sánh:

### 1.1 Arm A trả "Không có trong dữ liệu" **sai**

| Arm | Số câu trả "không có" (60 câu narrative) |
|---|---|
| A | **16** |
| B | **7** |
| B− | **14** |

Trong **7/16** câu mà A nói "không có", **gold section vẫn nằm trong top-8
context** ⇒ **lỗi ở tầng sinh**, không phải tầng truy xuất. Đây là lý do
`correctness` của A bị đẩy xuống ⇒ **điểm A thấp là do hệ thống, không phải do
thiếu KG**.

### 1.2 Section "di tích" chiếm chỗ trong top-8

BM25 cộng trọng số `title` ×3 cho **mọi** chunk của cùng bài ⇒ chunk
"Di tích lịch sử" (lặp tên bài trong body) đè chunk "Diễn biến" thật:

| Chỉ số (60 câu narrative) | Trước |
|---|---|
| TB chunk/section chiếm top-8 | **3,25** |
| Câu có gold section **không lọt** top-8 | **14/60** |

### 1.3 Bộ câu hỏi có lỗi **kỹ thuật** làm `expected_answer` không nhất quán

- **4.a** 7/60 câu narrative gộp chunk theo `doc_id` ⇒ gộp **nhiều section**
  khác nhau ⇒ `expected_answer` tham chiếu **không nhất quán** ⇒ judge chấm
  lung tung.
- **4.b** `rng.shuffle()` ngay sau `sort()` ⇒ xoá thứ tự ưu tiên khi chọn câu.
- **4.c** `NO_DATA_TOPICS` toàn "Cách tập luyện cơ bắp / món gà nướng than"
  (không liên quan lịch sử, quá dễ) ⇒ không đo được khả năng **không bịa ngoài
  phạm vi**.

## 2. Cách tiếp cận đã chọn

| Vấn đề | Phương án cân nhắc | Chọn? | Lý do |
|---|---|---|---|
| Tầng truy xuất | (a) hạ BM25 `title` ×3; (b) cap chunk/section + boost tiêu đề/section + chống nhiễu | ✅ (b) | (a) không phân biệt được chunk nào trong bài đúng ý nghĩa ⇒ nguyên nhân gốc |
| LLM nói "không có" khi context có dữ liệu | (a) chấp nhận; (b) retry bắt buộc | ✅ (b) | 7/16 câu là lỗi tầng sinh ⇒ sửa đúng chỗ |
| Phạm vi bộ câu hỏi | (a) lọc 9 triều đại; (b) giữ hết + kiểm chứng online | ✅ (b) | Chỉ đạo mới: *"không cần quá chuẩn về việc có nằm trong khoảng không; sau này mở rộng thêm dữ liệu"* |
| Kiểm chứng "không bịa" | (a) tin LLM-judge; (b) tra Wikipedia/Wikidata live | ✅ (b) | *"câu hỏi và câu trả lời judge cần phải tra mạng và kiểm chứng chính xác, chức không được nghĩ và bịa ra đâu đấy"* |
| Đo grounding | (a) để LLM-judge chấm; (b) đo bằng **code** (trùng token mệnh đề ↔ chunk đã trích dẫn) | ✅ (b) | Tương đối với "không tin LLM nói đúng" |

## 3. Bảng so sánh cấu hình retrieval (60 câu narrative, gold = `evidence_section`)

Đo offline, **không** tốn quota:

| Cấu hình | gold section trong top-8 |
|---|---|
| `cap=8`, không boost (cũ) | 43/60 |
| `cap=2`, không boost | 49/60 |
| `cap=2` + `title_boost=1.0` | 53/60 |
| **`cap=2` + `title_boost=1.0` + `section_boost=1.0`** | **57/60** |
| **`cap=2` + `title_boost` + `section_boost` + `noise_penalty=0.5`** | **57/60** (giữ chống nhiễu) |

Kế hoạch dự đoán `cap=2 + title_boost=1.0` cho 54/60 ⇒ đo thực tế **tốt hơn**
nhờ thêm `section_boost` (boost section có tên khớp câu hỏi: "Kể lại diễn biến
X" ⇒ section "Diễn biến").

## 4. Số liệu sau khi sửa

### 4.1 G19-2 — gold section trong top-8 (bộ `qa_rag_250_v2.jsonl`)

| Nhóm | Hit | Tỉ lệ | Ghi chú |
|---|---|---|---|
| `narrative` | **55/60** | 91,7 % | ✅ G19-2 (cần ≥ 55/60); trước **46/60** |
| `multi_hop` | 34/40 | 85 % | |
| `relational` | 43/58 | 74,1 % | |
| `multi_turn` | 24/58 | 41,4 % | *đúng kỳ vọng* — lượt sau là đại từ ⇒ cần query rewriting |
| `no_data` | 0/30 | 0 % | *đúng kỳ vọng* — ngoài corpus |

TB số section khác nhau trong top-8: **3,06**.

### 4.2 G19-7 — câu hỏi hợp lệ (kiểm chứng live)

**0/246** câu hỏi không hợp lệ (kiểm chứng **toàn bộ** bộ eval, không chỉ
`narrative` + `multi_turn`) ⇒ **không** loại câu hỏi nào vì lý do phạm vi.

| Nhóm | Số câu | Kiểm chứng | Kết quả |
|---|---|---|---|
| `narrative` | 60 | mọi năm trong `expected_answer` phải có trong Wikipedia live | 60/60 ✅ |
| `multi_turn` | 58 | như trên | 58/58 ✅ |
| `relational` | 58 | `Special:EntityData/<QID>.json` (Wikidata live) | 58/58 ✅ |
| `multi_hop` | 40 | như trên | 40/40 ✅ |
| `no_data` | 30 | ngoài phạm vi corpus (hậu-1945) | 30/30 ✅ |

Tổng **98 mệnh đề quan hệ** được đối chiếu trực tiếp với Wikidata live ⇒ 0 sai.

### 4.3 G19-6 — câu trả lời không bịa

Trên checkpoint (131 câu × 3 arm = **336** câu trả lời có nội dung): **0** câu có
năm không có trong Wikipedia live, **0** vi phạm `no_data`.

### 4.4 A vs B vs B−

Xem `reports/phase_19_report.md` §3.4. Checkpoint đang chạy: **131/246** câu.

| Nhóm | A | B | B− | Ghi chú |
|---|---|---|---|---|
| `narrative` (n=52) | **1,942** | 1,904 | **1,942** | KG **không** tạo lợi thế |
| `relational` (n=57) | 1,404 | **1,807** | 1,298 | KG rõ ràng có ích |
| `multi_hop` (n=22) | 1,091 | **1,545** | 1,273 | KG có ích |

**G19-1 đạt trên `narrative`**: `not_in_data` của A: **16/60 → 2/52**;
`abstain_with_evidence` = **0** (cả 3 arm) ⇒ không câu nào nói "không có" khi
context thật sự có đáp án.

**Hiện CHƯA kết luận được** trên `narrative` — còn thiếu 8 câu `narrative`, toàn bộ
`multi_turn` (58) và `no_data` (30) (quota Gemini RPD 500/model/ngày).

### 4.5 Bài học mới: **công cụ kiểm chứng cũng phải được kiểm chứng**

Lần chạy đầu của `verify_answers_online.py` báo 4 câu trả lời "bịa số năm". Điều tra
cho thấy **cả 4 là false negative của chính script** (D-146):

1. Khoá cache dùng `_norm()` (bỏ dấu) ⇒ "Lê Hiển Tông" va chạm "Lê Hiến Tông".
2. Chỉ so năm với `evidence_doc_id`, bỏ qua các nguồn đã trích dẫn (KG/text).

⇒ Mọi cờ "bịa" phải được **đối chiếu thủ công** với nguồn trước khi tin.

### 4.6 Bài học mới: **giả định về phạm vi corpus phải được đo**

D-142 giả định "corpus chỉ phủ 9 triều đại ⇒ chủ đề hậu-1945 chắc chắn ngoài
phạm vi". **Giả định này sai**: corpus phủ **toàn bộ** lịch sử VN (đến 2026) ⇒
**33/37** chủ đề `no_data` của bộ v2 thực ra **có** trong corpus ⇒ đo sai khả năng
"không bịa ngoài phạm vi".

⇒ Bộ v3 thay 30 câu `no_data` (216 câu còn lại giữ nguyên) + builder tự động loại
chủ đề trùng corpus (D-148).

## 5. Sai ở đâu (bài học)

1. **Số liệu đảo chiều giữa 2 lần chấm = dấu hiệu artefact, không phải nhiễu
   nhỏ.** Phải truy ngược về *tầng* trước khi truy ngược về *mô hình*.
2. **Điểm thấp của arm A có thể do chính hệ thống A** (trả "không có" sai),
   không phải do thiếu KG ⇒ so sánh "KG có ích không" mà chưa sửa lỗi tầng sinh
   là so sánh **giữa hai lỗi**, không phải giữa hai hệ thống.
3. **Truy xuất có "artefact dữ liệu"**: `title` ×3 ở tầng BM25 là doc-level ⇒ mọi
   chunk của bài nhận cùng điểm ⇒ chunk nhiễu (lặp tên bài) đè chunk nội dung.
4. **LLM trả chuỗi rỗng ≠ "không có trong dữ liệu"** — phải retry, không được
   mặc định.
5. **Kiểm chứng bằng LLM không phải kiểm chứng.** Chỉ tra nguồn ngoài live mới
   loại được "bịa số năm" / "quan hệ sai".
6. **Bind-mount container giữ inode cũ** ⇒ sau khi repo di chuyển, container vẫn
   ghi vào thư mục **đã bị xoá** ⇒ phải `--force-recreate` + đồng bộ code (image
   `COPY` code ⇒ cần `build` khi code đổi).
7. **Công cụ kiểm chứng cũng có bug** ⇒ mọi cờ "bịa" phải đối chiếu thủ công với
   nguồn trước khi tin (xem §4.5).

## 6. Kết luận lấy vào slide

- **"Trước khi nói KG hay không KG, phải sửa retrieval và sửa tầng sinh."**
- Sửa retrieval: gold section trong top-8 **46/60 → 55/60**; thêm retry "không
  có" khi context có dữ liệu.
- **Kiểm chứng bằng nguồn ngoài live**: **0/246** câu hỏi vô lý (98 mệnh đề Wikidata
  đối chiếu khớp tuyệt đối); **0** câu trả lời bịa số năm.
- Số liệu A vs B vs B− **chốt sau** khi eval đủ 246 câu — hiện **không kết luận
  được**, và đó là kết luận trung thực.
- **Tạm thời** (131/246 câu): KG **có ích rõ** trên `relational` (1,807 vs 1,404 vs
  1,298) và `multi_hop` (1,545 vs 1,091 vs 1,273); **không** thấy lợi thế trên
  `narrative` (1,942 ≈ 1,904 ≈ 1,942).

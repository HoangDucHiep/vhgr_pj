# 01 — Đặc tả yêu cầu chức năng

Mỗi yêu cầu có: **Mô tả** → **Tiêu chí nghiệm thu (AC)** → **Ưu tiên** → **Module liên quan**.
Mức ưu tiên: **M** = bắt buộc (MVP) · **S** = nên có (mở rộng) · **C** = có thì tốt.

---

## Module A — Thu thập và tiền xử lý dữ liậu

### A1. Tải, đọc và lọc dump Wikipedia tiếng Việt (M)

**Mô tả**
- Tải dump `viwiki-latest-pages-articles.xml.bz2` (hoặc `pages-articles-multistream`) từ `dumps.wikimedia.org/viwiki/latest/`.
- Đọc theo luồng (streaming) bằng `mwparser` / `wikitextparser` để không nạp toàn bộ vào RAM.
- Lọc bài theo phạm vi lịch sử bằng **nhiều tín hiệu kết hợp**:
  1. **Category** (độ tin cậy cao): `Thời đại ...`, `Vua ...`, `Trận đánh ...`, `Địa danh ...`, `Dòng họ ...`.
  2. **Infobox**: `loại_infobox` ∈ {`person`, `person infobox`, `triều đại`, `trận đánh`, `sự kiện`, `địa danh`} hoặc có trường `sinh`, `mất`, `triều đại`, `thời gian`.
  3. **Danh sách bài hạt giống (seed list)**: tập bài bắt đầu từ các bài triều đại, mở rộng theo đồ thị liên kết nội bộ (BFS) đến giới hạn độ sâu mong muốn.
- Lưu danh sách bài đã lọc kèm **vì sao bị giữ** (`keep_reason`: `category` | `infobox` | `seed_expansion` | `manual`), để kiểm tra độ bao phủ.

**AC**
- Chạy script tải + lọc tạo ra file `data/processed/documents.jsonl` với ≥ 2.000 bài và ≤ 5.000 bài.
- Mỗi bài có: `page_id`, `title`, `url`, `wikitext` (đã giữ), `categories`, `infobox_type`, `keep_reason`, `revision_id`.
- Chạy lại trên cùng dump cho kết quả giống hệt (byte-level hoặc theo checksum nội dung).
- Có thể chạy lại một phần bằng cờ `--resume` mà không tải lại toàn bộ.

**Đầu ra:** `data/processed/documents.jsonl`

---

### A2. Làm sạch wikitext (M)

**Mô tả**
- Bỏ: tham chiếu `<ref>...</ref>`, file/ảnh `[[File:...]]`, bảng `{| ... |}`, `{{cite web}}`, `{{Infobox ...}}` (nhưng **trích xuất infobox trước** theo A4), category link `[[Thể loại:...]]`, wiki cú pháp lạ, HTML, thẻ `<br>`, comment.
- Giữ lại: hyperlink nội bộ `[[Tên bài|hiển thị]]` (dùng làm nhãn silver cho B2/E1), tiêu đề mục `== ... ==`, câu văn xuôi.
- Chuẩn hóa khoảng trắng, bỏ dòng trống, gộp câu bị vỡ.

**AC**
- Văn bản sau làm sạch không còn `{{`, `}}`, `<ref`, `[[File:`, `[[Thể loại:`.
- Tỉ lệ hyperlink nội bộ được giữ lại ≥ 95% so với bản gốc (sau khi loại File và Thể loại).
- Câu trong văn bản sau làm sạch không chứa ký tự wiki còn sót.

**Đầu ra:** trường `clean_text` trong `documents.jsonl`

---

### A3. Tách câu và tách đoạn tiếng Việt (M)

**Mô tả**
- Tách câu: ưu tiên `pysbd` (rule-based, không cần model, hỗ trợ tiếng Việt) → fallback `underthesea`. Dùng `underthesea` cho **tách đoạn/đoạn văn**.
- Chuẩn hóa câu: bỏ khoảng trắng thừa, giữ dấu câu kết thúc, xử lý dấu ngoặc kép.

**AC**
- ≥ 95% câu kết thúc bằng dấu `.`, `!`, `?` hoặc `…`.
- Văn bản không bị vỡ câu ở giữa tên riêng có dấu phẩy (kiểm thử bằng tập mẫu cố định gồm tên nhân vật có dấu).

**Đầu ra:** `sentences: [{id, text, para_idx, sent_idx, char_start, char_end}]` và `paragraphs: [...]` trong mỗi document.

---

### A4. Trích thông tin có cấu trúc từ infobox (M)

**Mô tả**
- Parse `{{Infobox ...}}` (và biến thể `{{Thông tin ...}}`) thành dict phẳng: `key → value`.
- Trích các trường quan tâm thành **nguồn nhãn đầu vào** cho RE:
  - Nhân vật: `sinh`, `mất`, `cha`, `mẹ`, `vợ`/`chồng`/`phu quân`, `con`, `tiền đình`/`hậu thân`, `nghề nghiệp`/`chức vụ`, `triều đại`, `quốc gia`, `tôn`, `miếu hiệu`, `thụy hiệu`, `niên hiệu`, `thành viên`.
  - Trận đánh/sự kiện: `ngày`, `thời gian`, `địa điểm`, `bên tham chiến`, `kết quả`, `thua trận`.
  - Triều đại: `thành lập`, `sơ khai`, `kết thúc`, `thủ đô`, `thống trị`.
- Chuẩn hóa ngày tháng văn bản Việt Nam ("ngày 15 tháng 3 năm 1028") về ISO `YYYY-MM-DD` hoặc `YYYY` khi chỉ có năm.
- **Gắn nhãn từ infobox phải kèm nguồn cụ thể**: `evidence_sentence` = phần text trong infobox đã sinh câu, `source_url`, `method = "infobox"`, `confidence = 1.0` (nhãn từ infobox có độ tin cậy cao nhất).

**AC**
- Parse ≥ 95% số infobox của các bài nhân vật có infobox `person` trong tập lọc.
- ≥ 90% infobox nhân vật có ít nhất một trường ngày sinh/mất hoặc quan hệ gia đình được trích ra.
- Chuẩn hóa ngày đúng ≥ 95% trên tập kiểm thử gồm 30 chuỗi ngày rời rạc.
- Mọi triple sinh từ infobox có `method = "infobox"`, `confidence ≥ 0.95`.

**Đầu ra:** `data/interim/infobox_triples.jsonl`

---

### A5. Lưu metadata mỗi câu (S)

**Mô tả**
- Mỗi câu được gán: `doc_id` (page_id), `doc_title`, `url`, `paragraph_idx`, `sentence_idx`, `char_start`, `char_end`, `dump_version`, `extracted_at`.
- `dump_version` = nhãn phiên bản dump (ví dụ `20251101`) để tái lập kết quả.

**AC**
- Mọi triple đều dằng dẫn được tới `doc_id` + `sentence_id` cụ thể.
- Từ một triple, tra cứu ngược ra câu nguồn đầy đủ (văn bản, tiêu đề bài, URL) trong ≤ 1 giây.

---

## Module B — Nhận diện thực thể (NER)

### B1. Các loại thực thể (M)

**Mô tả**
Hệ thống hỗ trợ 6 lớp thực thể:

| Nhãn | Mô tả | Ví dụ |
|---|---|---|
| `PERSON` | Nhân vật lịch sử | Lê Lợi, Nguyễn Trung Trực |
| `DYNASTY` | Triều đại / dòng họ | nhà Hồ, nhà Trần |
| `EVENT` | Sự kiện, trận đánh | Trận Bạch Đằng, trận Tot Động–Chúc Động |
| `LOCATION` | Địa danh | Hoa Lư, Đống Đa, sông Hồng |
| `TIME` | Mốc thời gian | năm 938, thế kỷ XV, năm Canh Thân 1380 |
| `TITLE` | Miếu hiệu, thụy hiệu, niên hiệu, chức vụ | Lê Thái Tổ, Bình Định Vương, Thái tử, Tể tướng quân |

- Biểu diễn nhãn ở dạng **BIO** (BIOES) trong mô hình token classification.
- Quy ước tên nhãn đầy đủ trong mã: `PERSON`, `DYNASTY`, `EVENT`, `LOCATION`, `TIME`, `TITLE`.
- Xuất API: hàm nhận text → danh sách `(span, label, score)`.

**AC**
- Lớp nhãn đầy đủ khớp với danh sách trên; không sinh nhãn ngoài danh sách.
- Chuỗi đầu ra parse được thành câu có entity mentions với độ trôi (offset) chính xác về byte/ký tự.

**Đầu ra:** `data/interim/ner_predictions.jsonl`

---

### B2. Nhãn bạc từ hyperlink + huấn luyện PhoBERT (M)

**Mô tả**
- **Sinh nhãn silver tự động**: mỗi hyperlink nội bộ `[[Đích]]` tạo một mention có label suy ra từ `đích` (xem bảng bên dưới). Chỉ dùng link có anchor text khớp đích (anchor==target) hoặc chứa tên đích để tránh nhiễu (ví dụ `[[thành phố]]`).
- **Quy tắc suy nhãn theo đích:**
  - Nhân vật: đích nằm trong danh sách seed nhân vật, hoặc đích có infobox `person`, hoặc đích thuộc category `Vua ...`/`Nhân vật ...`.
  - `DYNASTY`: đích khớp mẫu `nhà X`, `triều đại X`, `... (gia tộc)`.
  - `EVENT`: đích thuộc category `Trận đánh ...` / `Sự kiện ...` / có infobox trận đánh.
  - `LOCATION`: đích thuộc category `Địa danh ...` / `Thành phố ...` / `Tỉnh ...` / `Sông ...`.
  - `TITLE`: đích là trang miếu hiệu/thụy hiệu (`... (miếu hiệu)`) hoặc khớp danh sách chức vụ.
  - `TIME`: link `[[1380]]`, `[[Thế kỷ XV]]`, `[[938]]` — nhận diện bằng mẫu số/`Thế kỷ`.
- Từ điển nhãn lưu được, có thể dùng lại để huấn luyện mà không cần tải lại dump.
- **Huấn luyện PhoBERT** (`vinai/phobert-base`) fine-tune token classification:
  - Chuyển mention → chuỗi nhãn BIO ở mức **subword** (dùng `wordpiece` offsets).
  - Tách train/dev theo **bài** (không tách theo câu) để tránh rò rỉ.
  - Loss chuẩn cross-entropy; early stopping theo F1; lưu checkpoint tốt nhất.
  - Có **notebook Kaggle** chạy được end-to-end, sinh ra: `ner_model/` (weights + tokenizer + config) và báo cáo F1 trên dev.
- Chế độ inference: nạp checkpoint từ đĩa, dự đoán theo câu (batching, sliding window nếu câu dài).

**AC**
- Nhãn silver sinh được cho ≥ 90% câu có ít nhất một hyperlink nội bộ trong tập lọc.
- Baseline rule-based (dựa trên hyperlink) đạt F1 ≥ 0.60 trên tập dev → chứng minh nhãn silver hợp lý.
- Mô hình PhoBERT đạt F1 ≥ 0.85 trên tập dev/gold.
- Notebook Kaggle chạy từ đầu đến cuối không lỗi, có checkpoint tải về được.

**Đầu ra:** `ner_model/`, `data/interim/ner_silver.jsonl`, `data/interim/ner_predictions.jsonl`

---

### B3. Chuẩn hóa biểu thức thời gian lịch sử (S)

**Mô tả**
- Nhận diện các dạng: `năm 938`, `năm 15 tháng 3 năm 1028`, `thế kỷ XV`, `thế kỷ 15`, `năm Canh Thân 1380`, `năm Ất Tý (938)`, `tháng 5 năm 1284`, khoảng `khoảng năm 1000`.
- Chuẩn hóa về **năm dương lịch**: `{"text": "năm Canh Thên 1380", "year": 1380, "precision": "year", "calendar": "solar"}`.
- Với năm âm lịch đi kèm năm dương → lấy năm dương.
- Với `thế kỷ XV` → `{year_start: 1401, year_end: 1500}` (quy ước thế kỷ 1 = năm 1).
- Tích hợp vào pipeline: giá trị `TIME` đã chuẩn hóa được dùng làm **đối tượng** cho quan hệ `SINH_NĂM`/`MẤT_NĂM` và làm **thuộc tính thời gian** cho quan hệ có thời gian (D5).

**AC**
- Chuẩn hóa đúng ≥ 90% trên tập 50 biểu thức thời gian tự gán nhãn.
- Mọi giá trị năm trong KG đều là số nguyên dương hoặc null.
- Năm âm lịch kèm năm dương được ưu tiên lấy năm dương.

---

### Binvoke. B4. So sánh với LLM few-shot (S)

**Mô tả**
- Baseline: đưa câu tiếng Việt vào prompt Gemini/Groq kèm mô tả 6 lớp nhãn + few-shot ví dụ, yêu cầu trả JSON theo schema `{"entities":[{"text","label","start","end"}]}`.
- Chạy trên cùng tập dev với PhoBERT, so sánh F1 theo label.
- Lưu kết quả so sánh dạng bảng vào báo cáo.

**AC**
- Có báo cáo so sánh F1 PhoBERT vs LLM few-shot trên ≥ 200 câu dev.
- Baseline LLM được lưu lại để tái lập (prompt + model + raw output).

---

## Module C — Đồng tham chiếu (Coreference)

### C1. Giải quyết đại từ và danh xưng trong cùng đoạn (M)

**Mô tả**
- Quy tắc ưu tiên (rule-based, không cần mô hình):
  1. Trong cùng đoạn, lấy **thực thể `PERSON` cuối cùng được nhắc** làm ứng viên chính cho đại từ ("ông", "ông ấy", "vua", "ông ta").
  2. Từ điển danh xưng: `ông` → `PERSON` nam giới, `bà` → `PERSON` nữ, `vua`/`hoàng đế` → `PERSON` đang giữ ngai vàng, `thái tử`/`tể tướng` → `TITLE` (và người được chiếu).
  3. "Người con trai của vua X" → `PERSON` (con trai) là quan hệ với X.
- Chuẩn hóa về **cùng chuẩn thực thể** với entity linking (Module E): sau khi coreference gán, chạy entity linking để gộp về nút trong KG.

**AC**
- Trên tập gold 100 câu có đại từ, độ chính xác gán ≥ 0.80.
- Mọi mention sau coreference đều có `mention_id` và `canonical_id` (trỏ tới entity trong KG).

**Đầu ra:** `data/interim/coref_resolved.jsonl`

---

### C2. Quan hệ gián tiếp bằng luật "chủ thể của bài" (M)

**Mô tả**
- Xác định **chủ thể bài** (`article_subject`): nhân vật chính của bài — thường là tiêu đề bài nếu là bài nhân vật; nếu bài là về sự kiện/triều đại → chủ thể là `EVENT`/`DYNASTY`.
- Áp dụng cho các câu không có tên rõ ràng nhưng có đại từ/danh xưng: gắn về chủ thể bài.
- Ví dụ: bài "Trận Bạch Đằng (1284)", câu "Chiến thắng này mang lại cho nhà Trần nhiều lợi thế." → `EVENT` + `DYNASTY` + quan hệ phát sinh.

**AC**
- ≥ 80% câu trong tập gold chứa đại từ được gắn đúng ít nhất một quan hệ hợp lệ.
- `article_subject` xác định đúng ≥ 90% trên tập 50 bài nhân vật kiểm thử.

**Đầu ra:** trường `article_subject` cho mỗi document.

---

### C3. Phiên bản nâng cao bằng LLM/mô hình coreference (C)

**Mô tả**
- Dùng LLM để giải quyết coreference khó (nhiều nhân vật trong đoạn, đại từ lặp lại xa).
- Hoặc dùng mô hình coreference tiếng Việt nếu tìm được.
- Kết quả dùng làm **nhãn đối chiếu** (sanity check) cho rule-based.

**AC**
- Có kết quả so sánh độ chính xác rule-based vs LLM trên cùng 100 câu.

---

## Module D — Trích xuất quan hệ (RE)

### Tập quan hệ cố định

| Nhóm | Quan hệ |
|---|---|
| Gia đình | `CHA_CỦA`, `MẸ_CỦA`, `VỢ_CỦA` / `CHỒNG_CỦA`, `ANH_EM_CỦA` |
| Chính trị | `THUỘC_TRIỀU_ĐẠI`, `KẾ_VỊ`, `GIỮ_CHỨC_VỤ`, `LẬP_RA` |
| Quân sự | `CHỈ_HUY_TRẬN`, `THAM_GIA_TRẬN`, `ĐÁNH_BẠI`, `DIỄN_RA_TẠI` |
| Địa lý / Thời gian | `SINH_TẠI`, `MẤT_TẠI`, `SINH_NĂM`, `MẤT_NĂM`, `ĐÓNG_ĐÔ_TẠI` |

**Quy ước bắt buộc**
- Tên quan hệ lưu trong KG là **chữ thường không dấu gạch dưới** để tương thích Cypher: `cha_cua`, `me_cua`, `vo_cua`, `chong_cua`, `anh_em_cua`, `thuoc_trieu_dai`, `ke_vi`, `giu_chuc_vu`, `lap_ra`, `chi_huy_tran`, `tham_gia_tran`, `danh_bai`, `dien_ra_tai`, `sinh_tai`, `mat_tai`, `sinh_nam`, `mat_nam`, `dong_doi_tai`.
- Quan hệ **đối xứng** phải khai báo tường minh trong hằng số `SYMMETRIC_RELATIONS = {anh_em_cua, than_gia_tran}`. Khi nạp, cạnh đối xứng được tạo **một lần duy nhất** (F2).
- Quan hệ **có hướng** mặc định là hướng từ subject → object.

### D1. Phân loại quan hệ bằng PhoBERT + entity marker, distant supervision từ Wikidata (M)

**Mô tả**
- **Distant supervision**: lấy cặp quan hệ thật từ Wikidata bằng SPARQL, ánh xạ property → quan hệ trong schema:
  - `P22` (father) → `cha_cua`; `P25` (mother) → `me_cua`; `P26` (spouse) → `vo_cua`/`chong_cua`; `P3373` (sibling) → `anh_em_cua`; `P40` (child) → nghịch đảo của `cha_cua`/`me_cua`.
  - `P580/P582` (start/end time) + `P39` (position held) → `ke_vi` + thuộc tính thời gian.
  - `P551` (residence), `P19` (birthplace) → `sinh_tai`; `P20` (place of death) → `mat_tai`; `P569` → `sinh_nam`; `P570` → `mat_nam`.
  - `P361`/`P463` (part of) với instance `dynasty` → `thuoc_trieu_dai`.
  - `P1344` (participant in) với instance `battle` → `tham_gia_tran`; `P710` (participant) → `tham_gia_tran`; `P276` (location) → `dien_ra_tai`.
- **Ánh xạ ngược**: để biết một bài Wikipedia tiếng Việt tương ứng QID nào, dùng `wikibase_item` trong infobox, hoặc tra `siteinfo`/`page_props` trong dump, hoặc SPARQL `schema:about`.
- **Sinh tập huấn luyện**: với mỗi cặp (subject, relation, object) có trong Wikidata, tìm câu trong tập bài tiếng Việt chứa **cả hai** entity (sau khi coreference + linking) → gắn nhãn quan hệ cho cặp đó trong câu đó.
- **Mô hình**: PhoBERT-base token classification trên chuỗi đã chèn **entity marker** `<s>`, `«`, `»` (kiểu marker đã dùng cho RE):
  - Đầu vào: `<subject_mention> [SEP] câu với marker quanh subject và object [SEP] <object_mention>`.
  - Đầu ra: nhãn quan hệ ở vị trí `[CLS]`, gồm cả nhãn `NA` (không có quan hệ).
- **Xử lý nhãn nhiễu**: mẫu âm `NA` được lấy từ cặp entity có mặt trong câu nhưng không có quan hệ trong Wikidata. Tỉ lệ âm/dương được cân bằng khi chia tập.
- Chia tập theo **bài** để không rò rỉ.

**AC**
- Tập huấn luyện có ≥ 20.000 mẫu có nhãn dương (nếu đạt, giữ ≥ 10.000 và ghi rõ trong báo cáo).
- PhoBERT đạt RE F1 ≥ 0.70 trên tập gold.
- Mọi quan hệ nằm trong tập quan hệ cố định; không sinh quan hệ ngoài schema.

---

### D2. Trích xuất bằng LLM theo schema cố định (M)

**Mô tả**
- Gọi Gemini/Groq với prompt chứa: schema quan hệ (tên + mô tả + ví dụ), quy tắc hướng, định dạng đầu ra JSON bắt buộc:
  ```json
  {"triples":[{"subject":"...","relation":"...","object":"...","evidence":"...","confidence":0.0}]}
  ```
- Yêu cầu `evidence` là **trích nguyên văn từ câu**; hậu kiểm: evidence phải là substring của câu đầu vào (không thì loại bỏ triple, đếm số lượt loại).
- Chia prompt theo **lô câu** (10–20 câu/lần) để tiết kiệm quota, có retry khi lỗi JSON.
- Kết quả được lưu raw để tái lập.

**AC**
- LLM baseline đạt RE F1 ≥ 0.65 trên tập gold (baseline, không bắt buộc đạt mục tiêu 0.70).
- ≥ 90% triple LLM có evidence hợp lệ (substring) trước khi lọc; sau lọc còn ≥ 60% tổng số triple ứng viên.
- Có file lưu prompt, raw output, và số lượt lỗi.

---

### D3. Mỗi triple lưu kèm bằng chứng và metadata (M)

**Mô tả**
Mỗi triple bắt buộc có đủ trường:
- `subject` / `relation` / `object` (canonical id hoặc surface form)
- `evidence_sentence` (chuỗi bằng chứng)
- `doc_id`, `doc_title`, `source_url`, `sentence_id`
- `confidence` ∈ [0,1]
- `method` ∈ {`infobox`, `distant_supervision`, `phobert_re`, `llm`, `rule`}

**AC**
- 100% triple trong KG có đủ 6 trường bắt buộc.
- Từ 1 triple, người dùng click vào cạnh trên UI thấy đúng câu bằng chứng + link bài Wikipedia.

---

### D4. Quan hệ có hướng và quan hệ đối xứng (S)

**Mô tả**
- Hằng số `SYMMETRIC_RELATIONS` khai báo quan hệ đối xứng; khi nạp, chỉ tạo 1 cạnh (canonical orientation) và UI hiển thị 2 chiều.
- Quan hệ có hướng giữ nguyên hướng; UI hiển thị mũi tên đúng chiều.

**AC**
- Không có cạnh trùng lặp do quan hệ đối xứng (`COUNT(DISTINCT ...)` bằng `COUNT(*)`).
- Kiểm thử tự động cho mọi quan hệ đối xứng.

---

### D5. Quan hệ có thời gian (S)

**Mô tả**
- Quan hệ có thời gian (`ke_vi`, `giu_chuc_vu`) lưu thuộc tính cạnh: `start_year`, `end_year`, `start_date`, `end_date`.
- Nguồn: Wikidata `P580`/`P582`, hoặc trích từ câu ("làm vua từ 1428 đến 1433").
- Truy vấn được: "các vua nhà Trần theo thứ tự thời gian", "vua nào trị vị giai đoạn 1400-1500".

**AC**
- ≥ 80% cạnh `ke_vi` có `start_year` khác null.
- Hỗ trợ truy vấn lọc theo khoảng năm trong UI (H5).

---

### D6. Phát hiện triple mâu thuẫn (C)

**Mô tả**
- Phát hiện: cùng một subject có 2 `sinh_nam` khác nhau; cùng cặp subject-relation có 2 object khác nhau; cùng object có 2 `sinh_nam` khác nhau.
- Gắn cờ `conflict: true` + lưu danh sách các triple xung đột vào collection `conflicts`, kèm quy tắc sinh ra.

**AC**
- Có script phát hiện chạy được trên đồ thị thật, báo cáo số nhóm xung đột.
- Có tập test với các cặp xung đột cố ý tạo.

---

## Module E — Liên kết thực thể (Entity Linking)

### E1. Từ điển alias (M)

**Mô tả**
- Với mỗi thực thể trong KB, gom **tất cả** tên gọi:
  - Tên bài Wikipedia (canonical name).
  - Tên húy (tên thật).
  - Miếu hiệu, thụy hiệu, niên hiệu.
  - Tên thường gọi/ngự danh.
  - Biến thể không dấu / có dấu, viết tắt.
  - Tên trong nội dung bài viết (từ hyperlink đích).
- Nguồn: infobox (A4) + danh sách đích hyperlink + Wikidata aliases (`P742`, `P1449`, `P1709`).
- Lưu `aliases: [{alias, type, source}]` với `type` ∈ {`canonical`, `birth_name`, `posthumous`, `temple`, `reign`, `alias`, `nickname`, `variant`}.

**AC**
- ≥ 95% thực thể `PERSON` có ≥ 2 alias (tính cả tên húy và biến thể).
- Ví dụ kiểm thử: `Lê Lợi` có alias `Lê Thái Tổ`, `Bình Định Vương`, `Lê Lợi (người)`.
- Tra cứu alias → canonical id là dict O(1) (hoặc hash index).

---

### E2. Sinh ứng viên bằng alias và embedding (M)

**Mô tả**
- **Stage 1 — Alias exact match (dictionary)**: tra chuẩn hóa (bỏ dấu, lowercase, bỏ dấu câu) trong từ điển alias → tập ứng viên. Đây là đường đi chính.
- **Stage 2 — Embedding**: encode mention bằng **BGE-M3** (`BAAI/bge-m3`) hoặc `intfloat/multilingual-e5-large`; so với vector của các thực thể (đã precompute). Lấy top-k (k=20).
- Ứng viên cuối = hợp nhất stage 1 và stage 2.
- Embedding được sinh offline trên **Kaggle GPU** và xuất ra file `.npy`/`.parquet` để máy i3 chỉ cần load.

**AC**
- Nêu rõ được recall@20 của ứng viên trên tập gold.
- File embedding lưu kèm metadata: `entity_id`, `model_name`, `dim`, `source_text` để tái lập.
- Thời gian sinh ứng viên (alias + embedding) ≤ 200ms/mention trên CPU.

---

### E3. Xếp hạng lại theo ngữ cảnh (M)

**Mô tả**
- Reranker điểm ứng viên bằng tín hiệu ngữ cảnh:
  - **Truyền cảm**: entity mention xuất hiện trong cùng đoạn / cùng bài với ứng viên.
  - **Thời gian**: khoảng năm sinh/mất của ứng viên phải chồng lấn với mốc thời gian trong câu.
  - **Triều đại**: ứng viên thuộc đúng triều đại đang xét.
  - **Loại thực thể**: ứng viên cùng loại với nhãn dự đoán của NER.
  - **Tần suất link**: số lần entity được nhắc trong corpus.
- Có thể dùng mô hình reranker (cross-encoder đa ngôn ngữ) nếu đủ thời gian; mặc định là tổng hợp trọng số có giải thích được.
- Khi có **nhiều ứng viên cùng điểm**, ghi `ambiguous: true` để admin duyệt.

**AC**
- Entity linking accuracy ≥ 0.85 trên tập gold (100–200 mention).
- Có bảng đóng góp điểm của từng tín hiệu để giải thích kết quả (phục vụ báo cáo).

---

### E4. Gán ID nội bộ và ánh xạ QID (M)

**Môtả**
- Mỗi thực thể có ID nội bộ ổn định: `ent_<slug>_<hash8>` (hash của canonical name + type) — ổn định giữa các lần chạy.
- Ánh xạ: `entity_id` → `wiki_url`, `wikidata_qid` (nếu có), `canonical_name`, `type`.
- Tổ chức lưu trữ: file `data/knowledge_base/entities.jsonl` (một dòng = một entity, đầy đủ alias + QID + thuộc tính) làm nguồn chuẩn để nạp Neo4j.

**AC**
- Nạp lại KG hai lần cho cùng tập entity → số node/edge không đổi (F2).
- ≥ 90% entity `PERSON` có `wikidata_qid` (báo cáo tỉ lệ thực tế).
- Entity không có QID vẫn dùng được trong KG, hiển thị badge "chưa xác minh" (E5).

---

### E5. Thực thể NIL — chưa xác minh (S)

**Mô tả**
- Khi không tìm thấy ứng viên đủ tin cậy, tạo node mới với `verified: false`, `surface_name` = chuỗi gốc, `source_method = "nil"`.
- Gộp các node NIL về cùng surface name để tránh phình đồ thị.
- Admin có thể duyệt/gán QID sau (I2).

**AC**
- Không vượt quá 10% số node là NIL.
- Node NIL hiển thị badge "chưa xác minh" trên UI.

---

### E6. Gộp thực thể trùng (entity resolution) (C)

**Mô tả**
- Gợi ý gộp các node có tên gần giống (độ Levenshtein/embedding cao) qua màn hình admin, duyệt thủ công.
- Lưu log thao tác gộp để tái lập.

**AC**
- Có màn hình gợi ý gộp và nhật ký thay đổi.

---

## Module F — Lưu trữ đồ thị (Neo4j)

### F1. Thiết kế schema (M)

**Mô tả**
- Nhãn nút: `Person`, `Dynasty`, `Event` (battle/sự kiện), `Place`, `Title`, `Article` (bài nguồn), `Conflict`.
- Nhãn cạnh = tên quan hệ (dưới dạng chữ thường không dấu gạch dưới).
- Thuộc tính nút: `entity_id`, `name`, `name_normalized`, `aliases` (list), `type`, `birth_year`, `death_year`, `birth_place`, `death_place`, `dynasty`, `reign_start`, `reign_end`, `description`, `wiki_url`, `wikidata_qid`, `verified`, `mention_count`, `source_method`.
- Thuộc tính cạnh: `confidence`, `method`, `evidence_sentence`, `source_url`, `doc_id`, `sentence_id`, `start_year`, `end_year`, `created_at`.
- Tất cả node đều có `entity_id` (khóa nghiệp vụ duy nhất).

**AC**
- Schema viết bằng Cypher DDL trong `schema.cypher`, có thể chạy lại không lỗi.
- Mọi node có `entity_id` khác null và duy nhất.

---

### F2. Nạp dữ liệu theo lô, idempotent (M)

**Mô tả**
- Nạp bằng `UNWIND` + `MERGE` theo `entity_id`.
- Chia lô 500–1.000 node/cạnh mỗi lần, có thanh tiến trình và log.
- Chạy lại nhiều lần không tạo bản ghi trùng.
- Lệnh xóa sạch đồ thị (`MATCH (n) DETACH DELETE n`) chỉ chạy khi có cờ xác nhận.

**AC**
- Chạy nạp 3 lần liên tiếp → số node và số cạnh không đổi (kiểm bằng script).
- Nạp 5.000 node + 50.000 cạnh hoàn tất trong < 10 phút trên máy i3.

---

### F3. Index và constraint (M)

**Mô tả**
- Constraint uniqueness: `Person.entity_id`, `Dynasty.entity_id`, `Event.entity_id`, `Place.entity_id`, `Title.entity_id`, `Article.entity_id`.
- Index: `name_normalized` trên mọi label; `alias_normalized` (nếu dùng node property) hoặc index trên `entity_id`; `wiki_url`.
- Index phục vụ truy vấn theo năm: `birth_year`, `death_year`, `reign_start`.

**AC**
- Script kiểm tra cho biết đã tạo đủ constraint/index chưa, chạy trước khi nạp.

---

### F4. Lưu bằng chứng trên mỗi cạnh (M)

**Môtả**
- Mỗi cạnh có đủ: `evidence_sentence`, `source_url`, `confidence`, `method` (như D3) → cạnh phải truy được về câu nguồn.

**AC**
- Kiểm tra tự động: 0 cạnh nào thiếu `evidence_sentence` hoặc `source_url`.
- Click vào cạnh trên UI hiển thị câu bằng chứng + link bài nguồn.

---

### F5. Xuất/nhập đồ thị (S)

**Mô tả**
- Xuất: `dump` cypher (`CALL apoc.export.graphml` hoặc `neo4j-admin database dump`) + CSV từng label/relation.
- Nhập: script nạp lại từ các file này.

**AC**
- Có script `export_graph.sh` / `import_graph.sh` và file xuất đã kiểm tra (import → số node/edge khớp).

---

## Module G — Hỏi đáp tiếng Việt (Text-to-Cypher)

### G1. Luồng hỏi đáp cơ bản (M)

**Mô tả**
Luồng end-to-end:
1. Nhận câu hỏi tiếng Việt.
2. Chuẩn hóa (G3: entity linking trên câu hỏi).
3. Sinh Cypher (G2).
4. Kiểm tra an toàn (G4).
5. Thực thi trên Neo4j.
6. Nếu lỗi/rỗng → tự sửa (G5, tối đa 3 lần).
7. Sinh câu trả lời tự nhiên từ kết quả (G7).
8. Trả về: câu trả lời văn bản + Cypher + kết quả thô + đồ thị con để vẽ.

**AC**
- Mỗi câu hỏi trả về đủ 4 phần: `answer`, `cypher`, `records`, `graph` (nodes + edges liên quan).
- Trả lời trong < 10 giây end-to-end (đo p50/p95).

---

### G2. Prompt sinh Cypher (M)

**Mô tả**
- Prompt chứa:
  - **Schema đầy đủ**: nhãn node, tên quan hệ hợp lệ, thuộc tính quan trọng.
  - **Danh sách quan hệ hợp lệ** (enum) — mô hình chỉ được sinh quan hệ trong danh sách.
  - **Quy tắc**: chỉ dùng `MATCH`/`OPTIONAL MATCH`/`RETURN`/`ORDER BY`/`LIMIT`/`WITH`/`UNWIND`/`CASE`; không `CREATE/DELETE/MERGE/SET/REMOVE`; luôn `LIMIT`; không dùng `MATCH (n) RETURN n` không lọc.
  - **Few-shot**: 8–12 ví dụ đa dạng (một bước, đếm, đa bước, so sánh, lọc năm).
  - **Hướng dẫn dùng ID đã chuẩn hóa**: entity trong câu hỏi được thay bằng `entity_id` trước khi sinh Cypher.
- Output bắt buộc là JSON: `{"cypher": "...", "explanation": "..."}`; parse lỗi → retry với hướng dẫn sửa.

**AC**
- Tỉ lệ sinh Cypher parse được JSON ngay lần đầu ≥ 95%.
- Tỉ lệ sinh quan hệ ngoài danh sách hợp lệ = 0% (kiểm tự động bằng validator, nếu phát hiện → retry 1 lần rồi từ chối).
- Cypher sinh ra luôn có `LIMIT` ≤ 100.

---

### G3. Chuẩn hóa tên thực thể trong câu hỏi (M)

**Môtả**
- Trước khi sinh Cypher, chạy entity linking trên câu hỏi với **từ điển alias của KG** (Module E).
- Thay thế span trong câu hỏi bằng `entity_id` tương ứng (ví dụ: "vợ của Lê Thái Tổ" → "vợ của `ent_le_loi_1a2b3c4d`").
- Cung cấp danh sách entity đã nhận diện cho mô hình trong prompt, kèm tên gốc để mô hình hiểu ngữ nghĩa.
- Nếu không nhận diện được entity nào → vẫn cho phép sinh Cypher nhưng thêm cảnh báo "không xác định được thực thể".

**AC**
- "Lê Thái Tổ" và "Lê Lợi" cùng ánh xạ tới **một** `entity_id`.
- ≥ 90% câu hỏi trong bộ test có ít nhất một entity được nhận diện đúng.

---

### G4. Kiểm tra Cypher, chỉ cho phép đọc (M)

**Môtả**
- **Validator tĩnh** (trước khi gửi DB): tokenize Cypher, chặn các từ khóa `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `CALL` (trừ `apoc` chỉ đọc — khuyến nghị chặn hẳn `CALL`), `LOAD CSV`, `FOREACH`.
- Chỉ cho phép mở đầu bằng `MATCH` / `OPTIONAL MATCH` / `WITH` / `UNWIND` / `RETURN`.
- Chặn câu có `;` nối nhiều câu lệnh.
- **Giới hạn runtime**: `CALL dbms.setConfigValue`/`dbms.transaction.timeout` hoặc dùng `neo4j` driver `timeout` (ms) + `LIMIT` bắt buộc + `MAX_RESULT_ROWS`.
- **Tài khoản DB chỉ quyền đọc** (`READ ONLY`) — lớp bảo vệ thứ hai ngoài validator.
- **Log**: ghi lại mọi Cypher đã chạy (câu hỏi, Cypher, thời gian, số kết quả) để audit.

**AC**
- Test tự động: ≥ 20 truy vấn độc hại (`MATCH (n) DETACH DELETE n`, `MATCH (n) SET n.x=1`, `CREATE (n:Node)`, `CALL dbms.killTransaction`, …) → **100% bị chặn**, không query nào chạm DB.
- Timeout 10 giây được áp dụng; truy vấn vượt thời gian trả lỗi thân thiện.
- Số kết quả trả về không vượt 100 dòng.

---

### G5. Tự sửa lỗi (S)

**Môtả**
- Vòng lặp: sinh Cypher → thực thi → nếu lỗi cú pháp hoặc kết quả rỗng → đưa thông báo lỗi + Cypher cũ + câu hỏi lại cho mô hình, tối đa 3 lần.
- Với kết quả rỗng: gợi ý mô hình thử lại với cách diễn đạt khác (bỏ ràng buộc, thử alias khác).
- Log từng lần thử để phân tích lỗi.

**AC**
- Trên bộ test, ≥ 80% câu hỏi đã từng cần ≥ 2 lần thử vẫn trả lời đúng sau vòng lặp.
- Log đầy đủ các lần retry.

---

### G6. Các dạng câu hỏi được hỗ trợ (M)

**Môtả**
Hệ thống phải hỗ trợ và có câu hỏi mẫu cho từng dạng:

| Dạng | Ví dụ | Cypher kỳ vọng (minh họa) |
|---|---|---|
| Tra cứu một bước | "Lê Lợi sinh năm nào?" | `MATCH (p:Person {entity_id:$id}) RETURN p.birth_year` |
| Tra cứu thuộc tính | "Lê Lợi mất ở đâu?" | `RETURN p.death_place` |
| Liệt kê | "Liệt kê các vua nhà Trần" | `MATCH (p:Person)-[:thuoc_trieu_dai]->(d:Dynasty) RETURN p` |
| Đếm | "Triều Trần có bao nhiêu vua?" | `RETURN count(p)` |
| Đa bước | "Vợ của vua X là con của ai?" | hai `MATCH` nối nhau |
| Lọc theo năm | "Vua nào trị vì sau năm 1400?" | `WHERE p.reign_start > 1400` |
| So sánh | "Ai làm vua lâu hơn, X hay Y?" | so sánh `reign_end - reign_start` |
| Bước giữa (bridge) | "Bạn của vua X là ai?" | `MATCH (p)-[:anh_em_cua]->(s) RETURN s` |
| Không có dữ liệu | "Ai là vua năm 1855?" | trả "không có trong dữ liệu" |

**AC**
- Bộ test có ≥ 60 câu, phân bố: 40% một bước, 25% đa bước, 20% đếm/liệt kê, 15% so sánh/lọc.
- Execution accuracy ≥ 0.70 tổng thể; ≥ 0.60 trên nhóm đa bước.
- Có tối thiểu 3 câu hỏi dạng "không có dữ liệu" và hệ thống **không** bịa câu trả lời cho chúng.

---

### G7. Sinh câu trả lời tự nhiên (S)

**Môtả**
- Đưa kết quả Cypher (dạng bảng) cho LLM cùng câu hỏi và **chỉ dùng dữ liệu trong kết quả**.
- Prompt cấm suy đoán; yêu cầu trích dẫn bằng chứng liên quan.
- Nếu kết quả rỗng → trả "không có trong dữ liệu" (G8).
- Tùy chọn: câu trả lời có kèm danh sách bằng chứng để người dùng bấm xem.

**AC**
- Kiểm thử bằng tay: không có câu trả lời nào chứa thông tin không có trong kết quả Cypher (rà soát tối thiểu 30 câu).
- Câu trả lời tiếng Việt tự nhiên, không phải liệt kê thô.

---

### G8. Không tìm thấy thì nói rõ (M)

**Môtả**
- Phân biệt 3 trạng thái: `found` (có kết quả), `not_in_data` (KG không có quan hệ đó), `error` (lỗi kỹ thuật).
- `not_in_data` → trả "Không có trong dữ liệu" kèm gợi ý câu hỏi liên quan.
- `error` → trả thông báo lỗi + cho phép xem log, **không** trả lời suy đoán.

**AC**
- 100% câu hỏi trong nhóm "không có dữ liệu" trả đúng thông báo, không có suy đoán.
- UI phân biệt rõ 3 trạng thái bằng màu/thẻ khác nhau.

---

### G9. Hỏi tiếp theo ngữ cảnh (C)

**Môtả**
- Giữ lịch sử hội thoại và các entity đã nhắc trong phiên hiện tại; câu hỏi tiếp theo ("còn con của ông ấy?") dùng entity từ lượt trước.
- Cơ chế: "thay thế đại từ" bằng entity gần nhất trong lịch sử, rồi tiếp tục pipeline như bình thường.

**AC**
- ≥ 70% câu hỏi tiếp theo dạng đại từ được hiểu đúng (kiểm thử tay với ≥ 10 chuỗi hội thoại).

---

## Module H — Giao diện web và trực quan hóa

### H1. Giao diện chat (M)

**Mô tả**
- Ô nhập câu hỏi tiếng Việt (textarea, Enter để gửi).
- Hiển thị: câu trả lời văn bản, **Cypher đã sinh** (mặc định thu gọn, bấm để mở), trạng thái ("đang tìm…"), bằng chứng tham chiếu.
- Lịch sử hội thoại hiển thị trong cùng trang, có nút xóa.

**AC**
- Gửi câu hỏi → nhận đủ 3 phần (trả lời, Cypher, đồ thị).
- Cypher ẩn/hiện được, copy được.
- Lịch sử hội thoại lưu lại theo phiên (session id).

---

### H2. Đồ thị con tương tác (M)

**Môtả**
- Vẽ bằng **Cytoscape.js** (React + `react-cytoscapejs` hoặc wrapper trực tiếp).
- Layout: `cose` (mặc định) hoặc `dagre` cho cây.
- Tương tác: kéo thả nút, zoom, pan, chọn nút.
- **Màu theo loại nút**: Person / Dynasty / Event / Place / Title — mỗi loại một màu, có chú giải (legend).
- Nút chưa xác minh (NIL) vẽ viền đứt.

**AC**
- Đồ thị ≥ 500 node vẫn mượt (kéo thả không giật) — đo bằng `performance.now()` quanh thao tác.
- Màu nút khớp loại, có legend.
- Click nút → mở thẻ thông tin (H3).

---

### H3. Mở rộng láng giềng và thẻ thông tin (M)

**Môtả**
- Click nút → hiển thị **thẻ thông tin**: tên, loại, alias, năm sinh/mất, mô tả, link Wikipedia, nút "mở rộng láng giềng".
- Bấm "mở rộng" → gọi API lấy quan hệ 1–2 hop quanh node đó và thêm vào đồ thị.
- Giới hạn số node mở rộng mỗi lần (ví dụ ≤ 30) để tránh phình to.

**AC**
- Mở rộng 1 hop trả về đúng quan hệ của node đó (đối chiếu với API).
- Mỗi lần mở rộng ≤ 30 node.

---

### H4. Bấm cạnh xem bằng chứng (M)

**Môtả**
- Click vào cạnh → panel hiển thị: câu bằng chứng (highlight entity), `source_url`, `confidence`, `method`, tên bài nguồn.
- Link bài Wikipedia mở tab mới.

**AC**
- Mọi cạnh trên UI đều có bằng chứng → panel không bao giờ trống.
- Link mở đúng bài Wikipedia.

---

### H5. Lọc theo triều đại, quan hệ, thời gian (S)

**Môtả**
- Bộ lọc: triều đại (multi-select), loại quan hệ (multi-select), khoảng năm (slider/date-range).
- Áp dụng lọc **cả ở server** (đưa vào tham số truy vấn Cypher) và ở client.

**AC**
- Lọc theo triều đại giảm số node hiển thị đúng theo kết quả truy vấn kiểm chứng.
- Bộ lọc thời gian dùng được cho quan hệ có `start_year`/`end_year`.

---

### H6. Chế độ cây gia phả (S)

**Môtả**
- Từ một nhân vật, dựng cây gia đình: cha–mẹ–vợ/chồng–con, giới hạn độ sâu (mặc định 3), dùng layout `dagre` dọc.

**AC**
- Chọn "Lý Thái Tổ" → cây hiển thị cha (Lý Công Uẩn), con (Lê Đại Hành), vợ, các anh em.

---

### H7. Chế độ timeline (S)

**Môtả**
- Trục thời gian ngang: sự kiện (`EVENT`) và các mốc sinh/mất/đăng quang, gắn năm lên trục.
- Click một mốc → mở đồ thị con quanh sự kiện đó.

**AC**
- Timeline hiển thị ≥ 20 mốc sắp xếp đúng thứ tự năm.
- Click mốc → đồ thị con tương ứng.

---

### H8. Chế độ bản đồ (C)

**Môtả**
- Leaflet + OpenStreetMap; ghim các địa danh (`Place`) có tọa độ (từ Wikidata `P625`).
- Marker tương tác: click → xem thẻ thông tin.

**AC**
- ≥ 70% node `Place` có tọa độ.
- Marker click hiển thị thông tin.

---

### H9. Tìm kiếm nhân vật, autocomplete (S)

**Môtả**
- Ô tìm kiếm với autocomplete: gợi ý theo tên và **alias** (tìm "Lê Thái Tổ" ra "Lê Lợi").
- Kết quả là card nhân vật: tên, năm sinh–mất, triều đại, link Wikipedia.

**AC**
- Gõ "Bình Định Vương" → gợi ý "Lê Lợi" trong 3 ký tự gõ đầu, không cần gõ hết.
- Click kết quả → mở đồ thị con quanh nhân vật đó.

---

### H10. Câu hỏi gợi ý trên trang chủ (C)

**Môtả**
- 6–10 câu hỏi mẫu dựng sẵn (theo triều đại), click để hỏi luôn.

**AC**
- Có ≥ 6 câu hỏi gợi ý phủ các dạng: một bước, đa bước, đếm, so sánh.

---

## Module I — Quản trị và đánh giá

### I1. Trang thống kê KG (S)

**Mô tả**
- Số node theo label, số cạnh theo quan hệ, phân bố `confidence`, tỉ lệ node chưa xác minh, top thực thể theo `mention_count`.
- Biểu đồ đơn giản (Recharts).

**AC**
- Số liệu khớp với truy vấn Cypher trực tiếp trên DB (kiểm thử tự động so sánh).

---

### I2. Duyệt/sửa/xóa triple (C)

**Môtả**
- Danh sách triple sắp xếp theo `confidence` tăng dần (hoặc `method = llm`).
- Thao tác: duyệt (tăng confidence), sửa subject/relation/object, xóa, gán QID cho node NIL.
- Mọi thay đổi ghi vào log.

**AC**
- Thao tác admin phản ánh ngay trên UI và trong DB.
- Có nhật ký thay đổi.

---

### I3. Bộ đánh giá: auto-gold + gán tay tối thiểu (M)

**Mô tả**
- **Tầng 1 — Auto-gold (nguồn chính, không cần người gán):**
  1. **NER gold**: mỗi hyperlink có đích **có QID** + `P31` khớp nhãn entity → nhãn vàng. Loại bỏ mọi mention không có QID (tránh nhãn sai). Nguồn độc lập với mô hình → dùng đo F1.
  2. **RE gold**: cặp quan hệ từ Wikidata (`P22`, `P25`, `P26`, `P569`, `P570`…) là đáp án đúng. Cặp có mặt trong câu nhưng không có trong Wikidata → nhãn `NEGATIVE`. **Đáp án không đến từ KG của mình** → không vòng tròn.
  3. **Linking gold**: mention → QID; đo accuracy theo QID (khách quan 100%).
  4. **Bộ câu hỏi Text-to-Cypher**: sinh tự động từ facts Wikidata bằng khuôn câu hỏi (`P22` → "Cha của X là ai?"…), 200–400 câu, phân dạng tự động (1 bước, đa bước, đếm, lọc, `no_data`). `expected_result` lấy từ Wikidata.
- **Tầng 2 — Gán tay tối thiểu (tùy chọn):**
  - Dùng **Label Studio** (cài local bằng `pip install label-studio` hoặc Docker `heartexlabs/label-studio`).
  - Xuất **100 câu** (chọn câu có ≥ 2 mention có QID → gán nhanh) ra JSONL.
  - Nếu có 2 người gán: gán độc lập trên ≥ 30 câu chung → tính **agreement rate** và (nếu đủ) **Cohen's kappa**. Nếu chỉ 1 người → báo cáo **agreement rate người–máy** so với auto-gold, nêu rõ khác biệt.
- **Mục đích của tầng 2**: kiểm chứng độ tin cậy của chính bộ auto-gold (tức là độ tin cậy của bộ đánh giá tự động).

**AC**
- [ ] Auto-gold NER ≥ 200 câu; auto-gold RE ≥ 500 cặp; auto-gold linking ≥ 300 mention; QA gold ≥ 200 câu phân ≥ 5 dạng
- [ ] Mọi đáp án trong auto-gold đến từ **Wikidata**, kiểm chứng được bằng script (`src/evaluation/check_no_circularity.py`)
- [ ] Nếu có gán tay: có báo cáo agreement rate (± kappa nếu có 2 người)
- [ ] File xuất dùng được trực tiếp cho script đánh giá (I4)

**Đầu ra:** `data/eval/{auto_gold_ner.jsonl, auto_gold_re.jsonl, auto_gold_link.jsonl, qa_gold.jsonl, manual_ner.jsonl}`

---

### I4. Script đánh giá tự động (M)

**Môtả**
- Script `evaluate.py` gồm các phép đo:
  - **NER**: token-level P/R/F1 (theo `seqeval`-style, IOB2), có breakdown theo label; báo cáo riêng micro/macro.
  - **RE**: P/R/F1 theo quan hệ, có đếm nhãn `NA`; đo cả trên câu có/không có coreference để chứng minh giá trị của Module C.
  - **Entity linking**: accuracy (mention → đúng entity), MRR nếu có nhiều đáp án.
  - **Text-to-Cypher**: execution accuracy (kết quả trả về khớp `expected_result`), tỉ lệ lỗi cú pháp, số lần retry trung bình, độ trùng khớp tập kết quả.
  - **Faithfulness**: LLM-judge (Gemini/Groq) trên 30 câu — câu trả lời có chứa thông tin ngoài `records` không.
- Đầu ra: bảng Markdown + JSON kết quả, lưu vào `reports/`.
- Script chạy được một lệnh, không cần thao tác tay.

**AC**
- `python scripts/evaluate.py --all` chạy được và in ra tất cả chỉ số.
- Có ít nhất 1 test tự động kiểm tra logic tính F1 (với dữ liệu mẫu đã biết kết quả).
- Báo cáo luôn kèm **kích thước tập đánh giá** cho từng chỉ số.

---

### I5. So sánh các cấu hình (S)

**Môtả**
- Chạy lại pipeline với các cấu hình: (a) không coreference, (b) không entity linking, (c) đầy đủ; so sánh NER/RE/linking/Text-to-Cypher.
- Kết quả lưu thành bảng trong báo cáo.

**AC**
- Có bảng so sánh ≥ 3 cấu hình với chỉ số của từng cấu hình.

---

## 5. Ma trận ưu tiên (MVP → mở rộng)

| Giai đoạn | Yêu cầu |
|---|---|
| **MVP** | A1–A4, B1–B2, C1–C2, D1–D3, E1–E4, F1–F4, G1–G4, G6, G8, H1–H4, I3–I4 |
| **Mở rộng** | B3, B4, D4–D5, E5, G5, G7, H5–H7, I1, I5 |
| **Nếu còn thời gian** | C3, D6, E6, G9, H8–H10, I2 |

## 6. Yêu cầu chéo giữa các module (cross-cutting)

| ID | Yêu cầu | Nguồn / đích |
|---|---|---|
| X1 | `entity_id` là khóa xuyên suốt: NER → RE → linking → Neo4j → API → UI | E4, F1, H3, H4 |
| X2 | Mọi triple/cạnh đều có `evidence_sentence` + `source_url` | D3, F4, H4 |
| X3 | Mọi entity đều có `wiki_url` (bắt buộc vì giấy phép CC BY-SA) | E4, F1 |
| X4 | Cùng một `relation` string dùng nhất quán giữa schema KG, prompt LLM, validator Cypher | D (tập quan hệ), G2, G4 |
| X5 | Mọi module ghi artifact trung gian ra `data/interim/` để chạy lại từng bước | A–E |
| X6 | Cấu hình tập trung trong `configs/` (yaml), không hard-code trong code | toàn bộ |

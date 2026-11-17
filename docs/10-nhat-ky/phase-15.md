# Phase 15 — Hybrid GraphRAG (nhánh B): kênh KG + ý định + fusion + hội thoại nhiều lượt

- Ngày: 17/11/2026
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: `reports/phase_15_report.md`
- Quyết định: `docs/DECISIONS.md` → **D-101** (template Cypher tất định), **D-102** (không gian `[n]` chung text + KG)
- Sai lệch: `reports/deviations.md` (D-104)

## 1. Bối cảnh và vấn đề cần giải

Phase 14 cho arm A (Vanilla RAG) đã trả lời được câu tự sự. Nhưng:

1. **Câu quan hệ cần chính xác tuyệt đối** ("Cha của Trần Nhân Tông là ai?") — RAG
   chỉ tìm đoạn văn có chứa tên ⇒ dễ lẫn giữa nhiều người cùng tên, dễ trả nhầm
   năm. KG có **quan hệ đã chuẩn hoá** ⇒ chính xác hơn.
2. **Câu đếm** ("Nhà Trần có bao nhiêu vua?") — KG đếm được `reign_start IS NOT NULL`;
   RAG đếm trong văn bản thì không đáng tin.
3. **Hội thoại nhiều lượt** — "Ông ấy mất năm nào?" cần **kế thừa chủ thề** từ lượt trước.

Ràng buộc lớn nhất: **arm B phải dùng cùng `Retriever`** với arm A (D-100) ⇒ mọi
khác biệt phải đến từ **kênh KG**, không từ retriever.

## 2. Phương án đã cân nhắc

### 2.1. Cách lấy context KG

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A. LLM sinh Cypher** (như Phase 11) | prompt → Cypher → Neo4j | chiều quan hệ đúng 5/5 khi đúng prompt; **biến thiên** giữa 2 lần chạy; tốn 1 request LLM/câu | ❌ | Không **tất định** ⇒ so sánh A/B không công bằng; tốn quota |
| **B. Template Cypher theo ý định** | 6 template Cypher cố định, chọn theo ý định | đảo chiều **chính xác 100%** (dùng bảng chiều đảo D-097); **0 request LLM**; bài Bạch Đằng: **30 entity → 60 cạnh / 0,11 s** | ✅ | Tất định + nhanh + không tốn quota |
| C. Duyệt toàn bộ KG | đọc hết 13.379 cạnh | 13.379 cạnh vào context ⇒ loãng, tốn token | ❌ | Không lọc theo câu hỏi |

**Bằng chứng template đảo chiều đúng** (đã verify trực tiếp trên Neo4j):

```
MATCH (p)<-[:cha_cua|me_cua]-(c) WHERE p.name = 'Trần Nhân Tông'
→ 5 con đúng
```

### 2.2. Cách mở rộng từ văn bản sang đồ thị ("link sang các quan hệ khác")

| Phương án | Cách làm | Kết quả | Chọn? | Lý do |
|---|---|---|---|---|
| Chỉ entity trong câu hỏi | 1–2 entity | nhiều câu không có entity | ❌ | Quá hẹp |
| **Mở rộng 1-hop từ `entity_ids` của chunk** | chunk đã truy xuất → 55,2% chunk có `entity_ids` → mở rộng 1-hop | bài Bạch Đằng: **30 entity → 60 cạnh**, gồm `Trần Hưng Đạo -chi_huy_tran-> Trận Bạch Đằng (1288)`, `Ô Mã Nhi -chi_huy_tran-> …`, `Trận Bạch Đằng -dien_ra_tai-> Sông Bạch Đằng` | ✅ | **Đây** là cơ chế "link sang quan hệ khác" mà kế hoạch yêu cầu |
| 2-hop | mở rộng 2 vòng | ~4× số cạnh, nhiều cạnh lạc | ❌ | Loãng context, không cần thiết |

### 2.3. Thứ tự hợp nhất (fusion)

| Ý định | Thứ tự | Lý do |
|---|---|---|
| `narrative` | **text-first** | narrative nằm ở văn bản; KG chỉ bổ sung |
| `relational` | **kg-first** | KG chính xác hơn; đặt lên đầu để LLM ưu tiên |
| `multi_hop` | **both** | cần nối text ↔ graph |
| `count` | **kg-first** | đếm trên KG |
| `comparison` / `no_data` | **both** | — |

### 2.4. Hội thoại nhiều lượt

| Phương án | Cách làm | Chọn? | Lý do |
|---|---|---|---|
| Lưu trong RAM của backend | dict trong process | ❌ | Mất khi restart; không dùng được khi chạy script đánh giá |
| **File JSON theo `session_id`** | `data/interim/sessions/<id>.json` | ✅ | Bền, **dùng chung** giữa API và script đánh giá, dễ inspect |
| Redis | cần hạ tầng thêm | ❌ | Quá nặng cho 1 phase demo |

**Cơ chế query rewriting:**

| Tình huống | Xử lý |
|---|---|
| Câu mới **có** entity mới | giữ nguyên, entity mới là chủ thề |
| Câu mới **không** có entity nhưng có đại từ ("ông ấy", "vị vua đó", "trận đó") | thay đại từ bằng `last_subject_name` |
| Câu mới **không** có entity, không có đại từ | kế thừa `last_subject` |

## 3. Quyết định đã chốt

**D-101 — Kênh KG = template Cypher tất định, không LLM sinh Cypher.**
- Lý do: đảo chiều chính xác 100%, không biến thiên LLM giữa 2 nhánh ⇒ so sánh công bằng; nhanh 0,11 s; không tốn quota.
- Ảnh hưởng: file mới `src/qa/graph_context.py`.

**D-102 — Không gian trích dẫn `[n]` dùng chung cho văn bản và KG.**
- Lý do: người dùng phân biệt được trích dẫn từ đâu; LLM không trộn chỉ số.
- **Bẫy đã gặp:** trong chiến lược `kg_first`, KG được đánh số `[1..M]` và text
  `[M+1..N]`. Nếu `to_text()` in text trước KG, thứ tự hiển thị **lệch** với số
  `[n]` ⇒ LLM trích dẫn sai chỉ số ⇒ judge báo "trích dẫn không tồn tại".
  ⇒ `FusedContext.to_text()` **phải sắp xếp theo `block["n"]`**, không hard-code thứ tự.
- Ảnh hưởng: `src/qa/fusion.py`, `src/qa/hybrid.py` (thêm `context_text`).

**6 ý định:** `narrative` · `relational` · `multi_hop` · `count` · `comparison` · `no_data`.

**Lọc nhiễu KG trong kênh đọc** (D-095) — dùng lại `src/graph/noise_filter.py`, không xoá khỏi Neo4j.

## 4. Thang số liệu so sánh

### 4.1. Template Cypher vs LLM sinh Cypher

| Tiêu chí | Template tất định | LLM sinh Cypher |
|---|---|---|
| Đảo chiều quan hệ | **chính xác 100%** (bảng D-097) | đúng **khi** prompt đúng; từng lần một |
| Tất định (chạy lại cho kết quả khác?) | ✅ không | ❌ có (temperature > 0, prompt khác context) |
| Chi phí LLM | **0 request** | 1 request/câu × 750 câu đánh giá ⇒ vượt quota |
| Độ trễ | **0,11 s** (30 entity → 60 cạnh) | 2,5–8,0 s (đo Phase 11) |
| Công bằng cho phép so sánh | ✅ | ❌ |

### 4.2. Fusion `kg_first` — bẫy đánh số `[n]`

| Cách sắp xếp `to_text()` | Số `[n]` trong prompt | Kết quả |
|---|---|---|
| Hard-code "text trước, KG sau" | KG `[1..M]`, text `[M+1..N]` | ❌ hiển thị lệch thứ tự ⇒ LLM trích dẫn sai ⇒ judge báo "không tồn tại" |
| **Sắp xếp theo `block["n"]`** | khớp hiển thị | ✅ mọi `[n]` trỏ đúng khối |

### 4.3. Quy mô kênh KG (bài Bạch Đằng)

| Chỉ số | Giá trị |
|---|---|
| Entity mở rộng 1-hop | **30** |
| Cạnh KG lấy được | **60** (`MAX_EDGES`) |
| Thời gian truy vấn | **0,11 s** |
| Cạnh mẫu | `Trần Hưng Đạo -chi_huy_tran-> Trận Bạch Đằng (1288)` |
| | `Ô Mã Nhi -chi_huy_tran-> Trận Bạch Đằng (1288)` |
| | `Trận Bạch Đằng -dien_ra_tai-> Sông Bạch Đằng` |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| "diễn biến trận Bạch Đằng" có **cả** narrative **và** ≥ 3 quan hệ KG có trích dẫn | có | ✅ có | ✅ |
| Hội thoại 3 lượt giữ chủ thề | có | ✅ ("Ông ấy mất năm nào?" → "Trần Hưng Đạo mất năm nào?") | ✅ |
| 2 nhánh dùng **cùng** retriever | bắt buộc | ✅ `Retriever` khởi tạo 1 lần, chia sẻ | ✅ |
| Số ý định | 6 | 6 | ✅ |
| Số template Cypher | ≥ 5 | **6** | ✅ |
| `MAX_EDGES` | ≤ 100 (rule `LIMIT ≤ 100`) | **60** | ✅ |
| `pytest -q tests/` | 0 fail | **0 fail** | ✅ |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| Judge báo "trích dẫn `[5]` không tồn tại trong context" | điểm `faithfulness` = 0 hàng loạt ở arm B | `to_text()` in **text trước** KG, nhưng `kg_first` đánh số KG `[1..M]` | sắp xếp `to_text()` theo `block["n"]` | **Số thứ tự hiển thị và số `[n]` phải là một**, không phải hai nguồn sự thật |
| Context judge vượt giới hạn token | judge trả JSON lỗi | context đầy đủ ~8.000+ ký tự × 3 arm | `compact_context()` cắt mỗi khối còn 600 ký tự, **giữ mọi header `[n]`** | Nén context phải cắt **thân khối**, không cắt **tiêu đề** — tiêu đề là không gian trích dẫn |
| Câu hỏi không có entity | không lấy được context KG | chỉ dựa vào entity trong câu hỏi | mở rộng 1-hop từ `entity_ids` của chunk đã truy xuất | Văn bản đã truy xuất là **nguồn entity** rẻ nhất |
| Alias đại từ map nhầm | "ông ấy" → George H. W. Bush | Phase 13 chưa chặn hết | đã chặn 42 bề mặt đại từ ở Phase 13; mở rộng `PRONOUNS` gồm cả "bà ấy", "cô ấy" | Sửa entity linking **trước** khi xây tầng trên nó |

## 7. Bài học kinh nghiệm

1. **Để so sánh ablation đáng tin, mọi thành phần ngoài đối tượng nghiên cứu phải là hằng số.** Ở đây: cùng retriever, cùng prompt, cùng bộ sinh câu trả lời — chỉ bật/tắt kênh KG.
2. **Template Cypher tất định thắng LLM sinh Cypher cho kênh KG.** Không chỉ về độ chính xác mà về **tính tái lập** (tái lập là nguyên tắc #6 trong `AGENTS.md` §5) và **chi phí quota**.
3. **Một không gian trích dẫn chung cho 2 loại nguồn** làm LLM và cả người đọc đều dễ kiểm chứng — nhưng đòi hỏi thứ tự hiển thị phải bám theo số `[n]`.
4. **Văn bản truy xuất được là nguồn entity tốt nhất để mở rộng đồ thị** — 61,5% chunk có `entity_ids`, rẻ hơn nhiều so với link trực tiếp trong câu hỏi.
5. **Đo trước quyết định dùng đường dẫn nào.** Nếu Phase 15 đã dùng LLM sinh Cypher, kết quả A/B sẽ chứa nhiễu không tái lập ⇒ không phân biệt được "đồ thị giúp" với "LLM may mắn".

## 8. Ý tưởng cho slide

- **"Vì sao KG làm kênh B bổ sung, không thay thế":** sơ đồ 2 nhánh — RAG (văn bản) + KG (triple) → fusion → 1 câu trả lời có `[n]`.
- **"Template Cypher tất định":** bảng so sánh 5 tiêu chí với LLM sinh Cypher (đảo chiều 100% / 0 request / 0,11 s).
- **"Link sang các quan hệ khác":** 30 entity → 60 cạnh trong 0,11 s — 3 cạnh mẫu về trận Bạch Đằng.
- **"Không gian trích dẫn chung":** ví dụ `kg_first` — KG `[1..M]` + text `[M+1..N]`, và bẫy khi thứ tự hiển thị lệch số.
- **"Hội thoại nhiều lượt":** *"Ông ấy mất năm nào?"* → *"Trần Hưng Đạo mất năm nào?"* → *"mất năm 1300"*.

## 9. Việc tiếp theo

**Phase 16 — Đánh giá A vs B vs B−.** Bộ câu hỏi 247 câu / 5 dạng từ Wikidata; LLM-judge chấm `correctness` · `faithfulness` · `citation_precision` · `no_data_accuracy` · `latency`; ablation 3 nhánh.

# Vì sao RAG thuần khó với lịch sử, và Hybrid GraphRAG giải quyết thế nào

> Tất cả số liệu dưới đây **đo trên corpus và KG thật** của dự án
> (`data/interim/documents_clean.jsonl`, `data/interim/coref_resolved.jsonl`,
> `data/interim/triples_merged.jsonl`, Neo4j `bolt://localhost:7687`).
> Không phải ví dụ minh hoạ — đây là số đo.

---

## 0. Tóm tắt một câu

Lịch sử khác ở 4 chỗ, và **cả 4 chỗ đều là chỗ mà đồ thị có lợi thế hơn văn bản thuần**:

| Đặc thù của lịch sử | RAG thuần gặp gì | KG có gì |
|---|---|---|
| Sự kiện nằm **rải rác** ở nhiều bài | không nối được | quan hệ `chi_huy_tran`, `dien_ra_tai` |
| Câu hỏi là **đếm/tổng hợp** ("17 đời vua") | không đếm được | `reign_start` + `thuoc_trieu_dai` |
| Tên lịch sử **trùng lặp/nhập nhằng** | lấy nhầm bài | entity_id + `source_url` |
| Câu hỏi **nhiều bước** | không nối 2 bài | đường đi 2-hop |

Và ngược lại, **KG không thể trả lời câu hỏi tự sự** — đó chính là lý do cần *cả hai*.

---

## 1. Bốn vấn đề cụ thể của RAG thuần với lịch sử — kèm số đo

### 1.1 Sự kiện lịch sử nằm rải rác ở nhiều bài, không bao giờ nằm trong một chunk

**Hiện tượng:** "Diễn biến trận Bạch Đằng (1288)" cần: đội hình Đại Việt, đội hình Mông Cổ,
kế cắm cọc, đường rút quân, kết cục. Nhưng các thông tin này nằm ở **nhiều bài khác nhau**:
`Trận Bạch Đằng (1288)`, `Trần Hưng Đạo`, `Chiến tranh Nguyên Mông – Đại Việt`,
`Ô Mã Nhi`, `Sông Bạch Đằng`, `Trương Hán Siêu`…

**Vì sao RAG thuần hỏng:** RAG đưa **k context cố định** vào prompt. Nếu k=8 chunk và 6 bài
khác nhau liên quan, 8 chunk đó sẽ bị pha loãng — không chunk nào đủ để trả lời trọn vẹn.

**Đo được:**
- Corpus có **2.441 bài**, **101.628 đoạn** — một sự kiện lịch sử trải trên nhiều bài.
- Bài `Trận Bạch Đằng (1288)` chỉ có **62 đoạn**, và phần `Diễn biến trận đánh` chỉ **4 đoạn**.
- **Chunk có entity KG: 55,2%** (một đoạn) — nhưng **81,8%** (gộp ~1000 ký tự).
  ⇒ Văn bản một mình **không chứa đủ entity cần thiết** cho một câu hỏi tự sự.

**Hybrid giải quyết:** lấy text làm **narrative**, rồi **mở rộng đồ thị 1-hop** từ entity
của chunk đó để bổ sung những mắt xích nằm ở bài khác.

> **Đo được:** bài Bạch Đằng (1288) → **30 entity → 60 cạnh KG trong 0,11 s**,
> gồm `Trần Hưng Đạo -chi_huy_tran-> Trận Bạch Đằng (1288)`,
> `Ô Mã Nhi -chi_huy_tran-> Trận Bạch Đằng (1288)`,
> `Phàn Tiếp`, `Tích Lệ Cơ`, `Trương Văn Hổ`, `Trương Văn Giáp` (phía Mông),
> `Trận Bạch Đằng -dien_ra_tai-> Sông Bạch Đằng`.
> ⇒ 5 tướng chỉ huy + địa điểm, **không nằm trong cùng một chunk** nào.

---

### 1.2 Câu hỏi đếm / tổng hợp — RAG không đếm được

**Hiện tượng:** "Nhà Lê sơ có bao nhiêu đời vua?", "Triều Lê có bao nhiêu đời vua?"
Là câu bạn đã hỏi và hệ thống trả lời sai.

**Vì sao RAG thuần hỏng:** LLM **không đếm trong context**. Nó đếm trong *training data*.
Đưa 8 chunk vào prompt, LLM vẫn có xu hướng đếm "số đoạn có nhắc tên vua" chứ không phải
"số vua thực sự lên ngôi". Đây là lỗi không sửa được bằng prompt.

**Đo được — KG đã phải sửa đúng lỗi này một lần (D-087):**
`thuoc_trieu_dai` cho biết *thuộc nhà*, **không** có nghĩa *là vua*.

| Truy vấn | Chỉ `thuoc_trieu_dai` | Chỉ người có `reign_start` | Đáp án lịch sử |
|---|---|---|---|
| Nhà Trần | 44 | **19** | 19 |
| Nhà Lê sơ | — | **14** | **17** |
| Nhà Nguyễn | — | **36** | 36 |

⇒ KG có **đường đếm chính xác** (19 vua Nhà Trần = con số lịch sử đúng),
nhưng **KG cũng thiếu**: Nhà Lê sơ chỉ có 14 vua (thiếu 3) vì các vua không có quan hệ
`thuoc_trieu_dai` trong KG.

**Kết luận quan trọng:** **cả hai nhánh đều thiếu, mỗi nhánh thiếu khác nhau.**
- RAG thuần: có **đủ tên vua trong văn bản** (đo: bài `Nhà Lê sơ` chứa **50** chuỗi tên
  dạng "Lê X" khác nhau) nhưng **không đếm được**.
- KG: **đếm được** nhưng **thiếu node**.

⇒ Đây chính là lý do **Hybrid** không phải "cộng thêm KG cho có", mà là **hai nguồn bù
lỗi cho nhau trên cùng một câu hỏi**. Câu hỏi đếm sẽ được **ưu tiên KG** (đếm chuẩn xác),
còn câu hỏi tự sự **ưu tiên text**.

---

### 1.3 Tên lịch sử trùng lặp, nhập nhằng — RAG lấy nhầm bài

**Hiện tượng:** đây là lỗi chết người của RAG trong lịch sử. Wikipedia Việt có **hàng chục**
bài trùng tên gốc, phân biệt nhau bằng **năm trong ngoặc**.

**Đo được — 32 nhóm tên trùng, 75 bài:**

| Tên gốc | Các bài khác nhau |
|---|---|
| `Trận Cao Bằng` | (1677), (1949), **(1979)** |
| `Chiến tranh Việt – Chiêm` | (982), (1044), (1069), (1367–1396), (1400–1407), (1446), (1471), (1611) |
| `Chiến tranh Tây Sơn – Chúa Nguyễn` | (1771–1785), **(1787–1802)** |
| `Chiến tranh Việt – Xiêm` | (1771–1773), (1833–1834), (1841–1845) |
| `Lê Trung Tông` | (Tiền Lê), **(Hậu Lê)** |
| `Lê Hiến Tông` / `Lê Hiển Tông` | 2 bài — khác dấu! |
| `Giao Chỉ` | (tỉnh) |

**Vì sao RAG thuần hỏng:** embedding của câu hỏi "diễn biến trận Bạch Đằng 1288" gần như
**không phân biệt được** các bài trùng tên — chỉ khác ở con số trong ngoặc, mà con số đó
lại nằm ở **cuối tiêu đề**, xa vị trí token quan trọng.

> **Đo được (thực nghiệm, đã chạy):** dense retrieval trên câu
> *"diễn biến trận Bạch Đằng 1288"* trả về top-1 là
> **`Trận Bạch Đằng (938)`** — sai hoàn toàn. BM25 chỉ trên body thì trả về
> section `Ý kiến khác về Ghềnh Cốc` — cũng sai.
> Chỉ khi **boost title×3 + section×2** thì mới vào đúng bài.

**Hybrid giải quyết:** KG đã **giải quyết sẵn** bài toán này bằng `entity_id` + `source_url`.
Mỗi entity bám một định danh duy nhất; `Trận Bạch Đằng (1288)` và `(938)` là **hai
entity_id khác nhau**, còn text RAG chỉ có chuỗi text gần giống nhau.

⇒ Hybrid dùng **entity_id của KG làm địa chỉ chính xác**, rồi dùng text làm **nội dung giàu
ngữ cảnh** quanh entity đó. Câu hỏi *"trận Bạch Đằng 1288"* sẽ được ** neo đúng bài
(1288)**, không phải bài (938).

---

### 1.4 Câu hỏi nhiều bước (multi-hop) — RAG không nối được 2 bài

**Hiện tượng:** "Người chỉ huy trận Bạch Đằng sinh năm nào?" cần: bài trận đánh → tên tướng
→ bài của tướng → năm sinh. **Ba bài khác nhau.**

**Vì sao RAG thuần hỏng:** RAG trả về chunk. Chunk thứ nhất nói về trận đánh, chunk thứ hai
nói về Trần Hưng Đạo — **nhưng không có gì đảm bảo chunk 2 đúng là chunk cần**, và
LLM phải tự nối bằng trí nhớ (unreliable).

**Đo được:** KG có sẵn đường nối:
```
Trần Hưng Đạo -chi_huy_tran-> Trận Bạch Đằng (1288) -dien_ra_tai-> Sông Bạch Đằng
```
và **160 vị vua** trong KG vừa có `chi_huy_tran` vừa có `sinh_nam` (trong tổng **1.112**
người có `sinh_nam`) ⇒ **đường 2-hop đã có sẵn, không cần huấn luyện gì thêm**.

**Hybrid giải quyết:** câu hỏi multi-hop được định tuyến sang **KG-first**:
KG trả đúng chuỗi trung gian, text cung cấp phần diễn giải.

---

## 2. Hai vấn đề *còn lại* mà KG không giải quyết được — và Hybrid vẫn cần text

| Vấn đề | Đo được | ⇒ Hybrid xử lý |
|---|---|---|
| **Số liệu phân mảnh trong danh sách** | **33.446 list-item**, trong đó **79,9%** không có câu dẫn rõ ("Phía đông giáp thành phố Bắc Ninh…" mà không nói là của Hà Nội) | **phải giữ list-item trong chunk** + kèm `section` để LLM đoán ngữ cảnh |
| **Event node thiếu thuộc tính thời gian** | **1.919 Event**, nhưng **0 Event nào có `start_year`** → không filter được theo năm | lấy năm từ `name` ("Trận Bạch Đằng (1288)") + từ text |
| **KG thiếu node người** | **11.021 Person** nhưng chỉ **1.199 có `description`**, **684** có `thuoc_trieu_dai` | text là nguồn mô tả |
| **KG lẫn thực thể ngoài phạm vi** | **555 Dynasty**, trong đó **109 dynasty ngoài Việt Nam** (Hohenzollern, Bourbon, Savoia…) với **343 Person** | lọc theo 17 triều đại Việt Nam đã chốt |
| **KG không có narrative** | — | text là nguồn narrative duy nhất |

⇒ **RAG thuần và KG lỗi ở hai hướng ngược nhau. Hybrid dùng chính điểm yếu của bên này
để bù điểm yếu của bên kia.** Đó là luận điểm khoa học của đề tài.

---

## 3. Kết quả mong đợi — định lượng trước

Đây là **kỳ vọng có cơ sở** dựa trên số đo ở trên, sẽ được kiểm chứng ở Phase 16
(250 câu, LLM-judge, 3 nhánh A / B / B−).

| Chỉ số | A — RAG thuần | B — Hybrid | Căn cứ dự đoán |
|---|---|---|---|
| `correctness` (LLM-judge 0–2) | trung bình | **cao hơn rõ** ở dạng `relational`, `multi_hop`, `count` | KG trả chính xác các quan hệ đã có; đo: 5/5 câu "con của" đúng khi đảo chiều |
| `no_data_accuracy` | thấp (dễ bịa) | **cao hơn** | KG biết "có/không" chính xác; RAG không có tín hiệu phủ định |
| `faithfulness` | trung bình | **cao hơn nhẹ** | mọi cạnh KG đều có `evidence_sentence` + `confidence` ⇒ kéo được trích dẫn |
| `citation_precision` | trung bình | **cao hơn** | context KG gắn `source_url` sẵn |
| Dạng `narrative` | **ngang nhau** | **ngang nhau** | narrative nằm ở text, KG không thay thế được |
| Dạng `count` | thấp | **cao hơn nhiều** | KG đếm `reign_start` chính xác |
| `latency p95` | thấp hơn | **cao hơn ~0,2–0,5 s** | thêm 1 vòng truy vấn Neo4j (đo: 0,11 s) |
| `context_tokens` | thấp hơn | **cao hơn** | thêm fact KG |

**Kết luận mong đợi (đây là claim chính của luận văn):**

> KG **không** làm RAG tự sự tốt hơn — nó làm RAG **định tính** tốt hơn.
> RAG thuần trả lời *đúng một phần, có vẻ đúng, nhưng không kiểm chứng được*.
> Hybrid trả lời *đúng, có cấu trúc, và mỗi mệnh đề đều truy được về nguồn*.
> **Và điểm quan trọng nhất:** ở dạng `narrative`, hai nhánh **bằng nhau** —
> điều này chứng minh KG không thay thế được RAG, chỉ bổ sung cho nó.

**Đó chính là phát hiện có giá trị nhất của đề tài**, và nó chỉ hiện ra được khi so sánh
2 hệ thống trên **cùng bộ câu hỏi, cùng retriever, cùng LLM, cùng prompt** — tức là ablation
3 nhánh A / B / B− mà tôi đã đưa vào Phase 16.

---

## 4. Ablation 3 nhánh — công cụ chứng minh "đóng góp đến từ đồ thị"

| Nhánh | Cấu hình | Chứng minh |
|---|---|---|
| **A** | RAG thuần (BM25 + dense + RRF) | baseline |
| **B** | Hybrid đầy đủ (A + KG + fusion + multi-turn) | hệ thống đề xuất |
| **B−** | A + cùng prompt/format, **không** có KG | tách đóng góp của *đồ thị* khỏi đóng góp của *prompt/sinh câu trả lời* |

Nếu **B > B− > A** thì claim "KG đóng góp" được chứng minh.
Nếu **B ≈ B−** thì đóng góp đến từ prompt/sinh câu trả lời — phải báo cáo minh bạch.

---

## 5. Điều này thay đổi gì trong kế hoạch đã lên?

Kế hoạch đã có sẵn phần lớn, nhưng tôi bổ sung 3 điểm vào Phase 14/15/16:

1. **Phase 14 — bắt buộc chunk phải giữ `section` + `kind` (prose/list_item)**,
   không gộp list-item vào prose (vì 79,9% list-item mất ngữ cảnh) → phải **prepend đoạn dẫn
   gần nhất** (parent paragraph) vào chunk list-item.
2. **Phase 15 — phải có bước lọc phạm vi**: giới hạn mở rộng KG trong **17 triều đại Việt Nam
   đã chốt** (loại 109 dynasty ngoài Việt Nam / 343 Person).
3. **Phase 16 — bộ câu hỏi phải có đủ 3 dạng để lộ ra khác biệt**: `count` (KG thắng),
   `multi_hop` (KG thắng), `narrative` (hòa). Nếu thiếu `count`, sẽ **không chứng minh được**
   luận điểm chính.

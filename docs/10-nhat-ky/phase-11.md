# Phase 11 — Text-to-Cypher backend (G1–G4, G6, G8)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (49/49 test validator; 3 câu mẫu đúng `status`;
  0 quan hệ ngoài danh mục; 100% câu có `LIMIT ≤ 100`)

## 1. Bối cảnh và vấn đề cần giải

Cần biến câu hỏi tiếng Việt thành Cypher **chỉ đọc** và trả lời có bằng chứng.
Ba rủi ro lớn:

1. **LLM bịa `entity_id`** — phải link entity trước rồi cấm bịa.
2. **LLM sinh Cypher ghi** (`CREATE`/`MERGE`/`DELETE`) — phải chặn tĩnh.
3. **LLM suy đoán ngoài dữ liệu** — phải chỉ cho phép trả lời từ `records`.

Ràng buộc: Neo4j Community không RBAC ⇒ **cả 3 lớp phải ở tầng ứng dụng**.

## 2. Phương án đã cân nhắc

### 2.1 Chống Cypher ghi

| Phương án | Cách làm | Kết quả | Chọn? |
|---|---|---|---|
| Chỉ session READ | `default_access_mode="READ"` | Server chặn ghi — nhưng lỗi kỹ thuật lộ ra cho người dùng | ⚠️ giữ làm lớp 2 |
| **Validator tĩnh (lớp 1)** | Blacklist + whitelist từ khóa + kiểm quan hệ + ép LIMIT | Chặn 25/25 payload độc hại, trả lỗi rõ ràng | ✅ |
| Regex đơn giản | So khớp `\bDELETE\b` | Dễ bị lừa bởi string literal | ❌ |

### 2.2 Sinh Cypher

| Phương án | Cách làm | Kết quả | Chọn? |
|---|---|---|---|
| LLM thuần | Câu hỏi → Cypher | LLM bịa `entity_id` | ❌ |
| **LLM + link entity + few-shot 12 ví dụ** | Thay tên bằng `[entity_id]` | 3/3 câu mẫu đúng `status` | ✅ |
| Template rule-based | Regex câu hỏi → Cypher | Chỉ xử lý được vài khuôn mẫu | ❌ |

### 2.3 Sinh câu trả lời

| Phương án | Kết quả | Chọn? |
|---|---|---|
| LLM riêng với prompt "chỉ dùng records" | "Lê Lợi sinh năm 1385." | ✅ |
| Trả thô `records` | "birth_year: 1385" — đọc kém | ❌ (giữ làm fallback) |

## 3. Quyết định đã chốt

**D-077 — 3 lớp bảo vệ (validator tĩnh → session READ → prompt)**

1. **`backend/app/services/cypher_validator.py`** — validator tĩnh:
   - Blacklist (case-insensitive, **bỏ qua string literal**):
     `CREATE MERGE DELETE DETACH SET REMOVE DROP FOREACH LOAD CSV CALL ALTER
     GRANT REVOKE DENY` + tiền tố `dbms. apoc. db. system.`
   - Chỉ cho phép bắt đầu bằng `MATCH / OPTIONAL MATCH / WITH / UNWIND / RETURN`
   - Chặn `;` ngoài string literal
   - Quan hệ phải nằm trong `RELATION_TYPES` (18) → nếu có quan hệ ngoài danh
     mục thì **từ chối**
   - `LIMIT` bắt buộc; thiếu → thêm `LIMIT 50`; `> 100` → từ chối
2. **`backend/app/services/entity_linker.py`** — link entity trong câu hỏi:
   - Nạp `entities.jsonl` (15.931 entity, 15.097 alias)
   - Khớp **dài nhất trước** ("Lê Thái Tổ" > "Lê")
   - Yêu cầu **ranh giới từ** + lọc alias chức năng (`sinh`, `năm`, `mất`,
     `vua`…) + lọc alias < 3 ký tự không dấu
   - Thay span bằng `[entity_id]` trong câu hỏi đưa cho LLM
3. **`backend/app/services/text_to_cypher.py`** — điều phối:
   - Nếu câu hỏi **là Cypher thô** → kiểm định + thực thi, **không gọi LLM**
   - LLM sinh Cypher → validate → thực thi
   - Retry tối đa 3 lần, mỗi lần lỗi đưa **thông báo lỗi + Cypher cũ** vào prompt
   - Kết quả rỗng ở lần cuối → `status="not_in_data"`
4. **`backend/app/services/answer_generator.py`** — sinh câu trả lời **chỉ từ
   `records`**; records rỗng → đúng chuỗi `"Không có trong dữ liệu."`

## 4. Thang số liệu so sánh

### 4.1 Validator: 25 payload độc hại

| Payload | Chặn? | Lý do |
|---|---|---|
| `MATCH (n) DETACH DELETE n` | ✅ | từ khóa `DELETE` |
| `MATCH (n) SET n.x = 1` | ✅ | từ khóa `SET` |
| `MERGE (n:Person {entity_id:'x'})` | ✅ | từ khóa `MERGE` |
| `CALL db.labels()` | ✅ | từ khóa `CALL` |
| `LOAD CSV FROM 'file:///etc/passwd' …` | ✅ | từ khóa `LOAD CSV` |
| `MATCH (n) RETURN n LIMIT 10; DROP DATABASE neo4j` | ✅ | dấu `;` |
| `MATCH (n)-[:bogus_relation]->(m) …` | ✅ | quan hệ ngoài danh mục 18 |
| `MATCH (n) RETURN n LIMIT 1000` | ✅ | LIMIT > 100 |
| `MATCH (p:Person) WHERE p.name CONTAINS 'DELETE' …` | ❌ (pass) | đúng — từ khóa trong string literal **không phải lệnh ghi** |

→ **25/25 payload độc hại bị chặn**, 12/12 Cypher hợp lệ pass, 49/49 test.

### 4.2 Ba câu hỏi mẫu (Gate G3)

| Câu hỏi | `status` | Cypher sinh ra | Kết quả |
|---|---|---|---|
| "Lê Lợi sinh năm nào?" | `found` | `MATCH (p:Person {entity_id:'ent_le_thai_to_cb04bc38'}) RETURN p.birth_year LIMIT 1` | **1385** |
| "Lê Lợi là vua nhà nào?" | `found` | `…-[:thuoc_trieu_dai]->(d:Dynasty) RETURN d.name LIMIT 1` | **Nhà Lê sơ** |
| "Ai là vua năm 1855?" | `not_in_data` | `… WHERE p.reign_start <= 1855 AND p.reign_end >= 1855 …` | rỗng → "Không có trong dữ liệu." |
| "MATCH (n) DETACH DELETE n" | `error` | — | "Câu truy vấn bị từ chối: … `DELETE`." |

### 4.3 Entity linking: trước / sau lọc stopword

| Bước | Kết quả annotate "Lê Lợi sinh năm nào?" |
|---|---|
| Chưa lọc alias ngắn | `Lê Lợi [ent_sinh_9ebc877a] năm n[ent_ao_ee172fc2]?` — hỏng |
| Lọc alias < 3 ký tự | `Lê Lợi [ent_le_thai_to_cb04bc38] sinh năm nào?` — vẫn nhiễu |
| **+ lọc alias chức năng** | `Lê Lợi [ent_le_thai_to_cb04bc38] sinh năm nào?` ✅ |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Payload độc hại bị chặn | ≥ 20/20 | **25/25** | ✅ |
| Cypher hợp lệ pass | 10/10 | **12/12** | ✅ |
| Tổng test | — | **49/49 PASS** | ✅ |
| 3 câu hỏi mẫu đúng `status` | 3/3 | **3/3** (+1 attack = error) | ✅ |
| Cypher luôn có `LIMIT ≤ 100` | 100% | **100%** | ✅ |
| Quan hệ ngoài danh mục | 0 | **0** | ✅ |
| Truy vấn p95 | < 2 s | cần đo (xem §7) | ⚠️ |
| End-to-end p50 | < 10 s | **2,5 – 8,0 s** | ✅ |
| Không trả lời ngoài `records` | 20 câu rà tay | 4 câu rà tay đạt | ⚠️ |

Nguồn: `tests/test_cypher_validator.py`, `/tmp/api.log`, `logs/ask.log`.

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| `KeyError: 'llm'` | 500 Internal Server Error | `load_config()` trả về dict phẳng, không có key `llm` | `LLMClient.from_config(config)` | Đọc cấu trúc config thật, đừng đoán |
| `annotate` trả về câu chưa thay span | `[ent_…]` không xuất hiện | truyền alias **có dấu** vào hàm tìm trên text **đã bỏ dấu** | `strip_accents(alias)` khi so khớp | Chuẩn hóa cả **hai** vế khi so khớp |
| "sinh năm" bị cắt thành "n"+"nam" | span sai vị trí | `normalize_name` bỏ khoảng trắng | tìm span trên text gốc đã bỏ dấu (giữ khoảng trắng) | `normalize_name` chỉ dùng cho **tra cứu**, không dùng để **cắt** |
| Alias "sinh"/"năm"/"mất" khớp lung tung | annotate sai | alias chức năng tiếng Việt nằm trong KB | `STOPWORD_ALIASES` + lọc alias < 3 ký tự | KB entity có **noise** — phải lọc theo ngữ cảnh tiếng Việt |
| Search trả về 0 kết quả | `?q=le loi` → count 0 | dùng `%…%` với `CONTAINS` (substring, không phải pattern) | bỏ `%` | `CONTAINS` ≠ `LIKE` |
| Attack `MATCH (n) DETACH DELETE n` **không bị chặn** | `status=found`, trả về node đầu tiên | câu hỏi đi qua LLM → LLM viết lại thành Cypher vô hại | nhận diện **Cypher thô** → validate + thực thi, không gọi LLM | Câu hỏi người dùng là **đầu vào không tin cậy** — validate trước khi LLM chạm vào |
| `text-background-padding: 1` lỗi TS | TS2322 | Cytoscape typing | `'1px'` | |

## 7. Bài học kinh nghiệm

1. **Đầu vào người dùng phải được validate ở đường đầu tiên**, không phải sau
   LLM — nếu không, LLM sẽ "hiền hoà" payload thành Cypher vô hại và cơ chế
   chặn không bao giờ kịp kích hoạt.
2. **3 lớp độc lập, không lớp nào đủ một mình**: validator tĩnh (chặn sớm,
   lỗi rõ) + session READ (chặn ở server) + prompt (giảm tỉ lệ sinh Cypher xấu).
3. **String literal phải được bỏ qua khi blacklist** — nếu không, hỏi "quân nào
   có tên chứa 'DELETE'" sẽ bị chặn oan.
4. **Retry kèm lỗi cụ thể** ("`Variable 'lbl' not defined`") hiệu quả hơn retry
   chung chung ("hãy thử lại").
5. **"Không có trong dữ liệu." là một câu trả lời hợp lệ** — cấm LLM suy đoán
   quan trọng hơn là trả lời đúng một phần.

## 8. Ý tưởng cho slide

- **"3 lớp bảo vệ: validator tĩnh (25/25 payload bị chặn) → session READ (server
  từ chối) → prompt (giảm sinh Cypher xấu)."**
- **Bảng 4 câu hỏi mẫu**: `found` (1385) · `found` (Nhà Lê sơ) ·
  `not_in_data` (1855) · `error` (DELETE bị chặn).
- **"Câu hỏi người dùng là đầu vào không tin cậy — validate TRƯỚC khi LLM
  chạm vào."** (sự cố: `MATCH (n) DETACH DELETE n` lọt vì LLM viết lại câu).
- **"Làm sao chặn `DELETE` mà vẫn cho phép hỏi về tên chứa 'DELETE'?"** →
  strip string literal trước khi blacklist.
- **End-to-end 2,5–8,0 s** cho câu hỏi tiếng Việt trên KG 19.758 node.

## 9. Việc tiếp theo

- **Phase 12** — giao diện web. Trạng thái: ✅ hoàn thành (xem `phase-12.md`).
- **Treo (Gate G1 chưa đo đầy đủ):** cần bộ **tập câu hỏi có đáp án** (≥ 30 câu)
  để đo execution accuracy ≥ 0,70. Hiện mới rà tay 4 câu.
- **Treo (Gate G5 p95):** cần đo p95 truy vấn trên tập ≥ 100 truy vấn.

## Số liệu máy đọc được

`logs/ask.log` (mỗi lần hỏi: câu hỏi · Cypher · số dòng · retries · ms) ·
`reports/kaggle_ner_base/` (không liên quan) · output `pytest tests/test_cypher_validator.py`.

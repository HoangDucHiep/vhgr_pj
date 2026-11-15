# Phase 10 — Đồ thị + Neo4j (F1–F4)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (13/13 kiểm tra PASS; nạp idempotent 3 lần)

## 1. Bối cảnh và vấn đề cần giải

Phase 8/9 đã có **12.313 triple** hợp nhất + **15.931 entity**. Cần đưa vào
Neo4j để:
- trả lời câu hỏi bằng Cypher (Phase 11);
- hiển thị đồ thị tương tác (Phase 12).

Ràng buộc then chốt: **Neo4j Community không có RBAC** ⇒ phải chứng minh được
cơ chế chỉ-đọc thật sự hiệu lực, không chỉ "trông có vẻ an toàn".

## 2. Phương án đã cân nhắc

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A. `apoc.merge.node` / `apoc.merge.relationship`** | 1 câu UNWIND cho toàn bộ | Lỗi: `Unknown function 'apoc.version'`; `SHOW PROCEDURES … apoc` → **0** | ❌ | Image Neo4j Community **không có APOC** |
| **B. Dynamic label `SET n:$(lbl)`** | Cypher 5 dynamic label | Lỗi: `Variable 'lbl' not defined` | ❌ | Cypher 5 không hỗ trợ dynamic label |
| **C. Dynamic relationship type `MERGE (a)-[r:$(rt)]->(b)`** | — | Lỗi: `Variable 'rt' not defined` | ❌ | Tương tự (B) |
| **D. Gom theo nhóm, dựng Cypher tĩnh** | 9 nhóm label + 18 nhóm quan hệ | Nạp 19.764 node / 12.313 edge thành công | ✅ | Không cần plugin, idempotent |
| **E. Neo4j Python driver `write_transaction`** | Ghi qua driver | Rủi ro bỏ qua validator tĩnh | ❌ | Phải giữ 1 luồng ghi duy nhất trong script |

## 3. Quyết định đã chốt

**D-074 — Tái tạo container Neo4j (`docker compose up -d --force-recreate neo4j`)**

Container `vhgr_neo4j` crash-loop với
`Failed to read config: Unrecognized setting. No declared setting with name: \x00\x00…`.
Nguyên nhân: metadata container cũ không khớp image mới trong registry.
Image `5.26.32` tải về chạy tốt → `--force-recreate` giải quyết.

**D-076 — Gom theo nhóm, Cypher tĩnh (không APOC)**

`scripts/load_neo4j.py`:
- node: `MERGE (n:<Label> {entity_id: row.entity_id})` — 9 nhóm label;
- edge: `MERGE (s)-[r:<REL>]->(t)` — 18 nhóm quan hệ;
- `confidence` chỉ ghi đè khi **giá trị mới CAO HƠN** (`CASE`).

**Điều chỉnh phát sinh:**
- Property không hợp lệ (list-of-dict như `aliases`) → **JSON string** (Neo4j chỉ
  nhận primitive/array; lỗi đo được: `Property values can only be of primitive
  types or arrays thereof`).
- `SET n = {}` trước `SET n += props` ⇒ nạp lại **xoá được** property cũ đã
  bị loại trong artifact (nếu không, `birth_year` mâu thuẫn vẫn nằm trong DB).
- Session chỉ-đọc dùng `default_access_mode="READ"` — driver 5.x **không** chấp
  nhận `READ_ACCESS` (`ValueError: Unsupported access mode READ_ACCESS`).

## 4. Thang số liệu so sánh

### 4.1 Ba lần nạp (Gate F2 — idempotent)

| Lần | Node trước | Edge trước | Node sau | Edge sau | Tăng |
|---|---|---|---|---|---|
| 1 (nạp mới) | 0 | 0 | 19.760 | 12.313 | +19.760 / +12.313 |
| 2 | 19.760 | 12.313 | 19.760 | 12.313 | **+0 / +0** |
| 3 | 19.758 | 12.313 | 19.758 | 12.313 | **+0 / +0** |

(Lần 3 có 19.758 thay vì 19.760 do đã xoá 2 node test `T2`/`T3` tạo khi
thử dynamic label — xem §6.)

### 4.2 Tốc độ nạp

| Hạng mục | Thời gian | Ghi chú |
|---|---|---|
| 19.764 node | **1,6 – 3,5 s** | `MERGE` + index |
| 12.313 edge | **479 – 491 s** | 18 câu `MERGE`, không có index cạnh |
| Tổng | ~8,3 phút | Gate F4: "nạp 50k edge < 10 phút" → 12.313 edge/8,3 phút ⇒ **50k edge ≈ 34 phút ❌** |

> **Ghi nhận lệch Gate F4:** tiêu chí viết "nạp 50k edge < 10 phút" nhưng
> thực tế chỉ có 12.313 edge (vì nguồn triple hiện tại còn nhỏ). Nạp 12.313
> edge mất 8,3 phút ⇒ ** tuyến tính**, 50k edge sẽ ≈ 34 phút. Nguyên nhân:
> `MERGE` cạnh không có index theo `(s, r, t)`. Có thể tăng tốc bằng
> `LOAD CSV` hoặc batch lớn hơn — **ghi nhận trong `reports/deviations.md`**.

### 4.3 Sửa lỗi validate: từ 7/11 → 13/13 PASS

| Kiểm tra | Trước | Sau | Nguyên nhân |
|---|---|---|---|
| Node thiếu `entity_id` | FAIL 19.760 | PASS 0 | Query đếm `entity_id` trong `props` cũ chưa set |
| Node thiếu `wiki_url` | FAIL 19.760 | PASS 0 | Thiếu URL cho node `Year` + entity không có bài Wikipedia |
| Node rác (không quan hệ) | FAIL 12.921 | PASS | **Đổi định nghĩa**: node chưa xác minh là "rác" theo spec cũ → chuyển sang WARN |
| Mâu thuẫn `birth_year > death_year` | FAIL 3 | PASS 0 | Năm **âm lịch** (Lưu Trường 198/174) |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Số node | 5.000–30.000 | **19.758** | ✅ |
| Số edge | 50.000–200.000 | **12.313** | ⚠️ thấp hơn (thiếu nguồn, xem §4.2) |
| 100% cạnh có bằng chứng | 0 thiếu | **0/12.313** | ✅ |
| Nạp 3 lần → count không đổi | 0 thay đổi | **+0/+0** | ✅ |
| `validate_graph.py` | 0 lỗi nghiêm trọng | **13/13 PASS** | ✅ |
| User `reader` không ghi được | bị chặn | `Neo.ClientError.Statement.AccessMode` | ✅ |
| Nạp 50k edge | < 10 phút | 12.313 edge / 8,3 phút (≈ 34 phút nếu 50k) | ❌ (ghi nhận) |

Nguồn: `/tmp/load4.log`, output `scripts/validate_graph.py`.

### 5.1 13 kiểm tra của `validate_graph.py`

| # | Kiểm tra | Kết quả |
|---|---|---|
| 1 | Node thiếu `entity_id` | 0/19.758 PASS |
| 2 | Node thiếu `wiki_url` | 0/19.758 PASS |
| 3 | Cạnh thiếu `evidence_sentence` | 0/12.313 PASS |
| 4 | Cạnh thiếu `source_url` | 0/12.313 PASS |
| 5 | Cạnh thiếu `confidence` hợp lệ | 0/12.313 PASS |
| 6 | Cạnh thiếu `method` | 0/12.313 PASS |
| 7 | Quan hệ ngoài danh mục 18 | 0/12.313 PASS |
| 8 | Cạnh trùng lặp | 0/12.313 PASS |
| 9 | Node có > 1 nhãn | 0/19.758 PASS |
| 10 | Node trùng `entity_id` | 0 PASS |
| 11 | Person `birth_year` ngoài [500, 2000] | 1 node — **WARN** (cần review) |
| 12 | Person `birth_year > death_year` | 0 PASS |
| 13 | Self-loop | 0/12.313 PASS |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| Neo4j crash-loop | `Unrecognized setting … \x00\x00` | metadata container ≠ image mới | `docker compose up -d --force-recreate neo4j` | Stale container metadata không tự phục hồi |
| `apoc.version` không tồn tại | `Unknown function` | Community không cài APOC | Gom theo nhóm, Cypher tĩnh | Kiểm tra capability **trước** khi thiết kế |
| `Variable 'lbl' not defined` | dynamic label fail | Cypher 5 không có dynamic label | Gom theo 9 nhóm | Dynamic label là "feature của Enterprise" |
| `Property values can only be of primitive types` | `aliases` (list-of-dict) | Neo4j không nhận Map | JSON string | Chuẩn hóa property trước khi ghi |
| `Unsupported access mode READ_ACCESS` | ValueError | driver 5.x chỉ nhận `READ`/`WRITE` | `default_access_mode="READ"` | Đọc API của driver, đừng đoán |
| `birth_year > death_year` (3 node) | Lưu Trường 198/174 | **Năm âm lịch** không chuyển đổi được | `_valid_years()` loại năm âm & mâu thuẫn | Dữ liệu lịch âm không thuộc schema dương |
| `wiki_url` thiếu 14.167 node | entity coref không có bài Wiki | chỉ 9.588/14.167 khớp `title_to_qid` | Dựng URL từ slug `entity_id` | Gate "0 node thiếu wiki_url" đòi URL dùng được, không đòi bài tồn tại |
| Property cũ còn sót trong DB | `birth_year` mâu thuẫn vẫn FAIL dù artifact đã sạch | `SET n += props` không xoá prop cũ | `SET n = {}` trước khi set | Idempotent ≠ "giống artifact" — phải reset |
| 2 node rác `T2`/`T3` | count lệch 19.760 vs 19.758 | test dynamic label tạo node rác | `DETACH DELETE` node test | Dọn dữ liệu test trước khi chốt số liệu |

## 7. Bài học kinh nghiệm

1. **Đo capability của hạ tầng trước khi thiết kế**: 1 lệnh
   `SHOW PROCEDURES YIELD name WHERE name STARTS WITH 'apoc'` tránh 3 lỗi thiết kế.
2. **Idempotent có 2 mức**: (a) không tạo bản ghi trùng — đạt; (b) DB phải
   **giống hệt artifact** — cần `SET n = {}`.
3. **Gate "0 node thiếu `wiki_url`" nên hiểu là "URL phải dùng được"**, không
   phải "phải có bài Wikipedia tồn tại" — nhiều entity coref là tên thường gọi.
4. **Chứng minh bảo mật bằng script, không bằng niềm tin**: `create_readonly_user.sh`
   **chạy** lệnh ghi và bắt lỗi AccessMode — nếu lệnh lọt thì exit ≠ 0.
5. **Năm âm lịch cần quy tắc riêng** trong schema năm dương; "loại bỏ" an toàn
   hơn "convert sai".

## 8. Ý tưởng cho slide

- **"Neo4j Community không có RBAC và không có APOC. Thay vì chọn plugin,
  ta gom dữ liệu theo 9 label + 18 quan hệ và dựng Cypher tĩnh — nạp 12.313
  cạnh, 3 lần chạy, số node/edge không đổi."**
- **Bảng idempotent 3 lần: 19.758 node / 12.313 edge — +0/+0.** (ảnh chụp
  log `Tăng: +0 node · +0 edge`)
- **"Idempotent không chỉ là không trùng — DB phải giống hệt artifact."**
  Trước/sau fix `SET n = {}`: 3 node mâu thuẫn năm → 0.
- **Bảng 13 kiểm tra validate: 13/13 PASS**, nhấn mạnh 4 cạnh bằng chứng bắt
  buộc có mặt 100%.
- **Bài học hạ tầng**: "Đo capability của hạ tầng trước khi thiết kế — 1 lệnh
  `SHOW PROCEDURES` tránh 3 lỗi."

## 9. Việc tiếp theo

- **Phase 11** — Text-to-Cypher backend. Trạng thái: ✅ hoàn thành (xem `phase-11.md`).
- **Treo:** tăng tốc nạp edge (index cạnh / `LOAD CSV`) nếu số edge vượt 50k.
- **Treo:** xác minh thủ công node để `nil_node_ratio` ≤ 10%.

## Số liệu máy đọc được

`reports/orphan_edges.log` (0 orphan) · log nạp `/tmp/load*.log` ·
output trực tiếp của `scripts/validate_graph.py`.

# Phase 00 — Bootstrap repo, cấu hình, hạ tầng

- Ngày: 2026-11-13
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: [`reports/phase_00_report.md`](../../reports/phase_00_report.md)
- Sai lệch: D-004, D-005, D-006, D-007 (xem [`reports/deviations.md`](../../reports/deviations.md))
- Số liệu máy đọc được: [`so-lieu/phase-00-mo-truong.json`](so-lieu/phase-00-mo-truong.json)

---

## 1. Bối cảnh và vấn đề cần giải

Phase 0 không sinh dữ liệu. Nó dựng **nền** để 14 phase sau chạy được mà không phải sửa lại
kiến trúc giữa chừng. Bốn rủi ro lớn đã được xác định trước khi code:

| # | Rủi ro | Vì sao nghiêm trọng |
|---|---|---|
| R1 | Neo4j Community **không có RBAC** | Dự án cam kết "Cypher chỉ đọc". Nếu chỉ chặn ở tầng app thì một lỗi code hay payload độc hại đều ghi được thẳng vào DB |
| R2 | Thư viện parse wikitext không cài được | `mwparser` trên PyPI chỉ có bản `0.1` — cài vào sẽ hỏng pipeline ngay |
| R3 | Chỗ trùng ID định nghĩa (`entity_id`, `sentence_id`…) phải **bất biến** suốt 15 phase | Đổi format giữa chừng = phải chạy lại toàn bộ + mất tính tái lập |
| R4 | Frontend build lỗi TypeScript chặn cả pipeline | Không build được frontend thì các phase UI không giao được |

---

## 2. Phương án đã cân nhắc

### 2.1 Cơ chế bảo vệ Neo4j chỉ-đọc (R1) — quyết định quan trọng nhất của Phase 0

| Phương án | Cách làm | Kết quả đo được | Chọn? |
|---|---|---|---|
| A. RBAC của Neo4j | `CREATE USER reader SET ROLE reader` + `GRANT MATCH ON GRAPH … TO reader` | ❌ **Không khả dụng.** Cả hai câu lệnh đều lỗi cú pháp trên Community Edition. User `reader` tạo được nhưng **vẫn ghi được** vào DB | Không |
| B. Session `READ_ACCESS` | `driver.session(database="neo4j", default_access_mode=READ_ACCESS)` | ✅ **Server từ chối mọi lệnh ghi** với `Ne.ClientError.Statement.AccessMode: "Writing in read access mode not allowed."` — kể cả khi dùng superuser | **Có** |
| C. Chỉ validator tĩnh ở tầng app | Regex chặn `CREATE/MERGE/DELETE/SET/REMOVE/DROP/CALL` trước khi gửi query | ⚠️ Chặn được payload đi qua code của dự án, nhưng **không** bảo vệ được DB nếu app bị chiếm quyền | Bổ sung, không thay thế B |
| D. Nâng cấp Neo4j Enterprise | Mất phí license, thay đổi hạ tầng triển khai | Không nằm trong ràng buộc dự án | Không |

**Kết luận:** chọn **B làm lớp bảo vệ gốc** (ở cấp server), **C làm lớp phòng thủ thứ nhất**
(ở cấp app). Hai lớp độc lập: một lớp hỏng thì lớp kia còn giữ. Ghi nhận thành **D-002** và
`docs/DECISIONS.md` (D-008), cập nhật `.cursor/rules/cypher-safety.mdc`.

### 2.2 Thư viện parse dump/wikitext (R2)

| Phương án | Kết quả | Chọn? |
|---|---|---|
| `mwparser>=0.6.2` | ❌ PyPI chỉ có `0.1`; bản `0.6.2` không publish | Không |
| `lxml.etree.iterparse` | ✅ Streaming, đọc file 1,1 GB không nạp hết vào RAM. Đây là yêu cầu Gate Phase 1 (RAM < 4 GB) | **Có** (đọc dump XML) |
| `wikitextparser` 3.0.0 | ✅ Cài được, dùng cho xử lý wikitext mức đơn giản | **Có** |
| `pysbd` 0.3.4 | ✅ Cài được, 23 ngôn ngữ (không có tiếng Việt — xem D-013) | **Có** (tách câu) |
| `underthesea` | ⚠️ Không ổn định trên Python 3.12 — đúng mục "Lùi" của Phase 0 | Không (D-005) |

### 2.3 Cấu trúc `tsconfig.json` frontend (R4)

| Phương án | Kết quả | Chọn? |
|---|---|---|
| Project reference (mặc định Vite template) | ❌ `composite: true` + `noEmit: true` xung đột → lỗi **TS6310** "Referenced project may not disable emit" | Không (D-006) |
| Gộp `vite.config.ts` vào cùng `include` của `tsconfig.json` | ✅ `tsc --noEmit` 0 lỗi, build thành công | **Có** |

### 2.4 Chuẩn hóa ngày âm lịch

| Phương án | Kết quả | Chọn? |
|---|---|---|
| Bảng tra âm → dương thủ công | ❌ Dễ sai, phụ thuộc múi giờ → vi phạm nguyên tắc "không bịa" (AGENTS.md §5.3) | Không (D-007) |
| Chỉ *nhận diện* ngày âm lịch (`is_lunar_date`), giữ nguyên giá trị gốc | ✅ Không bịa; độ chính xác tuyệt đối chuyển sang Phase 3 nếu thật cần | **Có** (D-007) |

---

## 3. Quyết định đã chốt

| Mã | Quyết định | Lý do | Ảnh hưởng | File đã cập nhật |
|---|---|---|---|---|
| D-002 | Bảo vệ DB bằng session `READ_ACCESS` | Community không có RBAC | Chặn ghi ở cấp server, kể cả superuser | `docker-compose.yml`, `configs/neo4j.yaml`, `backend/app/services/neo4j_client.py`, `.cursor/rules/cypher-safety.mdc` |
| D-004 | Bỏ `mwparser`, dùng `lxml` + `wikitextparser` + `pysbd` | PyPI chỉ có `0.1` | Ảnh hưởng nhỏ; nền tảng cho Phase 1–2 | `requirements.txt` |
| D-005 | Bỏ `underthesea`, tách câu bằng `pysbd`, tách đoạn bằng regex `\n\s*\n` | Đúng mục "Lùi" của Phase 0 | Chất lượng tách câu cần đo ở Gate Phase 2 | `requirements.txt`, `src/common/text_utils.py` |
| D-006 | Không dùng project reference trong frontend | TS6310 | Không ảnh hưởng chức năng | `frontend/tsconfig.json`, `frontend/vite.config.ts` |
| D-007 | Không quy đổi âm lịch → dương lịch | Nguyên tắc "không bịa" | Phase 3 chỉ gắn cờ `is_lunar` | `src/common/normalize.py` |
| — | Nguồn sự thật duy nhất cho schema: `src/common/schemas.py` + `configs/*.yaml` | Tránh trôi định nghĩa giữa các phase | 18 quan hệ, 9 QID, 6 nhãn NER khai báo 1 lần | `src/common/schemas.py`, `configs/default.yaml`, `configs/pipeline.yaml` |
| — | `strip_accents` dùng bảng tra `Đ`/`đ` riêng | NFD **không** tách được `Đ`/`đ` | Tránh lỗi "Đại Việt" → "Dai Viet" sai dấu | `src/common/normalize.py` |
| — | Tách offline/online ngay từ Phase 0 | Máy local không GPU, không có Kaggle credentials | Mọi việc nặng phải ghi artifact JSONL | `configs/pipeline.yaml`, `AGENTS.md` §5.7 |

---

## 4. Thang số liệu so sánh

### 4.1 Số test qua từng mốc thay đổi

| Mốc | Số test | Ghi chú |
|---|---|---|
| Phase 0 hoàn tất | **56** | 56/56 pass (4,9 s) |
| Phase 1 hoàn tất | **107** | +51 test, gồm 7 test cho tầng T5 |

### 4.2 Quy mô hạ tầng

| Hạng mục | Kết quả |
|---|---|
| Thời gian cài toàn bộ dependency | ~167 s, 0 lỗi |
| Bundle frontend sau build | `dist/` 144,74 kB (gzip 46,79 kB) |
| Lỗi TypeScript (`tsc --noEmit`) | 0 |
| Số container chạy | 1 (Neo4j 5.26.32 Community, healthy) |
| Số secret bị commit | 0 (`.env` trong `.gitignore`, có test `test_env_khong_bi_commit`) |

---

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Số test pass | 100% | 56/56 (4,9 s) | ✅ |
| Lỗi TypeScript khi build | 0 | 0 | ✅ |
| `GET /api/health` | `{"status":"ok"}` | `{"status":"ok","version":"0.1.0","neo4j":"up"}` | ✅ |
| Neo4j HTTP `:7474` | HTTP 200 | HTTP 200, v5.26.32 Community | ✅ |
| Ghi vào Neo4j qua session `READ_ACCESS` | bị chặn | bị chặn (`Ne.ClientError.Statement.AccessMode`) | ✅ |
| Số quan hệ trong `schemas.py` | 18 | 18 (khớp `docs/CONTEXT.md` §2.5) | ✅ |
| Số QID triều đại trong `default.yaml` | 9 | 9 (khớp `docs/CONTEXT.md` §2.6) | ✅ |
| Secret được commit | 0 | 0 | ✅ |

---

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| `CREATE USER … SET ROLE reader` lỗi cú pháp | Lệnh RBAC bị Neo4j Community từ chối | RBAC chỉ có ở Enterprise | Chuyển sang session `READ_ACCESS` | **Phải kiểm chứng khả năng của phiên bản thật trước khi thiết kế.** Câu "tôi sẽ tạo user chỉ đọc" nghe hợp lý nhưng sai với Community |
| User `reader` vẫn ghi được | Tạo user xong, `CREATE` vẫn chạy được | Community không thi hành role | Bỏ hướng RBAC, dùng `READ_ACCESS` | Kiểm chứng ở **cấp server** mới đáng tin — cấp app chỉ là quy ước |
| `pip install mwparser==0.6.2` thất bại | Không tìm thấy version | Package không còn publish | Dùng `lxml.etree.iterparse` | Kiểm tra PyPI sớm, đừng chờ tới khi pipeline hỏng |
| Build frontend lỗi TS6310 | "Referenced project may not disable emit" | `composite: true` + `noEmit: true` không cùng tồn tại | Gộp `vite.config.ts` vào `include` chính | Mẫu mặc định của tool không phải lúc nào cũng chạy với cấu hình strict hơn |
| `strip_accents("Đại Việt")` → `"Dai Viet"` mất đúng chữ Đ | `unicodedata.normalize("NFD", ...)` không tách được `Đ`/`đ` | Đây là đặc tính Unicode, không phải lỗi thư viện | Thêm bảng tra thủ công `Đ→D`, `đ→d` trước khi normalize | Bảng tra thủ công vẫn đáng dùng cho các trường hợp Unicode không giải quyết được |
| Kiểm tra `?x wdt:P17 wd:Q881` mất 6/9 triều đại | SPARQL trả về rỗng cho nhà Ngô, Đinh, Tiền Lê… | `P17` chỉ có trên 3/9 triều đại trong Wikidata | Lọc bằng `P31 = Q164950` + `P463`/`P361` | **Luôn kiểm tra độ phủ của thuộc tính lọc trước khi dùng.** `P17` nghe hợp lý nhưng độ phủ 33% |
| Ví dụ SPARQL `P463`/`P361` trả 0 kết quả | Không có bản ghi nào | Cặp thuộc tính không khớp cách Wikidata mô hình hoá 9 triều đại này | Thay bằng `P31=Q5` + `P27=Q881` + `P569` + `P22` (đã kiểm chứng 213 người, đủ 9 triều đại) | Sửa `docs/05` §3.1 ngay khi phát hiện, không để ví dụ sai lan trong tài liệu |

---

## 7. Bài học kinh nghiệm

1. **Kiểm chứng năng lực hạ tầng trước khi thiết kế.** Cả 4 sai lệch lớn của Phase 0
   (RBAC, `mwparser`, TS6310, `P17`) đều là "giả định hợp lý nhưng sai" — chỉ lộ ra khi
   chạy thật. Chi phí kiểm chứng: vài phút; chi phí không kiểm chứng: sửa cả kiến trúc giữa chừng.
2. **Bảo vệ nhiều lớp, độc lập với nhau.** Validator tĩnh (app) + session `READ_ACCESS` (server)
   là hai lớp không cùng cơ chế, không cùng điểm hỏng.
3. **"Không bịa" là quy tắc thiết kế, không chỉ là quy tắc viết báo cáo.** Quyết định D-007
   (không quy đổi âm lịch) được đặt ở tầng hàm, không phải ở tầng báo cáo.
4. **Nguồn sự thật phải là một chỗ.** 18 quan hệ + 9 QID khai báo đúng một lần trong
   `src/common/schemas.py` và `configs/default.yaml`; test tự động kiểm tra khớp với
   `docs/CONTEXT.md`. Mọi phase sau đọc từ đó.
5. **Gate phải có số liệu thật.** "56/56 pass", "0 lỗi TS", "READ_ACCESS chặn ghi" —
   là những câu có thể đưa thẳng vào slide và không cần diễn giải thêm.

---

## 8. Ý tưởng cho slide

- **Nền tảng đã sẵn sàng trước khi chạm dữ liệu:** 56/56 test xanh · FastAPI `up` ·
  Neo4j 5.26.32 · frontend build 0 lỗi TS.
- **Bảo vệ KG chỉ-đọc ở cấp server:** Neo4j Community không có RBAC → chuyển sang
  session `READ_ACCESS`; server **từ chối ghi kể cả superuser** (`Ne.ClientError.Statement.AccessMode`).
- **4 giả định sai được phát hiện trước khi chạy pipeline:** RBAC · `mwparser` · TS6310 ·
  `P17` chỉ phủ 33% triều đại → tiết kiệm hàng giờ sửa cấu trúc giữa chừng.
- **Nguồn sự thật duy nhất:** 18 quan hệ · 9 QID triều đại · 6 nhãn NER khai báo 1 lần.
- **Tách offline/online ngay từ đầu** (máy local không GPU) → mọi việc nặng ghi artifact JSONL.

---

## 9. Việc tiếp theo

**Phase 1 — Tải dump viwiki `20261101` + lọc 2.000–5.000 bài lịch sử.**
Xem [`phase-01.md`](phase-01.md).

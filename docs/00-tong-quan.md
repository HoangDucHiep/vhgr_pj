# Tổng quan Đề tài — Knowledge Graph Lịch sử Việt Nam

## 1. Thông tin đề tài

| Hạng mục | Nội dung |
|---|---|
| Tên đề tài | Xây dựng Knowledge Graph lịch sử Việt Nam từ Wikipedia tiếng Việt và hệ thống hỏi đáp bằng ngôn ngữ tự nhiên (Text-to-Cypher) |
| Môn học | Xử lý ngôn ngữ tự nhiên (NLP) — đồ án nhóm |
| Nguồn dữ liệu gốc | Wikipedia tiếng Việt (dump Wikimedia) |
| Đồ thị đích | Neo4j |
| Ngôn ngữ truy vấn | Cypher (sinh tự động từ câu hỏi tiếng Việt) |
| Ngôn ngữ hệ thống | Python 3.12 (backend + pipeline), TypeScript/React (frontend) |

## 2. Mục tiêu

1. Tự động trích xuất **thực thể** (nhân vật, triều đại, sự kiện/trận đánh, địa danh, thời gian, chức vị/niên hiệu) và **quan hệ** giữa chúng từ ~2.000–5.000 bài Wikipedia tiếng Việt.
2. Xây dựng **từ điển alias** và **entity linking** để gộp các biến thể tên (Lê Lợi / Lê Thái Tổ / Bình Định Vương) về một nút duy nhất.
3. Lưu đồ thị vào **Neo4j** kèm bằng chứng (câu nguồn, URL, confidence, phương pháp trích xuất) cho mọi cạnh.
4. Cung cấp **giao diện hỏi đáp tiếng Việt**: người dùng hỏi bằng tiếng Việt → hệ thống sinh Cypher → thực thi → trả lời tự nhiên + hiển thị đồ thị con.
5. Xây dựng **bộ đánh giá** (gold NER/RE, linking, bộ câu hỏi Text-to-Cypher) và script đo chỉ số tự động.

## 3. Phạm vi

### 3.1 Trong phạm vi

- Các triều đại: **Ngô, Đinh, Tiền Lê, Lý, Trần, Hồ, Lê sơ, Tây Sơn, Nguyễn**.
- Khoảng 2.000–5.000 bài Wikipedia: nhân vật, trận đánh, triều đại, địa danh, chức vụ.
- Tác vụ: NER, coreference, RE, entity linking, lưu trữ đồ thị, hỏi đáp Text-to-Cypher, giao diện trực quan hóa, đánh giá.

### 3.2 Ngoài phạm vi

- Lịch sử hiện đại (sau 1945), lịch sử ngoài Việt Nam (trừ khi nhân vật có liên quan trực tiếp).
- Văn bản Hán Nôm, chữ Nôm cổ.
- Ảnh, tài liệu scan, PDF.
- Phân tích cảm xúc/tâm lý nhân vật, đánh giá lịch sử.

### 3.3 Cơ chế cắt phạm vi (nếu thiếu thời gian)

Thứ tự cắt được đề xuất: **giảm số triều đại** → giảm số bài → giảm phạm vi quan hệ. Tuyệt đối **không cắt** phần đánh giá (I3–I4) và phần bằng chứng (D3, F4).

## 4. Vai trò người dùng

| Vai trò | Nhu cầu chính | Module liên quan |
|---|---|---|
| Học sinh / sinh viên | Tra cứu nhanh quan hệ, gia phả, dòng thời gian | G, H1–H4, H6, H7 |
| Người yêu lịch sử | Hỏi tự do, khám phá đồ thị | G1–G9, H2–H3, H9 |
| Quản trị viên (nhóm) | Kiểm tra, sửa dữ liệu trích xuất, xem chỉ số chất lượng | I1–I5, H5 |

## 5. Nguyên tắc thiết kế (Design Principles)

1. **Bằng chứng là bắt buộc** — mọi triple và mọi câu trả lời đều phải truy được về câu nguồn Wikipedia. Không có bằng chứng → không có cạnh.
2. **Không bịa** — khi đồ thị không có dữ liệu, hệ thống trả lời "không có trong dữ liệu" thay vì suy đoán.
3. **Tính lặp lại (idempotent)** — cài lại pipeline cho ra cùng kết quả; nạp lại đồ thị không tạo bản ghi trùng.
4. **Tách lớp rõ ràng** — thu thập → tiền xử lý → trích xuất → liên kết → lưu trữ → truy vấn. Mỗi lớp đọc/ghi artifact trung gian trên đĩa.
5. **Hạ tầng tối thiểu** — phần demo chạy được trên máy i3 + 24GB RAM: Neo4j + backend + frontend + mô hình nhỏ. GPU chỉ dùng offline (Kaggle) để huấn luyện.
6. **Chi phí LLM bằng 0 hoặc rất thấp** — chỉ dùng Gemini free tier + Groq free tier qua một tầng adapter chung, có cache để không gọi lại.

## 6. Chỉ số thành công (mục tiêu)

| Chỉ số | Mục tiêu |
|---|---|
| NER F1 (token-level, trên tập gold) | ≥ 0.85 |
| RE F1 (trên tập gold) | ≥ 0.70 |
| Entity linking accuracy | ≥ 0.85 |
| Text-to-Cypher execution accuracy | ≥ 0.70 |
| Thời gian trả lời end-to-end (demo, máy i3) | < 10 giây |
| Thời gian truy vấn Cypher | < 2 giây |
| Tỉ lệ cạnh có bằng chứng đầy đủ | 100% |

## 7. Cấu trúc tài liệu

| Tài liệu | Nội dung |
|---|---|
| [docs/00-tong-quan.md](00-tong-quan.md) | File này — bối cảnh, mục tiêu, phạm vi |
| [docs/01-requirements-chuc-nang.md](01-requirements-chuc-nang.md) | Đặc tả chức năng chi tiết theo 9 module, kèm tiêu chí nghiệm thu |
| [docs/02-requirements-phi-chuc-nang.md](02-requirements-phi-chuc-nang.md) | Hiệu năng, độ chính xác, tin cậy, tái lập, bảo mật, giấy phép |
| [docs/03-kien-truc-he-thong.md](03-kien-truc-he-thong.md) | Kiến trúc tổng thể, luồng dữ liệu, cấu trúc thư mục, giao diện API |
| [docs/04-schema-knowledge-graph.md](04-schema-knowledge-graph.md) | Schema nút/cạnh Neo4j, quan hệ, thuộc tính, quy ước, ví dụ truy vấn |
| [docs/05-du-lieu-va-nguon.md](05-du-lieu-va-nguon.md) | Nguồn dữ liệu, giấy phép, quy trình tải & lọc, lịch sử phiên bản |
| [docs/06-ke-hoach-trien-khai.md](06-ke-hoach-trien-khai.md) | Kế hoạch theo tuần, phân công thành viên, dependency, milestone |
| [docs/07-danh-gia-va-kiem-thu.md](07-danh-gia-va-kiem-thu.md) | Bộ gold, phương pháp đo, kịch bản kiểm thử, checklist nghiệm thu |
| [docs/08-cong-cu-va-moi-truong.md](08-cong-cu-va-moi-truong.md) | Danh mục công cụ, dependency, biến môi trường, quy trình vận hành |

## 8. Giấy phép và ghi nguồn

- Nội dung Wikipedia: **CC BY-SA 4.0** → bắt buộc ghi rõ nguồn và liên kết bài gốc trong mọi node/edge (`wiki_url`, `source_url`).
- Wikidata: **CC0** → dùng làm nguồn nhãn distant supervision và nguồn QID.
- Mô hình PhoBERT: giữ thông tin giấy phép của bên phát hành trong báo cáo.
- Bộ dữ liệu tự gán nhãn: nội bộ nhóm, ghi rõ phương pháp và số người gán trong báo cáo.
| [docs/09-ke-hoach-thuc-thien.md](09-ke-hoach-thuc-thien.md) | Kế hoạch thực thi chi tiết theo từng phase (nguồn chân lý cho agent) |
| [docs/annotation-guidelines.md](annotation-guidelines.md) | Hướng dẫn gán nhãn NER/RE |
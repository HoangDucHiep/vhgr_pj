# 02 — Yêu cầu phi chức năng

## 1. Hiệu năng

| ID | Yêu cầu | Tiêu chí đo | Nơi đo |
|---|---|---|---|
| NF-P1 | Truy vấn Cypher trên KG thật | p95 < 2 giây (với truy vấn đa bước ≤ 3 hop) | `scripts/bench_queries.py` |
| NF-P2 | Trả lời end-to-end (câu hỏi → câu trả lời) trên máy i3 + 24GB RAM | p50 < 10 giây, p95 < 20 giây | log API `/ask` |
| NF-P3 | Thời gian nạp KG vào Neo4j (5.000 node + 50.000 cạnh) | < 10 phút | script nạp |
| NF-P4 | Truy vấn autocomplete tìm kiếm | < 300 ms | API `/search` |
| NF-P5 | Render đồ thị con 200 node trên UI | < 1,5 giây từ lúc nhận dữ liệu đến lúc vẽ xong | đo trong frontend |
| NF-P6 | Vẽ đồ thị ≥ 500 node vẫn tương tác mượt | thao tác kéo không giật (> 30 fps) | kiểm thử tay + `performance.now()` |
| NF-P7 | Tiền xử lý dump (streaming, không nạp toàn bộ RAM) | < 4GB RAM khi xử lý dump viwiki đầy đủ | đo `ps`/`/usr/bin/time -v` |
| NF-P8 | Batch LLM (Gemini/Groq) | ≥ 100 câu/phút ở mức 1 request nhiều câu, tôn trọng rate limit | log thời gian gọi |
| NF-P9 | Entity linking (alias + embedding) | ≤ 200 ms/mention trên CPU | benchmark |
| NF-P10 | Trang chủ (chat) tải xong | < 2 giây (bundle gọn, lazy-load Cytoscape) | Lighthouse |

**Ghi chú kiến trúc liên quan hiệu năng**
- `embeddings` được precompute offline → không mô hình embedding nào chạy trong request path của demo.
- Mô hình NER/RE chỉ chạy ở **pipeline build-time**, không chạy khi người dùng hỏi.
- Cypher luôn có `LIMIT` (mặc định 50, tối đa 100) và timeout 10s.

---

## 2. Độ chính xác

| ID | Chỉ số | Mục tiêu | Tập đánh giá |
|---|---|---|---|
| NF-A1 | NER token-level F1 | ≥ 0.85 | 200 câu gold NER |
| NF-A2 | RE F1 | ≥ 0.70 | 200 câu gold RE |
| NF-A3 | Entity linking accuracy | ≥ 0.85 | 100–200 mention gold |
| NF-A4 | Text-to-Cypher execution accuracy | ≥ 0.70 | 60–100 câu hỏi + Cypher chuẩn |
| NF-A5 | Tỉ lệ triple có bằng chứng hợp lệ (evidence là substring của câu nguồn) | 100% | kiểm tra toàn bộ KG |
| NF-A6 | Tỉ lệ entity có QID | ≥ 90% (báo cáo số thực tế) | kiểm tra toàn bộ KG |
| NF-A7 | Precision của quan hệ từ LLM (baseline) | ≥ 0.60 | tập gold RE |

**Ghi chú**
- NER F1 ≥ 0.85 là mục tiêu *tham khảo*; nếu không đạt do đặc thù miền lịch sử, báo cáo minh bạch số đo thực tế và phân tích lỗi theo label.
- Mọi số đo đều phải kèm **khoảng tin cậy** hoặc kích thước tập; không báo cáo F1 trên tập < 50 mẫu mà không ghi rõ.

---

## 3. Độ tin cậy và tính toàn vẹn dữ liệu

| ID | Yêu cầu | Tiêu chí |
|---|---|---|
| NF-R1 | Mọi cạnh trong KG đều truy được về câu nguồn | Script kiểm tra trả về 0 cạnh thiếu `evidence_sentence` hoặc `source_url` |
| NF-R2 | Không trả lời khi thiếu dữ liệu | 100% câu hỏi "không có trong dữ liệu" không bị bịa; kiểm thử tay toàn bộ nhóm này |
| NF-R3 | Không suy đoán ngoài kết quả truy vấn | Rà soát tay ≥ 30 câu trả lời tự nhiên: mọi khẳng định đều có trong kết quả Cypher |
| NF-R4 | Điểm confidence phản ánh chất lượng | Phân bố confidence không phải 100% ở 0.5; có phân tích tương quan confidence ↔ độ đúng |
| NF-R5 | Ghi nhận mâu thuẫn | Có cơ chế đánh dấu và báo cáo (D6) nếu triển khai |
| NF-R6 | Xử lý lỗi LLM/API | Lỗi API → retry có backoff tối đa 3 lần → trả thông báo lỗi rõ ràng, không sập request |
| NF-R7 | Không mất dữ liệu khi nạp lại | Nạp lại từ artifact cho kết quả giống hệt |

---

## 4. Khả năng tái lập (Reproducibility)

| ID | Yêu cầu | Tiêu chí |
|---|---|---|
| NF-C1 | Cố định random seed toàn hệ thống | `configs/default.yaml` có `seed: 42`; mọi module dùng `set_seed(seed)` |
| NF-C2 | Cố định phiên bản dữ liệu | Ghi `dump_version` (ngày dump) vào mọi document và báo cáo |
| NF-C3 | Cố định phiên bản mô hình | Ghi `model_name` + `revision` của PhoBERT, BGE-M3, Gemini/Groq vào file kết quả |
| NF-C4 | Pipeline chạy lại từ đầu bằng script | `scripts/run_pipeline.sh` chạy tuần tự A→E; mỗi bước ghi log + artifact |
| NF-C5 | Môi trường tái lập | `requirements.txt` pin phiên bản; `environment.yml` hoặc `Dockerfile` cho phần chạy; `docker-compose.yml` cho Neo4j |
| NF-C6 | Seed ngẫu nhiên cho tập train/dev | Chia tập theo **bài** với seed cố định, lưu lại danh sách tập dưới dạng file để tái lập |
| NF-C7 | Notebook Kaggle có seed và xuất checkpoint | Notebook đặt seed, lưu cả checkpoint tốt nhất và checkpoint cuối |
| NF-C8 | Tài liệu lệnh chạy | Mỗi script có `--help` rõ ràng; README ghi lệnh chính xác đã chạy thật |

---

## 5. Bảo mật

| ID | Yêu cầu | Tiêu chí |
|---|---|---|
| NF-S1 | Cypher **chỉ đọc** | Validator tĩnh chặn từ khóa ghi; test ≥ 20 payload độc hại → 100% bị chặn; tài khoản Neo4j chỉ có quyền `READ` |
| NF-S2 | Timeout và giới hạn kết quả | Timeout 10s, `LIMIT` bắt buộc ≤ 100 dòng, giới hạn số query đồng thời |
| NF-S3 | API key nằm trong biến môi trường | Không có key nào trong code/commit; có `.env.example`; `.gitignore` chứa `.env` |
| NF-S4 | Không lộ chi tiết nội bộ trong lỗi trả về client | Lỗi nội bộ log ở server, client chỉ thấy thông báo thân thiện + mã lỗi |
| NF-S5 | Xác thực tài khoản admin (nếu có I2) | Tài khoản demo có mật khẩu mặc định đổi được qua biến môi trường |
| NF-S6 | CORS và binding | API bind `127.0.0.1` mặc định; CORS chỉ cho phép origin của frontend |
| NF-S7 | Không ghi log dữ liệu nhạy cảm vào repo | File log nằm ngoài git hoặc được ignore |
| NF-S8 | Neo4j không public | Neo4j listen trên `localhost`, port không mở ra ngoài |

---

## 6. Tương thích phần cứng

| ID | Yêu cầu | Tiêu chí |
|---|---|---|
| NF-H1 | Phần chạy ứng dụng chạy được trên máy i3 + 24GB RAM | Cài từ `docker-compose.yml` + `pip install -r requirements.txt` → `http://localhost:8000` hoạt động |
| NF-H2 | Không cần GPU khi demo | Toàn bộ request path không dùng GPU; mô hình NER/RE chỉ dùng ở build-time |
| NF-H3 | Không cần LLM lớn cục bộ khi demo | Dùng Gemini/Groq API qua adapter; có fallback trả thông báo nếu hết quota |
| NF-H4 | RAM khi nạp KG | < 6GB khi nạp 5.000 node + 50.000 cạnh |
| NF-H5 | Dung lượng đĩa | Toàn bộ dự án (dump đã xử lý + artifacts + models) < 10GB; dump gốc giữ ngoài repo |

**Phân bổ tài nguyên**

| Việc | Chạy ở đâu |
|---|---|
| Tải + tiền xử lý dump, lọc bài | Máy cá nhân (streaming) hoặc Kaggle CPU |
| Fine-tune PhoBERT (NER, RE) | **Kaggle GPU** |
| Chạy LLM trích xuất / Text-to-Cypher hàng loạt | **Kaggle GPU** (model lượng tử hóa) hoặc API Gemini/Groq |
| Sinh embedding cho entity linking | **Kaggle GPU**, xuất vector ra file |
| Neo4j, backend, frontend, demo | **Máy i3 24GB** |

---

## 7. Khả năng bảo trì

| ID | Yêu cầu |
|---|---|
| NF-M1 | Cấu trúc thư mục rõ ràng theo module (xem [03-kien-truc-he-thong.md](03-kien-truc-he-thong.md)) |
| NF-M2 | Cấu hình tập trung trong `configs/*.yaml`, không hard-code |
| NF-M3 | Mọi script CLI có `--help` và `--config` |
| NF-M4 | Test tự động tối thiểu cho: chuẩn hóa ngày, chuẩn hóa tên, tách quan hệ đối xứng, validator Cypher, tính F1 |
| NF-M5 | Logging thống nhất (kèm `module` + `run_id`), ghi ra `logs/` |
| NF-M6 | `run_id` gắn vào mọi artifact để truy vết một lần chạy cụ thể |
| NF-M7 | Code có type hint và docstring cho hàm public |
| NF-M8 | Không commit file lớn (> 50MB) lên git; dùng `.gitignore` cho `data/`, `models/`, `logs/` |

---

## 8. Giấy phép và pháp lý

| ID | Yêu cầu | Tiêu chí |
|---|---|---|
| NF-L1 | Wikipedia: CC BY-SA 4.0 | Mọi node/edge có `wiki_url` trỏ về bài gốc; báo cáo có đoạn ghi nguồn |
| NF-L2 | Wikidata: CC0 | Dùng làm nhãn distant supervision và nguồn QID; ghi nguồn trong báo cáo |
| NF-L3 | Ghi nguồn ở UI | Mọi thẻ thông tin và panel bằng chứng có link về bài Wikipedia gốc |
| NF-L4 | Giữ giấy phép mô hình | Báo cáo nêu tên + nguồn + giấy phép của PhoBERT, BGE-M3, Gemini, Groq |
| NF-L5 | Dữ liệu tự tạo | Ghi rõ phương pháp gán nhãn, số người gán, kappa trong báo cáo |
| NF-L6 | Không dùng dữ liệu scan/Hán Nôm | Tuân thủ phạm vi 3.2 |

---

## 9. Trải nghiệm người dùng (UX)

| ID | Yêu cầu | Tiêu chí |
|---|---|---|
| NF-UX1 | Giao diện tiếng Việt | Toàn bộ nhãn/placeholder/thông báo lỗi bằng tiếng Việt |
| NF-UX2 | Thông báo lỗi rõ ràng cho người dùng | Không hiện stack trace; hiện thông điệp + gợi ý hành động |
| NF-UX3 | Phân biệt 3 trạng thái kết quả | `found` / `không có trong dữ liệu` / `lỗi` — khác màu và khác thông điệp |
| NF-UX4 | Tải trạng thái rõ ràng | Hiện spinner + "Đang tìm trong dữ liệu lịch sử…" khi đang xử lý |
| NF-UX5 | Câu hỏi gợi ý | Có ≥ 6 câu hỏi mẫu trên trang chủ (H10) |
| NF-UX6 | Truy cập cơ bản | Điều hướng bằng bàn phím, tương phản đủ, nhãn cho mọi nút icon |

---

## 10. Checklist nghiệm thu phi chức năng

- [ ] Truy vấn Cypher p95 < 2s trên dữ liệu thật
- [ ] End-to-end p50 < 10s trên máy i3
- [ ] NER F1 ≥ 0.85 (hoặc báo cáo minh bạch số thực tế)
- [ ] RE F1 ≥ 0.70
- [ ] Entity linking accuracy ≥ 0.85
- [ ] Text-to-Cypher execution accuracy ≥ 0.70
- [ ] 100% cạnh có bằng chứng
- [ ] 100% payload độc hại bị chặn
- [ ] Pipeline chạy lại từ đầu cho kết quả giống hệt
- [ ] Không có secret nào trong repo
- [ ] Mọi entity có `wiki_url`
- [ ] Docker Compose khởi động Neo4j + backend + frontend từ máy sạch

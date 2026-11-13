# ANNOTATION-GUIDELINES.md — Hướng dẫn gán nhãn NER & RE

> Dùng cho Phase 13 (đánh giá). Mục tiêu: 100 câu NER (+ tối đa 250 câu RE nếu còn thời gian).
> Mọi nhãn phải **độc lập với mô hình** — không mở xem kết quả dự đoán của PhoBERT khi gán.

## 0. Nguyên tắc chung

1. Gán theo **nghĩa trong ngữ cảnh câu**, không theo kiến thức ngoài đời.
2. Khi phân vân giữa 2 nhãn → chọn nhãn **hẹp hơn** (ví dụ `TIME` thay vì `EVENT`).
3. Khi không chắc → **không gán** (bỏ qua span đó), đừng đoán.
4. Một span chỉ có **một** nhãn. Span chồng lấn → giữ span lớn hơn nếu nhãn tương thích.
5. Ghi chú mơ hồ vào cột "ghi chú" thay vì ép nhãn.

## 1. Sáu nhãn NER

| Nhãn | Gán khi nào | Ví dụ đúng | Ví dụ sai (không gán) |
|---|---|---|---|
| `PERSON` | Tên cá nhân (vua, tướng, tác giả, nữ hoàng…) | "Lê Lợi", "Trần Hưng Đạo" | "nhà Lê" (→`DYNASTY`), "vua" (danh xưng, → annotate nếu là đại từ: xem §3) |
| `DYNASTY` | Gia tộc cùng dòng vua chúa, hoặc kỷ nguyên lịch sử | "nhà Trần", "thời đại Ngô" | "triều đại Lê" nếu nói về 1 nhà cụ thể → vẫn `DYNASTY` |
| `EVENT` | Sự kiện có mốc thời gian cụ thể (trận đánh, hội nghị, khởi nghĩa) | "Trận Bạch Đằng (1284)", "khởi nghĩa Lam Sơn" | "thời đại Lý" (→`DYNASTY`), "thế kỷ XV" (→`TIME`) |
| `LOCATION` | Địa danh (thành, sông, núi, tỉnh, đất nước) | "Hoa Lư", "sông Hồng", "Thanh Hóa" | "phía Bắc" (không phải tên địa danh) |
| `TIME` | Mốc thời gian: năm, thế kỷ, khoảng thời gian | "năm 938", "thế kỷ XV", "năm Canh Thân 1380" | "mùa xuân" (không có năm cụ thể → bỏ qua) |
| `TITLE` | Miếu hiệu, thụy hiệu, niên hiệu, chức vụ, tước vị | "Lê Thái Tổ", "Bình Định Vương", "Tể tướng quân" | "vua" khi chỉ danh xưng chung (xem §3) |

### 1.1. Quy tắc đặc biệt

- **Tên có bối cảnh trong ngoặc**: `Lê Lợi (1385–1433)` → gán `Lê Lợi` là `PERSON`; phần trong ngoặc `1385–1433` là `TIME` (nếu tách được).
- **Tên kèm chức vụ**: `vua Lê Thái Tổ` → gán **cả** `vua` (`TITLE`) và `Lê Thái Tổ` (`TITLE`)? → **Không**: gán `Lê Thái Tổ` là `TITLE` (miếu hiệu); `vua` bỏ qua vì là danh xưng chung.
- **Link nội bộ không đồng nghĩa với entity cụ thể**: `[[thành phố]]`, `[[quận]]` → **không gán**.
- **Danh từ chỉ loại**: "nhà", "triều đại", "trận đánh" đứng riêng → không gán (trừ khi là tên riêng đầy đủ như "nhà Trần").
- **Số năm trong câu không có "năm"**: "Lê Lợi (1385–1433)" → `1385` và `1433` là `TIME`.
- **Năm âm lịch**: "năm Canh Thân 1380" → gán **toàn bộ** "năm Canh Thân 1380" là `TIME`.
- **Quân số, số liệu**: "3 vạn quân" → không gán.

## 2. Quy tắc span

- Span phải là **chuỗi liên tục** trong text, khớp chính xác (kể cả dấu cách).
- Bao gồm cả dấu tiếng Việt trong span (ví dụ `Lê Thái Tổ` giữ nguyên dấu).
- Không cắt giữa từ ("Lê Thái Tổ" không tách thành "Lê Thái" + "Tổ").
- Số ký tự: dùng **chỉ số ký tự** (0-based), `end` là vị trí sau ký tự cuối → `text[start:end]` = span.

## 3. Gán đại từ và danh xưng (quan trọng cho Module C)

Câu hỏi: có nên gán "ông", "vua", "thái tử"?

| Trường hợp | Hành động |
|---|---|
| "ông ấy" mà đoạn có đúng 1 nhân vật nam vừa được nhắc | Gán `ông ấy` là `PERSON` |
| "ông" mà đoạn có ≥ 2 nhân vật nam | **Bỏ qua** (mơ hồ) |
| "vua" khi nói rõ đang nói về ai đó trong câu | Gán `vua` là `PERSON` |
| "thái tử", "tể tướng" như danh xưng chung | Gán là `TITLE` |
| "vua" đứng riêng như danh xưng chung, không rõ ai | **Bỏ qua** |

## 4. Quy tắc quan hệ (RE)

18 quan hệ — chọn **đúng một** cho mỗi cặp (subject, object):

| Quan hệ | Chọn khi | Dấu hiệu trong câu | Ví dụ |
|---|---|---|---|
| `cha_cua` | subject là **con** của object | "con của", "cha là" | "Lê Lợi là con của Lê Khánh Dư" |
| `me_cua` | subject là con của object (mẹ) | "mẹ", "con của" | "Lê Lợi là con của bà Lê Thị Ngọc" |
| `vo_cua` | subject là chồng của object | "vợ của", "hoàng hậu" | "Lê Lợi có vợ là Lê Thị Ngọc" |
| `chong_cua` | subject là vợ của object | "chồng của" | "Lê Thị Ngọc là chồng... của Lê Lợi" → sửa: "Lê Thị Ngọc là vợ của Lê Lợi" |
| `anh_em_cua` | hai người là anh em | "anh", "em", "anh em" | "Lê Nghiễn là anh của Lê Lợi" |
| `thuoc_trieu_dai` | subject thuộc về triều đại | "thuộc", "nhà X", "vua nhà X" | "Lê Lợi là vua nhà Lê" |
| `ke_vi` | subject là người trước, object là người kế nhiệm | "kế vị", "sau đó", "kế tiếp" | "Lê Lợi được Lê Thái Tông kế vị" → hướng: Lê Lợi → Lê Thái Tông |
| `giu_chuc_vu` | subject giữ chức vụ | "là tể tướng", "đảm nhiệm chức" | "Lê Lợi từng là tể tướng quân" |
| `lap_ra` | subject lập ra dynasty/event | "lập ra", "sáng lập", "thành lập" | "Ngô Quyền lập ra nhà Ngô" |
| `chi_huy_tran` | subject chỉ huy trận | "chỉ huy", "điều quân" | "Trần Hưng Đạo chỉ huy trận Bạch Đằng" |
| `tham_gia_tran` | subject tham gia trận (không phải chỉ huy) | "tham gia", "cùng tham chiến" | "Trần Hưng Đạo tham gia trận Bạch Đằng" |
| `danh_bai` | subject đánh bại object | "đánh bại", "thắng trận" | "Lê Lợi đánh bại quân Minh" |
| `dien_ra_tai` | sự kiện diễn ra tại địa danh | "diễn ra tại", "ở ...", "tại ..." | "Trận Bạch Đằng diễn ra tại sông Hồng" |
| `sinh_tai` | subject sinh tại địa danh | "sinh ở", "nguồn gốc tại" | "Lê Lợi sinh ở Thanh Hóa" |
| `mat_tai` | subject mất tại địa danh | "mất ở", "qua đời tại" | "Lê Lợi mất ở Đông Quan" |
| `sinh_nam` | subject sinh năm | "sinh năm", "sinh ngày ... năm" | "Lê Lợi sinh năm 1385" |
| `mat_nam` | subject mất năm | "mất năm", "qua đời năm" | "Lê Lợi mất năm 1433" |
| `dong_doi_tai` | dynasty đóng đô tại địa danh | "đóng đô", "kinh đô" | "Nhà Lê đóng đô tại Thăng Long" |

### 4.1. Hướng quan hệ (bắt buộc)

- `cha_cua`, `me_cua`: **con → cha/mẹ** (ngược với chiều đọc tự nhiên).
- `vo_cua`: **chồng → vợ**; `chong_cua`: **vợ → chồng**.
- `ke_vi`: **trước → sau**.
- `danh_bai`: **thắng → thua**.
- `sinh_nam`, `mat_nam`: **person → year**.
- `dien_ra_tai`: **event → place**.

### 4.2. Nhãn `NA`

- Gán `NA` khi hai entity cùng xuất hiện trong câu nhưng **không có quan hệ nào** trong danh sách.
- Ví dụ: "Lê Lợi và Nguyễn Trung Trực là hai nhân vật nổi tiếng." → cặp (Lê Lợi, Nguyễn Trung Trực) = `NA`.

### 4.3. Cặp ứng viên

Chỉ gán cho cặp có **cả hai entity xuất hiện trong cùng câu**. Giới hạn cách nhau ≤ 60 token.

## 5. Làm việc với Label Studio

### 5.1. Cấu hình task NER

- Interface: **Labels** (không phải bounding box).
- Labels: `PERSON`, `DYNASTY`, `EVENT`, `LOCATION`, `TIME`, `TITLE`.
- Import: file JSONL `{"text": ..., "labels": [{"start", "end", "label"}]}` (Label Studio hỗ trợ `start`/`end` dạng char offset khi bật `LabelStudio` text config `"type": "labels"`).

### 5.2. Cấu hình task RE

- Interface: **Relations** — cần 2 project: 1 project gán span (`PERSON`/`DYNASTY`/`EVENT`/`LOCATION`/`TITLE`), 1 project gán quan hệ giữa các span.
- Nhãn quan hệ: 18 tên + `NA`.
- Xuất JSONL: `{"sentence": ..., "pairs": [{"s": [start,end], "o": [start,end], "rel": "..."}]}`.

### 5.3. Quy trình 2 người (nếu có)

1. Cùng gán 20 câu calibration → thảo luận đến khi thống nhất (đây là bộ mẫu chuẩn).
2. Gán độc lập phần còn lại.
3. Tính agreement rate trên ≥ 30 câu chung; nếu đủ dữ liệu → Cohen's kappa.
4. Với câu lệch > 2 span → gặp nhau chốt.

## 6. Mẫu chuẩn (bộ mẫu đã chốt — dùng làm chuẩn xử lý khi phân vân)

| Văn bản | Nhãn đúng |
|---|---|
| "Lê Lợi (1385–1433) là vua nhà Lê, người lập ra nhà Lê." | `Lê Lợi`=PERSON, `1385`=TIME, `1433`=TIME, `nhà Lê`=DYNASTY |
| "Trận Bạch Đằng (1284) là trận đánh lớn giữa nhà Trần và nhà Nguyên." | `Trận Bạch Đằng`=EVENT, `1284`=TIME, `nhà Trần`=DYNASTY, `nhà Nguyễn`=DYNASTY |
| "Ông ấy là con của Lê Khánh Dư." | `ông ấy`=PERSON (nếu đoạn chỉ có 1 nhân vật nam), `Lê Khánh Dư`=PERSON |
| "Thế kỷ XV chứng kiến nhiều cuộc khởi nghĩa." | `thế kỷ XV`=TIME; `cuộc khởi nghĩa` → **bỏ qua** (không có tên riêng) |
| "Hoa Lư là kinh đô của nhà Đinh." | `Hoa Lư`=LOCATION, `nhà Đinh`=DYNASTY |
| "Lê Thái Tổ (tức Lê Lợi) mất năm 1433." | `Lê Thái Tổ`=TITLE, `Lê Lợi`=PERSON, `1433`=TIME |
| "Quân đội gồm 3 vạn người do Nguyễn Chích chỉ huy." | `Nguyễn Chích`=PERSON; `3 vạn` → bỏ qua |

## 7. Câu hỏi thường gặp

| Câu hỏi | Trả lời |
|---|---|
| "nhà" đứng riêng có gán không? | Không |
| "triều đại Ngô" gán nhãn gì? | `DYNASTY` |
| "Trận Tốt Động – Chúc Động" gán nhãn gì? | `EVENT` (toàn bộ tên, gồm dấu gạch nối) |
| "vua Lê Thái Tổ" — gán 2 span hay 1? | 1 span: `Lê Thái Tổ` = `TITLE`. Bỏ `vua`. |
| Năm trong ngoặc của tên riêng? | `TIME` |
| Danh từ chỉ loại ("nhà", "triều đại", "trận")? | Không gán |
| Người nổi tiếng không rõ là ai? | Bỏ qua span |

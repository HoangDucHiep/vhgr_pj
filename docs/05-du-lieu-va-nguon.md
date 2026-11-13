# 05 — Dữ liệu và nguồn

## 1. Bảng tổng hợp nguồn dữ liệu

| # | Nguồn | Vai trò | Cách tiếp cận | Giấy phép | Ghi chú cần xác nhận |
|---|---|---|---|---|---|
| 1 | **Wikipedia tiếng Việt dump** | Văn bản gốc | `dumps.wikimedia.org/viwiki/latest/viwiki-latest-pages-articles.xml.bz2` | CC BY-SA 4.0 | ✅ Đã kiểm tra: server trả HTTP 200 (2026-11-08) |
| 2 | **Wikidata** | Nhãn quan hệ (distant supervision), QID, tọa độ | SPARQL endpoint `query.wikidata.org` | CC0 | Cần kiểm tra quota khi chạy batch lớn |
| 3 | **Wikidata aliases** | Từ điển alias (miếu hiệu, thụy hiệu, niên hiệu) | SPARQL (`skos:altLabel`, `P742`, `P1449`) | CC0 | |
| 4 | **Hyperlink nội bộ Wikipedia** | Nhãn bạc NER + Entity linking | Trích từ wikitext trong dump | CC BY-SA 4.0 | Không cần nguồn ngoài |
| 5 | **Bộ gold tự gán** | Đánh giá NER/RE/linking | Label Studio (nội bộ) | — | 2 người gán + Cohen's kappa |
| 6 | **Bộ câu hỏi Text-to-Cypher** | Đánh giá G | Tự viết (nội bộ) | — | 60–100 cặp (câu hỏi, Cypher chuẩn) |
| 7 | **Tọa độ địa danh** (tuỳ chọn) | Bản đồ H8 | Wikidata `P625` | CC0 | Chỉ cần cho `Place` |
| 8 | **VLSP 2016/2018** (nếu được) | Pretrain / so sánh NER | Yêu cầu qua email BTL | Điều khoản riêng | **Không chắc có** → coi là tuỳ chọn |
| 9 | **PhoNER_COVID19** | So sánh NER y tế | HuggingFace | Theo repo gốc | Ngoài miền, chỉ để tham chiếu |

> **Lưu ý về bản `wikimedia/wikipedia` trên HuggingFace**: bản `20231101.vi` chỉ có khoảng 49.000 bài (Wikipedia tiếng Việt có ~1,1 triệu bài). Bản này **không đủ lớn** cho phạm vi 2.000–5.000 bài lịch sử chất lượng? Thực tế có đủ, nhưng **dump chính thức là nguồn đáng tin hơn** vì:
> - có đầy đủ category và infobox (dump HF có wikitext nên vẫn OK),
> - có `page_props`/`wikibase_item` để ánh xạ QID chính xác,
> - dump HF đã bị lọc bỏ redirect và không có trường phân loại đầy đủ.
>
> **Khuyến nghị:** dùng **dump chính thức** làm nguồn chuẩn; bản HuggingFace chỉ dùng làm dự phòng nếu tải dump quá nặng.

---

## 2. Wikipedia dump

### 2.1 Địa chỉ tải

```
https://dumps.wikimedia.org/viwiki/latest/
```

| File | Dung lượng (ước lượng) | Chứa gì | Dùng khi |
|---|---|---|---|
| `viwiki-latest-pages-articles.xml.bz2` | ~1,5–2 GB (nén) | Toàn bộ bài, không redirect | **mặc định** |
| `viwiki-latest-pages-articles-multistream.xml.bz2` | tương tự | Bố cục multistream (đọc song song tốt hơn) | khi cần tốc độ đọc |
| `viwiki-latest-pages-meta-current.xml.bz2` | nhỏ hơn nhiều | Metadata: category, page_props (Wikidata QID) | **bắt buộc kèm** |
| `viwiki-latest-redirects.xml.bz2` | rất nhỏ | Redirect (đổi tên bài) | dùng để resolve alias |
| `viwiki-latest-all-titles-in-ns0.gz` | rất nhỏ | Danh sách tiêu đề | kiểm tra nhanh |

### 2.2 Yêu cầu về bản dump

- Ghi lại **ngày dump** (ví dụ `20251101`) vào `configs/default.yaml` → `dump_version`.
- Bản dump là điểm mốc dữ liệu; khi báo cáo, luôn nêu phiên bản.

### 2.3 Quy trình tải

```bash
# Kiểm tra phiên bản hiện tại trước
curl -sI https://dumps.wikimedia.org/viwiki/latest/viwiki-latest-pages-articles.xml.bz2

# Tải vào data/raw/
wget -c -P data/raw/ \
  https://dumps.wikimedia.org/viwiki/latest/viwiki-latest-pages-articles.xml.bz2 \
  https://dumps.wikimedia.org/viwiki/latest/viwiki-latest-pages-meta-current.xml.bz2 \
  https://dumps.wikimedia.org/viwiki/latest/viwiki-latest-redirects.xml.bz2
```

Dùng `-c` (tiếp tục) để tải lại sau khi gián đoạn. Kiểm tra checksum `.md5` nếu có.

### 2.4 Lọc bài thuộc phạm vi lịch sử

**Tín hiệu 1 — Category.** Danh sách category Wikipedia tiếng Việt cần dùng (không phải cây phẳng, phải bao gồm cả subcategory):

Nhóm — Category:
- Triều đại: `Thời đại Ngô`, `Thời đại Đinh`, `Thời đại Lý`, `Thời đại Trần`, `Thời đại Hồ`, `Thời đại Lê`, `Thời đại Tây Sơn`, `Thời đại Nguyễn`
- Nhân vật: `Vua`, `Hoàng hậu`, `Đại công thần`, `Nhân vật thời ...`, `Dòng họ ...`
- Trận đánh: `Trận đánh`, `Trận đánh thời ...`
- Sự kiện: `Sự kiện thời ...`
- Địa danh: `Địa danh Việt Nam`, `Thành phố`, `Tỉnh`, `Sông`, `Núi`, `Chợ`, `Cung điện`
- Bài: `Bài viết quan trọng`, `Bài viết dẫn nhập`

Cần **tải danh sách category đầy đủ** (kể cả subcategory) từ `viwiki-latest-pages-meta-current.xml.bz2` — không nên hard-code tên category như trên vì Wikipedia tiếng Việt đổi tên category theo thời gian. Phương án: hard-code danh sách "seed category" làm điểm khởi đầu, sau đó **mở rộng theo đồ thị category** (subcategory đệ quy, giới hạn độ sâu 3).

**Tín hiệu 2 — Infobox.** Giữ bài nếu `loại_infobox` ∈ {`person`, `triều đại`, `trận đánh`, `sự kiện`, `địa danh`, `chức vụ`, `tông tộc`} hoặc có ít nhất 2 trong các trường `sinh`, `mất`, `triều đại`, `thời gian`, `thủ đô`, `người đứng đầu`.

**Tín hiệu 3 — Seed list + mở rộng đồ thị.** Danh sách bài hạt giống (~150 bài):
- 9 bài triều đại: `Nhà Ngô`, `Nhà Đinh`, `Nhà Tiền Lê`, `Nhà Lý`, `Nhà Trần`, `Nhà Hồ`, `Nhà Lê`, `Nhà Tây Sơn`, `Nhà Nguyễn`
- ~40 bài vua chính mỗi triều đại
- ~30 trận đánh tiêu biểu: `Trận Bạch Đằng (1284)`, `Trận Vân Đồn`, `Trận Chi Lăng – Xương Giang`, `Trận Ngọc Hồi – Đống Đa`, `Trận Tốt Động – Chúc Động`, `Trận Rạch Gầm – Xoài Cầu`, `Trận Việt Trì`, `Trận Điện Biên Phủ` (không thuộc 9 triều đại → để ngoài phạm vi), …
- ~20 địa danh: `Hoa Lư`, `Thăng Long`, `Hà Nội`, `Đông Quan`, `Thanh Hóa`, `Tây Đô`, …
- ~20 nhân vật nổi bật: `Lê Lợi`, `Trần Hưng Đạo`, `Lý Thái Tổ`, `Ngô Quyền`, `Đinh Bộ Lĩnh`, `Cát Bà`, `Hồ Quý Ly`, `Nguyễn Trung Trực`, `Trịnh Tráng`, `Gia Long`, …

Mở rộng BFS theo hyperlink nội bộ: từ seed → các bài trong category tương ứng → từ đó tới nhân vật/trận/địa danh được nhắc. Giới hạn: **chiều sâu ≤ 2 hop từ seed**, và tổng số bài 2.000–5.000.

**Tín hiệu 4 — Loại trừ.** Bỏ các bài: `Thể loại:`, `Danh sách`, `Danh sách nhân vật`, `Bảng`, `Dự án Wikimedia`, `Wikipedia:`, `Chủ đề:`, `Bài viết tùy biến`, `Tin tức`.

### 2.5 Metadata cần lưu mỗi bài

| Trường | Nguồn | Bắt buộc |
|---|---|---|
| `page_id` | dump XML `<id>` | ✅ |
| `title` | dump | ✅ |
| `url` | dựng từ title | ✅ |
| `revision_id` | dump | ✅ |
| `categories` | dump | ✅ |
| `wikibase_item` | `pages-meta-current` (page_props) | ✅ |
| `infobox_type` | parse wikitext | ✅ |
| `keep_reason` | `category` / `infobox` / `seed_expansion` / `manual` | ✅ |
| `dump_version` | cấu hình | ✅ |
| `last_edit_ts` | dump | ⬜ |

---

## 3. Wikidata

### 3.1 Truy vấn SPARQL

Endpoint: `https://query.wikidata.org/sparql`
User-Agent bắt buộc: `vhgr-npl-project/1.0 (contact: <email>)`

**Ví dụ lấy quan hệ gia đình + triều đại + năm sinh/mất:**

```sparql
SELECT ?person ?personLabel ?qid ?father ?fatherLabel ?mother ?motherLabel
       ?spouse ?spouseLabel ?birthYear ?deathYear
WHERE {
  ?person wdt:P31 wd:Q5 .                       # con người
  ?person wdt:P27 wd:Q881 .                     # quốc tịch Việt Nam
  ?person wdt:P569 ?birth .                     # có năm sinh
  FILTER(YEAR(?birth) < 1950)                   # giới hạn nhân vật lịch sử
  OPTIONAL { ?person wdt:P22 ?father }
  OPTIONAL { ?person wdt:P25 ?mother }
  OPTIONAL { ?person wdt:P26 ?spouse }
  OPTIONAL { ?person wdt:P570 ?deathDate . BIND(YEAR(?deathDate) AS ?deathYear) }
  BIND(YEAR(?birth) AS ?birthYear)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "vi,en". }
}
```

> **Lưu ý (đã kiểm chứng 11/2026):** `P463` (thành viên) và `P361` (thuộc) **không** dùng được để suy ra quan hệ
> `thuoc_trieu_dai` — trả **0** kết quả cho người thuộc triều đại. Thay bằng `P31=Q5` + `P27=Q881` + `P569`
> (sinh < 1950) rồi nối `P22` (cha) / `P25` (mẹ) / `P26` (vợ). Query này trả **213 người có `P22`**,
> bao phủ đủ cả 9 triều đại.

**Bộ lọc phạm vi**: mô hình "Việt Nam" thực sự là `Q881` (country) — cần kiểm chứng bằng query đếm theo năm để tránh chọn sai QID.

**QID 9 triều đại đã verify** (đối chiếu `Special:EntityData`, xem `docs/CONTEXT.md` §2.6 — đây là bộ QID chuẩn duy nhất của dự án):

| Triều đại | QID |
|---|---|
| Nhà Ngô | `Q703919` |
| Nhà Đinh | `Q1372154` |
| Nhà Tiền Lê | `Q1317884` |
| nhà Lý | `Q878309` |
| nhà Trần | `Q3111454` |
| Nhà Hồ | `Q1209047` |
| nhà Lê sơ | `Q878276` |
| Nhà Tây Sơn | `Q1034173` |
| nhà Nguyễn | `Q6500483` |

Tất cả 9 đều có `P31 = Q164950`. **Không lọc bằng `P17 = Q881`** (chỉ 3/9 triều đại có) và **không dùng `P463`/`P361`** (trả 0 kết quả cho người thuộc triều đại). Chiến lược SPARQL đã kiểm chứng: `?person wdt:P31 wd:Q5 ; wdt:P27 wd:Q881 ; wdt:P569 ?birth` + `FILTER(YEAR(?birth) < 1950)`, bổ sung `P22` (cha) / `P25` / `P26` → trả 213 người có quan hệ cha, đúng cả 9 triều đại.

**Lấy alias:**
```sparql
SELECT ?item ?itemLabel ?alt WHERE {
  ?item wdt:P31 wd:Q5 .
  ?item skos:altLabel ?alt .
  FILTER(LANG(?alt) = "vi")
}
LIMIT 100000;
```

### 3.2 Chiến lược gọi SPARQL

| Vấn đề | Giải pháp |
|---|---|
| Endpoint public giới hạn 60s/timeout | Chia truy vấn theo từng triều đại / chunk 200 QID |
| Rate limit | Nghỉ 1–2s giữa các request; dùng User-Agent định danh |
| Timeout | Đặt `timeout` trong driver, retry |
| Dữ liệu lớn | Xuất kết quả ra JSONL ngay, không giữ trong RAM |

### 3.3 Ánh xạ QID ↔ bài Wikipedia tiếng Việt

Thứ tự ưu tiên:
1. `wikibase_item` trong `pages-meta-current` (đáng tin nhất, đúng bản dump).
2. SPARQL `schema:about` + `schema:isPartOf <https://vi.wikipedia.org/>`.
3. Bảng `redirects` để map tên bài cũ → bài mới.

### 3.4 Tọa độ

```sparql
SELECT ?place ?placeLabel ?coord WHERE {
  ?place wdt:P31/wdt:P279* wd:Q486972 .   # địa danh
  ?place wdt:P625 ?coord .
  ?place wdt:P17 wd:Q881 .
  SERVICE wikibase:label { bd:serviceParam wikibase:language "vi". }
}
```

Kết quả dạng `POINT(lon lat)` → parse thành `longitude`, `latitude`.

---

## 4. Bộ dữ liệu đánh giá (gold)

> **Chiến lược đã chốt (11/2026): ưu tiên auto-gold từ Wikidata, gán tay chỉ tối thiểu.**
> Lý do: tập gán tay đầy đủ (250 câu × 2 người + kappa) tốn ~1 tuần; trong khi **Wikidata là nguồn đáp án độc lập với mô hình** nên vẫn cho số liệu thật, và tập lớn hơn nhiều.
> Chi tiết phương pháp và định nghĩa chỉ số: [07-danh-gia-va-kiem-thu.md](07-danh-gia-va-kiem-thu.md).

### 4.0. Auto-gold (nguồn chính, không cần gán tay)

| Tập | Nguồn đáp án | Quy mô | Ghi chú |
|---|---|---|---|
| `auto_gold_ner.jsonl` | hyperlink có đích **có QID** + `P31` khớp nhãn | ≥ 200 câu | Bỏ mọi mention không có QID; nhãn độc lập với mô hình |
| `auto_gold_re.jsonl` | cặp quan hệ từ Wikidata (`P22`, `P25`, `P26`, `P569`…) | ≥ 500 cặp | Đáp án đến từ Wikidata, **không** từ KG của mình → không vòng tròn |
| `auto_gold_link.jsonl` | mention → QID | ≥ 300 mention | Đối chiếu theo QID, khách quan 100% |
| `qa_gold.jsonl` | sinh tự động từ facts Wikidata bằng khuôn câu hỏi | 200–400 câu | `expected_result` lấy từ Wikidata; có dạng 1 bước, đa bước, đếm, lọc, `no_data` |

**Cơ chế sinh câu hỏi QA tự động** (bảng ánh xạ fact → câu hỏi):

| Fact Wikidata | Khuôn câu hỏi sinh ra |
|---|---|
| `P22` (cha) | "Cha của {X} là ai?" |
| `P25` (mẹ) | "Mẹ của {X} là ai?" |
| `P569` (năm sinh) | "{X} sinh năm nào?" |
| `P570` (năm mất) | "{X} mất năm nào?" |
| `P19` (nơi sinh) | "{X} sinh ở đâu?" |
| `P20` (nơi mất) | "{X} mất ở đâu?" |
| `P26` (vợ/chồng) | "Vợ của {X} là ai?" / "Chồng của {X} là ai?" |
| `P3373` (anh em) | "Anh em của {X} là ai?" |
| `P463` (triều đại) | "{X} thuộc triều đại nào?" |
| `P1344`/`P710` | "{X} tham gia trận đánh nào?" |
| `P276` (địa điểm) | "Sự kiện {X} diễn ra ở đâu?" |
| nối 2 facts (`P26`→`P22`) | "Vợ của {X} là con của ai?" (đa bước) |
| ngoài phạm vi | "Ai là vua năm 1855?" → `expected_result = []` |

### 4.1. Gán tay tối thiểu (đối chiếu người–máy)

| Mục | Quy mô | Ghi chú |
|---|---|---|
| Tập gán | 100 câu NER (tùy chọn) | Chọn câu có entity rõ nhất để giảm thời gian gán |
| Người gán | 1 người (2 người nếu được) | |
| Nhãn | 6 loại entity (B1) | |
| Định dạng | Label Studio → JSONL | xem bên dưới |
| Kiểm đồng thuận | ≥ 30 câu chung (nếu có 2 người) | Tính **agreement rate**; nếu đủ dữ liệu thì tính thêm Cohen's kappa |

```json
{"text": "...", "labels": [{"start": 12, "end": 18, "label": "PERSON"}]}
```

> Nếu chỉ có 1 người gán: báo cáo **agreement rate giữa người và auto-gold**, nêu rõ đây là đối chiếu người–máy chứ không phải inter-annotator agreement.

### 4.2 RE gold (tùy chọn — nếu còn thời gian)

| Mục | Quy mô |
|---|---|
| Tập gán | 250 câu (có cả câu có quan hệ và câu `NA`) |
| Người gán | 2 người |
| Nhãn | 18 quan hệ + `NA` |
| Định dạng | JSONL: `{"sentence": ..., "pairs": [{"s": [...], "o": [...], "rel": "cha_cua"}]}` |

### 4.3 Entity linking gold (tùy chọn)

| Mục | Quy quyết |
|---|---|
| Tập gán | 150 mention |
| Nhãn | `entity_id` đúng (chấp nhận `NIL` khi không có) |
| Chọn mẫu | Cân bằng: 50% mention dễ (khớp chính tả), 50% khó (alias, trùng tên, viết tắt) |

### 4.4 Bộ câu hỏi Text-to-Cypher — bổ sung

Ngoài bộ sinh tự động ở mục 4.0, nhóm **viết tay thêm ~40–60 câu** để bao phủ các dạng mà khuôn sinh tự động không tạo được (so sánh, đếm điều kiện, lọc nhiều điều kiện, câu hỏi mơ hồ):

| Câu hỏi | Cypher chuẩn | Kết quả mong đợi |
|---|---|---|
| Lê Lợi sinh năm nào? | `MATCH (p:Person {entity_id:$id}) RETURN p.birth_year` | `[{p.birth_year: 1385}]` |
| Triều Trần có bao nhiêu vua? | `MATCH (p:Person)-[:thuoc_trieu_dai]->(d:Dynasty {name_normalized:'nha tran'}) RETURN count(p)` | `[{count: 15}]` |
| Vợ của vua Lê Thái Tổ là con của ai? | `MATCH (v:Person {entity_id:$id})-[:vo_cua]->(w:Person)-[:cha_cua]->(f:Person) RETURN w.name, f.name` | 1 dòng |
| Ai làm vua lâu hơn, Lê Thái Tổ hay Lê Thái Tông? | `MATCH (p:Person) WHERE p.name IN [...] RETURN p.name, p.reign_end-p.reign_start` | 2 dòng |
| Ai là vua năm 1855? | `MATCH (p:Person) WHERE p.reign_start <= 1855 AND (p.reign_end IS NULL OR p.reign_end >= 1855) RETURN p.name` | `[]` |

---

## 5. Chia tập dữ liệu

| Tập | Cách chia | Mục đích |
|---|---|---|
| `train` | 80% bài | Huấn luyện NER/RE |
| `dev` | 10% bài | Chọn checkpoint, early stopping |
| `test` | 10% bài | Đánh giá cuối (giữ kín, chỉ chạy 1 lần) |
| `gold` | câu được gán tay | Đánh giá tuyệt đối |

**Quy tắc:** chia theo **bài** (page_id), không theo câu, để tránh rò rỉ — câu trong cùng bài thường dùng lại cùng nhân vật/cấu trúc câu.
Lưu danh sách `page_id` của từng tập vào `data/splits/splits.json` để tái lập.

---

## 6. Kích thước dữ liệu dự kiến

| Artifact | Quy mô ước lượng |
|---|---|
| `documents.jsonl` (2.000–5.000 bài) | 300–800 MB (kể cả wikitext) |
| `documents.jsonl` (chỉ text + metadata) | 80–200 MB |
| `sentences` (~40–80 câu/bài) | 150.000–400.000 câu |
| `ner_predictions.jsonl` | 100–300 MB |
| `re_phobert.jsonl` | 50–150 MB |
| `entities.jsonl` | 5.000–30.000 entity |
| `graph.jsonl` | 50.000–200.000 cạnh |
| `entity_embeddings.npy` (BGE-M3, dim 1024, float16) | 30.000 × 1024 × 2B ≈ 61 MB |

**RAM khi xử lý**: dùng streaming + xử lý theo lô → < 4GB.

---

## 7. Giấy phép — bảng tổng hợp

| Nguồn | Giấy phép | Nghĩa vụ |
|---|---|---|
| Wikipedia tiếng Việt | CC BY-SA 4.0 | Ghi công + link bài gốc (đã làm ở `wiki_url`, `source_url`) |
| Wikidata | CC0 | Ghi nguồn trong báo cáo |
| PhoBERT (`vinai/phobert-base`) | Apache-2.0 (theo repo) | Trích dẫn trong báo cáo |
| BGE-M3 | MIT | Trích dẫn trong báo cáo |
| Gemini API | Theo điều khoản Google AI Studio | Không tái phân phối output hàng loạt nếu vi phạm điều khoản free tier |
| Groq API | Theo điều khoản Groq | Tương tự |
| Bộ gold tự tạo | Nội bộ | Ghi rõ phương pháp + kappa |

---

## 8. Kết quả xác minh nguồn (đã kiểm tra 10/11/2026)

### 8.1. QID chính xác — 9 triều đại

Đã tra trực tiếp bằng Wikidata API (`wbsearchentities` + `wbgetentities`). Tất cả đều có `P31 = Q164950` (triều đại):

| Triều đại | QID | `P31` | Ghi chú |
|---|---|---|---|
| Nhà Ngô | `Q703919` | Q164950, Q11514315, Q417175 | Q417175 = vương quốc |
| Nhà Đinh | `Q1372154` | Q164950 | |
| Nhà Tiền Lê | `Q1317884` | Q164950 | |
| nhà Lý | `Q878309` | Q164950, Q3024240 | `P17` = Q430309 (Đại Việt), Q10841085 (Đại Cồ Việt) |
| nhà Trần | `Q3111454` | Q164950, Q3024240 | ⚠️ **trùng tên** với nhà Trần Trung Quốc `Q62454` — phải chọn `Q3111454` |
| Nhà Hồ | `Q1209047` | Q164950 | `P17` = Q430309 |
| nhà Lê sơ | `Q878276` | Q164950, Q3024240 | ⚠️ "Nhà Lê" còn có `Q10800791` = nhà Lê trung hưng (1533–1789) — ngoài phạm vi |
| nhà Tây Sơn | `Q1034173` | Q164950, Q3024240 | `P17` = Q881 (Việt Nam) |
| nhà Nguyễn | `Q6500483` | Q164950, Q19953632, Q3024240 | |

### 8.2. QID lớp thực thể

| Lớp KG | QID | Nhãn Wikidata |
|---|---|---|
| `DYNASTY` | `Q164950` | triều đại |
| `EVENT` (trận đánh) | `Q178561` | trận đánh |
| `EVENT` (sự kiện) | `Q1656682` | sự kiện |
| `LOCATION` | `Q486972` | khu định cư |
| `PERSON` | `Q5` / `Q116` | người / quân chủ |
| `TITLE` — miếu hiệu | `Q706208` | miếu hiệu |
| `TITLE` — thụy hiệu | `Q696100` | thụy hiệu |
| `TITLE` — niên hiệu | `Q256408` (VN: `Q2420465`) | niên hiệu |
| `TITLE` — chức vụ | `Q4164871` | chức vụ |
| `TITLE` — tông tộc | `Q840178` | tông tộc |
| Quốc gia | `Q881` / `Q430309` / `Q10841085` | Việt Nam / Đại Việt / Đại Cồ Việt |
| Thời kỳ lịch sử | `Q11514315` | thời kỳ lịch sử |

### 8.3. Cảnh báo quan trọng cho SPARQL

`P17` (quốc gia) chỉ xuất hiện trên **3/9** triều đại (Lý, Hồ, Tây Sơn). **Không được lọc bằng `?x wdt:P17 wd:Q881`** vì sẽ mất 6 triều đại. Cách lọc đúng:
```
?dynasty wdt:P31 wd:Q164950 .          # bắt buộc
?person wdt:P463|wdt:P361 ?dynasty .   # hoặc heuristic theo nhãn
```

### 8.4. Mô hình LLM free tier (tính đến 11/2026)

| Model | Trạng thái free tier | RPM | RPD |
|---|---|---|---|
| `gemini-2.0-flash` | ❌ mất quota free, dự án mới không dùng được | 0 | 0 |
| `gemini-2.5-flash` / `-lite` | ❌ deprecated, key mới trả 404 | — | — |
| `gemini-3.5-flash-lite` | ✅ dùng được | 15 | 500 |
| `gemini-3.5-flash` | ✅ nhưng quá ít | 5 | 20 |
| `gemini-embedding-2` | ✅ | 100 | 1000 |
| Groq `openai/gpt-oss-20b` / `-120b` / `qwen/qwen3.8-27b` | ✅ | 30 | 1000 |
| Groq `llama-3.1-8b-instant`, `llama-3.3-70b-versatile` | ❌ đã retire 16/08/2026 | — | — |

**Hệ quả:** quota API free tổng ≈ 3.500 request/ngày, trong khi corpus có 150.000–400.000 câu → **không thể** chạy LLM trích xuất toàn corpus qua API. Phương án đã chốt: bulk trích xuất bằng **model mở lượng tử hóa trên Kaggle GPU**; API free tier chỉ dùng cho baseline tập con, Text-to-Cypher lúc demo và LLM-judge.

### 8.5. Hạ tầng

- **Kaggle Internet**: nút "Internet: On/Off" trong sidebar notebook (mặc định On). Tắt → chỉ dùng dataset/output đã mount, không `pip install` mới, không gọi API ngoài. Bắt buộc **On** khi tải checkpoint từ HuggingFace; nên **tắt** ở notebook inference để ổn định.
- **Neo4j**: image `neo4j:5-community` đã có sẵn trên máy. User `reader` dùng để tách credential cho API. **Lưu ý (kiểm chứng 11/2026): Community KHÔNG có RBAC** — `SET ROLE reader` lỗi cú pháp và user `reader` vẫn ghi được. Lớp bảo vệ thứ 2 phải dựa vào **session `READ_ACCESS`** (server từ chối ghi, kể cả superuser).
- **Label Studio**: `pip install label-studio` (hỗ trợ Python 3.10–3.12), chạy `label-studio start` ở `localhost:8080`, lưu SQLite mặc định, miễn phí. Có 2 task: Labels (NER) và Relations (RE).
- **Máy local**: RAM 23GB, còn 167GB đĩa, Python 3.12, Docker 29.9 → đủ cho Module A (streaming, < 4GB RAM) và toàn bộ tầng online.

### 8.6. Việc còn lại cần xác nhận

- [ ] Kích thước thực tế của `viwiki-latest-pages-articles.xml.bz2` tại thời điểm tải.
- [ ] Gemini key của bạn đã tạo được project với model nào còn quota (`gemini-3.5-flash-lite`?).
- [ ] Groq key còn model nào trong danh sách free.
- [ ] Có thể tạo 100 câu gán tay tối thiểu (không bắt buộc — xem chiến lược eval ở [07](07-danh-gia-va-kiem-thu.md)).

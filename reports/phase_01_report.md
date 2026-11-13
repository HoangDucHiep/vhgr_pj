# Phase 01 — Tải dump và lọc bài (A1)

- Ngày: 2026-11-13 (lượt chạy cuối: 14/11/2026 00:38)
- Trạng thái: ✅ đạt Gate

## Đã làm

1. **Tải dump** `viwiki-20261101`:
   - `data/raw/viwiki-20261101-pages-articles.xml.bz2` (~1,1 GB) — nguồn wikitext + categories + links.
   - `data/raw/viwiki-20261101-pages-meta-current.xml.bz2` (~1,4 GB) — nguồn `page_props/wikibase_item` và cây category.
   - `data/raw/manifest.json` — tên file, kích thước, sha1, ngày tải.
   - Ghi chú: viwiki **không** có `redirects.xml.bz2` riêng; redirect nằm trong `pages-articles` (thẻ `<redirect>`).

2. **Chỉ mục Wikidata** (`src/preprocess/wikidata_map.py`):
   - `data/interim/pageid_to_qid.json` (39,6 MB) và `data/interim/title_to_qid.json` (46,9 MB).
   - Bổ sung `PREFIXES` cho `p:`/`ps:`/`pq:`/`wikibase:` để SPARQL qualifier hoạt động trên QLever.

3. **Chỉ mục category** (`src/preprocess/category_index.py`):
   - Đọc `categorylinks` + `linktarget` từ `pages-meta-current`.
   - `data/interim/category_members.json` — 81 category, 1.682 categorylink, 1.285 trang duy nhất.
   - `data/interim/category_hierarchy.json` — 30 nhánh cây category (đệ quy độ sâu ≤ 3).
   - Đã sửa 2 lỗi: (a) trộn lẫn `page_id` với `lt_id` khi dựng ánh xạ cha–con → chuyển sang khóa theo **title**; (b) regex không nhận dòng SQL kết thúc bằng `;`.

4. **Bộ lọc 5 tầng** (`src/preprocess/filter_articles.py`), kiến trúc 3 lượt streaming:

   | Tầng | Nội dung | `keep_reason` |
   |---|---|---|
   | **T0** | Wikidata: seed lấy từ SPARQL (`P31=Q5`+`P27/P19/P39/P17=Q881`, `P31=Q178561` trận đánh, `P31=Q164950` triều đại), lọc theo `person_year_max=1900`, `history_year_max=1945` | `wikidata` |
   | **T1** | Category: 16 category seed đã verify + mở rộng đệ quy theo cây (81 category) | `category` |
   | **T2** | Infobox: loại trong whitelist + số trường lịch sử tối thiểu theo từng loại (`person: 3`, `place: 2`, `dynasty: 2`, `battle: 1`, `event: 1`) + mốc năm trong `[850, 1945]` + category trong phạm vi Việt Nam | `infobox` |
   | **T3** | BFS hyperlink từ biên seed, chiều sâu ≤ 2 (tìm thấy 512.288 tiêu đề, thêm 276 bài) | `seed_expansion` |
   | **T4** | Loại trừ: category/tiêu đề loại trừ (`Danh sách`, `Bảng`, `Wikipedia:`, `Dự án Wikimedia`…) | — |
   | **T5** | **Chốt phạm vi lịch sử Việt Nam** (thêm sau khi đo thấy ~35% nhiễu — xem "Sai lệch") | — |

5. **Artifact**:
   - `data/interim/documents.jsonl` — **2.441 bài**, mỗi dòng 1 JSON, có `wikitext` đầy đủ.
   - `data/interim/filter_stats.json` — thống kê theo `keep_reason`, `infobox_type`, tín hiệu Wikidata, top-50 category.

## Lệnh đã chạy

```bash
/usr/bin/time -v python -m src.preprocess.filter_articles --config configs/default.yaml
→ giữ 2.441 bài · wall clock 31:08 · Maximum resident set size 1.211.772 kB (≈ 1,16 GB) · exit 0

python -m src.preprocess.filter_articles --stats-only
→ in lại thống kê từ filter_stats.json

pytest -q tests/
→ 107 passed (gồm 7 test mới cho tầng T5 trong `tests/test_filter_scope.py`)

python - <<'PY'   # assert Gate
...
PY
→ PASS Gate (2.441 bài · QID 97,3% · đủ 4 loại infobox)
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số bài trong `documents.jsonl` | 2.000–5.000 | **2.441** ✅ |
| Tổng trang đã quét | — | 2.255.249 |
| Bài có `doc_id`/`title`/`url`/`keep_reason`/`dump_version`/`wikitext` | 100% | **100%** ✅ |
| `doc_id` khớp `page_id` | 100% | **100%** ✅ |
| Bài có `wikibase_item` (QID) | ≥ 80% | **97,3%** (2.375/2.441) ✅ |
| `infobox_type` có đủ `person`/`battle`/`dynasty`/`place` | đủ 4 | `person` 1.061 · `battle` 202 · `place` 150 · `dynasty` 16 · `event` 11 · `none` 1.001 ✅ |
| RAM peak | < 4 GB | **≈ 1,16 GB** ✅ |
| Checksum 2 lần chạy | giống hệt | **IDENTICAL** ✅ (`b04dd858…12de19`) |

### Phân bố `keep_reason`

| keep_reason | Số bài |
|---|---|
| `wikidata` (T0) | 930 |
| `category` (T1) | 933 |
| `infobox` (T2) | 302 |
| `seed_expansion` (T3) | 276 |

## Gate

- [x] `documents.jsonl` có 2.000–5.000 bài — **2.441**
- [x] Mọi bài có `doc_id`, `title`, `url`, `keep_reason`, `dump_version`, `wikitext` không rỗng — 100%
- [x] ≥ 80% bài có `wikibase_item` — **97,3%**
- [x] Phân bố `infobox_type` có đủ `person`, `battle`, `dynasty`, `place`
- [x] RAM peak < 4GB — **≈ 1,16 GB**
- [x] Chạy lại 2 lần cho checksum `documents.jsonl` giống hệt — **IDENTICAL**

### Checksum 2 lần chạy

```
run A (14/11 00:38): b04dd858b1494fb6f9365e7a69b980c6a4cb3bc15f365e01fedcb2980712de19
run B (14/11 01:15): b04dd858b1494fb6f9365e7a69b980c6a4cb3bc15f365e01fedcb2980712de19
→ IDENTICAL ✅
```

## Sai lệch so với kế hoạch

Ghi chi tiết trong `reports/deviations.md`:

- **D-008** — T2 cần thêm điều kiện "category trong phạm vi Việt Nam" (không chỉ dựa vào infobox + năm), vì các trận đánh toàn cầu (Verdun, Poltava, Boer) khớp infobox `battle` chung.
- **D-009** — `normalize_infobox_type` phải khớp **từ khoá đầy đủ** (`battle` ≠ `tranh`), không khớp tiền tố chuỗi.
- **D-010** — Cây category phải khóa theo **title** (MediaWiki `cl_from` là `page_id` của trang category, còn `cl_target_id` là `lt_id` trong bảng `linktarget`).
- **D-011** — Bộ lọc chạy 3 lượt streaming thay vì 1 lượt (đọc dump 3 lần) để giữ RAM dưới 4GB; tổng thời gian 31 phút.
- **D-012** — Thêm tầng **T5 "chốt phạm vi lịch sử Việt Nam"**: lượt chạy đầu giữ 3.113 bài nhưng **~35% rơi ra ngoài phạm vi** (Trận Stalingrad, Chiến tranh Afghanistan, Nhà Ptolemaios, Vương triều Palaiologos…) vì tín hiệu Wikidata `battle`/`dynasty` lấy được *mọi* trận đánh và triều đại có bài tiếng Việt. T5 siết theo tín hiệu → corpus còn **2.441 bài**, vẫn trong khoảng 2.000–5.000.

## Kiểm tra chất lượng (lấy mẫu ngẫu nhiên seed 99)

25 bài ngẫu nhiên trong corpus cuối: `Trận Bạch Đằng (938)`, `Đền Trần Thương`, `Cung Diên Thổ`, `Hiếu Trang Duệ Hoàng hậu`, `Nguyễn Hữu Tiến`, `Trương Đình Dụ`, `Phan Văn Trường`, `Dương Văn An`, `Lịch sử chiến tranh Trung Quốc – Việt Nam`, `Anh hùng dân tộc Việt Nam`… — tất cả đều thuộc phạm vi lịch sử Việt Nam.

## Việc tiếp theo

Phase 2 — làm sạch wikitext, tách câu/đoạn, trích hyperlink có offset ký tự chính xác.
Code đã sẵn sàng (`src/preprocess/clean_text.py`, `src/preprocess/split_sentences.py`, `tests/test_clean_text.py`, `tests/test_sentence_split.py`, `scripts/stats_text.py` — 18 test pass).

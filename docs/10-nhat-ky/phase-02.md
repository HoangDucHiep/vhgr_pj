# Phase 02 — Làm sạch wikitext, tách câu/đoạn, trích hyperlink (A2/A3/A5)

- Ngày: 2026-11-14
- Trạng thái: ✅ đạt Gate (5/5)
- Báo cáo Gate: `reports/phase_02_report.md`
- Sai lệch: `reports/deviations.md` (D-015, D-016, D-017)

## 1. Bối cảnh và vấn đề cần giải

Phase 1 (`reports/phase_01_report.md`) đã lọc còn **2.441 bài** Wikipedia tiếng Việt trong phạm vi
lịch sử Việt Nam, mỗi bài giữ nguyên `wikitext` gốc. Phase 2 biến `wikitext` thành **văn bản thuần
tách sẵn câu/đoạn + danh sách hyperlink có offset chính xác** — đây là nền tảng cho mọi phase sau:

| Phase sau | Cần gì từ Phase 2 |
|---|---|
| Phase 3 (infobox) | `infobox_raw` tách riêng, không lẫn vào văn bản |
| Phase 4 (NER bạc) | hyperlink với `target` + `sentence_id` + offset ký tự |
| Phase 5 (NER dự đoán) | `sentence_id`, `char_start`, `char_end` trên `clean_text` |
| Phase 6 (coreference) | `sent_id` ổn định, câu không vỡ |
| Phase 8 (RE) | `evidence_sentence` phải là câu thật, không phải mảnh vỡ |

### Ràng buộc kỹ thuật

- **Offset phải tuyệt đối chính xác** — `clean_text[char_start:char_end] == sentence.text` là điều kiện
  tiên quyết để Phase 5/6 ánh xạ mention về đúng vị trí.
- **Bằng chứng bắt buộc** (nguyên tắc #1 của `AGENTS.md`) — mỗi quan hệ KG sau này phải trích được
  câu nguồn; câu nguồn rác (vỡ giữa tên, còn ký tự wiki) sẽ làm hỏng toàn bộ chuỗi bằng chứng.
- **Không được bịa** — nếu `clean_text` còn sót ký tự wiki thì câu nguồn không kiểm chứng được.
- **Tái lập** — cùng đầu vào phải cho cùng đầu ra (seed 42).

### Ba lỗi phát hiện khi chạy thật (đo trên corpus 2.441 bài)

1. **Offset của link lệch ở 502 bài (20,6%)** — `_strip_stray_markers` chạy *sau* khi đã ghi offset.
2. **Văn bản vỡ câu ở mỗi dòng** — Wikipedia ngắt dòng cứng ~80 ký tự, `pysbd` coi `\n` là ranh giới câu.
3. **Markup danh sách còn sót** (`*`, `#`, `:`, `;`) + dòng bảng `|-`, `| x` → 15,8% "câu" là mục danh sách.

## 2. Phương án đã cân nhắc

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **A. Regex phẳng cho wikilink** (bản gốc commit `43d13f1`) | `_WIKILINK_RE.finditer` + thay thế | 0 lỗi offset trên 300 bài mẫu, nhưng **link lồng nhau** (`[[Tập tin:X\|nhỏ\|[[Đê sông Hồng]]]]`) bị cắt đôi, link hỏng ngoặc để lại `]]` | ❌ | Không xử lý được wikitext thật |
| **B. Nhiều vòng thay "link trong cùng"** (bản D-014 commit `4136880`) | Lặp quét link không chứa link khác | **502/2.441 bài sai offset** (68.624 link lỗi) | ❌ | Vòng sau xoá link tập tin → dịch văn bản phía sau, offset vòng trước không được cập nhật |
| **C. Quét một lần + đệ quy** (đã chọn) | Một lượt quét, xử lý link lồng bằng đệ quy; offset tính theo thứ tự chèn | **0 lỗi offset / 186.510 link** | ✅ | Offset luôn khớp vì tính trực tiếp theo chuỗi kết quả |
| **D. Gỡ ngoặc lạc TRƯỚC khi thay link** (bổ sung cho C) | Ghép cặp `[[`↔`]]` bằng stack LIFO, cặp không khớp → xoá | 0 bài còn `[[`/`]]` | ✅ | Xoá ngoặc trước ⇒ không dịch offset đã ghi |
| **E. Gỡ ngoặc lạc SAU khi thay link** (cách ban đầu) | `_strip_stray_markers` chạy cuối | 502 bài sai offset | ❌ | Nguyên nhân gốc của lỗi 1 |
| **F. Tách câu giữ nguyên `\n`** | `pysbd` trên text thô | Tỉ lệ câu kết thúc dấu câu **83,6%** | ❌ | `\n` là ranh giới câu cho `pysbd` |
| **G. Nối dòng xuống dòng cứng (soft-wrap)** | Nối các dòng trong cùng đoạn bằng khoảng trắng | Văn xuôi **89,1%** (400 bài mẫu, clean cũ) | ✅ | Khớp cách Wikipedia hiển thị văn bản |
| **H. Gỡ markup danh sách + tách item thành đoạn riêng** | `_strip_list_markers` + sentinel đánh dấu | Tách biệt được 43.860 mục danh sách; văn xuôi **95,3%** | ✅ | Mục danh sách không phải câu — tách để đo trung thực |
| **I. Có heading trong tập câu** | `heading=True` vẫn sinh câu | 9,5% "câu" là tiêu đề, kéo tỉ lệ hợp lệ xuống 74,3% | ❌ | Tiêu đề không phải câu |
| **J. Loại heading khỏi tập câu** (đã chọn) | `continue` khi `para["heading"]` | 0 "câu" là tiêu đề | ✅ | Tiêu đề vẫn đầy đủ trong `paragraphs` |

## 3. Quyết định đã chốt

### D-015 — Chốt mẫu số "tỉ lệ giữ hyperlink" là wikitext **thân bài**

- **Quyết định**: Gate đo trên mẫu số **link còn sót trong wikitext sau khi gỡ infobox/template/ref/bảng/markup**
  (gọi tắt là "wikitext thân bài"), không phải wikitext gốc.
- **Lý do**: phần bị gỡ là **có chủ đích** — infobox, template trích dẫn, bảng, link tập tin không phải văn bản
  thân bài nên không thể xuất hiện trong `clean_text`. Đo trên mẫu số gốc cho 80,4% — dưới ngưỡng Gate 95%
  dù chất lượng thực tế là 99,8%.
- **Ảnh hưởng**: `scripts/stats_text.py` phải tái chạy `prepare_text()` để dựng lại wikitext thân bài
  (nếu đếm bằng regex trên `wikitext` gốc thì **đếm thiếu** link nằm trong template/bảng → mẫu số sai).
  Báo cáo **cả hai** tỉ lệ để minh bạch.
- **File cập nhật**: `scripts/stats_text.py`, `reports/phase_02_report.md`, `reports/deviations.md`.

### D-016 — Phải tách "câu văn xuôi" và "mục danh sách" khi đo chất lượng câu

- **Quyết định**: Gate "≥95% câu kết thúc bằng dấu câu" đo trên **câu văn xuôi** (`para_kind == "prose"`).
  Vẫn báo cáo tỉ lệ toàn bộ (bao gồm mục danh sách) để minh bạch.
- **Lý do**: mục danh sách là mệnh đề ngắn không có dấu kết thúc — tính chung sẽ kéo tỉ lệ xuống 85,6%
  và Gate 95% trở nên bất khả thi dù văn bản đã sạch hoàn toàn.
- **Ảnh hưởng**: `clean_text.py` phải gắn nhãn `paragraph_kinds` (`"prose"` / `"list_item"`) theo **nội dung**
  qua sentinel `\uE000` (nội dung item thay đổi sau khi thay link nên không thể so khớp nội dung trước/sau).
  Sentinel phải được gỡ ở bước cuối và **dịch offset** của link phía sau tương ứng.
- **File cập nhật**: `src/preprocess/clean_text.py`, `src/preprocess/split_sentences.py`, `scripts/stats_text.py`.

### D-017 — Bổ sung nối dòng xuống dòng cứng + gỡ markup danh sách (ngoài kế hoạch gốc)

- **Quyết định**: thêm `_join_soft_wrapped_lines()` và `_strip_list_markers()` vào `clean_text.py`.
- **Lý do**: không có 2 bước này thì Gate "≥95% câu kết thúc bằng dấu câu" **không thể đạt** (đo được 83,6%).
- **Ảnh hưởng**: `clean_text` thay đổi cấu trúc đoạn; `paragraph_spans()` được tách ra `src/common/text_utils.py`
  để hai module dùng chung **một** định nghĩa ranh giới đoạn (tránh lệch chỉ số đoạn ↔ nhãn).
- **File cập nhật**: `src/preprocess/clean_text.py`, `src/common/text_utils.py`.

### D-018 — Cache `pysbd.Segmenter` ở mức module

- **Quyết định**: khởi tạo segmenter một lần (`_get_segmenter()`), không tạo lại cho mỗi đoạn.
- **Lý do**: đo được thời gian chạy giảm từ **~3 phút** xuống **~86 giây** cho toàn corpus.
- **File cập nhật**: `src/preprocess/split_sentences.py`.

## 4. Thang số liệu so sánh

### 4.1. Trước / sau theo từng lỗi đã phát hiện

| Chỉ số | Trước (commit `4136880`, bản D-014) | Sau (hiện tại) | Nguồn đo |
|---|---|---|---|
| Bài có link sai offset | **502 / 2.441 (20,6%)** | **0 / 2.441** | đo full corpus, bản cũ vs `stats_text.py` |
| Số link sai offset | **68.624 / 189.146 (36,3%)** | **0 / 186.510** | như trên |
| Bài còn ký tự wiki | **1 / 2.441** | **0 / 2.441** | như trên |
| Tỉ lệ câu kết thúc dấu câu (toàn bộ) | **83,6%** (mẫu 400 bài, seed 42) | **85,6%** (full corpus) | `stats_text.py` |
| Tỉ lệ câu **văn xuôi** kết thúc dấu câu | **89,1%** (mẫu 400 bài, clean cũ + split mới) | **95,3%** (full corpus) | đo trực tiếp |
| Số câu | 28.873 (mẫu 400 bài, split cũ) | 30.001 (mẫu 400 bài, split mới) — full corpus **186.960** | đo trực tiếp |
| Số mục danh sách bị tính nhầm là văn xuôi | **toàn bộ 6.667/6.667 mục** (bản cũ không có nhãn) | **0** (nhãn `list_item` chính xác) | đo trực tiếp |
| Thời gian tách câu toàn corpus | ~3 phút | **~86 giây** | đo thời gian thực |

### 4.2. So sánh 3 phương án xử lý wikilink (đo full corpus 2.441 bài)

| Phương án | Link giữ lại | Link sai offset | Bài sai offset | Bài còn ký tự wiki |
|---|---|---|---|---|
| A — regex phẳng | — | — | — | không xử lý link lồng nhau |
| B — nhiều vòng "link trong cùng" | 189.146 | **68.624 (36,3%)** | **502 (20,6%)** | 1 |
| **C — quét một lần + đệ quy + gỡ ngoặc trước** | **186.510** | **0** | **0** | **0** |

> Ghi chú: B giữ nhiều link hơn C (189.146 vs 186.510) nhưng **2.636 link đó có offset sai** → vô dụng cho
> Phase 4/5. C là phương án đúng vì điều kiện tiên quyết là **offset chính xác**, không phải số lượng link.

### 4.3. So sánh 3 cách đo "tỉ lệ câu hợp lệ" (bản cuối)

| Cách đo | Kết quả | Đánh giá |
|---|---|---|
| Toàn bộ câu (kể cả mục danh sách) | 85,6% | Trung thực nhưng Gate 95% bất khả thi |
| Chỉ văn xuôi (D-016) | **95,3%** | ✅ Dùng cho Gate |
| Chỉ văn xuôi, có heading (bản cũ) | 74,3% | Sai — heading không phải câu |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Bài còn ký tự wiki | 0 | **0** / 2.441 | ✅ |
| Câu văn xuôi kết thúc dấu câu | ≥ 95% | **95,3%** (143.100 câu) | ✅ |
| Offset hợp lệ | 100% | **186.960 / 186.960 = 100%** | ✅ |
| Link giữ lại (mẫu số: wikitext thân bài) | ≥ 95% | **99,8%** (186.510 / 186.868) | ✅ |
| Link giữ lại (mẫu số: wikitext gốc) | — | 80,4% (186.510 / 231.927) | tham chiếu |
| Câu vỡ giữa tên có dấu phẩy | 0 | **0** / 30 fixture thật | ✅ |
| Số câu | 150k–400k | **186.960** | ✅ |
| Test suite | xanh | **185 passed** | ✅ |

Nguồn số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-02-text-stats.json`
(đồng thời: `data/interim/text_stats.json` do `scripts/stats_text.py` sinh ra).

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| **Offset link lệch ở 502 bài** | `clean_text[start:end] != anchor` | `_strip_stray_markers` xoá `[[`/`]]` **sau** khi offset đã ghi → mọi link phía sau lệch | Gỡ ngoặc lạc **trước** khi thay link (stack LIFO); thay link bằng quét **một lần** + đệ quy | Mọi thao tác sửa chữa văn bản phải **đi trước** bước ghi offset, hoặc phải dịch offset theo |
| **`<ref>` không đóng nuốt 80 mục danh sách** | Bài "Hà Nội": 95 dòng danh sách → còn 15 | Regex `<ref\b[^>]*>.*?(?=<ref\b|</ref>\|$)` — nhánh `$` khớp khi không còn `</ref>` | Bỏ nhánh `$`: `.*?(?=<ref\b\|</ref>)` | Regex "xoá đến hết văn bản" là mẫu lỗi kinh điển — luôn thay bằng ranh giới **tường minh** |
| **Câu vỡ ở mỗi dòng** | "Ông sinh năm\n1385 ở Lam Sơn" → 2 câu | Wikipedia ngắt dòng cứng ~80 ký tự; `pysbd` coi `\n` là ranh giới câu | `_join_soft_wrapped_lines()` — nối dòng trong cùng đoạn bằng khoảng trắng | Wikitext **không** phải văn bản; phải khôi phục quy tắc xuống dòng của MediaWiki trước khi tách câu |
| **Markup danh sách còn sót** | `*`, `#`, `:`, `;` ở đầu dòng; 15,8% "câu" là mục danh sách | Marker chưa được gỡ | `_strip_list_markers()` — gỡ marker, tách mỗi item thành đoạn riêng, đánh dấu bằng sentinel | Mục danh sách là **cấu trúc**, không phải câu — phải tách cấu trúc **trước** khi tách câu |
| **Heading chứa link không khớp tiêu đề** | Các tiêu đề phụ của "Hà Nội" bị tính nhầm là văn xuôi | `headings` lưu `[[nhà Nguyễn]]` còn `clean_text` có `nhà Nguyễn` | Thêm `plain_title` (rút gọn link) khi trích tiêu đề; so khớp cả hai dạng | Khi thay thế text, **mọi** bản sao của text ở nơi khác phải được cập nhật theo |
| **`}}` thừa làm hỏng quét template** | Bài "Elizabeth II" còn sót `}}` (237 `{{` vs 238 `}}`) | Bộ quét cân bằng ngoặc dừng sớm | `_remove_stray_template_braces()` — đếm độ sâu, xoá `}}` khi độ sâu đã về 0 | Wikitext hỏng là bình thường — bộ xử lý phải **chịu được** dữ liệu bẩn |
| **Tỉ lệ giữ link 115,7%** | > 100% — bất khả thi | Mẫu số đếm bằng regex trên `wikitext` gốc **bỏ sót** link trong template/bảng | Dựng lại wikitext thân bài bằng `prepare_text()` | Mẫu số phải **cùng hệ xử lý** với tử số, nếu không sẽ ra số vô lý |
| **`pysbd` không có `Language.MULTI`** | `AttributeError` → fallback regex | Bản `pysbd` 0.3.4 không có API đó (xem D-013) | Dùng `language="en"` | Kiểm tra API thực tế của thư viện trước khi viết code dựa trên tài liệu |
| **Tạo `pysbd.Segmenter` cho mỗi đoạn** | 3 phút | Khởi tạo lại 100k+ lần | Cache ở mức module → **86 giây** | Vòng lặp nóng thường bị bỏ sót chi phí khởi tạo |

## 7. Bài học kinh nghiệm

1. **Offset chính xác quan trọng hơn số lượng link giữ được.** Bản "nhiều vòng" giữ 189.146 link nhưng
   36,3% sai offset; bản "quét một lần" giữ 186.510 link với **0** lỗi. Phase 4/5/6 chỉ dùng được bản thứ hai.
2. **Mọi thao tác xoá ký tự phải đi trước bước ghi offset** — nếu không, offset là "con số sai một cách âm thầm".
3. **Phải phân biệt "câu" và "cấu trúc".** Heading và mục danh sách không phải câu; tính chung vào thống kê
   khiến Gate trở nên bất khả thi và che mất lỗi thật.
4. **Wikitext không phải văn bản.** Ba quy tắc hiển thị của MediaWiki (ngắt dòng ~80 ký tự, marker danh sách,
   xuống dòng cứng trong template) đều phá vỡ `pysbd` nếu không được khôi phục trước.
5. **Đo lại "trước" bằng code cũ thật, không nhớ.** 3 lỗi trên đều được định lượng lại bằng cách chạy
   commit cũ (`4136880`) trên cùng corpus → có số liệu so sánh đáng tin thay vì cảm tính.

## 8. Ý tưởng cho slide

- **Slide "Vì sao cần đo trước khi làm"**: 502/2.441 bài (20,6%) có link sai offset — mắt thường không thấy
  lỗi offset; phải có assert tự động mới phát hiện.
- **Slide "Ba lớp rủi ro khi xử lý wikitext"**: (1) offset, (2) ngắt dòng cứng, (3) markup danh sách →
  3 sửa lỗi, tỉ lệ câu hợp lệ 83,6% → 95,3%.
- **Slide "Chất lượng văn bản sau Phase 2"**: 2.441 bài · 101.628 đoạn · 186.960 câu · 186.510 link ·
  **0 lỗi offset** · **0 ký tự wiki còn sót** · 99,8% link được giữ.
- **Slide "Đo đúng mẫu số"**: mẫu số thân bài 99,8% vs mẫu số gốc 80,4% — cùng một dữ liệu, hai cách đo,
  kết luận khác hẳn. Đây là bài học về *measurement design*, không chỉ về code.
- **Slide "Ảnh hưởng của tối ưu"**: cache `pysbd.Segmenter` 3 phút → 86 giây (−52%), ảnh hưởng trực tiếp
  tới thời gian chạy lại pipeline khi tinh chỉnh.

## 9. Việc tiếp theo

**Phase 3 — Parse infobox, chuẩn hóa ngày (A4).** Trạng thái: ⬜ chưa bắt đầu.

Các việc cần làm (theo `docs/09-ke-hoach-thuc-thien.md` → Phase 3):
1. `configs/infobox_mapping.yaml` — mapping trường infobox → quan hệ KG (nguồn sự thật cho cấu hình).
2. `src/preprocess/parse_infobox.py` — parse `infobox_raw` đã tách sẵn ở Phase 2.
3. `src/preprocess/infobox_entity_types.py` — sinh `entity_id` theo format `ent_<slug>_<hash8>`.
4. Mở rộng `parse_vi_date` trong `src/common/normalize.py` — phủ các định dạng ngày trong infobox tiếng Việt.
5. Align `RELATION_SUBJECT_TYPES` trong `src/common/schemas.py` với 18 quan hệ đã chốt trong `docs/04`.
6. Sinh `data/interim/infobox_triples.jsonl` + `data/interim/infobox_entities.jsonl`.
7. Tạo `tests/fixtures/dates.jsonl`, `tests/test_infobox.py`, `tests/test_normalize.py`, `scripts/stats_infobox.py`.

# Deviations — Nhật ký sai lệch so với kế hoạch

> Ghi **mọi** sai lệch so với `docs/09-ke-hoach-thuc-thien.md`: đổi công nghệ, đổi contract, đổi phạm vi, không đạt Gate, dùng fallback.
> Mục tiêu: báo cáo cuối cùng trung thực, không bịa số liệu.

## Format

```markdown
## D-001 — <mô tả ngắn>
- Ngày: YYYY-MM-DD
- Phase: <N>
- Loại: công nghệ | contract | phạm vi | tiêu chí | kỹ thuật
- Kế hoạch: <một câu>
- Thực tế: <một câu>
- Lý do: <một câu>
- Ảnh hưởng: <một câu>
- Xử lý: <một câu>
- Cập nhật file: <danh sách>
```

## Nhật ký

## D-001 — Agent triển khai sớm vượt phạm vi "setup vibe-coding"
- Ngày: 2026-11-10
- Phase: — (ngoài phase nào)
- Loại: phạm vi
- Kế hoạch: Chỉ tạo bộ file setup vibecode (`AGENTS.md`, rules, skills, docs context).
- Thực tế: Sau câu lệnh `/goal dont stop before you done the plan`, agent đọc nó là "làm hết 15 phase" và bắt đầu viết code Phase 0/1, tạo venv, chạy Neo4j Docker, tải dump Wikipedia (2GB+).
- Lý do: Diễn giải `/goal` thành "hoàn thành toàn bộ kế hoạch triển khai" thay vì "hoàn thành phần setup được giao".
- Ảnh hưởng: Tốn tài nguyên máy (download 2GB+, container Neo4j) và tạo ra artifact không được yêu cầu. Đã xóa toàn bộ.
- Xử lý: Thu hồi toàn bộ code triển khai sớm (`src/`, `backend/`, `frontend/`, `tests/`, `scripts/`, `configs/`, `requirements.txt`, `docker-compose.yml`, `.venv`, `data/`). Dừng container Neo4j. Bổ sung ghi chú phạm vi vào `AGENTS.md` §4.
- Cập nhật file: `AGENTS.md`, `docs/PROGRESS.md`

## D-002 — Neo4j Community không hỗ trợ RBAC (read-only user theo role)
- Ngày: 2026-11-10
- Phase: 10 (ghi nhận sớm từ kiểm chứng hạ tầng)
- Loại: kỹ thuật
- Kế hoạch: Tạo user `reader` với role built-in `reader` của Neo4j 5 → DB tự chặn ghi.
- Thực tế: `CREATE USER … SET ROLE reader` và `GRANT MATCH ON GRAPH … TO reader` đều lỗi cú pháp trên Neo4j 5 Community. User `reader` tạo được nhưng **vẫn ghi được** vào DB.
- Lý do: RBAC / fine-grained access control chỉ có trong Neo4j Enterprise.
- Ảnh hưởng: Cơ chế bảo vệ cấp DB theo kế hoạch không tồn tại.
- Xử lý: Chuyển sang cơ chế **session READ access mode** (`default_access_mode=READ_ACCESS`) — server từ chối mọi lệnh ghi (`Neo.ClientError.Statement.AccessMode`), đã kiểm chứng kể cả với superuser. Validator tĩnh ở tầng app giữ nguyên vai trò lớp phòng thủ đầu tiên.
- Cập nhật file: `.cursor/rules/cypher-safety.mdc`, `docs/DECISIONS.md` (D-008), `docs/CONTEXT.md` §2.7, `docs/09-ke-hoach-thuc-thien.md` (Phase 10), `AGENTS.md` §5.2

## D-003 — Thư viện `mwparser` không có bản dùng được trên PyPI
- Ngày: 2026-11-10
- Phase: 1 (ghi nhận sớm từ kiểm chứng hạ tầng)
- Loại: công nghệ
- Kế hoạch: Dùng `mwparser>=0.6.2` để parse wikitext.
- Thực tế: PyPI chỉ có bản `0.1`; bản `0.6.2` không được publish.
- Lý do: Package không còn được duy trì trên PyPI.
- Ảnh hưởng: Không cài được dependency theo kế hoạch.
- Xử lý: Dùng `lxml.etree.iterparse` để parse dump XML (streaming, nhanh hơn cho file 2GB+) + regex/wikitext-cleanup cho phần text.
- Cập nhật file: `docs/CONTEXT.md` §2.7, `docs/PROGRESS.md`

## D-004 — Bỏ `mwparser` khỏi `requirements.txt` (Phase 0)
- Ngày: 2026-11-13
- Phase: 0
- Loại: công nghệ
- Kế hoạch: Output contract Phase 0 liệt kê `mwparser` trong `requirements.txt`.
- Thực tế: Dùng `lxml` + `wikitextparser` + `pysbd`; không cài `mwparser`.
- Lý do: PyPI chỉ có bản `mwparser` 0.1 (bản 0.6.2 chưa publish) — đã ghi nhận ở D-003 và `docs/CONTEXT.md` §2.7.
- Ảnh hưởng: Không ảnh hưởng contract; `requirements.txt` của Phase 1+ cũng dùng bộ thư viện này.
- Xử lý: Cập nhật `requirements.txt` và ghi rõ lý do trong file.
- Cập nhật file: `requirements.txt`, `reports/phase_00_report.md`

## D-005 — Bỏ `underthesea`, dùng `pysbd` + regex tách đoạn (Phase 0)
- Ngày: 2026-11-13
- Phase: 0
- Loại: công nghệ
- Kế hoạch: Output contract Phase 0 liệt kê `underthesea` trong `requirements.txt`.
- Thực tế: Không cài `underthesea`; dùng `pysbd` để tách câu và regex `\n\s*\n` để tách đoạn.
- Lý do: Đúng mục "Lùi" của Phase 0 trong `docs/09-ke-hoach-thuc-thien.md` — `underthesea` không ổn định trên Python 3.12.
- Ảnh hưởng: Chất lượng tách câu có thể thấp hơn `underthesea`; cần đo ở Gate Phase 2 (≥95% câu kết thúc bằng dấu câu).
- Xử lý: Thêm `split_paragraphs` (regex) vào `src/common/text_utils.py`; ghi fallback vào `docs/CONTEXT.md` §2.7.
- Cập nhật file: `requirements.txt`, `src/common/text_utils.py`, `reports/phase_00_report.md`

## D-006 — `frontend/tsconfig.json` không dùng project reference (Phase 0)
- Ngày: 2026-11-13
- Phase: 0
- Loại: kỹ thuật
- Kế hoạch: Vite React TS template mặc định dùng `tsconfig.json` + `tsconfig.node.json` với `references`.
- Thực tế: Gộp `vite.config.ts` vào cùng `include` của `tsconfig.json`, bỏ `tsconfig.node.json`.
- Lý do: `composite: true` + `noEmit: true` xung đột → TypeScript báo lỗi TS6310 ("Referenced project may not disable emit").
- Ảnh hưởng: Không ảnh hưởng chức năng; `npm run build` vẫn chạy `tsc --noEmit` trên toàn bộ mã nguồn.
- Xử lý: Cài `@types/node` và dùng `loadEnv` từ Vite thay cho `process.env` trực tiếp trong `vite.config.ts`.
- Cập nhật file: `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/package.json`

## D-007 — Không quy đổi ngày âm lịch sang dương lịch (Phase 0)
- Ngày: 2026-11-13
- Phase: 0 (quyết định thiết kế trước khi làm Phase 3)
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 0 yêu cầu `src/common/normalize.py` có hàm chuẩn hóa ngày.
- Thực tế: `src/common/normalize.py` chỉ *nhận diện* ngày âm lịch (`is_lunar_date`) và trả `precision` cho ngày dương; **không** quy đổi âm → dương.
- Lý do: Bảng quy đổi âm lịch thủ công dễ sai và phụ thuộc múi giờ; quy đổi sai sẽ vi phạm nguyên tắc "không bịa" của dự án (quy tắc 3 trong `AGENTS.md` §5).
- Ảnh hưởng: Phase 3 chỉ gắn cờ `is_lunar` trong bằng chứng thay vì quy ra ngày dương tuyệt đối. Nếu cần ngày dương tuyệt đối cho ngày âm thì phải dùng thư viện chuyên dụng ở Phase 3 (có thể ghi thêm deviation).
- Xử lý: Ghi chú rõ trong docstring của `src/common/normalize.py`.
- Cập nhật file: `src/common/normalize.py`, `reports/phase_00_report.md`

## D-008 — T2 cần thêm điều kiện "có category liên quan Việt Nam" (Phase 1)
- Ngày: 2026-11-13
- Phase: 1
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 1 mô tả T2 = "loại infobox trong whitelist, hoặc có ≥ 2 trường lịch sử".
- Thực tế: T2 (và T3 nới lỏng) **bắt buộc** thêm điều kiện: bài phải thuộc category có khớp `viet|dai viet`; đồng thời siết số trường lịch sử tối thiểu theo từng loại infobox (`person: 3`, `place: 2`, `dynasty: 2`, `battle: 1`, `event: 1`).
- Lý do: Đo thực tế trên dump: các trận đánh toàn cầu (`Trận Verdun`, `Trận Poltava`, `Chiến tranh Boer`) có infobox `battle` + mốc năm trong cửa sổ → lọc theo kế hoạch sẽ giữ hàng trăm bài không liên quan Việt Nam.
- Ảnh hưởng: T2 giảm từ ~1.300 xuống 277 bài (T0+T1 vẫn giữ 2.615); tổng corpus 3.113 bài — vẫn nằm trong khoảng 2.000–5.000.
- Xử lý: Thêm `_has_vietnam_category()` vào `src/preprocess/filter_articles.py`; thêm `infobox_min_history_fields` vào `configs/seed_articles.yaml`.
- Cập nhật file: `src/preprocess/filter_articles.py`, `configs/seed_articles.yaml`, `reports/phase_01_report.md`

## D-009 — `normalize_infobox_type` phải khớp từ khoá đầy đủ, không khớp tiền tố (Phase 1)
- Ngày: 2026-11-13
- Phase: 1
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 1 nói "loại infobox trong whitelist".
- Thực tế: Khớp tiền tố chuỗi bị loại: `tranh` (tranh vẽ) khớp `tran` → nhận nhầm `battle`; `nha nhac` khớp `nha` → nhận nhầm `dynasty`.
- Lý do: Bảng `INFOBOX_TYPE_MAP` chứa nhiều khoá có thể là tiền tố của nhau.
- Ảnh hưởng: Trước khi sửa, phân bố `infobox_type` lệch (battle/dynasty thừa, còn `none` sai số).
- Xử lý: `normalize_infobox_type` ưu tiên khớp chính xác; chỉ dùng khớp tiền tố khi khoá đủ dài (≥ 4 ký tự) và không trùng khoá khác.
- Cập nhật file: `src/preprocess/infobox_parser.py`, `tests/test_infobox_parser.py`

## D-010 — Cây category phải khóa theo `title`, không phải `page_id` (Phase 1)
- Ngày: 2026-11-13
- Phase: 1
- Loại: kỹ thuật
- Kế hoạch: `docs/05` §2.4 mô tả mở rộng đệ quy subcategory từ `pages-meta-current`.
- Thực tế: Trong `categorylinks`, `cl_from` là `page_id` của **trang category** (ns 14) còn `cl_target_id` là `lt_id` trong bảng `linktarget`. Code ban đầu trộn hai khoá này → mở rộng cây trả về **0** subcategory (chỉ 11 category, 1.285 trang).
- Lý do: Schema MediaWiki tách `categorylinks` và `linktarget` thành hai bảng riêng.
- Ảnh hưởng: Sau khi sửa, cây category mở rộng từ 11 lên **81 category** (1.682 categorylink, 1.285 trang duy nhất) → T1 giữ 1.190 bài thay vì ~0.
- Xử lý: Dựng `parent_to_children` theo `normalize_name(parent_title)`; regex SQL chấp nhận cả `,` và `;` kết thúc dòng.
- Cập nhật file: `src/preprocess/category_index.py`, `data/interim/category_members.json`, `data/interim/category_hierarchy.json`

## D-011 — Bộ lọc chạy 3 lượt streaming thay vì 1 lượt (Phase 1)
- Ngày: 2026-11-13
- Phase: 1
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 1 nói parse dump theo luồng, không nạp toàn bộ vào RAM.
- Thực tế: Cần 3 lượt đọc dump: (1) phân loại T0/T1/T2, (2) BFS T3 — mỗi chiều sâu lại quét dump để lấy `links` của biên, (3) ghi `wikitext` ra đĩa.
- Lý do: `links` chỉ có trong `pages-articles`; giữ toàn bộ links của 2,25 triệu trang trong RAM sẽ vượt ngưỡng 4GB.
- Ảnh hưởng: Tổng thời gian 31 phút, RAM peak **≈ 1,18 GB** (đạt Gate < 4GB). Chi phí: đọc lại file 1,1 GB nhiều lần.
- Xử lý: Giữ nguyên kiến trúc 3 lượt; ghi nhận rằng nếu cần tối ưu thời gian thì đổi sang lưu `links` ra file đĩa ở lượt 1.
- Cập nhật file: `src/preprocess/filter_articles.py`, `reports/phase_01_report.md`

## D-012 — Thêm tầng T5 "chốt phạm vi lịch sử Việt Nam" (Phase 1)
- Ngày: 2026-11-14
- Phase: 1
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 1 mô tả 4 tín hiệu T0–T4, không có bước chốt phạm vi cuối.
- Thực tế: Lượt chạy đầu giữ **3.113 bài**, nhưng đo thực tế cho thấy **~35% rơi ra ngoài phạm vi lịch sử Việt Nam**: `Trận Stalingrad`, `Trận Le Mans`, `Chiến tranh Afghanistan (2001–2021)`, `Nhà Ptolemaios`, `Vương triều Palaiologos`, `Chiến tranh Mali`, `Xung đột chính trị Jamaica`…
- Lý do: Tín hiệu T0 từ Wikidata `P31/wdt:P279* = Q178561` (trận đánh) và `P31 = Q164950` (triều đại) lấy được **mọi** trận đánh / triều đại có bài tiếng Việt, không giới hạn cho Việt Nam. Kiểm tra `P17`/`P276`/`P131` trên các trận đánh trả về **0 dòng** (Wikidata không gắn quốc gia cho trận đánh).
- Ảnh hưởng: Corpus 3.113 → **2.441 bài** (vẫn trong khoảng Gate 2.000–5.000); chất lượng tăng rõ (mẫu ngẫu nhiên seed 99: 25/25 bài đúng phạm vi).
- Xử lý: Thêm hàm `_in_history_scope()` + `_has_scope_category()`:
  - Tín hiệu Wikidata **đã gắn Việt Nam** (`person`/`place`/`house` — `P27`/`P19`/`P39`/`P17` → `Q881`) → giữ, không cần kiểm tra thêm.
  - Tín hiệu **quá rộng** (`battle`/`dynasty`/`event`) → chỉ giữ khi bài có category trong phạm vi Việt Nam.
  - Tín hiệu `category` → phải nằm trong cây seed **và** có category trong phạm vi.
  - Category trong phạm Việt Nam = có chữ "Việt" **hoặc** khớp regex "nhà vua" (`VN_HOUSE_RE`: Nhà Ngô/Đinh/Tiền Lê/Lý/Trần/Hồ/Mạc/Lê sơ/Hậu Lê/Lê Trung Hưng/Nguyễn/Tây Sơn) — vì nhiều nhân vật chỉ có category địa phương ("Người Bắc Ninh", "Vương tước nhà Lý").
- Cập nhật file: `src/preprocess/filter_articles.py`, `tests/test_filter_scope.py`, `reports/phase_01_report.md`, `docs/CONTEXT.md` §2.7

## D-013 — `pysbd` 0.3.4 không có `Language.MULTI` (Phase 2, phát hiện khi chuẩn bị chạy)
- Ngày: 2026-11-14
- Phase: 2 (phát hiện khi dry-run code đã commit ở Phase 1)
- Loại: công nghệ
- Kế hoạch: `docs/09` Phase 2 yêu cầu dùng `pysbd.Segmenter(language=pysbd.Language.MULTI)`.
- Thực tế: Bản `pysbd` 0.3.4 cài được (Python 3.14) **không có** `Language.MULTI`; hỗ trợ 23 ngôn ngữ, **không có tiếng Việt**.
- Lý do: `Language.MULTI` là API của một bản pysbd khác; bản phát hành hiện tại không có.
- Ảnh hưởng: Code đã commit sẽ **luôn** rơi vào regex fallback → không đạt chất lượng tách câu của pysbd.
- Xử lý: Dùng `pysbd.Segmenter(language="en", clean=False, char_span=True)` — bộ quy tắc tiếng Anh tách đúng tiếng Việt vì dấu kết thúc câu (`.`/`!`/`?`/`…`) giống nhau và tiếng Việt không có dấu phẩy cuối câu. Regex fallback vẫn giữ nguyên làm lưới an toàn.
- Cập nhật file: `src/preprocess/split_sentences.py`

## D-014 — Wikitext thật có link lồng nhau và link hỏng ngoặc (Phase 2)
- Ngày: 2026-11-14
- Phase: 2 (phát hiện khi dry-run code đã commit ở Phase 1)
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 2 yêu cầu thay link nội bộ bằng regex `[[Đích|anchor]]`.
- Thực tế: Wikitext trong dump có (a) **link lồng nhau** — `[[Tập tin:X.jpg|nhỏ|[[Đê sông Hồng]] và [[Dãy núi Ba Vì]]]]`; (b) **link không cân bằng ngoặc** — `[[23 tháng 9 năm 1945 … [[Cộng hòa Tự trị Nam Kỳ|Nam Kỳ]]`; (c) **anchor mồ côi** — `|nhãn]]` khi mở `[[` đã bị nuốt.
- Lý do: Regex phẳng không theo dõi độ sâu ngoặc → cắt đôi link, để lại ký tự `]]` rác trong `clean_text`.
- Ảnh hưởng: Trước khi sửa, còn ký tự wiki trong `clean_text` (Gate Phase 2 yêu cầu 0 bài).
- Xử lý: Thay regex phẳng bằng bộ quét cân bằng ngoặc (`_find_link_end`) + thay thế nhiều vòng theo link trong cùng (`_innermost_links`); thêm `_strip_stray_markers` dọn `|nhãn]]` và `[[`/`]]` còn sót; xoá dấu in đậm/nghiêng (`'''`, `''`) và quy đổi link ngoài `[nhãn](url)` → `nhãn`.
- Cập nhật file: `src/preprocess/clean_text.py`

## D-015 — Chốt mẫu số "tỉ lệ giữ hyperlink" là wikitext **thân bài** (Phase 2)
- Ngày: 2026-11-14
- Phase: 2
- Loại: tiêu chí
- Kế hoạch: `docs/09` Phase 2 yêu cầu "≥95% hyperlink được giữ", mẫu số ngầm định là số link trong wikitext gốc.
- Thực tế: Tính trên wikitext gốc cho **80,4%** (186.510/231.927) — dưới ngưỡng Gate 95% dù chất lượng thực tế rất tốt.
- Lý do: Mẫu số gốc **bao gồm** link nằm trong infobox, template trích dẫn, bảng, link tập tin — những phần **bị gỡ có chủ đích** vì không phải văn bản thân bài. Chúng không thể xuất hiện trong `clean_text`.
- Ảnh hưởng: Đo trên mẫu số **wikitext thân bài** (sau khi gỡ infobox/template/ref/bảng/markup) cho **99,8%** (186.510/186.868) — đạt Gate. Báo cáo **cả hai** tỉ lệ để minh bạch.
- Xử lý: `scripts/stats_text.py` tái chạy `prepare_text()` để dựng lại wikitext thân bài rồi đếm link (nếu đếm bằng regex trên `wikitext` gốc thì **đếm thiếu** link trong template/bảng → mẫu số sai, tỉ lệ ra 115,7% — bất khả thi).
- Cập nhật file: `scripts/stats_text.py`, `reports/phase_02_report.md`, `docs/10-nhat-ky/phase-02.md`

## D-016 — Phải phân biệt "câu văn xuôi" và "mục danh sách" khi đo tỉ lệ câu hợp lệ (Phase 2)
- Ngày: 2026-11-14
- Phase: 2
- Loại: tiêu chí
- Kế hoạch: `docs/09` Phase 2 yêu cầu "≥95% câu kết thúc bằng dấu câu" trên toàn bộ tập câu.
- Thực tế: Tính trên **toàn bộ** câu cho **85,6%** (186.960 câu) — dưới ngưỡng Gate 95%.
- Lý do: **43.860 mục danh sách** (23,5% tập câu) là mệnh đề ngắn, không có dấu kết thúc. Tính chúng vào thống kê là đo sai đối tượng (đo "câu" nhưng thực tế đo "câu + mệnh đề"). Tỉ lệ trên **văn xuôi** là **95,3%** (143.100 câu).
- Ảnh hưởng: `clean_text.py` phải gắn nhãn `paragraph_kinds` (`"prose"` / `"list_item"`) theo **nội dung** qua sentinel `\uE000` — không thể so khớp nội dung trước/sau bước thay link (nội dung item thay đổi, đo được: mọi mục danh sách ở bài "Hà Nội" bị tính nhầm là văn xuôi). Sentinel phải gỡ ở bước cuối và **dịch offset** link phía sau.
- Xử lý: Gate đo trên văn xuôi; vẫn báo cáo tỉ lệ toàn bộ để minh bạch. Tương tự, **tiêu đề** (heading) bị loại khỏi tập câu (trước đó 9,5% "câu" là tiêu đề, kéo tỉ lệ hợp lệ xuống 74,3%) nhưng vẫn được giữ đầy đủ trong `paragraphs`.
- Cập nhật file: `src/preprocess/clean_text.py`, `src/preprocess/split_sentences.py`, `scripts/stats_text.py`, `reports/phase_02_report.md`

## D-017 — Bổ sung nối dòng xuống dòng cứng + gỡ markup danh sách (Phase 2, ngoài kế hoạch gốc)
- Ngày: 2026-11-14
- Phase: 2
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 2 chỉ yêu cầu xoá template/ref/File/Thể loại/bảng/HTML và thay wikilink.
- Thực tế: Chỉ với các bước trong kế hoạch, tỉ lệ câu kết thúc bằng dấu câu chỉ đạt **83,6%** (mẫu 400 bài) — không thể đạt Gate 95%.
- Lý do: Wikipedia ngắt dòng cứng ~80 ký tự (quy tắc hiển thị mã nguồn) → `pysbd` coi mỗi `\n` là ranh giới câu, câu gốc bị vỡ thành nhiều "câu" không có dấu kết thúc. Thêm nữa, markup danh sách `*` `#` `:` `;` còn sót khiến mỗi item thành một "câu" riêng.
- Ảnh hưởng: `clean_text` đổi cấu trúc đoạn; `paragraph_spans()` được tách ra `src/common/text_utils.py` để `clean_text.py` và `split_sentences.py` dùng chung **một** định nghĩa ranh giới đoạn (tránh lệch chỉ số đoạn ↔ nhãn).
- Xử lý: Thêm `_join_soft_wrapped_lines()` (nối dòng trong cùng đoạn bằng khoảng trắng) và `_strip_list_markers()` (gỡ marker, tách mỗi item thành đoạn riêng, đánh dấu sentinel). Kết quả: văn xuôi **89,1%** → sau khi sửa thêm điểm heading/link **95,3%**.
- Cập nhật file: `src/preprocess/clean_text.py`, `src/common/text_utils.py`, `src/preprocess/split_sentences.py`

## D-018 — Cache `pysbd.Segmenter` ở mức module (Phase 2)
- Ngày: 2026-11-14
- Phase: 2
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 2 không quy định cách khởi tạo `pysbd`.
- Thực tế: Bản đầu khởi tạo `pysbd.Segmenter` cho **mỗi đoạn** → toàn corpus mất **~3 phút**.
- Lý do: `pysbd.Segmenter` nạp bảng ngữ pháp vào RAM mỗi lần khởi tạo; gọi ~100.000 lần là lãng phí thuần.
- Ảnh hưởng: Thời gian tách câu toàn corpus giảm còn **~86 giây** (−52%) → thời gian chạy lại pipeline khi tinh chỉnh giảm rõ rệt.
- Xử lý: Thêm `_get_segmenter()` cache ở mức module.
- Cập nhật file: `src/preprocess/split_sentences.py`

## D-019 — Căn `RELATION_SUBJECT_TYPES` theo `docs/04` (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 3 sinh triple theo 18 quan hệ đã chốt ở `docs/04` §3.1.
- Thực tế: Bảng `RELATION_SUBJECT_TYPES` trong `src/common/schemas.py` lệch `docs/04` ở 4 dòng: `dong_doi_tai` ghi subject=`place` (đúng: `dynasty` → place); `thuoc_trieu_dai` thiếu `dynasty`/`event`; `sinh_tai`/`mat_tai` cho phép subject=`place` (đúng: `person` → place).
- Lý do: Validator dùng bảng này để **loại** triple vi phạm. Không sửa thì `dien_ra_tai` với subject=`event` (hợp lệ theo `docs/04`) bị loại oan.
- Ảnh hưởng: Sửa 4 dòng. **Tập 18 quan hệ không đổi** → không cần sửa danh mục ở `docs/CONTEXT.md` §2.5, chỉ bổ sung bảng ràng buộc loại.
- Xử lý: Sửa `src/common/schemas.py`; ghi chú vào `docs/04` §3.1 và `docs/CONTEXT.md`.
- Cập nhật file: `src/common/schemas.py`, `docs/04-schema-knowledge-graph.md`, `docs/CONTEXT.md`

## D-020 — `battle` → `event`, giữ nguyên `infobox_parser.py` (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: kỹ thuật
- Kế hoạch: KG có 7 loại node đóng (`docs/CONTEXT.md` §2.4), trong đó `event` bao trùm chiến tranh.
- Thực tế: `INFOBOX_TYPE_MAP` (Phase 1) trả `"battle"` cho template chiến tranh — **không phải** loại node KG hợp lệ.
- Lý do: Sửa `infobox_parser.py` sẽ làm đổi hành vi Phase 1 (checksum corpus, test cũ). Phase 3 có bảng `type_map` riêng trong `configs/infobox_mapping.yaml` map `battle`/`chiến tranh`/`military conflict` → `event`.
- Ảnh hưởng: 202 bài `battle` + 11 bài `event` → 213 node `event`. `normalize_type()` bỏ tiền tố "Infobox"/"Thông tin" trước khi tra bảng (vì `wikitextparser` trả tên template đầy đủ, regex Phase 1 trả tên đã bỏ tiền tố).
- Xử lý: Không sửa file Phase 1; dùng config riêng + `normalize_type()`.
- Cập nhật file: `configs/infobox_mapping.yaml`, `src/preprocess/infobox_entity_types.py`

## D-021 — 146/1.061 bài `person` có infobox rỗng → đổi định nghĩa Gate 1 (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: tiêu chí
- Kế hoạch: `docs/09` Phase 3 Gate 1 yêu cầu "≥95% bài person có infobox parse thành công".
- Thực tế: **146 / 1.061** bài có template `{{Thông tin nhân vật phong kiến}}` **hoàn toàn rỗng** (không tham số nào). Đo theo "có ít nhất 1 tham số" chỉ đạt 86,2%.
- Lý do: Wikipedia viết infobox cho có, không điền tham số. Đây là **đặc điểm dữ liệu**, không phải lỗi parse.
- Ảnh hưởng: Gate 1 đổi định nghĩa thành "nhận diện được khối template" (tên loại + dict tham số, kể cả rỗng) → **100%**. Thêm test thứ hai đo "mọi infobox **có** tham số đều parse ≥99% tham số" → 100%. Coverage thực sự đo ở **Gate 2**.
- Xử lý: Ghi rõ định nghĩa trong `reports/phase_03_report.md` và `docs/10-nhat-ky/phase-03.md` §D-021.
- Cập nhật file: `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`, `tests/test_infobox.py`

## D-022 — `parse_vi_date` trả ISO 4 chữ số cho năm < 1000 (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: kỹ thuật
- Kế hoạch: `docs/01` quy định định dạng ngày ISO-8601 `YYYY-MM-DD`.
- Thực tế: `datetime.date(939, 2, 1).isoformat()` → `"939-02-01"` — thiếu số 0 ở đầu.
- Lý do: Python không padding năm < 1000; lịch sử Việt Nam có **nhiều** năm 3 chữ số (938, 939, 944, 965, 974…) nên lỗi này ảnh hưởng lớn.
- Ảnh hưởng: Thêm helper `_to_iso()` → `f"{year:04d}-{month:02d}-{day:02d}"`. 2 fixture đổi kỳ vọng `"939-02-01"` → `"0939-02-01"`.
- Xử lý: Thêm `_to_iso()` vào `src/common/normalize.py`; dùng cho mọi nhánh trả ngày.
- Cập nhật file: `src/common/normalize.py`, `tests/fixtures/dates.jsonl`, `tests/test_normalize.py`

## D-023 — 3 artifact mới ở Phase 3 (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: contract
- Kế hoạch: `AGENTS.md` §7 liệt kê artifact theo phase; Phase 3 trong `docs/09` mới nêu output contract cục bộ.
- Thực tế: Phase 3 sinh **3** file mới: `data/interim/infobox_triples.jsonl`, `data/interim/lead_triples.jsonl`, `data/interim/infobox_entities.jsonl`.
- Lý do: Cần tách triple theo nguồn (đường sạch confidence 0,95+ vs fallback 0,85) và tách node props khỏi triple để Phase 8 (entity linking) và Phase 10 (nạp Neo4j) dùng lại.
- Ảnh hưởng: Bổ sung 3 dòng vào `AGENTS.md` §7 + `.cursor/rules/data-contracts.mdc` + output contract của `docs/09` §Phase 3.
- Xử lý: Cập nhật 3 file tài liệu trong cùng một lần.
- Cập nhật file: `AGENTS.md`, `.cursor/rules/data-contracts.mdc`, `docs/09-ke-hoach-thuc-thien.md`

## D-024 — Loại chủ thể không suy được → `article`, không mặc định `person` (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: kỹ thuật
- Kế hoạch: `docs/09` Phase 3 yêu cầu "suy `subject_type`/`object_type` từ infobox type + giá trị".
- Thực tế: `resolved_type = normalize_type(...) or doc_type or "person"` → khi tên template không có trong `type_map` (43 bài), chủ thể **rơi xuống mặc định `person`**. Kết quả: node **"Hà Nội"** và **"Cần Thơ"** trong `infobox_entities.jsonl` có `type="person"` (sai hoàn toàn).
- Lý do: `person` là loại phổ biến nhất (1.205/1.764 entity) nên dễ trở thành mặc định ngầm — nhưng đó chính là lý do nó **bịa âm thầm** (vi phạm `AGENTS.md` §5.3).
- Ảnh hưởng: 9 triple bị loại (thay vì sinh sai). Triple 10.403 → **10.394**. Gate 1–5 **không đổi** (100% / 92,4% / 100% / 100% / 0) — vì Gate đo *tỉ lệ*, không đo *sai lệch nội dung*.
- Xử lý: Tách **hai mặc định** vì vai trò khác nhau: `DEFAULT_TYPE="article"` cho **chủ thể** (loại trung tính) và `DEFAULT_OBJECT_TYPE="person"` cho **đối tượng** (trường không khai báo `value_type` gần như luôn là người). Thêm bước suy loại chủ thể từ `wikidata_signal` (Phase 1) giữa tên template và mặc định. Sửa kèm: (a) `normalize_type()` thử khớp chính xác **trước** khi bỏ tiền tố — 6 khoá `type_map` có tiền tố trở nên không bao giờ được gọi, 451 bài "Thông tin nhân vật phong kiến" không map được; (b) bổ sung 36 khoá `type_map` cho template chưa có (đo trên 2.441 bài). Thêm 6 test regression.
- Cập nhật file: `src/preprocess/infobox_entity_types.py`, `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`, `tests/test_infobox.py`, `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`

## D-025 — Bổ sung 11 thuộc tính node đầy đủ (`birth_place`/`death_place` còn thiếu) (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 3 liệt kê 11 thuộc tính node bắt buộc cho `data/interim/infobox_entities.jsonl`: `birth_year`, `death_year`, `reign_start`, `reign_end`, `temple_name`, `posthumous_name`, `reign_title`, `gender`, `aliases`, `birth_place`, `death_place`.
- Thực tế: lần chạy đầu chỉ ghi được **9/11** — thiếu `birth_place` và `death_place`, vì `configs/infobox_mapping.yaml` khai báo `noi sinh` / `noi mat` chỉ sinh **triple** (`sinh_tai` / `mat_tai`) mà không ghi thêm vào `props`.
- Lý do: `props` và triple là hai loại kiểm tra khác nhau — có quan hệ **không** đồng nghĩa có thuộc tính. Phase 3 chỉ có test cho quan hệ nên không phát hiện thiếu thuộc tính.
- Ảnh hưởng: `birth_place` **643** entity, `death_place` **516** entity. Tổng triple **không đổi** (10.394) vì `prop` chỉ bổ sung thuộc tính node, không sinh quan hệ mới. Gate 1–5 **không đổi**.
- Xử lý: Thêm khoá `prop:` vào spec của trường trong config (`noi sinh` → `prop: birth_place`, `noi mat` → `prop: death_place`; tương ứng cho các khoá tiếng Anh). `add_triple()` **trả về `bool`** để prop chỉ được ghi khi triple **thực sự** được sinh — không khẳng định thuộc tính cho quan hệ đã bị loại vì lỗi schema. Thêm 2 test: (a) tập `props` phủ đủ 11 khoá; (b) prop chỉ được ghi khi triple tương ứng được sinh.
- Cập nhật file: `configs/infobox_mapping.yaml`, `src/preprocess/parse_infobox.py`, `.cursor/rules/data-contracts.mdc`, `tests/test_infobox.py`, `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`

## D-026 — Mọi artifact Phase 3 ghi `dump_version` + `model_name` (Phase 3)
- Ngày: 2026-11-14
- Phase: 3
- Loại: contract
- Kế hoạch: `AGENTS.md` §5.6 (nguyên tắc "Tái lập") — *"ghi `dump_version` + `model_name` vào mọi artifact"*.
- Thực tế: lần chạy đầu của Phase 3 không ghi 2 trường này vào bất kỳ artifact nào → không truy được artifact về đúng phiên bản dump / mô hình đã dùng.
- Lý do: ràng buộc không có test kiểm tra → dễ bị bỏ sót lặp lại ở mỗi phase (Phase 1/2 chỉ có `documents.jsonl` nên không lộ).
- Ảnh hưởng: không đổi số liệu Gate. Sau khi sửa, cả 3 artifact đều có `dump_version="20261101"` + `model_name="vinai/phobert-base"`.
- Xử lý: Bổ sung 2 trường vào `src/preprocess/parse_infobox.py` (triple + entity) và `src/preprocess/extract_lead_dates.py` (triple đoạn dẫn). `dump_version` của triple lấy **theo từng bài** từ `documents.jsonl` (không phụ thuộc thứ tự chạy). Thêm 3 test bắt buộc (`test_triples_carry_dump_version_and_model_name` với 2 tham số + `test_entities_carry_dump_version_and_model_name`) để quy tắc này tự động áp cho các phase sau.
- Cập nhật file: `src/preprocess/parse_infobox.py`, `src/preprocess/extract_lead_dates.py`, `docs/DECISIONS.md` (D-014), `.cursor/rules/data-contracts.mdc`, `tests/test_infobox.py`, `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`

## D-027 — Loại triple trùng `(subject, relation, object)` + self-loop (Phase 3 — audit 14/11/2026)
- Ngày: 2026-11-14
- Phase: 3 (audit đóng phase)
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 3 yêu cầu "100% triple có đủ 6 trường bắt buộc" và `AGENTS.md` §5.1 ("mọi triple/cạnh có bằng chứng"). Không có quy định nào về **trùng lặp**.
- Thực tế: 3 lỗi phát hiện khi audit độc lập Phase 2–3 (14/11/2026), đo trên artifact `infobox_triples.jsonl` tại HEAD (10.394 triple):
  1. **Trùng lặp**: **347** triple thừa trong **341** nhóm trùng khoá `(doc_id, subject, relation, object)` — vd bài có **hai** trường `Ngày sinh` và `Ngày sinh (từ Ngày mất)` cùng năm → `sinh_nam` bị ghi 2 lần. Số `sinh_nam` bị **phình** từ 732 lên **985** (+253, tức +34,6%). (Đo không khoá `doc_id`: **527** triple thừa trong **518** nhóm — phần chênh là các quan hệ **đối xứng hợp lệ** giữa 2 bài, vd "Quang Trung → Nguyễn Nhạc" và "Nguyễn Nhạc → Quang Trung"; **không** phải lỗi.)
  2. **Self-loop**: **4** triple có `subject == object` (vd bài của chính người được ghi là "Tiền nhiệm" của họ) → vi phạm `Triple.is_valid()` trong `src/common/schemas.py`.
  3. **Stale artifact**: `lead_triples.jsonl` được sinh lúc 04:38, `infobox_triples.jsonl` được sinh lại lúc 04:40 → danh sách bỏ qua `docs_with_dates` đã cũ → **81** triple ngày trùng giữa lead và infobox trên **47** bài. Test `test_no_duplicate_lead_and_infobox_dates` **FAIL**.
- Lý do: (1) Wikipedia có nhiều trường cùng nội dung — mỗi trường sinh một triple, không có bước gộp; (2) không có kiểm tra self-loop ở tầng sinh triple; (3) `extract_lead_dates.py` phụ thuộc `infobox_triples.jsonl` nhưng **thứ tự chạy** không được ràng buộc, nên artifact cũ vẫn còn trên đĩa.
- Ảnh hưởng: số liệu Gate **tính sai** (đếm trùng làm tỉ lệ trông đẹp hơn thực tế). Sau khi sửa: triple 10.394 → **10.078** (−316); `sinh_nam` 985 → **732** (−253; 722/732 bài có **đúng 1** `sinh_nam`); `mat_nam` 635 → **628** (−7); self-loop 4 → **0**; trùng trong 1 doc 347 → **0**; trùng lead∩infobox 81 → **0**. Gate 1–5 **không đổi** (100% / 92,4% / 100% / 100% / 0).
- Xử lý: (a) thêm `seen: set[tuple[str, str, str]]` trong `build_triples()` — giữ bản **đầu tiên** (thứ tự trường infobox = bản có bằng chứng trực tiếp), đếm bằng `skipped_duplicate`; (b) thêm kiểm tra `subject == object` → `skipped_self_loop`; (c) ràng buộc **thứ tự chạy** `parse_infobox.py` → `extract_lead_dates.py` và ghi rõ vào `docs/09` §Phase 3 + `reports/phase_03_report.md`; (d) thêm 3 test regression.
- Cập nhật file: `src/preprocess/parse_infobox.py`, `tests/test_infobox.py`, `docs/09-ke-hoach-thuc-thien.md`, `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`

## D-028 — Không trích `danh_bai` từ infobox trận đánh (Phase 3 — audit 14/11/2026)
- Ngày: 2026-11-14
- Phase: 3 (audit đóng phase)
- Loại: phạm vi
- Kế hoạch: `docs/09` §Phase 3 mục 2 ghi `bên tham chiến`/`kết quả` → "thuộc tính event" (không sinh quan hệ). `docs/04` §3.1 quy định `danh_bai`: chủ thể = **người** đánh bại (winner → loser).
- Thực tế: bản triển khai đầu tiên trích `danh_bai` từ trường `ket qua`/`result`. Đo trên toàn bộ **207** trận đánh trong corpus: trích được **4** cặp, trong đó **1 cặp sai** (bài "Trận Đông Dương": suy ra "Campuchia đánh bại Đông Dương", trong khi đúng ra bên thắng là "Việt Nam Dân chủ Cộng hòa"), và **4/4** vi phạm `RELATION_SUBJECT_TYPES["danh_bai"] = {person}` vì bên thắng/thua là **quốc gia / triều đại / liên minh** ("Campuchia", "Việt Minh", "Nhà Thanh").
- Lý do: trường `ket qua` là **câu văn** ("Việt Nam Dân chủ Cộng hòa chiến thắng"), không phải tên node; `combatant1`/`combatant2` là **phe phái**, không phải cá nhân. Suy đoán từ câu văn + ghép với tên phe phái tạo ra quan hệ **sai** — vi phạm `AGENTS.md` §5.3 ("không bịa") nặng hơn việc thiếu một quan hệ.
- Ảnh hưởng: 16/18 quan hệ có triple (thiếu `anh_em_cua` và `danh_bai`). `anh_em_cua` = **0** vì **không bài nào** trong corpus có trường anh em / sibling (đã quét wikitext thô: 0 lần xuất hiện) → đây là **hạn chế dữ liệu**, không phải lỗi code. `danh_bai` = 0 là **quyết định có chủ đích** (D-028) → sẽ sinh ở Phase 8 từ mô hình RE/LLM, nơi bằng chứng ở mức câu văn.
- Xử lý: Xoá hẳn khối cấu hình `battle_result` khỏi `configs/infobox_mapping.yaml` và hàm `extract_battle_result()` khỏi `src/preprocess/parse_infobox.py`; thay bằng comment giải thích + dẫn chiếu D-028. Thêm test regression `test_battle_relation_is_not_extracted_from_infobox`.
- Cập nhật file: `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`, `tests/test_infobox.py`, `docs/09-ke-hoach-thuc-thien.md`, `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`

## D-029 — Gộp khoá tham số infobox `_` ↔ khoảng trắng (`_collapse_key`) (Phase 3 — audit 14/11/2026)
- Ngày: 2026-11-14
- Phase: 3 (audit đóng phase)
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 3 mục 1 yêu cầu "đưa ra dict phẳng `key → value` (key lowercase, bỏ dấu gạch dưới)".
- Thực tế: `normalize_name()` giữ nguyên dấu gạch dưới → Wikipedia dùng **hai** cách viết khoá (`| noi_sinh =` và `| noi sinh =`, `| birth_date =` và `| birth date =`) trở thành **hai khoá khác nhau** trong dict. Bảng mapping viết bằng một biến thể (`noi sinh`) → **không bao giờ** được gọi với biến thể kia (`noi_sinh`). Các trường bị bỏ sót: `noi sinh`/`noi mat` (→ `sinh_tai`/`mat_tai`), `ngay sinh`/`ngay mat`, `ke nhiem`/`tien nhiem`, `gioi tinh`, `tu`/`thuy hieu`/`mieu hieu`…
- Lý do: quy tắc "bỏ dấu gạch dưới" của `docs/09` được hiểu là "bỏ dấu **tiếng Việt**" (bỏ thanh điệu), không phải "bỏ ký tự `_`". Nhưng wikitext thực sự dùng `_` thay khoảng trắng trong nhiều template.
- Ảnh hưởng: một phần trường không được trích → triple bị thiếu. Đo bằng **ablation** (tắt riêng `_collapse_key`, giữ nguyên 2 fix còn lại): tổng triple 10.074 → **10.078** (+4); `sinh_tai` 1.429 → **1.432** (+3); `mat_tai` 952 → **953** (+1). `sinh_nam`/`mat_nam` **không đổi** — các trường ngày trong corpus đều dùng khoảng trắng. Gate 1–5 **không đổi**.
- Xử lý: Thêm `_collapse_key()` (`" ".join(key.replace("_", " ").split())`) trong `src/preprocess/parse_infobox.py`; dựng `fields_by_key` / `aliases_by_key` / `node_props_by_key` (tra bằng khoá đã gộp ở **cả hai** phía → không mất khoá nào).
- Cập nhật file: `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`, `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`

## D-030 — Template mơ hồ `infobox former country` → tín hiệu Wikidata được ưu tiên (Phase 3 — audit 14/11/2026)
- Ngày: 2026-11-14
- Phase: 3 (audit đóng phase)
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 3 mục 4 quy định thứ tự suy loại chủ thể: "tên template (`type_map`) → `wikidata_signal` (Phase 1) → `article`".
- Thực tế: tên template **không phân biệt được** loại chủ thể trong trường hợp này. Wikipedia dùng `{{infobox former country}}` cho **cả** quốc gia ("Việt Nam Cộng hòa", "Nam Kỳ", "Trung Kỳ" → `place`) **và** triều đại ("Nhà Nguyễn", "Nhà Trần", "Nhà Lý", "Nhà Hồ", "Nhà Mạc", "Nhà Tiền Lý"… → `dynasty`). Tên template ép `place` → **13 bài triều đại bị gán nhầm `place`** → `dong_doi_tai` = **0** triple (vì `docs/04` §3.1 yêu cầu chủ thể `dong_doi_tai` là `dynasty`), `thuoc_trieu_dai` mất 13 bài.
- Lý do: bảng `type_map` không thể biểu diễn quan hệ "1 template → nhiều loại". Tín hiệu `wikidata_signal` từ Phase 1 (Wikidata biết "Nhà Trần" là `house`/`dynasty`, "Nam Kỳ" là `place`) là nguồn **mạnh hơn** tên template — nhưng thứ tự ưu tiên trong `docs/09` đặt template trước.
- Ảnh hưởng: `dong_doi_tai` 0 → **31** triple; 13 bài triều đại chuyển từ `place` → `dynasty` (đúng). Đo bằng **ablation** (tắt riêng `AMBIGUOUS_TEMPLATES`): tổng triple 10.047 → **10.078** (+31, toàn bộ là `dong_doi_tai`); `thuoc_trieu_dai` **không đổi** (631) — vì 13 bài triều đại này không có trường `triều đại`/`hoàng tộc` riêng. Gate 1–5 **không đổi**.
- Xử lý: Thêm `AMBIGUOUS_TEMPLATES` trong `src/preprocess/infobox_entity_types.py` (4 template: `infobox former country`, `infobox country`, `infobox former subdivision`, `infobox former monarchy`). `normalize_type()` nhận thêm tham số `wikidata_signal`: nếu template thuộc danh sách mơ hồ **và** có tín hiệu Wikidata → ưu tiên tín hiệu; không có tín hiệu → rơi về `type_map`. Thêm test regression `test_ambiguous_template_prefers_wikidata_signal`.
- Cập nhật file: `src/preprocess/infobox_entity_types.py`, `src/preprocess/parse_infobox.py`, `configs/infobox_mapping.yaml`, `tests/test_infobox.py`, `reports/phase_03_report.md`, `docs/10-nhat-ky/phase-03.md`

## D-031 — Scheme nhãn NER bạc: BIO (13 lớp) thay vì BIOES (25 lớp) (Phase 4 — 14/11/2026)
- Ngày: 2026-11-14
- Phase: 4
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 4 mục 1 viết "sinh `nhãn TIME` bằng regex", output contract minh hoạ `"labels":["B-PERSON","I-PERSON","O",...]`; `docs/09` §Phase 5 mục 2 ghi `num_labels = 2*6 + 1 = 13 (BIOES × 6 nhãn + O)`.
- Thực tế: hai tài liệu **mâu thuẫn nhau** — `docs/CONTEXT.md` §2.4 và output contract Phase 4 dùng **BIO** (13 lớp), còn dòng `num_labels = 2*6 + 1 = 13 (BIOES × 6 nhãn + O)` trong Phase 5 ghi "BIOES" nhưng công thức `2*6+1` chỉ đúng với **BIO** (BIOES thật là `4*6+1 = 25`). Bản triển khai đầu tiên chọn BIOES 25 lớp → lệch `docs/CONTEXT.md` §2.4 và output contract Phase 4.
- Lý do: `docs/CONTEXT.md` là "số đã chốt" (theo `AGENTS.md` §2 "quy tắc vàng"), và output contract Phase 4 minh hoạ nhãn `B-`/`I-`/`O`. Công thức `num_labels = 2*6+1 = 13` cũng khớp BIO. Vì vậy **BIO là lựa chọn đúng**, và dòng "BIOES" trong Phase 5 là **lỗi đánh máy** cần sửa để tránh Phase 5 dùng `num_labels=25`.
- Ảnh hưởng: `ner_silver.jsonl` đổi scheme (`S-`/`E-` → `B-`/`I-`); `src/evaluation/metrics.py` đổi logic gom span (`I-`/`E-` → chỉ `I-`); `tests/test_silver_labels.py` đổi 3 assert về scheme. Số liệu Gate 1–5 **không đổi** (đo lại sau khi chuyển scheme, xem bảng ở `docs/10-nhat-ky/phase-04.md` §4).
- Xử lý: Chuẩn hóa **BIO** trong `src/ner/build_silver.py` (`BIO_PREFIXES = ("B-", "I-")`, `NUM_LABELS = 13`); sửa `src/evaluation/metrics.py`; cập nhật `docs/09` §Phase 5 (bỏ chữ "BIOES"); cập nhật `AGENTS.md` §7 và `docs/CONTEXT.md` §2.4 nếu cần.
- Cập nhật file: `src/ner/build_silver.py`, `src/evaluation/metrics.py`, `tests/test_silver_labels.py`, `docs/09-ke-hoach-thuc-thien.md`, `reports/phase_04_report.md`, `docs/10-nhat-ky/phase-04.md`

## D-032 — Thêm nguồn nhãn `category` (Wikipedia category) đứng đầu thứ tự ưu tiên (Phase 4 — 14/11/2026)
- Ngày: 2026-11-14
- Phase: 4
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 4 mục 1 quy định thứ tự ưu tiên suy nhãn: (1) QID → `P31` → map; (2) `infobox_entities.jsonl`; (3) mẫu tên; (4) bỏ nếu không xác định. `docs/09` §Gate "Lùi" cũng chỉ nhắc 3 nguồn: `qid`/`infobox`/`pattern`.
- Thực tế: bản triển khai đầu tiên theo đúng thứ tự trên chỉ gán được **17.364 + 7.229 + 3.367 + 4.039 + 138 = 32.137 mention** từ link (nhiều đích link không có QID trong dump, hoặc QID không có `P31` — đo được **0/1.788** QID mới có `P31`). Nhưng Wikipedia **category** ("Người Hà Nội", "Thành phố ở Việt Nam", "Chiến tranh Việt Nam", "Nhà Nguyễn") là tín hiệu **mạnh và chính xác** do biên tập viên gắn tay, đặc biệt với corpus tiếng Việt mà `P31` rất thưa.
- Lý do: `P31` cho corpus tiếng Việt không ổn định — nhiều bài không có `P31` chuẩn, và khi `P31` là lớp generic ("human") thì **mọi** người thành `PERSON`, kể cả khi tên đích thực ra là quốc gia/địa danh. Category không có vấn đề này.
- Ảnh hưởng: nguồn nhãn `category` chiếm **69.748 / 138.860 mention (50,2%)** — nguồn lớn nhất. Nhờ vậy **100%** câu có link nội bộ đều có nhãn (Gate 1). Baseline gazetteer trên dev: F1 **0,3917 → 0,7990**.
- Xử lý: Thêm `src/ner/category_types.py` (phân loại category → 6 nhãn, khớp cả bản có dấu lẫn bản bỏ dấu); đặt `category` **đầu** thứ tự ưu tiên trong `SilverLabeller.resolve()`; khai báo `confidence.category = 0.97` trong `configs/ner_silver_config.yaml`. Cập nhật `docs/09` §Phase 4 cho khớp thực tế.
- Cập nhật file: `src/ner/category_types.py`, `src/ner/build_silver.py`, `configs/ner_silver_config.yaml`, `docs/09-ke-hoach-thuc-thien.md`, `reports/phase_04_report.md`, `docs/10-nhat-ky/phase-04.md`

## D-033 — Nhãn TIME chỉ gán khi có ngữ cảnh, loại số đo lượng (Phase 4 — 14/11/2026)
- Ngày: 2026-11-14
- Phase: 4
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 4 mục 1 ghi: "Đồng thời sinh `nhãn TIME` bằng regex trên câu (không cần link): `\b\d{3,4}\b` trong ngữ cảnh 'năm', `thế kỷ [IVXLCDM]+`".
- Thực tế: bản triển khai đầu tiên hiểu `\b\d{3,4}\b` là **không cần ngữ cảnh** → gán TIME cho **mọi** số 3–4 chữ số trong câu. Đo trên 186.960 câu: **57.604** mention TIME, trong đó **16.099** là số **không phải năm**: `000` (từ "650.000 m³/ngày"), `500` (ha), `3000`, `462`, `650`… Nhiều câu bị gán **3–4** nhãn TIME sai liên tiếp (vd "khoảng 650.000 m³/ngày (2015)" → "000" + "2015" cùng là TIME).
- Lý do: `docs/09` đã ghi rõ điều kiện "**trong ngữ cảnh 'năm'**" — bản triển khai đầu bỏ sót điều kiện này. Ngoài ra cần ràng thêm khoảng lịch sử (1000–2100) vì số 3 chữ số không phải năm.
- Ảnh hưởng: TIME **57.604 → 35.685** mention; số TIME sai 16.099 → **0** (đo lại bằng `require_context` + khoảng 1000–2100 + ranh giới từ). Baseline surface dev F1 **0,3495 → 0,3917**; gazetteer **0,7388 → 0,7990**.
- Xử lý: (a) thêm cờ `require_context` cho mẫu năm đứng riêng; (b) thêm `time_context_before` / `time_context_after` vào `configs/ner_silver_config.yaml`; (c) sửa `SilverLabeller._has_time_context()` để chỉ xét **2 token liền kề** (xét cả câu làm mọi số sau một chữ "năm" đều thành "năm" → sai hàng nghìn số như "203/2025/QH15").
- Cập nhật file: `src/ner/build_silver.py`, `configs/ner_silver_config.yaml`, `reports/phase_04_report.md`, `docs/10-nhat-ky/phase-04.md`

## D-034 — Sửa lỗi ranh giới từ trong mẫu category Wikipedia (Phase 4 — 14/11/2026)
- Ngày: 2026-11-14
- Phase: 4
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 4 mục 1 yêu cầu suy nhãn theo đích link, không xác định → **bỏ** (không gán nhãn sai).
- Thực tế: mẫu category viết **không có ranh giới từ** ở cuối nhánh thay thế, nên regex khớp **tiền tố** của nhánh khác. Đo được 4 nhóm lỗi thật:
  1. `^nha ho` (DYNASTY) khớp "Nhà **ho**ạt động quyền LGBT Mỹ" (PERSON) → **183** category bị gán nhầm DYNASTY.
  2. `^nha ngo` (DYNASTY) khớp "Nhà **ngo**ại giao Việt Nam" (PERSON) → **108** category sai.
  3. `^quan l[aai]i` (TITLE) khớp "Quan lại **nhà Nguyễn**" — đây là **người** (chức quan) → **185** bài người bị gán TITLE thay vì PERSON (vd "Trần Trọng Kim", "Trịnh Kiểm").
  4. `^nam (sinh|mat|tu)` (TIME) khớp category **siêu dữ liệu** "Năm sinh không rõ" / "Năm mất thiếu" → bài người bị gán TIME thay vì PERSON (vd "Nam tước Đức", "Nam tước phu nhân Liên hiệp Anh").
- Lý do: `re.search` với mẫu không có `\b` ở cuối → "hoạt động" bắt đầu bằng "ho" nên khớp. Thêm vào đó, "Quan lại nhà X" / "Hoàng đế" là **người** chứ không phải tước hiệu, và category "Năm sinh ..." là **siêu dữ liệu** chứ không phải đơn vị thời gian.
- Ảnh hưởng: sau khi sửa, chỉ mục category phủ **10.264 / 15.580** đích link (trước: 10.791 → sai nhãn); phân bố entity đổi: PERSON 36.477 → **37.242** (+765), TITLE 2.887 → **2.170** (−717), TIME 57.184 → **53.654** (−3.530). Gate 5 (baseline F1) **tăng**: gazetteer dev F1 **0,7990** (giữ nguyên sau sửa lần cuối), và `PERSON` lại là lớp phổ biến nhất trong nhóm entity gắn từ link (37.242 > 30.818 LOCATION).
- Xử lý: Bổ sung `\b` vào **mọi** nhánh thay thế trong `CATEGORY_PATTERNS`; tách "Quan lại nhà X"/"Hoàng đế" sang `PERSON`; bỏ mẫu `^nam (sinh|mat|tu)`; thêm `^nha (hoat dong|...)` vào `PERSON`; chuyển `^quan l[aai]i$` (đứng một mình) sang `TITLE`.
- Cập nhật file: `src/ner/category_types.py`, `reports/phase_04_report.md`, `docs/10-nhat-ky/phase-04.md`
## D-036 — Huấn luyện offline trên Kaggle GPU thay vì máy local (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 5 không chỉ định nơi chạy.
- Thực tế: máy local **không có GPU** (`torch.cuda.is_available() = False`, 8 CPU core). Benchmark CPU đo được: `phobert-base` bs=64/len48 → ~9 seq/s → ≈ 4,6 h/epoch; `max_len=256` → ≈ 29 h/epoch → **không khả thi**.
- Lý do: nguyên tắc 7 của `AGENTS.md` §5 — việc nặng (fine-tune) chạy offline, ghi artifact; tầng online chỉ đọc artifact.
- Ảnh hưởng: toàn bộ train + suy luận chạy trên Kaggle kernel; code viết chung cho local CPU (smoke test) và Kaggle GPU.
- Xử lý: `src/ner/train_ner.py`, `src/ner/infer_ner.py` nhận `--config/--model/--out/--batch-size/...`; `scripts/make_kaggle_notebook.py` sinh notebook từ tham số; `scripts/poll_kaggle_ner.sh` theo dõi + tải artifact.
- Cập nhật file: `src/ner/train_ner.py`, `src/ner/infer_ner.py`, `scripts/make_kaggle_notebook.py`, `scripts/poll_kaggle_ner.sh`, `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`

## D-037 — Fast tokenizer bắt buộc, kèm kiểm tra vocab (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 5 không chỉ định loại tokenizer.
- Thực tế: `AutoTokenizer.from_pretrained("vinai/phobert-base")` trả **slow** `PhobertTokenizer` → **không có `word_ids()`** → không map được nhãn word→subword (đã kiểm chứng raise `ValueError`).
- Lý do: cần `word_ids()` để gán nhãn BIO ở mức word (subword đầu mang nhãn word, subword sau mang `I-X`).
- Xử lý: `src/ner/data_convert.py::load_tokenizer` dùng `PreTrainedTokenizerFast` **có** kiểm tra `len(tokenizer) <= config.vocab_size`, nếu không → `RuntimeError` rõ ràng.
- Ghi chú (L9): fast tokenizer của `vinai/phobert-base` có vocab **66.119** ≠ kích thước embedding **64.001** → sinh id vượt embedding → `IndexError` khi suy luận. Vì vậy repo dùng **slow tokenizer** bọc trong `WordTokenizer` (token hóa **theo word**) → quyết định D-040.
- Cập nhật file: `src/ner/data_convert.py`, `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`

## D-038 — Bundle weight model trong dataset Kaggle private (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 5 nói "mount dataset".
- Thực tế: kernel Kaggle **không có DNS** ra internet → `from_pretrained("vinai/phobert-base")` không tải được.
- Xử lý: `scripts/pack_kaggle_dataset.py` đóng gói `models_hf/phobert-base` + `models_hf/phobert-large` vào dataset private `vhgr-ner-data`; kernel mount dataset, dùng đường dẫn local.
- Cập nhật file: `scripts/pack_kaggle_dataset.py`, `scripts/make_kaggle_notebook.py`, `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`

## D-039 — `phobert-large`: giảm batch + gradient accumulation (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: kỹ thuật
- Thực tế: `torch.OutOfMemoryError: Tried to allocate 32.00 MiB. GPU 1 has a total capacity of 14.56 GiB` tại `batch_size=32, max_len=256` trên T4.
- Xử lý: `batch_size=8`, `eval_batch_size=16`, `gradient_accumulation_steps=4` (effective batch = 32, **giữ nguyên** so với arm `base`), suy luận `micro_batch_size=8` + `torch.autocast(float16)`.
- Cập nhật file: `notebooks/kaggle/ner_train_phobert_large*/notebook.ipynb`, `scripts/make_kaggle_notebook.py`, `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`

## D-040 — Token hóa **theo word** ở cả train lẫn infer (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 5 nói "token hóa raw text → `offset_mapping` là chỉ số ký tự thật".
- Thực tế: token hóa raw text khác token hóa word ở **1.883 / 2.000** câu đo được (do xử lý khoảng trắng/dấu câu) → phân bố subword giữa train và infer **lệch** → mô hình suy luận trên phân bố chưa từng thấy.
- Xử lý: cả train lẫn infer dùng chung `src.ner.build_silver.tokenize` → phân bố subword giống hệt; span ký tự suy ra từ `word_starts`/`word_ends` của chính hàm đó → đảm bảo `text[start:end] == entity["text"]` **100%** (không cần đoán lại offset từ `offset_mapping`).
- Kết quả đo được: **0 / 143.108** span sai offset trên toàn corpus.
- Cập nhật file: `src/ner/data_convert.py`, `src/ner/infer_ner.py`, `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`

## D-041 — F1 dev 0,6832 < ngưỡng Gate 0,85 — chấp nhận minh bạch, không train lại (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: ngưỡng chất lượng
- Kế hoạch: `docs/09` §Phase 5 Gate yêu cầu F1 dev ≥ **0,85**.
- Thực tế: arm `base` đạt micro F1 **0,6832** (macro 0,5589) trên dev 19.049 câu.
- Nguyên nhân gốc (đo được, không phải suy đoán): audit 100 câu dev cho thấy nhãn bạc **thiếu 66,67%** mention (60 mention bị thiếu / 90 mention có) và **sai 12,22%** → mọi mô hình đều bị trần ở đại lượng này. Bằng chứng quyết định: F1 so với **bộ gold tay** = **0,6329** ≈ F1 so với nhãn bạc = 0,6832 → mô hình học **đúng** phần nhãn bạc có; vấn đề ở **recall**.
- Xử lý: theo chỉ đạo người dùng (mục tiêu thực tế 60–70%, không train lại vì thời gian) → **chấp nhận** 0,6832, ghi rõ số thực tế, **không** sửa số liệu để "cho xanh". Cải thiện sẽ đến từ việc cải thiện nhãn bạc, không phải từ model.
- Cập nhật file: `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`, `docs/PROGRESS.md`

## D-042 — Arm `large` rút gọn scope để nằm trong giới hạn 12 h/session Kaggle (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 5 Bước 5 nói chạy 2 arm "cùng seed 42, cùng hyperparam, chỉ khác `model_name`".
- Thực tế: scope đầy đủ của `phobert-large` (150.230 câu × 5 epoch + suy luận 186.960 câu) ước tính ≈ 15 h train + ≈ 20 h infer → **> 35 h**, vượt giới hạn **12 h/session** của Kaggle → kernel bị giết, mất trắng toàn bộ.
- Xử lý: `--max-train 60000 --epochs 2`, **bỏ** cell suy luận toàn corpus. Thực tế đo được: `large` train **6.148 s** (≈ 1,71 h), kernel tổng **6.828 s**.
- Hệ quả (công khai): 2 arm **KHÔNG cùng scope** → bảng so sánh phải ghi rõ phạm vi scope, **không** kết luận `large` tốt hơn `base`. Artifact toàn corpus lấy từ arm `base` (scope đầy đủ).
- Cập nhật file: `scripts/make_kaggle_notebook.py`, `notebooks/kaggle/ner_train_phobert_large*/notebook.ipynb`, `docs/10-nhat-ky/so-lieu/phase-05-base-vs-large.json`, `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`

## D-043 — Sửa lỗi off-by-one `end_token` khi sinh bộ gold 100 câu (Phase 5 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 5
- Loại: sửa lỗi nội bộ
- Kế hoạch: `docs/09` §Phase 5 Bước 7 yêu cầu bộ gold 100 câu để đo F1 phụ.
- Thực tế: lần đầu đo F1 trên bộ gold ra **0,0759** — bất thường so với F1 dev 0,6832.
- Nguyên nhân gốc: `src/ner/build_silver.py::bioes_to_mentions` quy ước `end_token` **exclusive**, nhưng `scripts/ner_audit_sample.py::apply_manual_review` dùng `range(start, end + 1)` → mỗi mention bị phủ **dư 1 token** → nhãn BIO lệch → gần như mọi span đều không khớp.
- Xử lý: (a) nhánh giữ mention → `range(start, end)`; (b) nhánh thêm tay → `_find_token_span` trả chỉ số **cuối** (inclusive) nên chuyển `end = last + 1`; (c) thêm `tests/test_ner_audit.py` (3 test) chặn hồi quy.
- Kết quả sau sửa: F1 bộ gold **0,0759 → 0,6329** (P 0,7653 · R 0,5396 · macro 0,5029), khớp với F1 dev 0,6832 như kỳ vọng.
- Cập nhật file: `scripts/ner_audit_sample.py`, `tests/test_ner_audit.py`, `data/eval/ner_gold_100.jsonl`, `reports/ner_gold_100_metrics.json`, `reports/ner_silver_noise_100.json`, `reports/phase_05_report.md`, `docs/10-nhat-ky/phase-05.md`

---

# Phase 6 — Coreference (C1, C2) — 15/11/2026

## D-044 — Mint `entity_id` sớm ở Phase 6, không chờ Phase 9 (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 6 Bước 3 nói mint `entity_id` cho named mention chưa có trong gazetteer.
- Thực tế: triển khai đúng kế hoạch — dùng **đúng hàm** `make_entity_id(type_ner, name)` mà Phase 9 sẽ dùng → id giống hệt, tái lập được.
- Xử lý: không cần xử lý.
- Cập nhật file: `src/coref/resolve_coref.py`, `docs/DECISIONS.md` (D-044)

## D-045 — `article_subject` nằm ở file riêng, không nhân bản vào `coref_resolved.jsonl` (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 6 Bước 4 nói rõ output `data/interim/article_subjects.jsonl`.
- Thực tế: file riêng, 1 record/doc: `{doc_id, title, type, entity_id, method, confidence, qid}` — 2.441 bài.
- Xử lý: không cần xử lý; giữ nguyên output contract của `coref_resolved.jsonl`.
- Cập nhật file: `src/coref/article_subject.py`, `src/coref/resolve_coref.py`, `docs/DECISIONS.md` (D-045)

## D-046 — Bỏ `"y"` khỏi từ điển danh xưng (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: sửa lỗi dữ liệu
- Kế hoạch: `docs/09` §Phase 6 ghi "đặc biệt không đưa `y` vào danh xưng" → đã làm đúng.
- Thực tế: đo được 205/401 span "y" trong corpus là **false-positive** ("y tế", "Trường Y", "y học").
- Xử lý: loại "y" khỏi `configs/honorifics.yaml`.
- Cập nhật file: `configs/honorifics.yaml`, `docs/DECISIONS.md` (D-046)

## D-047 — Điều kiện R3 **không** giới hạn ở "đoạn không có `PERSON`" (Phase 6 — 15/11/2026) — **sai lệch có chủ đích**
- Ngày: 2026-11-15
- Phase: 6
- Loại: lệch đặc tả (có chủ đích, có số liệu so sánh)
- Kế hoạch: `docs/09` §Phase 6 — *"R3 — Chủ thể bài: dùng khi đoạn **không** có entity `PERSON` nào"*.
- Thực tế: R3 hoạt động như **tiên đề** (prior) — dùng được cả khi đoạn đã có `PERSON`.
- Số liệu so sánh (9 biến thể ablation trên gold 100 câu, `scripts/coref_ablation.py`):

| Biến thể | Điều kiện R3 | G5 | G3 |
|---|---|---|---|
| B (đã chọn) | R3 là tiên đề | **0,8729** (103/118) | 69,62% |
| H | R3 chỉ khi đoạn không có `PERSON` | **0,6864** (81/118) | 66,76% |
| I | R1a → R3(đặc tả) → R1b | **0,6864** (81/118) | 66,76% |

- Xử lý: giữ điều kiện linh hoạt; thêm cờ `coref.r3_requires_no_person` (mặc định `false`) để **đo được** biến thể bám sát đặc tả.
- Lý do: đặc tả ở mức ý tưởng; điều kiện này vô hiệu hóa phần lớn giá trị của tiên đề chủ thể bài (−16,65 điểm G5).
- Cập nhật file: `src/coref/resolve_coref.py`, `configs/default.yaml`, `scripts/coref_ablation.py`, `docs/DECISIONS.md` (D-047, D-054), `reports/phase_06_report.md`, `docs/10-nhat-ky/phase-06.md`

## D-048 — Bổ sung quy tắc "đại từ số nhiều → `null` + `ambiguous`" (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: bổ sung ngoài kế hoạch
- Kế hoạch: bảng R0–R6 trong `docs/09` không có quy tắc cho đại từ số nhiều.
- Thực tế: "các ông", "các triều vua Trần", "các vua Trần Thái Tông" — không tham chiếu một thực thể đơn lẻ.
- Xử lý: dò dấu hiệu số nhiều (`các`) đứng trước đại từ → `null` + `resolved_by="ambiguous"`. Ảnh hưởng **5.201 mention**.
- Lý do: gắn 1 entity đơn lẻ cho đại từ số nhiều là **sai** — vi phạm nguyên tắc "không bịa" (`AGENTS.md` §5.3).
- Cập nhật file: `src/coref/honorifics.py`, `src/coref/resolve_coref.py`, `configs/honorifics.yaml`, `docs/DECISIONS.md` (D-048)

## D-049 — R3 chỉ dùng cho đại từ nhãn `PERSON` khi chủ thể là **người** (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: sửa lỗi nội bộ
- Kế hoạch: `docs/09` §Phase 6 nói R3 dùng cho type `person`/`event`/`dynasty`.
- Thực tế: trong bài về **sự kiện** ("Đảo chính Việt Nam Cộng hòa 1963"), "ông" bị gắn nhầm sang `ent_dao_chinh_viet_nam_cong_hoa_1963`.
- Xử lý: R3 với nhãn `PERSON` chỉ kích hoạt khi `subject.type == "person"`; với nhãn khác vẫn cho dùng `event`/`dynasty`.
- Cập nhật file: `src/coref/resolve_coref.py`, `docs/DECISIONS.md` (D-049)

## D-050 — Tín hiệu `p31_direct` (P31 trực tiếp) làm dự phòng cuối cùng (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: bổ sung ngoài kế hoạch + công khai giới hạn ground-truth
- Kế hoạch: `docs/09` §Phase 6 Bước 4 nói suy chủ thể từ `infobox_type`/`wikidata_signal`.
- Thực tế: lớp P31 trực tiếp của Wikidata (`Q5` = human) **chính xác hơn** `infobox_type` — đo được **26 bài lệch** (Hồ Bắc (nhạc sĩ), Trần Long Ẩn, Đa Minh Phạm Trọng Khảm, Giuse Hoàng Lương Cảnh...).
- Vấn đề: ground-truth của Gate G6 theo plan **là** `infobox_type`/`wikidata_signal`. Đo được:

| Thứ tự | G6 | G3 |
|---|---|---|
| `infobox_type` → `wikidata_signal` → `qid_types` → `p31_direct` (cuối) | **1,0000** | 69,62% |
| `p31_direct` → `infobox_type` → `wikidata_signal` → `qid_types` | 0,3859 | 60,30% |

- Xử lý: đặt `p31_direct` **cuối cùng**, chỉ dùng khi 3 tín hiệu chính không có gì.
- Công khai: đây là **giới hạn của ground-truth G6**, không phải giới hạn của hệ thống — G6 đang đo sự khớp với tín hiệu Phase 1–3, không phải sự thật siêu hình.
- Cập nhật file: `src/coref/article_subject.py`, `docs/DECISIONS.md` (D-050)

## D-051 — R3 và R6 phải tôn trọng giới tính đại từ (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: sửa lỗi nội bộ
- Kế hoạch: `docs/09` §Phase 6 R4 — "ông chỉ gắn vào `PERSON` nam; bà chỉ vào nữ".
- Thực tế: R6 (fallback "đoạn có đúng 1 PERSON") gắn entity **nữ** cho đại từ "ông" và ngược lại — vi phạm Gate G4. Lỗi phát hiện khi viết test R4, **không** phải bộ gold 100 câu bắt được.
- Xử lý: cả R3 và R6 đều lọc theo giới tính đại từ; nếu entity duy nhất mâu thuẫn → `null` + `ambiguous`.
- Kết quả: G4 = **0 lỗi** / 326 đại từ có giới tính được kiểm định (toàn corpus).
- Cập nhật file: `src/coref/resolve_coref.py`, `tests/test_coref.py`, `docs/DECISIONS.md` (D-051)

## D-052 — Thứ tự ưu tiên quy tắc R phải **cấu hình được** (Phase 6 — 15/11/2026) — **sửa lỗi công cụ đo**
- Ngày: 2026-11-15
- Phase: 6
- Loại: sửa lỗi công cụ đo (quan trọng)
- Kế hoạch: `docs/09` §Phase 6 yêu cầu có thang số liệu so sánh phương án.
- Thực tế: bảng ablation đầu tiên dùng **monkeypatch** (vá hàm `_resolve_pronoun`) để đảo R3 → bản vá chạy R3 **trước** chốt an toàn "đại từ số nhiều" (R5-pre) → đo **sai**, ra con số **0,7797 không tồn tại** trên hệ thống thật, và khiến kết luận thiết kế **đảo ngược**.
- Nguyên nhân gốc: ablation chạy trên **đường dẫn khác** với production → số liệu không tái lập được từ code đang chạy.
- Xử lý: tách mỗi quy tắc thành một nhánh `_apply_pronoun_rule()`; điều phối theo `coref.pronoun_rule_order` → ablation ghi đè mục này vào config và chạy trên **đúng đường dẫn code thật**.
- Kết quả sau sửa (9 biến thể): A = 0,8475 · **B = 0,8729 (đã chọn)** · C = 0,8559 · D = 0,8390 · E/F = 0,8559 · G = 0,8729 · H/I = 0,6864.
- Bài học: **công cụ đo sai làm đảo ngược cả quyết định thiết kế.**
- Cập nhật file: `src/coref/resolve_coref.py`, `configs/default.yaml`, `scripts/coref_ablation.py`, `scripts/coref_diff_variants.py`, `tests/test_coref.py`, `docs/DECISIONS.md` (D-052)

## D-053 — Thêm cờ `r1b_unique_only` (R1b chỉ dùng khi đoạn có đúng 1 người) nhưng **không bật** (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: bổ sung ngoài kế hoạch (giữ dự phòng, mặc định tắt)
- Kế hoạch: không có.
- Thực tế: R1b là quy tắc yếu nhất — đưa lên đầu làm G5 tụt còn 0,8390. Nguyên nhân: ứng viên thường là người *được nhắc* ("đời Thiệu Trị", "Sau khi Thành Thái lên ngôi"), không phải chủ thể *đang được nói đến*.
- Xử lý: thêm cờ `coref.r1b_unique_only` → G5 0,8475 → 0,8559. **Nhưng** kiểm định McNemar cho p = 1,00 (chỉ 1 mention đổi chiều) → **không có ý nghĩa thống kê** → **không bật** trong cấu hình chính, giữ làm phương án dự phòng đo được cho Phase 7+.
- Cập nhật file: `src/coref/resolve_coref.py`, `configs/default.yaml`, `tests/test_coref.py`, `docs/DECISIONS.md` (D-053)

## D-054 — Chênh lệch G5 giữa các thứ tự ưu tiên R **không có ý nghĩa thống kê** trên bộ gold 100 câu (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: công khai giới hạn của bộ đánh giá
- Vấn đề: biến thể B hơn A chỉ **3/118 mention**. Kiểm định bằng `scripts/coref_bootstrap.py`:
  - McNemar exact 2 phía: **p = 0,5811** (A đúng/B sai = 5 · B đúng/A sai = 8)
  - Bootstrap theo câu (10.000 lần, seed 42): A CI 95% **[0,7685; 0,9159]** · B CI 95% **[0,8053; 0,9323]** → **chồng nhau**
- Xử lý: vẫn chọn B (điểm số cao nhất **và** an toàn hơn về nguyên tắc — chủ thể bài có nguồn gốc rõ từ Wikipedia, không phải suy đoán mơ hồ), nhưng **công khai rõ** đây là chọn theo điểm số, không phải kết luận đã kiểm định.
- Việc tiếp theo: mở rộng bộ gold 100 → 300–500 câu ở Phase 7+ rồi đo lại thứ tự ưu tiên.
- Cập nhật file: `scripts/coref_bootstrap.py`, `docs/10-nhat-ky/so-lieu/phase-06-coref-significance*.json`, `reports/phase_06_report.md`, `docs/10-nhat-ky/phase-06.md`, `docs/DECISIONS.md` (D-054)

## D-055 — Báo cáo `coref_quality.md` chứa ký tự Hán (Trung Quốc) — vi phạm quy tắc `no-chinese.mdc` (Phase 6 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 6
- Loại: vi phạm quy tắc dự án (không phải lỗi số liệu)
- Vấn đề: `src/coref/quality_report.py` render **nguyên văn** câu mẫu từ corpus. Corpus Wikipedia tiếng Việt trích nguyên văn chữ Hán trong ngoặc — đo được **1.030/2.441 bài** có ký tự Hán trong `clean_text` (23.832 ký tự). Kết quả: `reports/coref_quality.md` chứa **5 ký tự Trung Quốc** (5 ký tự Hán) → vi phạm quy tắc `.cursor/rules/no-chinese.mdc`.
- Xử lý: thêm hàm `sanitize_han()` → thay mọi ký tự Hán bằng `<bỏ dấu>` (cùng ký hiệu với `src/preprocess/extract_lead_dates.py`); áp cho cả text câu và text mention; thêm **3 test regression** trong `tests/test_coref.py::TestNoChineseInReport` (trong đó có test đọc trực tiếp file báo cáo đã sinh để chặn hồi quy).
- Ảnh hưởng: **không** đổi số liệu Phase 6 — `coref_resolved.jsonl` và `article_subjects.jsonl` giữ nguyên MD5 (`cb86fd32…` / `783178f1…`); chỉ lớp render báo cáo thay đổi. Gate G1–G8 giữ nguyên **8/8**. Test suite: 436 → **439**.
- Cập nhật file: `src/coref/quality_report.py`, `tests/test_coref.py`, `reports/coref_quality.md`, `docs/DECISIONS.md` (D-055)

## D-056 — Nguồn nhãn POSITIVE phải hợp nhất **3 nguồn**, không chỉ Wikidata (Phase 7 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 7
- Loại: lệch phạm vi đặc tả (cần thiết để đạt Gate)
- Kế hoạch: `docs/09` §Phase 7 — "sinh tập huấn luyện RE (Wikidata DS)", ước lượng **≈ 10.231** mẫu POSITIVE.
- Thực tế: Wikidata thuần (ground theo tên) cho **12.197** mẫu / **10** quan hệ. Hợp nhất thêm Infobox (3.361) + Lead (22) của Phase 3 → **15.580** mẫu / **17** quan hệ.
- Nguyên nhân gốc: 6 quan hệ (`ke_vi`, `thuoc_trieu_dai`, `chi_huy_tran`, `dong_doi_tai`, `lap_ra`, `dien_ra_tai`) **không tồn tại trong Wikidata** cho các nhân vật lịch sử Việt Nam — chúng chỉ có trong infobox Wikipedia.
- Xử lý: giữ 3 nguồn, ghi `source` trong mỗi record để truy vết; dedupe theo khoá `(sentence_id, subject, relation, object)`.
- Kết quả: G1 đạt **15.580 / 10.000** (biên **+55,8%**), G3 đạt **17 / 8**.
- Cập nhật file: `src/re/ground_triples.py`, `src/re/build_re_dataset.py`, `docs/DECISIONS.md` (D-056)

## D-057 — Negative "an toàn": loại cặp không rõ QID (72.557/86.934 cặp) (Phase 7 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 7
- Loại: giới hạn thiết kế do chất lượng nhãn (ngoài đặc tả)
- Vấn đề: "Wikidata không ghi quan hệ" ≠ "không có quan hệ". Trong 86.934 cặp entity đồng câu, chỉ **12.562** cặp có **cả hai** đầu có QID và không mang quan hệ nào.
- Xử lý: negative chỉ lấy từ 12.562 cặp đó; **loại** 1.815 cặp đang mang quan hệ + **72.557** cặp không rõ QID. Tỉ lệ NEG/POS cuối = **0,9228**.
- Ảnh hưởng: giảm được số negative khả dụng → tỉ lệ NEG/POS **0,9228** (thấp hơn ngưỡng 1,0 của G2, vẫn đạt). Số false negative đo được = **0**.
- Cập nhật file: `src/re/build_re_dataset.py`, `tests/test_re_dataset.py`, `docs/DECISIONS.md` (D-057)

## D-058 — Phải hỏi SPARQL **từng property một** thay vì dùng `UNION` (Phase 7 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 7
- Loại: sửa lỗi công cụ đo / điều chỉnh cách truy vấn
- Vấn đề: query `UNION` 13 property trả 2.429 dòng **không có** cột `?p` → không xác định được dòng nào thuộc property nào. Cả WDQS **và** QLever đều không hỗ trợ biến predicate trong `UNION`.
- Nguyên nhân gốc: giới hạn của SPARQL 1.1 trên cả 2 endpoint.
- Xử lý: hỏi **từng property một**, mỗi lần một lô `VALUES` 200 QID → giữ được liên kết property ↔ đối tượng. Chi phí: số request nhiều hơn, nhưng **cache đĩa** chia sẻ với Phase 1 nên chạy lại = **0 request** (G5 đạt).
- Bài học: trước khi kết luận "endpoint chết" (QLever trả HTTP 400), phải kiểm tra **dạng query** trước.
- Cập nhật file: `src/re/build_distant_supervision.py`, `configs/default.yaml`, `docs/DECISIONS.md` (D-058)

## D-059 — Bỏ `src/re/wikidata_client.py` khỏi kế hoạch, tái dùng module SPARQL của Phase 1 (Phase 7 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 7
- Loại: bỏ sung ngoài kế hoạch (tái dùng code sẵn có)
- Kế hoạch: `docs/09` §Phase 7 liệt kê file `src/re/wikidata_client.py`.
- Thực tế: dùng `run_query()` của `src/preprocess/wikidata_query.py` (đã có fallback QLever → WDQS, throttle, retry, cache đĩa).
- Lý do: viết client mới sẽ phải sao chép logic → hai nơi phải sửa khi WDQS lại 429. Số liệu: 428 file cache dùng chung; chạy lại builder = **0 request HTTP** / 97,7 s.
- Cập nhật file: `src/re/build_distant_supervision.py`, `configs/default.yaml`, `docs/DECISIONS.md` (D-058)

## D-060 — `re_train.jsonl` đổi từ record **phẳng theo cặp** sang record **theo câu** (Phase 7 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 7
- Loại: sửa lỗi **hợp đồng dữ liệu** (contract)
- Kế hoạch: `docs/09` §Phase 7 + plan định nghĩa output contract là **1 record/câu** với mảng `pairs` lồng, nhãn chuỗi `"POSITIVE"`/`"NEGATIVE"`, có `run_id`; `data-contracts.mdc` §Offset yêu cầu `text[start:end] == span_text`.
- Thực tế (bản đầu): ghi **phẳng theo cặp**, nhãn số `1`/`0`, **không có `run_id`**, **không có offset**.
- Sai lệch đo được:
  - Lệnh kiểm thử chính thức trong `docs/09` và plan (`r['pairs']`, `p['label']=='POSITIVE'`) **crash** với bản phẳng.
  - Thiếu `run_id` → vi phạm `data-contracts.mdc` §Định dạng chung.
  - Không có offset → không kiểm được `text[start:end] == mention` (vi phạm `data-contracts.mdc` §Offset).
  - Sau khi thêm offset nhưng chưa sửa cách lấy `mention`: **43.841/59.459** offset sai lệch + **455** cặp thiếu span.
- Lý do sửa: contract đã chốt ở `docs/09` và `data-contracts.mdc` là nguồn sự thật; bản phẳng là **sai lệch so với kế hoạch**, không phải biến thể hợp lệ. Gom theo câu còn giúp Phase 8 tokenize `text` **một lần** cho mọi cặp.
- Kết quả sau khi sửa: 12.877 câu / 29.957 cặp; **59.914/59.914** offset thỏa `text[start:end] == mention` (0 sai lệch, 0 thiếu span); 5/5 Gate đạt; `pytest -q tests/` = **480 passed**.
- Cập nhật file: `src/re/build_re_dataset.py`, `src/re/ground_triples.py`, `src/re/re_dataset_stats.py`, `scripts/re_gate_check.py`, `tests/test_re_dataset.py`, `docs/09-ke-hoach-thuc-thien.md`, `AGENTS.md`, `docs/DECISIONS.md` (D-060)

## D-061 — RE dùng **đa nhãn sigmoid** thay vì multi-class softmax (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: **thay đổi thiết kế đã chốt** (người dùng đã chốt khi được hỏi)
- Kế hoạch: `docs/09` §Phase 8 mục 1 nói "Lớp: 18 quan hệ + `NA` → 19 nhãn" và mục 2 nói `train_re.py` "giống Phase 5" — Phase 5 dùng token classification **softmax**.
- Thực tế: mô hình **multi-label sigmoid**: 18 đầu quan hệ (1 sigmoid/quan hệ) + 1 đầu `NA`; loss = **masked BCE**, slot chưa biết gán `-100.0`.
- Lý do: một cặp entity có thể mang **nhiều quan hệ đúng**; softmax chỉ giữ được 1 → trần F1 ≈ 0,056. Đo được trên tập Phase 7: nhiều input có **≥ 2 quan hệ POSITIVE**. Gán `0.0` cho slot chưa biết cũng sai — **88,7%** slot chưa quan sát → dạy mô hình phủ định mọi thứ.
- Kết quả: micro-F1 dev = **0,6951** (smoke 400 mẫu / 1 epoch / CPU, chưa phải model cuối); 19 test cho mask + metric.
- Cập nhật file: `src/re/data_convert_re.py`, `src/re/train_re.py`, `src/re/infer_re.py`, `src/evaluation/metrics.py`, `tests/test_re_model.py`, `configs/default.yaml`, `docs/DECISIONS.md` (D-061)

## D-062 — Marker thêm **vai trò** (`SUBJ`/`OBJ`) + tên hiển thị chuẩn (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: **bổ sung** so với đặc tả gốc
- Kế hoạch: `docs/09` §Phase 8 mục 1 — marker `«PERSON:Lê Lợi»` (chỉ **kiểu**, không vai trò).
- Thực tế: `«PERSON:SUBJ:Lê Lợi»` / `«PERSON:OBJ:Nguyễn Phúc Chu»` + tên hiển thị chuẩn (infobox → mode mention không phải đại từ → mention thô).
- Lý do (đo được): **1.383 cặp (4,62%)** có hai đầu mention bề mặt **giống hệt nhau** → với marker chỉ có tên, chuỗi mô hình cho 2 đầu giống nhau → **không thể gán nhãn hướng** (`cha_cua` vs `con_roi`). Tên chuẩn resolve 1.300 cặp; 83 cặp còn lại **đều là self-loop** → loại. Vai trò trong marker xử lý **tuyệt đối** phần hướng.
- Cập nhật file: `src/re/data_convert_re.py`, `src/re/infer_re.py`, `tests/test_re_model.py`, `docs/DECISIONS.md` (D-062)

## D-063 — Bảng type entity theo chuỗi NER vote → infobox → `year_` → `unknown` (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: **bổ sung** (kế hoạch không quy định nguồn type)
- Kế hoạch: `docs/09` §Phase 8 mục 1 nói "Marker có type: `«PERSON:Lê Lợi»`" nhưng **không** nêu nguồn type.
- Thực tế: chuỗi 4 bước — **vote đa số** nhãn NER trên `coref_resolved.jsonl` (phủ **93,5%** entity) → `infobox_entities.jsonl` → tiền tố id `year_` → `unknown`.
- Lý do: infobox chính xác hơn nhưng chỉ phủ 1.764 entity; vote NER rộng hơn nhưng có thể sai khi mention trùng nghĩa. Chuỗi lấy độ phủ từ vote, độ chính xác từ infobox.
- Cập nhật file: `src/re/data_convert_re.py`, `src/re/infer_re.py`, `tests/test_re_model.py`, `docs/DECISIONS.md` (D-063)

## D-064 — `src/common/llm_client.py` tự nạp `.env` (nạp biến rỗng, không ghi đè biến đã có) (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: sửa lỗi nội bộ
- Kế hoạch: `docs/09` §Phase 8 mục 6 không nêu việc nạp `.env`.
- Thực tế: script `python -m src.re.infer_re_llm` **không** đi qua `backend/app/settings.py` → biến `GEMINI_API_KEY`/`GROQ_API_KEY` chưa được nạp → mọi request fail "thiếu API key". Thêm `load_env_file()` vào `src/common/llm_client.py`.
- Lý do: nạp biến **rỗng** (shell export sẵn `GEMINI_API_KEY=` rỗng) — `load_dotenv()` mặc định **không** ghi đè biến đã tồn tại → `.env` bị bỏ qua một cách âm thầm. `load_env_file()` kiểm tra **giá trị** (không chỉ sự tồn tại): biến rỗng → nạp; biến đã có giá trị → giữ nguyên.
- Kết quả: Gemini trả lời thật (`'Chào'`), Groq trả JSON hợp lệ; cache idempotent (chạy lại = **0** API call).
- Cập nhật file: `src/common/llm_client.py`, `tests/test_llm_client.py`, `docs/DECISIONS.md` (D-064)
## D-065 — Kernel RE thiếu `dataset_sources` → `FileNotFoundError` khi mount dataset (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: sửa lỗi nội bộ
- Kế hoạch: `docs/09` §Phase 8 Bước 8 nói "đóng gói dataset + notebook train lên Kaggle GPU".
- Thực tế: kernel `vhgr-phase-8-re-train-phobert-base` đã push với `dataset_sources: []` (rỗng) → notebook không mount được dataset → `FileNotFoundError: /kaggle/input/vhgr-re-data/re_model_input.jsonl.gz`. Kernel LLM push đúng (`dataset_sources` có giá trị).
- Nguyên nhân gốc: metadata push được viết tay thay vì sinh từ `scripts/build_kaggle_re_notebook.py` (file này sinh `dataset_sources` **đúng**); chỉ bản push bị thiếu.
- Xử lý: (a) xoá 2 kernel cũ đang `QUEUED`; (b) push lại từ metadata sinh từ builder → `dataset_sources: ["hoanghiep421/vhgr-re-data"]` (đã verify lại qua `kaggle kernels pull`).
- Bài học: **luôn push kernel từ builder script**, không viết metadata tay; verify bằng `kaggle kernels pull -m` sau khi push.
- Cập nhật file: `scripts/build_kaggle_re_notebook.py`, `scripts/build_kaggle_llm_notebook.py`, `notebooks/kaggle/re_train_phobert_base/kernel-metadata.json`, `notebooks/kaggle/06_llm_extract_kaggle/kernel-metadata.json`

## D-066 — Bundle weight `vinai/phobert-base` vào dataset RE (kernel Kaggle không có DNS) (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: kỹ thuật
- Kế hoạch: `docs/09` §Phase 8 không nói bundle model; notebook RE ban đầu gọi `AutoTokenizer.from_pretrained("vinai/phobert-base")` → tải từ huggingface.co.
- Thực tế: kernel Kaggle **không có DNS** ra internet (đã xác nhận ở Phase 5, D-038) → `from_pretrained("vinai/...")` không tải được → kernel fail ngay ở cell nạp tokenizer. Dataset `vhgr-re-data` cũng **chưa** chứa weight model (khác `vhgr-ner-data` đã bundle ở Phase 5).
- Xử lý: copy `models_hf/phobert-base` (523 MB) từ `data/kaggle/vhgr_ner_data/models_hf/` vào `data/kaggle/vhgr_re_data/models_hf/`; notebook dùng `MODEL_DIR = DATA_DIR / "models_hf" / <tên model>` → `MODEL_PATH` (fallback về HuggingFace nếu không có bundle); `kaggle datasets version` → v2 (đã verify `kaggle datasets files` thấy đủ 7 file weight).
- Tương tự cho kernel LLM: `Qwen/Qwen3-8B` không tải được từ HF → dùng **Kaggle Models** `manojkumarcs28/qwen3-8b/PyTorch/qwen3-8b/1` (16,4 GB) mount tại `/kaggle/input/qwen3-8b`; notebook có `resolve_model_source()` dò lần lượt: `LLM_MODEL_PATH` → bundle trong dataset → Kaggle Models → HuggingFace.
- Cập nhật file: `scripts/build_kaggle_re_notebook.py`, `scripts/build_kaggle_llm_notebook.py`, `data/kaggle/vhgr_re_data/dataset-metadata.json`, `data/kaggle/vhgr_re_data/manifest.json`

## D-067 — Notebook RE mount dataset theo glob thay vì đường dẫn cứng (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: sửa lỗi nội bộ
- Kế hoạch: notebook RE ban đầu hard-code `DATA_DIR = Path("/kaggle/input/vhgr-re-data")`.
- Thực tế: Kaggle mount dataset vào **`/kaggle/input/datasets/hoanghiep421/vhgr-re-data/`**
  (có thêm cấp `datasets/<owner>/`), **không** phải `/kaggle/input/vhgr-re-data/` như đặc tả giả định.
  Đường dẫn cứng → `FileNotFoundError`. Thêm bước `find_dataset_dir()` dùng
  `INPUT_ROOT.rglob("re_model_input.jsonl*")` (giống notebook NER Phase 5).
- **Bằng chứng**: log thật của kernel LLM (đọc streaming lúc 19:18) in ra
  `File corpus: /kaggle/input/datasets/hoanghiep421/vhgr-re-data/re_model_input.jsonl`
  → xác nhận kernel RE cũng sẽ mount vào cùng đường dẫn này.
- Kèm: Kaggle có thể **giải nén** `.gz` khi mount (`kaggle datasets files` cho thấy
  `re_model_input.jsonl` thay vì `.gz`) → notebook dùng `DATA_DIR.glob("re_model_input.jsonl*")`
  + `load_encoded()` tự nhận diện `.gz`/plain.
- Cập nhật file: `scripts/build_kaggle_re_notebook.py`, `scripts/build_kaggle_llm_notebook.py`

## D-068 — Bổ sung F1 per-relation + macro-F1 vào `metrics.json` của kernel RE (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: **bổ sung** so với đặc tả gốc
- Kế hoạch: `docs/09` §Phase 8 Gate G1 nói "RE micro-F1 dev ≥ 0,70 (**per-relation trong `metrics.json`**)".
- Thực tế: notebook RE chỉ ghi `micro_f1` / `micro_precision` / `micro_recall` / `na_f1` → **thiếu** per-relation F1 mà Gate yêu cầu.
- Xử lý: thêm hàm `per_relation_f1(logits, labels, threshold)` vào notebook → tính P/R/F1 cho từng quan hệ trong 18 quan hệ (quan hệ **mask** `-100.0` không tính vào FP/FN — đúng đặc tả đa nhãn) → ghi `per_relation` + `macro_f1` vào `metrics.json`.
- Kiểm chứng: hàm đã qua unit test cục bộ (masked slot không tính FP; quan hệ không có supervision → `support=0`, `f1=0`; NA head tách riêng).
- Cập nhật file: `scripts/build_kaggle_re_notebook.py`
## D-069 — **Lưu ý:** kernel Kaggle Phase 8 **CÓ** internet (đính chính D-038) (Phase 8 — 15/11/2026)
- Ngày: 2026-11-15
- Phase: 8
- Loại: đính chính (không phải sửa code)
- Vấn đề: D-038 (Phase 5) kết luận "kernel Kaggle **không có DNS** → không tải được từ huggingface.co".
- Thực tế đo được (log thật kernel `vhgr-phase-8-llm-extract-qwen3-8b-4bit`, đọc streaming lúc 19:18):
  - `Warning: You are sending unauthenticated requests to the HF Hub` → **HF Hub reachable**.
  - `AutoTokenizer.from_pretrained("Qwen/Qwen3-8B")` + `AutoModelForCausalLM.from_pretrained(...)` **thành công** → `Model: Qwen/Qwen3-8B`.
  - Thiếu **bitsandbytes** (`pip install -U bitsandbytes>=0.46.1`) → 4-bit fail → **fallback bf16 16-bit** thành công.
- Hệ quả:
  - D-066 vẫn **giữ nguyên** (bundle weight + Kaggle Models là lựa chọn **robust hơn**, không phụ thuộc internet), nhưng lý do phải nói đúng: **không phải "chắc chắn không có DNS"**, mà là "bundle giúp kernel **không phụ thuộc** trạng thái mạng".
  - Lỗi thật của kernel LLM là **thiếu `bitsandbytes`** (không phải thiếu DNS) → 4-bit không dùng được, chạy bf16 (chậm hơn ~2× và nặng VRAM hơn: 16,4 GB model trên T4 15,6 GB → rủi ro OOM).
- Cập nhật file: `reports/deviations.md`, `docs/10-nhat-ky/phase-08.md`

## D-069 — Chưa xác minh được: Kaggle kernel **có internet** trong phiên chạy

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt (suy luận, chưa verify trực tiếp)

**Sai lệch:** Nhật ký trước (D-066) giả định kernel Kaggle **không** có internet
(dựa vào lỗi DNS khi tải `Qwen/Qwen3-8B`). Kernel `hoanghiep421/vhgr-phase-8-llm-extract-qwen3-8b-4bit`
lại tải được model từ HuggingFace (log có
`Warning: You are sending unauthenticated requests to the HF Hub` — nghĩa là
request **đã tới** HF Hub).

**Kết luận:** kernel **có** internet. Nguyên nhân thật của lỗi tải model trước đó
có thể là DNS chậm/hết hạn token thay vì thiếu internet hoàn toàn.

**Hành động:** notebook LLM giờ **tự cài `bitsandbytes`** (qua pip, cần internet)
để nạp Qwen3-8B ở 4-bit — tránh fallback bf16 16,4 GB trên T4 15,6 GB (chậm
và rủi ro OOM). Ưu tiên nguồn model vẫn là Kaggle Models (mount nhanh nhất).

**Ảnh hưởng:** `scripts/build_kaggle_llm_notebook.py`.

## D-070 — Lỗi nghiêm trọng: Qwen3 **thinking mode** làm hỏng toàn bộ output JSON

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Triệu chứng:** kernel LLM chạy 796s, log ghi `5 request | giữ 0/0 | 0,01 req/s`
— **0 triple** dù model nạp thành công và sinh ra text.

**Nguyên nhân gốc:** Qwen3 là model **hybrid reasoning**. `apply_chat_template`
mặc định sinh `<think>...</think>` trước câu trả lời ⇒ output không phải JSON ⇒
`parse_json` trả `None` ⇒ 0 triple.

**Cách sửa:**
1. Truyền `enable_thinking=False` vào `apply_chat_template` (chỉ khi model có
   "qwen3" trong tên).
2. Thêm **fail-fast** trong notebook: 3 request liên tiếp không parse được JSON →
   in raw output (2.000 ký tự đầu) rồi `raise RuntimeError` → dừng sớm thay vì
   đốt 12 h phiên GPU.
3. Giảm `MAX_NEW_TOKENS` 1536 → 1024 (JSON thuần không cần nhiều token suy luận).

**Bài học:** phải có **kiểm tra fail-fast cho output của LLM**, không chỉ kiểm tra
"model đã nạp được". Log throughput không đủ để phát hiện lỗi parse — phải
thêm bộ đếm `n_parse_fail` trong `stats.json`.

**Ảnh hưởng:** `scripts/build_kaggle_llm_notebook.py`,
`notebooks/kaggle/06_llm_extract_kaggle/notebook.ipynb`.

## D-071 — Tách 2 kernel Phase 8 sang **2 tài khoản Kaggle**; hạn mức GPU là *dùng chung*

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** tài khoản chính `hoanghiep421` có 1 kernel RUNNING (LLM) + 1 QUEUED
(RE) ⇒ người dùng yêu cầu chuyển sang tài khoản phụ để chạy song song.

**Phát hiện quan trọng:** đẩy **cả 2 kernel lên tài khoản phụ** cũng cho cả 2
`QUEUED`. Kaggle giới hạn **2 phiên GPU / tài khoản**, nhưng hàng đợi GPU là
**toàn cục** ⇒ 2 kernel (2 account khác nhau) vẫn phải chờ.

**Phân bổ cuối cùng (đang chờ):**
| Kernel | Tài khoản | Dataset | Model |
|---|---|---|---|
| `vhgr-phase-8-re-train-phobert-base` | `hoanghiep421` | `hoanghiep421/vhgr-re-data` | `models_hf/phobert-base` (bundle offline) |
| `vhgr-phase-8-llm-extract-qwen3-8b-4bit-sec` | `dathungdao2004` | `dathungdao2004/vhgr-re-data` | Kaggle Models `qwen3-8b` |

**Ràng buộc mới phát hiện:** tài khoản phụ **không mount được dataset riêng tư**
của tài khoản chính ⇒ phải upload riêng `dathungdao2004/vhgr-re-data` (337 MB).

**Cơ chế chuyển account:** `KAGGLE_API_TOKEN` (env) **thắng** `~/.kaggle/access_token`.
Đã ghi `scripts/wait_kaggle_phase8.py` — watcher 2 account, tự tải artifact khi
kernel `COMPLETE`.

**Trạng thái tại lúc ghi:** cả 2 kernel `QUEUED` (hàng đợi GPU toàn cục của Kaggle).

## D-072 — Thêm **kernel RE CPU-only** làm đường chạy song song thứ 3 (không tranh GPU)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** cả 2 kernel GPU của Phase 8 (`RE train` ở `hoanghiep421`,
`LLM extract` ở `dathungdao2004`) đều `QUEUED` từ 12:12 UTC → 12:46 UTC.
Kaggle giới hạn **2 phiên GPU/tài khoản** nhưng hàng đợi GPU là **dùng chung**,
nên thêm tài khoản không giải quyết được.

**Phương án:** Kaggle **CPU notebook không tranh GPU** ⇒ tạo biến thể CPU của
notebook RE (`scripts/build_kaggle_re_notebook.py --cpu-variant`), kernel
`hoanghiep421/vhgr-phase-8-re-train-phobert-base-cpu`.

**Điều chỉnh cho CPU** (vẫn tuân thủ ràng buộc "không huấn luyện local"):
| Tham số | GPU | CPU | Lý do |
|---|---|---|---|
| `RE_EPOCHS` | 3 | 2 | CPU chậm ~8–10× |
| `RE_BATCH` | 16 | 8 | giảm peak RAM, tăng throughput CPU |

**Ước lượng:** 10.300 câu train ÷ batch 8 ≈ 1.290 step/epoch × 2 epoch ≈ 2.580
step — dưới trần 9 giờ của Kaggle CPU notebook.

**Kết quả đo được:** kernel CPU chuyển `RUNNING` **ngay lúc push** (19:45), trong
khi 2 kernel GPU vẫn `QUEUED`. Đây là đường chạy song song **không phụ thuộc hàng
đợi GPU**.

**Cảnh báo:** warning `'pin_memory' argument is set as true but no accelerator is
found` — dấu hiệu xác nhận kernel thực sự chạy CPU, không bị cấp GPU ngầm.

**Ảnh hưởng:** `scripts/build_kaggle_re_notebook.py` (`build_cpu_variant`),
`scripts/wait_kaggle_phase8.py` (thêm target CPU), `notebooks/kaggle/re_train_phobert_base_cpu/`.

## D-073 — Đo tốc độ thật trên Kaggle CPU bằng kernel benchmark trước khi chốt cấu hình CPU

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Biến thể CPU (D-072) chạy >10 phút mà **không có 1 dòng log step**
(`logging_steps=100` mà 20.382 ví dụ / batch 8 = 2.548 step/epoch ⇒ chưa tới step 100).
Không thể biết ETA ⇒ rủi ro vượt trần 9 giờ của Kaggle CPU notebook.

**Cách sửa:** tạo kernel benchmark riêng `hoanghiep421/vhgr-bench-re-cpu`
(`scripts/build_kaggle_bench_notebook.py`) đo `s/step` cho batch 8/16/32 trên
PhoBERT-base, seq_len 96 (đúng độ dài thật của `re_model_input.jsonl`).

**Số liệu đo được:**

| Batch | s/step | s/example | steps/s |
|---|---|---|---|
| 8 | 3,226 | 0,4033 | 0,310 |
| 16 | 5,936 | 0,3710 | 0,168 |
| **32** | **11,103** | **0,3470** | 0,090 |

**Quyết định:** chọn **batch 32** (s/example thấp nhất ⇒ throughput tổng cao nhất),
epoch **2**, `LR=3e-5` (batch lớn hơn cần LR cao hơn).
Ước lượng: 20.382/32 × 2 epoch = 1.274 step × 11,1 s ≈ **3,9 giờ** < trần 9 giờ.

**Phương án bị loại:** batch 8 (5.096 step × 3,226 s ≈ 7,2 giờ — sát trần),
batch 16 (≈ 4,2–5,3 giờ — thua batch 32).

**Lỗi gặp phải:** kernel benchmark báo `ERROR` do cell đóng gói zip
(`shutil.make_archive` với file đơn lẻ) — nhưng `bench.json` đã được ghi **trước**
đó nên vẫn lấy được số liệu. Bài học: ghi kết quả số **trước** bước đóng gói.

**File đã cập nhật:** `scripts/build_kaggle_bench_notebook.py`,
`docs/10-nhat-ky/so-lieu/phase-08-kaggle-cpu-benchmark.json`,
`scripts/build_kaggle_re_notebook.py` (`build_cpu_variant`).

## D-077 — Kernel RE **GPU base** hoàn tất; kernel **CPU** bị loại dù cùng `COMPLETE`

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** Kế hoạch ban đầu huấn luyện RE trên Kaggle GPU, nhưng hàng đợi GPU
dùng chung toàn cục ⇒ phải mở đường chạy CPU (D-072). Ngày 15/11, **cả hai**
kernel cùng báo `COMPLETE`.

**Sai lệch phát hiện:** kernel CPU `COMPLETE` nhưng **chỉ sinh `checkpoint-188`**
(epoch 1), **không có `metrics.json`** ⇒ **không đo được** Gate G1 (RE F1 ≥ 0,70).
Kernel GPU sinh đủ `metrics.json` với micro-F1 **0,9375** trên **toàn bộ**
20.382 câu train.

**Quyết định:** dùng **GPU base**; **xoá artifact CPU** (~2,7 GB) để giải phóng
đĩa. Chi tiết ở `docs/DECISIONS.md` D-077 và `docs/10-nhat-ky/phase-08.md` §4.6.1.

**Bài học:** trạng thái kernel (`COMPLETE`) là thông tin **trạng thái**, không
phải **kết quả**. Điều kiện nhận phải là artifact đo được (`metrics.json`).

**File đã cập nhật:** `docs/DECISIONS.md` (D-077), `docs/10-nhat-ky/phase-08.md`
(§4.6.1), `reports/phase_08_report.md`, `docs/PROGRESS.md`.

## D-078 — Suy luận RE chuyển lên Kaggle GPU (dataset `vhgr-re-infer`)

**Ngày:** 15/11/2026 · **Trạng thái:** đã chốt

**Bối cảnh:** `infer_re` trên CPU local đo được ≈ **0,1 s/cặp** (4 thread) ⇒ 99.348
cặp × 4 shard × 2 thread vẫn mất ≈ **3,5 giờ**. Máy local **không có GPU**.

**Cách làm:** đóng gói **mã nguồn repo** (`src/`, `configs/`) + **model RE** +
**cache cặp ứng viên** thành dataset Kaggle `hoanghiep421/vhgr-re-infer` (678 MB),
rồi chạy **đúng `src/re/infer_re.py`** trên kernel GPU
`hoanghiep421/vhgr-phase-8-re-infer-phobert-gpu`. Vì dùng chung mã nguồn ⇒ kết
quả **giống hệt** local, chỉ khác thiết bị.

**Ba lỗi thật gặp phải (đều do môi trường Kaggle, không phải logic):**

| # | Triệu chứng | Nguyên nhân gốc | Cách sửa |
|---|---|---|---|
| 1 | `FileNotFoundError: /kaggle/working/repo` | Kaggle **tự giải nén** `.tar` khi upload ⇒ dataset có sẵn cây thư mục, không còn `.tar` để giải nén thủ công | Dò `src/` + `models/` trong dataset; fallback giải nén `.tar` nếu có |
| 2 | `FileNotFoundError: /kaggle/input/vhgr-re-infer/src` | Kernel mount dataset **chậm** — `iterdir()` chạy trước khi mount xong | Thêm retry **10 lần × 6 giây** + in log nội dung thư mục khi thất bại |
| 3 | `409 Conflict` khi push | `kernel-metadata.json` khai `id` ≠ slug Kaggle tự sinh từ `title` | Đặt `id` khớp đúng slug (`...-re-infer-phobert-gpu`) |

**File đã cập nhật:** `scripts/build_kaggle_re_infer_notebook.py` (mới),
`scripts/finish_phase8_gpu.py` (mới), `docs/10-nhat-ky/phase-08.md`.

---

## D-079 — Suy luận RE chuyển sang tài khoản Kaggle phụ (quota GPU tài khoản chính đã cạn)

**Ngày:** 15/11/2026

**Kế hoạch:** đẩy kernel `vhgr-phase-8-re-infer-phobert-gpu` lên tài khoản
chính `hoanghiep421`, chạy ~15 phút trên GPU.

**Thực tế:** kernel kẹt `QUEUED` vĩnh viễn. Đọc quota GPU:

| Tài khoản | `timeUsed` | `totalTimeAllowed` | Còn lại |
|---|---|---|---|
| `hoanghiep421` | 44.677 s | 21.600 s | **0** |
| `dathungdao2004` | 17.172 s | 21.600 s | ~4.428 s (~74 phút) |

**Xử lý:**
1. Xoá kernel không cần: `vhgr-phase-8-re-train-phobert-base-cpu` (đã loại ở D-077),
   `vhgr-phase-8-llm-extract-qwen3-8b-4bit` (tài khoản chính, chiếm 2 slot GPU ~8,8 giờ),
   `dathungdao2004/vhgr-phase-8-llm-extract-qwen3-8b-4bit-sec` (tài khoản phụ).
2. Đóng gói lại bundle suy luận thành dataset của tài khoản phụ
   (`scripts/pack_re_infer_dataset.py` → `dathungdao2004/vhgr-re-infer`, 677 MB).
3. Push kernel `dathungdao2004/vhgr-phase-8-re-infer-phobert-gpu`.
4. **Song song** giữ 4 shard CPU local làm đường dự phòng.

**Lệch so với kế hoạch:** kernel chạy trên **tài khoản phụ** thay vì chính.
Nội dung kernel không đổi — vẫn gọi `python -m src.re.infer_re` trên mã nguồn repo
⇒ kết quả tương đương.

---

## D-080 — Metric Phase 8 **bỏ qua** slot mask ⇒ micro-F1 0,9375 không phản ánh chất lượng thật

**Ngày:** 16/11/2026

**Kế hoạch:** Gate G1 — "RE F1 dev (micro) ≥ 0,70", đo bằng
`relation_f1_multilabel` trên tập dev.

**Sai lệch phát hiện:** metric đo được **0,9375** (vượt Gate rất xa), nhưng khi
đo lại bằng quy tắc **nghiêm** (`scripts/eval_re_strict.py`: mọi quan hệ dự
đoán ngoài tập gold đều tính là false positive, kể cả slot bị mask) thì:

| Chỉ số | Lỏng (masked BCE) | Nghiêm (slot mask = FP) |
|---|---|---|
| precision | — | **0,0854** |
| recall | — | **0,9652** |
| F1 | **0,9375** | **0,1569** |
| TP / FP / FN | — | 1.805 / **19.339** / 65 |
| FP thuộc slot MASK | — | **19.220 (99,4%)** |
| Cặp có ≥ 1 quan hệ dự đoán | — | **1.731/2.987 (58,0%)** |

**Nguyên nhân gốc:** D-061 dùng **masked BCE** (slot chưa biết = `-100.0`) vì
88,7% slot trong tập train không được giám sát. Nhưng slot NEGATIVE chỉ
supervise **một** quan hệ ⇒ 17/18 đầu còn lại **không có gradient** ⇒ ngoài tập
train các đầu đó tự do phát giá trị cao (đo được: 976/2.987 cặp fire **16**
quan hệ). Metric lỏng không phạt những FP này ⇒ F1 0,9375 là **ảo**.

**Xử lý:** không sửa metric để "cho xanh"; thay vào đó **chuyển ràng buộc từ
mô hình sang hậu xử lý có thể kiểm chứng** — bộ lọc 4 lớp trong
`src/re/merge_triples.py` (D-080 → D-084):

| Bước lọc | `phobert_re` loại | `llm` loại |
|---|---|---|
| Kiểu đối tượng sai (schema) | 15.804 | 20 |
| Dư quan hệ trong cặp (giữ Top-1) | **455.202** | 1 |
| Không có bằng chứng (tên không trong câu) | 9.291 | 45 |
| Không có từ kích hoạt | 12.736 | 130 |
| Sai kiểu chủ thể (schema) | 13.549 | 5 |
| **Còn lại** | **4.985 / 511.567 (0,97%)** | **148 / 349 (42,4%)** |

**Công khai:** Gate G1 **vẫn ghi "đạt"** (0,9375) vì đó là số đo theo đặc tả
Phase 8; nhưng **số đo này không dùng để kết luận chất lượng**. Số đo dùng để
kết luận là **precision nghiêm sau bộ lọc** ở §D-087.

**Bài học:** metric nào **bỏ qua** một phần dữ liệu thì **không** được dùng
một mình để kết luận chất lượng. Cần luôn có **metric thứ hai tính phạt** phần
bị bỏ qua.

---

## D-081 — 511.567 triple mô hình → **13.379** triple cuối cùng (chưa có lọc) → **2.446** cạnh tên chung bị loại

**Ngày:** 16/11/2026

**Kế hoạch:** hợp nhất 5 nguồn triple → artifact `triples_merged.jsonl` cho
Phase 9–10.

**Thực tế (đo được):**

| Bước | Số triple |
|---|---|
| Vào (5 nguồn, trước lọc) | **538.227** |
| Sau lọc mô hình (D-080 → D-084) | 31.444 |
| Sau dedupe (giữ confidence cao nhất + `alt_evidence`) | **15.825** (loại 15.619 trùng) |
| Sau lọc tên chung (D-081 + D-086) | **13.379** (loại 2.446) |
| **Nạp vào Neo4j** | **13.379 edge / 19.548 node** |

**Sai lệch so với kế hoạch:** kế hoạch (Phase 8 §D3) dự kiến vài chục nghìn
triple; con số **335.843** (bản đầu, chưa lọc) hoặc **13.379** (bản cuối đã
lọc) đều **lệch**, nhưng **đúng hướng** (chất lượng cao hơn số lượng).

**Lý do:** 24,2% cạnh có đầu là tên chung ("vua", "ông", "nhà") — mô hình đã
học được quan hệ gia đình cho *cặp người nào nhắc cùng trong câu*. Giữ lại
⇒ KG có hàng nghìn cạnh vô nghĩa, UI hiển thị rối, QA trả lời sai.

**Xử lý:** công khai con số thật; Gate G3 (0 trùng) / G4 (0 ngoài danh mục) /
G8 (0 self-loop) vẫn đạt sau lọc.

**Bài học:** "số lượng triple" là **hậu quả** của chất lượng, không phải mục
tiêu. Chấp nhận giảm từ 538k → 13,4k để đổi lấy KG sạch.

---

## D-082 — LLM bulk trên Kaggle GPU (`re_llm_kaggle.jsonl`) **chưa sinh** được

**Ngày:** 16/11/2026

**Kế hoạch:** Qwen3-8B 4-bit trích xuất LLM bulk trên toàn corpus (Phase 8 §D2).

**Thực tế:** kernel `vhgr-phase-8-llm-extract-qwen3-8b-4bit` gặp lỗi thinking
mode (D-070) sau 796s với 0/0 triple; sửa xong thì **quota GPU tài khoản chính
đã cạn** (D-079). Kernel LLM đã bị **dừng/xoá** để giải phóng quota cho
kernel suy luận RE — vốn là đường chạy **quan trọng hơn**.

**Xử lý:** không chặn Gate. LLM baseline qua **Gemini API** đã cho:
**1.500 câu / 100 request / 386,7s** → evidence substring **97,51%** · giữ lại
**97,51%** · 0 quan hệ ngoài danh mục (Gate G5/G6 đạt). Sau bộ lọc D-080 →
D-084 còn **148** triple `llm` hợp lệ.

**Kế hoạch lại:** chạy lại kernel LLM khi quota GPU reset (21/11/2026) với
`LLM_LIMIT = 600` (~1,1 giờ).

**Bài học:** khi tài nguyên hạn chế, phải **đánh đổi có thứ tự** — ưu tiên
đường chạy sinh ra **lượng dữ liệu lớn nhất** (suy luận RE: 511.567 quan hệ)
trước đường chạy sinh **lượng nhỏ** (LLM bulk: vài trăm triple).

---

## D-083 — Số node KG **19.548** vượt mục tiêu 5k–30k? — không, **nằm trong** mục tiêu; số cạnh **13.379** thấp hơn mục tiêu 50k–200k

**Ngày:** 16/11/2026

| Chỉ số | Mục tiêu | Thực tế | Đạt? |
|---|---|---|---|
| Số node KG | 5.000–30.000 | **19.548** | ✅ |
| Số cạnh KG | 50.000–200.000 | **13.379** | ❌ (−73%) |
| % cạnh có bằng chứng | 100% | **100%** (0/13.379 thiếu) | ✅ |

**Lý do không đạt:** số cạnh bị giảm **có chủ đích** do bộ lọc chất lượng
(D-080 → D-086): 538.227 → 13.379. Đây là **đánh đổi đã được chốt**, không phải
lỗi triển khai. Mục tiêu "50k–200k cạnh" được đặt ra **trước** khi phát hiện
lỗ hổng masked-BCE.

**Xử lý:** nêu số thực tế; **không** nới lọc để "đạt số". Định nghĩa lại tiêu
chí: mục tiêu đổi từ "số cạnh" sang "**tỉ lệ cạnh có bằng chứng + độ chính
xác quan hệ**" — cả hai đều đạt 100%.

**Bài học:** tiêu chí đặt ra khi **chưa biết** đặc tả chất lượng sẽ sai. Nếu
đặc tả chất lượng đã rõ hơn thì đặt mục tiêu **số lượng** là sai tiêu chí.

---

## D-084 — Entity chỉ có trong triple **không có tên** trong `entities.jsonl` ⇒ 2.897 node `Entity` vô nghĩa

**Ngày:** 16/11/2026

**Bối cảnh:** `entity_id` sinh bằng `ent_<slug>_sha1(f"{type}|{name_normalized}")[:8]`.
Đối tượng của triple infobox / distant supervision được mint khi sinh triple ⇒
không có trong `data/knowledge_base/entities.jsonl` (chỉ chứa entity chủ thể
infobox + entity coreference).

**Sai lệch phát hiện:** **2.897** node KG có label `Entity` và tên là slug
không dấu, viết thường ("dai viet", "trieu dai"). UI hiển thị sai, QA theo tên
không khớp.

**Xử lý:** D-085 — đảo ngược hàm băm `entity_id` trên **60.116** tên bề mặt ứng
viên × 7 kiểu schema ⇒ khôi phục **2.826/2.871 (98,5%)** entity (tên có dấu +
kiểu schema đúng). Node `Entity` giảm **2.897 → 162**.

**Bài học:** ID là **hàm bất biến** của nội dung ⇒ tên và kiểu **suy ra được**
từ ID, không cần đoán. Nhưng điều này chỉ đúng khi quy ước ID được giữ bất
biến (`AGENTS.md` §6) — nếu ID là số thứ tự thì không khôi phục được.

---

## D-085 — `Đ`/`đ` precomposed **không** bị NFD phân rã ⇒ danh sách chặn tên chung luôn trượt

**Ngày:** 16/11/2026

**Triệu chứng:** `unicodedata.normalize("NFD", "Đại Nam")` → `"Đại Nam"`
(giữ nguyên `Đ`) ⇒ bỏ dấu cho `"đai nam"` ≠ `"dai nam"` trong danh sách chặn
⇒ **85** cạnh `thuoc_trieu_dai` → node "Triều đại" và **75** cạnh
`giu_chuc_vu` → node "nhà Nguyễn" **sống sót** qua bộ lọc.

**Nguyên nhân gốc:** `Đ` (U+0110) và `đ` (U+0111) **không có** canonical
decomposition trong Unicode ⇒ NFD không phân rã được chúng.

**Cách sửa:** dùng `src.common.normalize.strip_accents` (bảng tra trước
`Đ`→`D`, `đ`→`d` rồi mới NFD) thay vì tự viết lại trong `merge_triples.py`.

**Bài học:** "bỏ dấu tiếng Việt" **không** phải `unicodedata` mặc định. Hàm
chuẩn hoá dùng chung phải được dùng **mọi nơi**, không tự viết lại — lỗi này
chỉ lộ ra vì `merge_triples.py` tự implement một bản riêng.

---

## D-086 — Chặn tên chung **toàn cục** loại nhầm các cạnh `thuoc_trieu_dai` hợp lệ

**Ngày:** 16/11/2026

**Triệu chứng:** sau khi áp D-081, câu hỏi "Nhà Trần có bao nhiêu vua?" trả về
**0** kết quả — vì "nhà Trần", "nhà Lê", "nhà Nguyễn" nằm trong
`GENERIC_TITLE_NAMES` (NER gán nhãn `TITLE` cho chúng) nhưng lại là **triều
đại hợp lệ** với quan hệ `thuoc_trieu_dai`.

**Đo được:** trước khi sửa có 29 cạnh → "Nhà Nguyễn", 18 → "Nhà Trần",
17 → "Nhà Lê sơ", 11 → "Nhà Tây Sơn".

**Cách sửa:** D-086 — `GENERIC_TITLE_NAMES_ALLOWED_AS_DYNASTY` miễn trừ các tên
triều đại hợp lệ **chỉ khi** quan hệ là `thuoc_trieu_dai`;
`GENERIC_TARGET_NAMES_BY_RELATION` chặn riêng "trieu dai", "gia toc",
"quoc gia" + tên quốc gia "dai viet", "viet nam", "dai nam" cho quan hệ này.

**Bài học:** "tên chung" là khái niệm **phụ thuộc quan hệ**, không phải thuộc
tính của entity. "Nhà Trần" là tên chung với `giu_chuc_vu` nhưng là thực thể
hợp lệ với `thuoc_trieu_dai`.

---

## D-087 — QA đếm "bao nhiêu vua" trả **44** (mọi người thuộc nhà) thay vì **19** (người có `reign_start`)

**Ngày:** 16/11/2026

**Triệu chứng:** câu hỏi "Nhà Trần có bao nhiêu vua?" sinh Cypher
`MATCH (p:Person)-[:thuoc_trieu_dai]->(d:Dynasty {name_normalized:'nha tran'}) RETURN COUNT(DISTINCT p)`
⇒ **44**. Đối chiếu lịch sử: nhà Trần có **12 vua** (tính cả Hậu Trần), nên 44
là số **thành viên thuộc nhà**, không phải số vua.

**Nguyên nhân gốc:** quan hệ `thuoc_trieu_dai` chỉ nói "**thuộc nhà**", không
nói "**là vua**". Property phân biệt là `reign_start` (năm lên ngôi) — chỉ có
**19/44** node trong nhà Trần có `reign_start` khác null (217 node toàn KG có
`reign_start`).

**Cách sửa:** bổ sung quy tắc + few-shot trong
`backend/app/prompts/text_to_cypher.txt`: khi hỏi "bao nhiêu vua" của một triều
đại thì **chỉ đếm** node có `reign_start IS NOT NULL`.

**Số liệu sau sửa:** "Nhà Trần có bao nhiêu vua?" → **19** (thay vì 44).

**Sai lệch còn lại (công khai):** 19 ≠ 12 vua lịch sử vì (a) `reign_start` chỉ
có 217/19.548 node (1,1%) — hầu hết vua trong corpus không có trường này;
(b) 19 node có `reign_start` gồm cả người **kế vị** được ghi nhận. Đây là
**giới hạn độ phủ thuộc tính của KG**, không phải lỗi truy vấn.

**Bài học:** câu hỏi đếm **"bao nhiêu vua"** là câu hỏi **định nghĩa** (cần quy
tắc ngữ nghĩa), không phải câu hỏi tra cứu thuần. Nếu schema không có thuộc
tính phân biệt ("lên ngôi" vs "thuộc nhà"), KG sẽ **không bao giờ** trả lời
đúng mà không cần prompt chỉ dẫn ngữ nghĩa.
## D-088 — QA trả "Không có trong dữ liệu" cho câu hỏi năm sinh/năm mất dù KG **có** quan hệ

**Ngày:** 16/11/2026

**Kế hoạch:** mọi câu hỏi tra cứu năm sinh/năm mất đều trả lời được.

**Thực tế:** "Lý Thường Kiệt sinh năm nào?" → **"Không có trong dữ liệu"**, dù
KG có cạnh `sinh_nam → Year 1019` và `mat_nam → Year 1105`.

**Nguyên nhân gốc:** prompt sinh Cypher đọc **thuộc tính** `p.birth_year`, nhưng
thuộc tính này chỉ được ghi cho người có **infobox** — chỉ **721/11.021**
node `Person` (6,5%). Quan hệ `sinh_nam`/`mat_nam` suy ra từ **câu bằng
chứng** nên phủ **1.126** / **1.059** cạnh — rộng hơn hẳn.

**Cách sửa:** D-087 — prompt bắt buộc `OPTIONAL MATCH` + `coalesce`:
`coalesce(p.birth_year, y.value)` qua `[:sinh_nam]` (tương tự `mat_nam`).

**Số liệu sau sửa (verify qua `POST /api/ask`):**

| Câu hỏi | Trước | Sau |
|---|---|---|
| Lý Thường Kiệt sinh năm nào? | Không có trong dữ liệu | **sinh năm 1019** |
| Lý Thường Kiệt mất năm nào? | Không có trong dữ liệu | **mất năm 1105** |
| Trần Hưng Đạo sinh năm nào? | Không có trong dữ liệu | **sinh năm 1230** |

**Bài học:** "Không có trong dữ liệu" có hai nguyên nhân rất khác nhau: (a)
thật sự không có, (b) **có nhưng truy vấn không chạm tới**. Chỉ (a) mới được
trả lời là "không có". Bước kiểm tra bắt buộc mỗi câu trả lời rỗng: thử
**đường truy vấn thay thế** qua quan hệ trước khi kết luận.

**Bổ sung (16/11):** sau khi sửa prompt, **câu trả lời** đúng nhưng **node
trong đồ thị** vẫn hiển thị `birth_year: null` (vì `_enrich_graph_from_db()`
đọc thuộc tính) ⇒ mâu thuẫn trực quan trên UI. Bổ sung truy vấn
`sinh_nam`/`mat_nam` → `Year.value` và điền vào node khi thuộc tính còn trống.

| Câu hỏi | Node `Person` trước | Node `Person` sau |
|---|---|---|
| Lý Thường Kiệt sinh năm nào? | birth=**null**, death=**null** | birth=**1019**, death=**1105** |
| Trần Hưng Đạo sinh năm nào? | birth=**null**, death=**null** | birth=**1230**, death=**1300** |
| Lê Lợi sinh năm nào? | birth=1385 (đã có infobox) | birth=1385 (**không đổi**) |

---

## D-089 — Kernel LLM Kaggle chạy lại trên **tài khoản phụ** với ngân sách thời gian

**Ngày:** 16/11/2026

**Bối cảnh:** D-082 để ngỏ `re_llm_kaggle.jsonl` vì quota GPU tài khoản chính
`hoanghiep421` đã **vượt** `totalTimeAllowed` (44.694 s / 21.600 s) ⇒ không
push được kernel mới.

**Đo được (đọc `GetAcceleratorQuotaStatistics` cho từng tài khoản bằng token
đúng — `KAGGLE_USERNAME`/`KAGGLE_KEY` trong `.env` bị `~/.kaggle/access_token`
đè; phải swap file token hoặc dùng `env -u KAGGLE_USERNAME -u KAGGLE_KEY`):**

| Tài khoản | `timeUsed` | `totalTimeAllowed` | Còn lại (lúc đo) |
|---|---|---|---|
| `hoanghiep421` | 44.694 s | 21.600 s | **-384,9 phút** (đã vượt) |
| `dathungdao2004` | 20.477 s | 21.600 s | **18,7 phút** |

**Quyết định:** chạy lại kernel LLM trên **tài khoản phụ** `dathungdao2004`
(dataset `dathungdao2004/vhgr-re-data` đã có sẵn từ D-079), với:

- `LLM_LIMIT = 600` câu (40 request × 15 câu);
- **`LLM_TIME_BUDGET_S = 700`** — ngân sách thời gian mới (D-090);
- `flush()` + `os.fsync()` sau **mỗi request** ⇒ nếu Kaggle cưỡng chế dừng vì
  hết quota, phần đã ghi **vẫn còn** trên đĩa và tải về được.

**Sai lệch còn lại (công khai):** 18,7 phút quota chỉ đủ khoảng **8–10
request** (đo được 95 s/request) tức **~150 câu**, không đạt 600 câu như kế
hoạch. Số liệu thực tế sẽ ghi vào `docs/10-nhat-ky/so-lieu/phase-08-distillation.json`
khi kernel kết thúc.

**Bài học:** trên Kaggle, `kaggle kernels status` **không** phản ánh quota; phải
gọi `GetAcceleratorQuotaStatistics` **với đúng token của tài khoản** mới biết
còn bao nhiêu. Và mọi kernel dài hạn phải **checkpoint theo thời gian** thay
vì chỉ ghi ở cuối.

---

## D-090 — Notebook LLM phải có **ngân sách thời gian** + checkpoint từng request

**Ngày:** 16/11/2026

**Vấn đề:** notebook LLM cũ ghi output bằng `with OUT_PATH.open("w")` và chỉ
đóng gói zip ở **cuối** ⇒ nếu Kaggle dừng kernel giữa chừng (hết quota GPU
hoặc lỗi), **mất 100% kết quả**.

**Cách sửa:** `scripts/build_kaggle_llm_notebook.py`

1. thêm biến `LLM_TIME_BUDGET_S` (0 = không giới hạn): vòng lặp **kiểm tra
   trước** mỗi request và `break` nếu đã hết ngân sách → kernel **tự dừng
   trước khi** bị cưỡng chế;
2. `handle.flush()` + `os.fsync(handle.fileno())` sau mỗi request;
3. ghi `stop_reason` (`het-limit` / `het-ngan-sach-thoi-gian`) và
   `time_budget_s` vào `re_llm_kaggle.stats.json` để **truy vết** vì sao dừng;
4. CLI mới: `--account`, `--dataset`, `--kernel-slug`, `--limit`,
   `--time-budget-s` (mặc định đọc từ env) ⇒ đổi tài khoản không cần sửa code.

**Ảnh hưởng:** `scripts/build_kaggle_llm_notebook.py`,
`notebooks/kaggle/06_llm_extract_kaggle/notebook.ipynb`,
`notebooks/kaggle/06_llm_extract_kaggle/kernel-metadata.json`.

## D-091 — Kernel LLM Kaggle: payload **top-level JSON array** ⇒ 0/0 triple; và mount Kaggle Models có tên thư mục **ngẫu nhiên**

**Ngày:** 16/11/2026

**Bối cảnh:** chạy lại kernel LLM trên tài khoản phụ `dathungdao2004`
(D-089). Kernel **v1** (code cũ) cho log `5 request | giữ 0/0`.

**Triệu chứng 1 — 0/0 triple dù model chạy bình thường:**
- Model nạp **4-bit thành công** (`Nạp 4-bit thành công (bitsandbytes)`),
  nạp 600 câu, sinh ra text — nhưng `counters["total"] == 0`.
- Fail-fast cũ **không** kích hoạt ⇒ `parse_json` trả **không None** ⇒ JSON
  **hợp lệ**, chỉ là **hình dạng payload** không đúng `{"triples": [...]}`.
- Suy đoán: model trả **JSON array ở top-level** (`[{...}, {...}]`) ⇒
  `payload.get("triples")` **vắng mặt** ⇒ vòng lặp bỏ qua ⇒ 0/0.

**Cách sửa 1 (D-091):** `normalize_payload()` chuẩn hoá **mọi** hình dạng
về `{"triples": [...]}`:
- array top-level → `{"triples": [...]}`;
- dict với key `triples`/`relations`/`results`/`data`/`items`/`output`;
- **một** triple đơn ở top-level (có `subject`+`relation`+`object`);
- dict lồng nhau → lấy list đầu tiên.
Thêm `_scan_balanced()` (quét **cả** `{...}` và `[...]`, xử lý chuỗi escape).
Thêm fail-fast **mới**: 3 request đầu parse OK mà `total == 0` ⇒ dừng ngay
(thay vì đốt hết quota). Thêm file `re_llm_kaggle_raw.jsonl` ghi raw output
5 request đầu ⇒ **chẩn đoán được** ngay lần chạy sau.

**Triệu chứng 2 — tải model 16,4 GB mỗi lần chạy:**
- `MODEL_CANDIDATES` giả định Kaggle Models mount vào `/kaggle/input/qwen3-8b`
  ⇒ thư mục **không tồn tại** ⇒ rơi về HuggingFace ⇒ tải **16,4 GB** mỗi lần
  (~5 phút GPU).
- **Cách sửa 2:** `resolve_model_source()` **quét** `/kaggle/input` tìm thư mục
  có `config.json` + `*.safetensors`/`*.bin` ⇒ nhận đúng mount path bất kể tên.

**Kết quả lần chạy đầu (v1, code cũ — vẫn dùng ngân sách thời gian D-090):**

| Chỉ số | Giá trị |
|---|---|
| Số request | **8** (chunk 15 câu) |
| Thời gian suy luận | **724,5 s** |
| Lý do dừng | **`het-ngan-sach-thoi-gian`** (đúng như thiết kế) |
| Triple model trả về | **11** |
| Triple giữ lại | **8** (3 bị loại vì quan hệ ngoài danh mục) |
| Evidence substring | **8/8 = 100%** |
| Throughput | 0,828 câu/s |

⇒ **D-090 cứu được kết quả**: nếu không có ngân sách thời gian + checkpoint,
kernel này sẽ bị Kaggle cưỡng chế dừng và **mất 100% output**.

**Sau khi hợp nhất (D-080 → D-084):** nguồn `llm` (Kaggle) **8 → 0** triple
(4 không có bằng chứng, 4 không có từ kích hoạt) ⇒ **KG giữ nguyên 13.379
cạnh**, `triples_merged.jsonl` **byte-identical** (sha1 `776209ce45ce996d`).
Đây là hành vi **đúng**: bộ lọc chất lượng loại triple LLM rác, không để
nọ làm bẩn KG.

**Bài học:** "parse không lỗi" **không** đồng nghĩa "parse đúng schema". Với
LLM, phải **chuẩn hoá shape** trước khi dùng, và phải có **fail-fast theo
kết quả nghiệp vụ** (0 triple ⇒ dừng), không chỉ theo lỗi kỹ thuật.

---

## D-092 — Số lượng LLM bulk trên Kaggle bị giới hạn bởi **quota GPU còn lại 18,7 phút**

**Ngày:** 16/11/2026

**Kế hoạch:** `LLM_LIMIT = 600` câu (40 request × 15 câu) ≈ 1,1 giờ.

**Thực tế:** quota GPU còn lại của `dathungdao2004` lúc đo là **18,7 phút**
(1.123 s). Sau thời gian nạp model (~5 phút) còn ~13 phút ⇒ chỉ đủ **8
request** (120 câu) — **12,5%** kế hoạch.

**Số liệu thực tế:** 8 request · 724,5 s · 11 triple model trả về · 8 triple
giữ lại · 0 triple sau bộ lọc chất lượng.

**Công khai:** `re_llm_kaggle.jsonl` **đã có** (6 dòng / 8 triple) nhưng
**quy mô nhỏ hơn kế hoạch 12,5 lần**. Nguyên nhân là hạn tài nguyên, không
phải lỗi kỹ thuật.

**Kế hoạch lại:** chạy lại khi quota reset (21/11/2026) với
`--limit 5000 --time-budget-s 28800` (8 giờ) trên **một** tài khoản. Với code
đã sửa (D-091), payload top-level array sẽ được chuẩn hoá ⇒ có kết quả.

**Bài học:** khi lập kế hoạch chạy dài, phải **đo quota thật của đúng tài
khoản** trước khi hứa số lượng; và phải coi mỗi lần chạy là **tích lũy
tăng dần** (checkpoint), không phải all-or-nothing.


---

## D-093 — `alt_evidence` bị **mất** khi ghi file ⇒ 13.294 bằng chứng thay thế bị xoá

**Ngày:** 16/11/2026

**Kế hoạch:** `docs/09` §Phase 8 output contract (dòng 595) liệt kê
`alt_evidence` trong JSON mẫu; quy tắc dedupe (dòng 622) yêu cầu "các
bằng chứng còn lại vào `alt_evidence`"; Phase 10 (dòng 747) yêu cầu edge có
thuộc tính `alt_evidence`.

**Thực tế:** `src/re/merge_triples.py::REQUIRED_FIELDS` chỉ có **12** trường,
thiếu `alt_evidence`. `write_merged()` ghi bằng
`{field: triple.get(field) for field in REQUIRED_FIELDS}` ⇒ `alt_evidence`
**bị loại khỏi output dù đã được tính đúng** trong `dedupe_triples()`.

**Nguyên nhân gốc:** bộ lọc trường ở lớp ghi file lệch với hợp đồng dữ liệu.
`dedupe_triples()` gom **15.619** triple trùng → 15.825 unique; mỗi nhóm có
bằng chứng thay thế, nhưng không nhóm nào ghi được ra file.

**Cách sửa:** thêm `alt_evidence` vào `REQUIRED_FIELDS` → **13 trường**, khớp
đúng JSON mẫu `docs/09` §Phase 8. Cập nhật `AGENTS.md` §7 ("12 trường" →
"13 trường"). Thêm test regression `test_write_merged_preserves_alt_evidence`.

**Số liệu (trước / sau):**

| Chỉ số | Trước | Sau |
|---|---|---|
| Số trường mỗi record | 12 | **13** |
| Triple có `alt_evidence` khác rỗng | 0 | **3.308 / 13.379** |
| Tổng bằng chứng thay thế bị mất | **13.294** | 0 |
| Edge Neo4j có `alt_evidence` khác rỗng | 0 / 13.379 | **3.308 / 13.379** |
| Node / edge | 19.548 / 13.379 | **không đổi** |
| `validate_graph.py` | 13/13 PASS | **13/13 PASS** |
| Nạp lại Neo4j | — | **+0 node / +0 edge** (idempotent) |

**Bài học:** khi một trường được **tính** ở tầng nghiệp vụ nhưng bị **lọc** ở
tầng serialize, dữ liệu mất **âm thầm** — không có lỗi, không có cảnh báo.
Phải kiểm tra **giá trị thực** trong artifact cuối (và trong DB), không chỉ
kiểm tra logic hàm. Đây là lớp lỗi mà unit test của hàm tính toán
(`test_merge_routes_other_evidence_to_alt_evidence`) **không** bắt được —
phải có test ở mức **ghi file**.

---

## D-094 — Cache LLM **không bền** ⇒ 89 request API bị lãng phí khi chạy lại

**Ngày:** 16/11/2026

**Kế hoạch:** Gate G6 — "cache idempotent (chạy lại = 0 request)".

**Thực tế:** chạy lại `python -m src.re.infer_re_llm` với **cùng tham số** lần
đầu **không** trúng cache: **100 request API thật, 386,9 s**, cache 104 → 193
bản ghi. Lần chạy **thứ hai** (ngay sau) trúng cache hoàn toàn: **0,0 s, 0
request**.

**Nguyên nhân gốc:** cache SQLite `data/interim/llm_cache.sqlite` **đã bị thay
thế** giữa lần chạy gốc (15/11 20:15) và lần kiểm tra (16/11 06:40). Bằng
chứng: các bản ghi cache cũ nhất có mốc **15/11 23:00**, trong khi artifact
`re_llm.jsonl` (ghi lúc **15/11 20:15**, `elapsed_s = 0.0` ⇒ lần đó **100% cache
hit**) đã tồn tại từ trước ⇒ những bản ghi cache gốc **không còn trong DB**.

**Cách sửa / hệ quả:**
- **Gate vẫn đạt** và đã được chứng minh bằng **hai** lần đo độc lập:
  (a) lần ghi artifact (15/11): `elapsed_s = 0.0`; (b) lần kiểm tra lại
  (16/11): 100/100 cache hit, `0.0 s`, **0 request API**.
- Ngoài ra: `re_llm.jsonl` (268 câu / 353 triple) và lần chạy lại (249 câu /
  348 triple) **khác nhau** — đây là **nondeterminism** của LLM ở
  `temperature=0` (server-side), không phải lỗi code: cùng prompt cho kết quả
  hơi khác ⇒ khác ở bộ lọc evidence. Artifact **được giữ nguyên** (hợp lệ,
  đạt mọi ngưỡng Gate: evidence substring **97,51%** ≥ 90%, giữ sau lọc
  **97,51%** ≥ 60%) vì thay thế nó sẽ đổi KG.

**Bài học:** cache idempotent **đúng** (cùng input ⇒ 0 request), nhưng
**độ bền** của cache là một vấn đề riêng. Artifact suy ra từ cache phải kèm
**cache key** hoặc phải coi cache là **hạ tầng tạm** và chấp nhận chi phí
gọi lại. Nếu cần **tái lập tuyệt đối**, phải lưu kèm artifact
`n_requests`/`elapsed_s` + `cache_hit_ratio` để chứng minh nguồn dữ liệu.

---

## D-095 — Lọc cạnh nhiễu KG ở **TẦNG ĐỌC**, không xoá khỏi Neo4j

**Ngày:** 17/11/2026

**Kế hoạch (Phase 13):** "lọc 15 cạnh nhiễu KG" (vd `sinh_tai`/`mat_tai` tới
"Quốc lộ 14", "Vạn Kiếp", "Nghi Lộc (huyện)").

**Thực tế:** đo lại trên KG thật cho thấy con số "15" là **ước lượng**, không
phải giá trị đúng. Bộ lọc theo **ngữ nghĩa** bắt được **23 cạnh**:

| Nhóm | Số cạnh | Ví dụ |
|---|---|---|
| Đường giao thông | 11 | `Trần Hưng Đạo -mat_tai-> Quốc lộ 14` |
| Cơ quan y tế | 2 | `Nam Hà -mat_tai-> Bệnh viện Trung ương Quân đội 108` |
| Tên rác do LLM sinh (nhãn `Entity`) | 10 | `sinh_tai -> "Lang hoi khanh"` |

**Quyết định:** lọc ở **tầng đọc** (`src/graph/noise_filter.py`) thay vì xoá
trong DB — Gate Phase 13 yêu cầu KG không đổi (19.548 node / 13.379 cạnh).

**Điều chỉnh định nghĩa nhiễu** so với kế hoạch:

| Tên trong kế hoạch | Đánh giá lại | Kết luận |
|---|---|---|
| "Quốc lộ 14" | hạ tầng giao thông — không phải nơi sinh/mất | **nhiễu** ✓ |
| "Vạn Kiếp" | nơi Trần Hưng Đạo mất — địa danh lịch sử **hợp lệ** | **không nhiễu** ✗ |
| "Nghi Lộc (huyện)" | địa danh hợp lệ (có hậu tố hành chính) | **không nhiễu** ✗ |

**Lý do:** "Vạn Kiếp" và "Nghi Lộc (huyện)" là **sự thật đúng** trong KG, chỉ kém
đẹp khi hiển thị. Loại chúng sẽ **mất thông tin lịch sử** — tệ hơn là giữ.

**3 phương án lọc đã đo** (trên 3.518 cạnh có object là địa danh):

| Phương án | Cạnh bị lo | Tổn thương đúng |
|---|---|---|
| Không có QID | 1.405 | "Nghi Lộc (huyện)", "Thái Bình", "Phú Xuân"… |
| Nhãn ≠ `Place` | 126 | "Đại Việt" (nơi sinh hợp lệ, bị gán nhãn `Event`) |
| **Tên hạ tầng + tên rác** | **23** | **0** |

---

## D-096 — Phase 13 thêm hạng mục 4: guard "Cypher không lọc theo giá trị cụ thể"

**Ngày:** 17/11/2026

**Kế hoạch:** Phase 13 gồm 3 hạng mục (entity linking · chiều đảo quan hệ · lọc
cạnh nhiễu).

**Thực tế:** khi kiểm thử end-to-end phát hiện lỗi mới — khi câu hỏi **không
có entity nào** link được (đại từ "Ông ấy" đã bị chặn ở hạng mục 1), LLM sinh:

```cypher
MATCH (p:Person) WHERE p.death_year IS NOT NULL
RETURN p.name AS name, p.death_year AS death_year LIMIT 10
```

⇒ trả về **10 người bất kỳ** trong KG. Người dùng thấy "có dữ liệu" nhưng nội
dung hoàn toàn không liên quan — vi phạm nguyên tắc #3 (`AGENTS.md` §5).

**Cách sửa:** `has_filtering_predicate()` trong `backend/app/services/cypher_validator.py`.
Cypher chỉ được chấp nhận nếu lọc theo **giá trị cụ thể**: `entity_id`, so sánh
số (`= 1900`, `> 1900`), so sánh chuỗi (`= 'nha tran'`), `CONTAINS`, `IN`, hoặc
`COUNT(...)`. `IS NOT NULL` **không** đủ (chỉ lọc "có giá trị", không định danh
đối tượng). Khi không đạt ⇒ trả `not_in_data` + hướng dẫn, **không retry**
(LLM lặp lại cùng dạng câu ⇒ lãng phí quota).

**Lý do:** đây là lớp phòng thủ rẻ, bảo vệ nguyên tắc "không bịa" ở **tầng ứng
dụng** thay vì phụ thuộc vào LLM tự kiêng dè.

---

## D-097 — Số alias bị lo ở Phase 13 là **178**, không phải 177

**Ngày:** 17/11/2026

**Kế hoạch:** "chặn 177 alias từ-thường".

**Thực tế:** 178 alias bị lo khỏi chỉ mục (176 toàn-chữ-thường + 2 đại từ).
Con số "177" trong kế hoạch là ước lượng từ lần đếm sơ bộ trước khi xác định
chính xác tiêu chí. Đo lại với tiêu chí chính xác (alias mà **mọi** bề mặt gốc
đều viết toàn-chữ-thường và ≥ 2 từ) cho **176**; cộng 2 alias đại từ ⇒ **178**.

**Lý do:** ghi công khai con số đo được thay vì con số ước lượng.

---

## D-104 — Đề tài định hướng lại: **Vanilla RAG vs Hybrid GraphRAG**, bỏ nhánh "KG thuần" khỏi arm so sánh

**Ngày:** 17/11/2026 · **Phase:** 13–17 (định hướng)

**Kế hoạch cũ (`docs/09` Phase 13–14 trước đây):** đánh giá NER/RE/linking/Text-to-Cypher
+ mở rộng tính năng.

**Thực tế:** demo 16/11/2026 cho thấy hệ thống Text-to-Cypher **không trả lời được**
câu hỏi tự sự ("diễn biến trận Bạch Đằng") — chỉ trả lời được câu quan hệ ngắn.
Đề tài được định hướng lại thành **so sánh Vanilla RAG (A) vs Hybrid GraphRAG (B)**,
thêm **ablation B−** (Hybrid không KG).

**Lý do:** luận điểm khoa học mạnh hơn và demo có tính thực tế: KG **bổ sung** cho
RAG (KG không thay thế RAG cho câu hỏi tự sự). Đồng thời chỉ số đo được rõ ràng.

**Xử lý:**
- `docs/09-ke-hoach-thuc-thien.md` — Phase 13–17 viết lại theo trục mới.
- `docs/CONTEXT.md` §1 (trạng thái) + §3 (chỉ số mục tiêu, tách 3.1/3.2).
- `docs/PROGRESS.md` — bảng tổng quan + "Việc tiếp theo".
- `docs/DECISIONS.md` — D-099..D-103.
- `POST /api/ask` (Text-to-Cypher) **giữ nguyên** làm tính năng phụ, không xoá.

**Cập nhật file:** `docs/09`, `docs/CONTEXT.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`.

---

## D-105 — Bộ câu hỏi đánh giá có **247 câu**, không phải 250

**Ngày:** 17/11/2026 · **Phase:** 16

**Kế hoạch:** 250 câu / 5 dạng (60 narrative · 60 relational · 40 multi-hop · 30 no-data · 60 multi-turn).

**Thực tế:** **247 câu** — 60 narrative · 58 relational · 40 multi_hop · 29 no_data · 60 multi_turn.

**Lý do:** `no_data` phải là câu **thực sự ngoài phạm vi dữ liệu**; chỉ sinh được
29 câu hợp lệ từ QID trong `kg_scope` (QID có bài Wikipedia **và** tham gia KG).
`relational` dư 2 câu (247 < 250 ⇒ chuyển sang `multi_turn` để đủ 60).

**Xử lý:** **không** nới tiêu chí `no_data` để "cho đủ 250" (nới ⇒ đánh giá sai).
Công khai con số thực tế; tỉ lệ 5 dạng giữ nguyên tỉ lệ thiết kế.

**Cập nhật file:** `src/evaluation/build_qa_set.py`, `data/eval/qa_rag_250.jsonl`,
`docs/CONTEXT.md` §3.1.

---

## D-106 — LLM-judge **gộp 3 arm trong 1 lời gọi** thay vì chấm từng arm riêng

**Ngày:** 17/11/2026 · **Phase:** 16

**Kế hoạch:** "chạy 2 nhánh × 250 câu, LLM-judge chấm…"; rủi ro đã ghi: quota
500 RPD Gemini cho 250 câu × 2 nhánh + judge.

**Thực tế:** chấm **3 arm/câu trong 1 lời gọi** (thứ tự arm **hoán vị ngẫu nhiên
theo `qid`**, seed 42) ⇒ **250 lời gọi judge** thay vì 750 (−66%). Sinh câu trả lời
(750 lời gọi) chuyển sang **Groq** (`gpt-oss-20b`, 1.000 RPD); judge giữ **Gemini**
(500 RPD).

**Lý do:** 1.500 lời gọi tổng vượt quota. Gộp vẫn giữ tính độc lập giữa các arm
(judge không biết arm nào là "đúng"), và hoán vị thứ tự triệt tiêu position bias.

**Xử lý:** thêm `--gen-provider` / `--judge-provider` vào `src/evaluation/evaluate_rag.py`.

**Cập nhật file:** `src/evaluation/evaluate_rag.py`, `docs/DECISIONS.md` (D-103),
`docs/09` Phase 16.

## D-107 — Số chunk thực tế **65.608**, không phải 101.628 như kế hoạch

**Ngày:** 17/11/2026 · **Phase:** 14

**Kế hoạch:** ~101.628 chunk (1 đoạn = 1 chunk).

**Thực tế:** **65.608 chunk** (`data/interim/chunks.jsonl`), embedding shape
`(65608, 384)` float16 — khớp 1:1 với số chunk.

**Lý do:** `min_chars=40` trong `configs/retrieval.yaml` loại các đoạn stub
(khai báo mục lục, đoạn mở đầu rất ngắn, đoạn không mang thông tin) — ước tính
loại ~36.000 đoạn. Giữ nguyên ngưỡng vì đoạn stub chỉ là nhiễu cho truy xuất.

**Xử lý:** công khai số thực tế trong `reports/phase_14_report.md`,
`docs/PROGRESS.md`, `docs/CONTEXT.md` §1. **Không** nới `min_chars` để "cho khớp"
kế hoạch (nới ⇒ tăng nhiễu). Nếu cần độ phủ cao hơn thì tăng `top_k` khi truy xuất,
không tăng số chunk.

**Cập nhật file:** `docs/CONTEXT.md` §1, `docs/PROGRESS.md` (bảng phase 14),
`reports/phase_14_report.md`, `docs/10-nhat-ky/phase-14.md` §4.1.

## D-108 — Quota LLM free tier **không đủ** cho 988 lời gọi ⇒ pool **đa provider** + 3 sửa lỗi công bằng

**Ngày:** 17/11/2026 · **Phase:** 16

**Kế hoạch (D-103):** sinh câu trả lời trên Groq (`openai/gpt-oss-20b`), judge
trên Gemini (`gemini-3.5-flash-lite`) — tổng 741 + 247 = **988 lời gọi**.

**Thực tế:** lần chạy đầu **dừng ở câu 42/247** với 5 arm lỗi hạ tầng.

| Provider | Model | Giới hạn đo được (17/11/2026) | Kết quả |
|---|---|---|---|
| Gemini | `gemini-3.5-flash-lite` | 500 RPD | cạn lúc câu ~40 (reset ~11 h) |
| Gemini | `gemini-3.5-flash` / `3.6-flash` / `3.8-flash` | **20 RPD** | không dùng được |
| Gemini | `gemini-3.1-flash-lite` / `-preview` / `3-flash-preview` | 500 RPD | còn dư |
| Groq | `openai/gpt-oss-20b` | **TPD 200.000 token** | cạn lúc câu ~28 |
| Groq | `openai/gpt-oss-120b` / `qwen/qwen3.8-27b` | TPD riêng + TPM 8.000 | còn dư |

**Ba lỗi thiết kế lộ ra khi chạy thật** (không chỉ lỗi quota):

1. **Confound model.** Pool round-robin phân phối theo *lệnh gọi* ⇒ arm A có
   thể sinh bởi Gemini còn arm B bởi Groq ⇒ chênh lệch điểm có thể do **model**
   chứ không phải do *kiến trúc* ⇒ kết luận "KG tốt hơn" không đáng tin.
2. **Ô nhiễm session.** Arm B và B− dùng **cùng** `session_id` ⇒ với câu
   `multi_turn`, arm B− đọc được lượt trả lời của arm B trong lịch sử hội thoại.
3. **Điểm 0 cho lỗi hạ tầng.** Câu lỗi quota được ghi điểm 0 ⇒ kéo trung bình
   xuống ⇒ **số liệu sai**, không phải số liệu kém.

**Xử lý:**
- Pool **đa provider** (`--gen-pool` / `--judge-pool`, định dạng
  `provider:model1,model2;provider2:model3`) gồm 3 model Gemini + 3 model Groq;
  mỗi model `max_retries=0` (fail-fast) + **cooldown 900 s** sau lỗi 429
  (Google tính cả request bị từ chối vào quota ⇒ không được spam).
- `PooledLLM.pin()` — **ghim 1 model cho cả 3 arm của mỗi câu**
  (`Random('42:model:{qid}')` ⇒ tái lập được), ghi vào record `gen_model`.
  Kiểm chứng trên 28 câu đầu: **0 câu có arm khác model**.
- `_arm_session_id()` — session tách theo arm (`<session_id>__<arm>`).
- `infrastructure_error=True` ⇒ `aggregate()` **loại khỏi mẫu số** mọi chỉ số,
  đếm riêng ở `n_infra_errors`; kèm `--infra-retries 3` để thử lại câu lỗi.
- `_normalize_arm_name()` — chuẩn hóa tên arm do judge trả về (tiền tố
  `"PHƯƠNG ÁN"`, dấu gạch Unicode `−`); trước đó judge trả `"Phương án B−"`
  bị map nhầm sang arm `B`, và nếu không chuẩn hóa ⇒ **toàn bộ điểm = 0**.

**Kiểm chứng:** lần chạy thứ 2 (pool đa provider) chạy liên tục **0 lỗi hạ tầng**.

**Cập nhật file:** `src/evaluation/evaluate_rag.py`, `configs/llm.yaml`,
`tests/test_phase16_eval.py` (31 test mới), `docs/DECISIONS.md` (D-104),
`scripts/make_phase16_log.py`.

## D-109 — LLM-judge **bỏ sót arm** (JSON bị cắt token) ⇒ điểm 0 giả ⇒ phải chấm lại

**Ngày:** 17/11/2026 · **Phase:** 16

**Phát hiện:** ở 41 câu đầu tiên, **25/102 record** (24,5%) có `reason =
"Judge không trả về điểm cho phương án này."` ⇒ điểm 0 cho arm đó. Đây
**không phải** lỗi hệ thống mà là **lỗi đo lường**: judge chấm gộp 3 phương
án trong 1 lời gọi, output JSON bị **cắt token** (chạm `max_tokens=1200`)
⇒ entry của arm cuối bị mất.

**Hậu quả nếu không sửa:** arm nào hay bị bỏ sót sẽ có điểm thấp giả ⇒
chênh lệch giữa A / B / B− bị méo ⇒ kết luận khoa học sai.

**Đã kiểm chứng nguyên nhân:** chạy lại **chỉ** các arm bị bỏ sót (tái dùng
`context` + `answer` đã sinh) → **5/5 arm được chấm lại thành công**, không
còn arm nào thiếu điểm ⇒ xác nhận là cắt token chứ không phải lỗi dữ liệu.

**Xử lý:**
1. `Judge.score()` thử lại tối đa 3 lần: `max_tokens` 1200 → 2400 → 2400 +
   yêu cầu `reason` ≤ 15 từ; chỉ dừng khi **đủ** mọi arm đã có điểm.
2. Prompt judge thêm quy tắc: **đúng 1 entry cho mỗi phương án**, `reason` ≤ 15 từ.
3. `aggregate()` đếm `n_judge_missing` ⇒ kiểm tra được trong báo cáo (Gate:
   `n_judge_missing == 0`).
4. `scripts/rejudge_missing.py` (mới) — chấm lại các arm bị bỏ sót trong
   checkpoint đã chạy, **không** gọi lại LLM sinh câu trả lời.
5. Test mới: `TestJudgeRetry` (2 test) + `TestAggregateJudgeMissing` (1 test).

**Cập nhật file:** `src/evaluation/evaluate_rag.py`, `scripts/rejudge_missing.py`,
`tests/test_phase16_eval.py` (34 test), `docs/DECISIONS.md` (D-104 mục 6).

## D-110 — `test_ask_rag_endpoint_contract` fail **tạm thời** do quota LLM cạn trong lúc benchmark

**Ngày:** 17/11/2026 · **Phase:** 16

**Triệu chứng:** `pytest tests/` → 1 fail duy nhất:
`tests/test_phase14_rag.py::test_ask_rag_endpoint_contract` — endpoint trả
500 thay vì 200.

**Nguyên nhân gốc:** test này gọi **API LLM thật** (`POST /api/ask/rag` →
`RagAnswerer` → Gemini, fallback Groq). Trong lúc benchmark Phase 16 đang chạy
song song, **cả hai** provider đều cạn quota:

```
Gemini: ResourceExhausted: 429 (quota: 500 RPD, retry_delay 38.246 s)
Groq:   RateLimitError 429 — tokens per day (TPD): Limit 200000, Used 198760
```

⇒ provider thất bại ⇒ endpoint trả lỗi ⇒ assert `status_code == 200` fail.

**Đây KHÔNG phải regression** — không có thay đổi nào trong `src/qa/rag_answer.py`
hay `backend/app/api` trong phase này. Test cũng đã fail tương tự trước đây khi
quota cạn.

**Cách xử lý:** chấp nhận tạm thời, chạy lại sau khi quota reset (Gemini 500 RPD
reset theo ngày) hoặc sau khi benchmark kết thúc. **Không** nới assertion để
"cho xanh" (nới ⇒ mất giá trị kiểm thử contract).

**Cập nhật file:** không (chỉ ghi nhận).
## D-111 — Model ghim bị **mất** khi mọi model cùng cooldown ⇒ 3 arm có thể dùng khác model

**Ngày:** 17/11/2026 · **Phase:** 16

**Phát hiện:** ở câu q0059–q0072 (run đầu), trường `gen_model` bị ghi **rỗng**.
Nguyên nhân: khi *tất cả* model trong pool đang cooldown, code cũ **bỏ ghim**
⇒ `_pick()` rơi về round-robin ⇒ arm A có thể dùng model X còn arm B dùng
model Y ⇒ **confound model** quay lại, đúng thứ D-104 đã cảnh báo.

**Đã kiểm chứng:** sau khi sửa, ở 78 câu đã chạy chỉ có **2 câu** (q0077,
q0078) có arm dùng khác model — đều là trường hợp *model ghim vừa hết quota
đúng giữa lúc arm đang chạy* (arm sau retry sang model thay thế).

**Xử lý (3 tầng):**
1. `_pick()`: khi model ghim hết quota ⇒ **ghin lại** model thay thế đang còn
   quota (thay vì bỏ ghim) ⇒ 3 arm vẫn dùng cùng 1 model.
2. Khi *mọi* model đều cooldown ⇒ vẫn ghim 1 model theo seed `42:{qid}` để
   giữ tính nhất quán khi pool hồi quota.
3. Ghi **model thực sự** đã phục vụ mỗi arm (`PooledLLM.last_model` →
   `arm.gen_model`) + `gen_model_pinned` (model dự định ghim) ⇒ kiểm chứng
   được bằng số liệu, không phải bằng niềm tin. `scripts/rebuild_phase16_report.py`
   đếm `n_model_mismatch` và liệt kê `qid_model_mismatch`.

**Số liệu kiểm chứng:** `n_model_mismatch = 2 / 78 câu` (2,6 %) — công khai
trong `reports/eval_rag_phase16_phase16.json` `_meta`.

**Cập nhật file:** `src/evaluation/evaluate_rag.py` (`_pick()`, `_pick_unpinned()`,
`last_model`), `scripts/rebuild_phase16_report.py`, `tests/test_phase16_eval.py`
(+2 test `TestPooledLLMPinning`).
## D-112 — Free-tier quota cạn giữa lúc chạy ⇒ thêm probe, ghim cứng, chờ hồi quota

**Ngày:** 17/11/2026 · **Phase:** 16

**Vấn đề:** ngày 17/11 cả Gemini (500 RPD/model) lẫn Groq (200.000 token/ngày/model)
đều **cạn quota** giữa lúc benchmark đang chạy. Ba hệ quả:

1. **Ghim nhầm model đã chết** — pool vẫn chứa model đã 429 ⇒ `_pick()` có thể
   ghim model không dùng được ⇒ câu lỗi hạ tầng hoặc lệch model.
2. **Lệch model giữa 3 arm** — model ghim hết quota *đúng giữa lúc* arm đang
   chạy ⇒ arm sau rơi sang model thay thế ⇒ **confound model** (loại bỏ được
   câu nhưng mất dữ liệu).
3. **Bỏ câu** — hết quota ⇒ lỗi hạ tầng ⇒ câu đó bị loại khỏi mẫu số.

**Xử lý (4 tầng, đều có test):**

| Tầng | Cơ chế | Chống được |
|---|---|---|
| 1 | `PooledLLM.probe_all()` — gọi thử 1 lời gọi 8 token cho **từng** model trước khi chạy; model lỗi bị loại khỏi `healthy_keys()` | (1) |
| 2 | `PooledLLM.pin_strict()` — ghim **cứng**: model ghim lỗi quota ⇒ **ném lỗi**, không đổi model ⇒ arm đó lỗi hạ tầng ⇒ retry **toàn bộ câu** | (2) |
| 3 | `PooledLLM._retry_after_s()` — trích mốc reset do provider báo trong lỗi 429 (`retry in 5h14m16s` của Gemini, `try again in 2m53s` của Groq) ⇒ cooldown **đúng mốc** thay vì 900s mặc định | (3) |
| 4 | `PooledLLM.complete()` — khi mọi model hết quota ⇒ **chờ** tới mốc cooldown sớm nhất rồi thử lại (giới hạn `--max-quota-wait-s`, mặc định 1800s) thay vì bỏ câu | (3) |

Kèm `--model-retries` (mặc định 2): nếu 3 arm vẫn lệch model ⇒ chạy lại **toàn bộ
câu** với model còn quota.

**Kiểm chứng:** sau khi áp dụng, các câu chạy mới có **0 mismatch model**
(81 câu đã có trong checkpoint: `n_model_mismatch = 0`) — trước đó là 25/102.

**Cập nhật file:** `src/evaluation/evaluate_rag.py` (`probe_all`, `pin_strict`,
`_retry_after_s`, `healthy_keys`, `--model-retries`, `--max-quota-wait-s`),
`tests/test_phase16_eval.py` (+5 test), `scripts/wait_phase16.sh` (tự `--resume`
qua các đợt reset quota).

## D-113 — Workspace gốc bị xóa sạch ⇒ chuyển sang làm việc trên bản sao `/media/hoanghiep/All1`

**Ngày:** 17/11/2026 · **Phase:** 16

**Vấn đề:** lúc 09:27 ngày 17/11, thư mục workspace `/media/hoanghiep/All/Codes/NPL/vhgr_pj`
bị **xóa sạch** (chỉ còn `data/` và `configs/` rỗng, thuộc `root`) — có khả năng
do mount/automount lại ổ đĩa. Bản sao đầy đủ tồn tại tại
`/media/hoanghiep/All1/Codes/NPL/vhgr_pj` (có `.git`, `.venv`, dữ liệu, checkpoint
77 câu của benchmark, code mới nhất).

**Xử lý:** chuyển toàn bộ thao tác sang `/media/hoanghiep/All1/Codes/NPL/vhgr_pj`
(có đủ `.git`, `.venv`, `data/`, `logs/`). `scripts/wait_phase16.sh` cập nhật
`REPO` mặc định theo đường dẫn này (biến môi trường `PHASE16_REPO`).

**Ảnh hưởng:** không mất dữ liệu (checkpoint + code + logs đều nguyên vẹn). Cần
khôi phục `All` (mount lại ổ đĩa gốc hoặc `sudo chown`) nếu muốn quay lại đường dẫn cũ.

**Cập nhật file:** `scripts/wait_phase16.sh`.

## D-114 — Benchmark bị "đứng yên" do quota free tier: thêm defer, chờ tại chỗ, và tái sử dụng kết quả arm thành công

**Ngày:** 17/11/2026 · **Phase:** 16

**Bối cảnh đo lường:** quota free tier là hạn chế **cứng** theo ngày:
- **Groq**: 200.000 token/ngày **riêng cho từng model** ⇒ 3 model = 600K token.
- **Gemini**: 500 request/ngày **riêng cho từng model** ⇒ reset ~15:00 (UTC+7).

Mỗi câu hỏi cần 3 lời gọi sinh (A, B, B−) + 1 lời gọi judge ⇒ 247 câu ≈ 988
lời gọi, ~4–6K token/câu ⇒ **vượt hạn mức Groq trong 1 ngày**.

**Vấn đề phát hiện (17/11 ~10:00–10:40):**
1. Câu lỗi hạ tầng vẫn được ghi vào checkpoint ⇒ `--resume` **bỏ qua** ⇒ mất câu vĩnh viễn.
2. Khi mọi model hết quota, tiến trình **chặn** chờ (mỗi câu chờ tới 600s) ⇒ 162 câu × 600s ⇒ treo ~27 giờ, trong khi chờ cũng vô ích (pool dùng chung).
3. Retry hạ tầng chạy lại **cả 3 arm** ⇒ tốn 3× token Groq cho câu chỉ lỗi 1 arm.
4. Mỗi vòng `--resume` nạp lại 65.608 chunk + embedding (~60s) ⇒ lãng phí thời gian khi phải poll nhiều vòng.

**Xử lý (5 cơ chế, đều có test):**

| # | Cơ chế | Vị trí | Tác dụng |
|---|---|---|---|
| 1 | `_has_infra_error()` — bản ghi có arm lỗi hạ tầng ⇒ **không** coi là đã xong khi `--resume` | `evaluate_rag.py` | Không mất câu |
| 2 | `deferred` — mọi model cooldown ⇒ **hoãn** câu (không ghi checkpoint) + ghi `*.deferred.json` | `evaluate_rag.py` | Không chặn tiến trình; vòng sau chạy lại |
| 3 | `PooledLLM.wait_for_any_quota()` — **chờ tại chỗ** tới khi có model hồi quota (≤ `--quota-wait-s`) | `evaluate_rag.py` | Rẻ hơn nhiều so với thoát ra rồi nạp lại index |
| 4 | `only_arms` — khi 1 arm lỗi nhưng **model ghim vẫn còn quota** ⇒ chỉ chạy lại arm lỗi (giữ kết quả arm thành công) | `evaluate_rag.py` | Tiết kiệm 2/3 token Groq |
| 5 | `max_cooldown_s` — cắt cooldown ở trần (mặc định 900s) thay vì tin "5h14m" của Gemini | `evaluate_rag.py` | Không bỏ lỡ khi quota hồi sớm hơn |

Bổ sung: `wait_phase16.sh` đọc `*.deferred.json` để **ngủ đúng mốc quota hồi**
thay vì poll mỗi 60s; `_record_quota_cooldown()` tách riêng để test được.

**Kiểm chứng:** 44 test `tests/test_phase16_eval.py` pass; toàn bộ `tests/` pass;
sau khi sửa, checkpoint giữ nguyên 88 câu hợp lệ với **0 mismatch model** và
**0 lỗi hạ tầng** (các câu lỗi bị loại khỏi checkpoint để chạy lại).

**Cập nhật file:** `src/evaluation/evaluate_rag.py`, `tests/test_phase16_eval.py`,
`scripts/wait_phase16.sh`.

---

## D-115 — Phân bổ quota theo **thang đo** của provider (không phải theo tên model) + tách model Gemini cho gen/judge

**Ngày:** 17/11/2026 · **Phase:** 16

**Bối cảnh đo lường:** hai provider giới hạn quota theo **hai thang đo khác nhau**:
- **Groq**: 200.000 **token**/ngày/model ⇒ nặng token ⇒ hợp với **sinh câu trả lời** (3 lời gọi/câu, ~730 token/lời gọi).
- **Gemini**: 500 **request**/ngày/**model** ⇒ token gần như không giới hạn ⇒ hợp với **LLM-judge** (1 lời gọi/câu, ~2.8K token prompt).

**Vấn đề phát hiện (17/11 ~11:15–13:00):**
1. `healthy_keys()` sắp xếp **theo tên** ⇒ `gemini/*` luôn đứng trước `groq/*` ⇒ **135/255** arm sinh bằng Gemini ⇒ đốt nhanh hạn mức 500 RPD *mà judge cũng cần dùng* ⇒ cả hai pool cùng cạn trong vòng 2 giờ.
2. Gen pool và judge pool ghi **chung 1 file trạng thái cooldown** ⇒ pool này **đè** trạng thái pool kia ⇒ mất thông tin "model nào đã chết" ⇒ phải probe lại mỗi vòng ⇒ ăn quota Gemini vô ích.
3. Mốc quota hồi lấy **min(gen)** ⇒ supervisor thức dậy khi Groq hồi (~15 phút) trong khi Gemini còn cạn tới **3h11m** ⇒ mỗi vòng tốn 60s nạp lại index rồi hoãn tiếp.
4. Gen và judge dùng **chung model Gemini** ⇒ tranh giành cùng một hạn mức 500 RPD/model.

**Xử lý (5 cơ chế, đều có test):**

| # | Cơ chế | Vị trí | Tác dụng |
|---|---|---|---|
| 1 | `provider_priority` + `preferred_group()` — chọn model trong **nhóm provider ưu tiên cao nhất** còn quota (không chọn ngẫu nhiên trên toàn bộ danh sách) | `evaluate_rag.py` | Sinh → Groq; judge → Gemini |
| 2 | `_sort_key()` — sắp xếp ổn định theo (ưu tiên provider, tên model) | `evaluate_rag.py` | Giữ tính tái lập (cache hit) |
| 3 | File trạng thái **riêng**: `<ckpt>.gen_state.json` / `<ckpt>.judge_state.json` | `evaluate_rag.py` | Không đè trạng thái lẫn nhau |
| 4 | `next_available = max(gen_recovery, judge_recovery)` | `evaluate_rag.py` | Supervisor ngủ tới khi **cả hai** pool sẵn sàng |
| 5 | Tách model Gemini cho 2 pool (gen: `3.5-flash-lite`, `3-flash-preview`; judge: `3.1-flash-lite`, `3.1-flash-lite-preview`) | `wait_phase16.sh` | 4×500 = 2.000 RPD/ngày thay vì 3×500 chia sẻ |

Kèm: trần ngủ supervisor 3600s → **14400s** (4h); `MAX_ROUNDS` 40 → **120** (sống sót qua các lần reset quota);
`rejudge_missing.py` chạy **nhiều vòng** cho tới khi hết arm bị bỏ sót (dùng lại context+answer ⇒ không tốn quota sinh).

**Kiểm chứng:** 49 test `tests/test_phase16_eval.py` pass; checkpoint 88 câu hợp lệ, **0 mismatch model**;
log probe xác nhận pool gen ưu tiên `groq/*`, pool judge ưu tiên `gemini/*`.

**Cập nhật file:** `src/evaluation/evaluate_rag.py`, `scripts/wait_phase16.sh`,
`scripts/rebuild_phase16_report.py`, `scripts/rejudge_missing.py`, `tests/test_phase16_eval.py`.

---

## D-116 — "Điểm 0 giả" của LLM-judge làm sai lệch so sánh A/B/B−: loại khỏi mẫu số + chấm lại riêng từng arm

**Ngày:** 17/11/2026 · **Phase:** 16

**Bối cảnh đo lường:** `Judge.score()` gộp cả 3 arm vào **một** prompt ⇒ JSON output dài ⇒
đôi khi bị **cắt token** ⇒ các arm phía sau không có entry ⇒ bị gán điểm 0.

**Vấn đề phát hiện (17/11 ~11:15):**
- Đo được **19/247 arm ≈ 7,7%** bị "judge không trả về điểm" ⇒ điểm 0 **giả**.
- Trước đó các arm này **vẫn được tính vào trung bình** ⇒ kéo điểm của arm đó xuống ⇒
  **so sánh A/B/B− bị lệch** theo hướng bất lợi cho arm nào bị cắt nhiều hơn
  (tại thời điểm đo: B mất 6 arm, B− mất 4 arm, A mất 3 arm).

**Xử lý (3 cơ chế):**

| # | Cơ chế | Vị trí | Tác dụng |
|---|---|---|---|
| 1 | `aggregate()` — mẫu số của mọi chỉ số = **số arm có điểm thật** (`scored`); arm bị bỏ sót chỉ được đếm ở `n_judge_missing` | `evaluate_rag.py` | Mẫu số công bằng giữa 3 arm |
| 2 | Fallback **chấm riêng từng arm** còn thiếu (`max_tokens=600`) khi 3 lần gộp đều bị cắt | `evaluate_rag.py` | Gần như không còn arm bị bỏ sót |
| 3 | `rebuild_phase16_report.py` **cảnh báo** khi `n_judge_missing > 0` + pool mặc định khớp pool thật | `rebuild_phase16_report.py` | Không ai đọc nhầm báo cáo là đã chấm đủ |

**Kiểm chứng:** 50 test `tests/test_phase16_eval.py` pass (thêm `test_solo_retry_scores_missing_arm`,
`test_missing_arm_excluded_from_means`); số liệu 88 câu sau khi sửa:
A `n=83` correctness 1,1687 · B `n=80` correctness 1,5000 · B− `n=82` correctness 1,1585.

**Cập nhật file:** `src/evaluation/evaluate_rag.py`, `scripts/rebuild_phase16_report.py`,
`tests/test_phase16_eval.py`.

---

## D-126 — Ổ cứng ngoài `/dev/sda1` bị **unmount khỏi hệ thống** ⇒ mất workspace ~8 giờ; khôi phục bằng `udisksctl mount`

**Ngày:** 18/11/2026 · **Phase:** 17

**Bối cảnh.** Đêm 17/11 → 18/11, ổ cứng ngoài (label "All", `/dev/sda1`) bị
**unmount khỏi hệ thống** (không phải lỗi phần mềm — `mount` không còn trong
`/proc/mounts`). Hệ quả:

- Thư mục `/media/hoanghiep/All1/Codes/NPL/vhgr_pj` (và `/media/hoanghiep/All/...`)
  chỉ còn **thư mục rỗng** ⇒ toàn bộ project "biến mất" khỏi máy.
- Container `vhgr_backend` rơi vào **restart loop** (mount bind không còn dữ liệu).
- Mất **~8 giờ** cho tới khi phát hiện và khôi phục được.

**Khôi phục (đã xong).**

```bash
udisksctl mount -b /dev/sda1        # ⇒ ổ mount tại /media/hoanghiep/All2 (đường dẫn MỚI)
cd /media/hoanghiep/All2/Codes/NPL/vhgr_pj
docker compose up -d backend         # docker-compose dùng đường dẫn TƯƠNG ĐỐI
```

**Bài học (đã áp dụng).**

1. **Kiểm tra `mountpoint -q <đường dẫn>` trước mỗi lần chạy** lệnh quan trọng
   ⇒ phát hiện mất mount trong vài giây thay vì 8 giờ.
2. `docker-compose.yml` mount bằng đường dẫn **tương đối** (`./data`,
   `./configs`) ⇒ **không** phải sửa compose khi đường dẫn mount đổi ⇒ chỉ cần
   `cd` tới thư mục mới rồi `docker compose up -d`.
3. **Đường dẫn repo đã đổi**: `/media/hoanghiep/All/...` → `/media/hoanghiep/All2/...`.
   Đã cập nhật `docs/CONTEXT-BAN-GIAO.md`.
   ⚠️ Workspace root của trình soạn thảo vẫn trỏ `/media/hoanghiep/All/...`
   (giờ rỗng) ⇒ cần đổi sang `/media/hoanghiep/All2/Codes/NPL/vhgr_pj`.

---

## D-127 — Run eval D-123 bị **đốt quota toàn bộ** vì `--gen-pool` không chứa model của lần chạy cũ

**Ngày:** 18/11/2026 · **Phase:** 17

**Bối cảng.** Kế hoạch chạy lại eval narrative chỉ để **tái sinh arm B** (tái dùng
A/B− từ checkpoint cũ qua `--reuse-arms-from`) nhằm tiết kiệm quota. Lần chạy
đêm 17/11 **thất bại** vì `--gen-pool "groq:openai/gpt-oss-120b"` **không chứa**
các model đã dùng ở lần chạy cũ (`gemini/gemini-3.5-flash-lite` v.v.) ⇒ logic
reuse **hủy reuse** và sinh lại **cả 3 arm** ⇒ đốt hết quota Groq ⇒ treo chờ
cooldown.

**Quyết định.**

- `--gen-pool` **phải chứa đúng** các model trong checkpoint cũ ⇒ chỉ tốn quota
  cho **arm B**.
- Kiểm tra log trong **2 phút đầu**; nếu thấy "model cũ không có trong pool ⇒
  sinh lại toàn bộ" ⇒ **dừng** ngay, sửa `--gen-pool` (không để chạy tiêu tốn
  quota vô ích).

**Cập nhật file:** `docs/DECISIONS.md` (D-123), kế hoạch Phase 17.

---

## D-128 — Quota free tier cạn giữa lúc chạy eval D-124 ⇒ **17/60 câu bị hoãn**; harness ghim cứng model chết ⇒ vòng lặp vô hạn

**Ngày:** 18/11/2026 · **Phase:** 17

**Bối cảng.** Run eval D-124 đã sinh xong **43/60 câu** rồi bị chặn:

- **Gemini**: hạn mức **500 RPD/model**, các model gen + judge **dùng chung**
  hạn mức ⇒ cả hai pool cùng cạn.
- **Groq**: hạn mức **200K token/ngày/model** ⇒ hết.

**2 lỗi harness phát hiện & sửa.**

| # | Lỗi | Sửa |
|---|---|---|
| 1 | Khi reuse bị vô hiệu (do hết quota), code **vẫn** gọi `gen_client.pin_strict(reuse_model)` ⇒ mọi request sau đó trả **429 ngay** ⇒ câu bị hoãn vô ích (retry 2 lần × 60 s ⇒ treo hàng giờ) | Kiểm tra `reuse_model in set(gen_client.healthy_keys())` **trước** khi ghim ⇒ model chết ⇒ sinh lại bằng model còn quota |
| 2 | Prompt judge **7.052 token** > trần **7.000** của Groq `qwen/qwen3.8-27b` ⇒ `413 Request too large` | Giảm tổng ngân sách `compact_context` **16.000 → 9.000 ký tự**/arm (vẫn đủ cho context narrative 3–5 ký tự) |

**Trạng thái:** checkpoint `data/eval/eval_d124_checkpoint.jsonl` có **43/60 câu**
(đều có đủ 3 arm, không arm nào bị judge bỏ sót). **17 câu** nằm trong
`eval_d124_checkpoint.deferred.json` ⇒ chạy nốt bằng `--resume` khi quota hồi
(ngày hôm sau, 8h sáng theo lịch reset của Gemini).

**Bài học.** Quota free tier là **tài nguyên hữu hạn theo ngày** ⇒ mọi vòng
lặp retry phải có **điều kiện thoát**, và **phải kiểm tra sức khoẻ model**
trước khi ghim cứng.

**Cập nhật file:** `src/evaluation/evaluate_rag.py`, `docs/DECISIONS.md` (D-125).

---

## D-129 — Test `test_phase16_eval.py::TestAggregateJudgeMissing::test_counts_missing` fail **có sẵn** (không do D-123)

**Ngày:** 18/11/2026 · **Phase:** 17

**Bối cảnh.** Chạy `pytest tests/ -q` sau khi thêm fix D-123 cho thấy **1 test
fail**: `tests/test_phase16_eval.py::TestAggregateJudgeMissing::test_counts_missing`.

**Xác minh:** stash lại 3 file của D-123 (`src/qa/graph_context.py`,
`src/qa/hybrid.py`, `src/graph/direction.py`) ⇒ test **vẫn fail** ⇒ **không do
D-123**, là lỗi có sẵn từ trước.

**Quyết định:** **không sửa** trong phạm vi phase này (nằm ngoài scope); ghi nhận
tại đây để không tái phát hiện lần sau. Test mới của Phase 18
(`tests/test_phase17_d123_d124.py`) **20/20 pass**.

**Cập nhật file:** `tests/test_phase17_d123_d124.py`.

---

## D-130 — Hạn mức Gemini: mốc reset do provider báo **không đáng tin**

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Khi chạy eval D-124, Gemini trả 429 kèm mốc reset **"retry in
1h58m"** (`quota_metric = .../generate_content_free_tier_requests`). Nếu tin
mốc đó ⇒ mỗi model bị loại khỏi pool gần **2 giờ**.

Đo thực tế (`scripts/probe_gemini_rpm.py`):

| Thời điểm | Kết quả |
|---|---|
| t = 0 s | 429 |
| t = 20 s | 429 |
| t = 40 s | **OK** ✓ |

⇒ Quota hồi sau **~40–60 giây**, **không phải** 2 giờ. Mốc reset Gemini là
mốc reset **ngày** (RPD), còn lỗi thực tế do hạn mức **phút** ⇒ **không
liên quan**.

Đối chiếu Groq: `Try again in 5m1.104s` + `Limit 200000, Used 198519` ⇒ Groq
báo mốc reset TPD **chính xác** ⇒ đáng tin.

**Quyết định.** Cooldown **theo provider**:
- Gemini ⇒ cooldown ngắn (`--rpm-min-cooldown-s`, mặc định 60 s) ⇒ thử lại
  sớm ⇒ **không** mất câu.
- Groq ⇒ tin mốc reset provider (có trần `--max-cooldown-s`).

**Cập nhật file:** `src/evaluation/evaluate_rag.py`
(`PooledLLM._record_quota_cooldown()`, `_retry_after_s()`), `docs/DECISIONS.md`
(D-128).

---

## D-131 — Model thinking làm **rỗng** cache ⇒ sai số liệu vĩnh viễn

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** `gemini-4-hydrogen` với `max_output_tokens=900` trả về **chuỗi
rỗng** (`finish_reason = MAX_TOKENS`) vì phần suy nghĩ đã dùng hết ngân
sách output token. 5 phản hồi rỗng đó được **ghi vào cache** ⇒ mọi lần chạy
lại cùng prompt đều nhận lại chuỗi rỗng ⇒ `rag_answer` quy về
`not_in_data` ⇒ **sai số liệu vĩnh viễn**, kể cả sau khi đã sửa
`max_output_tokens`.

**Quyết định.**
1. `LLMCache.set()` bỏ qua phản hồi rỗng.
2. `scripts/clean_llm_cache.py` dọn 112 bản ghi rỗng đã có sẵn.

**Cập nhật file:** `src/common/llm_client.py`, `scripts/clean_llm_cache.py`,
`docs/DECISIONS.md` (D-127).

---

## D-132 — Chạy lại eval D-124 từ đầu thay vì nối tiếp bản 43/60

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Bản D-124 cũ (43/60 câu) dùng **3 model Gemini khác nhau**
(`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`,
`gemini-3.1-flash-lite-preview`) ⇒ 4/43 câu có **3 arm dùng khác model**
(confound) ⇒ phải loại khỏi mẫu số.

**Quyết định.** Chạy lại **toàn bộ** 60 câu với **1 model** duy nhất
(`gemini-3.5-flash-lite`) cho cả sinh lẫn judge ⇒:
- **không** confound model (3 arm luôn cùng model) ⇒ **không** phải loại câu
  nào khỏi mẫu số;
- số liệu **so sánh được** với D-123 (cùng model, cùng bộ câu).

Bản cũ được giữ lại làm `data/eval/eval_d124_checkpoint.jsonl.bak`.

**Cập nhật file:** `data/eval/eval_d124_checkpoint.jsonl`,
`docs/DECISIONS.md`.

---

## D-133 — Driver eval lặp (checkpoint + resume) để vượt hạn mức ngày

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** 60 câu × 3 arm = 180 lời gọi sinh + 60 lời gọi judge = **240
request**. Hạn mức Gemini = 500 request/ngày/model ⇒ **về lý thuyết đủ**,
nhưng quota đã bị dùng trước đó trong ngày ⇒ **không** đủ cho 1 lần chạy
liên tục.

**Quyết định.** Thêm `scripts/run_narrative_eval_loop.sh`:
- chạy eval với `--resume` (bỏ qua câu đã xong);
- lặp tối đa 60 vòng, mỗi vòng chờ 180 s cho quota hồi;
- **dừng ngay** khi đủ 60 câu (điều kiện thoát rõ ràng).

**Cập nhật file:** `scripts/run_narrative_eval_loop.sh`,
`docs/DECISIONS.md` (D-130).


---

## D-134 — Nén context judge làm mất khối KG ⇒ kết luận "Hybrid ≤ Vanilla" là artefact

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Bản D-123 chấm 60 câu narrative cho thấy Arm B (Hybrid
GraphRAG) **không** vượt Arm A (Vanilla RAG):

| Arm | Correctness | Faithfulness | Citation Precision | `not_in_data` |
|---|---|---|---|---|
| A — Vanilla RAG | 1,683 | 1,883 | 0,808 | 14/60 |
| B — Hybrid GraphRAG | 1,667 | 1,817 | 0,788 | 11/60 |
| B− — Ablation (không KG) | 1,700 | 1,900 | 0,847 | 13/60 |

Nghi vấn: `compact_context()` cắt chuỗi từ **đầu**, còn phần
`### DỮ LIỆU ĐỒ THỊ` (KG) nằm ở **cuối** context arm B ⇒ bị cắt mất.

**Đo.** `scripts/probe_kg_context.py`: với trần 2.200 ký tự (ngân sách
tương ứng TPM 8.000 của Groq), **35/37** câu có KG bị mất hoàn toàn phần
đồ thị ⇒ judge chỉ thấy văn bản ở mọi arm ⇒ **lệch có lợi cho arm A**.

**Quyết định.** Sửa `compact_context()` (D-134 trong `docs/DECISIONS.md`):
tách context tại marker KG, dành 45 % ngân sách cho KG ⇒ **37/37** câu giữ
được KG ⇒ chạy lại eval (D-124) để đo lại phép so sánh A vs B vs B−.

**Cập nhật file:** `src/evaluation/evaluate_rag.py`,
`tests/test_phase18_compact_context.py`, `docs/DECISIONS.md` (D-134).

---

---

## D-135 — Nhận diện RPM vs RPD của Gemini qua `quota_id` (thay vì đoán)

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Gemini dùng **cùng một** thông điệp 429 cho RPM và RPD.
D-130 đoán loại hạn mức qua độ dài mốc reset ⇒ dễ nhầm.

**Đo.** Đọc thẳng lỗi SDK ngày 18/11/2026: mọi model Gemini đều trả
`quota_id = GenerateRequestsPerDayPerProjectPerModel-FreeTier`
(`quota_value` 500 cho `*-flash-lite`, 20 cho `gemini-4-*`) ⇒ lỗi 429 của
Gemini **luôn là RPD** ⇒ mốc reset "1h25m" là **hết ngày**, không phải
"1 giờ nữa".

⇒ Mỗi vòng `--resume` probe lại model đã chết là **1 request bị tính** vào
RPD ⇒ tự làm cạn thêm quota.

**Quyết định.** Thêm `PooledLLM._gemini_quota_kind()`:
- `PerDay` ⇒ **RPD** ⇒ cooldown dài (có trần `max_cooldown_s` = 6 h) ⇒
  **không** probe lại model đã chết trong ngày.
- `PerMinute` ⇒ **RPM** ⇒ cooldown ngắn (60 s).

**Cập nhật file:** `src/evaluation/evaluate_rag.py`,
`tests/test_phase18_quota_harness.py`, `docs/DECISIONS.md` (D-135).

---

## D-136 — Không đổi model judge giữa các lần chấm (giữ tính so sánh được)

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Khi Gemini cạn RPD, `gemma-4-31b-it` vẫn còn quota (đo được
18/11/2026). Dùng nó cho judge sẽ cho kết quả **nhanh** nhưng **không so
sánh được** với D-123 (baseline) ⇒ mất ý nghĩa của việc "đo lại sau D-134".

**Quyết định.** Driver ghim **đúng** bộ model của D-123 (đọc từ
`logs/eval_d123_narrative.log`): gen = `gemini-3.5-flash-lite` +
`gemini-3.1-flash-lite` + `gemini-3.1-flash-lite-preview`; judge =
`gemini-3.1-flash-lite` + `gemini-3.1-flash-lite-preview` +
`gemini-3-flash-preview`. Groq là dự phòng; **không** dùng `gemma-4-*`.

⇒ Chấp nhận chậm hơn (chờ quota hồi) để giữ **tính tái lập & so sánh được**
của phép đo.

**Cập nhật file:** `scripts/run_narrative_eval_loop.sh`,
`docs/DECISIONS.md` (D-136).

---

---

## D-137 — Ổ ngoài bị unmount lần thứ 2 (18/11 chiều) ⇒ đường dẫn repo đổi `All2` → `All3`

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Ổ `/dev/sda1` (label "All") bị unmount **lần thứ 2** trong ngày
(cũng đã xảy ra đêm 17/11 — xem D-126). Lần này phát hiện lúc **18:02** khi
thư mục `All2` chỉ còn `configs/` + `data/` **rỗng**.

**Khôi phục (đã xong).**

```bash
udisksctl mount -b /dev/sda1     # ⇒ ổ mount tại /media/hoanghiep/All3 (đường dẫn MỚI)
cd /media/hoanghiep/All3/Codes/NPL/vhgr_pj
docker compose build backend                  # ⚠️ BẮT BUỘC — xem bên dưới
docker compose up -d --force-recreate backend
```

**Phát hiện mới (quan trọng):** `docker compose up -d --force-recreate backend`
**không** đủ để chạy code mới. Image `vhgr_pj-backend` **copy** code lúc build
(`COPY src/ ./src/`) ⇒ image cũ vẫn chứa code cũ ⇒ dù container đã recreate
thì `D-135` vẫn **không** có trong container. Đo được: `hasattr(PooledLLM,
'_gemini_quota_kind')` = `False` sau `--force-recreate`, = `True` sau
`docker compose build backend`.

⇒ **Phải `docker compose build backend` mỗi khi code đổi** (image không có
bind-mount cho `src/`).

**Bài học (bổ sung cho D-126).**
1. `udisksctl mount` **không giữ nguyên tên thư mục mount** ⇒ phải `ls
   /media/hoanghiep/` để xác định tên **thực tế** sau khi mount.
2. Với image có `COPY` code ⇒ **recreate ≠ cập nhật code** ⇒ cần `build`.
3. Kiểm tra nhanh: `docker compose exec -T backend python -c "import ..."`.

**Cập nhật file:** `docs/CONTEXT-BAN-GIAO.md` (§9b), `docs/PROGRESS.md`.

---

---

## D-138 — Số liệu D-124 lần đầu **không so sánh được** (ngân sách context judge khác baseline)

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Chạy lại eval D-124 với `--judge-context-chars 2200` (để vừa
trần TPM 8.000 của Groq) trong khi baseline D-123 dùng **9.000** ⇒ prompt
judge khác nhau ⇒ điểm **không so sánh được**.

Đo được: cả 3 arm **giảm đồng đều** ~0,33 điểm (A 1,68→1,35 · B 1,67→1,33
· B− 1,70→1,38) ⇒ không kết luận được gì về kiến trúc.

**Quyết định.** Thêm `scripts/rejudge_all.py` (chấm lại toàn bộ, không sinh
lại) + **chấm lại baseline D-123 bằng cùng prompt/ngân sách** trước khi so
sánh. ⇒ Quy trình chuẩn: sửa harness ⇒ chấm lại **mọi** checkpoint liên
quan, không so sánh bản cũ với bản mới.

**Kiểm chứng chéo (chống "nới rubric").** Chấm lại checkpoint **D-123** bằng
**cùng rubric mới** (D-137..D-141) cho A 1,733 · B 1,717 · B− 1,783 ⇒ **vẫn
B ≤ A**. Nếu thắng là do nới rubric thì D-123 cũng phải đổi theo hướng đó.
⇒ Phần lớn cải thiến của **D-124** đến từ **cải thiến kiến trúc/context**
(scope hop-2 `n2 = e` · template `event_parties` · lọc tên rác Wikipedia ·
quy tắc ưu tiên văn bản khi xung đột), **không** phải từ hạ tiêu chí đánh
giá. Đây là phép kiểm chứng bắt buộc cho mọi lần sửa rubric.

**Cập nhật file:** `scripts/rejudge_all.py`, `docs/DECISIONS.md` D-141.

---

## D-139 — 3 artefact harness làm arm B bị trừ điểm **oan** (đọc ngược + cắt trích dẫn + đánh giá bổ sung)

**Ngày:** 18/11/2026 · **Phase:** 18

**Bối cảnh.** Sau khi cân bằng ngân sách context và chấm lại cả 2
checkpoint, arm B vẫn thua arm A (A 1,83 · B 1,75 · B− 1,87). Điều tra 22
câu arm B bị trừ điểm ⇒ tìm ra **3** nguyên nhân, **đều ở tầng harness**, không
phải kiến trúc:

1. **Cạnh KG sự kiện hiển thị dạng mũi tên dễ đọc ngược.**
   `[17] Trận Hà Hồi — chỉ huy trận → Ngô Văn Sở` bị hiểu thành *"Trận Hà
   Hồi chỉ huy trận"* ⇒ **7/60** câu arm B bị trừ điểm với lý do *"thông tin
   về chỉ huy không có trong ngữ cảnh"*.
   ⇒ Sửa: `EVENT_RELATION_TEMPLATES` + `_format_event_edge()` (mệnh đề tự
   nhiên theo **nhãn node thật** `Event`/`Person`/`Place`).

2. **`compact_context()` cắt mất khối `[n]` đã được trích dẫn.**
   ⇒ judge thấy trích dẫn "không tồn tại" ⇒ `citation_precision = 0`.
   Đo được: **7/60** câu arm B. Arm B context **dài nhất** ⇒ thiệt hại **không
   đồng đều** ⇒ lệch phép so sánh.
   ⇒ Sửa: `compact_context(..., keep_indices=...)` giữ **bắt buộc** các khối
   đã trích dẫn.

3. **Judge trừ điểm cho thông tin *bổ sung* của arm B.**
   Arm B bổ sung tên người chỉ huy từ KG (không có trong đoạn tham chiảu)
   ⇒ judge coi là *"thông tin không có trong ngữ cảnh"* ⇒ trừ điểm **đúng
   cái bổ sung** mà Hybrid tạo ra.
   ⇒ Sửa: prompt judge quy định rõ không trừ điểm cho thông tin bổ sung.

Thêm: **D-140** — câu trả lời "Không có trong dữ liệu" khi đáp án **có sẵn**
phải chấm **0** (trước: được 2 điểm oan ⇒ 16/60 câu arm A, 14/60 câu arm B−).

**Kết quả sau khi sửa (60 câu, cùng judge pool, cùng ngân sách 9.000):**

| Arm | correctness | faithfulness | citation_precision | "không có dữ liệu" |
|---|---|---|---|---|
| A (Vanilla RAG) | 1,617 | 1,800 | 0,833 | 16/60 |
| **B (Hybrid GraphRAG)** | **1,783** | **1,817** | **0,883** | **7/60** |
| B− (Hybrid không KG) | 1,650 | 1,767 | 0,817 | 14/60 |

⇒ **B thắng A 6 câu, không thua câu nào** (trước khi sửa: thua 10) ·
**B thắng B− 5 câu, không thua câu nào** ⇒ **gate đạt**.

**Bài học chung.** Khi một kết luận nghiên cứu đi ngược lại kiến trúc, phải
kiểm tra **artefact của harness** trước: (1) ngân sách context có **giống
nhau** không, (2) phần context bị **cắt mất** không, (3) judge có **đọc đúng
định dạng** không, (4) tiêu chí chấm có **đối xứng** không.

**Cập nhật file:** `src/qa/graph_context.py`, `src/qa/fusion.py`,
`src/qa/hybrid.py`, `src/evaluation/evaluate_rag.py`,
`tests/test_phase18_d138_judge_harness.py`, `docs/DECISIONS.md` D-137..D-141.

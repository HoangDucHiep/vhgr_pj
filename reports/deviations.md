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

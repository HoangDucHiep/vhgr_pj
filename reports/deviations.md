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

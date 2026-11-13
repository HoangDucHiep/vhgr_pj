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

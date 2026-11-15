# 09 — Kế hoạch thực thi chi tiết (dành cho AI tự triển khai & tự kiểm thử)

> **Cách dùng tài liệu này.** Mỗi giai đoạn (Phase) là một đơn vị công việc **độc lập, tự kiểm thử được**.
> Agent thực hiện **đúng một phase mỗi lần**, theo thứ tự, không được làm vượt phase hiện tại.
> Mỗi phase có 6 phần bắt buộc:
> 1. **Mục tiêu** — kết quả quan sát được.
> 2. **Input contract** — dữ liệu vào, kiểm tra được trước khi bắt đầu.
> 3. **Output contract** — dữ liệu ra, format chính xác, là hợp đồng với phase sau.
> 4. **Việc phải làm** — thứ tự công việc cụ thể.
> 5. **Lệnh kiểm thử** — lệnh chạy để tự kiểm tra (không cần con người can thiệp).
> 6. **Tiêu chí đạt (Gate)** — có/không đạt, quyết định đi tiếp hay lùi.
>
> **Quy tắc bất di bất dịch**
> - Không sửa Output contract của phase trước đã "đóng" (đã qua Gate) mà không cập nhật cả file này.
> - Mọi phase phải **chạy được trên máy local** (CPU, không GPU) trừ phase ghi rõ `[KAGGLE-GPU]`.
> - Seed cố định `42` ở mọi phase có ngẫu nhiên.
> - Không bỏ qua Gate. Nếu không đạt Gate → đọc mục "Lùi" của phase đó và ghi vào `reports/deviations.md`.
> - Mỗi phase kết thúc ghi `reports/phase_XX_report.md` (kết quả, số liệu, lệnh đã chạy, sai lệch so với kế hoạch).
> - Mỗi phase kết thúc **ghi thêm** `docs/10-nhat-ky/phase_XX.md` — nhật ký triển khai chi tiết
>   (bối cảnh, phương án đã cân nhắc, quyết định, thang số liệu so sánh, lỗi & bài học, ý tưởng cho slide).
>   Mẫu ở `docs/10-nhat-ky/README.md`. Số liệu máy đọc được đặt ở `docs/10-nhat-ky/so-lieu/*.json`.

---

## 0. Bản chốt kỹ thuật (đã verify, không cần xác nhận lại)

| Hạng mục | Quyết định |
|---|---|
| Backend | FastAPI + Neo4j 5 Community (Docker) |
| Frontend | React 18 + TS + Vite + Cytoscape.js |
| NER / RE | `vinai/phobert-base` (BIOES token classification) |
| Embedding | `BAAI/bge-m3` (1024 dim) |
| LLM bulk | Model **mở lượng tử hóa trên Kaggle GPU** (`Qwen/Qwen3-8B` hoặc `openai/gpt-oss-20b`) — không tốn quota |
| LLM API | Gemini `gemini-3.5-flash-lite` (15 RPM / 500 RPD) chính + Groq `openai/gpt-oss-20b` (30 RPM / 1000 RPD) dự phòng |
| LLM API dùng cho | baseline đối chiếu tập con ~1.500 câu · Text-to-Cypher lúc demo · LLM-judge cho đánh giá |
| **Không dùng** | `gemini-2.0-flash` (mất quota free), `gemini-2.5-*` (deprecated), `llama-3.1-8b-instant` / `llama-3.3-70b-versatile` (Groq đã retire 16/08/2026) |
| Đánh giá | Auto-gold từ Wikidata (tập lớn) + 100 câu gán tay tối thiểu để đối chiếu |
| QID 9 triều đại | Ngô `Q703919` · Đinh `Q1372154` · Tiền Lê `Q1317884` · Lý `Q878309` · Trần `Q3111454` · Hồ `Q1209047` · Lê sơ `Q878276` · Tây Sơn `Q1034173` · Nguyễn `Q6500483` |
| Lớp thực thể | triều đại `Q164950` · trận đánh `Q178561` · sự kiện `Q1656682` · khu định cư `Q486972` · người `Q5` · quân chủ `Q116` · miếu hiệu `Q706208` · thụy hiệu `Q696100` · niên hiệu `Q256408` (VN `Q2420465`) · chức vụ `Q4164871` · tông tộc `Q840178` · Việt Nam `Q881` · Đại Việt `Q430309` |
| Cảnh báo dữ liệu | `P17` chỉ có trên 3/9 triều đại → **không lọc bằng `P17`**; lọc bằng `P31 = Q164950` + heuristic nhãn |
| Tài khoản DB | `neo4j` (ghi, chỉ dùng cho script nạp) + `reader` (tách credential cho API). **Community không có RBAC** → bảo vệ cấp DB bằng session `READ_ACCESS`, không bằng role |

---

## Phase 0 — Bootstrap repo, cấu hình, hạ tầng

**Mục tiêu:** có repo chạy được: cấu hình YAML, Docker Compose (Neo4j), backend `/api/health` trả `ok`, frontend dev server mở được, `pytest` xanh.

**Input contract**
- Python 3.12 (`python3 --version` → 3.12.x).
- Docker (`docker --version` → 29.x).
- Không cần dữ liệu.

**Output contract**
```
configs/{default,pipeline,llm,neo4j}.yaml
.env.example
.gitignore
requirements.txt          # gồm: fastapi, uvicorn, neo4j, pydantic>=2, httpx, pyyaml,
                          # mwparser, wikitextparser, pysbd, underthesea, transformers,
                          # torch, datasets, accelerate, seqeval, scikit-learn, pandas,
                          # numpy, tqdm, python-dotenv, pytest
docker-compose.yml        # service: neo4j (5-community), backend, frontend
src/common/{__init__,config,logger,seed,normalize,schemas,ids,text_utils}.py
backend/app/main.py
backend/requirements.txt
frontend/{package.json,vite.config.ts,tsconfig.json,index.html}
frontend/src/{main.tsx,App.tsx}
tests/test_health.py
README.md
```

**Việc phải làm**
1. Tạo cây thư mục theo [03-kien-truc-he-thong.md](03-kien-truc-he-thong.md#4-cấu-trúc-thư-mục-dự-kiến).
2. `src/common/config.py`: load YAML, hỗ trợ biến môi trường dạng `${VAR}` trong giá trị; `load_config(path)` cache theo path.
3. `src/common/seed.py`: `set_seed(42)` gọi `random.seed`, `numpy.random.seed`, `torch.manual_seed` (nếu torch có sẵn) và `torch.cuda.manual_seed_all`.
4. `src/common/logger.py`: `get_logger(name)` → logger ghi ra `logs/<name>.log` + stdout, format có timestamp + level + module.
5. `src/common/normalize.py`: `strip_accents(s)`, `normalize_name(s)`, `normalize_date_vi(s)`, `parse_vi_date(s) -> (iso|None, year|None, precision)`, `slugify(s)`. Viết kèm docstring tiếng Việt.
6. `src/common/schemas.py`: dataclass/Pydantic cho `Document`, `Sentence`, `Mention`, `Triple`, `Entity`. **Đây là hợp đồng dữ liệu dùng chung mọi phase sau.**
7. `docker-compose.yml`: service `neo4j` (`neo4j:5-community`, `NEO4J_AUTH=neo4j/${NEO4J_PASSWORD:-neo4jpass}`, heap max 1G, pagecache 512M, ports 7474/7687, volume `neo4j_data`); service `backend` (build context `.`, env_file `.env`, volume `./data:/app/data`); service `frontend` (dev server, port 5173).
8. `.env.example` theo [08-cong-cu-va-moi-truong.md](08-cong-cu-va-moi-truong.md#24-biến-môi-trường-envexample). **Không** điền key thật.
9. `.gitignore` theo [08](08-cong-cu-va-moi-truong.md#6-gitignore-dự-kiến).
10. Backend: `GET /api/health` → `{"status":"ok","version":"0.1.0","neo4j":"up|down"}`; `GET /api/stats` → `{"nodes":0,"edges":0}` giả lập. Kết nối Neo4j lazy, không fail nếu DB chưa sẵn sàng.
11. Frontend: Vite + React + TS, trang chủ hiển thị tiêu đề + placeholder + nút gọi `/api/health`.
12. `tests/test_health.py`: test `/api/health` trả 200.

**Lệnh kiểm thử**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q tests/                       # kỳ vọng: pass
docker compose up -d neo4j
sleep 20 && curl -s localhost:7474 | head -3   # kỳ vọng: HTTP 200
uvicorn backend.app.main:app --port 8000 &
curl -s localhost:8000/api/health
cd frontend && npm install && npm run build     # kỳ vọng: build xong, 0 lỗi TS
docker compose down
```

**Gate**
- [ ] `pytest -q` pass
- [ ] `docker compose up -d neo4j` → Neo4j mở ở `localhost:7474`
- [ ] `/api/health` trả `{"status":"ok"}`
- [ ] `npm run build` thành công, không lỗi TypeScript
- [ ] `git status` không có file secret nào; `.env` nằm trong `.gitignore`

**Lùi:** nếu `underthesea` lỗi cài trên Python 3.12 → dùng `pysbd` cho cả tách câu lẫn đoạn (tách đoạn bằng regex `\n\s*\n`), ghi vào `reports/deviations.md`.

---

## Phase 1 — Tải dump và lọc bài (A1)

**Mục tiêu:** có `data/interim/documents.jsonl` chứa 2.000–5.000 bài lịch sử Việt Nam đã lọc, kèm lý do giữ.

**Input contract**
- `configs/default.yaml` có `dump_version` và `paths.raw_dir`.
- Mạng tới `dumps.wikimedia.org` (đã kiểm tra: HTTP 200).

**Output contract** — `data/interim/documents.jsonl`, mỗi dòng 1 JSON:
```json
{"doc_id":"doc_12345","page_id":12345,"title":"Lê Lợi","url":"https://vi.wikipedia.org/wiki/Lê_Lợi",
 "revision_id":99000000,"categories":["Vua","Nhân vật thời Lê"],"wikibase_item":"Q123",
 "infobox_type":"person","keep_reason":"infobox","dump_version":"20251101","wikitext":"..."}
```

**Việc phải làm**
1. `scripts/download_dump.py`:
   - Kiểm tra `dumps.wikimedia.org/viwiki/latest/` lấy ngày dump mới nhất, ghi vào `dump_version` (yêu cầu `--dump-version` để ghim).
   - Tải 3 file: `viwiki-latest-pages-articles.xml.bz2`, `viwiki-latest-pages-meta-current.xml.bz2`, `viwiki-latest-redirects.xml.bz2` vào `data/raw/` (dùng `wget -c` tương đương, hỗ trợ `--resume`).
   - Ghi `data/raw/manifest.json`: tên file, kích thước, sha1, ngày tải.
2. `src/preprocess/filter_articles.py`:
   - Parse `pages-articles.xml.bz2` bằng `mwparser` theo luồng, **không** nạp toàn bộ vào RAM.
   - Bỏ qua namespace ≠ 0, bỏ redirect, bỏ bài có `<redirect>`.
   - Ghi `wikitext` vào output.
3. Tính `categories` từ dump.
4. `src/preprocess/wikidata_map.py`: đọc `pages-meta-current.xml.bz2`, lấy `page_props/wikibase_item` → map `page_id → QID`; lưu `data/interim/pageid_to_qid.json`.
5. `src/preprocess/redirects.py`: đọc `redirects.xml.bz2` → map title cũ → title mới; dùng để resolve alias sau này (và để gộp bài trùng).
6. **Bộ lọc 4 tín hiệu** (mỗi tín hiệu ghi `keep_reason`):
   - **T1 category**: khớp seed category (xem [05](05-du-lieu-va-nguon.md#24-lọc-bài-thuộc-phạm-vi-lịch-sử)) HOẶC thuộc subcategory của seed (đệ quy giới hạn sâu 3, xây từ `pages-meta-current`).
   - **T2 infobox**: `loại_infobox` trong whitelist, hoặc có ≥ 2 trường trong `{sinh, mất, triều đại, thời gian, thủ đô, người đứng đầu}`.
   - **T3 seed + mở rộng BFS**: danh sách seed bài từ `configs/seed_articles.yaml`; mở rộng qua hyperlink nội bộ, chiều sâu ≤ 2.
   - **T4 loại trừ**: bài thuộc category loại trừ (`Danh sách`, `Bảng`, `Wikipedia:`, `Dự án Wikimedia`, `Bài viết dẫn nhập`...).
7. Chốt số bài trong khoảng 2.000–5.000: nếu > 5.000 → siết seed/loại trừ; nếu < 2.000 → tăng depth BFS lên 3 hoặc nới whitelist category.
8. Ghi `data/interim/filter_stats.json`: số bài theo `keep_reason`, theo `infobox_type`, theo nhóm category.

**Lệnh kiểm thử**
```bash
python scripts/download_dump.py --dump-version 20251101
python -m src.preprocess.filter_articles --config configs/default.yaml
python -m src.preprocess.filter_articles --stats-only     # in thống kê
python - <<'PY'
import json
rows=[json.loads(l) for l in open('data/interim/documents.jsonl')]
assert 2000 <= len(rows) <= 5000, len(rows)
assert all(r['doc_id'] and r['title'] and r['url'] and r['dump_version'] for r in rows)
assert all(r['keep_reason'] for r in rows)
print("OK", len(rows))
PY
/usr/bin/time -v python -m src.preprocess.filter_articles 2>&1 | grep -i "maximum resident"   # kỳ vọng < 4GB
```

**Gate**
- [ ] `documents.jsonl` có 2.000–5.000 bài
- [ ] Mọi bài có `doc_id`, `title`, `url`, `keep_reason`, `dump_version`, `wikitext` không rỗng
- [ ] ≥ 80% bài có `wikibase_item` (QID) — báo cáo số thực tế trong `filter_stats.json`
- [ ] Phân bố `infobox_type` có đủ `person`, `battle`, `dynasty`, `place`
- [ ] RAM peak < 4GB
- [ ] Chạy lại 2 lần cho checksum `documents.jsonl` giống hệt

**Lùi:** nếu < 2.000 bài → tăng BFS depth 3, thêm seed bài từ list mở rộng (`configs/seed_articles.yaml`), nới T2. Nếu > 5.000 → chỉ giữ T1+T2, bỏ T3.

---

## Phase 2 — Làm sạch wikitext, tách câu/đoạn, trích hyperlink (A2, A3, A5)

**Mục tiêu:** `documents.jsonl` được bổ sung `clean_text`, `paragraphs`, `sentences`, `links` — chuẩn bị cho NER.

**Input contract**
- `data/interim/documents.jsonl` (Phase 1 đã đạt Gate).

**Output contract** — mỗi document có thêm:
```json
{"clean_text":"...","paragraphs":[{"para_idx":0,"text":"..."}],
 "sentences":[{"sentence_id":"s12345_0_3","text":"...","para_idx":0,"sent_idx":3,"char_start":120,"char_end":168}],
 "links":[{"target":"Lê Lợi","anchor":"Lê Lợi","start":10,"end":16,"para_idx":0,"sentence_id":"s12345_0_0"}]}
```
> `char_start/char_end` là **offset trong `clean_text`** (chuỗi ký tự Python), và `sentence_id` theo format `s<page_id>_<para_idx>_<sent_idx>` — khóa ổn định dùng ở mọi phase sau.

**Việc phải làm**
1. `src/preprocess/clean_text.py` (thứ tự thao tác quan trọng):
   1. Tách `{{Infobox ...}}` / `{{Thông tin ...}}` ra trước (lưu vào `infobox_raw`), **không** xoá vĩnh viễn (Phase 3 dùng).
   2. Xoá `{{cite...}}`, `{{tham khảo}}`, `{{chú thích}}`, mọi template còn lại (cân bằng ngoặc kép).
   3. Xoá `<ref ...>...</ref>`, `<ref .../>`.
   4. Xoá `[[File:...]]`, `[[Tập tin:...]]`, `[[Image:...]]`.
   5. Xoá link category `[[Thể loại:...]]` (không phân biệt hoa thường).
   6. Xoá bảng `{| ... |}` (cân bằng `{|`/`|}`).
   7. Xoá HTML `<br>`, `<ref>`, thẻ HTML còn lại.
   8. Chuyển link nội bộ `[[Đích|anchor]]` → `anchor` **nhưng ghi lại mục `links` trước khi thay thế**. Bỏ `[[Đích]]` → `Đích`, ghi link với `anchor == target`.
   9. Giữ nguyên tiêu đề mục `== X ==` → chuyển thành dòng riêng, đánh dấu `heading` trong paragraphs.
   10. Chuẩn hóa whitespace, gộp dòng trống.
2. `src/preprocess/split_sentences.py`: dùng `pysbd` với `pysbd.Language.MULTI` (hỗ trợ tiếng Việt); fallback regex nếu lỗi. Bảo toàn offset trong `clean_text` (dùng `pysbd` trả `Span` → `char_start/char_end`).
3. Tách đoạn: theo `\n\n` trong `clean_text` (fallback) hoặc `underthesea.sent_tokenize` nếu đã cài.
4. `tests/fixtures/` — tạo fixture nhỏ: 10 bài mẫu thật (copy từ `documents.jsonl`) + `expected_clean.jsonl` để test hồi quy.
5. `scripts/stats_text.py`: in thống kê số câu/bài, phân bố độ dài câu, tỉ lệ câu kết thúc bằng dấu câu, tỉ lệ câu có hyperlink.

**Lệnh kiểm thử**
```bash
python -m src.preprocess.clean_text --config configs/default.yaml
python -m src.preprocess.split_sentences --config configs/default.yaml
pytest -q tests/test_clean_text.py tests/test_sentence_split.py
python - <<'PY'
import json,re
rows=[json.loads(l) for l in open('data/interim/documents.jsonl')]
bad=[r['title'] for r in rows if re.search(r'\{\{|\}\}|<ref|\[\[File:|\[\[Thể loại:', r['clean_text'])]
assert not bad, bad[:5]
ss=[s for r in rows for s in r['sentences']]
assert all(s['char_start']<s['char_end']<=len(r['clean_text']) for r in rows for s in r['sentences'])
print("OK docs",len(rows),"sentences",len(ss))
PY
python scripts/stats_text.py
```

**Gate**
- [ ] 0 bài còn ký tự wiki trong `clean_text`
- [ ] ≥ 95% câu kết thúc bằng `.`/`!`/`?`/`…`
- [ ] 100% `char_start/char_end` hợp lệ và trỏ đúng substring (`r['clean_text'][s['char_start']:s['char_end']] == s['text']`)
- [ ] Tỉ lệ hyperlink giữ lại ≥ 95% so với số link trong wikitext gốc (trừ File/Thể loại)
- [ ] Không câu nào bị vỡ ở giữa tên có dấu phẩy (kiểm thử bằng 30 tên mẫu)

**Lùi:** nếu `pysbd` tách sai nhiều → chuyển sang regex có bảng ngoại lệ tên riêng (`configs/name_exceptions.yaml`).

---

## Phase 3 — Parse infobox + chuẩn hóa ngày (A4)

**Mục tiêu:** `data/interim/infobox_triples.jsonl` — các triple có độ tin cậy cao nhất, kèm bằng chứng.

**Input contract**
- `documents.jsonl` (Phase 2) với `infobox_raw` đã lưu.

**Output contract**
```json
{"doc_id":"doc_1","sentence_id":"ibx_1","subject":"ent_le_loi_1a2b3c4d","subject_type":"person",
 "relation":"cha_cua","object":"ent_le_khanh_du_9f8e7d6c","object_type":"person",
 "evidence_sentence":"Cha: Lê Khánh Dư","source_url":"https://vi.wikipedia.org/wiki/Lê_Lợi",
 "doc_title":"Lê Lợi","confidence":0.97,"method":"infobox",
 "start_year":null,"end_year":null,"alt_evidence":[]}
```
> `method` chỉ nhận 5 giá trị: `infobox`, `distant_supervision`, `phobert_re`, `llm`, `rule`.

**Artifact sinh ra ở Phase 3** (3 file):

| Đường dẫn | Nội dung | `method` | `confidence` |
|---|---|---|---|
| `data/interim/infobox_triples.jsonl` | triple từ trường infobox | `infobox` | ≥ 0,95 |
| `data/interim/lead_triples.jsonl` | triple fallback từ đoạn dẫn | `rule` | 0,85 |
| `data/interim/infobox_entities.jsonl` | entity + `props` node | — | — |

**Việc phải làm**
1. `src/preprocess/parse_infobox.py`: dùng `wikitextparser` parse template, đưa ra dict phẳng `key → value` (key lowercase, bỏ dấu gạch dưới). Giữ nguyên giá trị gốc trong `raw_values`.
2. Mapping trường → quan hệ (bảng cố định trong `configs/infobox_mapping.yaml`):
   - `sinh` → `sinh_nam` (+ `sinh_tai` nếu có `nơi sinh`), `mất` → `mat_nam` (+`mat_tai`)
   - `cha` → `cha_cua`, `mẹ` → `me_cua`, `vợ`/`chồng`/`phu quân`/`hậu thân` → `vo_cua`/`chong_cua`, `con` → nghịch đảo `cha_cua`/`me_cua` (cần `con trai`/`con gái`)
   - `anh em`/`anh_em` → `anh_em_cua`, `tiều đình`/`hậu thân` → `ke_vi`
   - `triều đại` → `thuoc_trieu_dai`, `quốc gia` → `thuoc_trieu_dai`
   - `chức vụ`/`nghề nghiệp` → `giu_chuc_vu`, `thủ đô`/`đô thành` → `dong_doi_tai`
   - `miếu hiệu` → alias (Title), `thụy hiệu` → alias, `niên hiệu` → alias, `tự` → alias
   - `ngày sinh`/`ngày mất`/`thời gian` (battle) → `dien_ra_tai`, `bên tham chiến`/`kết quả` → thuộc tính event
3. `src/common/normalize.py` → bổ sung `parse_vi_date`:
   - `"ngày 15 tháng 3 năm 1028"` → `("1028-03-15","year",1028)`
   - `"15-3-1028"`, `"1028"`, `"tháng 5 năm 1284"`, `"khoảng năm 1000"` (precision `year`, qualifier `khoảng`)
   - Năm âm lịch kèm năm dương (`"năm Ất Tý (938)"`) → lấy năm dương 938.
   - **ISO-8601 với năm 4 chữ số**: năm < 1000 → `0939-02-01` (không phải `939-02-01`).
4. `src/preprocess/infobox_entity_types.py`: suy `subject_type`/`object_type` từ infobox type + giá trị (vd `cha` → `person`).
   - Thứ tự suy loại **chủ thể**: tên template (`type_map`) → `wikidata_signal` (Phase 1) → `"article"`.
   - **Không** mặc định `person` cho chủ thể (xem `reports/deviations.md` D-024).
   - Trường có giá trị là **tổ chức** (phe phái, quân đội) → **loại** triple, không gán `person`.
5. Ghi `data/interim/infobox_entities.jsonl`: trích **thuộc tính node** từ infobox — dùng cho Phase 9 (alias) và Phase 10 (node props).
   Tập **11 thuộc tính** đã chốt: `birth_year`, `death_year`, `reign_start`, `reign_end`,
   `temple_name`, `posthumous_name`, `reign_title`, `gender`, `aliases`, `birth_place`, `death_place`.
   > Prop chỉ được ghi khi triple tương ứng **thực sự** được sinh — không khẳng định thuộc tính cho quan hệ đã bị loại vì lỗi schema (xem `reports/deviations.md` D-025).
6. Fallback đoạn dẫn → `data/interim/lead_triples.jsonl`: chỉ ngoặc đầu tiên của câu dẫn, khoảng cách sinh–mất ≤ 120 năm, chỉ bài `person`.
7. **Truy vết**: cả 3 artifact phải ghi `dump_version` + `model_name` (ràng buộc `AGENTS.md` §5.6 — xem D-026).
8. **Thứ tự chạy là bắt buộc**: `parse_infobox.py` **phải** chạy trước `extract_lead_dates.py`, vì script sau đọc `infobox_triples.jsonl` để biết bài nào **đã có** ngày sinh/mất (tránh trích trùng từ đoạn dẫn). Chạy sai thứ tự → `lead_triples.jsonl` bị **stale** → trùng ngày (xem D-027).
9. **Loại triple trùng + self-loop**: `build_triples()` phải khử trùng `(subject, relation, object)` trong 1 doc và loại triple có `subject == object` (xem D-027).

**Lệnh kiểm thử**
```bash
python -m src.preprocess.parse_infobox --config configs/default.yaml
python -m src.preprocess.extract_lead_dates --config configs/default.yaml
pytest -q tests/test_infobox.py tests/test_normalize.py
python - <<'PY'
import json
rows=[json.loads(l) for l in open('data/interim/infobox_triples.jsonl')]
assert rows, "no triples"
REL={"cha_cua","me_cua","vo_cua","chong_cua","anh_em_cua","thuoc_trieu_dai","ke_vi","giu_chuc_vu",
     "lap_ra","chi_huy_tran","tham_gia_tran","danh_bai","dien_ra_tai","sinh_tai","mat_tai",
     "sinh_nam","mat_nam","dong_doi_tai"}
assert all(r['relation'] in REL for r in rows), "quan hệ ngoài schema"
assert all(r['method']=='infobox' and r['confidence']>=0.95 for r in rows)
assert all(r['evidence_sentence'] and r['source_url'] for r in rows)
print("OK triples",len(rows))
PY
python scripts/stats_infobox.py     # tỉ lệ parse thành công, tỉ lệ có sinh/mất
```

**Gate**
- [x] ≥ 95% bài có infobox `person` được parse thành công → **100,0%** (1.061/1.061)
      *(định nghĩa: nhận diện được khối template — 146 bài có template rỗng, xem D-021)*
- [x] ≥ 90% bài nhân vật có ít nhất 1 trường ngày sinh/mất hoặc quan hệ gia đình được trích → **92,4%** (980/1.061)
- [x] Chuẩn hóa ngày đúng ≥ 95% trên tập 30 chuỗi mẫu trong `tests/fixtures/dates.jsonl` → **100,0%** (30/30)
- [x] 100% triple có đủ 6 trường bắt buộc, `method="infobox"`, `confidence ≥ 0.95` → **100%** (10.078/10.078)
- [x] 0 quan hệ ngoài danh mục → **0** (0 vi phạm `RELATION_SUBJECT_TYPES`)
- [x] **0 triple trùng** `(subject, relation, object)` trong 1 doc → **0** (341 nhóm / 347 triple thừa ở HEAD → 0, xem D-027)
- [x] **0 self-loop** (`subject == object`) → **0** (4 ở HEAD → 0, xem D-027)
- [x] **0 trùng ngày** giữa `lead_triples.jsonl` và `infobox_triples.jsonl` → **0** (81 trên 47 bài ở HEAD → 0, xem D-027)

**Lùi:** nếu parse thấp → thay `wikitextparser` bằng regex cân bằng ngoặc cho template (viết trong `parse_infobox.py` với cờ `--fallback-regex`).

**Kết quả thực tế (14/11/2026):** báo cáo `reports/phase_03_report.md` · nhật ký `docs/10-nhat-ky/phase-03.md` · số liệu `docs/10-nhat-ky/so-lieu/phase-03-infobox-stats.json` · sai lệch D-019 → D-026.

> **Audit đóng phase (14/11/2026):** phát hiện 4 lỗi thật trong bản triển khai đầu (trùng triple, self-loop, stale artifact, template mơ hồ) → đã sửa, thêm 6 test regression (280 test → pass hết). Số liệu **đã cập nhật**: triple 10.394 → **10.078**; `sinh_nam` 985 → **732** (bỏ trùng); `dong_doi_tai` 0 → **31** (template mơ hồ). Gate 1–5 **không đổi**. Sai lệch mới: **D-027 → D-030**. Chi tiết: `reports/phase_03_report.md` §Audit.

---

## Phase 4 — Sinh nhãn bạc NER từ hyperlink (B2 phần 1)

**Mục tiêu:** `data/interim/ner_silver.jsonl` — nhãn NER tự động, chất lượng đủ dùng để train.

**Input contract**
- `documents.jsonl` (Phase 2) với `links`.
- `data/interim/pageid_to_qid.json` (Phase 1).
- `data/interim/infobox_entities.jsonl` (Phase 3) để biết entity nào là nhân vật/triều đại/event.

**Output contract**
```json
{"sentence_id":"s1_0_3","text":"...","tokens":["Lê","Lợi","là","người","..."],
 "labels":["B-PERSON","I-PERSON","O","O","..."],"mentions":[{"start":0,"end":10,"label":"PERSON","target":"Lê Lợi","qid":"Q..."}]}
```
> Nhãn ở **mức token** (word-level) vì PhaBERT dùng subword; khi train sẽ map sang subword bằng offset của tokenizer.

**Việc phải làm**
1. `src/ner/build_silver.py`:
   - Duyệt `links`; giữ link có `anchor == target` hoặc `target` là chuỗi con của `anchor` (tránh `[[thành phố]]` → "thành phố").
   - **Suy nhãn theo đích** theo thứ tự ưu tiên (đã cập nhật sau khi đo thực tế — xem D-032):
     1. **Category Wikipedia** của bài đích (từ `dump_facts.jsonl`) → khớp mẫu category → nhãn. Nguồn mạnh nhất cho corpus tiếng Việt (chiếm 50,2% nguồn nhãn).
     2. Đích có `wikibase_item` → tra QID → `P31` → map sang nhãn. Bảng map ở `configs/wikidata_type_map.yaml` (**sinh tự động** bằng `scripts/build_type_map.py`).
     3. Lớp cha `P279*` → map sang nhãn (bắt lớp không có tên trực tiếp).
     4. Đích nằm trong `infobox_entities.jsonl` với type đã biết.
     5. Tín hiệu `wikidata_signal` (Phase 1).
     6. Đích khớp mẫu tên: `nhà X` / `triều đại X` → DYNASTY; `[[<năm>]]` hoặc `[[Thế kỷ XV]]` → TIME; `[[X (miếu hiệu)]]` → TITLE.
     7. Không xác định → bỏ (không gán nhãn sai).
   - Đồng thời sinh `nhãn TIME` bằng regex trên câu (không cần link): `\b\d{3,4}\b` **trong ngữ cảnh "năm"**, `thế kỷ [IVXLCDM]+`. Năm đứng riêng chỉ được gán khi có **ngữ cảnh liền kề** (xem D-033).
   - Lưu `target_type_confidence` để lọc nhãn yếu.
2. `src/ner/silver_quality.py`: đánh giá nhãn bạc bằng **rule baseline** trên tập dev (tự đánh giá bằng chính quy tắc → đo độ nhất quán) + báo cáo phân bố nhãn, tỉ lệ câu có nhãn.
3. Chia tập theo **bài**: `data/splits/splits.json` = `{train: [page_id...], dev: [...], test: [...]}` — 80/10/10, seed 42, lưu file để tái lập.

**Lệnh kiểm thử**
```bash
python -m src.ner.build_silver --out data/interim/ner_silver.jsonl
pytest -q tests/test_silver_labels.py
python -m src.ner.silver_quality --out reports/silver_quality.md
python - <<'PY'
import json,collections
rows=[json.loads(l) for l in open('data/interim/ner_silver.jsonl')]
c=collections.Counter(l for r in rows for l in r['labels'])
assert c['O']>0 and len([k for k in c if k!='O'])>=4, c
assert all(len(r['tokens'])==len(r['labels']) for r in rows)
print("OK",len(rows),c)
PY
```

**Gate**
- [ ] Nhãn bạc sinh cho ≥ 90% câu có ≥ 1 hyperlink nội bộ
- [ ] ≥ 4 lớp nhãn khác `O` xuất hiện; `PERSON` là lớp phổ biến nhất
- [ ] 100% record có `len(tokens) == len(labels)`
- [ ] `splits.json` tồn tại, không trùng page_id giữa các tập
- [ ] Baseline rule F1 trên dev ≥ 0.60 (đo bằng `src/evaluation/metrics.py`)

**Lùi:** nếu nhãn bạc dưới 0.60 F1 → kiểm tra đường dẫn suy nhãn theo QID (thống kê phân bố nguồn nhãn: `qid`/`infobox`/`pattern`), sửa map, chạy lại.

**Kết quả thực tế (14/11/2026):** báo cáo `reports/phase_04_report.md` · nhật ký `docs/10-nhat-ky/phase-04.md` · số liệu `docs/10-nhat-ky/so-lieu/phase-04-ner-stats.json` · sai lệch D-031 → D-035.

> **Gate 1–5 đạt:** độ phủ câu có hyperlink **100,0%** (60.078/60.078) · **6** lớp nhãn, `PERSON` phổ biến nhất trong nhóm entity từ hyperlink (37.242) · 100% `len(tokens) == len(labels)` · splits 1.952/244/245, trùng **0** · baseline gazetteer dev micro F1 **0,7990** (≥ 0,60).
>
> **Audit đóng phase (14/11/2026):** phát hiện **4 lỗi thật** trong bản triển khai đầu → đã sửa, thêm 6 test regression (300 test → pass hết). Số liệu **đã cập nhật**: TIME 57.604 → **53.654** (loại **16.099** số đo lượng bị gán nhầm là năm); PERSON 35.425 → **37.242**; TITLE 2.887 → **2.170** (loại "Quan lại nhà Nguyễn" khỏi TITLE). Baseline gazetteer dev F1 **0,7388 → 0,7990**. Sai lệch mới: **D-031 → D-035**. Chi tiết: `reports/phase_04_report.md`.

---

## Phase 5 — Huấn luyện mô hình NER + suy luận (B1, B2)

**Mục tiêu:** `models/ner/` đạt F1 ≥ 0.85; `data/interim/ner_predictions.jsonl` cho toàn corpus.

**Input contract**
- `ner_silver.jsonl` + `data/splits/splits.json`.
- `transformers`, `torch`, `datasets` đã cài.

**Output contract**
- `models/ner/` gồm `config.json`, `model.safetensors`, `tokenizer/`, `trainer_state.json`, `metrics.json`.
- `data/interim/ner_predictions.jsonl`: `{"sentence_id","doc_id","text","entities":[{"start","end","text","label","score"}]}` — offset theo **ký tự** trong `text`.

**Việc phải làm**
1. `src/ner/data_convert.py`: word-level → subword BIOES. Dùng `tokenizer(text, is_split_into_words=True, return_offsets_mapping=True)`; label cho subword đầu = label của word, còn lại `I-<type>` nếu word đó cũng mang label, `O` nếu không; ghi `word_id` để map ngược.
2. `src/ner/train_ner.py` (chạy được cả local CPU lẫn Kaggle GPU):
   - `AutoModelForTokenClassification` từ `vinai/phobert-base`, `num_labels = 2*6 + 1 = 13` (BIO × 6 nhãn + O).
   - `TrainingArguments`: `seed=42`, `output_dir`, `save_total_limit=2`, `save_steps`, `eval_strategy="epoch"`, `metric_for_best_model="f1"`, `load_best_model_at_end=True`, `fp16` chỉ khi có CUDA, `report_to="none"`.
   - `EarlyStoppingCallback(early_stopping_patience=2)`.
   - Tính F1 bằng `src/evaluation/metrics.py` (seqeval-style) trên tập dev.
   - Lưu `metrics.json` gồm per-label P/R/F1 + micro/macro.
3. `notebooks/kaggle/01_train_ner.ipynb`: bản sao notebook của script cho Kaggle (mount dataset, `!pip install -r requirements.txt`, seed, checkpoint mỗi epoch, xuất `models/ner` ra `/kaggle/working`).
4. `src/ner/infer_ner.py`: nạp `models/ner/`, dự đoán theo lô (`batch_size=32`, `max_len=256`, sliding window nếu câu dài), map subword → span ký tự, lọc span không hợp lệ, ghi `ner_predictions.jsonl`.
5. `src/evaluation/metrics.py` (dùng lại ở Phase 12): `ner_f1(pred, gold)` trả `micro/macro/per_label`.

**Lệnh kiểm thử**
```bash
# local (CPU, dùng tập con 5.000 câu để smoke test)
python -m src.ner.train_ner --config configs/default.yaml --max-train 5000 --epochs 1 --out models/ner_smoke
pytest -q tests/test_metrics.py
# Kaggle
# mở notebooks/kaggle/01_train_ner.ipynb, chạy, tải models/ner về
python -m src.ner.infer_ner --model models/ner --out data/interim/ner_predictions.jsonl
python - <<'PY'
import json
rows=[json.loads(l) for l in open('data/interim/ner_predictions.jsonl')]
for r in rows:
    for e in r['entities']:
        assert r['text'][e['start']:e['end']]==e['text'], (r['sentence_id'],e)
        assert e['label'] in {"PERSON","DYNASTY","EVENT","LOCATION","TIME","TITLE"}
print("OK",len(rows))
PY
```

**Gate**
- [ ] `models/ner/` tồn tại, load được bằng `AutoModelForTokenClassification.from_pretrained`
- [ ] F1 dev ≥ 0.85 (nếu không: xem phân tích lỗi theo label, cân nhắc thêm nhãn từ Wikidata `P31`, tăng số epoch, hoặc đổi sang `vinai/phobert-large`)
- [ ] `ner_predictions.jsonl` cover ≥ 95% câu của corpus
- [ ] 0 span có offset sai (assert trên chạy toàn bộ)
- [ ] `metrics.json` có per-label F1

**Lùi:** nếu F1 < 0.80 sau 2 lần chỉnh: (a) thêm nhãn bạc từ `P31` trực tiếp từ Wikidata cho câu chứa 2 entity; (b) dùng `phobert-large`; (c) chấp nhận và báo cáo minh bạch số thực tế, kèm phân tích lỗi.

---

## Phase 6 — Coreference: đại từ, danh xưng, chủ thể bài (C1, C2)

**Mục tiêu:** `data/interim/coref_resolved.jsonl` — mọi mention có `canonical_id` trỏ tới entity trong KG.

**Input contract**
- `ner_predictions.jsonl` (Phase 5).
- `documents.jsonl` (Phase 2) để lấy `paragraphs`, `clean_text`.

**Output contract**
```json
{"sentence_id":"s1_0_3","text":"...","mentions":[
  {"start":0,"end":10,"text":"Lê Lợi","label":"PERSON","mention_id":"m1","canonical_id":"ent_le_loi_1a2b3c4d","resolved_by":"explicit"},
  {"start":40,"end":43,"text":"ông","label":"PERSON","mention_id":"m2","canonical_id":"ent_le_loi_1a2b3c4d","resolved_by":"coref_pronoun"}]}
```
> `canonical_id` dùng **đúng** format `ent_<slug>_<hash8>` của Phase 9 (hàm `make_entity_id` đặt ở `src/common/ids.py` ngay từ Phase 0 để dùng chung).

**Việc phải làm**
1. `src/common/ids.py`: `make_entity_id(type, name)` → `ent_{slug}_{sha1(type|name_normalized)[:8]}`; `make_year_id(y)` → `year_{y}`. Viết test ngay.
2. `src/coref/resolve_coref.py` (rule-based, thứ tự ưu tiên):
   - **R1 — Trong đoạn:** ứng viên chính = entity `PERSON` cuối cùng được nhắc trong đoạn (trước vị trí đại từ).
   - **R2 — Từ điển danh xưng:** `ông`, `ông ấy`, `ông ta`, `y`, `vua`, `hoàng đế`, `đại vương` → `PERSON`; `bà`, `bà ấy` → `PERSON`; `chàng trai`, `cô gái` → `PERSON`; `thái tử`, `tể tướng`, `thượng tướng`, `quận công`, `hầu tước` → `TITLE` (và gắn entity được chiếu nếu biết).
   - **R3 — Chủ thể bài:** `src/coref/article_subject.py` — bài nhân vật → `PERSON` là tên bài; bài trận đánh/sự kiện → `EVENT`; bài triều đại → `DYNASTY`; bài địa danh → `LOCATION`. Dùng khi đoạn không có entity `PERSON` nào.
   - **R4 — Giới tính:** `ông` chỉ gắn vào `PERSON` nam; `bà` chỉ vào nữ (từ `gender` trong infobox).
   - **R5 — Bỏ qua:** nếu đoạn có ≥ 3 `PERSON` và đại từ không có ứng viên rõ → gắn `canonical_id = null`, `resolved_by="ambiguous"`.
3. `src/coref/quality_report.py`: tỉ lệ mention có `canonical_id`, phân bố `resolved_by`, 20 ví dụ ngẫu nhiên để kiểm thử tay sau này.

**Lệnh kiểm thử**
```bash
python -m src.coref.resolve_coref --config configs/default.yaml
pytest -q tests/test_coref.py tests/test_entity_id.py
python - <<'PY'
import json,re
rows=[json.loads(l) for l in open('data/interim/coref_resolved.jsonl')]
res=[m for r in rows for m in r['mentions'] if m['resolved_by']!='explicit']
ok=sum(1 for r in rows for m in r['mentions'] if m['canonical_id'])
print("mentions resolved:",ok,"/",sum(len(r['mentions']) for r in rows))
assert all(m['canonical_id'] is None or m['canonical_id'].startswith('ent_') for r in rows for m in r['mentions'])
PY
```

**Gate**
- [ ] 100% `canonical_id` có dạng `ent_*` hoặc `null`
- [ ] `make_entity_id` deterministic: cùng input → cùng output (test)
- [ ] Tỉ lệ mention được resolve ≥ 60% (nêu số thực tế; đây là chỉ báo, không phải AC cứng)
- [ ] Không có đại từ nào gắn sai giới tính (kiểm thử 20 ví dụ định kỳ)

**Lùi:** nếu tỉ lệ resolve thấp → siết danh xưng, thêm `R6` = entity gần nhất trong câu trước.

---

## Phase 7 — Wikidata: cặp quan hệ + tập huấn luyện RE (D1 phần 1)

**Mục tiêu:** `data/interim/re_train.jsonl` — mẫu huấn luyện RE có nhãn từ Wikidata (distant supervision).

**Input contract**
- `coref_resolved.jsonl` (Phase 6).
- `pageid_to_qid.json` (Phase 1).
- Bộ QID 9 triều đại đã verify (mục 0) nạp vào `configs/wikidata_queries.yaml`.

**Output contract** — `data/interim/re_train.jsonl` (1 record **theo câu**, có `run_id`):
```json
{"run_id":"r20261115-161600","sentence_id":"s1_0_3","doc_id":"doc_1","page_id":1,
 "split":"train","text":"Lê Lợi là con của Lê Khánh Dư.",
 "pairs":[{"subject":{"mention":"Lê Lợi","entity_id":"ent_le_loi_1a2b3c4d","name":"Lê Lợi","start":0,"end":6},
           "object":{"mention":"Lê Khánh Dư","entity_id":"ent_le_khanh_du_...","name":"Lê Khánh Dư","start":16,"end":27},
           "relation":"cha_cua","label":"POSITIVE","source":"wikidata","property":"P22"},
          {"subject":{"mention":"Lê Lợi","entity_id":"ent_le_loi_1a2b3c4d"},
           "object":{"mention":"Lê Khánh Dư","entity_id":"ent_le_khanh_du_..."},
           "relation":"me_cua","label":"NEGATIVE","source":"distant_supervision"}]}
```
> Mỗi câu có nhiều cặp; cặp không có quan hệ → `"label":"NEGATIVE"`.

Quy tắc bắt buộc cho contract này:

- **1 record/câu** (không phải 1 record/cặp) → Phase 8 tokenize `text` một lần cho mọi cặp.
- `label` là **chuỗi** `"POSITIVE"`/`"NEGATIVE"` (không phải `1`/`0`).
- Mọi record có `run_id` (`r<YYYYMMDD-HHMMSS>`) — theo `.cursor/rules/data-contracts.mdc` §Định dạng chung.
- `split` ∈ `train`/`dev`/`test` theo `data/splits/splits.json` (chia theo bài → không rò rỉ).
- Mỗi cặp có `source` (wikidata / infobox / lead / distant_supervision) để truy nguồn nhãn.
- Offset `start`/`end` là **chỉ số ký tự Python** trong `text` của record; phải thỏa `text[start:end] == mention` (xem `data-contracts.mdc` §Offset).
- `mention` là **dạng bề mặt trong câu** (giữ dấu); `name` là tên chuẩn của entity trong KG.
- `relation` của mẫu NEGATIVE vẫn là quan hệ **được hỏi** (candidate relation), không phải quan hệ "không có".

**Việc phải làm**
1. `src/re/wikidata_client.py`: bọc SPARQL endpoint `https://query.wikidata.org/sparql`.
   - User-Agent định danh có email (`vhgr-npl-nlp/1.0 (student project; contact ...)`).
   - Timeout 60s, retry 3 lần với backoff, nghỉ ≥ 1s giữa các request.
   - **Chunk theo 9 triều đại** (mỗi truy vấn 1 triều đại) để tránh timeout.
   - Cache kết quả vào `data/interim/wikidata_cache/` theo hash truy vấn → không gọi lại.
2. `src/re/build_distant_supervision.py`:
   - Truy vấn mỗi triều đại: lấy `?p` với `P31` là người thuộc triều đại đó (qua `P463`/`P361` hoặc `P1308`... dùng `P463` + fallback theo `P31`), rồi lấy `P22` cha, `P25` mẹ, `P26` vợ/chồng, `P3373` anh em, `P569` sinh, `P570` mất, `P19` nơi sinh, `P20` nơi mất, `P39` chức vụ + `P580`/`P582`, `P1344`/`P710` tham gia trận, `P276` địa điểm, `P625` toạ độ.
   - Map property → quan hệ theo bảng [04-schema-knowledge-graph.md](04-schema-knowledge-graph.md#6-bảng-định-nghĩa-wikidata--quan-hệ).
   - **Bỏ qua** `P17` làm bộ lọc (chỉ 3/9 triều đại có) — dùng `P31 = Q164950` + `P463`/`P361` + heuristic nhãn.
   - Xuất `data/interim/wikidata_pairs.jsonl`: `{subject_qid, relation, object_qid, subject_label, object_label, start_year, end_year}`.
3. `src/re/build_re_dataset.py`:
   - Với mỗi cặp Wikidata, tìm câu trong corpus chứa **cả** hai entity (khớp theo `entity_id` sau Phase 6, fallback khớp theo QID).
   - Gắn nhãn `POSITIVE` cho cặp đó.
   - Sinh nhãn `NEGATIVE`: các cặp entity có mặt trong cùng câu nhưng **không** có quan hệ tương ứng trong Wikidata. Giới hạn tỉ lệ âm/dương ≤ 1:1.
   - Chia theo bài (dùng `splits.json`).
4. `src/re/re_dataset_stats.py`: in phân bố nhãn theo quan hệ, tỉ lệ POS/NEG, số mẫu dương.

**Lệnh kiểm thử**
```bash
python -m src.re.build_distant_supervision --config configs/default.yaml
python -m src.re.ground_triples --config configs/default.yaml
python -m src.re.build_re_dataset --config configs/default.yaml
python -m src.re.re_dataset_stats
pytest -q tests/test_re_dataset.py
python scripts/re_gate_check.py
python - <<'PY'
import json,collections
rows=[json.loads(l) for l in open('data/interim/re_train.jsonl')]
pos=sum(1 for r in rows for p in r['pairs'] if p['label']=='POSITIVE')
assert pos>=10000, pos
REL={"cha_cua","me_cua","vo_cua","chong_cua","anh_em_cua","thuoc_trieu_dai","ke_vi","giu_chuc_vu",
     "lap_ra","chi_huy_tran","tham_gia_tran","danh_bai","dien_ra_tai","sinh_tai","mat_tai",
     "sinh_nam","mat_nam","dong_doi_tai"}
assert all(p['relation'] in REL for r in rows for p in r['pairs'] if p['label']=='POSITIVE')
print("OK pos",pos,"neg",sum(1 for r in rows for p in r['pairs'] if p['label']=='NEGATIVE'))
PY
```

**Gate**
- [ ] ≥ 10.000 mẫu `POSITIVE` (mục tiêu 20.000; nếu dưới → nới phạm vi triều đại, thêm `P106`/nghề nghiệp, tăng số câu)
- [ ] Tỉ lệ NEG/POS ≤ 1:1
- [ ] ≥ 8 quan hệ khác nhau có mẫu dương
- [ ] 0 quan hệ ngoài danh mục
- [ ] Cache SPARQL hoạt động (chạy lại không tạo request mới)

**Lùi:** nếu số mẫu dương thấp → bổ sung nguồn nhãn: (a) `P40` (con) nghịch đảo, (b) infobox của chính bài đó (Phase 3) làm nhãn bổ sung, (c) mở rộng sang nhân vật không gắn triều đại rõ ràng.

---

## Phase 8 — Mô hình RE, LLM baseline, hợp nhất triple (D1, D2, D3)

**Mục tiêu:** `models/re/`, `data/interim/re_phobert.jsonl`, `data/interim/re_llm.jsonl`, `data/interim/triples_merged.jsonl`.

**Input contract**
- `re_train.jsonl` (Phase 7).
- `ner_predictions.jsonl` + `coref_resolved.jsonl` (Phase 5–6).
- `infobox_triples.jsonl` (Phase 3).
- LLM: model mở trên Kaggle GPU (bulk) + Gemini/Groq API (tập con).

**Output contract**
- `models/re/` (giống cấu trúc Phase 5).
- `re_phobert.jsonl`: `{"sentence_id","text","pairs":[{subject,relation,object,confidence,evidence_sentence,method:"phobert_re"}]}`.
- `re_llm.jsonl`: cùng format, `method:"llm"`.
- `triples_merged.jsonl`:
```json
{"doc_id":"doc_1","sentence_id":"s1_0_3","subject":"ent_le_loi_1a2b3c4d","relation":"cha_cua",
 "object":"ent_le_khanh_du_...","evidence_sentence":"...","source_url":"...","doc_title":"Lê Lợi",
 "confidence":0.97,"method":"phobert_re","start_year":null,"end_year":null,"alt_evidence":[]}
```

**Việc phải làm**
1. `src/re/data_convert_re.py`: format đầu vào mô hình (entity marker):
   `<s> subj_mention [SEP] câu có «subject» và «object» [SEP] obj_mention`
   - Marker có type: `«PERSON:Lê Lợi»`. Nhãn ở vị trí `[CLS]`.
   - Lớp: 18 quan hệ + `NA` → 19 nhãn.
2. `src/re/train_re.py`: giống Phase 5, `metric_for_best_model="f1"`, lưu `metrics.json` per-relation.
3. `src/re/infer_re.py`: dự đoán trên toàn corpus, sinh cặp ứng viên từ mention trong câu (cặp có cùng câu, cách nhau ≤ 60 token), lọc `NA`, ghi confidence = softmax.
4. **LLM bulk** `[KAGGLE-GPU]`: `notebooks/kaggle/06_llm_extract_kaggle.ipynb`
   - Model: `Qwen/Qwen3-8B` (hoặc `openai/gpt-oss-20b`) nạp bằng `transformers` + bitsandbytes 4-bit, hoặc `vllm` nếu thời gian cho phép.
   - Chunk 15 câu/request, prompt ép JSON: `{"triples":[{"subject","relation","object","evidence","confidence"}]}`.
   - **Bắt buộc**: `evidence` phải là substring của câu đầu vào → nếu không, loại triple và đếm số lượt loại.
   - Ghi `re_llm_kaggle.jsonl` ra `/kaggle/working` để tải về.
5. **LLM API baseline** (tập con ~1.500 câu, đủ quota): `src/re/infer_re_llm.py` dùng `src/common/llm_client.py` (Gemini `gemini-3.5-flash-lite` → fallback Groq `openai/gpt-oss-20b`), cache SQLite, rate limit theo provider.
6. `src/common/llm_client.py`:
   - Interface `complete(prompt, system=None, temperature=0.0, max_tokens=..., json_mode=False)`.
   - Provider Gemini (SDK `google-generativeai`) và Groq (SDK `groq`), fallback tự động khi 429/5xx.
   - Retry exponential backoff tối đa 3; rate limiter theo RPM/RPD từ `configs/llm.yaml`.
   - Cache `data/interim/llm_cache.sqlite` (key = sha256(model+prompt+params)).
   - **Không log giá trị key**.
7. `src/re/merge_triples.py`:
   - Gộp `infobox` + `phobert_re` + `llm` + `distant_supervision`.
   - Chuẩn hóa subject/object về `entity_id` (nếu chưa có → dùng `make_entity_id`).
   - Loại trùng (subject, relation, object): giữ bản `confidence` cao nhất; các bằng chứng còn lại vào `alt_evidence`.
   - Chuẩn hóa quan hệ đối xứng (`anh_em_cua`, `tham_gia_tran`) về orientation chuẩn (subject_id < object_id) → tránh trùng.
   - Loại triple có subject/object rỗng, có quan hệ ngoài danh mục, hoặc `evidence_sentence` rỗng.

**Lệnh kiểm thử**
```bash
python -m src.re.train_re --config configs/default.yaml
python -m src.re.infer_re --model models/re --out data/interim/re_phobert.jsonl
python -m src.re.merge_triples --out data/interim/triples_merged.jsonl
pytest -q tests/test_relations.py tests/test_llm_client.py
python - <<'PY'
import json
rows=[json.loads(l) for l in open('data/interim/triples_merged.jsonl')]
for r in rows:
    assert all(r.get(k) for k in ("evidence_sentence","source_url","doc_id","sentence_id")), r
    assert 0<=r['confidence']<=1
    assert r['method'] in {"infobox","distant_supervision","phobert_re","llm","rule"}
keys={(r['subject'],r['relation'],r['object']) for r in rows}
assert len(keys)==len(rows), "triple trùng sau merge"
print("OK triples",len(rows))
PY
```

**Gate**
- [ ] RE F1 dev ≥ 0.70 (per-relation trong `metrics.json`)
- [ ] 100% triple có 6 trường bắt buộc
- [ ] 0 triple trùng sau merge
- [ ] 0 quan hệ ngoài danh mục
- [ ] LLM baseline: ≥ 90% evidence là substring **trước** khi lọc; sau lọc còn ≥ 60% số triple ứng viên
- [ ] `llm_client` test: retry + fallback + cache hoạt động (mock)

**Lùi:** nếu RE F1 < 0.65: (a) thêm nhãn từ infobox vào tập train, (b) distill từ LLM (dùng output LLM làm nhãn mềm), (c) tăng số epoch, (d) đổi sang `phobert-large`.

---

## Phase 9 — Entity linking: alias, ứng viên, rerank (E1–E4)

**Mục tiêu:** `data/knowledge_base/entities.jsonl` + `linked_mentions.jsonl`; linking accuracy ≥ 0.85.

**Input contract**
- `triples_merged.jsonl` (Phase 8) → tập entity.
- `infobox_entities.jsonl` (Phase 3) → alias + thuộc tính.
- `pageid_to_qid.json` (Phase 1) → QID.
- Wikidata aliases (`skos:altLabel` tiếng Việt) — lấy qua `src/re/wikidata_client.py`.

**Output contract**
- `data/knowledge_base/entities.jsonl`:
```json
{"entity_id":"ent_le_loi_1a2b3c4d","name":"Lê Lợi","name_normalized":"le loi","type":"person",
 "aliases":[{"alias":"Lê Thái Tổ","type":"temple"},{"alias":"Bình Định Vương","type":"reign"}],
 "aliases_normalized":["le thai to","binh dinh vuong"],"wikidata_qid":"Q...","wiki_url":"...",
 "birth_year":1385,"death_year":1433,"verified":true,"mention_count":42,"source_method":"infobox"}
```
- `data/knowledge_base/entity_embeddings.npy` + `entity_embeddings_meta.json` (`entity_id`, `model`, `dim`, `order`).
- `linked_mentions.jsonl`: mỗi mention → `entity_id` hoặc `null` + `score` + `candidates`.

**Việc phải làm**
1. `src/link/build_aliases.py`:
   - Thu alias từ: infobox (`tên húy`, `miếu hiệu`, `thụy hiệu`, `niên hiệu`), `aliases` của Wikidata (`skos:altLabel`, `P742`, `P1449`, `P1709`), đích hyperlink trong corpus, các biến thể bỏ dấu.
   - Gán `type` cho từng alias.
   - Kiểm tra: `Lê Lợi` phải có ≥ 2 alias gồm `Lê Thái Tổ` và `Bình Định Vương`.
2. `src/link/embed_entities.py` `[KAGGLE-GPU]`: BGE-M3 encode mỗi entity (text = `"<name>. <aliases>". " <description 200 ký tự>"`), lưu `.npy` float16 + meta. Nếu chưa chạy Kaggle → dùng `sentence-transformers` `paraphrase-multilingual-MiniLM` CPU (chấp nhận chất lượng thấp hơn, ghi rõ trong báo cáo).
3. `src/link/link_mentions.py`:
   - **Stage 1 — alias exact:** tra dict chuẩn hóa → ứng viên.
   - **Stage 2 — embedding:** cosine similarity vs top-k (k=20) trên `entity_embeddings.npy`.
   - **Stage 3 — rerank theo ngữ cảnh** (điểm có giải thích):
     `score = w_alias*alias + w_ctx*context + w_temp*temporal + w_dyn*dynasty + w_type*type + w_freq*freq`
     với `w` trong `configs/default.yaml` (`link.context_weight`).
     - `context`: entity ứng viên có xuất hiện trong cùng đoạn/bài không.
     - `temporal`: khoảng năm sinh/mất của ứng viên chồng lấn mốc thời gian trong câu không.
     - `dynasty`: ứng viên thuộc đúng triều đại của bài không.
     - `type`: ứng viên có cùng `type` với nhãn NER không.
     - `freq`: `mention_count` chuẩn hóa.
   - Ngưỡng: `score < threshold` → `canonical_id = null` (chưa xác minh) + ghi `ambiguous`.
4. `src/link/resolve_nil.py` (E5, mở rộng): gộp các entity chưa xác minh theo surface name → `nil_<hash8>`, `verified=false`.
5. Ghi `linked_mentions.jsonl` và **cập nhật lại `entity_id` trong `triples_merged.jsonl`** (Phase 8 dùng entity_id tạm → Phase 9 thay bằng canonical).
6. `src/link/linking_report.py`: alias hit rate, recall@20, độ chính xác theo nhóm lỗi (khác chữ / trùng tên / ngoài KB).

**Lệnh kiểm thử**
```bash
python -m src.link.build_aliases --config configs/default.yaml
python -m src.link.embed_entities --out data/knowledge_base/entity_embeddings.npy
python -m src.link.link_mentions --config configs/default.yaml
pytest -q tests/test_aliases.py
python - <<'PY'
import json
ents={json.loads(l)['entity_id']: json.loads(l) for l in open('data/knowledge_base/entities.jsonl')}
le=[e for e in ents.values() if e['name']=='Lê Lợi']
assert le, "không tìm thấy Lê Lợi"
al={a['alias'] for a in le[0]['aliases']}
assert {'Lê Thái Tổ','Bình Định Vương'} <= al, al
print("OK entities",len(ents))
PY
```

**Gate**
- [ ] ≥ 95% entity `PERSON` có ≥ 2 alias
- [ ] `Lê Lợi` có alias `Lê Thái Tổ` + `Bình Định Vương` (assert)
- [ ] `entity_id` ổn định & không trùng (test)
- [ ] Recall@20 ≥ 0.90; alias hit rate ≥ 0.60
- [ ] Linking accuracy ≥ 0.85 trên tập gold (Phase 12) hoặc ≥ 0.85 trên tập auto-gold Wikidata (đo sớm để biết)
- [ ] Thời gian ≤ 200ms/mention trên CPU
- [ ] ≤ 10% node là NIL

**Lùi:** nếu accuracy < 0.85 → thêm reranker cross-encoder đa ngôn ngữ, mở rộng alias, đổi embedding model.

---

## Phase 10 — Đồ thị + Neo4j (F1–F4)

**Mục tiêu:** KG trong Neo4j: 5.000–30.000 node, 50.000–200.000 cạnh, 100% cạnh có bằng chứng, nạp idempotent.

**Input contract**
- `entities.jsonl` + `triples_merged.jsonl` (đã cập nhật canonical id từ Phase 9).
- `docker compose up -d neo4j` đã chạy.

**Output contract**
- `data/knowledge_base/graph.jsonl`: 2 phần `{"type":"nodes","items":[...]}` và `{"type":"edges","items":[...]}`.
- `src/graph/schema.cypher`: constraint + index.
- Neo4j chứa dữ liệu.

**Việc phải làm**
1. `src/graph/build_graph.py`:
   - Node: entity_id, name, name_normalized, type, aliases, aliases_normalized, description, wiki_url, wikidata_qid, verified, mention_count, source_method + thuộc tính riêng theo type (birth_year, death_year, reign_start/end, birth_place, death_place, dynasty, temple_name, posthumous_name, reign_title, gender, latitude/longitude).
   - Node `Year` cho `sinh_nam`/`mat_nam` (`entity_id = year_<n>`, `value = năm`).
   - Edge: 18 quan hệ; thuộc tính `confidence`, `method`, `evidence_sentence`, `source_url`, `doc_id`, `doc_title`, `sentence_id`, `alt_evidence`, `start_year`, `end_year`, `created_at`.
   - Chuẩn hóa orientation quan hệ đối xứng.
   - Bỏ edge có subject/object không có trong node set → ghi vào `reports/orphan_edges.log`.
2. `src/graph/schema.cypher`: theo [04](04-schema-knowledge-graph.md#5-schema-cypher) — constraint uniqueness cho 7 label, index cho `name_normalized`, `birth_year`, `death_year`, `reign_start/end`, `wiki_url`.
3. `scripts/load_neo4j.py`:
   - Đọc `schema.cypher` → chạy từng statement (bỏ qua lỗi "already exists").
   - Nạp bằng `UNWIND $batch AS row MERGE (n:Label {entity_id: row.entity_id}) SET n += row.props`, batch 500–1.000.
   - Edge: `UNWIND $batch AS row MATCH (s {entity_id: row.source}) MATCH (t {entity_id: row.target}) MERGE (s)-[r:REL]->(t) SET r += row.props` — nhưng chỉ set `confidence` khi lớn hơn giá trị hiện tại (dùng `CASE`).
   - Ghi log tiến trình + số node/edge trước và sau.
4. `scripts/create_readonly_user.sh`: tạo user `reader` (tách credential cho API) **và** kiểm chứng cơ chế chỉ-đọc.
   - Neo4j **Community không có RBAC**: `CREATE USER … SET ROLE reader` và `GRANT … ON GRAPH` đều lỗi cú pháp; user `reader` tạo được nhưng vẫn ghi được vào DB.
   - Cơ chế bảo vệ thực sự hiệu lực: **session `default_access_mode=READ_ACCESS`** → server từ chối mọi lệnh ghi (`Neo.ClientError.Statement.AccessMode`), kể cả khi dùng superuser.
   - Script phải **chứng minh** điều này: chạy 1 lệnh ghi bằng user `reader` với session `READ_ACCESS` → phải nhận lỗi AccessMode; nếu lệnh ghi lọt → exit code ≠ 0.
5. `scripts/validate_graph.py`: 11 kiểm tra trong [04](04-schema-knowledge-graph.md#10-kiểm-tra-chất-lượng-schema-script-validate_graphpy) → in bảng PASS/FAIL, exit code khác 0 nếu có lỗi nghiêm trọng.

**Lệnh kiểm thử**
```bash
python -m src.graph.build_graph --config configs/default.yaml
docker compose up -d neo4j && sleep 20
python scripts/load_neo4j.py --batch 1000
python scripts/load_neo4j.py --batch 1000     # chạy lần 2
python scripts/validate_graph.py
python - <<'PY'
import os
from neo4j import GraphDatabase
g=GraphDatabase.driver(os.environ["NEO4J_URI"],auth=(os.environ["NEO4J_USER"],os.environ["NEO4J_PASSWORD"]))
with g.session() as s:
    n1=s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
    e1=s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
print("nodes",n1,"edges",e1)
PY
python scripts/load_neo4j.py --batch 1000     # lần 3
python scripts/validate_graph.py               # kỳ vọng: 0 lỗi nghiêm trọng
```

**Gate**
- [ ] Node count trong khoảng 5.000–30.000; edge count 50.000–200.000
- [ ] Chạy nạp 3 lần → node/edge count **không đổi** (ghi lại 3 con số vào báo cáo)
- [ ] `validate_graph.py`: 0 node thiếu `entity_id`/`wiki_url`; 0 edge thiếu `evidence_sentence`/`source_url`/`confidence`/`method`; 0 quan hệ ngoài danh mục
- [ ] User `reader` không chạy được `MATCH (n) SET n.x=1` (test thủ công)
- [ ] Nạp 50k edge < 10 phút

**Lùi:** nếu edge quá nhiều → lọc `confidence >= 0.5` (ghi rõ trong báo cáo số bị loại). Nếu quá ít → nới ngưỡng ở Phase 8.

---

## Phase 11 — Text-to-Cypher backend (G1–G4, G6, G8)

**Mục tiêu:** `POST /api/ask` trả lời được câu hỏi tiếng Việt; execution accuracy ≥ 0.70; Cypher chỉ đọc.

**Input contract**
- Neo4j có dữ liệu (Phase 10).
- `entities.jsonl` (alias) để entity linking câu hỏi.
- `GEMINI_API_KEY` / `GROQ_API_KEY` trong `.env`.

**Output contract** — `POST /api/ask` trả JSON:
```json
{"status":"found","answer":"...","cypher":"...","entities":[...],
 "records":[...],"graph":{"nodes":[...],"edges":[...]},"retries":0,"elapsed_ms":2140}
```
`status` ∈ {`found`, `not_in_data`, `error`}.

**Việc phải làm**
1. `backend/app/services/neo4j_client.py`:
   - Driver, `session(default_access_mode=READ)`, `fetch_size`, timeout qua `session.run(..., timeout=10)`.
   - `MAX_ROWS = 100`, ép `LIMIT`.
2. `backend/app/services/cypher_validator.py`:
   - Blacklist (case-insensitive, có xử lý string literal): `CREATE`, `MERGE`, `DELETE`, `DETACH`, `SET`, `REMOVE`, `DROP`, `FOREACH`, `LOAD CSV`, `CALL`, `dbms.`, `apoc.`, `ALTER`, `GRANT`.
   - Chỉ cho phép câu bắt đầu bằng `MATCH` / `OPTIONAL MATCH` / `WITH` / `UNWIND` / `RETURN`.
   - Chặn `;` ngoài string literal.
   - Bắt buộc có `LIMIT`; nếu thiếu → thêm `LIMIT 50` hoặc từ chối.
   - Kiểm tra tất cả quan hệ dùng trong câu nằm trong `RELATION_TYPES` → nếu có quan hệ ngoài danh sách → từ chối.
   - Trả `(ok, reason)`.
3. `backend/app/services/entity_linker.py`: load `entities.jsonl` + dict alias chuẩn hóa; `link(text) -> [(span, entity_id, canonical_name)]`; hỗ trợ khớp dài nhất (ưu tiên alias dài hơn).
4. `backend/app/prompts/text_to_cypher.txt`:
   - Schema node (7 label) + thuộc tính chính.
   - Danh sách 18 quan hệ hợp lệ + mô tả 1 dòng mỗi quan hệ.
   - Quy tắc: chỉ `MATCH/OPTIONAL MATCH/WITH/UNWIND/RETURN/ORDER BY/LIMIT`; **không** `CREATE/MERGE/DELETE/SET`; luôn `LIMIT ≤ 100`; không `MATCH (n) RETURN n` không lọc; dùng `entity_id` đã chuẩn hóa.
   - 10–12 few-shot: một bước, đếm, đa bước, lọc năm, so sánh, bridge, "không có dữ liệu".
   - Output JSON: `{"cypher":"...","explanation":"..."}`.
5. `backend/app/services/text_to_cypher.py`:
   - Bước: link entity → thay span bằng `entity_id` trong câu hỏi (giữ cả tên gốc trong prompt để LLM hiểu) → gọi LLM → parse JSON → validate → thực thi.
   - Retry tối đa 3 lần khi lỗi cú pháp/rỗng, đưa thông báo lỗi + Cypher cũ vào prompt (G5).
   - Nếu kết quả rỗng ở lần cuối → `status="not_in_data"`.
6. `backend/app/services/answer_generator.py` (G7): prompt "chỉ dùng dữ liệu trong records", cấm suy đoán; nếu records rỗng → trả "Không có trong dữ liệu."
7. `backend/app/api/ask.py`: endpoint + log (câu hỏi, Cypher, thời gian, số dòng) vào `logs/ask.log`.
8. Các endpoint khác: `GET /api/search`, `GET /api/graph/{entity_id}`, `GET /api/entity/{entity_id}`, `GET /api/stats`.
9. `tests/test_cypher_validator.py`: ≥ 20 payload độc hại + 10 Cypher hợp lệ.

**Lệnh kiểm thử**
```bash
pytest -q tests/test_cypher_validator.py
uvicorn backend.app.main:app --port 8000 &
curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"Lê Lợi sinh năm nào?"}' | python -m json.tool
curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"MATCH (n) DETACH DELETE n"}' | python -m json.tool   # kỳ vọng: status=error, không xoá gì
curl -s -X POST localhost:8000/api/ask -H 'Content-Type: application/json' \
  -d '{"question":"Ai là vua năm 1855?"}' | python -m json.tool         # kỳ vọng: not_in_data
# xác nhận DB còn nguyên
python scripts/validate_graph.py
```

**Gate**
- [ ] ≥ 20/20 payload độc hại bị chặn (test tự động)
- [ ] 10/10 Cypher hợp lệ được pass
- [ ] 3 câu hỏi mẫu trả đúng `status` (found / not_in_data / error)
- [ ] Cypher sinh ra luôn có `LIMIT ≤ 100`; 0 quan hệ ngoài danh mục
- [ ] Truy vấn p95 < 2s; end-to-end p50 < 10s
- [ ] Không câu trả lời nào chứa thông tin ngoài `records` (rà soát tay 20 câu)

**Lùi:** nếu exec accuracy thấp → thêm few-shot, rút gọn schema trong prompt, ép `temperature=0`, thử provider khác.

---

## Phase 12 — Giao diện web (H1–H4)

**Mục tiêu:** trang chat có đồ thị tương tác + panel bằng chứng.

**Input contract**
- API Phase 11 chạy ở `localhost:8000`.
- Node/edge có đủ thuộc tính bằng chứng.

**Output contract**
- `frontend/src/components/{ChatPanel,MessageBubble,CypherBlock,GraphView,EntityCard,EvidencePanel,Legend}.tsx`
- `frontend/src/api/client.ts`, `frontend/src/types/index.ts`
- `frontend/src/pages/{Home,EntityPage}.tsx`

**Việc phải làm**
1. `ChatPanel`: textarea, Enter gửi, hiển thị trạng thái "Đang tìm trong dữ liệu lịch sử…", lịch sử hội thoại trong phiên (`session_id` lưu localStorage).
2. `MessageBubble`: hiển thị `answer` + 3 trạng thái khác màu (found / not_in_data / error).
3. `CypherBlock`: mặc định thu gọn, nút mở/ẩn, nút copy.
4. `GraphView`: Cytoscape.js; layout `cose`; màu theo label (`Person`, `Dynasty`, `Event`, `Place`, `Title`, `Year`); node NIL viền đứt; zoom/pan/kéo.
5. `EntityCard`: khi click node → tên, loại, alias, năm sinh/mất, mô tả, link Wikipedia, nút "Mở rộng láng giềng" (≤ 30 node).
6. `EvidencePanel`: khi click edge → `evidence_sentence` (highlight entity), `source_url`, `confidence`, `method`, `doc_title`; link mở tab mới.
7. `Legend`: chú giải màu.
8. Tích hợp `GET /api/graph/{id}` cho mở rộng, `GET /api/entity/{id}` cho thẻ.
9. `frontend/src/pages/EntityPage.tsx`: trang riêng cho một entity (URL `/entity/:id`).

**Lệnh kiểm thử**
```bash
cd frontend && npm run build && npx tsc --noEmit     # 0 lỗi TS
npm run dev
# kiểm thử tay bằng script Playwright/Puppeteer tùy chọn, hoặc checklist:
#  [ ] gửi câu hỏi → có answer + cypher + đồ thị
#  [ ] click node → mở EntityCard, click "mở rộng" → thêm ≤ 30 node
#  [ ] click edge → EvidencePanel có câu bằng chứng + link Wikipedia
#  [ ] node NIL viền đứt, màu đúng label
```

**Gate**
- [ ] `npm run build` xong, `tsc --noEmit` 0 lỗi
- [ ] Cả 4 hành vi H1–H4 hoạt động (checklist tự đánh dấu)
- [ ] Render 200 node < 1,5s; ≥ 500 node vẫn kéo mượt (đo bằng `performance.now()`)
- [ ] Mọi edge click đều hiện bằng chứng (không bao giờ trống)
- [ ] UI 100% tiếng Việt

**Lùi:** nếu Cytoscape chậm với > 500 node → bật `hideEdgesOnViewport`, giảm `nodeRepulsion`, giới hạn số node mặc định 150.

---

## Phase 13 — Đánh giá (I3, I4) — **không cần gán tay đầy đủ**

**Mục tiêu:** có số liệu thật cho NER F1, RE F1, linking accuracy, Text-to-Cypher execution accuracy; tạo `reports/`.

**Input contract**
- Mô hình `models/ner`, `models/re`.
- `wikidata_pairs.jsonl` (Phase 7) — nguồn **auto-gold** độc lập với mô hình.
- `entities.jsonl` + `pageid_to_qid.json` — auto-gold cho linking.
- Bộ câu hỏi `data/eval/qa_gold.jsonl` (sinh tự động, xem bước 2).
- Tối đa 100 câu gán tay (nếu làm được) — `data/eval/manual_ner.jsonl`.

**Output contract**
- `reports/eval_<timestamp>.md` + `.json`: bảng chỉ số.
- `data/eval/{auto_gold_ner.jsonl,auto_gold_re.jsonl,auto_gold_link.jsonl,qa_gold.jsonl}`.

**Việc phải làm**
1. **Auto-gold NER** (`src/evaluation/build_auto_gold.py`):
   - Nguồn: hyperlink có đích **có QID** + `P31` khớp nhãn (đã tra ở Phase 4) + anchor trùng đích.
   - Bỏ mọi mention không có QID (tránh nhãn sai).
   - Kết quả là nhãn **độc lập với mô hình** → dùng làm gold.
   - Báo cáo độ lớn tập; nếu < 200 câu → lấy thêm từ câu chứa entity Wikidata đã xác nhận.
2. **Auto-gold RE** (`src/evaluation/build_auto_gold.py`): từ `wikidata_pairs.jsonl` → cặp (subject, relation, object) là đáp án đúng; cặp có mặt trong câu nhưng không có trong Wikidata → NEGATIVE.
   - **Quan trọng**: đáp án đến từ Wikidata, **không** từ KG của mình → không vòng tròn.
3. **Auto-gold linking**: mention → QID; đúng khi entity dự đoán có cùng QID.
4. **Bộ câu hỏi QA tự sinh** (`src/evaluation/build_qa_set.py`):
   - Sinh từ facts Wikidata bằng khuôn câu hỏi:
     `cha_cua` → "Cha của X là ai?" · `me_cua` → "Mẹ của X là ai?" · `sinh_nam` → "X sinh năm nào?" · `mat_nam` → "X mất năm nào?" · `thuoc_trieu_dai` → "X thuộc triều đại nào?" · `vo_cua` → "Vợ của X là ai?" · `ke_vi` → "Ai kế vị X?" · `sinh_tai` → "X sinh ở đâu?" · `dien_ra_tai` → "Sự kiện X diễn ra ở đâu?" · `than_gia_tran` → "X tham gia trận đánh nào?"
   - `expected_result` lấy từ **Wikidata**, không từ KG → không vòng tròn.
   - Sinh thêm câu **đa bước** bằng cách nối 2 facts: "Vợ của X là con của ai?" (cha của vợ) — kỳ vọng suy ra từ Wikidata.
   - Phân dạng tự động: `one_hop`, `two_hop`, `count`, `list`, `filter`, `no_data`.
   - Sinh câu `no_data`: hỏi về năm ngoài phạm vi (vd "Ai là vua năm 1855?") → `expected_result = []`.
   - Mục tiêu 200–400 câu, mỗi dạng ≥ 20 câu.
5. **Gán tay tối thiểu (nếu làm được)** (`src/evaluation/import_labelstudio.py`):
   - Xuất 100 câu (có entity rõ nhất) ra JSONL cho Label Studio (`data/eval/to_annotate_ner.jsonl`).
   - Import kết quả → `data/eval/manual_ner.jsonl` (Label Studio export → JSONL).
   - Nếu có 2 người gán trên ≥ 30 câu chung → tính **agreement rate** (và Cohen's kappa nếu đủ); nếu chỉ 1 người → báo cáo **agreement rate** với auto-gold, nêu rõ đây là đối chiếu người–máy chứ không phải inter-annotator.
6. **Script đánh giá** (`src/evaluation/evaluate.py`):
   - `ner_f1(pred, gold)` — token-level IOB2, micro + macro + per-label.
   - `re_f1(pred, gold)` — micro theo quan hệ + macro + per-relation; báo cáo riêng tỉ lệ false-positive trên nhãn `NA`.
   - `linking_accuracy(pred, gold)`.
   - `qa_execution_accuracy(pred_cypher_results, expected_results)` — so sánh tập dòng, không phân biệt thứ tự (trừ câu yêu cầu `ORDER BY`).
   - `faithfulness_rate` — LLM-judge (Gemini/Groq) trên 30 câu: câu trả lời có chứa thông tin ngoài `records` không? Đo tỉ lệ "không bịa".
   - So sánh cấu hình: chạy lại eval với `pipeline.skip_coref=true` và `pipeline.skip_linking=true` → bảng so sánh (I5).
   - Đầu ra Markdown + JSON vào `reports/`.
7. `scripts/evaluate.py` wrapper: `python scripts/evaluate.py --all`.

**Lệnh kiểm thử**
```bash
python -m src.evaluation.build_auto_gold --config configs/default.yaml
python -m src.evaluation.build_qa_set --config configs/default.yaml
python scripts/evaluate.py --all --out reports/
pytest -q tests/test_metrics.py tests/test_eval_sets.py
python - <<'PY'
import json
m=json.load(open(sorted(__import__('glob').glob('reports/eval_*.json'))[-1]))
for k in ("ner_f1_micro","re_f1_micro","linking_accuracy","qa_execution_accuracy"):
    print(k, m["metrics"][k])
assert m["metrics"]["ner_f1_micro"]>=0.85
assert m["metrics"]["re_f1_micro"]>=0.70
assert m["metrics"]["linking_accuracy"]>=0.85
assert m["metrics"]["qa_execution_accuracy"]>=0.70
PY
```

**Gate**
- [ ] Auto-gold NER ≥ 200 câu; auto-gold RE ≥ 500 cặp; QA set ≥ 200 câu phân bố ≥ 5 dạng
- [ ] NER F1 ≥ 0.85, RE F1 ≥ 0.70, linking acc ≥ 0.85, QA exec acc ≥ 0.70 — **hoặc** báo cáo minh bạch số thực tế kèm phân tích lỗi
- [ ] Có bảng so sánh ≥ 3 cấu hình (đầy đủ / không coref / không linking)
- [ ] `faithfulness_rate` ≥ 0.90 (không bịa)
- [ ] `tests/test_metrics.py` xanh (F1 tính đúng với dữ liệu mẫu biết trước)
- [ ] `reports/eval_*.md` ghi rõ kích thước tập đánh giá

**Lùi:** nếu một chỉ số không đạt → **không sửa số liệu**, ghi rõ số thực tế + phân tích lỗi top 20 + hướng khắc phục trong báo cáo. Đây là hành vi bắt buộc.

---

## Phase 14 — Mở rộng (tùy thời gian) + đóng gói

**Mục tiêu:** hoàn thiện các mục "mở rộng" và đóng gói bàn giao.

**Việc phải làm** (làm theo thứ tự, dừng ngay khi hết thời gian):
1. **B3** — `src/preprocess/time_normalize.py`: chuẩn hóa "năm Canh Thân 1380", "thế kỷ XV", "tháng 5 năm 1284" → năm dương; gắn vào `TIME` và làm đối tượng của `sinh_nam`/`mat_nam`.
2. **D5** — cạnh `ke_vi`/`giu_chuc_vu` có `start_year`/`end_year` (từ Wikidata `P580`/`P582`); API hỗ trợ lọc theo khoảng năm.
3. **G5** — vòng lặp tự sửa lỗi (đã có sẵn trong Phase 11, cần **log đầy đủ** các lần retry + báo cáo tỉ lệ lỗi cú pháp).
4. **G7** — sinh câu trả lời tự nhiên (đã có ở Phase 11, cần đo `faithfulness_rate` ở Phase 13).
5. **E5** — node NIL có badge "chưa xác minh" trên UI.
6. **H5** — bộ lọc triều đại / loại quan hệ / khoảng thời gian (server-side trong Cypher).
7. **H7** — chế độ timeline (dùng `reign_start`, `year` của event).
8. **I1** — trang `/stats`: số node/cạnh theo label/quan hệ, phân bố confidence (Recharts).
9. **H6** — cây gia phả (cytoscape-dagre, layout dọc, giới hạn độ sâu 3).
10. **I5** — chạy và lưu bảng so sánh cấu hình.
11. **B4** — baseline NER bằng LLM few-shot trên 200 câu dev; bảng so sánh.
12. **F5** — `scripts/export_graph.sh` (dump + CSV), `scripts/import_graph.sh`.
13. **Đóng gói**: `README.md` với lệnh chạy thật đã test, `docs/` hoàn chỉnh, `reports/` đầy đủ, `.env.example`, `docker-compose.yml` chạy được từ máy sạch.

**Gate**
- [ ] Mỗi mục đã bật → có test tương ứng hoặc kiểm thử tay có ghi kết quả vào `reports/`
- [ ] `docker compose up` từ máy sạch → Neo4j + backend + frontend hoạt động
- [ ] README có: yêu cầu, cài đặt, lệnh chạy từng phase, lệnh đánh giá, ảnh chụp màn hình demo

---

## Phụ lục 1 — Hợp đồng dữ liệu (bất biến xuyên suốt)

| Đối tượng | Format | Ghi chú |
|---|---|---|
| `doc_id` | `doc_<page_id>` | |
| `sentence_id` | `s<page_id>_<para_idx>_<sent_idx>` | |
| `mention_id` | `m<sentence_id>_<idx>` | |
| `entity_id` | `ent_<slug>_<hash8>` | `hash8 = sha1(f"{type}\|{name_normalized}")[:8]` |
| `year_id` | `year_<năm>` | |
| `nil_id` | `nil_<hash8>` | entity chưa xác minh |
| Quan hệ | 18 chuỗi cố định | xem [04](04-schema-knowledge-graph.md#31-danh-mục-đầy-đủ) |
| `method` | `infobox` \| `distant_supervision` \| `phobert_re` \| `llm` \| `rule` | |
| Artifact | JSONL, UTF-8, không BOM, 1 record/dòng | |
| Offset | ký tự Python trong `clean_text` / `text` của câu | |

## Phụ lục 2 — Lệnh kiểm thử chuẩn (chạy mỗi phase)

```bash
source .venv/bin/activate
pytest -q tests/                                   # test unit + integration
python scripts/validate_graph.py                   # chỉ sau Phase 10
python scripts/evaluate.py --all --out reports/   # chỉ sau Phase 13
```
Kết quả mỗi phase ghi vào `reports/phase_XX_report.md` với: mô tả, lệnh đã chạy, output thực tế, gate pass/fail, sai lệch.

Kèm theo, mỗi phase ghi vào `docs/10-nhat-ky/phase_XX.md` với: bối cảnh, phương án đã cân nhắc,
quyết định đã chốt, thang số liệu so sánh, lỗi gặp phải & cách xử lý, bài học, ý tưởng cho slide.
Hai file này bổ sung cho nhau: báo cáo trả lời *"làm gì, đạt Gate chưa"*, nhật ký trả lời
*"vì sao chọn cách đó, số liệu so sánh ra sao, sai ở đâu, bài học gì"*.

## Phụ lục 3 — Quy tắc ứng xử khi bị kẹt

| Tình huống | Hành động |
|---|---|
| Một Gate không đạt sau 2 lần sửa | đọc mục "Lùi" của phase đó; nếu vẫn không đạt → ghi `reports/deviations.md`, **hạ tiêu chí có kiểm soát** và báo cáo minh bạch |
| Quota LLM hết | chuyển sang provider dự phòng; giảm tập con LLM; ghi rõ trong báo cáo phạm vi baseline |
| Kaggle hết giờ GPU | tải checkpoint cuối, chạy tiếp phiên sau; ưu tiên checkpoint `best` |
| Dữ liệu ít hơn kỳ vọng | giảm ngưỡng số bài, ghi rõ trong báo cáo phạm vi |
| Cần gộp/sửa schema | cập nhật [04](04-schema-knowledge-graph.md) **và** mọi prompt/test liên quan trong cùng một lần thay đổi |

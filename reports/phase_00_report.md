# Phase 00 — Bootstrap repo, cấu hình, hạ tầng

- Ngày: 2026-11-13
- Trạng thái: ✅ đạt Gate

## Đã làm

### Cây thư mục
Tạo đủ theo `docs/03-kien-truc-he-thong.md` §4 và Output contract của Phase 0:
`configs/`, `src/{preprocess,ner,coref,re,link,graph,qa,evaluation,common}/`,
`backend/app/{api,services,schemas,prompts}/`, `frontend/src/{components,pages,api,types}/`,
`scripts/`, `notebooks/kaggle/`, `tests/fixtures/`, `models/`, `logs/`, `reports/screenshots/`.

### Cấu hình (nguồn sự thật duy nhất)
- `configs/default.yaml` — seed 42, đường dẫn, `dump.dump_version: "20261101"`, ngưỡng,
  **18 quan hệ** và **9 QID triều đại** (sao chép từ `docs/CONTEXT.md` §2.5–2.6),
  18 lớp thực thể Wikidata đã verify.
- `configs/pipeline.yaml` — cờ bật/tắt module A–I, tỉ lệ chia tập 80/10/10 theo **bài**,
  cấu hình Kaggle GPU, ngưỡng chất lượng.
- `configs/llm.yaml` — Gemini `gemini-3.5-flash-lite` (chính) + Groq `openai/gpt-oss-20b`
  (dự phòng), quota, retry, cache SQLite, đường bulk trên Kaggle GPU.
- `configs/neo4j.yaml` — URI/user/db, `read_only_session: true`,
  `default_access_mode: READ_ACCESS`, `max_limit: 100`, `timeout_s: 10`, 7 label node.

### `src/common/` — hợp đồng dữ liệu dùng chung
| File | Nội dung |
|---|---|
| `config.py` | Nạp YAML, mở rộng `${VAR}` / `${VAR:-default}`, cache theo path, `resolve_path` |
| `seed.py` | `set_seed(42)` cho `random`/`numpy`/`torch` (+ `cuda`, deterministic) |
| `logger.py` | `get_logger()` → `logs/<name>.log` + stdout, timestamp + level + module |
| `normalize.py` | `strip_accents` (có bảng tra `Đ`/`đ` — NFD **không** tách được), `normalize_name`, `slugify`, `parse_vi_date`, `normalize_date_vi`, `is_lunar_date`, `extract_year` |
| `ids.py` | `make_entity_id` (`ent_<slug>_<sha1(type\|name_norm)[:8]>`), `make_year_id`, `make_nil_id`, `make_doc_id`, `make_sentence_id`, `make_mention_id`, `make_run_id` |
| `schemas.py` | 18 quan hệ đóng, 6 nhãn NER, 5 phương pháp trích xuất, 7 loại node, 2 quan hệ đối xứng, dataclass `Document/Sentence/Mention/Triple/Entity` + `Triple.is_valid()` |
| `text_utils.py` | Đọc/ghi JSONL theo luồng, `balance_wikitext`, `split_paragraphs` |

### Backend (FastAPI)
- `backend/app/main.py` — app + CORS + lifespan (đóng driver khi shutdown).
- `backend/app/api/health.py` — `GET /api/health` → `{"status":"ok","version":"0.1.0","neo4j":"up|down"}`.
- `backend/app/api/stats.py` — `GET /api/stats` → số node/cạnh thật từ Neo4j.
- `backend/app/services/neo4j_client.py` — driver singleton, **session `default_access_mode=READ_ACCESS`**,
  timeout 10s, `check_health()`.
- `backend/app/settings.py` — đọc `.env` + `configs/neo4j.yaml`.
- `backend/Dockerfile` + `backend/requirements.txt`.

### Frontend (Vite + React 18 + TS)
- `tsconfig.json` bật `strict` + `noUnusedLocals` + `noUnusedParameters` + `noUncheckedIndexedAccess`.
- `vite.config.ts` proxy `/api` → `:8000`.
- Trang chủ hiển thị tiêu đề + trạng thái dịch vụ + thống kê + placeholder khung hỏi đáp (100% tiếng Việt).
- `src/api/client.ts`, `src/types/index.ts`.

### Hạ tầng
- `docker-compose.yml` — `neo4j:5-community` (heap 1G, pagecache 512M, ports 7474/7687, volume),
  `backend` (build từ `backend/Dockerfile`), `frontend` (node:24-alpine, dev server).
- `requirements.txt` — **không** dùng `mwparser` (PyPI chỉ có 0.1); dùng `lxml` + `wikitextparser` + `pysbd`.
- `pytest.ini` với marker `integration` / `slow`.

### Sửa `docs/05` §3.1 (việc `fix-docs-qid`)
- Xoá bộ QID sai (`Q860615`, `Q173715`, `Q131975`, `Q355148`, `Q161983`, `Q314080`, `Q174778`).
- Thay bằng bảng 9 QID đã verify trong `docs/CONTEXT.md` §2.6.
- Thay ví dụ SPARQL dùng `P463`/`P361` (đã chứng minh trả **0** kết quả) bằng
  `P31=Q5` + `P27=Q881` + `P569` + `P22` (đã kiểm chứng trả 213 người, đủ 9 triều đại).

## Lệnh đã chạy

```bash
uv venv .venv && VIRTUAL_ENV=.venv uv pip install -r requirements.txt
→ 0 lỗi, ~167s, transformers 5.23.0 / wikitextparser 3.0.0 / lxml / pysbd đều cài được

.venv/bin/python -m pytest -q tests/
→ 56 passed

docker compose up -d neo4j
→ container vhgr_neo4j started

curl -s localhost:7474 | head -3
→ HTTP 200, {"neo4j_version":"5.26.32","neo4j_edition":"community"}

.venv/bin/uvicorn backend.app.main:app --port 8000 &
curl -s localhost:8000/api/health
→ {"status":"ok","version":"0.1.0","neo4j":"up"}

curl -s localhost:8000/api/stats
→ {"status":"found","nodes":2,"edges":0,"by_type":{"T2":1,"T3":1},"neo4j":"up"}
   (2 node T2/T3 là dữ liệu mặc định của Neo4j, sẽ bị xoá khi nạp KG ở Phase 10)

cd frontend && npm install && npm run build
→ tsc --noEmit 0 lỗi; vite build xong, dist/ 144.74 kB (gzip 46.79 kB)

# Kiểm chứng cơ chế chỉ đọc (bắt buộc của dự án)
python -c "driver.session(database='neo4j', default_access_mode=READ_ACCESS)"
→ read ok: 1
→ WRITE BLOCKED -> ClientError {neo4j_code: Ne.ClientError.Statement.AccessMode}
   "Writing in read access mode not allowed."
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| Số test pass | 100% | 56/56 pass (4,9 s) |
| Lỗi TypeScript khi build | 0 | 0 |
| `/api/health` | `{"status":"ok"}` | `{"status":"ok","version":"0.1.0","neo4j":"up"}` |
| Neo4j HTTP `:7474` | HTTP 200 | HTTP 200, v5.26.32 Community |
| Ghi vào Neo4j qua session `READ_ACCESS` | bị chặn | bị chặn (`Ne.ClientError.Statement.AccessMode`) |
| Số quan hệ trong `schemas.py` | 18 | 18 (khớp `docs/CONTEXT.md` §2.5) |
| Số QID triều đại trong `default.yaml` | 9 | 9 (khớp `docs/CONTEXT.md` §2.6) |
| Secret được commit | 0 | 0 (`.env` trong `.gitignore`, có test tự động) |

## Gate

- [x] `pytest -q` pass → 56 passed
- [x] `docker compose up -d neo4j` → Neo4j mở ở `localhost:7474` (HTTP 200, v5.26.32)
- [x] `/api/health` trả `{"status":"ok"}`
- [x] `npm run build` thành công, không lỗi TypeScript
- [x] `git status` không có file secret; `.env` nằm trong `.gitignore` (có test `test_env_khong_bi_commit`)

## Sai lệch so với kế hoạch

Ghi trong `reports/deviations.md`:
- **D-004** — Bỏ `mwparser` khỏi `requirements.txt` (đã có trong `docs/CONTEXT.md` §2.7 nhưng
  Output contract Phase 0 vẫn liệt kê). Dùng `lxml.etree.iterparse` + `wikitextparser` + `pysbd`.
- **D-005** — Bỏ `underthesea` khỏi `requirements.txt`; dùng `pysbd` cho tách câu và regex
  `\n\s*\n` cho tách đoạn. Đúng theo mục "Lùi" của Phase 0.
- **D-006** — `frontend/tsconfig.json` không dùng project reference (`tsconfig.node.json`)
  vì `composite` + `noEmit` xung đột (TS6310). Gộp `vite.config.ts` vào cùng `include`.
- **D-007** — `src/common/normalize.py` **không** quy đổi ngày âm lịch sang dương lịch.
  Chỉ *nhận diện* chuỗi là ngày âm lịch (`is_lunar_date`). Quy đổi cần thư viện chuyên dụng
  và phụ thuộc múi giờ; bảng tra thủ công dễ sai, không đạt nguyên tắc "không bịa".

## Việc tiếp theo

**Phase 1 — Tải dump viwiki `20261101` + lọc 2.000–5.000 bài lịch sử.**

Tín hiệu lọc (T0 Wikidata + T1 category đúng tên + T2 infobox + T3 BFS + T4 loại trừ) đã
được kiểm chứng ở plan §2: `Category:Vua Việt Nam` (57), `Category:Địa danh Việt Nam` (90),
`Category:Người Việt Nam` (68) là các category seed có thật trong dump viwiki.

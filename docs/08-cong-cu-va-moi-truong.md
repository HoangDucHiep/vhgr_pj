# 08 — Công cụ, môi trường và vận hành

## 1. Danh mục công cụ

### 1.1. Xử lý dữ liệu

| Công cụ | Phiên bản | Vai trò | Ghi chú |
|---|---|---|---|
| Python | 3.12 | ngôn ngữ chính | đã có sẵn trên máy |
| `mwparser` | ≥ 0.6 | parse wikitext nhanh | dùng cho streaming filter |
| `wikitextparser` | ≥ 0.6 | parse infobox chi tiết | dùng cho parse_infobox |
| `pywikibot` | ≥ 7.0 | tra category, resolve redirect | tuỳ chọn |
| `pysbd` | ≥ 0.3 | tách câu | không cần model, hỗ trợ tiếng Việt |
| `underthesea` | ≥ 6.x | tách đoạn, POS tag | có thể nặng → dùng `textpipe` |
| `unidecode` / `unicodedata` | — | chuẩn hóa tên bỏ dấu | dùng `unicodedata` chuẩn |
| `pandas` | ≥ 2.0 | xử lý bảng, thống kê | |
| `pyarrow` | ≥ 14 | đọc/ghi parquet | cho artifact lớn |
| `datasets` | ≥ 2.14 | xử lý dataset HuggingFace | |

### 1.2. NLP / mô hình

| Công cụ | Phiên bản | Vai trò |
|---|---|---|
| `transformers` | ≥ 4.40 | PhoBERT token classification |
| `torch` | ≥ 2.2 | huấn luyện (CUDA trên Kaggle) |
| `datasets` | ≥ 2.14 | load/save dataset |
| `accelerate` | ≥ 0.28 | trainer |
| `seqeval` | ≥ 1.2 | tính F1 token-level cho NER |
| `evaluate` | ≥ 0.4 | metrics |
| `sentencepiece` / `protobuf` | — | tokenizer PhoBERT |
| `scikit-learn` | ≥ 1.3 | metrics, phân tích lỗi |
| `FlagEmbedding` hoặc `sentence-transformers` | ≥ 2.7 | BGE-M3 embeddings |

### 1.3. LLM

| Công cụ | Vai trò | Ghi chú |
|---|---|---|
| `google-generativeai` (SDK Gemini) | provider chính | free tier; dùng `gemini-3.5-flash-lite` (15 RPM / 500 RPD) |
| `groq` | provider dự phòng | OpenAI-compatible; dùng `openai/gpt-oss-20b` (30 RPM / 1.000 RPD) |
| `litellm` (tuỳ chọn) | lớp trung gian đa provider | nếu muốn đổi provider linh hoạt |
| `bitsandbytes` + `transformers` | model mở lượng tử hóa 4-bit | chạy trên Kaggle GPU cho bulk trích xuất |

> **Lưu ý (đã verify 11/2026):** `gemini-2.0-flash` đã mất quota free; `gemini-2.5-*` đã deprecated; Groq đã retire `llama-3.1-8b-instant` và `llama-3.3-70b-versatile` (16/08/2026). Xem bảng đầy đủ ở [05-du-lieu-va-nguon.md](05-du-lieu-va-nguon.md#84-mô-hình-llm-free-tier-tính-đến-112026).
> **Trích xuất LLM trên toàn corpus KHÔNG dùng API free tier** (quota ~3.500 req/ngày ≪ 150.000–400.000 câu) → dùng model mở trên Kaggle GPU.

### 1.4. Đồ thị & backend

| Công cụ | Vai trò | Ghi chú |
|---|---|---|
| Neo4j Community 5.x | lưu trữ KG | chạy bằng Docker; có sẵn Docker 29.9 |
| `neo4j` (driver Python) | truy vấn | dùng session `READ` |
| `neo4j-admin` | dump/nhập DB | cho F5 |
| FastAPI | REST API | |
| Uvicorn | ASGI server | |
| Pydantic v2 | validate request/response | |
| `python-dotenv` | nạp `.env` | |
| `httpx` | gọi LLM API + client HTTP | |

### 1.5. Frontend

| Công cụ | Vai trò |
|---|---|
| React 18 + TypeScript | UI |
| Vite 5 | build/dev server |
| Cytoscape.js | đồ thị tương tác |
| `cytoscape-dagre` | layout cây gia phả |
| `react-leaflet` + `leaflet` | bản đồ (H8) |
| Recharts | biểu đồ thống kê (I1) |
| TanStack Query | quản lý state fetch |
| `react-markdown` | render câu trả lời markdown |

### 1.6. Đánh giá & quản trị

| Công cụ | Vai trò |
|---|---|
| Label Studio | gán nhãn NER/RE (I3) |
| `pytest` | unit + integration test |
| `datasets` | quản lý các bộ đánh giá |

---

## 2. Môi trường phát triển

### 2.1. Yêu cầu

| Thành phần | Tối thiểu | Khuyến nghị |
|---|---|---|
| RAM | 8 GB | 16 GB (24 GB nếu chạy Neo4j + backend + frontend cùng lúc) |
| CPU | 4 core | 8 core |
| GPU | không | chỉ cần cho Kaggle; local dùng CPU cho suy luận số lượng nhỏ |
| Đĩa | 20 GB | 50 GB (dump ~2 GB + artifacts + models) |
| OS | Linux/macOS/Windows | Linux đã kiểm tra |

### 2.2. Cài đặt

```bash
# 1. Tạo môi trường
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Cấu hình biến môi trường
cp .env.example .env
# điền GEMINI_API_KEY, GROQ_API_KEY, NEO4J_PASSWORD

# 3. Chạy Neo4j
docker compose up -d neo4j
# đợi ~30s, mở http://localhost:7474 để đặt mật khẩu (nếu chưa đặt)

# 4. Chạy backend
uvicorn backend.app.main:app --reload --port 8000

# 5. Chạy frontend
cd frontend && npm install && npm run dev
```

### 2.3. Docker Compose

Dịch vụ:

| Service | Cổng | Ghi chú |
|---|---|---|
| `neo4j` | 7474 (HTTP), 7687 (Bolt) | volume riêng, `NEO4J_AUTH=neo4j/<password>` |
| `backend` | 8000 | gắn `data/`, `models/` |
| `frontend` | 5173 | dev server, proxy `/api` → backend |
| `labelstudio` | 8080 | tuỳ chọn (I3) |

**Cấu hình Neo4j cho máy yếu** (`docker-compose.yml`):
```yaml
environment:
  - NEO4J_AUTH=neo4j/${NEO4J_PASSWORD:-neo4jpass}
  - NEO4J_server_memory_heap_initial__size=512m
  - NEO4J_server_memory_heap_max__size=1G
  - NEO4J_server_memory_pagecache_size=512m
```

### 2.4. Biến môi trường (`.env.example`)

```bash
# LLM
GEMINI_API_KEY=
GROQ_API_KEY=
LLM_PRIMARY_PROVIDER=gemini
LLM_PRIMARY_MODEL=gemini-3.5-flash-lite
LLM_FALLBACK_PROVIDER=groq
LLM_FALLBACK_MODEL=openai/gpt-oss-20b
LLM_TEMPERATURE=0.0

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=
NEO4J_READER_USER=reader
NEO4J_READER_PASSWORD=
NEO4J_DATABASE=neo4j

# Dữ liệu
DUMP_VERSION=20251101
WIKI_LANG=vi

# Ứng dụng
API_HOST=127.0.0.1
API_PORT=8000
CORS_ORIGINS=http://localhost:5173
SEED=42
```

> `.env` phải nằm trong `.gitignore`. Chỉ commit `.env.example`.

---

## 3. Quy trình Kaggle (fine-tune & LLM lượng tử hóa)

### 3.1. Nguyên tắc

- **Notebook nhỏ, một mục đích**: mỗi notebook tải input → huấn luyện → lưu output → xuất artifact.
- **Lưu checkpoint liên tục**: `save_total_limit=2`, `save_steps` hợp lý → tránh mất tiến độ khi hết giờ GPU.
- **Seed cố định** 42 trong `TrainingArguments`.
- **Output ra dataset Kaggle** hoặc file `.pt`/`.safetensors` để tải về.
- **Ghi log**: loss, F1 theo epoch vào `reports/kaggle_<tên>.md`.

### 3.2. Notebook dự kiến

| Notebook | Input | Output | Thời gian GPU ước lượng |
|---|---|---|---|
| `01_train_ner.ipynb` | `ner_silver.jsonl` | `models/ner/` + metrics | 30–60 phút (T4, ~150k câu, 3 epoch) |
| `02_infer_ner.ipynb` | `documents.jsonl` + model | `ner_predictions.jsonl` | 20–40 phút |
| `03_train_re.ipynb` | `re_train.jsonl` | `models/re/` + metrics | 45–90 phút |
| `04_infer_re.ipynb` | coref + model | `re_phobert.jsonl` | 30–60 phút |
| `05_embed_entities.ipynb` | `entities.jsonl` | `entity_embeddings.npy` | 15–30 phút |
| `06_llm_extract_kaggle.ipynb` | sentences (toàn corpus) | `re_llm_kaggle.jsonl` | 1–3 giờ (model mở 4-bit) |

### 3.3. Mẹo tiết kiệm quota GPU

- `max_len=256`, `batch_size=32`, `fp16=True`, `gradient_accumulation_steps` nếu GPU yếu.
- Dùng `datasets` streaming + `shuffle(seed=42)`.
- Xuất checkpoint **mỗi epoch** để không mất khi phiên hết giờ.
- Nếu phiên hết giờ → tải checkpoint cuối từ output Kaggle, chạy tiếp ở phiên sau.

---

## 4. Quy trình vận hành thường ngày

| Việc | Lệnh (dự kiến) |
|---|---|
| Tải dump | `python scripts/download_dump.py --lang vi` |
| Chạy toàn bộ pipeline | `bash scripts/run_pipeline.sh --config configs/default.yaml` |
| Chạy một module | `python -m src.preprocess.filter_articles --config configs/default.yaml` |
| Nạp KG vào Neo4j | `python scripts/load_neo4j.py --batch 1000` |
| Kiểm tra chất lượng KG | `python scripts/validate_graph.py` |
| Chạy đánh giá | `python scripts/evaluate.py --all --out reports/` |
| Xuất đồ thị | `bash scripts/export_graph.sh` |
| Chạy test | `pytest -q` |
| Xem log | `tail -f logs/<module>.log` |

---

## 5. Quản lý bí mật

| Quy tắc | Thực hiện |
|---|---|
| Không commit key | `.env` trong `.gitignore` |
| Cung cấp template | `.env.example` chỉ chứa tên biến, giá trị rỗng |
| Quét secret trước commit | `git grep -nE "(sk-|AIza|api[_-]?key\s*=)" -- . ':!.env.example'` |
| Log không chứa key | Logger chỉ log tên biến, không log giá trị |
| LLM client | Đọc key từ `os.environ`, không lưu vào config file |
| Rotate key | Nếu lỡ commit → thu hồi và tạo key mới ngay |

---

## 6. `.gitignore` dự kiến

```gitignore
.venv/
__pycache__/
*.pyc
.env
data/raw/
data/interim/
data/processed/
data/knowledge_base/*.npy
models/
logs/
reports/*.json
*.log
.DS_Store
node_modules/
dist/
.vite/
.kaggle/
```

> `docs/`, `configs/`, `src/`, `backend/`, `frontend/`, `scripts/`, `tests/`, `notebooks/`, `requirements.txt`, `docker-compose.yml`, `.env.example` → **có trong git**.

---

## 7. Ma trận license của dependency

| Nhóm | License chủ yếu | Ghi chú |
|---|---|---|
| FastAPI, Uvicorn, Pydantic | MIT / BSD | |
| Neo4j driver + Community | Apache-2.0 | Community miễn phí cho mục đích học tập |
| React, Vite, Cytoscape, Leaflet, Recharts | MIT | |
| PyTorch | BSD-3 | |
| Transformers | Apache-2.0 | |
| PhoBERT (`vinai/phobert-base`) | Apache-2.0 | trích dẫn trong báo cáo |
| BGE-M3 | MIT | trích dẫn trong báo cáo |
| Gemini SDK | Apache-2.0 | + điều khoản dịch vụ Google AI Studio |
| Groq SDK | MIT | + điều khoản dịch vụ Groq |
| Label Studio | Apache-2.0 | |

---

## 8. Checklist môi trường

- [ ] Python 3.12 + venv đã tạo
- [ ] `pip install -r requirements.txt` thành công
- [ ] `.env` đã tạo từ `.env.example`, đã điền key
- [ ] Docker Compose khởi động Neo4j thành công, truy cập `localhost:7474` được
- [ ] Tài khoản `reader` đã tạo trong Neo4j **và** đã kiểm chứng session `READ_ACCESS` chặn ghi (Community không có RBAC)
- [ ] Backend chạy, `/api/health` trả `ok`
- [ ] Frontend chạy ở `localhost:5173`
- [ ] Kaggle: đã bật GPU, đã mount dataset, đã test tải mô hình từ HuggingFace
- [ ] Label Studio đã cài và tạo project NER + RE
- [ ] `pytest -q` chạy xanh trên máy local

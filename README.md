# Knowledge Graph Lịch sử Việt Nam

Xây dựng Knowledge Graph lịch sử Việt Nam từ Wikipedia tiếng Việt và hệ thống hỏi đáp bằng ngôn ngữ tự nhiên (Text-to-Cypher).

> Đồ án nhóm môn Xử lý ngôn ngữ tự nhiên (NLP).

## Bắt đầu nhanh

```bash
# Đọc trước khi code
cat AGENTS.md              # hướng dẫn cho AI agent + người mới
cat docs/CONTEXT.md        # quyết định đã chốt, QID, model
cat docs/PROGRESS.md       # đang ở phase nào, việc tiếp theo

# Phase 0 — bootstrap
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # điền GEMINI_API_KEY, GROQ_API_KEY, NEO4J_PASSWORD
docker compose up -d neo4j
uvicorn backend.app.main:app --reload --port 8000
cd frontend && npm install && npm run dev
```

## Tài liệu

| # | Tài liệu | Nội dung |
|---|---|---|
| — | [AGENTS.md](AGENTS.md) | **Hướng dẫn làm việc** — đọc file này trước tiên |
| — | [docs/CONTEXT.md](docs/CONTEXT.md) | **Context sống** — quyết định đã chốt, QID, model, câu hỏi mở |
| — | [docs/PROGRESS.md](docs/PROGRESS.md) | Trạng thái từng phase, kết quả đo được |
| — | [docs/GLOSSARY.md](docs/GLOSSARY.md) | Thuật ngữ |
| — | [docs/DECISIONS.md](docs/DECISIONS.md) | Nhật ký quyết định kiến trúc |
| 00 | [Tổng quan](docs/00-tong-quan.md) | Mục tiêu, phạm vi, nguyên tắc thiết kế, chỉ số |
| 01 | [Yêu cầu chức năng](docs/01-requirements-chuc-nang.md) | 9 module A–I kèm tiêu chí nghiệm thu |
| 02 | [Yêu cầu phi chức năng](docs/02-requirements-phi-chuc-nang.md) | Hiệu năng, độ chính xác, tin cậy, tái lập, bảo mật |
| 03 | [Kiến trúc hệ thống](docs/03-kien-truc-he-thong.md) | Offline/online, luồng dữ liệu, API, cấu trúc thư mục |
| 04 | [Schema KG](docs/04-schema-knowledge-graph.md) | Node, quan hệ, thuộc tính, Cypher DDL |
| 05 | [Dữ liệu và nguồn](docs/05-du-lieu-va-nguon.md) | Nguồn, giấy phép, QID đã verify, quota LLM |
| 06 | [Kế hoạch triển khai](docs/06-ke-hoach-trien-khai.md) | Lộ trình 12 tuần, milestone, rủi ro |
| 07 | [Đánh giá và kiểm thử](docs/07-danh-gia-va-kiem-thu.md) | Chiến lược auto-gold, định nghĩa chỉ số, checklist |
| 08 | [Công cụ và môi trường](docs/08-cong-cu-va-moi-truong.md) | Công cụ, môi trường, quy trình Kaggle |
| 09 | [Kế hoạch thực thi](docs/09-ke-hoach-thuc-thien.md) | **Đặc tả 15 phase, mỗi phase tự kiểm thử được** |
| — | [Hướng dẫn gán nhãn](docs/annotation-guidelines.md) | Quy tắc gán NER/RE cho Label Studio |

## Cấu trúc thư mục

```
docs/        đặc tả + context
configs/    *.yaml — nguồn sự thật cho cấu hình
src/        pipeline: preprocess, ner, coref, re, link, graph, evaluation, common
backend/    FastAPI
frontend/   React + TS + Cytoscape
scripts/    CLI: download, load_neo4j, validate_graph, evaluate, export_graph
notebooks/  Kaggle: train_ner, train_re, embed_entities, llm_extract
tests/      pytest
data/       raw, interim, processed, knowledge_base  (gitignored)
models/     checkpoints  (gitignored)
reports/    kết quả đánh giá + báo cáo phase
```

## Công nghệ

| Hạng mục | Chọn |
|---|---|
| Backend | FastAPI + Neo4j 5 Community (Docker) |
| Frontend | React 18 + TypeScript + Vite + Cytoscape.js |
| Mô hình | PhoBERT (NER/RE) · BGE-M3 (entity linking) |
| LLM | Bulk: model mở lượng tử hóa trên Kaggle GPU · API: Gemini `gemini-3.5-flash-lite` + Groq `openai/gpt-oss-20b` |
| Dữ liệu | Wikipedia tiếng Việt dump (CC BY-SA 4.0) + Wikidata (CC0) |

## Phạm vi

9 triều đại: **Ngô, Đinh, Tiền Lê, Lý, Trần, Hồ, Lê sơ, Tây Sơn, Nguyễn** — 2.000–5.000 bài Wikipedia.

## License dữ liệu

- Wikipedia tiếng Việt: **CC BY-SA 4.0** → mọi node/edge có `wiki_url` trỏ về bài gốc.
- Wikidata: **CC0**.

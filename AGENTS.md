# AGENTS.md — Hướng dẫn cho AI Agent

> Đọc file này **trước khi làm bất cứ việc gì** trong repo này.
> Mục tiêu: một AI agent (không có memory giữa các phiên) có thể tiếp tục đúng việc đang dở.

## 1. Dự án là gì

Xây **Knowledge Graph lịch sử Việt Nam** từ Wikipedia tiếng Việt + **hệ thống hỏi đáp Text-to-Cypher**.

| Hạng mục | Giá trị |
|---|---|
| Backend | FastAPI (Python 3.12) + Neo4j 5 Community (Docker) |
| Frontend | React 18 + TypeScript + Vite + Cytoscape.js |
| Mô hình | PhoBERT (NER/RE), BGE-M3 (entity linking) |
| LLM | Bulk: model mở lượng tử hóa trên Kaggle GPU · API: Gemini `gemini-3.5-flash-lite` + Groq `openai/gpt-oss-20b` |
| Dữ liệu | Wikipedia tiếng Việt dump (CC BY-SA 4.0) + Wikidata (CC0) |
| Phạm vi | 9 triều đại: Ngô, Đinh, Tiền Lê, Lý, Trần, Hồ, Lê sơ, Tây Sơn, Nguyễn · 2.000–5.000 bài |

## 2. Đọc gì trước khi làm việc

| Khi nào | Đọc file |
|---|---|
| Bắt đầu phiên làm việc | `docs/CONTEXT.md` (context + quyết định đã chốt), `docs/PROGRESS.md` (phase đang làm) |
| Làm 1 phase của pipeline | `docs/09-ke-hoach-thuc-thien.md` → phần phase tương ứng |
| Định nghĩa quan hệ / node / thuộc tính | `docs/04-schema-knowledge-graph.md` |
| Ghi/chạy code Python | `.cursor/rules/python-standards.mdc`, `.cursor/rules/data-contracts.mdc` |
| Làm frontend | `.cursor/rules/frontend.mdc` |
| Viết prompt LLM / gọi API | `.cursor/rules/llm-usage.mdc` |
| Chạm Cypher | `.cursor/rules/cypher-safety.mdc` |
| Gán nhãn | `docs/annotation-guidelines.md` |

### Skills dự án (`.cursor/skills/`)

| Skill | Khi nào dùng |
|---|---|
| `run-phase` | Thực hiện 1 phase của `docs/09` — đọc skill này **trước khi** bắt đầu code |
| `check-context` | Câu hỏi về schema, QID, quan hệ, model, trạng thái tiến độ (trả lời nhanh, không cần code) |
| `validate-graph` | Kiểm tra chất lượng KG trong Neo4j (thiếu bằng chứng, quan hệ lạ, trùng lặp) |

**Quy tắc vàng:** số liệu, QID, tên quan hệ, ID format **đã chốt** nằm trong `docs/CONTEXT.md`. Không tự ý đổi. Nếu cần đổi → cập nhật cả `docs/CONTEXT.md` **và** file liên quan trong cùng một lần.

## 3. Cấu trúc thư mục

```
docs/          # đặc tả, context, quyết định, glossary, hướng dẫn gán nhãn
configs/      # *.yaml — nguồn sự thật cho cấu hình (không hard-code trong code)
src/          # pipeline: preprocess, ner, coref, re, link, graph, qa, evaluation, common
backend/      # FastAPI: app/api, app/services, app/prompts
frontend/     # React + Vite + TS
scripts/      # CLI một lần: download, load_neo4j, evaluate, export_graph
notebooks/    # Kaggle notebooks (train_ner, train_re, embed_entities, llm_extract)
tests/        # pytest unit + integration
data/         # raw/, interim/, processed/, knowledge_base/  (gitignored)
models/       # checkpoints (gitignored)
reports/      # kết quả đánh giá, phase reports
```

## 4. Quy trình làm việc bắt buộc

1. **Đọc `docs/PROGRESS.md`** để biết phase hiện tại và phase kế tiếp.
2. **Chỉ làm 1 phase mỗi lần.** Phase = 1 phần trong `docs/09-ke-hoach-thuc-thien.md`.
3. **Tuân thủ Input contract / Output contract** của phase đó. Không đổi format output.
4. **Chạy lệnh kiểm thử** ghi trong phase. Không bỏ qua.
5. **Đạt Gate** (checklist trong phase) mới được sang phase sau.
6. **Ghi `reports/phase_XX_report.md`**: mô tả, lệnh đã chạy, output thực tế, gate pass/fail, sai lệch.
7. **Cập nhật `docs/PROGRESS.md`** (trạng thái phase, ngày, kết quả chính).
8. Nếu lệch khỏi kế hoạch → ghi vào `reports/deviations.md` và cập nhật `docs/CONTEXT.md`.

> **Lưu ý về phạm vi:** setup vibe-coding (`AGENTS.md`, rules, skills, docs) là việc *độc lập* với triển khai pipeline.
> Chỉ bắt đầu code khi người dùng **nói rõ** muốn triển khai phase nào. Đọc `docs/PROGRESS.md` để biết phase hiện tại,
> nhưng **không tự ý** tạo `src/`, `backend/`, `frontend/`, tải dữ liệu hay khởi động hạ tầng nếu chưa được yêu cầu.

## 5. Nguyên tắc kỹ thuật (không được vi phạm)

| # | Nguyên tắc |
|---|---|
| 1 | **Bằng chứng bắt buộc** — mọi triple/cạnh có `evidence_sentence` + `source_url` + `confidence` + `method`. Không có bằng chứng → không có cạnh. |
| 2 | **Cypher chỉ đọc** — validator tĩnh chặn `CREATE/MERGE/DELETE/SET/REMOVE/DROP/CALL`; session Neo4j mở với `default_access_mode=READ_ACCESS` (server từ chối ghi, kể cả superuser); luôn `LIMIT ≤ 100`; timeout 10s. |
| 3 | **Không bịa** — khi KG không có dữ liệu, trả "Không có trong dữ liệu". Không suy đoán ngoài kết quả truy vấn. |
| 4 | **Idempotent** — nạp KG bằng `MERGE` theo `entity_id`; chạy lại không sinh bản ghi trùng. |
| 5 | **Schema đóng** — 18 quan hệ cố định (danh sách tại `docs/04`); không sinh quan hệ ngoài danh sách. |
| 6 | **Tái lập** — seed `42`; chia tập theo bài (không theo câu); ghi `dump_version` + `model_name` vào mọi artifact. |
| 7 | **Tách offline/online** — việc nặng (fine-tune, LLM bulk, embedding) chạy offline trên Kaggle và ghi artifact; tầng online chỉ đọc artifact + Neo4j + LLM API. |
| 8 | **Không commit secret** — key trong `.env` (gitignored), chỉ commit `.env.example`. |
| 9 | **Ngôn ngữ** — UI, prompt, tài liệu, comment: **tiếng Việt hoặc tiếng Anh**. Tuyệt đối không dùng tiếng Trung. |
| 10 | **Tiếng Việt có dấu** trong dữ liệu; chuẩn hóa bỏ dấu chỉ dùng cho *tra cứu* (`name_normalized`), không dùng làm tên hiển thị. |

## 6. Định dạng ID (bất biến)

| Đối tượng | Format | Ví dụ |
|---|---|---|
| `doc_id` | `doc_<page_id>` | `doc_12345` |
| `sentence_id` | `s<page_id>_<para_idx>_<sent_idx>` | `s12345_0_3` |
| `mention_id` | `m<sentence_id>_<idx>` | `ms12345_0_3_0` |
| `entity_id` | `ent_<slug>_<hash8>` | `ent_le_loi_1a2b3c4d` |
| `year_id` | `year_<năm>` | `year_1385` |
| `nil_id` | `nil_<hash8>` | `nil_9f2c1a7b` |

`hash8 = sha1(f"{type}|{name_normalized}")[:8]`

## 7. Artifact (JSONL, UTF-8, không BOM, 1 record/dòng)

| Đường dẫn | Sinh ra ở phase | Nội dung |
|---|---|---|
| `data/interim/documents.jsonl` | 1 | bài đã lọc + clean_text + sentences + links |
| `data/interim/infobox_triples.jsonl` | 3 | triple từ infobox |
| `data/interim/ner_silver.jsonl` | 4 | nhãn bạc NER |
| `data/interim/ner_predictions.jsonl` | 5 | NER dự đoán (offset ký tự) |
| `data/interim/coref_resolved.jsonl` | 6 | mention + canonical_id |
| `data/interim/re_train.jsonl` | 7 | tập huấn luyện RE (Wikidata DS) |
| `data/interim/triples_merged.jsonl` | 8 | triple hợp nhất |
| `data/knowledge_base/entities.jsonl` | 9 | entity + alias + QID |
| `data/knowledge_base/graph.jsonl` | 10 | nodes + edges cho Neo4j |

## 8. Lệnh thường dùng

```bash
source .venv/bin/activate
pytest -q tests/                                   # test unit + integration
docker compose up -d neo4j                        # DB
python scripts/load_neo4j.py --batch 1000          # nạp KG
python scripts/validate_graph.py                   # kiểm tra chất lượng KG
python scripts/evaluate.py --all --out reports/    # đánh giá (sau phase 13)
```

## 9. Khi bị kẹt

1. Đọc mục **"Lùi"** của phase hiện tại trong `docs/09-ke-hoach-thuc-thien.md`.
2. Nếu vẫn kẹt → đọc `docs/CONTEXT.md` mục "Câu hỏi mở" và "Quyết định đã chốt".
3. Nếu vẫn kẹt → **hỏi người dùng** thay vì đoán. Đặc biệt khi câu hỏi liên quan: phạm vi dữ liệu, thay đổi schema, ngưỡng chất lượng, chi phí LLM.
4. Ghi sai lệch vào `reports/deviations.md`.

## 10. File quan trọng

| File | Vai trò |
|---|---|
| `docs/CONTEXT.md` | **Context sống**: quyết định đã chốt, QID, model, quota, câu hỏi mở |
| `docs/PROGRESS.md` | Trạng thái từng phase, kết quả đo được, việc tiếp theo |
| `docs/DECISIONS.md` | Nhật ký quyết định kiến trúc (ADR-lite) |
| `docs/GLOSSARY.md` | Thuật ngữ Việt ↔ Anh ↔ trường dữ liệu |
| `docs/annotation-guidelines.md` | Hướng dẫn gán nhãn NER/RE |
| `docs/09-ke-hoach-thuc-thien.md` | **Kế hoạch thực thi chi tiết theo phase** (nguồn chân lý cho agent) |

## 11. Bảo vệ dữ liệu đầu vào

Không bao giờ:
- xóa hoặc ghi đè file trong `data/` mà không nêu rõ trong báo cáo phase;
- sửa trực tiếp record trong DB để "cho xanh" — sửa ở pipeline rồi nạp lại;
- commit `.env`, key API, checkpoint mô hình.

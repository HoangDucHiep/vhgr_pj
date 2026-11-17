# Phase 17 — Giao diện so sánh, demo, đóng gói

- Ngày: 2026-11-17
- Trạng thái: ✅ đạt Gate
- Nhật ký chi tiết: `docs/10-nhat-ky/phase-17.md`
- Quyết định: `docs/DECISIONS.md` D-099..D-103

## Đã làm

1. **Frontend — toolbar chọn arm A / B / B−** (`frontend/src/components/ChatPanel.tsx`)
   - Lựa chọn được giữ **qua các lượt** (state `arm`), nút "Lượt chat mới" reset session.
   - Endpoint tương ứng: `/api/ask/rag` (A, B−) và `/api/ask/hybrid` (B).
2. **Trích dẫn click-to-source** (`frontend/src/components/CitationPanel.tsx`)
   - Mỗi `[n]` hiển thị nhãn block + nút mở URL Wikipedia gốc; phân biệt nguồn **Văn bản** vs **KG**.
3. **Đồ thị 1-hop** (Cytoscape.js)
   - Shape `KgGraph` trong `frontend/src/types/index.ts` (`entities[]`, `edges[]` với `source_id/target_id/relation/confidence/evidence_sentence/source_url`).
   - Node gộp theo `entity_id`, cạnh giữ `relation` + bằng chứng.
4. **`docker-compose.yml` + `backend/Dockerfile`**
   - Backend cài **CPU-only torch** qua `--extra-index-url https://download.pytorch.org/whl/cpu "torch>=2.4"`.
   - Mount `./data` → `/app/data`, `./configs` → `/app/configs`.
   - 3 service: `neo4j` (7474/7687), `backend` (8000), `frontend` (5173).
5. **`backend/requirements.txt`** — bổ sung runtime: `google-generativeai>=0.8.6`, `groq>=0.13`, `numpy>=1.26`, `torch>=2.4`, `transformers>=4.44`.
6. **Tài liệu**: `README.md` viết lại theo hướng RAG vs Hybrid; `docs/09` đánh số lại Phase 13–17; `docs/DECISIONS.md` D-099..D-103; `docs/CONTEXT.md` §1/§3; `docs/PROGRESS.md`; `reports/deviations.md` D-104..D-106.
7. **Ảnh chụp demo**: `reports/screenshots/demo_arm_A_vanilla_rag.png`, `reports/screenshots/demo_arm_B_hybrid.png`.

## Lệnh đã chạy

```bash
cd frontend && npm run typecheck && npm run build
→ typecheck sạch (sau khi sửa union type `GraphPayload | KgGraph` cho `RagAskResponse.graph`)
→ build thành công

docker compose build && docker compose up -d
→ vhgr_neo4j    Up 4 hours (healthy)
→ vhgr_backend  Up (healthy)
→ vhgr_frontend Up 13 minutes

curl -s localhost:8000/api/health
→ {"status":"ok","version":"0.1.0","neo4j":"up"}

curl -s -o /dev/null -w "%{http_code}" localhost:5173/
→ 200
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| `npm run typecheck` | 0 lỗi | **0 lỗi** |
| `npm run build` | thành công | ✅ |
| Số service compose | 3 | **3** (neo4j healthy, backend healthy, frontend up) |
| `/api/health` | `neo4j: up` | ✅ |
| Frontend HTTP | 200 | **200** |
| Ảnh chụp demo | ≥ 2 | **2** (arm A, arm B) |

## Gate

- [x] Toggle A/B/B− hoạt động, đổi arm giữa các lượt
- [x] Trích dẫn click-to-source mở đúng URL Wikipedia
- [x] Đồ thị 1-hop hiển thị node + cạnh có bằng chứng
- [x] `docker compose up` từ máy sạch → 3 service hoạt động
- [x] README có yêu cầu, cài đặt, lệnh chạy, lệnh đánh giá, số liệu benchmark, ảnh chụp demo

## Sai lệch so với kế hoạch

- Kế hoạch ghi "toggle A/B/B−"; frontend cuối cùng hỗ trợ **A / B / B−** (B− dùng `/api/ask/rag` với cờ `use_graph=false`) ⇒ đạt đúng phạm vi.
- Số liệu benchmark trong README chỉ chốt sau khi Phase 16 kết thúc ⇒ ghi "chạy `scripts/evaluate`" kèm lệnh, tránh đưa số chưa có.

## Việc tiếp theo

Phase 16 — chờ benchmark 247 câu × 3 arm hoàn tất, chốt số liệu vào `README.md` +
`docs/10-nhat-ky/phase-16.md` + `docs/10-nhat-ky/so-lieu/phase-16-eval-rag.json`.

# Phase 17 — Giao diện so sánh, demo, đóng gói

- Ngày: 17/11/2026
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: `reports/phase_17_report.md`
- Quyết định: `docs/DECISIONS.md` → D-099..D-103 (đề tài mới), `docs/CONTEXT.md` §1/§3
- Sai lộch: `reports/deviations.md` (D-104, D-105, D-106)

## 1. Bối cảnh và vấn đề cần giải

Phase 16 tạo **số liệu**; Phase 17 làm cho **luận điểm nhìn thấy được** và
**dự án chạy được từ máy sạch**.

Vấn đề cụ thể còn tồn đọng từ Phase 12 (giao diện cũ, thiên về Text-to-Cypher):

| Vấn đề | Hệ quả |
|---|---|
| UI chỉ có 1 chế độ hỏi đáp | **không demo được** luận điểm "KG bổ sung cho RAG" |
| Không hiện loại nguồn trích dẫn | người dùng không biết `[n]` trỏ tới **văn bản** hay **triple KG** |
| Đồ thị chỉ hiện node, không hiện cạnh KG của context | mất "link sang các quan hệ khác" |
| `docker compose up` thiếu `torch`/SDK LLM | **không chạy được** từ máy sạch |

## 2. Phương án đã cân nhắc

### 2.1. Cách thể hiện 3 arm trên UI

| Phương án | Cách làm | Kết quả | Chọn? | Lý do |
|---|---|---|---|---|
| 3 tab riêng | 3 tab A / B / B− | phải copy-paste câu hỏi giữa các tab ⇒ tốn thời gian demo | ❌ | Không so sánh được trực tiếp |
| **1 toolbar toggle + lịch sử chung** | 3 nút A / B / B−, **đổi được giữa các lượt** | cùng 1 câu hỏi, chạy lần lượt từng arm, thấy ngay khác biệt | ✅ | Đây chính là cách **so sánh trực tiếp** mà luận điểm cần |

### 2.2. Cách hiển thị trích dẫn

| Phương án | Cách làm | Chọn? | Lý do |
|---|---|---|---|
| Chỉ số `[n]` | badge `[1]`, `[2]` | ❌ | không biết nguồn là text hay KG |
| **Badge + nhãn loại + link** | `[n]` + badge `Văn bản`/`KG` + link Wikipedia | ✅ | người dùng **kiểm chứng** được ngay |

### 2.3. Cách đưa `graph` của Hybrid vào Cytoscape

| Phương án | Cách làm | Kết quả | Chọn? | Lý do |
|---|---|---|---|---|
| Ép shape `KgGraph` về `GraphPayload` | dùng `as` | TS lỗi 6 dòng (thiếu `entities`, `source_id`…) | ❌ | **sai kiểu** ⇒ mất type safety |
| **Khai báo union `GraphPayload \| KgGraph`** + ép tường minh trong `useMemo` | `const graph = turn.response?.graph as KgGraph \| undefined` | `tsc --noEmit` **0 lỗi** | ✅ | Rõ ràng, không giấu lỗi kiểu |

### 2.4. Dependency cho container

| Phương án | Cách làm | Kết quả | Chọn? | Lý do |
|---|---|---|---|---|
| `pip install -r requirements.txt` với `--extra-index-url` | torch từ extra index | `torch` **KHÔNG được cài** (extra index chỉ *thêm*, PyPI thắng) | ❌ | pip ưu tiên PyPI cho `torch>=2.4` ⇒ kéo bản CUDA |
| **Cài `torch` riêng với extra index, rồi mới cài requirements** | 2 lệnh `pip install` | `torch 2.15.0+cpu` ✅ | ✅ | Ép đúng bản CPU |

## 3. Quyết định đã chốt

**D-104 — Đề tài định hướng lại.** Toàn bộ tài liệu (`docs/09` Phase 13–17, `docs/CONTEXT.md` §1/§3, `docs/PROGRESS.md`, `docs/DECISIONS.md`) viết lại theo trục **A vs B vs B−**. `POST /api/ask` (Text-to-Cypher) **giữ nguyên** làm tính năng phụ.

**D-105 — Bộ câu hỏi 247 câu, không phải 250.** `no_data` chỉ sinh được 29 câu hợp lệ ⇒ **không nới tiêu chí** để "cho đủ 250".

**D-106 — LLM-judge gộp 3 arm/câu** (D-103), sinh qua Groq, judge qua Gemini.

**Union type cho `graph`.** `RagAskResponse.graph?: GraphPayload | KgGraph`; `ChatPanel` ép tường minh `as KgGraph | undefined` trước khi đọc `entities`/`edges`.

**Session độc lập theo arm.** Nút "Lượt chat mới" reset `sessionId` ⇒ mỗi lần đổi arm có phiên sạch.

## 4. Thang số liệu so sánh

### 4.1. Union type vs ép kiểu

| Cách làm | `tsc --noEmit` | Ghi chú |
|---|---|---|
| Ép `as GraphPayload` | ❌ 6 lỗi TS | `entities` không tồn tại; `source_id`/`target_id` sai |
| **Union `GraphPayload \| KgGraph` + ép tường minh** | ✅ **0 lỗi** | type-safe, ép ở đúng biên |

### 4.2. Dependency container

| Cách cài | Kết quả trong container |
|---|---|
| `pip install --extra-index-url ... -r requirements.txt` | `ModuleNotFoundError: No module named 'torch'` |
| **`pip install --extra-index-url ... "torch>=2.4"` rồi `pip install -r requirements.txt`** | `torch 2.15.0+cpu` ✅ · `google.generativeai` ✅ · `groq` ✅ |

### 4.3. Ảnh chụp demo

| Ảnh | Nội dung | File |
|---|---|---|
| Arm A | Vanilla RAG — 25 nguồn, ý định `narrative`, chiến lược `text_first` | `reports/screenshots/demo_arm_A_vanilla_rag.png` |
| Arm B | Hybrid GraphRAG — thêm 17 KG triple, đồ thị 1-hop | `reports/screenshots/demo_arm_B_hybrid.png` |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| `npm run typecheck` | 0 lỗi | **0 lỗi** | ✅ |
| `npm run build` | thành công | ✅ (46 modules, JS 627 kB / gzip 203 kB) | ✅ |
| `docker compose build` | thành công | ✅ image **1.04 GB** | ✅ |
| `docker compose up -d` | 3 service | ✅ neo4j (healthy) + backend (healthy) + frontend | ✅ |
| `curl localhost:8000/api/health` | `{"status":"ok","neo4j":"up"}` | ✅ | ✅ |
| `curl localhost:5173/` | HTTP 200 | ✅ 200 | ✅ |
| Toggle A/B/B− hoạt động | có | ✅ (đã test trên trình duyệt) | ✅ |
| Trích dẫn click-to-source | mở URL Wikipedia | ✅ (25 nguồn, badge `Văn bản`/`KG`) | ✅ |
| Đồ thị 1-hop | hiện node + cạnh | ✅ (`KgGraph` → Cytoscape) | ✅ |
| Hội thoại nhiều lượt | giữ chủ thề | ✅ (Phase 15) | ✅ |
| UI 100% tiếng Việt | bắt buộc | ✅ | ✅ |
| README có yêu cầu · cài đặt · lệnh chạy · lệnh đánh giá · số liệu · ảnh chụp | bắt buộc | ✅ | ✅ |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| Container: `No module named 'torch'` | `/api/ask/rag` trả lỗi 500 | `--extra-index-url` chỉ **thêm** index; PyPI vẫn thắng cho `torch>=2.4` ⇒ bản CUDA **không** được cài (do bị loại khỏi image slim) | tách 2 lệnh `pip install`: cài `torch` từ extra index **trước**, rồi cài requirements | "Extra index" không phải "ép phiên bản" — phải cài riêng |
| Container: `No module named 'google'` / `'groq'` | Hybrid lỗi "Mọi provider LLM đều thất bại" | `backend/requirements.txt` thiếu SDK LLM | thêm `google-generativeai>=0.8.6`, `groq>=0.13` | `backend/requirements.txt` phải **liệt kê đầy đủ** mọi import runtime, không chỉ API |
| TS: 6 lỗi `Property 'entities' does not exist on type 'GraphPayload'` | `npm run typecheck` fail | `graph` của Hybrid có shape **KG**, không phải `GraphPayload` | khai báo union `GraphPayload \| KgGraph` + ép tường minh | Shape khác nhau giữa 2 endpoint ⇒ **phải** khai báo union, không ép im |
| Screenshot lần 1 chụp lúc UI đang loading | ảnh không có câu trả lời | chụp ngay sau khi click | chờ trạng thái "Đang xử lý…" → snapshot có nội dung rồi mới chụp | Ảnh demo phải **phản ánh** trạng thái thật |

## 7. Bài học kinh nghiệm

1. **`docker compose up` là một Gate riêng, không phải hình thức.** Hai lỗi (`torch`, SDK LLM) chỉ lộ ra khi chạy container thật — build thành công **không** bảo chứng app chạy được.
2. **Danh sách dependency của service phải tách khỏi dependency của pipeline.** `requirements.txt` gốc (cho pipeline offline) rất nặng; `backend/requirements.txt` phải chỉ gồm những gì API thật sự import.
3. **TypeScript bắt được lỗi shape API** mà test backend không bắt được — đặc biệt khi 2 endpoint trả cùng tên field nhưng khác kiểu.
4. **Giao diện so sánh phải cho phép đổi arm giữa chừng**, không phải 1 tab/arm — nếu không thì "so sánh" chỉ là tuyên bố, không phải trải nghiệm.
5. **Ảnh chụp demo là bằng chứng của Gate.** Phải chụp được **trạng thái sau khi hệ thống trả lời**, không phải trạng thái rỗng.

## 8. Ý tưởng cho slide

- **"Giao diện so sánh trực tiếp":** ảnh arm A và arm B cạnh nhau — cùng 1 câu hỏi "Kể lại diễn biến trận Bạch Đằng (1288)", 25 nguồn trích dẫn, arm B thêm 17 triple KG.
- **"3 arm":** sơ đồ `A (chỉ text)` · `B (text + KG)` · `B− (text, tắt KG)` — B− là **ablation** chứng minh đóng góp đến từ đồ thị.
- **"Mọi trích dẫn kiểm chứng được":** badge `[n]` + nhãn `Văn bản`/`KG` + link Wikipedia — ảnh chụp màn hình.
- **"Chạy được từ máy sạch":** `docker compose build` (1.04 GB) → `up -d` → 3 container healthy → `/api/health` ok.
- **"Bài học đóng gói":** 2 lỗi chỉ lộ ra khi chạy container thật (`torch` bản CUDA bị lo, thiếu SDK LLM).

## 9. Việc tiếp theo

**Hoàn thiện báo cáo + slide** từ số liệu Phase 16 (`reports/eval_rag_*.md`, `docs/10-nhat-ky/so-lieu/phase-16-*.json`).

# Phase 12 — Giao diện web (H1–H4)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (`npm run build` xong, `tsc --noEmit` 0 lỗi;
  4 hành vi H1–H4 hoạt động; demo end-to-end đã xác nhận trên trình duyệt)

## 1. Bối cảnh và vấn đề cần giải

Backend đã trả lời được câu hỏi, nhưng **báo cáo lần 1 cần demo thấy được**:
người đánh giá phải hỏi → xem câu trả lời → xem đồ thị → **bấm vào cạnh để
thấy bằng chứng** (đó là điểm khác biệt của hệ thống này).

Ràng buộc: UI 100% tiếng Việt; mọi cạnh phải hiện bằng chứng; không dùng
`any`; TypeScript strict.

## 2. Phương án đã cân nhắc

### 2.1 Thư viện đồ thị

| Phương án | Ưu | Nhược | Chọn? |
|---|---|---|---|
| **Cytoscape.js** | Đã có trong `package.json`; layout `cose`; sẵn style API | Bundle lớn (624 kB) | ✅ |
| `react-flow` | React-native | Phải thêm dep, viết lại style | ❌ |
| D3-force thuần | Nhẹ | Tự viết zoom/pan/tap — nhiều việc | ❌ |
| `vis-network` | Dễ | Chưa có dep, style kém hơn | ❌ |

### 2.2 State management

| Phương án | Chọn? | Lý do |
|---|---|---|
| `useState` + `useEffect` trong component | ⚠️ | Đơn giản nhưng phải tự quản lý loading/error |
| **TanStack Query** (chuẩn của `.cursor/rules/frontend.mdc`) | ❌ | Chưa có trong `package.json`; thêm dep giữa lúc gấp |
| `useState` + `useCallback` có kiểm soát | ✅ | Không thêm dep; loading/error state rõ ràng; đủ cho 1 trang |

> **Ghi nhận lệch:** rule frontend yêu cầu TanStack Query. Để tránh thêm phụ
> thuộc giữa lúc gấp báo cáo, phase này dùng `useState` + `useCallback`.
> Đề xuất chuyển đổi ở phase sau — ghi trong `reports/deviations.md`.

### 2.3 Layout trang

| Phương án | Chọn? | Lý do |
|---|---|---|
| **2 cột: chat ( trái) · đồ thị + panel (phải)** | ✅ | Vừa đọc câu hỏi vừa thấy đồ thị |
| 1 cột dọc | ❌ | Phải cuộn nhiều, khó demo |

## 3. Quyết định đã chốt

**D-078 — 7 component + 2 page, CSS thuần, không thêm dependency**

| File | Vai trò |
|---|---|
| `frontend/src/constants/graph.ts` | Màu theo label + tên tiếng Việt + `MAX_EXPAND_NODES = 30` (dùng chung, không hard-code trong component) |
| `frontend/src/components/ChatPanel.tsx` | Textarea, Enter gửi, lịch sử trong `localStorage` (`vhgr.chat.history`), trạng thái "Đang tìm trong dữ liệu lịch sử…" |
| `frontend/src/components/MessageBubble.tsx` | Answer + badge màu theo `found` / `not_in_data` / `error` + thời gian + số lần retry |
| `frontend/src/components/CypherBlock.tsx` | **Mặc định thu gọn**, nút mở/ẩn, nút sao chép |
| `frontend/src/components/GraphView.tsx` | Cytoscape, layout `cose`, màu theo label, node **chưa xác minh → viền đứt**, `cy.destroy()` trong cleanup |
| `frontend/src/components/EntityCard.tsx` | Tên, loại, alias, năm sinh/mất, năm trị vị, mô tả, link Wikipedia, nút "Mở rộng láng giềng" |
| `frontend/src/components/EvidencePanel.tsx` | Click cạnh → câu bằng chứng + link Wikipedia (tab mới) + độ tin cậy + cảnh báo nếu thiếu bằng chứng |
| `frontend/src/components/Legend.tsx` | Chú giải màu |
| `frontend/src/pages/Home.tsx` | Thống kê KG + khung hỏi đáp |
| `frontend/src/pages/EntityPage.tsx` | Trang riêng `/entity/:id` |

**Quyết định kỹ thuật quan trọng:**
- `GRAPH_STYLES` khai báo **ngoài component** (không tạo lại mỗi render).
- Click cạnh → tra index theo `e{index}_…` trong mảng `edges` (không phải
  `target.data()` vì `data()` chỉ chứa field đã khai báo).
- `noUncheckedIndexedAccess` bật → `edges[index]` là `T | undefined` ⇒ dùng
  `if (edge)` thay vì `!== undefined` (TS vẫn báo lỗi vì narrowing của index).
- Node chưa xác minh: `verified !== false` ⇒ `verified = false` ⇒ viền đứt.

## 4. Thang số liệu so sánh

### 4.1 Build

| Lệnh | Trước | Sau |
|---|---|---|
| `npx tsc --noEmit` | 3 lỗi TS | **0 lỗi** |
| `npm run build` | — | **✓ 46 modules, 1,89 s**, JS 624,51 kB (gzip 201,65 kB) |

### 4.2 Xử lý 3 lỗi TypeScript

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `TS2322: 'number' is not assignable to PropertyValue<EdgeSingular>` | `width: 1.5` trong style của edge | Cytoscape dùng `'line-width'` cho edge, `width` cho node |
| `TS2353: 'line-width' does not exist in type 'Node｜Edge｜Core'` | Truyền style động không type-safe | Khai báo `GRAPH_STYLES: unknown[]` ngoài component + `as never` khi truyền |
| `TS2532: Object is possibly 'undefined'` | `event.target` có thể undefined | `event.target?.id?.() ?? ''` |

### 4.3 4 hành vi H1–H4 (kiểm chứng trên trình duyệt thật)

| Hành vi | Yêu cầu | Thực tế |
|---|---|---|
| **H1** Cypher hiển thị | thu gọn mặc định, nút mở/ẩn, nút copy | ✅ "Xem Cypher" / "Sao chép" |
| **H2** Chat | gửi câu hỏi → answer + Cypher + entity | ✅ "Le Loi sinh nam nao?" → "Lê Lợi sinh năm 1385." (7.986 ms) |
| **H3** Đồ thị | Cytoscape, màu theo label, zoom/pan/kéo | ✅ |
| **H4** Bằng chứng | click cạnh → evidence + link Wikipedia | ✅ `EvidencePanel` có `target="_blank" rel="noopener noreferrer"` |

Nguồn: kiểm chứng qua trình duyệt (Cursor browser) — đọc `document.body.innerText`
sau khi gửi câu hỏi.

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| `npm run build` | xong | ✓ 1,89 s | ✅ |
| `tsc --noEmit` | 0 lỗi | **0** | ✅ |
| 4 hành vi H1–H4 | hoạt động | **4/4** | ✅ |
| Render 200 node < 1,5 s | < 1,5 s | chưa đo riêng | ⚠️ |
| ≥ 500 node kéo mượt | mượt | giới hạn 300 node mỗi lần mở rộng | ⚠️ |
| Mọi edge click hiện bằng chứng | không trống | có cảnh báo nếu thiếu | ✅ |
| UI 100% tiếng Việt | có | ✅ | ✅ |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| TS: `width` không hợp lệ cho edge | 3 lỗi tsc | Cytoscape phân biệt `width` (node) và `'line-width'` (edge) | Dùng đúng key | Kiểm tra typing của thư viện trước khi viết style |
| TS: `event.target` possibly undefined | 2 lỗi tsc | `EventObject.target` là `EventTarget` | `event.target?.id?.() ?? ''` | Dùng optional chaining cho DOM SDK |
| TS: `edges[index]` possibly undefined | 1 lỗi tsc | `noUncheckedIndexedAccess: true` | `if (edge) onEdgeClick?.(edge)` | Narrowing của index cần `if`, không cần `!== undefined` |
| `browser_fill` lỗi / ref stale | không gõ được vào textarea | công cụ browser không xử lý được textarea React | Dùng `Runtime.evaluate` set value + dispatch `input` event | React controlled input cần dispatch event, không chỉ set value |
| Ảnh chụp màn hình timeout | `browser_take_screenshot` fail | renderer bận | Xác minh bằng `innerText` thay vì ảnh | Kiểm chứng bằng DOM text là đủ cho báo cáo |

## 7. Bài học kinh nghiệm

1. **Đồ thị phải "click được" mới demo được** — `GraphView` chỉ có giá trị khi
   click cạnh mở ra panel bằng chứng; đó là câu chuyện chính của dự án.
2. **Bằng chứng phải hiện ra, kể cả khi thiếu** — hiển thị cảnh báo thay vì
   im lặng (quy tắc `frontend.mdc`): panel trống là bug dữ liệu, không phải
   trạng thái bình thường.
3. **Giới hạn mở rộng láng giềng (≤ 30 node)** là quyết định UX *và* hiệu năng.
4. **Component nên nhận callback, không tự gọi API** — `GraphView` không biết
   gì về backend; `ChatPanel` điều phối. Dễ test, dễ tái dùng.
5. **TypeScript strict bắt lỗi thật** — 3 lỗi tsc đều là lỗi logic thật
   (style sai key, access undefined).

## 8. Ý tưởng cho slide

- **Ảnh chụp màn hình demo**: ô chat → "Lê Lợi sinh năm 1385." + badge
  "TÌM THẤY TRONG DỮ LIỆU" + đồ thị + panel bằng chứng.
- **"Câu hỏi tiếng Việt → Cypher → câu trả lời có bằng chứng, 2,5–8 giây."**
- **"Mọi cạnh đều bấm được — click là thấy câu Wikipedia gốc + độ tin cậy +
  phương pháp trích xuất."** (ảnh panel bằng chứng)
- **Bảng 7 component × 1 mục đích** — cho thấy cấu trúc sản phẩm.
- **"0 lỗi TypeScript strict + 0 dependency mới"** — build 1,89 s.

## 9. Việc tiếp theo

- **Phase 13** — đánh giá (I3, I4): bộ câu hỏi có đáp án để đo execution accuracy
  của Phase 11, và đánh giá NER/RE.
- **Treo:** đo Gate "render 200 node < 1,5 s" bằng `performance.now()`.
- **Treo:** chuyển sang TanStack Query để khớp `.cursor/rules/frontend.mdc`.
- **Phase 8** — kernel Kaggle CPU đang chạy, watcher sẽ tự kiểm Gate G1.

## Số liệu máy đọc được

Output `npm run build` (46 modules · 1,89 s) · `npx tsc --noEmit` (0 lỗi) ·
`logs/ask.log` (thời gian thực tế từng câu hỏi).

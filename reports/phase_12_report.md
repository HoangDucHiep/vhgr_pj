# Phase 12 — Giao diện web (H1–H4)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (build sạch, 4/4 hành vi hoạt động)

## Đã làm

- 7 component: `ChatPanel`, `MessageBubble`, `CypherBlock`, `GraphView`, `EntityCard`,
  `EvidencePanel`, `Legend` + `constants/graph.ts` (màu label dùng chung).
- 2 page: `Home` (thống kê + khung hỏi đáp), `EntityPage` (`/entity/:id`).
- `api/client.ts` bổ sung `askQuestion`, `searchEntities`, `fetchGraph`, `fetchEntity`;
  `types/index.ts` khớp output contract Phase 11.
- `App.tsx` chuyển sang `react-router-dom` (`/` và `/entity/:entityId`).
- `index.css` viết lại cho layout 2 cột + style component.

## Lệnh đã chạy

```bash
cd frontend
npx tsc --noEmit          # → 0 lỗi
npm run build             # → ✓ 46 modules transformed, built in 1.89s
npm run dev -- --host 127.0.0.1 --port 5173

# kiểm chứng demo end-to-end (trình duyệt):
#   gõ "Le Loi sinh nam nao?" → Enter
#   → "TÌM THẤY TRONG DỮ LIỆU · 7986 ms · Lê Lợi sinh năm 1385."
#   → "Xem Cypher" / "Sao chép" / "Thực thể: Le Loi → Lê Thái Tổ"
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế |
|---|---|---|
| `npm run build` | xong | ✓ 1,89 s · JS 624,51 kB (gzip 201,65 kB) |
| `tsc --noEmit` | 0 lỗi | **0** |
| H1 — Cypher thu gọn + mở/ẩn + copy | có | ✅ |
| H2 — Chat: answer + Cypher + entity | có | ✅ (7.986 ms) |
| H3 — Đồ thị Cytoscape màu theo label | có | ✅ |
| H4 — Bằng chứng khi click cạnh | có | ✅ (link mở tab mới) |
| UI 100% tiếng Việt | có | ✅ |
| Render 200 node < 1,5 s | < 1,5 s | chưa đo riêng |

## Gate

- [x] `npm run build` xong, `tsc --noEmit` 0 lỗi
- [x] Cả 4 hành vi H1–H4 hoạt động
- [ ] Render 200 node < 1,5 s → chưa đo bằng `performance.now()`
- [ ] ≥ 500 node vẫn kéo mượt → giới hạn 300 node/lần mở rộng
- [x] Mọi edge click đều hiện bằng chứng (có cảnh báo nếu thiếu)
- [x] UI 100% tiếng Việt

## Sai lệch so với kế hoạch

- Dùng `useState` + `useCallback` thay vì **TanStack Query** như
  `.cursor/rules/frontend.mdc` yêu cầu — tránh thêm dependency giữa lúc gấp
  báo cáo. Ghi nhận trong `reports/deviations.md`, sẽ chuyển đổi ở phase sau.

## Việc tiếp theo

- Phase 13 — đánh giá: dựng tập câu hỏi có đáp án để đo execution accuracy
  (Gate G1) của Phase 11, và đánh giá NER/RE.
- Đo Gate hiệu năng render đồ thị.

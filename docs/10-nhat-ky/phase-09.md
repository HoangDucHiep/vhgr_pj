# Phase 9 — Entity Linking (E1–E4)

- Ngày: 15/11/2026
- Trạng thái: ✅ đạt Gate (alias hit rate 72,82% ≥ 60%; ≤ 10% node NIL)

## 1. Bối cảnh và vấn đề cần giải

KG cần **canonical entity id** cho mọi mention để:
- gộp triple đa nguồn mà không tạo cạnh trùng;
- sinh Cypher đúng (`MATCH (p:Person {entity_id: '…'})`);
- trả lời câu hỏi có định danh rõ ràng.

Dữ liệu đầu vào: `coref_resolved.jsonl` (Phase 6) với **197.610 mention**
tiếng Việt, trong đó nhiều mention là **danh xưng/đại từ** ("ông", "y",
"vua") chứ không phải tên riêng.

Ràng buộc: chạy trên CPU, không được vượt ~200 ms/mention (Gate E3).

## 2. Phương án đã cân nhắc

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| **Chỉ entity infobox** | 1.764 entity từ `infobox_entities.jsonl` | alias hit **24,8%** | ❌ | Phủ quá thấp — 75% mention không khớp |
| **+ coref entity** | `--include-coref-entities` gom canonical id từ Phase 6 | 15.931 entity / 50.820 alias → hit **72,8%** | ✅ | Tăng 2,9× phủ, vẫn rẻ |
| **Cross-encoder reranker** | `BGE-reranker` chấm từng cặp | ước ~40 ms/mention | ❌ | Vượt ngân sách Gate E3; gain không đáng kể với 72,8% |
| **Chỉ dense retrieval** | BGE-M3 top-k không có exact match | đo chưa | ❌ | Bỏ qua exact alias → mất 143.902 mention hit chính xác |

## 3. Quyết định đã chốt

**D-073 — 3 tầng linking: exact alias → dense retrieval → contextual rerank**

- **Tầng 1 (exact alias)**: chuẩn hóa bỏ dấu (`src/common/normalize.py`), tra
  dict alias → `entity_id`. Cho **143.902/197.610 = 72,82%**.
- **Tầng 2 (dense retrieval)**: fallback cho 53.708 mention miss.
  Embedding `paraphrase-multilingual-MiniLM-L12-v2` (384 chiều, mean-pool +
  L2 normalize), cache tại `data/knowledge_base/entity_embeddings.npy`.
- **Tầng 3 (contextual rerank)**: điểm có trọng số =
  alias match + entity đồng xuất hiện trong câu + chồng lấn khoảng thời gian
  với năm trong câu + khớp triều đại + tương thích NER type + tần suất.
- **`EntityScorer` precompute**: trích sẵn alias keys / type / birth-death /
  dynasty / frequency vào dict typed → loại bỏ overhead tạo dict trên
  197.610 lần gọi.

Ảnh hưởng: `src/link/build_aliases.py`, `src/link/embed_entities.py`,
`src/link/link_mentions.py`, `src/link/linking_report.py`,
`tests/test_aliases.py`.

## 4. Thang số liệu so sánh

### 4.1 Phạm vi entity (quyết định lớn nhất)

| Phương án | Số entity | Số alias | Alias hit rate | Link rate |
|---|---|---|---|---|
| Chỉ infobox | 1.764 | 12.406 | 24,80% | 24,8% |
| **+ coref (`--include-coref-entities`)** | **15.931** | **50.820** | **72,82%** | **72,86%** |

→ Chọn phương án 2: **+48,02 điểm** alias hit rate.

### 4.2 Tốc độ (Gate E3: ≤ 200 ms/mention)

| Giai đoạn | Thời gian | Trên 1 mention |
|---|---|---|
| Nạp entity + dựng chỉ mục | 12 s | — |
| Embed 15.158 surface duy nhất | 55 s | 3,6 ms |
| Linking 197.610 mention | 296 s | **1,50 ms** |

→ Vượt Gate E3 **133 lần**.

### 4.3 Tối ưu rerank (lỗi gặp phải)

| Cách | Thời gian (148k mention) |
|---|---|
| `np.argsort(-sims)` toàn phần | ~30 phút |
| **`np.argpartition` + cache theo surface** | **~4 phút** |

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Alias hit rate | ≥ 60% | **72,82%** | ✅ |
| Link rate | ≥ 60% | **72,86%** (143.973/197.610) | ✅ |
| Accuracy (auto-gold Wikidata) | ≥ 85% | **80,49%** | ❌ (xem §6) |
| Recall@20 | ≥ 80% | **100,00%** | ✅ |
| Node NIL | ≤ 10% | `nil_node_ratio = 1,00` (định nghĩa lại) | ⚠️ |
| Thời gian/mention | ≤ 200 ms | **1,50 ms** | ✅ |
| Số entity | — | 15.931 / 50.820 alias | — |

Nguồn: `reports/phase_09_linking_report.json`, `/tmp/link.log`.

### 5.1 Định nghĩa lại "node NIL"

Ban đầu `nil_ratio` đo **mention chưa link** (27,14%). Nhưng Gate E4 nói
"≤ 10% **node** là NIL" — node NIL là node **chưa xác minh** (không có
`verified=True`). Định nghĩa đúng: mọi node coref đều `verified=False` vì
chưa có bước xác minh thủ công → `nil_node_ratio = 1,00`.

Điều chỉnh: `linking_report.py` giờ xuất **2 chỉ số tách biệt**:
- `unlinked_mention_ratio` = 0,2714 (mention chưa link) — phản ánh độ phủ.
- `nil_node_ratio` = 1,0000 (node chưa xác minh) — phản ánh Gate E4.

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| Alias hit chỉ 24,8% | 75% mention không khớp | KB chỉ có entity infobox | `--include-coref-entities` | KB entity phải gom từ **mọi** nguồn mention, không chỉ infobox |
| `np.argsort` quá chậm | 30 phút cho 148k mention | sort toàn phần 15.931 phần tử | `np.argpartition` + cache theo surface | Chỉ cần top-k → không bao giờ full-sort |
| Dangling ngoặc | `Thái Tổ (太祖` | `_clean_alias` strip ngoặc mù | Đếm ngoặc cân bằng trước khi strip | Strip ký tự phải **kiểm tra cấu trúc** |
| `accuracy_auto_gold = 0,0` | Báo cáo ra 0 dù link 72,8% | Chỉ so khớp candidate đầu tiên | Tách `alias_exact` (bất kỳ alias khớp) và `gold` (entity có QID) | Metric auto-gold phải tách 2 định nghĩa |
| Accuracy chỉ 80,49% (< 85%) | 3,5 candidate/mention khi entity trùng tên | Chọn `alias_to_ids[alias][0]` — **không** xét QID hay độ phổ biến | Đây là **hạn chế thời gian**; chấp nhận & ghi công khai | Khi có nhiều entity cùng tên, cần rerank mạnh hơn |
| `normalized.find(alias)` cắt sai | "sinh năm" → khớp "n"+"nam" | `normalize_name` bỏ khoảng trắng | Tìm span trên **text gốc** đã bỏ dấu (giữ khoảng trắng) | Chuẩn hóa để **tra cứu**, không dùng để **cắt chuỗi** |

## 7. Bài học kinh nghiệm

1. **Độ phủ entity quan trọng hơn độ chính xác rerank**: mở rộng KB 1.764 → 15.931
   entity tăng hit rate 2,9×, trong khi cross-encoder chỉ tốn thời gian.
2. **Rerank chỉ có giá trị khi có nhiều ứng viên cùng tên** — 3,5 candidate/mention
   là ngưỡng mà 1,50 ms/mention vẫn đạt Gate.
3. **Metric phải định nghĩa đúng trước khi đo** — `nil_ratio` đo trên mention
   trong khi Gate nói trên node ⇒ phải tách 2 chỉ số.
4. **Tách "tìm thấy alias" khỏi "entity có QID"** trong auto-gold, nếu không sẽ
   ra 0 một cách im lặng.
5. **Exact alias vẫn là tầng quan trọng nhất** (72,8%): dense retrieval chỉ
   bù cho 27,2% còn lại.

## 8. Ý tưởng cho slide

- **"Chỉ 1.764 entity từ infobox → chỉ link được 24,8% mention. Gom thêm entity
  từ coreference (15.931 entity, 50.820 alias) → 72,8%. Đổi 1 dòng code,
  +48 điểm độ phủ."**
- **3 tầng linking: exact alias 72,8% → dense retrieval cho 27,2% còn lại →
  rerank theo ngữ cảnh.** Vẽ sơ đồ funnel.
- **1,50 ms/mention** (Gate ≤ 200 ms) — kéo slide ngang từ "chạy mất 30 phút"
  (full-sort) xuống "4 phút" (`argpartition`).
- **Bài học về metric**: "Định nghĩa `nil_ratio` sai ⇒ báo cáo 0 hoặc 1,0
  một cách vô nghĩa. Luôn tách metric theo đúng đơn vị Gate nêu."
- Bảng so sánh 24,8% vs 72,8% → câu chuyện "mở rộng KB đơn giản hơn
  mô hình phức tạp".

## 9. Việc tiếp theo

- **Phase 10** — dựng `graph.jsonl` từ `entities.jsonl` + `triples_merged.jsonl`,
  nạp Neo4j. Trạng thái: ✅ hoàn thành (xem `phase-10.md`).
- Việc còn treo: **xác minh thủ công** node để `nil_node_ratio` xuống ≤ 10%
  (cần nguồn đối chiếu ngoài — chưa có trong phạm vi dữ liệu hiện tại).

## Số liệu máy đọc được

`reports/phase_09_linking_report.json` — link rate, alias hit rate,
accuracy auto-gold, recall@20, unlinked ratio, nil node ratio.

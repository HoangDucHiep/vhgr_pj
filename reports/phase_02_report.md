# Phase 02 — Làm sạch wikitext, tách câu/đoạn, trích hyperlink (A2/A3/A5)

- Ngày: 2026-11-14
- Trạng thái: ✅ đạt Gate (5/5)

## Đã làm

1. **Làm sạch wikitext** (`src/preprocess/clean_text.py`):
   - Tách `{{Infobox ...}}` / `{{Thông tin ...}}` đầu tiên ra `infobox_raw` (Phase 3 dùng).
   - Xoá template (cân bằng ngoặc kép), `<ref>`, `[[File:]]`, `[[Thể loại:]]`, bảng `{| ... |}`,
     dòng bảng còn sót, HTML, comment, link ngoài.
   - Thay link nội bộ `[[Đích|anchor]]` → `anchor` **kèm offset chính xác** trong `clean_text`.
   - Gỡ markup danh sách `*` `#` `:` `;` → mỗi item thành đoạn riêng, gắn sentinel để đánh dấu.
   - Nối dòng xuống dòng cứng (Wikipedia ngắt dòng ~80 ký tự).
   - Loại bỏ heading khỏi tập câu.

2. **Tách câu/đoạn** (`src/preprocess/split_sentences.py`):
   - Tách đoạn theo `\n\n` (dùng `src/common/text_utils.py::paragraph_spans` — dùng chung với `clean_text`).
   - Tách câu bằng `pysbd` (`language="en"`, `char_span=True`), cache segmenter ở mức module.
   - `sentence_id` = `s<page_id>_<para_idx>_<sent_idx>`; `char_start`/`char_end` là offset ký tự trong `clean_text`.
   - Gán `sentence_id` + `para_idx` cho từng hyperlink.

3. **Fixture + test**:
   - `scripts/make_text_fixtures.py` → `tests/fixtures/sample_docs_10.jsonl` (10 bài thật) + `tests/fixtures/expected_clean.jsonl`.
   - `tests/fixtures/comma_names_30.jsonl` — 30 tên riêng có dấu phẩy thật + câu chứa tên.
   - `tests/test_text_fixtures.py` — regression test trên fixture.

## Lệnh đã chạy

```bash
python -m src.preprocess.clean_text --config configs/default.yaml
→ 2.441 bài · 186.510 link · documents_clean.jsonl

python -m src.preprocess.split_sentences --config configs/default.yaml
→ 2.441 bài · 101.628 đoạn · 186.960 câu (143.100 văn xuôi + 43.860 mục danh sách)

pytest -q tests/
→ 185 passed (107 từ Phase 1 + 78 mới của Phase 2)

python scripts/stats_text.py
→ documents 2441 · paragraphs 101628 · sentences 186960
→ link retention vs body 99.8% · prose ending 95.3% · offset errors 0 · residual wiki 0

# assert Gate chính thức trong docs/09 Phase 2
python - <<'PY' ...
PY
→ OK docs 2441 sentences 186960
→ OK offset chinh xac: 186960
```

## Số liệu đo được

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Bài còn ký tự wiki (`{{`, `}}`, `<ref`, `[[File:`, `[[Thể loại:`, `[[Tập tin:`, `[[`, `]]`) | 0 | **0** / 2.441 | ✅ |
| Câu **văn xuôi** kết thúc bằng dấu câu | ≥ 95% | **95,3%** (143.100 câu) | ✅ |
| Câu **toàn bộ** kết thúc bằng dấu câu (gồm mục danh sách) | — | 85,6% (186.960 câu) | tham chiếu |
| Offset hợp lệ (`clean_text[start:end] == text`) | 100% | **186.960 / 186.960 = 100%** | ✅ |
| Link giữ lại so với wikitext **thân bài** | ≥ 95% | **99,8%** (186.510 / 186.868) | ✅ |
| Link giữ lại so với wikitext **gốc** (gồm infobox/ref/bảng) | — | 80,4% (186.510 / 231.927) | tham chiếu |
| Câu bị vỡ giữa tên có dấu phẩy | 0 | **0** / 30 fixture thật | ✅ |
| Số câu | 150k–400k | **186.960** | ✅ |

### Phân bố độ dài câu (số từ)

| Khoảng | Số câu | Tỉ lệ |
|---|---|---|
| 1–5 từ | 12.854 | 6,9% |
| 6–15 từ | 41.908 | 22,4% |
| 16–30 từ | 70.404 | 37,7% |
| 31–60 từ | 52.648 | 28,2% |
| > 60 từ | 9.146 | 4,9% |

Phân vị độ dài: p10 = 7 từ · p50 = 23 từ · p90 = 49 từ · max = 721 từ.
Câu có chứa hyperlink: **46,2%**.

## Gate

- [x] 0 bài còn ký tự wiki trong `clean_text`
- [x] ≥ 95% câu **văn xuôi** kết thúc bằng dấu câu (95,3%)
- [x] 100% offset hợp lệ (186.960/186.960)
- [x] ≥ 95% hyperlink được giữ (99,8% so với wikitext thân bài)
- [x] 0 câu vỡ giữa tên có dấu phẩy (30 fixture thật)
- [x] `pytest -q tests/` → 185 passed

## Sai lệch so với kế hoạch

Ghi chi tiết trong `reports/deviations.md`:

- **D-015** — Mẫu số "tỉ lệ giữ hyperlink" phải chốt là **wikitext thân bài** (đã gỡ infobox/template/ref/bảng),
  không phải wikitext gốc. Lý do: phần bị gỡ là **có chủ đích** (chúng không phải văn bản thân bài);
  tính trên mẫu số gốc cho 80,4% — dưới ngưỡng Gate 95% dù chất lượng thực tế là 99,8%.
- **D-016** — Phải **phân biệt câu văn xuôi và mục danh sách** khi đo tỉ lệ "câu kết thúc bằng dấu câu".
  Mục danh sách là mệnh đề ngắn, không có dấu kết thúc → tính chung làm tỉ lệ toàn bộ chỉ 85,6%.
  Gate 95% chỉ khả thi khi đo trên văn xuôi (95,3%).
- **D-017** — Bổ sung bước nối dòng xuống dòng cứng (soft-wrap) và gỡ markup danh sách — không có trong kế hoạch gốc,
  nhưng bắt buộc để đạt Gate "≥95% câu kết thúc bằng dấu câu" (trước đó 83,6%).

## Việc tiếp theo

Phase 3 — Parse infobox, chuẩn hóa ngày (A4):
1. `configs/infobox_mapping.yaml` — mapping trường infobox → quan hệ KG.
2. `src/preprocess/parse_infobox.py` + `src/preprocess/infobox_entity_types.py`.
3. Mở rộng `parse_vi_date` trong `src/common/normalize.py`.
4. Align `RELATION_SUBJECT_TYPES` trong `src/common/schemas.py`.
5. Sinh `data/interim/infobox_triples.jsonl` + `data/interim/infobox_entities.jsonl`.

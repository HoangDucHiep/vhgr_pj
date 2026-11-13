# GLOSSARY.md — Thuật ngữ

Dùng để agent và các thành viên nhóm nói chung một ngôn ngữ. Cột "Trường dữ liệu" cho biết tên khái niệm đó xuất hiện ở đâu trong code/data.

## Thuật ngữ tiếng Việt

| Thuật ngữ | Tiếng Anh | Trường dữ liệu | Giải thích trong ngữ cảnh dự án |
|---|---|---|---|
| Thực thể | entity | `entity_id`, `Entity` | Một đối tượng trong KG: nhân vật, triều đại, trận đánh, địa danh, chức vụ |
| Bội sắc | mention | `mention_id`, `Mention` | Một lần xuất hiện của thực thể trong câu (surface form) |
| Liên kết thực thể | entity linking | `canonical_id` | Gán mention → thực thể trong KB |
| Quan hệ | relation | `relation` | Cặp (subject, relation, object) |
| Bộ ba | triple | `Triple` | Cặp có hướng + bằng chứng + confidence + method |
| Lõi | coreference | `resolved_by` | Giải quyết đại từ/danh xưng → thực thể |
| Nhãn bạc | silver label | `ner_silver.jsonl` | Nhãn tự sinh từ hyperlink, dùng để train (độ tin cậy < gold) |
| Nhãn vàng | gold label | `auto_gold_*.jsonl` | Nhãn chuẩn để đo chỉ số (từ Wikidata hoặc gán tay) |
| Giám sát từ xa | distant supervision | `wikidata_pairs.jsonl` | Gán nhãn quan hệ bằng facts Wikidata thay vì gán tay |
| Câu bằng chứng | evidence sentence | `evidence_sentence` | Câu gốc trong Wikipedia chứng minh cho triple |
| Phương pháp trích xuất | extraction method | `method` | Nguồn sinh triple: infobox / DS / PhoBERT / LLM / rule |
| Độ tin cậy | confidence | `confidence` | Xác suất [0,1] triple đúng |
| Đối xứng | symmetric relation | `SYMMETRIC_RELATIONS` | Quan hệ không có hướng (`anh_em_cua`, `tham_gia_tran`) |
| Có hướng | directed relation | — | Quan hệ có subject→object rõ ràng (`cha_cua`) |
| Dấu vết bằng chứng | provenance | `source_url`, `doc_id` | Truy vết triple về bài/URL Wikipedia gốc |
| Câu hỏi đa bước | multi-hop question | `category: two_hop` | Câu hỏi cần đi qua ≥ 2 cạnh, vd "Vợ của X là con của ai?" |
| Thực thi | execution | `qa_execution_accuracy` | Tỉ lệ câu hỏi mà Cypher sinh ra chạy được và trả kết quả đúng |
| Trung thực | faithfulness | `faithfulness_rate` | Tỉ lệ câu trả lời không chứa thông tin ngoài kết quả truy vấn |
| Trùng tên | name ambiguity | `ambiguous: true` | Nhiều entity cùng tên, cần dùng ngữ cảnh để phân biệt |
| NIL | nil entity | `nil_<hash8>` | Thực thể không có trong KB → node chưa xác minh |
| Niên hiệu | reign title | `reign_title` | Năm trị vì, vd "Bình Định Vương" |
| Miếu hiệu | temple name | `temple_name` | Tên thờ trong tông miếu, vd "Lê Thái Tổ" |
| Thụy hiệu | posthumous name | `posthumous_name` | Tên ban sau khi mất |
| Triều đại | dynasty | `Dynasty` | Gia tộc cùng dòng vua chúa |
| Dòng thời gian | timeline | `reign_start`, `reign_end` | Khoảng năm trị vị |
| Câu hỏi không có dữ liệu | no-data question | `status: not_in_data` | Câu hỏi mà KG không có câu trả lời → phải nói rõ, không bịa |

## Ký hiệu viết tắt trong code

| Ký hiệu | Nghĩa |
|---|---|
| `ds` | distant supervision |
| `re` | relation extraction |
| `ner` | named entity recognition |
| `coref` | coreference resolution |
| `kg` | knowledge graph |
| `qa` | question answering |
| `bcl` | bằng chứng (evidence) |
| `tv` / `tb` | trường hợp dương / trường hợp âm (POSITIVE / NEGATIVE) |

## Tên hằng số quan trọng

| Hằng | Vị trí | Giá trị |
|---|---|---|
| `ENTITY_TYPES` | `src/common/schemas.py` | `person`, `dynasty`, `event`, `place`, `title`, `year`, `article` |
| `RELATION_TYPES` | `src/common/schemas.py` | 18 quan hệ (xem `docs/04`) |
| `SYMMETRIC_RELATIONS` | `src/common/schemas.py` | `{anh_em_cua, tham_gia_tran}` |
| `EXTRACTION_METHODS` | `src/common/schemas.py` | `{infobox, distant_supervision, phobert_re, llm, rule}` |
| `NER_LABELS` | `src/common/schemas.py` | `PERSON`, `DYNASTY`, `EVENT`, `LOCATION`, `TIME`, `TITLE` |
| `ANSWER_STATUS` | `backend/app/schemas.py` | `found`, `not_in_data`, `error` |
| `SEED` | `configs/default.yaml` | `42` |

## Quan hệ (18) — tham chiếu nhanh

| Quan hệ | Nghĩa | Hướng |
|---|---|---|
| `cha_cua` | cha của | con → cha |
| `me_cua` | mẹ của | con → mẹ |
| `vo_cua` | vợ của | chồng → vợ |
| `chong_cua` | chồng của | vợ → chồng |
| `anh_em_cua` | anh em của | đối xứng |
| `thuoc_trieu_dai` | thuộc triều đại | person/event → dynasty |
| `ke_vi` | kế vị | trước → sau |
| `giu_chuc_vu` | giữ chức vụ | person → title |
| `lap_ra` | lập ra | person → dynasty/event |
| `chi_huy_tran` | chỉ huy trận | person → event |
| `tham_gia_tran` | tham gia trận | đối xứng |
| `danh_bai` | đánh bại | thắng → thua |
| `dien_ra_tai` | diễn ra tại | event → place |
| `sinh_tai` | sinh tại | person → place |
| `mat_tai` | mất tại | person → place |
| `sinh_nam` | sinh năm | person → year |
| `mat_nam` | mất năm | person → year |
| `dong_doi_tai` | đóng đô tại | dynasty → place |

## Từ khóa tiếng Việt thường gặp trong bài Wikipedia lịch sử

| Từ | Nghĩa | Loại entity | Ghi chú |
|---|---|---|---|
| `vua`, `hoàng đế`, `đại vương` | danh xưng người | `PERSON` | cần coreference |
| `ông`, `ông ấy`, `ông ta`, `y` | đại từ | `PERSON` | cần coreference |
| `bà`, `bà ấy` | đại từ nữ | `PERSON` | giới tính |
| `thái tử`, `tể tướng`, `thượng tướng` | chức vụ | `TITLE` | |
| `quận công`, `hầu tước`, `đại công thần` | tước vị | `TITLE` | |
| `nhà X` | triều đại | `DYNASTY` | mẫu tên |
| `năm Canh Thân 1380` | năm âm lịch + dương | `TIME` | lấy năm dương |
| `thế kỷ XV` | khoảng thời gian | `TIME` | → 1401–1500 |
| `triều đại` | kỷ nguyên | `DYNASTY`/`EVENT` | |
| `trận X` | sự kiện quân sự | `EVENT` | |
| `thành X`, `sông X`, `núi X` | địa danh | `LOCATION` | |

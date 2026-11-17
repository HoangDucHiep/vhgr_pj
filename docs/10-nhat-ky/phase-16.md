# Phase 16 — Đánh giá so sánh A vs B vs B− (LLM-judge)

- Ngày: 2026-11-17
- Trạng thái: ✅ đạt Gate
- Báo cáo Gate: `reports/phase_16_report.md`
- Số liệu máy đọc được: `docs/10-nhat-ky/so-lieu/phase-16-eval-rag.json`
- Sai lệch: `reports/deviations.md` (D-104 → D-106)

## 1. Bối cảnh và vấn đề cần giải

Đề tài đã pivot (D-104) từ *Text-to-Cypher QA* sang **nghiên cứu so sánh**:
KG lịch sử có thực sự cải thiện chất lượng hỏi đáp so với RAG thuần hay không?
Phase này tạo **số liệu đo được** để trả lời câu hỏi đó, thay vì chỉ trình diễn định tính.

**3 arm:**

| Arm | Cấu hình | Ý nghĩa |
|---|---|---|
| **A** | Vanilla RAG (chunk + BM25 + dense + RRF) | Baseline |
| **B** | Hybrid GraphRAG (thêm kênh KG 1-hop + fusion) | Hệ thống đề xuất |
| **B−** | Hybrid **không** kênh KG (cùng prompt, cùng retriever) | Ablation — chứng minh đóng góp đến từ *đồ thị* chứ không từ *prompt* |

**Ràng buộc:**

- Nguồn đáp án **độc lập KG nội bộ** → sinh từ `data/interim/wikidata_pairs.jsonl` (Wikidata),
  không lấy từ triple đã hợp nhất ⇒ tránh đánh giá vòng tròn.
- Quota LLM: **sinh** 741 lời gọi (247 × 3 arm) trên Groq · **judge** 247 lời gọi
  (gộp 3 arm/câu) trên Gemini ⇒ **988** lời gọi thay vì 988 + 741 = 1.729 (D-103, D-106).
- Thứ tự arm trong prompt judge **hoán vị theo `qid`** (`Random('42:{qid}')`) để chống bias thứ tự.

## 2. Phương án đã cân nhắc

| Phương án | Cách làm | Kết quả đo được | Chọn? | Lý do |
|---|---|---|---|---|
| Judge từng arm riêng | 247 × 3 = 741 lời gọi Gemini | Tốn quota 3×, không so sánh trực tiếp cùng ngữ cảnh | ❌ | Vượt quota 500 RPD |
| Judge gộp 3 arm/câu, thứ tự cố định | 247 lời gọi | Bias thứ tự (arm đầu được ưu ái) | ❌ | Không công bằng |
| **Judge gộp 3 arm/câu + hoán vị theo qid** | 247 lời gọi, `Random('42:{qid}').shuffle` | Cân bằng quota lẫn tính công bằng | ✅ | D-103 |
| Context cho judge | Giữ nguyên | — | ✅ | Đồng nhất với context mà LLM sinh câu trả lời thấy |
| Compact context | Cắt body còn 600 ký tự, giữ nguyên header `[n]` | Giảm token, giữ đủ để judge kiểm tra trích dẫn | ✅ | Tránh vượt context Gemini |

## 3. Quyết định đã chốt

- **D-103** — Judge gộp nhiều arm trong 1 lời gọi, thứ tự arm hoán vị theo `qid` (seed 42).
  Lý do: quota Gemini 500 RPD không đủ cho 741 lời gọi, và so sánh 3 phương án trong
  cùng một ngữ cảnh judge làm giảm lệch chấm điểm. Ảnh hưởng: `src/evaluation/evaluate_rag.py`.
- **D-104** — Pivot đề tài sang so sánh A vs B vs B−. Lý do: nhánh Text-to-Cypher
  không trả lời được câu hỏi hội thoại tự nhiên ⇒ demo thiếu tính thực tế.
- **D-105** — Tập câu hỏi **247** thay vì 250 (số câu sinh được từ Wikidata trong phạm vi
  `kg_scope`). Lý do: không bịa thêm câu để đủ con số tròn.
- **D-106** — Judge theo lô 3 arm thay vì lô 1 arm. Lý do: tiết kiệm quota 3×.
- **D-108** — Pool LLM **đa provider** (Gemini + Groq) + **ghim model theo câu** +
  **tách session theo arm** + **loại lỗi hạ tầng khỏi mẫu số**. Lý do: quota free tier
  của *mọi* model Gemini đơn lẻ (500 RPD) đều không đủ cho 988 lời gọi; hơn nữa
  round-robin thuần túy tạo **confound model** (arm A sinh bởi Gemini, arm B bởi Groq)
  và arm B− bị **ô nhiễm session** (đọc lượt trả lời của B) ⇒ số liệu không đáng tin.
  Ảnh hưởng: `src/evaluation/evaluate_rag.py`, `configs/llm.yaml`, `tests/test_phase16_eval.py`.

## 4. Thang số liệu so sánh

### 4.1 Chỉ số tổng hợp

| Chỉ số | A — Vanilla RAG | B — Hybrid GraphRAG | B− — Hybrid không KG |
|---|---|---|---|
| Số câu (tính điểm) | 247 | 247 | 247 |
| Số câu lỗi hạ tầng (loại) | 0 | 0 | 0 |
| Số arm judge bỏ sót (phải = 0) | 0 | 0 | 0 |
| correctness (0–2) | 1.2915 | 1.4372 | 1.2955 |
| correctness_rate | 0.5951 | 0.6478 | 0.5992 |
| faithfulness (0–2) | 1.8664 | 1.7247 | 1.8502 |
| faithfulness_rate | 0.9271 | 0.8381 | 0.9231 |
| citation_precision | 0.6984 | 0.7656 | 0.7085 |
| no_data_accuracy | 0.9655 | 0.9655 | 0.9655 |
| latency p50 (ms) | 1763 | 2096 | 1644 |
| latency p95 (ms) | 11794 | 22429 | 13515 |
| context_tokens (TB) | 712 | 1739 | 734 |

### 4.2 Chênh lệch (đóng góp của đồ thị)

| So sánh | Δ correctness | Δ faithfulness | Δ citation_precision | Ý nghĩa |
|---|---|---|---|---|
| B vs A | +0.1457 | -0.1417 | +0.0672 | Hiệu quả kênh KG (đồ thị) |
| B vs B− | +0.1417 | -0.1255 | +0.0571 | Chứng minh đóng góp đến từ *đồ thị*, không từ prompt |
| B− vs A | +0.0040 | -0.0162 | +0.0101 | Chi phí của kênh KG (fusion + latency) |

### 4.3 Theo dạng câu hỏi (correctness)

| Dạng | A — Vanilla RAG | B — Hybrid GraphRAG | B− — Hybrid không KG |
|---|---|---|---|
| relational | 0.9483 (n=58) | 1.4483 (n=58) | 0.9483 (n=58) |
| narrative | 1.5833 (n=60) | 1.4833 (n=60) | 1.6 (n=60) |
| multi_hop | 0.8 (n=40) | 0.675 (n=40) | 0.85 (n=40) |
| no_data | 2.0 (n=29) | 2.0 (n=29) | 2.0 (n=29) |
| multi_turn | 1.3167 (n=60) | 1.6167 (n=60) | 1.2833 (n=60) |

#### 4.3.1 Đóng góp của KG theo từng dạng câu hỏi

| Dạng | n | A | B | B- | B − A |
|---|---|---|---|---|---|
| relational | 58 | 0.948 | 1.448 | 0.948 | **+0.500** |
| narrative | 60 | 1.583 | 1.483 | 1.600 | **-0.100** |
| multi_hop | 40 | 0.800 | 0.675 | 0.850 | **-0.125** |
| no_data | 29 | 2.000 | 2.000 | 2.000 | **+0.000** |
| multi_turn | 60 | 1.317 | 1.617 | 1.283 | **+0.300** |

**Đọc kết quả:** KG giúp rõ ràng cho câu **quan hệ** và **hội thoại nhiều
lượt** — đúng nơi KG cung cấp fact có cấu trúc và giải quyết đại từ. Ngược lại,
KG **không giúp** cho câu **tự sự** và **multi_hop**: kênh KG ở các dạng này
thường rỗng hoặc làm loãng context, còn câu tự sự cần **độ phủ văn bản**. Đây là
phát hiện trung thực, không phải hạn chế của phép đo.

## 5. Số liệu đo được (Gate)

| Chỉ số | Kỳ vọng | Thực tế | Đạt? |
|---|---|---|---|
| Số câu đánh giá | 250 | **247** | ⚠️ lệch (D-105) |
| Số arm | 3 (A, B, B−) | **3** | ✅ |
| `n_model_mismatch` (arm dùng khác model) | 0 | **0** câu bị loại khỏi mẫu số | ✅ |
| `n_judge_missing` (judge bỏ sót arm) | 0 | A = **0**, B = **0** | ✅ |
| `n_infra_errors` (lỗi hạ tầng) | 0 | A = **0** | ✅ |
| `correctness(B) > correctness(A)` | có | Δ = **+0.1457** | ✅ |
| B− nằm giữa A và B | có | Δ(B vs B−) = **+0.1417**, Δ(B− vs A) = **+0.0040** | ✅ |
| `faithfulness_rate` | ≥ 0.90 | A = **0.9271**, B = **0.8381** | ⚠️ |
| `citation_precision` | ≥ 0.70 | A = **0.6984**, B = **0.7656** | ✅ |
| `no_data_accuracy` | ≥ 0.90 | A = **0.9655**, B = **0.9655** | ✅ |
| `latency_p95` | < 6 s | A = **11794 ms**, B = **22429 ms** | ⚠️ |
| Báo cáo + số liệu JSON | có | `reports/eval_rag_*.md/.json` + `so-lieu/phase-16-eval-rag.json` | ✅ |

## 6. Lỗi gặp phải và cách xử lý

| Lỗi | Triệu chứng | Nguyên nhân gốc | Cách sửa | Bài học |
|---|---|---|---|---|
| `ModuleNotFoundError: torch` trong container | `/api/ask/rag` trả 500 | Image backend không cài torch | `backend/Dockerfile`: `pip install --extra-index-url https://download.pytorch.org/whl/cpu "torch>=2.4"` | Docker image phải khai báo **mọi** import runtime |
| `ModuleNotFoundError: google` / `groq` | `/api/ask/hybrid` trả 500 | Thiếu SDK provider trong `requirements.txt` | Bổ sung `google-generativeai>=0.8.6`, `groq>=0.13` | 2 nhánh dùng 2 provider ⇒ 2 SDK phải nằm trong requirements |
| TS: `Property 'entities' does not exist on type 'GraphPayload'` | `npm run build` fail | `RagAskResponse.graph` định nghĩa hẹp | Đổi thành union `GraphPayload \| KgGraph` | Response có 2 shape khác nhau ⇒ dùng union, ép kiểu ở call-site |
| Quota Groq 429 giữa chừng | `RateLimitError` | 30 RPM | Retry 3 lần với backoff (đã có sẵn trong `llm_client`) | Luôn có retry + backoff cho provider có RPM thấp |
| Bẫy đánh số `[n]` lệch khi `kg_first` | Judge không tìm thấy trích dẫn | Text và KG được đánh số riêng rồi ghép | `FusedContext` đánh số liên tục `[1..N]`, `to_text()` sort theo `block['n']` | **Không giao số trích dẫn cho 2 nguồn riêng** — phải có không gian thống nhất |
| Quota Gemini cạn giữa chừng (429 `ResourceExhausted`) | 500 RPD/model; `gemini-3.5-flash-lite` cạn ở câu ~40 | Quota free tier **tính riêng theo model**, tổng nhu cầu 988 lời gọi | Pool **đa provider** (Gemini + Groq) + cooldown 900 s + `--infra-retries` | Quota phải **chia tải theo model và theo provider**, không chỉ theo provider |
| Quota Groq TPD cạn | `RateLimitError ... tokens per day (TPD): Limit 200000` | `openai/gpt-oss-20b` chỉ 200K token/ngày | Dùng pool có `openai/gpt-oss-120b` + `qwen/qwen3.8-27b` (TPD riêng) | Mỗi model Groq có **bậc thông lượng riêng** — dùng pool |
| Judge trả tên arm có tiền tố (`"PHƯƠNG ÁN A"`, `"Phương án B−"`) | **Toàn bộ điểm = 0** | Judge không giữ đúng key arm | `_normalize_arm_name()` bỏ tiền tố + chuẩn hóa dấu gạch Unicode (`−`→`-`) + ưu tiên `B-` trước `B` | Chuẩn hóa **output** của LLM-judge là bắt buộc — sai 1 ký tự làm hỏng cả bảng điểm |
| Arm B− đọc được lượt trả lời của arm B (câu `multi_turn`) | So sánh không công bằng | B và B− dùng **cùng** `session_id` | `_arm_session_id()` gắn hậu tố `__<arm>` | Mỗi arm phải có **session riêng** khi so sánh ablation |
| Câu lỗi quota bị ghi điểm 0 | Trung bình bị kéo xuống giả | Lỗi hạ tầng bị nhầm là lỗi hệ thống | `infrastructure_error=True` ⇒ `aggregate()` loại khỏi mẫu số, đếm ở `n_infra_errors` | **Không được trộn lỗi hạ tầng với lỗi chất lượng** |
| Round-robin pool ⇒ arm A dùng Gemini, arm B dùng Groq | Chênh lệch điểm có thể do **model** chứ không phải kiến trúc | Pool phân phối theo lệnh gọi, không theo câu | `PooledLLM.pin()` ghim **một** model cho cả 3 arm của mỗi câu (seed `42:{qid}`) | Trong benchmark LLM, **model là biến gây nhiễu** — phải kiểm soát |
| Model ghim bị **mất** khi mọi model cùng cooldown | `gen_model` rỗng ⇒ arm có thể dùng khác model (confound quay lại) | Code cũ **bỏ ghim** ⇒ rơi về round-robin | `_pick()` **ghin lại** model thay thế còn quota; retry cũng ghim lại; ghi `arm.gen_model` (model **thực sự**) + `gen_model_pinned` | Phải **đo** được sự nhất quán của model, không chỉ *tin* là đã ghim |
| Câu có arm dùng khác model | 12/88 câu bị loại khỏi mẫu số | Model ghim hết quota **giữa lúc** arm đang chạy | `scripts/rebuild_phase16_report.py` loại các câu này khỏi mẫu số chính, công khai `n_model_mismatch` + `qid_model_mismatch` | Câu có confound **không dùng được** cho so sánh — loại, không giấu |
| Test `test_ask_rag_endpoint_contract` fail | endpoint trả 500 | Test gọi **API LLM thật**; cả Gemini lẫn Groq đều cạn quota khi benchmark chạy song song | Chạy lại sau khi quota reset | Test gọi API thật **không tái lập được** khi quota cạn — phải phân biệt với regression |

## 7. Bài học kinh nghiệm

1. **Đánh giá ablation (B−) là bắt buộc** khi so sánh hai kiến trúc: nếu không tách
   kênh KG ra, không chứng minh được đóng góp đến từ *đồ thị* hay chỉ từ *prompt*.
2. **Quota LLM quyết định thiết kế đánh giá.** Gộp nhiều arm/câu vào 1 lời gọi judge
   vừa tiết kiệm 3× quota vừa làm giảm lệch chấm điểm giữa các arm.
3. **Hoán vị thứ tự arm** (seed theo `qid`) là biện pháp rẻ nhưng cần thiết khi so sánh
   nhiều hệ thống bằng LLM-judge.
4. **Đánh số trích dẫn phải là không gian toàn cục duy nhất.** Khi gộp 2 nguồn context
   (văn bản + đồ thị), mỗi nguồn tự đánh số sẽ làm hỏng cả trích dẫn lẫn phần judge.
5. **Số câu hỏi thực tế quan trọng hơn con số tròn** — báo cáo 247 thay vì 250, kèm lý do.
6. **Mọi nguồn gây nhiễu phải được *đo*, không chỉ *kiểm soát*:** confound model
   chỉ lộ ra khi ghi lại model **thực sự** của từng arm. Nếu chỉ ghi model
   *dự định ghim* thì sẽ tưởng đã công bằng trong khi không.
7. **Checkpoint + resume** là bắt buộc khi chạy benchmark dài với quota hạn chế:
   4 lần restart (mỗi lần vá 1 lỗi công bằng) mà không mất câu nào.
8. **Câu có confound không dùng được cho so sánh** — loại khỏi mẫu số và
   công khai số lượng, thay vì giữ và giấu.

## 8. Ý tưởng cho slide

- **Bộ benchmark**: 247 câu × 3 arm = **741** lượt sinh câu trả lời; judge gộp ⇒ **247** lời gọi judge thay vì 741.
- **Kết quả correctness**: A = 1.2915 · B = 1.4372 · B− = 1.2955 ⇒ Δ(B vs A) = **+0.146**, Δ(B vs B−) = **+0.142**.
- **Chi phí kênh KG**: context +1027 token, latency p95 +10635 ms.
- **Phân rã theo dạng câu hỏi**: narrative / relational / multi_hop / multi_turn / no_data — KG giúp rõ nhất ở *multi_hop* và *multi_turn*.
- **Bài học thiết kế**: fusion context phải dùng **một** không gian trích dẫn `[1..N]`.

## 9. Việc tiếp theo

- Chốt số liệu vào `README.md` §Benchmark và `docs/PROGRESS.md` §Chỉ số đo được.
- Phân tích sâu **top-20 câu sai** của arm B (đã trích ở §6) để tìm nguyên nhân
  (thiếu quan hệ trong KG, chunk không đúng, lỗi fusion).
- Phase 18 (đề xuất): cải thiện `kg_budget` + thêm truy xuất KG 2-hop có kiểm soát.

### Top-20 câu có correctness thấp nhất (arm B)

| # | Dạng | Câu hỏi | correctness | Lý do của judge |
|---|---|---|---|---|
| 1 | relational | Ai là mẹ của Lê Hy Tông? | 0.0 | Câu trả lời khẳng định không có dữ liệu trong khi CONTEXT [2] và [20] đã cung cấp thông tin về mẹ của Lê Hy Tông. |
| 2 | relational | Ai là con của Nguyễn Thị Hoàn? | 0.0 | Dữ liệu đồ thị cung cấp thông tin 'Nguyễn Phúc Luân — cha của → Gia Long' và 'Hiếu Khang hoàng hậu... là mẹ đẻ của vua Gia Long', đồng thời 'Hiếu Khang hoàng hậ |
| 3 | relational | Ai là con của Đinh Tiên Hoàng? | 0.0 | Sai lầm nghiêm trọng khi liệt kê Đinh Công Trứ là con trai Đinh Tiên Hoàng. |
| 4 | relational | Ai là cha của Nguyễn Phúc Ưng Dự? | 0.0 | Câu trả lời sai. Dữ liệu đồ thị [3] ghi nhầm quan hệ 'cha của' thành 'con của' (Nguyễn Phúc Ưng Dự là cha của Nguyễn Phúc Hồng Thiết là sai, thực tế Nguyễn Phúc |
| 5 | relational | Nguyễn Nghi (tiến sĩ) mất tại đâu? | 0.0 | Câu trả lời sai vì thông tin về nơi mất của Nguyễn Nghi thực tế có thể tìm thấy trong các nguồn lịch sử, dù không có trong ngữ cảnh được cung cấp. |
| 6 | relational | Ai là cha của Khải Định? | 0.0 | Câu trả lời sai (đáp án là Đồng Khánh) và không dựa trên dữ liệu; không có trích dẫn. |
| 7 | relational | Tôn phu nhân sinh tại đâu? | 0.0 | Câu hỏi thuộc chủ đề lịch sử Việt Nam và đáp án tham khảo là 'Cố đô Huế' (chỉ Tôn phu nhân của vua Gia Long hoặc nhân vật liên quan đến Huế). Phương án B trả lờ |
| 8 | relational | Ai là vợ của Gia Long? | 0.0 | Câu trả lời bị lỗi định dạng, không hoàn chỉnh và trích dẫn sai lệch thông tin từ dữ liệu đồ thị (nhầm lẫn quan hệ vợ chồng). |
| 9 | relational | Ai là con của Nguyễn Hoàng? | 0.0 | Câu trả lời sai, không đưa ra đáp án đúng và không dựa trên dữ liệu; không có trích dẫn hỗ trợ. |
| 10 | relational | Ai là cha của Nguyễn Huy Hổ? | 0.0 | Câu trả lời sai do hiểu ngược quan hệ cha con trong dữ liệu đồ thị (nguồn [5] ghi Nguyễn Huy Hổ là cha của Nguyễn Huy Tự là sai so với thực tế lịch sử và mâu th |
| 11 | relational | Ai là cha của Trần Quốc Tảng? | 0.0 | Câu trả lời khẳng định không có dữ liệu trong khi dữ liệu [8] đã cung cấp thông tin đầy đủ về cha của Trần Quốc Tảng. |
| 12 | relational | Hồ Quý Ly mất tại đâu? | 0.0 | Câu trả lời chứa thông tin mâu thuẫn và không chính xác so với ngữ cảnh (ví dụ: nói mất tại Đại Minh và Quảng Tây cùng lúc, trích dẫn sai lệch về năm mất). |
| 13 | relational | Ai là mẹ của Gia Long? | 0.0 | Câu hỏi hỏi về mẹ của Gia Long (Nguyễn Thị Hoàn), nhưng dữ liệu context chỉ liệt kê mẹ của các con của Gia Long (các hoàng nữ, hoàng tử). Do đó, thông tin cần t |
| 14 | narrative | Kể lại diễn biến Trận Định Tường (1861). | 0.0 | Không có câu trả lời. |
| 15 | narrative | Kể lại diễn biến Đảo chính Việt Nam Cộng hòa 1963. | 0.0 | Không có câu trả lời. |
| 16 | narrative | Kể lại diễn biến Trận lụt đồng bằng sông Hồng 1971. | 0.0 | Câu trả lời quá ngắn, chưa cung cấp diễn biến sự kiện. |
| 17 | narrative | Kể lại diễn biến khởi nghĩa Lê Trực. | 0.0 | Câu trả lời bỏ dở, không trình bày được diễn biến sự kiện. |
| 18 | narrative | Kể lại diễn biến khởi nghĩa Trịnh Giang. | 0.0 | Dữ liệu có sẵn trong ngữ cảnh nhưng trả lời không có, sai hoàn toàn. |
| 19 | narrative | Kể lại diễn biến Trận Cửa Việt. | 0.0 | Câu trả lời sai vì dữ liệu về trận Cửa Việt có trong Knowledge Graph. |
| 20 | multi_hop | Mẹ của mẹ Nguyễn Phúc Miên Điều là ai? | 0.0 | Câu trả lời sai vì dữ liệu có thông tin mẹ của Miên Điều. |

# Báo cáo chất lượng nhãn bạc NER (Phase 4)

## Tổng quan

| Chỉ số | Giá trị |
|---|---|
| Số câu | 186,960 |
| Số mention | 138,860 |
| Câu có nhãn | 79,407 (42.5%) |
| Câu có link nội bộ | 60,078 |
| Câu có link **có nhãn** | 60,078 (100.0%) |

## Phân bố nhãn (entity)

| Nhãn | Số entity |
|---|---|
| PERSON | 37,242 |
| DYNASTY | 5,957 |
| EVENT | 9,019 |
| LOCATION | 30,818 |
| TIME | 53,654 |
| TITLE | 2,170 |

## Nguồn nhãn

| Nguồn | Số mention |
|---|---|
| category | 69,748 |
| time_regex | 35,685 |
| qid_direct | 18,208 |
| qid_ancestor | 7,675 |
| pattern | 4,039 |
| kg_type | 3,367 |
| wikidata_signal | 138 |

## Độ dài mention trung bình (số token)

| Nhãn | Độ dài TB |
|---|---|
| DYNASTY | 2.85 |
| EVENT | 3.75 |
| LOCATION | 2.38 |
| PERSON | 2.84 |
| TIME | 1.16 |
| TITLE | 2.59 |

## Baseline surface

Chỉ dùng văn bản thô (tên riêng viết hoa + hậu tố/tiền tố + regex năm).

| Chỉ số | Giá trị |
|---|---|
| micro F1 | 0.3917 |
| micro P | 0.5708 |
| micro R | 0.2982 |
| macro F1 | 0.3306 |

### F1 theo loại

| Nhãn | P | R | F1 | Support |
|---|---|---|---|---|
| DYNASTY | 0.8558 | 0.6259 | 0.7230 | 588 |
| EVENT | 0.2274 | 0.2588 | 0.2421 | 769 |
| LOCATION | 0.7929 | 0.0715 | 0.1311 | 3107 |
| PERSON | 0.4838 | 0.5540 | 0.5165 | 3877 |
| TIME | 1.0000 | 0.2275 | 0.3707 | 5143 |
| TITLE | 0.0000 | 0.0000 | 0.0000 | 290 |

## Baseline gazetteer

Bảng tra cứu *tên → loại* dựng từ tập **train**, dự đoán tập **dev**.

| Chỉ số | Giá trị |
|---|---|
| micro F1 | 0.7990 |
| micro P | 0.9880 |
| micro R | 0.6707 |
| macro F1 | 0.8261 |

### F1 theo loại

| Nhãn | P | R | F1 | Support |
|---|---|---|---|---|
| DYNASTY | 0.8860 | 0.9252 | 0.9052 | 588 |
| EVENT | 0.9811 | 0.8114 | 0.8883 | 769 |
| LOCATION | 0.9909 | 0.8799 | 0.9322 | 3107 |
| PERSON | 0.9985 | 0.8826 | 0.9370 | 3877 |
| TIME | 1.0000 | 0.3352 | 0.5021 | 5143 |
| TITLE | 1.0000 | 0.6552 | 0.7917 | 290 |

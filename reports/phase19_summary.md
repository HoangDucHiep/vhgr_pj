## Tổng hợp eval — Phase-19 (đang chạy)

| Nhóm | Arm | n | correctness | faithfulness | not_in_data | abstain+căn cứ | latency p50 (ms) | latency p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| relational | A | 57 | 1.404 | 1.789 | 22 | 4 | 2658 | 9603 |
| relational | B | 57 | 1.807 | 1.86 | 3 | 1 | 2519 | 38045 |
| relational | B- | 57 | 1.298 | 1.737 | 24 | 4 | 4451 | 35533 |
| narrative | A | 52 | 1.942 | 1.904 | 2 | 0 | 2754 | 4180 |
| narrative | B | 52 | 1.904 | 1.846 | 0 | 0 | 3339 | 6800 |
| narrative | B- | 52 | 1.942 | 1.885 | 1 | 0 | 2776 | 4743 |
| multi_hop | A | 22 | 1.091 | 2 | 11 | 0 | 2866 | 5424 |
| multi_hop | B | 22 | 1.545 | 1.5 | 0 | 0 | 2151 | 3158 |
| multi_hop | B- | 22 | 1.273 | 1.955 | 6 | 0 | 2813 | 6959 |
| multi_turn | A | 0 | None | None | 0 | 0 | 0 | 0 |
| multi_turn | B | 0 | None | None | 0 | 0 | 0 | 0 |
| multi_turn | B- | 0 | None | None | 0 | 0 | 0 | 0 |
| no_data | A | 0 | None | None | 0 | 0 | 0 | 0 |
| no_data | B | 0 | None | None | 0 | 0 | 0 | 0 |
| no_data | B- | 0 | None | None | 0 | 0 | 0 | 0 |

| Arm | n | correctness | faithfulness | citeP | grounding (code) | mệnh đề không căn cứ | not_in_data | abstain+căn cứ | latency p50 | latency p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 131 | 1.565 | 1.87 | 0.822 | 0.9948 | 1/512 | 35 | 4 | 2744 | 6715 |
| B | 131 | 1.802 | 1.794 | 0.883 | 0.9873 | 6/548 | 3 | 1 | 3039 | 29232 |
| B- | 131 | 1.55 | 1.832 | 0.799 | 0.9848 | 3/532 | 31 | 4 | 2919 | 27381 |

## Tổng hợp eval — Phase-19 (partial)

| Nhóm | Arm | n | correctness | faithfulness | not_in_data | abstain+căn cứ | latency p50 (ms) | latency p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| relational | A | 57 | 1.123 | 1.971 | 22 | 4 | 2658 | 9603 |
| relational | B | 57 | 1.772 | 1.889 | 3 | 1 | 2519 | 38045 |
| relational | B- | 57 | 1.053 | 1.909 | 24 | 4 | 4451 | 35533 |
| narrative | A | 53 | 1.811 | 1.918 | 2 | 0 | 2754 | 4180 |
| narrative | B | 53 | 1.83 | 1.843 | 0 | 0 | 3340 | 6800 |
| narrative | B- | 53 | 1.887 | 1.882 | 1 | 0 | 2797 | 4743 |
| multi_hop | A | 22 | 0.682 | 2 | 11 | 0 | 2866 | 5424 |
| multi_hop | B | 22 | 1.545 | 1.5 | 0 | 0 | 2151 | 3158 |
| multi_hop | B- | 22 | 1.091 | 1.929 | 6 | 0 | 2813 | 6959 |
| multi_turn | A | 0 | None | None | 0 | 0 | 0 | 0 |
| multi_turn | B | 0 | None | None | 0 | 0 | 0 | 0 |
| multi_turn | B- | 0 | None | None | 0 | 0 | 0 | 0 |
| no_data | A | 0 | None | None | 0 | 0 | 0 | 0 |
| no_data | B | 0 | None | None | 0 | 0 | 0 | 0 |
| no_data | B- | 0 | None | None | 0 | 0 | 0 | 0 |

| Arm | n | correctness | faithfulness | citeP | grounding (code) | mệnh đề không căn cứ | not_in_data | abstain+căn cứ | latency p50 | latency p95 |
|---|---|---|---|---|---|---|---|---|---|---|
| A | 132 | 1.326 | 1.947 | 0.976 | 0.9948 | 1/522 | 35 | 4 | 2734 | 6715 |
| B | 132 | 1.758 | 1.803 | 0.895 | 0.9874 | 6/555 | 3 | 1 | 3039 | 29232 |
| B- | 132 | 1.394 | 1.898 | 0.936 | 0.985 | 3/541 | 31 | 4 | 2949 | 27381 |

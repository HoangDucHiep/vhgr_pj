# Báo cáo chất lượng coreference — Phase 6

Nguồn: `data/interim/coref_resolved.jsonl`

## 1. Tổng quan

| Chỉ số | Giá trị |
|---|---|
| Số câu | 186.960 |
| Số mention | 197.610 |
| Mention có `canonical_id` | 137.584 |
| **Tỉ lệ resolve (toàn bộ)** | **69.62%** |
| **Tỉ lệ resolve (không tính TIME)** | **96.35%** |
| Số danh xưng/đại từ | 54.502 |
| Tỉ lệ resolve danh xưng | 90.46% |

## 2. Phân bố `resolved_by`

| `resolved_by` | Số mention |
|---|---|
| `explicit` | 88.283 |
| `unlinked` | 54.825 |
| `article_subject` | 32.341 |
| `coref_honorific` | 14.521 |
| `ambiguous` | 5.201 |
| `coref_pronoun` | 2.439 |

## 3. Phân bố nhãn

| Nhãn | Tổng | Đã resolve |
|---|---|---|
| `PERSON` | 91.578 | 86.450 |
| `TIME` | 54.955 | 130 |
| `LOCATION` | 29.883 | 29.883 |
| `EVENT` | 9.739 | 9.739 |
| `DYNASTY` | 6.747 | 6.747 |
| `TITLE` | 4.708 | 4.635 |

## 4. Kiểm tra contract (Gate G1, G7)

| Kiểm tra | Số lỗi |
|---|---|
| `canonical_id_sai_dinh_dang` | 0 |
| `offset_khong_khop` | 0 |
| `nhan_ngoai_danh_muc` | 0 |
| `resolved_by_ngoai_danh_muc` | 0 |

**Tổng vi phạm: 0 — ✅ đạt**

## 5. 20 ví dụ ngẫu nhiên để kiểm thử tay

Seed 42, lấy trong các câu có danh xưng/đại từ.

### `s116_238_2`

> Bà là một trong 5 người phụ nữ nổi tiếng thời Tây Sơn được mệnh danh là Tây Sơn ngũ phụng thư.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `Bà` | PERSON | `article_subject` | `ent_quang_trung_242ef52d` |

### `s116_36_3`

> Thái Đức hoàng đế sai tướng vào đánh nhưng lại bị thua và mất thêm Bình Thuận.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `hoàng đế` | PERSON | `article_subject` | `ent_quang_trung_242ef52d` |

### `s117415_2_2`

> Thuở nhỏ, ông cùng các em nổi tiếng chăm học (người em út là Quách Hữu Nghiêm sau cũng đỗ Hoàng giáp năm 1466).

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `ông` | PERSON | `article_subject` | `ent_quach_dinh_bao_bed1f006` |
| `1466` | TIME | `unlinked` | `—` |

### `s118949_59_0`

> Năm 1832, vua Minh Mạng cải cách hành chính cả nước, đổi trấn thành tỉnh.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `1832` | TIME | `unlinked` | `—` |
| `vua` | PERSON | `coref_honorific` | `ent_minh_mang_e1773f37` |
| `Minh Mạng` | PERSON | `explicit` | `ent_minh_mang_e1773f37` |

### `s1555_87_1`

> Ông khẳng định nhân dân là lực lượng sản xuất ra vật chất của xã hội và động lực quyết định sự suy vong của triều đại, đất nước.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `Ông` | PERSON | `article_subject` | `ent_nguyen_trai_c5c8e6b3` |

### `s16551_36_2`

> Khi Nghiện Thần đến Yên Kinh, vua Minh sai Hồ Nguyên Trừng mượn cớ là tình nghĩa cố cựu, hỏi về tình hình trong nước mạnh yếu hư thực thế nào, Nghiện Thần nói hết cho Nguyên Trừng biết.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `vua` | PERSON | `coref_honorific` | `ent_minh_7c12b172` |

### `s1742119_3_0`

> Tổ tiên dòng họ ông có nguồn gốc từ Thanh Hóa đến lập nghiệp tại Nghệ An vào thế kỷ 17.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `ông` | PERSON | `article_subject` | `ent_nguyen_thuc_tu_ffdaf32c` |
| `Thanh Hóa` | LOCATION | `explicit` | `ent_thanh_hoa_8597c26d` |
| `Nghệ An` | LOCATION | `explicit` | `ent_nghe_an_d79d6b07` |
| `17` | TIME | `unlinked` | `—` |

### `s17689080_1_0`

> Nhiều nguồn tài liệu viết tên ông là Cáp hoặc Hợp, do đọc theo âm chữ [<bỏ dấu>] ở dưới bộ Miên (<bỏ dấu>).

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `ông` | PERSON | `article_subject` | `ent_nguyen_phuc_mien_khap_3c14194d` |

### `s19625169_6_1`

> Sau đó, ông quyết định thôi nghề dạy để về quê truyền bá tư tưởng cách mạng vô sản cho dân chúng.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `ông` | PERSON | `article_subject` | `ent_tran_toai_29ab1a4d` |

### `s2235090_0_1`

> Ông xuất thân là một ngư dân ngang tàng, có sức khỏe và tài năng chiêu dân chống lại thiên tai, được triều đình nhà Đinh trọng dụng và ban thưởng.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `Ông` | PERSON | `ambiguous` | `—` |
| `nhà Đinh` | DYNASTY | `explicit` | `ent_nha_dinh_5bd2e47e` |

### `s229620_70_1`

> Ngày 8 tháng 4, ông cùng Hard Rock International thực hiện ấn bản Eric Clapton Artist Spotlight ủng hộ tổ chức Crossroads Centre Antigua.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `ông` | PERSON | `article_subject` | `ent_eric_clapton_1ba3aba7` |

### `s234915_24_4`

> Nhà vua ôm mãi lấy Thái tử, không nỡ ly biệt.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `vua` | PERSON | `article_subject` | `ent_le_hien_tong_c54b6046` |
| `Thái tử` | TITLE | `article_subject` | `ent_le_hien_tong_c54b6046` |

### `s245014_33_2`

> Năm 1809, hài cốt của ông được đưa về mộ ở Long Hồ, thờ chung viên tẩm với cha là Tuyên vương Phúc Hạo.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `1809` | TIME | `unlinked` | `—` |
| `ông` | PERSON | `article_subject` | `ent_nguyen_phuc_duong_50691986` |
| `Long Hồ` | LOCATION | `explicit` | `ent_long_ho_372727c7` |

### `s29952_135_5`

> Về nhân vật Tuan Phaow (Đồng Phù), có ý kiến cho rằng ông ta trốn chạy sang Campuchia với tên Tuon Set Asmit và được vua Ang Eng thu dùng, cho làm tỉnh trưởng Tbong Khmum.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `ông ta` | PERSON | `article_subject` | `ent_lich_su_cham_pa_f84c4e01` |
| `vua` | PERSON | `coref_honorific` | `ent_ang_eng_00c17ba2` |
| `Ang Eng` | PERSON | `explicit` | `ent_ang_eng_00c17ba2` |
| `Tbong Khmum` | LOCATION | `explicit` | `ent_tbong_khmum_2ac2770f` |

### `s42146_38_4`

> Tống sử cho biết Lê Hoàn đã sai sứ dâng 93 tù binh Chiêm Thành cho vua Tống nhằm chứng tỏ thực lực của Đại Cồ Việt.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `Tống sử` | PERSON | `explicit` | `ent_tong_su_89057824` |
| `vua` | PERSON | `coref_honorific` | `ent_tong_cb44c899` |
| `Đại Cồ Việt` | EVENT | `explicit` | `ent_dai_co_viet_72acb714` |

### `s55946_2_2`

> Sau đó, năm 1599, ông buộc nhà vua phải phong cho mình tước Bình An Vương (<bỏ dấu>) và lập phủ Chúa ngay bên cạnh triều đình vua Lê.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `1599` | TIME | `unlinked` | `—` |
| `ông` | PERSON | `article_subject` | `ent_trinh_tung_48a810c1` |
| `vua` | PERSON | `article_subject` | `ent_trinh_tung_48a810c1` |
| `vua` | PERSON | `coref_honorific` | `ent_le_e34b3c45` |

### `s65970_2_2`

> Sau khi Hoàng Kế Viêm thi đỗ cử nhân vào năm 1843 thời vua Thiệu Trị, ông được bổ Tư vụ, hàm Quang lộc tự khanh.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `1843` | TIME | `unlinked` | `—` |
| `vua` | PERSON | `coref_honorific` | `ent_thieu_tri_5e0c56a5` |
| `Thiệu Trị` | PERSON | `explicit` | `ent_thieu_tri_5e0c56a5` |
| `ông` | PERSON | `article_subject` | `ent_hoang_ke_viem_1b45b2b4` |
| `Tư` | DYNASTY | `explicit` | `ent_tu_344470d7` |

### `s80936_4_1`

> Trước đó, cuối năm 1971, ông về thăm quê và người thân ở Bình Định, nhưng để giữ bí mật, ông không cho ai biết dự định ra chiến khu của mình, kể cả mẹ ông.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `1971` | TIME | `unlinked` | `—` |
| `ông` | PERSON | `ambiguous` | `—` |
| `ông` | PERSON | `ambiguous` | `—` |
| `ông` | PERSON | `ambiguous` | `—` |

### `s83758_8_6`

> Vua Xiêm La muốn giữ lại, nhưng ông cương quyết về với chúa Nguyễn.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `Vua` | PERSON | `coref_honorific` | `ent_xiem_la_51579f8b` |
| `ông` | PERSON | `article_subject` | `ent_nguyen_huynh_duc_9a5fafe0` |

### `s983252_26_0`

> Sau đó Trịnh Doanh sai ông làm Đốc suất Nghệ An.

| Mention | Nhãn | `resolved_by` | `canonical_id` |
|---|---|---|---|
| `Trịnh Doanh` | PERSON | `explicit` | `ent_trinh_doanh_ab000561` |
| `ông` | PERSON | `article_subject` | `ent_pham_dinh_trong_vo_tuong_d4c97980` |
| `Nghệ An` | LOCATION | `explicit` | `ent_nghe_an_d79d6b07` |

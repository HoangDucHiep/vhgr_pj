"""Gán tay bộ gold coref 100 câu (Phase 6).

File này chứa **nhãn vàng thủ công** cho `data/eval/coref_gold_100.jsonl`.
Mỗi mục là `(sentence_id, start, end) -> (canonical_id | None, resolved_by)`.

Nguyên tắc gán
--------------
- Chỉ gán cho mention có `source` ∈ {`pronoun`, `pronoun_name`} (đại từ /
  danh xưng), **không** gán cho mention NER có tên (đó là R0/R0' — tra
  gazetteer, không phải coreference).
- `canonical_id = None` khi:
  - thực sự không xác định được (đại từ số nhiều, phong cách báo chí
    không rõ chủ thể, v.v.), **hoặc**
  - hệ thống gán sai (ghi `resolved_by` = cách hệ thống đã gán để đối
    chiếu).
- `resolved_by` ghi **cách hệ thống đã dùng** (`explicit` · `coref_pronoun`
  · `coref_honorific` · `article_subject` · `ambiguous` · `unlinked`) để
  đo độ chính xác theo từng nhóm quy tắc.

Cách dùng
----------
```bash
python scripts/coref_gold_annotate.py --config configs/default.yaml
```
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_config, resolve_path  # noqa: E402
from src.common.logger import get_logger  # noqa: E402

logger = get_logger(__name__)

#: Nhãn vàng thủ công: `sentence_id -> [(start, end, canonical_id, resolved_by)]`.
#:
#: `canonical_id` = `None` → không xác định được (gold = null).
#: `resolved_by` = cách hệ thống đã gán (để đo độ chính xác theo nhóm).
GOLD: dict[str, list[tuple[int, int, str | None, str | None]]] = {
    # --- [0] Quang Trung ---
    "s116_128_0": [
        (0, 3, "ent_quang_trung_242ef52d", "coref_honorific"),
        (37, 40, "ent_quang_trung_242ef52d", "article_subject"),
    ],
    # --- [1] Quang Trung ---
    "s116_315_3": [
        (77, 80, "ent_quang_trung_242ef52d", "coref_pronoun"),
    ],
    # --- [2] Quang Trung ---
    "s116_327_10": [
        (24, 32, "ent_quang_trung_242ef52d", "coref_honorific"),
    ],
    # --- [3] Quang Trung — "Vua Xiêm" (người Xiêm, KHÔNG phải Quang Trung) ---
    "s116_40_1": [
        (0, 3, "ent_xiem_47d92d5e", "coref_honorific"),
    ],
    # --- [4] Quang Trung — "Vua Chiêu Thống" ---
    "s116_66_2": [
        (0, 3, "ent_chieu_thong_ab710949", "coref_honorific"),
    ],
    # --- [5] Quang Trung — "Vua Lê Chiêu Thống" ---
    "s116_66_5": [
        (0, 3, "ent_le_chieu_thong_858c94dd", "coref_honorific"),
    ],
    # --- [6] Đặng Lộ — "ông" = Đặng Lộ; "vua Trần" = nhà Trần (số nhiều) ---
    "s1336333_0_1": [
        (99, 102, "ent_dang_lo_f847b6e5", "coref_pronoun"),
        (118, 121, None, "ambiguous"),
        (143, 146, "ent_dang_lo_f847b6e5", "coref_pronoun"),
    ],
    # --- [7] Trịnh Thị Ngọc Lung — "vua Lê Hy Tông" ---
    "s1336758_12_0": [
        (108, 111, "ent_le_hy_tong_35698bc5", "coref_honorific"),
    ],
    # --- [8] Vũ Duy Đoán ---
    "s1376680_2_5": [
        (52, 55, "ent_vu_duy_doan_49eaf277", "coref_pronoun"),
    ],
    # --- [9] Cửu Đỉnh (nhà Nguyễn) — 8 danh xưng "vua" + tên ---
    "s141105_25_1": [
        (30, 33, "ent_minh_mang_e1773f37", "coref_honorific"),
        (77, 80, "ent_thieu_tri_5e0c56a5", "coref_honorific"),
        (121, 124, "ent_tu_duc_8a7b7dd0", "coref_honorific"),
        (163, 166, "ent_kien_phuc_c12a8f41", "coref_honorific"),
        (209, 212, "ent_dong_khanh_d5fe6bba", "coref_honorific"),
        (256, 259, "ent_khai_dinh_881d0feb", "coref_honorific"),
        (299, 302, "ent_ham_nghi_3f195773", "coref_honorific"),
        (344, 347, "ent_duy_tan_dc5258b1", "coref_honorific"),
    ],
    # --- [10] Ngô Quyền — "tự lập mình làm vua" → Dương Bình Vương ---
    "s1411_41_0": [
        (46, 49, "ent_duong_binh_vuong_04e50dfb", "coref_pronoun"),
    ],
    # --- [11] Ngô Quyền ---
    "s1411_62_1": [
        (0, 3, "ent_ngo_quyen_70732bc0", "article_subject"),
    ],
    # --- [12] Phạm Thị Trân — "tước Ưu Bà" ---
    "s144739_0_0": [
        (34, 36, "ent_pham_thi_tran_0c3101bc", "article_subject"),
    ],
    # --- [13] Phạm Thị Trân ---
    "s144739_18_0": [
        (47, 50, "ent_dinh_85a4026d", "coref_honorific"),
        (57, 59, "ent_pham_thi_tran_0c3101bc", "coref_honorific"),
    ],
    # --- [14] Thất trảm sớ ---
    "s145888_0_0": [
        (68, 71, "ent_tran_du_tong_c96000c8", "coref_honorific"),
        (112, 115, "ent_tran_du_tong_c96000c8", "coref_pronoun"),
    ],
    # --- [15] Chùa Hàm Long — "ông" = trụ trì Thích Thanh Dũng ---
    "s15240412_11_0": [
        (10, 13, None, "ambiguous"),
    ],
    # --- [16] Lý Thần Tông ---
    "s152713_3_1": [
        (3, 6, "ent_ly_than_tong_71b99f5c", "article_subject"),
    ],
    # --- [17] Xác ướp Xóm Cải ---
    "s15273554_12_0": [
        (22, 24, "ent_xac_uop_xom_cai_175b93a9", "article_subject"),
        (155, 158, None, "article_subject"),
    ],
    # --- [18] Đa Minh Phạm Trọng Khảm — "ông" = chính Đa Minh ---
    "s15390954_4_1": [
        (47, 50, "ent_da_minh_pham_trong_kham_8cf2f276", "ambiguous"),
    ],
    # --- [19] Hiệp định Genève 1954 — "ông" = tướng Navarre ---
    "s16599_8_0": [
        (90, 93, None, "ambiguous"),
    ],
    # --- [20] Thành cổ Quảng Trị ---
    "s16766_1_1": [
        (46, 49, "ent_minh_mang_e1773f37", "coref_honorific"),
    ],
    # --- [21] Lê Duy Phường — "lập ... làm vua, tức là Lê Ý Tông" ---
    "s173011_10_1": [
        (49, 52, "ent_le_y_tong_d1caf7c3", "coref_honorific"),
    ],
    # --- [22] Phan Kế Toại ---
    "s176100_31_0": [
        (7, 10, "ent_phan_ke_toai_71596242", "article_subject"),
        (25, 27, "ent_nguyen_thi_mao_b2c78993", "coref_honorific"),
    ],
    # --- [23] Giuse Hoàng Lương Cảnh — "ông" = chính Đức Mẹ ---
    "s19642894_1_7": [
        (22, 25, "ent_giuse_hoang_luong_canh_249d9d80", "ambiguous"),
    ],
    # --- [24] Nguyễn An (nhạc sĩ) — "Cô gái Sơn Tây" = tên tác phẩm ---
    "s19883179_13_0": [
        (59, 65, "ent_son_tay_87c1ef8a", "coref_honorific"),
    ],
    # --- [25] Nguyễn An (nhạc sĩ) ---
    "s19883179_6_0": [
        (0, 3, "ent_nguyen_an_nhac_si_52ec34b4", "article_subject"),
    ],
    # --- [26] Bùi Bình Thi ---
    "s19928167_31_1": [
        (0, 3, "ent_bui_binh_thi_952e925e", "article_subject"),
    ],
    # --- [27] Nguyễn Hữu Thảng ---
    "s20031033_2_8": [
        (18, 21, "ent_nguyen_huu_thang_b193540b", "coref_pronoun"),
    ],
    # --- [28] Điện Thái Hòa — "vua Thành Thái" ---
    "s201789_11_0": [
        (97, 100, "ent_thanh_thai_67764b20", "coref_honorific"),
    ],
    # --- [29] Võ Tánh ---
    "s213054_23_0": [
        (38, 41, "ent_vo_tanh_d27ec873", "article_subject"),
    ],
    # --- [30] Võ Tánh ---
    "s213054_6_0": [
        (49, 52, "ent_vo_tanh_d27ec873", "article_subject"),
    ],
    # --- [31] Lê Hiển Tông — "con thứ tư của vua" = Lê Duy Cận ---
    "s234915_24_9": [
        (47, 50, "ent_le_hien_tong_c54b6046", "coref_pronoun"),
        (69, 76, "ent_le_duy_can_549a078c", "coref_pronoun"),
    ],
    # --- [32] Nguyễn Văn Nhơn ---
    "s276733_32_0": [
        (0, 9, "ent_nguyen_van_nhon_c7cc6b75", "coref_honorific"),
        (112, 115, "ent_thieu_tri_5e0c56a5", "coref_pronoun"),
    ],
    # --- [33] Tađêô Lê Hữu Từ ---
    "s283212_51_0": [
        (94, 97, "ent_tadeo_le_huu_tu_1e3b87c2", "article_subject"),
    ],
    # --- [34] Mai Hắc Đế — "miếu vua Mai" ---
    "s28923_45_0": [
        (27, 30, "ent_mai_9f0844a2", "coref_honorific"),
    ],
    # --- [35] Hưng Hóa — "ông Nguyễn Đức Du" ---
    "s29880_13_0": [
        (16, 19, None, "coref_honorific"),
    ],
    # --- [36] Phan Văn Lân — "vua Quang Trung" ---
    "s308387_16_0": [
        (66, 69, "ent_quang_trung_242ef52d", "coref_honorific"),
    ],
    # --- [37] Donald Sutherland ---
    "s3140902_0_1": [
        (0, 3, "ent_donald_sutherland_10fb1055", "article_subject"),
    ],
    # --- [38] Hiển Từ Thuận Thiên hoàng hậu — "vua cha" + "bà" ---
    "s3197998_23_1": [
        (43, 46, None, "article_subject"),
        (56, 58, "ent_hien_tu_thuan_thien_hoang_hau_76840f87", "article_subject"),
    ],
    # --- [39] Hiển Từ Thuận Thiên hoàng hậu ---
    "s3197998_2_1": [
        (5, 7, "ent_hien_tu_thuan_thien_hoang_hau_76840f87", "article_subject"),
    ],
    # --- [40] Hiển Từ Thuận Thiên hoàng hậu — "anh trai lớn của mẹ bà" ---
    "s3197998_4_1": [
        (184, 186, "ent_hien_tu_thuan_thien_hoang_hau_76840f87", "coref_pronoun"),
    ],
    # --- [41] Hiển Từ Thuận Thiên hoàng hậu — "đại vương Trần Quốc Khang" ---
    "s3197998_8_0": [
        (117, 126, "ent_tran_quoc_khang_4ef2b549", "coref_honorific"),
    ],
    # --- [42] George Harrison — "ông" = The Beatles (ban nhạc) ---
    "s321161_1_2": [
        (83, 86, "ent_the_beatles_aff45f67", "coref_pronoun"),
    ],
    # --- [43] George Harrison ---
    "s321161_50_2": [
        (27, 30, "ent_george_harrison_d09e2d64", "article_subject"),
    ],
    # --- [44] George Harrison — "ông"=Harrison, "ông"(lần 2)=Chuck Berry ---
    "s321161_61_3": [
        (0, 3, "ent_george_harrison_d09e2d64", "article_subject"),
        (78, 81, "ent_chuck_berry_94fca280", "coref_pronoun"),
    ],
    # --- [45] George Harrison ---
    "s321161_71_4": [
        (19, 22, "ent_george_harrison_d09e2d64", "coref_pronoun"),
    ],
    # --- [46] George Harrison ---
    "s321161_73_1": [
        (32, 35, "ent_george_harrison_d09e2d64", "article_subject"),
        (101, 104, "ent_george_harrison_d09e2d64", "article_subject"),
    ],
    # --- [47] Nguyễn Duy Hiệu — "triều vua Đồng Khánh" ---
    "s33608_8_0": [
        (50, 53, "ent_dong_khanh_d5fe6bba", "coref_honorific"),
    ],
    # --- [48] Nguyễn Duy Hiệu — "học trò của ông" = Nguyễn Duy Hiệu ---
    "s33608_9_1": [
        (81, 84, "ent_dong_khanh_d5fe6bba", "coref_honorific"),
        (117, 120, "ent_nguyen_duy_hieu_03c0e048", "coref_pronoun"),
    ],
    # --- [49] Trần Thủ Độ — "Thái tử Lý Huệ Tông" ---
    "s33633_1_0": [
        (119, 126, "ent_ly_hue_tong_37a57eda", "coref_pronoun"),
    ],
    # --- [50] Bà Huyện Thanh Quan ---
    "s34187_3_2": [
        (14, 16, "ent_ba_huyen_thanh_quan_0f8c7bab", "coref_pronoun"),
    ],
    # --- [51] Đèo Văn Long ---
    "s341912_0_0": [
        (150, 153, "ent_deo_van_long_7a542fd8", "article_subject"),
    ],
    # --- [52] Đèo Văn Long ---
    "s341912_2_0": [
        (122, 125, "ent_deo_van_long_7a542fd8", "article_subject"),
    ],
    # --- [53] Thân Văn Nhiếp ---
    "s3424148_8_0": [
        (56, 59, "ent_than_van_nhiep_da125df5", "article_subject"),
    ],
    # --- [54] Diệp Văn Cương — "ông" = Diệp Văn Cương (sau Thành Thái) ---
    "s343848_15_0": [
        (29, 32, "ent_diep_van_cuong_665fbc36", "coref_pronoun"),
    ],
    # --- [55] Diệp Văn Cương ---
    "s343848_34_0": [
        (29, 32, "ent_diep_van_cuong_665fbc36", "article_subject"),
        (88, 91, "ent_diep_van_cuong_665fbc36", "article_subject"),
        (304, 307, "ent_diep_van_cuong_665fbc36", "article_subject"),
    ],
    # --- [56] Hồ Nguyên Trừng — "Cha con vua Hồ" = Hồ Quý Ly ---
    "s35255_22_2": [
        (8, 11, "ent_ho_7d45b9e8", "coref_honorific"),
    ],
    # --- [57] Hồ Nguyên Trừng — "cho con ông" = Lê Thúc Lâm ---
    "s35255_42_0": [
        (41, 44, "ent_ho_nguyen_trung_1c51d392", "article_subject"),
    ],
    # --- [58] Hồ Nguyên Trừng — "Hoàng đế (Chu Đệ)" ---
    "s35255_44_4": [
        (13, 21, "ent_chu_de_03a7c9c8", "coref_honorific"),
    ],
    # --- [59] Hồ Nguyên Trừng ---
    "s35255_44_6": [
        (13, 16, "ent_ho_nguyen_trung_1c51d392", "article_subject"),
    ],
    # --- [60] Tranh chấp đất đai tại Đồng Tâm — "Bà" = không rõ ---
    "s3678090_27_1": [
        (0, 2, None, "ambiguous"),
    ],
    # --- [61] Tranh chấp đất đai tại Đồng Tâm ---
    "s3678090_86_0": [
        (54, 57, None, "ambiguous"),
    ],
    # --- [62] Chiến tranh Việt – Xiêm (1841–1845) ---
    "s411524_41_2": [
        (18, 21, None, "ambiguous"),
    ],
    # --- [63] Chiến tranh Việt – Xiêm (1841–1845) — "vua Phuttha Yotfa" ---
    "s411524_4_2": [
        (10, 13, "ent_phuttha_yotfa_chulalok_378ff076", "coref_honorific"),
    ],
    # --- [64] Phạm Trọng Cầu ---
    "s41239_5_1": [
        (19, 22, "ent_pham_trong_cau_a9e38376", "ambiguous"),
    ],
    # --- [65] Nguyễn Văn Tường — "vua Hàm Nghi" ---
    "s42024_40_0": [
        (68, 71, "ent_ham_nghi_3f195773", "coref_honorific"),
    ],
    # --- [66] Sự biến Thổ Mộc bảo — "lên ngôi hoàng đế" = Chu Kỳ Ngọc ---
    "s420361_35_2": [
        (106, 114, "ent_chu_ky_ngoc_205aa79e", "coref_pronoun"),
    ],
    # --- [67] Lê Uy Mục ---
    "s42055_18_1": [
        (22, 25, "ent_le_uy_muc_1cb6b9ac", "article_subject"),
        (95, 98, "ent_le_uy_muc_1cb6b9ac", "coref_pronoun"),
        (156, 159, "ent_le_uy_muc_1cb6b9ac", "coref_pronoun"),
        (229, 232, "ent_le_uy_muc_1cb6b9ac", "coref_pronoun"),
    ],
    # --- [68] Lê Trung Tông (Tiền Lê) ---
    "s42322_24_0": [
        (35, 38, "ent_le_dai_hanh_23f6a9e7", "coref_honorific"),
        (100, 103, "ent_le_trung_tong_tien_le_2f851d8f", "coref_pronoun"),
        (150, 153, "ent_le_long_dinh_07bc012e", "coref_honorific"),
    ],
    # --- [69] Loạn 12 sứ quân ---
    "s42495_73_1": [
        (13, 16, None, "ambiguous"),
    ],
    # --- [70] Lịch sử chiến tranh Trung Quốc – Việt Nam ---
    "s434790_28_2": [
        (8, 11, None, "ambiguous"),
    ],
    # --- [71] Lịch sử chiến tranh Trung Quốc – Việt Nam — "các vua Trần" ---
    "s434790_38_0": [
        (195, 198, None, "ambiguous"),
    ],
    # --- [72] Nguyễn Hữu Bài ---
    "s448517_5_1": [
        (10, 13, "ent_nguyen_huu_bai_8d62f658", "coref_pronoun"),
    ],
    # --- [73] Nguyễn Mộng Tuân — "Đời Lê Nhân Tông ông giữ chức..." ---
    "s475085_5_4": [
        (17, 20, "ent_nguyen_mong_tuan_d13dd8a6", "coref_pronoun"),
    ],
    # --- [74] Trương Hán Siêu ---
    "s49066_0_0": [
        (119, 122, None, "article_subject"),
        (237, 240, "ent_truong_han_sieu_f2c42350", "article_subject"),
        (248, 251, None, "article_subject"),
    ],
    # --- [75] Trương Hán Siêu ---
    "s49066_15_2": [
        (17, 20, "ent_truong_han_sieu_f2c42350", "article_subject"),
    ],
    # --- [76] Trương Hán Siêu ---
    "s49066_24_1": [
        (81, 84, "ent_truong_han_sieu_f2c42350", "article_subject"),
        (123, 126, "ent_truong_han_sieu_f2c42350", "article_subject"),
    ],
    # --- [77] Trương Hán Siêu ---
    "s49066_26_1": [
        (10, 13, "ent_truong_han_sieu_f2c42350", "article_subject"),
    ],
    # --- [78] Nhà Nguyễn — "nhà vua" (số nhiều) ---
    "s4997_124_7": [
        (271, 274, None, "coref_pronoun"),
        (317, 320, None, "coref_pronoun"),
    ],
    # --- [79] Nhà Nguyễn — "vua Bảo Đại" ---
    "s4997_149_2": [
        (61, 64, "ent_bao_dai_3a960bfa", "coref_honorific"),
    ],
    # --- [80] Nhà Nguyễn — "chức danh tể tướng" ---
    "s4997_175_2": [
        (68, 76, None, "coref_pronoun"),
    ],
    # --- [81] Đảo chính Việt Nam Cộng hòa 1963 — "các ông" (số nhiều) ---
    "s512057_114_2": [
        (22, 25, None, "ambiguous"),
    ],
    # --- [82] Đảo chính Việt Nam Cộng hòa 1963 ---
    "s512057_147_4": [
        (107, 110, "ent_ngo_dinh_diem_17e3f059", "coref_pronoun"),
    ],
    # --- [83] Đảo chính Việt Nam Cộng hòa 1963 ---
    "s512057_151_0": [
        (0, 3, "ent_ngo_dinh_diem_17e3f059", "ambiguous"),
    ],
    # --- [84] Đảo chính Việt Nam Cộng hòa 1963 ---
    "s512057_5_3": [
        (14, 17, "ent_ngo_dinh_diem_17e3f059", "ambiguous"),
        (72, 75, "ent_ngo_dinh_diem_17e3f059", "ambiguous"),
    ],
    # --- [85] Ngoại giao Việt Nam thời Nguyễn — "đối với vua" ---
    "s544352_59_10": [
        (85, 88, "ent_nguyen_tri_phuong_f7f39df4", "coref_pronoun"),
    ],
    # --- [86] Ngoại giao Việt Nam thời Nguyễn ---
    "s544352_9_3": [
        (0, 3, None, "ambiguous"),
    ],
    # --- [87] Phan Thúc Trực ---
    "s546166_38_1": [
        (15, 18, "ent_phan_thuc_truc_99111858", "article_subject"),
        (83, 86, "ent_phan_thuc_truc_99111858", "article_subject"),
    ],
    # --- [88] Phan Thúc Trực ---
    "s546166_40_0": [
        (0, 3, "ent_phan_thuc_truc_99111858", "article_subject"),
    ],
    # --- [89] Phan Thúc Trực — "đời Thiệu Trị, ông vẫn chỉ đỗ Tú tài" ---
    "s546166_7_0": [
        (107, 110, "ent_phan_thuc_truc_99111858", "coref_pronoun"),
    ],
    # --- [90] Giản Định Đế — "quyết định này của vua Trần" ---
    "s64678_12_3": [
        (55, 58, "ent_tran_91d2302e", "coref_honorific"),
    ],
    # --- [91] Trần Nhật Duật ---
    "s68748_0_2": [
        (0, 3, "ent_tran_nhat_duat_49989774", "article_subject"),
    ],
    # --- [92] Trần Nhật Duật ---
    "s68748_30_3": [
        (0, 3, "ent_tran_nhat_duat_49989774", "article_subject"),
        (73, 76, "ent_tran_nhat_duat_49989774", "coref_pronoun"),
    ],
    # --- [93] Lê Quát — "triều vua Trần Minh Tông" ---
    "s772237_3_0": [
        (88, 91, "ent_tran_minh_tong_b82f5c7b", "coref_honorific"),
    ],
    # --- [94] Anê Lê Thị Thành ---
    "s88640_3_0": [
        (0, 2, "ent_ane_le_thi_thanh_180768a7", "coref_honorific"),
    ],
    # --- [95] Anê Lê Thị Thành ---
    "s88640_7_0": [
        (0, 2, "ent_ane_le_thi_thanh_180768a7", "coref_honorific"),
    ],
    # --- [96] Francisco de Pina ---
    "s92588_2_3": [
        (8, 11, "ent_francisco_de_pina_e1521cdf", "coref_pronoun"),
    ],
    # --- [97] Lý Cao Tông — "vua" + "Bà Câu" ---
    "s92750_29_0": [
        (71, 74, "ent_ly_cao_tong_34ef5aec", "article_subject"),
        (132, 134, "ent_cau_ba27d729", "coref_honorific"),
    ],
    # --- [98] Lý Cao Tông ---
    "s92750_2_1": [
        (0, 3, "ent_ly_cao_tong_34ef5aec", "article_subject"),
    ],
    # --- [99] Lê Phụng Hiểu ---
    "s96607_15_0": [
        (26, 29, "ent_le_phung_hieu_ea22ce63", "article_subject"),
        (69, 72, "ent_le_phung_hieu_ea22ce63", "article_subject"),
        (135, 138, "ent_le_phung_hieu_ea22ce63", "article_subject"),
    ],
}


def main(argv: list[str] | None = None) -> int:
    """Điểm vào CLI.

    Args:
        argv: Tham số dòng lệnh.

    Returns:
        Mã thoát.
    """
    parser = argparse.ArgumentParser(
        description="Gán tay nhãn vàng coref vào data/eval/coref_gold_100.jsonl"
    )
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--gold", default=None, help="Đường dẫn gold JSONL")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    coref_config = dict(config.get("coref", {}))
    gold_path = resolve_path(
        args.gold or coref_config.get("gold_path", "data/eval/coref_gold_100.jsonl")
    )

    rows = [
        json.loads(line)
        for line in gold_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    applied = 0
    unmatched: list[str] = []
    for row in rows:
        sid = str(row.get("sentence_id"))
        labels = GOLD.get(sid)
        if labels is None:
            unmatched.append(sid)
            continue
        by_offset = {(start, end): (cid, method) for start, end, cid, method in labels}
        for mention in row.get("mentions") or []:
            key = (mention.get("start"), mention.get("end"))
            if key in by_offset:
                canonical_id, method = by_offset[key]
                mention["canonical_id"] = canonical_id
                mention["resolved_by"] = method
                applied += 1
            else:
                mention["canonical_id"] = None
                mention["resolved_by"] = "ambiguous"

    with gold_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    logger.info(
        "Đã gán %d mention trên %d câu → %s",
        applied,
        len(rows) - len(unmatched),
        gold_path,
    )
    if unmatched:
        logger.warning("Không có nhãn tay cho %d câu: %s", len(unmatched), unmatched[:10])
    return 0


if __name__ == "__main__":
    sys.exit(main())

/**
 * Hằng số dùng chung cho màu node/label.
 *
 * Nguồn: `docs/04-schema-knowledge-graph.md` §3 (7 label) + `Entity`
 * (node chưa xác định loại).
 */

/** Màu theo label Neo4j. */
export const LABEL_COLORS: Readonly<Record<string, string>> = {
  Person: '#e6194b',
  Dynasty: '#3cb44b',
  Event: '#4363d8',
  Place: '#f58231',
  Title: '#911eb4',
  Year: '#808000',
  Organization: '#008080',
  Article: '#9a6324',
  Entity: '#a9a9a9',
};

/** Nhãn hiển thị tiếng Việt cho từng label. */
export const LABEL_NAMES: Readonly<Record<string, string>> = {
  Person: 'Nhân vật',
  Dynasty: 'Triều đại',
  Event: 'Sự kiện',
  Place: 'Địa danh',
  Title: 'Miếu hiệu / chức vụ',
  Year: 'Năm',
  Organization: 'Tổ chức',
  Article: 'Bài viết',
  Entity: 'Thực thể khác',
};

/** Số node tối đa được mở rộng láng giềng mỗi lần. */
export const MAX_EXPAND_NODES = 30;

/**
 * Lấy màu của một label.
 *
 * @param label Nhãn Neo4j.
 * @returns Mã màu hex.
 */
export function colorOf(label: string): string {
  return LABEL_COLORS[label] ?? LABEL_COLORS.Entity ?? '#a9a9a9';
}

/**
 * Lấy tên hiển thị tiếng Việt của label.
 *
 * @param label Nhãn Neo4j.
 * @returns Tên tiếng Việt.
 */
export function labelNameOf(label: string): string {
  return LABEL_NAMES[label] ?? label;
}

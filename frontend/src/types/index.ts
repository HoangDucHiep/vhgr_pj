/**
 * Kiểu dữ liệu dùng chung giữa frontend và backend.
 * Nguồn sự thật cho các trường: `docs/03-kien-truc-he-thong.md` §5.
 */

/** Trạng thái chuẩn của mọi response API. */
export type ApiStatus = 'found' | 'not_in_data' | 'error';

/** Loại node trong KG. */
export type NodeType =
  | 'person'
  | 'dynasty'
  | 'event'
  | 'place'
  | 'title'
  | 'year'
  | 'article';

/** Kết quả `/api/health`. */
export interface HealthResponse {
  status: string;
  version: string;
  neo4j: 'up' | 'down';
}

/** Kết quả `/api/stats`. */
export interface StatsResponse {
  status: ApiStatus;
  nodes: number;
  edges: number;
  by_type: Record<string, number>;
  neo4j?: 'up' | 'down';
  error?: string;
}

/** Một node trong đồ thị trả về từ API. */
export interface GraphNode {
  id: string;
  label: string;
  name: string;
  verified?: boolean;
}

/** Một cạnh trong đồ thị — luôn kèm bằng chứng. */
export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
  confidence?: number;
  evidence_sentence?: string;
  source_url?: string;
}

/** Đồ thị con. */
export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

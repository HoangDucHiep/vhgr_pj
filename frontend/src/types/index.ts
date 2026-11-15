/**
 * Kiểu dữ liệu dùng chung giữa frontend và backend.
 * Nguồn sự thật cho các trường: `docs/03-kien-truc-he-thong.md` §5
 * và output contract của Phase 11 (`docs/09-ke-hoach-thuc-thien.md`).
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

/** Entity được nhận diện trong câu hỏi. */
export interface LinkedEntity {
  surface: string;
  entity_id: string;
  canonical_name: string;
}

/** Kết quả `/api/ask` (output contract Phase 11). */
export interface AskResponse {
  status: ApiStatus;
  answer: string;
  cypher: string;
  entities: LinkedEntity[];
  records: Record<string, unknown>[];
  graph: GraphPayload;
  retries: number;
  elapsed_ms: number;
}

/** Kết quả `/api/search`. */
export interface SearchResponse {
  query: string;
  count: number;
  results: Array<{
    entity_id: string;
    name: string;
    label: string;
    wiki_url: string | null;
    wikidata_qid: string | null;
  }>;
}

/** Quan hệ của một entity (từ `/api/entity/{id}`). */
export interface EntityRelation {
  relation: string;
  entity_id: string;
  name: string;
  confidence: number | null;
  evidence_sentence: string | null;
  source_url: string | null;
}

/** Kết quả `/api/entity/{id}`. */
export interface EntityDetail {
  entity_id: string;
  name: string;
  labels: string[];
  name_normalized: string;
  type: string;
  description: string | null;
  wiki_url: string | null;
  wikidata_qid: string | null;
  birth_year: number | null;
  death_year: number | null;
  reign_start: number | null;
  reign_end: number | null;
  dynasty: string | null;
  gender: string | null;
  mention_count: number;
  source_method: string;
  aliases: string[];
  relations: EntityRelation[];
}

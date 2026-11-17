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

/** Cạnh KG trả về từ kênh đồ thị của Hybrid (shape riêng). */
export interface KgEdge {
  source_id?: string;
  source_name?: string;
  target_id?: string;
  target_name?: string;
  relation?: string;
  confidence?: number | null;
  evidence_sentence?: string | null;
  source_url?: string | null;
  method?: string | null;
}

/** Node KG trả về từ kênh đồ thị của Hybrid. */
export interface KgEntity {
  entity_id: string;
  name: string;
}

/** Đồ thị KG của Hybrid (context 1-hop). */
export interface KgGraph {
  entities: KgEntity[];
  edges: KgEdge[];
  source?: string;
  n_entities?: number;
  n_edges?: number;
  elapsed_ms?: number;
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

/**
 * Kiểu arm so sánh.
 *
 * - `A` — Vanilla RAG (chỉ văn bản, `/api/ask/rag`).
 * - `B` — Hybrid GraphRAG (văn bản + KG, `/api/ask/hybrid`).
 * - `B-` — Hybrid nhưng tắt kênh KG (ablation).
 */
export type AskArm = 'A' | 'B' | 'B-';

/** Nguồn trích dẫn `[n]` (dùng chung cho văn bản và triple). */
export interface Citation {
  /** Số thứ tự trích dẫn (`[n]` trong câu trả lời). */
  n: number;
  /** `text` = đoạn văn, `kg` = triple đồ thị. */
  kind?: 'text' | 'kg';
  chunk_id?: string;
  doc_id?: string;
  title?: string | null;
  section?: string | null;
  source_url?: string | null;
  relation?: string | null;
  entity_ids?: string[];
}

/** Ý định của câu hỏi (Phase 15). */
export interface IntentInfo {
  intent: string;
  confidence?: number;
  strategy?: string;
  reason?: string;
}

/** Kết quả `/api/ask/rag` (arm A) và `/api/ask/hybrid` (arm B / B−). */
export interface RagAskResponse {
  status: ApiStatus;
  answer: string;
  citations: Citation[];
  context_used: string[];
  kg_used?: string[];
  context_text?: string;
  intent?: IntentInfo | null;
  fusion_strategy?: string;
  rewritten_question?: string;
  session_id?: string;
  entities?: Array<{ entity_id: string; name: string }>;
  /**
   * Đồ thị trả về kèm.
   *
   * - Arm A (`/api/ask/rag`): không có.
   * - Arm B/B− (`/api/ask/hybrid`): shape **KG** (`entities` + `edges` với
   *   `source_id`/`target_id`).
   */
  graph?: GraphPayload | KgGraph;
  faithfulness_ok?: boolean | null;
  retries: number;
  elapsed_ms: number;
}

/** Một lượt trong lịch sử phiên hội thoại. */
export interface SessionTurn {
  question: string;
  rewritten_question?: string;
  answer: string;
  entities?: string[];
  subject_entity_id?: string;
  subject_name?: string;
  ts?: number;
}

/** Kết quả `/api/session/{id}`. */
export interface SessionResponse {
  session_id: string;
  turns: SessionTurn[];
  last_subject_entity_id?: string;
  last_subject_name?: string;
  recent_entity_ids?: string[];
}


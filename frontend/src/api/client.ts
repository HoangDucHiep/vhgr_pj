/** Client gọi API backend. */

import type {
  AskResponse,
  EntityDetail,
  GraphPayload,
  HealthResponse,
  SearchResponse,
  StatsResponse,
} from '../types';

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '';

/**
 * Gọi GET và parse JSON.
 *
 * @param path Đường dẫn API, ví dụ `/api/health`.
 * @returns Promise chứa dữ liệu JSON.
 * @throws Error nếu response không phải 2xx hoặc JSON không hợp lệ.
 */
async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`Lỗi ${response.status} khi gọi ${path}`);
  }
  return (await response.json()) as T;
}

/**
 * Gọi POST JSON.
 *
 * @param path Đường dẫn API.
 * @param body Body gửi đi.
 * @returns Promise chứa dữ liệu JSON.
 * @throws Error nếu response không phải 2xx hoặc JSON không hợp lệ.
 */
async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Lỗi ${response.status} khi gọi ${path}`);
  }
  return (await response.json()) as T;
}

/** Lấy trạng thái dịch vụ. */
export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/health');
}

/** Lấy thống kê KG. */
export function fetchStats(): Promise<StatsResponse> {
  return getJson<StatsResponse>('/api/stats');
}

/** Gửi câu hỏi và nhận câu trả lời + Cypher + đồ thị. */
export function askQuestion(question: string): Promise<AskResponse> {
  return postJson<AskResponse>('/api/ask', { question });
}

/** Tìm entity theo tên. */
export function searchEntities(query: string): Promise<SearchResponse> {
  return getJson<SearchResponse>(`/api/search?q=${encodeURIComponent(query)}`);
}

/** Lấy đồ thị con quanh một entity. */
export function fetchGraph(entityId: string, depth = 1): Promise<GraphPayload> {
  return getJson<GraphPayload>(
    `/api/graph/${encodeURIComponent(entityId)}?depth=${depth}`,
  );
}

/** Lấy chi tiết một entity. */
export function fetchEntity(entityId: string): Promise<EntityDetail> {
  return getJson<EntityDetail>(`/api/entity/${encodeURIComponent(entityId)}`);
}

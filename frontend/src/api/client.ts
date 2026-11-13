/** Client gọi API backend. */

import type { HealthResponse, StatsResponse } from '../types';

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

/** Lấy trạng thái dịch vụ. */
export function fetchHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>('/api/health');
}

/** Lấy thống kê KG. */
export function fetchStats(): Promise<StatsResponse> {
  return getJson<StatsResponse>('/api/stats');
}

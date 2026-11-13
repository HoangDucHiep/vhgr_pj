import { useEffect, useState } from 'react';
import { fetchHealth, fetchStats } from './api/client';
import type { HealthResponse, StatsResponse } from './types';

/**
 * Trang chủ (Phase 0): hiển thị tiêu đề, trạng thái dịch vụ và placeholder
 * cho khung hỏi đáp. Nội dung UI 100% tiếng Việt.
 */
export default function App(): JSX.Element {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async (): Promise<void> => {
      try {
        const [healthResult, statsResult] = await Promise.all([
          fetchHealth(),
          fetchStats(),
        ]);
        if (cancelled) return;
        setHealth(healthResult);
        setStats(statsResult);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Lỗi không xác định');
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="app">
      <header className="app__header">
        <h1>Knowledge Graph Lịch sử Việt Nam</h1>
        <p className="app__subtitle">
          Hệ thống hỏi đáp Text-to-Cypher — 9 triều đại, 18 quan hệ, mọi cạnh đều
          có bằng chứng.
        </p>
      </header>

      <main className="app__main">
        <section className="card">
          <h2>Trạng thái dịch vụ</h2>
          {error ? (
            <p className="status status--error">
              Không kết nối được backend: {error}
            </p>
          ) : health ? (
            <ul className="status-list">
              <li>
                API: <strong>{health.status}</strong>
              </li>
              <li>
                Phiên bản: <strong>{health.version}</strong>
              </li>
              <li>
                Neo4j: <strong>{health.neo4j}</strong>
              </li>
            </ul>
          ) : (
            <p className="status">Đang tải trạng thái…</p>
          )}
        </section>

        <section className="card">
          <h2>Thống kê Knowledge Graph</h2>
          {stats ? (
            <ul className="status-list">
              <li>
                Số node: <strong>{stats.nodes}</strong>
              </li>
              <li>
                Số cạnh: <strong>{stats.edges}</strong>
              </li>
            </ul>
          ) : (
            <p className="status">Đang tải thống kê…</p>
          )}
        </section>

        <section className="card">
          <h2>Khung hỏi đáp</h2>
          <p className="placeholder">
            Ô nhập câu hỏi sẽ hoạt động từ Phase 11 (Text-to-Cypher). Gợi ý:
            <em>“Vợ của vua Lê Thái Tổ là con của ai?”</em>
          </p>
        </section>
      </main>
    </div>
  );
}

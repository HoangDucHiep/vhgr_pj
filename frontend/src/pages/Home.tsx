import { useCallback, useEffect, useState } from 'react';

import { fetchHealth, fetchStats } from '../api/client';
import type { GraphEdge, GraphNode, HealthResponse, StatsResponse } from '../types';

import ChatPanel from '../components/ChatPanel';

/**
 * Trang chủ: thống kê KG + khung hỏi đáp có đồ thị.
 *
 * @returns Element React.
 */
export default function Home(): JSX.Element {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
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

  const handleGraphChange = useCallback(
    (nextNodes: GraphNode[], nextEdges: GraphEdge[]): void => {
      setNodes(nextNodes);
      setEdges(nextEdges);
    },
    [],
  );

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1>Knowledge Graph Lịch sử Việt Nam</h1>
          <p className="page__subtitle">
            Hỏi đáp Text-to-Cypher — 9 triều đại, 18 quan hệ, mọi cạnh đều có
            bằng chứng.
          </p>
        </div>
        <div className="page__stats">
          {error ? (
            <span className="status status--error">
              Không kết nối được backend: {error}
            </span>
          ) : health ? (
            <>
              <span className={`status status--${health.neo4j}`}>
                API: {health.status} · Neo4j: {health.neo4j === 'up' ? 'sẵn sàng' : 'lỗi'}
              </span>
              {stats ? (
                <span className="status status--ok">
                  {stats.nodes.toLocaleString('vi-VN')} node ·{' '}
                  {stats.edges.toLocaleString('vi-VN')} cạnh
                </span>
              ) : null}
            </>
          ) : (
            <span className="status">Đang tải trạng thái…</span>
          )}
        </div>
      </header>

      <main className="page__main">
        <ChatPanel nodes={nodes} edges={edges} onGraphChange={handleGraphChange} />
      </main>
    </div>
  );
}

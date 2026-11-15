import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { fetchEntity, fetchGraph } from '../api/client';
import type { EntityDetail, GraphEdge, GraphNode } from '../types';

import EntityCard from '../components/EntityCard';
import EvidencePanel from '../components/EvidencePanel';
import GraphView from '../components/GraphView';
import Legend from '../components/Legend';

/**
 * Trang riêng cho một entity (`/entity/:id`).
 *
 * @returns Element React.
 */
export default function EntityPage(): JSX.Element {
  const { entityId } = useParams<{ entityId: string }>();
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!entityId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([fetchEntity(entityId), fetchGraph(entityId, 1)])
      .then(([detail, graph]) => {
        if (cancelled) return;
        setEntity(detail);
        setNodes(graph.nodes ?? []);
        setEdges(graph.edges ?? []);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Lỗi không xác định');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  const handleExpand = useCallback((): void => {
    if (!entity) return;
    fetchGraph(entity.entity_id, 2)
      .then((graph) => {
        const merged = new Map<string, GraphNode>();
        nodes.forEach((node) => merged.set(node.id, node));
        graph.nodes.forEach((node) => merged.set(node.id, node));
        setNodes([...merged.values()].slice(0, 300));
        setEdges([...(edges ?? []), ...(graph.edges ?? [])].slice(0, 300));
      })
      .catch(() => undefined);
  }, [entity, nodes, edges]);

  return (
    <div className="page">
      <header className="page__header">
        <div>
          <h1>{entity?.name ?? 'Thực thể'}</h1>
          <p className="page__subtitle">
            Đồ thị quan hệ của thực thể — click cạnh để xem bằng chứng.
          </p>
        </div>
      </header>

      <main className="page__main page__main--entity">
        {error ? (
          <p className="status status--error">Không tải được thực thể: {error}</p>
        ) : null}
        <div className="entity-layout">
          <div className="entity-layout__graph">
            <GraphView
              nodes={nodes}
              edges={edges}
              onEdgeClick={setSelectedEdge}
            />
            <Legend />
          </div>
          <div className="entity-layout__side">
            <EntityCard
              entity={entity}
              loading={loading}
              onExpand={() => void handleExpand()}
            />
            <EvidencePanel
              edge={selectedEdge}
              sourceName={
                selectedEdge
                  ? nodes.find((node) => node.id === selectedEdge.source)?.name
                  : undefined
              }
              targetName={
                selectedEdge
                  ? nodes.find((node) => node.id === selectedEdge.target)?.name
                  : undefined
              }
            />
          </div>
        </div>
      </main>
    </div>
  );
}

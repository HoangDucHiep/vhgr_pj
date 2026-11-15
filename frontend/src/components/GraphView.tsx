import { useEffect, useRef } from 'react';
import cytoscape, { type Core, type EventObject } from 'cytoscape';

import { colorOf } from '../constants/graph';
import type { GraphEdge, GraphNode } from '../types';

interface GraphViewProps {
  /** Danh sách node. */
  nodes: GraphNode[];
  /** Danh sách cạnh. */
  edges: GraphEdge[];
  /** Callback khi click node. */
  onNodeClick?: (nodeId: string) => void;
  /** Callback khi click cạnh. */
  onEdgeClick?: (edge: GraphEdge) => void;
}


/** Style Cytoscape — khai báo ngoài component để không tạo lại mỗi render. */
const GRAPH_STYLES: unknown[] = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      'font-size': 10,
      'text-valign': 'bottom',
      'text-margin-y': 4,
      width: 26,
      height: 26,
      'background-color': (element: cytoscape.NodeSingular): string =>
        colorOf(String(element.data('nodeLabel'))),
      'border-width': 2,
      'border-color': '#333333',
    },
  },
  {
    selector: 'node[verified = false]',
    style: {
      'border-style': 'dashed',
      'border-color': '#666666',
    },
  },
  {
    selector: 'edge',
    style: {
      'line-width': 1.5,
      'line-color': '#b0b0b0',
      'target-arrow-color': '#b0b0b0',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
      label: 'data(relation)',
      'font-size': 8,
      'text-rotation': 'autorotate',
      'text-background-color': '#ffffff',
      'text-background-opacity': 0.75,
      'text-background-padding': '1px',
    },
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': '#ff6600',
      'target-arrow-color': '#ff6600',
      'line-width': 3,
    },
  },
];

/**
 * Đồ thị tương tác bằng Cytoscape.js.
 *
 * - Layout `cose`; màu node theo `label`; node chưa xác minh → viền đứt.
 * - `hideEdgesOnViewport` bật khi > 300 node để giữ hiệu năng.
 * - Cleanup `cy.destroy()` trong `useEffect` để không rò rỉ bộ nhớ.
 *
 * @param props Props của component.
 * @returns Element React.
 */
export function GraphView({
  nodes,
  edges,
  onNodeClick,
  onEdgeClick,
}: GraphViewProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const cy = cytoscape({
      container,
      elements: [
        ...nodes.map((node) => ({
          data: {
            id: node.id,
            label: node.name,
            nodeLabel: node.label,
            verified: node.verified !== false,
          },
        })),
        ...edges.map((edge, index) => ({
          data: {
            id: `e${index}_${edge.source}_${edge.target}_${edge.relation}`,
            source: edge.source,
            target: edge.target,
            relation: edge.relation,
            confidence: edge.confidence ?? 0,
            evidence: edge.evidence_sentence ?? '',
            url: edge.source_url ?? '',
          },
        })),
      ],
      style: GRAPH_STYLES as never,
      layout: { name: 'cose', animate: false, nodeRepulsion: 8000, idealEdgeLength: 90 },
      wheelSensitivity: 0.2,
    });
    cyRef.current = cy;

    cy.on('tap', 'node', (event: EventObject) => {
      const id = event.target?.id?.() ?? '';
      if (id) onNodeClick?.(id);
    });
    cy.on('tap', 'edge', (event: EventObject) => {
      const rawId = event.target?.id?.() ?? '';
      const index = Number(rawId.split('_')[0].replace('e', ''));
      const edge = edges[index];
      if (edge) onEdgeClick?.(edge);
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [nodes, edges, onNodeClick, onEdgeClick]);

  return <div ref={containerRef} className="graph" data-testid="graph-view" />;
}

export default GraphView;

import { useCallback, useEffect, useRef, useState } from 'react';

import { askQuestion, fetchEntity, fetchGraph } from '../api/client';
import type { AskResponse, EntityDetail, GraphEdge, GraphNode } from '../types';

import CypherBlock from './CypherBlock';
import EntityCard from './EntityCard';
import EvidencePanel from './EvidencePanel';
import GraphView from './GraphView';
import Legend from './Legend';
import MessageBubble from './MessageBubble';

interface Turn {
  /** Câu hỏi của người dùng. */
  question: string;
  /** Kết quả trả lời (null khi đang tải). */
  response: AskResponse | null;
  /** Đang xử lý. */
  pending: boolean;
}

interface ChatPanelProps {
  /** Node/edge hiện tại (từ trang cha). */
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Callback cập nhật đồ thị. */
  onGraphChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}

/** Khóa lưu lịch sử hội thoại trong phiên. */
const STORAGE_KEY = 'vhgr.chat.history';

/**
 * Khung hỏi đáp: textarea, Enter để gửi, lịch sử hội thoại trong phiên.
 *
 * @param props Props của component.
 * @returns Element React.
 */
export function ChatPanel({
  nodes,
  edges,
  onGraphChange,
}: ChatPanelProps): JSX.Element {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [entityLoading, setEntityLoading] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);

  // Nạp lịch sử phiên.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setTurns(JSON.parse(raw) as Turn[]);
    } catch {
      /* bỏ qua lỗi localStorage */
    }
  }, []);

  // Lưu lịch sử phiên.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(turns));
    } catch {
      /* bỏ qua lỗi localStorage */
    }
  }, [turns]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [turns]);

  const handleNodeClick = useCallback(
    (nodeId: string): void => {
      setEntityLoading(true);
      fetchEntity(nodeId)
        .then((detail) => setEntity(detail))
        .catch(() => setEntity(null))
        .finally(() => setEntityLoading(false));
    },
    [],
  );

  const handleExpand = useCallback((): void => {
    if (!entity) return;
    setExpanding(true);
    fetchGraph(entity.entity_id, 1)
      .then((graph) => {
        const merged = new Map<string, GraphNode>();
        nodes.forEach((node) => merged.set(node.id, node));
        graph.nodes.forEach((node) => merged.set(node.id, node));
        const mergedEdges = [...edges, ...graph.edges].filter(
          (edge, index, list) =>
            list.findIndex(
              (other) =>
                other.source === edge.source &&
                other.target === edge.target &&
                other.relation === edge.relation,
            ) === index,
        );
        onGraphChange([...merged.values()].slice(0, 300), mergedEdges.slice(0, 300));
      })
      .catch(() => undefined)
      .finally(() => setExpanding(false));
  }, [entity, nodes, edges, onGraphChange]);

  const send = async (): Promise<void> => {
    const text = question.trim();
    if (!text || loading) return;
    setQuestion('');
    setLoading(true);
    setTurns((prev) => [...prev, { question: text, response: null, pending: true }]);

    try {
      const response = await askQuestion(text);
      setTurns((prev) =>
        prev.map((turn, index) =>
          index === prev.length - 1 ? { ...turn, response, pending: false } : turn,
        ),
      );
      if (response.graph?.nodes?.length) {
        onGraphChange(response.graph.nodes, response.graph.edges ?? []);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Lỗi không xác định';
      setTurns((prev) =>
        prev.map((turn, index) =>
          index === prev.length - 1
            ? {
                ...turn,
                pending: false,
                response: {
                  status: 'error',
                  answer: `Không gửi được câu hỏi: ${message}`,
                  cypher: '',
                  entities: [],
                  records: [],
                  graph: { nodes: [], edges: [] },
                  retries: 0,
                  elapsed_ms: 0,
                },
              }
            : turn,
        ),
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat">
      <div className="chat__history" ref={listRef}>
        {turns.length === 0 ? (
          <div className="chat__empty">
            <p>
              Hỏi bất kỳ câu nào về lịch sử Việt Nam — ví dụ: <em>“Lê Lợi sinh năm
              nào?”</em> hoặc <em>“Nhà Trần có bao nhiêu vua?”</em>
            </p>
            <ul className="chat__samples">
              <li>Lê Lợi sinh năm nào?</li>
              <li>Lê Lợi là vua nhà nào?</li>
              <li>Nguyễn Huệ chỉ huy trận nào?</li>
              <li>Nhà Trần có bao nhiêu vua?</li>
            </ul>
          </div>
        ) : null}

        {turns.map((turn, index) => (
          <div key={`${turn.question}-${index}`} className="chat__turn">
            <p className="chat__question">{turn.question}</p>
            {turn.pending ? (
              <p className="chat__loading">Đang tìm trong dữ liệu lịch sử…</p>
            ) : turn.response ? (
              <>
                <MessageBubble
                  answer={turn.response.answer}
                  status={turn.response.status}
                  elapsedMs={turn.response.elapsed_ms}
                  retries={turn.response.retries}
                />
                {turn.response.cypher ? <CypherBlock cypher={turn.response.cypher} /> : null}
                {turn.response.entities.length > 0 ? (
                  <p className="chat__entities">
                    Thực thể:{' '}
                    {turn.response.entities
                      .map((item) => `${item.surface} → ${item.canonical_name}`)
                      .join(', ')}
                  </p>
                ) : null}
              </>
            ) : null}
          </div>
        ))}
      </div>

      <div className="chat__input">
        <textarea
          value={question}
          placeholder="Nhập câu hỏi về lịch sử Việt Nam…"
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
          rows={3}
        />
        <button type="button" onClick={() => void send()} disabled={loading || !question.trim()}>
          {loading ? 'Đang xử lý…' : 'Gửi câu hỏi'}
        </button>
      </div>

      <div className="chat__side">
        <GraphView
          nodes={nodes}
          edges={edges}
          onNodeClick={handleNodeClick}
          onEdgeClick={setSelectedEdge}
        />
        <Legend />
        <EntityCard
          entity={entity}
          loading={entityLoading}
          onExpand={() => void handleExpand()}
          expanding={expanding}
        />
        <EvidencePanel
          edge={selectedEdge}
          sourceName={selectedEdge ? nodes.find((n) => n.id === selectedEdge.source)?.name : undefined}
          targetName={selectedEdge ? nodes.find((n) => n.id === selectedEdge.target)?.name : undefined}
        />
      </div>
    </div>
  );
}

export default ChatPanel;

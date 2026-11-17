import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { askByArm, fetchEntity, fetchGraph } from '../api/client';
import type {
  AskArm,
  Citation,
  GraphEdge,
  GraphNode,
  KgGraph,
  RagAskResponse,
} from '../types';

import CitationPanel from './CitationPanel';
import EntityCard from './EntityCard';
import EvidencePanel from './EvidencePanel';
import GraphView from './GraphView';
import Legend from './Legend';
import MessageBubble from './MessageBubble';

interface Turn {
  /** Câu hỏi của người dùng. */
  question: string;
  /** Kết quả trả lời (null khi đang tải). */
  response: RagAskResponse | null;
  /** Đang xử lý. */
  pending: boolean;
  /** Arm đã dùng cho lượt này. */
  arm: AskArm;
}

interface ChatPanelProps {
  /** Node/edge hiện tại (từ trang cha). */
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Callback cập nhật đồ thị. */
  onGraphChange: (nodes: GraphNode[], edges: GraphEdge[]) => void;
}

/** Khóa lưu lịch sử hội thoại trong phiên. */
const STORAGE_KEY = 'vhgr.chat.history.v2';

/** Khóa lưu arm đang chọn. */
const ARM_STORAGE_KEY = 'vhgr.chat.arm';

/** Nhãn hiển thị của từng arm. */
const ARM_LABELS: Record<AskArm, string> = {
  A: 'A · Vanilla RAG',
  B: 'B · Hybrid GraphRAG',
  'B-': 'B− · Hybrid (tắt KG)',
};

/** Mô tả ngắn arm để người dùng hiểu đang so sánh gì. */
const ARM_HINTS: Record<AskArm, string> = {
  A: 'Chỉ truy xuất văn bản Wikipedia (không dùng Knowledge Graph).',
  B: 'Văn bản + Knowledge Graph, hợp nhất theo ý định câu hỏi.',
  'B-': 'Hybrid nhưng tắt kênh đồ thị — dùng để chứng minh đóng góp của KG.',
};

/**
 * Khung hỏi đáp: chọn arm A/B, gửi câu hỏi, xem trích dẫn click-to-source,
 * đồ thị 1-hop của entity trong context và lịch sử hội thoại nhiều lượt.
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
  const [arm, setArm] = useState<AskArm>('B');
  const [loading, setLoading] = useState(false);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [entity, setEntity] = useState<Awaited<ReturnType<typeof fetchEntity>> | null>(
    null,
  );
  const [entityLoading, setEntityLoading] = useState(false);
  const [expanding, setExpanding] = useState(false);
  const [activeCitation, setActiveCitation] = useState<number | null>(null);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const listRef = useRef<HTMLDivElement | null>(null);

  // Nạp lịch sử phiên + arm đã chọn.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setTurns(JSON.parse(raw) as Turn[]);
      const storedArm = window.localStorage.getItem(ARM_STORAGE_KEY) as AskArm | null;
      if (storedArm === 'A' || storedArm === 'B' || storedArm === 'B-') {
        setArm(storedArm);
      }
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
    try {
      window.localStorage.setItem(ARM_STORAGE_KEY, arm);
    } catch {
      /* bỏ qua lỗi localStorage */
    }
  }, [arm]);

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

  /** Chuyển graph của KG (hybrid) sang định dạng Cytoscape. */
  const kgGraph = useMemo(() => {
    const graphNodes = new Map<string, GraphNode>();
    const graphEdges: GraphEdge[] = [];
    turns.forEach((turn) => {
      const graph = turn.response?.graph as KgGraph | undefined;
      if (!graph || !Array.isArray(graph.entities)) return;
      (graph.entities ?? []).forEach((item) => {
        const id = String(item.entity_id ?? '');
        if (!id) return;
        graphNodes.set(id, {
          id,
          label: 'entity',
          name: String(item.name ?? id),
        });
      });
      (graph.edges ?? []).forEach((edge) => {
        const source = String(edge.source_id ?? '');
        const target = String(edge.target_id ?? '');
        if (!source || !target) return;
        if (!graphNodes.has(source)) {
          graphNodes.set(source, {
            id: source,
            label: 'entity',
            name: String(edge.source_name ?? source),
          });
        }
        if (!graphNodes.has(target)) {
          graphNodes.set(target, {
            id: target,
            label: 'entity',
            name: String(edge.target_name ?? target),
          });
        }
        graphEdges.push({
          source,
          target,
          relation: String(edge.relation ?? ''),
          confidence: edge.confidence ?? undefined,
          evidence_sentence: edge.evidence_sentence ?? undefined,
          source_url: edge.source_url ?? undefined,
        });
      });
    });
    return { nodes: [...graphNodes.values()], edges: graphEdges };
  }, [turns]);

  const handleCitationSelect = useCallback((citation: Citation): void => {
    setActiveCitation(citation.n);
    if (citation.source_url) {
      window.open(citation.source_url, '_blank', 'noopener');
    }
  }, []);

  const send = async (): Promise<void> => {
    const text = question.trim();
    if (!text || loading) return;
    setQuestion('');
    setLoading(true);
    setTurns((prev) => [
      ...prev,
      { question: text, response: null, pending: true, arm },
    ]);

    try {
      const response = await askByArm(text, arm, sessionId);
      if (response.session_id) setSessionId(response.session_id);
      setTurns((prev) =>
        prev.map((turn, index) =>
          index === prev.length - 1 ? { ...turn, response, pending: false } : turn,
        ),
      );
      const graph = response.graph as KgGraph | undefined;
      if (graph?.entities?.length) {
        onGraphChange(
          graph.entities.map((entity) => ({
            id: entity.entity_id,
            label: 'entity',
            name: entity.name,
          })),
          [],
        );
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
                  citations: [],
                  context_used: [],
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

  /** Xoá lịch sử và bắt đầu phiên mới. */
  const resetSession = useCallback((): void => {
    setTurns([]);
    setSessionId(undefined);
    setActiveCitation(null);
  }, []);

  return (
    <div className="chat">
      <div className="chat__toolbar">
        <div className="chat__arms" role="group" aria-label="Chọn nhánh hỏi đáp">
          {(Object.keys(ARM_LABELS) as AskArm[]).map((key) => (
            <button
              key={key}
              type="button"
              className={`chat__arm ${arm === key ? 'chat__arm--active' : ''}`}
              title={ARM_HINTS[key]}
              onClick={() => setArm(key)}
            >
              {ARM_LABELS[key]}
            </button>
          ))}
        </div>
        <p className="chat__arm-hint">{ARM_HINTS[arm]}</p>
        <button type="button" className="chat__reset" onClick={resetSession}>
          Lượt chat mới
        </button>
      </div>

      <div className="chat__history" ref={listRef}>
        {turns.length === 0 ? (
          <div className="chat__empty">
            <p>
              Hỏi bất kỳ câu nào về lịch sử Việt Nam — ví dụ: <em>“Kể lại diễn biến
              trận Bạch Đằng (1288)”</em> hoặc <em>“Ai là con của Trần Nhân Tông?”</em>
            </p>
            <ul className="chat__samples">
              <li>Kể lại diễn biến trận Bạch Đằng (1288).</li>
              <li>Ai là con của Trần Nhân Tông?</li>
              <li>Trần Hưng Đạo chỉ huy trận nào?</li>
              <li>Nhà Trần có bao nhiêu vua?</li>
            </ul>
          </div>
        ) : null}

        {turns.map((turn, index) => (
          <div key={`${turn.question}-${index}`} className="chat__turn">
            <p className="chat__question">
              <span className="chat__arm-tag">{ARM_LABELS[turn.arm].split(' · ')[0]}</span>
              {turn.question}
            </p>
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
                {turn.response.intent ? (
                  <p className="chat__meta">
                    Ý định: <strong>{turn.response.intent.intent}</strong>
                    {turn.response.fusion_strategy
                      ? ` · chiến lược: ${turn.response.fusion_strategy}`
                      : ''}
                    {turn.response.rewritten_question &&
                    turn.response.rewritten_question !== turn.question
                      ? ` · đã viết lại: “${turn.response.rewritten_question}”`
                      : ''}
                  </p>
                ) : null}
                <CitationPanel
                  citations={turn.response.citations ?? []}
                  active={activeCitation}
                  onSelect={handleCitationSelect}
                />
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
          nodes={kgGraph.nodes.length > 0 ? kgGraph.nodes : nodes}
          edges={kgGraph.edges.length > 0 ? kgGraph.edges : edges}
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

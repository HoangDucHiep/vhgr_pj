import type { GraphEdge } from '../types';

interface EvidencePanelProps {
  /** Cạnh được chọn. */
  edge: GraphEdge | null;
  /** Tên node gốc (để hiển thị đầy đủ quan hệ). */
  sourceName?: string;
  /** Tên node đích. */
  targetName?: string;
}

/**
 * Panel bằng chứng — hiển thị đầy đủ thông tin của cạnh đã chọn.
 *
 * Không bao giờ để trống: nếu cạnh thiếu bằng chứng thì đó là lỗi dữ liệu
 * → hiển thị cảnh báo thay vì im lặng (theo `.cursor/rules/frontend.mdc`).
 *
 * @param props Props của component.
 * @returns Element React.
 */
export function EvidencePanel({
  edge,
  sourceName,
  targetName,
}: EvidencePanelProps): JSX.Element {
  if (!edge) {
    return (
      <aside className="evidence evidence--empty">
        <p>Chọn một cạnh trong đồ thị để xem câu bằng chứng.</p>
      </aside>
    );
  }

  const relation = edge.relation.replace(/_/g, ' ');
  const missing = !edge.evidence_sentence || !edge.source_url;

  return (
    <aside className="evidence">
      <h3 className="evidence__title">
        {sourceName ?? edge.source} <em>{relation}</em> {targetName ?? edge.target}
      </h3>

      {missing ? (
        <p className="evidence__warning">
          ⚠ Cạnh này thiếu bằng chứng — đây là lỗi dữ liệu, vui lòng báo lại.
        </p>
      ) : null}

      {edge.evidence_sentence ? (
        <blockquote className="evidence__sentence">{edge.evidence_sentence}</blockquote>
      ) : null}

      <dl className="evidence__meta">
        <dt>Độ tin cậy</dt>
        <dd>
          {edge.confidence !== undefined
            ? `${(edge.confidence * 100).toFixed(0)}%`
            : 'Không rõ'}
        </dd>
        <dt>Nguồn</dt>
        <dd>
          {edge.source_url ? (
            <a href={edge.source_url} target="_blank" rel="noopener noreferrer">
              Xem bài Wikipedia
            </a>
          ) : (
            'Không có'
          )}
        </dd>
      </dl>
    </aside>
  );
}

export default EvidencePanel;

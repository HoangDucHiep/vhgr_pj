import { useState } from 'react';

interface CypherBlockProps {
  /** Nội dung Cypher. */
  cypher: string;
}

/**
 * Khối hiển thị Cypher — mặc định thu gọn, có nút mở/ẩn và nút sao chép.
 *
 * @param props Props của component.
 * @returns Element React.
 */
export function CypherBlock({ cypher }: CypherBlockProps): JSX.Element {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(cypher);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="cypher">
      <div className="cypher__bar">
        <button
          type="button"
          className="cypher__toggle"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          {expanded ? 'Ẩn Cypher' : 'Xem Cypher'}
        </button>
        <button type="button" className="cypher__copy" onClick={() => void copy()}>
          {copied ? 'Đã sao chép' : 'Sao chép'}
        </button>
      </div>
      {expanded ? (
        <pre className="cypher__code">
          <code>{cypher}</code>
        </pre>
      ) : (
        <p className="cypher__hint">Câu truy vấn Cypher đã dùng để tìm câu trả lời.</p>
      )}
    </div>
  );
}

export default CypherBlock;

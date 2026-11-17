import { useState } from 'react';

import type { Citation } from '../types';

interface CitationPanelProps {
  /** Danh sách nguồn `[n]`. */
  citations: Citation[];
  /** Số trích dẫn đang được chọn (highlight trong câu trả lời). */
  active?: number | null;
  /** Callback khi người dùng bấm 1 trích dẫn. */
  onSelect?: (citation: Citation) => void;
}

/**
 * Danh sách nguồn của một câu trả lời (click-to-source).
 *
 * Mỗi nguồn hiển thị: số `[n]`, loại (văn bản / đồ thị), tiêu đề bài +
 * section (văn bản) hoặc quan hệ (đồ thị), và link tới nguồn Wikipedia.
 *
 * @param props Props của component.
 * @returns Element React.
 */
export function CitationPanel({
  citations,
  active = null,
  onSelect,
}: CitationPanelProps): JSX.Element | null {
  const [open, setOpen] = useState(false);
  if (!citations || citations.length === 0) return null;

  const visible = open ? citations : citations.slice(0, 4);

  return (
    <div className="citations">
      <button
        type="button"
        className="citations__toggle"
        onClick={() => setOpen((prev) => !prev)}
      >
        {open ? 'Ẩn' : 'Hiện'} nguồn ({citations.length})
      </button>
      <ul className="citations__list">
        {visible.map((citation) => (
          <li
            key={citation.n}
            className={`citations__item ${active === citation.n ? 'citations__item--active' : ''}`}
          >
            <button
              type="button"
              className="citations__badge"
              onClick={() => onSelect?.(citation)}
            >
              [{citation.n}]
            </button>
            <span className={`citations__kind citations__kind--${citation.kind ?? 'text'}`}>
              {citation.kind === 'kg' ? 'KG' : 'Văn bản'}
            </span>
            <span className="citations__label">
              {citation.kind === 'kg' ? (
                <em>{citation.relation ?? 'quan hệ'}</em>
              ) : (
                <>
                  {citation.title ?? '(không rõ bài)'}
                  {citation.section ? ` › ${citation.section}` : ''}
                </>
              )}
            </span>
            {citation.source_url ? (
              <a
                className="citations__link"
                href={citation.source_url}
                target="_blank"
                rel="noreferrer"
              >
                nguồn
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default CitationPanel;

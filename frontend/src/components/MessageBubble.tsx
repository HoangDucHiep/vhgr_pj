import type { ApiStatus } from '../types';

interface MessageBubbleProps {
  /** Nội dung trả lời. */
  answer: string;
  /** Trạng thái kết quả. */
  status: ApiStatus;
  /** Thời gian xử lý (ms). */
  elapsedMs?: number;
  /** Số lần retry. */
  retries?: number;
}

/** Nhãn tiếng Việt cho từng trạng thái. */
const STATUS_LABELS: Record<ApiStatus, string> = {
  found: 'Tìm thấy trong dữ liệu',
  not_in_data: 'Không có trong dữ liệu',
  error: 'Lỗi xử lý câu hỏi',
};

/**
 * Bong bóng hiển thị một câu trả lời, kèm trạng thái màu theo kết quả.
 *
 * @param props Props của component.
 * @returns Element React.
 */
export function MessageBubble({
  answer,
  status,
  elapsedMs,
  retries,
}: MessageBubbleProps): JSX.Element {
  return (
    <div className={`bubble bubble--${status}`}>
      <div className="bubble__status">
        <span className={`bubble__badge bubble__badge--${status}`}>
          {STATUS_LABELS[status]}
        </span>
        {elapsedMs !== undefined ? (
          <span className="bubble__meta">{elapsedMs} ms</span>
        ) : null}
        {retries !== undefined && retries > 0 ? (
          <span className="bubble__meta">thử lại {retries} lần</span>
        ) : null}
      </div>
      <p className="bubble__answer">{answer}</p>
    </div>
  );
}

export default MessageBubble;

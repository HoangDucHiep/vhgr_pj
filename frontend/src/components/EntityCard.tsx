import { labelNameOf } from '../constants/graph';
import type { EntityDetail } from '../types';

interface EntityCardProps {
  /** Chi tiết entity (null khi chưa chọn). */
  entity: EntityDetail | null;
  /** Đang tải. */
  loading?: boolean;
  /** Callback mở rộng láng giềng. */
  onExpand?: () => void;
  /** Đang mở rộng. */
  expanding?: boolean;
}

/**
 * Thẻ thông tin entity: tên, loại, alias, năm sinh/mất, mô tả, link Wikipedia.
 *
 * @param props Props của component.
 * @returns Element React.
 */
export function EntityCard({
  entity,
  loading = false,
  onExpand,
  expanding = false,
}: EntityCardProps): JSX.Element {
  if (loading) {
    return (
      <aside className="entity-card entity-card--loading">
        <p>Đang tải thông tin thực thể…</p>
      </aside>
    );
  }

  if (!entity) {
    return (
      <aside className="entity-card entity-card--empty">
        <p>Chọn một node trong đồ thị để xem chi tiết.</p>
      </aside>
    );
  }

  const label = entity.labels?.[0] ?? 'Entity';
  const aliases = Array.isArray(entity.aliases) ? entity.aliases : [];

  return (
    <aside className="entity-card">
      <h3 className="entity-card__name">{entity.name}</h3>
      <p className="entity-card__type">{labelNameOf(label)}</p>

      <dl className="entity-card__meta">
        {entity.birth_year || entity.death_year ? (
          <>
            <dt>Năm sinh – mất</dt>
            <dd>
              {entity.birth_year ?? '?'} – {entity.death_year ?? '?'}
            </dd>
          </>
        ) : null}
        {entity.reign_start || entity.reign_end ? (
          <>
            <dt>Năm trị vị</dt>
            <dd>
              {entity.reign_start ?? '?'} – {entity.reign_end ?? '?'}
            </dd>
          </>
        ) : null}
        {entity.wikidata_qid ? (
          <>
            <dt>Wikidata</dt>
            <dd>{entity.wikidata_qid}</dd>
          </>
        ) : null}
        {entity.mention_count ? (
          <>
            <dt>Số lần được nhắc</dt>
            <dd>{entity.mention_count}</dd>
          </>
        ) : null}
      </dl>

      {entity.description ? (
        <p className="entity-card__description">{entity.description}</p>
      ) : null}

      {aliases.length > 0 ? (
        <div className="entity-card__aliases">
          <h4>Tên gọi khác</h4>
          <ul>
            {aliases.slice(0, 8).map((alias) => (
              <li key={alias}>{alias}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="entity-card__actions">
        {onExpand ? (
          <button type="button" onClick={onExpand} disabled={expanding}>
            {expanding ? 'Đang mở rộng…' : 'Mở rộng láng giềng'}
          </button>
        ) : null}
        {entity.wiki_url ? (
          <a href={entity.wiki_url} target="_blank" rel="noopener noreferrer">
            Xem trên Wikipedia
          </a>
        ) : null}
      </div>
    </aside>
  );
}

export default EntityCard;

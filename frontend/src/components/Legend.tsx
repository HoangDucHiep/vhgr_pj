import { LABEL_NAMES } from '../constants/graph';

/**
 * Chú giải màu node theo label.
 *
 * @returns Element React.
 */
export function Legend(): JSX.Element {
  const entries = Object.entries(LABEL_NAMES);
  return (
    <div className="legend">
      <h3 className="legend__title">Chú giải</h3>
      <ul className="legend__list">
        {entries.map(([label, name]) => (
          <li key={label} className="legend__item">
            <span
              className="legend__swatch"
              style={{ backgroundColor: `var(--color-${label.toLowerCase()})` }}
              aria-hidden="true"
            />
            <span>{name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default Legend;

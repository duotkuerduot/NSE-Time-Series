interface Props {
  label: string;
  items: { label: string; value: number }[];
  format: (value: number) => string;
}

/** Signed bars around a zero line, each labelled with its value (colour never carries the
 * meaning on its own). Plain HTML, so the labels keep their size on every screen. */
export function BarChart({ label, items, format }: Props) {
  if (items.length === 0) return null;
  const top = Math.max(0, ...items.map((i) => i.value));
  const bottom = Math.min(0, ...items.map((i) => i.value));
  const span = top - bottom || 1;
  const pct = (v: number) => ((top - v) / span) * 100;
  return (
    <figure className="chart">
      <div className="bars" role="img" aria-label={label} style={{ gridTemplateColumns: `repeat(${items.length}, 1fr)` }}>
        {items.map((item) => {
          const start = pct(Math.max(0, item.value));
          const size = Math.abs(pct(item.value) - pct(0));
          return (
            <div className="bar-col" key={item.label} aria-hidden="true">
              <div className="bar-area">
                <div className="zero" style={{ top: `${pct(0)}%` }} />
                <div
                  className={item.value < 0 ? "bar neg" : "bar"}
                  style={{ top: `${start}%`, height: `max(${size}%, 1px)` }}
                />
                <span
                  className="bar-value"
                  style={item.value < 0 ? { top: `calc(${start + size}% + 2px)` } : { top: `calc(${start}% - 18px)` }}
                >
                  {format(item.value)}
                </span>
              </div>
              <span className="bar-label">{item.label}</span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}

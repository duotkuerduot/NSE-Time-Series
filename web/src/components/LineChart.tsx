import { formatMonthYear, gapStarts } from "../lib/format";

export interface LineSeries {
  label: string;
  values: (number | null)[];
  tone: "ink" | "model" | "muted";
}

interface Range {
  lower: number;
  upper: number;
  point: number;
}

interface Props {
  /** What the chart shows, read by screen readers; the page also states it in text. */
  label: string;
  dates: string[];
  series: LineSeries[];
  /** Sessions to mark with a dot, for example moves left out of modelling. */
  markers?: string[];
  /** A forecast range drawn one step after the last date. */
  range?: Range;
  format: (value: number) => string;
}

// The plot is stretched to its box, so text lives in HTML around it and keeps its size on
// every screen; strokes use non-scaling widths.
const W = 1000;
const H = 200;

/** A small dependency-free line chart. Colour is never the only cue: the legend names each
 * line and the page repeats the key numbers in text. */
export function LineChart({ label, dates, series, markers = [], range, format }: Props) {
  const values = series.flatMap((s) => s.values.filter((v): v is number => v != null && Number.isFinite(v)));
  if (range) values.push(range.lower, range.upper);
  if (dates.length < 2 || values.length === 0) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min || Math.abs(max) || 1) * 0.08;
  const lo = min - pad;
  const hi = max + pad;
  const steps = dates.length - 1 + (range ? 1 : 0);
  const x = (i: number) => (i / steps) * W;
  const y = (v: number) => ((hi - v) / (hi - lo)) * H;
  const dot = (cx: number, cy: number) => `M${cx.toFixed(1)},${cy.toFixed(1)}L${cx.toFixed(1)},${cy.toFixed(1)}`;
  // The line is not drawn across a hole in the data.
  const breaks = new Set(gapStarts(dates));
  const path = (vals: (number | null)[]) => {
    let d = "";
    let pen = false;
    vals.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) {
        pen = false;
        return;
      }
      if (breaks.has(i)) pen = false;
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const index = new Map(dates.map((d, i) => [d, i]));
  const first = series[0];
  const tick = (v: number) => ({ top: `${(y(v) / H) * 100}%` });
  return (
    <figure className="chart">
      <div className="plot" role="img" aria-label={label}>
        <div className="y-labels" aria-hidden="true">
          <span style={tick(max)}>{format(max)}</span>
          <span style={tick(min)}>{format(min)}</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
          <path className="axis" d={`M0,${H}L${W},${H}`} />
          {series.map((s) => (
            <path key={s.label} className={`line ${s.tone}`} d={path(s.values)} />
          ))}
          {first &&
            markers.map((day) => {
              const i = index.get(day);
              const v = i == null ? null : first.values[i];
              return i == null || v == null ? null : <path key={day} className="marker" d={dot(x(i), y(v))} />;
            })}
          {range && (
            <g className="range">
              <path className="band" d={`M${x(steps)},${y(range.upper)}L${x(steps)},${y(range.lower)}`} />
              <path className="point" d={dot(x(steps), y(range.point))} />
            </g>
          )}
        </svg>
        <div className="x-labels" aria-hidden="true">
          <span>{formatMonthYear(dates[0] ?? "")}</span>
          <span>{formatMonthYear(dates[dates.length - 1] ?? "")}</span>
        </div>
      </div>
      <figcaption className="legend">
        {series.map((s) => (
          <span key={s.label} className={`key ${s.tone}`}>
            {s.label}
          </span>
        ))}
        {markers.length > 0 && <span className="key marker">Left out of modelling</span>}
        {range && <span className="key range">Forecast and 80% range</span>}
      </figcaption>
    </figure>
  );
}

import { Navigate, useParams } from "react-router";
import type { StockPrediction } from "../api";
import { NotFoundError } from "../api/client";
import { useHistory, usePrediction, useStock, useStocks } from "../api/hooks";
import { ChangeValue } from "../components/ChangeValue";
import { Section } from "../components/Section";
import { COPY } from "../lib/copy";
import {
  forecastChangeText,
  formatEat,
  formatInt,
  formatKes,
  formatPct,
  formatPrice,
  formatSessionDate,
  formatSignedPrice,
} from "../lib/format";
import { resolveAlias } from "../lib/search";

const unsigned = (fraction: number, digits = 1) =>
  formatPct(Math.abs(fraction), digits).replace("+", "");

function PredictionPanel({ data }: { data: StockPrediction }) {
  if (!data.latest) {
    return <p>{data.unavailable_reason ? COPY.noForecast[data.unavailable_reason] : null}</p>;
  }
  const f = data.latest;
  const t = data.track_record;
  return (
    <div>
      <h2>{COPY.forecastFor(f.target_session)}</h2>
      <p>
        {COPY.forecastClose} <span className="big model">{formatKes(f.predicted_close)}</span>{" "}
        <span className="model">({forecastChangeText(f.predicted_return)})</span>
      </p>
      <p>
        {COPY.expectedRange}:{" "}
        <span className="model">
          {formatKes(f.range.lower)} to {formatPrice(f.range.upper)}
        </span>
      </p>
      {t && (
        <p>
          {COPY.trackRecordSentence(unsigned(t.mae_pct), unsigned(t.naive_mae_pct), unsigned(t.range_coverage, 0), t.basis)}
        </p>
      )}
      <p className="meta">
        {COPY.generated(f.model.label, f.model.version, formatEat(f.generated_at), f.data_through)}
      </p>
      {f.is_late && <p className="meta">{COPY.lateForecast}</p>}
      <p className="meta">{COPY.disclaimer}</p>
    </div>
  );
}

export function StockPage() {
  const ticker = (useParams().ticker ?? "").toUpperCase();
  const stocks = useStocks();
  const stock = useStock(ticker);
  const history = useHistory(ticker, "1y");
  const prediction = usePrediction(ticker);

  if (stock.error instanceof NotFoundError) {
    const current = stocks.data ? resolveAlias(stocks.data.items, ticker) : undefined;
    if (current) return <Navigate to={`/stocks/${current.ticker}`} replace />;
    return (
      <section>
        <h1>{COPY.unknownTicker(ticker)}</h1>
      </section>
    );
  }

  const s = stock.data;
  const h = history.data;
  const rows = prediction.data?.history.slice(0, 10) ?? [];
  return (
    <>
      <section>
        {s ? (
          <>
            <h1>{s.name}</h1>
            <p className="meta">
              {[s.ticker, s.sector, s.segment].filter(Boolean).join(", ")}
            </p>
            {s.latest && (
              <p>
                <span className="big">{formatKes(s.latest.close)}</span>{" "}
                {formatSignedPrice(s.latest.change)} (<ChangeValue fraction={s.latest.change_pct} />){" "}
                <span className="meta">{COPY.closeOn(s.latest.session)}</span>
              </p>
            )}
            <p className="meta">{COPY.officialPrice}</p>
          </>
        ) : (
          <p aria-busy="true" className="meta">…</p>
        )}
      </section>
      <Section title="Price history" isPending={history.isPending} error={history.error} onRetry={() => void history.refetch()}>
        {h && h.dates.length > 0 && (
          <p>
            {h.dates.length} sessions from {formatSessionDate(h.dates[0] ?? "")} to{" "}
            {formatSessionDate(h.dates[h.dates.length - 1] ?? "")}. 52-week range{" "}
            {s?.range_52w ? `${formatPrice(s.range_52w.low)} to ${formatPrice(s.range_52w.high)}` : "n/a"}.{" "}
            <span className="meta">{COPY.chartsLater}</span>
          </p>
        )}
      </Section>
      <Section title="Forecast" isPending={prediction.isPending} error={prediction.error} onRetry={() => void prediction.refetch()}>
        {prediction.data && <PredictionPanel data={prediction.data} />}
      </Section>
      {rows.length > 0 && (
        <Section title={COPY.historyTitle} isPending={false} error={null} onRetry={() => undefined}>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th className="num">Forecast</th>
                <th className="num">Range</th>
                <th className="num">Actual</th>
                <th className="num">Miss</th>
                <th>Direction</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.target_session}>
                  <td>{formatSessionDate(r.target_session, false)}</td>
                  <td className="num model">{formatPrice(r.predicted_close)}</td>
                  <td className="num model">
                    {formatPrice(r.lower)}–{formatPrice(r.upper)}
                  </td>
                  <td className="num">{r.actual_close != null ? formatPrice(r.actual_close) : "—"}</td>
                  <td className="num">{r.error_pct != null ? formatPct(r.error_pct, 1) : "—"}</td>
                  <td>{r.direction ? COPY.direction[r.direction] : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="meta">Volume on the latest session: {s?.latest ? formatInt(s.latest.volume) : "n/a"} shares.</p>
        </Section>
      )}
    </>
  );
}

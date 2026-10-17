import { Navigate, useParams } from "react-router";
import type { Report, StockDetail, StockPrediction } from "../api";
import { NotFoundError } from "../api/client";
import { useHistory, usePrediction, useReport, useStock, useStocks } from "../api/hooks";
import { ChangeValue } from "../components/ChangeValue";
import { LineChart } from "../components/LineChart";
import { Section } from "../components/Section";
import { COPY } from "../lib/copy";
import {
  forecastChangeText,
  formatEat,
  formatInt,
  formatKes,
  formatPct,
  formatPeriod,
  formatPrice,
  formatSessionDate,
  formatShare,
  formatSignedPrice,
  gapStarts,
} from "../lib/format";
import { resolveAlias } from "../lib/search";

function PredictionPanel({
  data,
  report,
  stock,
}: {
  data: StockPrediction;
  report: Report | undefined;
  stock: StockDetail | undefined;
}) {
  if (!data.latest) {
    return (
      <>
        {stock?.status === "delisted" && stock.latest && <p>{COPY.noLongerQuoted(stock.latest.session)}</p>}
        <p>{data.unavailable_reason ? COPY.noForecast[data.unavailable_reason] : null}</p>
      </>
    );
  }
  const f = data.latest;
  const t = data.track_record;
  const holdout = report?.periods.holdout;
  return (
    <div className="forecast">
      <h3 className="label">
        {COPY.forecastFor(f.target_session)}
        {!f.target_from_calendar && <span> · {COPY.nextWeekday}</span>}
      </h3>
      {f.target_in_past && <p className="meta">{COPY.targetInPast(f.data_through)}</p>}
      <p className="forecast-close">
        <span className="meta">{COPY.forecastClose}</span> <span className="big model">{formatKes(f.predicted_close)}</span>{" "}
        <span className="model">({forecastChangeText(f.predicted_return)})</span>
      </p>
      <p className="forecast-range">
        {COPY.expectedRange}:{" "}
        <span className="model">
          {formatKes(f.range.lower)} to {formatPrice(f.range.upper)}
        </span>
      </p>
      {t && (
        <p>
          {holdout && <strong>{COPY.backtestLabel(formatPeriod(holdout.start, holdout.end))}. </strong>}
          {COPY.trackRecordSentence(t.n, formatShare(t.mae_pct, 2), formatShare(t.naive_mae_pct, 2), formatShare(t.range_coverage, 0))}
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
  const report = useReport();

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
  const latest = prediction.data?.latest;
  const moves = (h?.events ?? []).filter((e) => e.type === "large_move").map((e) => e.date);
  const rows = prediction.data?.history.slice(0, 10) ?? [];
  const holdout = report.data?.periods.holdout;
  return (
    <>
      <section className="stock-head">
        {s ? (
          <>
            <p className="label">{[s.ticker, s.sector, s.segment].filter(Boolean).join(", ")}</p>
            <h1>{s.name}</h1>
            {s.latest && (
              <p className="price-line">
                <span className="big">{formatKes(s.latest.close)}</span>{" "}
                <span className="price-change">
                  {formatSignedPrice(s.latest.change)} (<ChangeValue fraction={s.latest.change_pct} />)
                </span>{" "}
                <span className="meta">{COPY.closeOn(s.latest.session)}</span>
              </p>
            )}
            <p className="meta">{COPY.officialPrice}</p>
          </>
        ) : (
          <p aria-busy="true" className="meta">
            …
          </p>
        )}
      </section>
      <div className="stock-grid">
        <Section title="Price history" isPending={history.isPending} error={history.error} onRetry={() => void history.refetch()}>
          {h && h.dates.length > 0 && (
            <>
              <LineChart
                label={`${ticker} official closing price over the past year${latest ? ", with the next-session forecast and its 80% range" : ""}`}
                dates={h.dates}
                series={[{ label: "Official close", values: h.close, tone: "ink" }]}
                markers={moves}
                range={latest ? { lower: latest.range.lower, upper: latest.range.upper, point: latest.predicted_close } : undefined}
                format={formatPrice}
              />
              <p>
                {h.dates.length} sessions from {formatSessionDate(h.dates[0] ?? "")} to{" "}
                {formatSessionDate(h.dates[h.dates.length - 1] ?? "")}. 52-week range{" "}
                {s?.range_52w ? `${formatPrice(s.range_52w.low)} to ${formatPrice(s.range_52w.high)}` : "n/a"}.
              </p>
              {gapStarts(h.dates).map((i) => (
                <p key={h.dates[i]} className="meta">
                  {COPY.dataGap(h.dates[i - 1] ?? "", h.dates[i] ?? "")}
                </p>
              ))}
              {moves.length > 0 && <p className="meta">{COPY.largeMoves(moves.length)}</p>}
            </>
          )}
        </Section>
        <Section title="Forecast" isPending={prediction.isPending} error={prediction.error} onRetry={() => void prediction.refetch()}>
          {prediction.data && <PredictionPanel data={prediction.data} report={report.data} stock={s} />}
        </Section>
      </div>
      {rows.length > 0 && (
        <Section title={COPY.historyTitle} isPending={false} error={null} onRetry={() => undefined}>
          {holdout && <p className="meta">{COPY.backtestLabel(formatPeriod(holdout.start, holdout.end))}. Most recent first.</p>}
          <div className="table-scroll" role="region" aria-label={COPY.historyTitle} tabIndex={0}>
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
          </div>
          <p className="meta">Volume on the latest session: {s?.latest ? formatInt(s.latest.volume) : "n/a"} shares.</p>
        </Section>
      )}
    </>
  );
}

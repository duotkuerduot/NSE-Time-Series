import { Link } from "react-router";
import type { Mover } from "../api";
import { useOverview } from "../api/hooks";
import { ChangeValue } from "../components/ChangeValue";
import { Section } from "../components/Section";
import { StockSearch } from "../components/StockSearch";
import { COPY } from "../lib/copy";
import { formatCompactKes, formatPct, formatPrice, formatSessionDate } from "../lib/format";

function MoversList({ title, movers }: { title: string; movers: Mover[] }) {
  return (
    <div>
      <h2>{title}</h2>
      <table>
        <tbody>
          {movers.map((m) => (
            <tr key={m.ticker}>
              <td>
                <Link to={`/stocks/${m.ticker}`}>{m.ticker}</Link>
              </td>
              <td>{m.name}</td>
              <td className="num">{formatPrice(m.close)}</td>
              <td className="num">
                <ChangeValue fraction={m.change_pct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function HomePage() {
  const overview = useOverview();
  const data = overview.data;
  const retry = () => void overview.refetch();
  const trend = data?.charts.index_trend;
  const breadth = data?.charts.breadth;
  const record = data?.charts.track_record;
  const last = <T,>(values: T[] | undefined) => (values && values.length ? values[values.length - 1] : undefined);

  return (
    <>
      <section>
        <StockSearch autoFocus asHeading />
        {data && (
          <p>
            {data.summary.nasi && (
              <>
                NASI {formatPrice(data.summary.nasi.level)} <ChangeValue fraction={data.summary.nasi.change_pct} />
                {"  "}
              </>
            )}
            {data.summary.nse20 && (
              <>
                NSE 20 {formatPrice(data.summary.nse20.level)} <ChangeValue fraction={data.summary.nse20.change_pct} />
                {"  "}
              </>
            )}
            {data.summary.advancers} up, {data.summary.decliners} down, {data.summary.unchanged} flat. Turnover{" "}
            {formatCompactKes(data.summary.turnover_kes)}
            {data.summary.turnover_vs_20d != null && ` (${data.summary.turnover_vs_20d.toFixed(1)}× 20-day average)`}
          </p>
        )}
      </section>
      <Section title="Market movers" isPending={overview.isPending} error={overview.error} onRetry={retry}>
        {data && (
          <>
            <div className="grid2">
              <MoversList title={COPY.gainers} movers={data.movers.gainers} />
              <MoversList title={COPY.losers} movers={data.movers.losers} />
            </div>
            <p className="meta">{COPY.moversFilter(formatCompactKes(data.movers.min_turnover_kes))}</p>
          </>
        )}
      </Section>
      <Section title={COPY.indexTrend} isPending={overview.isPending} error={overview.error} onRetry={retry}>
        {trend && trend.dates.length > 1 && (
          <p>
            {trend.index} moved from {formatPrice(trend.level[0] ?? 0)} on {formatSessionDate(trend.dates[0] ?? "")} to{" "}
            {formatPrice(last(trend.level) ?? 0)} on {formatSessionDate(last(trend.dates) ?? "")}.{" "}
            <span className="meta">{COPY.chartsLater}</span>
          </p>
        )}
      </Section>
      <div className="grid2">
        <Section title={COPY.breadth} isPending={overview.isPending} error={overview.error} onRetry={retry}>
          {breadth && (
            <p>
              Latest session: {last(breadth.advancers)} advancers, {last(breadth.decliners)} decliners,{" "}
              {last(breadth.unchanged)} unchanged.
            </p>
          )}
        </Section>
        <Section title={COPY.trackRecord} isPending={overview.isPending} error={overview.error} onRetry={retry}>
          {record && record.dates.length > 0 && (
            <p>
              60-session average miss: <span className="model">{formatPct(last(record.model_mae_pct_60) ?? 0).replace("+", "")}</span>{" "}
              for the model ({last(record.model_label)}, {last(record.basis) === "live" ? "live" : "simulated"}), against{" "}
              {formatPct(last(record.naive_mae_pct_60) ?? 0).replace("+", "")} for a no-change guess.
            </p>
          )}
        </Section>
      </div>
    </>
  );
}

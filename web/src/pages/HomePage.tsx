import { Link } from "react-router";
import type { Mover } from "../api";
import { useOverview } from "../api/hooks";
import { ChangeValue } from "../components/ChangeValue";
import { LineChart } from "../components/LineChart";
import { Section } from "../components/Section";
import { StockSearch } from "../components/StockSearch";
import { COPY } from "../lib/copy";
import { formatCompactKes, formatPrice, formatShare } from "../lib/format";

function MoversList({ title, movers }: { title: string; movers: Mover[] }) {
  return (
    <div>
      <h3>{title}</h3>
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

const last = <T,>(values: T[] | undefined) => (values && values.length ? values[values.length - 1] : undefined);

export function HomePage() {
  const overview = useOverview();
  const data = overview.data;
  const retry = () => void overview.refetch();
  const trend = data?.charts.index_trend;
  const breadth = data?.charts.breadth;
  const record = data?.charts.track_record;
  // When the champion is the no-change guess, its errors are the no-change errors.
  const noChange = Boolean(record && record.model_mae_pct_60.every((v, i) => v === record.naive_mae_pct_60[i]));

  return (
    <>
      <section className="hero">
        <StockSearch autoFocus asHeading />
        {data && (
          <p className="market-line">
            {data.summary.nasi && (
              <span>
                NASI {formatPrice(data.summary.nasi.level)} <ChangeValue fraction={data.summary.nasi.change_pct} />{" "}
              </span>
            )}
            {data.summary.nse20 && (
              <span>
                NSE 20 {formatPrice(data.summary.nse20.level)} <ChangeValue fraction={data.summary.nse20.change_pct} />{" "}
              </span>
            )}
            <span>
              {data.summary.advancers} up, {data.summary.decliners} down, {data.summary.unchanged} flat.{" "}
            </span>
            <span>
              Turnover {formatCompactKes(data.summary.turnover_kes)}
              {data.summary.turnover_vs_20d != null && ` (${data.summary.turnover_vs_20d.toFixed(1)}× 20-day average)`}
            </span>
          </p>
        )}
      </section>
      <Section title="Market movers" isPending={overview.isPending} error={overview.error} onRetry={retry}>
        {data && (
          <>
            <p className="meta">{COPY.moversOn(data.session)}</p>
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
          <>
            <LineChart
              label={`${trend.index} level over the past year`}
              dates={trend.dates}
              series={[{ label: trend.index, values: trend.level, tone: "ink" }]}
              format={formatPrice}
            />
            <p>
              {COPY.indexMoved(
                trend.index,
                formatPrice(trend.level[0] ?? 0),
                trend.dates[0] ?? "",
                formatPrice(last(trend.level) ?? 0),
                last(trend.dates) ?? "",
              )}
            </p>
          </>
        )}
      </Section>
      <div className="grid2">
        <Section title={COPY.breadth} isPending={overview.isPending} error={overview.error} onRetry={retry}>
          {breadth && breadth.dates.length > 0 && (
            <p>{COPY.breadthLatest(last(breadth.advancers) ?? 0, last(breadth.decliners) ?? 0, last(breadth.unchanged) ?? 0)}</p>
          )}
        </Section>
        <Section title={COPY.trackRecord} isPending={overview.isPending} error={overview.error} onRetry={retry}>
          {record && record.dates.length > 0 && (
            <>
              <LineChart
                label="Rolling 60-session average miss of the model and of a no-change guess"
                dates={record.dates}
                series={[
                  ...(noChange
                    ? []
                    : [{ label: last(record.model_label) ?? "Model", values: record.model_mae_pct_60, tone: "model" as const }]),
                  { label: "No-change guess", values: record.naive_mae_pct_60, tone: "muted" },
                ]}
                format={(v) => formatShare(v, 2)}
              />
              <p>
                {noChange
                  ? COPY.trackRecordNoChange(formatShare(last(record.naive_mae_pct_60) ?? 0, 2))
                  : COPY.trackRecordHome(
                      formatShare(last(record.model_mae_pct_60) ?? 0, 2),
                      formatShare(last(record.naive_mae_pct_60) ?? 0, 2),
                      last(record.model_label) ?? "model",
                    )}
              </p>
            </>
          )}
        </Section>
      </div>
    </>
  );
}

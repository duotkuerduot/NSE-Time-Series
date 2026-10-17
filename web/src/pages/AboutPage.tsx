import type { Report, ReportModel, ReportScores } from "../api";
import { useReport, useSite, useStatus } from "../api/hooks";
import { BarChart } from "../components/BarChart";
import { Section } from "../components/Section";
import { COPY } from "../lib/copy";
import { formatInt, formatPct, formatPeriod, formatSessionDate, formatShare } from "../lib/format";

const skill = (value: number | null | undefined) => (value == null ? "n/a" : formatPct(value, 2));
const share = (value: number | null | undefined) => (value == null ? "n/a" : formatShare(value, 1));
const pValue = (value: number | null | undefined) => (value == null ? "n/a" : value.toFixed(3));

/** The model whose skill by year is charted: the champion, or the strongest ML candidate when
 * the champion is the no-change guess (whose skill is zero by definition). */
function chartedModel(report: Report): ReportModel | undefined {
  const champion = report.models.find((m) => m.is_champion);
  if (champion && champion.model_id !== "B0") return champion;
  const ml = report.models.filter((m) => !m.model_id.startsWith("B"));
  return ml.sort((a, b) => b.selection.skill - a.selection.skill)[0];
}

function Headline({ report }: { report: Report }) {
  const period = formatPeriod(report.periods.holdout.start, report.periods.holdout.end);
  const h: ReportScores | null = report.headline;
  if (report.champion.model_id !== "B0" && h) {
    return (
      <p className="lead">
        On data the models never saw during development ({period}), the champion, <strong>{report.champion.label}</strong>,
        missed by {share(h.mae)} of price on average against {share(h.mae_no_change)} for a no-change guess: a skill of{" "}
        <strong>{skill(h.skill)}</strong> (Diebold–Mariano p = {pValue(h.dm_p)}) across {h.securities} liquid NSE stocks. The
        actual close fell inside its 80% range {share(h.coverage)} of the time.
      </p>
    );
  }
  const best = chartedModel(report);
  return (
    <p className="lead">
      On data the models never saw during development ({period}), no model beat the no-change guess by the margins the
      gates require, so the forecasts shown are the no-change guess itself, and the app says so. On this data that is the
      honest result.
      {best?.holdout && (
        <>
          {" "}
          The strongest machine-learning candidate, {best.label}, had a holdout skill of {skill(best.holdout.skill)}.
        </>
      )}
      {h?.coverage != null && <> The actual close fell inside the 80% range {share(h.coverage)} of the time.</>}
    </p>
  );
}

function GateTable({ report }: { report: Report }) {
  return (
    <>
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th className="num">Selection skill</th>
            <th className="num">DM p</th>
            <th className="num">Holdout skill</th>
            <th className="num">In 80% range</th>
            <th>Gates</th>
          </tr>
        </thead>
        <tbody>
          {report.models.map((m) => {
            const failed = m.gates.filter((g) => !g.passed);
            return (
              <tr key={m.model_id}>
                <td>
                  {m.label}
                  {m.is_champion && <strong> (champion)</strong>}
                </td>
                <td className="num">{skill(m.selection.skill)}</td>
                <td className="num">{m.model_id === "B0" ? "—" : pValue(m.selection.dm_p)}</td>
                <td className="num">{skill(m.holdout?.skill)}</td>
                <td className="num">{share(m.selection.coverage)}</td>
                <td>
                  {m.gates.length === 0
                    ? "Reference"
                    : failed.length === 0
                      ? `All ${m.gates.length} passed`
                      : `${m.gates.length - failed.length} of ${m.gates.length} passed`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="meta">
        Skill is 1 − (model’s average miss ÷ no-change guess’s average miss), measured on the selection period (
        {formatPeriod(report.periods.selection.start, report.periods.selection.end)}) unless marked holdout. Positive means the
        model missed by less. It is never an “accuracy” percentage of the price.
      </p>
      {report.models
        .filter((m) => m.gates.length > 0)
        .map((m) => (
          <details key={m.model_id}>
            <summary>Gate details: {m.label}</summary>
            <ul>
              {m.gates.map((g) => (
                <li key={g.id}>
                  {g.passed ? "Passed" : "Failed"}: {g.name}. <span className="meta">{g.detail}</span>
                </li>
              ))}
            </ul>
          </details>
        ))}
    </>
  );
}

function Results({ report }: { report: Report }) {
  const charted = chartedModel(report);
  const years = charted
    ? Object.entries(charted.skill_by_year)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([label, value]) => ({ label, value }))
    : [];
  const a = report.data_audit;
  const u = report.universe;
  return (
    <>
      <Headline report={report} />
      <h3>Every model, through the same gates</h3>
      <GateTable report={report} />
      {charted && years.length > 0 && (
        <>
          <h3>Skill by year: {charted.label}</h3>
          <BarChart
            label={`${charted.label}: skill against the no-change guess, by year`}
            items={years}
            format={(v) => formatPct(v, 1)}
          />
          <p className="meta">
            Years up to {report.periods.selection.end.slice(0, 4)} are the selection period; later years are the holdout.
          </p>
        </>
      )}
      <h3>Forecast universe and data</h3>
      <p>
        Forecasts cover ordinary shares that traded on at least 80% of the last 250 sessions with enough turnover and history:
        between {u.min} and {u.max} stocks across the {report.refit} refits (median {u.median}), and {u.at_last_session} at the
        last session.
      </p>
      <ul>
        <li>{formatInt(a.sessions)} trading sessions and {a.securities} securities after cleaning</li>
        <li>
          {a.corrections_applied} documented corrections ({formatInt(a.rows_corrected)} rows re-dated) and{" "}
          {formatInt(a.duplicates_dropped)} duplicate rows dropped
        </li>
        <li>{a.missing_sessions} trading days with no data, never filled in</li>
        <li>{formatInt(a.events_excluded)} moves beyond the ±10% daily band left out of modelling</li>
        <li>{formatInt(a.carried_forward_rows)} untraded stock-days carried forward at the last price</li>
      </ul>
      <p className="meta">
        Profile: {report.profile}. Results from the run that produced this release, on{" "}
        {report.dataset.title} ({formatSessionDate(report.dataset.first_session)} to{" "}
        {formatSessionDate(report.dataset.last_session)}).
      </p>
    </>
  );
}

export function AboutPage() {
  const report = useReport();
  const site = useSite();
  const status = useStatus();
  const dataset = status.data?.dataset;
  return (
    <>
      <section>
        <h1>How the forecasts work</h1>
        <p>
          NSE Forecast estimates the next session’s official closing price for the most actively traded stocks on the Nairobi
          Securities Exchange, with an 80% expected range. Everything runs on your own computer: one command reads the
          historical dataset, checks and cleans it, trains and tests the models, picks a champion by fixed rules and serves
          this app.
        </p>
      </section>
      <Section title="Results" isPending={report.isPending} error={report.error} onRetry={() => void report.refetch()}>
        {report.data && <Results report={report.data} />}
      </Section>
      <section>
        <h2>What the numbers mean</h2>
        <p>
          The official closing price is the volume-weighted average price of the whole session. Every forecast is compared
          with a no-change guess: tomorrow’s close equals today’s. Skill is how much smaller the model’s average miss is than
          the guess’s. The 80% expected range is where the actual close should fall about 8 times in 10; its measured
          coverage is shown next to it. Every number on this page is out of sample.
        </p>
        <h2>Why the no-change guess is the number to beat</h2>
        <p>
          A no-change guess usually misses by only 1–2% of the price, so a forecast can look accurate without knowing
          anything. On the NSE the official close is a session average and many stocks trade thinly, so returns carry a
          mechanical carry-over from one day to the next. A per-stock AR(1) model measures that effect, and a model has to
          beat it, not just the no-change guess, to show it adds something.
        </p>
        <h2>Method</h2>
        <ol>
          <li>Acquire: copy the dataset files and record their SHA-256 hashes.</li>
          <li>
            Ingest: fix documented defects, check data quality, and build one row per stock and trading session. Days with
            no data are never filled in.
          </li>
          <li>
            Features: returns, trend, volatility, liquidity and market context, each computed only from data up to the
            forecast day. Windows that span a gap or a move beyond the ±10% band are left out.
          </li>
          <li>
            Train and evaluate: four baselines and the machine-learning candidates are refitted through time (walk-forward)
            and scored on a selection period; a later holdout period only confirms the result.
          </li>
          <li>
            Select: a champion must pass every gate, including significance tests against the no-change guess and the best
            simple baseline; otherwise a baseline is used.
          </li>
          <li>Predict and publish: the champion forecasts the next session and this app reads the results.</li>
        </ol>
        <h2>Limitations</h2>
        <ul>
          <li>
            Historical only: the forecast is for the session after the dataset ends, which is in the past. The app shows the
            method and its measured skill; it does not follow the market live.
          </li>
          <li>
            The dataset has gaps (July to December 2020, November to December 2025), duplicates and misdated rows. They are
            handled by documented rules, but unknown errors may remain.
          </li>
          <li>
            No corporate-action adjustment: sessions with moves beyond the price band are left out of modelling, which also
            removes some genuine large moves.
          </li>
          <li>
            Next-session changes are hard to predict. Any skill is likely small, and part of it comes from the mechanics of
            average-price closes and thin trading.
          </li>
          <li>Past results do not predict future results. {COPY.disclaimer}</li>
        </ul>
        <h2>Data</h2>
        {dataset?.citation ? (
          <p>
            {dataset.citation}
            {dataset.url && (
              <>
                {" "}
                (<a href={dataset.url}>{dataset.url}</a>)
              </>
            )}
            . {dataset.licence ? `Licence: ${dataset.licence}.` : "The licence is not recorded in this copy; use the data for personal research."}
          </p>
        ) : (
          dataset && <p>{dataset.title}.</p>
        )}
        <p>{COPY.dataOrigin}</p>
      </section>
      <section>
        <h2>Contact</h2>
        {site.data ? (
          <>
            <p>
              {site.data.tagline || COPY.builtBy(site.data.owner_name)}. {COPY.contactInvite}
            </p>
            <ul className="links">
              {site.data.links.map((link) => (
                <li key={link.url}>
                  <a href={link.url}>{link.label}</a>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="meta">…</p>
        )}
      </section>
    </>
  );
}

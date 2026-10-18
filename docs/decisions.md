# Decisions

The design decisions behind NSE Forecast and the reason for each, grouped by area. Earlier
decision records for a hosted design that NSE Forecast replaced are kept in
[archive/](archive/README.md).

## Product shape

**A local tool, run with one command.** Anyone clones the public repository and runs
`uv run nsefc run`. The tool reads the dataset files on the user's machine, builds a clean
panel, evaluates the models walk-forward, chooses a champion with fixed gates, publishes
static JSON and serves the app on `127.0.0.1`. Nothing is hosted, scheduled, downloaded or
uploaded, and nothing derived from the data is committed.
*Why:* a cloneable demonstration costs nothing to run, needs no accounts, keys or secrets, and
publishes no derived market data. It replaces a hosted design with nightly scraping, cloud
storage and a public API, whose sources needed licences and whose every published number
raised redistribution questions. *Consequence:* results are historical, and the forecast is
for the session after the dataset ends.

**The dataset is downloaded by hand into `data/source/`, never committed and never fetched.**
The folder is in the repository with a README, but its contents are git-ignored. There is no
download client and no network access at run time.
*Why:* the files are third-party data whose licence is not recorded, so the repository does
not redistribute them, and without a download client the tool stays offline and simple. A
fresh clone without the files stops with exit code 10 and explains where to get them;
`--sample` runs everything on synthetic data, which is also what CI uses.

**No database.** Parquet tables (pandas and pyarrow) and JSON files under `data/`.
*Why:* the data is small, and plain files are easy to inspect and need no service.

**The web app is built ahead of time and committed inside the package.**
*Why:* people who clone the repository need neither Node.js nor pnpm. A source hash checked
in CI keeps the committed build in step with its sources.

**A standard-library HTTP server bound to `127.0.0.1`.**
*Why:* serving a few static files locally needs no extra dependency, and nothing listens
beyond the user's own machine.

**The champion is chosen automatically on every run, by gates fixed in advance.**
*Why:* a promotion review only makes sense for a production service. Fixed gates make the
choice reproducible, and a baseline, including the no-change guess, can win; the app then
says so.

## Data

**No back-adjustment for corporate actions.** A move beyond the ±10% price band plus 0.5
percentage points is an event, excluded from labels and from feature windows.
*Why:* there is no reviewed corporate-actions source. The rule is simple and honest; its cost,
dropping some genuine large moves, is a documented limitation.

**Corrections are keyed to a file's SHA-256 and a line range.** A rule that matches no rows,
or that would create a duplicate key, stops the ingest. The synthetic sample has one planted
misdated block, fixed by rule SAMPLE-01.
*Why:* a correction can never apply silently to a different file, and the sample exercises
the same machinery as the real data.

**CSV files are hashed and copied with Windows line endings converted to LF.**
*Why:* downloads and checkouts can differ only in line endings. Without this, the same file
would have two SHA-256 values, the corrections keyed by hash would not apply, and ingest would
stop on the defects they fix.

**Raw copies sit flat in their folder under their own names**, with a short hash prefix only
if two names clash; the manifest records each file's original path.
*Why:* the source collections' nested folder names would push temporary paths beyond the
260-character limit of a typical Windows clone.

**Index levels go to their own table, and bars carry an `is_event` flag.**
*Why:* index rows are not securities, and downstream stages read one flag instead of
recomputing the band rule.

**Each row's year is checked against its file's name (DAT-03), and imports may only add
sessions after the dataset's last session (IMP-01).**
*Why:* the files state the period they cover, which is how the 2015-dated block in the 2017
file was found, and an import that overlapped the dataset would mix two sources in one
session.

**High and low are null on days without trades.**
*Why:* the source repeats stale quotes on untraded days, which would distort the day-range
feature.

**Isolated weekdays without data stay missing sessions and trigger the gap guard.**
*Why:* it is the documented rule, and filling or guessing would hide data problems. It costs
data: the 26 isolated missing weekdays and the two long gaps exclude 1,128 of 4,682 sessions
from modelling. A weekday confirmed as a market closure can be recorded as a holiday in
`config/calendar/nse_holidays.yaml`, which restores the rows around it.

**The attribution shown to users is read from `reference/mendeley.yaml` at publish time.**
*Why:* filling in the licence then takes effect on the next run without copying or
retraining anything.

## Modelling and evaluation

**The default profile uses frozen hyperparameters; only `--profile full` tunes.** The frozen
values are the initial ones in `config/models/*.yaml`, fixed before any result was seen.
Values tuned on the tuning period with `nsefc dev tune` are recorded there, commented out, and
are not active.
*Why:* a fast first run and a holdout that no choice has touched. With the tuned values,
LightGBM's directional calls on the holdout come within 0.2 percentage points of the
plausibility tripwire, and its selection-period skill is lower than with the frozen values.
No gate threshold has been changed after seeing results.

**The forecast universe needs a median daily value traded of KES 150,000.**
*Why:* KES 1 million left only 8 to 15 securities. 150,000 gives 16 to 31 (median 20) across
the refits, and it was chosen on universe size before any model result was seen. The dataset
has no turnover column, so value traded is median volume × close.

**One pooled model across stocks, not one per ticker.**
*Why:* pooling gives a model far more rows than any single stock has, and the features and the
target are scale-free returns and ratios, so one model can serve every stock.

**The AR(1) baseline is fitted by least absolute deviations,** per stock over the trailing
500 sessions, with at least 50 return pairs.
*Why:* champions are judged on the average absolute miss, so the baseline they must beat is
fitted on the same loss.

**Huber regression is a candidate of its own,** in the same pipeline as Ridge.
*Why:* it gives the linear family a robust loss that matches the median target.

**The walk-forward starts 250 sessions before the selection period,** and those predictions
only calibrate the ranges.
*Why:* the rolling conformal window then has 250 sessions of out-of-sample scores on the first
selection day, so selection-period coverage is honest from the start.

**LightGBM and CatBoost early-stop on the last 10% of sessions in each training window** and
keep the best iteration, without a refit on the full window.
*Why:* one fit per refit keeps the default run fast, and the validation slice still ends
before the test window.

**Exponentially weighted volatility uses renormalised weights over the 60-session window,
and rolling statistics are computed window by window.**
*Why:* an unbounded average would reach back past events and missing sessions, and pandas'
running sums carry rounding from earlier rows of other securities. Bounded, window-by-window
statistics make features exactly invariant to truncation and independent across securities.

**The volume ratio feature is `ln((1 + volume) / (1 + 20-session median volume))`.**
*Why:* it is bounded and defined when the median is zero, which is common for thin stocks.

**Market features use all ordinary shares, not only the forecast universe.**
*Why:* they then do not depend on a membership rule that changes at each refit, and every
stock's features share one market series.

**G-DIR and G-BASE are precise tests.** G-DIR is a one-sided z-test (α = 0.05) of a model's
directional calls against the best trivial sign rule; G-BASE needs a paired one-sided
Diebold–Mariano p below 0.10 against the best of B1 to B3, or the simpler model wins. The
"sign of the last return" rule is scored only where it makes a call, as models are.
*Why:* "not significantly worse" and "not significantly better" need a definition that can be
tested, and counting the rule's non-calls as misses would understate it and favour the
models.

**A universe stock whose 60-session window contains an event or a missing session gets no
forecast,** with the reason `RECENT_PRICE_EVENT` (or `INSUFFICIENT_HISTORY`).
*Why:* the forecast obeys the same gap guard as training, and the reason tells the user why.

**Model files are pickle-based (joblib), loaded only when produced locally and hash-checked.**
*Why:* scikit-learn pipelines are saved this way. The loader refuses any file whose SHA-256
does not match its sidecar, and the tool never loads model files from elsewhere.

## Pipeline, publishing and the app

**Each stage's fingerprint covers the source code it depends on.**
*Why:* an updated clone never reuses results computed by older code, and a change to
publishing code republishes without retraining.

**`predict` and `publish` refuse outputs computed from older data, settings or code.**
*Why:* running stage commands out of order (for example `import`, `ingest`, then `predict`)
would otherwise reuse a stale forecast or mix releases.

**The publish fingerprint includes the local date.**
*Why:* whether the forecast's target date is in the past depends on the day, so a run on a
later day republishes instead of reusing a stale flag.

**Publishing keeps the previous release folder beside the new one.**
*Why:* a page that is already open keeps reading a complete release until it fetches the new
`status.json`.

**API contract v1.1 adds what the local app shows:** the data mode, the dataset's
attribution, the contract version, the target date's provenance, the `large_move` event type,
the `RECENT_PRICE_EVENT` reason, `report.json` and `site.json`. `stale_after` is null,
because historical data is never late.
*Why:* each addition is something a page shows, and the changes are backwards compatible.

**Prices in `prediction.json` are derived from the rounded last close.**
*Why:* every published forecast then validates against the contract whatever the source's
precision.

**Gates carry plain-language names, and the app never shows the raw gate ids.**
*Why:* the id G-HOLD would put the banned word "hold" on screen.

**Module boundaries are import-linter contracts.**
*Why:* a leak (features importing targets) or a dependency cycle fails CI instead of slipping
through review.

**A calm, typographic design.** Cream, near-black and deep blue design tokens, Inter Tight
ExtraBold for headlines and the two hero numbers, Inter for everything else, self-hosted under
the SIL Open Font License.
*Why:* the content is numbers and short explanations, so large type, space and a palette in
which every colour has one meaning carry it best; self-hosted fonts keep the app offline.
[architecture.md](architecture.md#design) has the tokens and their measured contrast.

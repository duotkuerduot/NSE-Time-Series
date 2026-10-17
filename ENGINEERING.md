# NSE Forecast: a local, one-command forecasting tool for the Nairobi Securities Exchange

Engineering design document (`ENGINEERING.md`)

| | |
|---|---|
| Status | 2.1, replaces Draft 1.0 (7 Oct 2026). 2.1 records the owner's data decision (D-10) and the implementation decisions in §22 |
| Date | 17 October 2026 |
| Owner | @duotkuerduot |
| Repository | github.com/duotkuerduot/NSE-Time-Series (public) |
| Audience | The agent or engineer implementing this, and anyone who clones the repository |

**What changed from Draft 1.0.** Draft 1.0 described a hosted production platform: daily automated scraping, Cloudflare R2, GitHub Actions scheduling, a CDN-served API, a model registry with pull-request promotion, alerting and a legal gate before public launch. Version 2.0 removes all of that. The product is now a local tool: anyone clones the public repository, runs one command, and the tool reads the historical dataset that ships in the repository's `NSE Data/` folder, trains and evaluates the models, produces forecasts and opens the results in a browser on their own machine. Nothing is hosted, scheduled, downloaded or uploaded. The ML methodology (target, baselines, leakage rules, walk-forward evaluation, honest metrics, conformal intervals) is kept, because it is what makes the result credible.

**What changed in 2.1.** 2.0 planned to download the dataset from Mendeley Data at runtime and keep it out of the repository. The owner decided instead (D-10) that the tool uses the copy already committed in `NSE Data/` and cites it as Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026", Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1. There is no download client. §1, §3, §4.3, §5, §21 and §22 are updated accordingly; superseded 2.0 text is removed rather than struck through. On 17 October 2026 the owner's 2026 files, which run to 30 June 2026, were added to `NSE Data/`, and the numbers in this document were refreshed from a run on the full folder.

**Conventions.** MUST, SHOULD and MAY have their RFC 2119 meanings. **T** is the origin session, the latest session whose data is used. **T+1** is the next NSE trading session after T, from the calendar, not the next calendar day. Session dates are plain local dates in Africa/Nairobi. Prices are in KES. Items marked *(verify)* MUST be confirmed during implementation before code depends on them.

---

## 0. Instructions for the implementing agent

Read this section first and follow it throughout.

1. **Build in the phase order of §20.** Each phase ends with acceptance checks. Do not start a phase until the previous phase's checks pass. Run the full test suite at the end of every phase.
2. **Reuse Phase 0 work.** The repository already contains a working `nsefc` package and web app from Draft 1.0's Phase 0 (see `docs/archive/phase-0-status.md`). §4 says exactly what to keep, change and delete. Do not rewrite working, tested modules for style.
3. **Never guess the dataset.** Phase 1 inspected the files in `NSE Data/` and recorded their names, formats, columns, date range and defects in `docs/data/mendeley-dataset.md` before any parser was written. Where this document once assumed a column or format, the finding is recorded there.
4. **No network access at runtime (D-10).** The tool reads the committed `NSE Data/` folder; nothing is downloaded. `uv` needs the internet once, to install Python and the packages. CI and tests use the synthetic sample (§16.3).
5. **Keep it simple.** If a design question is not answered here, choose the simplest option that keeps results honest, and record the decision in §22 of this file (one short paragraph each).
6. **Stop and ask the owner** before: rewriting git history, deleting anything under `NSE Data/`, adding a dependency that needs a compiler or a system package, or changing a gate threshold in §11.4 after seeing results.
7. **Cross-platform.** The owner and most people who clone the repository use Windows. Everything MUST work on Windows 10/11, macOS and Linux with only `git` and `uv` installed. No `make`, no shell scripts in the main path, no Node.js required to run the tool, `pathlib` everywhere.
8. **Environment notes from Phase 0** (if running on the owner's device): device commands cannot leave background processes running, so run `uv` steps in the foreground; keep virtual environments out of the owner's folder by working on a scratch copy under `$HOME`.

---

## 1. Summary

### 1.1 What it is

A command-line tool and local web app. One command, run in a fresh clone:

```text
uv run nsefc run
```

does everything:

1. **Acquire.** Copies the NSE daily price files from the repository's `NSE Data/` folder (Wanjawa 2026, Mendeley Data, doi: 10.17632/hvmhnp7f9r.1) into `data/raw/`, recording each file's SHA-256 in a manifest.
2. **Ingest.** Normalises it into a clean canonical panel in `data/canonical/`, applying data-quality checks and documented corrections.
3. **Train and evaluate.** Builds leakage-safe features, trains baselines and two ML candidates, evaluates them walk-forward, and selects a champion through fixed gates.
4. **Predict.** Forecasts the next session's close, with an 80% expected range, for every stock in the forecast universe.
5. **Publish.** Writes the results as static JSON files in `data/api/v1/`.
6. **Serve.** Starts a local web server and opens the existing React frontend in the browser.

A second run reuses everything already copied and computed, and only redoes stages whose inputs changed.

### 1.2 The claim the project makes

Next-session price forecasting is a low-signal problem. Predicting tomorrow's price *level* looks very accurate with no skill at all, because a "no change" guess usually misses by only 1–2%. The project therefore never claims to be "98% accurate". It claims, and shows on screen and in the README, something like:

> On data the models never saw during development (2023 to the end of the dataset), the champion reduced average forecast error by X% compared with a no-change guess across N liquid NSE stocks, and the actual close fell inside its 80% range Y% of the time.

If no ML model beats the baselines, the tool says so and ships the best baseline. That is a correct outcome, not a failure.

### 1.3 Decisions at a glance

| Area | Decision |
|---|---|
| Shape | One Python package (`nsefc`) plus the existing React app, prebuilt and shipped inside the package |
| Entry point | `uv run nsefc run`; individual stages also available as subcommands |
| Data source | The committed `NSE Data/` folder, cited as Wanjawa, Barack (2026), Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1 (D-10); no download |
| Optional extra data | `nsefc import <csv>` lets a user add more recent sessions they collected themselves |
| Storage | Local files only: raw copies, Parquet tables and JSON, under `data/` (git-ignored) |
| Database | None. pandas and pyarrow over Parquet |
| Target | Next-session simple return; price derived from it |
| Baselines | No change, drift, 5-session moving average, per-stock AR(1) |
| Candidates | Ridge and Huber regression, LightGBM (default); CatBoost only in the `full` profile |
| Evaluation | Walk-forward with periodic refits; a holdout period never used for development |
| Primary metric | MAE skill against no-change, with a Diebold–Mariano significance test |
| Intervals | Volatility-scaled split conformal, 80% level |
| Champion | Chosen automatically by fixed gates on every run; falls back to a baseline |
| Serving | Python standard-library HTTP server; frontend reads `/api/v1/*.json` |
| CI | GitHub Actions for tests only, on a synthetic sample dataset; no data, no secrets |
| Cost | $0. No cloud services, no accounts, no API keys |

---

## 2. Goals and non-goals

### 2.1 Goals

| ID | Goal |
|---|---|
| G-1 | **One command.** A user with `git` and `uv` gets results in the browser with `uv run nsefc run`, on Windows, macOS or Linux. |
| G-2 | **Fast enough to try.** The default run finishes in under 20 minutes on a typical laptop (4 cores, 8 GB RAM); a repeat run with no changes finishes in under 1 minute before serving. |
| G-3 | **Honest results.** Every performance number is out-of-sample and compared with a no-change guess. |
| G-4 | **Leakage-proof and reproducible.** The same dataset files and code produce the same predictions on any machine, within numerical tolerance. |
| G-5 | **Traceable data.** Every canonical row traces to a source file with a recorded SHA-256, and every correction is documented. |
| G-6 | **Impressive to read.** The README and the app's About page explain the method and results clearly enough that a reader understands what was built and how to contact the owner. |

### 2.2 Non-goals

Automatic daily scraping or scheduling. Downloading data at runtime (D-10). Cloud storage, hosting, CDNs or deployment. Any account, key or secret. Live tracking of predictions against real future sessions (see §22.2). Weekly or multi-session horizons (the schema is horizon-ready; the feature is not built). Buy, sell or hold recommendations. Agents or LLM features. Deep learning. User accounts. Mobile apps. Committing derived data (anything under `data/`) to the repository.

---

## 3. The one-command experience

### 3.1 Commands

| Command | What it does |
|---|---|
| `uv run nsefc run` | All stages, then serve. The default |
| `uv run nsefc run --no-serve` | All stages, then exit (used by CI) |
| `uv run nsefc run --profile full` | Adds hyperparameter tuning, monthly refits and CatBoost; slower (§11.1) |
| `uv run nsefc run --sample` | Uses the synthetic sample dataset instead of `NSE Data/`; for a two-minute trial and for CI |
| `uv run nsefc run --source-dir PATH` | Reads dataset files in the same format from PATH instead of `NSE Data/` |
| `uv run nsefc run --force` | Recomputes every stage even if cached |
| `uv run nsefc acquire` / `ingest` / `train` / `predict` / `publish` / `serve` | Individual stages, in that order; each fails with a clear message if its inputs are missing |
| `uv run nsefc import FILE.csv` | Adds user-supplied sessions after the dataset's end (§5.5); the next `run` picks them up |
| `uv run nsefc status` | Prints what is in `data/`: dataset, date range, last run, champion, headline metrics |
| `uv run nsefc clean [--all]` | Deletes derived data (keeps the raw copies unless `--all`) |
| `uv run nsefc dev ...` | Maintainer tools: `contract`, `web-hash`, `update-readme`, `calendar` |

`--profile full` needs the optional dependencies: `uv run --extra full nsefc run --profile full`.

### 3.2 What the user sees

The run prints one line per stage with its timing, using `rich`. This is the real output of the first run in a fresh clone (Linux, 2 cores, 17 October 2026; with `uv`'s package cache already warm, creating the environment added about 6 seconds before it):

```text
NSE Forecast  ·  Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026  ·  2007-01-02 to 2026-06-30
  Data: Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026", Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1
  Licence not recorded in reference/mendeley.yaml: use the data for personal research.
  acquire   27 files, copied                        0.3 s
  ingest    4,682 sessions, 92 securities           5.2 s   (4 corrections applied, 2 warnings)
  train     ridge, huber, lightgbm, 4 baselines  3 m 13 s
  predict   32 forecasts for Wed 1 Jul 2026         0.3 s
  publish   373 files                               2.6 s

Champion: No-change guess  ·  holdout 2023-01 to 2026-06
  No model beat the no-change guess by enough to pass the gates.
  best ML candidate: LightGBM, holdout skill +0.59%
  80% range contained the actual close 80.3% of the time

Finished in 3 m 21 s. Reports: /home/you/NSE-Time-Series/data/reports

Serving at http://127.0.0.1:8000  (Ctrl+C to stop)
```

When an ML model passes the gates, the champion lines instead give its holdout average miss against the no-change guess's, its skill and Diebold–Mariano p-value. A repeat run with nothing changed prints `cached` for every stage and is serving in about 2 seconds. Warnings are summarised; full details go to `data/runs/<run_id>/log.jsonl` and `data/reports/`.

### 3.3 Exit codes

`0` success; `2` usage error; `10` dataset could not be acquired (the `NSE Data/` folder or a `--source-dir` folder is missing, empty or unreadable), with a message explaining `--source-dir` and `--sample`; `20` data-quality failure that blocks the run; `30` training or evaluation failure, including G-PLAUS; `40` publishing or contract-validation failure.

### 3.4 Prerequisites stated in the README

`git` and `uv` (install instructions linked for each OS). Python 3.12 is installed by `uv` automatically. About 2 GB of free disk space. An internet connection the first time, for `uv` to download Python and the packages; the data ships with the repository.

---

## 4. Repository changes from Phase 0

The repository already has Phase 0 work (see `docs/archive/phase-0-status.md`). Handle it as follows.

### 4.1 Keep (adapt where noted)

| Item | Notes |
|---|---|
| `nsefc` package skeleton, uv, Python 3.12, ruff, mypy, pytest | Keep |
| import-linter contracts | Keep the ones that still apply to §6.2; delete the rest |
| Domain types | Keep |
| Layered settings | Keep; remove every setting about R2, secrets and environments other than `default`, `sample` and `test` |
| Trading calendar (2005–2026, held sessions) | Keep. It is central |
| Local object store | Keep only if it is a thin, useful file-store wrapper; otherwise replace with plain `pathlib` functions in `storage/` |
| Historical CSV reader and report generators | Keep; the reader is adapted to the dataset's files (done in Phase 2) |
| API contract v1 (Pydantic models, JSON Schema, fixtures, validator) | Keep, with the changes in §13.3 |
| Web app (Vite, React 19, TypeScript, TanStack Query), vitest, Playwright with axe | Keep, with the minimal changes in §15 |
| `ci.yml` checks | Keep the lint, type, test, audit and web checks; adapt per §17 |
| Baseline configs drafted for MF-6 | Keep and use in §10 |
| `docs/adr/` | Keep as history. Add `ADR-017-local-first.md` that records this redesign and supersedes ADR-003, ADR-014 and ADR-015 |

### 4.2 Delete

| Item | Why |
|---|---|
| R2 object store, compare-and-swap pointers, R2 bootstrap script | No cloud storage |
| Source-spike tooling (probe, backcheck, report) and `source-spike.yml` | No live scraping |
| Runbooks for R2, healthchecks and production secrets | No production |
| Legal enquiry drafts for NSE and Kingdom | Move to `docs/archive/` rather than delete, since they may be reused later |
| `var/nsefc-phase0-delivery.tar.gz` | Leftover delivery archive |
| Any `production` configuration, environment or workflow | No production |

### 4.3 The `NSE Data/` folder and git history

**`NSE Data/` stays committed (D-10).** It was committed in `5066df8` ("nse data 07-25") and is the tool's data source, cited as Wanjawa (2026) wherever the data is used (§5.3). It is not git-ignored, and the agent never edits or deletes anything under it (§0.6). Only `data/*` (except `data/.gitkeep` and `data/README.md`) is git-ignored.

**One history question remains for the owner.** Commit `c755a39` (27 Jul 2025) added an unrelated `backend/` project (a knowledge-base service with six government PDF documents); `5066df8` removed it, but the files stay in the history of the public repository. If that is not wanted, the owner chooses between rewriting history (`git filter-repo --path backend --invert-paths`, then a force-push) and starting a fresh repository from the current tree. **The agent MUST NOT do either without the owner's explicit go-ahead.**

### 4.4 Target directory tree

```text
NSE-Time-Series/
├── README.md                     quick start, results, method, contact (§18)
├── ENGINEERING.md                this document
├── LICENSE                       MIT for the code (owner to confirm); data licences are separate
├── pyproject.toml                package, dependencies, extras, tool settings
├── uv.lock
├── .gitignore                    data/*, .venv/, web/node_modules/, web/dist/
├── .github/workflows/ci.yml      tests only (§17)
├── NSE Data/                     the dataset (Wanjawa 2026), committed and read at runtime (D-10)
├── config/
│   ├── default.yaml              all tunable settings (§14)
│   ├── site.yaml                 owner name and contact links shown in the app (§18)
│   ├── calendar/nse_holidays.yaml
│   └── models/                   frozen hyperparameters for the default profile; search spaces for full
├── reference/
│   ├── corrections.yaml          documented fixes to the source data (§6.4)
│   ├── securities.csv            ticker, name, sector, aliases (built in Phase 2, reviewed)
│   └── mendeley.yaml             the dataset's citation, DOI and licence (empty until confirmed)
├── src/nsefc/
│   ├── domain/  calendar/  storage/  acquire/  ingest/  quality/
│   ├── features/  targets/  models/  intervals/  evaluation/  selection/
│   ├── prediction/  api/  publishing/  serve/  pipeline/
│   ├── web_dist/                 prebuilt frontend (committed; §15.4)
│   ├── sample/                   generator for the synthetic sample dataset (§16.3)
│   ├── config.py
│   └── cli.py
├── contracts/api/v1/             JSON Schema exported from nsefc.api
├── tests/                        unit, property, leakage, integration, e2e
├── web/                          React source (unchanged structure)
├── data/                         EMPTY in git except .gitkeep and README.md
└── docs/
    ├── adr/
    ├── data/mendeley-dataset.md  Phase 1 findings
    ├── methodology.md            source text for the About page
    └── archive/                  Draft 1.0 material kept for reference
```

---

## 5. Data acquisition

### 5.1 Source (D-10)

The data is the copy of the NSE daily price files committed in the repository's `NSE Data/` folder: 20 yearly price files and 7 sector files from 2 January 2007 to 30 June 2026, in seven sub-folders named after the Mendeley Data collections they came from. On 16 October 2026 the owner added the 2026 collection, the one the citation names, and moved the other folders' files up out of their inner sub-folders; the tool finds files at any depth. There is no data for November and December 2025, between the 2025 and 2026 files. By the owner's decision the dataset is cited, everywhere it is used, as:

> Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026", Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1

`reference/mendeley.yaml` holds that citation, the DOI, the dataset URL and the licence. Nothing is downloaded, so there is no API client, no network access and no `--dataset-version` option. Phase 1 recorded the file names, formats, columns, row counts, SHA-256 hashes and defects in `docs/data/mendeley-dataset.md`.

### 5.2 Acquire

1. `acquire` hashes every `.csv` and `.zip` file under `NSE Data/`, copies them flat into `data/raw/mendeley/hvmhnp7f9r/v1/` under their own file names (zips are extracted, refusing member paths that would leave the folder; D-35), and writes `manifest.json`: source, dataset id, version, title, licence, DOI, citation, the time of the copy (UTC), and per file the name, original path, size and SHA-256. CSV files, including those extracted from zips, are copied and hashed with Windows line endings converted to LF, so a file has the same SHA-256 in a fresh clone, a Windows checkout and the original download (D-41).
2. Cache: if the manifest exists, lists exactly the same files and hashes as the source folder, and every copied file still matches its hash, nothing is copied (an edited citation or licence only refreshes the manifest's record, D-37). A changed, added or removed file produces a new copy and a new manifest, so the next ingest re-runs.
3. `data/raw/active.json` records which manifest the next ingest reads (`dataset`, `local` or `sample`), so individual stage commands follow the last `acquire`.
4. A missing or empty folder exits with code 10 and explains `--source-dir` and `--sample`.

### 5.3 Licence and attribution

The citation above is shown in the run summary, the app's footer and About page, the README, `status.json` and `site.json`. The licence field in `reference/mendeley.yaml` is empty because the dataset page could not be checked from the build environment (`data.mendeley.com` was refused by its network policy). While it is empty, the run summary and the app add a one-line notice that the data is for personal research use. When the owner confirms the licence on the dataset page, they fill in `licence` and `licence_url`, and the notice disappears.

### 5.4 Other sources

`--source-dir PATH` accepts any folder of files in the same format. The tool hashes them, copies them to `data/raw/local/<hash>/` with a manifest marked `source: "local"`, and proceeds identically. `--sample` uses the synthetic dataset (§16.3) and labels everything in the UI as sample data.

### 5.5 User-supplied recent sessions (`nsefc import`)

The dataset ends months before today, so the "next session" forecast is for a date already in the past. To let a user extend the data, `nsefc import FILE.csv` accepts a CSV with columns `date, ticker, close, volume` and optional `high, low, open, turnover, prev_close`. Imported rows:

1. are stored in `data/raw/imports/<sha256>.csv` with a manifest entry marked `source: "user_import"`;
2. pass through the same quality checks as the dataset (§6), plus IMP-01 (§6.6);
3. may only add sessions after the dataset's last session. Overlapping dates are rejected with a message;
4. are labelled as user-imported in the status file and the UI ("Data through Fri 14 Mar 2026, including sessions you imported").

The tool does not fetch these sessions itself. An import should include every security that should get a forecast: a security with no rows in the imported sessions has no row on the new last session, so it gets no forecast (it stays active and keeps its history).

---

## 6. Ingestion and data quality

### 6.1 Data folder layout

```text
data/
├── README.md                     committed: explains this folder
├── raw/                          copied, generated or imported files, never modified
│   ├── mendeley/hvmhnp7f9r/v1/   the NSE Data/ copy and manifest.json
│   ├── local/<hash>/             a --source-dir copy
│   ├── sample/v1/                the generated sample
│   ├── imports/                  nsefc import files and manifest.json
│   └── active.json               which manifest the next ingest reads
├── canonical/
│   ├── bars.parquet              one row per (ticker, session), §6.2
│   ├── indices.parquet           index levels (NASI and others)
│   ├── securities.parquet
│   ├── sessions.parquet          calendar with held / missing / holiday status
│   └── ingest_report.json
├── features/                     feature tables by feature-set hash
├── models/                       fitted artifacts and metadata by run
├── predictions/                  walk-forward and forward predictions (Parquet)
├── reports/                      data audit, evaluation report (Markdown and JSON)
├── api/v1/                       published JSON for the frontend (§13)
├── stamps/                       one file per stage: input fingerprint and outputs (§19)
└── runs/<run_id>/                log.jsonl, run.json (inputs, hashes, timings, outcome)
```

### 6.2 Canonical daily bar

| Column | Type | Null | Notes |
|---|---|---|---|
| `ticker` | string | no | Current ticker after alias mapping (§6.5) |
| `session_date` | date | no | Local session date; never derived from a timestamp |
| `close` | float64 | no | Official daily price as published. On the NSE this is a session VWAP (Rules 7.6.1 and 7.6.6, confirmed in Phase 0) |
| `prev_close_reported` | float64 | yes | As printed by the source (`Previous`; present, missing in 18 rows) |
| `open`, `high`, `low` | float64 | yes | `open` is never published, so always null; `high` and `low` are null when the security did not trade |
| `volume` | int64 | no | 0 when untraded |
| `turnover` | float64 | yes | Not published by the dataset, so always null; liquidity rules use `volume × close` |
| `traded` | bool | no | `volume > 0` |
| `is_carried_forward` | bool | no | True if synthesised (§6.3) |
| `is_event` | bool | no | True if the move from the previous close is a PRC-01 event (§6.7) |
| `source` | string | no | `mendeley:hvmhnp7f9r:v1` (the `NSE Data/` copy), `local`, `sample` or `user_import` |
| `source_file_sha256` | string | no | Lineage |

Primary key `(ticker, session_date)`. Write with pyarrow; sort by `(ticker, session_date)`. Index levels (`^NASI`, `^N20I` and others, found in the price files) go to a separate `indices.parquet` (`session_date`, `index`, `level`).

### 6.3 Panel rules

1. A security is treated as listed from its first to its last appearance in the data.
2. **Market-level checks run first, on observed rows only.** A session date with no rows for any security is a missing session (not a holiday), recorded in `sessions.parquet`. This avoids Draft 1.0's MF-3 defect, where carried-forward rows were synthesised before completeness was checked.
3. Only then, for a session that is held, a listed security with no row gets a synthesised row: `volume = 0`, `traded = false`, `close` = last close, `is_carried_forward = true`.
4. No rows are synthesised inside a missing session. Missing sessions are never filled.

The Phase 0 audit already found a gap with no data from July to December 2020. It is handled by the gap guard in §8.4, not by filling.

### 6.4 Corrections

Known source defects are fixed by explicit, reviewable rules in `reference/corrections.yaml`, each keyed to the SHA-256 of the file it applies to (and to a line range inside it), so a correction never silently applies to a different file. A rule that matches no rows, or would create a duplicate key, stops the ingest. Phase 0 findings, re-checked in Phase 2 and encoded:

| Finding | Rule |
|---|---|
| 2017 file contains a block dated Saturday 2015-05-09 that belongs to 2017-05-09 | `redate` rule R2017-01 (70 rows); the block's "Previous" prices chain exactly with the sessions around 9 May 2017 |
| 152 duplicate keys in 2009 | Three misdated blocks (29 Jan, 2 Apr and 8 Oct 2009 written where 21 Jan, 4 Feb and 10 Aug belong): `redate` rules R2009-01 to R2009-03 (158 rows). Every remaining duplicate is identical |
| Identical duplicates (64 rows after the redates) | Dropped automatically and counted |
| 27 Dec 2010 and 27 Dec 2011 traded in full | Already recorded as held sessions in the calendar |
| Weekdays with no data and no known reason (26, plus 129 in the 2020 gap) | Recorded as missing sessions |

The synthetic sample has one planted misdated block, fixed by rule SAMPLE-01 keyed to the generated file's hash. Every correction is counted and listed in `data/reports/data-audit.md`.

### 6.5 Securities and aliases

Phase 2 builds `reference/securities.csv` from the dataset: ticker, company name, sector (if present), first and last session, and known former tickers or names as aliases (Barclays Bank of Kenya, `BBK`, to Absa Bank Kenya, `ABSA`: confirmed, since the last 2012 close under the old code equals the first 2013 "Previous" under the new one). Ticker suffixes that mark rights or other non-ordinary lines (the Phase 0 audit saw `-R`) MUST be identified and excluded from the forecast universe; they can remain in the display universe.

### 6.6 Quality checks

Severity is **error** (blocks the run, exit code 20), **exclude** (drops the affected rows from modelling, kept for display, counted in the report) or **warn** (reported only).

| ID | Check | Severity |
|---|---|---|
| SCH-01 | Required columns present and parseable; types correct | error |
| SCH-02 | `close > 0`, `volume >= 0`, `high >= low` where present | exclude row |
| KEY-01 | No duplicate `(ticker, session_date)` after corrections | error |
| DAT-01 | Every date is a weekday | error, unless fixed by a correction |
| DAT-02 | Every date with data is a scheduled session or a recorded held session; otherwise listed for review | warn |
| DAT-03 | Each file's rows fall in the year its file name states (the dataset states its range per file) | error |
| PRC-01 | Absolute change from previous close beyond the ±10% daily band (confirmed in Phase 0: 99.82% of price-setting rows fall inside it) | exclude from labels and feature windows (§8.4); show in display data |
| VOL-01 | `turnover / volume` close to `close` where all are present (consistency with VWAP basis); the dataset has no turnover, so it applies only to imports | warn |
| MKT-01 | Number of securities in a held session is at least 70% of the trailing 20-session median | warn; market-context features for that session are null |
| GAP-01 | Missing sessions are listed with their ranges | warn |
| IMP-01 | Imported sessions come after the dataset's last session (§5.5) | error |

Thresholds live in `config/default.yaml`.

### 6.7 Corporate actions (simplified)

Draft 1.0 called for a full corporate-actions table with back-adjustment. Version 2.0 does not back-adjust. Instead, any session with an absolute move beyond the band plus 0.5 percentage points (PRC-01) is treated as an event: its return is excluded from labels and evaluation, and feature windows that include it are recomputed from the session after the event (§8.4). This removes splits, bonus issues, rights issues and data errors from training without needing an external corporate-actions source. The cost is that genuine large moves are excluded too; the evaluation report counts them. Listed in §21 as a known limitation.

---

## 7. Trading calendar

Keep the Phase 0 calendar (rules, confirmed, listed and provisional entries, held sessions). Changes:

1. Add the 2026 holidays found in the review and missing from Draft 1.0: Idd-ul-Azha (27 May 2026, `listed` from published holiday lists) and Mazingira Day (10 October, a fixed-date rule since 2024, confirmed by the absence of trading on 10 Oct 2024 and 2025). Done; the 2026 files later confirmed Idd-ul-Fitr (20 March) and Idd-ul-Azha (27 May), and their 122 sessions match the calendar exactly.
2. Add a `missing` status for sessions that were scheduled but have no data (§6.3).
3. The interface stays `is_scheduled_session(d)`, `next_session(d)`, `previous_session(d)`, `sessions_between(a, b)`. No other module computes "tomorrow" with date arithmetic.
4. The calendar must cover at least one session beyond the last data date, so the forecast target date is defined. If the data ends in a year the calendar does not cover, the target falls back to the next weekday, and the UI labels it "next weekday (calendar not available)".

---

## 8. Features

### 8.1 Principles (unchanged from Draft 1.0)

Scale-free inputs only (returns, ratios, normalised quantities, never raw price levels). As-of only: every feature for session T uses data with `session_date <= T`. Windows count trading sessions, not calendar days. One code path for training and prediction: `features.build(panel, as_of)`.

### 8.2 Feature set v1

Keep this deliberately small. Fewer features mean fewer failure modes, and the extra families from Draft 1.0 rarely pay for themselves on this data.

| Family | Features |
|---|---|
| Returns | `ret_k = ln(C_T / C_{T−k})` for k in {1, 2, 3, 5, 10, 20} |
| Trend | `C_T / SMA_n − 1` for n in {5, 20, 50}; distance from 250-session high and low |
| Volatility | Rolling std of `ret_1` over 5 and 20 sessions; EWMA volatility (λ = 0.94, over the 60-session window, D-21); `(H − L) / C` (high and low are present) |
| Liquidity | `log1p(volume)`; `ln((1 + volume) / (1 + 20-session median))` (D-23); share of last 20 sessions traded; sessions since last trade (capped at 60). The dataset has no turnover |
| Market | Equal-weighted return of all ordinary shares over 1 and 5 sessions (D-24); breadth `(advancers − decliners) / n`; NASI return over 1 and 5 sessions (index levels are in the price files; NASI from 25 Feb 2008, null before) |
| Calendar | Day of week; `days_to_next_session` |
| Static | Sector, from the dataset's sector files |

Features are declared in `config/default.yaml` under `features:`. The feature-set hash is the hash of that block plus the package version, and it names the cache folder in `data/features/`.

### 8.3 Leakage rules (mandatory)

| Rule | Requirement |
|---|---|
| L1 | Feature code receives data only through `load_panel(as_of=T)`, which filters to `session_date <= T` and asserts it |
| L2 | Negative shifts, `center=True`, back-fill and interpolation are banned in `features/` (enforced by an AST test). `features` cannot import `targets` (import-linter) |
| L3 | Every shift and rolling operation is grouped by ticker on data sorted by `(ticker, session_date)` |
| L4 | Anything fitted (scalers, imputers, winsorisation bounds, encoders) is fitted only on each fold's training rows, inside a scikit-learn `Pipeline` saved with the model |
| L5 | No random splits anywhere. Each training window ends at least one session before its test window |
| L6 | Universe membership at a date uses only data up to that date. Delisted securities stay in historical training data |
| L7 | Plausibility tripwire: results far better than plausible are treated as a leakage bug (gate G-PLAUS, §11.4) |

### 8.4 Gap guard

A feature row for session T is valid only if its lookback window (the longest window used, 60 sessions by default; 250 for the high and low features, which become null rather than invalidating the row) contains no missing session and no PRC-01 event for that security. Rows failing the guard are excluded from training and evaluation and counted in the report. This handles the 2020 gap and corporate actions with one rule.

---

## 9. Target

```text
y(i, T) = C(i, T+1) / C(i, T) − 1

T+1 = the next held session after T in which security i is listed
predicted_close(i, T+1) = C(i, T) × (1 + ŷ)
```

If the security does not trade at T+1, `y = 0` and the row is kept, because an unchanged price is exactly what will be reported. Rows whose T+1 return is a PRC-01 event, or whose next held session is not the next scheduled session (the gap crosses a missing session), have no label. Training labels are winsorised at ±10.5%; evaluation is never winsorised. Price-level targets are rejected for the reasons in Draft 1.0 §14 (non-stationary, not poolable, misleading level metrics).

The displayed predicted close is the model's conditional median: models are trained with L1 or Huber loss, and MAE is the primary metric.

---

## 10. Baselines and models

### 10.1 Baselines (run in the same harness, eligible to be champion)

| ID | Baseline | Forecast ŷ |
|---|---|---|
| B0 | No change | 0 |
| B1 | Drift | Trailing 250-session mean return of the security |
| B2 | Moving average | `SMA_5(T) / C_T − 1` |
| B3 | AR(1) | Per-security AR(1) on returns, fitted on the trailing 500 sessions at each refit |

B3 matters most. Because the NSE close is a session VWAP and many stocks trade thinly, daily returns have mechanical positive autocorrelation, so a no-change forecast is beatable without any real insight. Beating B0 is necessary; beating B3 is what shows the ML adds something. The About page explains this in plain words.

### 10.2 Candidates

| ID | Model | Profile |
|---|---|---|
| M1 | Ridge regression in a scikit-learn pipeline (imputation, standard scaling, winsorisation fitted in-fold); a Huber variant | default and full |
| M2 | LightGBM, L1 or Huber objective, shallow trees, large minimum leaf size, early stopping on the last 10% of each training window | default and full |
| M3 | CatBoost, MAE or Huber loss, depth 3–6 | full only |

One global model pooled across all securities in the forecast universe, not one model per ticker (Draft 1.0 §13.2).

**Default profile hyperparameters are frozen** in `config/models/*.yaml`. They are chosen once by the maintainer by running the full profile's tuning on the tuning period only (§11.2), then committed. The default run never tunes, which keeps it fast and makes the holdout result trustworthy. Initial values before that tuning run: Ridge `alpha = 1.0`; LightGBM `objective = l1, learning_rate = 0.03, num_leaves = 15, min_data_in_leaf = 500, feature_fraction = 0.8, bagging_fraction = 0.8, bagging_freq = 1, lambda_l2 = 1.0, n_estimators up to 1000 with early stopping after 50`.

Determinism: fixed seeds; LightGBM `deterministic = true`, `num_threads` fixed from config (default 4); rows sorted before training; CPU only.

### 10.3 Artifacts

Models are saved with `joblib` under `data/models/<run_id>/<model>.joblib`, with a JSON sidecar holding the algorithm, hyperparameters, feature-set hash, training window, dataset version and the artifact's SHA-256. The loader refuses any artifact whose SHA-256 does not match its sidecar, and the tool only ever loads artifacts it produced on the same machine; it never downloads or accepts model files from elsewhere. This resolves Draft 1.0's MF-7 conflict (pickle ban versus persisted scikit-learn pipelines): pickle-based formats are acceptable for locally produced, hash-checked files and are never loaded from untrusted sources.

---

## 11. Evaluation and champion selection

### 11.1 Profiles

| | default | full |
|---|---|---|
| Hyperparameters | Frozen from config | Tuned with Optuna (TPE, 40 trials per model, fixed seed) on the tuning period |
| Refit frequency in walk-forward | Quarterly | Monthly |
| Candidates | M1, M2 | M1, M2, M3 |
| Target runtime on a 4-core laptop | under 15 minutes for train and evaluate | a few hours |

### 11.2 Timeline

Boundaries live in `config/default.yaml` and assume data from 2007; the holdout always runs to the last session in the data.

```text
2007 ........ 2012 | 2013 ...... 2017 | 2018 ............. 2022 | 2023 ........ data end | after data end
warm-up, training  | tuning           | selection walk-forward | holdout                | forecast
only               | (full profile)   | (refits every quarter) | (same procedure, never | (champion,
                   |                  |                        |  used for development) |  next session)
```

| Period | Procedure | Used for |
|---|---|---|
| Tuning, 2013–2017 | Expanding-window annual folds | Hyperparameters only (full profile). Its results are never used for selection |
| Selection, 2018-01 to 2022-12 | Frozen hyperparameters; expanding-window walk-forward with a refit every quarter (monthly in full) | Gates G-SKILL to G-CAL |
| Holdout, 2023-01 to data end | Same procedure, run for every model that passed selection and for all baselines | Gate G-HOLD, and the headline numbers shown to users |
| Forecast | The champion is refit on all data and predicts the session after the last data date | The forecast shown in the app |

Rule for maintainers: no change to features, models, hyperparameters or gates may be made because of holdout results. If one is made anyway, record it in §22 and say in the README that the holdout is no longer clean.

### 11.3 Metrics

Errors are in return space, `e = ŷ − y`, so absolute return error equals absolute price error as a share of the last close ("average miss of 1.3% of price").

| Metric | Use |
|---|---|
| **MAE skill vs B0**: `1 − MAE_model / MAE_B0`, pooled over all (security, session) rows | Primary; gate metric |
| Diebold–Mariano test, one-sided, on the daily cross-sectional mean loss differential, Newey–West variance with 5 lags | Significance of skill |
| Directional accuracy on non-flat sessions (actual changed and forecast outside ±0.1%), reported with its coverage and against "always up", "always down" and "sign of last return" | Secondary |
| 80% interval coverage and mean width | Secondary |
| Per-security skill distribution; share of securities with non-negative skill | Secondary |
| Breakdowns by year, liquidity tercile and volatility regime | Report only |

Not used: MAPE on returns (undefined when the actual return is zero, which is common), R² on price levels (inflated by persistence), pooled KES-level MAE (dominated by high-priced stocks).

### 11.4 Gates

Fixed before results are seen. Thresholds live in `config/default.yaml` under `gates:`.

| Gate | Condition |
|---|---|
| G-INT Integrity | Artifact hash matches; predictions contain no NaN; lower ≤ point ≤ upper; reloading the artifact reproduces predictions within 1e-9; the leakage tests in §16.2 pass |
| G-SKILL Beats no-change | Selection-period MAE skill ≥ 1.0% with one-sided DM p < 0.05 |
| G-BASE Beats the best simple baseline | Selection MAE no worse than the best of B1–B3. If the improvement over that baseline is not significant (p ≥ 0.10), the simpler model wins |
| G-STAB Stability | Positive skill vs B0 in at least 4 of the 5 selection years; no year below −2% |
| G-DIR Direction guardrail | Directional accuracy on non-flat sessions not significantly worse than the best trivial sign baseline |
| G-CAL Calibration | Selection-period 80% coverage within [75%, 85%] |
| G-HOLD Holdout confirmation | Holdout skill vs B0 positive, and at least half of the selection skill |
| G-PLAUS Plausibility | If pooled skill exceeds 15% or directional accuracy exceeds 65%, the run stops with exit code 30 and a "suspected leakage" message, whatever the other gates say |

### 11.5 Selection

1. Candidates that pass all gates are ranked by selection-period MAE. Ties (difference not significant at p < 0.10) go to the simpler model: baseline, then Ridge, then LightGBM, then CatBoost.
2. If no ML candidate passes, the best of B1–B3 that passes G-SKILL, G-BASE and G-CAL becomes champion; otherwise B0 is champion.
3. The champion's name is always shown honestly ("AR(1) baseline", never "AI model").
4. The full gate table for every model is written to `data/reports/evaluation.md` and to `report.json` (§13.2).

---

## 12. Prediction intervals

Volatility-scaled split conformal, as in Draft 1.0 §19, simplified:

1. `σ̂` = EWMA volatility of the security's returns up to T (λ = 0.94), floored at 0.25%.
2. Calibration scores `s = (y − ŷ) / σ̂` from the most recent 250 sessions of out-of-sample walk-forward predictions, pooled across the universe. Never in-sample residuals.
3. Interval `[ŷ + q₀.₁₀(s)·σ̂, ŷ + q₀.₉₀(s)·σ̂]` in return space, mapped to price with `C_T × (1 + bound)` and clipped to the ±10% band.
4. In walk-forward evaluation, the calibration window rolls forward with the evaluation, so coverage is measured honestly.

The UI calls it an "80% expected range", never a confidence interval, and shows its holdout coverage next to it.

---

## 13. Forecast universe, predictions and publishing

### 13.1 Forecast universe

Evaluated point-in-time at each refit date and at the forecast date: ordinary shares only (no `-R` or similar lines); traded on at least 80% of the last 250 held sessions; median daily turnover over those sessions of at least KES 150,000, measured as median `volume × close` because the dataset has no turnover column (D-13: KES 1 million gave only 8 to 15 securities); at least 500 sessions of history. Thresholds live in config. On the real data the universe has 16 to 31 securities across the walk-forward refits (median 20) and 33 at the last session. All securities stay in the display universe.

### 13.2 Published files

The publisher writes the API contract v1 files into `data/api/v1/`, validating each against its Pydantic model before writing. A file that fails validation stops the run with exit code 40.

| File | Contents |
|---|---|
| `status.json` | Run and data status (§13.3) |
| `stocks.json` | Securities index for search |
| `stocks/{TICKER}.json` | Stock header and summary |
| `stocks/{TICKER}/history.1y.json`, `history.max.json` | Price chart data, columnar |
| `stocks/{TICKER}/prediction.json` | Latest forecast, track record and prediction history |
| `market/overview.json` | Session summary, movers, homepage charts |
| `report.json` | New: evaluation results for the About page (§15.2) |
| `site.json` | New: owner name and contact links from `config/site.yaml`, plus dataset attribution |

Every file except `status.json` lives in the release folder `r/<release_id>/`, including `report.json` and `site.json`, so a page never mixes two releases. Writes go to a temporary folder that is then renamed into place, so the server never sees a half-written release. The `release_id` stays: `<last data session>.<first 12 hex characters of the publish fingerprint>`.

### 13.3 Contract changes (contract v1.1; backwards-compatible additions plus one relaxed field)

1. `status.json`:
   - add `data_mode` (`"historical"`, `"historical+imports"` or `"sample"`);
   - add `dataset` (`{ "source", "title", "version", "first_session", "last_session", "licence", "citation", "doi", "url" }`);
   - add `contract_version` (`"1.1"`);
   - make `stale_after` nullable. It is `null` in local mode, because historical data is never "late".
   - `pipeline.primary_source` becomes `"mendeley"`, `"local"` or `"sample"`; `fallback_used` is always `false`.
2. `prediction.json`: `track_record.basis` is always `"backtest"` and covers the holdout period; `history` lists the holdout-period walk-forward predictions with their actuals (the most recent 250 per security, to keep files small).
3. `latest.target_session` comes from the calendar; add `latest.target_in_past` (bool, true when the target date is before today's date on the user's machine when the release was published) and `latest.target_from_calendar` (false when the calendar does not cover the target and it is the next weekday, §7 item 4).
4. `history.events[].type` gains `"large_move"` for PRC-01 events, so the chart can mark sessions excluded from modelling; `unavailable_reason` gains `RECENT_PRICE_EVENT` (D-19).
5. New `report.json` schema: dataset summary, universe size, per-model gate table, headline holdout metrics, skill by year, coverage, data audit counts.
6. New `site.json` schema: `owner_name`, `links` (list of `{ label, url }`), `attribution`.
7. Regenerate JSON Schema into `contracts/api/v1/` and the frontend TypeScript types; add fixtures for each new field.

### 13.4 Predictions storage

`data/predictions/<run_id>/walkforward.parquet` holds every out-of-sample prediction (model, security, origin session, target session, predicted return, bounds, actual, error). `forecast.parquet` holds the champion's forward forecasts. Each run writes a new folder; the latest run is referenced in `data/runs/latest.json`.

---

## 14. Configuration

One file, `config/default.yaml`, holds every tunable value: paths, dataset id, quality thresholds, feature list, universe rules, period boundaries, model settings per profile, gate thresholds, interval settings, server host and port, and thread count. `--sample` loads `config/sample.yaml` over it (shorter periods, smaller universe). Settings are validated with Pydantic on load; an unknown key is an error. There are no secrets and no environment variables are required. `NSEFC_DATA_DIR` MAY override the data folder location.

`config/site.yaml` (committed, filled in by the owner):

```yaml
owner_name: "Your Name"
tagline: "Built by Your Name"
links:
  - { label: "Email", url: "mailto:you@example.com" }
  - { label: "GitHub", url: "https://github.com/duotkuerduot" }
  - { label: "LinkedIn", url: "https://www.linkedin.com/in/your-handle" }
```

---

## 15. Frontend (minimal changes)

The existing app, its pages, components, design tokens, accessibility work and tests stay. Only these changes are made. On 17 October 2026 the owner also asked for a visual redesign (D-42, `docs/design/redesign.md`), which changed the styling only.

### 15.1 Data access

1. The API client's base URL becomes the relative path `/api/v1/`, served by the local server (§15.4). Remove any CDN or R2 base URL.
2. Release resolution through `status.json` stays as is.

### 15.2 Content changes

| Where | Change |
|---|---|
| Header `DataStatus` | Shows "Data through Tue 30 Jun 2026 · Mendeley Data v1" (or "Sample data") instead of an update time |
| `StaleDataBanner` | Shown only when `stale_after` is not null. In local mode it never appears |
| Prediction panel title | "Model forecast for Wed 1 Jul 2026". When `target_in_past` is true, add the line: "The dataset ends on Tue 30 Jun 2026, so this is the forecast the model would have made that evening." |
| Track record copy | Always labelled "Simulated (backtest), Jan 2023 to Jun 2026" |
| About page | New "Results" section rendered from `report.json`: headline numbers, the gate table, skill by year (small bar chart using the existing chart wrapper), coverage, data audit counts. Existing methodology and limitations text is updated from `docs/methodology.md` |
| Footer and About page | Contact links and owner name from `site.json`; dataset attribution |
| Sample mode | A small, permanent notice on every page: "Showing synthetic sample data. Run without --sample to use real NSE data." |

### 15.3 Language rules (unchanged, with one fix)

The UI never uses "buy", "sell", "hold", "target price", "signal", "recommendation", "guaranteed", "will reach" or "certain". Every forecast carries "Research forecast, not investment advice." The existing banned-word test stays. Fix for Draft 1.0's MF-10: no UI string may contain the word "hold" in any sense, so the data-quality state copy uses "paused" instead ("Forecasts are paused while the data is checked."). The test matches whole words, case-insensitively.

### 15.4 Shipping the frontend without Node.js

People who clone the repository should not need Node.js or pnpm.

1. `web/vite.config.ts` sets `build.outDir` to `../src/nsefc/web_dist` and `base` to `/`.
2. The built files in `src/nsefc/web_dist/` are committed, and included as package data in `pyproject.toml`.
3. `web_dist/.source-hash` contains a SHA-256 over `web/src/**`, `web/index.html`, `web/package.json`, `web/pnpm-lock.yaml` and `web/vite.config.ts`. A small script, `uv run nsefc dev web-hash`, computes it. CI recomputes it and fails if the committed build is stale, with the message "run `pnpm -C web build` and commit `src/nsefc/web_dist`".
4. Developers who change the frontend run `pnpm -C web install` and `pnpm -C web build`, then commit the result.

### 15.5 Local server (`nsefc serve`)

Python standard library only (`http.server.ThreadingHTTPServer` with a custom handler):

1. Binds to `127.0.0.1` only. Port from config (default 8000); if busy, tries the next 10 ports and prints the one used.
2. `/api/v1/*` is served from `data/api/v1/` with `Content-Type: application/json` and `Cache-Control: no-store`.
3. Any other path that matches a file in `web_dist/` is served with the correct MIME type (register `.js`, `.mjs`, `.css`, `.svg`, `.woff2` explicitly, because Windows registry MIME types are unreliable). Hashed assets get a one-year cache header.
4. Any other path returns `index.html` (single-page-app routing for `/stocks/:ticker` and `/about`).
5. Path traversal is rejected: resolved paths must stay inside their root folder.
6. Opens the default browser with `webbrowser.open` unless `--no-browser`. Ctrl+C stops cleanly.
7. If `data/api/v1/status.json` does not exist, `serve` exits with "No results yet. Run `uv run nsefc run` first."

---

## 16. Testing

### 16.1 Data and pipeline

| Test | What it proves |
|---|---|
| Acquire | Manifest writing with SHA-256 hashes; cache hit; a changed, added or removed source file triggers a new copy; zip extraction refuses unsafe paths; a missing or empty folder gives exit code 10 with guidance |
| Reader golden files | A small hand-made file in the dataset's format parses to the expected canonical rows |
| Corrections | Each rule in `corrections.yaml` applies only to its keyed file; the redate rule moves the misdated rows; conflicting duplicates are handled as configured |
| Quality checks | Every check in §6.6 has a passing and a failing fixture |
| Panel rules | Market-level checks run before synthesis; no synthesis inside missing sessions |
| Import | Overlapping dates rejected; imported rows pass the same checks; status reports `historical+imports` |
| Calendar | Holidays, Sunday-to-Monday observation, Easter, the Mashujaa Day example, missing sessions |
| Idempotency | Two consecutive `run --no-serve` calls on the sample give byte-identical `data/api/v1/` contents and the same `release_id` |
| Caching | A second run without `--force` skips acquire, ingest, features and training |

### 16.2 ML

| Test | What it proves |
|---|---|
| Feature correctness | Hand-computed values on small fixtures |
| Truncation invariance (Hypothesis) | Features at T computed on data truncated at T equal features at T computed on the full data |
| Future perturbation | Changing every row after T leaves features at T unchanged |
| Cross-security bleed | No value crosses from one ticker into the next |
| Label alignment | Targets line up exactly on a synthetic series with a known next value |
| Static leakage scan | Banned constructs in `features/` fail the test |
| Gap guard | Rows whose window spans a missing session or an event are excluded |
| Random-walk null test | On pure random walks, no candidate shows significant skill; any skill means a bug |
| Planted-signal test | On synthetic AR(1) data, the harness detects skill of roughly the expected size and AR(1) wins or ties |
| Determinism | Same inputs and seed give identical predictions |
| Artifact round trip | Save, load and predict reproduces predictions within 1e-9; a tampered artifact is refused |
| Gates | Each gate passes and fails on constructed results; G-PLAUS stops the run |

### 16.3 Synthetic sample dataset

`nsefc.sample` generates a deterministic synthetic dataset (fixed seed) in the same file format as the files in `NSE Data/`: about 30 fictional tickers (names like `SMPL01`, clearly not real companies), 2015–2024, with thin trading, VWAP-like autocorrelation, a missing-session gap, a few band-breaching events, duplicates and a misdated row to exercise corrections. It is generated at runtime, not committed as data. `--sample` uses it with `config/sample.yaml`, which shortens the periods so the whole run takes under 2 minutes.

### 16.4 API contract and frontend

Every published file validates against its model; generated TypeScript types match the committed ones; securities without a forecast carry a valid `unavailable_reason`. Frontend: the existing vitest, component and Playwright tests stay; add tests for the changes in §15.2 (data-through label, no stale banner when `stale_after` is null, `target_in_past` line, Results section, contact links, sample notice). The banned-word test and axe checks stay.

### 16.5 End-to-end

`uv run nsefc run --sample --no-serve` followed by starting `nsefc serve --no-browser` in the test process and running the Playwright smoke tests against it: homepage loads, search finds a sample ticker, the stock page shows a forecast, the About page shows results and contact links.

---

## 17. CI

One workflow, `.github/workflows/ci.yml`, on push and pull request. No secrets, no data downloads, no scheduled jobs.

| Job | Runs on | Steps |
|---|---|---|
| python | ubuntu-latest | `uv sync --frozen`; ruff; mypy; import-linter; pytest (unit, property, leakage, integration); pip-audit |
| e2e-sample | ubuntu-latest, windows-latest, macos-latest | `uv run nsefc run --sample --no-serve`; check exit code 0 and that `data/api/v1/status.json` exists and validates |
| web | ubuntu-latest | `pnpm install --frozen-lockfile`; type-check; vitest; banned-word test; build; verify `web_dist/.source-hash`; pnpm audit |
| browser | ubuntu-latest | Sample run, local server, Playwright with axe |

The Windows job matters: it is the owner's platform and likely the platform of many people who clone the repository.

---

## 18. README and presentation

The README is the project's front page. Required sections, in this order:

1. **One-paragraph summary** and a screenshot of the stock page (stored in `docs/images/`).
2. **Quick start:** install `uv` (one command per OS), `git clone`, `cd`, `uv run nsefc run`. Nothing else.
3. **Results:** the headline numbers and gate table from the most recent maintainer run, inserted between `<!-- results:start -->` and `<!-- results:end -->` markers by `uv run nsefc dev update-readme`. Include the dataset version and date range they apply to.
4. **How it works:** a short version of `docs/methodology.md`, with a Mermaid diagram of the six stages.
5. **Why "no change" is the number to beat:** three or four sentences on VWAP closes, thin trading and the AR(1) baseline.
6. **Limitations:** historical data only, the dataset end date, no corporate-action adjustment (§6.7), the 2020 gap, past results not predicting future results, not investment advice.
7. **Data and attribution:** the dataset citation (Wanjawa 2026, doi: 10.17632/hvmhnp7f9r.1) and its licence status; the data ships in `NSE Data/` by the owner's decision (D-10).
8. **Commands:** the table from §3.1.
9. **Contact:** owner name and links (same as `config/site.yaml`), with a line inviting questions and collaboration.
10. **Licence** for the code.

---

## 19. Pipeline orchestration

`nsefc.pipeline` runs the stages in order. Each stage:

1. declares its inputs (files and config keys) and outputs;
2. computes an input fingerprint (SHA-256 over input file hashes, the relevant config block and the package version);
3. skips itself if its outputs exist with the same fingerprint, unless `--force`;
4. writes outputs to a temporary folder, then renames into place;
5. logs start, end, duration, counts and warnings as JSON lines to `data/runs/<run_id>/log.jsonl`.

`data/runs/<run_id>/run.json` records the command, profile, dataset version and hashes, package version, git commit (if available), per-stage fingerprints, timings, outcome and champion. A failed stage leaves earlier outputs untouched, so a fixed rerun resumes from that stage.

Train and evaluate use `joblib` parallelism across walk-forward folds where it is safe, limited by the configured thread count.

---

## 20. Implementation phases

Each phase lists its deliverables and the checks that close it.

### Phase 1: Clean-up and dataset discovery

Deliverables: deletions and moves from §4.2; updated `.gitignore`; `data/.gitkeep` and `data/README.md`; ADR-017; `docs/data/mendeley-dataset.md` recording the citation, file list, formats, columns, date range, row counts, hashes and defects of the files in `NSE Data/`; §5 of this document corrected to match reality. 2.0's API exploration script and metadata fixture were dropped with the download (D-10). Owner gate: §4.3 history decision.

Checks: CI passes after deletions; `git status` shows nothing under `data/` tracked; the dataset findings document exists and every *(verify)* in §5 and §6.2 is resolved or explicitly left open with a reason.

### Phase 2: Acquire and ingest

Deliverables: `acquire` (copy of `NSE Data/`, manifest, cache, `--source-dir`, `--sample`); the synthetic sample generator; `ingest` (reader, corrections, alias mapping, panel rules, quality checks, `bars.parquet`, `securities.parquet`, `sessions.parquet`); `reference/securities.csv`; `data/reports/data-audit.md`; `nsefc import`; `nsefc status`.

Checks: ingest of the real dataset produces a canonical panel whose row counts, date range and missing-session list match the Phase 0 findings (or the differences are explained); all Phase 0 data defects are handled by documented rules; tests in §16.1 pass; the sample run's ingest takes under 10 seconds.

### Phase 3: Features, targets and the leakage suite

Deliverables: feature set v1, targets, gap guard, feature cache; every leakage test in §16.2.

Checks: all leakage tests, including the random-walk null test, pass; feature build for the full dataset takes under 2 minutes.

### Phase 4: Baselines, universe and evaluation harness

Deliverables: B0–B3; the forecast universe with point-in-time membership; walk-forward runner with configurable refit frequency; metrics; DM test; the evaluation report generator.

Checks: planted-signal test passes; on the real data, the baseline report shows B0–B3 skill by year; universe size is between 15 and 35 (adjust thresholds in config if not, and record the change in §22).

### Phase 5: Models, intervals, gates and selection

Deliverables: M1, M2 (and M3 behind the `full` extra); conformal intervals; artifacts with hash sidecars; gates; selection with fallback; the champion refit on all data; the forward forecast; the full profile with Optuna tuning on the tuning period. Run the full profile once on the real data and commit the tuned default hyperparameters to `config/models/` (tuning-period results only).

Checks: default-profile train and evaluate finish in under 15 minutes on the owner's machine; G-PLAUS has not fired; the evaluation report contains the gate table for all models; determinism and round-trip tests pass.

### Phase 6: Publish, serve and frontend changes

Deliverables: contract v1.1 changes and regenerated types; the publisher; `report.json` and `site.json`; `nsefc serve`; the frontend changes in §15.2; `web_dist` build and hash check; `nsefc run` orchestration with caching.

Checks: `uv run nsefc run` on a fresh clone opens the browser and every page works with real data; the repeat run reaches "Serving" in under 1 minute; contract and frontend tests pass; the banned-word and axe tests pass.

### Phase 7: CI, README and the fresh-clone test

Deliverables: `ci.yml` per §17; README per §18 with real results; screenshots; `docs/methodology.md`; `nsefc dev update-readme`.

Checks: CI is green on all three operating systems; a fresh clone in a new folder on Windows, with only `git` and `uv`, runs `uv run nsefc run` to a working app with no other steps; §21's acceptance criteria are all met.

---

## 21. Acceptance criteria

| ID | Criterion |
|---|---|
| AC-01 | A fresh clone on Windows, macOS and Linux runs `uv run nsefc run` to a working app with only `git` and `uv` installed |
| AC-02 | The default run completes in under 20 minutes on a 4-core, 8 GB laptop; a repeat run reaches "Serving" in under 1 minute |
| AC-03 | The dataset in `NSE Data/` is copied, hash-verified and recorded with its citation (D-10); `--source-dir` and `--sample` work |
| AC-04 | `data/` contains nothing in git except `.gitkeep` and `README.md`. `NSE Data/` is committed by the owner's decision (D-10) and its citation is shown wherever the data is used |
| AC-05 | Every data defect found in the Phase 0 audit is handled by a documented rule and counted in the data audit report |
| AC-06 | The full leakage suite, including the random-walk null and planted-signal tests, passes |
| AC-07 | B0–B3 and at least two ML candidates are evaluated walk-forward; the holdout is used only for confirmation and headline numbers |
| AC-08 | A champion is selected by the gates in §11.4, honestly named, and may be a baseline |
| AC-09 | Every forecast-universe security has a forecast with an 80% range, or a valid `unavailable_reason` |
| AC-10 | The app shows the homepage, stock pages and an About page with results, methodology, limitations, attribution and contact links |
| AC-11 | The banned-word test, the disclaimer on every forecast, and axe checks pass |
| AC-12 | CI is green on all three operating systems without secrets or network data access |
| AC-13 | The README presents the results as skill against a no-change guess, never as an "accuracy" percentage of price |

---

## 22. Decisions and known limitations

### 22.1 Decisions

| ID | Decision | Reason |
|---|---|---|
| D-1 | Local-first; no cloud, scheduling or hosting | The goal is a cloneable demonstration; removes cost, secrets and redistribution concerns |
| D-2 | Superseded by D-10 (was: the Mendeley dataset is downloaded at runtime and never committed) | |
| D-3 | No database; Parquet and JSON files | Data is small; fewer moving parts; easy to inspect |
| D-4 | Champion selected automatically on each run, by fixed gates | Replaces Draft 1.0's pull-request promotion, which only makes sense for a production service |
| D-5 | No back-adjustment for corporate actions; events excluded by the band rule | Avoids building a corporate-actions source; honest and simple; documented limitation |
| D-6 | Frozen hyperparameters in the default profile; tuning only in the full profile | Fast first run; trustworthy holdout |
| D-7 | Prebuilt frontend committed inside the package | Users need neither Node.js nor pnpm |
| D-8 | Standard-library HTTP server | No extra dependency for serving a few static files locally |
| D-9 | Pickle-based model files allowed only for locally produced, hash-checked artifacts | Resolves MF-7 without banning scikit-learn pipelines |
| D-10 | **Owner decision (16 Oct 2026).** The data is the committed `NSE Data/` folder, cited as Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026", Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1. No download client and no `--dataset-version`; the licence field stays empty until the owner confirms it on the dataset page | `data.mendeley.com` was unreachable from the build environment, and the files were already in the repository. The citation appears in the run summary, the app, the README and the published JSON |
| D-11 | Index levels (codes starting with `^`) go to `canonical/indices.parquet`; bars carry an `is_event` column for PRC-01 events | Index rows are not securities; the publisher and features read one flag instead of recomputing the band rule |
| D-12 | DAT-03 checks each row's year against the year in its file's name; IMP-01 rejects imported sessions on or before the dataset's last session | The dataset states its range per file, which is how the 2017 file's 2015-dated block was caught |
| D-13 | Forecast-universe turnover threshold KES 150,000 (median `volume × close` over 250 sessions), not KES 1 million | KES 1 million gave 8 to 15 securities; 150,000 gives 16 to 29 (median 20), inside §20 Phase 4's 15 to 35. Chosen on universe size before any model result was seen. With the 2026 files the range is 16 to 31 |
| D-14 | Corrections are keyed to a file's SHA-256 and a line range; a rule that matches nothing, or would create a duplicate key, stops the ingest. The synthetic sample's planted misdated block is fixed by rule SAMPLE-01, keyed to the generated file's hash | A correction can never apply silently to a different file, and the sample exercises the same machinery as the real data |
| D-15 | `high` and `low` are set to null on rows with no trades | The source repeats stale quotes on untraded days; null keeps `(H − L) / C` honest |
| D-16 | import-linter contracts for the 2.0 layout: `domain` is pure; `features` cannot import `targets`, models, evaluation or anything downstream; acquire, ingest and quality never import ML or publishing; publishing and serve never import ML; only the CLI imports `pipeline` | Encodes L2 and the stage boundaries so a leak or a cycle fails CI |
| D-17 | §10.2's "Huber variant" of M1 is a separate candidate (`huber`, scikit-learn `HuberRegressor` in the same pipeline), evaluated through the gates like Ridge | Gives the linear family a robust loss that matches the median target without changing Ridge |
| D-18 | The walk-forward starts 250 held sessions before the selection period (`calibration_warmup_sessions`), and those predictions are used only to calibrate intervals | The rolling conformal window (§12) then has 250 sessions of out-of-sample scores on the first selection day, so selection-period coverage is honest from the start |
| D-19 | A universe security whose gap-guard window contains a PRC-01 event or a missing session gets no forecast, with the new reason `RECENT_PRICE_EVENT` (or `INSUFFICIENT_HISTORY`) | The forecast must obey the same gap guard as training (§8.4); the reason tells the user why |
| D-20 | B3 is fitted by least absolute deviations (IRLS) per security on the trailing 500 sessions, with at least 50 return pairs | The champion is judged on MAE, so the baseline it must beat is fitted on the same loss |
| D-21 | EWMA volatility uses weights over the 60-session gap-guard window, renormalised | An infinite EWMA would reach back past events and missing sessions and break truncation invariance |
| D-22 | LightGBM and CatBoost early-stop on the last 10% of sessions in each training window and keep the best iteration; they are not refit on the full window | One fit per refit keeps the default run inside its time budget; the validation slice is still strictly before the test window (L5) |
| D-23 | The volume ratio feature is `ln((1 + volume) / (1 + 20-session median volume))` | Bounded and defined when the median is zero, which is common for thin stocks |
| D-24 | Market features (equal-weighted return, breadth) use all ordinary shares, not only the forecast universe | They do not depend on a membership rule that changes at each refit, and every stock's features share one market series |
| D-25 | G-DIR is a one-sided z-test (α = 0.05) of the model's directional accuracy against the best trivial sign rule; G-BASE requires a paired one-sided DM p < 0.10 against the best of B1 to B3, otherwise the simpler model wins | Makes "not significantly worse" and "not significantly better" in §11.4 precise and testable |
| D-26 | Contract v1.1 adds, beyond §13.3's list, `contract_version`, the `doi`, `url` and `title` dataset fields, `target_from_calendar`, the `large_move` event type and `RECENT_PRICE_EVENT`; `report.json` and `site.json` live inside the release folder | Each addition is something the frontend shows; release folders keep every page on one release |
| D-27 | `--dataset-version` is removed; `nsefc dev` groups the maintainer tools (`contract`, `web-hash`, `update-readme`, `calendar`); `Claude outputs/` and other Phase 0 delivery leftovers are removed or archived | Follows from D-10 and §4.2 |
| D-28 | The publish fingerprint includes the publishing machine's date | `target_in_past` depends on today's date, so a run on a later day republishes instead of reusing a stale flag |
| D-29 | Each stage's fingerprint also covers the source code it depends on (`pipeline/context.py`, `STAGE_CODE`) | An updated clone never reuses results computed by older code; a change to publishing code re-publishes without retraining |
| D-30 | **Open owner decision (§0.6).** The full profile was run once on the real data (16 Oct 2026, data to 31 Oct 2025) and stopped at G-PLAUS: holdout directional accuracy LightGBM 67.6%, CatBoost 66.7% (> 65%). `nsefc dev tune` then tuned Ridge, Huber and LightGBM on the tuning period only; with those values the default run also stopped at G-PLAUS (LightGBM holdout 66.1%). The tuned values are therefore recorded, commented out, in `config/models/*.yaml` and **not** active; the default profile keeps §10.2's initial values, fixed before any result was seen, and passes every check (LightGBM holdout 64.0%, and 63.2% once the 2026 files were added). With the 2026 files the tuned values pass as well, just under the tripwire (64.8%), but the champion is still the no-change guess and the tuned LightGBM is weaker in the selection period (skill −0.01% against +0.14%). No gate threshold was changed | Changing G-PLAUS after seeing results needs the owner. G-PLAUS also has no minimum sample size, so imported sessions that extend the holdout could trip it. The evidence points to a genuine effect rather than a leak: features are exactly truncation-invariant on the real panel at 12 random dates, the random-walk null test passes, and the tuned LightGBM calls direction on only 9% of rows (66% right), 74% of them continuing the day's move, where the plain last-sign rule scores 59%. Options for the owner: keep the initial values (current state, recommended: more room under the tripwire and the stronger selection result); activate the tuned values, which pass on the current data but would stop the run if imported sessions pushed their direction score past 65%; or raise `gates.plaus_direction_max` (for example to 0.70) as well, and say in the README that the gate was changed after results were seen |
| D-31 | Rolling statistics in `features/` are computed window by window (`sliding_window_view`), not with pandas' running sums | Each value then depends only on its own window, so truncation invariance and cross-security independence hold exactly; pandas' running variance carried rounding of about 1e-8 from earlier rows of other securities |
| D-32 | Isolated weekdays with no data stay missing sessions and trigger the gap guard, as §6.3 and §8.4 say | It is the documented rule, but it costs data: 26 isolated missing weekdays (and the gaps in 2020 and at the end of 2025) exclude 1,128 of 4,682 sessions from modelling. If the owner confirms some of them as market closures (for example 28-30 Nov 2023), recording them as holidays in `config/calendar/nse_holidays.yaml` restores those rows |
| D-33 | `nsefc dev tune` runs only the full profile's tuning step and prints the values to freeze; the full profile saves `tuned.json` as soon as tuning ends | A G-PLAUS stop later in a full run no longer loses the tuning result, and a maintainer can tune without the monthly walk-forward |
| D-34 | Report gates carry a plain-language `name` (contract v1.1), and the app never shows the raw gate ids | The id G-HOLD would put the banned word "hold" on screen (§15.3) |
| D-35 | Raw copies sit flat in their folder under their own file names (a short hash prefix only if two names clash), the manifest records each file's `original` path, and temporary files have short names | The source's nested folder names made the raw copy's temporary paths about 270 characters long under a typical Windows clone, beyond the 260-character limit; the first real run on Windows would have failed (found in review) |
| D-36 | `predict` and `publish` refuse outputs computed from older data, settings or code ("run `nsefc train` first"), checking the stamps' lineage | Running stage commands out of order (for example `import`, `ingest`, then `predict`) would otherwise reuse a stale forecast or mix releases |
| D-37 | The dataset attribution shown to users (citation, licence, DOI) is read from `reference/mendeley.yaml` when publishing, and `acquire` refreshes the manifest's record when it changes | Filling in the licence then takes effect on the next run without copying or retraining anything (§5.3) |
| D-38 | Publishing keeps the previous release folder beside the new one (same contract version only) | A page that is already open keeps reading a complete release until it fetches the new `status.json` |
| D-39 | The "sign of the last return" rule in G-DIR is scored only on rows where it makes a call (the last return was non-zero), as models are | Counting its non-calls as misses understated it by up to 8 points and favoured the models; a metric correction found in review, not a threshold change. No gate outcome on the real data changed |
| D-40 | Prices in `prediction.json` are derived from the rounded last close; a stock outside the forecast universe is told which rules decide membership, and a security with no recent prices is described as no longer quoted | Keeps every published forecast valid against the contract for any source precision, and replaces a reason ("trades too rarely") that was wrong for most such stocks |
| D-41 | Dataset CSVs are copied and hashed with Windows line endings (CRLF) converted to LF | Git stores the files with LF (`.gitattributes`), but the Mendeley downloads and the owner's Windows checkout have CRLF, so the same file had two SHA-256 values. Corrections are keyed by hash (§6.4), so on the owner's machine they would not have applied and ingest would have stopped on the misdated blocks (found at delivery) |
| D-42 | Visual redesign at the owner's request: cream, near-black and deep blue tokens (`web/src/styles/tokens.css`), Inter Tight ExtraBold for headlines and the two hero numbers, Inter for everything else, three self-hosted woff2 files (SIL OFL 1.1). Routes, data fetching, the contract, component logic and page content are unchanged | The owner likes the calm, big-type style of tihada.com. `docs/design/redesign.md` records the qualities taken from it, the measured contrast ratios (all text at least 5.2:1), the font licences and the checks (axe in both modes at 1440px and 360px) |

Add new decisions here during implementation, one short paragraph each.

### 22.2 Known limitations (also stated in the README and About page)

1. **Historical only.** The forecast is for the session after the dataset ends, which is in the past. The tool demonstrates the method and its measured skill; it does not track the market live.
2. **Dataset quality.** The dataset has gaps (July to December 2020, November to December 2025), duplicates and misdated rows; they are handled by rules, but unknown errors may remain.
3. **No corporate-action adjustment.** Sessions with moves beyond the price band are excluded from modelling, which removes some genuine large moves.
4. **Low signal.** Any skill over no-change is likely small, and part of it comes from mechanical effects of VWAP closes and thin trading, which the AR(1) baseline measures.
5. **Not investment advice.**

---

## 23. Future work (not part of this build)

1. **Live data.** An optional `nsefc fetch` command that adds recent sessions from a licensed or permitted source, then a forward-test log that freezes each evening's forecasts and scores them later. Requires resolving data licensing first (Draft 1.0 §8.5, archived).
2. **Weekly horizon.** A separate five-session model; the schema already carries `horizon_sessions`.
3. **Corporate actions.** A reviewed `corporate_actions.csv` and back-adjusted series.
4. **Reporting agent.** An LLM-written daily or weekly summary generated from `report.json` and the forecasts, with every number checked against the data.
5. **Hosted demo.** A static build of `data/api/v1/` published alongside the frontend, only after confirming the dataset licence permits redistribution of derived results.

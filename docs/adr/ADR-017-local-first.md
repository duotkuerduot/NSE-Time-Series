# ADR-017: Local-first, one-command tool

Status: accepted, 16 October 2026. Supersedes ADR-003 (data providers), ADR-014 and ADR-015
(Draft 1.0's hosting and promotion decisions, archived in
`docs/archive/ENGINEERING-draft-1.0.md`), and the cloud parts of ADR-016.

## Context

Draft 1.0 designed a hosted platform: nightly scraping, Cloudflare R2, scheduled GitHub
Actions, a CDN-served API, pull-request model promotion and a legal gate before launch. Its
Phase 0 showed the costs: licensed sources, secrets, a source spike that could not reach the
exchange from the build environment, and redistribution rules for every number published.

## Decision

The product is a local tool. Anyone clones the public repository and runs
`uv run nsefc run`. The tool reads the dataset committed in `NSE Data/` (or another local
folder, or a generated synthetic sample), builds a clean panel, trains and evaluates the
models walk-forward, selects a champion with fixed gates, publishes static JSON and serves the
existing React app on 127.0.0.1. Nothing is hosted, scheduled, downloaded or uploaded, and
nothing derived from the data is committed.

**Amendment, 16 October 2026 (ENGINEERING.md D-10).** ENGINEERING.md 2.0 first planned to
download the dataset from Mendeley Data at runtime. The owner decided instead to use the copy
already committed in `NSE Data/`, cited as Wanjawa, Barack (2026), "Kenya Nairobi Securities
Exchange (NSE) All Stocks Prices 2026", Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1. There is
no download client; the licence is recorded once the owner confirms it on the dataset page.

## What changed in the repository

- Deleted: the R2 object store and compare-and-swap pointers, the R2 bootstrap script, the
  source-spike tooling and workflow, the runbooks, the production and dry-run configuration,
  `.env.example`, `migrations/` and `research/`.
- Archived in `docs/archive/`: Draft 1.0, the Phase 0 status and reports, the source
  evaluation, and the legal enquiry drafts (they may be reused if live data returns).
- Kept: the package skeleton, domain types, the calendar, the API contract, the web app,
  CI checks, and the Phase 0 findings about the data, now encoded as corrections.

## Consequences

- $0 cost, no accounts, no secrets, no network access at runtime; CI tests run on a synthetic
  dataset only.
- Results are historical: the forecast is for the session after the dataset ends. Live data
  is future work and needs the licensing questions in the archived ADR-003 answered first.
- The champion is chosen automatically on every run by fixed gates, instead of by a
  promotion pull request. A baseline can win, and the app says so.

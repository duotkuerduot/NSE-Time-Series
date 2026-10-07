# NSE Daily Stock Prediction Platform

Ingests Nairobi Securities Exchange end-of-day data, validates it, forecasts the next
session's official closing price with an 80% expected range for liquid equities, and
publishes everything as a static JSON API read by a small web app. The design is in
[ENGINEERING.md](ENGINEERING.md); the design review is in the KARD project.

**Status: Phase 0** (repository, contract, calendar and source spike). Progress against the
Phase 0 acceptance criteria is tracked in [docs/phase-0-status.md](docs/phase-0-status.md).

## Quick start

Requires Python 3.11+ with [uv](https://docs.astral.sh/uv/), and Node 20+ with pnpm for the
web app.

```bash
uv sync                                   # Python environment from uv.lock
uv run nsefc config validate              # every environment's configuration loads
uv run nsefc calendar holidays 2026       # weekday market closures
uv run nsefc calendar next-session 2026-10-19   # -> 2026-10-21 (Mashujaa Day)
uv run nsefc contract validate            # fixtures match the API contract
uv run pytest                             # unit, property and contract tests

cd web && pnpm install && pnpm dev        # the app, served from contract fixtures
pnpm test                                 # unit and page tests (jsdom)
pnpm exec playwright install chromium && pnpm e2e   # real-browser smoke test with axe
```

CI runs the same checks on every pull request (ENGINEERING.md 28.2), plus `pip-audit` and
`pnpm audit`.

## Phase 0 tools

| Command | What it does |
| --- | --- |
| `nsefc data profile --data-dir "NSE Data"` | Coverage profile of the historical CSVs |
| `nsefc calendar reconcile --data-dir "NSE Data"` | Calendar versus the dates that have trading data |
| `nsefc contract export [--check]` | Write (or check) JSON Schema in `contracts/api/v1` |
| `nsefc spike probe` | Has each source published the latest session? Archives what it finds |
| `nsefc spike backcheck --from 2026-01-01 --to 2026-10-07` | How far back each source's archive reaches |
| `nsefc spike report` | Availability and first-seen times from the observations so far |

Raw files from third-party sources are archived only to private storage (`var/`, git-ignored,
or the private R2 bucket). Never commit them or upload them as public CI artifacts: that
would redistribute them, which the NSE Market Data Policies restrict.

## Repository layout

```text
config/       layered settings, calendar, providers, policies (all reviewed by pull request)
contracts/    JSON Schema for the static API, plus fixture releases
src/nsefc/    the Python package (modular monolith; import rules in pyproject.toml)
tests/        unit, property, leakage, golden, integration and end-to-end tests
web/          Vite + React + TypeScript single-page app
docs/         ADRs, runbooks, source evaluation, legal correspondence drafts
reports/      generated audit reports committed as decision records
NSE Data/     historical dataset (Mendeley Data, CC BY 4.0), read by the historical provider
```

## Data attribution

The historical files in `NSE Data/` come from the "Nairobi Securities Exchange (NSE) All
Stocks Prices" datasets on Mendeley Data, published under CC BY 4.0. Market data originates
from the Nairobi Securities Exchange. Public display of NSE data needs the licences and
attribution described in the NSE Market Data Policies; see `docs/legal/`.

# Contributing

Issues and pull requests are welcome. This guide covers setting up, running the checks, and
the rules every change keeps. [architecture.md](architecture.md) explains how the code fits
together.

## Set up

You need [git](https://git-scm.com/downloads) and [uv](https://docs.astral.sh/uv/). Working
on the web app also needs [Node.js](https://nodejs.org/) 20 or later (CI uses 22) and
[pnpm](https://pnpm.io/installation) 10.

```bash
git clone https://github.com/duotkuerduot/NSE-Time-Series.git
cd NSE-Time-Series
uv sync
uv run nsefc run --sample --no-serve
```

`uv sync` installs Python 3.12, the package and the development tools. The sample run checks
the whole pipeline on synthetic data in about two minutes. For the real data, put the
Mendeley files in `data/source/` ([data/README.md](../data/README.md)).

## Checks

CI runs these on every push and pull request, with no secrets and no data downloads. Run them
before opening a pull request.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run nsefc dev contract --check
uv run nsefc dev contract --validate contracts/api/v1/fixtures
uv run nsefc dev web-hash --check
uv run pytest
```

For the web app:

```bash
pnpm -C web install --frozen-lockfile
pnpm -C web check:types
pnpm -C web lint
pnpm -C web typecheck
pnpm -C web test
pnpm -C web build
pnpm -C web check:size
```

The browser tests need Playwright's Chromium once
(`pnpm -C web exec playwright install chromium`). `pnpm -C web e2e` runs them against the
contract fixtures. To run them against the real server on sample results, start the server in
one terminal:

```bash
uv run nsefc run --sample --no-serve
uv run nsefc serve --no-browser --port 8765
```

and run the tests in another:

```bash
NSEFC_E2E_URL=http://127.0.0.1:8765 pnpm -C web e2e
```

In Windows PowerShell, set the variable first: `$env:NSEFC_E2E_URL = "http://127.0.0.1:8765"`,
then run `pnpm -C web e2e`.

CI also runs `uv run nsefc run --sample --no-serve` on Windows, macOS and Linux, and audits the
locked dependencies with pip-audit and `pnpm audit`.

## Tests

| Where | What it checks |
| --- | --- |
| `tests/unit/` | Each module: acquire, ingest, quality checks, panel rules, calendar, models, metrics, intervals, gates, publishing, the API contract, the server, the CLI and the repository rules |
| `tests/property/` | Hypothesis properties of the trading calendar |
| `tests/leakage/` | The leakage suite: truncation invariance, future perturbation, cross-security bleed, label alignment, the static scan of `features/`, the random-walk null test, the planted-signal test, determinism and model file integrity |
| `tests/integration/test_pipeline_sample.py` | The whole pipeline on the sample through the CLI: published files validate, every universe stock has a forecast or a reason, repeat runs are cached and byte-identical, and the plausibility tripwire and contract failures give exit codes 30 and 40 |
| `tests/integration/test_real_dataset.py` | Acquire and ingest of the files in `data/source/` reproduce the counts and corrections in [data/README.md](../data/README.md); skipped when the files are not there |
| `web/src/**/*.test.ts(x)` | vitest: formatting, search, staleness, the pages, and the language rules |
| `web/e2e/smoke.spec.ts` | Playwright with axe, against the contract fixtures |
| `web/e2e/sample.spec.ts` | Playwright with axe, against `nsefc serve` on sample results |

## Making changes

**The API contract.** Edit the models in `src/nsefc/api/v1.py`, then regenerate everything
that derives from them:

```bash
uv run nsefc dev contract
uv run python scripts/make_fixtures.py
pnpm -C web gen:types
```

The first writes the JSON Schema in `contracts/api/v1/`, the second rebuilds the fixture
release in `contracts/api/v1/fixtures/` (seeded, illustrative values), and the third
regenerates the app's types in `web/src/api/types/`.

**The web app.** `pnpm -C web dev` serves the app with the contract fixtures at `/api/v1`, so
every page renders without a pipeline run. After a change, run `pnpm -C web build` and commit
`src/nsefc/web_dist/` with its `.source-hash`; CI fails if the committed build is older than
its sources.

**Results.** After a change that affects results, run the real data
(`uv run nsefc run --no-serve`), then `uv run nsefc dev update-readme` to refresh the README's
results block, and update [results.md](results.md) from `data/reports/evaluation.md`.

**Hyperparameters.** `uv run --extra full nsefc dev tune` tunes the candidates on the tuning
period (2013 to 2017) and prints values to freeze in `config/models/*.yaml`.

**The trading calendar.** `uv run nsefc dev calendar 2026` lists a year's weekday closures.
The calendar in `config/calendar/nse_holidays.yaml` covers 2005 to 2026; add the next year's
holidays, including the moon-dependent ones, before December. Every entry has a status and a
source.

**Corrections.** A rule in `reference/corrections.yaml` names the file and its SHA-256 (with
LF line endings), the inclusive line range (the header is line 1), the action (`redate` with
`from` and `to`, or `drop`) and the evidence. Ingest stops if a rule matches no rows or would
create a duplicate.

**Securities.** `reference/securities.csv` holds every ticker's name, sector, instrument type
and former tickers. `uv run python scripts/build_securities.py data/source` prints a draft
from the dataset files, which is then checked by hand.

## Rules every change keeps

* **Honest results.** Gate thresholds are fixed; no feature, model, hyperparameter or gate
  changes because of holdout results. Results are reported as skill against the no-change
  guess, and a baseline can be the champion.
* **No leakage.** Feature code reads the panel only through the as-of door
  (`features/panel.py`); the leakage suite and the import-linter contracts must pass.
* **The app's language.** No "buy", "sell", "hold", "target price", "signal",
  "recommendation", "guaranteed", "will reach" or "certain", and every forecast carries
  "Research forecast, not investment advice." The language test enforces it.
* **Accessibility.** WCAG 2.2 AA: axe passes, targets are at least 44 × 44 px, focus is
  visible, every chart has a text summary, and pages work at 360 px wide.
* **Every platform.** The tool runs on Windows, macOS and Linux with only git and uv: no
  shell scripts or `make` in the main path, no Node.js to run it, `pathlib` for every path.
* **No data in git.** Nothing under `data/` is committed except its READMEs and `.gitkeep`,
  and neither are the Mendeley files.
* **Pull requests** follow the checklist in
  [.github/pull_request_template.md](../.github/pull_request_template.md).

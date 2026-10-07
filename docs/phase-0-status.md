# Phase 0 status

As of 8 October 2026. Tracks the Phase 0 deliverables and acceptance criteria in
ENGINEERING.md ("Phase 0: Architecture, repository setup and source spike"). Decisions taken
along the way are in [ADR-016](adr/ADR-016-phase-0-decisions.md).

**Summary.** The build work is done and passes every check locally. Phase 0 cannot close until
two things happen outside the code: the source spike has to run for 10 sessions on GitHub,
and the infrastructure and legal steps need your accounts.

## Acceptance criteria

| Criterion | Status | Evidence |
| --- | --- | --- |
| CI passes on the skeleton | **Passes locally.** The first GitHub run starts when the code is pushed | `.github/workflows/ci.yml`; results below |
| Every candidate source observed for at least 10 consecutive sessions, with samples archived | **Not started.** The spike runs on GitHub's runners after the push. Files are archived only once R2 credentials exist; until then only metadata is kept | `.github/workflows/source-spike.yml`, [source evaluation](sources/source-evaluation.md) |
| Primary and secondary providers named, with evidence | **Provisional.** Primary candidate: the NSE daily price list. Validator: the Kingdom Securities wrap. KenyaStocks and AFX are excluded | [ADR-003](adr/ADR-003-data-providers.md) |
| A2, A4 and A5 answered, or left open with an owner | **A4 and A5 answered. A2 open**, owned by the repository owner and answered by the spike | [Assumptions](#assumptions) |
| The calendar reproduces every known 2024–2026 holiday | **Done.** 2024 and January–October 2025 closures match the trading data exactly. 2026 matches the published holiday list | `tests/unit/test_calendar.py`, [reconciliation](../reports/calendar-reconciliation.md) |
| The frontend renders every page from fixtures | **Done.** Covered by page tests in jsdom and by Playwright on mobile and desktop viewports | `web/src/pages/pages.test.tsx`, `web/e2e/smoke.spec.ts` |

Results of the full local run on 8 October 2026 (Linux, Python 3.12, Node 22), before the first push:

- **Python:**
  - 154 tests pass.
  - ruff, format and mypy (strict) are clean.
  - All 17 import-linter contracts hold.
  - Every configuration environment validates.
  - The schemas are current and the fixtures validate.
  - pip-audit finds no known vulnerabilities.
- **Web:**
  - Generated types are current, and ESLint and tsc are clean.
  - 23 unit and page tests pass.
  - The build is 94 KB of initial JavaScript gzipped, against a 150 KB budget.
  - 14 Playwright and axe checks pass, with no serious or critical WCAG 2.1 AA findings.
  - pnpm audit is clean.

## Assumptions

**A4: the official price is a volume-weighted average.**

- **Answer: yes.**
- NSE Equity Trading Rules (July 2025):
  - 7.6.1: the closing price is the session's volume-weighted average price.
  - 7.6.6: a session with fewer than 100 shares traded keeps the previous price.
- The domain model follows this: `DailyBar.price_set` means at least 100 shares traded, and the contract states `price_basis: vwap`.
- **Still to do:** the empirical check, VOL-02 (turnover divided by volume is close to the close). It needs volume and turnover for the same session, which means the NSE list together with the Kingdom wrap. That check belongs to Phase 2.

**A5: a daily price band of ±10%.**

- **Answer: yes.**
- The rules set ±10% on the main board and ±5% on the Recovery Board, with the exceptions listed in Rule 5.10.5.
- The 2007–2025 data agrees:
  - 99.82% of price-setting rows lie within 10% of the previous price, allowing a tolerance of one tick.
  - That is 384 exceptions in 211,643 rows.
- The largest exceptions have known causes:
  - rights issues: the `-R` codes;
  - share splits: KCB in 2007, Equity in 2009 and KPLC in 2010;
  - new listings.
- The Phase 1 audit classifies every exception. The full table is in [historical data coverage](../reports/historical-data-coverage.md).

**A2: a free source publishes complete end-of-day data on the evening of T.**

- **Status: open.**
- **Owner:** the repository owner (@duotkuerduot).
- **Evidence will come from:** the spike's first 10 sessions, followed by the decision in ADR-003.
- **Early sign:** Kingdom's 7 October wrap was online by 20:08 EAT.
- **Not yet measured:** the NSE list's publication time, and whether its PDF can be parsed without OCR.

## Deliverables

| Deliverable | State | Where |
| --- | --- | --- |
| Repository skeleton (§33) with modules stubbed and import-linter contracts | Done | `src/nsefc/`, `pyproject.toml` |
| CI for Python and web (§28.2) | Done. The migration check and parser golden tests arrive with migrations (Phase 1) and parsers (Phase 2). Secret scanning is a repository setting (runbook step 3) | `.github/workflows/ci.yml` |
| `domain` types | Done | `src/nsefc/domain/` |
| Settings loading and validation | Done | `src/nsefc/config.py`, `config/` |
| Trading calendar for 2005–2026 | Done | `config/calendar/nse_holidays.yaml`, `src/nsefc/calendar/` |
| R2 buckets, scoped tokens, GitHub environments | Scripted and documented; needs your Cloudflare and GitHub accounts | `deploy/cloudflare/bootstrap.py`, [runbook](runbooks/infra-bootstrap.md) |
| API contract: Pydantic models, JSON Schema, TypeScript types, a fixture per resource | Done | `src/nsefc/api/`, `contracts/api/v1/`, `web/src/api/types/` |
| Source verification spike and `source-evaluation.md` | Tooling done; observation starts after the push | `src/nsefc/ingestion/spike.py`, [source evaluation](sources/source-evaluation.md) |
| Legal enquiries to the exchange and candidate sources | Drafted, not sent | [NSE](legal/nse-data-enquiry.md), [Kingdom Securities](legal/kingdom-securities-enquiry.md) |
| ADR-003 updated with the chosen providers | Provisional update; final after the spike | [ADR-003](adr/ADR-003-data-providers.md) |

## Historical data: findings for the Phase 1 audit

The full reports are [historical data coverage](../reports/historical-data-coverage.md) and
[calendar reconciliation](../reports/calendar-reconciliation.md).

**Coverage**

- 19 daily files cover 2 January 2007 to 31 October 2025.
- There is no data for July–December 2020: 133 weekdays.
- There is nothing after October 2025. From 1 January 2026 to today that is about 193 sessions, so the 2026 backfill depends on the spike's backcheck (review MF-2).

**Data quality**

- The files use three header variants and three date formats; the reader handles all of them.
- There are duplicate keys: 152 in 2009 and 64 in 2017.
- One date fails to parse in each of 2014 and 2018.
- The 2017 file contains rows dated Saturday 9 May 2015. These are almost certainly 9 May 2017, which otherwise has no data.

**Calendar against the data**

- 30 weekdays have no data and no known closure. They are listed for the audit and deliberately left out of the calendar.
- Two days the holiday rules would close were full trading sessions: 27 December 2010 and 27 December 2011. They are recorded as held sessions, because for history the data decides (§7.5).
- The calendar also gained two provisional entries that have no data to check against:
  - the 2005 referendum day;
  - Idd-ul-Azha on 31 July 2020.

## A second review of this phase

An independent pass over the Phase 0 code found ten problems. All are fixed and covered by tests:

- a fragment of a secret in configuration error messages;
- a spike that could not tell a blocked request from a missing file;
- contract checks that were too loose (timestamps without a time zone, unbounded rates) or too strict (rounded forecast returns);
- local storage writes that two writers could both win;
- a CI artifact step that skipped failed runs;
- several smaller CI gaps.

ADR-016 records the resulting rules.

## What needs you, in order

1. **Commit and push.** Review the new files, then commit and push them. CI runs on the push, and the spike starts on its schedule, every 15 minutes from 17:07 EAT on weekdays.
2. **Measure archive depth.** Run the `source-spike` workflow once by hand in `backcheck` mode, from 2026-01-01.
3. **Set up storage and secrets.** Create the R2 buckets and tokens and the `production` environment secrets (runbook steps 1–3). With them in place, the spike archives files privately instead of keeping only metadata.
4. **Send the enquiries.** Add contact details to the NSE and Kingdom Securities drafts and send them.
5. **After 10 sessions, close the spike.** Score the sources in the source evaluation, finalise ADR-003 and record the answer to A2 here. Phase 0 then closes.

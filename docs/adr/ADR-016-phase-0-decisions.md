# ADR-016: Phase 0 decisions and design-review amendments

Status: accepted, 8 October 2026. Extends ENGINEERING.md; where they differ, this record wins.
The review IDs (MF-, D-, ML-, P-, FE-) refer to the design review in the KARD project.

## Calendar

- The calendar lists statutory rules, moon-dependent dates and one-off closures, each with a
  status (rule, confirmed, listed, provisional) and a source. 2026 adds Idd-ul-Azha (27 May) and
  Mazingira Day (10 October), both missing from ENGINEERING.md 7.5.
- History is reconciled against the repository's trading data (`nsefc calendar reconcile`).
  Weekday gaps with no known reason stay out of the calendar and are listed in
  reports/calendar-reconciliation.md for the Phase 1 audit.
- A holiday on a Sunday moves to the next weekday that is not itself a holiday. The data confirms
  the cascade: Christmas on Sunday closed both 26 and 27 December in 2016 and 2022.
- Where the data shows a full session on a day the rules would close (27 December 2010 and
  27 December 2011), the calendar records a `held_session`: for history, the data wins (7.5).
- Entries that no data can confirm (2005-2006, and July-December 2020) are `provisional`,
  including the 2005 referendum day and Idd-ul-Azha on 31 July 2020.
- The calendar refuses dates outside its coverage (currently to 31 December 2026) instead of
  guessing; next year's moon-dependent dates must be added before December.

## Data model

- `SessionIngestStatus.MISSING_ACKNOWLEDGED` is a terminal state set by an audited command, so
  ingestion can move past an unrecoverable session (MF-1). Labels never span such a session.
- `DailyBar.price_set` (volume of at least 100 shares) is the modelling notion of "traded"
  (NSE Equity Trading Rules 7.6.6; D-5). `traded` (volume above zero) is kept for display.
- A prediction correction inserts a new revision plus a `PredictionSupersession` record; no
  prediction row is ever updated (MF-8).

## Storage

- Object stores offer `put_if_absent` (immutable objects) and `put_if_match` (compare-and-swap
  pointers). R2 implements both with S3 conditional writes, so the database pointer swap is a
  real compare-and-swap rather than check-then-write (MF-4). Dry runs get a read-only wrapper.
- Raw third-party files are stored only in the private bucket or the git-ignored `var/`
  directory, never in git or public CI artifacts (NSE Market Data Policies 4.5, 20.2).
- Both stores give `put_if_absent` the same contract: False when the object exists with the
  same bytes, an error when it exists with different bytes. The local store creates objects
  with a hard link from a finished temporary file and holds a lock file during a pointer
  swap, so concurrent writers in development and CI behave like R2's conditional writes.

## API contract (v1)

- Fields with defaults are still required in the published JSON Schema, because every file
  carries every field.
- Additions: `PredictionHistoryRow.model_id` and `TrackRecordSeries.model_label`, so the
  public record names the model behind each published forecast (FE-4), and
  `StockIndexItem.liquidity_rank`, which breaks search ties (24.3).

- Timestamps must carry an offset (`AwareDatetime`): a browser reads a bare timestamp as the
  viewer's local time, which would shift the stale banner. Error sizes are non-negative and
  shares lie in [0, 1]. A history file's `range` must match its file name.
- `predicted_close` must equal `last_close * (1 + predicted_return)` within rounding: KES 0.005
  for the close plus 0.00005 of the last close for a return rounded to 4 decimal places.

## Configuration

- `pipeline.preopen_cutoff_eat` is 08:45, the start of pre-trading (Rule 6.1.3; P-1): a forecast
  published after it is late.
- Environment variables override settings as strings (JSON for lists); times must be quoted
  "HH:MM" in YAML, because YAML 1.1 reads an unquoted 22:00 as the number 1320.
- Configuration errors never echo input values (`hide_input_in_errors`): pydantic otherwise
  prints a truncated copy of the settings, whose tail is the last secret set.

## Scheduling and CI

- GitHub schedules use `timezone: "Africa/Nairobi"` (now supported) and minutes off the hour.
  Concurrency groups that must not drop runs use `queue: max` (MF-4).
- Every action is pinned to a commit SHA, enforced by tests/unit/test_repository.py, which
  parses the workflow YAML rather than grepping it.
- Pull requests also run `pip-audit` on the exported lockfile, `pnpm audit`, and a Playwright
  smoke test with axe (WCAG 2.1 AA, serious and critical findings fail) on mobile and desktop
  viewports. The homepage's search label is its h1.
- Python 3.11+ managed by uv; the web app pins TypeScript 6.0 because typescript-eslint does not
  yet support TypeScript 7.

## Language rules

- The banned-word test matches whole words and phrases, and the data-hold state reads "paused",
  not "on hold" (MF-10).

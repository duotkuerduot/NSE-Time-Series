# Source evaluation (Phase 0 spike)

Status: in progress. Day 0 of the 10-session observation window (ENGINEERING.md 8.3). This file
becomes the evidence for the final ADR-003.

## How the spike runs

- `.github/workflows/source-spike.yml` runs `nsefc spike probe` every 15 minutes from 17:07 to
  22:52 EAT on weekdays and once at 06:40 the next morning. Each observation records the time,
  HTTP status, size and SHA-256 of what the source served, and whether it was a real document.
- With R2 credentials in the `production` GitHub environment, files are archived to the private
  bucket; without them, only observation metadata is kept (90-day workflow artifacts).
- `nsefc spike backcheck --from 2026-01-01 --to <today>` measures how far back each archive
  reaches, which decides the 2026 backfill (review MF-2). Run it once from the workflow's manual
  trigger; add `--store` once R2 exists to archive what it finds.
- `nsefc spike report` summarises availability, archive reach and median first-seen time.
- Every request ends in one of four outcomes: `available`, `not_found` (404, 410, or a 200
  that is not a PDF), `blocked` (401, 403, 429, 451) or `error` (5xx, network). Only
  `not_found` says anything about an archive; a run with blocked or failed requests says so
  instead of reporting a shallow archive. 429 and 5xx responses are retried, honouring
  `Retry-After` up to two minutes.
- WordPress upload folders (`/uploads/2026/10/`) name the month a file was uploaded. For
  sessions in the last week of a month the spike also tries the next month's folder, and
  records which URL answered. A re-upload that WordPress renamed (for example `...-1.pdf`)
  would still be missed; check any unexplained gap by hand on the source's listing page.
- Observations are saved one at a time, and the metadata artifact is uploaded even when a
  run fails, so a crash or a timeout loses at most the request in flight.

The development environments used so far could not reach nse.co.ke or
kingdomsecurities.co.ke, so the spike runs on GitHub's runners.

## Candidates, as checked on 7 October 2026

| Source | What it serves | Price basis | Terms | Status |
| --- | --- | --- | --- | --- |
| NSE daily equity price list | PDF at `dataservices/wp-content/uploads/DD-MON-YY.pdf` | VWAP (official) | NSE Market Data Policies v6/2026 | Primary candidate; check text extraction |
| Kingdom Securities Daily Market Wrap | PDF at `wp-content/uploads/YYYY/MM/Daily-Market-Wrap-DD-Mon-YYYY.pdf`; names, previous and current price, change, turnover (KES m) | VWAP (official) | Research disclaimer; redistribution not addressed | Validator candidate; online by 20:08 EAT on 7 Oct |
| KenyaStocks (kenyastocks.co.ke) | HTML; ticker, price, change, volume | Possibly last-traded since 11 Sep 2026 | Forbids republishing price tables at scale | Excluded |
| AFX (afx.kwayisi.org/nse) | HTML; showed a 20 Nov 2024 trading summary | Unknown | Not stated | Excluded (stale) |
| myStocks | Licensed NSE vendor; 20+ years of history | VWAP | Redistribution needs written consent | Licensed backfill candidate |
| AIB-AXYS Daily Market Watch | Volume report (used by KenyaStocks) | Unknown | Unknown | Find URL pattern |
| Repository `NSE Data` | Daily CSVs, 2007-01-02 to 2025-10-31 | VWAP ("Day Price") | CC BY 4.0 (check provenance) | Historical foundation |

## Scoring (after the legal review removes anything that fails it)

Completeness 30%, timeliness 25%, parse robustness 20%, history and archive depth 15%,
stability and track record 10% (ENGINEERING.md 8.3).

| Source | Completeness | Timeliness | Parse robustness | Archive depth | Stability | Score |
| --- | --- | --- | --- | --- | --- | --- |
| NSE price list | | | | | | |
| Kingdom wrap | | | | | | |

## Observation log

Add one line per day: date, sources available, first-seen times, notes.

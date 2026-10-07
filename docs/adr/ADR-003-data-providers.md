# ADR-003: Data providers (update 1, provisional)

Status: provisional, pending the 10-session spike. Supersedes the provisional assignment in
ENGINEERING.md section 36 (Kingdom primary, KenyaStocks secondary). Date: 8 October 2026.

## Decision so far

| Role | Provider | Why |
| --- | --- | --- |
| Primary candidate | NSE daily equity price list | Official source with the official price (session VWAP), volume, high and low, at a date-patterned URL |
| Validator candidate | Kingdom Securities Daily Market Wrap | Independent parse of the same prices; same-evening publication observed |
| Backfill candidate (licensed) | myStocks or another licensed NSE vendor | 20+ years of history, but redistribution needs the vendor's written consent |
| Historical foundation | Repository `NSE Data` (Mendeley Data, CC BY 4.0) | 2007-01-02 to 2025-10-31; see reports/historical-data-coverage.md |
| Excluded | KenyaStocks, AFX | KenyaStocks' terms forbid republishing price tables and it re-publishes Kingdom and Mansa data; AFX appears stale since November 2024 |

## Why the brief's assignment changed

- The Kingdom wrap carries no volume, high, low or deal count, so it cannot fill the canonical
  bar on its own (`volume` is NOT NULL in ENGINEERING.md 7.4). Its header row contains the
  session dates, so layout fingerprints must normalise dates before hashing.
- KenyaStocks (kenyastocks.co.ke; the .com domain does not resolve) is assembled from Kingdom's
  wraps, a broker's volume report and Mansa Markets, whose prices are credited as last-traded
  from 11 September 2026. It is not independent of Kingdom and may not share the VWAP basis,
  which would fail PRV-02 and MKT-04.
- Two re-publishers of one NSE feed confirm the parse, not the data. Cross-source agreement is
  described as a parse check.

## Open, owned by the spike

- Does the NSE price list parse without OCR? (A quick text extraction returned nothing.)
- First-seen publication times in EAT for both sources over at least 10 sessions.
- Archive depth back to 1 January 2026 (`nsefc spike backcheck`), which decides the 2026 backfill.
- Legal: the NSE Market Data Policies (v6/2026) require a data agreement and fees for end-of-day
  distribution, and a licence for derived works, indices and non-display use. See
  docs/legal/nse-data-enquiry.md. Using the Kingdom wrap as a validator needs Kingdom's
  consent: docs/legal/kingdom-securities-enquiry.md.

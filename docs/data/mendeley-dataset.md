# The NSE daily price dataset (Phase 1 findings)

Recorded 16 October 2026 (ENGINEERING.md Phase 1, §5, §6.2) and updated on 17 October 2026
for the 2026 files the owner added. Every *(verify)* in §5 and §6.2 is either answered here or
left open with a reason.

## Source and citation (decision D-10)

The tool reads the copy of the dataset committed in the repository's `NSE Data/` folder.
Nothing is downloaded. By the owner's decision (16 October 2026) the data is cited, wherever
it is used, as:

> Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026",
> Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1

`reference/mendeley.yaml` holds the citation, DOI and URL
(<https://data.mendeley.com/datasets/hvmhnp7f9r/1>). The citation is shown in the run
summary, in the app's footer and About page, in the README, and in `status.json`,
`report.json` and `site.json`.

## Open question for the owner: the licence

`data.mendeley.com` was refused by the network policy of the build environment, so the
dataset page, and with it the licence, could not be checked. The `licence` and `licence_url`
fields in `reference/mendeley.yaml` are therefore empty, and while they are, the run summary
and the app add a one-line notice that the data is for personal research use. To resolve it,
open the dataset page, copy the licence name (for example "CC BY 4.0") and its URL into
`reference/mendeley.yaml`, and run `uv run nsefc run` again: the notice disappears and the
licence appears next to the citation.

The folder's seven sub-folders are named after the Mendeley Data collections the files came
from, one per period; the 2026 collection is the one the citation names. They are cited as one
dataset, as the owner decided; if the owner later wants to cite each collection separately, the
citation text in `reference/mendeley.yaml` is the only thing to change.

## The files (verified)

Seven folders in `NSE Data/`, each holding its files directly. On 16 October 2026 the owner
added the 2026 folder and moved the other folders' files up out of an inner sub-folder (for
example `97hkwn5y3x-4/`, which has the form of a Mendeley dataset id and version). The tool
finds files at any depth, so the layout does not matter to it.

| Folder | Files | Period |
| --- | --- | --- |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2007-2012 | 6 price files | 2007-2012 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2013-2020 | 8 price files, 2 sector files | 2013 to 30 Jun 2020 |
| Nairobi Securities Exchange (NSE) All Stock Prices 2021 | 1 price file, 1 sector file | 2021 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2022 | 1 price file, 1 sector file | 2022 |
| Nairobi Securities Exchange (NSE) All Stocks 2023-2024 | 2 price files, 1 sector file | 2023-2024 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2025 | 1 price file, 1 sector file | 2 Jan to 31 Oct 2025 |
| Nairobi Securities Exchange (NSE) All Stocks Prices 2026 | 1 price file, 1 sector file | 2 Jan to 30 Jun 2026 |

| File | Bytes | Rows | First (equities) | Last | Codes | SHA-256 (prefix) |
| --- | --- | --- | --- | --- | --- | --- |
| `NSE_data_all_stocks_2007.csv` | 843,961 | 10,608 | 2007-01-02 | 2007-12-24 | 54 | `9cf31c14768d` |
| `NSE_data_all_stocks_2008.csv` | 849,672 | 10,583 | 2008-01-02 | 2008-12-31 | 54 | `c68a4142f79f` |
| `NSE_data_all_stocks_2009.csv` | 1,083,066 | 14,386 | 2009-01-02 | 2009-12-31 | 57 | `ac9bdb30a7f7` |
| `NSE_data_all_stocks_2010.csv` | 1,148,209 | 14,952 | 2010-01-04 | 2010-12-31 | 61 | `191a350bf9d8` |
| `NSE_data_all_stocks_2011.csv` | 1,137,773 | 14,931 | 2011-01-03 | 2011-12-30 | 59 | `f5e5a63d036b` |
| `NSE_data_all_stocks_2012.csv` | 1,218,332 | 16,044 | 2012-01-03 | 2012-12-31 | 67 | `ca2c76e96a64` |
| `NSE_data_all_stocks_2013.csv` | 1,221,420 | 14,889 | 2013-01-02 | 2013-12-31 | 58 | `30d0bedbae47` |
| `NSE_data_all_stocks_2014.csv` | 1,302,426 | 15,695 | 2014-01-02 | 2014-12-31 | 61 | `91ad2135c8f3` |
| `NSE_data_all_stocks_2015.csv` | 1,358,547 | 16,386 | 2015-01-02 | 2015-12-31 | 62 | `e3e821e6caa0` |
| `NSE_data_all_stocks_2016.csv` | 1,385,250 | 16,800 | 2016-01-04 | 2016-12-30 | 64 | `2c718a417822` |
| `NSE_data_all_stocks_2017.csv` | 1,396,341 | 16,981 | 2015-05-09 * | 2017-12-29 | 65 | `1f4f1f6adceb` |
| `NSE_data_all_stocks_2018.csv` | 1,460,278 | 17,650 | 2018-01-02 | 2018-12-31 | 66 | `87def7e669e4` |
| `NSE_data_all_stocks_2019.csv` | 1,514,466 | 18,147 | 2019-01-02 | 2019-12-31 | 66 | `78f51d653bb2` |
| `NSE_data_all_stocks_2020_to_jun30.csv` | 729,602 | 8,733 | 2020-01-02 | 2020-06-30 | 64 | `68138c29405a` |
| `NSE_data_all_stocks_2021_upto_31dec2021.csv` | 1,550,258 | 17,746 | 2021-01-04 | 2021-12-31 | 64 | `d0a451fc3e64` |
| `NSE_data_all_stocks_2022.csv` | 1,390,082 | 16,806 | 2022-01-03 | 2022-12-30 | 66 | `c6b58ea83c8f` |
| `NSE_data_all_stocks_2023.csv` | 1,474,887 | 17,274 | 2023-01-03 | 2023-12-29 | 66 | `9050850c15cc` |
| `NSE_data_all_stocks_2024.csv` | 1,560,791 | 18,119 | 2024-01-02 | 2024-12-31 | 67 | `16c34c7b4fe8` |
| `NSE_data_all_stocks_2025_jan_to_oct.csv` | 1,247,718 | 15,114 | 2025-01-02 | 2025-10-31 | 67 | `7241047984db` |
| `NSE_data_all_stocks_2026_upto_jun.csv` | 773,923 | 9,280 | 2026-01-02 | 2026-06-30 | 71 | `bfc83a381e11` |

\* a misdated block; see Defects. Rows include index rows; codes count equities only. Sizes
and hashes are for the files with LF line endings, as git stores them; a Windows checkout and
the Mendeley downloads have CRLF line endings, which `acquire` converts before hashing (D-41).
Sector files (`NSE_data_stock_market_sectors_*.csv`, 62-77 rows each) map codes to sectors,
with two header spellings (`SECTOR, CODE, NAME` and `Sector, Stock_code, Stock_name`).

## Format (answers the *(verify)* items in §6.2)

| Column (header case varies) | Canonical column | Notes |
| --- | --- | --- |
| `Date` / `DATE` | `session_date` | Three formats: `02-Jan-25` (2013 on), `1/2/2007` month first (2007-2012) |
| `Code` / `CODE` | `ticker` | After alias mapping; codes starting with `^` are index levels |
| `Name` / `NAME` | securities table | Company names change over time; the latest is shown |
| `Day Price` | `close` | The official price, a session VWAP (Rules 7.6.1, 7.6.6) |
| `Previous` | `prev_close_reported` | **Present** (missing in 22 rows, four of them first days of 2026 listings) |
| `Day Low`, `Day High` | `low`, `high` | **Present**; set to null when the security did not trade |
| (none) | `open` | **Not published**: always null |
| `Volume` | `volume` | `-` means no trades (0); thousands separators |
| (none) | `turnover` | **Not published**: always null, so VOL-01 does not apply and the universe uses volume x close |
| `12m Low`, `12m High`, `Change`, `Change%` | not used | `Change%` has no sign in older files |
| `Adjust` / `Adjusted Price` | not used | Back-adjusted prices for about 13% of rows; v2 does not back-adjust (§6.7) |

Index levels in the files: `^NASI` (from 25 Feb 2008), `^N20I`, `^N25I` (from Oct 2015),
`^N10I` (from Sep 2023), `^FNK15`, `^FNK25` (2013-2021), `^ZKEQTK`, `^ZKEQTU` (from Jul 2018),
`^NBDI` and `^NBSI`. NASI is used for the market features (§8.2).

## Defects and how each is handled

| Finding | Handling | Count |
| --- | --- | --- |
| Three blocks in the 2009 file dated 29 Jan, 2 Apr and 8 Oct sit where 21 Jan, 4 Feb and 10 Aug belong (two are day-month swaps) | `redate` rules R2009-01 to R2009-03 in `reference/corrections.yaml`; prices chain exactly through each block | 158 rows |
| The 2017 file has a block dated Saturday 9 May 2015 that belongs to 9 May 2017 | `redate` rule R2017-01 | 70 rows |
| Identical duplicate rows | Dropped automatically (after the redates, every remaining duplicate is identical) | 64 rows |
| Blank lines (`,,,,`) at the end of the 2014 and 2018 files | Skipped and counted | 2 |
| A row without a price (MSC, 16 Oct 2019) | SCH-02: excluded | 1 |
| Moves beyond ±10.5% (splits, bonus and rights issues, listings, errors, moves across a data gap) | PRC-01 events: excluded from labels and feature windows (§6.7) | 416 |
| No data from 1 Jul to 31 Dec 2020 | Missing sessions; never filled; the gap guard excludes nearby rows (§8.4) | 129 sessions |
| No data from 3 Nov to 31 Dec 2025: the 2025 file ends on 31 October and the 2026 file starts on 2 January | Missing sessions, handled the same way | 40 sessions |
| 26 other scheduled weekdays with no data | Missing sessions | 26 |
| 3 and 4 Jan 2008 quote only 8 and 27 securities | MKT-01: market features null for those sessions | 2 |
| 27 Dec 2010 and 27 Dec 2011 traded in full | Held sessions in the calendar | 2 |
| The 2007-2012 files use old tickers (BBK, BERG, C&G, CFC, ICDC, NIC, FIRE, PAFR, CFCI) | `former_tickers` in `reference/securities.csv`; confirmed from prices (the last 2012 close equals the first 2013 "Previous") | 9 tickers |
| Rights lines (`-R`), preference shares (`-P4`, `-P7`), ETFs (GLD, SMWF) and REITs (FAHR, LAPR, ALP) | `instrument_type` in `reference/securities.csv`, or inferred from the sector file for ALP: display only, never in the forecast universe | 17 lines |
| Four securities first quoted in 2026: KPC (10 Mar), ALP (11 Mar), FMLY (23 Jun) and TRFC (29 Jun); the source cuts off the names of ALP and TRFC | Shown as the source names them; none has the 500 sessions of history the forecast universe needs | 4 securities |

The 2026 file has no duplicate, misdated or weekend rows, and its 122 sessions match the
trading calendar exactly, which confirms the 2026 Idd-ul-Fitr (20 March) and Idd-ul-Azha
(27 May) closures.

After corrections the canonical panel has 92 securities (75 ordinary shares), 4,682 held
sessions from 2 Jan 2007 to 30 Jun 2026, and 293,848 bars, of which 12,661 are carried
forward. These numbers are regenerated in `data/reports/data-audit.md` on every run.
